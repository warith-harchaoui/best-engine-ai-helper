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

To use a tighter safety margin (0.5 instead of the default 0.85):

```sh
best-engine-ai-helper recommend --headroom 0.5
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
api_key_env: MISTRAL_API_KEY   # name of the env var holding the key — never
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
classifiers for `safety=` need `[filtered]` — both degrade gracefully
(a light retry, no caching, a keyword heuristic) rather than erroring when
absent.

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
hardware-specific — add it to `.gitignore`:

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

Consume it from Python — no `DEFAULT_MODEL` constant, the model is always read
from the resolved engine file:

```python
from best_engine_ai_helper import ensure, llm

engine = ensure(".")            # loads llm.engine.yaml, or resolves it from
                                # llm.brief.yaml on first use
summary = llm.chat(prompt, engine=engine, kind="llm")
critique = llm.chat(prompt, engine=engine, kind="vlm",
                    images=[png], json_schema=SCHEMA)
```

`chat` reads the backend and model from the engine and dispatches to Ollama
(`/api/generate`) or vLLM (OpenAI `/v1/chat/completions`) transparently; with a
`json_schema` it returns a parsed dict. See the README's
[Downstream integration → Pattern B](README.md#pattern-b-a-per-project-engine-resolved-from-a-tuned-brief)
for the full flow and the missing-file policy.

---

## usages

Browse and resolve the sev7n **usage catalog** — named task profiles grouped
into families. A profile states only its *needs*; best-engine chooses the model.

```sh
best-engine-ai-helper usages list
```

Lists the families (`F1` constrained generation, `F2` prose generation, `F3`
embeddings) and every profile (`text2sql`, `rag-answer`, `embeddings`,
`text2sql-figures`, `report-bluf`, `classification`, `pii-rgpd`, `persona`) with
its family and status — no model names, only needs.

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
machine-specific) — the same rule as `resolve`. From Python:

```python
from best_engine_ai_helper import resolve_usage, resolve_family, list_usages

for u in list_usages():
    print(u["name"], u["family"], u["status"])

engine = resolve_usage("text2sql")   # best-engine chooses the model here
family = resolve_family("F1")        # one model for the whole F1 group
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

## Python library usage

All public functions are importable without invoking Click:

```python
from best_engine_ai_helper.detect import available_memory, chip_vendor
from best_engine_ai_helper.catalog import load_catalog
from best_engine_ai_helper.score import select

hw = available_memory()
catalog = load_catalog()

best_vlm = select(hw, catalog, kind="vlm")
print(best_vlm["id"])        # e.g. 'gemma3:12b' on a 96 GB machine
print(best_vlm["ram_gb"])    # e.g. 9.2

best_llm = select(hw, catalog, kind="llm")
print(best_llm["id"])        # e.g. 'qwen3:72b-q4_k_m' on a 96 GB machine
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
print(report["recommendations"]["vlm"]["chosen"]["id"])   # best VLM
print(to_markdown(report))                                # human-readable report
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

Summarize the local activity/cost ledger — who called what, how often, at
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
