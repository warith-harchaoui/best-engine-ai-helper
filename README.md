# best-engine-ai-helper

Pick and pull the best local large language model (LLM) or vision-language model (VLM) for the hardware in the current machine.

The tool detects available memory (Apple Silicon unified pool, NVIDIA VRAM, or system RAM), consults a bundled model catalog, and selects the highest-scoring model that fits within a configurable safety headroom. After selection, it pulls the model via Ollama, runs two quality gates (the Ralph Loop for prose and the Ralph Eyeball Loop for vision), and writes an environment file that downstream projects source to find the chosen model.

Phase 0a (this release) covers detection, catalog, scoring, and the CLI skeleton. Phase 0b adds the pull, validate, and env commands.

## Requirements

- Python 3.10 or later
- [Ollama](https://ollama.com) (Phase 0b only; not needed for `detect` and `recommend`)
- psutil, PyYAML, click, requests (installed automatically)

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

# Browse the full catalog
best-engine-ai-helper catalog show

# Browse the hardware chip table
best-engine-ai-helper hardware show
```

See [EXAMPLES.md](EXAMPLES.md) for runnable recipes with expected output.

## How selection works

Available memory is determined by the highest-priority probe that succeeds:

1. Apple Silicon unified memory (`system_profiler SPHardwareDataType`)
2. NVIDIA VRAM summed across all GPUs (`nvidia-smi`)
3. AMD VRAM (`rocm-smi`)
4. Half of system RAM as a conservative CPU-only estimate

A model fits when its estimated peak inference RAM is at most 80% of the available pool (the headroom leaves room for OS overhead and KV cache spikes). Among all fitting models, the highest benchmark score wins: vision score for VLM selection, general score for LLM selection.

When nothing fits, the tool selects the smallest model in the catalog and prints a warning; the user can then decide to free memory or accept the constraint.

## Model catalog

The bundled seed catalog (`models.yaml`) covers 13 models from the Qwen 3, Qwen 2.5, and Gemma 3 families, from 3B to 72B parameters, across Q4_K_M and Q8_0 quantizations. The catalog tracks on-disk size, estimated peak RAM, and benchmark scores from the Open LLM Leaderboard v2 and the OpenVLM Leaderboard.

`catalog update` (Phase 0b) refreshes the cache from four external sources: the Ollama registry API, the HuggingFace Hub API, the Open LLM Leaderboard v2 dataset, and the OpenVLM Leaderboard dataset. The bundled seed is never modified by the refresh.

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

MIT. Copyright 2026 Warith Harchaoui.
