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
best-engine-ai-helper airllm status [--measure] [--json] [--request auto|always|never]
best-engine-ai-helper airllm plan [--kind llm|vlm|both] [--compression 4bit|8bit] [--context K] [--batch B] [--tokens N]
best-engine-ai-helper airllm compare [--tokens N] [--batch B] [--prompt-tokens P] [--application AXIS]
best-engine-ai-helper airllm prepare --model REPO [--compression 4bit] [--shards-path DIR] [--delete-original]
best-engine-ai-helper recommend --backend airllm
best-engine-ai-helper resolve --brief llm.brief.yaml --backend airllm
```

Needs `pip install 'best-engine-ai-helper[airllm]'` to *run* a model; the three
read-only commands are pure arithmetic and work without it, which is how a user
finds out what installing it would buy.

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
Manual via `--backend airllm`, `airllm: always` in the brief, or
`BEST_ENGINE_AIRLLM=always`; `never` disables the whole path.

Relevant library calls: `airllm_decide`, `airllm_plan`, `airllm_rank`,
`airllm_pick`, `airllm_footprint_gb`, `airllm_generation_time`,
`airllm_seconds_per_pass`, `airllm_compare`, `streaming_budget_gb`,
`disk_profile`, `airllm_load`, `airllm_generate`.

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
