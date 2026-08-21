# best-engine-ai-helper

[🇫🇷](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/README.md)

Pick and pull the best local large language model (LLM) or vision-language model (VLM) for the hardware in the current machine.

![Best Engine AI Helper glove logo](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/logo.png)

The tool detects available memory (Apple Silicon unified pool, NVIDIA VRAM, or system RAM), consults a bundled model catalog, and selects the highest-scoring model that fits within a configurable safety headroom. After selection, it pulls the model via Ollama and puts it through two quality gates before trusting it: does it catch and fix a known flaw seeded into a short text (the Ralph Loop), and does it spot an obvious visual defect seeded into a small test image (the Ralph Eyeball Loop)? Only a model that passes both gets its environment file written, the file downstream projects read to find the chosen model.

## The Promise

`best-engine-ai-helper` is designed to run entirely offline once the weights
are downloaded. Two honest cases:

1. **Guaranteed local.** Hardware detection, model selection, the quality
   gates, and writing the environment file all run on your machine. No
   telemetry, no account, no dependency on a cloud service.
2. **The only caveat: the initial download.** The `pull` command downloads
   the model weights via Ollama (a normal download from Ollama's servers).
   After that, everything runs offline. Refreshing the catalog
   (`catalog update`) is also online, but optional: the bundled catalog is
   enough for everyday use.

A minimal browser GUI (`best-engine-ai-helper gui`) covers the read-only half
of this flow (the hardware snapshot and the task-to-engine recommendation)
without touching the terminal. The page is bilingual: French by default,
English via `/gui?lang=en`, with a header link to switch. See
[GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md).

## In production

This package sits at the base of the AI Helpers suite's model-selection layer: three other published packages (`md2star`, `standpoint`, `vocal-helper`) route every LLM and VLM call through it instead of hardcoding a model name. It ships on PyPI with a green CI gate on every push (ruff, mypy, and a pytest suite held above 90% coverage), and every release is a semantic-version tag on GitHub.

## Documentation

[💻 Documentation](https://harchaoui.org/warith/ai-helpers/docs/best-engine-ai-helper-doc/)

[🗺️ Landscape](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LANDSCAPE.md)

[📋 Examples](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXAMPLES.md)

## Requirements

- Python 3.10 or later
- [Ollama](https://ollama.com) (needed for `pull`, `validate`, `env`; not for `detect`, `recommend`, or `report`)
- Everything else installs automatically: os-helper (hardware detection),
  PyYAML, click, requests, langdetect, and the FastAPI/MCP surfaces
  (`fastapi`, `uvicorn`, `fastapi-mcp`). The CLI, GUI, HTTP API, and MCP
  server are all part of the default install, nothing extra to opt into.
- Optional: `[cloud]` for cloud-provider mode (retry, caching,
  pseudonymization, an OS-keychain fallback for API keys) and `[filtered]`
  for real NSFW classifiers (a DistilBERT text model; LAION's CLIP-based
  image detector, via `transformers` for the CLIP encoder and a bundled
  `onnxruntime` model for the classifier head). See [EXAMPLES.md's
  `resolve`/`mode: cloud`
  section](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXAMPLES.md#resolve)
  for the full story; both degrade gracefully (a keyword heuristic, or an
  "unavailable" verdict) when absent, never a hard failure.

## Installation

The package is pure Python (Python 3.10+). The only platform-specific pieces
are **Python itself** and the optional **Ollama** runtime (needed only for
`pull` / `validate` / `env`, not for `detect`, `recommend`, `report`, the GUI,
or the MCP surface). Pick your OS below.

### 🍎 macOS

```sh
# 1. Python 3.10+ (skip if you already have it: python3 --version)
brew install python

# 2. Install into an isolated virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install best-engine-ai-helper

# 3. Optional: Ollama, only if you'll run `pull`
brew install ollama          # then: ollama serve
```

Hardware detection uses the built-in `system_profiler` (Apple Silicon unified
memory), so nothing extra is needed.

### 🐧 Ubuntu / Debian

```sh
# 1. Python 3.10+ with venv support
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

# 2. Install into an isolated virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install best-engine-ai-helper

# 3. Optional: Ollama, only if you'll run `pull`
curl -fsSL https://ollama.com/install.sh | sh   # then: ollama serve
```

GPU detection is automatic when the vendor tools are on `PATH`: `nvidia-smi`
(ships with the NVIDIA driver) for NVIDIA VRAM, `rocm-smi` (ROCm stack) for
AMD. With no GPU it falls back to system RAM.

### 🪟 Windows (PowerShell)

```powershell
# 1. Python 3.10+ (skip if you already have it: py --version)
winget install Python.Python.3.12

# 2. Install into an isolated virtual environment (recommended)
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install best-engine-ai-helper

# 3. Optional: Ollama, only if you'll run `pull`
winget install Ollama.Ollama
```

NVIDIA VRAM is detected via `nvidia-smi` (installed with the driver).

### From source (any OS)

```sh
git clone https://github.com/warith-harchaoui/best-engine-ai-helper
cd best-engine-ai-helper
pip install -e .
```

### Verify the install

```sh
best-engine-ai-helper --version
best-engine-ai-helper detect     # prints this machine's hardware as JSON
```

Every command is also available through an argparse twin,
`best-engine-ai-helper-argparse` (same flags, same output): the suite's
zero-extra-runtime-dependency CLI surface (click is a core dependency here,
so `best-engine-ai-helper` stays the primary entry point; the argparse twin
is the added surface, not a replacement).

## Quick start

```sh
# See what hardware this machine has
best-engine-ai-helper detect

# See which models would be selected (no download)
best-engine-ai-helper recommend

# Recommend the best engine(s) for a task, as a report (Markdown + JSON)
best-engine-ai-helper report --task "product descriptions and image-quality checks" --out engine

# Browse the full catalog
best-engine-ai-helper catalog show

# Browse the hardware chip table
best-engine-ai-helper hardware show

# Launch the browser GUI
best-engine-ai-helper gui

# Who's calling what, and at what cost (local SQLite ledger)
best-engine-ai-helper activity
```

The same `/api/system`, `/api/recommend`, and `/api/activity` endpoints are
also reachable as MCP tools for any MCP-aware agent host:

```sh
best-engine-ai-helper-mcp        # -> http://127.0.0.1:8000 (MCP at /mcp)
```

See [EXAMPLES.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXAMPLES.md) for runnable recipes with expected output, and [GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md) for the browser GUI.

## GUI

`best-engine-ai-helper gui` serves a single-page browser GUI (FastAPI +
vanilla JS, no build step) at `http://127.0.0.1:8000/gui`: the same hardware
snapshot as `detect`, and a task-description box that returns the same
recommendation as `report`, with no terminal needed. The page is bilingual
(French by default, English at `/gui?lang=en`), with a header link to switch.

![Recommendation results](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/screenshots/gui-recommendation.png)

See [GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md) for the full write-up, the JSON API it's built on, and
how the favicon / touch-icon set is generated from `assets/logo.png`.

## Activity ledger

Every `llm.chat()` call, whether from this tool's own `pull`/`validate` gates
or from any downstream project that imports `best_engine_ai_helper.llm`, can
be recorded to a local, append-only SQLite ledger
(`~/.best-engine-ai-helper/usage.db`): who called it (`BEST_ENGINE_USER` env
var, else the OS login name), which model and backend, latency,
success/failure, and an estimated cost for paid backends (always `0.0` for
local Ollama/vLLM). Built for the "one company, several users on a shared
machine" case: answer "who is calling what, how often, at what cost" without
a separate telemetry stack. Local only, no network call, no third-party
service.

```sh
best-engine-ai-helper activity              # table
best-engine-ai-helper activity --format json
```

The CLI, GUI, and MCP server all enable recording by default; opt out with
`BEST_ENGINE_NO_LEDGER=1`. The GUI's **Activity** section and `GET /api/activity`
read the same ledger. See `best_engine_ai_helper.observe` for the library API
(`enable()`, `as_user(name)`, `Ledger.summary()`).

## How selection works

Selection weighs four factors, each made explicit in the `report` output so the
recommendation is reproducible and can be argued with.

### 1. Structured-output capability (can it be driven by a schema?)

The AI-Helpers suite routes every task through a JSON schema (intent parsing,
edit proposals, visual critique). Some open-weight models cannot honour Ollama's
grammar-constrained structured output and return an empty response under it (the
Qwen3-VL family does this, verified on `qwen3-vl:8b`). A model marked
`structured_output: false` in the catalog is never auto-selected, however high
its raw benchmark, and it still appears lower in the ranked list so an explicit
non-schema task can find it. Entries with no such marker are assumed capable.

### 2. Memory fit (will it run on the accelerator?)

Available memory comes from the highest-priority probe that succeeds: Apple
Silicon unified memory (`system_profiler`), NVIDIA VRAM (`nvidia-smi`), AMD VRAM
(`rocm-smi`), else half of system RAM as a conservative CPU-only estimate.

The usable budget is **not** the whole pool. On Apple Silicon, Metal caps GPU
allocations at about **66%** of unified memory at or below 36 GB and about
**75%** above it (`recommendedMaxWorkingSetSize`); past that, work spills to the
CPU and slows sharply. An extra safety `headroom` (default **0.85**) is applied
on top, reserving room for the OS, your own application, and a model's own
working memory: as a conversation or prompt gets longer, a model keeps a
running cache of everything it has already read so it does not recompute it
on every new word (the KV cache), and that cache keeps growing as context
fills. A catalog entry's `ram_gb` is already a peak-inference estimate
(weights plus a moderate KV cache; roughly weights ÷ 0.7, since weights are only
about 70% of runtime memory and can approach 2× at long context). A model fits
when that `ram_gb` is at most the budget.

### 3. Task fit (is it good at the job?)

A task, even a vague phrase like *"retail descriptions and image-quality
checks"*, maps to a benchmark axis (`generalist`, `code`, `math`, `ocr`,
`vision`) and to the model kinds it needs (text implies an LLM, anything visual
implies a VLM).
Among fitting models, the highest benchmark on that axis wins.

### 4. Throughput (how fast will it generate?)

Token generation is **memory-bandwidth bound**: each token reads the active
model from memory once, so the ceiling is `bandwidth ÷ model-size`, derated to
about 65% for KV-cache reads and overhead. `report` estimates tokens/s per
candidate from the chip's memory bandwidth, and offers a lighter, faster
alternative when one is nearly as strong. Bigger is not automatically better: a
72B model that technically fits may run at a few tokens/s, while an 8-14B model
leaves headroom and runs several times faster.

When nothing fits, the tool falls back to the smallest model and says so.

### 5. Live server load (optional, `--live`)

The four factors above describe the machine's *theoretical* capacity. Add
`--live` (`recommend`/`report`; `live: true` on `POST /api/recommend`) to also
weigh what else is happening on it *right now*: current free RAM, CPU/GPU/disk
usage, and how many engines (Ollama models, vLLM servers) are already running.
A busy or already-loaded machine gets a smaller, more realistic budget than an
idle one with identical hardware. Off by default: it adds a short live probe
(~0.1-0.5s: `nvidia-smi`/`ioreg`, a local Ollama ping, a `psutil` sample) and
makes the recommendation depend on this exact moment rather than being a
deterministic function of the hardware alone, which matters for reproducible
reports and CI.

**Sources.** Apple Metal working-set cap (Apple developer docs / apple-specs);
inference-memory breakdown weights + KV (15-20%) + overhead (5-10%) (local-LLM
sizing guides); bandwidth-bound decode `tok/s ≈ bandwidth ÷ active-bytes × 0.5-0.8`
(llama.cpp / MLX community benchmarks). The exact ratios live as documented
constants in `score.py`.

## Available commands

| Command | Description |
|---------|-------------|
| `detect` | Print the detected hardware as JSON |
| `recommend` | Rank candidates for this hardware (no download) |
| `report` | Recommend the best engine(s) for a task (Markdown + JSON) |
| `catalog show` | Print the merged model catalog |
| `catalog update` | Refresh the model cache from the ApXML open-weight directory (`--limit N` for a partial refresh) |
| `hardware show` | Print the known hardware chip table |
| `hardware update` | Record this machine's chip and memory in the hardware cache |
| `pull` | Download the best model and run the Ralph gates |
| `validate` | Run the Ralph gates on the currently configured model |
| `env` | Print the shell export block ready for `~/.zshrc` |
| `gui` | Launch the browser GUI |
| `activity` | Summarize the local activity/cost ledger (calls, cost, by user/model, errors) |
| `usages list` | List usage profiles and families (needs only, never a model) |
| `usages show <profile>` | Show one profile's needs (task, structured output, floors) |
| `usages resolve <profile>` | Resolve a profile (or `--family`) to the model best-engine picks here |

## Model catalog

The bundled seed catalog (`models.yaml`) covers the Qwen 3, Qwen 2.5, Qwen 2.5-Coder, and Gemma 3 families (from 3B to 72B parameters, across Q4_K_M and Q8_0), plus a small set of `kind: embed` text embedders for the retrieval index. The catalog tracks on-disk size, estimated peak RAM, and benchmark scores from the Open LLM Leaderboard v2, the OpenVLM Leaderboard, EvalPlus (code), and MTEB (embedding retrieval). This is the *search space* best-engine picks from: it is never a per-usage choice.

`catalog update` refreshes the cache from the [ApXML LLM directory](https://apxml.com/models?modelType=open_weight) (open-weight models with their per-quant VRAM needs, consulted regularly). It fetches the specs, normalizes them to catalog entries, and merges them into `~/.best-engine-ai-helper/catalog_cache.yaml` by id (the bundled seed is never modified). Use `--limit N` for a quick partial refresh. ApXML's static pages carry specs but no numeric leaderboard scores, so refreshed entries keep null benchmarks (and rank low) until a scored source, such as the Open LLM Leaderboard v2 or the OpenVLM Leaderboard, fills them.

## Hardware table

`hardware.yaml` lists known GPU and Apple Silicon chip configurations with their usable memory (physical pool minus OS and driver overhead). There is no public specs API spanning every chip, so `hardware update` records ground truth for the machine it runs on instead: it detects this machine's chip, memory pool, and Ollama-usable share, and upserts that row into `~/.best-engine-ai-helper/hardware_cache.yaml` (keyed on chip + memory tier).

## Downstream integration

There are two ways to consume the selected model. Use the first when every tool on the machine should share one model. Use the second when a project has its own idea of the job and wants the pick that fits that job, not a generic one.

### Pattern A: one shared model for the whole machine

After `best-engine-ai-helper pull` completes, it writes `~/.best-engine-ai-helper/env.sh`. `pull` picks one model that clears both quality gates and points the text and vision slots at it, so both tags match (the exact tag depends on your hardware):

```sh
export BEST_LLM_TEXT=gemma3:12b
export BEST_LLM_VISION=gemma3:12b
export BEST_LLM_BACKEND=ollama
export BEST_LLM_BASE_URL=http://localhost:11434
```

Projects that consume the selected model source this file or read the companion `config.json`.

### Pattern B: a per-project engine resolved from a tuned brief

A project usually knows its job more precisely than a machine-wide default can, and the quality of the pick depends on how well that job is described: the task text is what maps to a scoring axis and decides whether a VLM is needed (see [How selection works](#how-selection-works)). So the project keeps a committed **brief** describing the job and resolves it, per machine, into a gitignored **engine file** that names the backend and model to use. No `DEFAULT_MODEL` constant lives in the project: the model is always read from the resolved engine file.

1. **Commit the brief**: `llm.brief.yaml` in the repo, hardware-independent:

   ```yaml
   kind: both              # llm | vlm | both
   headroom: 0.5           # max fraction of usable accelerator memory (clamped to 0.5)
   min_tps: 15             # comfort throughput floor (tokens/s)
   structured_output: true # the job needs schema-constrained output
   task: >-
     Name PCA axis poles as schema-constrained JSON, write a short analysis in
     the table's own language, and sanity-check the rendered chart image.
   ```

2. **Resolve it, per machine**: writes a gitignored `llm.engine.yaml`:

   ```sh
   best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
   ```

   The backend is chosen for the hardware: **vLLM when a discrete GPU (NVIDIA/AMD) is present, Ollama otherwise** (macOS, CPU-only Linux, Intel iGPU). The pick is deliberately conservative: the memory headroom is capped at 0.5, and among models within a few benchmark points of the best it takes the leanest and fastest, not the largest that merely fits. vLLM picks are sized against full FP16 weights (heavier than the Ollama Q4 estimate), so a vLLM pick is realistic on the real GPU. The output is hardware-specific; add it to `.gitignore`:

   ```yaml
   backend: ollama
   base_url: http://localhost:11434
   llm: {model: gemma3:12b, ram_gb: 9.2, est_tokens_per_s: 28.3, structured_output: true}
   vlm: {model: gemma3:12b, ram_gb: 9.2, est_tokens_per_s: 28.3, structured_output: true}
   serve: [ollama pull gemma3:12b]
   ```

3. **Consume it, no constant**: read the engine at call time and let the transport route to the right backend:

   ```python
   from best_engine_ai_helper import ensure, llm

   engine = ensure(".")            # loads llm.engine.yaml, or resolves it from
                                   # llm.brief.yaml on first use
   summary = llm.chat(prompt, engine=engine, kind="llm")
   critique = llm.chat(prompt, engine=engine, kind="vlm",
                       images=[png], json_schema=SCHEMA)
   ```

   `chat` reads the backend and model from the engine file and dispatches to Ollama (`/api/generate`) or vLLM (OpenAI-compatible `/v1/chat/completions`) transparently, with schema-constrained structured output on both.

**Missing-file policy.** The brief is committed, so its absence is a real bug and `ensure` raises loudly with the command to run. The engine file is gitignored and machine-specific, so its absence is normal: `ensure` resolves it from the brief on first use. This keeps the model out of any variable: the resolved engine file is the single source of truth.

The suite's consumers, [Standpoint](https://github.com/warith-harchaoui/standpoint), vocal-helper, and md2star, follow this pattern; each ships an `llm.brief.yaml` describing its own job (Standpoint's, for instance, names schema-constrained JSON, so the structured-output gate rules out higher-scoring vision models that cannot honour a schema and picks the strongest one that can) and reads the model only from the resolved engine file.

## Usages / task profiles

Where a brief is written per repo, the recurring eight workloads are named once in a bundled **usage catalog** (`usages.yaml`). Each **profile**, `text2sql`, `rag-answer`, `embeddings`, `text2sql-figures`, `report-bluf`, `classification`, `pii-rgpd`, `persona`, states only its **needs**: task type (text / code / vision / embeddings), whether it needs structured output, a throughput floor, a memory headroom, an advisory quality bar, and a context-length hint. A profile is, at heart, a named brief, so it is resolved by the **same four-criteria picker** as any brief.

A profile **never names a model.** best-engine is the sole decider: it reads the needs, probes the machine, and chooses the concrete local model, writing that choice only into a generated engine file (`llm.engine*.yaml`) that is **gitignored and machine-specific**, never a committed literal. That is the whole point of the tool.

Profiles are grouped into **families**: the usages that can share one model, so a machine need not hold eight:

| Family | What it needs | Profiles |
|--------|---------------|----------|
| **F1: constrained generation** | code + reliable structured output (SQL / JSON), deterministic | `text2sql`, `text2sql-figures`, `classification`, `pii-rgpd` |
| **F2: prose generation** | faithful FR/EN prose over long context | `rag-answer`, `report-bluf`, `persona` |
| **F3: embeddings** | multilingual, multi-granular retrieval vectors (never a chat model) | `embeddings` |

Resolving a family yields **one** model for the group; resolving a single profile yields the possibly-specialised model for that job when the hardware allows it. On a roomy machine best-engine may specialise; on a tight one a family collapses onto one model.

Discover and resolve through the existing CLI / library surface:

```sh
best-engine-ai-helper usages list                 # every profile + family (needs, no models)
best-engine-ai-helper usages show text2sql        # one profile's needs
best-engine-ai-helper usages resolve text2sql     # -> the model best-engine picks here
best-engine-ai-helper usages resolve --family F1 --out llm.engine.F1.yaml
```

```python
from best_engine_ai_helper import resolve_usage, resolve_family, list_usages

for u in list_usages():
    print(u["name"], u["family"], u["status"])

engine = resolve_usage("text2sql")   # best-engine chooses the model for THIS machine
family = resolve_family("F1")        # one model for the whole constrained-generation group
```

best-engine writes the retained models into the gitignored `llm.engine*.yaml` for this machine (the extension of the `env.sh` it already emits); the app reads that file and re-resolution re-decides if the hardware changes. Adding a profile is a few lines in `usages.yaml`; a user overlay at `~/.best-engine-ai-helper/usages_cache.yaml` overrides by name.

## Author

[Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

## Acknowledgements

Special thanks to [Victor Favreau](https://www.linkedin.com/in/victor-favreau-41b823117/) for fruitful discussions.

## License

[BSD-3-Clause](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LICENSE). Copyright 2026 Warith Harchaoui.
