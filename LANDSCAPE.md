# Landscape

[🇫🇷 PAYSAGE.md](PAYSAGE.md) · 🇬🇧 English

Tools that answer some version of *"which model should I use?"*, compared against
`best-engine-ai-helper`. Ratings are ⭐ (1) to ⭐⭐⭐⭐⭐ (5), scored on this project's
intended job: **decide between a free local model and a paid cloud one, on the hardware
you actually have and the API keys you actually hold, and prove the choice works.**

A tool optimised for a different job is not being criticised; the score reflects fit to
*this* niche. Several of the entries below are excellent at theirs.

Surveyed 2026-10-19. Nine criteria, two of them added after this project started measuring decode speed rather than estimating it.

## At a glance

<!-- TABLE:START -->
| Model selection | Hardware detection | Local fit | Measures speed on this machine | Paid models in the same decision | Routes on keys present | Scores carry provenance | Catalog breadth | Verifies quality before you depend on it | Programmatic API |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **best-engine-ai-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| llmfit | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| RouteLLM | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| LiteLLM | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| OpenRouter | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ |
| Not Diamond | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Ollama | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ |
| LM Studio | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ |
| Browser VRAM calculators | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ |
<!-- TABLE:END -->

## Positioning map

<!-- FIGURE:START -->
2D representation of the table above, by PCA (see [`standpoint`](https://github.com/warith-harchaoui/standpoint)).

![Positioning map](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/landscape.png)

Read it as a shape, not a scoreboard. The axes read **Horizontal — Abundance ↔ Precision**
and **Vertical — Adaptability ↔ Control**.
<!-- FIGURE:END -->

## What the map actually shows

Two readings, and the second is the one that moved.

**Left — abundance.** LiteLLM, OpenRouter, Not Diamond, RouteLLM. They reach hundreds of
models through one surface and answer *"which provider should this request go to, and
what will it cost?"*. Excellent at that, and entirely unaware of the machine the caller
is sitting at: none of them will ever answer "actually, run it locally for nothing".

**Bottom — adaptability.** Ollama, LM Studio, the browser VRAM calculators. They answer
*"will this model fit, and how do I start it?"*, on whatever hardware you put them on.
Also excellent, and entirely unaware that a paid API exists.

**Top-right — a decision that has been checked.** `best-engine-ai-helper` sits alone
there. `llmfit` is the nearest neighbour on the precision axis and sits well below it on
control, which is the honest shape of the difference: `llmfit` and this project now both
*measure* decode speed on the machine in front of them, but `llmfit` measures and
reports, where this project measures, then lets the number disqualify a model and
re-weight every estimate that follows.

**The gap is still the top-right.** No surveyed tool combines *"what does this machine
run"* with *"what would a provider charge, and do I even hold that key"* in a single
decision. That is not a claim about quality; it is a claim about coverage, and it is what
this project is for.

### The column this project loses

**Catalog breadth: ⭐⭐ against `llmfit`'s ⭐⭐⭐⭐⭐.** Twenty hand-maintained seed entries
against hundreds. The constraint is deliberate rather than accidental — every entry
carries a `source:` and a `fetched_at`, and an entry with no provenance is worth less
than no entry — but a constraint you chose is still a constraint, and a reader comparing
the two tools on catalogue size should pick `llmfit`.

It is on the map on purpose. A landscape where the author wins every column is a
landscape nobody believes, and this is the column where the work is genuinely unfinished.

## Positioning

`best-engine-ai-helper` answers one question the others split in two: **free local or
paid cloud, for this need, on this machine, with these keys.**

Four things follow from treating it as one question.

**The brief names a need, never a model.** A caller says it wants schema-constrained SQL
under a latency floor; the picker says which model that is, locally or in the cloud. The
model name is an output, which is what makes swapping one a configuration change.

**The cloud fallback goes in the safe direction.** A cloud brief resolves a paid model
*and* a local fallback from the same brief, so a failed paid call degrades to the
always-available local model. Paid → local, never the reverse.

**A provider whose key is absent is not a candidate.** Keys are resolved through
`settings.yaml`, `.env`, the environment, then the OS keychain. A recommendation you
cannot act on is not a recommendation.

**Every score says where it came from.** Benchmarks are tagged with their leaderboard
and their refresh date; an Arena rating carries its snapshot, and a snapshot too old to
trust is refused rather than merged — a rating fourteen months stale would rank a
previous generation of models first, which is worse than having no rating.

## Ideas taken from the field

Worth saying plainly, since none of this was invented here.

- **`llmfit`: every estimate ships its inputs.** Its `info` command shows what a number
  assumes and how to verify it on your own machine. The same instinct drives this
  project's `--report` flags and the `source:` field on every catalog figure.
- **RouteLLM: route on the request, not on the account.** Its per-prompt classifier is a
  finer granularity than this project's per-usage-profile briefs. The trade is
  deliberate — a brief is declarative, reviewable and testable, where a learned router
  is none of the three — but the idea of routing on *what is being asked* rather than on
  *who is asking* is theirs.
- **The cloud routers: cost is a first-class axis.** Published figures put routing
  savings at 60-85% on mixed workloads. That is the reason `pricing.yaml` carries list
  prices and the picker exposes a quality-versus-cost weight rather than ranking on
  quality alone.

## Per-tool write-up

### llmfit

The nearest neighbour on the map. Detects CPU, RAM, discrete and unified memory across
CUDA, Metal, ROCm and OneAPI, then scores hundreds of models on memory fit, estimated
speed, quality and context. Its speed model is memory-bandwidth-based and grounded in
community measurements, and `llmfit info` shows the inputs behind any number — the same
transparency instinct as this project. Where it stops: local only.

### RouteLLM

From LMSYS and UC Berkeley. A per-prompt classifier choosing between a strong frontier
model and a weak cheap one, with published savings up to 85% at ~95% of GPT-4 quality.
Finer granularity than a usage brief, and not reviewable or testable the way a YAML brief
is. Complementary: a brief could reasonably resolve *to* RouteLLM.

### LiteLLM

The de-facto open-source gateway: one OpenAI-shaped surface over a hundred providers,
with keys, budgets, fallbacks and retries. It routes; it does not choose, and it does not
know the machine exists.

### OpenRouter

The managed version of the same idea, with a marketplace and a markup. Zero operational
overhead, at the cost of every request leaving your network.

### Not Diamond

A managed learned recommender optimising quality-per-dollar. Closest in intent to this
project's picker, opposite in posture: the decision happens on someone else's servers,
against a catalogue you cannot read, and local models are not in it.

### Ollama

The local-first runner most of this suite actually uses. Pulls and serves models with one
command. Deliberately opinionated and deliberately not a selector: `ollama run` assumes
you already decided.

### LM Studio

A desktop application with a model browser that does warn when a model will not fit. The
closest any GUI gets to selection, and it stops at a warning: no ranking, no validation,
no scriptable surface.

### Browser VRAM calculators

`modelfit.io`, `llmconfigurator.com`, `willitrunai.com` and others. Type your VRAM, read
which sizes fit. Genuinely useful for a five-second sanity check before a purchase, and
structurally incapable of being part of a pipeline.
