# Landscape

[🇫🇷 PAYSAGE.md](PAYSAGE.md) · 🇬🇧 English

Tools that answer some version of *"which model should I use?"*, compared against
`best-engine-ai-helper`. Ratings are ⭐ (1) to ⭐⭐⭐⭐⭐ (5), scored on this project's
intended job: **decide between a free local model and a paid cloud one, on the hardware
you actually have and the API keys you actually hold, and prove the choice works.**

A tool optimised for a different job is not being criticised; the score reflects fit to
*this* niche. Several of the entries below are excellent at theirs.

Re-surveyed 2026-10-29, which added three entries and moved the conclusion. Nine
criteria, twelve tools. Two cells this project loses are written up rather than buried —
see [the columns this project loses](#the-columns-this-project-loses).

## At a glance

<!-- TABLE:START -->
| Model selection | Hardware detection | Local fit | Measures speed on this machine | Paid models in the same decision | Routes on keys present | Scores carry provenance | Catalog breadth | Verifies quality before you depend on it | Programmatic API |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **best-engine-ai-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| llmfit | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| AMD Lemonade | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| ngrok AI Gateway | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| RouteLLM | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| LiteLLM | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| OpenRouter | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ |
| Not Diamond | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Ollama | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ |
| LM Studio | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ |
| Browser VRAM calculators | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ |
| Break-even calculators | ⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐ | ⭐ | ⭐ |
<!-- TABLE:END -->

## Three abilities, and the one region with a single occupant

![Three families of tool: knows this machine, reaches the paid providers, prices one against the other — and the centre where all three meet](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/three-families.png)

Before the map, the shape of the field in plain terms. Three abilities are in play and
almost nobody has more than one of them. **Knowing this machine** — detecting its memory
and sizing a model against it — belongs to `llmfit`, Ollama, LM Studio and the browser
VRAM calculators. **Reaching the paid providers** through one surface belongs to LiteLLM,
OpenRouter, Not Diamond, RouteLLM and the ngrok AI gateway. **Pricing the two worlds
against each other** belongs only to the break-even calculators, and they do it from a
monthly token volume you type in.

One tool sits in a two-way overlap: AMD Lemonade detects CPU, GPU and NPU, and an
experimental cloud-offload setting hands a request to an OpenAI-compatible provider. The
other two two-way overlaps are empty. So is everything else in the middle.

## Positioning map

<!-- FIGURE:START -->
2D representation of the table above, by PCA (see [`standpoint`](https://github.com/warith-harchaoui/standpoint)).

![Positioning map](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/landscape.png)

Read it as a shape, not a scoreboard. The figure prints **Horizontal — Valuable ↔
Resourceful** and **Vertical — Adaptable ↔ Connected**, and those pole names are written by
the model that drew the map — the loadings under them are the part that does not change
between runs, so read those. Horizontal is built almost entirely from local fit (0.50),
measured decode speed (0.50) and hardware detection (0.49): *right* means **knows the
machine in front of it**. Vertical is built from routing on keys present (0.51), paid
models in the same decision (0.50), verified quality (0.45) and the programmatic API
(0.43): *up* means **decides across both worlds, then checks the answer**. The two carry
70% of the variance between them, so nearly a third of the table is not on this picture —
less than the 75% the nine-tool version carried, which is what adding three tools that
disagree with each other does to a plane.
<!-- FIGURE:END -->

## What the map actually shows

Three readings. The third is new, and it is the one that costs this project a sentence it
used to enjoy writing.

**Left — reach, blind to the machine.** LiteLLM, OpenRouter, Not Diamond, RouteLLM, the
ngrok gateway. They reach hundreds of models through one surface and answer *"which
provider should this request go to, and what will it cost?"*. Excellent at that. The
gateway can be pointed at a local Ollama or vLLM endpoint, which is a real difference from
the rest of its column and still not the same thing: it will route *to* a local model you
already chose and has no way to tell you which one fits.

**Bottom — fit, blind to the bill.** Ollama, LM Studio, the browser VRAM calculators.
They answer *"will this model fit, and how do I start it?"*, on whatever hardware you put
them on. Also excellent, and entirely unaware that a paid API exists.

**Top-right — and it is no longer an empty corner this project happens to stand in.**
`best-engine-ai-helper` lands at (2.68, 1.93), and the two numbers are both ties rather
than wins. `llmfit` sits at **exactly the same horizontal coordinate**, 2.68: on "knows
the machine in front of it" the two are indistinguishable, which is the correct reading —
both detect the hardware and both *measure* decode speed rather than estimating it. The
ngrok AI gateway sits at **exactly the same vertical coordinate**, 1.93: on "decides
across both worlds" the two are indistinguishable too, because a gateway that mixes
hosted providers and self-hosted endpoints under one policy, with failover across models,
providers and keys, is doing that.

So the honest claim is narrower than "alone in the corner", and sharper: **this project is
best on neither axis, and it is the only entry that is not near the bottom of one.**
`llmfit` is at -0.03 vertically; ngrok is at -2.34 horizontally. Covering both is the
whole product, and the map now says so by arithmetic instead of by absence.

### The columns this project loses

Two, and the second one is new.

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
hundreds; the breadth of what it can **rank on quality** is still the curated entries plus
whatever two sources agree on. A null ranks low and stays honest, where a guessed score
would rank wrongly while looking authoritative.

That is also why this is ⭐⭐⭐⭐ and not ⭐⭐⭐⭐⭐: `llmfit` ships its hundreds in the box,
with no network call and nothing to opt into. Here the breadth is one command and one
request away, which is close enough to matter and not the same thing.

**Accelerator coverage, which has no column and should be read into "hardware
detection".** AMD Lemonade routes across CPU, GPU **and NPU** — `lemonade backends`
reports what is on the machine, and on Ryzen AI hardware it will put prompt processing on
the XDNA2 NPU and token generation on the GPU. This project knows three memory pools:
Apple unified, discrete VRAM, system RAM. It has **no notion of an NPU at all**, so on a
Ryzen AI laptop it sizes against the GPU or the RAM and silently ignores the third
accelerator sitting there. Both tools score ⭐⭐⭐⭐⭐ on hardware detection and that is
generous to this one: the star rating is about whether the machine is *detected*, and on
*which accelerators can be used* Lemonade is simply ahead. Writing it here rather than
inventing a tenth column, because a column added the moment a competitor wins it is not a
criterion, it is a scoreboard.

Both columns stay on the map on purpose. A landscape where the author wins every column is
a landscape nobody believes — and the useful lesson is the one the catalog-breadth entry
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
- **`llmfit` again: a measurement is worth more when it is shared.** `llmfit bench
  --share` sends a measured tok/s figure back to the project, so the next person's
  *estimate* is grounded in somebody's real hardware. This project measures decode speed
  on `pull` and `validate` and keeps the number strictly local — a deliberate choice,
  since the promise at the top of the README is that nothing leaves the machine, and a
  benefit genuinely forgone rather than a feature nobody thought of.
- **AMD Lemonade: the accelerator is a routing decision, not a constant.** It picks a
  *backend* per model and per device — llama.cpp for GGUF, ONNX Runtime for optimised
  graphs, an NPU runtime on Ryzen AI — where this project picks between exactly two
  backends on one rule (vLLM on Linux with a discrete GPU, Ollama everywhere else). The
  NPU gap above is the visible half of that idea.
- **RouteLLM: route on the request, not on the account.** Its per-prompt classifier is a
  finer granularity than this project's per-usage-profile briefs. The trade is
  deliberate — a brief is declarative, reviewable and testable, where a learned router
  is none of the three — but the idea of routing on *what is being asked* rather than on
  *who is asking* is theirs.
- **The cloud routers: cost is a first-class axis.** Published figures put routing
  savings at 60-85% on mixed workloads. That is the reason `pricing.yaml` carries list
  prices and the picker exposes a quality-versus-cost weight rather than ranking on
  quality alone.
- **The break-even calculators: ask what the other world would have cost.** Their whole
  genre compares running a model here against paying for it there, and the weak joint is
  always the same — you type in a monthly token volume before you have run the workload,
  and the payback period you read back inherits the guess. The activity ledger already
  holds the workload, measured, so `best-engine-ai-helper activity --what-if` crosses it
  with the same price table the ledger bills paid calls against: what the local calls you
  **already made** would have cost at list price, cheapest provider first. It is reported
  as an *avoided bill*, never as a saving — electricity, disk and the slower model's time
  are real costs and this ledger measures none of them.
- **lightweight: "does it fit?" is the wrong question when a transformer is sequential.**
  Every tool on this map, this one included, answered *which model fits the memory I
  have*. lightweight points out that a decoder reads its layers in order, so only the layer
  being computed has to be resident — and the memory a model needs collapses from its
  parameter count to its widest single layer. That is a genuinely different idea rather
  than a better estimate, and it is now the `lightweight` backend here (see the README).
  What this project adds on top is the part lightweight has no reason to own: whether *this*
  machine should take the trade, which model it should stream, and what the better model
  will cost in seconds per token versus the one that already fits. The runtime is
  imported, not copied — the arithmetic and the decision are native.

## Per-tool write-up

### llmfit

The nearest neighbour on the map, and the one that ties this project exactly on the
horizontal axis. Detects CPU, system RAM, GPUs, VRAM and accelerator configuration, then
scores its catalogue on memory fit, estimated speed, quality and context, across GGUF,
AWQ, GPTQ and EXL2 and with mixture-of-experts layers handled specially. Its speed model
is memory-bandwidth-based and grounded in community measurements; `llmfit bench` measures
real tok/s on your machine and `llmfit bench --share` contributes the figure back.
`llmfit info` shows the inputs behind any number — the same transparency instinct as this
project. Its "providers" are *local runtimes* — Ollama, llama.cpp, MLX, Docker Model
Runner, LM Studio — not paid APIs. Where it stops: local only, which is the whole vertical
axis.

### AMD Lemonade

New to this survey. An AMD-backed local server that serves LLMs, image generation and
speech from one install, exposing an OpenAI-compatible endpoint plus a CLI and an
embeddable binary. The interesting part is the hardware: it detects and routes across
CPUs (x86_64, ARM64), GPUs (CUDA, ROCm, Vulkan, Metal) and **NPUs** (XDNA2, Ryzen AI),
picking a backend per model and device, and the Lemonade Router added in v11.5.0 sends a
request to the most suitable *already-installed* model. An experimental Cloud Offload
setting can hand a request to an OpenAI-compatible provider. Where it stops: there is no
published quality ranking — it chooses between models you installed rather than telling
you which to install — and the cloud half is a configuration you write, not a decision it
makes. The NPU gap it exposes here is real, and the honest reason it is not an action item
is that this project cannot test one.

### ngrok AI Gateway

New to this survey; general availability 2026-06-23. One endpoint in front of hosted
providers *and* self-hosted ones — Ollama, vLLM, LM Studio, or any OpenAI-compatible
custom provider — with CEL expressions deciding which model a request gets, automatic
failover across models, providers and keys, managed or bring-your-own credentials, token
counting and a traffic inspector. It is the first entry in this survey that genuinely mixes
local and paid inference in one decision, which is why it ties this project's vertical
coordinate. Where it stops is the horizontal axis: it has no idea what the machine behind
the local endpoint can run. It will route to `ollama/llama3:70b` on a 16 GB laptop and
report the failure afterwards. Managed service, so the policy lives on ngrok's network.

### RouteLLM

From LMSYS and UC Berkeley. A per-prompt classifier choosing between a strong frontier
model and a weak cheap one, with published savings up to 85% at ~95% of GPT-4 quality.
Finer granularity than a usage brief, and not reviewable or testable the way a YAML brief
is. Complementary: a brief could reasonably resolve *to* RouteLLM.

### LiteLLM

The de-facto open-source gateway: one OpenAI-shaped surface over a hundred providers,
with keys, budgets, fallbacks and retries. It routes; it does not choose, and it does not
know the machine exists. This project reads its public price table — the one source that
turned `pricing.yaml` from a hand-typed list into a refreshable one.

### OpenRouter

The managed version of the same idea, with a marketplace and a markup. Zero operational
overhead, at the cost of every request leaving your network.

### Not Diamond

A managed learned recommender optimising quality-per-dollar. Closest in intent to this
project's picker, opposite in posture: the decision happens on someone else's servers,
against a catalogue you cannot read, and local models are not in it.

### lightweight

Not a selector at all, and not trying to be: a layer-streaming *runtime*. It splits a
checkpoint into per-layer shards and reads them back one at a time, so a 70B model runs
in about 4 GB of resident memory instead of 141 — no quantisation, no distillation, no
pruning. The cost is that every token re-reads the whole checkpoint from disk, which puts
it at seconds per token rather than tokens per second.

The most interesting entry on this map, because it does not compete with anything else on
it: it changes what the word "fits" means. Where it stops is exactly where this project
starts — lightweight will happily stream a 671B model onto a drive with no room for the split,
at two minutes a token, and has no opinion about whether you should. Those judgements
(resident footprint, disk required for the split, seconds per token, and native-versus-
streamed priced in the same unit) are native here, and the runtime is imported as a core
dependency rather than hidden behind an extra. Apache-2.0.

It is not scored in the table above, for the reason this paragraph gives: it answers a
different question, and a star rating against "which model should I use?" would be a
category error dressed as a measurement.

### Ollama

The local-first runner most of this suite actually uses. Pulls and serves models with one
command. Deliberately opinionated and deliberately not a selector: `ollama run` assumes
you already decided.

### LM Studio

A desktop application with a model browser that does warn when a model will not fit. The
closest any GUI gets to selection, and it stops at a warning: no ranking, no validation,
no scriptable surface.

### Browser VRAM calculators

`modelfit.io`, `llmconfigurator.com`, `willitrunai.com`, `llmhardware.io` and others.
Type your VRAM, read which sizes fit, usually with the KV-cache arithmetic shown. Genuinely
useful for a five-second sanity check before a purchase, and structurally incapable of
being part of a pipeline. They score ⭐⭐⭐⭐ on local fit and ⭐ on hardware detection for
the same reason: the arithmetic is sound and the inputs are typed in by hand.

### Break-even calculators

New to this survey, and a genre rather than a tool: `runyard.dev`'s API-cost-versus-local
calculator, `llmconfigurator.com`'s local-versus-cloud guide, and a long tail of 2026 blog
posts with the same spreadsheet behind them. You enter a monthly token volume, a GPU price
and an electricity rate; they return a payback period, typically landing between 5 and 20
million tokens a month depending on which models are being compared. They are the only
entry here whose subject *is* "here versus there", and the only one with no catalogue, no
hardware detection and no way to be called from code. The weak joint is the volume: it is
a guess made before the workload exists, and everything downstream inherits it. That
observation is what `activity --what-if` is for.

## When to pick what

The honest answer is often another entry on this map.

**Pick `llmfit`** when the question is purely local and you want the widest catalogue in the
box, with no network call and nothing to configure. It ties this project on hardware
detection and on measured decode speed, and it ships hundreds of scored models where this
one ships a curated seed plus whatever `catalog update` adds. If no paid API is ever going
into the decision, the extra machinery here buys nothing.

**Pick AMD Lemonade** when the machine has an NPU, or when the point is serving rather
than deciding: it will use accelerators this project cannot see, and it serves text, images
and speech from one install. Pair the two rather than choose, if you like — nothing stops a
brief resolving to a model Lemonade then serves.

**Pick the ngrok AI gateway** when the decision is already made and the problem is traffic:
one endpoint over hosted and self-hosted models, with failover, policy and credentials
managed centrally. It is the only other entry that spans both worlds, and it spans them at
the routing layer rather than at the choosing layer.

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

**Pick lightweight directly** when you already know you want layer streaming and need nothing
to size it, refuse it or price it against the model that fits.

**Pick a browser VRAM calculator** when you want a five-second answer before a hardware
purchase and nothing has to end up in a pipeline.

**Pick a break-even calculator** when the question is capital, not configuration: whether
to buy the GPU at all. It wants a workload you can only estimate; once the workload exists,
`activity --what-if` answers the same question from what actually ran.

**Pick this one** when the decision spans both worlds: when *"run it locally for free"* and
*"pay a provider per token"* are both live options, when the answer has to differ per
machine without the repository changing, and when you want a pick **refused** rather than
merely reported if it is too slow, too large for the disk, or backed by a key you do not
hold.

## Sources and as-of date

**Re-surveyed 2026-10-29.** Every claim about another project in this document was read
from that project's own public documentation, repository or command-line help — nothing
here is a benchmark this project ran against a competitor. The 2026-10-29 pass added AMD
Lemonade, the ngrok AI gateway and the break-even-calculator genre, re-read `llmfit`'s own
repository (which is where the `bench --share` and local-runtime-provider facts come from,
and which supersedes the previous survey's note that no URL had been recorded), and left
the other entries' readings at their 2026-10-19 date. Where an entry has not been
re-checked, that earlier date is the one a reader should hold it to.

Where the entries were read. The links below point at each project's canonical
home, not at a dated page: no version number is cited anywhere in this document,
deliberately, because a version is the part of a claim that goes stale fastest
and none of the readings here depended on one. The two exceptions are named as
dates in the prose — Lemonade's router and ngrok's general availability — because
both are "this did not exist at the last survey" facts and a date is the claim.

- **layer streaming** — implemented in this package (`streaming.py`) over
  torch, transformers, accelerate and safetensors. It used to be the
  third-party `airllm`; that dependency was dropped because it could not run
  a non-Llama architecture on Apple Silicon and wrote a second copy of every
  checkpoint to disk before running.
  The "70B in about 4 GB of resident memory" figure is the project's own headline claim,
  not an independent measurement.
- **llmfit** — [github.com/AlexsJones/llmfit](https://github.com/AlexsJones/llmfit),
  read 2026-10-29. Several forks publish the same README with different model counts in
  the tagline; the counts are not quoted here for that reason.
- **AMD Lemonade** — [github.com/lemonade-sdk/lemonade](https://github.com/lemonade-sdk/lemonade),
  read 2026-10-29. The router's completion in v11.5.0 (2026-07-22) and the NPU/GPU split
  figures are AMD's own published claims.
- **ngrok AI Gateway** — [ngrok.com/docs/ai-gateway](https://ngrok.com/docs/ai-gateway/overview),
  read 2026-10-29. General availability 2026-06-23 is ngrok's own announcement.
- **LiteLLM** — [github.com/BerriAI/litellm](https://github.com/BerriAI/litellm).
- **RouteLLM** — [github.com/lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM), LMSYS
  and UC Berkeley. The "up to 85% savings at ~95% of GPT-4 quality" figure comes from the
  project's own published results.
- **OpenRouter** — [openrouter.ai](https://openrouter.ai).
- **Not Diamond** — [notdiamond.ai](https://www.notdiamond.ai).
- **Ollama** — [ollama.com](https://ollama.com).
- **LM Studio** — [lmstudio.ai](https://lmstudio.ai).
- **Browser VRAM calculators** — `modelfit.io`, `llmconfigurator.com`,
  `willitrunai.com`, `llmhardware.io`, read as published pages.
- **Break-even calculators** — `runyard.dev`'s API-cost-versus-local-cost tool and
  `llmconfigurator.com`'s local-versus-cloud guide, read 2026-10-29, plus the surrounding
  2026 blog literature. The "5 to 20 million tokens a month" band is the range those pages
  quote, not an independent measurement, and it depends entirely on which two models are
  being compared.

The **60-85%** routing-savings band quoted under [Ideas taken from the
field](#ideas-taken-from-the-field) is a range of vendor-published figures across the
cloud routers, not an independent measurement, and mixed-workload savings depend entirely
on the mix. Treat it as the reason a cost axis exists here, not as a number to plan with.

Where this project's own numbers come from:

- **The star ratings are a judgement, not a measurement.** They score each tool's
  documented capabilities against the job stated at the top of this page. A tool built for
  a different job scores low here and is not being criticised.
- **The two axes, their loadings and every coordinate quoted above** are a PCA over
  `assets/landscape.csv`, computed by
  [`standpoint`](https://github.com/warith-harchaoui/standpoint), so the figure is
  re-derivable from the table above rather than drawn by hand. The pole *names* are written
  by a model and do move between runs; the loadings and the coordinates do not.
- **Catalog figures** — 420 pullable tags, 257 families, 221 declaring their sizes — are
  this project's own measurement from the `catalog update --ollama` run of 2026-10-20
  against the official Ollama library.
- **Benchmark scores and prices** in the bundled catalogues
  (`best_engine_ai_helper/data/models.yaml`, `pricing.yaml`) each carry their own `source:`
  and `fetched_at` field, which is where to look for the provenance of any single figure
  rather than here.

## Ideas worth stealing

Researched rather than guessed: what each neighbour does better, and what this library would have to change to match it. Nothing here is a commitment — it is the reading list the next version starts from.

- **`RouteLLM` — route per request, not once per machine** — It learns to send easy prompts to a cheap model and hard ones to a strong model, judging difficulty before answering. This helper picks the largest model that fits the machine, which is the right question asked once; the per-request question is a different and complementary one.

- **`AMD Lemonade` — the NPU is a third destination** — Routing across CPU and GPU covers most machines today and will not for long. Lemonade routes CPU, GPU and NPU, and a helper whose whole job is "what does this machine actually have" should know about the third one.

- **`LiteLLM` — budgets and rate limits as part of the router** — Picking a model and governing its spend are usually two libraries. For the paid catalogue this helper now carries, a per-key budget is the missing half of a price-aware recommendation.

- **`OpenRouter` — publish the price and latency behind each pick** — It shows cost and speed per model at the moment of choosing. This helper already crosses a price table with a quality board; surfacing both numbers on the recommendation makes the choice auditable rather than asserted.
