# best-engine-ai-helper CLI reference

One command line, built with click — a core dependency here, not an optional
extra, so nothing has to be installed to get it. Every command below is
spelled `best-engine-ai-helper <command>`; `-h` and `-V` work everywhere
`--help` and `--version` do.

Ollama is required for `pull` and `validate`; **not** for `detect`,
`recommend` or `report`.

## Hardware

```bash
best-engine-ai-helper detect                 # JSON
best-engine-ai-helper hardware show          # the merged chip table
best-engine-ai-helper hardware update        # record this machine's chip
best-engine-ai-helper storage [--backend ollama|vllm]
```

`detect` reports the memory actually usable for a model: the Apple Silicon
unified pool, NVIDIA VRAM, or system RAM, whichever applies. `--live` (on
`recommend` and `report`) adds the current load (CPU percent, available RAM,
running vLLM processes) so the recommendation accounts for what is already
occupying the machine. `storage` plans capacity: what fits on disk, and what
fits in memory.

All raw probing is delegated to `os-helper` — this package does not read
`sysctl` or `nvidia-smi` itself.

## Recommendation

```bash
best-engine-ai-helper recommend [--kind llm|vlm|both] [--application code|math|ocr|vision|chat|generalist] \
    [--headroom F] [--min-tps F] [--live] [--backend ollama|vllm|lightweight]
best-engine-ai-helper report --task "summarise long French meeting transcripts" [--format md|json] [--out STEM]
```

`recommend` ranks the candidates for this hardware (a dry run, nothing is
pulled). A free-text task goes to `report --task`: it is **parsed**
(`parse_task`, with offline language ID), so plain words beat keywords.
Output: the ranked engines that fit, with the reason each was chosen or
rejected.

```bash
best-engine-ai-helper catalog show                  # the merged catalogue, as a table
best-engine-ai-helper catalog update [--ollama] [--arena] [--cloud] [--limit N]
best-engine-ai-helper usages list                   # usage profiles and families
best-engine-ai-helper usages show NAME              # one profile's needs
best-engine-ai-helper usages resolve NAME [--family F1] [--out FILE]
best-engine-ai-helper providers [--json]            # which cloud providers are usable
```

The bundled catalogue is enough for everyday use; `catalog update` is the only
other online call besides `pull`.

## The headroom model

Selection never fills the machine. `MAX_HEADROOM` reserves memory for the OS
and for the context window, so the chosen model has room to actually run
rather than fitting on paper and then swapping.

- `estimate_ram` / `model_footprint_gb` — what a model needs.
- `effective_budget` — what this machine can really give it.
- `estimated_tokens_per_second` — whether the fit will also be usable.

A model that fits exactly is the wrong choice; that is the point of the gap.

## Layer streaming — when nothing good fits

```bash
best-engine-ai-helper lightweight status [--measure] [--json] [--request auto|always|never]
best-engine-ai-helper lightweight plan [--kind llm|vlm|both] [--context K] [--batch B] [--tokens N] [--measure] [--json]
best-engine-ai-helper lightweight compare [--kind llm|vlm] [--tokens N] [--batch B] [--prompt-tokens P] \
    [--application AXIS] [--native-backend ollama|vllm] [--measure] [--json]
best-engine-ai-helper lightweight prepare --model REPO
best-engine-ai-helper recommend --backend lightweight
best-engine-ai-helper resolve --brief llm.brief.yaml --backend lightweight
```

The lightweight runtime lives behind an extra:
`pip install 'best-engine-ai-helper[lightweight]'` (about 2 GB, torch
included). The three read-only commands never import it, so they answer
correctly without it — and `lightweight status` prints `runtime import :
FAILS` with that install command when it is missing.

**The model, in four numbers.** Resident memory is one layer shard — the
checkpoint over its decoder depth, ×1.25 (the embedding layer is the widest
one), ×2 with prefetching on — plus the KV cache of **every** layer, which
streaming does not shrink. Throughput is bounded by the **disk**: one forward
pass reads the whole checkpoint, so one token costs one pass (`tok/s = disk
GB/s ÷ checkpoint GB × 0.85`). Disk *space* is the constraint that usually
refuses a model, but it is the checkpoint's own size and nothing more. And the
comfort floor is 0.01 tok/s — a batch floor, not the 15 tok/s interactive one,
which would reject every candidate.

**Two levers, both worth quoting to a user who says it is too slow.** A batch
of B prompts shares each pass, so B answers arrive in the time of one;
there is no compression flag: the runtime reads the checkpoint at the dtype
it ships in. The prompt itself is nearly free — a 2000-token prompt rides through each layer in
the same pass as a 10-token one, which no other backend can say.

**Activation.** Never automatic unless the conventional backend found nothing
that fits, and then per *kind* (a mixed engine file is the honest outcome).
Manual via `--backend lightweight`, `lightweight: always` in the brief, or
`BEST_ENGINE_LIGHTWEIGHT=always`; `never` disables the whole path.

Relevant library calls: `lightweight_decide`, `lightweight_plan`, `lightweight_rank`,
`lightweight_pick`, `lightweight_footprint_gb`, `lightweight_generation_time`,
`lightweight_seconds_per_pass`, `lightweight_compare`, `streaming_budget_gb`,
`disk_profile`, `lightweight_load`, `lightweight_generate`.

## Text-to-image — the third kind

```bash
best-engine-ai-helper imagine plan [--size auto|512x512|1024x1024|…] [--json]
best-engine-ai-helper imagine generate --prompt TEXT [--out FILE] [--model REPO] \
    [--size WxH] [--steps N] [--seed N] [--negative TEXT]
```

Sized per component, not per model: a diffusion pipeline is text encoders plus a
denoiser plus a VAE taking turns, so all-resident costs their sum while
`diffusers`' component offload costs the largest one. `imagine plan` tries the
first and falls back to the second before rejecting anything, and reports which
it used.

Timed in **seconds per image** = steps x denoiser passes. The step count is a
property of the weights (1-4 distilled, 28 otherwise) and comes from the
catalogue, because running a distilled checkpoint at 28 steps is slower AND
worse. `size: auto` uses the model's native resolution, the one size it is
actually good at.

Library: `imagine_plan`, `imagine_rank`, `imagine_pick`, `image_footprint_gb`,
`seconds_per_image`, `imagine_load`, `imagine_generate`.

## OpenAI-compatible server

```bash
best-engine-ai-helper serve [--host 127.0.0.1] [--port 8000]
```

Serves `/v1/models`, `/v1/chat/completions` (text, vision, streaming,
`response_format`), `/v1/completions`, `/v1/embeddings` and
`/v1/images/generations` on the same app as the GUI, the `/api/*` routes and
`/mcp`. Point any OpenAI SDK at the printed base URL; the only call-site change
from a hosted OpenAI setup is `base_url` plus `model="best"`.

Model names: `best` (a VLM on its own when the request carries images),
`best-llm`, `best-vlm`, `best-embed`, `best-image`, `best:<free-text task>`, or
any literal tag, which passes through untouched. The response reports the model
that actually ran.

Refuses rather than pretends: `n > 1`, `logprobs` and `tools` are 400s;
`http(s)` image URLs need `BEST_OPENAI_FETCH_IMAGE_URLS=1` (fetching a
caller-chosen address is an SSRF primitive); token counts are real where the
backend reports them and flagged as estimates in `system_fingerprint` where it
does not.

## Pull, validate, write

```bash
best-engine-ai-helper pull [--application AXIS] [--min-tps F] [--keep-failed] [--vllm]
best-engine-ai-helper validate
best-engine-ai-helper env
best-engine-ai-helper resolve --brief llm.brief.yaml [--out FILE] [--backend …] [--endpoint URL]
best-engine-ai-helper doctor [--directory .]
```

1. **`pull`** picks the best model for this machine (it takes no model name),
   downloads it through Ollama (online, once) and runs the two quality gates:
   - the **Ralph Loop** — a known flaw is seeded into a short text; does the
     model catch and fix it?
   - the **Ralph Eyeball Loop** — an obvious visual defect is seeded into a
     small image; does the model see it?
   Only a model that passes both is written to
   `~/.best-engine-ai-helper/env.sh`; a failed one is removed unless
   `--keep-failed`.
2. **`validate`** re-runs the gates on the model already configured
   (`BEST_LLM_TEXT` / `BEST_LLM_VISION`), e.g. after a manual `ollama pull`.
3. **`env`** prints that env file, ready to source; it writes nothing and
   exits 1 if `pull` has not written it yet.
4. **`resolve`** turns a project's committed usage brief into a
   machine-specific engine file; `doctor` compares that file with what the
   daemon actually serves.

A pulled model is not a trusted model until the gates pass.

## Reporting and activity

```bash
best-engine-ai-helper report [--task TEXT] [--out STEM] [--format md|json] [--cloud]
best-engine-ai-helper activity [--format table|json] [--what-if]
best-engine-ai-helper gui [--host H] [--port N]
```

`report` renders the hardware snapshot and the recommendation as Markdown
(`--out STEM` writes `STEM.md` and `STEM.json`). `activity` summarises the
local call ledger: calls, cost, by user and by model.

## Output contract

- Machine-readable output: `detect` prints JSON; `report --format json`,
  `activity --format json`, `providers --json`, and `--json` on the
  `lightweight` and `imagine plan` subcommands. `recommend` and
  `catalog show` print tables only.
- `detect`, `recommend` and `report` work without Ollama; `pull` and
  `validate` fail fast with a clear message if it is absent.
- `-v` / `-vv` (before the subcommand) raise the log level; failures exit
  non-zero.
