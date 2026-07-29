# CODING.md

Local copy of the coding standards for this project.
Canonical source: gist warith-harchaoui/21e67f6eabd3052d3ae426d5e0b1e950

Refresh with:

    gh gist view 21e67f6eabd3052d3ae426d5e0b1e950 > CODING.md

The standards that apply to every function and class in this codebase:

- NumPy-style docstrings (Parameters, Returns, Raises, Examples) on every function and class, including private ones.
- Full typing on every signature (`from __future__ import annotations`; no bare `Any` unless genuinely unavoidable).
- Comment density approximately 25 to 30 percent (one comment per three to four lines), explaining why, not what.
- `EXAMPLES.md` with one runnable recipe per public command, tested in CI.
- `requirements.txt` (runtime only) and `requirements-dev.txt` (pytest, ruff, mypy); dev packages never leak into the runtime install.
- pytest test suite in `tests/`, CI gate on every push.
- ruff for style (PEP 8, import order); violations block merges.
- Multi-surface: CLI via Click is mandatory; the same business logic must be importable as a library without invoking Click.
