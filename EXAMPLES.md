# EXAMPLES.md

One runnable recipe per public CLI command. All examples assume
`best-engine-ai-helper` is installed and Ollama is running locally on port
11434 (only required for Phase 0b commands).

---

## detect

Print the detected hardware as JSON.

```sh
best-engine-ai-helper detect
```

Expected output on an Apple M2 Max 96 GB machine:

```json
{
  "platform": "darwin",
  "chip_vendor": "apple",
  "memory": {
    "unified_gb": 96.0,
    "vram_gb": null,
    "ram_gb": 96.0
  }
}
```

The `unified_gb` field is null on non-Apple machines; `vram_gb` is populated
on Linux/Windows machines with a discrete NVIDIA or AMD GPU.

---

## recommend

Print ranked model candidates for the current hardware without downloading anything.

```sh
best-engine-ai-helper recommend
```

On an M2 Max 96 GB machine the output looks like:

```
=== LLM candidates ===
id                 ram_gb  score  fits  notes
-----------------  ------  -----  ----  ----------------------------------------
qwen3:72b-q8_0    78      89     yes   72B at Q8; needs 96 GB unified.
qwen3:72b-q4_k_m  48      87     yes   Top text-only; needs 64 GB unified or VRA
...

=== VLM candidates ===
id                 ram_gb  score  fits  notes
-----------------  ------  -----  ----  ----------------------------------------
qwen3-vl:72b       52      91     yes   Best local VLM; needs 64 GB unified or VR
...
```

To see only VLM candidates:

```sh
best-engine-ai-helper recommend --kind vlm
```

To use a tighter safety margin (50% instead of 80%):

```sh
best-engine-ai-helper recommend --headroom 0.5
```

---

## catalog show

Print the full merged model catalog (bundled seed plus any local cache updates).

```sh
best-engine-ai-helper catalog show
```

Each row shows the Ollama tag, kind, parameter count, quantization, on-disk
size, estimated peak RAM, and benchmark scores.

---

## hardware show

Print the full merged hardware chip table.

```sh
best-engine-ai-helper hardware show
```

Each row shows the chip name, vendor, total memory, usable memory (after OS
overhead), and the data source.

---

## Python library usage

All public functions are importable without invoking Click:

```python
from best_engine_ai_helper.detect import available_memory, chip_vendor
from best_engine_ai_helper.catalog import load_catalog
from best_engine_ai_helper.score import select

hw = available_memory()
catalog = load_catalog()

best_vlm = select(hw, catalog, kind="vlm")
print(best_vlm["id"])        # e.g. 'qwen3-vl:72b' on a 96 GB machine
print(best_vlm["ram_gb"])    # e.g. 52.0

best_llm = select(hw, catalog, kind="llm")
print(best_llm["id"])        # e.g. 'qwen3:72b-q8_0' on a 96 GB machine
```

---

## Phase 0b commands (not yet available)

The following commands are planned for Phase 0b:

```sh
best-engine-ai-helper pull            # pull the best model; run Ralph gates
best-engine-ai-helper validate        # re-run Ralph gates on the current model
best-engine-ai-helper env             # print env block for ~/.zshrc
best-engine-ai-helper catalog update  # refresh catalog from 4 external sources
best-engine-ai-helper hardware update # refresh hardware table from TechPowerUp
```
