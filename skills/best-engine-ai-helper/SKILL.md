---
name: best-engine-ai-helper
description: >-
  Pick, pull and validate the best local LLM or VLM for the machine at hand.
  Detects available memory (Apple Silicon unified pool, NVIDIA VRAM, or system
  RAM), ranks a bundled catalogue inside a safety headroom, pulls the winner
  through Ollama, puts it through two quality gates (a seeded text flaw and a
  seeded visual defect), and writes the environment file downstream projects
  read. Also sizes and times models that do NOT fit, runnable by streaming
  their layers off disk (airllm). Use when the user asks "which model should I
  run on this machine", "what LLM fits in my RAM / VRAM", "can this Mac run a
  14B", "can I run a 70B on 8 GB", "pull a local model", "which vision model",
  "is this model good enough", "how many tokens per second", or names
  `best-engine-ai-helper`, `model_for`, `airllm`, `recommend_engines`. **Any
  suite package that needs an LLM or VLM must route through this one rather
  than hardcode a model name.** Do NOT use to run inference, serve a model, or
  pick a vector index (ann-router).
license: BSD-3-Clause
metadata:
  author: Warith Harchaoui
  package: best-engine-ai-helper
  suite: ai-helpers
  homepage: https://deraison.ai/ai-helpers
---

# best-engine-ai-helper — choose the local model this machine can actually run

`best-engine-ai-helper` answers one question: **given this hardware and this
task, which local model should run, and is it good enough?** It detects the
memory actually available, ranks a bundled catalogue against a safety
headroom, pulls the winner via Ollama, and only writes the environment file
after the model passes two quality gates.

## The suite rule

> Every AI Helpers package that needs an LLM or a VLM resolves it through
> `best-engine-ai-helper`. None of them hardcodes a model name.

`md2star`, `standpoint` and `vocal-helper` already do this in production —
`md2star` is the reference implementation to copy. `os-helper` is the one
package that must never mention an LLM at all.

When writing suite code that needs a model:

```python
import best_engine_ai_helper as be

model = be.text_model()  # resolved for this machine, from the env file
vlm = be.vision_model()
```

Not `"llama3.2:3b"`, not an env var you invented.

## Before anything: verify it is installed

```bash
best-engine-ai-helper detect              # hardware snapshot; no Ollama needed
python -c "import best_engine_ai_helper"  # library import check
ollama --version                          # needed for pull / validate / env
```

Install — **CLI, GUI, HTTP API and MCP are all in the default install**, there
is nothing to opt into:

```bash
pip install best-engine-ai-helper
pip install 'best-engine-ai-helper[cloud]'     # + hosted-model price lookups
```

[Ollama](https://ollama.com) is required for `pull`, `validate` and `env`; not
for `detect`, `recommend` or `report`.

## What it does, and how to invoke it

| Intent | Command | Library |
|---|---|---|
| What hardware is this | `detect`, `hardware` | `compute_profile`, `available_memory` |
| Which model for this task | `recommend "task description"` | `recommend_engines`, `parse_task` |
| Rank / inspect the catalogue | `list`, `show`, `catalog` | `load_catalog`, `rank`, `select` |
| Pull the chosen model | `pull` | `ensure` |
| Run the quality gates | `validate` | — |
| Write the env file projects read | `env` | `write_engine`, `load_engine` |
| Resolve the model to use now | `resolve` | `model_for`, `resolved_models` |
| A written report | `report` | `to_markdown`, `write_report` |
| What is running right now | `activity` | — |
| Task families and usages | `usages` | `list_usages`, `resolve_usage` |
| Browser version of the read-only half | `gui` | — |
| Could this machine stream a too-large model | `airllm status` | `airllm_decide`, `disk_profile` |
| What it could stream, and at what price | `airllm plan` | `airllm_rank`, `airllm_pick` |
| Native model or streamed model | `airllm compare` | `airllm_compare`, `airllm_generation_time` |
| Split a checkpoint before the first call | `airllm prepare` | `airllm_load` |

Quick examples:

```bash
best-engine-ai-helper detect
best-engine-ai-helper recommend "summarise long French meeting transcripts"
best-engine-ai-helper pull && best-engine-ai-helper validate
best-engine-ai-helper env                 # writes the file downstream reads
best-engine-ai-helper airllm compare --tokens 300   # when nothing good fits
```

For the full command and flag matrix, the catalogue schema and the headroom
model, read `references/cli-reference.md`. For the HTTP API, MCP tools and the
bilingual GUI, read `references/surfaces.md`. For the exhaustive trigger list,
read `references/triggers.md`.

## Rules of thumb

- **Detect before you recommend.** The whole point is fitting the machine;
  a recommendation made without `detect` is a guess.
- **Describe the task in words.** `recommend` parses a natural-language task
  description (`parse_task`), so "summarise long French transcripts" produces
  a better answer than "give me a good model".
- **Headroom is not pessimism.** `MAX_HEADROOM` leaves room for the OS and the
  context window; a model that fits exactly will swap and crawl.
- **A pulled model is not yet a trusted model.** `validate` runs the two gates
  — the Ralph Loop (a seeded textual flaw) and the Ralph Eyeball Loop (a
  seeded visual defect). Only a model that passes both gets written to the
  env file.
- **Read the choice, do not re-derive it.** Downstream code calls
  `text_model()` / `vision_model()`; it does not re-run detection.
- **Offline after the download.** `pull` and `catalog update` are the only
  online operations, and the bundled catalogue is enough for everyday use.
- **"Nothing fits" has two answers, and the second one is slow.** A model too
  large to load can still be run by streaming its layers off disk — the airllm
  runtime ships with the package, so there is nothing to install first.
  Resident memory becomes one layer shard — a 70B in about 4 GB instead of 141
  — and the price is **seconds per token**, because every
  token re-reads the whole checkpoint. Reach for it when the user needs a
  better model than fits, never when they need a quick answer. `airllm
  compare` prices both sides for the same answer length and usually says "stay
  native"; quote its verdict rather than guessing.
- **Under streaming, the prompt is nearly free and batching is the big
  lever.** One forward pass reads the checkpoint once whatever rides through
  it, so a 2000-token prompt costs what a 10-token one does (unique to this
  backend), and eight prompts answered together arrive in the time of one.
  4-bit compression is worth ~3x; a batch of 8 is worth 8x.
- **Disk, not memory, is what refuses a streamed model.** The layer split needs
  roughly twice the checkpoint free at once. Check `airllm status` for free
  space before promising anything.
- **No streamed model honours a JSON schema.** airllm exposes raw generation,
  so schema-driven tasks stay on an Ollama model. The engine file says
  `structured_output: false` and `llm.chat` raises rather than pretending.
- **This package chooses; it does not infer.** It will not run a prompt for
  you, and serving is Ollama's job.
- **After running, report the chosen model, the memory it needs and the
  headroom left** — those three numbers are the decision.
