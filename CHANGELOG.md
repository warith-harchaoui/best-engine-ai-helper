# Changelog

All notable changes to best-engine-ai-helper are documented here.

## [Unreleased]

### Added

- **Comfort throughput floor** in recommendation and pulling. A model that
  fits in memory can still decode too slowly to be usable (a 32B at Q8 crawls
  at ~7 tok/s on an M2 Max / 400 GB/s). Selection now treats "fits your
  hardware" as *fits in memory AND runs at a usable speed*: a new comfort floor
  (`score.COMFORT_TPS`, default 15 tok/s, reusing the existing
  `estimated_tokens_per_second` estimate) marks memory-fitting-but-slow models
  as not comfortable. `recommend` picks the highest-scoring comfortable model
  (falling back to a fitting-but-slow one only when none is comfortable, with a
  warning), `pull` tries comfortable candidates before slow ones, and both the
  `recommend` and `report` outputs gain a `comfy` column plus a stated floor.
  A `--min-tps` flag overrides the threshold on `recommend` and `pull`.
  Previously the ranker chose the top benchmark score that merely fit memory,
  over-recommending large models that technically load but feel stuck.

## [0.5.0] — 2026-08-02

### Added

- `catalog update` now refreshes the model cache from the ApXML open-weight
  directory: it fetches specs, normalizes them to catalog entries, and merges
  them into `~/.best-engine-ai-helper/catalog_cache.yaml` by id (the bundled
  seed is never touched). Supports `--limit` and `--timeout`. ApXML carries no
  numeric benchmarks, so refreshed entries rank low until a scored source
  fills them.
- `hardware update` now records the running machine into
  `~/.best-engine-ai-helper/hardware_cache.yaml`: the detected chip, its memory
  pool, and the Ollama-usable share after the OS reservation, upserted by
  chip + memory tier. (There is no public specs API spanning every GPU / Apple
  chip, so a refresh captures ground truth for the current machine rather than
  scraping a third-party site.)
- English variant of the GUI: the page is now bilingual (French by default,
  English at `/gui?lang=en`), with a header link to switch. Both are rendered
  from one template plus a per-language strings table (`render_gui`); the JSON
  API stays language-neutral.
- GUI mirrors the structured-output ranking: the candidate table gains a
  `structured` column, and the chosen model shows a warning when it can't do
  structured JSON output. A `/gui?task=...` deep link pre-fills the box and
  runs the recommendation on load, so a result is shareable by URL.
- Minimal browser GUI: `best-engine-ai-helper gui` (needs the new `[api]`
  extra: `fastapi` + `uvicorn`) serves a single-page app at `/gui`: the
  hardware snapshot `detect` prints, plus a task-description box that returns
  the same recommendation as `report`, in the browser. `api.py` exposes it as
  `GET /api/system` and `POST /api/recommend`; `gui.py` is the page (vanilla
  JS + Tailwind CDN, no build step, matching the AI Helpers suite's house
  style). See `GUI.md`.
- `scripts/generate_icons.py` + `best_engine_ai_helper/static/`: favicon,
  apple-touch-icon, and Android/PWA icons generated from `assets/logo.png`,
  composited onto the suite's cream background so the engraved-glove mark
  reads on both light and dark browser chrome.

### Changed

- Docstring `Examples` are now gated: `pytest` collects them via
  `--doctest-modules` (configured in `pyproject.toml`), so a drifted example
  fails CI. Fixed three that had drifted (`score.select`, `score.rank` used
  names not in scope; `validate_llm.validate` asserted a pass its stub model
  could not produce).
- Documentation pass over every Markdown file: brought the prose into line with
  the project's writing charter (removed em/en-dash asides), corrected stale
  facts (the `catalog update` / `hardware update` commands, the four selection
  factors including structured-output, the `gemma3:12b` vision default, the
  `pip install -e ".[api]" -r requirements-dev.txt` install, the `validate`
  entry points), brought LISEZMOI to parity with README, and refreshed the
  sample `recommend` / `select` outputs to match the current ranking. Populated
  the `references/WRITING.md`, `references/ECRITURE.md`, and `references/CODING.md`
  local copies from their canonical gists. Absolutized the image and link URLs
  in `README.md` / `LISEZMOI.md` to `raw.githubusercontent` / `github.com/blob`
  so they render on the PyPI project page (relative paths 404 there).
- Rationalized the test suite per the project's testing philosophy: fewer,
  richer tests (≈138 → 81) at **higher** coverage (74% → 93%). Collapsed
  one-assertion micro-tests into scenario and table-style tests, mirrored the
  source tree (`test_llm` / `test_ralph` / `test_pull` / `test_validate` replace
  `test_phase0b`), added `tests/conftest.py` for the shared Click runner and
  `tests/test_scenarios.py` for end-to-end workflows, and mock-covered the
  previously-untested subprocess / network / gate paths (hardware probes, ollama
  pull, LLM backends and errors, the Ralph loops, the validation gates).

### Fixed

- CI (and local `pytest`) was red on the two langchain-backend tests: the
  langchain branch in `llm.py` imports `langchain_core.messages`
  unconditionally, but `langchain-core` was not a declared dev dependency.
  Added it to `requirements-dev.txt` and made the `ChatOllama` test stub the
  optional backend via `sys.modules` (mirroring the existing `langchain_openai`
  stub) instead of importing the uninstalled real package.
- `recommend`'s "lighter alternative" was chosen by score proximity alone, so
  under a structured-capable pick it could suggest a lighter but
  structured-incapable model (e.g. a Qwen3-VL) that silently fails the suite's
  schema-driven tasks. The alternative is now required to be at least as
  structured-output-capable as the chosen model.
- `score.select` ignored the structured-output flag, so the library's `select`
  returned a different (structured-incapable) model than `recommend` / `report`
  / the GUI, which rank structured-capable models first. `select` now applies
  the same priority, restoring the documented `rank(...)[0] == select(...)`
  invariant.
- AMD VRAM detection: `_amd_vram_gb` split the rocm-smi line on the *first*
  colon, so the real `GPU[0] : VRAM Total Memory (B): <bytes>` format left the
  label text where the number was expected and detection silently returned
  None. Split on the last colon instead.
- Ralph eyeball gate: the verdict prompt's literal JSON example (`{"ship": ...}`)
  was not brace-escaped, so `.format(critique=...)` raised `KeyError` on every
  real verdict. Escaped it; the eyeball loop now completes.
- Clean `mypy` run across the package: annotated the subprocess and JSON
  boundaries that leaked `Any` (`detect`, `llm`, `ralph`, `catalog`), gave
  `cli._fmt_table` its `dict[str, Any]` argument, typed the LangChain message
  list, and dropped `type: ignore` comments that no longer apply.

## [0.4.0] - 2026-07-31

### Added

- Depend on `os-helper` (`>=1.5.0`) and route all logging through it. Library
  modules now emit `osh.info` at their seams (catalog / hardware load, memory
  detection, recommendation picks, model pull/remove, Ralph iterations, chat
  dispatch) and `osh.warning` / `osh.error` on the failure paths (malformed
  YAML/JSON config, unknown chip, no model fitting the budget, failed inference
  requests, gate failures). `info` / `debug` are off by default and surface with
  the new `-v` / `-vv` flag on the CLI; warnings and errors always show.
- File management goes through `os-helper` helpers: `osh.file_exists` for the
  config / catalog presence checks and `osh.make_directory` in place of ad-hoc
  `Path.mkdir(parents=True, exist_ok=True)`.

## [0.3.0] - 2026-07-31

Make the chosen model tags trivially consumable by downstream suite packages,
so model selection lives here (its rightful home) rather than being hard-coded
in each consumer.

### Added

- `config.py`: cheap, deterministic resolvers `text_model()` / `vision_model()`
  / `resolved_models()` / `load_config()`. Precedence is env override
  (`BEST_LLM_TEXT` / `BEST_LLM_VISION`, with the legacy `SPREZZATURE_LLM_*`
  spellings accepted) → the selection persisted by `pull` in
  `~/.best-engine-ai-helper/config.json` → a safe built-in default
  (`qwen3-vl:8b`). They never probe hardware and never raise, so they are safe
  to call at import time, in CI, and in tests. Exported from the package root.

### Changed

- `llm.py` transport now resolves its model tags through `config`, closing the
  gap where it read only `SPREZZATURE_LLM_*` and ignored a fresh `pull`
  selection persisted under `BEST_LLM_*`.

## [0.2.0] - 2026-07-30

Hardware-aware recommendation that weighs memory, accelerator, and compute, and
emits a justifiable report in Markdown and JSON.

### Added

- `recommend.py`: the end-to-end algorithm. Takes a hardware description, the
  benchmark catalog, and a (possibly vague, free-text) task, and returns the
  best engine per needed kind (LLM/VLM), each justified by task fit, memory fit,
  and estimated throughput. `parse_task` maps a phrase to a benchmark axis and
  the model kinds it needs. `to_markdown` / `write_report` render the result;
  the report round-trips through JSON.
- `report` CLI command: `--task "…" --out <stem> [--format md|json]` writes
  `<stem>.md` and `<stem>.json`.
- `detect.compute_profile()` and `detect.chip_name()`: accelerator kind and
  Apple-Silicon memory bandwidth (published specs), used for the throughput
  estimate.
- `score.estimated_tokens_per_second()`: bandwidth-bound decode-speed estimate.

### Changed

- **Memory budget model.** `effective_budget` now applies the Apple Metal
  GPU-usable cap (~66% ≤36 GB, ~75% >36 GB of unified memory) instead of
  treating the whole pool as usable, then a default `headroom` of 0.85 (was a
  flat 0.80 of everything) for the OS, workload, and KV growth. This stops the
  tool from steering toward RAM-maxing models that leave no room to work.
- Reliability: model-call timeout is now bounded and configurable via
  `SPREZZATURE_LLM_TIMEOUT` (default 120s, was a fixed 600s), so validation
  terminates predictably on a light model.

### Fixed

- Stale CLI test that treated the implemented `pull` / `validate` commands as
  stubs and hung the suite by driving the live model loop.

## [0.1.0] - 2026-07-28

First release. Phase 0a: pure Python, no model download required.

### Added

- Hardware detection (`detect.py`): Apple Silicon unified memory, NVIDIA VRAM via
  nvidia-smi, AMD VRAM via rocm-smi, CPU-only fallback via psutil.
- Model catalog (`catalog.py`, `models.yaml`): 13-entry bundled seed covering
  Qwen 3 VL (4B to 72B), Qwen 3 text (8B to 72B Q8), Qwen 2.5 3B, Gemma 3 12B.
  Cache-merge logic for future `catalog update` output.
- Hardware chip table (`hardware.py`, `hardware.yaml`): Apple Silicon M1 through
  M4 Ultra across all memory tiers; NVIDIA RTX 3060 through H100. Cache-merge logic.
- Selection algorithm (`score.py`): filters by 80% headroom, ranks by benchmark
  score (vision for VLMs, general for LLMs), last-resort smallest-model fallback.
- CLI (`cli.py`): `detect`, `recommend`, `catalog show`, `hardware show` commands
  fully implemented. `pull`, `validate`, `env`, `catalog update`, `hardware update`
  stubbed with Phase 0b notice.
- Test suite: 40+ tests in `tests/` covering all public functions.
