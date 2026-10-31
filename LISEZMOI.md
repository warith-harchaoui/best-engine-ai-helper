# best-engine-ai-helper

[🇫🇷](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/README.md)

[![Licence : BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](#)

Choisit et télécharge le meilleur modèle de langage (LLM, *large language model*) ou modèle
de vision-langage (VLM, *vision-language model*) local adapté au matériel de la machine
courante.

L'outil détecte la mémoire disponible (mémoire unifiée Apple Silicon, mémoire vidéo NVIDIA ou RAM système), consulte un catalogue de modèles intégré, puis sélectionne le modèle au meilleur score qui tient dans une marge de sécurité configurable.

Après la sélection, il télécharge le modèle via Ollama puis le soumet à **deux contrôles** avant de lui faire confiance :

- sait-il repérer puis corriger un défaut connu glissé dans un court texte ? (la boucle Ralph)
- sait-il repérer un défaut visuel évident glissé dans une petite image de test ? (la boucle Ralph Eyeball)

Seul un modèle qui réussit les deux voit son fichier d'environnement écrit — le fichier que les projets en aval viennent lire pour trouver le modèle choisi.

[![logo](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/logo.png)](https://deraison.ai/ai-helpers)

## Le film

[![Le film de lancement : un nom de modèle écrit en dur n'a raison qu'une seule fois](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/film/poster.jpg)](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/film/best-engine-ai-helper.mp4)

Cinquante-deux secondes, dans `assets/film/`. Ce qu'il *affirme* vit dans
`film.yaml` plutôt que dans les images, puis c'est la seule raison pour
laquelle on peut le vérifier :

```sh
make-film verify assets/film/film.yaml --root .   # les affirmations contre le code
make-film pitch  assets/film/film.yaml --duration 52
```

Un chiffre gravé dans une image-clé n'est jamais relu : le film est donc le
pire endroit de ce dépôt où garder un fait. Douze affirmations, chacune
pointant le fichier qui en décide ; les nombres qu'aucune source ne pouvait
appuyer ont été retirés de l'écran plutôt que laissés sans contrôle. Le premier
montage disait qu'un modèle avait été *refusé* à 15,2 jetons/s contre un
plancher de 15 — dessiner l'histogramme est ce qui a montré que 15,2 le
franchit, puis le LISEZMOI avait déjà la meilleure phrase.

## La promesse

`best-engine-ai-helper` est conçu pour fonctionner entièrement hors ligne une fois les poids
téléchargés. Deux cas, en toute franchise :

1. **Garanti local.** La détection du matériel, la sélection du modèle, les contrôles de
   qualité et l'écriture du fichier d'environnement s'exécutent tous sur votre machine. Aucune
   télémétrie, aucun compte, aucune dépendance à un service en nuage.
2. **La seule réserve : le téléchargement initial.** La commande `pull` télécharge les poids
   du modèle via Ollama (un téléchargement normal depuis les serveurs Ollama). Ensuite, tout
   fonctionne hors ligne. La mise à jour du catalogue (`catalog update`) est également en ligne,
   mais optionnelle : le catalogue intégré suffit pour un usage courant. Le flux
   de couches suit la même règle : un téléchargement depuis le Hub
   HuggingFace, puis le modèle s'exécute depuis votre propre disque — dans
   votre propre processus, sans aucun serveur.

Une GUI minimale dans le navigateur (`best-engine-ai-helper gui`) couvre la moitié en
lecture seule de ce flux (les caractéristiques matérielles et la recommandation de moteur
à partir d'une tâche) sans passer par le terminal. La page est bilingue : français par
défaut, anglais via `/gui?lang=en`, avec un lien d'en-tête pour basculer. Voir
[GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md) (en anglais).

## En production

Ce paquet est à la base de la couche de sélection de modèles de la suite AI Helpers, puis la règle de la suite est que **tout membre ayant besoin d'un LLM ou d'un VLM le résout par ce paquet plutôt que de coder en dur un nom de modèle**. Trois membres publiés le font déjà — `md2star`, `standpoint`, `vocal-helper` — `md2star` servant d'implémentation de référence à recopier.

Un nom de modèle écrit en littéral dans un autre paquet est un défaut là-bas, pas un raccourci : il survit à la machine sur laquelle il a été choisi, puis rien ne redécide quand le matériel change.

Il est publié sur PyPI avec une intégration continue verte à chaque envoi (ruff, mypy, une suite de tests maintenue au-dessus de 90 % de couverture). Chaque version est un tag sémantique sur GitHub.

## Documentation

[💻 Documentation](https://deraison.ai/ai-helpers/docs/best-engine-ai-helper-doc/)

[🗺️ Paysage](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/PAYSAGE.md)

[📋 Exemples](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXEMPLES.md)

## Prérequis

- Python 3.10 ou ultérieur
- [Ollama](https://ollama.com) (nécessaire uniquement pour `pull`, `validate` et `env` ; pas
  requis pour `detect`, `recommend` ou `report`)
- Tout le reste s'installe automatiquement : os-helper (détection matérielle),
  PyYAML, click, requests, langdetect puis les surfaces FastAPI/MCP (`fastapi`,
  `uvicorn`, `fastapi-mcp`). La CLI, la GUI, l'API HTTP puis le serveur MCP
  font tous partie de l'installation par défaut. **Quelques mégaoctets, et
  quelques secondes.**
- **Exécuter un modèle s'active ; en choisir un, non.** Le moteur d'apprentissage profond — torch, transformers, accelerate, safetensors, puis diffusers pour les images — vit derrière `[lightweight]` puis `[imagine]`.

  Il a été central trois jours ; c'est la mesure qui explique qu'il ne le soit plus. Cette pile pèse 196 Mo en roue processeur seul, puis des gigaoctets de charge `nvidia-*` quand pip prend la version CUDA — ce qu'il fait par défaut sous Linux.

  Qui demande quel modèle tient dans son portable ne devrait pas télécharger une pile d'apprentissage profond pour l'apprendre.

  Rien au-dessus de cette ligne n'en a besoin. Les catalogues, le score, la
  sonde matérielle puis l'arithmétique d'empreinte et de durée derrière `rank`,
  `imagine_rank` et `imagine_pick` sont du Python ordinaire sur une table, et
  répondent sur un interpréteur qui n'a jamais entendu parler de torch.
  `detect`, `recommend` puis `report` sont aussi rapides qu'avant, et
  l'installation l'est devenue aussi.
- Optionnel, deux extras supplémentaires :
  - `[cloud]` pour le mode fournisseur cloud : retry, cache, pseudonymisation, repli sur le trousseau OS pour les clés API ;
  - `[filtered]` pour de vrais classifieurs NSFW : un modèle DistilBERT pour le texte, puis le détecteur d'image basé sur CLIP de LAION — `transformers` pour l'encodeur CLIP, un modèle `onnxruntime` embarqué pour la tête de classification.

  Les deux se dégradent proprement : sans eux, une heuristique par mots-clés prend le relais. Voir [Où tourne le modèle](#où-tourne-le-modèle) plus bas, puis [la section « modèle payant » d'EXEMPLES.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXEMPLES.md#4-un-modèle-payant-seulement-si-vous-donnez-une-clé) pour le déroulé complet.

## Comment ça marche

![Comment best-engine-ai-helper fonctionne : cette machine en entrée, le plus gros modèle qui tienne vraiment en sortie](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/comment-ca-marche.png)

## Installation

Python 3.10+. Le code de ce paquet est en Python pur, son installation par
défaut aussi : **quelques mégaoctets**. Le moteur de lecture en flux amène
torch avec lui, mais il vit derrière `[lightweight]`, donc ce téléchargement
d'environ 2 Go ne se paie que si vous le demandez. L'autre élément spécifique
à la plateforme est
le runtime **Ollama** optionnel (nécessaire uniquement pour `pull` /
`validate` / `env`, pas pour `detect`, `recommend`, `report`, la GUI ni la
surface MCP). Choisissez votre OS ci-dessous.

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

`best-engine-ai-helper` est la seule ligne de commande livrée par ce
paquet : une surface, construite avec click, qui est une dépendance de base
et non un extra optionnel. Les versions antérieures à la 1.9.0
installaient aussi un second point d'entrée suffixé qui la doublait commande
par commande. Il n'y a plus qu'un seul nom : celui-ci.

## Prise en main rapide

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

# Rien de bon ne tient ? Voir ce que cette machine pourrait exécuter en lisant
# les couches en flux depuis le disque, puis ce que le meilleur modèle coûterait
# en secondes par jeton
best-engine-ai-helper lightweight compare --tokens 300

# Quel modèle texte-vers-image tourne ici, puis combien de temps prend une image
best-engine-ai-helper imagine plan

# Tout servir comme un point d'entrée compatible OpenAI : n'importe quel SDK
# OpenAI, aucun changement de code, puis `model="best"` au lieu d'un nom de
# modèle qu'il aurait fallu choisir
best-engine-ai-helper serve
```

Les mêmes points d'accès `/api/system`, `/api/recommend` et `/api/activity`
sont aussi accessibles comme outils MCP pour tout hôte agentique compatible :

```sh
best-engine-ai-helper-mcp        # -> http://127.0.0.1:8000 (MCP sur /mcp)
```

Un hôte agentique lit une seule phrase avant de décider s'il charge ces outils,
donc cette phrase dit les deux moitiés : la détection du matériel puis le
meilleur moteur local, **puis** le meilleur modèle payant pour la même tâche
ainsi que les fournisseurs dont la clé est utilisable. Tout cela tourne ici
puis **ne fait aucun appel de modèle ni aucun appel fournisseur** — c'est
précisément pourquoi les routes d'inférence `/v1` sont exclues de la liste
d'outils au lieu d'y être publiées.

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

Chaque appel `llm.chat()` peut être enregistré dans un journal SQLite local, en ajout seul (`~/.best-engine-ai-helper/usage.db`). Cela vaut depuis les contrôles `pull`/`validate` de cet outil comme depuis tout projet en aval qui importe `best_engine_ai_helper.llm`.

Ce qui est consigné : qui a appelé (variable d'environnement `BEST_ENGINE_USER`, sinon le nom de connexion du système), quel modèle puis quel backend, la latence, le succès ou l'échec, enfin un coût estimé pour les backends payants — toujours `0,0` pour Ollama puis vLLM en local.

C'est pensé pour le cas « une entreprise, plusieurs utilisateurs sur une machine partagée » : répondre à « qui appelle quoi, combien de fois, à quel coût » sans pile de télémétrie séparée. Local uniquement : aucun appel réseau, aucun service tiers.

```sh
best-engine-ai-helper activity              # tableau
best-engine-ai-helper activity --format json
best-engine-ai-helper activity --what-if    # + ce que les appels gratuits auraient coûté
```

**`--what-if` : une facture évitée, pas une économie.** Les calculateurs de seuil de rentabilité local-contre-cloud posent tous la même question, puis doivent tous deviner la même entrée : vous saisissez un volume mensuel de jetons avant que la charge n'existe, si bien que la durée d'amortissement hérite de la devinette.

Ce journal tient déjà la charge, mesurée. `--what-if` la croise avec la table de prix contre laquelle le journal facture les appels payants, puis affiche ce que les **appels gratuits déjà faits** auraient coûté au tarif public de chaque modèle payant, du moins cher au plus cher.

C'est rapporté comme une facture évitée, jamais comme une économie : l'électricité, le disque puis le temps d'un modèle plus lent sont des coûts réels, dont aucun n'est mesuré ici. Les comptes de jetons sont approximatifs aussi — un backend local ne rend aucun bloc `usage`, donc les caractères passent par la même règle de ~4 caractères par jeton qu'un appel payant non rapporté.

Le CLI, la GUI et le serveur MCP activent l'enregistrement par défaut ;
désactivable avec `BEST_ENGINE_NO_LEDGER=1`. La section **Activité** de la GUI
et `GET /api/activity` lisent le même journal. Voir
`best_engine_ai_helper.observe` pour l'API bibliothèque (`enable()`,
`as_user(nom)`, `Ledger.summary()`, `Ledger.counterfactual()`).

## Comment fonctionne la sélection

La sélection pèse quatre facteurs, tous rendus explicites dans la sortie de `report` pour
que la recommandation soit reproductible et discutable. (Un moteur est jugé sur
d'autres facteurs, parce qu'une autre ressource le borne : voir [le flux de
couches](#trop-gros-pour-tenir-en-mémoire-exécutable-quand-même--le-flux-de-couches)
plus bas.)

L'ensemble, avant le détail :

![Comment la sélection fonctionne : deux filtres, puis deux classements, contre un budget mesuré](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/pipeline-de-selection.png)

Deux portes rejettent, deux classements ordonnent, puis la seule chose
que la machine apporte est un nombre : le budget sous lequel le `ram_gb`
d'un candidat doit atterrir.

### 1. Capacité de sortie structurée

La suite AI-Helpers fait passer chaque tâche par un schéma JSON (analyse d'intention,
propositions d'édition, critique visuelle). Certains modèles open-weight n'honorent pas la
sortie structurée contrainte par grammaire d'Ollama et renvoient une réponse vide (la
famille Qwen3-VL, vérifié sur `qwen3-vl:8b`). Un modèle marqué `structured_output: false`
dans le catalogue n'est jamais choisi automatiquement, quel que soit son score brut ; il
reste plus bas dans le classement pour qu'une tâche sans schéma puisse le retrouver. Les
entrées sans ce marqueur sont supposées capables.

### 2. Adéquation mémoire

La mémoire disponible vient de la première sonde qui réussit : mémoire unifiée Apple Silicon (`system_profiler`), mémoire vidéo NVIDIA (`nvidia-smi`), mémoire vidéo AMD (`rocm-smi`), sinon la moitié de la RAM système comme estimation conservative sur CPU.

Le budget utilisable n'est pas tout le pool. Sur Apple Silicon, Metal plafonne l'allocation GPU à environ 66 % de la mémoire unifiée jusqu'à 36 Go, environ 75 % au-delà (`recommendedMaxWorkingSetSize`). Une marge de sécurité `headroom` s'applique par-dessus (par défaut 0,5, qui est aussi le plafond dur : une valeur plus grande y est ramenée).

Un modèle tient quand son `ram_gb` — pic d'inférence estimé — reste au plus égal à ce budget.

Sur la machine où ceci s'écrit, cette arithmétique donne ceci :

![Ce que 96 Go de mémoire unifiée valent réellement pour un modèle : le pool, moins les 24 Go que Metal ne confiera pas au GPU, moins 36 Go de marge pour le système puis pour un cache KV qui grandit, laissant un budget de 36 Go](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/budget-memoire.png)

96 Go sur la boîte, 36 Go pour un modèle. L'écart n'est pas du pessimisme :
une moitié est une limite de pilote qui ne se discute pas, l'autre est une
marge qui se discute (`--headroom`, jusqu'au plafond de 0,5 où elle est
ramenée).

### 3. Adéquation à la tâche

Une tâche, même une phrase vague comme « fiches produit et contrôle qualité des photos »,
se traduit en un axe de benchmark (`generalist`, `code`, `math`, `ocr`, `vision`) et en
types de modèles nécessaires (du texte implique un LLM, tout visuel implique un VLM). Parmi
les modèles qui tiennent, le meilleur score sur cet axe l'emporte.

### 4. Débit

La génération est bornée par la bande passante mémoire : chaque jeton lit une fois le modèle actif en mémoire, donc le plafond est `bande passante ÷ taille`.

Ce plafond est réduit à environ 65 % pour tenir compte de la mémoire de travail que le modèle garde en cours de génération — le *cache KV*, la trace de tout ce qu'il a déjà lu, pour ne pas le relire à chaque nouveau mot — puis des autres surcoûts.

`report` estime les jetons/s par candidat, puis propose une alternative plus légère avec plus rapide quand elle est presque aussi forte. Plus gros n'est pas toujours mieux : un modèle 72B qui tient tout juste peut tourner à quelques jetons/s, là où un 8-14B laisse de la marge puis va plusieurs fois plus vite.

Quand aucun modèle ne tient, l'outil sélectionne le plus petit du catalogue puis
le signale — puis, sur une machine qui a le disque pour cela, propose d'exécuter
un *bon* modèle à la place en lisant ses couches en flux (voir [plus
bas](#trop-gros-pour-tenir-en-mémoire-exécutable-quand-même--le-flux-de-couches)).

### 5. Charge serveur en direct (optionnel, `--live`)

Les quatre facteurs ci-dessus décrivent la capacité *théorique* de la machine. Ajouter `--live` (`recommend`/`report` ; `live: true` sur `POST /api/recommend`) pèse aussi ce qui s'y passe *en ce moment* : RAM libre actuelle, usage CPU/GPU/disque, nombre de moteurs déjà lancés (modèles Ollama, serveurs vLLM).

Une machine chargée obtient alors un budget plus réaliste qu'une machine identique mais inactive.

C'est désactivé par défaut pour deux raisons. Cela ajoute une sonde en direct (~0,1-0,5 s : `nvidia-smi`/`ioreg`, un ping Ollama local, un échantillon `psutil`). Puis cela rend la recommandation dépendante de cet instant précis plutôt que fonction déterministe du seul matériel — ce qui compte pour des rapports reproductibles comme pour la CI.

**Sources.** Le plafond de l'ensemble de travail Metal d'Apple (documentation
développeur Apple / apple-specs) ; la décomposition de la mémoire d'inférence
poids + KV (15-20 %) + surcoûts (5-10 %) (guides de dimensionnement des LLM
locaux) ; le décodage borné par la bande passante
`jetons/s ≈ bande passante ÷ octets actifs × 0,5-0,8` (mesures communautaires
llama.cpp / MLX). Les rapports exacts vivent en constantes documentées dans
`score.py`.

### Le débit mesuré, puis pourquoi l'estimation demandait une correction

![La boucle de mesure : prédire, choisir, éprouver, puis réinjecter la mesure dans la prédiction suivante](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/boucle-de-mesure.png)

Tout ce qui précède est une **estimation**. Pour un outil dont l'argument est
qu'il faut mesurer plutôt que supposer, c'était le seul endroit où il supposait
— alors `pull` puis `validate` le mesurent désormais.

La mesure ne coûte rien de plus. Les deux commandes tirent déjà un candidat
puis le soumettent à deux portes Ralph : les jetons sont donc déjà générés, il
ne manquait qu'un chronomètre. Le chiffre atterrit dans
`~/.best-engine-ai-helper/measurements.yaml`, indexé par modèle **et** par
machine, puisque les jetons par seconde sont une propriété des deux.

Le chronométrage s'appuie sur l'`eval_duration` d'Ollama — la phase de décodage
telle que le démon la mesure — plutôt que sur le temps mural autour de l'appel,
qui contient aussi le traitement du prompt, HTTP puis l'attente en file. Chaque
mesure retient de quelle horloge elle vient et seule celle du démon peut
disqualifier un modèle : le temps mural sous-estime la vitesse de décodage, et
sous-estimer est précisément ce qui rejetterait un modèle qui tourne très bien.

Remesurer le même modèle conserve l'échantillon **le plus rapide** plutôt que le plus récent, ce qui est une exigence de correction, non de l'optimisme. La grandeur que l'on calibre est un **plafond** de bande passante mémoire, puis une machine occupée ne peut que faire paraître une observation plus lente que le matériel ne l'est réellement.

La leçon vient du comportement lui-même. `gemma3:12b` a mesuré 15,2 jetons/s sur une machine au repos, puis 8,7 jetons/s avec trois suites de tests en cours — et l'échantillon sous contention aurait donné à lui seul une correction de 0,31 contre 0,54 pour la machine au repos, faussant toutes les estimations de la machine.

Le champ `samples` indique sur combien d'observations repose le chiffre retenu.

Trois conséquences, dont la troisième est la plus intéressante :

1. **Une mesure l'emporte sur une estimation** partout où les deux existent.
   `recommend` la marque d'une `*`.
2. **`min_tps` est devenu une vraie contrainte.** Chaque brief d'usage portait
   déjà un plancher de débit, qui ne faisait que classer. Un modèle *mesuré*
   sous le plancher est maintenant écarté de la sélection automatique, exactement
   comme un modèle qui ne tient pas en mémoire. Un modèle simplement *estimé*
   sous le plancher est signalé puis laissé en place : une machine qui n'a jamais
   lancé `pull` se comporte donc comme avant.
3. **Mesurer un modèle améliore l'estimation de tous les autres.** Le rapport
   entre mesure et estimation est une propriété de la machine bien plus que du
   modèle, donc il se transfère. Sur l'Apple M2 Max qui a servi au développement,
   `gemma3:12b` décode à **15,2 jetons/s** là où le modèle de bande passante
   prédisait **28,3**. Ce rapport s'applique ensuite à chaque estimation sur
   cette machine, y compris pour des modèles jamais tirés.

   Cette affirmation est **éprouvée** plutôt que posée : `scripts/validate_calibration.py` calibre sur un modèle, prédit un autre, puis dit si le résultat bat l'estimation brute. C'est le cas dans toutes les directions essayées, l'erreur tombant de **64-118 % à 17-25 %**.

**Les deux moitiés méritent d'être dites : la correction est grande, puis elle n'est pas de la précision.** Les rapports s'étalent d'environ **0,46 à 0,61** selon le modèle, puis d'une exécution à l'autre du même modèle — ce qui explique pourquoi le facteur est une **médiane** sur plusieurs mesures plutôt qu'une seule, puis pourquoi une vraie mesure l'emporte toujours sur une estimation corrigée quand elle existe.

La calibration fait passer une estimation de « fausse d'un facteur deux » à « fausse d'un cinquième ». Elle ne la rend pas juste.

Le point 3 explique aussi pourquoi le plancher de confort comptait plus qu'il
n'y paraissait : `COMFORT_TPS` vaut 15 jetons/s, donc une estimation non corrigée
de 28,3 le franchit sans hésiter alors que la mesure réelle de 15,2 l'effleure.
La correction fait toute la différence entre une recommandation qui *semble*
confortable puis une qui l'est.

## Trop gros pour tenir en mémoire, exécutable quand même : le flux de couches

Tout ce qui précède répond à une question : **quel modèle tient ?** Cette
section traite de la question suivante, celle qui vient quand la réponse
honnête est *aucun des bons*.

Un transformeur n'a jamais besoin de toutes ses couches en mémoire à la fois. Le décodage lit la couche 1, puis la couche 2, puis la couche 3 : seule la couche en cours de calcul doit être résidente.

En gardant une tranche de couche en mémoire puis en lisant les autres depuis le disque, la mémoire qu'exige un modèle cesse d'être proportionnelle à son nombre de paramètres. Elle devient proportionnelle à sa **plus large couche**.

Un modèle de 70 milliards de paramètres passe ainsi de 141 Go à environ **4 Go résidents**.

Le moteur qui fait cela est **celui de ce paquet**
(`best_engine_ai_helper.streaming`), à un extra de distance.

```sh
pip install 'best-engine-ai-helper[lightweight]'    # le moteur de flux
pip install 'best-engine-ai-helper[generate]'       # flux + images
```

Décider *si* un modèle peut être diffusé, puis à quelle vitesse, n'en demande
rien : `lightweight plan` puis `lightweight compare` répondent sur une
installation de base, parce que l'arithmétique appartient au paquet et que le
moteur ne sert qu'au moment d'exécuter quelque chose.

C'était `airllm`. Cette dépendance est partie, pour des raisons mesurées
plutôt que supposées :

- **Elle ne marchait pas du tout sur Apple Silicon.** Sa fabrique de modèles
  saute la répartition par architecture sur macOS puis rend un transformeur
  Llama écrit à la main en MLX, quoi qu'on lui demande : Qwen (biais
  d'attention), Llama 3.2 (embeddings liés, donc pas de tenseur `lm_head`)
  puis les vieux exports (`rotary_emb.inv_freq` persisté) échouaient chacun
  différemment.
- **Elle écrivait une seconde copie du checkpoint sur le disque**, une couche
  par fichier, avant de rien lancer : 294 Go libres pour diffuser un 70B qui
  en pèse 140. C'est cela, pas la mémoire, qui faisait refuser la plupart des
  modèles sur un portable.

Celui-ci lit un tenseur à la fois directement dans les safetensors du
checkpoint — mémoire-mappés, avec leur propre index — donc **aucun espace de
travail n'est nécessaire**. `transformers` garde la passe avant, donc
l'architecture est celle que `transformers` connaît. Apple Silicon, c'est
torch sur Metal (MPS), pas un second cadriciel.

C'est ce qu'achète `[lightweight]` (torch, transformers, accelerate,
safetensors). Cela se paie une fois, à l'installation, puis seulement par qui l'a
demandé : les imports sont paresseux par-dessus, donc rien de cette pile n'est
chargé avant que vous ne diffusiez réellement un modèle, puis `detect` /
`recommend` / `report` restent
instantanés.

Comment une passe avant diffusée se déroule réellement :

![Comment tourne une passe avant en flux : une seule couche de décodeur résidente](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/passe-avant-en-flux.png)

Ce qui doit être résident, c'est la plus large couche, pas le checkpoint. Si
un interpréteur n'arrive malgré tout pas à importer la pile — conteneur
allégé, roue mal construite — chaque surface le dit puis pointe vers une
réinstallation, parce qu'à ce stade l'installation est incomplète plutôt que
non activée.

### Ce que ça coûte : des secondes par jeton, pas des jetons par seconde

Le marché est réel puis considérable. Sous tous les autres moteurs, la
génération est bornée par la **bande passante mémoire**. Sous le flux de
couches, elle est bornée par le **disque**, puis par une borne bien plus dure :
les poids ne restent nulle part, donc chaque jeton coûte une passe complète sur
le checkpoint. Sur un disque NVMe à 4 Go/s, un modèle de 70 milliards de
paramètres en bf16 décode à environ **0,024 jeton/s, soit une quarantaine de
secondes par jeton**.

Cela fait du flux de couches un outil de traitement par lots : une question
difficile, une évaluation nocturne, une référence de qualité pour juger le petit
modèle que vous utilisez tous les jours. Pas une fenêtre de discussion. Le
paquet le dit sur chaque surface, en secondes par jeton plutôt qu'en jetons par
seconde, parce que « 0,024 » se lit comme une erreur d'arrondi alors que
« 41 s/jeton » se lit pour ce que c'est.

### L'unité est la passe avant, ce qui a trois conséquences utiles

Une passe avant en flux parcourt les couches dans l'ordre, lit chaque tranche,
la calcule sur **tous les jetons de la passe** puis la libère. Une passe coûte
donc ce que coûte une lecture du checkpoint, **indépendamment du nombre de
jetons qui l'ont traversée**. Trois choses en découlent, dont deux sont des
leviers que vous pouvez actionner :

**1. Un jeton produit coûte une passe.** Le décodage est autorégressif : le
jeton N+1 exige son propre parcours de toutes les couches. C'est de là que vient
le chiffre en secondes par jeton, puis c'est pourquoi une longue *réponse* coûte
cher.

**2. Le prompt est quasi gratuit.** Un prompt de 2000 jetons est traité dans la même passe unique qu'un prompt de 10 jetons. Aucun autre moteur n'offre cette propriété : sous Ollama comme sous vLLM, un long prompt est du vrai travail de préremplissage.

Le flux de couches est donc comparativement bon pour « long document en entrée, verdict court en sortie » : classification, extraction, jugement, une réponse d'une ligne sur un long contexte.

Au-delà de quelques milliers de jetons, le calcul par couche commence à compter, puis l'estimation le signale au lieu de faire comme si de rien n'était.

**3. Un lot de B prompts coûte une passe, pas B.** B questions indépendantes
traitées ensemble vont B fois plus vite par réponse. La compression apporte
environ ×3 ; un lot de 8 apporte ×8. Pour un vrai travail par lots, le lot est
de loin le plus gros levier, son seul coût étant un cache KV par séquence — que
l'estimation d'empreinte vous facture, pour qu'un travail par lots ne puisse pas
se planifier lui-même jusqu'au manque de mémoire.

« À quelle vitesse ? » a donc trois réponses, puis citer la mauvaise est la
façon dont un travail par lots se fait planifier comme un travail interactif.
Les trois sont rapportées :

| Chiffre | Ce qu'il signifie |
|---|---|
| `decode_tps` | Débit en régime, un jeton par passe. Le chiffre d'affiche, le plus pessimiste aussi. |
| `time_to_first_token_s` | Une passe, prompt compris — le *même* temps que n'importe quel autre jeton, ce qui est inhabituel. |
| `effective_tps` | Jetons livrés par seconde d'horloge, lot compris. Celui qui décide si un travail finit dans la nuit. |

### Ce que ça coûte en mémoire, puis où est la vraie contrainte

La mémoire résidente, c'est une tranche, plus la seule chose que le flux de
couches ne réduit **pas** :

```
résident ≈ (checkpoint ÷ couches) × 1,25 × tranches_résidentes
           + cache KV de toutes les couches
           + activations et tampons du moteur
```

- `checkpoint ÷ couches` est la tranche moyenne. La **plus grosse** tranche est
  la matrice d'embedding des jetons plutôt qu'une couche de décodeur — un
  vocabulaire moderne de 128 000 à 152 000 entrées le veut ainsi — d'où le 1,25.
- `couches_résidentes` vaut 2 avec le préchargement (la couche
  suivante est lue pendant que la courante calcule, d'où son gain d'environ
  10 %) puis 1 sans. Couper le préchargement est le seul bouton qui fait tenir un
  70B sur une carte de 4 Go, puis ce paquet l'essaie automatiquement avant de
  rejeter un candidat pour cause de mémoire.
- Le **cache KV n'est pas diffusé** : le décodage autorégressif ne peut pas
  recalculer les clés puis les valeurs antérieures, donc la tranche de chaque
  couche reste résidente pendant toute la génération. Il croît avec le contexte
  *et* avec la profondeur, puis sur un modèle profond c'est le deuxième terme le
  plus lourd. C'est pourquoi une longueur de contexte vous fait gagner ou perdre
  un modèle ici.

Chiffré, sur un disque NVMe à 4 Go/s avec un contexte de 4k :

| Modèle | Checkpoint (= disque libre nécessaire) | Couches | Résident (préchargé / série) | s/jeton |
|---|---|---|---|---|
| Llama-3.3-70B | 140 Go | 80 | 6,1 Go / 3,9 Go | 41 s |
| Qwen2.5-VL-72B | 146 Go | 80 | 6,3 Go / 4,0 Go | 43 s |
| Mixtral-8x22B (141B, MoE) | 282 Go | 56 | 14,0 Go / 7,7 Go | 83 s |
| Qwen3-235B-A22B (MoE) | 470 Go | 94 | 14,5 Go / 8,2 Go | 138 s |
| DeepSeek-V3 (671B, fp8, MoE) | 671 Go | 61 | 29,0 Go / 15,2 Go | 197 s |
| Llama-3.1-405B | 810 Go | 126 | 18,5 Go / 10,5 Go | 238 s |

C'est la profondeur qui rend la dernière ligne possible : 405 milliards de
paramètres sur 126 couches donnent une couche *plus légère* que 141 milliards
sur 56. Un mélange d'experts (MoE) brise la relation habituelle entre taille et
profondeur — DeepSeek-V3 fait 671 milliards sur 61 couches là où la tendance
dense en prédirait le double — donc une entrée MoE qui ne déclare pas ses
`layers` est **refusée** plutôt que devinée : une devinette s'y trompe d'un
facteur deux, dans le sens qui promet trop.

Lisez la deuxième colonne en premier. **C'est l'espace disque, pas la mémoire, qui refuse d'ordinaire un modèle** — mais seulement à la taille du checkpoint lui-même.

Les couches sont lues dans les safetensors d'origine, mémoire-mappés puis indexés tenseur par tenseur : rien n'est recopié, donc il n'y a aucun espace de travail à trouver. Un modèle de 405 milliards de paramètres, c'est 810 Go de téléchargement, puis il est prêt.

Le moteur précédent écrivait une seconde copie par couche à côté de la première. C'est pourquoi cette colonne affichait 1701 Go, puis pourquoi presque chaque ligne de `lightweight plan` disait `runs: NO`.

La mémoire est la moitié facile du problème.

Ces chiffres ont été vérifiés contre ceux que publie airllm, puis la vérification mérite d'être énoncée précisément : le « 70B sur un GPU de 4 Go » de l'affiche est vrai à une longueur de contexte que personne ne mentionne.

Le même modèle fait 3,0 Go en série à 1k de contexte — la démo — 3,9 Go en série à 4k, puis 6,1 Go à 4k avec le préchargement.

Les poids sont identiques dans les trois cas. Ce qui bouge, c'est le cache qui n'est pas diffusé.

### Modèle natif ou modèle en flux ? `lightweight compare` répond en un écran

C'est la décision que le flux de couches impose vraiment, puis aucun des deux
classements n'y répond seul. Une machine qui exécute confortablement un modèle
de 14 milliards de paramètres peut aussi en diffuser un de 70 : les deux
diffèrent de quelques points de référence dans un sens puis de trois ordres de
grandeur de latence dans l'autre.

Une colonne en jetons par seconde ne peut pas trancher — 26 puis 0,024 ne se
situent pas sur une échelle dont quiconque raisonne. Des secondes pour la même
réponse, oui :

```sh
best-engine-ai-helper lightweight compare --tokens 300
```

```
=== LLM: ollama vs lightweight, for a 300-token answer ===
  budgets: 11.04 GB resident (ollama) · 22.08 GB per layer (lightweight) · disk 4.0 GB/s (declared)
model                       backend  score  resident  tok/s  answer  runs
--------------------------  -------  -----  --------  -----  ------  ----
qwen3:72b-q8_0              ollama   89     78.0      8.4    36 s    NO
qwen3:72b-q4_k_m            ollama   87     48.0      13.7   22 s    NO
qwen3:14b                   ollama   78     10.5      62.4   5 s     yes
gemma3:12b                  ollama   77     9.2       71.2   4 s     yes
Qwen/Qwen3-72B-Instruct     lightweight   89     6.2       0.024  3.5 h   yes
Qwen/Qwen3-VL-72B-Instruct  lightweight   88     6.2       0.024  3.5 h   yes

  Streaming buys 11 benchmark points (89 vs 78) for 2647x the wait: 3.5 h
  instead of 5 s for a 300-token answer.
```

Lisez la colonne `runs` : le modèle de 72 milliards de paramètres qui marque 89
est bien présent dans le catalogue Ollama puis **il ne tient pas** sur cette
carte de 24 Go. Le flux de couches est ce qui met la même classe de modèle à
portée, au prix affiché dans la colonne `answer`.

Chaque côté est classé selon les règles de son propre moteur, puis le côté en flux inverse la règle habituelle.

Partout ailleurs, ce paquet choisit le modèle le **plus léger** à quelques points de référence du meilleur, parce qu'un gigaoctet de résidence se paie à chaque exécution puis entre en concurrence avec votre propre charge.

Le flux de couches brise cette prémisse : la résidence est une tranche quelle que soit la taille du modèle, donc la légèreté n'achète rien — puis la règle anti-gourmandise atterrit sur un modèle de 8 milliards de paramètres, le seul résultat absurde, puisqu'un 8B tourne nativement cent fois plus vite. Le choix en flux est donc le modèle le **plus capable** qui s'exécute, au score de référence, la taille ne tranchant que là où aucun score ne le fait.

Pas simplement le plus gros, puis la différence n'est pas académique : la
première règle ici *était* « le plus gros qui s'exécute », puis ce tableau même a
montré ce qu'elle coûte — un mélange d'experts de 141 milliards marquant 84
battait un modèle dense de 72 milliards marquant 87 sur le seul nombre de
paramètres, en étant deux fois plus lent par jeton. Plus gros, plus lent **puis**
plus faible est dominé sur tous les axes qui intéressent l'appelant.

La comparaison porte un biais délibéré, énoncé pour que vous puissiez en tenir
compte : le temps natif ne compte que le décodage puis ignore le traitement du
prompt, alors que le temps en flux est complet. Cela flatte le côté natif — la
bonne direction pour une comparaison honnête dont la conclusion est le plus
souvent « restez en natif » ; ce moteur doit être prêt à le dire de lui-même.

### Quand ça s'active

Jamais par défaut. Deux déclencheurs, rien d'autre :

![Quand le flux de couches s'active, puis pourquoi jamais par défaut](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/declencheurs-du-flux.png)

**Automatique** — le moteur conventionnel n'a rien résolu qui *tienne* sur cette machine pour un genre que votre cahier des charges demande. Le flux de couches est alors la différence entre un modèle puis aucun, donc `resolve` le propose avec son coût énoncé.

Le secours est **par genre**. Si votre LLM tient puis qu'aucun VLM ne tient, seul le VLM bascule, puis le fichier moteur est honnêtement mixte : Ollama pour un genre, `lightweight` pour l'autre (`model_for()` lit d'abord le moteur du genre).

Le descripteur enregistre la décision puis sa raison sous `lightweight:`, *y compris quand la réponse est non* — pour qu'une machine qui ne peut pas diffuser dise pourquoi au lieu de rester muette.

**Manuelle** — vous le demandez :

```sh
best-engine-ai-helper resolve --brief llm.brief.yaml --backend lightweight
```

ou dans le cahier des charges versionné :

```yaml
kind: llm
task: juger la qualité de descriptions produit générées
lightweight: always          # auto (défaut) | always | never
```

ou dans l'environnement, qui ne surclasse que les valeurs par défaut :

```sh
export BEST_ENGINE_LIGHTWEIGHT=always   # ou never, pour couper toute la voie
```

`never` gagne sur tout, y compris sur le déclencheur automatique. Qui veut un
modèle de 235 milliards de paramètres sur un portable pendant la nuit fait un
choix légitime qu'aucune règle automatique ne devrait avoir à deviner, puis qui
ne veut jamais voir son disque malmené mérite un seul interrupteur qui le dise
vraiment.

### Les commandes

```sh
# Cette machine peut-elle diffuser, devrait-elle, puis qu'est-ce qui bloque ?
best-engine-ai-helper lightweight status
best-engine-ai-helper lightweight status --measure      # mesurer le disque au lieu de le supposer

# Que pourrait-elle diffuser, le plus capable d'abord ?
best-engine-ai-helper lightweight plan --kind llm --context 32 --batch 8

# Natif ou en flux, même longueur de réponse, les deux prix
best-engine-ai-helper lightweight compare --tokens 300 --batch 8

# Payer le téléchargement maintenant, pas dans le premier appel
best-engine-ai-helper lightweight prepare --model meta-llama/Llama-3.3-70B-Instruct
```

`--measure` mérite d'être connu. Le disque fixe toute la vitesse de ce moteur, donc supposer sa classe (NVMe interne Apple, NVMe générique, SSD SATA, disque à plateaux) est une entrée plus faible que la mesurer.

La mesure écrit puis relit environ 256 Mo **en contournant le cache de pages** (`F_NOCACHE` sur macOS, `O_DIRECT` sur Linux). Sans cette étape, la lecture est servie depuis la RAM puis rapporte la bande passante mémoire — c'est ainsi que cette sonde a d'abord annoncé 13 Go/s sur un disque dont la fiche technique plafonne près de 7.

Sur une plateforme sans moyen de contourner le cache, elle ne renvoie rien plutôt qu'un chiffre flatteur, puis chaque surface étiquette la valeur `measured` ou `declared`.

### Les limites, énoncées franchement

- **Pas de sortie structurée.** Le moteur expose une génération brute, sans
  équivalent du `format` contraint par grammaire d'Ollama. Tout modèle en flux
  est donc `structured_output: false` — un fait sur le moteur, pas sur les poids
  — puis les tâches de la suite pilotées par schéma restent sur un modèle
  Ollama. `llm.chat` lève une erreur au lieu d'honorer un schéma de nom
  seulement.
- **Texte uniquement.** L'adaptateur renvoie un modèle de langage causal nu,
  sans le processeur d'images qu'exige un prompt de VLM. Les images lèvent une
  erreur au lieu d'être silencieusement traitées depuis le seul texte.
- **Pas de serveur.** Le moteur est une bibliothèque, donc un modèle en flux
  s'exécute *dans votre propre processus* ; le `base_url` du fichier moteur est
  vide à dessein, parce qu'inventer un port local enverrait un consommateur
  chercher un démon qui n'existera jamais. `llm.chat` garde le modèle chargé
  entre les appels — découper un checkpoint de 141 Go à chaque appel rendrait le
  transport inutilisable.
- **safetensors uniquement.** Un checkpoint publié seulement en
  `pytorch_model.bin` est refusé nommément. Le pickle ne porte aucun index par
  tenseur, donc « lire une couche » voudrait dire lire tout le fichier une fois
  par couche — la seule chose que ce moteur existe pour ne pas faire.
- **Pas de flux par expert sur un MoE.** Une couche de mélange d'experts
  épars est matérialisée entière, donc son chiffre résident est le jeu complet
  d'experts plutôt que la poignée vers laquelle un jeton route vraiment. Le
  dimensionnement facture le jeu complet, ce qui explique qu'une ligne MoE
  paraisse chère à côté d'un modèle dense de même profondeur.
- **Aucune quantisation à la volée.** Le checkpoint tourne dans le dtype où il
  est publié. Il n'y a pas de bouton `--compression`, parce que rien ici ne
  pourrait l'honorer : pour diffuser en moins de bits, pointez vers un dépôt
  déjà publié ainsi, puis le `dtype` du catalogue le tarifera. (Une version
  antérieure acceptait ce drapeau puis annonçait un gain de 3× que le moteur
  ne rendait jamais.)
- **Le processeur fonctionne, lentement.** `cuda`, `mps` puis `cpu` sont trois
  voies réelles — l'appareil est nommé explicitement plutôt que deviné. Une
  machine sans accélérateur ne se voit toujours pas *proposer* le flux
  automatiquement, parce que le débit qu'elle obtiendrait passe sous le
  plancher de lot ; elle peut le demander.
- **Le contexte vaut 4096 jetons sauf demande contraire.** Un tokeniseur laissé à son propre défaut *tronque* au-delà, donc le moteur configure toujours `max_seq_len` explicitement — réglé sur les mêmes 4k que ceux auxquels l'empreinte ci-dessus est tarifée.

  Les deux nombres sont délibérément le même : un outil qui annonce la mémoire d'un contexte de 4k puis exécute en silence un contexte de 512 mentirait dans le sens où vous perdez la fin de votre prompt.

  Montez-le avec `max_seq_len=` puis le terme de cache KV monte exactement comme la formule le dit.

### Pourquoi ce moteur est le nôtre plutôt qu'un import

Question légitime, puis la réponse a changé. La technique a été démontrée par
[airllm](https://github.com/lyogavin/airllm) (Apache-2.0), que ce paquet
importait au départ. Trois mesures l'ont fait rentrer à la maison :

1. **Ça ne marchait pas du tout sur Apple Silicon.** L'`AutoModel` d'airllm dispatche sur l'architecture partout sauf sur macOS, où il rend d'office un transformeur Llama écrit à la main en MLX, avec `bias=False` partout. Trois plantages différents en découlent :
   - Qwen porte des biais d'attention ;
   - Llama 3.2 lie ses embeddings, donc il n'y a pas de tenseur `lm_head` ;
   - les vieux exports persistent `rotary_emb.inv_freq`.

   Sur la plateforme où cette suite se développe, donc. Puis `generate()` n'arrivait de toute façon jamais jusque-là, levant `AttributeError: 'AirLLMLlamaMlx' object has no attribute 'device'` au premier appel sur tous les Mac.
2. **Il écrivait une seconde copie de chaque checkpoint sur le disque.** Des
   tranches par couche, écrites avant que rien ne tourne, donc un 70B
   réclamait ~294 Go libres au lieu de ~140. C'est ce qui faisait lire
   `runs: NO` à presque chaque ligne de `lightweight plan` sur un portable
   ordinaire : les modèles tenaient en mémoire par couche puis échouaient sur
   un espace de travail qui n'a plus lieu d'exister.
3. **Il traînait MLX, bitsandbytes puis une sous-classe par famille** — Llama,
   Qwen, DeepSeek, Mixtral, ChatGLM, Kimi — chacune réécrite à la sortie de la
   famille. Tout cela est parti avec lui.

Ce qui le remplace est plus petit, pas plus gros : construire le modèle sur l'appareil `meta`, accrocher sur chaque couche de décodeur un pré-crochet qui matérialise ses poids depuis les safetensors mémoire-mappés du checkpoint, puis un post-crochet qui libère exactement ceux-là.

**`transformers` garde la passe avant**, donc l'architecture est celle que `transformers` connaît. Puis la pile de décodeurs est *découverte* — la `ModuleList` dont la longueur vaut le nombre de couches de la config — au lieu d'être nommée dans une table par famille que quelqu'un doit tenir à jour.

Le partage du travail à l'intérieur du paquet n'a pas bougé : `streaming.py`
possède la passe avant, puis `offload.py` possède toutes les questions de
*sélection* — l'arithmétique d'empreinte, le modèle de temps borné par le
disque, la politique d'activation, la comparaison natif contre flux puis les
métadonnées de catalogue dont tout cela a besoin (`layers`, `dtype`, `moe`).
Rien d'`offload.py` n'importe torch : c'est ce qui fait que `lightweight status`
puis `lightweight compare` répondent juste, puis instantanément, même là où le
moteur lui-même refuserait de se charger.

### Depuis Python

```python
import best_engine_ai_helper as beah

hw, disk = beah.available_memory(), beah.disk_profile()

# Cette machine devrait-elle diffuser ?
decision = beah.lightweight_decide(conventional_resolved=False)
print(decision["activate"], decision["reason"], decision["blockers"])

# Que coûterait un 70B ici ?
entry = {
    "id": "llama3.3:70b",
    "size_b": 70,
    "layers": 80,
    "hf_id": "meta-llama/Llama-3.3-70B-Instruct",
}
print(beah.lightweight_footprint_gb(entry))  # 6,1 Go résidents
print(beah.lightweight_generation_time(entry, disk["read_gbs"], new_tokens=300, batch=8))

# Natif ou en flux, pour une réponse de 300 jetons ?
report = beah.lightweight_compare(
    beah.load_catalog(),
    hw=hw,
    disk=disk,
    bandwidth_gbs=beah.compute_profile()["bandwidth_gbs"],
    new_tokens=300,
)
print(report["verdict"])

# Puis l'exécuter vraiment
text = beah.lightweight_generate(
    "Juge cette description :…", model="meta-llama/Llama-3.3-70B-Instruct", max_new_tokens=64
)
```

La surface HTTP répond aux mêmes questions en un seul appel —
`GET /api/lightweight?answer_tokens=300&batch=8` renvoie la décision, le profil de
stockage, les plans classés puis la comparaison — puis elle est accessible comme
outil MCP, comme tous les autres points d'entrée.

## Commandes disponibles

| Commande | Description |
|----------|-------------|
| `detect` | Affiche le matériel détecté au format JSON |
| `recommend` | Classe les candidats pour ce matériel (sans téléchargement) |
| `report` | Recommande le(s) meilleur(s) moteur(s) pour une tâche (Markdown + JSON) |
| `resolve` | Transforme un brief d'usage commité en `llm.engine.yaml` propre à cette machine |
| `doctor` | Compare ce que le fichier moteur a résolu avec ce que le démon sait servir |
| `storage` | Planifie la capacité : ce qui tient sur le disque, puis ce qui tient en mémoire ensemble |
| `providers` | Quels fournisseurs cloud sont utilisables, puis pour les autres la variable à poser |
| `catalog show` | Affiche le catalogue de modèles fusionné |
| `catalog update` | Rafraîchit le cache modèles (`--ollama` pour des tags réellement tirables, `--arena` pour fusionner les notes LM Arena, `--cloud` pour retarifer le catalogue payant, `--cloud --arena` pour adopter en plus les modèles que les deux sources connaissent, `--limit N` pour un rafraîchissement partiel) |
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
| `lightweight status` | Cette machine peut-elle lire les couches en flux depuis le disque, devrait-elle, puis qu'est-ce qui bloque (`--measure` pour mesurer le disque) |
| `lightweight plan` | Ce qu'un modèle trop gros coûterait ici, classé : tranche résidente, secondes par jeton, disque pour la découpe |
| `lightweight compare` | Modèle natif contre modèle en flux, même longueur de réponse, les deux tarifés en secondes |
| `lightweight prepare` | Télécharger puis découper un checkpoint maintenant, plutôt que dans le premier appel |
| `imagine plan` | Quel modèle texte-vers-image cette machine peut exécuter, son empreinte puis ses secondes par image |
| `imagine generate` | Générer une image en local, vers un fichier PNG |
| `serve` | Servir l'API compatible OpenAI : pointez n'importe quel SDK OpenAI dessus puis demandez `best` |

## Catalogue de modèles

Le catalogue de base intégré (`models.yaml`) couvre les familles Qwen 3, Qwen 2.5, Qwen 2.5-Coder et Gemma 3 (de 3B à 72B paramètres, en Q4_K_M et Q8_0), plus un petit ensemble d'*embedders* textuels (`kind: embed`) pour l'index de recherche. Le catalogue suit la taille sur disque, la RAM de pic estimée et les scores de benchmark issus de l'Open LLM Leaderboard v2, de l'OpenVLM Leaderboard, d'EvalPlus (code) et de MTEB (recherche par *embedding*). C'est l'*espace de recherche* dans lequel best-engine choisit, jamais un choix propre à un usage.

`catalog update` rafraîchit le cache depuis l'[annuaire LLM ApXML](https://apxml.com/models?modelType=open_weight) : des modèles à poids ouverts avec leurs besoins VRAM par quantification, consulté régulièrement.

Il récupère les fiches, les normalise en entrées de catalogue, puis les fusionne dans `~/.best-engine-ai-helper/catalog_cache.yaml` par identifiant — le catalogue de base intégré n'est jamais modifié. `--limit N` donne un rafraîchissement partiel rapide.

Une réserve : les pages statiques d'ApXML portent des caractéristiques mais aucun score de classement numérique. Les entrées rafraîchies gardent donc des benchmarks nuls, avec un rang bas, jusqu'à ce qu'une source notée comme l'Open LLM Leaderboard v2 ou l'OpenVLM Leaderboard les remplisse.

`--ollama` élargit le catalogue depuis la [bibliothèque officielle Ollama](https://ollama.com/library) plutôt que depuis ApXML. Il existe parce que le catalogue *servable* plafonnait à vingt modèles, pour une raison qui n'a jamais été une question de notation.

ApXML peut ajouter des centaines d'entrées, mais il les nomme d'après le papier (`qwen36-35b-a3b`) : un nom de dépôt HuggingFace qu'`ollama pull` ne résout pas, donc ces entrées sont réservées à vLLM.

La bibliothèque publie au contraire les familles, leurs capacités puis les tailles livrées. Une famille plus une taille **est** un tag de tirage : `qwen3` plus `8b` donne `qwen3:8b`, exactement l'orthographe déjà utilisée par le catalogue de base. 256 familles donnent environ 420 tags, en une seule requête.

Ces entrées ne portent **aucune note de benchmark**, parce que la bibliothèque publie des tailles puis des descriptions, pas des résultats de classement. Elles se classent donc **sous** tout modèle noté, jusqu'à ce qu'une source notée les remplisse. C'est le but plutôt qu'une limite : cela élargit ce que l'outil sait dimensionner puis tirer sans changer ce qu'il recommande ; une note inventée vaudrait moins qu'une note absente — un `null` se classe bas puis reste honnête, une invention se classe mal tout en ayant l'air d'une autorité.

Les tailles viennent d'une constante **mesurée** sur les quatorze entrées Q4 du catalogue de base, pas devinée : 0,646 Go par milliard de paramètres pour un modèle texte, 0,714 pour un modèle vision, puisqu'une tour d'image est réellement plus lourde par paramètre. L'écart aux chiffres connus du catalogue reste sous les 5 %. Une famille qui n'annonce aucune taille est écartée plutôt qu'enregistrée à zéro, ce qui l'aurait fait paraître tenir sur n'importe quelle machine.

`--arena` fusionne en plus les notes de préférence conversationnelle issues des miroirs de [LM Arena](https://lmarena.ai). Deux faits mesurés méritent d'être connus avant d'y recourir.

![Chaque source Arena essayée tour à tour : le tableau officiel n'a aucune API publique, un miroir communautaire répond désormais avec 37 modèles d'un instantané vieux de 21 jours, un collecteur payant est refusé par principe, puis l'historique en vrac a 524 jours](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/obsolescence-arena.png)

**Elle note des points d'accès hébergés de pointe, puis rien d'autre.** L'Arena note ce avec quoi ses votants peuvent discuter, ce qui donne aujourd'hui des noms comme `claude-opus-5.5-max`, `gpt-6-astra-max` puis `gemini-4-argon-high`. Au relevé du 2026-10-28, cela fait **37 modèles** sur trois tableaux de vingt.

Face au catalogue *local*, c'est presque rien : **1 sur 51**, `kimi-k3` — parce que personne ne vote sur un tag Ollama à poids ouverts.

Face au catalogue *payant*, c'est l'essentiel : **18 sur 28**, dès que `catalog update --cloud` a mis des modèles actuels dans le fichier.

Cette asymétrie est la propriété qui définit l'axe, pas un défaut dedans.

Un nom de tableau porte un suffixe d'effort de raisonnement qu'un identifiant d'API ne porte jamais : `claude-opus-5.5-max` puis `claude-opus-5.5-high` sont un seul modèle facturable servi à deux efforts, facturé une fois au même tarif par jeton.

Les deux notes appartiennent donc à la même entrée de catalogue, puis celle qui est retenue est la **plus basse**. La plus haute décrit un mode qu'il faut demander, qui coûte davantage de jetons de sortie : l'attribuer à l'identifiant nu promettrait ce qu'un appel par défaut ne rend pas.

Quand le tableau note aussi le nom sans suffixe — `claude-opus-4-6` voisine avec son `-high` — c'est celui-là qui gagne d'emblée : il *est* le mode par défaut. Un *produit* de service différent, tel que `claude-3-5-sonnet-20250219-thinking-32k`, continue de n'apparier rien, exprès.

Les modèles d'embedding ne peuvent pas s'apparier par construction : personne ne discute avec un encodeur, donc aucun classement de préférences conversationnelles n'en notera jamais un. La commande imprime son propre `apparié/total` à chaque passage, vous n'avez donc jamais à croire ce paragraphe sur parole.

**C'est le scrape d'un tiers, puis les miroirs pourrissent d'une façon qui ressemble à une panne.** L'Arena ne publie aucune API. Un miroir a cessé d'être mis à jour il y a 524 jours. L'autre tourne tous les jours puis continue de produire un répertoire même les jours où son propre scrape ne rend rien — son index nomme donc un répertoire vide, puis l'adaptateur lisait celui-là, annonçait « aucune donnée utilisable », enfin s'arrêtait.

Il fait désormais deux choses à la place. Il remonte jusqu'au plus récent instantané qui *contient* des données. Puis il lit les noms des tableaux dans l'index du miroir au lieu de les deviner : deux des quatre noms devinés (`overall`, `coding`) n'ont jamais été publiés, donc l'axe code restait vide en silence face à un miroir qui le servait sous `code`.

C'est la différence entre 0 note puis 37.

Passé `MAX_SNAPSHOT_AGE_DAYS`, l'adaptateur refuse toujours puis nomme la raison, parce qu'un Elo d'une génération précédente classerait les modèles de 2025 au-dessus de ceux de 2026 — strictement pire que pas d'Elo du tout. Il n'annonce jamais un succès qui n'a rien enrichi.

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

Un projet connaît en général sa tâche plus précisément qu'un défaut valable pour toute la machine, puis la qualité du choix dépend de la précision avec laquelle cette tâche est décrite : c'est le texte de la tâche qui se traduit en axe de score, puis qui décide si un VLM est nécessaire (voir [Comment fonctionne la sélection](#comment-fonctionne-la-sélection)).

Le projet garde donc un **brief** versionné qui décrit son travail, puis le résout, par machine, en un **fichier moteur** gitignoré qui nomme le backend avec le modèle à utiliser.

Aucune constante `DEFAULT_MODEL` ne vit dans le projet : le modèle se lit toujours depuis le fichier moteur résolu.

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
   voir [EXEMPLES.md → modèle payant](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXEMPLES.md#4-un-modèle-payant-seulement-si-vous-donnez-une-clé)
   pour un brief `mode: cloud` complet. Le retry/cache/pseudonymisation
   nécessitent l'extra `[cloud]` ; les vrais classifieurs NSFW de
   `llm.chat(safety=...)` nécessitent `[filtered]` : les deux se dégradent
   proprement plutôt que d'échouer en leur absence.
2. **Le résoudre, par machine** : écrit un `llm.engine.yaml` gitignoré :

   ```sh
   best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
   ```

   Le backend est choisi par un arbre de décision à trois branches, qui reflète ce que chaque
   moteur supporte réellement bien plutôt que ce sur quoi il tourne tant bien que mal :

   - **macOS -> Ollama.** vLLM n'a pas de runtime natif macOS.
   - **CPU seul (Linux ou macOS) -> Ollama.** Le chemin CPU seul de vLLM — notamment sous
     Linux — est son propre point faible signalé ; le chemin CPU d'Ollama est le plus éprouvé.
   - **GPU discret (NVIDIA/AMD) sous Linux — le vrai cas de production -> vLLM**, notamment
     pour sa gestion de la concurrence et du batching de requêtes sous charge réelle, qu'Ollama
     n'égale pas.

   Windows retombe aussi sur Ollama (pas de wheel vLLM natif, WSL uniquement), d'où le résumé : **vLLM uniquement sous Linux avec un GPU discret, Ollama partout ailleurs.**

Le choix reste prudent par ailleurs. La marge mémoire est plafonnée à 0,5, puis parmi les modèles à quelques points de benchmark du meilleur, il prend le plus léger avec le plus rapide — pas le plus gros qui tient tout juste.

Les choix vLLM sont dimensionnés sur les poids FP16 complets, plus lourds que l'estimation Ollama Q4, pour qu'un choix vLLM soit réaliste sur le vrai GPU. La sortie est spécifique au matériel ; ajoutez-la au `.gitignore` :

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

   # charge llm.engine.yaml ou le résout depuis llm.brief.yaml au premier usage
   engine = ensure(".")
   summary = llm.chat(prompt, engine=engine, kind="llm")
   critique = llm.chat(prompt, engine=engine, kind="vlm", images=[png], json_schema=SCHEMA)
   ```

   `chat` lit le backend et le modèle depuis le fichier moteur et dispatche vers Ollama
   (`/api/generate`) ou vLLM (`/v1/chat/completions`, compatible OpenAI) de façon transparente,
   avec sortie structurée contrainte par schéma des deux côtés.

**Politique de fichier manquant.** Le brief est versionné : son absence est un vrai bug et
`ensure` lève une erreur explicite avec la commande à lancer. Le fichier moteur est gitignoré
et spécifique à la machine : son absence est normale, `ensure` le résout depuis le brief au
premier usage. Le modèle reste ainsi hors de toute variable : le fichier moteur résolu est
l'unique source de vérité.

Les consommateurs de la suite — [Standpoint](https://github.com/warith-harchaoui/standpoint),
vocal-helper puis md2star — suivent ce motif : chacun livre un `llm.brief.yaml` qui décrit
son propre travail (celui de Standpoint, par exemple, réclame du JSON contraint par schéma,
donc la garde de sortie structurée écarte des modèles de vision mieux notés mais incapables
d'honorer un schéma, puis retient le plus fort de ceux qui le peuvent) et ne lit le modèle
que depuis le fichier moteur résolu.

## Où tourne le modèle

C'est le seul paquet de la suite AI Helpers qui sache joindre un service cloud payant de
tiers : autant être exact sur le moment où il le fait. Un modèle résolu peut vivre à trois
endroits, dont seul le troisième coûte de l'argent puis quitte votre réseau :

| Où | Brief | Coût | Joint un tiers |
|---|---|---|---|
| **Cette machine** | `mode: local` — le défaut ; sinon aucun champ `mode` | rien | non |
| **Votre propre serveur** | `mode: local` plus `--endpoint` / `base_url` | votre matériel | non |
| **Un fournisseur payant** | `mode: cloud` plus un `api_key_env` dont la variable est réellement renseignée | au jeton | oui |

Chaque brief choisit un des deux modes avec `mode: local` (le défaut) ou `mode: cloud`. Les
deux se résolvent vers le même type de fichier moteur et le même point d'appel
`llm.chat(engine=..., kind=...)` en aval : seuls le transport et le coût changent.

Sur lequel des trois un brief atterrit, puis ce que ça coûte :

![Où tourne un modèle résolu, puis lequel des trois endroits coûte de l'argent](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/ou-ca-tourne.png)

### Sur cette machine (gratuit, par défaut)

`mode: local` — ou l'absence de champ `mode` — correspond à [la promesse](#la-promesse) : la
détection matérielle, la sélection du modèle et chaque garde qualité tournent sur cette
machine, contre un modèle déjà tiré via Ollama ou servi via vLLM. Chaque appel coûte **0,0 $**,
toujours (voir [Journal d'activité](#journal-dactivité)) : il n'y a aucun appel API payant à
chiffrer.

### Sur votre propre serveur (toujours sans qu'aucun tiers facture)

Le mode local ne veut pas dire *cette* machine-ci. `--endpoint URL` — ou `base_url` dans le brief — pointe le même moteur résolu vers un serveur que vous opérez : typiquement vLLM sur une machine à GPU au bout du couloir, avec `--backend vllm` pour le forcer.

La sélection reste faite pour le matériel qui servira le modèle, le journal chiffre toujours chaque appel à `0,0 $`, puis rien ne quitte une infrastructure que vous contrôlez.

C'est l'option intermédiaire, celle qu'on oublie : « pas sur mon portable » n'oblige pas à « sur le compte de quelqu'un d'autre ».

### Chez un fournisseur payant (sur demande, puis seulement si vous fournissez une clé)

Un appel payant n'arrive jamais par accident. Il exige un brief qui dit `mode: cloud` **puis** un `api_key_env` nommant une variable d'environnement réellement renseignée.

`api_key_env` porte le NOM de la variable, jamais la clé elle-même, puis la clé n'est jamais écrite dans le fichier moteur.

- **Quand le brief n'épingle aucun fournisseur**, le choix automatique ne considère que ceux dont la clé se résout *à l'instant*. Avec une clé Mistral puis aucune clé Gemini, vous obtenez Mistral — même là où Gemini marque plus haut. `best-engine-ai-helper providers` liste exactement lesquels sont utilisables, puis pourquoi les autres ne le sont pas.
- **Un fournisseur *épinglé* reste honoré sans clé**, parce qu'`api_key_env` porte un nom de variable : un descripteur s'écrit là où le secret est absent, puis s'exécute là où il est présent. Le fichier moteur consigne `api_key_present: true|false` pour distinguer les deux cas.

`mode: cloud` route plutôt vers un fournisseur payant : OpenAI, Mistral, OpenRouter, Together
ou Azure OpenAI (tous compatibles OpenAI), plus Anthropic et Gemini (formats propres à chacun),
tout en gardant le même point d'appel `llm.chat(engine=..., kind=...)` en aval. Deux façons de
choisir le modèle :

- **Le fixer** : nommer `provider` et `model` explicitement dans le brief, exactement comme
  avant.
- **Le choisir automatiquement** : omettez `model` — puis `provider`, pour chercher chez tous les fournisseurs — et best-engine choisit le meilleur modèle payant depuis un petit catalogue embarqué (`pricing.yaml`, enrichi de scores de benchmark par modèle).

  C'est la même mécanique que le mode local depuis `models.yaml`, à une différence près : la ressource budgétée est le **prix**, pas la mémoire, puisque tout modèle payant tourne sur n'importe quelle machine.

  Un curseur `quality_vs_cost` (0 à 1, défaut 0,7) oriente le choix : `1.0` choisit uniquement sur le score, `0.0` uniquement sur le prix, puis le défaut privilégie la qualité avec le prix en départage.

Azure se fixe à la main, ne se choisit jamais automatiquement, puis la raison
est structurelle plutôt qu'une préférence : c'est le seul fournisseur sans
adresse de base universelle vers laquelle router. Son point d'accès est
`https://<votre-ressource>.openai.azure.com` puis l'identifiant qu'une requête
porte est un *nom de déploiement* que vous avez choisi, pas le nom de modèle
qu'une table de prix liste — une entrée Azure choisie automatiquement se
résoudrait donc en `base_url` vide puis n'appellerait rien. Fixez `provider`,
`model` puis `base_url` et cela marche exactement comme avant.

#### Garder le catalogue payant honnête

`pricing.yaml` est tenu à la main, puis il est longtemps resté sans source d'où
se rafraîchir — il vieillissait donc en silence pendant qu'`observe.py` tarifait
chaque appel payant dessus puis que le choix automatique classait sur les mêmes
nombres. Il en a une désormais :

```sh
best-engine-ai-helper catalog update --cloud
```

La commande tire les prix catalogue puis les longueurs de contexte de
[la table publique de LiteLLM](https://github.com/BerriAI/litellm) vers
`~/.best-engine-ai-helper/pricing_cache.yaml`, superposé à la graine embarquée,
jamais modifiée. La fusion est délibérément étroite, puis c'est tout l'intérêt :

- **Prix, longueurs de contexte puis drapeaux de capacité sont rafraîchis.** À
  l'arrivée de cette commande, quatre des dix entrées de la graine étaient
  fausses : `mistral-large-latest` était tarifé quatre fois son coût réel, donc
  le classement évitait le modèle qui était justement le moins cher, pendant que
  `mistral-medium-latest` sous-facturait de presque quatre. Les deux directions
  comptent, puisque `quality_vs_cost` classe exactement sur ces nombres.
- **Les scores de benchmark ne sont jamais touchés.** Une table de prix n'a
  aucun avis sur la qualité, donc les entrées rafraîchies gardent les scores de
  la graine. Ce paquet ne mettra pas dans un fichier qui facture des gens un
  nombre que personne n'a mesuré.
- **Rien n'est supprimé automatiquement.** Les modèles dont la source n'a
  jamais entendu parler — quatre sur dix, dont les deux entrées Gemini 1.5,
  retirées par Google bien avant — sont signalés puis laissés tels quels, parce
  que l'absence d'une source est un indice fort, pas une preuve.
- **Rien n'est ajouté sur une seule source.** Un modèle payant sans score ne
  peut pas être classé, donc un modèle tarifé mais non noté est *affiché* pour
  que vous triiez plutôt que fusionné. Ce qui sort un modèle de cette liste,
  c'est une seconde source — voir ci-dessous.

Tant que vous ne l'avez pas lancée, chaque surface cloud dit que la table ne
porte aucune date. C'est exact : les nombres de la graine ont été écrits de
mémoire plutôt que vérifiés un jour donné, donc il n'y a pas d'`as_of` honnête à
poser. Un rafraîchissement écrit un vrai `fetched_at` par entrée, puis
l'avertissement cesse.

#### Comment le catalogue payant s'agrandit : deux sources, puis une entrée exige les deux

Le retarifage corrige ce que les modèles du catalogue *coûtent*. Il ne peut pas
apprendre au catalogue qu'un modèle existe, puisque le classer demande une note
de qualité puis qu'une table de prix n'en publie aucune. Le fichier pouvait donc
apprendre que `gpt-4o` avait augmenté, jamais que `gpt-6-sol` était sorti — dix
modèles de 2024, indéfiniment.

Ajoutez `--arena` : une seconde source répond à l'autre moitié.

```sh
best-engine-ai-helper catalog update --cloud --arena
```

![Comment le catalogue payant s'agrandit : une table de prix publique connaît 188 modèles de dialogue achetables sans aucune note de qualité, un miroir de classement connaît 37 noms notés sans aucun prix, puis un modèle n'est adopté que si les deux le nomment — 18 aujourd'hui, avec 164 tarifés non notés affichés pour triage puis 4 entrées du catalogue inconnues de la source de prix laissées exactement en l'état](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/deux-sources.png)

**Une entrée n'est adoptée que si les deux sources nomment le même modèle.** Cela fait deux citations, dont aucune n'est inventée, puis c'est tout le test d'admission. Un modèle tarifé que personne n'a noté n'est toujours pas adopté ; un modèle noté que personne ne tarife ne peut toujours pas être facturé.

Au relevé du 2026-10-28 par [`scripts/measure_arena_coverage.py`](scripts/measure_arena_coverage.py) : 18 modèles passent, 164 sont tarifés sans note puis restent sur la liste de triage, le catalogue passant de 10 entrées à 28. **Relancer ce script imprime le compte du jour, pas ces chiffres-ci** — la source de prix gagne des modèles (190 au 2026-10-31) pendant que l'instantané du tableau vieillit, donc les nombres ci-dessus sont une lecture datée, étiquetée comme telle.

Ce qu'une entrée adoptée ne porte délibérément **pas**, c'est un score `general`, `code`, `math`, `ocr` ou `vision`. Ceux-là restent nuls.

Le classement mesure une préférence conversationnelle ; en synthétiser un nombre façon MMLU serait la fiction même que le reste de ce fichier existe pour éviter.

Le classeur lit directement les axes Arena, donc un nul n'y coûte rien. Puis chaque entrée adoptée enregistre le nom de tableau derrière chaque axe retenu, si bien que `85.2` se retrace jusqu'à `claude-opus-5.5-high` sur l'instantané `2026-10-07`, au lieu d'être un nombre sans provenance.

Deux conséquences à connaître avant de lire le classement :

- **La colonne `from` n'est pas un ornement.** Un score de 88 mesuré par une
  suite publiée façon MMLU puis un score de 86 converti d'un classement de
  préférence s'impriment tous deux sur 100 sans être *la même grandeur*. La
  table cloud nomme l'axe derrière chaque ligne exactement pour ça, puis
  quelques points entre deux lignes mesurées différemment ne sont pas un
  résultat.
- **Un modèle peut être noté puis afficher `?`.** Le miroir publie les vingt premiers par tableau, donc un modèle peut être noté en code puis absent du texte : censuré, pas faible.

  Ces candidats se classent derniers en qualité, *puis* sortent de l'étendue de qualité, afin que l'un d'eux ne puisse pas aplatir l'échelle de tous les autres.

  Il le pouvait : avant cela, quatre entrées de ce genre transformaient un écart de qualité de 68 à 88 en 0 à 88, puis le défaut orienté qualité se mettait à se comporter comme un défaut orienté prix.

Refaites vous-même n'importe lequel de ces nombres — le script est dans le
dépôt puis il lit à travers les chargeurs du paquet, il ne peut donc pas diverger
de ce que fait le code :

```sh
python scripts/measure_arena_coverage.py
```

```yaml
mode: cloud
kind: both
quality_vs_cost: 0.7           # optionnel, 0..1 ; choix automatique seulement, défaut 0.7
task: extraire les lignes structurées d'une facture PDF depuis son texte OCR
```

Trois autres clés existent pour le cas épinglé ; le brief est le seul endroit où les poser. `vlm_model` épingle séparément la place vision — avec `kind: both` puis `model` seul, le même modèle sert les deux. `base_url` remplace le point d'entrée du fournisseur (mandataire ou déploiement régional), puis `api_key_env` remplace le NOM de la variable d'environnement d'où la clé est lue, qui vaut par défaut celui du fournisseur. Ni l'une ni l'autre ne contient jamais la clé elle-même.

```sh
best-engine-ai-helper resolve --brief llm.brief.yaml --out llm.engine.yaml
# Wrote llm.engine.yaml
#   backend: openai  (llm=gpt-4o, vlm=gpt-4o)
```

Prévisualiser le choix automatique pour n'importe quelle tâche avant d'écrire un brief, côte à
côte avec le choix local, sans clé API ni appel réseau :

```sh
best-engine-ai-helper report --task "extraire les lignes d'une facture"
# ... section locale ...
# ## Best cloud VLM (axis: ocr)
# **→ `gpt-4o`** (openai) — score 69, ~$6.25/1M tokens (blended)
```

(`--no-cloud` retire cette section ; `--quality-vs-cost` et `--cloud-provider` l'ajustent.)

Chaque moteur cloud porte aussi un **repli** local embarqué, résolu depuis le même brief, pour
qu'un appel payant en échec dégrade vers le modèle local toujours disponible : payant vers
local, la seule direction sûre (un moteur local n'escalade jamais silencieusement vers un appel
payant). Quatre autres choses se produisent automatiquement au point d'appel `llm.chat()` dès
que `engine=` est un descripteur cloud :

| Point | Défaut | Désactiver / configurer |
|---|---|---|
| **Clé API** | le NOM dans `api_key_env` (jamais la valeur de la clé) est cherché en un passage (`settings.yaml`, puis un éventuel fichier `.env`, puis l'environnement du processus), puis le trousseau du système via `keyring` | `pip install 'best-engine-ai-helper[cloud]'` pour le repli trousseau |
| **Scan de sécurité** | chaque prompt/image scanné en sortie, chaque réponse scannée en entrée, pour le local ET le cloud (un souci de politique de contenu, pas un risque propre au cloud) | `chat(..., safety=False)` |
| **Pseudonymisation** | désactivée ; une fois activée, nettoie les données personnelles avec le modèle de repli LOCAL avant que le prompt ne quitte la machine, les restaure dans la réponse | `chat(..., pseudonymize=True)`, nécessite `[cloud]` |
| **Retry + cache** | désactivés ; le retry rejoue un échec transport transitoire avant de basculer, le cache mémoïse les appels identiques pour qu'une répétition ne soit jamais payée deux fois | `chat(..., retries=3, cache=True)`, le cache nécessite `[cloud]` |
| **Suivi du coût** | chaque appel, local ou payant, ajouté au journal d'activité local, chiffré depuis les comptages de jetons réels du fournisseur quand ils sont rapportés, sinon une estimation par caractères | `best-engine-ai-helper activity`, désactiver avec `BEST_ENGINE_NO_LEDGER=1` |

Voir [la section « modèle payant » d'EXEMPLES.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXEMPLES.md#4-un-modèle-payant-seulement-si-vous-donnez-une-clé) pour la recette complète
(settings.yaml, trousseau, sortie structurée, chaîne de repli) et [GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md) pour le
tableau de bord d'activité.

## L'utiliser comme un point d'entrée OpenAI

Tout ce qui précède est l'idiome propre à ce paquet : cahiers des charges,
fichiers moteur, `model_for()`. Cette section va dans l'autre sens : **vu de
l'extérieur, il se comporte comme un serveur compatible OpenAI.**

```sh
best-engine-ai-helper serve          # http://127.0.0.1:8000/v1
```

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="not-needed")

client.chat.completions.create(model="best", messages=[{"role": "user", "content": "…"}])
client.embeddings.create(model="best-embed", input=["…"])
client.images.generate(model="best-image", prompt="un vélo rouge")
```

Aucun changement de code côté client, puis aucun nom de modèle à connaître.
Cette seconde moitié est tout l'intérêt : le serveur compatible OpenAI habituel
— vLLM, le `/v1` d'Ollama, LM Studio — vous demande *quel* modèle charger, ce
qui laisse la partie difficile (est-ce que ça tient, est-ce assez rapide, un
plus gros vaut-il l'attente) à qui écrit la configuration. Ici le protocole est
le protocole familier puis **le choix est le produit**.

### `best` est un nom de modèle virtuel

Il se résout à chaque requête, contre cette machine, vers le modèle le mieux
classé qui tient — puis une requête portant une image exige un VLM, donc le même
nom se résout différemment selon ce qu'elle contient. La grammaire est petite :

| Nom de modèle | Se résout en |
|---|---|
| `best` / `auto` | Meilleur modèle texte ; meilleur modèle **vision** quand la requête porte des images |
| `best-llm` | Meilleur modèle texte ; une image dans la requête est refusée plutôt qu'ignorée |
| `best-vlm` | Meilleur modèle vision-langage |
| `best-embed` | Meilleur modèle d'embedding, classé sur la recherche (MTEB) plutôt que sur la connaissance générale |
| `best-image` | Meilleur modèle texte-vers-image |
| `best:<tâche>` | Meilleur modèle *pour cette tâche* — `best:write SQL`, `best:read screenshots`. La tâche choisit l'axe de référence, exactement comme `report --task`, puis donne un meilleur choix que l'alias nu |
| n'importe quoi d'autre | Passe tel quel : `qwen3:14b` veut toujours dire `qwen3:14b` |

La réponse annonce le modèle qui a réellement tourné (`"model": "qwen3:14b"`),
ce qu'un nom virtuel vous rend : vous avez renoncé à le nommer, donc la réponse
vous le dit.

Toute la grammaire, puis où chaque nom aboutit :

![Comment le nom de modèle virtuel « best » se résout, puis ce que la réponse nomme](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/nom-de-modele-virtuel.png)

### Ce qu'il sert

| Point d'entrée | Notes |
|---|---|
| `GET /v1/models` | Les alias ci-dessus, plus tout modèle du catalogue qui **tient sur cette machine** — la liste déroulante d'un client cesse donc de proposer un 72B à un portable |
| `POST /v1/chat/completions` | Texte puis vision. Flux réel (SSE), `response_format` comme vraie contrainte de schéma, conversation multi-tours rendue en transcription étiquetée plutôt que tronquée au dernier message |
| `POST /v1/completions` | Le point d'entrée historique, routé par le chat — tous les moteurs ici sont instruits, il n'y a donc aucun mode de complétion brute à exposer |
| `POST /v1/embeddings` | Encodage `float` ou `base64`, un vecteur par entrée, indices compris |
| `POST /v1/images/generations` | Diffusion locale. `size: "auto"` (le défaut) utilise la résolution **native** du modèle ; `b64_json` est le format de réponse par défaut, un serveur local n'ayant nulle part où héberger un fichier |

**La longueur de contexte est mesurée, pas déclarée.** Aucune des 31 lignes du catalogue local ne porte de `context_length`, puis aucune ne le devrait : la fenêtre appartient à une quantification précise d'un checkpoint précis, donc un chiffre saisi dans `models.yaml` décrirait un fichier que personne ici n'a ouvert.

Un modèle réellement téléchargé connaît la sienne, lui : les métadonnées GGUF la portent, puis Ollama la livre sur `/api/show`. `pull` puis `validate` la lisent, ensuite l'écrivent dans le même magasin par machine où vit la vitesse de décodage mesurée. `/v1/models` publie alors une vraie fenêtre pour les modèles que cette machine détient, puis rien du tout pour les autres.

La moitié payante n'a besoin de rien de cela : la source de prix publie une fenêtre, donc une entrée cloud en déclare simplement une.

`/v1` vit sur la même application que la GUI, les routes `/api/*` puis le point
d'entrée MCP : un processus, un port. La surface MCP ne publie délibérément
**pas** les routes `/v1` — sa description promet qu'aucun appel de modèle n'a
lieu dans ses outils, puis ça reste vrai.

### Ce qui n'est délibérément pas simulé

Une couche de compatibilité se gagne en refusant plutôt qu'en faisant semblant :

- **Les comptes de jetons sont réels quand le moteur les rapporte.** Ollama
  renvoie `prompt_eval_count`/`eval_count`, puis c'est ce que porte `usage`. Là
  où un moteur ne rapporte rien, les comptes sont une estimation par caractères
  — puis `system_fingerprint` le dit (`usage=estimated` contre
  `usage=reported`) au lieu de faire passer l'un pour l'autre.
- **Le flux est un vrai flux** pour du texte simple. Pour une requête qui exige
  en plus un schéma ou qui porte une image, il dégrade à un seul morceau, parce
  que le transport sous-jacent ne porte ni l'un ni l'autre. Un goutte-à-goutte
  mot à mot sur une réponse déjà complète aurait meilleure allure puis ne vous
  dirait rien de vrai sur l'avancement.
- **Les paramètres non gérés sont des erreurs qui se nomment.** `n > 1`,
  `logprobs` puis `tools` renvoient un 400. Un paramètre ignoré en silence est
  pire qu'un paramètre refusé : vous croiriez avoir obtenu ce que vous
  demandiez. (Pour les outils, demandez plutôt un schéma JSON : tout modèle
  Ollama l'applique nativement.)
- **Les `image_url` distants sont coupés par défaut.** Une URL `data:` marche
  toujours ; une URL `http(s)` fait chercher au serveur une adresse choisie par
  *l'appelant*, ce qui est une primitive de falsification de requête côté
  serveur, puis ce serveur tourne d'ordinaire sur une machine ayant accès à un
  réseau privé. Posez `BEST_OPENAI_FETCH_IMAGE_URLS=1` pour l'autoriser.
- **Les erreurs utilisent l'enveloppe d'OpenAI**, jusqu'aux 422 de FastAPI : un
  SDK déballe `error.message`, puis un corps `{"detail": …}` arrive à
  l'utilisateur comme « unknown error ». Bornée à `/v1` — les appelants de
  `/api` gardent les conventions de FastAPI.

L'affirmation « un SDK OpenAI analyse ça » est testée avec le SDK OpenAI
(`tests/test_openai_sdk.py`), pas avec des assertions de notre cru.

## Des pixels autant que du texte : génération d'images locale

`kind: image` est la troisième sorte de modèle que ce paquet choisit, puis il
est choisi comme les autres — une empreinte contre le vrai budget de cette
machine, une estimation de temps dans l'unité où l'on attend, une entrée de
catalogue plutôt qu'un nom en dur.

```sh
best-engine-ai-helper imagine plan                    # ce qui tourne ici, puis à quelle vitesse
best-engine-ai-helper imagine generate --prompt "un vélo rouge" --out velo.png
```

```
=== Image models: 36.0 GB budget, 400.0 GB/s memory bandwidth ===
id             params  size       steps  gb    offload  s/image  runs
-------------  ------  ---------  -----  ----  -------  -------  ----
flux1-schnell  16.9B   1024x1024  4      30.8  yes      16.9     yes
sd35-medium    10.9B   1024x1024  28     28.3  no       24.8     yes
sdxl           3.5B    1024x1024  28     9.8   no       25.8     yes
sdxl-turbo     3.5B    512x512    4      9.0   no       0.9      yes
sd15           1.1B    512x512    28     2.9   no       2.1      yes
```

Un modèle de diffusion n'est pas une pile de couches mais **trois ou quatre
réseaux qui se relaient** — encodeurs de texte, un dénoiseur (UNet ou
transformeur), un VAE — puis deux conséquences traversent toute la
fonctionnalité :

**La mémoire dépend de la façon dont ils se relaient.** Tous résidents, l'empreinte est leur somme. Confiés à `enable_model_cpu_offload()` de `diffusers`, seul le composant qui calcule reste résident, puis le pic devient le *plus gros*.

C'est le même marché que la lecture des couches en flux pour un LLM, à une pénalité bien moindre, parce que les composants se relaient quelques fois par image au lieu d'une fois par jeton.

C'est la colonne `offload` ci-dessus, puis elle est essayée automatiquement avant qu'un modèle soit rejeté pour cause de mémoire. Sur FLUX, où 8,4B des 16,9B sont un encodeur T5 utilisé une fois par image, c'est la différence entre l'exécuter puis ne pas l'exécuter.

**Le temps, ce sont des étapes, pas des jetons.** La boucle d'échantillonnage exécute un nombre fixe d'étapes de débruitage, chacune une passe complète du dénoiseur, donc l'unité honnête est la seconde par image.

Le plus gros levier est le nombre d'étapes, qui est une propriété des *poids* plutôt qu'une préférence. SDXL-Turbo puis FLUX.1-schnell sont distillés pour 1 à 4 étapes là où SDXL en veut 28 ; exécuter un checkpoint distillé à 28 étapes est plus lent **puis** moins bon.

Le nombre d'étapes vient donc du catalogue, ce qui est ce qui rend utilisable un modèle d'image choisi automatiquement.

Deux autres choses que le catalogue porte pour la même raison.

- **La résolution native**, parce que c'est la seule taille où un modèle de diffusion est bon : demander 1024×1024 à un modèle 512px duplique les sujets au lieu d'ajouter du détail. D'où `size: "auto"`, qui résout vers le chiffre du modèle.
- **La licence, qui diffère selon le modèle** — SD 1.5 puis SDXL en CreativeML OpenRAIL-M, SD 3.5 sous la licence communautaire Stability, FLUX.1-schnell en Apache-2.0 (son frère `[dev]` non). Vérifiez celle du modèle choisi avant de publier sa sortie.

## Usages / profils de tâche

Là où un *brief* est écrit par dépôt, les huit charges de travail récurrentes de la suite sont nommées une fois dans un **catalogue d'usages** intégré (`usages.yaml`).

Chaque **profil** — `text2sql`, `rag-answer`, `embeddings`, `text2sql-figures`, `report-bluf`, `classification`, `pii-rgpd`, `persona` — n'énonce que ses **besoins** : type de tâche (texte / code / vision / *embeddings*), besoin ou non de sortie structurée, plancher de débit, marge mémoire, seuil de qualité indicatif, longueur de contexte.

Un profil est, au fond, un *brief* nommé : il est donc résolu par le **même moteur à quatre critères** que n'importe quel *brief*.

Un profil **ne nomme jamais de modèle.** best-engine est le seul décideur : il lit les
besoins, sonde la machine et choisit le modèle local concret, en n'écrivant ce choix que
dans un fichier moteur généré (`llm.engine*.yaml`), **gitignoré et spécifique à la machine**,
jamais un littéral versionné. C'est tout l'intérêt de l'outil.

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

engine = resolve_usage("text2sql")  # best-engine choisit le modèle pour CETTE machine
family = resolve_family("F1")  # un seul modèle pour tout le groupe F1
```

best-engine écrit les modèles retenus dans le `llm.engine*.yaml` gitignoré de cette machine
(le prolongement de l'`env.sh` qu'il produit déjà) ; l'application lit ce fichier et une
nouvelle résolution re-décide si le matériel change. Ajouter un profil = quelques lignes dans
`usages.yaml` ; un *overlay* utilisateur dans `~/.best-engine-ai-helper/usages_cache.yaml`
surcharge par nom.

## En tant que skill d'agent

`skills/best-engine-ai-helper/` empaquette best-engine-ai-helper comme **skill Claude** *et* skill
**OpenCode**, pour qu'un agent puisse s'en saisir à votre place. Voir
[`skills/README.md`](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/skills/README.md) pour l'installer (liens
symboliques vers `~/.claude/skills/` et `~/.opencode/skills/`) et
[`TRIGGERS.md`](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/TRIGGERS.md) pour le catalogue exhaustif des
déclencheurs — `scripts/check_triggers.py` maintient la description du skill
alignée dessus ; la suite de tests échoue si une capacité cesse d'être
nommée.

## Auteur

[Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

## Remerciements

Remerciements chaleureux à [Victor Favreau](https://www.linkedin.com/in/victor-favreau-41b823117/) pour nos échanges fructueux.

## Licence

[BSD-3-Clause](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LICENSE). Copyright 2026 Warith Harchaoui.
