# best-engine-ai-helper CLI reference

**Naming is inverted here** relative to the rest of the suite: click is the
primary CLI because click is already a core dependency, and the argparse twin
mirrors it 1:1.

| CLI | Command |
|---|---|
| click (primary) | `best-engine-ai-helper …` |
| argparse (twin) | `best-engine-ai-helper-argparse …` |

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
