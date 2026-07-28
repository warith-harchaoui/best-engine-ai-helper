# Changelog

All notable changes to best-engine-ai-helper are documented here.

## [0.1.0] — 2026-07-28

First release. Phase 0a: pure Python, no model download required.

### Added

- Hardware detection (`detect.py`): Apple Silicon unified memory, NVIDIA VRAM via
  nvidia-smi, AMD VRAM via rocm-smi, CPU-only fallback via psutil.
- Model catalog (`catalog.py`, `models.yaml`): 13-entry bundled seed covering
  Qwen 3 VL (4B to 72B), Qwen 3 text (8B to 72B Q8), Qwen 2.5 3B, Gemma 3 12B.
  Cache-merge logic for future `catalog update` output.
- Hardware chip table (`hardware.py`, `hardware.yaml`): Apple Silicon M1 through
  M4 Ultra across all memory tiers; NVIDIA RTX 3060 through H100. Cache-merge logic.
- Selection algorithm (`score.py`): filters by 80% headroom, ranks by benchmark
  score (vision for VLMs, general for LLMs), last-resort smallest-model fallback.
- CLI (`cli.py`): `detect`, `recommend`, `catalog show`, `hardware show` commands
  fully implemented. `pull`, `validate`, `env`, `catalog update`, `hardware update`
  stubbed with Phase 0b notice.
- Test suite: 40+ tests in `tests/` covering all public functions.
