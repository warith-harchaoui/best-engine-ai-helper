# Changelog

All notable changes to best-engine-ai-helper are documented here.

## [1.9.0] - 2026-10-25

### Removed

- **The argparse CLI twin (`cli_argparse.py`) and its entry point
  `best-engine-ai-helper-argparse`.** This package now ships exactly one
  command line, `best-engine-ai-helper`, built with click. A suffix naming
  the parsing library describes the implementation, not the interface, and
  the twin cost two of everything — two parsers, two option declarations, two
  test modules, and a 1:1 parity contract that only existed to keep the
  duplication honest — for no behaviour a user could observe. `click` was
  already a core dependency here, so nothing moved between dependency
  sections and no extra was deleted.

  Parity was verified before deleting, not assumed: the two surfaces agreed
  on all 23 command/option nodes (15 top-level commands, 19 leaf command
  paths), and the only declared differences were already allow-listed as
  deliberate (`detect --json`, hidden and always true; `report --cloud`, the
  positive half of click's `--cloud/--no-cloud` pair). `cli_argparse.py`
  imported `_VALID_APPLICATIONS` and `_fmt_table` *from* `cli.py`, never the
  other way round, so the surviving module lost nothing.

  Coverage that existed only on the argparse side was ported rather than
  dropped: the command inventory (the parity tests were the only place the
  command set was written down, now `EXPECTED_COMMANDS` in
  `tests/test_cli.py`), the `--help` smoke over every command and subgroup,
  the `"hardware"` key in `detect`'s JSON, and the `providers` tally line.

### Added

- **`-h` and `-V`.** `--help` worked and `-h` answered "No such option";
  `--version` worked and `-V` did not exist. Both are now registered on the
  group, `-V` capitalised because `-v` is already `--verbose`. Found by
  running the command, not by reading it.

### Fixed

- **`--version` reported the installed distribution, not the checked-out
  tree.** `@click.version_option(package_name=…)` with no version argument
  reads the metadata pip last wrote, so an editable checkout at 1.9.0
  answered `1.8.1` — which is precisely the question somebody debugging a
  local change asks it. `__version__` is now passed explicitly, and
  `prog_name` with it: `python -m best_engine_ai_helper.cli --version` used
  to name the module instead of the command.

- **The module docstring of `cli.py` listed 12 of the 15 commands.**
  `resolve`, `report`, `usages`, `providers` and `gui` had been added without
  it, so the one place a reader looks for the command set was wrong by a
  third.

### Changed

- **The `os-helper` cap widened from `<3` to `<4`.** os-helper 3.0.0 drops
  its own command line, which nothing here ever called, so the major bump is
  not breaking for this package.

- **The click group is named `cli` and the console wrapper is named `main`**
  (they were `main` and `console_entry`), matching every other member of the
  suite: `[project.scripts]` now reads
  `best-engine-ai-helper = "best_engine_ai_helper.cli:main"`. The wrapper
  itself is unchanged — it still turns a stray library exception into one
  `Error: …` line and exit 1 instead of a traceback.

### Migration

- `best-engine-ai-helper-argparse <command>` → `best-engine-ai-helper
  <command>`. Same commands, same options, same output; only the suffix is
  gone. Reinstall (`pip install -U best-engine-ai-helper`) to drop the stale
  console script, which otherwise lingers in the environment pointing at a
  module that no longer exists.
- Code importing `best_engine_ai_helper.cli_argparse` must import
  `best_engine_ai_helper.cli`; code importing `cli.main` as the click group
  must import `cli.cli` (`cli.main` is now the console wrapper).

## [1.8.1] - 2026-10-22

### Changed

- **`i18n.prompt()` delegates to `os_helper.Prompts`**, the prompt loader
  added in os-helper 2.9.0, instead of this module's own accessor over
  `Locales.raw`. Three members were each solving prompts privately; this was
  one of them.

  Nothing about the file changes. `Prompts` serves the single-language shape
  this package uses (`key -> role -> text`) as readily as a multi-language
  one, so the deliberate choice to author one model-facing language — declared
  as `meta.model_prompt_locale`, documented in CODING.md 21.3.3 — is kept
  intact rather than reshaped away. What the package gains is the section-wide
  `problems()` check, now called by a test.

## [1.8.0] - 2026-10-21

### Changed

- **The GUI's strings moved from `locales/i18n.yaml` to a `gettext`
  catalogue** — the last of the suite's eight GUIs to migrate, completing the
  move to one mechanism (os-helper 2.6.0). The English is now the source,
  written in the markup as `{{_("…")}}`; the French lives in
  `best_engine_ai_helper/locales/fr/LC_MESSAGES/best_engine_ai_helper.po`, at
  84 entries the largest catalogue in the suite.

  A string the French catalogue has not caught up with renders as **readable
  English** instead of as a key. The cost is the mirror image — rewording the
  English orphans its French entry, and gettext would quietly serve the
  English — so `tests/test_gui_i18n.py` hands every source string to
  `Catalog.problems`, which names both halves of that fault.

- **The prompts stay in `locales/i18n.yaml`, and that is not an exception to
  the rule.** They are single-language, model-facing templates keyed on
  meaning: there is no `fr`/`en` pair anywhere under `prompts`, so there is
  nothing for gettext to translate. `Locales` remains the right loader for
  text keyed that way, and the YAML now says so in a comment where the `gui`
  section used to be. What the package no longer has is two mechanisms for the
  *same* kind of text.

- **The English task placeholder now uses curly quotes**, matching the French
  guillemets it sits beside: `e.g. “write product descriptions…”`. The ASCII
  quotes it carried before had to be HTML-escaped to survive the attribute
  they render into; curly quotes cannot break out of it at all. The regression
  guard that a raw `"` never reaches `placeholder="…"` is kept.

### Removed

- `i18n.gui_strings()`, which nothing reads now that the GUI resolves through
  `Catalog`. `i18n.locales()`, `i18n.prompt()` and `PROMPTS_SECTION` stay —
  they serve the prompts.

## [1.7.0] - 2026-10-21

### Fixed

- **The gate could not run the tests on macOS.** `scripts/gate.sh`, added in
  this same release, builds `timeout_args=()` and expands it as
  `"${timeout_args[@]}"`. Under `set -u`, bash 3.2 — the bash macOS ships, and
  therefore the one most contributors have — treats the expansion of an
  *empty* array as an unbound variable. So the branch written precisely so the
  gate works without `pytest-timeout` was the one branch that could not run:
  `timeout_args[@]: unbound variable`, and no tests at all.

  Found by running the gate before releasing, not by reading it. CI never saw
  it, having `pytest-timeout` installed, so the array was never empty there —
  a failure that only appears on the machine the fallback exists for. Fixed
  with `${timeout_args[@]+"${timeout_args[@]}"}`, the portable spelling.

### Changed

- **The gate was written three times and the copies disagreed.** `CONTRIBUTING`
  listed commands to copy-paste, `.githooks/pre-push` ran its own variant, and
  `.github/workflows/ci.yml` ran a third. The hook's promise is that a red
  local state never reaches CI, and it cannot keep that promise while running
  something else: it enforced a coverage floor CI also enforced, skipped a
  consistency check CI did not skip, and passed `-m ""` to wake integration
  tests this project does not have (no test here carries a marker, so the flag
  selected exactly what plain `pytest` selects; the comment explaining it
  described another project's suite).

  `scripts/gate.sh` now holds the commands, with one stage per question:
  `lint`, `types`, `tests`, `version`. CI calls them one at a time so a
  failure is named by the step that failed; the hook and the contributor call
  the script with no argument and get all four. The hook keeps the one thing
  that is genuinely its own, which is *where* the gate runs: a throwaway
  worktree holding the commit being pushed, not the working directory.

  Two stages sit outside the default sweep because their verdict depends on
  the environment rather than on the commit. `deps` (`pip check`) is sharp in
  CI's throwaway venv, which holds this project and nothing else, and useless
  in the shared conda environment a developer works in, where it reports a
  dozen unrelated projects disagreeing about numpy; a stage that is red for
  reasons the commit cannot fix is one people learn to skip, and the only way
  to skip it is `--no-verify`, which skips the lint and the tests with it.
  `package` is the build, described below.

  `types` is in the sweep but degrades rather than lying. mypy aborts the
  whole run when a *dependency's* stubs will not parse, and that is ordinary
  on a developer machine: `requirements-dev.txt` caps numpy below 2.5 because
  its stubs use PEP 695 syntax mypy rejects under this project's
  `python_version = "3.10"` target, so a shared environment holding another
  project's numpy 2.5 cannot type-check this one. When every error mypy
  reports lies outside the package, the stage says the environment could not
  answer and leaves the verdict to CI; one error inside the package and it
  fails, as it should. Verified both ways.

- **CI built a wheel on every commit to prove a docstring had not broken the
  sdist.** The build step pulled Git LFS, installed `build` and `twine`, made
  a distribution and weighed the ONNX model inside it, on every push, when
  none of that can be invalidated by editing a function body.

  It now lives in its own `packaging` workflow that watches the inputs which
  *can* make a wheel wrong: `pyproject.toml`, `MANIFEST.in`,
  `requirements.txt`, and the four package-data directories. Plus
  `workflow_dispatch`, for asking on purpose. There is deliberately no tag
  trigger: `on: push: tags:` would fall under the same `paths:` filter as the
  branch trigger, and a tag pointing at an already-pushed commit introduces no
  files, so the run would be skipped silently. It needs none, because a
  release bumps the version in `pyproject.toml` and that commit fires the
  workflow before the tag exists.

  The per-commit lane keeps lint, types, tests and the version/CHANGELOG
  check, and drops `lfs: true` with the build (the suite never opens the
  model; onnxruntime is mocked, not installed). The pip cache is now keyed on
  `pyproject.toml` as well as `requirements-dev.txt`, so a dependency edit
  stops restoring a stale wheel set, and both workflows carry a
  `timeout-minutes` so a hung job is cancelled by the clock rather than
  holding a runner for six hours. `actions/checkout` and
  `actions/setup-python` move to v7, off the deprecated Node 20 runtime.

  `.mypy_cache` is carried between runs, which was the second largest item in
  the lane after installing: mypy spent 13 seconds of a 69 second job
  re-reading stubs it had read the run before. The key is pinned to the
  dependency set, since stubs are what is cached and a dependency edit must
  not restore a cache describing the versions before it.

  Measured across the change, per commit: **70s to 43s**, with the build and
  the Git-LFS fetch gone from the lane and the type check down from 13.0s to
  0.4s. Coverage on Linux went from 89.26%, which was failing the 90% floor,
  to 92.51%.

- **`scripts/gate.sh package` builds into a temporary directory**, not `dist/`.
  The command it replaces began with `rm -rf dist`, which is defensible in a
  container and a trap on a laptop, where `dist/` may hold a release somebody
  else is in the middle of.

- **`storage` ranked resident sets by how much memory they used.** The comment
  argued the case — "among sets that fit, the one using the most memory is the
  most capable" — and it is a proxy, not the thing meant: a 20 GB model
  scoring 70 is not a better companion than a 16 GB one scoring 85. Measured
  on the bundled catalog at a 48 GB budget, the old rule's top answer was
  `qwen3:32b-q8_0` + `qwen3-vl:14b` at **score 232.7, 47.9 GB**, while
  `qwen3:32b-q4_k_m` + `qwen3-vl:32b` at **score 236.0, 47.2 GB** came fifth.
  It preferred the heavier, weaker set, which is the proxy failing in exactly
  the direction that costs the reader something.

  Sets are now ranked on benchmark score, with total memory as the tiebreak
  and model id below that. Keeping memory as the *second* key is what makes
  this safe rather than disruptive: hundreds of entries from the Ollama
  library publish sizes and no leaderboard results, and for a catalog where
  nothing is scored the order is byte-for-byte the one it always was. Each row
  now reports `total_score`, and both CLIs print it first — a list ordered by
  an invisible key asks the reader to take the order on trust.

  Kinds are not scored on one axis, so the score is read per kind: `general`
  for a text model, `vision` for a vision model, `mteb` for an embedder
  (asking an embedder for a general score returns nothing, which would have
  ranked every embedder identically). The sum mixes figures from different
  leaderboards, so it orders sets against each other and is not a measurement;
  the docstring says so.

  The branch and bound still holds, on the new composite. The differential
  test against the exhaustive oracle was extended with scores and caught a
  real defect in the process: on sets tied in both score and memory, the heap
  that keeps the best `limit` compared model ids in the opposite direction to
  the published order, so the set that should have been returned was the one
  discarded. Hence `_Set`, whose ordering is written out once rather than
  inferred from tuple comparison.

- **`storage` planned resident sets by enumerating every combination, on a
  premise the same release had already killed.** The comment said it plainly:
  "the catalog is small (tens of entries), so an exhaustive product is both
  exact and instant... if it ever grows to thousands this wants a bound, but
  pretending to need one now would be guessing at a problem nobody has."
  `catalog update --ollama` shipped in that release and makes it 420 entries.
  Measured against the real library index: 342 LLMs x 75 VLMs x 3 embedders =
  **76,950 combinations, 2.8 s, 230,850 calls to `model_footprint_gb`** — the
  cost is cubic, so an embedder count rising from 3 to 30 would make it 28 s.
  The problem stopped being nobody's.

  Replaced with a branch and bound over kinds sorted heaviest-first, which is
  **exact** rather than approximate — the same rows, in the same order. Two
  bounds carry it: a branch whose remaining kinds overrun the budget even at
  their lightest is skipped, and once `limit` results are in hand, a branch
  that cannot beat the weakest of them even at its heaviest ends the scan of
  that kind outright, which is sound precisely because the entries are sorted
  heaviest-first. Candidates are also sized once each instead of once per
  combination, which is where most of the old time actually went.

  **2.8 s to 2 ms on the same input**, and 230,850 sizings to 840. The new
  tests include a 200x200x200 catalog — 8 million combinations, which the old
  code could not have answered at all — and a differential test that runs the
  original implementation as an oracle over 200 randomised shapes, so
  "exact" is checked rather than claimed.

  Equal totals now break ties on model id. The exhaustive version left them in
  catalog order, which was stable only by accident.

### Fixed

- **`usages resolve` crashed on any machine whose memory bandwidth cannot be
  read.** Both CLI twins built the tokens-per-second string before checking
  there was a number to format, so `est_tokens_per_s: None` raised
  `TypeError: unsupported format string passed to NoneType.__format__` and
  took the whole command with it. None is the ordinary value there, not an
  edge case: it means no measurement exists for this pair and no bandwidth
  figure could be derived, which is the standing condition inside a container.
  That is where it was found, in CI, where it had been failing every run for a
  day while passing on the laptop that wrote it.

  Both twins now borrow `recommend._fmt_tps`, which already handled the absent
  figure correctly and was two lines away from the two that did not. One
  formatter cannot disagree with itself.

  `_fmt_tps` returned `-` for any falsy value, so a measured **0.0 tok/s**
  (a stalled daemon, the single most alarming answer it can give) printed as
  the same dash that means "nobody asked". It now tests `is None`. This is
  the defect family `scripts/measure_absent_vs_zero.py` exists to count, and
  reusing the function would have spread it rather than contained it.

- **A brief saying it does not need schemas was ignored on the local path.**
  `structured_output` is documented as a brief key — `resolve`'s docstring
  lists it, the README's local example shows it — and `_resolve_cloud` reads
  it as an override. `_resolve_local` never did.

  The gate itself is right by default: the helper routes its own tasks through
  a JSON schema, so a model that cannot honour Ollama structured output is
  demoted out of auto-selection. But `resolve` builds an engine for a
  *downstream consumer*, and one whose job needs no schema was saying so in
  its brief and being overruled. Demonstrated: a brief with
  `structured_output: false`, a catalog holding a non-schema model scoring 92
  and a schema-capable one scoring 74, both fitting comfortably — the brief got
  the 74.

  `require_structured` now threads from the brief through `recommend` into
  `rank`, `select` and `_pick_sufficient`, and the "will fail on schema-driven
  tasks" warning no longer fires for a job that never wanted them. Only an
  explicit `false` relaxes the gate: a brief that says nothing keeps today's
  behaviour, because widening on behalf of a caller who did not ask is the
  wrong direction. The engine file still reports the chosen model's real
  capability, so nobody is misled about what it can do.

- **Not holding a cloud key was logged as an error.** `osh.get_config` logs at
  ERROR before raising when a key is absent, and absent is the ordinary state
  for a provider you do not use — `_cloud_api_key`'s own contract is that `""`
  means no key, and `chat` falls back to the local model on exactly that. The
  new `providers` command therefore printed one red ERROR line per
  unconfigured provider for a perfectly normal situation. A red that lies
  costs the same credibility as a green that lies. Narrowed to that one
  lookup, so a real failure elsewhere still surfaces.

- **`pull` wrote two environment variables the tool then ignored.**
  `pull.write_env` persists four values into `~/.best-engine-ai-helper/env.sh`
  and `config.json`; the README and LISEZMOI print that export block and tell
  the reader to source it. Two of the four worked. `BEST_LLM_TEXT` and
  `BEST_LLM_VISION` resolve through `config.py`; `BEST_LLM_BACKEND` and
  `BEST_LLM_BASE_URL` were read by nobody, because `llm.py` consulted only the
  legacy `SPREZZATURE_*` spelling.

  Demonstrated: `pull` writing `vllm` at `http://gpu-box:8000`, with the file
  sourced exactly as documented, left the transport on `ollama` at
  `http://localhost:11434`. Anyone serving on a non-default port, or with
  vLLM, was silently routed somewhere else.

  Half a block working is what made it hard to notice — the model tags were
  honoured, so the file looked like it was being read. The gap had already
  been found and closed once on the other half: `_text_model`'s docstring says
  it "closes the old gap where the transport read only `SPREZZATURE_LLM_TEXT`
  and ignored a fresh `pull` selection persisted under `BEST_LLM_TEXT`". The
  identical shape in the two connection settings was left behind.

  Both now resolve through the same `config._resolve` chain as the model tags
  — canonical env, then legacy env, then `config.json`, then the built-in
  default — so a value set any documented way is honoured, and nothing that
  worked before changes. `llm.py`'s environment-variable documentation now
  leads with the canonical spelling it actually writes.

- **The GUI localised its labels and not its numbers.** Every string goes
  through `locales/i18n.yaml`, but the figures beside them were written with
  `toFixed` and a bare `$` prefix, which are English conventions whatever the
  page language is. The French GUI therefore read `47.2 GB`, `$0.0020` and
  `73%` where French writes `47,2`, `0,0020 $US` and `73 %`. `Intl` does the
  whole job in the browser with no dependency: the page is now given the
  locale it actually resolved to — not the one that was asked for, which may
  have fallen back — and every figure goes through a formatter built from it.

  Pinned as "no raw formatter survives in the rendered page", because that is
  the property that rots: a new cell written with `toFixed` would be wrong in
  exactly one of the two languages, which is the kind of defect nobody
  reports.

### Added

- **`scripts/gate.sh`**, the single definition of the gate, called by the
  pre-push hook, by CI one stage at a time, and by hand.

- **Tests for `storage`, `doctor` and (in the argparse twin) `providers`,
  through both command-line surfaces.** Three handlers shipped with no test
  reaching them through a CLI at all, so the twin could have been wired to
  nothing and still looked green. With the throughput regression test, Linux
  coverage moves clear of the 90% floor it was failing by three quarters of a
  point, rather than meeting it by a rounding.

- **`providers`, a CLI command for a feature only the GUI could reach.** This
  package claims to route on the keys you actually hold, and
  `cloud_catalog.provider_status` answers "which cloud providers are usable
  right now, and for the others, the variable to set". It shipped in 1.5.0
  served at `/api/providers` — and nowhere else. The CLI is this project's
  primary surface and it could not ask the question. Same shape as the Arena
  reader that was written, tested, and wired to no command.

  `providers` prints one row per provider with the variable name to set, or
  `--json` for a script. It never prints a key value, only whether one
  resolved — the point of storing `api_key_env` rather than the key is that
  the secret stays out of every report, and that holds here too.

- **The three cloud brief keys that only the API docstring knew about.**
  `vlm_model`, `base_url` and `api_key_env` are read by `resolve` and were
  absent from the README's and LISEZMOI's brief sections, so the only way to
  learn them was to read `engine.py`. Documented where the reader is told to
  look, including the part that is not guessable: with `kind: both` and only
  `model` pinned, the same model serves both slots.

- **`settings.yaml.example` documents every provider the catalog ships.** It
  listed `MISTRAL_API_KEY` alone while the bundled catalog carries four
  providers, so a reader holding an OpenAI key had to find the name in an
  internal map in `engine.py`. The mechanism was never broken — any
  `api_key_env` name resolves — but the file the README tells you to copy is
  where that is supposed to be visible. Two tests now make it an invariant
  rather than something to remember: every shipped provider must resolve a key
  variable name, and that name must appear in the example file.

- **Tests for `i18n`, which had none.** The module is the single source of
  truth for every GUI string and every model-facing prompt, and the invariants
  behind that claim were guarded by nothing. Audited by hand first and all
  four held — 89 GUI keys with complete `fr`/`en` parity, every key `gui.py`
  asks for present, all eight prompt templates resolving, and no user-visible
  literal bypassing the file (only the product, package and author names,
  which are not translated). They are now tests, because an invariant that
  holds today and is guarded by nothing is the one the next feature breaks —
  and the GUI's fallback is what makes it worth guarding specifically: a
  missing English translation would quietly show French rather than fail.

- **The documented way to switch the safety gate from `warn` to `block` did
  nothing.** `safety.py`'s module docstring tells the operator how to tighten
  the policy once the classifier has earned trust: "Raise the bar
  (`DEFAULT_ACTION = \"block\"`) once you trust it on your traffic."
  `check_text` and `check_image` took `action: Action = DEFAULT_ACTION`, and a
  default argument is evaluated **once, at import**. Reassigning the constant
  afterwards therefore never reached either check. Demonstrated: with
  `DEFAULT_ACTION = "block"` set and a text scoring 0.99, the call returned
  `flagged: True`, logged the warning, and raised nothing. `DEFAULT_THRESHOLD`
  was frozen the same way, so the bar could not be moved in either direction.

  Both constants are now read inside the function body, with `None` meaning
  "take the constant as it stands at call time". An explicit argument still
  wins, so no call site changes behaviour. Four tests pin it, including that
  the shipped `warn` policy still passes flagged text through — the point of
  the default is that a false positive should not break a legitimate call.

  Worth separating from the other entries here: this one is not a parameter
  that went unwired between two layers, it is a **control that was documented,
  reachable and inert**. That is the worse shape, because the absence of a
  safety control gets noticed and the presence of a broken one does not.

- **`report` sized every pick against Ollama, including on the machines where
  this tool serves with vLLM.** The command passed neither `backend` nor
  `installed` to `recommend()`, so it always took the defaults: Ollama Q4
  footprints, and no knowledge of what is already on disk. On Linux with a
  discrete GPU — the configuration `engine.default_backend` sends to vLLM, and
  the one the README calls "the real production case" — the report and the
  engine file `resolve` builds therefore disagreed, with the report on the
  optimistic side. Measured on a 48 GB GPU against the bundled catalog: the
  report offered `qwen2.5-coder:14b` at **9.9 GB** while the engine it would
  actually build picked `qwen2.5-coder:7b` at **16.1 GB**. A bigger model at a
  smaller claimed footprint — vLLM loads FP16 weights, roughly three times the
  Q4 figure, which is the "unrealistic recommendation" `model_footprint_gb`'s
  own docstring says it guards against.

  `report` now takes `--backend {auto,ollama,vllm}` like `resolve` and
  `candidates`, defaulting to `auto`, and asks the daemon which tags are
  present when the backend is Ollama — the same condition `storage` already
  used. That second half also switches on the already-pulled tiebreak, which
  had only ever fired through `engine.resolve`: the command most people run
  could not see it.

- **A catalog entry with no size at all fitted every machine, and was
  recommended on the ones where nothing real fitted.** `model_footprint_gb`
  returned `0.0` for an entry carrying neither `ram_gb` nor `size_b`, and
  `0.0 GB` does not mean "unknown" — it means "fits anywhere". The entry
  therefore passed the fit test, won the leanest-candidate tiebreak in
  `_pick_sufficient`, won `select`'s "smallest model" fallback, and won all
  three of the equivalent steps in embedder resolution. On a 4 GB machine,
  with a real 8B model that genuinely did not fit, the phantom was the
  recommendation.

  Reachable from the shipped sources, not only in theory: ApXML does not carry
  a Q4 VRAM figure for every model, `normalize_apxml_spec` skipped only
  records without a slug, and a `None` went straight into the cache.

  This is the defect family `scripts/measure_absent_vs_zero.py` was written to
  hunt — and the line, `score.py:172`, was **on its survivor list**. The hand
  review cleared all thirteen survivors on the grounds that "the fallback
  equals the value it would swallow". For this one it does not, which is worth
  recording: the detector did its job, and the judgement call after it is
  where the defect got through.

  Fixed at the root rather than at the four call sites. An entry that cannot
  be sized now reports an infinite footprint, so it fails every fit test by
  construction; `is_sizeable` and `sizeable_only` name the rule, and `rank`,
  `select` and embedder resolution drop such entries **with a warning** rather
  than silently, since a pool that quietly shrinks reads as one that was fully
  considered. `normalize_apxml_spec` now skips a sizeless record at ingest,
  which is the rule `ollama_library.to_specs` already stated and already
  followed: an entry whose size is unknown cannot be sized.

  `model_footprint_gb` had no test of any kind before this, including none for
  the FP16 sizing the README advertises as what keeps a vLLM pick realistic on
  the real GPU. It has eight now. An existing test caught the one regression
  the change caused — an unsizeable entry briefly estimated at a confident
  `0.0 tok/s`, where the honest answer is no estimate at all.

- **Every surface printed a measurement as though it were an estimate.** The
  candidate row carries `tps_basis` now (`"measured"` / `"estimated"` /
  `None`), the engine file records it alongside `est_tokens_per_s`, and the
  Markdown report, the GUI table and the CLI engine summary mark a measured
  figure with a trailing `*` — the notation the `candidates` command already
  used and the README already documented, rather than a second one invented
  for the same fact. The "fits but decodes slowly" warning now says *measured
  at* when it was, instead of inviting the reader to discount a real number as
  a guess.

- **The measured-throughput gate never fired on the path everything uses.**
  1.5.0 shipped the claim that a model *measured* too slow on this machine is
  demoted out of auto-selection, "exactly as one that does not fit in memory
  is" — the thing this package does that tools which measure and report do
  not. `recommend()` is the path the CLI, `engine.resolve`, the HTTP API and
  the GUI all take, and on that path the gate was off. Two independent
  defects, either of which alone was enough:

  `recommend()` called `rank()` without `min_tps`, which defaults to `None`,
  meaning "no floor" — so `rank` collected the measurement and then had
  nothing to compare it against. It also omitted `bandwidth_gbs`, so `rank`
  could not estimate for the unmeasured candidates either.

  `_candidate_row()` then recomputed the bandwidth estimate instead of reading
  the `_tps` / `_tps_basis` that `rank` had already resolved, so the
  measurement could not reach `comfortable` — and `comfortable` is what builds
  the pool `_pick_sufficient` chooses from. Even with the ranking fixed, the
  anti-greed pick would have reinstated the slow model, because it takes the
  **leanest** candidate within a few benchmark points, and the model too slow
  to use is very often the small one. The hazard was already named in
  `cli.py`, where the `candidates` command carries the comment "recomputing
  the estimate here would quietly discard it"; the other path did precisely
  that.

  Demonstrated rather than argued, and now pinned by four tests: a model
  measured at **8 tok/s** against a 20 tok/s floor was selected and reported
  as `comfortable: true` at its estimated **43 tok/s**. There was no test
  anywhere for the measured demotion — `min_tps` appeared in no test of
  `score.rank` at all, which is how a headline feature shipped switched off.

## [1.6.1] - 2026-10-20

### Fixed

- **The wheel shipped none of the package's data, so an installed copy had an
  empty catalogue.** `models.yaml`, `hardware.yaml`, `usages.yaml`,
  `pricing.yaml` and `locales/i18n.yaml` sat *beside* the package, next to
  `pyproject.toml`. `[tool.setuptools.package-data]` listed all five by name —
  and matched nothing, because those patterns resolve relative to a **package
  directory**, never to the repo root. A declaration that looks correct and
  covers nothing is why this survived every release up to 1.5.0.

  Measured on the published 1.5.0 wheel, in a clean virtualenv with an empty
  `HOME`: `load_catalog()` returned **0 entries** and `i18n.gui_strings()`
  raised `FileNotFoundError`. The package's whole purpose — pick the best
  local model — could not work for anyone installing it from PyPI.

  Two things hid it. A repo checkout has every file exactly where the code
  looked, and a developer machine has a populated `~/.best-engine-ai-helper`
  cache that `load_catalog()` merges *over* the missing seed, so the entry
  count looked plausible (20) while the seed contributed nothing.

  The data now lives in `best_engine_ai_helper/data/` and the locale file in
  `best_engine_ai_helper/locales/`, both inside the package, with
  package-data patterns that reach them. Verified the same way the defect
  was: clean virtualenv, empty `HOME`, **20 entries and 89 GUI keys**.

  `tests/test_packaging.py` now asserts the property that survives
  packaging — every runtime data file resolves under the importable package
  directory, the build declares it, and nothing is left at the repo root.

**1.6.0 was tagged but never published to PyPI**; this is the first release
carrying the i18n delegation described below.

## [1.6.0] - 2026-10-20

### Changed

- **`i18n` now delegates to `os_helper.Locales` instead of re-implementing
  it.** Parsing, locale resolution and validation were written here and
  written again in another member of the suite — two packages holding two
  answers to the same question, which is how they drift. They now come from
  the loader shared by the whole suite (os-helper 2.4.0, hence the raised
  floor).

  What stays in this module is the part os-helper must not know: that a
  `prompts` section exists at all, and what a prompt's fields mean. The
  generic mechanism belongs in the foundation, the domain vocabulary belongs
  where the domain is. `meta()`, `gui_strings()` and `prompt()` keep their
  exact signatures, so no call site moved.

- **`locales/i18n.yaml` declares `meta.unlocalized_sections: [prompts]`.**
  That section is keyed by ROLE — `system`, `user`, `text` — and not by
  locale, because this product authors one model-facing language rather than
  translating it (references/CODING.md 21.3.3). The declaration is what tells
  a validator so. Without it the shared validator read every role name as an
  undeclared locale and every key as missing both translations: **38 findings
  about translations that were never meant to exist**. With it, none.

### Added

- A test asserting the locale file satisfies the shared validator outright
  (`problems() == []`), which is the section 21.3.7 check and is now a single
  line. It covers the faults nobody thought to write a test for, which the
  four hand-rolled checks beside it cannot.

## [1.5.0] - 2026-10-20

### Fixed

- **Coverage had slipped under the floor, and nothing local could see it.**
  CONTRIBUTING documents a 90% floor that CI fails on; six modules added in
  this release took it to **89.54%**. The pre-push gate ran the tests but not
  the coverage check, so a gate promising "a red local state never reaches CI"
  was blind to the one thing CI would have failed on. It now checks the floor
  in the same run, which is where the check belongs.

  Brought back to **90.38%** by covering paths that were worth pinning rather
  than by chasing lines: the Ollama library fetch (one bounded request, `limit`
  keeping the most popular families, a family listed twice recorded once — the
  real index repeats some — and navigation `<li>` elements ignored), and the
  Arena history mirror, which had no tests at all despite being the only source
  that still answers (newest snapshot wins, each board lands on the axis it
  measures, an unmapped board contributes nothing rather than guessing, a dead
  mirror returns None rather than raising, a malformed board costs that board
  and not the lot).

- **The pre-push gate judged the working directory instead of the commit being
  pushed.** It was wrong in both directions, and both were observed rather than
  argued. *False failures:* `ruff check .` walks the filesystem, so untracked
  files belonging to another session failed your push for a commit that did not
  contain them — three concurrent sessions blocked each other this way on
  2026-10-19. *False passes:* a lint error that is committed but already fixed
  in the working tree sailed through, because ruff read the fixed file on disk
  while the broken version was what got pushed.

  The second was the one nobody had spotted, and it is the worse of the two: a
  gate that promises "nothing red reaches CI" while not looking at what it
  sends. Narrowing to tracked files would have fixed only the first.

  The hook now checks out the pushed commit into a throwaway worktree and runs
  the gate there, which answers the question a pre-push hook is actually for —
  "is what I am about to publish clean?" — and gets isolation from concurrent
  sessions for free, by construction rather than by filtering. It also says so
  when your working tree differs from the commit it judged, so a green gate on
  a dirty tree is not a surprise.

  Deliberate, because the alternative is worse than strictness: a gate that
  fires wrongly teaches people to reach for `--no-verify`, which skips the lint
  and the tests together. Verified here — the sweep is the same 282 passed /
  4 skipped in the worktree as in the working tree, so no gitignored artifact
  is needed to run it.

- **An unreadable keychain took down a cloud call instead of falling back.**
  `_cloud_api_key` caught only `ImportError` around its `keyring` lookup, but
  `keyring.errors.NoKeyringError` is not one — it is what a headless Linux box
  with no secret service raises on *every* lookup, and a locked macOS keychain
  raises too. The call sits before the failover loop's `try`, so the exception
  escaped `chat` entirely rather than degrading to the local fallback. The
  engine chain exists precisely so a cloud problem falls back to the
  always-available local model, and an unreadable key store is a cloud problem.
  "No key found" was already a normal outcome reported as `""`; an unreadable
  store is the same outcome with a different cause, so it now gets the same
  answer and a line in the log.

- The GUI escapes the values it interpolates into HTML. Every panel builds
  markup with template literals and assigns it through `innerHTML`, and model
  ids, provider names and ledger rows went in raw. Nothing here is
  attacker-controlled in a loopback, single-user GUI, so this is hygiene rather
  than a patched breach — but the catalog can now be refreshed from a remote
  source, and "it happens to be safe today" is not a property that survives a
  new one. One helper is cheaper than re-auditing every call site each time an
  input arrives from somewhere else.

- **A streamed call leaked its connection and was invisible to the ledger.**
  `chat_stream` never closed its streaming response, so a caller that stopped
  consuming early — the documented use, speaking chunks as they arrive and
  stopping when interrupted — leaked a socket every time. It also emitted no
  observer event, so streamed calls never reached the SQLite ledger that
  `activity` and `/api/activity` report: a user who streamed all their work
  would have read an empty ledger and concluded the tool did nothing. Both are
  now handled in a `finally`, which also runs when the generator is abandoned.

  The final `done` event carries `eval_count`, `eval_duration` and
  `prompt_eval_count` — the same counts the whole-answer path records — and
  they were being discarded. They are now read, so a streamed call is costed
  like any other and `throughput.Meter` can measure one. A stream cut before
  that event reports `None` rather than zero: zero reads as a measurement.

- **`gemma3:12b` could be reported as already installed when the daemon held
  only `gemma3:latest`.** `pull.installed_tags` adds the bare form of a tag
  only when that tag is `latest`, so plain set membership is both necessary and
  sufficient; an extra `name.split(":")[0]` fallback matched any size of the
  family. Introduced in this release's own `doctor`, `storage` and
  already-installed tiebreak. The consequence was worst in `doctor`, which
  would have issued a clean bill of health for a model that fails at the first
  inference call — precisely the failure it exists to catch. `engine.resolve`
  had it right and is unchanged.

- **A catalog refresh could erase hand-curated benchmark scores.** The cache
  overlays the seed by id with a plain dict replacement, so an entry refreshed
  from a source that publishes no benchmarks handed its nulls to a seed entry
  that had real numbers — widening the catalog quietly degraded it. Latent
  until now because ApXML, the only refresh source, keys entries by directory
  slug and never collided with the seed's pull tags; a source that emits real
  tags collides constantly and surfaced it. The overlay is now field-wise: the
  refreshed entry wins, except that a null never replaces a value already
  there, and benchmarks merge per axis so a source silent about an axis does
  not discard it.

- **An unpriced cloud model ranked as though it were free.**
  `blended_price_per_1m` collapsed a missing price to `0.0`, and the cost axis
  inverts price into a score, so an entry nobody had priced came out at the
  best possible cost and won that axis outright. The bundled `pricing.yaml` is
  complete, so nothing was mispriced in practice — but the function was built
  to tolerate absent prices, which means this would have fired silently the
  first time anyone added an entry without them. It now returns `None` for "no
  price at all", distinct from a genuine `0.0`, and the ranker scores unknown
  cost as the *worst* rather than the best: this package's position elsewhere
  is that a figure without provenance is worth less than no figure, and
  pessimism is the safe direction for something that may bill you. Billing on
  one side only stays a real price, and callers that print the figure now say
  "price unknown" instead of "$0.00".

  Found by measurement rather than by reading — see
  `scripts/measure_absent_vs_zero.py`. It is one instance of the family where a
  legitimate value (`0.0`, a directory slug) is mistaken for an absent one,
  which is also what the catalog fix above is.

- **A resolved local engine could name a model Ollama cannot pull.** The
  catalog's own contract says `id` IS the Ollama pull tag, and the
  hand-maintained seed honours it — but the ApXML adapter keys entries by the
  directory's slug (`qwen36-35b-a3b`, `llama-3-70b`), because that is what the
  directory publishes. Those entries then competed in the recommender, won on
  size, and produced `llm.engine.yaml` naming a model `ollama pull` cannot
  resolve. The caller discovered it at its first inference call, usually in
  the middle of a long job. `catalog.servable()` / `catalog.servable_only()`
  now gate the pool by backend before the recommender sees it, and
  `_resolve_local` applies the gate. Deliberately narrow: the discriminator is
  the entry's **source**, not the shape of its id — `gemma3` is a legal tag
  that Ollama resolves to `gemma3:latest`, and vLLM is not gated at all
  because a missing `vllm_id` already falls back to the raw tag with a
  warning. An entry may also declare `backends: [...]` and that wins. A pool
  emptied by the gate warns rather than raising, by the same rule as an empty
  catalog.

- **The landscape scored a limitation this release had already removed.**
  `LANDSCAPE.md` and `PAYSAGE.md` rated catalog breadth ⭐⭐ and explained it
  with provenance discipline: twenty hand-maintained entries, each carrying a
  `source:` and a `fetched_at`, because an entry without provenance is worth
  less than no entry. The explanation was a misdiagnosis, and `catalog update
  --ollama` — added in this same release, six hours after those pages were
  written — proved it: 420 pullable tags in one request, every one of them
  carrying the same `source:` and `fetched_at` as the seed. Provenance was
  never what held the catalog at twenty; ApXML naming models by the paper's
  slug, which `ollama pull` cannot resolve, was.

  Re-scored to ⭐⭐⭐⭐ against `llmfit`'s ⭐⭐⭐⭐⭐, with the limit that does
  still hold stated instead: those 420 entries carry null benchmarks, so they
  rank below every scored model, and what the tool can **rank on quality** is
  still the twenty curated entries. ⭐⭐⭐⭐ rather than ⭐⭐⭐⭐⭐ because
  `llmfit` ships its hundreds in the box, where here they are one command and
  one request away. The column is still one this project loses, which is the
  point of keeping it on the map.

  Both maps were regenerated from the corrected tables, so the figures match
  what the tables say; `assets/landscape.yaml` and `assets/paysage.yaml` are
  now committed alongside them, which makes the coordinates and axis loadings
  quoted in the prose checkable rather than merely quoted. `standpoint` names
  the axis poles with a model, so the names moved between runs — the pages now
  print the names *and* the loadings underneath them, and say which of the two
  is stable.

  The pattern is the one this release keeps running into: a page that explains
  a weakness asserts a *cause*, and a cause goes stale exactly like a number
  does. This one outlived the limitation it described by a day.

- French prose across `LISEZMOI.md`, `PAYSAGE.md` and `EXEMPLES.md` no longer
  puts a comma before `et` or `ou`. Thirty-two occurrences, each rewritten
  rather than stripped where dropping the comma alone would have read badly.

### Added

- `scripts/measure_absent_vs_zero.py`: counts how often a legitimate value
  could be read as an absent one, across three candidate rules. It exists
  because the temptation is to turn such a rule straight into a lint gate, and
  the only way to know whether a rule is a gate or just noise is to count
  first. Measured here: `or` on a numeric flags 14 lines (reviewable, and it
  found the pricing defect above), `.get(k)` with no default flags 266, and
  `if <name>:` flags 66. One rule in three survived, so this reports and does
  not gate — a check that fires 266 times teaches people to ignore it.

- `scripts/validate_calibration.py` tests the claim the calibration rests on,
  instead of restating it. Measuring one model is supposed to improve the
  estimate for others; that is a statement about the world, not about the code,
  so no unit test can settle it. The script measures several models, calibrates
  on each, predicts the rest, and prints the failures as plainly as the
  successes.

  It held: on an Apple M2 Max the correction beat the raw estimate in every
  direction tried, cutting the error from 64-118% to 17-25%. It also showed the
  claim was being overstated here — ratios ranged about 0.46 to 0.61 across
  models and across repeated runs of the *same* model, so the prose, docstrings
  and diagram said "0.54, i.e. 86% optimistic" with more precision than the
  measurement supports. All of them now give the band and the residual error,
  and say the honest version: calibration moves an estimate from wrong by a
  factor of two to wrong by about a fifth. It does not make it right.

  Two design choices already in place are what that spread justifies: the
  factor is a median over several measurements rather than one sample, and a
  real measurement always outranks a calibrated estimate.

- The CLI parity test now pins **flags**, not just command names. The suite
  already asserted that both surfaces expose the same commands, which is the
  cheaper half: drift actually happens one option at a time, when a flag is
  added to the click twin and forgotten on the argparse one (or the reverse).
  That is a one-line mistake nothing else caught, and it nearly shipped twice
  in this release. Two differences are allowlisted with their reasons, and a
  third test fails if an allowlisted entry stops being a real difference — an
  allowlist nobody prunes quietly stops being a list of exceptions.

- `llm.embed()` takes a `model`. The catalog ships four embedders
  (`nomic-embed-text`, `mxbai-embed-large`, `snowflake-arctic-embed2`,
  `bge-m3`) and `usages.resolve_usage` already picks between them on MTEB score
  and available memory — but nothing wired that choice to `embed()`, which
  silently used the configured *chat* model and still does by default.

  The default is left alone deliberately rather than quietly improved: vectors
  from two different models are not comparable, so swapping the model under an
  existing store poisons every similarity it computes. A corruption nobody is
  told about is worse than a weak default that is written down, so the caveat
  is now in the docstring and the override is available.

- **The GUI remembers your preferences.** Headroom, the quality-versus-cost
  weight and the live-load toggle persist to
  `~/.best-engine-ai-helper/preferences.yaml` via `GET`/`POST
  /api/preferences`, and the page reads them back on load rather than keeping
  a second copy of the state.

  Deliberately *not* written to `settings.yaml`. That file holds API keys, and
  a browser form should never be in a position to rewrite a file containing
  secrets — one naive dump and the keys are gone. Secrets and preferences also
  have different lifetimes and different blast radii, so they get different
  files. A form posts strings, so each value is coerced to the type its default
  implies on the way in; one that cannot be is skipped with a warning rather
  than stored broken, and an unknown key is ignored rather than accumulated.

- **`catalog update --ollama`: widen the catalog with tags Ollama can pull.**
  The catalog was stuck at twenty *servable* models, and the reason was not
  scoring: ApXML can add hundreds, but it names them by the paper's slug, which
  `ollama pull` cannot resolve, so those entries are vLLM-only. The official
  library at ollama.com publishes families, capabilities and the sizes each
  ships — and a family plus a size is a real pull tag, `qwen3` + `8b` being
  exactly the `qwen3:8b` the seed already uses. 256 families expand to ~420
  pull tags from a single request, since the index lists sizes inline.

  It invents nothing. The library publishes no benchmarks, so entries land with
  null scores and rank *below* every scored model — reach widens, ranking does
  not change until a scored source fills them in. Sizes are derived from a
  constant measured against the seed's own fourteen Q4 entries rather than
  guessed (0.646 GB per billion parameters for text models, 0.714 for vision
  ones, since an image tower is genuinely heavier), which lands within about 5%
  of the seed's known-good figures. A family listing no size is skipped rather
  than sized as zero, which would have made it "fit" every machine.

- **The GUI shows which cloud providers are usable, and why the rest are not.**
  This package claims to route on the keys you actually hold, and that claim is
  only worth something if you can watch it being applied. Unavailable providers
  are dimmed rather than hidden — the point is to show the rule, not to quietly
  shorten the list — and each one names the variable to set and where it is
  looked for. New `GET /api/providers` and `cloud_catalog.provider_status()`
  behind it. Only *whether* a key resolved is reported, never a key value: the
  reason descriptors store `api_key_env` rather than the secret is that the
  secret stays out of every screen, and that holds here too.

- **`storage`: plan capacity, including what fits in memory *together*.**
  "How many models fit on my SSD" is a subtraction and is answered, but the
  question behind it is usually different: a working setup is a text model, a
  vision model and an embedder, and what decides the day is whether they can be
  resident at once rather than taking turns. Each may fit alone while the trio
  does not, and no per-model view would ever say so. Disk size and working set
  are kept as the separate budgets they are, a floor is held clear for the OS
  rather than filling the disk to the last gigabyte, and the plan is built only
  from models the backend can actually load — planning around an unpullable
  name is worse than not planning.

- **`doctor`: compare what was resolved against what the daemon serves.**
  "Resolved" and "runnable" are two different claims and they drift apart
  quietly — an engine file is written once, the daemon it names is mutable, and
  `ollama rm` leaves no trace in the descriptor. Until now the gap surfaced at
  the first inference call, typically mid-job. It diagnoses only and never
  re-resolves, because re-resolving would hide the drift it exists to show; an
  unreachable daemon and a non-Ollama backend are reported as "cannot tell"
  rather than passed. Exits non-zero when anything named cannot be served now.

- At comparable quality **and** comparable footprint, a model already on disk
  now wins over an equivalent download. Deliberately the weakest key in the
  sort: quality is compared first, then footprint to the nearest gigabyte, and
  only inside that rounding does "already here" decide. The two costs are not
  the same kind of thing — a gigabyte of footprint is paid on every run, a
  download once — so leanness stays primary and this never promotes a worse or
  heavier model to save a fetch. The engine resolver already asked the daemon
  what it had; it now asks before ranking rather than after, so the answer can
  inform the choice instead of only annotating it.

- Re-measuring a model keeps the **fastest** sample rather than the latest.
  Found by running the proof while three test suites were competing for the
  machine: the same model measured 15.2 tok/s idle and 8.7 tok/s contended, and
  the contended figure alone produced a correction of 0.31 against the idle
  run's 0.54. Since the quantity being calibrated is a bandwidth *ceiling*, and
  contention can only push an observation below the hardware's real capability,
  the fastest sample is the closest to what is being predicted.
  `record(..., replace=True)` overrules this when the hardware genuinely slowed.
- Two hand-authored SVG diagrams in `assets/diagrams/`, embedded in both
  READMEs: the predict → choose → prove loop with the real figures on it, and
  why every LM Arena source fails today.

- **Decode speed is now measured, not only estimated.** This package argued
  for measuring over assuming while estimating the one thing a competitor
  measured, which was the most awkward contradiction in it. `throughput.Meter`
  wraps the chat callable handed to the Ralph gates during `pull` and
  `validate`, so the figure falls out of inference that was already happening
  — no extra call, no new command, and `validate_llm.py` / `validate_vlm.py`
  are untouched. Measured first result: `gemma3:12b` on an Apple M2 Max decodes
  at **15.2 tok/s** where the bandwidth model predicted **28.3**.
- Measurements prefer Ollama's `eval_duration`, the decode phase as timed by
  the daemon, over the caller's wall clock, which also contains prompt
  processing, HTTP, and queueing. Every measurement records which clock it came
  from, and only the daemon's can disqualify a model: a wall-clock figure
  understates decode speed, and understating is what would reject models that
  run perfectly well. `llm.chat`'s ledger events carry `gen_ms` for the same
  reason.
- **`min_tps` became a real constraint.** Every usage brief already carried a
  throughput floor, and it only ever sorted. A model now *measured* below the
  floor on this machine is demoted out of auto-selection, exactly as one that
  does not fit memory is — the missing half of "fits your hardware". A model
  merely *estimated* below it is annotated and left where it was, so a machine
  that has never run `pull` ranks precisely as it did before.
- **A measurement improves the models you never ran.**
  `throughput.calibration_factor()` is the median measured-over-estimated
  ratio for the machine, and `score.estimated_tokens_per_second` applies it.
  The bias belongs to the hardware far more than to the model, so measuring one
  model pulls every other estimate on that machine toward the truth. Derived
  from the stored measurements rather than kept as separate state, so it cannot
  drift away from them; median rather than mean so one odd model cannot drag
  the machine; and ignored entirely outside [0.2, 3.0], where a bad catalog
  footprint is a likelier explanation than the hardware.

- `catalog update --arena` reaches the Arena adapter from the command line, in
  both CLI twins. It was previously importable and nothing more. The merge
  decision lives in `catalog.merge_arena_axes()` rather than in either front
  end, since the click and argparse CLIs mirror each other 1:1 and a copy in
  each would be two places to drift. A dead mirror is non-fatal — the ApXML
  refresh it follows has already succeeded, and discarding a good catalog
  because someone else's scrape rotted would punish the user for an outage
  they do not own — but a merge that enriched nothing always says so, because
  an axis the user believes is populated is worse than one they know is empty.
- Documented the axis's measured coverage in README and LISEZMOI: 6/10 cloud
  models, 3/20 local ones, every local match a 32B build, and embedders
  unmatchable by construction. Counter-intuitive for something called a
  leaderboard, and silence would leave callers expecting tiebreaks it cannot
  provide.

- **An LM Arena source, and the honesty to say when it has nothing.**
  `sources/arena.py` reads conversational Elo from community mirrors and
  converts it to the same 0-100 scale as the other axes, via the Elo expected-
  score formula rather than a min-max — a min-max rescales every time the
  leaderboard moves, so a cached catalog would silently disagree with a fresh
  one. Staleness is a first-class property: Arena publishes no API, every
  mirror is a third-party scrape, and as of 2026-10 the freshest one is well
  past the bar, so the adapter **refuses and names the reason** instead of
  merging ratings from a previous generation of models. Name matching runs
  five passes from strict to loose (the leaderboard names dated releases,
  catalogs name aliases); an ambiguous prefix is **declined**, because the
  ranker acts on a wrong axis and merely ignores an empty one.
- `score._APP_BENCH_PRIORITY` gains the Arena axes, weighted by position: an
  Elo leads for `chat`, where it measures exactly what is being asked, and
  trails on every execution axis, where preferring agreeable prose to a
  schema-valid query is the known failure. A positional test pins the order so
  a later edit cannot quietly reshuffle it.
- `pull.installed_tags()`: which tags the local Ollama daemon can serve right
  now, best-effort with a short timeout (no daemon is the common case during
  resolution, not an error). `_resolve_local` uses it to record `available`
  per kind, and a `pull:` command when the chosen model is not there yet —
  so "resolved" and "runnable" stop being the same claim.

## [1.4.4] - 2026-10-14

### Fixed

- `safety.scan_text` guarded only `ImportError`, so having `transformers`
  installed but the model unreachable took down the caller. The classifier is
  fetched from HuggingFace on first use: a cold cache with no network, a cache
  path on an unmounted disk, a rate limit or an outage all raise `OSError` from
  `_cached_nsfw_text_classifier()`, and that escaped `scan_text`, escaped
  `check_text`, and failed the whole `chat()` call — for a scan that is
  best-effort by construction. Loading and scoring now sit inside one guard
  that degrades to the keyword heuristic and warns, like the existing
  no-`nsfw`-label path. Same class of bug as the `truncation=True` fix.
- `safety.scan_image` had the same gap, and worse: `_clip_image_embedding`
  fetches the CLIP encoder from HuggingFace and was guarded by nothing at all.
  `_cached_onnx_session()` also caught only `ImportError`, so a present but
  corrupt ONNX head raised through. Encoder fetch, head load and inference now
  degrade to `"unavailable"` with a warning.
- Three regression tests cover the new paths; all three fail against the
  previous code.

## [1.4.3] - 2026-09-03

### Fixed

- `score._benchmark_score`'s default (non-`application`) ranking branch used
  `benchmarks.get("vision") or benchmarks.get("general") or 0`, which treats
  a legitimately-recorded `0.0` benchmark score the same as a missing one and
  silently falls through to a different axis. Switched to explicit
  `is not None` checks, matching the pattern already used in the
  `application`-priority branch a few lines above.

## [1.4.2] - 2026-08-25

### Fixed

- **`default_backend()` picked vLLM for any discrete NVIDIA/AMD GPU
  regardless of OS**, so a GPU on Windows would auto-pick vLLM despite it
  shipping no native Windows wheel (WSL-only), and macOS has no native
  vLLM runtime at all. Now vLLM only wins when both a discrete GPU AND
  Linux are detected — the real production case, where vLLM's
  request-batching/concurrency handling under load beats Ollama; every
  other case (macOS, Windows, CPU-only) falls back to Ollama. Docs and
  CLI help text updated to spell out the three-branch rule and why each
  backend fits each case.

## [1.4.1] - 2026-08-25

### Fixed

- **`safety.scan_text` crashed (not degraded) on any prompt over ~380
  words.** DistilBERT's positional embeddings top out at 512 tokens; the
  classifier pipeline was called with no `truncation=True`, so a longer
  prompt made the model's embedding layer receive more positions than it
  has slots for, and torch raised a bare `RuntimeError` ("size of tensor a
  (602) must match ... 512") instead of the classifier just scoring the
  first 512 tokens. Since `chat(..., safety=True)` is the default for
  every engine, local or cloud, this took down the WHOLE call for any
  caller sending a normal, non-adversarial, moderately long prompt (a
  table plus instructions, common across this suite's own downstream
  callers) — the exact "silently no-op or crash the caller" failure mode
  this module's own design explicitly exists to avoid. Found via
  `standpoint`'s own test suite hitting it live against the real model
  (the existing test suite here only ever exercised a mocked classifier,
  so a real over-length prompt was never actually driven through the real
  pipeline before). Fixed with `classifier(text, truncation=True)`;
  regression test asserts the classifier is actually called with
  `truncation=True`, not just that a long prompt happens to work today.

## [1.4.0] - 2026-08-24

### Added

- **Cloud mode auto-picks the best paid model, like local mode auto-picks
  the best local one.** A `mode: cloud` brief's `model` is now optional:
  omit it (and `provider`, to search every provider) and `resolve` picks
  the best paid model itself, from a new small catalog (`pricing.yaml`,
  extended with `provider`, `kind`, `structured_output`, and per-axis
  `benchmarks` per entry) on a quality-vs-price trade-off. A `quality_vs_cost`
  brief field (0..1, default 0.7) tips the pick: `1.0` picks purely on
  benchmark score, `0.0` picks purely on price. New module
  `cloud_catalog.py` (`load_cloud_catalog`, `rank_cloud`, `pick_cloud`,
  `blended_price_per_1m`) mirrors `score.py`'s local picker. Pinning
  `provider`/`model` explicitly still works exactly as before.
- **`report`/`recommend.cloud_recommend`**: `report` now also shows the
  best PAID model for the task, on by default (`--no-cloud` to skip,
  `--quality-vs-cost`, `--cloud-provider` to tune it) — reference only,
  needs no API key and reaches no network. `to_markdown` renders it as an
  extra section when a report carries a `"cloud"` key.
- **GUI gains a local/cloud mode switch**: a `mode` dropdown next to the
  task box mirrors the brief's own `mode: local` / `mode: cloud` field —
  only the selected mode's recommendation renders, with only that mode's
  controls shown (memory headroom + live server load for local;
  `quality_vs_cost` for cloud, reference only, no API key or network call).
  `POST /api/recommend` gains matching `cloud`, `quality_vs_cost`, and
  `cloud_provider` fields, reusing `cloud_recommend()` so the CLI and GUI
  share the same ranking logic.

### Fixed

- **`__version__`/`pyproject.toml` drift, again**: the `v1.3.8` and `v1.3.9`
  git tags were placed on commits whose `pyproject.toml`/`__init__.py`
  still read `1.3.8`'s predecessor value — the version bump step was
  skipped before tagging, so those tags shipped no matching release
  (confirmed: PyPI's live version stayed `1.3.7` through both). This
  release bumps straight to `1.4.0`, since `1.3.8`/`1.3.9` are already
  consumed as (mismatched) git tags and must not be reused.
- **`catalog.write_cache`/`hardware.write_cache` wrote the YAML cache
  non-atomically** (`path.write_text` directly, bypassing os-helper's
  `osh.make_directory` convention used everywhere else in this package).
  A crash or a concurrent `load_catalog`/`load_hardware` read mid-write
  could see a truncated file — silently discarded as "malformed YAML,
  ignoring" by `_load_yaml_file`, losing the entire cache. Both now use
  the same same-directory-temp-file-then-`os.replace` atomic write
  `pull.write_env` already established for `env.sh`/`config.json`.
- **`engine.write_engine`/`recommend.write_report` had the same
  non-atomic-write gap**, found in a follow-up sweep for every remaining
  `Path.write_text()` call in the package. `write_engine` is the more
  consequential of the two: `engine.load_engine` has no `try/except` around
  a malformed YAML parse (unlike the catalog/hardware loaders), so a reader
  racing a `resolve --out llm.engine.yaml` write would crash outright
  instead of degrading gracefully. Both now write atomically, same pattern.
- **`observe.py`'s module docstring claimed the FastAPI app calls
  `observe.enable()` at startup** — it doesn't; `GET /api/activity` reads
  the ledger directly instead (documented correctly in its own docstring),
  so a plain `uvicorn best_engine_ai_helper.api:app` never needs `enable()`
  called at all. Corrected the module docstring to match.
- **README.md/LISEZMOI.md had a few relative links/images** (`EXAMPLES.md#resolve`,
  `GUI.md`, `LICENSE`, and LISEZMOI's logo pointing at a GitHub `blob` URL
  instead of `raw.githubusercontent.com`) — relative paths and `blob` image
  URLs break once the README is rendered outside the repo (PyPI's project
  page), so both are now absolute `github.com/.../blob/main/...` links and
  `raw.githubusercontent.com` image URLs, matching the convention already
  used everywhere else in both files.
- **Stale "cloud branch" wording** in `pricing.yaml`'s header comment and
  `observe.py`'s module/function docstrings claimed cloud calls only
  matter "once the cloud branch lands" / "has no effect on main" — cloud
  mode (paid transports, cost ledger, real provider token counts) has
  been live on `main` for several releases; the comments now say so.

### Documentation

- README.md/LISEZMOI.md gain a **"Two modes: local (free) and cloud
  (paid)"** section: what each mode guarantees, the auto-pick vs. manual
  pin choice, and a table of what happens automatically at the
  `llm.chat()` call site for a cloud engine (API key lookup, safety scan,
  pseudonymization, retry/cache, cost tracking).
- EXAMPLES.md/EXEMPLES.md's `resolve` recipe gains an auto-pick walkthrough
  and `report`'s recipe gains the `--cloud` comparison.

## [1.3.9] - 2026-08-21

### Fixed

- **`pull`'s Ralph gates validated the wrong model.** `pull_cmd`
  (`cli.py`/`cli_argparse.py`) pulls a candidate tag, then calls
  `validate_vlm.validate(_llm.chat)` and `validate_llm.validate(_llm.chat)`
  to gate it before trusting it. Neither call bound a `model=`, so
  `llm.chat`'s no-model-given resolution fell back to `BEST_LLM_TEXT` /
  `BEST_LLM_VISION` (env, then the config `pull` itself last wrote, then
  the built-in default) instead of the tag just pulled. On a fresh
  machine this queried a model that was never pulled (a hard failure);
  on a repeat `pull` it silently re-validated the PREVIOUS model while
  writing `env.sh` for the NEW one, so a candidate could be promoted
  without ever actually being tested. Both gate calls now bind the
  candidate explicitly (`functools.partial(_llm.chat, model=tag)`).
- **`--headroom` defaulted to 0.85 in every entry point** (`recommend`,
  `report`, `POST /api/recommend`, the GUI's headroom field), even though
  `score.MAX_HEADROOM` (0.5) has clamped any larger value since 1.1.0, so
  the documented default silently became 0.5 with no indication in
  `--help` or the GUI. The GUI's number input additionally set
  `min="0.5" max="1"`, a range in which every value has the exact same
  effect. Defaults now read `score.MAX_HEADROOM` directly, the GUI input's
  range is `0-0.5`, and the `--help` text says plainly that a larger value
  is clamped.

## [1.3.8] - 2026-08-21

### Fixed

- **`cli_argparse`'s `env` command printed one extra trailing blank line**
  compared to its click twin: `_emit` always appends a newline, but
  `env.sh`'s content already ends in one, so the two CLI surfaces produced
  byte-different output for the same command. The argparse path now
  writes the file content as-is.

### Documentation

- README.md/LISEZMOI.md: `server_load()`'s docstring no longer describes
  the os-helper live-load fields as a future/unreleased dependency — the
  `os-helper>=2.3.0,<3` floor already pinned in `pyproject.toml`
  guarantees them on every install.

## [1.3.7] - 2026-08-17

### Fixed

- **`pull.ollama_rm` had no timeout** — same bug class already fixed for
  `ollama_pull`: a hung daemon or a locked model file would block the
  pull-and-validate loop forever. Now bounded (default 60s; local
  filesystem delete, no network, so shorter than `ollama_pull`'s 600s).
- **`pull.write_env`'s docstring claimed the files it writes are atomic**,
  but the implementation was a plain `Path.write_text()`. Now actually
  atomic (write to a sibling temp file, `os.replace()` into place), so the
  docstring's guarantee is real.

### Documentation

- README.md/LISEZMOI.md now explain what the Ralph Loop and Ralph Eyeball
  Loop quality gates actually check (catch-and-fix a seeded text flaw,
  spot a seeded visual defect) before naming them, and gloss "KV-cache" at
  first use in both languages. Prose-only cleanup of stray punctuation
  dashes; no behavior change.

## [1.3.6] - 2026-08-15

### Fixed

- **`__init__.py`'s `__version__` was drifted from `pyproject.toml`** (stuck
  at `"1.2.0"` since before 1.3.0, unused anywhere else in the codebase but
  misleading to anyone inspecting `best_engine_ai_helper.__version__`
  directly). Synced.

- **`pull.ollama_pull`'s `timeout` was never actually enforced**: the
  progress-streaming loop blocks on each read until a line arrives or the
  pipe closes (i.e. until the process exits), so a stalled pull (network
  stall, hung Ollama server) hung forever regardless of `timeout`. A
  watchdog thread now kills the process and raises `subprocess.TimeoutExpired`
  after `timeout` seconds. `cli.py`'s and `cli_argparse.py`'s `pull` command
  now catch that (skip to the next candidate, like a failed pull) and
  `FileNotFoundError` (no candidate can pull without the `ollama` binary —
  fail fast with a clear message instead of repeating the same crash per
  candidate).
- **`catalog._load_yaml_file` silently produced garbage on a non-list YAML
  top level**: `list(a_dict)` returned only the dict's keys as fake
  "entries", `list(a_string)` returned one-character "entries", and a bare
  scalar crashed `list(...)` outright — all reachable from a hand-edited or
  corrupted `catalog_cache.yaml`. Now validated and skipped with a warning,
  same treatment as an empty file.
- **`safety.scan_text` could crash `check_text`/`chat()` outright**: the
  NSFW-label lookup (`next(r for r in result if r["label"] == "nsfw")`) had
  no default and no case-insensitivity, so a differently-cased or renamed
  label from a future model update would raise an unhandled `StopIteration`
  instead of degrading — the exact "silently no-op" failure this module's
  design otherwise avoids. Now case-insensitive with a heuristic fallback
  instead of a crash.
- **CLI**: an exception from the library now prints one clean `Error: ...`
  line to stderr and exits 1, instead of a raw Python traceback, on both CLI
  twins. `best-engine-ai-helper`'s console-script entry point now points at
  a new `cli.console_entry()` wrapper (was the bare `main` click group);
  `cli_argparse.py`'s `main()` now wraps its subcommand dispatch the same
  way. `pyproject.toml` updated.

## [1.3.5] - 2026-08-13

Solidifies documentation, tests, and CI. No behavior change for end users
beyond one bug fix.

### Fixed

- `safety.scan_image` crashed with an uncaught `PIL.UnidentifiedImageError`
  when Pillow was installed but fed malformed or truncated image bytes,
  instead of degrading gracefully like every other missing-dependency path
  in that function. Found while writing a `CODING.md`-required docstring
  Example, not by inspection. Now returns the same `"unavailable"` degrade
  shape as a missing optional dependency.
- `tests/test_safety.py`'s heuristic-fallback assertions assumed
  `transformers` is never importable in the test environment; on a machine
  where a sibling package already pulls it in (true of this suite's shared
  dev env), `scan_text` legitimately took the real-classifier path instead,
  failing the test. Now forces `transformers` absent via the same
  `sys.modules` monkeypatch already used for the `PIL`-missing case, so the
  assertion is deterministic regardless of what else is installed.

### Added

- CI: a `concurrency` group cancels a still-running run for the same
  branch/PR when a new push lands. Two new post-test checks: `pyproject.toml`
  version vs. `CHANGELOG.md` entry consistency, and a real `python -m build`
  + `twine check` that also verifies the Git-LFS-tracked ONNX model lands in
  the wheel as its real ~1.9 MB binary, not an LFS pointer stub.
- Docstring `Examples` sections completed across `safety.py`.

### Changed

- Test coverage: 92.60% -> 94.45% (`ralph.py`, `engine.py`, `safety.py` now
  100%; `apxml.py` 96%; `cli.py` 98%). 104 tests collected, up from 99.

## [1.3.4] - 2026-08-10

Reverses `1.3.3`'s image-detector decision: LAION's `CLIP-based-NSFW-Detector`
now ships as the default, converted to ONNX to remove the fragility that
made `1.3.3` keep Falconsai instead.

### Changed

- **Image NSFW classifier: `Falconsai/nsfw_image_detection` -> LAION's
  `CLIP-based-NSFW-Detector`.** `1.3.3` measured LAION's real accuracy
  (96.16%/94.56%/97.58%/2.29% FPR, independently verified) but kept
  Falconsai because LAION's *documented* loading path needed TensorFlow +
  the unmaintained `autokeras` and OpenAI `clip` packages, plus an
  un-versioned runtime zip download. That's now moot: the classifier head
  was converted once, offline, from LAION's TensorFlow SavedModel to ONNX
  (`tf2onnx`) and is bundled directly in the package
  (`best_engine_ai_helper/models/clip_nsfw_vit_l14.onnx`, ~1.9 MB, tracked
  via Git LFS; MIT-licensed original, see `models/NOTICE.md`). Verified
  against the original TensorFlow model on LAION's own public test set:
  only 6 of 3199 samples (0.19%) flip their classification decision at the
  0.8 threshold — normal graph-conversion floating-point noise, concentrated
  where a sigmoid-shaped output is most sensitive (the 0.3-0.7 range), not a
  correctness bug. `[filtered]` now needs `onnxruntime` (new) plus
  `transformers` for the CLIP ViT-L/14 encoder (`openai/clip-vit-large-
  patch14`) — no TensorFlow, no `autokeras`, no runtime download.
- **Fixed a real, pre-existing gap found while wiring this up**: the
  `[filtered]` extra declared `transformers` but never an inference backend
  for it (`torch`/`tensorflow`/`flax`) — every classifier in this module,
  including the ones already shipped in `1.3.3`, would fail on first real
  inference call without one already present by luck. Added `torch>=2.0`
  to `[filtered]`.
- `requirements-dev.txt` gained `numpy>=1.24,<2.5` (the upper bound: numpy
  2.5's own type stubs use PEP 695 `type X = ...` syntax that mypy 1.20.2
  rejects under this project's `python_version = "3.10"` target, aborting
  the whole mypy run, not just warning about numpy specifically) — needed
  because `safety.py`'s new `_clip_image_embedding` does a real
  `import numpy` internally to L2-normalize the CLIP embedding (a
  requirement discovered by checking the actual norm of LAION's own
  published test embeddings: ≈1.0, not raw/unnormalized — using an
  unnormalized embedding would have silently produced nonsense scores).
- Uses the low-level, architecturally-stable `model.vision_model` +
  `model.visual_projection` submodules to compute the CLIP embedding,
  rather than the higher-level `get_image_features()` convenience method,
  whose return shape was found to differ across `transformers` major
  versions (a plain tensor historically; a wrapped
  `BaseModelOutputWithPooling` object in the version this was verified
  against) — this project's own `transformers>=4.30` pin has no upper
  bound, so the code needs to stay correct across that whole range.
- `ci.yml`'s checkout step now fetches Git LFS content (`lfs: true`). Not a
  test-suite regression risk today (`onnxruntime` is mocked in CI, never
  installed, so nothing opens the real `.onnx` file), but a plain checkout
  otherwise leaves an LFS pointer stub in its place, which would silently
  break any future build/publish step reading the real bytes.

## [1.3.3] - 2026-08-10

Re-evaluated both `safety.py` classifier choices against real, independently
run tests (not vendor claims) and swapped one of them.

### Changed

- **Text NSFW classifier: Detoxify -> `eliasalbouzidi/distilbert-nsfw-text-classifier`.**
  Detoxify scores general toxicity (hate/insult/threat/obscenity), not
  NSFW/sexual content specifically. On a hand-built probe set, sexual-but-
  not-abusive text scored 0.01-0.40 on Detoxify (Detoxify's own default
  threshold in this module is 0.8, so it would have MISSED these) but 0.99+
  on the NSFW-specific model; both agreed on clean text (~0) and
  toxic-and-sexual text (~0.99+). Also simplifies the `[filtered]` extra:
  both the text and image classifiers now load through `transformers`
  alone — the `detoxify` package is dropped entirely.

### Evaluated and kept as-is

- **Image NSFW classifier: `Falconsai/nsfw_image_detection` stays, LAION's
  `CLIP-based-NSFW-Detector` was NOT swapped in**, despite being the more
  widely-cited option (it filters LAION-5B, the dataset behind Stable
  Diffusion). Ran LAION's ViT-L/14 model for real against its own public,
  manually-annotated test set (`nsfw_testset.zip`): 96.16% accuracy, 94.56%
  recall, 97.58% precision, 2.29% false-positive rate at this module's 0.8
  threshold — solid, and independently verifiable by anyone. But its
  *documented* loading path needs a second deep-learning framework
  (TensorFlow) plus the unmaintained `autokeras` and OpenAI `clip` packages,
  and downloads an un-versioned zip from a GitHub raw URL at runtime; worse,
  its packaged TensorFlow SavedModel no longer loads through Keras 3's own
  `load_model()` — only an undocumented `tf.saved_model.load(...)
  .signatures["serving_default"]` workaround got it running for this
  evaluation. Falconsai self-reports 98.04% accuracy (not independently
  verified — no real NSFW imagery was fetched for this evaluation; unlike
  CLIP embeddings, raw image bytes of that content are not something this
  project will download or store) but needs only `transformers`, matching
  the text classifier above, with no legacy-framework or fragile-download
  risk. See `safety.py`'s module docstring for the full writeup.

## [1.3.2] - 2026-08-10

Test suite consolidation: no runtime behavior changes, test-only. The suite
had grown to 263 pytest items (many narrow, single-assertion unit tests) —
consolidated into 99 broader functional tests, each walking several related
scenarios sequentially in one function body instead of one function per
scenario. Coverage improved slightly (92.05% -> 92.55%) in the process,
since a few genuinely uncovered lines got picked up along the way:
`mcp.main()` (44% -> 94% covered — was entirely untested) and
`privacy.augment_with_presidio` plus a couple of `pseudonymize`'s
disambiguation branches (80% -> 98%). `test_cli_argparse.py` in particular
went from 30 collected items (12 of them a `--help` parametrize sweep) down
to 4, since it exists only to prove the argparse twin mirrors `cli.py`'s
click surface — deep business-logic coverage stays in `test_cli.py` and the
library-level test files.

### Fixed

- `requirements.txt` pinned `os-helper>=2.3.0` without the `<3` upper bound
  `pyproject.toml`'s `dependencies` carries — now consistent.

## [1.3.1] - 2026-08-10

Packaging restructuring: the CLI, GUI, HTTP API, and MCP server are now ALL
part of the default install — `fastapi`, `uvicorn`, `fastapi-mcp`, and the
`mcp` SDK moved from the `[api]`/`[mcp]` extras into core `dependencies`.
Only two optional extras remain: `[cloud]` (cloud-provider mode: retry,
caching, pseudonymization, an OS-keychain fallback for API keys — merges the
former `cloud`/`cache`/`privacy`/`keyring` extras into one) and `[filtered]`
(real NSFW/toxicity classifiers — renamed from `[safety]`, same contents).
Nothing about runtime behavior changes; every optional dependency still
degrades gracefully (a light retry, no caching, a keyword heuristic, an
"unavailable" verdict) when its extra is absent.

### Changed

- `pyproject.toml`: `[api]` and `[mcp]` extras removed, their deps folded
  into core `dependencies`; `[cloud]`, `[cache]`, `[privacy]`, `[keyring]`
  merged into one `[cloud]` extra; `[safety]` renamed to `[filtered]`.
  `psutil` added as an explicit core dependency (`detect.server_load()`
  imports it directly; previously relied on it arriving transitively via
  `os-helper`).
- `requirements.txt` updated to mirror the new core dependency set.
- Removed the now-dead `ImportError` guards in `api.py`, `mcp.py`,
  `cli.py`'s `gui` command, and `cli_argparse.py`'s `_handle_gui` — fastapi/
  uvicorn/fastapi-mcp/mcp are no longer optional, so the "extra not
  installed" error paths were unreachable.
- Docs (`README.md`, `LISEZMOI.md`, `GUI.md`, `EXAMPLES.md`, `EXEMPLES.md`,
  `CONTRIBUTING.md`) and `ci.yml` updated to drop `[api]`/`[mcp]` install
  instructions and point `[cache]`/`[privacy]`/`[keyring]`/`[safety]`
  references at `[cloud]`/`[filtered]`. `EXEMPLES.md`/`LISEZMOI.md`'s
  `mode: cloud` sections, stale since before the 1.3.0 merge (still said
  cloud mode was unresolvable), now match `EXAMPLES.md`/`README.md`.
- Fixed a stray `safety.py` docstring line that still said the `safety=`
  default was cloud-only — it's been True for every engine, local or cloud,
  since the 1.3.0 merge.

## [1.3.0] - 2026-08-10

Merges the `cloud` branch: `mode: cloud` now actually works (it previously
raised `NotImplementedError` on `main`, per the "Keep main strictly local"
policy from `1.2.0`'s predecessor). Paid-provider calls are opt-in — nothing
about the local-only default path changes.

### Added

- **Anthropic and Gemini transports** (`llm._chat_anthropic`,
  `llm._chat_gemini`), closing the last TODO from the original cloud-phase
  commit. Every OpenAI-compatible provider (OpenAI, **Mistral**, OpenRouter,
  Together, Azure OpenAI) already worked via `_chat_openai`; Mistral is now
  in `_OPENAI_COMPATIBLE` and `engine._CLOUD_BASE_URLS`.
- **Real, provider-reported token counts for cost accounting.** Every
  transport (including Ollama's `prompt_eval_count`/`eval_count`) now returns
  `(text, usage)`; the `chat()` event gains `in_tokens`/`out_tokens` when the
  provider reports them, and `observe.estimate_cost_usd` now prefers these
  exact counts over its char-count heuristic whenever they're present (falls
  back to the heuristic otherwise, e.g. LangChain). `pricing.yaml` gained
  Mistral's four model tiers alongside the existing OpenAI/Anthropic/Gemini
  entries. Verified against a real, live Mistral call (see below).
- **`llm._cloud_api_key`**: resolves a cloud engine's API key via
  `os_helper.get_config` — its own fallback order in one call (a
  `settings.yaml`/`settings.json` file in the current directory, then any
  `.env` file, then the plain process environment) for the env var named in
  the engine's `api_key_env` field — then the OS keychain via the optional
  `keyring` extra as a last resort. The key VALUE is never read from or
  written to the engine descriptor itself. New `settings.yaml.example`
  (copy to `settings.yaml`, gitignored, fill in your key; an empty value is
  a deliberate "cloud stays off", not a missing file).
- **Failover chain, retry, and cache** (`llm._engine_chain`, `_with_retry`,
  `_cache_key_payload`): `chat(engine=..., retries=N, cache=True)`. A cloud
  engine's embedded local `fallback` is tried automatically on failure
  (paid -> local); `cache=True` memoizes identical calls via the optional
  `wallet-helper` extra so a repeated call never pays for the same cloud
  request twice.
- **`privacy.py` wired into `chat(..., pseudonymize=True)`**: scrubs personal
  data from the prompt with the engine's local fallback before a cloud send,
  restores it in the response. Cloud-only (a no-op on a local engine — there
  is nowhere for personal data to leak to), or with a loud warning if the
  cloud engine has no local fallback to scrub with.
- **`safety.py` (Phase 6.5, new): NSFW/policy scanning, for text AND images,
  for local AND cloud engines alike** — content policy is independent of who
  is billed, so this is on by default for every `chat()` call, not just
  paid ones (pass `safety=False` to opt out). Scans the outbound
  prompt/images and the inbound response; `action` policy is `block` (raise
  `SafetyViolation`) / `redact` (text only) / `warn` (log, pass through —
  the default, since this has no track record on real traffic yet).
  Detoxify (text) and a CLIP-based classifier (images, via `transformers`)
  are optional (`[safety]` extra); absent them, text scanning degrades to a
  crude keyword heuristic (never silently no-ops) and image scanning
  degrades to `"unavailable"` (never a fabricated verdict).
- `engine.resolve(mode="cloud")` now actually resolves instead of raising
  `NotImplementedError` — provider + model (+ optional `base_url`/
  `api_key_env`) plus a local `fallback` from the same brief.

### Verification

Everything above is covered by mocked tests (no network call, no API key,
no paid request) — 263 passed, 92.0% coverage, ruff/mypy clean. Also ran a
real, live call against Mistral (`mistral-small-latest`, via the
`settings.yaml` key) end to end: request/response, real token counts, and a
real computed cost ($0.0000048 for a two-word exchange) all confirmed
working outside the mocks. Anthropic/Gemini payload shapes are verified
against their documented APIs but have not had a live call yet.

## [1.2.0] - 2026-08-09

### Added

- **Local activity/cost ledger (`observe.py`), the first piece of the `cloud`
  branch's Phase 6.1 monitoring plan landed on `main`.** `llm.chat()` gained
  an observer seam (`add_observer`/`_emit`, ported from the `cloud` branch —
  cloud-agnostic, so it lands here independent of the rest of that branch):
  every call fans a small event out to registered observers. `observe.py`'s
  `Ledger` is the first consumer — a local, append-only SQLite database
  (`~/.best-engine-ai-helper/usage.db`) recording who called what (
  `BEST_ENGINE_USER` env var, else the OS login name; `observe.as_user(name)`
  for scoped attribution, e.g. per-request in a shared server), which
  model/backend, latency, success/failure, and an estimated cost (bundled
  `pricing.yaml`; always `0.0` for local Ollama/vLLM, `None` — never
  fabricated — for an unpriced cloud model). Built for the "one company,
  several users" case. New `activity` CLI command (table/JSON), `GET
  /api/activity`, and a GUI **Activity** section all read the same ledger.
  Enabled by default in the CLI, API, and MCP server; opt out with
  `BEST_ENGINE_NO_LEDGER=1`. **Scope note:** this repo's own commands rarely
  call `llm.chat()` themselves (only the `pull`/`validate` Ralph gates do) —
  the ledger's real value comes once downstream projects that import
  `best_engine_ai_helper.llm` also call `observe.enable()`; that's a
  per-project follow-up, not something this change does for the whole suite
  automatically. Cost accounting for actual paid-provider calls, and the
  remaining Phase 6.2 (Anthropic/Gemini transports) and 6.5 (NSFW safety)
  work, stay on the `cloud` branch until finished.
- **Task-description quality check in `recommend.parse_task`.** A missing or
  blank task now logs a loud warning instead of silently defaulting to a
  generic profile: "activity and cost monitoring cannot attribute this call
  to a job without one." Also runs best-effort language detection
  (`langdetect`, new core dependency, fully offline) on the task text; a
  string with no detectable language (symbols/digits only) warns too. The
  parsed report now carries a `language` field, surfaced in the CLI Markdown
  report and the GUI results panel. Detection confidence is deliberately NOT
  used as a "clean text" signal — `langdetect` can be confidently *wrong* on
  a short phrase (e.g. "write SQL queries" detects as French at 99.9%
  confidence), not merely uncertain.
- **Live server-load awareness, opt-in via `--live`.** `detect.server_load()`
  snapshots current free RAM, CPU/GPU utilization, disk usage, and how many
  local engines (Ollama models, vLLM processes) are already running.
  `score.effective_budget()` (and `rank()`/`select()`) accept an optional
  `load` parameter: when given, the recommendation's memory budget is capped
  at what is actually free right now (not just the theoretical accelerator
  pool) and further derated when the CPU is saturated or disk space is low.
  Off by default everywhere (`recommend()`'s `load=None`, CLI's `--live`
  flag on `recommend`/`report`, API's `live: bool = False` on
  `POST /api/recommend`, GUI's "live server load" checkbox) — it adds a
  ~0.1-0.5s probe and makes the result depend on the exact moment it ran
  rather than being a deterministic function of the hardware alone, which
  matters for reproducible reports and CI. The report gains a `server_load`
  key (and a Markdown/GUI section) only when `--live` is used.
  **Cross-repo note:** the underlying generic live-metric probes
  (`cpu_percent`, `available_ram_gb`, `disk_usage_gb`,
  `gpu_utilization_percent` — including an Apple Silicon GPU-utilization
  read via `ioreg`'s `IOAccelerator` node, which needs no `powermetrics`/sudo)
  were added to `os-helper`'s `hardware_utils.py`, matching that module's own
  "raw facts belong here, AI-domain interpretation belongs to the consumer"
  split. They are not yet in a published os-helper release; the `os-helper`
  pin in `pyproject.toml` needs bumping once one ships, or `server_load()`
  raises on a fresh install.

### Changed

- **Repository no longer distributed as a Claude/OpenCode Agent Skill.**
  Removed `skills/best-engine-ai-helper/` (the skill packaging README) and
  `TRIGGERS.md` (an orphaned natural-language trigger catalog that existed
  only to back that skill's routing). The project ships as a library, CLI
  (`cli.py` + `cli_argparse.py`), FastAPI GUI/HTTP API (`api.py`), and MCP
  server (`mcp.py`) — no skill surface.
- **`locales/i18n.yaml` is now the single source of truth for every
  GUI-visible string AND every model-facing prompt template.** New shared
  loader `i18n.py` (`meta()` / `gui_strings()` / `prompt(key, field)`).
  `gui.py` no longer hardcodes its French/English label tables (`gui:`
  namespace, 57 semantic keys, `meta.default_locale` / `meta.supported_locales`
  drive fallback). `ralph.py` (eyeball + prose Ralph loops), `validate_vlm.py`,
  and `validate_llm.py` no longer hardcode their system/user prompt strings
  either — they live under `prompts:`, authored in English
  (`meta.model_prompt_locale`) since these are model instructions, not GUI
  copy that needs translating (see CODING.md section 21.3.3). Wording is
  unchanged in every case; only where it lives changed.
- **`references/CODING.md` refreshed from its canonical gist**, with one
  deliberate, documented deviation: the gist's "Agent Skills" section (and
  every skill-specific delivery-surface reference) is dropped, since this
  project does not ship one. Root `CODING.md` rewritten as a short pointer to
  the mirror plus the standard's key bullets (now including the
  `locales/i18n.yaml` and multi-surface-delegation rules). `CONTRIBUTING.md`'s
  mirrored bullet list updated to match.

### Fixed

- **`gui.py` mypy strict compliance** for the new locale-loading code path
  (`_locale_meta` / `_locale_gui_strings` typed precisely instead of a bare
  `dict[str, object]`).
- Two undocumented FastAPI route handlers (`api.py`'s `root()` and `gui()`)
  now carry a one-line docstring.
- **A misattributed `# type: ignore[arg-type]` in `cli.py`/`cli_argparse.py`**
  sat on the `headroom=` line instead of `kind=k` (the actual mismatch: `k`
  is `str`, `rank()` expects `Literal["llm", "vlm"]`, narrowed only by the
  CLI's own `choices=`/`typer.Option`, not by mypy). A newer mypy no longer
  flags either line either way, which is how this passed CI unnoticed; an
  older local mypy (1.20) still catches it. Moved the ignore to the line it
  actually covers, with a comment explaining why it's needed.
- **`ruff`/`mypy` were unpinned (`ruff>=0.5`, `mypy>=1.10`) in
  `requirements-dev.txt`, so CI silently drifted to newer versions than the
  local dev environment.** Two concrete bites: mypy 2.3 (CI) missed the
  misattributed `type: ignore` above that mypy 1.20 (local) caught, and
  ruff 0.16 promoted Markdown formatting from preview-only to stable, so
  adding `ruff format --check .` to CI below failed on `README.md`/
  `LISEZMOI.md`/`EXAMPLES.md`'s embedded Python code fences even though
  they were never touched locally. Pinned both (`ruff==0.15.21`,
  `mypy==1.20.2`) to keep CI and local checks looking at the same rules.

## [1.1.0] - 2026-08-06

### Added

- **MCP surface (`mcp.py`, `[mcp]` extra), entry point
  `best-engine-ai-helper-mcp`.** Exposes the same FastAPI app from `[api]`
  (`/api/system`, `/api/recommend`) as MCP tools via `fastapi-mcp`, mirroring
  the pattern already shipped in `standpoint` / `vocal-helper` / `md2star`.
  Closes the last surface gap flagged in `ai-helpers/.private/do.md` §7.
- **argparse CLI twin (`cli_argparse.py`), entry point
  `best-engine-ai-helper-argparse`.** Mirrors every `cli.py` command 1:1
  (same flags, same defaults, same output); no business logic duplicated —
  every handler delegates to the same library functions the click commands
  call. Closes the suite's CLI-surface gap flagged in `ai-helpers/.private/do.md`
  §7 (this repo was the only member without an argparse surface). The click
  entry point (`best-engine-ai-helper`) stays the primary, unchanged one —
  click is a core dependency here, not an opt-in extra, so the suite's usual
  "argparse is primary, click is the twin" naming is inverted; see the new
  module's docstring for the reasoning.
- **NVIDIA/AMD memory-bandwidth tables (`detect.py`).** `compute_profile()`
  previously only estimated decode throughput on Apple Silicon —
  `bandwidth_gbs` was always `None` on NVIDIA/AMD, so `est_tokens_per_s` and
  the comfort-throughput floor never applied on a discrete-GPU machine. New
  per-board bandwidth tables (`_NVIDIA_BANDWIDTH_GBS`, `_AMD_BANDWIDTH_GBS`,
  matched by substring against the detected GPU name) close that gap; an
  unrecognised board still degrades to `bandwidth_gbs: None` rather than a
  fabricated number.
- **Backend-aware decode efficiency (`score.py`).** `estimated_tokens_per_second`
  now applies a different achieved-bandwidth fraction for vLLM (0.75) than for
  Ollama (0.65) — confirmed to differ on identical Ubuntu + discrete-GPU
  hardware, not just a cross-platform artifact. PagedAttention + CUDA-graph
  decode tracks closer to the bandwidth ceiling than llama.cpp's more
  conservative kernel path for single-stream generation.
- **Hardware detection now delegates to `os_helper.hardware_utils`.**
  `detect.py` no longer shells out to `nvidia-smi` / `rocm-smi` /
  `system_profiler` / `lspci` itself; it calls the new generic hardware probe
  in `os-helper>=2.1.0` (cores, CPU model, GPU vendor/model/VRAM, RAM) and adds
  only the AI-throughput-specific layer (bandwidth tables, backend sizing) on
  top. `detect`/`/api/system` gained a `hardware` field with the raw facts
  (CPU cores/model, per-GPU name + VRAM) alongside the existing throughput
  estimate. `psutil` is no longer a direct dependency (comes transitively via
  os-helper).
- **Usage catalog (`usages.yaml`) — named sev7n task profiles + families.** Eight
  profiles (`text2sql`, `rag-answer`, `embeddings`, `text2sql-figures`,
  `report-bluf`, `classification`, `pii-rgpd`, `persona`), each stating only its
  **needs** (task type, structured-output requirement, throughput floor, memory
  headroom, advisory quality bar, context length) — **never a model name**. A
  profile is a named brief, resolved by the same four-criteria picker. Profiles
  are grouped into families **F1** (constrained generation), **F2** (prose
  generation), **F3** (embeddings) — the usages that can share one model. New
  CLI `usages list` / `usages show NAME` / `usages resolve NAME|--family FID`,
  and library `list_usages`, `list_families`, `get_usage`, `get_family`,
  `usage_brief`, `family_brief`, `resolve_usage`, `resolve_family`. best-engine
  chooses the concrete model and writes it only to the gitignored
  `llm.engine*.yaml` (added to `.gitignore`). A user overlay at
  `~/.best-engine-ai-helper/usages_cache.yaml` overrides by name.
- **Catalog additions (the search space).** Qwen 2.5-Coder entries (a real code
  axis for `text2sql`) and `kind: embed` text embedders (scored on MTEB) for the
  embeddings usage. `embed` joins `llm`/`vlm` as a third catalog kind; the
  generative picker ignores it, the F3 usage selects among embedders by memory
  fit.
- **`resolve` command + the brief → engine contract.** A repo commits a tuned
  `llm.brief.yaml` (its LLM/VLM usage: `kind`, `headroom`, `min_tps`,
  `structured_output`, free-text `task`, and `mode: local|cloud`).
  `best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml`
  turns it into a **gitignored, machine-specific** engine descriptor (backend +
  model per kind). Consumers read the model only from that file — no
  `DEFAULT_MODEL` constant.
- **Dual backend, chosen by hardware.** `engine.default_backend()`: **vLLM on a
  discrete GPU (NVIDIA/AMD), Ollama otherwise** (macOS, CPU-only Linux, Intel
  iGPU). `resolve --backend auto|ollama|vllm` and `--endpoint URL` override it.
- **`engine.ensure(dir)` + missing-file policy.** Loads `llm.engine.yaml`, or
  resolves it from the brief on first use; a missing **brief** raises loudly
  (it is committed, so its absence is a real bug).
- **Centralized transport.** `llm.chat(..., engine=<descriptor|path>, kind=…)`
  reads the backend/base_url/model from the engine file and dispatches to Ollama
  (`/api/generate`) or vLLM (OpenAI-compatible `/v1/chat/completions`), with
  schema-constrained structured output on both. `base_url` is now injectable.
- **Brief `mode: local|cloud` field** (default `local`), recognised now for
  forward-compatibility. `mode: cloud` raises `NotImplementedError` — cloud
  providers (with a paid → local fallback), cost, failover, pseudonymization and
  NSFW safety ship on a later `cloud` branch.
- New Python API: `resolve`, `ensure`, `write_engine`, `load_engine`,
  `model_for`, `default_backend`, `model_footprint_gb`, `MAX_HEADROOM`.

### Fixed

- **Mypy CI regression from the `kinds`/usage-catalog work.** `recommend()`'s
  `kinds` parameter and `engine._kinds_from_brief` now return
  `list[Literal["llm", "vlm"]]` instead of `list[str]`, matching what `rank()`
  expects.
- **Mypy + CI collection regressions from the argparse CLI / MCP work.**
  `cli_argparse.py`'s `_score.rank` call, its three `_add_*_group` helpers
  (missing `_SubParsersAction` type argument), and `main`'s `ns.func(ns)`
  dispatch (returning `Any` against a declared `int`) are now typed cleanly.
  Separately, CI installed only the `[api]` extra, so `pytest
  --doctest-modules` failed to even collect `mcp.py` (it raises at import
  time without `[mcp]`, by design — same pattern as `api.py`); CI now
  installs `.[mcp]`, which already pulls in `[api]`'s deps too.

### Changed

- **Anti-greed selection — picks are realistic, not maximal.**
  - **Headroom capped at 0.5** (`score.MAX_HEADROOM`), and any caller/brief value
    is clamped down to it (was a 0.85 default). This is the main guard against a
    model that technically loads but leaves no room for the OS or KV growth.
  - **Leanest-sufficient, not biggest-that-fits.** Among models within 3 benchmark
    points of the best comfortable candidate, `recommend` now picks the
    smallest/fastest, not the top scorer.
  - **Backend-aware sizing.** `score.model_footprint_gb` sizes a vLLM pick against
    full FP16 weights (~2 bytes/param + overhead), not the Ollama Q4 `ram_gb`, so
    a vLLM recommendation is realistic on the real GPU. `select`/`rank`/
    `recommend`/`estimated_tokens_per_second` take a `backend` argument.

## [1.0.0] - 2026-08-02

First stable release. The recommender now defaults to **comfortable, realistic**
picks (not merely "theoretically fits"), and the whole suite sits on the
os-helper 2.0.0 foundation.

### Changed

- **Requires os-helper 2.x** (`os-helper>=2.0.0,<3`, was `>=1.5.0`). Logging
  routes through os-helper on its stable 2.x contract.
- Install docs use `pip install best-engine-ai-helper` (from PyPI); added a test
  guarding every Markdown file against a stale `git+...@vX.Y.Z` self-pin. CI stays
  a super-light blocking gate (ruff + mypy + pytest).

### Added

- **Comfort throughput floor** in recommendation and pulling. A model that
  fits in memory can still decode too slowly to be usable (a 32B at Q8 crawls
  at ~7 tok/s on an M2 Max / 400 GB/s). Selection now treats "fits your
  hardware" as *fits in memory AND runs at a usable speed*: a new comfort floor
  (`score.COMFORT_TPS`, default 15 tok/s, reusing the existing
  `estimated_tokens_per_second` estimate) marks memory-fitting-but-slow models
  as not comfortable. `recommend` picks the highest-scoring comfortable model
  (falling back to a fitting-but-slow one only when none is comfortable, with a
  warning), `pull` tries comfortable candidates before slow ones, and both the
  `recommend` and `report` outputs gain a `comfy` column plus a stated floor.
  A `--min-tps` flag overrides the threshold on `recommend` and `pull`.
  Previously the ranker chose the top benchmark score that merely fit memory,
  over-recommending large models that technically load but feel stuck.

## [0.5.0] — 2026-08-02

### Added

- `catalog update` now refreshes the model cache from the ApXML open-weight
  directory: it fetches specs, normalizes them to catalog entries, and merges
  them into `~/.best-engine-ai-helper/catalog_cache.yaml` by id (the bundled
  seed is never touched). Supports `--limit` and `--timeout`. ApXML carries no
  numeric benchmarks, so refreshed entries rank low until a scored source
  fills them.
- `hardware update` now records the running machine into
  `~/.best-engine-ai-helper/hardware_cache.yaml`: the detected chip, its memory
  pool, and the Ollama-usable share after the OS reservation, upserted by
  chip + memory tier. (There is no public specs API spanning every GPU / Apple
  chip, so a refresh captures ground truth for the current machine rather than
  scraping a third-party site.)
- English variant of the GUI: the page is now bilingual (French by default,
  English at `/gui?lang=en`), with a header link to switch. Both are rendered
  from one template plus a per-language strings table (`render_gui`); the JSON
  API stays language-neutral.
- GUI mirrors the structured-output ranking: the candidate table gains a
  `structured` column, and the chosen model shows a warning when it can't do
  structured JSON output. A `/gui?task=...` deep link pre-fills the box and
  runs the recommendation on load, so a result is shareable by URL.
- Minimal browser GUI: `best-engine-ai-helper gui` (needs the new `[api]`
  extra: `fastapi` + `uvicorn`) serves a single-page app at `/gui`: the
  hardware snapshot `detect` prints, plus a task-description box that returns
  the same recommendation as `report`, in the browser. `api.py` exposes it as
  `GET /api/system` and `POST /api/recommend`; `gui.py` is the page (vanilla
  JS + Tailwind CDN, no build step, matching the AI Helpers suite's house
  style). See `GUI.md`.
- `scripts/generate_icons.py` + `best_engine_ai_helper/static/`: favicon,
  apple-touch-icon, and Android/PWA icons generated from `assets/logo.png`,
  composited onto the suite's cream background so the engraved-glove mark
  reads on both light and dark browser chrome.

### Changed

- Docstring `Examples` are now gated: `pytest` collects them via
  `--doctest-modules` (configured in `pyproject.toml`), so a drifted example
  fails CI. Fixed three that had drifted (`score.select`, `score.rank` used
  names not in scope; `validate_llm.validate` asserted a pass its stub model
  could not produce).
- Documentation pass over every Markdown file: brought the prose into line with
  the project's writing charter (removed em/en-dash asides), corrected stale
  facts (the `catalog update` / `hardware update` commands, the four selection
  factors including structured-output, the `gemma3:12b` vision default, the
  `pip install -e ".[api]" -r requirements-dev.txt` install, the `validate`
  entry points), brought LISEZMOI to parity with README, and refreshed the
  sample `recommend` / `select` outputs to match the current ranking. Populated
  the `references/WRITING.md`, `references/ECRITURE.md`, and `references/CODING.md`
  local copies from their canonical gists. Absolutized the image and link URLs
  in `README.md` / `LISEZMOI.md` to `raw.githubusercontent` / `github.com/blob`
  so they render on the PyPI project page (relative paths 404 there).
- Rationalized the test suite per the project's testing philosophy: fewer,
  richer tests (≈138 → 81) at **higher** coverage (74% → 93%). Collapsed
  one-assertion micro-tests into scenario and table-style tests, mirrored the
  source tree (`test_llm` / `test_ralph` / `test_pull` / `test_validate` replace
  `test_phase0b`), added `tests/conftest.py` for the shared Click runner and
  `tests/test_scenarios.py` for end-to-end workflows, and mock-covered the
  previously-untested subprocess / network / gate paths (hardware probes, ollama
  pull, LLM backends and errors, the Ralph loops, the validation gates).

### Fixed

- CI (and local `pytest`) was red on the two langchain-backend tests: the
  langchain branch in `llm.py` imports `langchain_core.messages`
  unconditionally, but `langchain-core` was not a declared dev dependency.
  Added it to `requirements-dev.txt` and made the `ChatOllama` test stub the
  optional backend via `sys.modules` (mirroring the existing `langchain_openai`
  stub) instead of importing the uninstalled real package.
- `recommend`'s "lighter alternative" was chosen by score proximity alone, so
  under a structured-capable pick it could suggest a lighter but
  structured-incapable model (e.g. a Qwen3-VL) that silently fails the suite's
  schema-driven tasks. The alternative is now required to be at least as
  structured-output-capable as the chosen model.
- `score.select` ignored the structured-output flag, so the library's `select`
  returned a different (structured-incapable) model than `recommend` / `report`
  / the GUI, which rank structured-capable models first. `select` now applies
  the same priority, restoring the documented `rank(...)[0] == select(...)`
  invariant.
- AMD VRAM detection: `_amd_vram_gb` split the rocm-smi line on the *first*
  colon, so the real `GPU[0] : VRAM Total Memory (B): <bytes>` format left the
  label text where the number was expected and detection silently returned
  None. Split on the last colon instead.
- Ralph eyeball gate: the verdict prompt's literal JSON example (`{"ship": ...}`)
  was not brace-escaped, so `.format(critique=...)` raised `KeyError` on every
  real verdict. Escaped it; the eyeball loop now completes.
- Clean `mypy` run across the package: annotated the subprocess and JSON
  boundaries that leaked `Any` (`detect`, `llm`, `ralph`, `catalog`), gave
  `cli._fmt_table` its `dict[str, Any]` argument, typed the LangChain message
  list, and dropped `type: ignore` comments that no longer apply.

## [0.4.0] - 2026-07-31

### Added

- Depend on `os-helper` (`>=1.5.0`) and route all logging through it. Library
  modules now emit `osh.info` at their seams (catalog / hardware load, memory
  detection, recommendation picks, model pull/remove, Ralph iterations, chat
  dispatch) and `osh.warning` / `osh.error` on the failure paths (malformed
  YAML/JSON config, unknown chip, no model fitting the budget, failed inference
  requests, gate failures). `info` / `debug` are off by default and surface with
  the new `-v` / `-vv` flag on the CLI; warnings and errors always show.
- File management goes through `os-helper` helpers: `osh.file_exists` for the
  config / catalog presence checks and `osh.make_directory` in place of ad-hoc
  `Path.mkdir(parents=True, exist_ok=True)`.

## [0.3.0] - 2026-07-31

Make the chosen model tags trivially consumable by downstream suite packages,
so model selection lives here (its rightful home) rather than being hard-coded
in each consumer.

### Added

- `config.py`: cheap, deterministic resolvers `text_model()` / `vision_model()`
  / `resolved_models()` / `load_config()`. Precedence is env override
  (`BEST_LLM_TEXT` / `BEST_LLM_VISION`, with the legacy `SPREZZATURE_LLM_*`
  spellings accepted) → the selection persisted by `pull` in
  `~/.best-engine-ai-helper/config.json` → a safe built-in default
  (`qwen3-vl:8b`). They never probe hardware and never raise, so they are safe
  to call at import time, in CI, and in tests. Exported from the package root.

### Changed

- `llm.py` transport now resolves its model tags through `config`, closing the
  gap where it read only `SPREZZATURE_LLM_*` and ignored a fresh `pull`
  selection persisted under `BEST_LLM_*`.

## [0.2.0] - 2026-07-30

Hardware-aware recommendation that weighs memory, accelerator, and compute, and
emits a justifiable report in Markdown and JSON.

### Added

- `recommend.py`: the end-to-end algorithm. Takes a hardware description, the
  benchmark catalog, and a (possibly vague, free-text) task, and returns the
  best engine per needed kind (LLM/VLM), each justified by task fit, memory fit,
  and estimated throughput. `parse_task` maps a phrase to a benchmark axis and
  the model kinds it needs. `to_markdown` / `write_report` render the result;
  the report round-trips through JSON.
- `report` CLI command: `--task "…" --out <stem> [--format md|json]` writes
  `<stem>.md` and `<stem>.json`.
- `detect.compute_profile()` and `detect.chip_name()`: accelerator kind and
  Apple-Silicon memory bandwidth (published specs), used for the throughput
  estimate.
- `score.estimated_tokens_per_second()`: bandwidth-bound decode-speed estimate.

### Changed

- **Memory budget model.** `effective_budget` now applies the Apple Metal
  GPU-usable cap (~66% ≤36 GB, ~75% >36 GB of unified memory) instead of
  treating the whole pool as usable, then a default `headroom` of 0.85 (was a
  flat 0.80 of everything) for the OS, workload, and KV growth. This stops the
  tool from steering toward RAM-maxing models that leave no room to work.
- Reliability: model-call timeout is now bounded and configurable via
  `SPREZZATURE_LLM_TIMEOUT` (default 120s, was a fixed 600s), so validation
  terminates predictably on a light model.

### Fixed

- Stale CLI test that treated the implemented `pull` / `validate` commands as
  stubs and hung the suite by driving the live model loop.

## [0.1.0] - 2026-07-28

First release. Phase 0a: pure Python, no model download required.

### Added

- Hardware detection (`detect.py`): Apple Silicon unified memory, NVIDIA VRAM via
  nvidia-smi, AMD VRAM via rocm-smi, CPU-only fallback via psutil.
- Model catalog (`catalog.py`, `models.yaml`): 13-entry bundled seed covering
  Qwen 3 VL (4B to 72B), Qwen 3 text (8B to 72B Q8), Qwen 2.5 3B, Gemma 3 12B.
  Cache-merge logic for future `catalog update` output.
- Hardware chip table (`hardware.py`, `hardware.yaml`): Apple Silicon M1 through
  M4 Ultra across all memory tiers; NVIDIA RTX 3060 through H100. Cache-merge logic.
- Selection algorithm (`score.py`): filters by 80% headroom, ranks by benchmark
  score (vision for VLMs, general for LLMs), last-resort smallest-model fallback.
- CLI (`cli.py`): `detect`, `recommend`, `catalog show`, `hardware show` commands
  fully implemented. `pull`, `validate`, `env`, `catalog update`, `hardware update`
  stubbed with Phase 0b notice.
- Test suite: 40+ tests in `tests/` covering all public functions.
