# Examples

[🇫🇷 EXEMPLES.md](EXEMPLES.md) · 🇬🇧 English

Ten scenarios, each one a job somebody actually arrives with, then one section
listing every command. Every snippet below was checked against the code, and
the outputs pasted here were produced by running it — see
[Setup](#setup) for the machine they came from and for the handful of commands
that could not be run.

The one idea worth carrying through all of it: **you never name a model.** You
describe the job, and this package names the model, differently on every
machine.

## Table of Contents

- [Setup](#setup)
- [1. What this machine can run](#1-what-this-machine-can-run)
- [2. The best engine for a job, as a report](#2-the-best-engine-for-a-job-as-a-report)
- [3. One brief per repo, one engine per machine](#3-one-brief-per-repo-one-engine-per-machine)
- [4. A paid model, only when you hand it a key](#4-a-paid-model-only-when-you-hand-it-a-key)
- [5. Usage profiles instead of model names](#5-usage-profiles-instead-of-model-names)
- [6. Capacity planning: what fits together](#6-capacity-planning-what-fits-together)
- [7. Too large to fit, still runnable: layer streaming](#7-too-large-to-fit-still-runnable-layer-streaming)
- [8. Who called what, at what cost](#8-who-called-what-at-what-cost)
- [9. The GUI, the HTTP API and the MCP tools](#9-the-gui-the-http-api-and-the-mcp-tools)
- [10. Call it from your own package](#10-call-it-from-your-own-package)
- [Command line](#command-line)
- [Troubleshooting](#troubleshooting)

## Setup

```sh
pip install best-engine-ai-helper
```

Expect about 2 GB and a few minutes: this package is pure Python and tiny, but
the layer-streaming runtime brings torch with it. One command line is
installed, plus a server:

```sh
best-engine-ai-helper --version     # best-engine-ai-helper, version 1.9.0
best-engine-ai-helper-mcp           # HTTP API + MCP, http://127.0.0.1:8000
```

Every Python snippet below assumes these imports, and nothing else:

```python
import best_engine_ai_helper as beah  # the flat public surface
from best_engine_ai_helper import llm  # the one call that runs a model
```

[Ollama](https://ollama.com) is needed only to **run** a model — so for `pull`,
`validate`, `env` and for the `llm.chat` snippet in
[§10](#10-call-it-from-your-own-package). Everything that only *decides*
(`detect`, `recommend`, `report`, `resolve`, `usages`, `storage`, `providers`,
`catalog show`, `hardware show`, every `lightweight` sizing subcommand, the GUI, the
HTTP API) works with no daemon and no network at all.

**Where the outputs came from.** Every table and panel below was produced on an
Apple M2 Max with 96 GB of unified memory, under macOS, with a pristine
`~/.best-engine-ai-helper/` so that the **bundled** catalogue is what answers
rather than a refreshed cache. Two properties of that machine shape several
numbers and are worth knowing before you compare: its memory bandwidth is
400 GB/s, which sets every `tok/s` figure, and its disk was **98% full**, which
is why so many rows in
[§7](#7-too-large-to-fit-still-runnable-layer-streaming) are refused on disk
rather than on memory. A `~` marks an estimate derived from bandwidth; a `*` in
real output marks a figure measured on the machine. The free-disk figures differ
slightly between panels because each panel is a separate run and the drive was
filling between them — that is a live reading, not an inconsistency.

Five commands are **not** executed anywhere below, and their effect is described
rather than pasted: `pull` and `validate` (they download model weights and run
two generation gates), `catalog update` and `hardware update` (the first reaches
the network), `lightweight prepare` (it downloads a checkpoint) and
`imagine generate` (it downloads a diffusers pipeline). Nothing in this file is
invented output.

## 1. What this machine can run

Start here. `detect` says what the hardware is; `recommend` says what that
hardware should run, without downloading anything.

```sh
best-engine-ai-helper detect
```

```json
{
  "platform": "darwin",
  "chip_vendor": "apple",
  "memory": {
    "unified_gb": 96.0,
    "vram_gb": null,
    "ram_gb": 96.0
  },
  "hardware": {
    "platform": "darwin",
    "cpu": {
      "physical_cores": 12,
      "logical_cores": 12,
      "model": "Apple M2 Max",
      "percent": 66.9
    },
    "ram_gb": 96.0,
    "available_ram_gb": 52.0,
    "disk": {
      "free_gb": 22.1,
      "used_gb": 972.6,
      "total_gb": 994.7,
      "percent_used": 97.8
    },
    "gpu_vendor": "apple",
    "gpus": [],
    "gpu_utilization_percent": 58.0,
    "apple_chip": "Apple M2 Max",
    "apple_unified_gb": 96.0
  }
}
```

The top-level `memory` block is the stable part: `unified_gb` is populated only
on Apple Silicon, `vram_gb` only on a machine with a discrete NVIDIA or AMD
GPU, and `ram_gb` always. The `hardware` block underneath is a live reading
delegated to `os-helper`, so `percent`, `available_ram_gb` and
`gpu_utilization_percent` differ on every run — they are the fields that
`report --live` consumes.

```sh
best-engine-ai-helper recommend --kind llm
```

```
=== LLM candidates (ollama) ===
id                 ram_gb  score  fits  tok/s  comfy  notes
-----------------  ------  -----  ----  -----  -----  ----------------------------------------
qwen3:72b-q8_0     78      89     NO    3      NO     72B at Q8; needs 96 GB unified. Reliable
qwen3:72b-q4_k_m   48      87     NO    5      NO     Top text-only; needs 64 GB unified or VR
qwen3:32b-q8_0     36      85     yes   7      NO     32B at full Q8 precision. Reliable struc
qwen3:32b-q4_k_m   22      83     yes   12     NO     Large text model; fits 24 GB VRAM with h
qwen3:14b          10.5    78     yes   25     yes    Good mid-size text model. Reliable struc
gemma3:12b         9.2     77     yes   28     yes    Google Gemma 3 12B multimodal. Reliable
qwen2.5-coder:32b  22      75     yes   12     NO     Qwen2.5-Coder 32B: top open code/SQL mod
qwen3:8b           5.6     74     yes   46     yes    Solid text-only 8B. Reliable structured
qwen2.5-coder:14b  9.9     72     yes   26     yes    Qwen2.5-Coder 14B: stronger code/SQL at
qwen2.5-coder:7b   5.2     66     yes   50     yes    Qwen2.5-Coder 7B: SQL/code specialist. R
qwen2.5:3b         2.2     62     yes   118    yes    Text-only; very small footprint. Reliabl
qwen3-vl:72b       52      88     NO    5      NO     Highest raw vision benchmarks, but Qwen3
qwen3-vl:32b       24      84     yes   11     NO     Large VLM; needs 32 GB VRAM. Qwen3-VL: u
qwen3-vl:14b       11.2    79     yes   23     yes    Strong mid-size VLM. Qwen3-VL: unreliabl
qwen3-vl:8b        6.8     73     yes   38     yes    Qwen3-VL 8B: strong raw vision/OCR but r
qwen3-vl:4b        3.5     66     yes   74     yes    Small VLM; fits on 4 GB VRAM machines. Q
```

Three columns decide, and none of them is the score alone.

`fits` compares a model's **peak inference** RAM against the budget, which on
this machine is **36.0 GB**: 96 GB of unified memory, of which 72.0 GB is
usable once macOS has taken its share, halved again by the 0.5 safety headroom.
That is why `qwen3:32b-q8_0` at exactly 36 GB still reads `yes` while
`qwen3:72b-q4_k_m` at 48 GB reads `NO` on a 96 GB machine. Check the number
rather than trusting the arithmetic:

```python
hw = beah.available_memory()
print(beah.usable_pool_gb(hw))  # 72.0
print(beah.effective_budget(hw))  # 36.0
print(beah.MAX_HEADROOM)  # 0.5
```

`comfy` is the second refusal. `qwen3:32b-q8_0` fits memory and is still not
chosen, because at an estimated 7 tok/s it sits below the 15 tok/s comfort
floor: a model that fits and crawls is not a recommendation.

Tighten the margin and `fits` moves with it. `--headroom` is clamped at 0.5, so
the only direction available is stricter:

```sh
best-engine-ai-helper recommend --kind llm --headroom 0.3
```

```
qwen3:32b-q8_0     36      85     NO    7      NO     32B at full Q8 precision. Reliable struc
qwen3:32b-q4_k_m   22      83     NO    12     NO     Large text model; fits 24 GB VRAM with h
qwen3:14b          10.5    78     yes   25     yes    Good mid-size text model. Reliable struc
```

`--kind vlm` restricts to vision-language models and ranks them on the vision
axis rather than the general one, which reorders the table. `gemma3:12b` leads
at score 78 even though `qwen3-vl:32b` scores 87, because the Qwen3-VL family
cannot honour Ollama's schema-constrained output and this suite routes every
task through a schema:

```sh
best-engine-ai-helper recommend --kind vlm
```

```
=== VLM candidates (ollama) ===
id            ram_gb  score  fits  tok/s  comfy  notes
------------  ------  -----  ----  -----  -----  ----------------------------------------
gemma3:12b    9.2     78     yes   28     yes    Google Gemma 3 12B multimodal. Reliable
qwen3-vl:72b  52      91     NO    5      NO     Highest raw vision benchmarks, but Qwen3
qwen3-vl:32b  24      87     yes   11     NO     Large VLM; needs 32 GB VRAM. Qwen3-VL: u
qwen3-vl:14b  11.2    83     yes   23     yes    Strong mid-size VLM. Qwen3-VL: unreliabl
qwen3-vl:8b   6.8     80     yes   38     yes    Qwen3-VL 8B: strong raw vision/OCR but r
qwen3-vl:4b   3.5     72     yes   74     yes    Small VLM; fits on 4 GB VRAM machines. Q
```

## 2. The best engine for a job, as a report

`recommend` ranks the catalogue. `report` answers a *question*: given this
sentence describing the work, which kinds of model are needed, and which one
should serve each. The task can be vague — vision vocabulary in it adds a VLM.

```sh
best-engine-ai-helper report \
    --task "retail product descriptions and image-quality checks" \
    --out engine
```

```
wrote engine.md and engine.json
# Best local engine — recommendation

**Task:** retail product descriptions and image-quality checks
**Language:** en
**Matched keywords:** image
**Needs:** LLM, VLM

## Hardware

- Chip / accelerator: Apple M2 Max (gpu-metal)
- Memory pool: 96.0 GB
- Memory bandwidth: 400 GB/s (sets the decode-speed ceiling)
- Usable model budget: **36.0 GB** (headroom 0.5)
- Comfort throughput floor: **15 tok/s** (a model below this fits memory but decodes too slowly to recommend)

## Best LLM (axis: generalist)

**→ `gemma3:12b`** — 9.2 GB, score 77, ~28 tok/s

Lighter alternative: `qwen3:8b` — 5.6 GB, score 74, ~46 tok/s.
```

Note what the words did. "Product descriptions" matched no specialist axis, so
the LLM is ranked on the **generalist** benchmark, while "image" raised a VLM
need which is ranked on the **vision** axis. Ask for code and the axis changes
again:

```sh
best-engine-ai-helper report --task "write python code" --live
```

```
## Server load (live, at recommendation time)

- Available RAM: 54.3 GB
- CPU: 53%, GPU: 10%
- Disk free: 20.7 GB (98% used)
- Already-running engines: 1

## Best LLM (axis: code)
```

`--live` is off by default and worth understanding before switching it on. It
adds a short probe, roughly 0.1-0.5 s, and makes the answer a function of
*this moment* rather than of the hardware alone: the same command run twice can
disagree, which is correct behaviour and surprising behaviour at once. The
`Already-running engines: 1` line above is the probe noticing a model server
that was already holding memory.

`--out engine` writes `engine.md` and `engine.json` side by side; omit it to
print only, and `--format json` swaps the Markdown for the machine-readable
twin.

The same command also previews the best **paid** model for the task. It is on
by default, and it needs no API key and reaches no network, because it ranks
the bundled `pricing.yaml` instead of calling anybody:

```sh
best-engine-ai-helper report --task "extract line items from an invoice"
```

```
## Best cloud LLM (axis: generalist)

**→ `gemini-1.5-pro`** (gemini) — score 86, ~$3.12/1M tokens (blended)

## Best cloud VLM (axis: ocr)

**→ `gpt-4o`** (openai) — score 69, ~$6.25/1M tokens (blended)
```

"Invoice" mapped the vision slot to the **ocr** axis, which is why `gpt-4o`
wins there while `gemini-1.5-pro` takes the text slot at half the price. Skip
the whole section with `--no-cloud`; steer it with `--quality-vs-cost 0..1`
(1.0 = best benchmark whatever the price, 0.0 = cheapest whatever the quality,
default 0.7) and `--cloud-provider openai|mistral|...` to restrict it to one
provider.

## 3. One brief per repo, one engine per machine

`report` prints advice. `resolve` writes the descriptor your code reads at call
time, and that is the pattern to adopt: a **brief** committed to the repository
saying what the job needs, resolved per machine into a gitignored **engine
file** naming the model chosen here.

Commit this, hardware-independent, as `llm.brief.yaml`:

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

Resolve it, once per machine. The backend is chosen for the hardware — **vLLM
on a discrete GPU, Ollama otherwise**:

```sh
best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
```

```
WARNING | llm model gemma3:12b is not on this Ollama daemon yet: run `ollama pull gemma3:12b` before the first call.
WARNING | vlm model gemma3:12b is not on this Ollama daemon yet: run `ollama pull gemma3:12b` before the first call.
Wrote llm.engine.yaml
  backend: ollama  (llm=gemma3:12b, vlm=gemma3:12b)
  NOTE: hardware-specific — add 'llm.engine.yaml' to .gitignore, do not commit.
  bring it up:  ollama pull gemma3:12b
```

Those two warnings are the useful half of the output: the pick is made against
the catalogue, not against whatever happens to be downloaded, so it tells you
what to fetch rather than silently settling for something already present.

The file it wrote, which belongs in `.gitignore`:

```yaml
# GENERATED by best-engine-ai-helper — do NOT commit.
# Hardware-specific: the backend and models chosen for THIS machine.
# Regenerate with:  best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml

generated_by: best-engine-ai-helper — machine-specific, do not commit
mode: local
resolved_for:
  chip: Apple M2 Max
  accelerator: gpu-metal
  memory_gb: 96.0
backend: ollama
base_url: http://localhost:11434
headroom: 0.5
min_tps: 15.0
llm:
  model: gemma3:12b
  ram_gb: 9.2
  est_tokens_per_s: 28.3
  tps_basis: estimated
  structured_output: true
  score: 77.0
  fits: true
  comfortable: true
  available: false
  pull: ollama pull gemma3:12b
vlm:
  model: gemma3:12b
  ram_gb: 9.2
  est_tokens_per_s: 28.3
  tps_basis: estimated
  structured_output: true
  score: 78.0
  fits: true
  comfortable: true
  available: false
  pull: ollama pull gemma3:12b
serve:
- ollama pull gemma3:12b
```

The pick is deliberately conservative: headroom capped at 0.5, and among models
within a few benchmark points of the best it takes the leanest and fastest, not
the largest that merely fits. `tps_basis: estimated` says the throughput came
from memory bandwidth rather than from a measurement; `available: false` says
the daemon does not have the model yet.

Force a backend with `--backend ollama|vllm` (default `auto`), or point the
same resolved engine at a server you run with `--endpoint URL`. That second
option is the one people forget: local mode does not mean *this* box, and a
vLLM machine of your own costs nothing per token either.

Afterwards, check that the machine agrees with the file:

```sh
best-engine-ai-helper doctor
```

```
engine file : llm.engine.yaml
backend     : ollama
daemon      : reachable
serves      : qwen2.5:3b, qwen3-vl:4b, qwen3-vl:4b-ctx8k, qwen3-vl:8b, qwen3:8b

  - llm: the engine file names 'gemma3:12b', which this daemon does not serve. Run `ollama pull gemma3:12b`, or re-resolve.
  - vlm: the engine file names 'gemma3:12b', which this daemon does not serve. Run `ollama pull gemma3:12b`, or re-resolve.
```

`doctor` exits non-zero when the resolved engine and the live daemon disagree,
which makes it the right thing to put in a deployment check. Consuming the file
from Python is [§10](#10-call-it-from-your-own-package).

## 4. A paid model, only when you hand it a key

This is the only member of the AI Helpers suite that can reach a paid
third-party service, and it never does so by accident. A paid call needs **two**
things: a brief that says `mode: cloud`, and an `api_key_env` naming an
environment variable that is actually set. `api_key_env` holds the variable's
**name**, never the key, and the key is never written into the engine file.

Ask first which providers are even usable:

```sh
best-engine-ai-helper providers
```

```
provider   key_env            usable  models  why not
---------  -----------------  ------  ------  ------------------------------------------------------------
anthropic  ANTHROPIC_API_KEY  NO      2       no API key found. Set ANTHROPIC_API_KEY in settings.yaml, a
gemini     GEMINI_API_KEY     NO      2       no API key found. Set GEMINI_API_KEY in settings.yaml, a .en
mistral    MISTRAL_API_KEY    NO      4       no API key found. Set MISTRAL_API_KEY in settings.yaml, a .e
openai     OPENAI_API_KEY     NO      2       no API key found. Set OPENAI_API_KEY in settings.yaml, a .en

0 of 4 provider(s) usable.
Set a key in settings.yaml, a .env file, the environment, or the keychain.
```

That is the real output on a machine holding no keys, and it is the behaviour
to rely on: a provider whose key cannot be found is not a candidate at all. A
recommendation you cannot act on is not a recommendation.

Pin a provider and a model explicitly:

```yaml
mode: cloud
provider: mistral        # openai | mistral | openrouter | together | azure |
                         # anthropic | gemini (anthropic/gemini use their own
                         # wire formats; the rest speak OpenAI-compatible)
model: mistral-large-latest
api_key_env: MISTRAL_API_KEY   # the NAME of the variable holding the key,
                               # never the key value, never persisted
structured_output: true
task: extract structured line items from an invoice PDF's OCR text
```

```sh
export MISTRAL_API_KEY=...     # your key, in the shell, never committed
best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
```

Or let it choose. Omit `model` — and `provider` too, to search every provider —
and the pick comes from the same bundled `pricing.yaml` that
[§2](#2-the-best-engine-for-a-job-as-a-report) previewed. It is the cloud
counterpart of local auto-selection, except that the budgeted resource is
**price** rather than memory, since every paid model runs on any machine:

```yaml
mode: cloud
kind: both
quality_vs_cost: 0.7   # optional, 0..1, default 0.7: 1.0 = best score whatever
                       # the price, 0.0 = cheapest whatever the quality, in
                       # between leans quality with price as a tiebreaker
task: extract structured line items from an invoice PDF's OCR text
```

Pin `provider` alone, with no `model`, to auto-pick within one provider — the
case where you already hold exactly one key. Structured-output capability is
checked first here, exactly as it is locally: a model that cannot honour a JSON
schema never wins the auto-pick over one that can, however attractively priced.

Three further keys exist for the pinned case, and the brief is the only place
they can be set. `vlm_model` pins the vision slot separately (with `kind: both`
and only `model` given, one model serves both). `base_url` overrides the
provider's endpoint, for a proxy or a regional deployment. `api_key_env`
overrides which variable the key is read from, defaulting to the provider's
conventional name. None of them ever holds the key itself.

Every cloud engine also carries a **local fallback**, resolved from the same
brief, so a failed paid call degrades to the always-available local model.
Paid → local is the only automatic direction; a local engine never silently
escalates into a paid call. Four more things then happen at the `llm.chat()`
call site:

| Concern | Default | Configure |
|---|---|---|
| **API key** | the name in `api_key_env` is looked up in `settings.yaml`, then any `.env`, then the process environment, then the OS keychain | the keychain step needs `pip install 'best-engine-ai-helper[cloud]'` |
| **Safety scan** | on, for local **and** cloud: prompts and images outbound, responses inbound | `llm.chat(..., safety=False)`; real NSFW classifiers need `[filtered]` |
| **Pseudonymization** | off; when on, scrubs personal data with the **local** fallback model before the prompt leaves the machine, then restores it | `llm.chat(..., pseudonymize=True)`, needs `[cloud]` |
| **Retry + cache** | off; retry replays a transient transport failure before failing over, cache means a repeat never pays twice | `llm.chat(..., retries=3, cache=True)`, cache needs `[cloud]` |
| **Cost tracking** | on, every call, local or paid, into the local ledger | [§8](#8-who-called-what-at-what-cost), opt out with `BEST_ENGINE_NO_LEDGER=1` |

Both extras degrade rather than fail when absent: a light retry instead of
backoff, no caching, a keyword heuristic instead of a classifier.

## 5. Usage profiles instead of model names

A brief is written per repository. The suite's eight recurring workloads are
named once instead, in a bundled usage catalogue, each stating only its
*needs*. A profile is a named brief, resolved by the same picker.

```sh
best-engine-ai-helper usages list
```

```
Families (usages that can share one model):
id  name                    members                                               summary
--  ----------------------  ----------------------------------------------------  ------------------------------------------------
F1  constrained-generation  text2sql, text2sql-figures, classification, pii-rgpd  Code + reliable structured output (SQL / JSON):
F2  prose-generation        rag-answer, report-bluf, persona                      Faithful FR/EN prose over long context: one gene
F3  embeddings              embeddings                                            Multilingual multi-granular embeddings: an embed

Profiles:
name              family  status    summary
----------------  ------  --------  ----------------------------------------------------
text2sql          F1      stable    Natural-language question -> read-only SQL (Vanna /
rag-answer        F2      stable    Sourced RAG answer with page-precise citations, FR/E
embeddings        F3      stable    Local multi-granular embeddings for the ann-router i
text2sql-figures  F1      scaffold  Question + table -> structured figure spec that spre
report-bluf       F2      stable    Multi-persona report / BLUF generation, FR/EN, quali
classification    F1      stable    Confidentiality classification C1/C2/C3, fast and de
pii-rgpd          F1      stable    PII / GDPR detection + pseudonymisation surrogates,
persona           F2      stable    Persona / register adaptation of a passage, FR/EN, m
```

No model name appears anywhere in that listing — that is the point. One
profile's needs in full:

```sh
best-engine-ai-helper usages show text2sql
```

```
text2sql  [stable, family F1]
  Natural-language question -> read-only SQL (Vanna / qwencoder).

Needs (selection criteria):
  kind             : llm
  structured_output: True
  min_tps          : 20
  headroom         : 0.5
  min_quality      : 80
  context_length   : 32768
  local_strict     : True
  task             : Translate a natural-language question into a single read-only SQL query against a fixed schema; deterministic, schema-constrained SQL and code reasoning.
```

Resolve it, and watch the needs do their work:

```sh
best-engine-ai-helper usages resolve text2sql
```

```
WARNING | llm model qwen2.5-coder:14b is not on this Ollama daemon yet: run `ollama pull qwen2.5-coder:14b` before the first call.
text2sql: backend ollama  llm=qwen2.5-coder:14b (9.9 GB, ~26 tok/s)
  NOTE: machine-specific — the chosen model lives only in the generated file; keep it gitignored, never commit.
```

The general-purpose answer on this machine was `gemma3:12b`
([§2](#2-the-best-engine-for-a-job-as-a-report)). Here it is
`qwen2.5-coder:14b`, which carries a *lower* general score, because the
profile's task text is code-shaped and its `min_tps: 20` floor is stricter than
the default 15. Nobody chose a coder model; the needs did.

A whole family resolves to **one** shared model, so a machine need not hold
eight:

```sh
best-engine-ai-helper usages resolve --family F1 --out llm.engine.F1.yaml
```

```
F1: backend ollama  llm=qwen2.5-coder:14b (9.9 GB, ~26 tok/s)
  NOTE: machine-specific — the chosen model lives only in the generated file; keep it gitignored, never commit.
  wrote llm.engine.F1.yaml
  bring it up:  ollama pull qwen2.5-coder:14b
```

On a roomy machine, resolving a single profile may specialise beyond what its
family gets; on a tight one the family collapses onto one model. From Python:

```python
for u in beah.list_usages():
    print(u["name"], u["family"], u["status"])

engine = beah.resolve_usage("text2sql")  # best-engine chooses the model here
family = beah.resolve_family("F1")  # one model for the whole F1 group
```

## 6. Capacity planning: what fits together

The questions above are each about one model. `storage` asks the one that
matters once a machine has to serve a product: what can this disk hold, and
which *combination* can be resident at the same time.

```sh
best-engine-ai-helper storage
```

```
disk   : 22.1 GB free of 994.7 (97.8% used); 17.1 GB spendable
memory : 36.0 GB available to models together

already here: qwen2.5:3b (2.0 GB), qwen3-vl:4b (3.2 GB), qwen3:8b (5.2 GB), qwen3-vl:8b (6.1 GB)

Could be pulled into the space left (6):
     0.3 GB  nomic-embed-text  [embed]
     0.7 GB  mxbai-embed-large  [embed]
     1.1 GB  snowflake-arctic-embed2  [embed]
     1.1 GB  bge-m3  [embed]
     4.7 GB  qwen2.5-coder:7b  [llm]
     8.4 GB  gemma3:12b  [vlm]

Can be held in memory at the same time, best first:
  score  232.0    34.4 GB  llm:qwen3:32b-q4_k_m + vlm:qwen3-vl:14b + embed:bge-m3   (headroom 1.6 GB)
  score  231.0    35.7 GB  llm:qwen3:14b + vlm:qwen3-vl:32b + embed:bge-m3   (headroom 0.3 GB)
  score  231.0    34.4 GB  llm:qwen3:32b-q4_k_m + vlm:qwen3-vl:14b + embed:snowflake-arctic-embed2   (headroom 1.6 GB)
  score  230.7    33.9 GB  llm:qwen3:32b-q4_k_m + vlm:qwen3-vl:14b + embed:mxbai-embed-large   (headroom 2.1 GB)
  score  230.0    35.7 GB  llm:qwen3:14b + vlm:qwen3-vl:32b + embed:snowflake-arctic-embed2   (headroom 0.3 GB)
```

Two different constraints, reported separately because they fail differently.
`17.1 GB spendable` is less than the 22.1 GB free: the command keeps a reserve
rather than letting you fill the volume. The memory section is a bundle search
rather than a ranking — the best LLM plus the best VLM plus the best embedder
usually does **not** fit together, and the winning combination here trades a
smaller VLM for a bigger LLM. `--backend vllm` re-prices the whole thing for
vLLM's footprint instead of Ollama's.

The two reference tables behind every answer in this file are printable:

```sh
best-engine-ai-helper catalog show
```

```
id                       kind   size_b  quant   disk_gb  ram_gb  general  vision
-----------------------  -----  ------  ------  -------  ------  -------  ------
qwen2.5:3b               llm    3       Q4_K_M  2.0      2.2     62       -
qwen2.5-coder:7b         llm    7       Q4_K_M  4.7      5.2     66       -
qwen2.5-coder:14b        llm    14      Q4_K_M  9.0      9.9     72       -
qwen2.5-coder:32b        llm    32      Q4_K_M  20       22      75       -
qwen3-vl:4b              vlm    4       Q4_K_M  3.2      3.5     66       72
qwen3:8b                 llm    8       Q4_K_M  5.2      5.6     74       -
```

```sh
best-engine-ai-helper hardware show
```

```
chip                     vendor  memory_gb  ollama_usable_gb  source
-----------------------  ------  ---------  ----------------  -----------
Apple M1                 apple   8          7                 apple-specs
Apple M1                 apple   16         14                apple-specs
Apple M1 Pro             apple   16         14                apple-specs
Apple M1 Pro             apple   32         29                apple-specs
Apple M1 Max             apple   32         29                apple-specs
```

Both are the merge of a bundled seed with anything cached under
`~/.best-engine-ai-helper/`; the seed itself is never modified. Refreshing them
was not run for this file: `catalog update` pulls open-weight specs from ApXML,
`catalog update --ollama` widens to real pull tags from the official Ollama
library, `catalog update --arena` merges LM Arena ratings when a fresh enough
mirror exists and says so plainly when none does, `catalog update --cloud`
reprices the PAID catalogue from LiteLLM's public table (prices and context
lengths only, never benchmark scores, which that source does not publish), and
`hardware update` records this machine's own chip and memory.

## 7. Too large to fit, still runnable: layer streaming

A decoder reads its layers in order, so only the layer being computed has to be
resident. Stream the rest off disk and a model's memory requirement collapses
from its parameter count to its widest single layer — a 70B model in a couple
of gigabytes instead of 140. The bill arrives in time: every token re-reads the
whole checkpoint, which puts this at **seconds per token** rather than tokens
per second.

The runtime is `best_engine_ai_helper.streaming`, a core dependency,
which is most of why this package's install is around 2 GB. Three of the four
subcommands are pure arithmetic over the hardware and the catalogue and never
import it, so they answer correctly, and instantly, even in an environment
where it would fail to load.

### Can this machine stream, and would it be asked to?

```sh
best-engine-ai-helper lightweight status
```

```
=== Layer streaming (lightweight) ===
  runtime here    : mps
  runtime import  : ok
  storage         : apple-internal (declared)
  read bandwidth  : 4.0 GB/s
  free disk       : 31.1 GB
  layer budget    : 72.0 GB of resident memory
  request         : auto
  would activate  : no
  trigger         : not-needed

  A model already fits this machine's memory, so streaming its layers off disk would trade two to three orders of magnitude of speed for nothing. Ask for it explicitly (--backend lightweight) to override.

  Known limits of this runtime:
  - the checkpoint has to publish safetensors; a repository that ships only a pickled pytorch_model.bin is refused, because reading one layer out of a pickle means reading the whole file once per layer
  - a sparse mixture-of-experts layer is materialised whole, so its resident figure is the full expert set rather than the few a token routes to

  Repair the install:  pip install --upgrade --force-reinstall best-engine-ai-helper
```

That output is real, and it is showing a **broken install**: the environment
these examples ran in had the package without its lightweight dependency. It is the
more instructive panel for it. `runtime import` is the honest version of a
question that used to read "is the extra installed" — lightweight ships with the
package, so anything other than `ok` means an incomplete install, and the line
says so and prints the repair command instead of a vaguer failure later.
`runtime here : mlx` is a separate fact and still true: this hardware *would*
stream, on MLX. Note also `would activate : no` with `trigger: not-needed` —
the import failure is not the reason it declined. A model already fits, so
streaming was never wanted.

`--measure` replaces the declared storage class with a real measurement of this
drive (about 256 MB written and read back with the page cache bypassed, one or
two seconds) and flips `basis` from `declared` to `measured`. Worth the two
seconds, because the drive sets this backend's entire speed.

`--json` gives the machine-readable twin, which is what the HTTP endpoint
returns:

```sh
best-engine-ai-helper lightweight status --json --request always
```

```json
{
  "decision": {
    "activate": false,
    "request": "always",
    "trigger": "manual",
    "reason": "Layer streaming cannot run here: the lightweight runtime cannot be imported, though it is a dependency of this package — the install looks incomplete: pip install --upgrade --force-reinstall best-engine-ai-helper",
    "installed": false,
    "runtime": "mlx",
    "blockers": [
      "the lightweight runtime cannot be imported, though it is a dependency of this package — the install looks incomplete: pip install --upgrade --force-reinstall best-engine-ai-helper"
    ]
  },
  "compute": {"accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400.0},
  "disk": {"storage": "apple-internal", "read_gbs": 4.0, "basis": "declared", "free_gb": 22.1},
  "memory_budget_gb": 72.0,
  "install": "pip install --upgrade --force-reinstall best-engine-ai-helper"
}
```

`--request always` forced the question and still got `activate: false`, with
the blocker named. `install` is a **repair** command, not an opt-in one: it is
what to run when `installed` comes back false.

### What could it stream, and at what price?

```sh
best-engine-ai-helper lightweight plan --kind llm
```

```
=== LLM: streamable off apple-internal at 4.0 GB/s, 72.0 GB layer budget ===
id                        params  layer_gb  ckpt_gb  s/token  disk_gb  runs  notes
------------------------  ------  --------  -------  -------  -------  ----  -----------------------------------------------
qwen3-vl:14b              14B     2.7       28.0     8.3      28.0     yes   48 layers
qwen3:14b                 14B     2.7       28.0     8.3      28.0     yes   48 layers
gemma3:12b                12B     2.6       24.0     7.0      24.0     yes   39 layers
qwen3:8b                  8B      2.2       16.0     4.7      16.0     yes   32 layers
qwen2.5-coder:7b          7B      2.1       14.0     4.1      14.0     yes   32 layers
qwen2.5:3b                3B      1.5       6.0      1.8      6.0      yes   28 layers
deepseek-v3:671b          671B    29.0      671.0    200.0    671.0    NO    the checkpoint is 671 GB and only 31 GB is free
llama3.1:405b             405B    18.5      810.0    250.0    810.0    NO    the checkpoint is 810 GB and only 31 GB is free
qwen3:235b-a22b           235B    14.5      470.0    142.9    470.0    NO    the checkpoint is 470 GB and only 31 GB is free
mixtral:8x22b             141B    14.0      282.0    83.3     282.0    NO    the checkpoint is 282 GB and only 31 GB is free
llama3.3:70b              70B     6.1       140.0    41.7     140.0    NO    the checkpoint is 140 GB and only 31 GB is free
qwen3:32b-q8_0            32B     4.0       64.0     18.9     64.0     NO    the checkpoint is 64 GB and only 31 GB is free

  Pick: Qwen/Qwen3-VL-14B-Instruct — 14B in 2.7 GB resident, 8.3 s/token, 28 GB of checkpoint on disk.
  A 300-token answer: 41 min.
```

Read three columns, in that order, and the order is the lesson. `layer_gb` is
what has to fit in **memory** — one decoder layer, not the model — and it is
tiny everywhere, even for 671B. `disk_gb` is what has to be free on the
**drive**, and on this 97%-full one it is what refuses everything large: a 70B
is turned away for want of 140 GB while its resident cost would have been
6.1 GB. `s/token` is what you then wait.

That disk column is the checkpoint and nothing more. It used to be roughly
double, because the previous runtime wrote a second per-layer copy before
running anything; reading out of the original safetensors removed the scratch
space entirely, and with it the reason almost every row once said `NO`.

Depth, not size, decides the layer: `llama3.1:405b` streams in an 18.5 GB layer
across 126 layers, where `mixtral:8x22b` at 141B needs 14.0 GB across 56 — the
parameter counts alone would have predicted a far wider gap.

`--context 32` re-prices the layer for a 32k context, which is not free: the KV
cache is the one thing streaming does not shrink. `--batch 8` pulls the only
big lever the backend has — the wall clock for a 300-token answer does not
move, but it buys eight answers instead of one, and the layer figure grows by
the seven extra KV caches that bought them. There is no compression flag: the
runtime reads the checkpoint at the dtype it ships in, so fewer bits means
pointing at a repository already published that way.

### Native model or streamed model? One screen.

This is the decision the backend actually forces, and the command prices both
sides in the same unit.

```sh
best-engine-ai-helper lightweight compare --tokens 300
```

```
=== LLM: ollama vs lightweight, for a 300-token answer ===
  budgets: 36.0 GB resident (ollama) · 72.0 GB per layer (lightweight) · disk 4.0 GB/s (declared)
model                               backend  score  resident  tok/s  answer  runs
----------------------------------  -------  -----  --------  -----  ------  ----
qwen3:72b-q8_0                      ollama   89     78.0      3.3    2 min   NO
qwen3:72b-q4_k_m                    ollama   87     48.0      5.4    56 s    NO
qwen3:32b-q8_0                      ollama   85     36.0      7.2    42 s    NO
qwen3:32b-q4_k_m                    ollama   83     22.0      11.8   25 s    NO
qwen3:14b                           ollama   78     10.5      24.8   12 s    yes
gemma3:12b                          ollama   77     9.2       28.3   11 s    yes
Qwen/Qwen3-VL-4B-Instruct           lightweight   66     1.6       0.425  12 min  yes
Qwen/Qwen2.5-3B-Instruct            lightweight   62     1.5       0.567  9 min   yes
deepseek-ai/DeepSeek-V3             lightweight   91     29.0      0.005  16.4 h  NO
Qwen/Qwen3-235B-A22B-Instruct-2507  lightweight   90     14.5      0.007  11.5 h  NO
Qwen/Qwen3-72B-Instruct             lightweight   89     6.2       0.024  3.5 h   NO
meta-llama/Llama-3.1-405B-Instruct  lightweight   88     18.5      0.004  19.9 h  NO

  Streaming buys nothing here: Qwen/Qwen3-VL-4B-Instruct scores no higher than qwen3-vl:14b, which already fits and answers in 13 s. Stay native.
```

The verdict is the whole output. On this machine the streamable models that
*fit the disk* are small ones scoring no better than what already runs
natively, and the big ones that would score higher cannot be split on a
98%-full drive — so the honest recommendation is to stay native, and it is
given. That is the behaviour to want here: a tool that always found streaming
attractive would be useless.

`--batch 8` is the lever to try before concluding something is too slow: eight
prompts ride through each layer pass together, so eight answers arrive in the
time of one. It is the only one the backend has.

### Paying the download deliberately

The first streaming call downloads the checkpoint, which for a large model is
tens of minutes of disk and reads exactly like a hang. Pay it on purpose
instead:

```sh
best-engine-ai-helper lightweight prepare \
  --model meta-llama/Llama-3.3-70B-Instruct
```

Not run for this file: it downloads a 70B checkpoint. There is nothing else to
prepare, and that is the whole change from the previous runtime — layers are
read out of the checkpoint's own memory-mapped safetensors, so no second copy
is written, there is no conversion step, and the only thing this command buys
is paying the download at a moment you chose.

### The same brief, resolved for streaming

```sh
best-engine-ai-helper resolve --brief llm.brief.yaml --backend lightweight
```

```
WARNING | The brief wants schema-constrained output and llm resolved to a streamed model, which cannot honour one. Schema-driven calls must stay on an Ollama model.
Wrote llm.engine.yaml
  backend: lightweight  (llm=Qwen/Qwen3-VL-4B-Instruct, vlm=Qwen/Qwen3-VL-4B-Instruct)
  NOTE: hardware-specific — add 'llm.engine.yaml' to .gitignore, do not commit.
  bring it up:  best-engine-ai-helper lightweight prepare --model Qwen/Qwen3-VL-4B-Instruct
```

The warning is the point. The brief in
[§3](#3-one-brief-per-repo-one-engine-per-machine) asks for
`structured_output: true`, and lightweight has no schema-constrained generation, so
forcing this backend contradicts the brief and the command says so rather than
quietly producing something that would fail at the first `json_schema=` call.
The engine file records it honestly:

```yaml
backend: lightweight
base_url: ''              # a library, not a server: it runs in your process
lightweight:
  activate: false
  trigger: manual
  runtime: mps
  installed: true
llm:
  model: Qwen/Qwen3-VL-4B-Instruct
  catalog_id: qwen3-vl:4b
  backend: lightweight         # per-kind, so a mixed descriptor stays readable
  streaming: true
  ram_gb: 2.7             # one resident layer
  checkpoint_gb: 8.0      # what every token re-reads
  layers: 29
  layers_estimated: true
  disk_peak_gb: 16.8
  disk_steady_gb: 8.8
  disk_fits: true
  est_tokens_per_s: 0.425
  seconds_per_token: 2.4
  structured_output: false  # lightweight has no schema-constrained generation
serve:
- best-engine-ai-helper lightweight prepare --model Qwen/Qwen3-VL-4B-Instruct
```

With no `--backend`, a kind for which nothing fits escalates to streaming on
its own, and only that kind does. Set `lightweight: never` in the brief, or
`BEST_ENGINE_LIGHTWEIGHT=never`, to switch the escalation off entirely.

### From Python

```python
hw, disk = beah.available_memory(), beah.disk_profile()

entry = {
    "id": "llama3.3:70b",
    "size_b": 70,
    "layers": 80,
    "hf_id": "meta-llama/Llama-3.3-70B-Instruct",
}

# Three different answers to "how fast is it", all of them true
timing = beah.lightweight_generation_time(entry, disk["read_gbs"], new_tokens=300, batch=8)
print(timing["decode_tps"])  # 0.024  — steady state, one sequence
print(timing["time_to_first_token_s"])  # 41.176 — one pass, prompt included
print(timing["effective_tps"])  # 0.194  — eight answers share each pass

# Should this machine stream at all?
print(beah.lightweight_decide(conventional_resolved=False)["reason"])

# Native or streamed, for a 300-token answer?
print(
    beah.lightweight_compare(
        beah.load_catalog(),
        hw=hw,
        disk=disk,
        bandwidth_gbs=beah.compute_profile()["bandwidth_gbs"],
        new_tokens=300,
    )["verdict"]
)
```

Those three timing numbers are the executed output, and the gap between them is
the argument for having all three: 0.024 tok/s is the steady state for one
sequence, 41.176 s is a single forward pass, and 0.194 tok/s is what batching
eight prompts turns the same hardware into. `disk_profile(measure=True)` takes
a second or two and replaces the declared read bandwidth with a measured one.

`beah.lightweight_generate(prompt, model=..., max_new_tokens=64)` runs a streamed
model in this process, with no server involved. It is the one function here
that needs the runtime importable, so it is not executed in this file.

## 8. Who called what, at what cost

Every `llm.chat()` call — from this package's own gates or from any downstream
project — can be appended to a local, append-only SQLite ledger at
`~/.best-engine-ai-helper/usage.db`: who called it, which model and backend,
latency, success or failure, and a cost that is always `0.0` for local Ollama
or vLLM. It exists for the "one company, several people on a shared machine"
case, without standing up a telemetry stack.

```sh
best-engine-ai-helper activity
```

```
No calls recorded yet.
```

That is the real output against a fresh ledger, and it is what a reader should
expect: nothing is recorded until something calls a model. Once calls exist the
same command reports the totals, then a breakdown by user and by model;
`--format json` gives the machine-readable twin.

Local only, no network call. `BEST_ENGINE_NO_LEDGER=1` disables recording
entirely, and `BEST_ENGINE_USER=alice` attributes calls to a named person on a
shared machine. The library API behind it is `best_engine_ai_helper.observe`
(`enable()`, `as_user(name)`, `Ledger.summary()`).

## 8bis. Speak OpenAI to it

The outside view: any OpenAI SDK, no code changes, and no model name to choose.

```sh
best-engine-ai-helper serve
```

```
  OpenAI-compatible API : http://127.0.0.1:8000/v1
  Browser GUI           : http://127.0.0.1:8000/gui
  OpenAPI schema        : http://127.0.0.1:8000/docs
  MCP endpoint          : http://127.0.0.1:8000/mcp

  from openai import OpenAI
  client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="not-needed")
  client.chat.completions.create(model="best", messages=[...])

  Model names: best · best-llm · best-vlm · best-embed · best-image
               best:<task>  (e.g. best:write SQL)
```

### Chat, with the model chosen for you

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="not-needed")

done = client.chat.completions.create(
    model="best",  # not a name you had to know
    messages=[{"role": "user", "content": "name three colours"}],
)
print(done.model)  # 'qwen3:14b' — what actually ran
print(done.choices[0].message.content)
print(done.system_fingerprint)  # 'best-engine-ai-helper:usage=reported'
```

`model` in the response is the point: you gave up naming it, so the answer
tells you. `system_fingerprint` says whether `usage` was counted by the backend
or estimated from characters — Ollama reports real counts, so it usually reads
`usage=reported`.

Name the task and you get a better pick, on the axis that matters:

```python
client.chat.completions.create(
    model="best:write SQL for a warehouse",
    messages=[{"role": "user", "content": "top 10 customers by revenue"}],
)
```

### Vision, by sending an image the way the SDK's own docs do

```python
import base64, pathlib

encoded = base64.b64encode(pathlib.Path("screenshot.png").read_bytes()).decode()
client.chat.completions.create(
    model="best",  # resolves to a VLM because of the image
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what is wrong with this layout?"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
            ],
        }
    ],
)
```

A `data:` URI always works. An `http(s)` URL is refused unless you set
`BEST_OPENAI_FETCH_IMAGE_URLS=1`, because fetching an address the *caller*
chose turns this server into a request-forgery hop into whatever private
network it can see.

### Streaming, and a schema

```python
for chunk in client.chat.completions.create(
    model="best", messages=[{"role": "user", "content": "count to five"}], stream=True
):
    print(chunk.choices[0].delta.content or "", end="")
```

```python
done = client.chat.completions.create(
    model="best",
    messages=[{"role": "user", "content": "three colours, as JSON"}],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "colours",
            "schema": {"type": "object", "properties": {"colours": {"type": "array"}}},
        },
    },
)
```

The schema is a real constraint, not a prompt instruction: it goes to Ollama's
grammar-constrained output, so the shape is guaranteed rather than requested.
That is also why a schema request arrives in one chunk when streamed — the
constrained path does not stream, and a fake drip would tell you nothing true.

### Embeddings and images

```python
vectors = client.embeddings.create(model="best-embed", input=["one", "two"])
len(vectors.data), len(vectors.data[0].embedding)  # (2, 768)

picture = client.images.generate(
    model="best-image",
    prompt="a red bicycle in the rain",
    n=1,
)
pathlib.Path("bike.png").write_bytes(base64.b64decode(picture.data[0].b64_json))
```

`b64_json` is the default response format here rather than OpenAI's `url`,
because a local server has nowhere to host a file; asking for `url` returns a
`data:` URI. `size` defaults to `"auto"`, which means the chosen model's native
resolution — the one size it is actually good at.

### What a refusal looks like

```python
from openai import BadRequestError

try:
    client.chat.completions.create(model="best", messages=[{"role": "user", "content": "x"}], n=3)
except BadRequestError as exc:
    print(exc)  # 400 - n must be 1: this server runs one local model per request
```

Every unsupported parameter answers like that, by name. A parameter silently
ignored would be worse: you would believe you got what you asked for.

## 8ter. An image, locally

```sh
best-engine-ai-helper imagine plan
```

```
=== Image models: 36.0 GB budget, 400.0 GB/s memory bandwidth ===
id             params  size       steps  gb    offload  s/image  runs  notes
-------------  ------  ---------  -----  ----  -------  -------  ----  -----
flux1-schnell  16.9B   1024x1024  4      30.8  yes      16.9     yes
sd35-medium    10.9B   1024x1024  28     28.3  no       24.8     yes
sdxl           3.5B    1024x1024  28     9.8   no       25.8     yes
sdxl-turbo     3.5B    512x512    4      9.0   no       0.9      yes
sd15           1.1B    512x512    28     2.9   no       2.1      yes

  Pick: black-forest-labs/FLUX.1-schnell — 1024x1024 in 30.8 GB resident,
  4 steps, about 16.9 s an image (components taking turns).
```

Three columns carry the whole decision. `gb` is what has to be resident, and
`offload` says whether that figure assumes the pipeline's components take turns
on the device — tried automatically before any model is rejected for memory,
because on FLUX it is the difference between 43 GB and 31 GB. `s/image` is
steps times denoiser passes, which is why a distilled 4-step model beats a
28-step one of the same size by seven times.

```sh
best-engine-ai-helper imagine generate --prompt "a red bicycle in the rain" --out bike.png
```

```
Using black-forest-labs/FLUX.1-schnell at 1024x1024, about 16.9 s an image.
Wrote bike.png (1483 kB)
```

Weights download on first use, and the licences differ per model — SD 1.5 and
SDXL are CreativeML OpenRAIL-M, SD 3.5 is the Stability Community licence,
FLUX.1-schnell is Apache-2.0 — so check the one you picked before publishing
its output.

## 9. The GUI, the HTTP API and the MCP tools

One process serves all three surfaces.

```sh
best-engine-ai-helper gui          # browser GUI + /api routes, port 8000
best-engine-ai-helper-mcp          # the same, plus the MCP endpoint at /mcp
```

Open `http://127.0.0.1:8000/gui`: the hardware panel loads immediately, and
typing a task calls the same `recommend()` that backs `report`. The page is
bilingual — French by default, English at `/gui?lang=en`. `--host` and `--port`
override the defaults. See [GUI.md](GUI.md) for screenshots and the full
write-up.

The JSON endpoints are usable directly, and the output below is real:

```sh
curl -s http://127.0.0.1:8000/api/system | python3 -m json.tool
```

```json
{
    "platform": "darwin",
    "chip_vendor": "apple",
    "memory": {"unified_gb": 96.0, "vram_gb": null, "ram_gb": 96.0},
    "compute": {"accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400.0},
    "memory_budget_gb": 36.0,
    "hardware": {"...": "the live os-helper reading, exactly as in detect"}
}
```

```sh
curl -s -X POST http://127.0.0.1:8000/api/recommend \
     -H 'Content-Type: application/json' \
     -d '{"task": "product descriptions and image-quality checks"}' \
  | python3 -m json.tool
```

```json
{
    "task": {
        "input": "product descriptions and image-quality checks",
        "kinds": ["llm", "vlm"],
        "application": "generalist",
        "vlm_application": "vision",
        "matched": ["image"],
        "language": "en"
    },
    "backend": "ollama",
    "memory_budget_gb": 36.0,
    "headroom": 0.5,
    "comfort_tps": 15.0,
    "recommendations": {
        "llm": {
            "axis": "generalist",
            "chosen": {
                "id": "gemma3:12b",
                "vllm_id": "google/gemma-3-12b-it",
                "ram_gb": 9.2,
                "score": 77.0,
                "fits": true,
                "structured_output": true,
                "est_tokens_per_s": 28.3,
                "tps_basis": "estimated",
                "comfortable": true,
                "installed": false
            }
        }
    }
}
```

```sh
curl -s 'http://127.0.0.1:8000/api/lightweight?answer_tokens=300&batch=8' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["comparison"]["verdict"])'
```

```
Streaming buys nothing here: Qwen/Qwen3-VL-4B-Instruct scores no higher than qwen3-vl:14b, which already fits and answers in 13 s. Stay native.
```

That one call returns the decision, the storage profile, the ranked plans and
the comparison together; its top-level keys are `decision`, `disk`,
`memory_budget_gb`, `comfort_tps_streaming`, `install`, `chosen`, `plans` and
`comparison`. `GET /api/providers` returns the same rows as the `providers`
command, and `GET /api/activity` reads the ledger from
[§8](#8-who-called-what-at-what-cost).

Every one of those routes is published as an **MCP tool** by
`best-engine-ai-helper-mcp`, so an agent host can call them directly. The
wrapper publishes only the deciding routes on purpose: no MCP tool here runs a
model. `BEST_ENGINE_HOST` and `BEST_ENGINE_PORT` override the bind address.

A fourth surface on the same port runs a model rather than deciding about one:
`best-engine-ai-helper serve` adds an OpenAI-compatible `/v1`, so an existing
OpenAI client asks for the model named `best` and gets whatever this hardware
should actually run. See [Command line](#command-line) for its banner and model
aliases.

## 10. Call it from your own package

This is the integration every other member of the AI Helpers suite uses: no
`DEFAULT_MODEL` constant anywhere, the model always read from a resolved
engine.

The cheapest entry point, for a package that only needs to know *which tag*:

```python
print(beah.text_model())  # 'qwen3:8b'
print(beah.vision_model())  # 'gemma3:12b'
print(beah.resolved_models())  # {'text': 'qwen3:8b', 'vision': 'gemma3:12b'}
```

Those resolve an environment override, then the selection persisted by `pull`,
then a safe default — no hardware probe, no network, deterministic, so they are
safe in CI. The values above are the real output on a machine where nothing has
been pulled yet, which is exactly why they are the defaults.

The full pattern, for a repository that has a brief:

```python
engine = beah.ensure(".")  # loads llm.engine.yaml, resolving it on first use
print(beah.model_for(engine, "llm"))  # ('ollama', 'http://localhost:11434', 'gemma3:12b')

summary = llm.chat(prompt, engine=engine, kind="llm")
critique = llm.chat(prompt, engine=engine, kind="vlm", images=[png], json_schema=SCHEMA)
```

`chat` reads the backend and model from the engine and dispatches to Ollama
(`/api/generate`) or vLLM (OpenAI `/v1/chat/completions`) transparently; given
a `json_schema` it returns a parsed dict rather than a string. See the README's
[Downstream integration → Pattern B](README.md#pattern-b-a-per-project-engine-resolved-from-a-tuned-brief)
for the whole flow and the missing-file policy.

A schema-constrained call, executed against a local daemon:

```python
out = llm.chat(
    "In one short sentence: what is unified memory?",
    model="qwen2.5:3b",
    json_schema={
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    },
)
print(out)
```

```
{'answer': 'Unified memory is a memory management system that allows CPU and GPU to share memory efficiently.'}
```

That is the one snippet in this file that needed Ollama running, and the one
whose output is **not** reproducible: a model is not a function, and a second
run of exactly that call returned "…share memory in a unified way" instead. The
*shape* is the guarantee — `json_schema=` makes it a parsed dict with an
`answer` key rather than a string to regex — and the sentence inside is not.
`model=` is spelled out only because the example has no brief to resolve; in
real code it is `engine=`, and the tag is never written down.

The decision machinery is importable on its own, with no CLI and no engine
file:

```python
hw, catalog = beah.available_memory(), beah.load_catalog()

print(beah.select(hw, catalog, kind="vlm")["id"])  # 'gemma3:12b'
print(beah.select(hw, catalog, kind="llm")["id"])  # 'qwen3:32b-q8_0'
```

Note that `select` and `report` disagree here, and the disagreement is correct:
`select` returns the best model that **fits memory** (`qwen3:32b-q8_0`, 36 GB,
score 85), while `report` and `resolve` also apply the comfort-throughput floor
and so return `gemma3:12b`. Reach for `rank()` when you want the ordered list
with the `comfortable` flag on every row.

The whole recommendation — memory, compute and task together — is one call:

```python
report = beah.recommend_engines(
    beah.available_memory(),
    beah.load_catalog(),
    task="product descriptions and image-quality checks",
    compute=beah.compute_profile(),
)
print(report["recommendations"]["vlm"]["chosen"]["id"])  # 'gemma3:12b'
print(beah.to_markdown(report))  # the report from section 2
```

`beah.write_report(report, "engine")` writes the `engine.md` / `engine.json`
pair that `report --out engine` produces.

## Command line

One command line, built with click. `best-engine-ai-helper -h` lists it, and
`best-engine-ai-helper <command> -h` documents any one of them. Releases before
1.9.0 also installed a second, suffixed entry point mirroring it command for
command; there is one name now, and this is it.

| Command | What it does | Needs |
|---|---|---|
| `detect` | this machine's hardware, as JSON | — |
| `recommend` | ranked candidates for this hardware; `--kind`, `--headroom` | — |
| `report` | best engine(s) for a free-text task, Markdown + JSON; `--task`, `--out`, `--live`, `--format`, `--no-cloud`, `--quality-vs-cost`, `--cloud-provider` | — |
| `resolve` | a brief into a machine-specific engine file; `--brief`, `--out`, `--backend`, `--endpoint` | — |
| `usages list` / `show` / `resolve` | the bundled task profiles and families | — |
| `storage` | what fits on disk, and which models fit in memory together; `--backend` | — |
| `providers` | which cloud providers are usable right now, and why not; `--json` | — |
| `doctor` | resolved engine against live daemon; non-zero when they disagree; `--directory`, `--timeout` | Ollama |
| `catalog show` | the merged model catalogue | — |
| `catalog update` | refresh the catalogue cache; `--limit`, `--timeout`, `--ollama`, `--arena`, `--cloud` (paid list prices from LiteLLM) | network |
| `hardware show` | the merged chip table | — |
| `hardware update` | record this machine's chip and memory | — |
| `lightweight status` | can this machine stream layers, and would it; `--measure`, `--json`, `--request` | — |
| `lightweight plan` | what it could stream, and at what price; `--kind`, `--context`, `--batch`, `--json` | — |
| `lightweight compare` | native against streamed, same answer, both prices; `--tokens`, `--batch`, `--measure`, `--json` | — |
| `lightweight prepare` | download a checkpoint now rather than inside the first call; `--model` | network, runtime |
| `pull` | pull the best model, then run both Ralph gates; `--keep-failed`, `--vllm`, `--application`, `--min-tps` | Ollama, network |
| `validate` | re-run the Ralph gates on the configured model | Ollama |
| `env` | print the env block for `~/.zshrc` | `pull` first |
| `activity` | the local cost ledger; `--format` | — |
| `gui` | serve the browser GUI and the `/api` routes; `--host`, `--port` | — |
| `serve` | the same port, plus an OpenAI-compatible `/v1`; `--host`, `--port` | Ollama, to answer |
| `imagine plan` | rank the text-to-image models this machine can run; `--size`, `--json` | — |
| `imagine generate` | generate one image locally; `--prompt`, `--out`, `--model`, `--size`, `--steps`, `--seed`, `--negative` | network |

Two of those deserve a line of their own. `serve` puts an **OpenAI-compatible**
surface on the same port as the GUI, the `/api` routes and `/mcp`, so an
existing OpenAI client reaches the model this machine should run without knowing
its name:

```
  OpenAI-compatible API : http://127.0.0.1:8000/v1
  Browser GUI           : http://127.0.0.1:8000/gui
  OpenAPI schema        : http://127.0.0.1:8000/docs
  MCP endpoint          : http://127.0.0.1:8000/mcp

  from openai import OpenAI
  client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="not-needed")
  client.chat.completions.create(model="best", messages=[...])

  Model names: best · best-llm · best-vlm · best-embed · best-image
               best:<task>  (e.g. best:write SQL)
```

`GET /v1/models` lists those aliases alongside every concrete catalogue entry —
`best` resolves to a VLM when the request carries images, and `best:write SQL`
runs the same task parsing `report` does. `api_key="not-needed"` is literal: the
server is local and asks for nothing.

`imagine` is the third kind of model this package chooses, and the arithmetic is
not the LLM arithmetic: a diffusion model is three or four networks taking turns,
so its footprint depends on whether they are all resident or handed to
`diffusers`' component offload, and its cost is steps times denoiser passes
rather than tokens per second.

```sh
best-engine-ai-helper imagine plan
```

```
=== Image models: 36.0 GB budget, 400.0 GB/s memory bandwidth ===
id             params  size       steps  gb    offload  s/image  runs  notes
-------------  ------  ---------  -----  ----  -------  -------  ----  -----
flux1-schnell  16.9B   1024x1024  4      30.8  yes      16.9     yes
sd35-medium    10.9B   1024x1024  28     28.3  no       24.8     yes
sdxl           3.5B    1024x1024  28     9.8   no       25.8     yes
sdxl-turbo     3.5B    512x512    4      9.0   no       0.9      yes
sd15           1.1B    512x512    28     2.9   no       2.1      yes

  Pick: black-forest-labs/FLUX.1-schnell — 1024x1024 in 30.8 GB resident, 4 steps, about 16.9 s an image (components taking turns).
```

Read the `steps` column against `s/image`: `sdxl-turbo` is the same 3.5B network
as `sdxl`, distilled to 4 steps instead of 28, and that one column is the whole
28x difference in wait. `offload: yes` on FLUX means it only fits by handing the
components to `diffusers` in turn. `--size auto` is the default and the fair
comparison, because asking a 512px model for 1024x1024 duplicates subjects
rather than adding detail. `imagine generate` is not run here: it downloads a
diffusers pipeline.

The three not demonstrated above, because running them here would mean a model
download:

```sh
best-engine-ai-helper pull        # pull the best model; run both Ralph gates
best-engine-ai-helper validate    # re-run the gates on the current model
best-engine-ai-helper env         # print the env block for ~/.zshrc
```

`pull` selects as `recommend` does, downloads through Ollama, then refuses to
write anything until the model passes two gates: it must catch and fix a flaw
seeded into a short text (the Ralph Loop), and spot an obvious defect seeded
into a small test image (the Ralph Eyeball Loop). Only then is `env.sh`
written, which is what `env` prints. Run before `pull`, it says so:

```
env.sh not found. Run `best-engine-ai-helper pull` first.
```

## Troubleshooting

**`env.sh not found. Run best-engine-ai-helper pull first.`** — `env` prints a
file that `pull` writes. Nothing has been pulled and validated yet.

**`doctor` says the engine file names a model the daemon does not serve.** The
pick is made against the catalogue, not against what is downloaded. Run the
`ollama pull …` line that `resolve` printed, or re-resolve.

**Everything reads `NO` in the `fits` column.** The budget is half of the
*usable* pool, not half of installed memory: 96 GB becomes 72.0 GB usable, then
36.0 GB after headroom. `beah.effective_budget(beah.available_memory())` prints
the number. `--headroom` only ever tightens it; values above 0.5 are clamped.

**A model fits and is still not chosen.** It failed the comfort-throughput
floor, not the memory test. Look at the `comfy` column, and at `min_tps` in the
brief.

**`lightweight status` says `runtime import : FAILS (install incomplete)`.** lightweight
is a core dependency, so this is a broken install rather than a missing extra —
a stripped container, or a wheel that failed to build. The panel prints the
repair command. `status`, `plan` and `compare` keep working regardless; only
actually generating needs the runtime.

**`lightweight plan` refuses almost everything on `disk_gb`.** That column is
the checkpoint's own size — nothing is copied, so there is no scratch space on
top — and it is still the usual blocker, far more often than memory. A 70B is
140 GB before it is anything else. Free space, or pick a smaller checkpoint.

**A structured-output call comes back empty.** Either the model cannot honour a
JSON schema — `catalog show` and the `notes` column say which ones cannot, and
the Qwen3-VL family is the common surprise — or the backend is lightweight, which
has no schema-constrained generation at all. `resolve --backend lightweight` warns
about exactly this.

**`providers` says `0 of 4 usable` when a key is exported.** The lookup order is
`settings.yaml`, then any `.env`, then the process environment, then the OS
keychain, and the brief's `api_key_env` decides *which variable name* is read. A
key held under some other name than the provider's conventional one needs that
field set. The keychain step itself needs
`pip install 'best-engine-ai-helper[cloud]'`.

**A cloud call fails and nothing seems to happen.** It fell back. Every cloud
engine carries a local fallback resolved from the same brief, and `activity` is
where the failed paid call and the local retry both show up.
