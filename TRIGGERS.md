# TRIGGERS: best-engine-ai-helper

This is the user-facing, exhaustive catalogue of what `best-engine-ai-helper`
can do and the natural-language phrasings, commands, functions, and situations
that should invoke it.

`best-engine-ai-helper` **chooses** a local LLM or VLM for the machine at hand,
pulls it through Ollama, gates it on quality, and writes the environment file
downstream projects read. It is local-first: detection, selection, the gates
and the env file all run on your machine. It does **not** run inference, serve
a model, fine-tune, or pick a vector index.

## Operations → how to invoke

| Intent | CLI | Library | API |
|--------|-----|---------|-----|
| Hardware snapshot | `detect`, `hardware` | `compute_profile`, `available_memory`, `chip_name` | `GET /api/system` |
| Recommend for a task | `recommend "…"` | `recommend_engines`, `parse_task` | `POST /api/recommend` |
| List / inspect the catalogue | `list`, `show`, `catalog` | `load_catalog`, `rank`, `select` | n/a |
| Estimate a model's footprint | `show` | `estimate_ram`, `model_footprint_gb` | n/a |
| Estimate throughput | `show` | `estimated_tokens_per_second` | n/a |
| Pull the chosen model | `pull` | `ensure` | n/a |
| Run the two quality gates | `validate` | — | n/a |
| Write the env file | `env` | `write_engine` | n/a |
| Read the resolved choice | `resolve` | `model_for`, `text_model`, `vision_model`, `resolved_models`, `load_engine` | n/a |
| Markdown report | `report` | `to_markdown`, `write_report` | n/a |
| What is running now | `activity` | — | `GET /api/activity` |
| Task families / usages | `usages` | `list_usages`, `get_usage`, `resolve_usage`, `list_families` | n/a |
| Refresh the catalogue (online) | `catalog update`, `update` | — | n/a |
| Browser GUI (read-only half) | `gui` | — | `GET /gui` |

There is exactly one command line, `best-engine-ai-helper …`, built with
click — a core dependency here, not an optional extra, so nothing has to be
installed to get it. `-h` and `-V` work everywhere `--help` and `--version`
do.

## Natural-language phrasings that should fire

- **Fit the machine**: "which model can this machine run", "what LLM fits in
  my RAM", "will a 14B fit on this Mac", "how much VRAM do I have for a
  model", "is 8 GB enough", "biggest model I can run locally", "what can my
  M-series handle".
- **Pick for a task**: "which model for summarisation / translation / code /
  OCR", "best local model for French transcripts", "which vision model",
  "recommend an engine for this job", "pick a VLM".
- **Pull and set up**: "pull a local model", "install a model with Ollama",
  "set up Ollama for this project", "download the model weights", "bootstrap
  the local model for this repo".
- **Trust and quality**: "is this model good enough", "validate the model",
  "does it catch a seeded flaw", "Ralph Loop", "Ralph Eyeball Loop", "quality
  gate the model before using it".
- **Throughput and cost**: "how many tokens per second", "will this be fast
  enough", "estimate the footprint", "how much memory will it take",
  "headroom".
- **Resolution in code**: "which model should this package use", "don't
  hardcode the model name", "read the resolved model", "the env file with the
  chosen engine", `model_for`, `text_model`, `vision_model`,
  `resolved_models`.
- **Inspection**: "list the catalogue", "show me this model's entry", "what is
  running right now", "refresh the model catalogue", "what task families does
  it know".
- **Explicit mentions**: `best-engine-ai-helper`,
  `best-engine-ai-helper-mcp`,
  `import best_engine_ai_helper as be`, `recommend_engines`, `compute_profile`,
  "install / run best-engine-ai-helper".

## The suite rule — fire on this too

Any time **suite code needs an LLM or a VLM**, this skill is in scope, even if
the user never names it:

- A `*-helper` package is about to hardcode `"llama3.2:3b"` or read a
  hand-rolled `MODEL` env var → route through `model_for()` instead.
- A new package needs a summarisation / vision step → `md2star` is the
  reference implementation to copy.
- Exception: **`os-helper` must never mention an LLM at all.** It is the
  dependency-free foundation; a model reference there leaks a heavy concern
  into every package in the suite.

## When NOT to use best-engine-ai-helper (SKIP)

- Running a prompt, chatting, or generating text → this package chooses a
  model, it does not call one.
- Serving or hosting a model → that is Ollama's job (or vLLM's).
- Fine-tuning, quantising, or converting weights.
- Choosing an approximate-nearest-neighbour backend or a vector index → use
  `ann-router`, the vector-search sibling.
- Choosing a cloud/API model for its own sake — the `[cloud]` extra adds price
  lookups, but the package's purpose is local models.
- Picking a Python library, a framework, or a package manager.

## See also

- the repo's `README.md`: features, install, quick start.
- the repo's `EXAMPLES.md`: runnable recipes.
- the repo's `GUI.md`: the bilingual browser GUI.
- the repo's `LANDSCAPE.md`: how it compares with picking a model by hand.
- `skills/best-engine-ai-helper/SKILL.md`: the same catalogue, compressed for
  an agent.
