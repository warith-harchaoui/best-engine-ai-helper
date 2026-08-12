# best-engine-ai-helper

[🇫🇷](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/README.md)

[![Licence : BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](#)

Choisit et télécharge le meilleur modèle de langage (LLM, *large language model*) ou modèle
de vision-langage (VLM, *vision-language model*) local adapté au matériel de la machine
courante.

L'outil détecte la mémoire disponible (mémoire unifiée Apple Silicon, mémoire vidéo NVIDIA
ou RAM système), consulte un catalogue de modèles intégré et sélectionne le modèle au
meilleur score qui tient dans une marge de sécurité configurable. Après la sélection, il
télécharge le modèle via Ollama, exécute deux contrôles de qualité (la boucle Ralph pour la
prose et la boucle Ralph Eyeball pour la vision) et écrit un fichier d'environnement que
les projets en aval viennent sourcer.

[![logo](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/assets/logo.png)](https://harchaoui.org/warith/ai-helpers)

## La promesse

`best-engine-ai-helper` est conçu pour fonctionner entièrement hors ligne une fois les poids
téléchargés. Deux cas, en toute franchise :

1. **Garanti local.** La détection du matériel, la sélection du modèle, les contrôles de
   qualité et l'écriture du fichier d'environnement s'exécutent tous sur votre machine. Aucune
   télémétrie, aucun compte, aucune dépendance à un service en nuage.
2. **La seule réserve : le téléchargement initial.** La commande `pull` télécharge les poids
   du modèle via Ollama (un téléchargement normal depuis les serveurs Ollama). Ensuite, tout
   fonctionne hors ligne. La mise à jour du catalogue (`catalog update`) est également en ligne,
   mais optionnelle : le catalogue intégré suffit pour un usage courant.

Une GUI minimale dans le navigateur (`best-engine-ai-helper gui`) couvre la moitié en
lecture seule de ce flux (les caractéristiques matérielles et la recommandation de moteur
à partir d'une tâche) sans passer par le terminal. La page est bilingue : français par
défaut, anglais via `/gui?lang=en`, avec un lien d'en-tête pour basculer. Voir
[GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md) (en anglais).

## Documentation

[💻 Documentation](https://harchaoui.org/warith/ai-helpers/docs/best-engine-ai-helper-doc/)

[🗺️ Paysage](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/PAYSAGE.md)

[📋 Exemples](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXEMPLES.md)

## Prérequis

- Python 3.10 ou ultérieur
- [Ollama](https://ollama.com) (nécessaire uniquement pour `pull`, `validate` et `env` ; pas
  requis pour `detect`, `recommend` ou `report`)
- Tout le reste s'installe automatiquement : os-helper (détection matérielle),
  PyYAML, click, requests, langdetect, ainsi que les surfaces FastAPI/MCP
  (`fastapi`, `uvicorn`, `fastapi-mcp`). La CLI, la GUI, l'API HTTP et le
  serveur MCP font tous partie de l'installation par défaut, rien
  d'optionnel à activer.
- Optionnel : `[cloud]` pour le mode fournisseur cloud (retry, cache,
  pseudonymisation, repli sur le trousseau OS pour les clés API) et
  `[filtered]` pour de vrais classifieurs NSFW (un modèle DistilBERT pour le
  texte ; le détecteur d'image basé sur CLIP de LAION, via `transformers`
  pour l'encodeur CLIP et un modèle `onnxruntime` embarqué pour la tête de
  classification).

## Installation

Le paquet est en Python pur (Python 3.10+). Les seuls éléments spécifiques à
la plateforme sont **Python lui-même** et le runtime **Ollama** optionnel
(nécessaire uniquement pour `pull` / `validate` / `env`, pas pour `detect`,
`recommend`, `report`, la GUI ni la surface MCP). Choisissez votre OS
ci-dessous.

### 🍎 macOS

```sh
# 1. Python 3.10+ (ignorez si déjà présent : python3 --version)
brew install python

# 2. Installer dans un environnement virtuel isolé (recommandé)
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install best-engine-ai-helper

# 3. Optionnel : Ollama, uniquement si vous utiliserez `pull`
brew install ollama          # puis : ollama serve
```

La détection matérielle utilise `system_profiler` intégré (mémoire unifiée
Apple Silicon) : rien d'autre à installer.

### 🐧 Ubuntu / Debian

```sh
# 1. Python 3.10+ avec le support venv
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

# 2. Installer dans un environnement virtuel isolé (recommandé)
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install best-engine-ai-helper

# 3. Optionnel : Ollama, uniquement si vous utiliserez `pull`
curl -fsSL https://ollama.com/install.sh | sh   # puis : ollama serve
```

La détection GPU est automatique quand les outils du fabricant sont dans le
`PATH` : `nvidia-smi` (fourni avec le pilote NVIDIA) pour la VRAM NVIDIA,
`rocm-smi` (pile ROCm) pour AMD. Sans GPU, l'outil retombe sur la RAM système.

### 🪟 Windows (PowerShell)

```powershell
# 1. Python 3.10+ (ignorez si déjà présent : py --version)
winget install Python.Python.3.12

# 2. Installer dans un environnement virtuel isolé (recommandé)
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install best-engine-ai-helper

# 3. Optionnel : Ollama, uniquement si vous utiliserez `pull`
winget install Ollama.Ollama
```

La VRAM NVIDIA est détectée via `nvidia-smi` (installé avec le pilote).

### Depuis les sources (tout OS)

```sh
git clone https://github.com/warith-harchaoui/best-engine-ai-helper
cd best-engine-ai-helper
pip install -e .
```

### Vérifier l'installation

```sh
best-engine-ai-helper --version
best-engine-ai-helper detect     # affiche le matériel de la machine en JSON
```

Chaque commande existe aussi via un jumeau argparse,
`best-engine-ai-helper-argparse` (mêmes options, même sortie) : la surface
CLI sans dépendance supplémentaire de la suite (click est ici une dépendance
de base, donc `best-engine-ai-helper` reste le point d'entrée principal ; le
jumeau argparse est une surface ajoutée, pas un remplacement).

## Démarrage rapide

```sh
# Afficher le matériel détecté
best-engine-ai-helper detect

# Voir quels modèles seraient sélectionnés (sans téléchargement)
best-engine-ai-helper recommend

# Recommander le(s) meilleur(s) moteur(s) pour une tâche, en rapport (Markdown + JSON)
best-engine-ai-helper report --task "fiches produit et contrôle qualité des photos" --out engine

# Parcourir le catalogue complet
best-engine-ai-helper catalog show

# Parcourir la table des puces matérielles
best-engine-ai-helper hardware show

# Lancer la GUI navigateur
best-engine-ai-helper gui

# Qui appelle quoi et à quel coût (journal SQLite local)
best-engine-ai-helper activity
```

Les mêmes points d'accès `/api/system`, `/api/recommend` et `/api/activity`
sont aussi accessibles comme outils MCP pour tout hôte agentique compatible :

```sh
best-engine-ai-helper-mcp        # -> http://127.0.0.1:8000 (MCP sur /mcp)
```

Voir [EXEMPLES.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXEMPLES.md) pour des recettes complètes avec exemples de sortie
et [GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md) pour la GUI navigateur.

## GUI

`best-engine-ai-helper gui` sert une GUI mono-page (FastAPI + JS natif, sans étape de
build) sur `http://127.0.0.1:8000/gui` : les mêmes caractéristiques système que `detect`,
et une zone de texte pour la tâche qui renvoie la même recommandation que `report`, sans
terminal. La page est bilingue (français par défaut, anglais sur `/gui?lang=en`), avec un
lien d'en-tête pour basculer.

![Résultats de recommandation](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/screenshots/gui-recommendation.png)

Voir [GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md) pour le détail complet, l'API JSON sous-jacente et comment le jeu
d'icônes (favicon / touch-icon) est généré à partir de `assets/logo.png`.

## Journal d'activité

Chaque appel `llm.chat()` (depuis les contrôles `pull`/`validate` de cet outil,
ou depuis tout projet en aval qui importe `best_engine_ai_helper.llm`) peut
être enregistré dans un journal SQLite local, en ajout seul
(`~/.best-engine-ai-helper/usage.db`) : qui a appelé (variable d'environnement
`BEST_ENGINE_USER`, sinon le nom de connexion du système), quel modèle et
backend, la latence, le succès ou l'échec et un coût estimé pour les backends
payants (toujours `0,0` pour Ollama/vLLM en local). Pensé pour le cas « une
entreprise, plusieurs utilisateurs sur une machine partagée » : répondre à
« qui appelle quoi, combien de fois, à quel coût » sans pile de télémétrie
séparée. Local uniquement : aucun appel réseau, aucun service tiers.

```sh
best-engine-ai-helper activity              # tableau
best-engine-ai-helper activity --format json
```

Le CLI, la GUI et le serveur MCP activent l'enregistrement par défaut ;
désactivable avec `BEST_ENGINE_NO_LEDGER=1`. La section **Activité** de la GUI
et `GET /api/activity` lisent le même journal. Voir
`best_engine_ai_helper.observe` pour l'API bibliothèque (`enable()`,
`as_user(nom)`, `Ledger.summary()`).

## Comment fonctionne la sélection

La sélection pèse quatre facteurs, tous rendus explicites dans la sortie de `report` pour
que la recommandation soit reproductible et discutable.

### 1. Capacité de sortie structurée

La suite AI-Helpers fait passer chaque tâche par un schéma JSON (analyse d'intention,
propositions d'édition, critique visuelle). Certains modèles open-weight n'honorent pas la
sortie structurée contrainte par grammaire d'Ollama et renvoient une réponse vide (la
famille Qwen3-VL, vérifié sur `qwen3-vl:8b`). Un modèle marqué `structured_output: false`
dans le catalogue n'est jamais choisi automatiquement, quel que soit son score brut ; il
reste plus bas dans le classement pour qu'une tâche sans schéma puisse le retrouver. Les
entrées sans ce marqueur sont supposées capables.

### 2. Adéquation mémoire

La mémoire disponible vient de la première sonde qui réussit : mémoire unifiée Apple Silicon
(`system_profiler`), mémoire vidéo NVIDIA (`nvidia-smi`), mémoire vidéo AMD (`rocm-smi`),
sinon la moitié de la RAM système comme estimation conservative sur CPU. Le budget utilisable
n'est pas tout le pool : sur Apple Silicon, Metal plafonne l'allocation GPU à environ 66 %
de la mémoire unifiée jusqu'à 36 Go et environ 75 % au-delà (`recommendedMaxWorkingSetSize`),
puis une marge de sécurité `headroom` (par défaut 0,85) s'applique par-dessus. Un modèle
tient quand son `ram_gb` (pic d'inférence estimé) reste au plus égal à ce budget.

### 3. Adéquation à la tâche

Une tâche, même une phrase vague comme « fiches produit et contrôle qualité des photos »,
se traduit en un axe de benchmark (`generalist`, `code`, `math`, `ocr`, `vision`) et en
types de modèles nécessaires (du texte implique un LLM, tout visuel implique un VLM). Parmi
les modèles qui tiennent, le meilleur score sur cet axe l'emporte.

### 4. Débit

La génération est bornée par la bande passante mémoire : chaque jeton lit une fois le modèle
actif en mémoire, donc le plafond est `bande passante ÷ taille`, réduit à environ 65 % pour
le cache KV et les surcoûts. `report` estime les jetons/s par candidat et propose une
alternative plus légère et plus rapide quand elle est presque aussi forte. Plus gros n'est
pas toujours mieux : un modèle 72B qui tient tout juste peut tourner à quelques jetons/s,
là où un modèle 8-14B laisse de la marge et va plusieurs fois plus vite.

Quand aucun modèle ne tient, l'outil sélectionne le plus petit du catalogue et le signale.

### 5. Charge serveur en direct (optionnel, `--live`)

Les quatre facteurs ci-dessus décrivent la capacité *théorique* de la machine. Ajouter
`--live` (`recommend`/`report` ; `live: true` sur `POST /api/recommend`) pèse aussi ce qui
s'y passe *en ce moment* : RAM libre actuelle, usage CPU/GPU/disque et le nombre de moteurs
déjà lancés (modèles Ollama, serveurs vLLM). Une machine chargée obtient un budget plus
réaliste qu'une machine identique mais inactive. Désactivé par défaut : cela ajoute une
sonde en direct (~0,1-0,5 s : `nvidia-smi`/`ioreg`, un ping Ollama local, un échantillon
`psutil`) et rend la recommandation dépendante de cet instant précis plutôt que d'être une
fonction déterministe du seul matériel, ce qui compte pour des rapports reproductibles et la CI.

## Commandes disponibles

| Commande | Description |
|----------|-------------|
| `detect` | Affiche le matériel détecté au format JSON |
| `recommend` | Classe les candidats pour ce matériel (sans téléchargement) |
| `report` | Recommande le(s) meilleur(s) moteur(s) pour une tâche (Markdown + JSON) |
| `catalog show` | Affiche le catalogue de modèles fusionné |
| `catalog update` | Rafraîchit le cache modèles depuis l'annuaire open-weight ApXML (`--limit N` pour un rafraîchissement partiel) |
| `hardware show` | Affiche la table des puces matérielles connues |
| `hardware update` | Enregistre la puce et la mémoire de cette machine dans le cache matériel |
| `pull` | Télécharge le meilleur modèle et exécute les contrôles Ralph |
| `validate` | Exécute les contrôles Ralph sur le modèle actuellement configuré |
| `env` | Affiche le bloc d'exports shell prêt pour `~/.zshrc` |
| `gui` | Lance la GUI navigateur |
| `activity` | Résume le journal local d'activité/coût (appels, coût, par utilisateur/modèle, erreurs) |
| `usages list` | Liste les profils d'usage et les familles (besoins uniquement, jamais de modèle) |
| `usages show <profil>` | Affiche les besoins d'un profil (tâche, *structured output*, planchers) |
| `usages resolve <profil>` | Résout un profil (ou `--family`) vers le modèle que best-engine choisit ici |

## Catalogue de modèles

Le catalogue de base intégré (`models.yaml`) couvre les familles Qwen 3, Qwen 2.5, Qwen 2.5-Coder et Gemma 3 (de 3B à 72B paramètres, en Q4_K_M et Q8_0), plus un petit ensemble d'*embedders* textuels (`kind: embed`) pour l'index de recherche. Le catalogue suit la taille sur disque, la RAM de pic estimée et les scores de benchmark issus de l'Open LLM Leaderboard v2, de l'OpenVLM Leaderboard, d'EvalPlus (code) et de MTEB (recherche par *embedding*). C'est l'*espace de recherche* dans lequel best-engine choisit, jamais un choix propre à un usage.

`catalog update` rafraîchit le cache depuis l'[annuaire LLM ApXML](https://apxml.com/models?modelType=open_weight) (modèles à poids ouverts avec leurs besoins VRAM par quantification, consulté régulièrement). Il récupère les fiches, les normalise en entrées de catalogue et les fusionne dans `~/.best-engine-ai-helper/catalog_cache.yaml` par identifiant (le catalogue de base intégré n'est jamais modifié). Utilisez `--limit N` pour un rafraîchissement partiel rapide. Les pages statiques d'ApXML portent des caractéristiques mais aucun score de classement numérique, donc les entrées rafraîchies gardent des benchmarks nuls (et un rang bas) jusqu'à ce qu'une source notée, comme l'Open LLM Leaderboard v2 ou l'OpenVLM Leaderboard, les remplisse.

## Table matérielle

`hardware.yaml` liste les configurations de puces GPU et Apple Silicon connues avec leur mémoire utilisable (pool physique moins la réserve OS et pilote). Il n'existe aucune API publique de caractéristiques couvrant toutes les puces, donc `hardware update` enregistre plutôt la vérité terrain pour la machine sur laquelle elle tourne : elle détecte la puce, le pool mémoire et la part utilisable par Ollama de cette machine, puis met à jour cette ligne dans `~/.best-engine-ai-helper/hardware_cache.yaml` (indexée par puce + palier mémoire).

## Intégration avec les projets en aval

Il y a deux façons de consommer le modèle sélectionné. La première quand tous les outils de
la machine doivent partager un même modèle. La seconde quand un projet a sa propre idée du
travail à faire et veut le modèle adapté à ce travail, pas un modèle générique.

### Modèle A : un seul modèle partagé pour toute la machine

Après `best-engine-ai-helper pull`, le fichier `~/.best-engine-ai-helper/env.sh` contient
les tags du modèle retenu. `pull` choisit un seul modèle qui passe les deux contrôles de
qualité et pointe les emplacements texte et vision dessus, donc les deux tags coïncident
(le tag exact dépend de votre matériel) :

```sh
export BEST_LLM_TEXT=gemma3:12b
export BEST_LLM_VISION=gemma3:12b
export BEST_LLM_BACKEND=ollama
export BEST_LLM_BASE_URL=http://localhost:11434
```

Les projets qui utilisent le modèle sélectionné sourcent ce fichier ou lisent le
`config.json` correspondant.

### Modèle B : un moteur par projet, résolu depuis un brief ajusté

Un projet connaît en général sa tâche plus précisément qu'un défaut valable pour toute la
machine et la qualité du choix dépend de la précision avec laquelle cette tâche est décrite
— c'est le texte de la tâche qui se traduit en axe de score et qui décide si un VLM est
nécessaire (voir [Comment fonctionne la sélection](#comment-fonctionne-la-sélection)). Le
projet garde donc un **brief** versionné qui décrit son travail et le résout, par machine,
en un **fichier moteur** gitignoré qui nomme le backend et le modèle à utiliser. Aucune
constante `DEFAULT_MODEL` ne vit dans le projet : le modèle se lit toujours depuis le fichier
moteur résolu.

1. **Versionner le brief** : `llm.brief.yaml` dans le dépôt, indépendant du matériel :

   ```yaml
   mode: local             # local (défaut) ou cloud
   kind: both              # llm | vlm | both
   headroom: 0.5           # fraction max de la mémoire accélérateur utilisable (plafonnée à 0,5)
   min_tps: 15             # plancher de débit confortable (jetons/s)
   structured_output: true # la tâche exige une sortie contrainte par schéma
   task: >-
     Nommer les pôles des axes ACP en JSON contraint par schéma, rédiger une courte
     analyse dans la langue de la table et vérifier l'image du graphique rendu.
   ```

   `mode: local` est le défaut. `mode: cloud` résout un fournisseur payant plus
   un repli local depuis le même brief (payant vers local en cas d'échec) ;
   voir [EXEMPLES.md → resolve](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXEMPLES.md#resolve)
   pour un brief `mode: cloud` complet. Le retry/cache/pseudonymisation
   nécessitent l'extra `[cloud]` ; les vrais classifieurs NSFW de
   `llm.chat(safety=...)` nécessitent `[filtered]` : les deux se dégradent
   proprement plutôt que d'échouer en leur absence.
2. **Le résoudre, par machine** : écrit un `llm.engine.yaml` gitignoré :

   ```sh
   best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
   ```

   Le backend est choisi selon le matériel : **vLLM quand un GPU discret (NVIDIA/AMD) est
   présent, Ollama sinon** (macOS, Linux CPU seul, iGPU Intel). Le choix est délibérément
   prudent : la marge mémoire est plafonnée à 0,5 et parmi les modèles à quelques points de
   benchmark du meilleur, il prend le plus léger et le plus rapide, pas le plus gros qui tient
   tout juste. Les choix vLLM sont dimensionnés sur les poids FP16 complets (plus lourds que
   l'estimation Ollama Q4), pour qu'un choix vLLM soit réaliste sur le vrai GPU. La sortie est
   spécifique au matériel ; ajoutez-la au `.gitignore` :

   ```yaml
   backend: ollama
   base_url: http://localhost:11434
   llm: {model: gemma3:12b, ram_gb: 9.2, est_tokens_per_s: 28.3, structured_output: true}
   vlm: {model: gemma3:12b, ram_gb: 9.2, est_tokens_per_s: 28.3, structured_output: true}
   serve: [ollama pull gemma3:12b]
   ```

3. **Le consommer, sans constante** : lisez le moteur au moment de l'appel et laissez le
   transport router vers le bon backend :

   ```python
   from best_engine_ai_helper import ensure, llm

   engine = ensure(".")            # charge llm.engine.yaml ou le résout depuis
                                   # llm.brief.yaml au premier usage
   summary = llm.chat(prompt, engine=engine, kind="llm")
   critique = llm.chat(prompt, engine=engine, kind="vlm",
                       images=[png], json_schema=SCHEMA)
   ```

   `chat` lit le backend et le modèle depuis le fichier moteur et dispatche vers Ollama
   (`/api/generate`) ou vLLM (`/v1/chat/completions`, compatible OpenAI) de façon transparente,
   avec sortie structurée contrainte par schéma des deux côtés.

**Politique de fichier manquant.** Le brief est versionné : son absence est un vrai bug et
`ensure` lève une erreur explicite avec la commande à lancer. Le fichier moteur est gitignoré
et spécifique à la machine : son absence est normale, `ensure` le résout depuis le brief au
premier usage. Le modèle reste ainsi hors de toute variable : le fichier moteur résolu est
l'unique source de vérité.

## Usages / profils de tâche

Là où un *brief* est écrit par dépôt, les huit charges de travail récurrentes de la suite
sont nommées une fois dans un **catalogue d'usages** intégré (`usages.yaml`). Chaque
**profil** (`text2sql`, `rag-answer`, `embeddings`, `text2sql-figures`, `report-bluf`,
`classification`, `pii-rgpd`, `persona`) n'énonce que ses **besoins** : type de tâche
(texte / code / vision / *embeddings*), besoin ou non de sortie structurée (*structured
output*), plancher de débit, marge mémoire, seuil de qualité indicatif et longueur de
contexte. Un profil est, au fond, un *brief* nommé : il est donc résolu par le **même moteur
à quatre critères** que n'importe quel *brief*.

Un profil **ne nomme jamais de modèle.** best-engine est le seul décideur : il lit les
besoins, sonde la machine et choisit le modèle local concret, en n'écrivant ce choix que
dans un fichier moteur généré (`llm.engine*.yaml`), **gitignoré et spécifique à la machine**
— jamais un littéral versionné. C'est tout l'intérêt de l'outil.

Les profils sont regroupés en **familles** : les usages qui peuvent partager un même modèle,
pour qu'une machine n'ait pas à en garder huit :

| Famille | Besoin | Profils |
|---------|--------|---------|
| **F1 : génération contrainte** | code + sortie structurée fiable (SQL / JSON), déterministe | `text2sql`, `text2sql-figures`, `classification`, `pii-rgpd` |
| **F2 : génération rédactionnelle** | prose fidèle FR/EN sur long contexte | `rag-answer`, `report-bluf`, `persona` |
| **F3 : *embeddings*** | vecteurs de recherche multilingues et multi-granulaires (jamais un modèle de chat) | `embeddings` |

Résoudre une famille donne **un** modèle pour le groupe ; résoudre un profil seul donne le
modèle éventuellement spécialisé pour ce travail quand le matériel le permet. Sur une machine
spacieuse best-engine peut spécialiser ; sur une machine contrainte, une famille se replie
sur un seul modèle.

Découverte et résolution via la même surface CLI / bibliothèque :

```sh
best-engine-ai-helper usages list                 # tous les profils + familles (besoins, pas de modèle)
best-engine-ai-helper usages show text2sql        # les besoins d'un profil
best-engine-ai-helper usages resolve text2sql     # -> le modèle que best-engine choisit ici
best-engine-ai-helper usages resolve --family F1 --out llm.engine.F1.yaml
```

```python
from best_engine_ai_helper import resolve_usage, resolve_family, list_usages

for u in list_usages():
    print(u["name"], u["family"], u["status"])

engine = resolve_usage("text2sql")   # best-engine choisit le modèle pour CETTE machine
family = resolve_family("F1")        # un seul modèle pour tout le groupe F1
```

best-engine écrit les modèles retenus dans le `llm.engine*.yaml` gitignoré de cette machine
(le prolongement de l'`env.sh` qu'il produit déjà) ; l'application lit ce fichier et une
nouvelle résolution re-décide si le matériel change. Ajouter un profil = quelques lignes dans
`usages.yaml` ; un *overlay* utilisateur dans `~/.best-engine-ai-helper/usages_cache.yaml`
surcharge par nom.

## Auteur

[Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

## Remerciements

Remerciements chaleureux à [Victor Favreau](https://www.linkedin.com/in/victor-favreau-41b823117/) pour nos échanges fructueux.

## Licence

[BSD-3-Clause](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LICENSE). Copyright 2026 Warith Harchaoui.
