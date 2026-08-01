# GUI — Best Engine AI Helper

A minimal single-page GUI, served by a small FastAPI app, for the two things
you'd otherwise run `detect` and `report` for: seeing this machine's hardware,
and getting the best local engine(s) for a task description — without leaving
the browser.

Keeps the AI Helpers suite's house style: **vanilla JS + Tailwind (CDN), no
build step, no framework, no npm.** The GUI is a thin client over the same
library calls the CLI uses — `detect.available_memory()`,
`detect.compute_profile()`, `score.effective_budget()`, and
`recommend.recommend()` — so its numbers always match `best-engine-ai-helper
detect` / `report` run at the same moment.

## Install and run

```sh
pip install 'best-engine-ai-helper[api]'
best-engine-ai-helper gui
# open http://127.0.0.1:8000/gui
```

`gui` is a thin wrapper around Uvicorn (`--host` / `--port` to change the
bind address). Equivalent, if you want the ASGI app directly:

```sh
uvicorn best_engine_ai_helper.api:app --port 8000
```

## What it shows

### 1. Caractéristiques système (hardware snapshot)

Plateforme, fournisseur / puce, accélérateur, bande passante mémoire, et le
budget mémoire utilisable (`effective_budget`, after the Apple Metal
GPU-usable cap and the safety headroom — see the README's "How selection
works"). A **Rafraîchir** button re-probes the machine without reloading the
page, useful right after plugging in an eGPU or closing memory-heavy apps.

![Hardware panel](assets/screenshots/gui-hardware.png)

### 2. Décrire la tâche → best engine(s)

Type a free-text task — the same kind of phrase `report --task "..."` takes —
and the page shows, per model kind the task needs (LLM for text, VLM when
anything visual is mentioned): the detected keywords and benchmark axis, the
chosen model with its RAM footprint / benchmark score / estimated tokens per
second, a lighter alternative when one is nearly as strong, and the full
ranked candidate table behind a disclosure toggle.

![Recommendation results](assets/screenshots/gui-recommendation.png)

The memory headroom (default `0.85`) is editable next to the button, matching
`report --headroom`.

## HTTP surface

The GUI is a client of two JSON endpoints, usable directly (e.g. from another
tool, or `curl`):

| Method | Path | Body | Returns |
|--------|------|------|---------|
| `GET`  | `/api/system` | — | hardware + compute profile + `memory_budget_gb` |
| `POST` | `/api/recommend` | `{"task": str \| null, "headroom": float}` | the same report `recommend()` / `report` produce, as JSON |

```sh
curl -s http://127.0.0.1:8000/api/system | python3 -m json.tool

curl -s -X POST http://127.0.0.1:8000/api/recommend \
     -H 'Content-Type: application/json' \
     -d '{"task": "product descriptions and image-quality checks"}' \
  | python3 -m json.tool
```

`GET /` redirects to `/gui`. `GET /docs` (FastAPI's default) has the full
OpenAPI schema.

## Icons

`assets/logo.png` (the engraved glove) is the source of every icon the page
serves: `favicon.ico`, 16/32 px favicons, `apple-touch-icon.png`, and the two
Android/PWA sizes referenced from `site.webmanifest`. All are generated —
never hand-edited — by `scripts/generate_icons.py`, which composites the logo
onto the suite's cream background (`#f7f3ea`) so it reads on light and dark
browser chrome alike. Re-run it whenever `assets/logo.png` changes:

```sh
python scripts/generate_icons.py
```

## What it deliberately doesn't do

- **No pull / validate from the browser.** `pull` downloads multi-gigabyte
  weights and runs the Ralph gates; that stays a deliberate, watched CLI
  action, not a button click.
- **No persistence.** Every recommendation is a fresh, stateless call; nothing
  is written to `~/.best-engine-ai-helper/` from the GUI.
- **No auth, no remote exposure by default.** `gui` binds to `127.0.0.1`.
  Passing `--host 0.0.0.0` is your call, not the default.
