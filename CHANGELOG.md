# Changelog

All notable changes to best-engine-ai-helper are documented here.

## [Unreleased]

### Added

- **MCP surface (`mcp.py`, `[mcp]` extra), entry point
  `best-engine-ai-helper-mcp`.** Exposes the same FastAPI app from `[api]`
  (`/api/system`, `/api/recommend`) as MCP tools via `fastapi-mcp`, mirroring
  the pattern already shipped in `standpoint` / `vocal-helper` / `md2star`.
  Closes the last surface gap flagged in `ai-helpers/.private/do.md` §7.
- **argparse CLI twin (`cli_argparse.py`), entry point
  `best-engine-ai-helper-argparse`.** Mirrors every `cli.py` command 1:1
  (same flags, same defaults, same output); no business logic duplicated —
  every handler delegates to the same library functions the click commands
  call. Closes the suite's CLI-surface gap flagged in `ai-helpers/.private/do.md`
  §7 (this repo was the only member without an argparse surface). The click
  entry point (`best-engine-ai-helper`) stays the primary, unchanged one —
  click is a core dependency here, not an opt-in extra, so the suite's usual
  "argparse is primary, click is the twin" naming is inverted; see the new
  module's docstring for the reasoning.
- **NVIDIA/AMD memory-bandwidth tables (`detect.py`).** `compute_profile()`
  previously only estimated decode throughput on Apple Silicon —
  `bandwidth_gbs` was always `None` on NVIDIA/AMD, so `est_tokens_per_s` and
  the comfort-throughput floor never applied on a discrete-GPU machine. New
  per-board bandwidth tables (`_NVIDIA_BANDWIDTH_GBS`, `_AMD_BANDWIDTH_GBS`,
  matched by substring against the detected GPU name) close that gap; an
  unrecognised board still degrades to `bandwidth_gbs: None` rather than a
  fabricated number.
- **Backend-aware decode efficiency (`score.py`).** `estimated_tokens_per_second`
  now applies a different achieved-bandwidth fraction for vLLM (0.75) than for
  Ollama (0.65) — confirmed to differ on identical Ubuntu + discrete-GPU
  hardware, not just a cross-platform artifact. PagedAttention + CUDA-graph
  decode tracks closer to the bandwidth ceiling than llama.cpp's more
  conservative kernel path for single-stream generation.
- **Hardware detection now delegates to `os_helper.hardware_utils`.**
  `detect.py` no longer shells out to `nvidia-smi` / `rocm-smi` /
  `system_profiler` / `lspci` itself; it calls the new generic hardware probe
  in `os-helper>=2.1.0` (cores, CPU model, GPU vendor/model/VRAM, RAM) and adds
  only the AI-throughput-specific layer (bandwidth tables, backend sizing) on
  top. `detect`/`/api/system` gained a `hardware` field with the raw facts
  (CPU cores/model, per-GPU name + VRAM) alongside the existing throughput
  estimate. `psutil` is no longer a direct dependency (comes transitively via
  os-helper).
- **Usage catalog (`usages.yaml`) — named sev7n task profiles + families.** Eight
  profiles (`text2sql`, `rag-answer`, `embeddings`, `text2sql-figures`,
  `report-bluf`, `classification`, `pii-rgpd`, `persona`), each stating only its
  **needs** (task type, structured-output requirement, throughput floor, memory
  headroom, advisory quality bar, context length) — **never a model name**. A
  profile is a named brief, resolved by the same four-criteria picker. Profiles
  are grouped into families **F1** (constrained generation), **F2** (prose
  generation), **F3** (embeddings) — the usages that can share one model. New
  CLI `usages list` / `usages show NAME` / `usages resolve NAME|--family FID`,
  and library `list_usages`, `list_families`, `get_usage`, `get_family`,
  `usage_brief`, `family_brief`, `resolve_usage`, `resolve_family`. best-engine
  chooses the concrete model and writes it only to the gitignored
  `llm.engine*.yaml` (added to `.gitignore`). A user overlay at
  `~/.best-engine-ai-helper/usages_cache.yaml` overrides by name.
- **Catalog additions (the search space).** Qwen 2.5-Coder entries (a real code
  axis for `text2sql`) and `kind: embed` text embedders (scored on MTEB) for the
  embeddings usage. `embed` joins `llm`/`vlm` as a third catalog kind; the
  generative picker ignores it, the F3 usage selects among embedders by memory
  fit.
- **`resolve` command + the brief → engine contract.** A repo commits a tuned
  `llm.brief.yaml` (its LLM/VLM usage: `kind`, `headroom`, `min_tps`,
  `structured_output`, free-text `task`, and `mode: local|cloud`).
  `best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml`
  turns it into a **gitignored, machine-specific** engine descriptor (backend +
  model per kind). Consumers read the model only from that file — no
  `DEFAULT_MODEL` constant.
- **Dual backend, chosen by hardware.** `engine.default_backend()`: **vLLM on a
  discrete GPU (NVIDIA/AMD), Ollama otherwise** (macOS, CPU-only Linux, Intel
  iGPU). `resolve --backend auto|ollama|vllm` and `--endpoint URL` override it.
- **`engine.ensure(dir)` + missing-file policy.** Loads `llm.engine.yaml`, or
  resolves it from the brief on first use; a missing **brief** raises loudly
  (it is committed, so its absence is a real bug).
- **Centralized transport.** `llm.chat(..., engine=<descriptor|path>, kind=…)`
  reads the backend/base_url/model from the engine file and dispatches to Ollama
  (`/api/generate`) or vLLM (OpenAI-compatible `/v1/chat/completions`), with
  schema-constrained structured output on both. `base_url` is now injectable.
- **Brief `mode: local|cloud` field** (default `local`), recognised now for
  forward-compatibility. `mode: cloud` raises `NotImplementedError` — cloud
  providers (with a paid → local fallback), cost, failover, pseudonymization and
  NSFW safety ship on a later `cloud` branch.
- New Python API: `resolve`, `ensure`, `write_engine`, `load_engine`,
  `model_for`, `default_backend`, `model_footprint_gb`, `MAX_HEADROOM`.

### Fixed

- **Mypy CI regression from the `kinds`/usage-catalog work.** `recommend()`'s
  `kinds` parameter and `engine._kinds_from_brief` now return
  `list[Literal["llm", "vlm"]]` instead of `list[str]`, matching what `rank()`
  expects; `llm._dispatch`, `llm._cache_key_payload` and the retry closure in
  `llm.chat` gained the parameter annotations mypy was missing; `chat`'s
  JSON-mode return is explicitly cast from `json.loads`.

### Changed

- **Anti-greed selection — picks are realistic, not maximal.**
  - **Headroom capped at 0.5** (`score.MAX_HEADROOM`), and any caller/brief value
    is clamped down to it (was a 0.85 default). This is the main guard against a
    model that technically loads but leaves no room for the OS or KV growth.
  - **Leanest-sufficient, not biggest-that-fits.** Among models within 3 benchmark
    points of the best comfortable candidate, `recommend` now picks the
    smallest/fastest, not the top scorer.
  - **Backend-aware sizing.** `score.model_footprint_gb` sizes a vLLM pick against
    full FP16 weights (~2 bytes/param + overhead), not the Ollama Q4 `ram_gb`, so
    a vLLM recommendation is realistic on the real GPU. `select`/`rank`/
    `recommend`/`estimated_tokens_per_second` take a `backend` argument.

## [1.0.0] - 2026-08-02

First stable release. The recommender now defaults to **comfortable, realistic**
picks (not merely "theoretically fits"), and the whole suite sits on the
os-helper 2.0.0 foundation.

### Changed

- **Requires os-helper 2.x** (`os-helper>=2.0.0,<3`, was `>=1.5.0`). Logging
  routes through os-helper on its stable 2.x contract.
- Install docs use `pip install best-engine-ai-helper` (from PyPI); added a test
  guarding every Markdown file against a stale `git+...@vX.Y.Z` self-pin. CI stays
  a super-light blocking gate (ruff + mypy + pytest).

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
