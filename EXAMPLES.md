# EXAMPLES.md

One runnable recipe per public CLI command. All examples assume
`best-engine-ai-helper` is installed and Ollama is running locally on port
11434 (only required for the `pull`, `validate`, and `env` commands).

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
=== VLM candidates ===
id            ram_gb  score  fits  notes
------------  ------  -----  ----  ----------------------------------------
gemma3:12b    9.2     78     yes   Google Gemma 3 12B multimodal. Reliable
qwen3-vl:72b  52      91     yes   Highest raw vision benchmarks, but Qwen3
qwen3-vl:32b  24      87     yes   Large VLM; needs 32 GB VRAM. Qwen3-VL: u
...
```

Note the ordering: `gemma3:12b` (score 78) sits above `qwen3-vl:72b` (score 91)
because the Qwen3-VL family cannot honour Ollama structured output, so it is
never chosen for the suite's schema-driven tasks however high its raw score.
The `fits` column marks whether a model's peak-inference RAM sits inside the
budget: on this machine `qwen3:72b-q8_0` (78 GB) shows `NO` against the 61.2 GB
budget, while everything smaller shows `yes`.

To see only VLM candidates:

```sh
best-engine-ai-helper recommend --kind vlm
```

To use a tighter safety margin (0.5 instead of the default 0.85):

```sh
best-engine-ai-helper recommend --headroom 0.5
```

---

## report

Recommend the best engine(s) for a task and write both a Markdown report and a
JSON file. The task can be a vague phrase; vision words add a VLM.

```sh
best-engine-ai-helper report \
    --task "retail product descriptions and image-quality checks" \
    --out engine
# wrote engine.md and engine.json
```

The report states, for each needed kind, the chosen model with its memory fit
and estimated tokens/s, a lighter/faster alternative when one is close, the full
ranked candidate table, and the sourced rationale. Print JSON instead of
Markdown with `--format json` (omit `--out` to only print).

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
print(best_vlm["id"])        # e.g. 'gemma3:12b' on a 96 GB machine
print(best_vlm["ram_gb"])    # e.g. 9.2

best_llm = select(hw, catalog, kind="llm")
print(best_llm["id"])        # e.g. 'qwen3:72b-q4_k_m' on a 96 GB machine
```

`select` and the `recommend` / `report` output agree on the winner: both put
structured-output-capable models first, then rank by benchmark score within the
memory budget.

The full recommendation algorithm (memory + compute + task) is one call:

```python
from best_engine_ai_helper import recommend_engines, to_markdown
from best_engine_ai_helper.detect import available_memory, compute_profile
from best_engine_ai_helper.catalog import load_catalog

report = recommend_engines(
    available_memory(),
    load_catalog(),
    task="product descriptions and image-quality checks",
    compute=compute_profile(),
)
print(report["recommendations"]["vlm"]["chosen"]["id"])   # best VLM
print(to_markdown(report))                                # human-readable report
```

---

## gui

Launch the browser GUI (hardware snapshot + task → best engine). Requires the
`[api]` extra:

```sh
pip install 'best-engine-ai-helper[api]'
best-engine-ai-helper gui
# Serving GUI at http://127.0.0.1:8000/gui
```

Open `http://127.0.0.1:8000/gui`: the hardware panel loads on page load, and
typing a task and clicking "Recommander" calls the same `recommend()` used by
`report`. The two JSON endpoints it's built on are usable directly too:

```sh
curl -s http://127.0.0.1:8000/api/system | python3 -m json.tool

curl -s -X POST http://127.0.0.1:8000/api/recommend \
     -H 'Content-Type: application/json' \
     -d '{"task": "product descriptions and image-quality checks"}' \
  | python3 -m json.tool
```

See [GUI.md](GUI.md) for screenshots and the full write-up.

---

## pull, validate, env

```sh
best-engine-ai-helper pull            # pull the best model; run Ralph gates
best-engine-ai-helper validate        # re-run Ralph gates on the current model
best-engine-ai-helper env             # print env block for ~/.zshrc
```

Refresh the caches (both merge into `~/.best-engine-ai-helper/`, leaving the
bundled seed untouched):

```sh
best-engine-ai-helper catalog update            # fetch open-weight models from ApXML
best-engine-ai-helper catalog update --limit 20 # quick partial refresh / smoke test
best-engine-ai-helper hardware update           # record this machine's chip + memory
```
