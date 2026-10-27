# EXAMPLES.md

One runnable recipe per public CLI command. All examples assume
`best-engine-ai-helper` is installed and Ollama is running locally on port
11434 (only required for the `pull`, `validate`, and `env` commands).

---

## detect

Print the detected hardware as JSON.

```sh
best-engine-ai-helper detect
```

Expected output on an Apple M2 Max 96 GB machine:

```json
{
  "platform": "darwin",
  "chip_vendor": "apple",
  "memory": {
    "unified_gb": 96.0,
    "vram_gb": null,
    "ram_gb": 96.0
  }
}
```

The `unified_gb` field is null on non-Apple machines; `vram_gb` is populated
on Linux/Windows machines with a discrete NVIDIA or AMD GPU.

---

## recommend

Print ranked model candidates for the current hardware without downloading anything.

```sh
best-engine-ai-helper recommend
```

On an M2 Max 96 GB machine the output looks like:

```
=== VLM candidates ===
id            ram_gb  score  fits  notes
------------  ------  -----  ----  ----------------------------------------
gemma3:12b    9.2     78     yes   Google Gemma 3 12B multimodal. Reliable
qwen3-vl:72b  52      91     yes   Highest raw vision benchmarks, but Qwen3
qwen3-vl:32b  24      87     yes   Large VLM; needs 32 GB VRAM. Qwen3-VL: u
...
```

Note the ordering: `gemma3:12b` (score 78) sits above `qwen3-vl:72b` (score 91)
because the Qwen3-VL family cannot honour Ollama structured output, so it is
never chosen for the suite's schema-driven tasks however high its raw score.
The `fits` column marks whether a model's peak-inference RAM sits inside the
budget: on this machine `qwen3:72b-q8_0` (78 GB) shows `NO` against the 61.2 GB
budget, while everything smaller shows `yes`.

To see only VLM candidates:

```sh
best-engine-ai-helper recommend --kind vlm
```

To use a tighter safety margin than the default (`--headroom` maxes out at
`0.5`; anything larger is silently clamped down to it):

```sh
best-engine-ai-helper recommend --headroom 0.3
```

---

## report

Recommend the best engine(s) for a task and write both a Markdown report and a
JSON file. The task can be a vague phrase; vision words add a VLM.

```sh
best-engine-ai-helper report \
    --task "retail product descriptions and image-quality checks" \
    --out engine
# wrote engine.md and engine.json
```

The report states, for each needed kind, the chosen model with its memory fit
and estimated tokens/s, a lighter/faster alternative when one is close, the full
ranked candidate table, and the sourced rationale. Print JSON instead of
Markdown with `--format json` (omit `--out` to only print).

Add `--live` to also weigh the machine's CURRENT load (free RAM, CPU/GPU/disk
usage, already-running engines), not just its theoretical capacity:

```sh
best-engine-ai-helper report --task "write python code" --live
# ...
# ## Server load (live, at recommendation time)
#
# - Available RAM: 50.3 GB
# - CPU: 43%, GPU: 3%
# - Disk free: 41.5 GB (96% used)
# - Already-running engines: 0
# ...
```

Off by default: it adds a short live probe (~0.1-0.5s) and makes the result
depend on this exact moment rather than being a deterministic function of the
hardware alone.

`report` also shows the best PAID model for the task, on by default, needing
no API key and reaching no network: it ranks the bundled `pricing.yaml`
catalog (see the `resolve` section below).

```sh
best-engine-ai-helper report --task "extract line items from an invoice"
# ... local section ...
# ## Best cloud VLM (axis: ocr)
# **→ `gpt-4o`** (openai) — score 69, ~$6.25/1M tokens (blended)
```

Skip it with `--no-cloud`, or steer it with `--quality-vs-cost 0..1` (1.0 =
best benchmark regardless of price, 0.0 = cheapest regardless of quality;
default 0.7) and `--cloud-provider openai|mistral|...` (restrict to one
provider).

---

## resolve

Turn a project's committed **brief** (what the repo needs from an LLM/VLM) into a
gitignored, machine-specific **engine file** (the backend and model to use here).
Unlike `report`, which prints a recommendation, `resolve` writes the descriptor
that `ensure` / `llm.chat` read at call time.

Commit a hardware-independent `llm.brief.yaml` in the repo:

```yaml
mode: local             # local (default) or cloud
kind: both              # llm | vlm | both
headroom: 0.5           # max fraction of usable accelerator memory (clamped to 0.5)
min_tps: 15             # comfort throughput floor (tokens/s)
structured_output: true # the job needs schema-constrained output
task: >-
  Name PCA axis poles as schema-constrained JSON, write a short analysis in
  the table's own language, and sanity-check the rendered chart image.
```

`mode: local` is the default. `mode: cloud` resolves a paid provider PLUS a
local fallback from the same brief (paid -> local on failure):

```yaml
mode: cloud
provider: mistral        # openai | mistral | openrouter | together | azure |
                         # anthropic | gemini (anthropic/gemini use their own
                         # wire formats; the rest speak OpenAI-compatible)
model: mistral-large-latest
api_key_env: MISTRAL_API_KEY   # name of the env var holding the key, never
                                # the key value itself, never persisted
structured_output: true
task: extract structured line items from an invoice PDF's OCR text
```

```sh
export MISTRAL_API_KEY=...     # your key, in the shell, never committed
best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
```

The resulting engine's `fallback` is resolved from the SAME brief, so
`llm.chat(engine=...)` degrades to the always-available local model if the
paid call fails. See `llm.chat`'s `pseudonymize=` (scrub personal data before
it reaches the cloud, via the local fallback engine) and `safety=` (NSFW/
policy scanning, on by default for every engine, local or cloud) keywords for
the rest of the cloud-call safety net. Retry/caching/pseudonymization need the
`[cloud]` extra (`pip install 'best-engine-ai-helper[cloud]'`); real NSFW
classifiers for `safety=` need `[filtered]`; both degrade gracefully
(a light retry, no caching, a keyword heuristic) rather than erroring when
absent.

### Auto-pick the best paid model (no `model` in the brief)

`model` is optional. Omit it (and `provider`, to search every provider) and
`resolve` picks the best paid model itself, from the same bundled
`pricing.yaml` catalog `report --cloud` previews (the cloud counterpart of
local mode's `models.yaml` auto-pick, except the resource being budgeted is
**price**, not memory, since every paid model runs on any machine):

```yaml
mode: cloud
kind: both
quality_vs_cost: 0.7   # optional, 0..1, default 0.7: 1.0 = best score
                        # regardless of price, 0.0 = cheapest regardless of
                        # quality, in between leans quality with price as a
                        # tiebreaker
task: extract structured line items from an invoice PDF's OCR text
```

```sh
best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
# Wrote llm.engine.yaml
#   backend: openai  (llm=gpt-4o, vlm=gpt-4o)
```

Pin `provider` alone (no `model`) to auto-pick within one provider only:
useful when you already have a key for that provider and just want its best
model for the job. Structured-output capability is checked first, exactly
like local mode: a model that cannot honour a JSON schema never wins the
auto-pick over one that can, however attractively priced.

Resolve it, per machine (the backend is chosen for the hardware: **vLLM on a
discrete GPU, Ollama otherwise**):

```sh
best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
```

On an Apple M2 Max 96 GB machine that prints:

```
Wrote llm.engine.yaml
  backend: ollama  (llm=gemma3:12b, vlm=gemma3:12b)
  NOTE: hardware-specific — add 'llm.engine.yaml' to .gitignore, do not commit.
  bring it up:  ollama pull gemma3:12b
```

The pick is deliberately conservative: headroom is capped at 0.5, and among
models within a few benchmark points of the best it takes the leanest and
fastest, not the largest that merely fits. The resulting `llm.engine.yaml` is
hardware-specific; add it to `.gitignore`:

```yaml
# GENERATED by best-engine-ai-helper — do NOT commit.
# Hardware-specific: the backend and models chosen for THIS machine.
# Regenerate with:  best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml

mode: local
resolved_for: {chip: Apple M2 Max, accelerator: apple, memory_gb: 96.0}
backend: ollama
base_url: http://localhost:11434
headroom: 0.5
min_tps: 15.0
llm: {model: gemma3:12b, ram_gb: 9.2, est_tokens_per_s: 28.3, structured_output: true}
vlm: {model: gemma3:12b, ram_gb: 9.2, est_tokens_per_s: 28.3, structured_output: true}
serve: [ollama pull gemma3:12b]
```

Force a backend with `--backend ollama|vllm` (default `auto`), or point at a
remote server with `--endpoint URL`.

Consume it from Python: no `DEFAULT_MODEL` constant, the model is always read
from the resolved engine file:

```python
from best_engine_ai_helper import ensure, llm

# loads llm.engine.yaml, or resolves it from llm.brief.yaml on first use
engine = ensure(".")
summary = llm.chat(prompt, engine=engine, kind="llm")
critique = llm.chat(prompt, engine=engine, kind="vlm", images=[png], json_schema=SCHEMA)
```

`chat` reads the backend and model from the engine and dispatches to Ollama
(`/api/generate`) or vLLM (OpenAI `/v1/chat/completions`) transparently; with a
`json_schema` it returns a parsed dict. See the README's
[Downstream integration → Pattern B](README.md#pattern-b-a-per-project-engine-resolved-from-a-tuned-brief)
for the full flow and the missing-file policy.

---

## usages

Browse and resolve the bundled **usage catalog**: eight named task profiles
grouped into families. A profile states only its *needs*; best-engine chooses
the model.

```sh
best-engine-ai-helper usages list
```

Lists the families (`F1` constrained generation, `F2` prose generation, `F3`
embeddings) and every profile (`text2sql`, `rag-answer`, `embeddings`,
`text2sql-figures`, `report-bluf`, `classification`, `pii-rgpd`, `persona`) with
its family and status; no model names, only needs.

```sh
best-engine-ai-helper usages show text2sql
```

Prints one profile's needs: task text (mapped to a benchmark axis), whether it
needs structured output, its throughput floor, memory headroom, advisory quality
bar, and context-length hint.

```sh
# Resolve one profile to the model best-engine picks for THIS machine
best-engine-ai-helper usages resolve text2sql

# Resolve a whole family to a single shared model, written to a gitignored file
best-engine-ai-helper usages resolve --family F1 --out llm.engine.F1.yaml
```

The chosen model lives only in the generated `llm.engine*.yaml` (gitignored,
machine-specific), the same rule as `resolve`. From Python:

```python
from best_engine_ai_helper import resolve_usage, resolve_family, list_usages

for u in list_usages():
    print(u["name"], u["family"], u["status"])

engine = resolve_usage("text2sql")  # best-engine chooses the model here
family = resolve_family("F1")  # one model for the whole F1 group
```

---

## catalog show

Print the full merged model catalog (bundled seed plus any local cache updates).

```sh
best-engine-ai-helper catalog show
```

Each row shows the Ollama tag, kind, parameter count, quantization, on-disk
size, estimated peak RAM, and benchmark scores.

---

## hardware show

Print the full merged hardware chip table.

```sh
best-engine-ai-helper hardware show
```

Each row shows the chip name, vendor, total memory, usable memory (after OS
overhead), and the data source.

---

## airllm

Four commands for the one backend that runs a model which does **not** fit in
memory, by streaming its layers off disk. Nothing to install: the airllm
runtime is a core dependency, which is most of why the package's install is
~2 GB.

`status`, `plan` and `compare` are pure arithmetic over this machine's hardware
and the catalog — they never import the runtime, so they answer correctly (and
instantly) even in an environment where it would fail to load.

### airllm status

Can this machine stream layers, would it be asked to, and what is in the way?

```sh
best-engine-ai-helper airllm status
```

```
=== Layer streaming (airllm) ===
  runtime import  : ok
  storage         : apple-internal (declared)
  read bandwidth  : 4.0 GB/s
  free disk       : 22.3 GB
  shard budget    : 72.0 GB of resident memory
  request         : auto
  would activate  : no
  trigger         : not-needed

  A model already fits this machine's memory, so streaming its layers off disk
  would trade two to three orders of magnitude of speed for nothing. Ask for it
  explicitly (--backend airllm) to override.
```

`runtime import` is the honest version of a question that used to be "is the
extra installed": airllm ships with the package, so the only way this reads
anything but `ok` is an incomplete install (a stripped container, a wheel that
failed to build) — in which case the line says so and the panel prints the
reinstall command.

`--measure` replaces the storage-class assumption with a real measurement of
this drive (~256 MB written and read back with the page cache bypassed, one or
two seconds). Worth it: the drive sets the entire speed of this backend, and the
`basis` field flips from `declared` to `measured` so you can tell the two apart.

`--json` gives the same thing machine-readably, which is what the HTTP endpoint
returns:

```sh
best-engine-ai-helper airllm status --json --request always
```

```json
{
  "decision": {
    "activate": true,
    "request": "always",
    "trigger": "manual",
    "reason": "Layer streaming was requested explicitly and runs here on mlx.",
    "installed": true,
    "runtime": "mlx",
    "blockers": []
  },
  "compute": {"accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400.0},
  "disk": {"storage": "apple-internal", "read_gbs": 4.0, "basis": "declared", "free_gb": 22.3},
  "memory_budget_gb": 72.0,
  "install": "pip install --upgrade --force-reinstall best-engine-ai-helper"
}
```

`install` is a repair command, not an opt-in one — it is what to run if
`installed` ever comes back false.

### airllm plan

What could this machine stream, and at what price?

```sh
best-engine-ai-helper airllm plan --kind llm --compression 4bit
```

```
=== LLM: streamable off nvme at 4.0 GB/s, 22.08 GB shard budget ===
id                params  shard_gb  ckpt_gb  s/token  disk_gb  runs  notes
----------------  ------  --------  -------  -------  -------  ----  ------------------------------
qwen3:235b-a22b   235B    5.1       117.5    45.5     599.2    yes   94 layers
llama3.1:405b     405B    6.5       202.5    76.9     1032.8   yes   126 layers
qwen2.5-vl:72b    73B     2.9       36.5     14.3     186.2    yes   80 layers
llama3.3:70b      70B     2.8       35.0     13.7     178.5    yes   80 layers
mixtral:8x22b     141B    4.5       70.5     27.8     359.6    yes   56 layers
deepseek-v3:671b  671B    15.2      335.5    125.0    1040.0   NO    estimated 0.008 tok/s (125.0 s

  Pick: Qwen/Qwen3-235B-A22B-Instruct-2507 — 235B in 5.1 GB resident, 45.5 s/token,
  599 GB free disk to split (129 GB after).
```

Two things that row order teaches. The 405B model streams in a *leaner shard*
than the 141B one — 126 layers against 56 — so depth, not size, decides what
fits. And DeepSeek-V3 is refused on speed rather than on memory: 125 s/token is
past the batch floor, and the blocker says so instead of offering a
technically-correct eternity.

Three columns to read in order: `shard_gb` is what has to fit in memory (one
layer shard, not the model), `disk_gb` is what has to be free *during the split*
— the constraint that usually refuses a model — and `s/token` is what you will
wait. `--context 32` re-prices the shard for a 32k context, which is not free: the KV
cache is the one thing streaming does not shrink. `--batch 8` prices the big
lever on both sides at once — the wall clock for a 300-token answer does not
move, but it now buys eight answers instead of one, and the shard figure grows
by the seven extra KV caches that bought it.

### airllm compare

Native model or streamed model, same answer, both prices. This is the decision
the backend actually forces.

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

`--batch 8` is the lever worth trying before concluding it is too slow: eight
prompts ride through each layer pass together, so eight answers arrive in the
time of one. `--compression 4bit` is the other (~3x). They compose.

### airllm prepare

Pay the download and the layer split deliberately, rather than inside your first
inference call — which for a large model is tens of minutes of disk, and reads
exactly like a hang.

```sh
best-engine-ai-helper airllm prepare --model meta-llama/Llama-3.3-70B-Instruct \
  --compression 4bit --shards-path /Volumes/fast/airllm-shards
```

```
Prepared meta-llama/Llama-3.3-70B-Instruct: layer shards are on disk and the
first call will not have to split them.
```

`--shards-path` is worth pointing at your fastest volume: the shard read *is*
the decode speed. `--delete-original` drops the downloaded checkpoint once the
shards exist, halving the disk requirement — at the cost of re-downloading if the
shards are ever lost.

### resolve --backend airllm

The same brief, resolved for streaming instead of for Ollama:

```sh
best-engine-ai-helper resolve --brief llm.brief.yaml --backend airllm
```

```
Wrote llm.engine.yaml
  backend: airllm  (llm=meta-llama/Llama-3.3-70B-Instruct)
  NOTE: hardware-specific — add 'llm.engine.yaml' to .gitignore, do not commit.
  bring it up:  best-engine-ai-helper airllm prepare --model meta-llama/Llama-3.3-70B-Instruct
```

```yaml
# llm.engine.yaml (gitignored, machine-specific)
backend: airllm
base_url: ''              # a library, not a server: it runs in your process
min_tps: 0.01             # the batch floor, not the 15 tok/s interactive one
airllm:
  activate: true
  trigger: manual
  reason: Layer streaming was requested explicitly and runs here on cuda.
  runtime: cuda
  installed: true
  compression: null
  blockers: []
llm:
  model: meta-llama/Llama-3.3-70B-Instruct
  catalog_id: llama3.3:70b
  backend: airllm         # per-kind, so a mixed descriptor is readable
  streaming: true
  ram_gb: 6.1             # one resident shard
  checkpoint_gb: 140.0    # what every token re-reads
  layers: 80
  layers_estimated: false
  disk_peak_gb: 294.0
  disk_steady_gb: 154.0
  disk_fits: true
  est_tokens_per_s: 0.024
  seconds_per_token: 41.7
  structured_output: false  # airllm has no schema-constrained generation
  fits: true
  comfortable: true
serve:
- best-engine-ai-helper airllm prepare --model meta-llama/Llama-3.3-70B-Instruct
```

Or let it happen by itself: with no `--backend`, a kind for which nothing fits
this machine falls back to streaming on its own, and only that kind does. Set
`airllm: never` in the brief (or `BEST_ENGINE_AIRLLM=never`) to switch the
escalation off entirely.

### From Python

```python
import best_engine_ai_helper as beah

hw, disk = beah.available_memory(), beah.disk_profile(measure=True)
entry = {
    "id": "llama3.3:70b",
    "size_b": 70,
    "layers": 80,
    "hf_id": "meta-llama/Llama-3.3-70B-Instruct",
}

# Three different answers to "how fast is it", all of them true
timing = beah.airllm_generation_time(entry, disk["read_gbs"], new_tokens=300, batch=8)
print(timing["decode_tps"])  # 0.024  — steady state, one sequence
print(timing["time_to_first_token_s"])  # 41.2   — one pass, prompt included
print(timing["effective_tps"])  # 0.194  — eight answers share each pass

# Should this machine stream at all?
print(beah.airllm_decide(conventional_resolved=False)["reason"])

# Native or streamed, for a 300-token answer?
print(
    beah.airllm_compare(
        beah.load_catalog(),
        hw=hw,
        disk=disk,
        bandwidth_gbs=beah.compute_profile()["bandwidth_gbs"],
        new_tokens=300,
    )["verdict"]
)

# Run it, in this process, with no server involved
print(
    beah.airllm_generate(
        "Rate this product description 1-5 and say why:…",
        model="meta-llama/Llama-3.3-70B-Instruct",
        max_new_tokens=64,
    )
)
```

### HTTP / MCP

```sh
curl -s 'http://127.0.0.1:8000/api/airllm?answer_tokens=300&batch=8' | jq '.comparison.verdict'
```

```json
"Streaming buys 11 benchmark points (89 vs 78) for 2647x the wait: 3.5 h instead of 5 s for a 300-token answer."
```

The endpoint returns the decision, the storage profile, the ranked plans and the
comparison in one call, and is exposed as an MCP tool like every other route.

---

## Python library usage

All public functions are importable without invoking Click:

```python
from best_engine_ai_helper.detect import available_memory, chip_vendor
from best_engine_ai_helper.catalog import load_catalog
from best_engine_ai_helper.score import select

hw = available_memory()
catalog = load_catalog()

best_vlm = select(hw, catalog, kind="vlm")
print(best_vlm["id"])  # e.g. 'gemma3:12b' on a 96 GB machine
print(best_vlm["ram_gb"])  # e.g. 9.2

best_llm = select(hw, catalog, kind="llm")
print(best_llm["id"])  # e.g. 'qwen3:72b-q4_k_m' on a 96 GB machine
```

`select` and the `recommend` / `report` output agree on the winner: both put
structured-output-capable models first, then rank by benchmark score within the
memory budget.

The full recommendation algorithm (memory + compute + task) is one call:

```python
from best_engine_ai_helper import recommend_engines, to_markdown
from best_engine_ai_helper.detect import available_memory, compute_profile
from best_engine_ai_helper.catalog import load_catalog

report = recommend_engines(
    available_memory(),
    load_catalog(),
    task="product descriptions and image-quality checks",
    compute=compute_profile(),
)
print(report["recommendations"]["vlm"]["chosen"]["id"])  # best VLM
print(to_markdown(report))  # human-readable report
```

---

## gui

Launch the browser GUI (hardware snapshot + task → best engine):

```sh
best-engine-ai-helper gui
# Serving GUI at http://127.0.0.1:8000/gui
```

Open `http://127.0.0.1:8000/gui`: the hardware panel loads on page load, and
typing a task and clicking "Recommander" calls the same `recommend()` used by
`report`. The two JSON endpoints it's built on are usable directly too:

```sh
curl -s http://127.0.0.1:8000/api/system | python3 -m json.tool

curl -s -X POST http://127.0.0.1:8000/api/recommend \
     -H 'Content-Type: application/json' \
     -d '{"task": "product descriptions and image-quality checks"}' \
  | python3 -m json.tool
```

See [GUI.md](GUI.md) for screenshots and the full write-up.

---

## activity

Summarize the local activity/cost ledger: who called what, how often, at
what cost. Populated by any command (or downstream project) that calls
`llm.chat()`; nothing to show until then.

```sh
best-engine-ai-helper activity
# No calls recorded yet.

best-engine-ai-helper pull   # calls the model via the Ralph validation gates

best-engine-ai-helper activity
# Total calls: 4   Total cost: $0.0000   Error rate: 0.0%
#
# By user:
# user              calls  cost_usd
# ----              -----  --------
# warithharchaoui   4      0.0
#
# By model:
# model      calls  cost_usd
# -----      -----  --------
# qwen3:8b   4      0.0

best-engine-ai-helper activity --format json
```

Local only (`~/.best-engine-ai-helper/usage.db`), no network call. Disable
recording entirely with `BEST_ENGINE_NO_LEDGER=1`, or attribute calls to a
specific person on a shared machine with `BEST_ENGINE_USER=alice`.

---

## pull, validate, env

```sh
best-engine-ai-helper pull            # pull the best model; run Ralph gates
best-engine-ai-helper validate        # re-run Ralph gates on the current model
best-engine-ai-helper env             # print env block for ~/.zshrc
```

Refresh the caches (both merge into `~/.best-engine-ai-helper/`, leaving the
bundled seed untouched):

```sh
best-engine-ai-helper catalog update            # fetch open-weight models from ApXML
best-engine-ai-helper catalog update --limit 20 # quick partial refresh / smoke test
best-engine-ai-helper hardware update           # record this machine's chip + memory
```
