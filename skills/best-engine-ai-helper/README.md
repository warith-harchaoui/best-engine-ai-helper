# best-engine-ai-helper skill

This skill lets a Claude or OpenCode agent select, download, and validate the best local LLM
or VLM for the current machine. Once run, it writes `~/.best-engine-ai-helper/env.sh` with
four environment variables that every other AI-Helpers project consumes.

## What the skill does

1. Detects available memory (Apple Silicon unified pool, NVIDIA VRAM, or CPU RAM).
2. Consults the bundled model catalog and ranks candidates: structured-output capability
   first (a model that cannot honour Ollama's schema-constrained output is never chosen),
   then benchmark score, among those that fit the available memory budget (the accelerator
   cap plus a safety headroom).
3. Pulls the top candidate via Ollama.
4. Runs the Ralph Eyeball Loop (vision quality) and the Ralph prose loop (text quality) as
   empirical validation gates. If either gate fails, it removes the model and tries the next
   candidate.
5. Writes `~/.best-engine-ai-helper/env.sh` after both gates pass.

## Installation as a Claude / OpenCode skill

Copy or symlink this folder into your skills directory:

```sh
# Claude Code
cp -r skills/best-engine-ai-helper ~/.claude/skills/

# OpenCode
cp -r skills/best-engine-ai-helper ~/.opencode/skills/
```

Then install the package so the CLI is available:

```sh
pip install best-engine-ai-helper
# or: pip install -e ~/best-engine-ai-helper
```

## Environment variables exported

After `best-engine-ai-helper pull` succeeds, source the env file:

```sh
source ~/.best-engine-ai-helper/env.sh
```

| Variable | Example value | Purpose |
|----------|---------------|---------|
| `BEST_LLM_TEXT` | `gemma3:12b` | Text model tag for Ollama |
| `BEST_LLM_VISION` | `gemma3:12b` | Vision model tag for Ollama |
| `BEST_LLM_BACKEND` | `ollama` | Backend: ollama or openai |
| `BEST_LLM_BASE_URL` | `http://localhost:11434` | Server base URL |

Downstream projects (sprezzature-local, sprezzature-publish, sprezzature-vision) read these
as `SPREZZATURE_LLM_*` via a one-line mapping in their `.envrc`.
