"""
Tests for best_engine_ai_helper.sources.apxml.

Exercises the offline parsing path (RSC reconstruction, brace-matched object
extraction, field normalization) against a synthetic Next.js payload, so the
suite never touches the network. The live ``fetch_open_weight_models`` path is
left to manual/integration runs.
"""

from __future__ import annotations

import json

from best_engine_ai_helper.sources import apxml

# A trimmed model object mirroring ApXML's real shape: quoted numeric params,
# a multimodal modality, and a HuggingFace weights URL.
_MODEL_OBJ = {
    "slug": "qwen35-9b",
    "name": "Qwen3.5-9B",
    "provider": {"name": "Qwen"},
    "modality": "multimodal",
    "num_of_params": "9.00",
    "architecture": "dense",
    "num_of_experts": None,
    "num_of_active_experts": None,
    "context_length": 262144,
    "license": "Apache 2.0",
    "open_weights": True,
    "link_weights": "https://huggingface.co/Qwen/Qwen3.5-9B",
    "release_date": "2026-02-24",
    "inference_vram_required_q4": "6.30",
    "inference_vram_required_q8": "11.49",
    "inference_vram_required_fp16": "21.86",
}


def _compact(obj: dict) -> str:
    """
    Serialise an object the way ApXML streams it: no whitespace between tokens.

    Parameters
    ----------
    obj : dict
        Object to serialise.

    Returns
    -------
    str
        Compact JSON, so the ``"num_of_params":"..."`` anchor matches.
    """
    return json.dumps(obj, separators=(",", ":"))


def _rsc_page(payload: str) -> str:
    """
    Wrap a payload string in a Next.js ``self.__next_f.push`` script call.

    Parameters
    ----------
    payload : str
        The logical RSC payload to embed.

    Returns
    -------
    str
        HTML fragment carrying the payload as one escaped chunk.
    """
    # json.dumps gives us exactly the escaping the real page uses per chunk.
    escaped = json.dumps(payload)[1:-1]
    return f'<script>self.__next_f.push([1,"{escaped}"])</script>'


def test_reconstruct_rsc_payload_unescapes_and_joins() -> None:
    html = _rsc_page("ab\ncd") + _rsc_page('e"f')
    assert apxml._reconstruct_rsc_payload(html) == 'ab\ncde"f'


def test_parse_directory_slugs_dedupes_and_orders() -> None:
    html = (
        '<a href="/models/qwen3-8b">x</a>'
        '<a href="/models/qwen3-8b">y</a>'
        '<a href="/models/glm-5">z</a>'
    )
    assert apxml.parse_directory_slugs(html) == ["qwen3-8b", "glm-5"]


def test_hf_id_from_weights_url() -> None:
    hf = apxml._hf_id_from_weights_url
    assert hf("https://huggingface.co/Qwen/Qwen3.5-9B") == "Qwen/Qwen3.5-9B"
    assert hf("https://huggingface.co/Qwen/Qwen3.5-9B/tree/main") == "Qwen/Qwen3.5-9B"
    assert hf("https://example.com/model") is None
    assert hf(None) is None


def test_parse_model_page_normalizes_fields() -> None:
    # A leading i18n label map (with the same key names but no numeric value)
    # must not be mistaken for the real spec object.
    labels = '{"modality":"Modality","architecture":"Architecture"}'
    html = _rsc_page(labels + _compact(_MODEL_OBJ))

    spec = apxml.parse_model_page(html)
    assert spec is not None
    assert spec["slug"] == "qwen35-9b"
    assert spec["kind"] == "vlm"  # multimodal -> vision-capable
    assert spec["size_b"] == 9.0
    assert spec["architecture"] == "dense"
    assert spec["vllm_id"] == "Qwen/Qwen3.5-9B"
    # ram_gb mirrors the Q4 VRAM estimate, the project's default pull quant.
    assert spec["ram_gb"] == 6.30
    assert spec["vram_q8_gb"] == 11.49
    assert spec["context_length"] == 262144
    assert spec["open_weights"] is True


def test_parse_model_page_text_only_is_llm() -> None:
    obj = dict(_MODEL_OBJ, modality="text")
    spec = apxml.parse_model_page(_rsc_page(_compact(obj)))
    assert spec is not None
    assert spec["kind"] == "llm"


def test_parse_model_page_returns_none_without_model() -> None:
    assert apxml.parse_model_page("<html>no payload here</html>") is None


def test_fetch_open_weight_models_skips_failures_and_honours_limit(monkeypatch) -> None:
    # Patch _fetch so the whole crawl runs offline: one directory page linking a
    # good model and a broken one; the broken page raises and must be skipped,
    # not sink the feed.
    directory = '<a href="/models/qwen35-9b">a</a><a href="/models/broken">b</a>'
    model_html = _rsc_page(_compact(_MODEL_OBJ))

    def fake_fetch(url: str, session: object, timeout: float) -> str:
        if "modelType=open_weight" in url:
            return directory
        if "qwen35-9b" in url:
            return model_html
        raise apxml.requests.HTTPError("500 on the broken page")

    monkeypatch.setattr(apxml, "_fetch", fake_fetch)
    models = apxml.fetch_open_weight_models()
    assert [m["slug"] for m in models] == ["qwen35-9b"]
    # limit caps how many model pages are fetched.
    assert apxml.fetch_open_weight_models(limit=0) == []
