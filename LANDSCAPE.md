# Landscape

[🇫🇷 PAYSAGE.md](PAYSAGE.md) · 🇬🇧 English

Tools that answer some version of *"which model should I use?"*, compared against
`best-engine-ai-helper`. Ratings are ⭐ (1) to ⭐⭐⭐⭐⭐ (5), scored on this project's
intended job: **decide between a free local model and a paid cloud one, on the hardware
you actually have and the API keys you actually hold, and prove the choice works.**

A tool optimised for a different job is not being criticised; the score reflects fit to
*this* niche. Several of the entries below are excellent at theirs.

Surveyed 2026-10-19. Nine criteria, two of them added after this project started measuring
decode speed rather than estimating it. One cell re-measured on 2026-10-20 — see [the
column this project loses](#the-column-this-project-loses).

## At a glance

<!-- TABLE:START -->
| Model selection | Hardware detection | Local fit | Measures speed on this machine | Paid models in the same decision | Routes on keys present | Scores carry provenance | Catalog breadth | Verifies quality before you depend on it | Programmatic API |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **best-engine-ai-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
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

Read it as a shape, not a scoreboard. The figure prints **Horizontal — Valuable ↔
Resourceful** and **Vertical — Diverse ↔ Precise**, and those pole names are written by the
model that drew the map — the loadings under them are the part that does not change between
runs, so read those. Horizontal is built almost entirely from hardware detection, local fit
and measured decode speed, each loading about 0.50: *right* means **knows the machine in
front of it**. Vertical is built from paid models in the same decision, routing on keys
present, the programmatic API and verified quality, each between 0.44 and 0.50: *up* means
**decides across both worlds, then checks the answer**. The two carry 75% of the variance
between them, so a quarter of the table is not on this picture.
<!-- FIGURE:END -->

## What the map actually shows

Two readings, and the second is the one that moved.

**Left — reach, blind to the machine.** LiteLLM, OpenRouter, Not Diamond, RouteLLM. They
reach hundreds of models through one surface and answer *"which provider should this
request go to, and what will it cost?"*. Excellent at that, and entirely unaware of the
machine the caller is sitting at: none of them will ever answer "actually, run it locally
for nothing".

**Bottom — fit, blind to the bill.** Ollama, LM Studio, the browser VRAM calculators.
They answer *"will this model fit, and how do I start it?"*, on whatever hardware you put
them on. Also excellent, and entirely unaware that a paid API exists.

**Top-right — a decision that has been checked.** `best-engine-ai-helper` sits alone
there, and the honest detail is that it is not alone on the horizontal axis: `llmfit` lands
at the *same* coordinate, both of them at its maximum. On "knows the machine in front of
it" the two are tied, which is the correct reading — `llmfit` and this project now both
*measure* decode speed rather than estimating it. The gap is vertical, and it is two full
units: `llmfit` measures and reports, where this project measures, then lets the number
disqualify a model and re-weight every estimate that follows.

**The gap is still the top-right.** No surveyed tool combines *"what does this machine
run"* with *"what would a provider charge, and do I even hold that key"* in a single
decision. That is not a claim about quality; it is a claim about coverage, and it is what
this project is for.

### The column this project loses

**Catalog breadth: ⭐⭐⭐⭐ against `llmfit`'s ⭐⭐⭐⭐⭐.** This column read ⭐⭐ until
2026-10-20, and the reason it gave was wrong. It blamed provenance discipline: twenty
hand-maintained entries, every one carrying a `source:` and a `fetched_at`, because an
entry with no provenance is worth less than no entry. That sounded like a principled
trade-off. It was a misdiagnosis. `catalog update --ollama` now reaches **420
pullable tags** in a single request — the official library lists 257 families, 221 of
which declare the sizes they ship, and a family plus a size is a pull tag. Every one of
those entries carries the same `source:` and `fetched_at` as the seed. Provenance was never
what held the catalog at twenty; a naming mismatch was. ApXML names models by the paper's
slug, which `ollama pull` cannot resolve, so the one automatic source available could add
hundreds of entries without widening what could actually be served.

What did *not* change is the part worth being precise about. Those 420 entries carry null
scores on all five benchmark axes, because the library publishes sizes and descriptions
rather than leaderboard results — so they rank *below* every scored model until a scored
source fills them in. The breadth of what this tool can size, fit and pull is now in the
hundreds; the breadth of what it can **rank on quality** is still the twenty curated
entries. A null ranks low and stays honest, where a guessed score would rank wrongly
while looking authoritative.

That is also why this is ⭐⭐⭐⭐ and not ⭐⭐⭐⭐⭐: `llmfit` ships its hundreds in the box,
with no network call and nothing to opt into. Here the breadth is one command and one
request away, which is close enough to matter and not the same thing.

The column stays on the map on purpose. A landscape where the author wins every column is
a landscape nobody believes — and the useful lesson is the one this entry just
demonstrated against itself: a page that explains a weakness is asserting a cause, and a
cause goes stale exactly like a number does. The old ⭐⭐ survived a day longer than the
limitation it described.

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
- **airllm: "does it fit?" is the wrong question when a transformer is sequential.**
  Every tool on this map, this one included, answered *which model fits the memory I
  have*. airllm points out that a decoder reads its layers in order, so only the layer
  being computed has to be resident — and the memory a model needs collapses from its
  parameter count to its widest single layer. That is a genuinely different idea rather
  than a better estimate, and it is now the `airllm` backend here (see the README).
  What this project adds on top is the part airllm has no reason to own: whether *this*
  machine should take the trade, which model it should stream, and what the better model
  will cost in seconds per token versus the one that already fits. The runtime is
  imported, not copied — the arithmetic and the decision are native.

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

### airllm

Not a selector at all, and not trying to be: a layer-streaming *runtime*. It splits a
checkpoint into per-layer shards and reads them back one at a time, so a 70B model runs
in about 4 GB of resident memory instead of 141 — no quantisation, no distillation, no
pruning. The cost is that every token re-reads the whole checkpoint from disk, which puts
it at seconds per token rather than tokens per second.

The most interesting entry on this map, because it does not compete with anything else on
it: it changes what the word "fits" means. Where it stops is exactly where this project
starts — airllm will happily stream a 671B model onto a drive with no room for the split,
at two minutes a token, and has no opinion about whether you should. Those judgements
(resident footprint, disk required for the split, seconds per token, and native-versus-
streamed priced in the same unit) are native here, and the runtime is imported as a core
dependency rather than hidden behind an extra. Apache-2.0.

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

## When to pick what

The honest answer is often another entry on this map.

**Pick `llmfit`** when the question is purely local and you want the widest catalogue in the
box, with no network call and nothing to configure. It ties this project on hardware
detection and on measured decode speed, and it ships hundreds of scored models where this
one ships twenty curated ones plus whatever `catalog update --ollama` adds. If no paid API
is ever going into the decision, the extra machinery here buys nothing.

**Pick LiteLLM or OpenRouter** when every call is already going to a provider and the
problem is plumbing: one surface over many providers, with keys, budgets, retries and
fallbacks. Neither will ever suggest running the job locally for nothing, which is the
right behaviour when that was never on the table. LiteLLM if you want to run the gateway
yourself; OpenRouter if you would rather not.

**Pick RouteLLM or Not Diamond** when the routing decision has to be made per request
rather than per repository. A learned router sees the prompt; a brief only sees the job
description. The trade is that a brief is a reviewable file under version control and a
classifier is a model.

**Pick Ollama or LM Studio** when you have already decided which model to run and simply
want it served. That is most days, and it is why this project resolves *to* Ollama instead
of replacing it.

**Pick airllm directly** when you already know you want layer streaming and need nothing
to size it, refuse it or price it against the model that fits.

**Pick a browser VRAM calculator** when you want a five-second answer before a hardware
purchase and nothing has to end up in a pipeline.

**Pick this one** when the decision spans both worlds: when *"run it locally for free"* and
*"pay a provider per token"* are both live options, when the answer has to differ per
machine without the repository changing, and when you want a pick **refused** rather than
merely reported if it is too slow, too large for the disk, or backed by a key you do not
hold.

## Sources and as-of date

**Surveyed 2026-10-19.** Every claim about another project in this document was read that
day from that project's own public documentation, repository or command-line help — nothing
here is a benchmark this project ran against a competitor. One cell, catalog breadth, was
re-measured on 2026-10-20 and the write-up explaining it was rewritten; see [the column
this project loses](#the-column-this-project-loses). No competitor claim has been
re-checked since 2026-10-19, which is the date a reader should hold them to.

Where the entries were read. The links below point at each project's canonical
home, not at a dated page: no version number is cited anywhere in this document,
deliberately, because a version is the part of a claim that goes stale fastest
and none of the readings here depended on one.

- **airllm** — [github.com/lyogavin/airllm](https://github.com/lyogavin/airllm), Apache-2.0.
  The "70B in about 4 GB of resident memory" figure is the project's own headline claim,
  not an independent measurement.
- **LiteLLM** — [github.com/BerriAI/litellm](https://github.com/BerriAI/litellm).
- **RouteLLM** — [github.com/lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM), LMSYS
  and UC Berkeley. The "up to 85% savings at ~95% of GPT-4 quality" figure comes from the
  project's own published results.
- **OpenRouter** — [openrouter.ai](https://openrouter.ai).
- **Not Diamond** — [notdiamond.ai](https://www.notdiamond.ai).
- **Ollama** — [ollama.com](https://ollama.com).
- **LM Studio** — [lmstudio.ai](https://lmstudio.ai).
- **llmfit** — its own README and the output of `llmfit info` / `llmfit bench`. No URL is
  recorded here, deliberately: the entry describes behaviour that was read, and a link
  invented after the fact would look like a citation without being one.
- **Browser VRAM calculators** — `modelfit.io`, `llmconfigurator.com`,
  `willitrunai.com`, read as published pages.

The **60-85%** routing-savings band quoted under [Ideas taken from the
field](#ideas-taken-from-the-field) is a range of vendor-published figures across the
cloud routers, not an independent measurement, and mixed-workload savings depend entirely
on the mix. Treat it as the reason a cost axis exists here, not as a number to plan with.

Where this project's own numbers come from:

- **The star ratings are a judgement, not a measurement.** They score each tool's
  documented capabilities against the job stated at the top of this page. A tool built for
  a different job scores low here and is not being criticised.
- **The two axes and their loadings** are a PCA over `assets/landscape.csv`, computed by
  [`standpoint`](https://github.com/warith-harchaoui/standpoint), so the figure is
  re-derivable from the table above rather than drawn by hand. The pole *names* are written
  by a model and do move between runs; the loadings do not.
- **Catalog figures** — 420 pullable tags, 257 families, 221 declaring their sizes — are
  this project's own measurement from the `catalog update --ollama` run of 2026-10-20
  against the official Ollama library.
- **Benchmark scores and prices** in the bundled catalogues
  (`best_engine_ai_helper/data/models.yaml`, `pricing.yaml`) each carry their own `source:`
  and `fetched_at` field, which is where to look for the provenance of any single figure
  rather than here.
