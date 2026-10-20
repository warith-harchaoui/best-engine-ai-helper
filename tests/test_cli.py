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

import pytest
import requests
import yaml
from click.testing import CliRunner

from best_engine_ai_helper.cli import main


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
        result = runner.invoke(main, args)
        assert result.exit_code == 0, f"{args} -> {result.exit_code}\n{result.output}"
        assert result.output.strip() and needle in result.output, args

    live = runner.invoke(main, ["report", "--task", "write copy", "--live"])
    assert live.exit_code == 0
    assert "Server load (live, at recommendation time)" in live.stdout

    data = json.loads(runner.invoke(main, ["detect"]).output)
    assert {"platform", "chip_vendor", "memory"} <= data.keys()
    assert set(data["memory"]) == {"unified_gb", "vram_gb", "ram_gb"}
    assert data["memory"]["ram_gb"] > 0

    md = runner.invoke(main, ["report", "--task", "write python code"])
    assert md.exit_code == 0 and "# Best local engine" in md.output
    # No --task here: parse_task logs a WARNING (see recommend.py), and
    # CliRunner's `.output` merges stdout+stderr, so parse strictly from
    # `.stdout` — the CLI's real machine-readable-JSON contract is stdout only.
    js = runner.invoke(main, ["report", "--format", "json"])
    assert js.exit_code == 0 and "recommendations" in json.loads(js.stdout)
    out = runner.invoke(main, ["report", "--out", str(tmp_path / "r")])
    assert out.exit_code == 0
    assert (tmp_path / "r.md").is_file() and (tmp_path / "r.json").is_file()

    brief = tmp_path / "llm.brief.yaml"
    brief.write_text(yaml.safe_dump({"kind": "llm", "task": "write python code"}))
    engine_out = tmp_path / "llm.engine.yaml"
    resolved = runner.invoke(main, ["resolve", "--brief", str(brief), "--out", str(engine_out)])
    assert resolved.exit_code == 0
    assert f"Wrote {engine_out}" in resolved.output
    assert engine_out.is_file() and "backend" in yaml.safe_load(engine_out.read_text())

    missing = runner.invoke(main, ["resolve", "--brief", str(tmp_path / "nope.yaml")])
    assert missing.exit_code == 1
    assert "not found" in missing.output

    # A brief that reaches engine.resolve() but fails there (not a missing
    # file) is reported readably too, not as a raw traceback. No 'model' asks
    # for a cloud auto-pick; a provider absent from the catalog can't serve it.
    bad_cloud_brief = tmp_path / "bad_cloud.brief.yaml"
    bad_cloud_brief.write_text(
        yaml.safe_dump({"mode": "cloud", "provider": "not-a-real-provider", "kind": "llm"})
    )
    resolve_failed = runner.invoke(main, ["resolve", "--brief", str(bad_cloud_brief)])
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
        main, ["resolve", "--brief", str(pinned_cloud_brief), "--out", str(pinned_out)]
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
        main, ["resolve", "--brief", str(auto_cloud_brief), "--out", str(auto_out)]
    )
    assert auto_resolved.exit_code == 0
    auto_engine = yaml.safe_load(auto_out.read_text())
    assert auto_engine["backend"] == "openai" and auto_engine["llm"]["model"]

    # `report`'s default best-cloud-pick section needs no API key/network.
    cloud_report = runner.invoke(main, ["report", "--task", "write python code"])
    assert cloud_report.exit_code == 0
    assert "Best cloud engine" in cloud_report.output
    assert "Best cloud LLM" in cloud_report.output

    no_cloud_report = runner.invoke(main, ["report", "--task", "write python code", "--no-cloud"])
    assert no_cloud_report.exit_code == 0
    assert "Best cloud engine" not in no_cloud_report.output

    cloud_json = runner.invoke(main, ["report", "--task", "write python code", "--format", "json"])
    cloud_data = json.loads(cloud_json.stdout)
    assert "cloud" in cloud_data and cloud_data["cloud"]["recommendations"]["llm"]["chosen"]


def test_activity_empty_and_populated(runner: CliRunner, tmp_path: Path) -> None:
    from unittest.mock import patch

    from best_engine_ai_helper import llm, observe

    # A test-owned ledger, enabled up front, so `activity_cmd`'s "no active
    # ledger -> open the default path" fallback never touches the real
    # ~/.best-engine-ai-helper/usage.db (conftest's autouse fixture sets
    # BEST_ENGINE_NO_LEDGER=1, so `main()`'s own auto-enable stays a no-op).
    ledger = observe.enable(str(tmp_path / "usage.db"))

    empty = runner.invoke(main, ["activity"])
    assert empty.exit_code == 0 and "No calls recorded yet." in empty.stdout

    empty_json = runner.invoke(main, ["activity", "--format", "json"])
    assert json.loads(empty_json.stdout)["total_calls"] == 0

    # Record one call, then check both output formats reflect it.
    with patch("requests.post") as p:
        p.return_value.json.return_value = {"response": "hi"}
        p.return_value.raise_for_status.return_value = None
        llm.chat("hello", model="qwen3:8b")

    table = runner.invoke(main, ["activity"])
    assert table.exit_code == 0
    assert "Total calls: 1" in table.stdout and "qwen3:8b" in table.stdout

    as_json = runner.invoke(main, ["activity", "--format", "json"])
    data = json.loads(as_json.stdout)
    assert data["total_calls"] == 1 and data["total_cost_usd"] == 0.0

    # A failed call renders a "Recent errors" table too, not just the tallies.
    with patch("requests.post", side_effect=requests.ConnectionError("no server")):
        try:
            llm.chat("hello", model="qwen3:8b")
        except RuntimeError:
            pass
    with_error = runner.invoke(main, ["activity"])
    assert with_error.exit_code == 0
    assert "Recent errors:" in with_error.stdout
    ledger.close()


def test_usages_subcommands(runner: CliRunner, tmp_path: Path) -> None:
    listing = runner.invoke(main, ["usages", "list"])
    assert listing.exit_code == 0
    assert "Families" in listing.output and "Profiles" in listing.output
    assert "text2sql" in listing.output and "F1" in listing.output

    shown = runner.invoke(main, ["usages", "show", "text2sql"])
    assert shown.exit_code == 0
    assert "Needs (selection criteria):" in shown.output
    assert "structured_output" in shown.output

    unknown_show = runner.invoke(main, ["usages", "show", "not-a-real-profile"])
    assert unknown_show.exit_code == 1

    out = tmp_path / "llm.engine.yaml"
    resolved = runner.invoke(main, ["usages", "resolve", "text2sql", "--out", str(out)])
    assert resolved.exit_code == 0
    assert "text2sql: backend" in resolved.output
    assert out.is_file()

    family = runner.invoke(main, ["usages", "resolve", "--family", "F1"])
    assert family.exit_code == 0
    assert "F1: backend" in family.output

    no_target = runner.invoke(main, ["usages", "resolve"])
    assert no_target.exit_code == 1
    assert "NAME or --family" in no_target.output

    unknown_resolve = runner.invoke(main, ["usages", "resolve", "not-a-real-profile"])
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
    ok = runner.invoke(main, ["catalog", "update"])
    assert ok.exit_code == 0 and cache.exists()
    written = yaml.safe_load(cache.read_text())
    assert written[0]["id"] == "qwen3-8b" and written[0]["source"] == "apxml"

    # An empty feed leaves the cache untouched and reports failure.
    cache.unlink()
    monkeypatch.setattr(apxml, "fetch_open_weight_models", lambda **kw: [])
    empty = runner.invoke(main, ["catalog", "update"])
    assert empty.exit_code != 0 and not cache.exists()

    # A network/parse failure is reported readably, not as a raw traceback.
    def _boom(**kw: object) -> None:
        raise ConnectionError("ApXML unreachable")

    monkeypatch.setattr(apxml, "fetch_open_weight_models", _boom)
    network_fail = runner.invoke(main, ["catalog", "update"])
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
    hw_ok = runner.invoke(main, ["hardware", "update"])
    assert hw_ok.exit_code == 0
    assert yaml.safe_load(hw_cache.read_text())[0]["chip"] == "Apple M2 Max"

    # Nothing detectable -> cache untouched, non-zero exit.
    hw_cache.unlink()
    monkeypatch.setattr(hardware, "detect_local_entry", lambda *a, **k: None)
    hw_none = runner.invoke(main, ["hardware", "update"])
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
    passed = runner.invoke(main, ["pull"])
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
    comfortable = runner.invoke(main, ["pull"])
    assert comfortable.exit_code == 0
    assert pulled[0] == "small-fast"  # comfortable model tried first, not big-slow

    # A failed VLM gate removes the candidate and exits non-zero.
    _patch_gates(monkeypatch, vlm=False, prose=True)
    removed: list[str] = []
    monkeypatch.setattr(pull, "ollama_rm", lambda tag: (removed.append(tag), True)[1])
    failed = runner.invoke(main, ["pull"])
    assert failed.exit_code == 1 and removed  # failed candidates are cleaned up

    # --vllm prints the serve command without ever calling ollama_pull.
    monkeypatch.setattr(pull, "ollama_pull", lambda *a, **k: pytest.fail("--vllm must not pull"))
    vllm = runner.invoke(main, ["pull", "--vllm"])
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
        unconfigured = runner.invoke(main, cmd)
        combined = (unconfigured.output or "") + (unconfigured.stderr or "")
        assert unconfigured.exit_code != 0 and combined.strip()

    # env with a real env.sh in place prints it verbatim.
    env_dir = fake_home / ".best-engine-ai-helper"
    env_dir.mkdir()
    (env_dir / "env.sh").write_text("export BEST_LLM_TEXT=qwen3:8b\n")
    configured_env = runner.invoke(main, ["env"])
    assert configured_env.exit_code == 0
    assert configured_env.output == "export BEST_LLM_TEXT=qwen3:8b\n"

    # validate with a model configured and both gates passing.
    monkeypatch.setenv("BEST_LLM_TEXT", "qwen3:8b")
    monkeypatch.setattr(validate_vlm, "validate", lambda chat: True)
    monkeypatch.setattr(validate_llm, "validate", lambda chat: True)
    configured = runner.invoke(main, ["validate"])
    assert configured.exit_code == 0
    assert "pass" in configured.output.lower()

    import uvicorn

    gui_calls: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: gui_calls.update(app=app, **kw))
    gui_result = runner.invoke(main, ["gui", "--host", "0.0.0.0", "--port", "9000"])
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

    auto = runner.invoke(main, ["report", "--format", "json", "--task", "write python code"])
    assert auto.exit_code == 0
    forced = runner.invoke(
        main,
        ["report", "--format", "json", "--task", "write python code", "--backend", "vllm"],
    )
    assert forced.exit_code == 0
    # 'auto' on Linux + a discrete GPU resolves to vLLM, so the two agree.
    assert json.loads(auto.output) == json.loads(forced.output)

    # And an explicit Ollama run is genuinely different — otherwise the
    # assertion above would pass on a backend flag that does nothing.
    ollama = runner.invoke(
        main,
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
        main, ["report", "--format", "json", "--task", "write copy", "--backend", "ollama"]
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

    res = runner.invoke(main, ["providers"])
    assert res.exit_code == 0
    # Every shipped provider is accounted for, usable or not.
    for provider in ("mistral", "openai", "anthropic", "gemini"):
        assert provider in res.output
    # The variable to set is named, which is what makes the row actionable.
    assert "OPENAI_API_KEY" in res.output
    # The key value itself never appears.
    assert "sk-secret" not in res.output

    as_json = runner.invoke(main, ["providers", "--json"])
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
        res = runner.invoke(main, ["providers"])
    assert res.exit_code == 0
    assert not [r for r in caplog.records if "cloud API key" in r.message]
