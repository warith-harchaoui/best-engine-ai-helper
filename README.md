# best-engine-ai-helper

Pick and pull the best local large language model (LLM) or vision-language model (VLM) for the hardware in the current machine.

The tool detects available memory (Apple Silicon unified pool, NVIDIA VRAM, or system RAM), consults a bundled model catalog, and selects the highest-scoring model that fits within a configurable safety headroom. After selection, it pulls the model via Ollama, runs two quality gates (the Ralph Loop for prose and the Ralph Eyeball Loop for vision), and writes an environment file that downstream projects source to find the chosen model.

A minimal browser GUI (`best-engine-ai-helper gui`) covers the read-only half of this — hardware snapshot and task → engine recommendation — without the CLI. See [GUI.md](GUI.md).

## Requirements

- Python 3.10 or later
- [Ollama](https://ollama.com) (needed for `pull`, `validate`, `env`; not for `detect`, `recommend`, or `report`)
- psutil, PyYAML, click, requests (installed automatically)
- Optional: `fastapi` + `uvicorn` for the browser GUI (`pip install 'best-engine-ai-helper[api]'`)

## Install

```sh
pip install best-engine-ai-helper
```

Or from source:

```sh
git clone https://github.com/warith-harchaoui/best-engine-ai-helper
cd best-engine-ai-helper
pip install -e .
```

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

# Launch the browser GUI (requires the [api] extra)
best-engine-ai-helper gui
```

See [EXAMPLES.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXAMPLES.md) for runnable recipes with expected output, and [GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md) for the browser GUI.

## GUI

`best-engine-ai-helper gui` serves a single-page browser GUI (FastAPI +
vanilla JS, no build step) at `http://127.0.0.1:8000/gui`: the same hardware
snapshot as `detect`, and a task-description box that returns the same
recommendation as `report` — no terminal needed.

![Recommendation results](assets/screenshots/gui-recommendation.png)

See [GUI.md](GUI.md) for the full write-up, the JSON API it's built on, and
how the favicon / touch-icon set is generated from `assets/logo.png`.

## How selection works

Selection weighs three factors, each made explicit in the `report` output so the
recommendation is reproducible and can be argued with.

### 1. Memory fit (will it run on the accelerator?)

Available memory comes from the highest-priority probe that succeeds: Apple
Silicon unified memory (`system_profiler`), NVIDIA VRAM (`nvidia-smi`), AMD VRAM
(`rocm-smi`), else half of system RAM as a conservative CPU-only estimate.

The usable budget is **not** the whole pool. On Apple Silicon, Metal caps GPU
allocations at about **66%** of unified memory at or below 36 GB and about
**75%** above it (`recommendedMaxWorkingSetSize`); past that, work spills to the
CPU and slows sharply. An extra safety `headroom` (default **0.85**) is applied
on top, reserving room for the OS, your own application, and KV-cache growth as
context fills. A catalog entry's `ram_gb` is already a peak-inference estimate
(weights plus a moderate KV cache; roughly weights ÷ 0.7, since weights are only
about 70% of runtime memory and can approach 2× at long context). A model fits
when that `ram_gb` is at most the budget.

### 2. Task fit (is it good at the job?)

A task — even a vague phrase like *"retail descriptions and image-quality
checks"* — maps to a benchmark axis (`generalist`, `code`, `math`, `ocr`,
`vision`) and to the model kinds it needs (text ⇒ LLM, anything visual ⇒ VLM).
Among fitting models, the highest benchmark on that axis wins.

### 3. Throughput (how fast will it generate?)

Token generation is **memory-bandwidth bound**: each token reads the active
model from memory once, so the ceiling is `bandwidth ÷ model-size`, derated to
about 65% for KV-cache reads and overhead. `report` estimates tokens/s per
candidate from the chip's memory bandwidth, and offers a lighter, faster
alternative when one is nearly as strong. Bigger is not automatically better: a
72B model that technically fits may run at a few tokens/s, while an 8–14B model
leaves headroom and runs several times faster.

When nothing fits, the tool falls back to the smallest model and says so.

**Sources.** Apple Metal working-set cap (Apple developer docs / apple-specs);
inference-memory breakdown weights + KV (15–20%) + overhead (5–10%) (local-LLM
sizing guides); bandwidth-bound decode `tok/s ≈ bandwidth ÷ active-bytes × 0.5–0.8`
(llama.cpp / MLX community benchmarks). The exact ratios live as documented
constants in `score.py`.

## Model catalog

The bundled seed catalog (`models.yaml`) covers 13 models from the Qwen 3, Qwen 2.5, and Gemma 3 families, from 3B to 72B parameters, across Q4_K_M and Q8_0 quantizations. The catalog tracks on-disk size, estimated peak RAM, and benchmark scores from the Open LLM Leaderboard v2 and the OpenVLM Leaderboard.

`catalog update` (Phase 0b) refreshes the cache from external sources: the Ollama registry API, the HuggingFace Hub API, the Open LLM Leaderboard v2 dataset, the OpenVLM Leaderboard dataset, and the [ApXML LLM directory](https://apxml.com/models?modelType=open_weight) (open-weight models with VRAM/compute needs and coding benchmarks, consulted regularly). The bundled seed is never modified by the refresh.

## Hardware table

`hardware.yaml` lists known GPU and Apple Silicon chip configurations with their usable memory (physical pool minus OS and driver overhead). `hardware update` (Phase 0b) refreshes NVIDIA entries from TechPowerUp.

## Downstream integration

After `best-engine-ai-helper pull` completes, it writes `~/.best-engine-ai-helper/env.sh`:

```sh
export BEST_LLM_TEXT=qwen3-vl:72b
export BEST_LLM_VISION=qwen3-vl:72b
export BEST_LLM_BACKEND=ollama
export BEST_LLM_BASE_URL=http://localhost:11434
```

Projects that consume the selected model source this file or read the companion `config.json`.

## License

[BSD-3-Clause](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LICENSE). Copyright 2026 Warith Harchaoui.
