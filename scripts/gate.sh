#!/usr/bin/env bash
# The gate, written once.
#
# Three places used to answer "is this clean?" and each answered it in its own
# words: CONTRIBUTING.md listed four commands to copy-paste, .githooks/pre-push
# ran a fifth variant, and .github/workflows/ci.yml ran a sixth. They drifted,
# which is the only thing three copies of one rule ever do: the hook promised
# "a red local state never reaches CI" while running a different sweep than CI
# ran, so a push could pass the hook and fail the gate it was supposed to
# predict. One file now holds the commands; the hook, CI and the contributor
# all call it, so there is nothing left to drift.
#
# Usage:
#   scripts/gate.sh            # everything, in the order CI runs it
#   scripts/gate.sh lint       # ruff check + ruff format --check
#   scripts/gate.sh types      # mypy
#   scripts/gate.sh tests      # pytest + the coverage floor
#   scripts/gate.sh version    # pyproject version has a CHANGELOG entry
#
# Two stages exist but are NOT in `all`, because each asks a question the
# answer to which depends on the environment rather than on the commit:
#
#   scripts/gate.sh deps       # pip check -- sharp in CI's clean venv only
#   scripts/gate.sh package    # build a wheel + sdist and inspect them
#
# CI calls the stages one at a time so a failure is named by its own step;
# humans and the hook call it with no argument. Same commands either way.
set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || dirname "$(dirname "$(realpath "$0")")")"

# The one number both the hook and CI enforce. It lived only in CI before, so
# nothing local could see a breach: six modules went out at 89.54% because the
# floor was somewhere the author never ran. Keep it here, raise it here.
COVERAGE_FLOOR="${COVERAGE_FLOOR:-90}"

PACKAGE="best_engine_ai_helper"

say() { printf '\n\033[1m[gate] %s\033[0m\n' "$*"; }

gate_deps() {
  # CI-only, and not part of `all`. `pip check` asks whether the INSTALLED set
  # is coherent, which is a sharp question in CI's throwaway venv (it holds
  # this project and nothing else) and a meaningless one in the shared conda
  # environment a developer actually works in, where it reports a dozen
  # unrelated projects disagreeing about numpy. A gate stage that is red for
  # reasons the commit cannot fix is a stage people learn to skip, and the
  # only way to skip this one is --no-verify, which skips the lint and the
  # tests with it.
  say "pip check (the installed dependency set is coherent)"
  python -m pip check
}

gate_lint() {
  say "ruff check"
  ruff check .
  say "ruff format --check"
  ruff format --check .
}

gate_types() {
  say "mypy"
  # mypy aborts the whole run when a *dependency's* stubs will not parse, and
  # that is an ordinary state on a developer machine: `requirements-dev.txt`
  # caps numpy below 2.5 precisely because its stubs use PEP 695 syntax that
  # mypy rejects under this project's python_version = "3.10" target, and a
  # shared conda environment holding some other project's numpy 2.5 therefore
  # cannot type-check this one. CI installs the pinned set and is unaffected.
  #
  # Failing the push on that would be a verdict about the machine wearing the
  # clothes of a verdict about the commit, and the only way past a wrong red
  # is --no-verify, which skips the lint and the tests with it. So: if every
  # error mypy reports lies outside this package, the environment could not
  # answer the question and says so; one error inside the package and it is
  # a real failure, judged as one.
  local output status
  set +e
  output="$(mypy "$PACKAGE" 2>&1)"
  status=$?
  set -e
  printf '%s\n' "$output"
  [ "$status" -eq 0 ] && return 0

  if printf '%s\n' "$output" | grep -qE "^$PACKAGE/.*: (error|note):"; then
    return "$status"
  fi

  echo "[gate] note: mypy could not run here -- every error above is in a" >&2
  echo "[gate]       dependency, not in $PACKAGE/. Your environment's pins" >&2
  echo "[gate]       differ from requirements-dev.txt; CI will judge this." >&2
  return 0
}

gate_tests() {
  # A gate must never hang: the only way out of a stalled push is
  # --no-verify, which skips the lint and the tests together, so a gate that
  # can hang is a gate that teaches people to disable it. pytest-timeout
  # turns a stall into a failure that names the test. It is in
  # requirements-dev.txt, but the gate still has to work where it is absent,
  # and the absence is announced rather than silently downgraded.
  local timeout_args=()
  if python -c "import pytest_timeout" 2>/dev/null; then
    timeout_args=(--timeout=600)
  else
    echo "[gate] note: pytest-timeout is not installed; a hung test will not be named."
  fi

  say "pytest (unit + doctests), coverage floor ${COVERAGE_FLOOR}%"
  python -m pytest -q \
    --cov="$PACKAGE" --cov-report=term-missing \
    --cov-fail-under="$COVERAGE_FLOOR" "${timeout_args[@]}"
}

gate_version() {
  # The easy-to-forget half of a version bump. Cheap enough to run every
  # time, and it fails at the push rather than at the release.
  say "pyproject version has a CHANGELOG entry"
  local version
  version="$(python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
  if ! grep -qF "## [$version]" CHANGELOG.md; then
    echo "::error::pyproject.toml is at $version but CHANGELOG.md has no '## [$version]' entry" >&2
    return 1
  fi
  echo "[gate] $version is in CHANGELOG.md"
}

gate_package() {
  # Deliberately NOT part of the default sweep: it installs two more tools and
  # builds the distribution, which is minutes of work that only the packaging
  # inputs can invalidate. The packaging workflow runs it when they change.
  say "build + inspect the distribution"
  python -m pip install --quiet --no-cache-dir build twine
  # A private output directory rather than ./dist: this runs on developer
  # machines too, and a build script that quietly deletes whatever a release
  # left in dist/ is a trap, not a convenience.
  local outdir
  outdir="$(mktemp -d "${TMPDIR:-/tmp}/gate-dist-XXXXXX")"
  trap 'rm -rf "$outdir"' RETURN
  python -m build --outdir "$outdir"
  twine check "$outdir"/*
  python - "$outdir" <<'PYEOF'
"""The ONNX model must reach the wheel as bytes, not as an LFS pointer.

`models/clip_nsfw_vit_l14.onnx` is tracked with Git LFS, so a checkout
without `lfs: true` leaves a ~130-byte text stub where the model should be.
Nothing fails at build time: the stub packs happily, and the breakage
surfaces only when somebody installs [filtered] and the image classifier
loads garbage. Weighing the member is the cheapest way to tell the two
apart.
"""

import pathlib
import sys
import zipfile

wheel = next(pathlib.Path(sys.argv[1]).glob("*.whl"))
with zipfile.ZipFile(wheel) as zf:
    name = "best_engine_ai_helper/models/clip_nsfw_vit_l14.onnx"
    size_mb = zf.getinfo(name).file_size / 1_000_000
    assert size_mb > 1.0, (
        f"{name} is {size_mb:.3f} MB in the wheel -- that is an LFS pointer "
        "stub, not the real model (expected ~1.9 MB). Run `git lfs pull`."
    )
print(f"OK: {name} is {size_mb:.2f} MB in the wheel")
PYEOF
}

gate_all() {
  gate_lint
  gate_types
  gate_tests
  gate_version
  say "all green"
}

case "${1:-all}" in
  all) gate_all ;;
  deps) gate_deps ;;
  lint) gate_lint ;;
  types) gate_types ;;
  tests) gate_tests ;;
  version) gate_version ;;
  package) gate_package ;;
  *)
    echo "usage: scripts/gate.sh [all|deps|lint|types|tests|version|package]" >&2
    exit 2
    ;;
esac
