"""
observe — a local, append-only activity/cost ledger for :func:`llm.chat`.

Every :func:`best_engine_ai_helper.llm.chat` call already emits a small event
dict to any observer registered via :func:`llm.add_observer`; nothing
consumes it by default. This module is that consumer: call :func:`enable`
once (the CLI, the FastAPI app, and the MCP server all do this at startup)
and every subsequent call — local or, once the ``cloud`` branch's paid
transports land, cloud — is appended to a SQLite database at
``~/.best-engine-ai-helper/usage.db``.

The point is the "one company, several users" case: a shared machine or a
small internal server fields calls from more than one person, and someone
needs to answer "who is calling what, how often, and at what cost" without
standing up a separate telemetry stack. This ledger is local-only (no
network call, no third-party service) and off by default.

Cost is a **best-effort estimate**, not a provider-verified bill. Providers
report real token usage per call; until that lands (tracked on the ``cloud``
branch), cost is estimated from character counts via a fixed chars-per-token
ratio (see :data:`_CHARS_PER_TOKEN`) against the bundled ``pricing.yaml``
table. Local backends (Ollama, vLLM) always cost ``0.0`` — there is no paid
API call to price. A cloud-backend call for a model absent from
``pricing.yaml`` gets ``cost_usd: None`` (unknown), never a fabricated number.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

import contextvars
import getpass
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import llm as _llm

# ---------------------------------------------------------------------------
# Storage location
# ---------------------------------------------------------------------------

_USER_DIR = Path.home() / ".best-engine-ai-helper"
_DEFAULT_DB_PATH = _USER_DIR / "usage.db"

# Root of the installed package; pricing.yaml sits next to pyproject.toml,
# same convention as models.yaml / hardware.yaml / usages.yaml (see catalog.py).
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_PRICING_PATH = _PACKAGE_ROOT / "pricing.yaml"

# Backends that never incur a per-call charge: local inference, whatever the
# hardware. Any other backend name is treated as a paid API.
_FREE_BACKENDS = frozenset({"ollama", "vllm", "langchain"})

# Rough English-text approximation (OpenAI's own rule of thumb: ~4 characters
# per token). A real count from the provider's `usage` field is always
# preferred once available; this is the fallback until then.
_CHARS_PER_TOKEN = 4.0

# ---------------------------------------------------------------------------
# User attribution
# ---------------------------------------------------------------------------
# Scoped override for a single call or a `with` block (e.g. a web server
# handling one request per user); falls back to a process-wide override env
# var, then the OS login name -- the sensible default for a shared machine
# where each person has their own account.
_CURRENT_USER: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "best_engine_current_user", default=None
)


def current_user() -> str:
    """
    Resolve the identity to attribute the next ledger entry to.

    Precedence: :func:`as_user` scope > ``BEST_ENGINE_USER`` env var > OS
    login name > ``"unknown"`` (only when even the OS refuses to say).

    Returns
    -------
    str
        The resolved user identity. Never empty.

    Examples
    --------
    >>> isinstance(current_user(), str) and current_user() != ""
    True
    """
    scoped = _CURRENT_USER.get()
    if scoped:
        return scoped
    env = os.environ.get("BEST_ENGINE_USER")
    if env:
        return env
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 — some sandboxes have no login name at all
        return "unknown"


class as_user:
    """
    Context manager: attribute every ledger entry inside the block to ``name``.

    Parameters
    ----------
    name : str
        Identity to record for calls made inside this block.

    Examples
    --------
    >>> with as_user("alice"):
    ...     current_user()
    'alice'
    >>> current_user() != "alice"
    True
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._token: contextvars.Token[str | None] | None = None

    def __enter__(self) -> None:
        self._token = _CURRENT_USER.set(self._name)

    def __exit__(self, *exc_info: object) -> None:
        if self._token is not None:
            _CURRENT_USER.reset(self._token)


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


def _load_pricing() -> dict[str, dict[str, float]]:
    """
    Load ``pricing.yaml``: ``{model_id: {input_per_1m, output_per_1m}}`` (USD).

    Returns
    -------
    dict
        Empty dict if the file is absent or empty — an unpriced catalog
        degrades to "cost unknown" for every cloud call, never a crash.
    """
    if not _PRICING_PATH.is_file():
        return {}
    raw = yaml.safe_load(_PRICING_PATH.read_text(encoding="utf-8")) or {}
    models: dict[str, dict[str, float]] = raw.get("models", {})
    return models


def estimate_cost_usd(event: dict[str, Any]) -> float | None:
    """
    Estimate the USD cost of one :func:`llm.chat` event.

    Parameters
    ----------
    event : dict
        One event dict as emitted by :func:`llm.chat` (``backend``, ``model``,
        ``in_chars``, ``out_chars``).

    Returns
    -------
    float or None
        ``0.0`` for a local backend (always free). For a paid backend: the
        estimated cost from ``pricing.yaml``, or None when the model is not
        in the table — an unpriced model must never silently show as free.

    Examples
    --------
    >>> estimate_cost_usd({"backend": "ollama", "model": "qwen3:8b",
    ...                     "in_chars": 100, "out_chars": 100})
    0.0
    >>> estimate_cost_usd({"backend": "openai", "model": "not-in-table",
    ...                     "in_chars": 100, "out_chars": 100}) is None
    True
    """
    backend = event.get("backend", "")
    if backend in _FREE_BACKENDS:
        return 0.0

    pricing = _load_pricing().get(event.get("model", ""))
    if not pricing:
        return None

    in_tokens = float(event.get("in_chars", 0)) / _CHARS_PER_TOKEN
    out_tokens = float(event.get("out_chars", 0)) / _CHARS_PER_TOKEN
    cost: float = (
        in_tokens / 1_000_000 * float(pricing.get("input_per_1m", 0.0))
        + out_tokens / 1_000_000 * float(pricing.get("output_per_1m", 0.0))
    )
    return round(cost, 6)


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


class Ledger:
    """
    Append-only SQLite sink for :func:`llm.chat` observer events.

    Parameters
    ----------
    db_path : str or Path or None
        Where to store the database. Defaults to
        ``~/.best-engine-ai-helper/usage.db``; ``:memory:`` is accepted for
        tests. The parent directory is created if missing.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = str(db_path) if db_path is not None else str(_DEFAULT_DB_PATH)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # `check_same_thread=False`: a FastAPI app may call `record` from a
        # different thread than the one that constructed the Ledger; SQLite
        # itself serializes writes, so this is safe for the low write volume
        # a per-call ledger sees.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the ``calls`` table if it does not already exist."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                user TEXT NOT NULL,
                backend TEXT NOT NULL,
                model TEXT NOT NULL,
                kind TEXT NOT NULL,
                in_chars INTEGER NOT NULL,
                images INTEGER NOT NULL,
                out_chars INTEGER NOT NULL,
                latency_ms REAL NOT NULL,
                ok INTEGER NOT NULL,
                error TEXT,
                cost_usd REAL
            )
            """
        )
        self._conn.commit()

    def record(self, event: dict[str, Any]) -> None:
        """
        Persist one :func:`llm.chat` event, enriched with user and cost.

        Parameters
        ----------
        event : dict
            One event dict as emitted by :func:`llm.chat`.
        """
        self._conn.execute(
            """
            INSERT INTO calls
                (ts, user, backend, model, kind, in_chars, images, out_chars,
                 latency_ms, ok, error, cost_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                current_user(),
                event.get("backend", ""),
                event.get("model", ""),
                event.get("kind", ""),
                event.get("in_chars", 0),
                event.get("images", 0),
                event.get("out_chars", 0),
                event.get("latency_ms", 0.0),
                1 if event.get("ok") else 0,
                event.get("error"),
                estimate_cost_usd(event),
            ),
        )
        self._conn.commit()

    def summary(self) -> dict[str, Any]:
        """
        Aggregate the ledger into the figures a usage dashboard needs.

        Returns
        -------
        dict
            ``total_calls``, ``total_cost_usd`` (``0.0`` for an empty ledger,
            None if any recorded call has an unpriced model — an unknown
            component must never be silently dropped from the total),
            ``error_rate`` (0-1), ``by_user`` / ``by_model`` (call count +
            cost per key, sorted by call count descending), and
            ``recent_errors`` (last 10 failed calls: ts, user, model, error).
        """
        cur = self._conn.cursor()
        total_calls = cur.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
        total_cost = cur.execute(
            "SELECT SUM(cost_usd) FROM calls WHERE cost_usd IS NOT NULL"
        ).fetchone()[0]
        has_unpriced_paid_call = cur.execute(
            "SELECT COUNT(*) FROM calls WHERE cost_usd IS NULL"
        ).fetchone()[0]
        errors = cur.execute("SELECT COUNT(*) FROM calls WHERE ok = 0").fetchone()[0]

        def _grouped(column: str) -> list[dict[str, Any]]:
            rows = cur.execute(
                f"SELECT {column}, COUNT(*), SUM(cost_usd) FROM calls "  # noqa: S608 — column is one of two fixed literals below, never user input
                f"GROUP BY {column} ORDER BY COUNT(*) DESC"
            ).fetchall()
            return [
                {column: key, "calls": count, "cost_usd": cost}
                for key, count, cost in rows
            ]

        recent_errors = cur.execute(
            "SELECT ts, user, model, error FROM calls WHERE ok = 0 "
            "ORDER BY id DESC LIMIT 10"
        ).fetchall()

        if total_calls == 0:
            total_cost_usd: float | None = 0.0
        elif has_unpriced_paid_call:
            total_cost_usd = None
        else:
            total_cost_usd = total_cost

        return {
            "total_calls": total_calls,
            "total_cost_usd": total_cost_usd,
            "error_rate": round(errors / total_calls, 4) if total_calls else 0.0,
            "by_user": _grouped("user"),
            "by_model": _grouped("model"),
            "recent_errors": [
                {"ts": ts, "user": user, "model": model, "error": error}
                for ts, user, model, error in recent_errors
            ],
        }

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()


# ---------------------------------------------------------------------------
# Module-level enable/disable
# ---------------------------------------------------------------------------

_active_ledger: Ledger | None = None


def enable(db_path: str | Path | None = None) -> Ledger:
    """
    Start recording every :func:`llm.chat` call to a ledger.

    Idempotent: calling this again returns the already-active ledger rather
    than registering a second observer.

    Parameters
    ----------
    db_path : str or Path or None
        Forwarded to :class:`Ledger`. Ignored if a ledger is already active.

    Returns
    -------
    Ledger
        The active ledger, for direct querying (:meth:`Ledger.summary`).
    """
    global _active_ledger
    if _active_ledger is None:
        _active_ledger = Ledger(db_path)
        _llm.add_observer(_active_ledger.record)
    return _active_ledger


def disable() -> None:
    """
    Stop recording and close the active ledger, if any.

    Clears every registered :mod:`llm` observer, not only this module's —
    today the ledger is the only observer type in the suite, so this is
    equivalent in practice, but a caller with its own observers registered
    separately would need to re-register them after calling this.
    """
    global _active_ledger
    _llm.clear_observers()
    if _active_ledger is not None:
        _active_ledger.close()
        _active_ledger = None


def is_enabled() -> bool:
    """Return whether a ledger is currently recording."""
    return _active_ledger is not None


def active_ledger() -> Ledger | None:
    """Return the active ledger, or None if :func:`enable` was never called."""
    return _active_ledger
