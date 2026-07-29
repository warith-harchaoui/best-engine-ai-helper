# Contributing

Thanks for your interest. This file documents how the project is maintained and what to expect.

## Versioning

This project follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
Given a version `MAJOR.MINOR.PATCH`:

- **MAJOR** bumps when the public API changes in a way that breaks existing callers: function removed,
  signature changed incompatibly, return type changed, exception class changed.
- **MINOR** bumps when functionality is added in a backwards-compatible way: new function, new optional
  parameter, new optional dependency.
- **PATCH** bumps for backwards-compatible fixes only: bug fixes, internal refactors, packaging fixes.

Names starting with `_` are private and may change between any two releases without a MAJOR bump.

## Code standards

Every Python file follows the mandate in [CODING.md](CODING.md):

1. NumPy-style docstrings on every function and class (including private ones).
2. Full type annotations; `from __future__ import annotations` in every file.
3. Comment density approximately 25 to 30 percent, explaining the *why*.
4. No bare `print(...)` in library code; use `click.echo` or `sys.stderr.write` in the CLI layer.
5. `EXAMPLES.md` stays runnable: every recipe is tested in CI.

Run the checks before opening a pull request:

```sh
pip install -e ".[dev]"
ruff check best_engine_ai_helper/ tests/
python -m pytest tests/ -x -q
```

## Writing standards

English prose (README, EXAMPLES, docstrings, comments) follows [references/WRITING.md](references/WRITING.md).
French prose (LISEZMOI, PAYSAGE) follows [references/ECRITURE.md](references/ECRITURE.md).

Key rules for both:

- No punctuation dashes (no em dash, no en dash used as an aside). Rewrite with commas, colons,
  semicolons, or parentheses.
- No machine tells: no "Moreover", "Furthermore", "crucial", "game-changer", "In conclusion".
- Acronyms: plain-language gloss first, then the term, then the abbreviation.

## Releases

Releases live in [CHANGELOG.md](CHANGELOG.md), tagged `vX.Y.Z` in git, and published as GitHub releases.

## Authorship

Sole author: [Warith Harchaoui](https://www.linkedin.com/in/warith-harchaoui/).
External contributions are welcome. Open an issue or pull request on GitHub.

## License

[BSD-3-Clause](LICENSE).
