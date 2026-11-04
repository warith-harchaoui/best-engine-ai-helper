# best-engine-ai-helper non-CLI surfaces

Unlike the rest of the suite, **the CLI, GUI, HTTP API and MCP server are all
in the default install**. There are no `[api]` / `[mcp]` extras to opt into;
the extras are for what runs a model or reaches a paid one: `[cloud]`
(hosted providers), `[lightweight]` (layer streaming), `[imagine]`
(text-to-image), `[filtered]` (CLIP safety screening) and `[generate]`.

## 1. Library — the surface other packages use

```python
import best_engine_ai_helper as be
```

### The three calls downstream code needs

```python
be.text_model()  # the resolved local LLM for this machine
be.vision_model()  # the resolved local VLM
be.resolved_models()  # both, plus how they were resolved
```

That is the whole contract for a consuming package. Nothing downstream
hardcodes a model name, and nothing downstream re-runs detection.

### The rest of the API

- **Hardware** — `platform_name`, `chip_vendor`, `chip_name`,
  `available_memory`, `compute_profile`, `load_hardware`, `lookup_chip`.
- **Catalogue and ranking** — `load_catalog`, `rank`, `select`,
  `estimate_ram`, `model_footprint_gb`, `effective_budget`,
  `estimated_tokens_per_second`, `MAX_HEADROOM`.
- **Recommendation** — `recommend_engines`, `parse_task`, `to_markdown`,
  `write_report`.
- **Resolution and environment** — `resolve`, `ensure`, `write_engine`,
  `load_engine`, `model_for`, `default_backend`, `load_config`,
  `DEFAULT_TEXT_MODEL`, `DEFAULT_VISION_MODEL`, `BRIEF_NAME`, `ENGINE_NAME`.
- **Usages and families** — `list_usages`, `list_families`, `get_usage`,
  `get_family`, `load_usages`, `load_families`, `usage_brief`, `family_brief`,
  `resolve_usage`, `resolve_family`.

Logging and file management route through `os_helper` — the suite convention,
and the only hardware probing path this package uses.

## 2. CLI — click

`best-engine-ai-helper`, the one command line this package ships. See
`cli-reference.md` for every command.

## 3. HTTP API — FastAPI (default install)

```bash
best-engine-ai-helper gui           # serves the app, GUI included
```

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | redirect to the GUI |
| GET | `/gui` | the bilingual browser page |
| GET | `/api/system` | hardware snapshot |
| GET / POST | `/api/preferences` | read / save `~/.best-engine-ai-helper/preferences.yaml` |
| GET | `/api/providers` | which cloud providers are usable (never a key) |
| POST | `/api/recommend` | task description → ranked engines |
| GET | `/api/lightweight` | layer-streaming decision, plans and comparison |
| GET | `/api/activity` | the call and cost ledger summary |
| … | `/v1/*` | the OpenAI-compatible inference routes (see `cli-reference.md`, `serve`) |

The `/api/*` routes cover detection and recommendation, plus saving
preferences. Pulling weights and writing the environment file stay on the CLI
deliberately: they change the machine.

## 4. MCP — `fastapi-mcp` over the *same* app (default install)

```bash
best-engine-ai-helper-mcp           # same app, MCP mounted at /mcp
```

`best_engine_ai_helper.mcp` takes the FastAPI app and mounts `FastApiMCP` on
it. Every MCP tool *is* an HTTP route, so the two surfaces cannot drift and
one process serves both doors.

Register it with Claude Code:

```bash
claude mcp add best-engine --transport http http://127.0.0.1:8000/mcp
```

Every `/api/*` route is a tool, `POST /api/preferences` included (it writes
`preferences.yaml`, never `settings.yaml`); the `/v1` inference routes are
not. An agent holding these tools can advise and save preferences, but cannot
download weights or rewrite the environment file.

## 5. Bilingual GUI

`GET /gui` — French by default, English at `/gui?lang=en`, with a header link
to switch. It covers the hardware snapshot and the task-to-engine
recommendation without touching the terminal. See the repo's `GUI.md`.

## 6. Layer streaming — the one backend with no server

`lightweight` is a library, not a daemon, so a streamed model runs **in the caller's
own process**. The engine descriptor's `base_url` is empty on purpose: a
localhost port would send a consumer looking for something that will never
exist. `llm.chat` dispatches on the backend name, keeps the loaded model
between calls (splitting a 141 GB checkpoint per call would make the transport
unusable), and raises rather than accepting images or a JSON schema, neither of
which this runtime can honour.

The read-only half is on every other surface: `lightweight status|plan|compare` on
the CLI, `GET /api/lightweight?answer_tokens=300&batch=8` over HTTP (decision +
storage profile + ranked plans + native-vs-streamed comparison in one call),
the same route as an MCP tool, and a "Too large to load, still runnable" panel
in the GUI in both languages.

## Where this sits in the suite

```
best-engine-ai-helper  ◄── md2star        (reference implementation)
                       ◄── standpoint
                       ◄── vocal-helper
```

Three published packages already route every LLM and VLM call through it.
`os-helper`, the dependency-free foundation, must never mention a model at
all — that is what keeps the heavy concern out of every package in the suite.
