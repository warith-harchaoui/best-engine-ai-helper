# best-engine-ai-helper CLI reference

One command line, built with click — a core dependency here, not an optional
extra, so nothing has to be installed to get it. Every command below is
spelled `best-engine-ai-helper <command>`; `-h` and `-V` work everywhere
`--help` and `--version` do.

Ollama is required for `pull`, `validate` and `env`; **not** for `detect`,
`recommend` or `report`.

## Hardware

```bash
best-engine-ai-helper detect [--live] [--json]
best-engine-ai-helper hardware
```

`detect` reports the memory actually usable for a model: the Apple Silicon
unified pool, NVIDIA VRAM, or system RAM, whichever applies. `--live` adds the
current load (CPU percent, available RAM, running vLLM processes) so the
recommendation accounts for what is already occupying the machine.

All raw probing is delegated to `os-helper` — this package does not read
`sysctl` or `nvidia-smi` itself.

## Recommendation

```bash
best-engine-ai-helper recommend "summarise long French meeting transcripts" [--json]
```

The task description is **parsed** (`parse_task`, with offline language ID),
so plain words beat keywords. Output: the ranked engines that fit, with the
reason each was chosen or rejected.

```bash
best-engine-ai-helper list                  # the catalogue
best-engine-ai-helper show MODEL            # one entry: footprint, scores, tags
best-engine-ai-helper usages                # known task families and usages
best-engine-ai-helper catalog update        # refresh from the network (optional)
```

The bundled catalogue is enough for everyday use; `update` is the only other
online call besides `pull`.

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
best-engine-ai-helper lightweight plan [--kind llm|vlm|both] [--compression 4bit|8bit] [--context K] [--batch B] [--tokens N]
best-engine-ai-helper lightweight compare [--tokens N] [--batch B] [--prompt-tokens P] [--application AXIS]
best-engine-ai-helper lightweight prepare --model REPO [--compression 4bit] [--shards-path DIR] [--delete-original]
best-engine-ai-helper recommend --backend lightweight
best-engine-ai-helper resolve --brief llm.brief.yaml --backend lightweight
```

The lightweight runtime is a core dependency, so nothing has to be installed first
(it is most of why this package's install is ~2 GB). The three read-only
commands never import it, so they answer correctly even where it would fail to
load — and `lightweight status` reports that failure as an incomplete install, since
at that point it is one.

**The model, in four numbers.** Resident memory is one layer shard — the
checkpoint over its decoder depth, ×1.25 (the embedding shard is the biggest
one), ×2 with prefetch on — plus the KV cache of **every** layer, which
streaming does not shrink. Throughput is bounded by the **disk**: one forward
pass reads the whole checkpoint, so one token costs one pass (`tok/s = disk
GB/s ÷ checkpoint GB × 0.85`). Disk *space* is the constraint that usually
refuses a model: the split needs ~2× the checkpoint free at once. And the
comfort floor is 0.01 tok/s — a batch floor, not the 15 tok/s interactive one,
which would reject every candidate.

**Two levers, both worth quoting to a user who says it is too slow.** A batch
of B prompts shares each pass, so B answers arrive in the time of one;
4-bit compression divides the bytes read, worth ~3× net of dequantisation. The
prompt itself is nearly free — a 2000-token prompt rides through each layer in
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
best-engine-ai-helper pull [MODEL]
best-engine-ai-helper validate
best-engine-ai-helper env
best-engine-ai-helper resolve
```

The order matters:

1. **`pull`** downloads the weights through Ollama (online, once).
2. **`validate`** runs the two quality gates:
   - the **Ralph Loop** — a known flaw is seeded into a short text; does the
     model catch and fix it?
   - the **Ralph Eyeball Loop** — an obvious visual defect is seeded into a
     small image; does the model see it?
3. **`env`** writes the environment file **only for a model that passed
   both**. That file is what downstream projects read.
4. **`resolve`** prints what the current environment resolves to.

A pulled model is not a trusted model until step 2 passes.

## Reporting and activity

```bash
best-engine-ai-helper report [-o report.md]
best-engine-ai-helper activity
best-engine-ai-helper gui [--port N]        # browser, read-only half
```

`report` renders the hardware snapshot and the recommendation as Markdown.
`activity` shows what is running right now.

## Output contract

- Every reporting command takes `--json`; prefer it when parsing.
- `detect` and `recommend` work without Ollama; the others fail fast with a
  clear message if Ollama is absent.
- Failures are logged through `os_helper` and exit non-zero.
