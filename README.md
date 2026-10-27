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
   enough for everyday use. Layer streaming follows the same rule: one
   download from the HuggingFace Hub, then the model runs from your own disk —
   in your own process, with no server at all.

A minimal browser GUI (`best-engine-ai-helper gui`) covers the read-only half
of this flow (the hardware snapshot and the task-to-engine recommendation)
without touching the terminal. The page is bilingual: French by default,
English via `/gui?lang=en`, with a header link to switch. See
[GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md).

## In production

This package sits at the base of the AI Helpers suite's model-selection layer: three other published packages (`md2star`, `standpoint`, `vocal-helper`) route every LLM and VLM call through it instead of hardcoding a model name. It ships on PyPI with a green CI gate on every push (ruff, mypy, and a pytest suite held above 90% coverage), and every release is a semantic-version tag on GitHub.

## Documentation

[💻 Documentation](https://deraison.ai/ai-helpers/docs/best-engine-ai-helper-doc/)

[🗺️ Landscape](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LANDSCAPE.md)

[📋 Examples](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXAMPLES.md)

## Requirements

- Python 3.10 or later
- [Ollama](https://ollama.com) (needed for `pull`, `validate`, `env`; not for `detect`, `recommend`, or `report`)
- Everything else installs automatically: os-helper (hardware detection),
  PyYAML, click, requests, langdetect, the FastAPI/MCP surfaces (`fastapi`,
  `uvicorn`, `fastapi-mcp`), and **airllm** for [layer
  streaming](#too-large-to-load-still-runnable-layer-streaming). The CLI, GUI,
  HTTP API, MCP server and the streaming backend are all part of the default
  install, nothing extra to opt into.
- **Budget around 2 GB for the install and a few minutes for it.** That is not
  this package — it is pure Python and tiny — it is airllm's stack: torch,
  transformers and accelerate. The trade is deliberate: "which model can this
  machine run" and "which model can it run if it streams the layers" are the
  same question, and a capability behind an optional extra is one most people
  never find. The import stays lazy, so none of that weight is paid at
  startup: `detect`, `recommend` and `report` are as fast as they ever were.
- Optional: `[cloud]` for cloud-provider mode (retry, caching,
  pseudonymization, an OS-keychain fallback for API keys) and `[filtered]` for
  real NSFW classifiers (a DistilBERT text model; LAION's CLIP-based
  image detector, via `transformers` for the CLIP encoder and a bundled
  `onnxruntime` model for the classifier head). See [Two modes: local (free)
  and cloud (paid)](#two-modes-local-free-and-cloud-paid) below and
  [EXAMPLES.md's `resolve`
  section](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXAMPLES.md#resolve)
  for the full story; both degrade gracefully (a keyword heuristic, or an
  "unavailable" verdict) when absent, never a hard failure.

## Installation

Python 3.10+. This package's own code is pure Python; its dependency tree is
not, because the layer-streaming runtime brings torch with it — so expect a
**download of about 2 GB** and a wheel chosen for your platform. The other
platform-specific piece is the optional **Ollama** runtime (needed only for
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

`best-engine-ai-helper` is the only command line this package ships: one
surface, built with click, which is a core dependency and not an optional
extra. Releases before 1.9.0 also installed a second, suffixed entry point
mirroring it command for command; there is one name now, and it is this one.

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

# Nothing good fits? See what this machine could run by streaming layers off
# disk, and what the better model would cost you in seconds per token
best-engine-ai-helper airllm compare --tokens 300
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
recommendation is reproducible and can be argued with. (One backend is judged on
different ones, because a different resource binds it: see [layer
streaming](#too-large-to-load-still-runnable-layer-streaming) below.)

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
CPU and slows sharply. An extra safety `headroom` (default **0.5**, the hard
ceiling: a larger value is clamped down to it) is applied
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

When nothing fits, the tool falls back to the smallest model and says so — and
on a machine with the disk for it, offers to run a *good* model instead by
streaming its layers (see [below](#too-large-to-load-still-runnable-layer-streaming)).

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

### Measured throughput, and why the estimate needed correcting

![The measurement loop: predict, choose, prove, and feed the measurement back into the next prediction](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/measurement-loop.png)

Everything above is an *estimate*. For a tool whose argument is that you should
measure rather than assume, that was the one place it assumed — so `pull` and
`validate` now measure it.

The measurement costs nothing extra. Both commands already pull a candidate and
put it through two Ralph gates, which means the tokens have already been
generated; all that was missing was a stopwatch. The figure lands in
`~/.best-engine-ai-helper/measurements.yaml`, keyed by model **and** machine,
since tokens per second is a property of both.

It is timed with Ollama's `eval_duration` — the decode phase as the daemon
measures it — rather than wall-clock time around the call, which also contains
prompt processing, HTTP, and any queueing. Each measurement records which clock
produced it, and only the daemon's clock is allowed to disqualify a model: wall
time understates decode speed, and understating is what would reject a model
that runs perfectly well.

Re-measuring the same model keeps the **fastest** sample rather than the latest,
which is a correctness requirement rather than optimism. The quantity being
calibrated is a memory-bandwidth *ceiling*, and a busy machine can only ever
make an observation look slower than the hardware really is. This was learned
from the behaviour itself: `gemma3:12b` measured 15.2 tok/s on an idle machine
and 8.7 tok/s with three test suites running — and the contended sample alone
would have yielded a correction of 0.31 against the idle run's 0.54, skewing
every estimate on the machine. `samples` records how much evidence stands behind
the stored figure.

Three things follow, and the third is the interesting one:

1. **A measured figure beats an estimate** wherever both exist. `recommend`
   marks it with `*`.
2. **`min_tps` became a real constraint.** Every usage brief already carried a
   throughput floor and it only ever sorted. A model *measured* below the floor
   is now demoted out of auto-selection, exactly as one that does not fit in
   memory is. A model merely *estimated* below it is flagged and left alone, so
   a machine that has never run `pull` behaves exactly as it did before.
3. **Measuring one model improves the estimate for all the others.** The ratio
   of measured to estimated is a property of the machine far more than of the
   model, so it transfers. On the Apple M2 Max this was developed against,
   `gemma3:12b` decodes at **15.2 tok/s** where the bandwidth model predicted
   **28.3**. That ratio is applied to every subsequent estimate on this
   machine, including for models that were never pulled.

   That claim is tested rather than asserted — `scripts/validate_calibration.py`
   calibrates on one model, predicts another, and reports whether it beat the
   raw estimate. It did, in every direction tried, cutting the error from
   **64-118% down to 17-25%**. Worth stating both halves: the correction is
   large and it is not precision. Ratios ranged about **0.46 to 0.61** across
   models and across repeated runs of the same model, which is why the factor
   is a median over several measurements rather than one, and why a real
   measurement still outranks a calibrated estimate wherever one exists.
   Calibration moves an estimate from wrong by a factor of two to wrong by
   about a fifth; it does not make it right.

Point 3 is also why the comfort floor mattered more than it looked: `COMFORT_TPS`
is 15 tok/s, so an uncorrected estimate of 28.3 sails past it while the real
15.2 only just clears it. The correction is the difference between a
recommendation that sounds comfortable and one that is.

## Too large to load, still runnable: layer streaming

Everything above answers one question: **which model fits?** This section is
about the question that follows when the honest answer is *none of the good
ones*.

A transformer never needs all of its layers in memory at once. Decoding reads
layer 1, then layer 2, then layer 3; only the layer being computed has to be
resident. Keep one layer shard in memory, stream the rest off the disk, and the
memory a model needs stops scaling with its parameter count and starts scaling
with its *widest single layer*. A 70B model becomes about **4 GB resident
instead of 141 GB**.

The runtime that does this is [airllm](https://github.com/lyogavin/airllm)
(Apache-2.0), and it is a **core dependency**: streaming is available on every
install, with nothing to opt into.

```sh
pip install best-engine-ai-helper     # airllm comes with it
```

That is what the ~2 GB of the install buys (torch, transformers, accelerate).
It is paid once, at install time: the import is lazy, so nothing of that stack
is loaded until you actually stream a model, and `detect` / `recommend` /
`report` stay instant. If an interpreter cannot import airllm anyway — a
stripped container, a failed wheel build — every surface says so and points at
a reinstall, because at that point the install is incomplete rather than
un-opted-into.

### What it costs: seconds per token, not tokens per second

The trade is real and it is large. Under every other backend, generation is
bounded by **memory bandwidth**. Under streaming it is bounded by the **disk**,
and by a much harder bound: the weights do not stay anywhere, so each token
costs a full pass over the checkpoint. On a 4 GB/s NVMe drive a 70B model at
bf16 decodes at about **0.024 tok/s — roughly forty seconds a token**.

That makes streaming a batch tool: one hard question, an overnight evaluation, a
quality reference to judge the small model you run every day. Not a chat window.
The package says so in every surface, in seconds per token rather than in
tokens per second, because "0.024" reads like a rounding error and "41 s/token"
reads like what it is.

### The unit is a forward pass, which has three useful consequences

A streamed forward pass walks the layers in order, reads each shard, computes it
over *every token in the pass*, and frees it. So a pass costs what reading the
checkpoint once costs — **independent of how many tokens rode through it**.
Three things follow, and the second and third are levers you can pull:

**1. One generated token costs one pass.** Decoding is autoregressive: token
N+1 needs its own walk through every layer. This is where the
seconds-per-token figure comes from, and it is why a long *answer* is
expensive.

**2. The prompt is nearly free.** A 2000-token prompt is processed in the same
single pass as a 10-token one. No other backend has that property — under
Ollama or vLLM a long prompt is real prefill work. It makes streaming
comparatively good at *long document in, short verdict out*: classification,
extraction, judging, a one-line answer over a long context. Past a few thousand
tokens the per-layer compute starts to matter and the estimate says so rather
than pretending otherwise.

**3. A batch of B prompts costs one pass, not B.** B independent questions
answered together go B times faster per answer. Compression gives about 3×; a
batch of 8 gives 8×. For a real batch job the batch is the bigger lever by far,
and its only cost is one KV cache per sequence — which the footprint estimate
charges you for, so a batch job cannot plan itself into an out-of-memory.

So "how fast is it?" has three answers, and quoting the wrong one is how a batch
job gets planned as an interactive one. All three are reported:

| Figure | What it means |
|---|---|
| `decode_tps` | Steady-state rate, one token per pass. The headline, and the pessimistic reading. |
| `time_to_first_token_s` | One pass, prompt included — the *same* as any other token, which is unusual. |
| `effective_tps` | Tokens delivered per second of wall clock, batch included. The one that decides whether a job finishes overnight. |

### What it costs in memory, and where the real constraint is

Resident memory is one shard, plus the one thing streaming does **not** shrink:

```
resident ≈ (checkpoint ÷ layers) × 1.25 × shards_resident
           + KV cache for every layer
           + activations and runtime buffers
```

- `checkpoint ÷ layers` is the average shard. The **biggest** shard is the
  token-embedding matrix rather than a decoder layer — a modern 128k–152k
  vocabulary makes it so — hence the 1.25.
- `shards_resident` is 2 with airllm's prefetch on (the next shard is read while
  the current one computes, which is where its ~10% speed-up comes from) and 1
  without. Turning prefetch off is the single knob that gets a 70B model onto a
  4 GB card, and this package tries it automatically before rejecting a
  candidate for memory.
- The **KV cache is not streamed**: autoregressive decoding cannot recompute
  earlier keys and values, so every layer's slice stays resident for the whole
  generation. It grows with context *and* with depth, and on a deep model it is
  the second-largest term. This is why a context length buys or loses you a
  model here.

Worked, on a 4 GB/s NVMe drive at a 4k context:

| Model | Checkpoint | Layers | Resident (prefetch / serial) | s/token | Free disk to split |
|---|---|---|---|---|---|
| Llama-3.3-70B | 140 GB | 80 | 6.1 GB / 3.9 GB | 41 s | 294 GB |
| Qwen2.5-VL-72B | 146 GB | 80 | 6.3 GB / 4.0 GB | 43 s | 307 GB |
| Mixtral-8x22B (141B, MoE) | 282 GB | 56 | 14.0 GB / 7.7 GB | 83 s | 592 GB |
| Qwen3-235B-A22B (MoE) | 470 GB | 94 | 14.5 GB / 8.2 GB | 138 s | 987 GB |
| DeepSeek-V3 (671B, fp8, MoE) | 671 GB | 61 | 29.0 GB / 15.2 GB | 197 s | 1409 GB |
| Llama-3.1-405B | 810 GB | 126 | 18.5 GB / 10.5 GB | 238 s | 1701 GB |

Depth is what makes the last row possible: 405B parameters over 126 layers is a
*leaner shard* than 141B over 56. A mixture-of-experts breaks the usual
relation between size and depth (DeepSeek-V3 is 671B across 61 layers, where
the dense trend would predict twice as many), so a MoE entry that does not
declare its `layers` is **refused** rather than guessed at — a guess there is
wrong by a factor of two, in the direction that over-promises.

Read that last column first. **Disk space, not memory, is what usually refuses
a model**: airllm writes per-layer shards beside the downloaded checkpoint, so
the cache holds both at once and the split needs roughly twice the checkpoint
free. A 405B model is an 810 GB download before it is anything else. Memory is
the easy half of streaming.

These figures were checked against airllm's own published numbers, and the check
is worth stating precisely because the headline "70B on a 4 GB GPU" is true at a
context length nobody mentions: the same model is 3.0 GB serially at a 1k
context — the demo — 3.9 GB serially at 4k, and 6.1 GB at 4k with prefetch on.
The weights are identical in all three. What moves is the cache that is not
streamed.

### Native model or streamed model? `airllm compare` answers in one screen

This is the decision streaming actually forces, and neither ranking answers it
alone. A machine that runs a 14B model comfortably can also stream a 70B one:
the two differ by a handful of benchmark points in one direction and three
orders of magnitude of latency in the other.

A tokens-per-second column cannot settle it — 26 and 0.024 do not sit on a scale
anybody reasons about. Seconds for the same answer do:

```sh
best-engine-ai-helper airllm compare --tokens 300
```

```
=== LLM: ollama vs airllm, for a 300-token answer ===
  budgets: 11.04 GB resident (ollama) · 22.08 GB per shard (airllm) · disk 4.0 GB/s (declared)
model                       backend  score  resident  tok/s  answer  runs
--------------------------  -------  -----  --------  -----  ------  ----
qwen3:72b-q8_0              ollama   89     78.0      8.4    36 s    NO
qwen3:72b-q4_k_m            ollama   87     48.0      13.7   22 s    NO
qwen3:14b                   ollama   78     10.5      62.4   5 s     yes
gemma3:12b                  ollama   77     9.2       71.2   4 s     yes
Qwen/Qwen3-72B-Instruct     airllm   89     6.2       0.024  3.5 h   yes
Qwen/Qwen3-VL-72B-Instruct  airllm   88     6.2       0.024  3.5 h   yes

  Streaming buys 11 benchmark points (89 vs 78) for 2647x the wait: 3.5 h
  instead of 5 s for a 300-token answer.
```

Read the `runs` column: the 72B that scores 89 is right there in the Ollama
catalog and **does not fit** this 24 GB card. Streaming is what puts the same
class of model within reach, at the price in the `answer` column.

Each side is ranked by its own backend's rules, and the streamed side inverts
the usual one. Everywhere else this package picks the **leanest** model within a
few benchmark points of the best, because a gigabyte of residency is paid on
every run and competes with your own workload. Streaming breaks that premise:
residency is one shard whatever the model's size, so leanness buys nothing and
the anti-greed rule lands on an 8B model — the one senseless outcome, since an
8B model runs natively a hundred times faster. The streamed pick is instead the
**most capable** model that runs, by benchmark score, with parameter count
deciding only where no benchmark does.

Not simply the biggest, and the difference is not academic: the first rule here
*was* "biggest that runs", and this very table showed what it cost — a 141B
mixture-of-experts scoring 84 beat a dense 72B scoring 87 on parameter count
while taking twice as long per token. Bigger, slower **and** weaker is dominated
on every axis a caller cares about.

The comparison carries one deliberate bias, stated so you can discount it: the
native timing counts decode only and ignores prompt processing, while the
streamed timing is complete. That flatters the native side — the right direction
for an honest comparison whose conclusion is usually "stay native", and the
backend has to be willing to say that about itself.

### When it switches on

Never by default. Two triggers, and nothing else:

**Automatic** — the conventional backend resolved nothing that *fits* this
machine for a kind your brief needs. Streaming is then the difference between a
model and no model, so `resolve` proposes it with its cost stated. The rescue is
**per kind**: if your LLM fits and no VLM does, only the VLM falls back, and the
engine file is honestly mixed (Ollama for one kind, `airllm` for the other —
`model_for()` reads the per-kind backend first). The descriptor records the
decision and its reason under `airllm:`, *including when the answer was no*, so
a machine that cannot stream says why instead of staying silent.

**Manual** — you ask:

```sh
best-engine-ai-helper resolve --brief llm.brief.yaml --backend airllm
```

or in the committed brief:

```yaml
kind: llm
task: judge the quality of generated product descriptions
airllm: always          # auto (default) | always | never
airllm_compression: 4bit
```

or in the environment, which outranks nothing but defaults:

```sh
export BEST_ENGINE_AIRLLM=always   # or never, to switch the whole path off
```

`never` wins over everything, including the automatic trigger. A human who
wants a 235B model on a laptop overnight is making a legitimate choice that no
automatic rule should have to guess, and a human who never wants their disk
thrashed deserves one switch that means it.

### The commands

```sh
# Can this machine stream, should it, and what is in the way?
best-engine-ai-helper airllm status
best-engine-ai-helper airllm status --measure      # measure the disk, don't assume it

# What could it stream, biggest runnable first?
best-engine-ai-helper airllm plan --kind llm --compression 4bit --batch 8

# Native or streamed, same answer length, both prices
best-engine-ai-helper airllm compare --tokens 300 --batch 8

# Pay the download and the layer split now, not inside your first call
best-engine-ai-helper airllm prepare --model meta-llama/Llama-3.3-70B-Instruct
```

`--measure` is worth knowing about. The drive sets the entire speed of this
backend, so assuming its class (Apple internal NVMe, generic NVMe, SATA SSD,
spinning disk) is a weaker input than measuring it. The measurement writes and
reads back ~256 MB **with the page cache bypassed** (`F_NOCACHE` on macOS,
`O_DIRECT` on Linux); without that step the read is served from RAM and reports
the memory bus — which is how this probe first claimed 13 GB/s on a drive whose
own specification tops out near 7. On a platform with no way to bypass the cache
it returns nothing rather than a flattering number, and every surface labels the
figure `measured` or `declared`.

### Limits, stated plainly

- **No structured output.** airllm exposes raw generation, with no equivalent of
  Ollama's grammar-constrained `format`. Every streamed model is therefore
  `structured_output: false` — a fact about the backend, not about the weights —
  and the suite's schema-driven tasks stay on an Ollama model. `llm.chat` raises
  rather than honouring a schema in name only.
- **Text only.** The adapter returns a bare causal language model, without the
  image processor a VLM prompt needs. Images raise instead of being silently
  answered from the text alone.
- **No server.** airllm is a library, so a streamed model runs *in your own
  process*; the engine file's `base_url` is empty on purpose, because inventing
  a localhost port would send a consumer looking for a daemon that will never
  exist. `llm.chat` keeps the loaded model between calls — splitting a 141 GB
  checkpoint per call would make the transport unusable.
- **Experimental on CPU.** airllm's CPU path only works for unsharded models, so
  a CPU-only machine is not offered streaming automatically. It can still be
  asked for.
- **4-bit compression is unavailable on macOS.** It needs `bitsandbytes`, which
  publishes no macOS wheel, so the dependency carries a platform marker and
  Apple Silicon streams through MLX uncompressed. The sizing says so rather
  than quoting a speed-up that will not happen.
- **The context is 4096 tokens unless you ask for more.** airllm's own default
  is 512 and it *truncates* past it, so this adapter always passes an explicit
  `max_seq_len` — set to the same 4k the footprint above is priced at. The two
  numbers are deliberately the same one: a tool that quotes memory for a 4k
  context and then quietly runs a 512-token one would be lying in the direction
  where you lose the end of your prompt. Raise it with `max_seq_len=` and the
  KV term rises exactly as the formula says.

### Why airllm is imported rather than copied in

A fair question for a package that re-derives the arithmetic. Four reasons:

1. **Vendoring would not have avoided the weight.** airllm needs torch,
   transformers, accelerate, safetensors, scipy and sentencepiece, and a copy of
   its source would need all of them too — the weight *is* its dependency tree,
   not its code. So the ~2 GB is the price of the capability however it arrives,
   and it is paid here deliberately rather than hidden behind an extra nobody
   finds. What a copy would add on top is the next three problems.
2. **It is a moving target.** airllm's value is per-family sharding code (Llama,
   Qwen, DeepSeek, Mixtral, ChatGLM, Kimi), rewritten as each new family ships.
   Vendored, it would be frozen at the day it was copied and rot from the first
   release after.
3. **Licence hygiene.** airllm is Apache-2.0; this package is BSD-3-Clause.
   Importing keeps the two trees, and their notice obligations, separate.
4. **The division of labour is real, not a dodge.** airllm decides *how* to
   stream. Nothing in it decides *whether* this machine should, *which* model it
   should stream, or *what it will cost you in time* — and those are the three
   questions a caller of this package is actually asking.

So the runtime is imported and the **decision** is native: `offload.py` owns the
footprint arithmetic, the disk-bound timing model, the activation policy, the
native-versus-streamed comparison, and the catalog metadata all of it needs
(`layers`, `dtype`, `moe`). None of that imports airllm — which is what keeps
the import lazy, and what makes `airllm status` and `airllm compare` answer
correctly even in an environment where the runtime itself will not load.

### From Python

```python
import best_engine_ai_helper as beah  # airllm is a dependency, nothing to install

hw, disk = beah.available_memory(), beah.disk_profile()

# Should this machine stream at all?
decision = beah.airllm_decide(conventional_resolved=False)
print(decision["activate"], decision["reason"], decision["blockers"])

# What would a 70B cost here?
entry = {
    "id": "llama3.3:70b",
    "size_b": 70,
    "layers": 80,
    "hf_id": "meta-llama/Llama-3.3-70B-Instruct",
}
print(beah.airllm_footprint_gb(entry))  # 6.1 GB resident
print(beah.airllm_generation_time(entry, disk["read_gbs"], new_tokens=300, batch=8))

# Native or streamed, for a 300-token answer?
report = beah.airllm_compare(
    beah.load_catalog(),
    hw=hw,
    disk=disk,
    bandwidth_gbs=beah.compute_profile()["bandwidth_gbs"],
    new_tokens=300,
)
print(report["verdict"])

# And actually run it
text = beah.airllm_generate(
    "Judge this description:…", model="meta-llama/Llama-3.3-70B-Instruct", max_new_tokens=64
)
```

The HTTP surface answers the same questions in one call —
`GET /api/airllm?answer_tokens=300&batch=8` returns the decision, the storage
profile, the ranked plans and the comparison — and it is reachable as an MCP
tool like every other endpoint.

## Available commands

| Command | Description |
|---------|-------------|
| `detect` | Print the detected hardware as JSON |
| `recommend` | Rank candidates for this hardware (no download) |
| `report` | Recommend the best engine(s) for a task (Markdown + JSON) |
| `resolve` | Turn a committed usage brief into this machine's `llm.engine.yaml` |
| `doctor` | Compare what the engine file resolved against what the daemon can serve |
| `storage` | Plan capacity: what fits on disk, and what fits in memory together |
| `providers` | Which cloud providers are usable right now, and for the others, the variable to set |
| `catalog show` | Print the merged model catalog |
| `catalog update` | Refresh the model cache (`--ollama` for pullable tags from the official library, `--arena` to merge LM Arena ratings, `--limit N` for a partial refresh) |
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
| `airllm status` | Can this machine stream layers off disk, should it, and what is in the way (`--measure` to measure the drive) |
| `airllm plan` | What a too-large model would cost here, ranked: resident shard, seconds per token, disk to split |
| `airllm compare` | Native model vs streamed model, same answer length, both priced in seconds |
| `airllm prepare` | Download and split a checkpoint now, instead of inside the first call |

## Model catalog

The bundled seed catalog (`models.yaml`) covers the Qwen 3, Qwen 2.5, Qwen 2.5-Coder, and Gemma 3 families (from 3B to 72B parameters, across Q4_K_M and Q8_0), plus a small set of `kind: embed` text embedders for the retrieval index. The catalog tracks on-disk size, estimated peak RAM, and benchmark scores from the Open LLM Leaderboard v2, the OpenVLM Leaderboard, EvalPlus (code), and MTEB (embedding retrieval). This is the *search space* best-engine picks from: it is never a per-usage choice.

`catalog update` refreshes the cache from the [ApXML LLM directory](https://apxml.com/models?modelType=open_weight) (open-weight models with their per-quant VRAM needs, consulted regularly). It fetches the specs, normalizes them to catalog entries, and merges them into `~/.best-engine-ai-helper/catalog_cache.yaml` by id (the bundled seed is never modified). Use `--limit N` for a quick partial refresh. ApXML's static pages carry specs but no numeric leaderboard scores, so refreshed entries keep null benchmarks (and rank low) until a scored source, such as the Open LLM Leaderboard v2 or the OpenVLM Leaderboard, fills them.

`--ollama` widens the catalog from the [official Ollama library](https://ollama.com/library) instead of ApXML, and it exists because the servable catalog was stuck at twenty models for a reason that was never about scoring. ApXML can add hundreds of entries, but it names them by the paper's slug (`qwen36-35b-a3b`), which is a HuggingFace repo name that `ollama pull` cannot resolve — so those entries are vLLM-only. The library instead publishes families, their capabilities, and the sizes each one ships, and a family plus a size **is** a pull tag: `qwen3` plus `8b` is `qwen3:8b`, exactly the spelling the seed already uses. 256 families expand to roughly 420 pull tags, from a single request.

These entries carry **no benchmark scores**, because the library publishes sizes and descriptions rather than leaderboard results. They therefore rank *below* every scored model until a scored source fills them in. That is the point rather than a limitation: it widens what the tool can size and pull without changing what it recommends, and an invented score would be worse than an absent one — a null ranks low and is honest, a guess ranks wrongly and looks authoritative.

Sizes are derived from a constant **measured** against the seed's own fourteen Q4 entries, not guessed: 0.646 GB per billion parameters for text models and 0.714 for vision ones, since an image tower is genuinely heavier per parameter. That lands within about 5% of the seed's known-good figures. A family listing no size at all is skipped rather than recorded as zero, which would have made it appear to fit every machine.

`--arena` additionally merges conversational ratings from [LM Arena](https://lmarena.ai) mirrors, and two measured facts about that axis are worth knowing before you reach for it.

![Every Arena source tried in turn, and why each one fails today](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/arena-staleness.png)

**It serves the cloud catalog, not the local one.** Arena rates what its voters can chat with. Matched against the bundled catalogs (measured 2026-10-19 against the freshest working mirror), it covered **6 of the 10 cloud models** in `pricing.yaml` but only **3 of the 20 local models** in `models.yaml`.

The three local hits say more than the ratio does: they were `qwen2.5-coder:32b`, `qwen3:32b-q4_k_m` and `qwen3:32b-q8_0` — every match was a 32B build, and nothing smaller matched at all. The four embedding models (`nomic-embed-text`, `mxbai-embed-large`, `snowflake-arctic-embed2`, `bge-m3`) cannot match by construction: nobody chats with an embedder, so no leaderboard of chat preferences will ever rate one. So the axis is not simply "cloud-biased" — it rates large conversational models, which is most of a cloud price list and a minority of a local catalog. That is the opposite of what most people expect from a "model leaderboard", and it is the difference between using the axis well and waiting for it to break ties it will never see. The command prints its own `matched/total` every run, so you never have to take this paragraph's word for it.

**It may well return nothing at all.** Arena publishes no API, so every source here is a third-party scrape, and scrapes rot: as of 2026-10 the official site answers 403, one mirror returns empty leaderboards, and the freshest working mirror is more than a year stale. The adapter refuses a snapshot past its staleness bar and names the reason rather than merging it, because an Elo from a previous generation of models would rank 2025's models above 2026's — strictly worse than no Elo. When that happens the command says so and leaves the axis empty; it does not report a success that enriched nothing.

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

   The backend is chosen by a three-branch decision tree, matching what each backend actually supports well rather than what it merely runs on:

   - **macOS -> Ollama.** vLLM ships no native macOS runtime.
   - **CPU-only (Linux or macOS) -> Ollama.** vLLM's CPU-only path — notably on Linux — is its own reported weak spot; Ollama's CPU path is the well-trodden one.
   - **Discrete GPU (NVIDIA/AMD) on Linux — the real production case -> vLLM**, chiefly for the request-batching/concurrency handling it offers under real load, which Ollama does not match.

   Windows falls back to Ollama too (no native vLLM wheel, WSL-only), so in short: **vLLM only on Linux with a discrete GPU; Ollama everywhere else.** The pick is deliberately conservative in other ways too: the memory headroom is capped at 0.5, and among models within a few benchmark points of the best it takes the leanest and fastest, not the largest that merely fits. vLLM picks are sized against full FP16 weights (heavier than the Ollama Q4 estimate), so a vLLM pick is realistic on the real GPU. The output is hardware-specific; add it to `.gitignore`:

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

   # loads llm.engine.yaml, or resolves it from llm.brief.yaml on first use
   engine = ensure(".")
   summary = llm.chat(prompt, engine=engine, kind="llm")
   critique = llm.chat(prompt, engine=engine, kind="vlm", images=[png], json_schema=SCHEMA)
   ```

   `chat` reads the backend and model from the engine file and dispatches to Ollama (`/api/generate`) or vLLM (OpenAI-compatible `/v1/chat/completions`) transparently, with schema-constrained structured output on both.

**Missing-file policy.** The brief is committed, so its absence is a real bug and `ensure` raises loudly with the command to run. The engine file is gitignored and machine-specific, so its absence is normal: `ensure` resolves it from the brief on first use. This keeps the model out of any variable: the resolved engine file is the single source of truth.

The suite's consumers, [Standpoint](https://github.com/warith-harchaoui/standpoint), vocal-helper, and md2star, follow this pattern; each ships an `llm.brief.yaml` describing its own job (Standpoint's, for instance, names schema-constrained JSON, so the structured-output gate rules out higher-scoring vision models that cannot honour a schema and picks the strongest one that can) and reads the model only from the resolved engine file.

## Two modes: local (free) and cloud (paid)

Every brief picks one of two modes with `mode: local` (the default) or `mode: cloud`. Both resolve to the same shape of engine file and the same `llm.chat(engine=..., kind=...)` call site downstream: only the transport and the cost change.

### Local (free, default)

`mode: local`, or no `mode` field at all, is [the promise](#the-promise): hardware detection, model selection, and every quality gate run on this machine against a model already pulled via Ollama or served via vLLM. Every call costs **$0.0**, always, with no paid API call to price (see [Activity ledger](#activity-ledger)).

### Cloud (paid)

`mode: cloud` routes through a paid provider instead: OpenAI, Mistral, OpenRouter, Together, or Azure OpenAI (all OpenAI-compatible), plus Anthropic and Gemini (their own wire formats), while keeping the exact same `llm.chat(engine=..., kind=...)` call site downstream. Two ways to pick the model:

- **Pin it**: name `provider` and `model` explicitly in the brief, exactly as before.
- **Auto-pick it**: omit `model` (and `provider`, to search every provider) and best-engine picks the best paid model from a small bundled catalog (`pricing.yaml`, extended with benchmark scores per model), the same way local mode auto-picks from `models.yaml`, except that the resource being budgeted is **price**, not memory, since every paid model fits on any machine. A `quality_vs_cost` knob (0..1, default 0.7) tips the pick: `1.0` picks purely on benchmark score, `0.0` picks purely on price, and the default leans quality with price as a tiebreaker.

```yaml
mode: cloud
kind: both
quality_vs_cost: 0.7           # optional, 0..1; auto-pick only, default 0.7
task: extract structured line items from an invoice PDF's OCR text
```

Three further keys exist for the pinned case, and the brief is the only place they can be set. `vlm_model` pins the vision slot separately — with `kind: both` and only `model` given, the same model serves both. `base_url` overrides the provider's endpoint (for a proxy or a regional deployment), and `api_key_env` overrides the NAME of the environment variable the key is read from, which defaults to the provider's conventional one. Neither ever holds the key itself.

```sh
best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
# Wrote llm.engine.yaml
#   backend: openai  (llm=gpt-4o, vlm=gpt-4o)
```

Preview the auto-pick for any task before writing a brief, side by side with the local pick, with no API key and no network call:

```sh
best-engine-ai-helper report --task "extract line items from an invoice"
# ... local section ...
# ## Best cloud VLM (axis: ocr)
# **→ `gpt-4o`** (openai) — score 69, ~$6.25/1M tokens (blended)
```

(`--no-cloud` skips that section; `--quality-vs-cost` and `--cloud-provider` tune it.)

Every cloud engine also carries an embedded local **fallback**, resolved from the SAME brief, so a failed paid call degrades to the always-available local model: paid → local, the one safe direction (a local engine never silently escalates to a paid call). Four more things happen automatically at the `llm.chat()` call site once `engine=` is a cloud descriptor:

| Concern | Default | Opt out / configure |
|---|---|---|
| **API key** | the NAME in `api_key_env` (never the key value) is looked up in one pass (`settings.yaml`, then any `.env` file, then the process environment), then the OS keychain via `keyring` | `pip install 'best-engine-ai-helper[cloud]'` for the keyring fallback |
| **Safety scan** | every prompt/image scanned outbound, every response scanned inbound, for BOTH local and cloud (a content-policy concern, not a cloud-only risk) | `chat(..., safety=False)` |
| **Pseudonymization** | off; when on, scrubs personal data with the LOCAL fallback model before the prompt leaves the machine, restores it in the response | `chat(..., pseudonymize=True)`, needs `[cloud]` |
| **Retry + cache** | off; retry replays a transient transport failure before failing over, cache memoizes identical calls so a repeat never pays twice | `chat(..., retries=3, cache=True)`, cache needs `[cloud]` |
| **Cost tracking** | every call, local or paid, appended to the local activity ledger, priced from real provider token counts when reported, else a character estimate | `best-engine-ai-helper activity`, opt out with `BEST_ENGINE_NO_LEDGER=1` |

See [EXAMPLES.md's `resolve` section](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXAMPLES.md#resolve) for the full worked recipe (settings.yaml, keyring, structured output, the failover chain) and [GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md) for the activity dashboard.

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

engine = resolve_usage("text2sql")  # best-engine chooses the model for THIS machine
family = resolve_family("F1")  # one model for the whole constrained-generation group
```

best-engine writes the retained models into the gitignored `llm.engine*.yaml` for this machine (the extension of the `env.sh` it already emits); the app reads that file and re-resolution re-decides if the hardware changes. Adding a profile is a few lines in `usages.yaml`; a user overlay at `~/.best-engine-ai-helper/usages_cache.yaml` overrides by name.

## Use it as an agent skill

`skills/best-engine-ai-helper/` packages best-engine-ai-helper as a **Claude Skill** *and* an **OpenCode
skill**, so an agent can reach for it on your behalf. See
[`skills/README.md`](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/skills/README.md) to install it (symlink into
`~/.claude/skills/` and `~/.opencode/skills/`), and
[`TRIGGERS.md`](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/TRIGGERS.md) for the exhaustive trigger catalogue —
`scripts/check_triggers.py` keeps the skill's description in sync with it, and
the test suite fails if a capability stops being named.

## Author

[Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

## Acknowledgements

Special thanks to [Victor Favreau](https://www.linkedin.com/in/victor-favreau-41b823117/) for fruitful discussions.

## License

[BSD-3-Clause](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LICENSE). Copyright 2026 Warith Harchaoui.
