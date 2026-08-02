# Landscape

[🇫🇷 PAYSAGE.md](PAYSAGE.md) · 🇬🇧 English

Related tools in the "pick and run a local large language model" space, compared against
`best-engine-ai-helper`. Ratings are ⭐ (1) to ⭐⭐⭐⭐⭐ (5), scored on this project's
intended job: detect available hardware, select the highest-scoring model that fits within a
safety headroom, validate it with empirical quality gates, and write an environment file that
downstream projects consume. Tools optimised for a very different job are not penalised; the
score reflects fit to *this* niche.

## At a glance

<!-- TABLE:START -->
| Local LLM Selection | Auto hardware detection | Benchmark-ranked selection | Ralph validation gates | Offline catalog | CI-testable | Programmatic API |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| **best-engine-ai-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Ollama (CLI) | ⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| LM Studio | ⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ |
| Jan.ai | ⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ |
| llm (Simon Willison) | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| LocalAI | ⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| text-generation-webui | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐⭐ |
<!-- TABLE:END -->

## Positioning map

<!-- FIGURE:START -->
2D representation of the table above.

![Positioning map](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/landscape.png)

The map is a 2-D summary of the six criteria, so read it as a shape, not a scoreboard. `best-engine-ai-helper` is at the top-right corner. The axes read **Horizontal — Programmatic ↔ Automated** and **Vertical — Offline ↔ Testable**.
<!-- FIGURE:END -->

## Positioning

`best-engine-ai-helper` sits at the narrow intersection of hardware awareness, empirical
validation, and scriptable automation. Most tools in this space solve the *serving* problem
(how to run a model once you have chosen it). This project solves the *selection* problem
(how to choose the model in the first place, and prove it works on this specific machine).

## Per-tool write-up

### Ollama

Ollama is the runtime backend that `best-engine-ai-helper` uses for pulling and serving
models. It is excellent at what it does: a one-binary server with a clean REST API and a
broad model library. It does not, however, select models based on detected hardware or rank
candidates by benchmark score. You tell Ollama which model to pull; this project tells you
which model to pull.

### LM Studio

LM Studio is a cross-platform desktop application for browsing, downloading, and running
local models. Its hardware detection is partial: it warns you when a model is too large, but
it does not proactively rank candidates by benchmark score or automatically select the best
fit. It has no scriptable API for CI pipelines.

### Jan.ai

Jan.ai offers a similar GUI experience to LM Studio, with a clean interface and a curated
model hub. Like LM Studio, it is primarily interactive: no automatic hardware-based
selection, no quality gates, no programmatic surface for automation.

### llm (Simon Willison)

The `llm` command-line tool is an elegant, plugin-based interface to dozens of model
providers, both cloud and local. Its strength is breadth: one command, many backends. It
does not detect hardware or rank models by benchmark. It is the right choice when you know
which model you want and need a convenient CLI to talk to it.

### LocalAI

LocalAI is an OpenAI-compatible REST server that runs local models via llama.cpp and
similar backends. It is the right choice when you want to drop a local endpoint into
existing OpenAI client code. Selection and validation are left to the user.

### text-generation-webui (Oobabooga)

text-generation-webui is a full-featured web interface for running and fine-tuning local
models. It is GPU-focused, manually configured, and not designed for scripted automation or
CI pipelines. It is the right choice for interactive experimentation and fine-tuning
workflows.
