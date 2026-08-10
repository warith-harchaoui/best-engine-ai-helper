# EXEMPLES.md

Une recette exécutable par commande CLI publique. Tous les exemples supposent
que `best-engine-ai-helper` est installé et qu'Ollama tourne en local sur le
port 11434 (nécessaire seulement pour les commandes `pull`, `validate` et
`env`).

---

## detect

Affiche le matériel détecté au format JSON.

```sh
best-engine-ai-helper detect
```

Sortie attendue sur une machine Apple M2 Max 96 Go :

```json
{
  "platform": "darwin",
  "chip_vendor": "apple",
  "memory": {
    "unified_gb": 96.0,
    "vram_gb": null,
    "ram_gb": 96.0
  }
}
```

Le champ `unified_gb` vaut `null` sur les machines non Apple ; `vram_gb` est
renseigné sur les machines Linux/Windows dotées d'un GPU discret NVIDIA ou
AMD.

---

## recommend

Affiche les modèles candidats classés pour le matériel courant, sans rien
télécharger.

```sh
best-engine-ai-helper recommend
```

Sur une machine M2 Max 96 Go, la sortie ressemble à ceci :

```
=== VLM candidates ===
id            ram_gb  score  fits  notes
------------  ------  -----  ----  ----------------------------------------
gemma3:12b    9.2     78     yes   Google Gemma 3 12B multimodal. Reliable
qwen3-vl:72b  52      91     yes   Highest raw vision benchmarks, but Qwen3
qwen3-vl:32b  24      87     yes   Large VLM; needs 32 GB VRAM. Qwen3-VL: u
...
```

Remarquez l'ordre : `gemma3:12b` (score 78) passe devant `qwen3-vl:72b`
(score 91) parce que la famille Qwen3-VL ne respecte pas la sortie structurée
d'Ollama ; elle n'est donc jamais choisie pour les tâches à schéma imposé de
la suite, quel que soit son score brut. La colonne `fits` indique si la RAM
de pointe d'un modèle tient dans le budget : sur cette machine,
`qwen3:72b-q8_0` (78 Go) affiche `NO` face au budget de 61,2 Go, alors que
tout modèle plus léger affiche `yes`.

Pour ne voir que les candidats VLM :

```sh
best-engine-ai-helper recommend --kind vlm
```

Pour resserrer la marge de sécurité (0,5 au lieu de 0,85 par défaut) :

```sh
best-engine-ai-helper recommend --headroom 0.5
```

---

## report

Recommande le ou les meilleurs moteurs pour une tâche et écrit à la fois un
rapport Markdown et un fichier JSON. La tâche peut être une phrase vague ; un
vocabulaire visuel ajoute un VLM.

```sh
best-engine-ai-helper report \
    --task "retail product descriptions and image-quality checks" \
    --out engine
# wrote engine.md and engine.json
```

Le rapport indique, pour chaque type requis : le modèle choisi avec son
empreinte mémoire et son débit estimé en tokens/s, une alternative plus
légère ou plus rapide quand elle est proche, le tableau complet des
candidats classés et le raisonnement sourcé. Imprimez du JSON plutôt que du
Markdown avec `--format json` (omettez `--out` pour un simple affichage).

Ajoutez `--live` pour tenir compte aussi de la charge ACTUELLE de la machine
(RAM libre, usage CPU/GPU/disque, moteurs déjà lancés), pas seulement de sa
capacité théorique :

```sh
best-engine-ai-helper report --task "write python code" --live
# ...
# ## Server load (live, at recommendation time)
#
# - Available RAM: 50.3 GB
# - CPU: 43%, GPU: 3%
# - Disk free: 41.5 GB (96% used)
# - Already-running engines: 0
# ...
```

Désactivé par défaut : cela ajoute une courte sonde en direct (environ
0,1 à 0,5 s) et rend le résultat dépendant de cet instant précis, plutôt
qu'une fonction déterministe du seul matériel.

---

## resolve

Transforme le **brief** d'un projet (ce dont le dépôt a besoin d'un
LLM/VLM), committé dans le dépôt, en un **fichier moteur** gitignoré et
propre à la machine (le backend et le modèle à utiliser ici). Contrairement
à `report`, qui affiche une recommandation, `resolve` écrit le descripteur
que lisent `ensure` et `llm.chat` au moment de l'appel.

Committez un `llm.brief.yaml` indépendant du matériel dans le dépôt :

```yaml
mode: local             # local (par défaut) ou cloud
kind: both              # llm | vlm | both
headroom: 0.5           # fraction maximale de la mémoire accélératrice utilisable (plafonnée à 0.5)
min_tps: 15             # plancher de débit confortable (tokens/s)
structured_output: true # la tâche exige une sortie contrainte par schéma
task: >-
  Name PCA axis poles as schema-constrained JSON, write a short analysis in
  the table's own language, and sanity-check the rendered chart image.
```

`mode: local` est la valeur par défaut. `mode: cloud` résout un fournisseur
payant plus un repli local à partir du même brief (payant vers local en cas
d'échec) :

```yaml
mode: cloud
provider: mistral        # openai | mistral | openrouter | together | azure |
                         # anthropic | gemini (anthropic/gemini ont leur
                         # propre format, les autres parlent OpenAI-compatible)
model: mistral-large-latest
api_key_env: MISTRAL_API_KEY   # nom de la variable d'environnement qui
                                # porte la clé — jamais la clé elle-même
structured_output: true
task: extraire les lignes structurées d'un texte OCR de facture
```

```sh
export MISTRAL_API_KEY=...     # votre clé, dans le shell, jamais committée
best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
```

Le `fallback` du moteur résultant est résolu à partir du MÊME brief, si bien
que `llm.chat(engine=...)` retombe sur le modèle local toujours disponible en
cas d'échec de l'appel payant. Voir les paramètres `pseudonymize=`
(anonymise les données personnelles avant qu'elles n'atteignent le cloud, via
le moteur local de repli) et `safety=` (filtrage NSFW/politique de contenu,
activé par défaut pour chaque moteur, local ou cloud) de `llm.chat` pour le
reste du filet de sécurité de l'appel cloud. Le retry/cache/pseudonymisation
nécessitent l'extra `[cloud]` (`pip install 'best-engine-ai-helper[cloud]'`) ;
les vrais classifieurs NSFW de `safety=` nécessitent `[filtered]` —
les deux se dégradent proprement (retry simple, pas de cache, heuristique par
mots-clés) plutôt que d'échouer en leur absence.

Résolvez-le, par machine (le backend est choisi selon le matériel : **vLLM
sur un GPU discret, Ollama sinon**) :

```sh
best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
```

Sur une machine Apple M2 Max 96 Go, cela affiche :

```
Wrote llm.engine.yaml
  backend: ollama  (llm=gemma3:12b, vlm=gemma3:12b)
  NOTE: hardware-specific — add 'llm.engine.yaml' to .gitignore, do not commit.
  bring it up:  ollama pull gemma3:12b
```

Le choix est délibérément prudent : la marge est plafonnée à 0,5. Parmi les
modèles à quelques points de score du meilleur, c'est le plus léger et le
plus rapide qui est retenu, pas le plus grand qui tient tout juste dans le
budget. Le fichier `llm.engine.yaml` obtenu est propre à la machine :
ajoutez-le au `.gitignore` :

```yaml
# GÉNÉRÉ par best-engine-ai-helper : ne pas committer.
# Propre à ce matériel : le backend et les modèles choisis pour CETTE machine.
# Régénérer avec :  best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml

mode: local
resolved_for: {chip: Apple M2 Max, accelerator: apple, memory_gb: 96.0}
backend: ollama
base_url: http://localhost:11434
headroom: 0.5
min_tps: 15.0
llm: {model: gemma3:12b, ram_gb: 9.2, est_tokens_per_s: 28.3, structured_output: true}
vlm: {model: gemma3:12b, ram_gb: 9.2, est_tokens_per_s: 28.3, structured_output: true}
serve: [ollama pull gemma3:12b]
```

Forcez un backend avec `--backend ollama|vllm` (par défaut `auto`), ou
visez un serveur distant avec `--endpoint URL`.

Consommez-le depuis Python : il n'existe aucune constante `DEFAULT_MODEL`,
le modèle est toujours lu depuis le fichier moteur résolu :

```python
from best_engine_ai_helper import ensure, llm

engine = ensure(".")            # charge llm.engine.yaml ou le résout depuis
                                # llm.brief.yaml au premier appel
summary = llm.chat(prompt, engine=engine, kind="llm")
critique = llm.chat(prompt, engine=engine, kind="vlm",
                    images=[png], json_schema=SCHEMA)
```

`chat` lit le backend et le modèle depuis le moteur, puis délègue à Ollama
(`/api/generate`) ou à vLLM (`/v1/chat/completions` au format OpenAI) de
façon transparente ; avec un `json_schema`, il renvoie un dictionnaire déjà
parsé. Voir la section « Downstream integration → Pattern B » du README
([README.md#pattern-b-a-per-project-engine-resolved-from-a-tuned-brief](README.md#pattern-b-a-per-project-engine-resolved-from-a-tuned-brief))
pour le déroulé complet et la politique en cas de fichier manquant.

---

## usages

Parcourt et résout le **catalogue d'usages** sev7n : des profils de tâches
nommés, regroupés en familles. Un profil n'énonce que ses *besoins* ;
best-engine choisit le modèle.

```sh
best-engine-ai-helper usages list
```

Liste les familles (`F1` génération contrainte, `F2` génération de prose,
`F3` embeddings) et chaque profil (`text2sql`, `rag-answer`, `embeddings`,
`text2sql-figures`, `report-bluf`, `classification`, `pii-rgpd`, `persona`)
avec sa famille et son statut : aucun nom de modèle, seulement des besoins.

```sh
best-engine-ai-helper usages show text2sql
```

Affiche les besoins d'un profil : le texte de la tâche (rattaché à un axe
de benchmark), le besoin ou non de sortie structurée, son plancher de débit,
sa marge mémoire, sa barre de qualité indicative et son indice de longueur
de contexte.

```sh
# Résout un profil vers le modèle que best-engine choisit pour CETTE machine
best-engine-ai-helper usages resolve text2sql

# Résout une famille entière vers un seul modèle partagé, écrit dans un fichier gitignoré
best-engine-ai-helper usages resolve --family F1 --out llm.engine.F1.yaml
```

Le modèle choisi ne vit que dans le `llm.engine*.yaml` généré (gitignoré,
propre à la machine) : la même règle que pour `resolve`. Depuis Python :

```python
from best_engine_ai_helper import resolve_usage, resolve_family, list_usages

for u in list_usages():
    print(u["name"], u["family"], u["status"])

engine = resolve_usage("text2sql")   # best-engine choisit le modèle ici
family = resolve_family("F1")        # un seul modèle pour tout le groupe F1
```

---

## catalog show

Affiche le catalogue de modèles complet, fusion du jeu de départ embarqué et
des mises à jour du cache local.

```sh
best-engine-ai-helper catalog show
```

Chaque ligne montre le tag Ollama, le type, le nombre de paramètres, la
quantification, la taille sur disque, la RAM de pointe estimée et les
scores de benchmark.

---

## hardware show

Affiche le tableau matériel complet, fusion du jeu de départ et du cache
local.

```sh
best-engine-ai-helper hardware show
```

Chaque ligne montre le nom de la puce, le fabricant, la mémoire totale, la
mémoire utilisable (après réservation par l'OS) et la source des données.

---

## Utilisation en bibliothèque Python

Toutes les fonctions publiques sont importables sans passer par Click :

```python
from best_engine_ai_helper.detect import available_memory, chip_vendor
from best_engine_ai_helper.catalog import load_catalog
from best_engine_ai_helper.score import select

hw = available_memory()
catalog = load_catalog()

best_vlm = select(hw, catalog, kind="vlm")
print(best_vlm["id"])        # p. ex. 'gemma3:12b' sur une machine 96 Go
print(best_vlm["ram_gb"])    # p. ex. 9.2

best_llm = select(hw, catalog, kind="llm")
print(best_llm["id"])        # p. ex. 'qwen3:72b-q4_k_m' sur une machine 96 Go
```

`select` s'accorde avec la sortie de `recommend` et de `report` sur le
vainqueur : les deux placent d'abord les modèles capables de sortie
structurée, puis classent par score de benchmark dans la limite du budget
mémoire.

L'algorithme de recommandation complet (mémoire, calcul, tâche) tient en un
seul appel :

```python
from best_engine_ai_helper import recommend_engines, to_markdown
from best_engine_ai_helper.detect import available_memory, compute_profile
from best_engine_ai_helper.catalog import load_catalog

report = recommend_engines(
    available_memory(),
    load_catalog(),
    task="product descriptions and image-quality checks",
    compute=compute_profile(),
)
print(report["recommendations"]["vlm"]["chosen"]["id"])   # meilleur VLM
print(to_markdown(report))                                # rapport lisible par un humain
```

---

## gui

Lance l'interface graphique dans le navigateur (état du matériel + tâche →
meilleur moteur) :

```sh
best-engine-ai-helper gui
# Serving GUI at http://127.0.0.1:8000/gui
```

Ouvrez `http://127.0.0.1:8000/gui` : le panneau matériel se charge au
chargement de la page ; taper une tâche puis cliquer sur « Recommander »
appelle le même `recommend()` que `report`. Les deux points d'accès JSON
sur lesquels elle repose s'utilisent aussi directement :

```sh
curl -s http://127.0.0.1:8000/api/system | python3 -m json.tool

curl -s -X POST http://127.0.0.1:8000/api/recommend \
     -H 'Content-Type: application/json' \
     -d '{"task": "product descriptions and image-quality checks"}' \
  | python3 -m json.tool
```

Voir [GUI.md](GUI.md) pour les captures d'écran et le compte rendu complet.

---

## activity

Résume le registre local d'activité et de coût : qui a appelé quoi, à
quelle fréquence, pour quel coût. Alimenté par toute commande (ou tout
projet en aval) qui appelle `llm.chat()` ; rien à afficher avant ça.

```sh
best-engine-ai-helper activity
# No calls recorded yet.

best-engine-ai-helper pull   # appelle le modèle via les portes de validation Ralph

best-engine-ai-helper activity
# Total calls: 4   Total cost: $0.0000   Error rate: 0.0%
#
# By user:
# user              calls  cost_usd
# ----              -----  --------
# warithharchaoui   4      0.0
#
# By model:
# model      calls  cost_usd
# -----      -----  --------
# qwen3:8b   4      0.0

best-engine-ai-helper activity --format json
```

Purement local (`~/.best-engine-ai-helper/usage.db`), aucun appel réseau.
Désactivez l'enregistrement entièrement avec `BEST_ENGINE_NO_LEDGER=1`, ou
attribuez les appels à une personne précise sur une machine partagée avec
`BEST_ENGINE_USER=alice`.

---

## pull, validate, env

```sh
best-engine-ai-helper pull            # récupère le meilleur modèle ; lance les portes Ralph
best-engine-ai-helper validate        # relance les portes Ralph sur le modèle actuel
best-engine-ai-helper env             # affiche le bloc env pour ~/.zshrc
```

Rafraîchissez les caches (les deux se fondent dans
`~/.best-engine-ai-helper/`, sans toucher au jeu de départ embarqué) :

```sh
best-engine-ai-helper catalog update            # récupère les modèles ouverts depuis ApXML
best-engine-ai-helper catalog update --limit 20 # rafraîchissement partiel rapide / test de fumée
best-engine-ai-helper hardware update           # enregistre la puce et la mémoire de cette machine
```
