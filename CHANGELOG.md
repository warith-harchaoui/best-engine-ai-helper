# Changelog

All notable changes to best-engine-ai-helper are documented here.

## [Unreleased]

### Fixed

- **`pull.ollama_pull`'s `timeout` was never actually enforced**: the
  progress-streaming loop blocks on each read until a line arrives or the
  pipe closes (i.e. until the process exits), so a stalled pull (network
  stall, hung Ollama server) hung forever regardless of `timeout`. A
  watchdog thread now kills the process and raises `subprocess.TimeoutExpired`
  after `timeout` seconds. `cli.py`'s and `cli_argparse.py`'s `pull` command
  now catch that (skip to the next candidate, like a failed pull) and
  `FileNotFoundError` (no candidate can pull without the `ollama` binary —
  fail fast with a clear message instead of repeating the same crash per
  candidate).
- **`catalog._load_yaml_file` silently produced garbage on a non-list YAML
  top level**: `list(a_dict)` returned only the dict's keys as fake
  "entries", `list(a_string)` returned one-character "entries", and a bare
  scalar crashed `list(...)` outright — all reachable from a hand-edited or
  corrupted `catalog_cache.yaml`. Now validated and skipped with a warning,
  same treatment as an empty file.
- **`safety.scan_text` could crash `check_text`/`chat()` outright**: the
  NSFW-label lookup (`next(r for r in result if r["label"] == "nsfw")`) had
  no default and no case-insensitivity, so a differently-cased or renamed
  label from a future model update would raise an unhandled `StopIteration`
  instead of degrading — the exact "silently no-op" failure this module's
  design otherwise avoids. Now case-insensitive with a heuristic fallback
  instead of a crash.
- **CLI**: an exception from the library now prints one clean `Error: ...`
  line to stderr and exits 1, instead of a raw Python traceback, on both CLI
  twins. `best-engine-ai-helper`'s console-script entry point now points at
  a new `cli.console_entry()` wrapper (was the bare `main` click group);
  `cli_argparse.py`'s `main()` now wraps its subcommand dispatch the same
  way. `pyproject.toml` updated.

## [1.3.5] - 2026-08-13

Solidifies documentation, tests, and CI. No behavior change for end users
beyond one bug fix.

### Fixed

- `safety.scan_image` crashed with an uncaught `PIL.UnidentifiedImageError`
  when Pillow was installed but fed malformed or truncated image bytes,
  instead of degrading gracefully like every other missing-dependency path
  in that function. Found while writing a `CODING.md`-required docstring
  Example, not by inspection. Now returns the same `"unavailable"` degrade
  shape as a missing optional dependency.
- `tests/test_safety.py`'s heuristic-fallback assertions assumed
  `transformers` is never importable in the test environment; on a machine
  where a sibling package already pulls it in (true of this suite's shared
  dev env), `scan_text` legitimately took the real-classifier path instead,
  failing the test. Now forces `transformers` absent via the same
  `sys.modules` monkeypatch already used for the `PIL`-missing case, so the
  assertion is deterministic regardless of what else is installed.

### Added

- CI: a `concurrency` group cancels a still-running run for the same
  branch/PR when a new push lands. Two new post-test checks: `pyproject.toml`
  version vs. `CHANGELOG.md` entry consistency, and a real `python -m build`
  + `twine check` that also verifies the Git-LFS-tracked ONNX model lands in
  the wheel as its real ~1.9 MB binary, not an LFS pointer stub.
- Docstring `Examples` sections completed across `safety.py`.

### Changed

- Test coverage: 92.60% -> 94.45% (`ralph.py`, `engine.py`, `safety.py` now
  100%; `apxml.py` 96%; `cli.py` 98%). 104 tests collected, up from 99.

## [1.3.4] - 2026-08-10

Reverses `1.3.3`'s image-detector decision: LAION's `CLIP-based-NSFW-Detector`
now ships as the default, converted to ONNX to remove the fragility that
made `1.3.3` keep Falconsai instead.

### Changed

- **Image NSFW classifier: `Falconsai/nsfw_image_detection` -> LAION's
  `CLIP-based-NSFW-Detector`.** `1.3.3` measured LAION's real accuracy
  (96.16%/94.56%/97.58%/2.29% FPR, independently verified) but kept
  Falconsai because LAION's *documented* loading path needed TensorFlow +
  the unmaintained `autokeras` and OpenAI `clip` packages, plus an
  un-versioned runtime zip download. That's now moot: the classifier head
  was converted once, offline, from LAION's TensorFlow SavedModel to ONNX
  (`tf2onnx`) and is bundled directly in the package
  (`best_engine_ai_helper/models/clip_nsfw_vit_l14.onnx`, ~1.9 MB, tracked
  via Git LFS; MIT-licensed original, see `models/NOTICE.md`). Verified
  against the original TensorFlow model on LAION's own public test set:
  only 6 of 3199 samples (0.19%) flip their classification decision at the
  0.8 threshold — normal graph-conversion floating-point noise, concentrated
  where a sigmoid-shaped output is most sensitive (the 0.3-0.7 range), not a
  correctness bug. `[filtered]` now needs `onnxruntime` (new) plus
  `transformers` for the CLIP ViT-L/14 encoder (`openai/clip-vit-large-
  patch14`) — no TensorFlow, no `autokeras`, no runtime download.
- **Fixed a real, pre-existing gap found while wiring this up**: the
  `[filtered]` extra declared `transformers` but never an inference backend
  for it (`torch`/`tensorflow`/`flax`) — every classifier in this module,
  including the ones already shipped in `1.3.3`, would fail on first real
  inference call without one already present by luck. Added `torch>=2.0`
  to `[filtered]`.
- `requirements-dev.txt` gained `numpy>=1.24,<2.5` (the upper bound: numpy
  2.5's own type stubs use PEP 695 `type X = ...` syntax that mypy 1.20.2
  rejects under this project's `python_version = "3.10"` target, aborting
  the whole mypy run, not just warning about numpy specifically) — needed
  because `safety.py`'s new `_clip_image_embedding` does a real
  `import numpy` internally to L2-normalize the CLIP embedding (a
  requirement discovered by checking the actual norm of LAION's own
  published test embeddings: ≈1.0, not raw/unnormalized — using an
  unnormalized embedding would have silently produced nonsense scores).
- Uses the low-level, architecturally-stable `model.vision_model` +
  `model.visual_projection` submodules to compute the CLIP embedding,
  rather than the higher-level `get_image_features()` convenience method,
  whose return shape was found to differ across `transformers` major
  versions (a plain tensor historically; a wrapped
  `BaseModelOutputWithPooling` object in the version this was verified
  against) — this project's own `transformers>=4.30` pin has no upper
  bound, so the code needs to stay correct across that whole range.
- `ci.yml`'s checkout step now fetches Git LFS content (`lfs: true`). Not a
  test-suite regression risk today (`onnxruntime` is mocked in CI, never
  installed, so nothing opens the real `.onnx` file), but a plain checkout
  otherwise leaves an LFS pointer stub in its place, which would silently
  break any future build/publish step reading the real bytes.

## [1.3.3] - 2026-08-10

Re-evaluated both `safety.py` classifier choices against real, independently
run tests (not vendor claims) and swapped one of them.

### Changed

- **Text NSFW classifier: Detoxify -> `eliasalbouzidi/distilbert-nsfw-text-classifier`.**
  Detoxify scores general toxicity (hate/insult/threat/obscenity), not
  NSFW/sexual content specifically. On a hand-built probe set, sexual-but-
  not-abusive text scored 0.01-0.40 on Detoxify (Detoxify's own default
  threshold in this module is 0.8, so it would have MISSED these) but 0.99+
  on the NSFW-specific model; both agreed on clean text (~0) and
  toxic-and-sexual text (~0.99+). Also simplifies the `[filtered]` extra:
  both the text and image classifiers now load through `transformers`
  alone — the `detoxify` package is dropped entirely.

### Evaluated and kept as-is

- **Image NSFW classifier: `Falconsai/nsfw_image_detection` stays, LAION's
  `CLIP-based-NSFW-Detector` was NOT swapped in**, despite being the more
  widely-cited option (it filters LAION-5B, the dataset behind Stable
  Diffusion). Ran LAION's ViT-L/14 model for real against its own public,
  manually-annotated test set (`nsfw_testset.zip`): 96.16% accuracy, 94.56%
  recall, 97.58% precision, 2.29% false-positive rate at this module's 0.8
  threshold — solid, and independently verifiable by anyone. But its
  *documented* loading path needs a second deep-learning framework
  (TensorFlow) plus the unmaintained `autokeras` and OpenAI `clip` packages,
  and downloads an un-versioned zip from a GitHub raw URL at runtime; worse,
  its packaged TensorFlow SavedModel no longer loads through Keras 3's own
  `load_model()` — only an undocumented `tf.saved_model.load(...)
  .signatures["serving_default"]` workaround got it running for this
  evaluation. Falconsai self-reports 98.04% accuracy (not independently
  verified — no real NSFW imagery was fetched for this evaluation; unlike
  CLIP embeddings, raw image bytes of that content are not something this
  project will download or store) but needs only `transformers`, matching
  the text classifier above, with no legacy-framework or fragile-download
  risk. See `safety.py`'s module docstring for the full writeup.

## [1.3.2] - 2026-08-10

Test suite consolidation: no runtime behavior changes, test-only. The suite
had grown to 263 pytest items (many narrow, single-assertion unit tests) —
consolidated into 99 broader functional tests, each walking several related
scenarios sequentially in one function body instead of one function per
scenario. Coverage improved slightly (92.05% -> 92.55%) in the process,
since a few genuinely uncovered lines got picked up along the way:
`mcp.main()` (44% -> 94% covered — was entirely untested) and
`privacy.augment_with_presidio` plus a couple of `pseudonymize`'s
disambiguation branches (80% -> 98%). `test_cli_argparse.py` in particular
went from 30 collected items (12 of them a `--help` parametrize sweep) down
to 4, since it exists only to prove the argparse twin mirrors `cli.py`'s
click surface — deep business-logic coverage stays in `test_cli.py` and the
library-level test files.

### Fixed

- `requirements.txt` pinned `os-helper>=2.3.0` without the `<3` upper bound
  `pyproject.toml`'s `dependencies` carries — now consistent.

## [1.3.1] - 2026-08-10

Packaging restructuring: the CLI, GUI, HTTP API, and MCP server are now ALL
part of the default install — `fastapi`, `uvicorn`, `fastapi-mcp`, and the
`mcp` SDK moved from the `[api]`/`[mcp]` extras into core `dependencies`.
Only two optional extras remain: `[cloud]` (cloud-provider mode: retry,
caching, pseudonymization, an OS-keychain fallback for API keys — merges the
former `cloud`/`cache`/`privacy`/`keyring` extras into one) and `[filtered]`
(real NSFW/toxicity classifiers — renamed from `[safety]`, same contents).
Nothing about runtime behavior changes; every optional dependency still
degrades gracefully (a light retry, no caching, a keyword heuristic, an
"unavailable" verdict) when its extra is absent.

### Changed

- `pyproject.toml`: `[api]` and `[mcp]` extras removed, their deps folded
  into core `dependencies`; `[cloud]`, `[cache]`, `[privacy]`, `[keyring]`
  merged into one `[cloud]` extra; `[safety]` renamed to `[filtered]`.
  `psutil` added as an explicit core dependency (`detect.server_load()`
  imports it directly; previously relied on it arriving transitively via
  `os-helper`).
- `requirements.txt` updated to mirror the new core dependency set.
- Removed the now-dead `ImportError` guards in `api.py`, `mcp.py`,
  `cli.py`'s `gui` command, and `cli_argparse.py`'s `_handle_gui` — fastapi/
  uvicorn/fastapi-mcp/mcp are no longer optional, so the "extra not
  installed" error paths were unreachable.
- Docs (`README.md`, `LISEZMOI.md`, `GUI.md`, `EXAMPLES.md`, `EXEMPLES.md`,
  `CONTRIBUTING.md`) and `ci.yml` updated to drop `[api]`/`[mcp]` install
  instructions and point `[cache]`/`[privacy]`/`[keyring]`/`[safety]`
  references at `[cloud]`/`[filtered]`. `EXEMPLES.md`/`LISEZMOI.md`'s
  `mode: cloud` sections, stale since before the 1.3.0 merge (still said
  cloud mode was unresolvable), now match `EXAMPLES.md`/`README.md`.
- Fixed a stray `safety.py` docstring line that still said the `safety=`
  default was cloud-only — it's been True for every engine, local or cloud,
  since the 1.3.0 merge.

## [1.3.0] - 2026-08-10

Merges the `cloud` branch: `mode: cloud` now actually works (it previously
raised `NotImplementedError` on `main`, per the "Keep main strictly local"
policy from `1.2.0`'s predecessor). Paid-provider calls are opt-in — nothing
about the local-only default path changes.

### Added

- **Anthropic and Gemini transports** (`llm._chat_anthropic`,
  `llm._chat_gemini`), closing the last TODO from the original cloud-phase
  commit. Every OpenAI-compatible provider (OpenAI, **Mistral**, OpenRouter,
  Together, Azure OpenAI) already worked via `_chat_openai`; Mistral is now
  in `_OPENAI_COMPATIBLE` and `engine._CLOUD_BASE_URLS`.
- **Real, provider-reported token counts for cost accounting.** Every
  transport (including Ollama's `prompt_eval_count`/`eval_count`) now returns
  `(text, usage)`; the `chat()` event gains `in_tokens`/`out_tokens` when the
  provider reports them, and `observe.estimate_cost_usd` now prefers these
  exact counts over its char-count heuristic whenever they're present (falls
  back to the heuristic otherwise, e.g. LangChain). `pricing.yaml` gained
  Mistral's four model tiers alongside the existing OpenAI/Anthropic/Gemini
  entries. Verified against a real, live Mistral call (see below).
- **`llm._cloud_api_key`**: resolves a cloud engine's API key via
  `os_helper.get_config` — its own fallback order in one call (a
  `settings.yaml`/`settings.json` file in the current directory, then any
  `.env` file, then the plain process environment) for the env var named in
  the engine's `api_key_env` field — then the OS keychain via the optional
  `keyring` extra as a last resort. The key VALUE is never read from or
  written to the engine descriptor itself. New `settings.yaml.example`
  (copy to `settings.yaml`, gitignored, fill in your key; an empty value is
  a deliberate "cloud stays off", not a missing file).
- **Failover chain, retry, and cache** (`llm._engine_chain`, `_with_retry`,
  `_cache_key_payload`): `chat(engine=..., retries=N, cache=True)`. A cloud
  engine's embedded local `fallback` is tried automatically on failure
  (paid -> local); `cache=True` memoizes identical calls via the optional
  `wallet-helper` extra so a repeated call never pays for the same cloud
  request twice.
- **`privacy.py` wired into `chat(..., pseudonymize=True)`**: scrubs personal
  data from the prompt with the engine's local fallback before a cloud send,
  restores it in the response. Cloud-only (a no-op on a local engine — there
  is nowhere for personal data to leak to), or with a loud warning if the
  cloud engine has no local fallback to scrub with.
- **`safety.py` (Phase 6.5, new): NSFW/policy scanning, for text AND images,
  for local AND cloud engines alike** — content policy is independent of who
  is billed, so this is on by default for every `chat()` call, not just
  paid ones (pass `safety=False` to opt out). Scans the outbound
  prompt/images and the inbound response; `action` policy is `block` (raise
  `SafetyViolation`) / `redact` (text only) / `warn` (log, pass through —
  the default, since this has no track record on real traffic yet).
  Detoxify (text) and a CLIP-based classifier (images, via `transformers`)
  are optional (`[safety]` extra); absent them, text scanning degrades to a
  crude keyword heuristic (never silently no-ops) and image scanning
  degrades to `"unavailable"` (never a fabricated verdict).
- `engine.resolve(mode="cloud")` now actually resolves instead of raising
  `NotImplementedError` — provider + model (+ optional `base_url`/
  `api_key_env`) plus a local `fallback` from the same brief.

### Verification

Everything above is covered by mocked tests (no network call, no API key,
no paid request) — 263 passed, 92.0% coverage, ruff/mypy clean. Also ran a
real, live call against Mistral (`mistral-small-latest`, via the
`settings.yaml` key) end to end: request/response, real token counts, and a
real computed cost ($0.0000048 for a two-word exchange) all confirmed
working outside the mocks. Anthropic/Gemini payload shapes are verified
against their documented APIs but have not had a live call yet.

## [1.2.0] - 2026-08-09

### Added

- **Local activity/cost ledger (`observe.py`), the first piece of the `cloud`
  branch's Phase 6.1 monitoring plan landed on `main`.** `llm.chat()` gained
  an observer seam (`add_observer`/`_emit`, ported from the `cloud` branch —
  cloud-agnostic, so it lands here independent of the rest of that branch):
  every call fans a small event out to registered observers. `observe.py`'s
  `Ledger` is the first consumer — a local, append-only SQLite database
  (`~/.best-engine-ai-helper/usage.db`) recording who called what (
  `BEST_ENGINE_USER` env var, else the OS login name; `observe.as_user(name)`
  for scoped attribution, e.g. per-request in a shared server), which
  model/backend, latency, success/failure, and an estimated cost (bundled
  `pricing.yaml`; always `0.0` for local Ollama/vLLM, `None` — never
  fabricated — for an unpriced cloud model). Built for the "one company,
  several users" case. New `activity` CLI command (table/JSON), `GET
  /api/activity`, and a GUI **Activity** section all read the same ledger.
  Enabled by default in the CLI, API, and MCP server; opt out with
  `BEST_ENGINE_NO_LEDGER=1`. **Scope note:** this repo's own commands rarely
  call `llm.chat()` themselves (only the `pull`/`validate` Ralph gates do) —
  the ledger's real value comes once downstream projects that import
  `best_engine_ai_helper.llm` also call `observe.enable()`; that's a
  per-project follow-up, not something this change does for the whole suite
  automatically. Cost accounting for actual paid-provider calls, and the
  remaining Phase 6.2 (Anthropic/Gemini transports) and 6.5 (NSFW safety)
  work, stay on the `cloud` branch until finished.
- **Task-description quality check in `recommend.parse_task`.** A missing or
  blank task now logs a loud warning instead of silently defaulting to a
  generic profile: "activity and cost monitoring cannot attribute this call
  to a job without one." Also runs best-effort language detection
  (`langdetect`, new core dependency, fully offline) on the task text; a
  string with no detectable language (symbols/digits only) warns too. The
  parsed report now carries a `language` field, surfaced in the CLI Markdown
  report and the GUI results panel. Detection confidence is deliberately NOT
  used as a "clean text" signal — `langdetect` can be confidently *wrong* on
  a short phrase (e.g. "write SQL queries" detects as French at 99.9%
  confidence), not merely uncertain.
- **Live server-load awareness, opt-in via `--live`.** `detect.server_load()`
  snapshots current free RAM, CPU/GPU utilization, disk usage, and how many
  local engines (Ollama models, vLLM processes) are already running.
  `score.effective_budget()` (and `rank()`/`select()`) accept an optional
  `load` parameter: when given, the recommendation's memory budget is capped
  at what is actually free right now (not just the theoretical accelerator
  pool) and further derated when the CPU is saturated or disk space is low.
  Off by default everywhere (`recommend()`'s `load=None`, CLI's `--live`
  flag on `recommend`/`report`, API's `live: bool = False` on
  `POST /api/recommend`, GUI's "live server load" checkbox) — it adds a
  ~0.1-0.5s probe and makes the result depend on the exact moment it ran
  rather than being a deterministic function of the hardware alone, which
  matters for reproducible reports and CI. The report gains a `server_load`
  key (and a Markdown/GUI section) only when `--live` is used.
  **Cross-repo note:** the underlying generic live-metric probes
  (`cpu_percent`, `available_ram_gb`, `disk_usage_gb`,
  `gpu_utilization_percent` — including an Apple Silicon GPU-utilization
  read via `ioreg`'s `IOAccelerator` node, which needs no `powermetrics`/sudo)
  were added to `os-helper`'s `hardware_utils.py`, matching that module's own
  "raw facts belong here, AI-domain interpretation belongs to the consumer"
  split. They are not yet in a published os-helper release; the `os-helper`
  pin in `pyproject.toml` needs bumping once one ships, or `server_load()`
  raises on a fresh install.

### Changed

- **Repository no longer distributed as a Claude/OpenCode Agent Skill.**
  Removed `skills/best-engine-ai-helper/` (the skill packaging README) and
  `TRIGGERS.md` (an orphaned natural-language trigger catalog that existed
  only to back that skill's routing). The project ships as a library, CLI
  (`cli.py` + `cli_argparse.py`), FastAPI GUI/HTTP API (`api.py`), and MCP
  server (`mcp.py`) — no skill surface.
- **`locales/i18n.yaml` is now the single source of truth for every
  GUI-visible string AND every model-facing prompt template.** New shared
  loader `i18n.py` (`meta()` / `gui_strings()` / `prompt(key, field)`).
  `gui.py` no longer hardcodes its French/English label tables (`gui:`
  namespace, 57 semantic keys, `meta.default_locale` / `meta.supported_locales`
  drive fallback). `ralph.py` (eyeball + prose Ralph loops), `validate_vlm.py`,
  and `validate_llm.py` no longer hardcode their system/user prompt strings
  either — they live under `prompts:`, authored in English
  (`meta.model_prompt_locale`) since these are model instructions, not GUI
  copy that needs translating (see CODING.md section 21.3.3). Wording is
  unchanged in every case; only where it lives changed.
- **`references/CODING.md` refreshed from its canonical gist**, with one
  deliberate, documented deviation: the gist's "Agent Skills" section (and
  every skill-specific delivery-surface reference) is dropped, since this
  project does not ship one. Root `CODING.md` rewritten as a short pointer to
  the mirror plus the standard's key bullets (now including the
  `locales/i18n.yaml` and multi-surface-delegation rules). `CONTRIBUTING.md`'s
  mirrored bullet list updated to match.

### Fixed

- **`gui.py` mypy strict compliance** for the new locale-loading code path
  (`_locale_meta` / `_locale_gui_strings` typed precisely instead of a bare
  `dict[str, object]`).
- Two undocumented FastAPI route handlers (`api.py`'s `root()` and `gui()`)
  now carry a one-line docstring.
- **A misattributed `# type: ignore[arg-type]` in `cli.py`/`cli_argparse.py`**
  sat on the `headroom=` line instead of `kind=k` (the actual mismatch: `k`
  is `str`, `rank()` expects `Literal["llm", "vlm"]`, narrowed only by the
  CLI's own `choices=`/`typer.Option`, not by mypy). A newer mypy no longer
  flags either line either way, which is how this passed CI unnoticed; an
  older local mypy (1.20) still catches it. Moved the ignore to the line it
  actually covers, with a comment explaining why it's needed.
- **`ruff`/`mypy` were unpinned (`ruff>=0.5`, `mypy>=1.10`) in
  `requirements-dev.txt`, so CI silently drifted to newer versions than the
  local dev environment.** Two concrete bites: mypy 2.3 (CI) missed the
  misattributed `type: ignore` above that mypy 1.20 (local) caught, and
  ruff 0.16 promoted Markdown formatting from preview-only to stable, so
  adding `ruff format --check .` to CI below failed on `README.md`/
  `LISEZMOI.md`/`EXAMPLES.md`'s embedded Python code fences even though
  they were never touched locally. Pinned both (`ruff==0.15.21`,
  `mypy==1.20.2`) to keep CI and local checks looking at the same rules.

## [1.1.0] - 2026-08-06

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
  expects.
- **Mypy + CI collection regressions from the argparse CLI / MCP work.**
  `cli_argparse.py`'s `_score.rank` call, its three `_add_*_group` helpers
  (missing `_SubParsersAction` type argument), and `main`'s `ns.func(ns)`
  dispatch (returning `Any` against a declared `int`) are now typed cleanly.
  Separately, CI installed only the `[api]` extra, so `pytest
  --doctest-modules` failed to even collect `mcp.py` (it raises at import
  time without `[mcp]`, by design — same pattern as `api.py`); CI now
  installs `.[mcp]`, which already pulls in `[api]`'s deps too.

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
