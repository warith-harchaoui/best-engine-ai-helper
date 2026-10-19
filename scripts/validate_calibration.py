"""Test whether calibrating on one model really improves the estimate for others.

`throughput.calibration_factor` rests on a claim: the gap between the
bandwidth estimate and reality belongs to the *machine* more than to the
*model*, so measuring one model should sharpen the prediction for every other
one — including models that were never pulled. The mechanism is unit-tested.
The claim is not something a unit test can settle, because it is about the
world rather than about the code.

So this measures several models and runs the honest version of the test:
calibrate on A, predict B, and ask whether that beats the raw bandwidth model.
Leave-one-out, in every direction, with the failure printed as plainly as the
success. A script that can only confirm what it set out to show is not a test.

What it found on an Apple M2 Max, 2026-10-19
--------------------------------------------
Measured ratios of actual to predicted throughput, over three runs::

    gemma3:12b     0.537
    qwen3-vl:4b    0.545   0.611   0.573
    qwen2.5:3b     0.505   0.458

Two conclusions, and both matter.

The claim holds. Correcting by a ratio measured on a *different* model beat the
raw estimate in **every direction tried across the three runs — six out of
six** — cutting the error from 64-118% down to 17-25%. A correction learned
from one model genuinely transfers to another.

But it does not transfer perfectly. The ratios span roughly 0.46 to 0.61
across models, and the *same* model landed 12% apart on consecutive runs. So
calibration takes an estimate from "wrong by a factor of two" to "wrong by
about a fifth". That is a large improvement and it is not precision — which is
exactly why :func:`throughput.calibration_factor` takes the **median across
models** rather than trusting a single sample, and why the Ralph gate's
measurement still beats a calibrated estimate whenever one exists.

Usage::

    python scripts/validate_calibration.py qwen3-vl:4b qwen2.5:3b

Needs a running Ollama daemon with the named models pulled, and generates
tokens on each. Writes to a temporary store, never the real one.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

#: Long enough to generate the sample, deliberately not unbounded: a stalled
#: daemon should fail this script rather than hang it.
_DEFAULT_TIMEOUT_S = "900"

#: Asks for enough tokens that the figure is a decode rate rather than mostly
#: the first-token latency the decode clock is meant to exclude.
_PROMPT = "Count from 1 to 80, one number per line, nothing else."


def main(tags: list[str]) -> int:
    """Measure each tag, then test transfer in every direction."""
    os.environ.setdefault("SPREZZATURE_LLM_BACKEND", "ollama")
    os.environ.setdefault("SPREZZATURE_LLM_TIMEOUT", _DEFAULT_TIMEOUT_S)

    from best_engine_ai_helper import catalog, detect, llm, score, throughput

    if len(tags) < 2:
        print("Give at least two model tags: transfer needs something to transfer to.")
        return 2

    store = Path(tempfile.mkdtemp()) / "measurements.yaml"
    throughput._STORE_PATH = store  # never touch the user's real store

    bandwidth = detect.compute_profile().get("bandwidth_gbs")
    entries = {str(e.get("id")): e for e in catalog.load_catalog()}

    rows: list[dict[str, Any]] = []
    print(f"machine: {throughput.machine_id()}   bandwidth: {bandwidth} GB/s\n")
    for tag in tags:
        entry = entries.get(tag)
        if entry is None:
            print(f"  {tag}: not in the catalog, skipped")
            continue
        raw = score.estimated_tokens_per_second(entry, bandwidth, calibrated=False)
        if not raw:
            print(f"  {tag}: not estimable on this hardware, skipped")
            continue

        meter = throughput.Meter()
        meter.wrap(llm.chat)(_PROMPT, model=tag, safety=False)
        measured = meter.measurement()
        if measured is None:
            print(f"  {tag}: nothing measurable")
            continue

        rows.append({"tag": tag, "raw": raw, "measured": measured["tokens_per_second"]})
        print(
            f"  {tag:<16} estimate {raw:>6.1f}   measured "
            f"{measured['tokens_per_second']:>6.1f}   "
            f"ratio {measured['tokens_per_second'] / raw:.3f}   "
            f"({measured['tokens']} tok, {measured['basis']})"
        )

    if len(rows) < 2:
        print(f"\nNeed two measured models to test transfer; got {len(rows)}.")
        return 1

    print("\nLeave-one-out — calibrate on A, predict B:")
    print(f"  {'calibrated on':<16}{'predicts':<16}{'raw err':>9}{'calib err':>11}{'better?':>9}")
    helped = 0
    pairs = 0
    for a in rows:
        for b in rows:
            if a is b:
                continue
            pairs += 1
            factor = a["measured"] / a["raw"]
            predicted = b["raw"] * factor
            raw_err = abs(b["raw"] - b["measured"]) / b["measured"] * 100
            cal_err = abs(predicted - b["measured"]) / b["measured"] * 100
            better = cal_err < raw_err
            helped += better
            print(
                f"  {a['tag']:<16}{b['tag']:<16}{raw_err:>8.1f}%"
                f"{cal_err:>10.1f}%{'  yes' if better else '   NO':>9}"
            )

    print(f"\nCalibration helped in {helped}/{pairs} directions.")
    ratios = [r["measured"] / r["raw"] for r in rows]
    print(
        f"Ratios span {min(ratios):.3f} to {max(ratios):.3f} across {len(rows)} models — "
        "which is why the factor is a median over several, not one sample."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
