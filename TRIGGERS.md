# TRIGGERS: best-engine-ai-helper

Exhaustive catalogue of what `best-engine-ai-helper` can do and the natural-language
phrasings that should invoke it, whether you call it directly or drive it as a Claude /
OpenCode skill.

`best-engine-ai-helper` selects, downloads, validates, and documents the best local LLM
or VLM for the current machine. It does **not** run inference itself; it configures the
environment so that other tools (Ollama, vLLM, sprezzature-local) can.

## Commands and how to invoke them

| Intent | CLI | Library function |
|--------|-----|-----------------|
| Show detected hardware | `best-engine-ai-helper detect` | `detect.available_memory()` |
| Rank models for this hardware | `best-engine-ai-helper recommend` | `score.rank(hw, catalog, kind)` |
| Select the best model | (part of `recommend`) | `score.select(hw, catalog, kind)` |
| Recommend engine(s) for a free-text task | `best-engine-ai-helper report --task "..."` | `recommend.recommend(hw, catalog, task)` |
| Resolve a committed brief into a per-machine engine file | `best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml` | `engine.resolve(brief)` / `engine.ensure(dir)` |
| Browse the full model catalog | `best-engine-ai-helper catalog show` | `catalog.load_catalog()` |
| Browse the hardware chip table | `best-engine-ai-helper hardware show` | `hardware.load_hardware()` |
| Pull the best model and validate | `best-engine-ai-helper pull` | `pull.ollama_pull(tag)` |
| Validate the current model | `best-engine-ai-helper validate` | `validate_vlm.validate()` + `validate_llm.validate()` |
| Print the env block | `best-engine-ai-helper env` | `pull.write_env(...)` |
| Refresh the model catalog | `best-engine-ai-helper catalog update` | `apxml.fetch_open_weight_models()` + `catalog.write_cache(...)` |
| Refresh the hardware table | `best-engine-ai-helper hardware update` | `hardware.detect_local_entry()` + `hardware.write_cache(...)` |
| Launch the browser GUI | `best-engine-ai-helper gui` | `uvicorn best_engine_ai_helper.api:app` |
| Open the GUI in English | `best-engine-ai-helper gui` → `/gui?lang=en` | `gui.render_gui("en")` |

## Natural-language phrasings that should fire

The following phrasings, in English or French, are signals that `best-engine-ai-helper` is
the right tool:

**English:**
- "what is the best model for my machine"
- "which model fits in my RAM"
- "pick the best local LLM for this hardware"
- "select a VLM that fits in 96 GB"
- "download the highest-scoring model that fits"
- "what model should I pull"
- "detect my hardware for Ollama"
- "how much memory do I have for a local model"
- "rank the models by benchmark for my machine"
- "validate the selected model"
- "run the Ralph gates on the model"
- "write the env file for sprezzature"
- "which qwen3 variant fits on my M2 Max"
- "resolve my project's llm.brief.yaml into an engine file"
- "pick the backend and model for this repo's brief"
- "make the gitignored llm.engine.yaml for this machine"
- "show the model catalog"
- "refresh the catalog from the leaderboard"
- "show available hardware chips"
- "open the GUI for the best model"
- "launch the browser interface"
- "show me my hardware in a web page"

**French:**
- « quel est le meilleur modèle pour ma machine »
- « quel modèle tient dans ma mémoire »
- « choisir le meilleur LLM local pour ce matériel »
- « sélectionner un VLM qui tient en 96 Go »
- « télécharger le modèle au meilleur score qui tient »
- « quel modèle dois-je télécharger »
- « détecter mon matériel pour Ollama »
- « combien de mémoire est disponible pour un modèle local »
- « classer les modèles par score pour ma machine »
- « valider le modèle sélectionné »
- « lancer les contrôles Ralph sur le modèle »
- « écrire le fichier d'environnement pour sprezzature »
- « quel variant qwen3 tient sur mon M2 Max »
- « résoudre le llm.brief.yaml de mon projet en fichier moteur »
- « choisir le backend et le modèle pour le brief de ce dépôt »
- « générer le llm.engine.yaml gitignoré pour cette machine »
- « afficher le catalogue de modèles »
- « rafraîchir le catalogue depuis le classement »
- « afficher les puces matérielles connues »
- « ouvrir la GUI pour le meilleur modèle »
- « lancer l'interface dans le navigateur »
- « montre-moi mon matériel dans une page web »

## What it does NOT do

- It does not run inference. Use Ollama, vLLM, or sprezzature-local for that.
- It does not fine-tune models.
- It does not manage datasets or training pipelines.
- It does not transcribe, generate audio, or process images directly.
- It does not connect to cloud APIs (Anthropic, OpenAI, Google). It is local-only.
- It does not cache model weights itself. Ollama manages the weight cache.

## Files read and written

| File | Location | Direction | Purpose |
|------|----------|-----------|---------|
| `models.yaml` | package root | read | Bundled model seed catalog |
| `hardware.yaml` | package root | read | Bundled chip lookup table |
| `catalog_cache.yaml` | `~/.best-engine-ai-helper/` | read+write | Auto-refresh model layer |
| `hardware_cache.yaml` | `~/.best-engine-ai-helper/` | read+write | Auto-refresh hardware layer |
| `env.sh` | `~/.best-engine-ai-helper/` | write | Shell exports for downstream projects |
| `config.json` | `~/.best-engine-ai-helper/` | write | JSON version of env.sh |
| `llm.brief.yaml` | consumer repo root | read | Committed, hardware-independent usage brief |
| `llm.engine.yaml` | consumer repo root | write | Gitignored, machine-specific engine descriptor (`resolve` / `ensure`) |
