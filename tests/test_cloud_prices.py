"""
The paid catalogue's refresh path: a real source, a narrow merge, a date.

`pricing.yaml` is hand-maintained and said so in its own header -- "refresh
when a provider reprices or ships a new flagship" -- with nothing to refresh
*from*. These tests pin the three properties that make the new path worth
having: it corrects prices, it never invents a quality score, and it says how
old the numbers are.

Offline throughout: the table is a fixture, so the suite does not depend on a
third party's availability or on today's prices.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from best_engine_ai_helper import cloud_catalog as cc
from best_engine_ai_helper.sources import litellm_prices as lp

# A slice of the real table, shaped exactly as LiteLLM publishes it: bare keys
# and `<provider>/<model>` keys side by side, a Bedrock mirror that must be
# skipped, a fine-tune template, a billing bucket, and a zero-priced preview.
_TABLE: dict[str, Any] = {
    "gpt-4o": {
        "litellm_provider": "openai",
        "mode": "chat",
        "input_cost_per_token": 2.5e-06,
        "output_cost_per_token": 1e-05,
        "max_input_tokens": 128000,
        "supports_vision": True,
        "supports_response_schema": True,
    },
    "mistral/mistral-large-latest": {
        "litellm_provider": "mistral",
        "mode": "chat",
        "input_cost_per_token": 5e-07,
        "output_cost_per_token": 1.5e-06,
        "max_input_tokens": 262144,
        "supports_vision": True,
        "supports_response_schema": True,
    },
    "text-embedding-3-small": {
        "litellm_provider": "openai",
        "mode": "embedding",
        "input_cost_per_token": 2e-08,
        "max_input_tokens": 8191,
    },
    # Someone else's routing surface for the same weights.
    "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0": {
        "litellm_provider": "bedrock",
        "mode": "chat",
        "input_cost_per_token": 3e-06,
    },
    "ft:gpt-3.5-turbo": {
        "litellm_provider": "openai",
        "mode": "chat",
        "input_cost_per_token": 3e-06,
    },
    "together-ai-21.1b-41b": {
        "litellm_provider": "together_ai",
        "mode": "chat",
        "input_cost_per_token": 3e-07,
    },
    # The same OpenAI model under Azure's roof: a deployment name the tenant
    # chooses, behind an endpoint only they know.
    "azure/gpt-4o": {
        "litellm_provider": "azure",
        "mode": "chat",
        "input_cost_per_token": 2.5e-06,
        "output_cost_per_token": 1e-05,
        "max_input_tokens": 128000,
        "supports_vision": True,
    },
    # Priced at nothing: a preview tier, not something you can buy.
    "gemini-exp-1206": {
        "litellm_provider": "gemini",
        "mode": "chat",
        "input_cost_per_token": 0.0,
        "output_cost_per_token": 0.0,
    },
}


def _normalised() -> list[dict[str, Any]]:
    return [
        entry
        for key, spec in _TABLE.items()
        if (entry := lp.normalize_price_entry(key, spec, "2026-10-28")) is not None
    ]


def test_the_source_contributes_prices_and_never_a_benchmark() -> None:
    """The deliberate gap, mirroring sources.apxml.

    A price table has no opinion about quality, so this adapter must not grow
    one. If it ever synthesised a score, `rank_cloud` would start ranking on a
    number nobody measured -- in a file that bills people.
    """
    entries = {e["id"]: e for e in _normalised()}

    assert entries["gpt-4o"]["input_per_1m"] == 2.5
    assert entries["gpt-4o"]["output_per_1m"] == 10.0
    assert entries["gpt-4o"]["context_length"] == 128000
    assert all("benchmarks" not in e for e in entries.values())


def test_vision_and_schema_support_decide_kind_not_a_guess() -> None:
    """`kind` and `structured_output` come from the source's own flags."""
    entries = {e["id"]: e for e in _normalised()}

    assert entries["gpt-4o"]["kind"] == "vlm"
    assert entries["gpt-4o"]["structured_output"] is True
    assert entries["text-embedding-3-small"]["kind"] == "embed"


def test_only_ids_a_transport_here_could_send_survive() -> None:
    """Three shapes of noise, each skipped for its own reason.

    A Bedrock key prices the same weights behind routing this package has no
    transport for; `ft:` names a fine-tune family rather than a model;
    `together-ai-21.1b-41b` is a parameter-count price band. Carrying any of
    them would put an id in the catalogue that `llm.chat` could not send.
    """
    ids = {e["id"] for e in _normalised()}

    assert "gpt-4o" in ids
    # The provider prefix is stripped: the transport sends the bare name.
    assert "mistral-large-latest" in ids and "mistral/mistral-large-latest" not in ids
    assert not any("claude-3-5-sonnet" in i for i in ids)
    assert not any(i.startswith(("ft:", "together-ai-")) for i in ids)


def test_reprice_corrects_the_price_and_leaves_the_score_alone() -> None:
    """The merge is narrow on purpose.

    Measured against the live table when this landed: `mistral-large-latest`
    was priced at 2.00/6.00 against a real 0.50/1.50 -- four times too dear, so
    the ranker avoided a model that was in fact the cheap one -- while
    `mistral-medium-latest` was 0.40/2.00 against 1.50/7.50, under-billing by
    nearly four. Both directions were wrong, and `quality_vs_cost` ranks on
    exactly these numbers.
    """
    seed = [
        {
            "id": "mistral-large-latest",
            "provider": "mistral",
            "kind": "llm",
            "benchmarks": {"general": 84, "code": 92},
            "input_per_1m": 2.00,
            "output_per_1m": 6.00,
        }
    ]
    merged, missing = cc.reprice(seed, _normalised())

    assert missing == []
    assert merged[0]["input_per_1m"] == 0.5
    assert merged[0]["output_per_1m"] == 1.5
    assert merged[0]["context_length"] == 262144
    # The source says vlm; the seed said llm. The source wins on capability.
    assert merged[0]["kind"] == "vlm"
    # And the one thing it cannot know is untouched.
    assert merged[0]["benchmarks"] == {"general": 84, "code": 92}


def test_a_model_the_source_never_heard_of_is_reported_not_deleted() -> None:
    """Retirement is a judgement call, and the seed holds the only scores.

    `gemini-1.5-pro` and `gemini-1.5-flash` shipped in this catalogue long
    after Google retired the 1.5 line, and the live table has no entry for
    either. Absence from one source is strong evidence, not proof, so the
    refresh surfaces the ids and changes nothing.
    """
    seed = [
        {"id": "gemini-1.5-pro", "provider": "gemini", "kind": "vlm", "input_per_1m": 1.25},
        {"id": "gpt-4o", "provider": "openai", "kind": "vlm", "input_per_1m": 999.0},
    ]
    merged, missing = cc.reprice(seed, _normalised())

    assert missing == ["gemini-1.5-pro"]
    by_id = {e["id"]: e for e in merged}
    assert by_id["gemini-1.5-pro"]["input_per_1m"] == 1.25  # untouched
    assert by_id["gpt-4o"]["input_per_1m"] == 2.5  # corrected


def test_the_cache_overlays_the_seed_and_deleting_it_reverts(tmp_path: Path) -> None:
    """Same contract as the local catalogue: the bundled seed is never written."""
    cache = tmp_path / "pricing_cache.yaml"
    cc.write_cloud_cache(
        [{"id": "gpt-4o", "input_per_1m": 1.0, "output_per_1m": 2.0, "fetched_at": "2026-10-28"}],
        cache_path=cache,
    )

    written = yaml.safe_load(cache.read_text())["models"]["gpt-4o"]
    assert written["input_per_1m"] == 1.0
    # The id is the key, never duplicated into the body.
    assert "id" not in written


def test_an_undated_table_says_so_rather_than_implying_freshness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The seed carries no `as_of`, and that absence is deliberate.

    Its numbers were written from recollection, not verified against a source
    on a given day, so there is no honest date to stamp. Using the last commit
    that touched the file would say "verified on" about an edit. The note says
    plainly that there is no date, and names the command that creates one.
    """
    monkeypatch.setattr(cc, "_CLOUD_CACHE_PATH", tmp_path / "absent.yaml")
    seed = tmp_path / "pricing.yaml"
    seed.write_text(yaml.safe_dump({"models": {"m": {"provider": "p", "kind": "llm"}}}))

    assert cc.catalog_as_of(path=seed) is None
    note = cc.staleness_note(path=seed)
    assert note is not None and "carries no date" in note
    assert "catalog update --cloud" in note


def test_a_dated_table_only_complains_once_it_is_old(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A warning, never a refusal: an old price beats no price, and offline is real."""
    monkeypatch.setattr(cc, "_CLOUD_CACHE_PATH", tmp_path / "absent.yaml")
    seed = tmp_path / "pricing.yaml"
    seed.write_text(
        yaml.safe_dump({"as_of": "2026-01-01", "models": {"m": {"provider": "p", "kind": "llm"}}})
    )

    assert cc.catalog_as_of(path=seed) == "2026-01-01"
    assert cc.staleness_note(today="2026-02-01", path=seed) is None
    stale = cc.staleness_note(today="2027-01-01", path=seed)
    assert stale is not None and "2026-01-01" in stale


def test_azure_rows_never_enter_the_catalogue() -> None:
    """A catalogue entry must be routable from its id alone, and Azure is not.

    Azure is the one provider `llm._OPENAI_COMPATIBLE` lists that
    `engine._CLOUD_BASE_URLS` does not, because there is no universal base URL
    to list: the endpoint is per-tenant and the id in a request is a deployment
    name the tenant picked. An auto-picked Azure entry resolves to
    `base_url=""` and cannot be called. It also duplicated — most Azure rows
    repeat an OpenAI id that already works — so admitting them filled the
    triage list with models that were already there.
    """
    from best_engine_ai_helper import engine

    entries = _normalised()
    assert "azure" not in {e["provider"] for e in entries}
    # The reason, pinned: no base URL means no route.
    assert "azure" not in engine._CLOUD_BASE_URLS
    # And exactly one gpt-4o survives, under the provider that can serve it.
    gpt4o = [e for e in entries if e["id"] == "gpt-4o"]
    assert [e["provider"] for e in gpt4o] == ["openai"]


def test_the_two_sources_together_are_what_grows_the_catalogue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`catalog update --cloud --arena`, end to end, with both sources faked.

    The bug this pins: adoption used to be gated on the Arena merge landing on
    the *seed*. It never can — the seed is ten models from 2024 and the board
    rates what people chat with today — so the gate meant the catalogue could
    only ever reprice itself. The two questions are different, and only the
    second one grows anything.
    """
    from click.testing import CliRunner

    from best_engine_ai_helper import catalog as _catalog
    from best_engine_ai_helper.cli import cli

    seed = tmp_path / "pricing.yaml"
    seed.write_text(
        "models:\n"
        "  old-model:\n"
        "    provider: mistral\n"
        "    kind: llm\n"
        "    benchmarks: {general: 84}\n"
        "    input_per_1m: 2.0\n"
        "    output_per_1m: 6.0\n",
        encoding="utf-8",
    )
    cache = tmp_path / "pricing_cache.yaml"
    monkeypatch.setattr(cc, "_PRICING_PATH", seed)
    monkeypatch.setattr(cc, "_CLOUD_CACHE_PATH", cache)
    monkeypatch.setattr(lp, "fetch_cloud_prices", lambda **kw: _normalised())
    monkeypatch.setattr(
        _catalog,
        "fetch_arena_safely",
        lambda timeout: (
            {"snapshot": "2026-10-07", "scores": {"arena": {"gpt-4o": 88.0}}},
            "fixture",
        ),
    )

    result = CliRunner().invoke(cli, ["catalog", "update", "--cloud", "--arena"])
    assert result.exit_code == 0, result.output

    written = yaml.safe_load(cache.read_text())["models"]
    # The seed's own model is still there, repriced and never re-adopted.
    assert "old-model" in written
    # And a model the seed never carried arrived, because two sources name it.
    assert written["gpt-4o"]["benchmarks"]["arena"] == 88.0
    assert written["gpt-4o"]["benchmarks"]["general"] is None
    assert written["gpt-4o"]["source"] == "litellm+arena"
    # The priced-but-unrated ones stayed out.
    assert "mistral-large-latest" not in written
    assert "Adopted 1 model(s)" in result.output
