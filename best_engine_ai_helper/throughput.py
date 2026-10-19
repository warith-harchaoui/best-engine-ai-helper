"""
throughput — measure decode speed from work the Ralph gates already do.

This package ranks models partly on how fast they decode, and until now that
figure was always *estimated*: memory bandwidth times a community constant.
For a project whose argument is that you should measure rather than assume,
that was the one place it assumed. This module closes it.

The measurement costs no extra inference. ``pull`` already pulls a candidate
and puts it through two Ralph gates, which means the tokens have already been
generated and the only thing missing was a stopwatch. :class:`Meter` wraps the
chat callable the gates are handed, counts what passes through, and leaves the
gates themselves untouched — they do not need to know they are being timed.

Two clocks, and the difference matters
--------------------------------------
Ollama reports ``eval_duration``: the decode phase alone, as timed by the
daemon. Wall-clock time around the same call also contains prompt processing,
HTTP, and any queueing behind another request. Dividing tokens by wall time
therefore *understates* decode speed, sometimes by a lot on a short reply, and
understating is exactly what turns a throughput floor into a gate that rejects
models which would have run fine.

So a measurement records which clock produced it. ``basis="eval_duration"`` is
trustworthy enough to disqualify a model; ``basis="wall_clock"`` is a hint and
is labelled as one. A caller that refuses to act on a hint can check.

Why the figure is stored per machine, and why the best sample wins
-----------------------------------------------------------------
Tokens per second is a property of a model *and* the machine under it, so a
measurement is keyed by both. Measuring on a new machine adds a row, and
nothing is ever averaged across hardware that has nothing in common.

Re-measuring the same pair keeps the **fastest** sample rather than the most
recent. This is not optimism, it is what the figure means: the quantity being
calibrated is a memory-bandwidth *ceiling*, and contention can only push an
observation below the hardware's real capability, never above it. Measured
during development, the same model on the same machine gave 15.2 tok/s idle and
8.7 tok/s with three test suites running — so taking the latest sample would let
whatever happened to be running at the time poison every estimate on the
machine. ``record(..., replace=True)`` overrules this for the case where the
hardware genuinely did slow down.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import functools
import os
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import os_helper as osh
import yaml

#: User-writable runtime directory, shared with the catalog cache.
_USER_DIR = Path.home() / ".best-engine-ai-helper"

#: Where measurements accumulate.
_STORE_PATH = _USER_DIR / "measurements.yaml"

#: Below this many sampled output tokens a throughput figure is noise rather
#: than a measurement. A handful of tokens is dominated by the first-token
#: latency the decode clock is supposed to exclude, and a model should never be
#: disqualified on that. Deliberately low: the prose gate's fixtures are short
#: rewrites, so demanding hundreds of tokens would mean never measuring at all.
MIN_TOKENS_FOR_CONFIDENCE = 40


def machine_id() -> str:
    """
    Name the machine a measurement belongs to.

    The CPU model is the coarsest label that still separates hardware whose
    decode speed has nothing in common ("Apple M2 Max" vs "Apple M1"), while
    staying stable across reboots and OS updates — unlike a hostname, which a
    user can change, or a MAC address, which has no business in a file like
    this.

    Returns
    -------
    str
        A short hardware label, or ``"unknown"`` if it cannot be determined.
    """
    try:
        return str(osh.cpu_model() or "unknown")
    except Exception:  # noqa: BLE001 — a label is never worth a crash
        return "unknown"


class Meter:
    """
    Count tokens and time for every chat call that passes through it.

    Wrap a chat callable with :meth:`wrap` and hand the wrapper to whatever
    already generates tokens — the Ralph gates, in this package's case. The
    meter accumulates across every call, so a gate that makes six requests
    yields one measurement over all six rather than six noisy ones.

    Attributes
    ----------
    tokens : int
        Output tokens seen so far, as reported by the backend.
    gen_ms : float
        Decode-only milliseconds, summed. Zero when no backend reported any.
    wall_ms : float
        Wall-clock milliseconds, summed. Always populated.
    calls : int
        Calls that yielded a usable output-token count — not calls made. A
        request that raised, or one whose backend reports no token counts,
        contributes nothing here, because neither produced anything to divide
        by. So ``calls`` is the size of the sample, which is what a reader of
        a measurement wants to know.

    Examples
    --------
    A callable that reports no usage cannot be measured, and the meter says so
    rather than counting the call and inventing a rate for it:

    >>> def fake_chat(prompt, **kw):
    ...     return "ok"
    >>> meter = Meter()
    >>> meter.wrap(fake_chat)("hello")      # the reply is passed straight through
    'ok'
    >>> meter.calls                         # ...but nothing was measurable
    0
    >>> meter.measurement() is None
    True
    """

    def __init__(self) -> None:
        self.tokens = 0
        self.gen_ms = 0.0
        self.wall_ms = 0.0
        self.calls = 0

    def wrap(self, chat: Callable[..., Any]) -> Callable[..., Any]:
        """
        Return `chat` with metering attached, same signature and return value.

        The wrapper is transparent: it forwards every argument, returns the
        callee's result untouched, and lets exceptions through. Metering must
        never change what the gates see, or the gate result stops meaning what
        it meant before.

        Parameters
        ----------
        chat : callable
            A ``llm.chat``-compatible callable.

        Returns
        -------
        callable
            The metered wrapper.
        """
        from . import llm

        @functools.wraps(chat)
        def _metered(*args: Any, **kwargs: Any) -> Any:
            # Observe this one call's usage without disturbing any observer the
            # user already registered: append, read, remove.
            seen: list[dict[str, Any]] = []
            sink = seen.append
            llm.add_observer(sink)
            try:
                with osh.wall_timer() as timer:
                    result = chat(*args, **kwargs)
            finally:
                llm.remove_observer(sink)

            for event in seen:
                if not event.get("ok"):
                    continue
                out = event.get("out_tokens")
                if not isinstance(out, (int, float)) or out <= 0:
                    # A backend that does not report token counts cannot be
                    # measured here. Counting characters instead would invent a
                    # tokeniser, and a wrong divisor is worse than no figure.
                    continue
                self.tokens += int(out)
                self.calls += 1
                gen = event.get("gen_ms")
                if isinstance(gen, (int, float)) and gen > 0:
                    self.gen_ms += float(gen)
                else:
                    self.wall_ms += float(timer.get("milliseconds") or 0.0)

            return result

        return _metered

    def measurement(self) -> dict[str, Any] | None:
        """
        Summarise what was metered, or ``None`` when there is nothing to say.

        Returns ``None`` rather than a zero or a guess in every case where a
        number would be made up: no calls, no token counts, no elapsed time, or
        too few tokens to be more than first-token latency. A caller can then
        treat "unmeasured" and "measured slow" as the different things they are.

        Returns
        -------
        dict or None
            ``{"tokens_per_second", "basis", "tokens", "calls",
            "measured_at", "measured_on"}``.
        """
        if self.calls == 0 or self.tokens <= 0:
            return None

        # Prefer the daemon's decode clock; fall back to the wall clock only
        # when no call reported one, and say which was used either way.
        if self.gen_ms > 0:
            elapsed_ms, basis = self.gen_ms, "eval_duration"
        elif self.wall_ms > 0:
            elapsed_ms, basis = self.wall_ms, "wall_clock"
        else:
            return None

        if self.tokens < MIN_TOKENS_FOR_CONFIDENCE:
            osh.info(
                f"Throughput sample of {self.tokens} token(s) is below the "
                f"{MIN_TOKENS_FOR_CONFIDENCE}-token confidence floor; not reporting it."
            )
            return None

        return {
            "tokens_per_second": round(self.tokens / (elapsed_ms / 1000.0), 1),
            "basis": basis,
            "tokens": self.tokens,
            "calls": self.calls,
            "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "measured_on": machine_id(),
        }


def load_measurements(store_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """
    Read the measurement store, keyed ``"<model>@<machine>"``.

    A missing or unreadable store is an empty dict, not an error: no
    measurement yet is the normal state on a fresh machine, and every caller
    here has an estimate to fall back on.

    Parameters
    ----------
    store_path : Path or None
        Override the default location; for tests.

    Returns
    -------
    dict
        Mapping of key to measurement dict.
    """
    path = store_path if store_path is not None else _STORE_PATH
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — a corrupt cache is not fatal
        osh.warning(f"Could not read throughput store, ignoring it:\n\t{path}\n\t{exc}")
        return {}
    if not isinstance(data, dict):
        osh.warning(f"Throughput store is not a mapping, ignoring it:\n\t{path}")
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def record(
    model: str,
    measurement: dict[str, Any],
    store_path: Path | None = None,
    estimated_tps: float | None = None,
    replace: bool = False,
) -> Path:
    """
    Persist one measurement, keeping the best sample for the (model, machine) pair.

    Parameters
    ----------
    model : str
        The model tag that was measured.
    measurement : dict
        As returned by :meth:`Meter.measurement`.
    store_path : Path or None
        Override the default location; for tests.
    estimated_tps : float or None
        What the bandwidth model predicted for this model on this machine.
        Stored next to the measurement so :func:`calibration_factor` can derive
        the ratio later without having to re-enter the estimator — which is
        also what keeps this module from importing :mod:`score`, the module
        that imports it.
    replace : bool
        Overwrite a faster stored sample with this one. Off by default, because
        a slower sample almost always means the machine was busy rather than
        that the model slowed down. Pass True when the hardware really did
        change and the old ceiling is no longer reachable.

    Returns
    -------
    Path
        The file written.
    """
    path = store_path if store_path is not None else _STORE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    row: dict[str, Any] = {"model": model, **measurement}
    if estimated_tps and estimated_tps > 0:
        row["estimated_tps"] = round(float(estimated_tps), 1)
        measured = measurement.get("tokens_per_second")
        if isinstance(measured, (int, float)) and measured > 0:
            row["calibration_ratio"] = round(float(measured) / float(estimated_tps), 3)

    store = load_measurements(path)
    key = f"{model}@{measurement.get('measured_on', machine_id())}"
    previous = store.get(key)

    # Keep the BEST sample for a pair, not the most recent one.
    #
    # This was learned the hard way. The same model on the same machine
    # measured 15.2 tok/s on an idle box and 8.7 tok/s while three test suites
    # were running -- a factor of 1.7 apart, and the slow one yielded a
    # calibration factor of 0.31 against the idle run's 0.54. Taking the latest
    # sample therefore lets whatever happened to be running at the time poison
    # every estimate on the machine.
    #
    # The maximum is the principled choice rather than merely the optimistic
    # one: the figure being calibrated is a memory-bandwidth *ceiling*, and
    # contention can only ever push an observation below the hardware's real
    # capability, never above it. So the fastest observation is the closest to
    # what is being predicted. `samples` records how much evidence stands
    # behind it, and `replace` exists for the case where the hardware genuinely
    # did get slower (thermal throttling, a different OS) and the old ceiling
    # is no longer reachable.
    samples = int(previous.get("samples", 1)) + 1 if previous else 1
    row["samples"] = samples

    if previous and not replace:
        old = previous.get("tokens_per_second")
        new = row.get("tokens_per_second")
        if (
            isinstance(old, (int, float))
            and isinstance(new, (int, float))
            and float(old) > float(new)
        ):
            osh.info(
                f"Keeping the faster earlier measurement for {key}: "
                f"{old} tok/s over {new} tok/s. A slower sample usually means the "
                "machine was busy, not that the model got slower; pass replace=True "
                "to overrule."
            )
            kept = {**previous, "samples": samples}
            # The earlier row may predate the caller being able to supply an
            # estimate. Keep its (faster, more trustworthy) throughput, but
            # take the estimate now on offer, and derive the ratio against the
            # figure actually kept -- pairing the old estimate with the new
            # measurement, or vice versa, would calibrate against a comparison
            # that never happened.
            if estimated_tps and estimated_tps > 0 and "calibration_ratio" not in kept:
                kept["estimated_tps"] = round(float(estimated_tps), 1)
                kept["calibration_ratio"] = round(float(old) / float(estimated_tps), 3)
            store[key] = kept
            return _write_store(store, path)

    store[key] = row
    return _write_store(store, path)


def _write_store(store: dict[str, dict[str, Any]], path: Path) -> Path:
    """
    Write the store atomically.

    Via a temporary file in the same directory, then a rename. An interrupted
    write would otherwise leave a half-parsed file behind, and the next run
    would warn about a corrupt store it had written itself.

    Parameters
    ----------
    store : dict
        The complete store to serialise.
    path : Path
        Destination file.

    Returns
    -------
    Path
        The path written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(store, sort_keys=True, allow_unicode=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".measurements-", suffix=".yaml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def measured_tps(
    model: str,
    machine: str | None = None,
    store_path: Path | None = None,
    trusted_only: bool = False,
) -> float | None:
    """
    Look up the measured decode speed for `model` on this machine.

    Parameters
    ----------
    model : str
        Model tag to look up.
    machine : str or None
        Machine label; defaults to this machine.
    store_path : Path or None
        Override the default location; for tests.
    trusted_only : bool
        When True, ignore a figure derived from the wall clock. Pass this from
        anywhere a measurement would *disqualify* a model, since wall time
        understates decode speed and would reject candidates unfairly.

    Returns
    -------
    float or None
        Tokens per second, or None when there is no applicable measurement.
    """
    key = f"{model}@{machine or machine_id()}"
    row = load_measurements(store_path).get(key)
    if not row:
        return None
    if trusted_only and row.get("basis") != "eval_duration":
        return None
    value = row.get("tokens_per_second")
    return float(value) if isinstance(value, (int, float)) else None


# ---------------------------------------------------------------------------
# Calibration: what one measurement teaches us about the models we never ran
# ---------------------------------------------------------------------------

#: Clamp on the correction factor. A single measurement taken while the machine
#: was thrashing, or against a model whose catalog footprint is wrong, would
#: otherwise poison every estimate on the machine. Outside this band the ratio
#: says "something is wrong with the inputs", not "the hardware is 10x slower
#: than predicted", so it is ignored rather than trusted.
_MIN_CALIBRATION = 0.2
_MAX_CALIBRATION = 3.0


def _median(values: list[float]) -> float:
    """Median of a non-empty list. Preferred over the mean: with a handful of
    samples one odd model should not drag the whole machine's factor with it."""
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def calibration_factor(
    machine: str | None = None,
    store_path: Path | None = None,
) -> tuple[float, int] | None:
    """
    How wrong the bandwidth estimate runs on this machine, and on how much evidence.

    The bandwidth model predicts decode speed from memory bandwidth and a
    community-derived efficiency constant. Those constants are averages over
    other people's hardware, so on any particular machine the prediction has a
    systematic bias. That bias is a property of the machine far more than of
    the model, which is what makes it transferable: measuring *one* model
    improves the prediction for every model in the catalog, including the ones
    that were never pulled.

    How much it transfers, measured rather than assumed
    ---------------------------------------------------
    ``scripts/validate_calibration.py`` runs the leave-one-out version of that
    claim — calibrate on A, predict B — and on an Apple M2 Max it held in
    every direction tried: the error fell from 64-118% to 17-25%.

    So the claim is true and it is not precision. Across models and across
    repeated runs of the same model the ratio ranged roughly 0.46 to 0.61,
    which is why this returns a **median over several measurements** rather
    than trusting one, and why a real measurement still outranks a calibrated
    estimate wherever one exists. Calibration moves an estimate from wrong by
    a factor of two to wrong by about a fifth; it does not make it right.

    Derived from stored measurements rather than kept as separate state, so it
    cannot drift out of agreement with the measurements it summarises. Only
    figures from the serving daemon's own decode clock count — a wall-clock
    ratio would bake prompt-processing time into a decode correction.

    Parameters
    ----------
    machine : str or None
        Machine label; defaults to this machine.
    store_path : Path or None
        Override the measurement store location; for tests.

    Returns
    -------
    (factor, samples) or None
        The multiplier to apply to an estimate and how many measurements back
        it, or None when there is no usable evidence or the ratio is so far out
        that the inputs are more likely wrong than the hardware.
    """
    target = machine or machine_id()
    ratios = [
        float(row["calibration_ratio"])
        for row in load_measurements(store_path).values()
        if row.get("measured_on") == target
        and row.get("basis") == "eval_duration"
        and isinstance(row.get("calibration_ratio"), (int, float))
        and float(row["calibration_ratio"]) > 0
    ]
    if not ratios:
        return None

    factor = _median(ratios)
    if not _MIN_CALIBRATION <= factor <= _MAX_CALIBRATION:
        osh.warning(
            f"Ignoring a throughput calibration factor of {factor:.2f} on {target}: "
            f"outside [{_MIN_CALIBRATION}, {_MAX_CALIBRATION}], so the catalog "
            "footprint or the measurement is more likely wrong than the hardware."
        )
        return None
    return round(factor, 3), len(ratios)
