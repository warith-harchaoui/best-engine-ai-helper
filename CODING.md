# CODING.md

This project follows the coding standard published at gist
[warith-harchaoui/21e67f6eabd3052d3ae426d5e0b1e950](https://gist.github.com/warith-harchaoui/21e67f6eabd3052d3ae426d5e0b1e950).
A full local mirror lives at [references/CODING.md](references/CODING.md), with
one deliberate deviation: the gist's Agent Skills section and every
skill-specific surface reference are dropped from the mirror. The project's own
skill lives in `skills/best-engine-ai-helper/`, installed as
`skills/README.md` describes. Refresh the mirror (re-apply that same deviation)
with:

    gh gist view 21e67f6eabd3052d3ae426d5e0b1e950 --raw > references/CODING.md

The standards that apply to every function and class in this codebase:

- NumPy-style docstrings (Parameters, Returns, Raises, Examples) on every function and class, including private ones.
- Full typing on every signature (`from __future__ import annotations`; no bare `Any` unless genuinely unavoidable).
- Comments explain why, not what.
- `EXAMPLES.md` with one runnable recipe per public command, tested in CI.
- `requirements.txt` (runtime only) and `requirements-dev.txt` (pytest, ruff, mypy); dev packages never leak into the runtime install.
- pytest test suite in `tests/` (plus the docstring Examples): the fast tests gate CI on every push, the whole suite gates the pre-push hook.
- ruff for style (PEP 8, import order); violations block merges.
- Multi-surface, one shared core: importable library (`best_engine_ai_helper`), CLI (`cli.py`, one command line built with Click), GUI + HTTP API (`api.py`, FastAPI), and MCP (`mcp.py`, fastapi-mcp) all delegate to the same application logic — no surface grows its own copy of business rules.
- Every GUI-visible string and human-language prompt resolves through `best_engine_ai_helper/locales/i18n.yaml`.
