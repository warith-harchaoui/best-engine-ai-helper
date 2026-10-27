# Exemples

🇫🇷 Français · [🇬🇧 EXAMPLES.md](EXAMPLES.md)

Dix scénarios, chacun un besoin avec lequel quelqu'un arrive vraiment, puis une
section qui recense toutes les commandes. Chaque extrait ci-dessous a été
confronté au code, puis les sorties collées ici ont été produites en
l'exécutant — voir [Mise en place](#mise-en-place) pour la machine d'où elles
viennent ainsi que pour les rares commandes qui n'ont pas pu être lancées.

L'idée à retenir d'un bout à l'autre : **vous ne nommez jamais un modèle.** Vous
décrivez le travail ; ce paquet nomme le modèle, différemment sur chaque
machine.

## Table des matières

- [Mise en place](#mise-en-place)
- [1. Ce que cette machine peut exécuter](#1-ce-que-cette-machine-peut-exécuter)
- [2. Le meilleur moteur pour une tâche, en rapport](#2-le-meilleur-moteur-pour-une-tâche-en-rapport)
- [3. Un brief par dépôt, un moteur par machine](#3-un-brief-par-dépôt-un-moteur-par-machine)
- [4. Un modèle payant, seulement si vous donnez une clé](#4-un-modèle-payant-seulement-si-vous-donnez-une-clé)
- [5. Des profils d'usage plutôt que des noms de modèles](#5-des-profils-dusage-plutôt-que-des-noms-de-modèles)
- [6. Planifier la capacité disponible](#6-planifier-la-capacité-disponible)
- [7. Trop gros pour tenir, exécutable quand même](#7-trop-gros-pour-tenir-exécutable-quand-même)
- [8. Qui appelle quoi, à quel coût](#8-qui-appelle-quoi-à-quel-coût)
- [9. La GUI, l'API HTTP puis les outils MCP](#9-la-gui-lapi-http-puis-les-outils-mcp)
- [10. L'appeler depuis votre propre paquet](#10-lappeler-depuis-votre-propre-paquet)
- [Ligne de commande](#ligne-de-commande)
- [Dépannage](#dépannage)

## Mise en place

```sh
pip install best-engine-ai-helper
```

Comptez environ 2 Go puis quelques minutes : ce paquet est en Python pur et
minuscule, mais le moteur de lecture des couches en flux amène torch avec lui.
Une seule ligne de commande est installée, plus un serveur :

```sh
best-engine-ai-helper --version     # best-engine-ai-helper, version 1.9.0
best-engine-ai-helper-mcp           # API HTTP + MCP, http://127.0.0.1:8000
```

Chaque extrait Python ci-dessous suppose ces imports, rien de plus :

```python
import best_engine_ai_helper as beah  # la surface publique à plat
from best_engine_ai_helper import llm  # le seul appel qui exécute un modèle
```

[Ollama](https://ollama.com) ne sert qu'à **exécuter** un modèle : donc pour
`pull`, `validate`, `env` puis pour l'extrait `llm.chat` de la
[section 10](#10-lappeler-depuis-votre-propre-paquet). Tout ce qui se contente
de *décider* (`detect`, `recommend`, `report`, `resolve`, `usages`, `storage`,
`providers`, `catalog show`, `hardware show`, toutes les sous-commandes de
dimensionnement d'`airllm`, la GUI, l'API HTTP) fonctionne sans démon ni réseau.

**D'où viennent les sorties.** Chaque tableau puis chaque panneau ci-dessous a
été produit sur un Apple M2 Max de 96 Go de mémoire unifiée, sous macOS, avec un
`~/.best-engine-ai-helper/` vierge afin que ce soit le catalogue **embarqué** qui
réponde plutôt qu'un cache rafraîchi. Deux propriétés de cette machine
déterminent plusieurs chiffres : sa bande passante mémoire vaut 400 Go/s, ce qui
fixe chaque valeur de `tok/s`, puis son disque était rempli à **98 %**, ce qui
explique pourquoi tant de lignes de la
[section 7](#7-trop-gros-pour-tenir-exécutable-quand-même) sont refusées sur le
disque plutôt que sur la mémoire. Un `~` signale une estimation déduite de la
bande passante ; un `*` dans une vraie sortie signale un chiffre mesuré sur la
machine. Les chiffres de disque libre diffèrent légèrement d'un panneau à
l'autre parce que chaque panneau est une exécution distincte puis que le disque
se remplissait entre-temps : c'est un relevé en direct, pas une incohérence.

Cinq commandes ne sont **pas** exécutées ici, leur effet est décrit plutôt que
collé : `pull` puis `validate` (elles téléchargent des poids puis font tourner
deux gardes de génération), `catalog update` puis `hardware update` (la première
atteint le réseau), `airllm prepare` (elle télécharge un checkpoint puis le
découpe) puis `imagine generate` (elle télécharge un pipeline diffusers). Rien
dans ce fichier n'est une sortie inventée.

## 1. Ce que cette machine peut exécuter

Commencez ici. `detect` dit ce qu'est le matériel ; `recommend` dit ce que ce
matériel devrait exécuter, sans rien télécharger.

```sh
best-engine-ai-helper detect
```

```json
{
  "platform": "darwin",
  "chip_vendor": "apple",
  "memory": {
    "unified_gb": 96.0,
    "vram_gb": null,
    "ram_gb": 96.0
  },
  "hardware": {
    "platform": "darwin",
    "cpu": {
      "physical_cores": 12,
      "logical_cores": 12,
      "model": "Apple M2 Max",
      "percent": 66.9
    },
    "ram_gb": 96.0,
    "available_ram_gb": 52.0,
    "disk": {
      "free_gb": 22.1,
      "used_gb": 972.6,
      "total_gb": 994.7,
      "percent_used": 97.8
    },
    "gpu_vendor": "apple",
    "gpus": [],
    "gpu_utilization_percent": 58.0,
    "apple_chip": "Apple M2 Max",
    "apple_unified_gb": 96.0
  }
}
```

Le bloc `memory` de premier niveau est la partie stable : `unified_gb` n'est
renseigné que sur Apple Silicon, `vram_gb` que sur une machine dotée d'un GPU
discret NVIDIA ou AMD, puis `ram_gb` toujours. Le bloc `hardware` en dessous est
un relevé en direct délégué à `os-helper` : `percent`, `available_ram_gb` puis
`gpu_utilization_percent` diffèrent donc à chaque exécution — ce sont les champs
que consomme `report --live`.

```sh
best-engine-ai-helper recommend --kind llm
```

```
=== LLM candidates (ollama) ===
id                 ram_gb  score  fits  tok/s  comfy  notes
-----------------  ------  -----  ----  -----  -----  ----------------------------------------
qwen3:72b-q8_0     78      89     NO    3      NO     72B at Q8; needs 96 GB unified. Reliable
qwen3:72b-q4_k_m   48      87     NO    5      NO     Top text-only; needs 64 GB unified or VR
qwen3:32b-q8_0     36      85     yes   7      NO     32B at full Q8 precision. Reliable struc
qwen3:32b-q4_k_m   22      83     yes   12     NO     Large text model; fits 24 GB VRAM with h
qwen3:14b          10.5    78     yes   25     yes    Good mid-size text model. Reliable struc
gemma3:12b         9.2     77     yes   28     yes    Google Gemma 3 12B multimodal. Reliable
qwen2.5-coder:32b  22      75     yes   12     NO     Qwen2.5-Coder 32B: top open code/SQL mod
qwen3:8b           5.6     74     yes   46     yes    Solid text-only 8B. Reliable structured
qwen2.5-coder:14b  9.9     72     yes   26     yes    Qwen2.5-Coder 14B: stronger code/SQL at
qwen2.5-coder:7b   5.2     66     yes   50     yes    Qwen2.5-Coder 7B: SQL/code specialist. R
qwen2.5:3b         2.2     62     yes   118    yes    Text-only; very small footprint. Reliabl
qwen3-vl:72b       52      88     NO    5      NO     Highest raw vision benchmarks, but Qwen3
qwen3-vl:32b       24      84     yes   11     NO     Large VLM; needs 32 GB VRAM. Qwen3-VL: u
qwen3-vl:14b       11.2    79     yes   23     yes    Strong mid-size VLM. Qwen3-VL: unreliabl
qwen3-vl:8b        6.8     73     yes   38     yes    Qwen3-VL 8B: strong raw vision/OCR but r
qwen3-vl:4b        3.5     66     yes   74     yes    Small VLM; fits on 4 GB VRAM machines. Q
```

Trois colonnes décident, puis aucune n'est le score seul.

`fits` compare la RAM **de pointe en inférence** d'un modèle au budget, qui vaut
**36,0 Go** sur cette machine : 96 Go de mémoire unifiée, dont 72,0 Go
utilisables une fois macOS servi, divisés encore par deux par la marge de
sécurité de 0,5. Voilà pourquoi `qwen3:32b-q8_0` à exactement 36 Go affiche
encore `yes` là où `qwen3:72b-q4_k_m` à 48 Go affiche `NO` sur une machine de
96 Go. Vérifiez le chiffre au lieu de croire l'arithmétique :

```python
hw = beah.available_memory()
print(beah.usable_pool_gb(hw))  # 72.0
print(beah.effective_budget(hw))  # 36.0
print(beah.MAX_HEADROOM)  # 0.5
```

`comfy` est le second refus. `qwen3:32b-q8_0` tient en mémoire puis n'est
pourtant pas choisi : à 7 tok/s estimés il passe sous le plancher de confort de
15 tok/s. Un modèle qui tient puis rampe n'est pas une recommandation.

Resserrez la marge puis `fits` suit. `--headroom` est plafonné à 0,5 : la seule
direction disponible est donc plus stricte.

```sh
best-engine-ai-helper recommend --kind llm --headroom 0.3
```

```
qwen3:32b-q8_0     36      85     NO    7      NO     32B at full Q8 precision. Reliable struc
qwen3:32b-q4_k_m   22      83     NO    12     NO     Large text model; fits 24 GB VRAM with h
qwen3:14b          10.5    78     yes   25     yes    Good mid-size text model. Reliable struc
```

`--kind vlm` restreint aux modèles vision-langage puis les classe sur l'axe
vision au lieu de l'axe général, ce qui réordonne le tableau. `gemma3:12b` passe
devant avec un score de 78 alors que `qwen3-vl:32b` obtient 87, parce que la
famille Qwen3-VL ne sait pas honorer la sortie contrainte par schéma d'Ollama
puis que cette suite fait passer chaque tâche par un schéma :

```sh
best-engine-ai-helper recommend --kind vlm
```

```
=== VLM candidates (ollama) ===
id            ram_gb  score  fits  tok/s  comfy  notes
------------  ------  -----  ----  -----  -----  ----------------------------------------
gemma3:12b    9.2     78     yes   28     yes    Google Gemma 3 12B multimodal. Reliable
qwen3-vl:72b  52      91     NO    5      NO     Highest raw vision benchmarks, but Qwen3
qwen3-vl:32b  24      87     yes   11     NO     Large VLM; needs 32 GB VRAM. Qwen3-VL: u
qwen3-vl:14b  11.2    83     yes   23     yes    Strong mid-size VLM. Qwen3-VL: unreliabl
qwen3-vl:8b   6.8     80     yes   38     yes    Qwen3-VL 8B: strong raw vision/OCR but r
qwen3-vl:4b   3.5     72     yes   74     yes    Small VLM; fits on 4 GB VRAM machines. Q
```

## 2. Le meilleur moteur pour une tâche, en rapport

`recommend` classe le catalogue. `report` répond à une *question* : étant donné
cette phrase qui décrit le travail, quels types de modèle sont nécessaires puis
lequel doit servir chacun. La tâche peut être vague — un vocabulaire visuel y
ajoute un VLM.

```sh
best-engine-ai-helper report \
    --task "retail product descriptions and image-quality checks" \
    --out engine
```

```
wrote engine.md and engine.json
# Best local engine — recommendation

**Task:** retail product descriptions and image-quality checks
**Language:** en
**Matched keywords:** image
**Needs:** LLM, VLM

## Hardware

- Chip / accelerator: Apple M2 Max (gpu-metal)
- Memory pool: 96.0 GB
- Memory bandwidth: 400 GB/s (sets the decode-speed ceiling)
- Usable model budget: **36.0 GB** (headroom 0.5)
- Comfort throughput floor: **15 tok/s** (a model below this fits memory but decodes too slowly to recommend)

## Best LLM (axis: generalist)

**→ `gemma3:12b`** — 9.2 GB, score 77, ~28 tok/s

Lighter alternative: `qwen3:8b` — 5.6 GB, score 74, ~46 tok/s.
```

Remarquez ce que les mots ont fait. « Product descriptions » n'a touché aucun axe
spécialisé, le LLM est donc classé sur le benchmark **generalist**, tandis
qu'« image » a fait naître un besoin de VLM, classé lui sur l'axe **vision**.
Demandez du code puis l'axe change encore :

```sh
best-engine-ai-helper report --task "write python code" --live
```

```
## Server load (live, at recommendation time)

- Available RAM: 54.3 GB
- CPU: 53%, GPU: 10%
- Disk free: 20.7 GB (98% used)
- Already-running engines: 1

## Best LLM (axis: code)
```

`--live` est désactivé par défaut puis mérite d'être compris avant d'être
activé. Il ajoute une sonde courte, de l'ordre de 0,1 à 0,5 s, puis fait du
résultat une fonction de *cet instant* plutôt que du seul matériel : la même
commande lancée deux fois peut se contredire, ce qui est à la fois le
comportement correct puis un comportement surprenant. La ligne
`Already-running engines: 1` ci-dessus est la sonde qui remarque un serveur de
modèle déjà en train d'occuper de la mémoire.

`--out engine` écrit `engine.md` puis `engine.json` côte à côte ; omettez-le pour
un simple affichage, puis `--format json` remplace le Markdown par son jumeau
lisible par une machine.

La même commande prévisualise aussi le meilleur modèle **payant** pour la tâche.
C'est activé par défaut, sans clé API ni appel réseau, parce qu'elle classe le
`pricing.yaml` embarqué au lieu d'appeler qui que ce soit :

```sh
best-engine-ai-helper report --task "extract line items from an invoice"
```

```
## Best cloud LLM (axis: generalist)

**→ `gemini-1.5-pro`** (gemini) — score 86, ~$3.12/1M tokens (blended)

## Best cloud VLM (axis: ocr)

**→ `gpt-4o`** (openai) — score 69, ~$6.25/1M tokens (blended)
```

Le mot « invoice » a rattaché l'emplacement vision à l'axe **ocr**, ce qui
explique la victoire de `gpt-4o` là où `gemini-1.5-pro` prend l'emplacement
texte à moitié prix. Sautez toute la section avec `--no-cloud` ; orientez-la avec
`--quality-vs-cost 0..1` (1.0 = meilleur benchmark sans égard au prix, 0.0 = le
moins cher sans égard à la qualité, défaut 0.7) puis
`--cloud-provider openai|mistral|...` pour la limiter à un seul fournisseur.

## 3. Un brief par dépôt, un moteur par machine

`report` affiche un conseil. `resolve` écrit le descripteur que votre code lit au
moment de l'appel, puis c'est le motif à adopter : un **brief** committé dans le
dépôt qui dit ce dont le travail a besoin, résolu par machine en un **fichier
moteur** gitignoré qui nomme le modèle choisi ici.

Committez ceci, indépendant du matériel, sous `llm.brief.yaml` :

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

Résolvez-le, une fois par machine. Le backend est choisi pour le matériel :
**vLLM sur un GPU discret, Ollama sinon**.

```sh
best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
```

```
WARNING | llm model gemma3:12b is not on this Ollama daemon yet: run `ollama pull gemma3:12b` before the first call.
WARNING | vlm model gemma3:12b is not on this Ollama daemon yet: run `ollama pull gemma3:12b` before the first call.
Wrote llm.engine.yaml
  backend: ollama  (llm=gemma3:12b, vlm=gemma3:12b)
  NOTE: hardware-specific — add 'llm.engine.yaml' to .gitignore, do not commit.
  bring it up:  ollama pull gemma3:12b
```

Ces deux avertissements sont la moitié utile de la sortie : le choix se fait
contre le catalogue, pas contre ce qui se trouve déjà téléchargé, si bien qu'il
vous dit quoi récupérer au lieu de se rabattre en silence sur ce qui est
présent.

Le fichier qu'il a écrit, qui a sa place dans le `.gitignore` :

```yaml
# GENERATED by best-engine-ai-helper — do NOT commit.
# Hardware-specific: the backend and models chosen for THIS machine.
# Regenerate with:  best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml

generated_by: best-engine-ai-helper — machine-specific, do not commit
mode: local
resolved_for:
  chip: Apple M2 Max
  accelerator: gpu-metal
  memory_gb: 96.0
backend: ollama
base_url: http://localhost:11434
headroom: 0.5
min_tps: 15.0
llm:
  model: gemma3:12b
  ram_gb: 9.2
  est_tokens_per_s: 28.3
  tps_basis: estimated
  structured_output: true
  score: 77.0
  fits: true
  comfortable: true
  available: false
  pull: ollama pull gemma3:12b
vlm:
  model: gemma3:12b
  ram_gb: 9.2
  est_tokens_per_s: 28.3
  tps_basis: estimated
  structured_output: true
  score: 78.0
  fits: true
  comfortable: true
  available: false
  pull: ollama pull gemma3:12b
serve:
- ollama pull gemma3:12b
```

Le choix est délibérément prudent : marge plafonnée à 0,5, puis parmi les modèles
à quelques points de benchmark du meilleur c'est le plus léger et le plus rapide
qui est retenu, pas le plus grand qui tient tout juste. `tps_basis: estimated`
dit que le débit vient de la bande passante mémoire plutôt que d'une mesure ;
`available: false` dit que le démon n'a pas encore le modèle.

Forcez un backend avec `--backend ollama|vllm` (par défaut `auto`) ; ou bien visez
avec le même moteur résolu un serveur que vous opérez, via `--endpoint URL`. Cette
seconde option est celle qu'on oublie : le mode local ne veut pas dire *cette*
machine-ci, puis une machine vLLM à vous ne coûte rien au jeton non plus.

Ensuite, vérifiez que la machine est d'accord avec le fichier :

```sh
best-engine-ai-helper doctor
```

```
engine file : llm.engine.yaml
backend     : ollama
daemon      : reachable
serves      : qwen2.5:3b, qwen3-vl:4b, qwen3-vl:4b-ctx8k, qwen3-vl:8b, qwen3:8b

  - llm: the engine file names 'gemma3:12b', which this daemon does not serve. Run `ollama pull gemma3:12b`, or re-resolve.
  - vlm: the engine file names 'gemma3:12b', which this daemon does not serve. Run `ollama pull gemma3:12b`, or re-resolve.
```

`doctor` sort avec un code non nul quand le moteur résolu puis le démon en
fonctionnement se contredisent, ce qui en fait la bonne commande à placer dans un
contrôle de déploiement. Consommer le fichier depuis Python, c'est la
[section 10](#10-lappeler-depuis-votre-propre-paquet).

## 4. Un modèle payant, seulement si vous donnez une clé

C'est le seul membre de la suite AI Helpers qui sache joindre un service payant
de tiers, puis il ne le fait jamais par accident. Un appel payant exige **deux**
choses : un brief qui dit `mode: cloud`, puis un `api_key_env` nommant une
variable d'environnement réellement renseignée. `api_key_env` porte le **nom** de
la variable, jamais la clé, puis la clé n'est jamais écrite dans le fichier
moteur.

Demandez d'abord quels fournisseurs sont ne serait-ce qu'utilisables :

```sh
best-engine-ai-helper providers
```

```
provider   key_env            usable  models  why not
---------  -----------------  ------  ------  ------------------------------------------------------------
anthropic  ANTHROPIC_API_KEY  NO      2       no API key found. Set ANTHROPIC_API_KEY in settings.yaml, a
gemini     GEMINI_API_KEY     NO      2       no API key found. Set GEMINI_API_KEY in settings.yaml, a .en
mistral    MISTRAL_API_KEY    NO      4       no API key found. Set MISTRAL_API_KEY in settings.yaml, a .e
openai     OPENAI_API_KEY     NO      2       no API key found. Set OPENAI_API_KEY in settings.yaml, a .en

0 of 4 provider(s) usable.
Set a key in settings.yaml, a .env file, the environment, or the keychain.
```

C'est la vraie sortie sur une machine qui ne détient aucune clé, puis c'est le
comportement sur lequel compter : un fournisseur dont la clé est introuvable
n'est pas candidat du tout. Une recommandation sur laquelle on ne peut pas agir
n'est pas une recommandation.

Fixez un fournisseur puis un modèle explicitement :

```yaml
mode: cloud
provider: mistral        # openai | mistral | openrouter | together | azure |
                         # anthropic | gemini (anthropic/gemini ont leur propre
                         # format ; les autres parlent OpenAI-compatible)
model: mistral-large-latest
api_key_env: MISTRAL_API_KEY   # le NOM de la variable qui porte la clé,
                               # jamais la valeur, jamais persistée
structured_output: true
task: extract structured line items from an invoice PDF's OCR text
```

```sh
export MISTRAL_API_KEY=...     # votre clé, dans le shell, jamais committée
best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
```

Ou laissez-le choisir. Omettez `model` — puis `provider` aussi, pour chercher
chez tous les fournisseurs — puis le choix vient du même `pricing.yaml` embarqué
que prévisualisait la
[section 2](#2-le-meilleur-moteur-pour-une-tâche-en-rapport). C'est le pendant
cloud du choix automatique local, sauf que la ressource budgétée est le **prix**
plutôt que la mémoire, puisque tout modèle payant tourne sur n'importe quelle
machine :

```yaml
mode: cloud
kind: both
quality_vs_cost: 0.7   # optionnel, 0..1, défaut 0.7 : 1.0 = meilleur score sans
                       # égard au prix, 0.0 = le moins cher sans égard à la
                       # qualité ; entre les deux, la qualité d'abord avec le
                       # prix en départage
task: extract structured line items from an invoice PDF's OCR text
```

Fixez `provider` seul, sans `model`, pour choisir automatiquement au sein d'un
seul fournisseur : le cas où vous détenez déjà exactement une clé. La capacité de
sortie structurée est vérifiée en premier ici, exactement comme en local : un
modèle incapable d'honorer un schéma JSON ne gagne jamais le choix automatique
face à un modèle qui le peut, aussi attractif soit son prix.

Trois autres clés existent pour le cas épinglé, puis le brief est le seul endroit
où elles se règlent. `vlm_model` épingle l'emplacement vision séparément (avec
`kind: both` et seulement `model` donné, un seul modèle sert les deux).
`base_url` remplace l'endpoint du fournisseur, pour un proxy ou un déploiement
régional. `api_key_env` remplace la variable dans laquelle la clé est lue, qui
vaut par défaut le nom conventionnel du fournisseur. Aucune ne porte jamais la
clé elle-même.

Chaque moteur cloud porte aussi un **repli local**, résolu depuis le même brief,
si bien qu'un appel payant en échec se dégrade vers le modèle local toujours
disponible. Payant → local est la seule direction automatique ; un moteur local
ne monte jamais en silence vers un appel payant. Quatre choses de plus se passent
alors au point d'appel `llm.chat()` :

| Sujet | Défaut | Réglage |
|---|---|---|
| **Clé API** | le nom porté par `api_key_env` est cherché dans `settings.yaml`, puis un éventuel `.env`, puis l'environnement du processus, puis le trousseau du système | l'étape trousseau exige `pip install 'best-engine-ai-helper[cloud]'` |
| **Scan de sécurité** | activé, pour le local **comme** le cloud : prompts et images en sortie, réponses en entrée | `llm.chat(..., safety=False)` ; les vrais classifieurs NSFW exigent `[filtered]` |
| **Pseudonymisation** | désactivée ; activée, elle nettoie les données personnelles avec le modèle de repli **local** avant que le prompt ne quitte la machine, puis les restaure | `llm.chat(..., pseudonymize=True)`, exige `[cloud]` |
| **Retry + cache** | désactivés ; le retry rejoue un échec transport transitoire avant de basculer, le cache fait qu'une répétition n'est jamais payée deux fois | `llm.chat(..., retries=3, cache=True)`, le cache exige `[cloud]` |
| **Suivi du coût** | activé, chaque appel, local ou payant, dans le journal local | [section 8](#8-qui-appelle-quoi-à-quel-coût), désactiver avec `BEST_ENGINE_NO_LEDGER=1` |

Les deux extras se dégradent plutôt que d'échouer en leur absence : un retry
simple au lieu d'un backoff, pas de cache, une heuristique par mots-clés au lieu
d'un classifieur.

## 5. Des profils d'usage plutôt que des noms de modèles

Un brief s'écrit par dépôt. Les huit charges de travail récurrentes de la suite
sont plutôt nommées une fois pour toutes, dans un catalogue d'usages embarqué,
chacune n'énonçant que ses *besoins*. Un profil est un brief nommé, résolu par le
même sélecteur.

```sh
best-engine-ai-helper usages list
```

```
Families (usages that can share one model):
id  name                    members                                               summary
--  ----------------------  ----------------------------------------------------  ------------------------------------------------
F1  constrained-generation  text2sql, text2sql-figures, classification, pii-rgpd  Code + reliable structured output (SQL / JSON):
F2  prose-generation        rag-answer, report-bluf, persona                      Faithful FR/EN prose over long context: one gene
F3  embeddings              embeddings                                            Multilingual multi-granular embeddings: an embed

Profiles:
name              family  status    summary
----------------  ------  --------  ----------------------------------------------------
text2sql          F1      stable    Natural-language question -> read-only SQL (Vanna /
rag-answer        F2      stable    Sourced RAG answer with page-precise citations, FR/E
embeddings        F3      stable    Local multi-granular embeddings for the ann-router i
text2sql-figures  F1      scaffold  Question + table -> structured figure spec that spre
report-bluf       F2      stable    Multi-persona report / BLUF generation, FR/EN, quali
classification    F1      stable    Confidentiality classification C1/C2/C3, fast and de
pii-rgpd          F1      stable    PII / GDPR detection + pseudonymisation surrogates,
persona           F2      stable    Persona / register adaptation of a passage, FR/EN, m
```

Aucun nom de modèle n'apparaît dans cette liste : c'est tout le propos. Les
besoins d'un profil au complet :

```sh
best-engine-ai-helper usages show text2sql
```

```
text2sql  [stable, family F1]
  Natural-language question -> read-only SQL (Vanna / qwencoder).

Needs (selection criteria):
  kind             : llm
  structured_output: True
  min_tps          : 20
  headroom         : 0.5
  min_quality      : 80
  context_length   : 32768
  local_strict     : True
  task             : Translate a natural-language question into a single read-only SQL query against a fixed schema; deterministic, schema-constrained SQL and code reasoning.
```

Résolvez-le puis regardez les besoins faire leur travail :

```sh
best-engine-ai-helper usages resolve text2sql
```

```
WARNING | llm model qwen2.5-coder:14b is not on this Ollama daemon yet: run `ollama pull qwen2.5-coder:14b` before the first call.
text2sql: backend ollama  llm=qwen2.5-coder:14b (9.9 GB, ~26 tok/s)
  NOTE: machine-specific — the chosen model lives only in the generated file; keep it gitignored, never commit.
```

La réponse généraliste sur cette machine était `gemma3:12b`
([section 2](#2-le-meilleur-moteur-pour-une-tâche-en-rapport)). Ici c'est
`qwen2.5-coder:14b`, dont le score général est *plus bas*, parce que le texte de
tâche du profil a la forme d'un besoin de code puis que son plancher
`min_tps: 20` est plus strict que les 15 par défaut. Personne n'a choisi un
modèle de code : les besoins l'ont fait.

Une famille entière se résout vers **un seul** modèle partagé, pour qu'une
machine n'ait pas à en tenir huit :

```sh
best-engine-ai-helper usages resolve --family F1 --out llm.engine.F1.yaml
```

```
F1: backend ollama  llm=qwen2.5-coder:14b (9.9 GB, ~26 tok/s)
  NOTE: machine-specific — the chosen model lives only in the generated file; keep it gitignored, never commit.
  wrote llm.engine.F1.yaml
  bring it up:  ollama pull qwen2.5-coder:14b
```

Sur une machine spacieuse, résoudre un profil seul peut spécialiser au-delà de ce
que sa famille obtient ; sur une machine serrée la famille s'effondre sur un seul
modèle. Depuis Python :

```python
for u in beah.list_usages():
    print(u["name"], u["family"], u["status"])

engine = beah.resolve_usage("text2sql")  # best-engine choisit le modèle ici
family = beah.resolve_family("F1")  # un seul modèle pour tout le groupe F1
```

## 6. Planifier la capacité disponible

Les questions ci-dessus portent chacune sur un modèle. `storage` pose celle qui
compte dès qu'une machine doit servir un produit : que peut contenir ce disque,
puis quelle *combinaison* peut être résidente en même temps.

```sh
best-engine-ai-helper storage
```

```
disk   : 22.1 GB free of 994.7 (97.8% used); 17.1 GB spendable
memory : 36.0 GB available to models together

already here: qwen2.5:3b (2.0 GB), qwen3-vl:4b (3.2 GB), qwen3:8b (5.2 GB), qwen3-vl:8b (6.1 GB)

Could be pulled into the space left (6):
     0.3 GB  nomic-embed-text  [embed]
     0.7 GB  mxbai-embed-large  [embed]
     1.1 GB  snowflake-arctic-embed2  [embed]
     1.1 GB  bge-m3  [embed]
     4.7 GB  qwen2.5-coder:7b  [llm]
     8.4 GB  gemma3:12b  [vlm]

Can be held in memory at the same time, best first:
  score  232.0    34.4 GB  llm:qwen3:32b-q4_k_m + vlm:qwen3-vl:14b + embed:bge-m3   (headroom 1.6 GB)
  score  231.0    35.7 GB  llm:qwen3:14b + vlm:qwen3-vl:32b + embed:bge-m3   (headroom 0.3 GB)
  score  231.0    34.4 GB  llm:qwen3:32b-q4_k_m + vlm:qwen3-vl:14b + embed:snowflake-arctic-embed2   (headroom 1.6 GB)
  score  230.7    33.9 GB  llm:qwen3:32b-q4_k_m + vlm:qwen3-vl:14b + embed:mxbai-embed-large   (headroom 2.1 GB)
  score  230.0    35.7 GB  llm:qwen3:14b + vlm:qwen3-vl:32b + embed:snowflake-arctic-embed2   (headroom 0.3 GB)
```

Deux contraintes différentes, rapportées séparément parce qu'elles échouent
différemment. `17.1 GB spendable` est inférieur aux 22,1 Go libres : la commande
garde une réserve au lieu de vous laisser remplir le volume. La section mémoire
est une recherche de combinaison plutôt qu'un classement — le meilleur LLM plus
le meilleur VLM plus le meilleur embedder ne tiennent **pas** ensemble le plus
souvent, puis la combinaison gagnante ici échange un VLM plus petit contre un LLM
plus grand. `--backend vllm` retarife le tout pour l'empreinte de vLLM au lieu de
celle d'Ollama.

Les deux tables de référence derrière chaque réponse de ce fichier sont
affichables :

```sh
best-engine-ai-helper catalog show
```

```
id                       kind   size_b  quant   disk_gb  ram_gb  general  vision
-----------------------  -----  ------  ------  -------  ------  -------  ------
qwen2.5:3b               llm    3       Q4_K_M  2.0      2.2     62       -
qwen2.5-coder:7b         llm    7       Q4_K_M  4.7      5.2     66       -
qwen2.5-coder:14b        llm    14      Q4_K_M  9.0      9.9     72       -
qwen2.5-coder:32b        llm    32      Q4_K_M  20       22      75       -
qwen3-vl:4b              vlm    4       Q4_K_M  3.2      3.5     66       72
qwen3:8b                 llm    8       Q4_K_M  5.2      5.6     74       -
```

```sh
best-engine-ai-helper hardware show
```

```
chip                     vendor  memory_gb  ollama_usable_gb  source
-----------------------  ------  ---------  ----------------  -----------
Apple M1                 apple   8          7                 apple-specs
Apple M1                 apple   16         14                apple-specs
Apple M1 Pro             apple   16         14                apple-specs
Apple M1 Pro             apple   32         29                apple-specs
Apple M1 Max             apple   32         29                apple-specs
```

Les deux sont la fusion d'un jeu de départ embarqué avec ce qui est en cache sous
`~/.best-engine-ai-helper/` ; le jeu de départ n'est jamais modifié. Leur
rafraîchissement n'a pas été lancé pour ce fichier : `catalog update` tire les
spécifications des modèles à poids ouverts depuis ApXML, `catalog update --ollama`
élargit à de vrais tags tirables depuis la bibliothèque officielle d'Ollama,
`catalog update --arena` fusionne les notes de LM Arena quand un miroir assez
frais existe puis le dit franchement quand aucun ne l'est, enfin
`hardware update` consigne la puce puis la mémoire de cette machine.

## 7. Trop gros pour tenir, exécutable quand même

Un décodeur lit ses couches dans l'ordre : seule la couche en cours de calcul
doit donc être résidente. Lisez le reste en flux depuis le disque puis l'exigence
mémoire d'un modèle s'effondre de son nombre de paramètres à sa plus large
couche — un modèle de 70 milliards de paramètres dans deux ou trois gigaoctets
au lieu de 140. La facture arrive en temps : chaque jeton relit tout le
checkpoint, ce qui place l'affaire à des **secondes par jeton** plutôt qu'à des
jetons par seconde.

Le moteur est [airllm](https://github.com/lyogavin/airllm), une dépendance de
plein droit, ce qui explique l'essentiel des quelque 2 Go d'installation de ce
paquet. Trois des quatre sous-commandes sont de l'arithmétique pure sur le
matériel puis le catalogue, puis ne l'importent jamais : elles répondent donc
juste — instantanément, même — dans un environnement où il refuserait de se
charger.

### Cette machine peut-elle lire en flux, le lui demanderait-on ?

```sh
best-engine-ai-helper airllm status
```

```
=== Layer streaming (airllm) ===
  runtime here    : mlx
  runtime import  : FAILS (install incomplete)
  storage         : apple-internal (declared)
  read bandwidth  : 4.0 GB/s
  free disk       : 22.1 GB
  shard budget    : 72.0 GB of resident memory
  request         : auto
  would activate  : no
  trigger         : not-needed

  A model already fits this machine's memory, so streaming its layers off disk would trade two to three orders of magnitude of speed for nothing. Ask for it explicitly (--backend airllm) to override.
  - the airllm runtime cannot be imported, though it is a dependency of this package — the install looks incomplete: pip install --upgrade --force-reinstall best-engine-ai-helper

  Repair the install:  pip install --upgrade --force-reinstall best-engine-ai-helper
```

Cette sortie est réelle, puis elle montre une **installation cassée** :
l'environnement où ces exemples ont tourné avait le paquet sans sa dépendance
airllm. Le panneau n'en est que plus instructif. `runtime import` est la version
honnête d'une question qui demandait avant « est-ce que l'extra est installé » —
airllm est livré avec le paquet, donc toute valeur autre qu'`ok` signale une
installation incomplète, puis la ligne le dit et imprime la commande de
réparation au lieu d'un échec plus vague plus tard. `runtime here : mlx` est un
fait distinct, toujours vrai : ce matériel *saurait* lire en flux, sur MLX.
Remarquez aussi `would activate : no` avec `trigger: not-needed` — l'échec
d'import n'est pas la raison du refus. Un modèle tient déjà, donc le flux n'a
jamais été souhaité.

`--measure` remplace la classe de stockage déclarée par une vraie mesure de ce
disque (environ 256 Mo écrits puis relus en contournant le cache de pages, une à
deux secondes) puis fait passer `basis` de `declared` à `measured`. Ces deux
secondes valent la peine, parce que le disque fixe toute la vitesse de ce
backend.

`--json` donne le jumeau lisible par une machine, exactement ce que renvoie
l'endpoint HTTP :

```sh
best-engine-ai-helper airllm status --json --request always
```

```json
{
  "decision": {
    "activate": false,
    "request": "always",
    "trigger": "manual",
    "reason": "Layer streaming cannot run here: the airllm runtime cannot be imported, though it is a dependency of this package — the install looks incomplete: pip install --upgrade --force-reinstall best-engine-ai-helper",
    "installed": false,
    "runtime": "mlx",
    "blockers": [
      "the airllm runtime cannot be imported, though it is a dependency of this package — the install looks incomplete: pip install --upgrade --force-reinstall best-engine-ai-helper"
    ]
  },
  "compute": {"accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400.0},
  "disk": {"storage": "apple-internal", "read_gbs": 4.0, "basis": "declared", "free_gb": 22.1},
  "memory_budget_gb": 72.0,
  "install": "pip install --upgrade --force-reinstall best-engine-ai-helper"
}
```

`--request always` a forcé la question puis a obtenu quand même
`activate: false`, le bloqueur étant nommé. `install` est une commande de
**réparation**, pas d'activation : c'est ce qu'il faut lancer quand `installed`
revient à faux.

### Que pourrait-elle lire en flux, à quel prix ?

```sh
best-engine-ai-helper airllm plan --kind llm --compression 4bit
```

```
=== LLM: streamable off apple-internal at 4.0 GB/s, 72.0 GB shard budget ===
id                 params  shard_gb  ckpt_gb  s/token  disk_gb  runs  notes
-----------------  ------  --------  -------  -------  -------  ----  ----------------------------------------------------
qwen3:8b           8B      1.3       4.0      1.6      20.4     yes   32 layers
qwen3-vl:8b        8B      1.3       4.0      1.6      20.4     yes   32 layers
qwen2.5-coder:7b   7B      1.3       3.5      1.4      17.9     yes   32 layers
qwen3-vl:4b        4B      1.1       2.0      0.8      10.2     yes   29 layers
qwen2.5:3b         3B      1.1       1.5      0.6      7.7      yes   28 layers
deepseek-v3:671b   671B    15.2      335.5    125.0    1040.0   NO    the split needs 1040 GB free during the layer split
qwen3:235b-a22b    235B    5.1       117.5    45.5     599.2    NO    the split needs 599 GB free during the layer split (
llama3.1:405b      405B    6.5       202.5    76.9     1032.8   NO    the split needs 1033 GB free during the layer split
qwen2.5-vl:72b     73B     2.9       36.5     14.3     186.2    NO    the split needs 186 GB free during the layer split (
llama3.3:70b       70B     2.8       35.0     13.7     178.5    NO    the split needs 178 GB free during the layer split (
mixtral:8x22b      141B    4.5       70.5     27.8     359.6    NO    the split needs 360 GB free during the layer split (
qwen3:32b-q8_0     32B     2.1       16.0     6.3      81.6     NO    the split needs 82 GB free during the layer split (1
gemma3:12b         12B     1.5       6.0      2.4      30.6     NO    the split needs 31 GB free during the layer split (7

  Pick: Qwen/Qwen3-8B-Instruct — 8B in 1.3 GB resident, 1.6 s/token, 20 GB free disk to split (4 GB after).
  A 300-token answer: 8 min.
```

Lisez trois colonnes, dans cet ordre, puis l'ordre est la leçon. `shard_gb` est
ce qui doit tenir en **mémoire** — une tranche de couche, pas le modèle — puis
c'est minuscule partout, même pour 671 milliards de paramètres. `disk_gb` est ce
qui doit être libre **pendant la découpe**, puis sur ce disque rempli à 98 % c'est
ce qui refuse presque tout : un modèle de 12 milliards de paramètres est écarté
faute de 31 Go alors que son coût résident aurait été de 1,5 Go. `s/token` est ce
que vous attendez ensuite.

C'est la profondeur, pas la taille, qui décide de la tranche : `llama3.1:405b` se
lit en flux dans une tranche de 6,5 Go sur 126 couches, là où `mixtral:8x22b` à
141 milliards de paramètres en demande 4,5 Go sur 56 — les seuls nombres de
paramètres auraient prédit l'ordre inverse.

`--context 32` retarife la tranche pour un contexte de 32k, ce qui n'est pas
gratuit : le cache KV est la seule chose que le flux ne réduit pas. `--batch 8`
tire le grand levier des deux côtés à la fois — l'horloge pour une réponse de 300
jetons ne bouge pas, mais elle achète huit réponses au lieu d'une, puis la
tranche grossit des sept caches KV supplémentaires qui les ont payées.
`--compression 4bit`, employé ci-dessus, divise les octets lus par jeton puis
vaut environ un facteur 3.

### Modèle natif ou modèle en flux ? Un seul écran.

C'est la décision que le backend impose réellement, puis la commande tarife les
deux côtés dans la même unité.

```sh
best-engine-ai-helper airllm compare --tokens 300
```

```
=== LLM: ollama vs airllm, for a 300-token answer ===
  budgets: 36.0 GB resident (ollama) · 72.0 GB per shard (airllm) · disk 4.0 GB/s (declared)
model                               backend  score  resident  tok/s  answer  runs
----------------------------------  -------  -----  --------  -----  ------  ----
qwen3:72b-q8_0                      ollama   89     78.0      3.3    2 min   NO
qwen3:72b-q4_k_m                    ollama   87     48.0      5.4    56 s    NO
qwen3:32b-q8_0                      ollama   85     36.0      7.2    42 s    NO
qwen3:32b-q4_k_m                    ollama   83     22.0      11.8   25 s    NO
qwen3:14b                           ollama   78     10.5      24.8   12 s    yes
gemma3:12b                          ollama   77     9.2       28.3   11 s    yes
Qwen/Qwen3-VL-4B-Instruct           airllm   66     1.6       0.425  12 min  yes
Qwen/Qwen2.5-3B-Instruct            airllm   62     1.5       0.567  9 min   yes
deepseek-ai/DeepSeek-V3             airllm   91     29.0      0.005  16.4 h  NO
Qwen/Qwen3-235B-A22B-Instruct-2507  airllm   90     14.5      0.007  11.5 h  NO
Qwen/Qwen3-72B-Instruct             airllm   89     6.2       0.024  3.5 h   NO
meta-llama/Llama-3.1-405B-Instruct  airllm   88     18.5      0.004  19.9 h  NO

  Streaming buys nothing here: Qwen/Qwen3-VL-4B-Instruct scores no higher than qwen3-vl:14b, which already fits and answers in 13 s. Stay native.
```

Le verdict est toute la sortie. Sur cette machine, les modèles diffusables qui
*tiennent sur le disque* sont de petits modèles qui ne notent pas mieux que ce
qui tourne déjà nativement, puis les gros qui noteraient plus haut ne peuvent pas
être découpés sur un disque rempli à 98 % — la recommandation honnête est donc de
rester en natif, puis elle est donnée. C'est le comportement qu'on veut ici : un
outil qui trouverait toujours le flux séduisant serait inutile.

`--batch 8` est le levier à essayer avant de conclure que c'est trop lent (huit
prompts traversent ensemble chaque passe de couche), puis `--compression 4bit`
est l'autre. Ils se composent.

### Payer le téléchargement délibérément

Le premier appel en flux télécharge le checkpoint puis le découpe en tranches par
couche, ce qui pour un grand modèle représente des dizaines de minutes de disque
puis ressemble exactement à un blocage. Payez-le exprès à la place :

```sh
best-engine-ai-helper airllm prepare \
  --model meta-llama/Llama-3.3-70B-Instruct \
  --compression 4bit \
  --shards-path /Volumes/fast/airllm-shards
```

Non lancée pour ce fichier : elle télécharge un checkpoint de 70 milliards de
paramètres. `--shards-path` mérite de viser votre volume le plus rapide, parce
que la lecture des tranches *est* la vitesse de décodage. `--delete-original`
supprime le checkpoint téléchargé dès que les tranches existent, ce qui divise par
deux l'exigence disque — au prix d'un nouveau téléchargement si les tranches sont
perdues. `--compression` accepte `4bit` ou `8bit`.

### Le même brief, résolu pour le flux

```sh
best-engine-ai-helper resolve --brief llm.brief.yaml --backend airllm
```

```
WARNING | The brief wants schema-constrained output and llm resolved to a streamed model, which cannot honour one. Schema-driven calls must stay on an Ollama model.
Wrote llm.engine.yaml
  backend: airllm  (llm=Qwen/Qwen3-VL-4B-Instruct, vlm=Qwen/Qwen3-VL-4B-Instruct)
  NOTE: hardware-specific — add 'llm.engine.yaml' to .gitignore, do not commit.
  bring it up:  best-engine-ai-helper airllm prepare --model Qwen/Qwen3-VL-4B-Instruct
```

L'avertissement est le point important. Le brief de la
[section 3](#3-un-brief-par-dépôt-un-moteur-par-machine) demande
`structured_output: true`, puis airllm n'a aucune génération contrainte par
schéma : forcer ce backend contredit donc le brief, puis la commande le dit au
lieu de produire en silence quelque chose qui échouerait au premier appel avec
`json_schema=`. Le fichier moteur le consigne honnêtement :

```yaml
backend: airllm
base_url: ''              # une bibliothèque, pas un serveur : ça tourne dans votre processus
airllm:
  activate: false
  trigger: manual
  runtime: mlx
  installed: false
  compression: null
llm:
  model: Qwen/Qwen3-VL-4B-Instruct
  catalog_id: qwen3-vl:4b
  backend: airllm         # par type, pour qu'un descripteur mixte reste lisible
  streaming: true
  ram_gb: 1.6             # une tranche résidente
  checkpoint_gb: 8.0      # ce que chaque jeton relit
  layers: 29
  layers_estimated: true
  disk_peak_gb: 16.8
  disk_steady_gb: 8.8
  disk_fits: true
  est_tokens_per_s: 0.425
  seconds_per_token: 2.4
  structured_output: false  # airllm n'a pas de génération contrainte par schéma
serve:
- best-engine-ai-helper airllm prepare --model Qwen/Qwen3-VL-4B-Instruct
```

Sans `--backend`, un type pour lequel rien ne tient monte de lui-même vers le
flux, puis ce type-là seulement. Mettez `airllm: never` dans le brief, ou
`BEST_ENGINE_AIRLLM=never`, pour couper cette escalade entièrement.

### Depuis Python

```python
hw, disk = beah.available_memory(), beah.disk_profile()

entry = {
    "id": "llama3.3:70b",
    "size_b": 70,
    "layers": 80,
    "hf_id": "meta-llama/Llama-3.3-70B-Instruct",
}

# Trois réponses différentes à « c'est rapide comment », toutes vraies
timing = beah.airllm_generation_time(entry, disk["read_gbs"], new_tokens=300, batch=8)
print(timing["decode_tps"])  # 0.024  — régime établi, une séquence
print(timing["time_to_first_token_s"])  # 41.176 — une passe, prompt compris
print(timing["effective_tps"])  # 0.194  — huit réponses partagent chaque passe

# Cette machine devrait-elle lire en flux du tout ?
print(beah.airllm_decide(conventional_resolved=False)["reason"])

# Natif ou en flux, pour une réponse de 300 jetons ?
print(
    beah.airllm_compare(
        beah.load_catalog(),
        hw=hw,
        disk=disk,
        bandwidth_gbs=beah.compute_profile()["bandwidth_gbs"],
        new_tokens=300,
    )["verdict"]
)
```

Ces trois chiffres de temps sont la sortie exécutée, puis l'écart entre eux est
l'argument qui justifie de les avoir tous les trois : 0,024 tok/s est le régime
établi pour une séquence, 41,176 s est une seule passe avant, puis 0,194 tok/s
est ce que le même matériel devient quand huit prompts sont groupés.
`disk_profile(measure=True)` prend une seconde ou deux puis remplace la bande
passante de lecture déclarée par une bande passante mesurée.

`beah.airllm_generate(prompt, model=..., max_new_tokens=64)` exécute un modèle en
flux dans ce processus, sans aucun serveur. C'est la seule fonction ici qui
exige le moteur importable : elle n'est donc pas exécutée dans ce fichier.

## 8. Qui appelle quoi, à quel coût

Chaque appel `llm.chat()` — venu des gardes de ce paquet ou de n'importe quel
projet en aval — peut être ajouté à un journal SQLite local, uniquement en
ajout, sous `~/.best-engine-ai-helper/usage.db` : qui a appelé, quel modèle puis
quel backend, la latence, le succès ou l'échec, puis un coût toujours égal à
`0.0` pour Ollama ou vLLM en local. Il existe pour le cas « une entreprise,
plusieurs personnes sur une machine partagée », sans monter de pile de
télémétrie.

```sh
best-engine-ai-helper activity
```

```
No calls recorded yet.
```

C'est la vraie sortie contre un journal vierge, puis c'est ce qu'un lecteur doit
attendre : rien n'est consigné avant qu'un modèle ne soit appelé. Dès que des
appels existent, la même commande rapporte les totaux puis une ventilation par
utilisateur puis par modèle ; `--format json` donne le jumeau lisible par une
machine.

Local uniquement, aucun appel réseau. `BEST_ENGINE_NO_LEDGER=1` désactive
entièrement l'enregistrement, puis `BEST_ENGINE_USER=alice` attribue les appels à
une personne nommée sur une machine partagée. L'API bibliothèque derrière tout
cela est `best_engine_ai_helper.observe` (`enable()`, `as_user(name)`,
`Ledger.summary()`).

## 9. La GUI, l'API HTTP puis les outils MCP

Un seul processus sert les trois surfaces.

```sh
best-engine-ai-helper gui          # GUI navigateur + routes /api, port 8000
best-engine-ai-helper-mcp          # la même chose, plus l'endpoint MCP sur /mcp
```

Ouvrez `http://127.0.0.1:8000/gui` : le panneau matériel se charge
immédiatement, puis saisir une tâche appelle le même `recommend()` qui porte
`report`. La page est bilingue — français par défaut, anglais sur
`/gui?lang=en`. `--host` puis `--port` remplacent les valeurs par défaut. Voir
[GUI.md](GUI.md) pour les captures d'écran puis la notice complète.

Les endpoints JSON sont utilisables directement, puis la sortie ci-dessous est
réelle :

```sh
curl -s http://127.0.0.1:8000/api/system | python3 -m json.tool
```

```json
{
    "platform": "darwin",
    "chip_vendor": "apple",
    "memory": {"unified_gb": 96.0, "vram_gb": null, "ram_gb": 96.0},
    "compute": {"accelerator": "gpu-metal", "chip": "Apple M2 Max", "bandwidth_gbs": 400.0},
    "memory_budget_gb": 36.0,
    "hardware": {"...": "le relevé os-helper en direct, exactement comme dans detect"}
}
```

```sh
curl -s -X POST http://127.0.0.1:8000/api/recommend \
     -H 'Content-Type: application/json' \
     -d '{"task": "product descriptions and image-quality checks"}' \
  | python3 -m json.tool
```

```json
{
    "task": {
        "input": "product descriptions and image-quality checks",
        "kinds": ["llm", "vlm"],
        "application": "generalist",
        "vlm_application": "vision",
        "matched": ["image"],
        "language": "en"
    },
    "backend": "ollama",
    "memory_budget_gb": 36.0,
    "headroom": 0.5,
    "comfort_tps": 15.0,
    "recommendations": {
        "llm": {
            "axis": "generalist",
            "chosen": {
                "id": "gemma3:12b",
                "vllm_id": "google/gemma-3-12b-it",
                "ram_gb": 9.2,
                "score": 77.0,
                "fits": true,
                "structured_output": true,
                "est_tokens_per_s": 28.3,
                "tps_basis": "estimated",
                "comfortable": true,
                "installed": false
            }
        }
    }
}
```

```sh
curl -s 'http://127.0.0.1:8000/api/airllm?answer_tokens=300&batch=8' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["comparison"]["verdict"])'
```

```
Streaming buys nothing here: Qwen/Qwen3-VL-4B-Instruct scores no higher than qwen3-vl:14b, which already fits and answers in 13 s. Stay native.
```

Ce seul appel renvoie ensemble la décision, le profil de stockage, les plans
classés puis la comparaison ; ses clés de premier niveau sont `decision`, `disk`,
`memory_budget_gb`, `comfort_tps_streaming`, `install`, `chosen`, `plans` puis
`comparison`. `GET /api/providers` renvoie les mêmes lignes que la commande
`providers`, puis `GET /api/activity` lit le journal de la
[section 8](#8-qui-appelle-quoi-à-quel-coût).

Chacune de ces routes est publiée comme **outil MCP** par
`best-engine-ai-helper-mcp`, de sorte qu'un hôte d'agent puisse les appeler
directement. L'adaptateur ne publie exprès que les routes qui décident : aucun
outil MCP ici n'exécute de modèle. `BEST_ENGINE_HOST` puis `BEST_ENGINE_PORT`
remplacent l'adresse d'écoute.

Une quatrième surface sur le même port exécute un modèle au lieu de décider
lequel : `best-engine-ai-helper serve` ajoute un `/v1` compatible OpenAI, si
bien qu'un client OpenAI existant demande le modèle nommé `best` puis obtient ce
que ce matériel devrait réellement exécuter. Voir
[Ligne de commande](#ligne-de-commande) pour sa bannière puis ses alias de
modèles.

## 10. L'appeler depuis votre propre paquet

C'est l'intégration qu'utilise chaque autre membre de la suite AI Helpers :
aucune constante `DEFAULT_MODEL` nulle part, le modèle toujours lu depuis un
moteur résolu.

Le point d'entrée le moins cher, pour un paquet qui a seulement besoin de savoir
*quel tag* :

```python
print(beah.text_model())  # 'qwen3:8b'
print(beah.vision_model())  # 'gemma3:12b'
print(beah.resolved_models())  # {'text': 'qwen3:8b', 'vision': 'gemma3:12b'}
```

Ces fonctions résolvent une surcharge d'environnement, puis la sélection
persistée par `pull`, puis un défaut sûr — sans sonder le matériel, sans réseau,
de façon déterministe : elles sont donc sans danger en intégration continue. Les
valeurs ci-dessus sont la vraie sortie sur une machine où rien n'a encore été
tiré, ce qui est exactement pourquoi ce sont les défauts.

Le motif complet, pour un dépôt qui possède un brief :

```python
engine = beah.ensure(".")  # charge llm.engine.yaml, le résout au premier appel
print(beah.model_for(engine, "llm"))  # ('ollama', 'http://localhost:11434', 'gemma3:12b')

summary = llm.chat(prompt, engine=engine, kind="llm")
critique = llm.chat(prompt, engine=engine, kind="vlm", images=[png], json_schema=SCHEMA)
```

`chat` lit le backend puis le modèle dans le moteur, puis délègue à Ollama
(`/api/generate`) ou à vLLM (`/v1/chat/completions` au format OpenAI) de façon
transparente ; avec un `json_schema` il renvoie un dictionnaire déjà parsé plutôt
qu'une chaîne. Voir [Intégration avec les projets en aval → Modèle
B](LISEZMOI.md#modèle-b--un-moteur-par-projet-résolu-depuis-un-brief-ajusté) du
LISEZMOI pour le déroulé complet puis la politique en cas de fichier manquant.

Un appel contraint par schéma, exécuté contre un démon local :

```python
out = llm.chat(
    "In one short sentence: what is unified memory?",
    model="qwen2.5:3b",
    json_schema={
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    },
)
print(out)
```

```
{'answer': 'Unified memory is a memory management system that allows CPU and GPU to share memory efficiently.'}
```

C'est le seul extrait de ce fichier qui a eu besoin d'Ollama en fonctionnement,
puis le seul dont la sortie n'est **pas** reproductible : un modèle n'est pas une
fonction, puis une seconde exécution de cet appel exact a renvoyé
« …share memory in a unified way ». C'est la *forme* qui est garantie —
`json_schema=` en fait un dictionnaire parsé portant une clé `answer` plutôt
qu'une chaîne à passer au peigne d'une expression régulière — pas la phrase
qu'il contient. `model=` n'est écrit que parce que l'exemple n'a pas de brief à
résoudre ; dans du vrai code c'est `engine=`, puis le tag n'est jamais écrit
nulle part.

La machinerie de décision s'importe seule, sans CLI ni fichier moteur :

```python
hw, catalog = beah.available_memory(), beah.load_catalog()

print(beah.select(hw, catalog, kind="vlm")["id"])  # 'gemma3:12b'
print(beah.select(hw, catalog, kind="llm")["id"])  # 'qwen3:32b-q8_0'
```

Remarquez que `select` puis `report` se contredisent ici, puis que la
contradiction est correcte : `select` renvoie le meilleur modèle qui **tient en
mémoire** (`qwen3:32b-q8_0`, 36 Go, score 85), là où `report` puis `resolve`
appliquent en plus le plancher de débit confortable, donc renvoient `gemma3:12b`.
Passez par `rank()` quand vous voulez la liste ordonnée avec le drapeau
`comfortable` sur chaque ligne.

La recommandation complète — mémoire, calcul puis tâche ensemble — tient en un
appel :

```python
report = beah.recommend_engines(
    beah.available_memory(),
    beah.load_catalog(),
    task="product descriptions and image-quality checks",
    compute=beah.compute_profile(),
)
print(report["recommendations"]["vlm"]["chosen"]["id"])  # 'gemma3:12b'
print(beah.to_markdown(report))  # le rapport de la section 2
```

`beah.write_report(report, "engine")` écrit la paire `engine.md` / `engine.json`
que produit `report --out engine`.

## Ligne de commande

Une seule ligne de commande, construite avec click. `best-engine-ai-helper -h`
la liste, puis `best-engine-ai-helper <commande> -h` documente n'importe laquelle
d'entre elles. Les versions antérieures à la 1.9.0 installaient aussi un second
point d'entrée suffixé qui la doublait commande par commande ; il n'y a plus
qu'un seul nom, c'est celui-ci.

| Commande | Ce qu'elle fait | Exige |
|---|---|---|
| `detect` | le matériel de cette machine, en JSON | — |
| `recommend` | les candidats classés pour ce matériel ; `--kind`, `--headroom` | — |
| `report` | le ou les meilleurs moteurs pour une tâche libre, Markdown + JSON ; `--task`, `--out`, `--live`, `--format`, `--no-cloud`, `--quality-vs-cost`, `--cloud-provider` | — |
| `resolve` | un brief vers un fichier moteur propre à la machine ; `--brief`, `--out`, `--backend`, `--endpoint` | — |
| `usages list` / `show` / `resolve` | les profils de tâche puis les familles embarqués | — |
| `storage` | ce qui tient sur le disque, puis quels modèles tiennent ensemble en mémoire ; `--backend` | — |
| `providers` | quels fournisseurs cloud sont utilisables à l'instant, puis pourquoi pas les autres ; `--json` | — |
| `doctor` | le moteur résolu face au démon en fonctionnement ; code non nul s'ils se contredisent ; `--directory`, `--timeout` | Ollama |
| `catalog show` | le catalogue de modèles fusionné | — |
| `catalog update` | rafraîchit le cache du catalogue ; `--limit`, `--timeout`, `--ollama`, `--arena` | réseau |
| `hardware show` | la table des puces fusionnée | — |
| `hardware update` | consigne la puce puis la mémoire de cette machine | — |
| `airllm status` | cette machine peut-elle lire les couches en flux, le lui demanderait-on ; `--measure`, `--json`, `--request` | — |
| `airllm plan` | ce qu'elle pourrait lire en flux, à quel prix ; `--kind`, `--compression`, `--context`, `--batch`, `--json` | — |
| `airllm compare` | natif face au flux, même réponse, les deux prix ; `--tokens`, `--batch`, `--compression`, `--measure`, `--json` | — |
| `airllm prepare` | télécharge puis découpe un checkpoint maintenant ; `--model`, `--compression`, `--shards-path`, `--delete-original` | réseau, moteur |
| `pull` | tire le meilleur modèle puis passe les deux gardes Ralph ; `--keep-failed`, `--vllm`, `--application`, `--min-tps` | Ollama, réseau |
| `validate` | repasse les gardes Ralph sur le modèle configuré | Ollama |
| `env` | affiche le bloc d'environnement pour `~/.zshrc` | `pull` d'abord |
| `activity` | le journal de coût local ; `--format` | — |
| `gui` | sert la GUI navigateur puis les routes `/api` ; `--host`, `--port` | — |
| `serve` | le même port, plus un `/v1` compatible OpenAI ; `--host`, `--port` | Ollama, pour répondre |
| `imagine plan` | classe les modèles texte-vers-image que cette machine sait exécuter ; `--size`, `--json` | — |
| `imagine generate` | produit une image en local ; `--prompt`, `--out`, `--model`, `--size`, `--steps`, `--seed`, `--negative` | réseau |

Deux d'entre elles méritent une ligne à part. `serve` pose une surface
**compatible OpenAI** sur le même port que la GUI, les routes `/api` puis
`/mcp` : un client OpenAI existant atteint ainsi le modèle que cette machine
devrait exécuter sans connaître son nom.

```
  OpenAI-compatible API : http://127.0.0.1:8000/v1
  Browser GUI           : http://127.0.0.1:8000/gui
  OpenAPI schema        : http://127.0.0.1:8000/docs
  MCP endpoint          : http://127.0.0.1:8000/mcp

  from openai import OpenAI
  client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="not-needed")
  client.chat.completions.create(model="best", messages=[...])

  Model names: best · best-llm · best-vlm · best-embed · best-image
               best:<task>  (e.g. best:write SQL)
```

`GET /v1/models` liste ces alias aux côtés de chaque entrée concrète du
catalogue : `best` résout vers un VLM dès que la requête porte des images, puis
`best:write SQL` fait tourner la même analyse de tâche que `report`.
`api_key="not-needed"` est littéral : le serveur est local puis ne demande rien.

`imagine` est le troisième type de modèle que ce paquet choisit, puis
l'arithmétique n'y est pas celle d'un LLM : un modèle de diffusion est trois ou
quatre réseaux qui se relaient, si bien que son empreinte dépend de leur
résidence simultanée ou de leur passage au décalage par composant de
`diffusers`, puis son coût s'exprime en nombre de pas multiplié par les passes du
dénoiseur plutôt qu'en jetons par seconde.

```sh
best-engine-ai-helper imagine plan
```

```
=== Image models: 36.0 GB budget, 400.0 GB/s memory bandwidth ===
id             params  size       steps  gb    offload  s/image  runs  notes
-------------  ------  ---------  -----  ----  -------  -------  ----  -----
flux1-schnell  16.9B   1024x1024  4      30.8  yes      16.9     yes
sd35-medium    10.9B   1024x1024  28     28.3  no       24.8     yes
sdxl           3.5B    1024x1024  28     9.8   no       25.8     yes
sdxl-turbo     3.5B    512x512    4      9.0   no       0.9      yes
sd15           1.1B    512x512    28     2.9   no       2.1      yes

  Pick: black-forest-labs/FLUX.1-schnell — 1024x1024 in 30.8 GB resident, 4 steps, about 16.9 s an image (components taking turns).
```

Lisez la colonne `steps` face à `s/image` : `sdxl-turbo` est le même réseau de
3,5 milliards de paramètres que `sdxl`, distillé à 4 pas au lieu de 28, puis
cette seule colonne porte tout le facteur 28 d'attente. `offload: yes` sur FLUX
signifie qu'il ne tient qu'en confiant les composants à `diffusers` à tour de
rôle. `--size auto` est le défaut puis la comparaison juste, parce que demander
du 1024x1024 à un modèle de 512 pixels duplique les sujets au lieu d'ajouter du
détail. `imagine generate` n'est pas lancée ici : elle télécharge un pipeline
diffusers.

Les trois qui ne sont pas démontrées ci-dessus, parce que les lancer ici
impliquerait un téléchargement de modèle :

```sh
best-engine-ai-helper pull        # tire le meilleur modèle ; passe les deux gardes Ralph
best-engine-ai-helper validate    # repasse les gardes sur le modèle courant
best-engine-ai-helper env         # affiche le bloc d'environnement pour ~/.zshrc
```

`pull` sélectionne comme le fait `recommend`, télécharge via Ollama, puis refuse
d'écrire quoi que ce soit avant que le modèle ne passe deux gardes : il doit
repérer puis corriger un défaut semé dans un texte court (la boucle Ralph), puis
repérer un défaut visuel évident semé dans une petite image de test (la boucle
Ralph Eyeball). Alors seulement `env.sh` est écrit, ce qu'`env` affiche. Lancée
avant `pull`, elle le dit :

```
env.sh not found. Run `best-engine-ai-helper pull` first.
```

## Dépannage

**`env.sh not found. Run best-engine-ai-helper pull first.`** — `env` affiche un
fichier qu'écrit `pull`. Rien n'a encore été tiré puis validé.

**`doctor` dit que le fichier moteur nomme un modèle que le démon ne sert pas.**
Le choix se fait contre le catalogue, pas contre ce qui est téléchargé. Lancez la
ligne `ollama pull …` qu'a imprimée `resolve` ; sinon résolvez à nouveau.

**Tout affiche `NO` dans la colonne `fits`.** Le budget est la moitié du bassin
*utilisable*, pas la moitié de la mémoire installée : 96 Go deviennent 72,0 Go
utilisables, puis 36,0 Go après la marge.
`beah.effective_budget(beah.available_memory())` affiche le chiffre.
`--headroom` ne fait que resserrer ; au-delà de 0,5 la valeur est ramenée au
plafond.

**Un modèle tient puis n'est pourtant pas choisi.** Il a échoué au plancher de
débit confortable, pas au test mémoire. Regardez la colonne `comfy`, puis
`min_tps` dans le brief.

**`airllm status` dit `runtime import : FAILS (install incomplete)`.** airllm est
une dépendance de plein droit : c'est donc une installation cassée plutôt qu'un
extra manquant : un conteneur allégé, une roue qui n'a pas pu se construire.
Le panneau imprime la commande de réparation. `status`, `plan` puis `compare`
continuent de fonctionner de toute façon ; seule la génération réelle exige le
moteur.

**`airllm plan` refuse presque tout sur `disk_gb`.** Cette colonne est la place
nécessaire *pendant la découpe des couches*, soit à peu près deux fois le
checkpoint, puis c'est le bloqueur habituel — bien plus souvent que la mémoire.
Libérez de la place ; sinon visez un autre volume avec `--shards-path`.

**Un appel à sortie structurée revient vide.** Soit le modèle ne sait pas honorer
un schéma JSON — `catalog show` puis la colonne `notes` disent lesquels, la
famille Qwen3-VL étant la surprise courante — soit le backend est airllm, qui n'a
aucune génération contrainte par schéma. `resolve --backend airllm` avertit
exactement de cela.

**`providers` dit `0 of 4 usable` alors qu'une clé est exportée.** L'ordre de
recherche est `settings.yaml`, puis un éventuel `.env`, puis l'environnement du
processus, puis le trousseau du système, puis c'est l'`api_key_env` du brief qui
décide *quel nom de variable* est lu. Une clé détenue sous un autre nom que celui
conventionnel du fournisseur exige ce champ. L'étape trousseau elle-même exige
`pip install 'best-engine-ai-helper[cloud]'`.

**Un appel cloud échoue puis rien ne semble se passer.** Il s'est replié. Chaque
moteur cloud porte un repli local résolu depuis le même brief, puis `activity`
est l'endroit où l'appel payant en échec puis la reprise locale apparaissent
tous les deux.
