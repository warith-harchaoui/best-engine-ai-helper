"""
sources.arena — conversational-preference ratings from the LM Arena family.

Arena ratings come from humans comparing two anonymous answers and picking one.
That makes them the best public measure of *conversational preference* and a
poor measure of almost everything else: a model that writes agreeable prose
outranks one that emits a schema-valid SQL query, because nobody voting was
asked to run the query. This adapter therefore contributes **one** axis,
``arena``, and the ranking layer decides what that axis is worth per use case
(see :data:`score._APP_BENCH_PRIORITY`, where an axis's weight is its position
in the list).

Two problems had to be solved before the numbers could enter the catalog.

**Scale.** An Elo rating lives around 1000-1500; every other axis in the
catalog is 0-100. The ranking layer takes the first non-null axis in a
priority list, so two candidates scored on different axes would be compared on
incompatible scales. Ratings are therefore converted at ingestion to the
expected win rate against a fixed reference rating -- see :func:`elo_to_score`.

**Staleness.** Arena data is not freely and freshly available. As of
2026-10-19 the site answers 403 behind a bot wall, one community mirror is
emitting empty snapshots, and the other two stopped updating in 2025. A rating
fourteen months old would rank last year's models above this year's, which is
strictly worse than having no rating at all. So every source reports the date
of the snapshot it returned, and anything older than
:data:`MAX_SNAPSHOT_AGE_DAYS` is refused with the reason rather than quietly
merged.

**Not supported, deliberately:** the commercial scraping APIs that do have
fresh data. They require a paid token and route the query through a third
party, which is the opposite of what this suite promises. If you have such a
feed, pass it as a custom source rather than having this module reach for one.

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import datetime as _dt
import math
import re
from typing import Any

import requests

#: Reference rating for the 0-100 conversion. Roughly a competent mid-board
#: model, so a score of 50 means "wins about half its comparisons against a
#: solid-but-unremarkable opponent". Fixed rather than derived from the board
#: so the conversion does not rescale every time the leaderboard moves.
REFERENCE_ELO = 1200.0

#: The Elo scale constant. A 400-point gap is a 10:1 expected win ratio.
ELO_SCALE = 400.0

#: Oldest snapshot still worth merging. Beyond this the ratings describe a
#: different generation of models and would actively mislead the ranker.
MAX_SNAPSHOT_AGE_DAYS = 120

#: Community mirrors, tried in order. Arena publishes no API, so every entry
#: here is someone else's scrape and every one of them can rot; the adapter
#: reports which answered and how old it was rather than assuming.
HISTORY_URL = "https://raw.githubusercontent.com/nakasyou/lmarena-history/main/output/scores.json"
SNAPSHOT_INDEX_URL = (
    "https://raw.githubusercontent.com/oolong-tea-2026/arena-ai-leaderboards/main/data/latest.json"
)
#: Directory listing for the dated snapshots. The mirror runs daily and keeps
#: every day it has ever produced, so the newest date is not necessarily the
#: newest date *with data* — see :func:`_from_snapshots`.
SNAPSHOT_DIR_URL = (
    "https://api.github.com/repos/oolong-tea-2026/arena-ai-leaderboards/contents/data"
)

SNAPSHOT_BOARD_URL = (
    "https://raw.githubusercontent.com/oolong-tea-2026/arena-ai-leaderboards"
    "/main/data/{date}/{board}.json"
)

_USER_AGENT = "Mozilla/5.0 (compatible; best-engine-ai-helper/0.3)"

#: Board name in a mirror -> the axis it informs. Only boards whose meaning is
#: unambiguous are mapped; "overall with style control" and friends are left
#: out because what they measure is a research question, not a catalog fact.
#: Board name as the mirror publishes it -> the axis this catalogue stores.
#:
#: Read against a real snapshot rather than guessed. The mirror's own
#: ``_index.json`` lists ``agent, code, document, image-edit, image-to-video,
#: search, text, text-to-image, text-to-video, video-edit, vision`` — so the
#: two entries this table used to carry for ``overall`` and ``coding`` could
#: never match anything: there is no ``overall`` board, and the code one is
#: spelled ``code``. The synonyms stay mapped because the history mirror and
#: the snapshot mirror do not agree on spelling, and a board we cannot name is
#: a score we silently drop.
_BOARD_AXES = {
    "overall": "arena",
    "text": "arena",
    "code": "arena_code",
    "coding": "arena_code",
    "vision": "arena_vision",
}

_DATE_RE = re.compile(r"(20\d{2})-?(\d{2})-?(\d{2})")

#: Quantization and packaging suffixes a runtime tag carries and a leaderboard
#: does not. ``qwen3:32b-q4_k_m`` and Arena's ``qwen3-32b`` are the same model;
#: the suffix describes how this machine stores it.
#:
#: Attributing a full-precision rating to a quantized copy slightly flatters
#: it. That is already how every other axis in this catalog works -- published
#: benchmarks are run on the full model -- so the treatment is consistent, and
#: the quant is recorded separately on the entry for anyone who wants to
#: discount it.
_QUANT_SUFFIX = re.compile(r"-(?:q\d+(?:[-_][a-z0-9]+)*|fp\d+|bf\d+|int\d+|awq|gptq|gguf|mlx)$")

#: Suffixes a leaderboard adds and a runtime tag does not.
_RELEASE_SUFFIXES = ("-instruct", "-chat", "-it", "-preview", "-latest")

#: An alias suffix meaning "whichever release is current".
_ALIAS_SUFFIX = re.compile(r"-(?:latest|preview)$")

#: A dated release token, in the three spellings providers actually use:
#: ``2024-05-13``, ``20241022``, ``2407`` (year-month).
#:
#: This is the shape of the naming gap. A leaderboard rates a *release* --
#: ``gpt-4o-2024-05-13``, ``claude-3-5-sonnet-20241022``, ``mistral-large-2407``
#: -- while a pricing catalog names the *alias* an API accepts: ``gpt-4o``,
#: ``mistral-large-latest``. Resolving an alias to the newest dated release of
#: the same family is not a guess; it is what the alias means.
_DATED_RELEASE = re.compile(r"^(?P<stem>.+)-(?P<when>\d{4}-\d{2}-\d{2}|\d{8}|\d{4})$")


def elo_to_score(elo: float, reference: float = REFERENCE_ELO) -> float:
    """
    Convert an Elo rating to a 0-100 score comparable with the other axes.

    Uses the Elo expected-score formula: the probability that a model rated
    ``elo`` beats one rated ``reference``, as a percentage.

    Chosen over min-max normalisation for two reasons. A min-max rescales
    every time the leaderboard moves, so yesterday's 100 is today's 94 and a
    cached catalog silently disagrees with a fresh one. And Elo is an interval
    scale with no meaningful zero, so the floor of a min-max would be an
    artefact of whoever happened to be last that week.

    Parameters
    ----------
    elo : float
        The rating, typically 800-1600.
    reference : float
        The rating that maps to 50. Defaults to :data:`REFERENCE_ELO`.

    Returns
    -------
    float
        Expected win rate against the reference, 0-100, rounded to one decimal.

    Examples
    --------
    >>> elo_to_score(1200)
    50.0
    >>> elo_to_score(1600) > 90
    True
    >>> elo_to_score(800) < 10
    True
    """
    expected = 1.0 / (1.0 + math.pow(10.0, (reference - float(elo)) / ELO_SCALE))
    return round(expected * 100.0, 1)


def _parse_date(text: str) -> _dt.date | None:
    """Pull a date out of a snapshot key or filename, in either spelling."""
    found = _DATE_RE.search(str(text))
    if not found:
        return None
    try:
        return _dt.date(*(int(g) for g in found.groups()))
    except ValueError:
        return None


def snapshot_age_days(snapshot: str, today: _dt.date | None = None) -> int | None:
    """Age in days of a snapshot identifier, or None if it carries no date."""
    when = _parse_date(snapshot)
    if when is None:
        return None
    return ((today or _dt.date.today()) - when).days


def _fetch_json(url: str, session: requests.Session | None, timeout: float) -> Any:
    sess = session or requests.Session()
    response = sess.get(url, timeout=timeout, headers={"User-Agent": _USER_AGENT})
    response.raise_for_status()
    return response.json()


def _from_history(
    session: requests.Session | None, timeout: float
) -> tuple[str, dict[str, dict[str, float]]] | None:
    """Read the flat history mirror: ``{date: {board: {sub: {model: elo}}}}``.

    Large (~18 MB) and simple. Returns the newest snapshot it carries, which
    may well be too old to use -- that judgement belongs to the caller, which
    has the staleness policy.
    """
    try:
        data = _fetch_json(HISTORY_URL, session, timeout)
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(data, dict) or not data:
        return None

    newest = max(data)
    boards: dict[str, dict[str, float]] = {}
    for board, sub in (data[newest] or {}).items():
        if not isinstance(sub, dict):
            continue
        # Each board holds several sub-boards; prefer the plain one over the
        # style-controlled and language-specific variants, which answer a
        # different question.
        for name in ("overall", "full", board):
            rows = sub.get(name)
            if isinstance(rows, dict) and rows:
                axis = _BOARD_AXES.get(board)
                if axis:
                    boards[axis] = {k: float(v) for k, v in rows.items()}
                break
    return (newest, boards) if boards else None


def _snapshot_dates(session: requests.Session | None, timeout: float) -> list[str]:
    """Dated snapshot directories the mirror holds, newest first.

    One listing request rather than guessing dates: the mirror produces a
    directory most days but not every day, so walking back a day at a time
    would spend most of its requests on 404s.

    Parameters
    ----------
    session : requests.Session or None
        Session to reuse, or None for a bare request.
    timeout : float
        Per-request network timeout, in seconds.

    Returns
    -------
    list[str]
        ISO dates, newest first; empty when the listing cannot be read.
    """
    try:
        listing = _fetch_json(SNAPSHOT_DIR_URL, session, timeout)
    except (requests.RequestException, ValueError):
        return []
    if not isinstance(listing, list):
        return []
    dates = [
        str(item.get("name"))
        for item in listing
        if isinstance(item, dict)
        and item.get("type") == "dir"
        and _DATE_RE.match(str(item.get("name") or ""))
    ]
    return sorted(dates, reverse=True)


def _from_snapshots(
    session: requests.Session | None, timeout: float
) -> tuple[str, dict[str, dict[str, float]]] | None:
    """Read the structured daily-snapshot mirror.

    Two things this used to get wrong, both of which left the axis empty while
    the mirror was serving perfectly good data:

    1. **It trusted ``latest.json``.** That file names the newest *directory*,
       and the mirror keeps producing a directory every day even when its own
       scrape returns nothing — ``_index.json`` then lists no leaderboards and
       every board is a 404. The newest date with data can be weeks older than
       the newest date. This walks back to the first one that has any, bounded
       by :data:`MAX_SNAPSHOT_AGE_DAYS` so a long-dead mirror still reports as
       dead rather than quietly serving ancient ratings.
    2. **It guessed the board names.** The index lists them, so they are read
       rather than assumed — which is how ``coding`` went unnoticed against a
       mirror that spells it ``code``.
    """
    dates = _snapshot_dates(session, timeout)
    if not dates:
        # No listing: fall back to whatever the index names, which is still
        # better than nothing on a machine behind a proxy that blocks the API.
        try:
            index = _fetch_json(SNAPSHOT_INDEX_URL, session, timeout)
            named = str((index or {}).get("date") or "")
        except (requests.RequestException, ValueError):
            return None
        dates = [named] if named else []

    for date in dates:
        age = snapshot_age_days(date)
        if age is not None and age > MAX_SNAPSHOT_AGE_DAYS:
            break
        try:
            index = _fetch_json(
                SNAPSHOT_BOARD_URL.format(date=date, board="_index"), session, timeout
            )
        except (requests.RequestException, ValueError):
            continue
        published = (index or {}).get("leaderboards") if isinstance(index, dict) else None
        names = sorted(published) if isinstance(published, dict) and published else []
        if not names:
            continue

        boards: dict[str, dict[str, float]] = {}
        for board in names:
            axis = _BOARD_AXES.get(board)
            if axis is None or axis in boards:
                continue
            try:
                payload = _fetch_json(
                    SNAPSHOT_BOARD_URL.format(date=date, board=board), session, timeout
                )
            except (requests.RequestException, ValueError):
                continue
            rows = payload.get("models") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                continue
            ratings: dict[str, float] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = row.get("model") or row.get("name") or row.get("key")
                value = row.get("score", row.get("elo", row.get("rating")))
                if name and value is not None:
                    try:
                        ratings[str(name)] = float(value)
                    except (TypeError, ValueError):
                        continue
            if ratings:
                boards[axis] = ratings
        if boards:
            return date, boards
    return None


#: Mirrors in preference order. The structured one first because its shape is
#: unambiguous; the bulk history as the fallback.
SOURCES = (
    ("arena-ai-leaderboards", _from_snapshots),
    ("lmarena-history", _from_history),
)


def fetch_arena_ratings(
    session: requests.Session | None = None,
    timeout: float = 30.0,
    max_age_days: int = MAX_SNAPSHOT_AGE_DAYS,
    today: _dt.date | None = None,
) -> dict[str, Any]:
    """
    Fetch Arena ratings from whichever mirror is alive and fresh enough.

    Parameters
    ----------
    session : requests.Session or None
        Optional shared session.
    timeout : float
        Per-request timeout in seconds.
    max_age_days : int
        Refuse a snapshot older than this. Set to 0 to disable the check, which
        you should only do to inspect an old snapshot deliberately -- merging
        one into a live catalog ranks a previous generation of models first.
    today : datetime.date or None
        Injectable for tests.

    Returns
    -------
    dict
        ``{"source": str, "snapshot": str, "age_days": int | None,
        "ratings": {axis: {model: elo}}, "scores": {axis: {model: 0-100}},
        "stale": bool, "note": str}``. ``ratings`` and ``scores`` are empty
        when nothing usable was found; ``note`` always says why.

    Examples
    --------
    >>> result = fetch_arena_ratings()          # doctest: +SKIP
    >>> result["source"], result["age_days"]    # doctest: +SKIP
    ('lmarena-history', 515)
    """
    attempts: list[str] = []

    for name, reader in SOURCES:
        try:
            found = reader(session, timeout)
        except Exception as exc:  # a broken mirror must not sink the refresh
            attempts.append(f"{name}: {type(exc).__name__}")
            continue
        if not found:
            attempts.append(f"{name}: no usable data")
            continue

        snapshot, ratings = found
        age = snapshot_age_days(snapshot, today)
        stale = bool(max_age_days) and age is not None and age > max_age_days
        if stale:
            attempts.append(f"{name}: snapshot {snapshot} is {age} days old")
            continue

        return {
            "source": name,
            "snapshot": snapshot,
            "age_days": age,
            "ratings": ratings,
            "scores": {
                axis: {model: elo_to_score(elo) for model, elo in rows.items()}
                for axis, rows in ratings.items()
            },
            "stale": False,
            "note": (
                f"{sum(len(r) for r in ratings.values())} rating(s) from {name}, "
                f"snapshot {snapshot}" + (f" ({age} days old)" if age is not None else "")
            ),
        }

    return {
        "source": None,
        "snapshot": None,
        "age_days": None,
        "ratings": {},
        "scores": {},
        "stale": True,
        "note": (
            "No fresh Arena source. Arena publishes no API, and every community "
            "mirror is either empty or stale: "
            + "; ".join(attempts)
            + ". Ranking continues on the other axes, which is the correct "
            "behaviour -- a stale rating would be worse than none."
        ),
    }


def match_model(catalog_id: str, ratings: dict[str, float]) -> str | None:
    """
    Find the Arena entry for a catalog id, or None.

    Arena names a model the way its provider announced it
    (``qwen3-235b-a22b-instruct-2507``); this catalog names it the way the
    runtime pulls it (``qwen3:32b``). No shared identifier exists, so the match
    is heuristic and deliberately conservative: a wrong match attributes
    another model's reputation to this one, which is worse than no match.

    Five passes, strictest first: exact; exact after normalising separators;
    exact after dropping a quantization suffix the leaderboard never carries
    (``qwen3:32b-q4_k_m`` is Arena's ``qwen3-32b``); and finally a *unique*
    prefix match, which catches the release suffixes a leaderboard adds
    (``-instruct``, ``-preview``). A prefix matching several entries is
    rejected rather than guessed: attributing one model's reputation to
    another is worse than leaving the axis empty, because the ranker would act
    on it. Finally, an alias is resolved to the newest dated release of its
    family, which is what the alias means rather than a heuristic.

    Parameters
    ----------
    catalog_id : str
        An id as ``models.yaml`` spells it, e.g. ``"qwen3-vl:8b"``.
    ratings : dict
        ``{arena model name: rating}``.

    Returns
    -------
    str or None
        The matching Arena key, or None when no confident match exists.

    Examples
    --------
    >>> match_model("qwen3:32b", {"qwen3-32b": 1300.0})
    'qwen3-32b'
    >>> match_model("qwen3:32b-q4_k_m", {"qwen3-32b": 1300.0})
    'qwen3-32b'
    >>> match_model("qwen3:32b", {"qwen3-32b-instruct": 1300.0})
    'qwen3-32b-instruct'
    >>> match_model("qwen3:32b", {"qwen3-32b-a": 1.0, "qwen3-32b-b": 2.0}) is None
    True
    >>> match_model("mistral-large-latest",
    ...             {"mistral-large-2407": 1.0, "mistral-large-2411": 2.0})
    'mistral-large-2411'
    >>> match_model("claude-3-5-sonnet",
    ...             {"claude-3-5-sonnet-20240620": 1.0,
    ...              "claude-3-5-sonnet-20241022": 2.0})
    'claude-3-5-sonnet-20241022'
    >>> match_model("claude-3-5-sonnet",
    ...             {"claude-3-5-sonnet-20250219-thinking-32k": 1.0}) is None
    True
    """

    def normalise(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

    if catalog_id in ratings:
        return catalog_id

    index = {normalise(k): k for k in ratings}

    wanted = normalise(catalog_id)
    bare = _QUANT_SUFFIX.sub("", wanted)
    for candidate in (wanted, bare):
        if candidate in index:
            return index[candidate]

    # A unique prefix only. Several matches means the leaderboard distinguishes
    # variants this catalog does not, and picking one would be a coin toss.
    for candidate in (wanted, bare):
        prefixed = [
            original
            for key, original in index.items()
            if key.startswith(candidate + "-") and key[len(candidate) :] in _RELEASE_SUFFIXES
        ]
        if len(prefixed) == 1:
            return prefixed[0]

    # Alias -> newest dated release of the same family. `mistral-large-latest`
    # IS `mistral-large-2411` until the provider ships the next one, so taking
    # the newest is the alias's own definition rather than a heuristic.
    #
    # Anchored on the date token, so `claude-3-5-sonnet-20250219-thinking-32k`
    # is NOT matched by `claude-3-5-sonnet`: a different serving mode is a
    # different thing to rate.
    stem = _ALIAS_SUFFIX.sub("", bare)
    dated: list[tuple[str, str]] = []
    for key, original in index.items():
        found = _DATED_RELEASE.match(key)
        if found and found.group("stem") == stem:
            dated.append((found.group("when"), original))
    if dated:
        # Compare within one spelling only: mixing `2407` with `20241022`
        # would order by string length rather than by time.
        widest = max(len(when) for when, _ in dated)
        newest = max((d for d in dated if len(d[0]) == widest), key=lambda d: d[0])
        return newest[1]
    return None


def merge_into(
    entries: list[dict[str, Any]],
    result: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Add Arena axes to catalog entries, and report what was matched.

    Entries are copied, not mutated: a refresh that half-applies and then
    fails should leave the caller's catalog as it found it.

    Returns
    -------
    (entries, report)
        ``report`` carries ``matched``, ``unmatched`` and the source note, so a
        caller can show which models got a rating and which the heuristic
        declined to guess at.
    """
    scores = result.get("scores") or {}
    if not scores:
        return list(entries), {"matched": [], "unmatched": [], "note": result.get("note", "")}

    merged: list[dict[str, Any]] = []
    matched: list[str] = []
    unmatched: list[str] = []

    for entry in entries:
        copy = {**entry, "benchmarks": dict(entry.get("benchmarks") or {})}
        ident = str(copy.get("id") or "")
        hit = False
        for axis, rows in scores.items():
            key = match_model(ident, rows)
            if key is not None:
                copy["benchmarks"][axis] = rows[key]
                hit = True
        if hit:
            copy["arena_snapshot"] = result.get("snapshot")
            matched.append(ident)
        else:
            unmatched.append(ident)
        merged.append(copy)

    return merged, {
        "matched": matched,
        "unmatched": unmatched,
        "note": result.get("note", ""),
    }
