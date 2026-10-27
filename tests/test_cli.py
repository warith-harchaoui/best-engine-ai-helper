"""
Tests for best_engine_ai_helper.cli.

Uses Click's CliRunner, so no real subprocess or server is spawned. The
read-only commands run against real detection and the bundled catalog; the
side-effectful ones (refresh, pull, validate) have their network / detection /
ollama layer patched so the tests stay offline and never touch the real user
config under ~/.best-engine-ai-helper. Each test groups several related
commands/scenarios into one functional check rather than one test per
command, so the suite stays small while covering the same ground.
"""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest
import requests
import yaml
from click.testing import CliRunner

from best_engine_ai_helper import __version__
from best_engine_ai_helper.cli import cli

# Every command this CLI ships, spelled as the user types it. Written down
# rather than read back from the group, because a list the test re-derives
# cannot notice a command lost to a bad merge or renamed by half. This is the
# inventory the deleted argparse twin's parity tests used to hold: they were
# the only place the command set was pinned, so it is pinned here now, against
# the one surface that remains.
EXPECTED_COMMANDS = {
    "detect",
    "recommend",
    "resolve",
    "report",
    "usages list",
    "usages show",
    "usages resolve",
    "catalog show",
    "catalog update",
    "hardware show",
    "hardware update",
    "pull",
    "storage",
    "providers",
    "doctor",
    "validate",
    "gui",
    "env",
    "activity",
    "airllm status",
    "airllm plan",
    "airllm compare",
    "airllm prepare",
}


def _command_paths(group: click.Group, prefix: str = "") -> set[str]:
    """Every leaf command path under `group`, space-separated."""
    paths: set[str] = set()
    for name, command in group.commands.items():
        if isinstance(command, click.Group):
            paths |= _command_paths(command, f"{prefix}{name} ")
        else:
            paths.add(f"{prefix}{name}")
    return paths


def test_the_command_inventory_and_every_help_screen(runner: CliRunner) -> None:
    """The command set is what it claims, every --help renders, -h and -V work.

    Neither short flag existed before 1.9.0: `--help` worked and `-h` was
    "No such option", `--version` worked and `-V` did not. And `--version`
    read the *installed* distribution metadata, so an editable checkout
    answered with whatever release was last pip-installed rather than with
    the version in the tree -- which is precisely the question somebody
    debugging asks it.
    """
    assert _command_paths(cli) == EXPECTED_COMMANDS

    # A --help that raises is invisible from every other test in this file,
    # since none of them asks for one.
    for path in sorted(EXPECTED_COMMANDS | {"catalog", "hardware", "usages", "airllm"}):
        res = runner.invoke(cli, [*path.split(), "--help"])
        assert res.exit_code == 0, f"{path} --help -> {res.exit_code}\n{res.output}"
        assert res.output.strip()

    short = runner.invoke(cli, ["-h"])
    assert short.exit_code == 0
    assert short.output == runner.invoke(cli, ["--help"]).output

    for flag in ("-V", "--version"):
        version = runner.invoke(cli, [flag])
        assert version.exit_code == 0, flag
        assert __version__ in version.output, flag
        assert "best-engine-ai-helper" in version.output, flag


def test_read_only_and_report_commands(runner: CliRunner, tmp_path: Path) -> None:
    cases = [
        (["detect"], "platform"),
        (["recommend"], ""),
        (["recommend", "--kind", "llm"], "LLM"),
        (["recommend", "--kind", "vlm"], "VLM"),
        (["recommend", "--headroom", "0.5"], ""),
        (["recommend", "--live"], ""),
        (["catalog", "show"], "qwen3-vl:8b"),
        (["hardware", "show"], "Apple M2 Max"),
    ]
    for args, needle in cases:
        result = runner.invoke(cli, args)
        assert result.exit_code == 0, f"{args} -> {result.exit_code}\n{result.output}"
        assert result.output.strip() and needle in result.output, args

    live = runner.invoke(cli, ["report", "--task", "write copy", "--live"])
    assert live.exit_code == 0
    assert "Server load (live, at recommendation time)" in live.stdout

    data = json.loads(runner.invoke(cli, ["detect"]).output)
    # "hardware" is os_helper's raw CPU/GPU facts, distinct from the inference
    # budgets under "memory"; only the deleted argparse test asserted it.
    assert {"platform", "chip_vendor", "memory", "hardware"} <= data.keys()
    assert set(data["memory"]) == {"unified_gb", "vram_gb", "ram_gb"}
    assert data["memory"]["ram_gb"] > 0

    md = runner.invoke(cli, ["report", "--task", "write python code"])
    assert md.exit_code == 0 and "# Best local engine" in md.output
    # No --task here: parse_task logs a WARNING (see recommend.py), and
    # CliRunner's `.output` merges stdout+stderr, so parse strictly from
    # `.stdout` — the CLI's real machine-readable-JSON contract is stdout only.
    js = runner.invoke(cli, ["report", "--format", "json"])
    assert js.exit_code == 0 and "recommendations" in json.loads(js.stdout)
    out = runner.invoke(cli, ["report", "--out", str(tmp_path / "r")])
    assert out.exit_code == 0
    assert (tmp_path / "r.md").is_file() and (tmp_path / "r.json").is_file()

    brief = tmp_path / "llm.brief.yaml"
    brief.write_text(yaml.safe_dump({"kind": "llm", "task": "write python code"}))
    engine_out = tmp_path / "llm.engine.yaml"
    resolved = runner.invoke(cli, ["resolve", "--brief", str(brief), "--out", str(engine_out)])
    assert resolved.exit_code == 0
    assert f"Wrote {engine_out}" in resolved.output
    assert engine_out.is_file() and "backend" in yaml.safe_load(engine_out.read_text())

    missing = runner.invoke(cli, ["resolve", "--brief", str(tmp_path / "nope.yaml")])
    assert missing.exit_code == 1
    assert "not found" in missing.output

    # A brief that reaches engine.resolve() but fails there (not a missing
    # file) is reported readably too, not as a raw traceback. No 'model' asks
    # for a cloud auto-pick; a provider absent from the catalog can't serve it.
    bad_cloud_brief = tmp_path / "bad_cloud.brief.yaml"
    bad_cloud_brief.write_text(
        yaml.safe_dump({"mode": "cloud", "provider": "not-a-real-provider", "kind": "llm"})
    )
    resolve_failed = runner.invoke(cli, ["resolve", "--brief", str(bad_cloud_brief)])
    assert resolve_failed.exit_code == 1
    assert "resolve failed" in resolve_failed.output

    # An explicit provider + model still pins exactly that model (the
    # pre-existing, no-catalog-lookup manual path).
    pinned_cloud_brief = tmp_path / "pinned_cloud.brief.yaml"
    pinned_cloud_brief.write_text(
        yaml.safe_dump({"mode": "cloud", "provider": "openai", "model": "gpt-4o", "kind": "llm"})
    )
    pinned_out = tmp_path / "pinned.engine.yaml"
    pinned_resolved = runner.invoke(
        cli, ["resolve", "--brief", str(pinned_cloud_brief), "--out", str(pinned_out)]
    )
    assert pinned_resolved.exit_code == 0
    assert yaml.safe_load(pinned_out.read_text())["llm"]["model"] == "gpt-4o"

    # No 'model': the CLI auto-picks the best paid model from pricing.yaml.
    auto_cloud_brief = tmp_path / "auto_cloud.brief.yaml"
    auto_cloud_brief.write_text(
        yaml.safe_dump({"mode": "cloud", "provider": "openai", "kind": "llm", "task": "write SQL"})
    )
    auto_out = tmp_path / "auto.engine.yaml"
    auto_resolved = runner.invoke(
        cli, ["resolve", "--brief", str(auto_cloud_brief), "--out", str(auto_out)]
    )
    assert auto_resolved.exit_code == 0
    auto_engine = yaml.safe_load(auto_out.read_text())
    assert auto_engine["backend"] == "openai" and auto_engine["llm"]["model"]

    # `report`'s default best-cloud-pick section needs no API key/network.
    cloud_report = runner.invoke(cli, ["report", "--task", "write python code"])
    assert cloud_report.exit_code == 0
    assert "Best cloud engine" in cloud_report.output
    assert "Best cloud LLM" in cloud_report.output

    no_cloud_report = runner.invoke(cli, ["report", "--task", "write python code", "--no-cloud"])
    assert no_cloud_report.exit_code == 0
    assert "Best cloud engine" not in no_cloud_report.output

    cloud_json = runner.invoke(cli, ["report", "--task", "write python code", "--format", "json"])
    cloud_data = json.loads(cloud_json.stdout)
    assert "cloud" in cloud_data and cloud_data["cloud"]["recommendations"]["llm"]["chosen"]


def test_activity_empty_and_populated(runner: CliRunner, tmp_path: Path) -> None:
    from unittest.mock import patch

    from best_engine_ai_helper import llm, observe

    # A test-owned ledger, enabled up front, so `activity_cmd`'s "no active
    # ledger -> open the default path" fallback never touches the real
    # ~/.best-engine-ai-helper/usage.db (conftest's autouse fixture sets
    # BEST_ENGINE_NO_LEDGER=1, so the group callback's own auto-enable stays
    # a no-op).
    ledger = observe.enable(str(tmp_path / "usage.db"))

    empty = runner.invoke(cli, ["activity"])
    assert empty.exit_code == 0 and "No calls recorded yet." in empty.stdout

    empty_json = runner.invoke(cli, ["activity", "--format", "json"])
    assert json.loads(empty_json.stdout)["total_calls"] == 0

    # Record one call, then check both output formats reflect it.
    with patch("requests.post") as p:
        p.return_value.json.return_value = {"response": "hi"}
        p.return_value.raise_for_status.return_value = None
        llm.chat("hello", model="qwen3:8b")

    table = runner.invoke(cli, ["activity"])
    assert table.exit_code == 0
    assert "Total calls: 1" in table.stdout and "qwen3:8b" in table.stdout

    as_json = runner.invoke(cli, ["activity", "--format", "json"])
    data = json.loads(as_json.stdout)
    assert data["total_calls"] == 1 and data["total_cost_usd"] == 0.0

    # A failed call renders a "Recent errors" table too, not just the tallies.
    with patch("requests.post", side_effect=requests.ConnectionError("no server")):
        try:
            llm.chat("hello", model="qwen3:8b")
        except RuntimeError:
            pass
    with_error = runner.invoke(cli, ["activity"])
    assert with_error.exit_code == 0
    assert "Recent errors:" in with_error.stdout
    ledger.close()


def test_usages_subcommands(runner: CliRunner, tmp_path: Path) -> None:
    listing = runner.invoke(cli, ["usages", "list"])
    assert listing.exit_code == 0
    assert "Families" in listing.output and "Profiles" in listing.output
    assert "text2sql" in listing.output and "F1" in listing.output

    shown = runner.invoke(cli, ["usages", "show", "text2sql"])
    assert shown.exit_code == 0
    assert "Needs (selection criteria):" in shown.output
    assert "structured_output" in shown.output

    unknown_show = runner.invoke(cli, ["usages", "show", "not-a-real-profile"])
    assert unknown_show.exit_code == 1

    out = tmp_path / "llm.engine.yaml"
    resolved = runner.invoke(cli, ["usages", "resolve", "text2sql", "--out", str(out)])
    assert resolved.exit_code == 0
    assert "text2sql: backend" in resolved.output
    assert out.is_file()

    family = runner.invoke(cli, ["usages", "resolve", "--family", "F1"])
    assert family.exit_code == 0
    assert "F1: backend" in family.output

    no_target = runner.invoke(cli, ["usages", "resolve"])
    assert no_target.exit_code == 1
    assert "NAME or --family" in no_target.output

    unknown_resolve = runner.invoke(cli, ["usages", "resolve", "not-a-real-profile"])
    assert unknown_resolve.exit_code == 1
    assert "resolve failed" in unknown_resolve.output


def test_catalog_and_hardware_update(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from best_engine_ai_helper import catalog, hardware
    from best_engine_ai_helper.sources import apxml

    cache = tmp_path / "catalog_cache.yaml"
    monkeypatch.setattr(catalog, "_CACHE_PATH", cache)
    monkeypatch.setattr(
        apxml,
        "fetch_open_weight_models",
        lambda **kw: [
            {
                "slug": "qwen3-8b",
                "kind": "llm",
                "size_b": 8.0,
                "ram_gb": 6.0,
                "vllm_id": "Qwen/Qwen3-8B",
                "url": "https://apxml.com/models/qwen3-8b",
            }
        ],
    )
    ok = runner.invoke(cli, ["catalog", "update"])
    assert ok.exit_code == 0 and cache.exists()
    written = yaml.safe_load(cache.read_text())
    assert written[0]["id"] == "qwen3-8b" and written[0]["source"] == "apxml"

    # An empty feed leaves the cache untouched and reports failure.
    cache.unlink()
    monkeypatch.setattr(apxml, "fetch_open_weight_models", lambda **kw: [])
    empty = runner.invoke(cli, ["catalog", "update"])
    assert empty.exit_code != 0 and not cache.exists()

    # A network/parse failure is reported readably, not as a raw traceback.
    def _boom(**kw: object) -> None:
        raise ConnectionError("ApXML unreachable")

    monkeypatch.setattr(apxml, "fetch_open_weight_models", _boom)
    network_fail = runner.invoke(cli, ["catalog", "update"])
    assert network_fail.exit_code != 0
    assert "catalog update failed" in network_fail.output

    hw_cache = tmp_path / "hardware_cache.yaml"
    monkeypatch.setattr(hardware, "_HW_CACHE_PATH", hw_cache)
    monkeypatch.setattr(
        hardware,
        "detect_local_entry",
        lambda *a, **k: {
            "chip": "Apple M2 Max",
            "vendor": "apple",
            "memory_gb": 32.0,
            "ollama_usable_gb": 28.0,
            "source": "detected",
            "fetched_at": "2026-08-01",
        },
    )
    hw_ok = runner.invoke(cli, ["hardware", "update"])
    assert hw_ok.exit_code == 0
    assert yaml.safe_load(hw_cache.read_text())[0]["chip"] == "Apple M2 Max"

    # Nothing detectable -> cache untouched, non-zero exit.
    hw_cache.unlink()
    monkeypatch.setattr(hardware, "detect_local_entry", lambda *a, **k: None)
    hw_none = runner.invoke(cli, ["hardware", "update"])
    assert hw_none.exit_code != 0 and not hw_cache.exists()


def _patch_gates(monkeypatch: pytest.MonkeyPatch, vlm: bool, prose: bool) -> None:
    from best_engine_ai_helper import pull, validate_llm, validate_vlm

    monkeypatch.setattr(pull, "ollama_pull", lambda tag, **k: True)
    monkeypatch.setattr(validate_vlm, "validate", lambda chat: vlm)
    monkeypatch.setattr(validate_llm, "validate", lambda chat: prose)


def test_pull_validate_env(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from best_engine_ai_helper import catalog, detect, pull, validate_llm, validate_vlm

    _patch_gates(monkeypatch, vlm=True, prose=True)
    written: dict[str, object] = {}
    monkeypatch.setattr(
        pull, "write_env", lambda **kw: (written.update(kw), tmp_path / "env.sh")[1]
    )
    passed = runner.invoke(cli, ["pull"])
    assert passed.exit_code == 0 and "Both gates passed" in passed.output
    assert written["text_model"]  # the chosen tag was persisted

    # On an M2-Max-like machine a 48 GB model fits memory but crawls (~5 tok/s);
    # a 10 GB model clears the comfort floor (~26 tok/s). pull must try the
    # comfortable model first even though the slow one scores higher.
    monkeypatch.setattr(
        detect, "available_memory", lambda: {"unified_gb": 96.0, "vram_gb": None, "ram_gb": 96.0}
    )
    monkeypatch.setattr(
        detect,
        "compute_profile",
        lambda: {"accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400.0},
    )
    monkeypatch.setattr(
        catalog,
        "load_catalog",
        lambda: [
            {
                "id": "big-slow",
                "kind": "vlm",
                "ram_gb": 48.0,
                "benchmarks": {"vision": 90, "general": 90},
                "structured_output": True,
            },
            {
                "id": "small-fast",
                "kind": "vlm",
                "ram_gb": 10.0,
                "benchmarks": {"vision": 80, "general": 80},
                "structured_output": True,
            },
        ],
    )
    pulled: list[str] = []
    monkeypatch.setattr(pull, "ollama_pull", lambda tag, **k: (pulled.append(tag), True)[1])
    monkeypatch.setattr(pull, "write_env", lambda **kw: tmp_path / "env.sh")
    comfortable = runner.invoke(cli, ["pull"])
    assert comfortable.exit_code == 0
    assert pulled[0] == "small-fast"  # comfortable model tried first, not big-slow

    # A failed VLM gate removes the candidate and exits non-zero.
    _patch_gates(monkeypatch, vlm=False, prose=True)
    removed: list[str] = []
    monkeypatch.setattr(pull, "ollama_rm", lambda tag: (removed.append(tag), True)[1])
    failed = runner.invoke(cli, ["pull"])
    assert failed.exit_code == 1 and removed  # failed candidates are cleaned up

    # --vllm prints the serve command without ever calling ollama_pull.
    monkeypatch.setattr(pull, "ollama_pull", lambda *a, **k: pytest.fail("--vllm must not pull"))
    vllm = runner.invoke(cli, ["pull", "--vllm"])
    assert vllm.exit_code == 0 and "vllm serve" in vllm.output

    # `env` reads ~/.best-engine-ai-helper/env.sh with no override, so point
    # Path.home() at a tmp dir for isolation -- otherwise this test's
    # "unconfigured" case silently depends on the REAL developer machine
    # never having run a real `pull` before (a real, if latent, isolation gap).
    import pathlib

    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", lambda: fake_home)

    # validate/env with nothing configured: both explain what to run.
    monkeypatch.delenv("BEST_LLM_TEXT", raising=False)
    monkeypatch.delenv("SPREZZATURE_LLM_TEXT", raising=False)
    for cmd in (["validate"], ["env"]):
        unconfigured = runner.invoke(cli, cmd)
        combined = (unconfigured.output or "") + (unconfigured.stderr or "")
        assert unconfigured.exit_code != 0 and combined.strip()

    # env with a real env.sh in place prints it verbatim.
    env_dir = fake_home / ".best-engine-ai-helper"
    env_dir.mkdir()
    (env_dir / "env.sh").write_text("export BEST_LLM_TEXT=qwen3:8b\n")
    configured_env = runner.invoke(cli, ["env"])
    assert configured_env.exit_code == 0
    assert configured_env.output == "export BEST_LLM_TEXT=qwen3:8b\n"

    # validate with a model configured and both gates passing.
    monkeypatch.setenv("BEST_LLM_TEXT", "qwen3:8b")
    monkeypatch.setattr(validate_vlm, "validate", lambda chat: True)
    monkeypatch.setattr(validate_llm, "validate", lambda chat: True)
    configured = runner.invoke(cli, ["validate"])
    assert configured.exit_code == 0
    assert "pass" in configured.output.lower()

    import uvicorn

    gui_calls: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: gui_calls.update(app=app, **kw))
    gui_result = runner.invoke(cli, ["gui", "--host", "0.0.0.0", "--port", "9000"])
    assert gui_result.exit_code == 0
    assert gui_calls["app"] == "best_engine_ai_helper.api:app"
    assert (gui_calls["host"], gui_calls["port"]) == ("0.0.0.0", 9000)


def test_report_sizes_against_the_backend_this_machine_would_serve_with(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`report` must agree with the engine file `resolve` would build.

    It used to size every pick against Ollama Q4 whatever the machine was, so
    on the one configuration where `resolve` picks vLLM — Linux with a
    discrete GPU, the documented production case — the two disagreed, and the
    report was the optimistic one. The README's claim that "vLLM picks are
    sized against full FP16 weights, so a vLLM pick is realistic on the real
    GPU" was true of `resolve` and false here.
    """
    from best_engine_ai_helper import detect as _detect

    monkeypatch.setattr(_detect, "platform_name", lambda: "linux")
    monkeypatch.setattr(_detect, "chip_vendor", lambda: "nvidia")

    auto = runner.invoke(cli, ["report", "--format", "json", "--task", "write python code"])
    assert auto.exit_code == 0
    forced = runner.invoke(
        cli,
        ["report", "--format", "json", "--task", "write python code", "--backend", "vllm"],
    )
    assert forced.exit_code == 0
    # 'auto' on Linux + a discrete GPU resolves to vLLM, so the two agree.
    assert json.loads(auto.output) == json.loads(forced.output)

    # And an explicit Ollama run is genuinely different — otherwise the
    # assertion above would pass on a backend flag that does nothing.
    ollama = runner.invoke(
        cli,
        ["report", "--format", "json", "--task", "write python code", "--backend", "ollama"],
    )
    assert ollama.exit_code == 0
    assert json.loads(ollama.output) != json.loads(auto.output)


def test_report_prefers_a_model_already_on_disk(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The already-pulled tiebreak only ever fired through `engine.resolve`.

    `report` never passed `installed`, so the whole feature was invisible from
    the command most people run. Asserted through the report's own
    `installed` flag rather than the chosen id, since which models tie depends
    on the bundled catalog.
    """
    from best_engine_ai_helper import pull as _pull

    monkeypatch.setattr(_pull, "installed_tags", lambda *a, **k: {"qwen3:8b"})
    res = runner.invoke(
        cli, ["report", "--format", "json", "--task", "write copy", "--backend", "ollama"]
    )
    assert res.exit_code == 0
    rows = json.loads(res.output)["recommendations"]["llm"]["candidates"]
    assert any(r["id"] == "qwen3:8b" and r["installed"] for r in rows)
    assert not any(r["installed"] for r in rows if r["id"] != "qwen3:8b")


def test_providers_lists_every_provider_and_never_prints_a_key(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The routing claim is only worth something if you can see it applied.

    `provider_status` existed and was served at `/api/providers`, but only the
    GUI could ask: there was no CLI command, so the surface most people use
    could not answer "why is this provider not being offered to me".
    """
    from best_engine_ai_helper import llm as _llm

    monkeypatch.setattr(
        _llm, "_cloud_api_key", lambda spec: "sk-secret" if "MISTRAL" in spec["api_key_env"] else ""
    )

    res = runner.invoke(cli, ["providers"])
    assert res.exit_code == 0
    # Every shipped provider is accounted for, usable or not.
    for provider in ("mistral", "openai", "anthropic", "gemini"):
        assert provider in res.output
    # The variable to set is named, which is what makes the row actionable.
    assert "OPENAI_API_KEY" in res.output
    # The key value itself never appears.
    assert "sk-secret" not in res.output
    # The tally line that tells you how many of them you can actually use.
    assert "provider(s) usable" in res.output

    as_json = runner.invoke(cli, ["providers", "--json"])
    assert as_json.exit_code == 0
    rows = json.loads(as_json.output)
    assert {r["provider"] for r in rows} >= {"mistral", "openai", "anthropic", "gemini"}
    assert all("key_env" in r and "available" in r for r in rows)
    assert "sk-secret" not in as_json.output


def test_a_missing_cloud_key_is_not_an_error(
    runner: CliRunner, caplog: pytest.LogCaptureFixture
) -> None:
    """Not holding a key you do not use is the ordinary state, not a failure.

    `osh.get_config` logs at ERROR before raising when a key is absent, so
    `providers` printed one red line per unconfigured provider. A red that
    lies costs the same credibility as a green that lies.
    """
    import logging

    with caplog.at_level(logging.ERROR, logger="os_helper"):
        res = runner.invoke(cli, ["providers"])
    assert res.exit_code == 0
    assert not [r for r in caplog.records if "cloud API key" in r.message]


def test_a_resolved_model_with_no_throughput_figure_still_prints(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A machine whose bandwidth cannot be read must not crash the printout.

    `est_tokens_per_s` is None whenever no measurement exists and no memory
    bandwidth figure could be derived -- the ordinary state inside a CI
    container, and the reason this was found there rather than here. The
    printout built the "~43 tok/s" string *before* checking there was a
    number, so `usages resolve` died on `None.__format__` and took the rest
    of the command with it. The defect was in both CLI surfaces back when
    there were two; only the click one is left to guard.
    """
    from best_engine_ai_helper import cli as _cli

    descriptor = {
        "usage": "text2sql",
        "backend": "ollama",
        "llm": {"model": "qwen3:8b", "ram_gb": 6.5, "est_tokens_per_s": None},
    }
    _cli._echo_resolved(descriptor, None)
    out = capsys.readouterr().out
    # The model is still named, with its memory cost; only the speed clause is
    # dropped, because there is no speed to report.
    assert "llm=qwen3:8b (6.5 GB)" in out
    assert "tok/s" not in out

    # And when the figure does exist it is still printed, measured figures
    # marked with the "*" the report documents.
    measured = {
        "family": "F1",
        "backend": "ollama",
        "llm": {
            "model": "qwen3:8b",
            "ram_gb": 6.5,
            "est_tokens_per_s": 42.4,
            "tps_basis": "measured",
        },
    }
    _cli._echo_resolved(measured, None)
    assert "42* tok/s" in capsys.readouterr().out


def test_storage_and_doctor_commands(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two capacity-planning commands print a report and gate correctly.

    Both were reachable only by hand before: `storage` answers "what fits",
    `doctor` answers "does what we resolved still run", and neither had a
    test through the CLI, so the formatting around a correct library answer
    was unverified. `installed_tags` is pinned rather than probed so the
    already-here branch runs on a machine with no daemon, which is every CI
    container and most laptops at rest.
    """
    from best_engine_ai_helper import pull as _pull

    monkeypatch.setattr(_pull, "installed_tags", lambda *a, **k: {"qwen3:8b"})

    res = runner.invoke(cli, ["storage"])
    assert res.exit_code == 0, res.output
    assert "disk   :" in res.output and "memory :" in res.output
    assert "already here: qwen3:8b" in res.output
    assert "Could be pulled into the space left" in res.output
    assert "Can be held in memory at the same time" in res.output

    # vLLM sizes against the heavier FP16 footprint and never asks Ollama
    # what it holds, so the already-here line has nothing to report.
    res = runner.invoke(cli, ["storage", "--backend", "vllm"])
    assert res.exit_code == 0, res.output
    assert "already here" not in res.output

    # No engine file is a finding, not a crash, and it exits non-zero.
    res = runner.invoke(cli, ["doctor", "--directory", str(tmp_path)])
    assert res.exit_code == 1
    assert "No engine file at" in res.output

    # The all-clear path, with the daemon's answer canned: `doctor` reports
    # what `diagnose` found, it does not re-derive it.
    from best_engine_ai_helper import engine as _engine

    monkeypatch.setattr(
        _engine,
        "diagnose",
        lambda directory, timeout=1.5: {
            "engine_path": str(tmp_path / "llm.engine.yaml"),
            "backend": "ollama",
            "daemon_reachable": True,
            "served": ["qwen3:8b"],
            "findings": [],
            "ok": True,
        },
    )
    res = runner.invoke(cli, ["doctor", "--directory", str(tmp_path)])
    assert res.exit_code == 0, res.output
    assert "daemon      : reachable" in res.output
    assert "serves      : qwen3:8b" in res.output
    assert "Everything the engine file names can be served right now." in res.output


# ---------------------------------------------------------------------------
# Layer streaming: the three commands, and the backend flag on two others
# ---------------------------------------------------------------------------


def test_airllm_status_reports_the_decision_and_how_to_act_on_it(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command exists to be read by a human who then has something to do."""
    from best_engine_ai_helper import offload as _offload

    monkeypatch.setattr(_offload, "available", lambda: False)

    res = runner.invoke(cli, ["airllm", "status"])
    assert res.exit_code == 0, res.output
    assert "Layer streaming (airllm)" in res.output
    assert "NOT installed" in res.output
    # A blocker nobody can act on is just a refusal, so the install command is
    # part of the output rather than something to go and look up.
    assert _offload.INSTALL_HINT in res.output

    # `--request always` asks the policy a different question, and the answer
    # must change with it rather than being a fixed capability dump.
    monkeypatch.setattr(_offload, "available", lambda: True)
    forced = runner.invoke(cli, ["airllm", "status", "--request", "always", "--json"])
    assert forced.exit_code == 0, forced.output
    payload = json.loads(forced.output)
    assert payload["decision"]["request"] == "always"
    assert payload["decision"]["trigger"] in ("manual", "disabled")
    assert payload["memory_budget_gb"] > 0


def test_airllm_plan_ranks_candidates_in_seconds_per_token(runner: CliRunner) -> None:
    """Biggest runnable first, and priced in the unit that is honest here."""
    res = runner.invoke(cli, ["airllm", "plan", "--kind", "llm"])
    assert res.exit_code == 0, res.output
    assert "s/token" in res.output
    assert "shard_gb" in res.output
    # Whatever this machine is, the table has to say whether each row runs.
    assert "runs" in res.output


def test_airllm_prepare_fails_readably_without_the_runtime(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command's whole job is the download, so a missing runtime is its first error."""
    from best_engine_ai_helper import offload as _offload

    def _no_runtime(*_a: object, **_k: object) -> None:
        raise ImportError(f"needs the airllm runtime: {_offload.INSTALL_HINT}")

    monkeypatch.setattr(_offload, "load", _no_runtime)

    res = runner.invoke(cli, ["airllm", "prepare", "--model", "meta-llama/Llama-3.3-70B-Instruct"])
    assert res.exit_code == 1
    assert "airllm" in res.output


def test_recommend_backend_airllm_switches_the_table_and_the_floor(runner: CliRunner) -> None:
    """Streaming candidates are a different table, not the same one relabelled."""
    plain = runner.invoke(cli, ["recommend", "--kind", "llm"])
    streamed = runner.invoke(cli, ["recommend", "--kind", "llm", "--backend", "airllm"])

    assert plain.exit_code == 0 and streamed.exit_code == 0, streamed.output
    assert "(ollama)" in plain.output and "(airllm)" in streamed.output
    # The interactive comfort floor describes a resident model; judging a
    # streamed one by it would mark every row uncomfortable and say nothing.
    assert "Batch floor: 0.01 tok/s" in streamed.output
    assert "Memory is one layer shard" in streamed.output
    # And the columns differ, because `ram_gb` would be a lie in this table.
    assert "shard_gb" in streamed.output and "shard_gb" not in plain.output


def test_resolve_accepts_the_streaming_backend(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: a brief in, a streaming engine file out."""
    from best_engine_ai_helper import offload as _offload

    monkeypatch.setattr(_offload, "available", lambda: True)
    brief = tmp_path / "llm.brief.yaml"
    brief.write_text("kind: llm\ntask: general assistant\nstructured_output: false\n")

    res = runner.invoke(cli, ["resolve", "--brief", str(brief), "--backend", "airllm"])
    assert res.exit_code == 0, res.output
    assert "backend: airllm" in res.output

    written = yaml.safe_load((tmp_path / "llm.engine.yaml").read_text())
    assert written["backend"] == "airllm"
    assert written["llm"]["streaming"] is True
    assert written["llm"]["seconds_per_token"] > 0


def test_airllm_compare_prices_both_backends_for_the_same_answer(runner: CliRunner) -> None:
    """The decision the backend forces, in one screen.

    Tokens per second cannot be read across these backends — 26 and 0.024 do
    not sit on a scale a person reasons about. Seconds for the same answer do,
    and the verdict line says which side wins on this machine.
    """
    res = runner.invoke(cli, ["airllm", "compare", "--tokens", "300"])
    assert res.exit_code == 0, res.output
    assert "vs airllm, for a 300-token answer" in res.output
    assert "answer" in res.output  # the shared unit
    # Both sides are present, each ranked by its own backend's rules.
    assert "ollama" in res.output and "airllm" in res.output
    # And a verdict a human can act on, whichever way it goes.
    assert any(
        phrase in res.output
        for phrase in ("Stay native", "benchmark points", "only option", "Nothing can be streamed")
    )


def test_airllm_compare_json_carries_the_timings_behind_the_verdict(runner: CliRunner) -> None:
    """A consumer must be able to re-derive the conclusion, not just read it."""
    res = runner.invoke(cli, ["airllm", "compare", "--tokens", "120", "--json"])
    assert res.exit_code == 0, res.output

    report = json.loads(res.output)
    assert report["new_tokens"] == 120
    assert set(report) >= {"native", "streamed", "verdict", "quality_gain", "slowdown"}
    for plan in report["streamed"]["rows"]:
        # Seconds per pass is the atom; the answer time is the product. Both
        # travel, so the arithmetic is checkable from the outside.
        assert "seconds_per_pass" in plan
        assert "answer_seconds" in plan
