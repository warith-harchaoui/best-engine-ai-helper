# best-engine-ai-helper

[🇫🇷](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/README.md)

[![Licence : BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](#)

Choisit et télécharge le meilleur modèle de langage (LLM, *large language model*) ou modèle
de vision-langage (VLM, *vision-language model*) local adapté au matériel de la machine
courante.

L'outil détecte la mémoire disponible (mémoire unifiée Apple Silicon, mémoire vidéo NVIDIA
ou RAM système), consulte un catalogue de modèles intégré et sélectionne le modèle au
meilleur score qui tient dans une marge de sécurité configurable. Après la sélection, il
télécharge le modèle via Ollama et le soumet à deux contrôles avant de lui faire confiance :
sait-il repérer et corriger un défaut connu glissé dans un court texte (la boucle Ralph), et
sait-il repérer un défaut visuel évident glissé dans une petite image de test (la boucle
Ralph Eyeball) ? Seul un modèle qui réussit les deux voit son fichier d'environnement
écrit, le fichier que les projets en aval viennent lire pour trouver le modèle choisi.

[![logo](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/logo.png)](https://deraison.ai/ai-helpers)

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

## En production

Ce paquet est à la base de la couche de sélection de modèles de la suite AI Helpers : trois autres paquets publiés (`md2star`, `standpoint`, `vocal-helper`) font transiter chaque appel LLM et VLM par lui plutôt que de coder en dur un nom de modèle. Il est publié sur PyPI avec une intégration continue verte à chaque envoi (ruff, mypy et une suite de tests maintenue au-dessus de 90 % de couverture). Chaque version est un tag sémantique sur GitHub.

## Documentation

[💻 Documentation](https://deraison.ai/ai-helpers/docs/best-engine-ai-helper-doc/)

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
  classification). Voir [Deux modes : local (gratuit) et cloud
  (payant)](#deux-modes--local-gratuit-et-cloud-payant) plus bas et [la
  section `resolve`
  d'EXEMPLES.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXEMPLES.md#resolve)
  pour le déroulé complet ; les deux se dégradent proprement (une
  heuristique par mots-clés ou un verdict « indisponible ») en leur
  absence, jamais un échec brutal.

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

`best-engine-ai-helper` est la seule ligne de commande livrée par ce
paquet : une surface, construite avec click, qui est une dépendance de base
et non un extra optionnel. Les versions antérieures à la 1.9.0
installaient aussi un second point d'entrée suffixé qui la doublait commande
par commande ; il n'y a plus qu'un seul nom, et c'est celui-ci.

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
puis une marge de sécurité `headroom` (par défaut 0,5, le plafond dur : une valeur plus
grande est ramenée à ce plafond) s'applique par-dessus. Un modèle
tient quand son `ram_gb` (pic d'inférence estimé) reste au plus égal à ce budget.

### 3. Adéquation à la tâche

Une tâche, même une phrase vague comme « fiches produit et contrôle qualité des photos »,
se traduit en un axe de benchmark (`generalist`, `code`, `math`, `ocr`, `vision`) et en
types de modèles nécessaires (du texte implique un LLM, tout visuel implique un VLM). Parmi
les modèles qui tiennent, le meilleur score sur cet axe l'emporte.

### 4. Débit

La génération est bornée par la bande passante mémoire : chaque jeton lit une fois le modèle
actif en mémoire, donc le plafond est `bande passante ÷ taille`, réduit à environ 65 % pour
la mémoire de travail que le modèle garde en cours de génération (le *cache KV*, la trace
de tout ce qu'il a déjà lu, pour ne pas le relire à chaque nouveau mot) et pour les autres
surcoûts. `report` estime les jetons/s par candidat et propose une
alternative plus légère et plus rapide quand elle est presque aussi forte. Plus gros n'est
pas toujours mieux : un modèle 72B qui tient tout juste peut tourner à quelques jetons/s,
là où un modèle 8-14B laisse de la marge et va plusieurs fois plus vite.

Quand aucun modèle ne tient, l'outil sélectionne le plus petit du catalogue et le signale.

#### Le débit mesuré, puis pourquoi l'estimation demandait une correction

![La boucle de mesure : prédire, choisir, éprouver, puis réinjecter la mesure dans la prédiction suivante](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/measurement-loop.png)

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

Remesurer le même modèle conserve l'échantillon **le plus rapide** plutôt que le
plus récent, ce qui est une exigence de correction et non de l'optimisme. La
grandeur que l'on calibre est un **plafond** de bande passante mémoire et une
machine occupée ne peut que faire paraître une observation plus lente que le
matériel ne l'est réellement. La leçon vient du comportement lui-même :
`gemma3:12b` a mesuré 15,2 jetons/s sur une machine au repos puis 8,7 jetons/s
avec trois suites de tests en cours — et l'échantillon sous contention aurait
donné à lui seul une correction de 0,31 contre 0,54 pour la machine au repos,
faussant toutes les estimations de la machine. Le champ `samples` indique sur
combien d'observations repose le chiffre retenu.

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

   Cette affirmation est **éprouvée** plutôt que posée :
   `scripts/validate_calibration.py` calibre sur un modèle, prédit un autre,
   puis dit si le résultat bat l'estimation brute. C'est le cas dans toutes les
   directions essayées, l'erreur tombant de **64-118 % à 17-25 %**. Les deux
   moitiés méritent d'être dites : la correction est grande puis elle n'est pas
   de la précision. Les rapports s'étalent d'environ **0,46 à 0,61** selon le
   modèle puis d'une exécution à l'autre du même modèle, ce qui explique
   pourquoi le facteur est une **médiane** sur plusieurs mesures et non une
   seule et pourquoi une vraie mesure l'emporte toujours sur une estimation
   corrigée quand elle existe. La calibration fait passer une estimation de
   « fausse d'un facteur deux » à « fausse d'un cinquième » ; elle ne la rend
   pas juste.

Le point 3 explique aussi pourquoi le plancher de confort comptait plus qu'il
n'y paraissait : `COMFORT_TPS` vaut 15 jetons/s, donc une estimation non corrigée
de 28,3 le franchit sans hésiter alors que la mesure réelle de 15,2 l'effleure.
La correction fait toute la différence entre une recommandation qui *semble*
confortable puis une qui l'est.

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
| `resolve` | Transforme un brief d'usage commité en `llm.engine.yaml` propre à cette machine |
| `doctor` | Compare ce que le fichier moteur a résolu avec ce que le démon sait servir |
| `storage` | Planifie la capacité : ce qui tient sur le disque, puis ce qui tient en mémoire ensemble |
| `providers` | Quels fournisseurs cloud sont utilisables, puis pour les autres la variable à poser |
| `catalog show` | Affiche le catalogue de modèles fusionné |
| `catalog update` | Rafraîchit le cache modèles (`--ollama` pour des tags réellement tirables, `--arena` pour fusionner les notes LM Arena, `--limit N` pour un rafraîchissement partiel) |
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

`--ollama` élargit le catalogue depuis la [bibliothèque officielle Ollama](https://ollama.com/library) plutôt que depuis ApXML. Il existe parce que le catalogue *servable* plafonnait à vingt modèles pour une raison qui n'a jamais été une question de notation. ApXML peut ajouter des centaines d'entrées, mais il les nomme d'après le papier (`qwen36-35b-a3b`), un nom de dépôt HuggingFace qu'`ollama pull` ne résout pas : ces entrées sont donc réservées à vLLM. La bibliothèque publie au contraire les familles, leurs capacités puis les tailles livrées — et une famille plus une taille **est** un tag de tirage : `qwen3` plus `8b` donne `qwen3:8b`, exactement l'orthographe déjà utilisée par le catalogue de base. 256 familles donnent environ 420 tags, en une seule requête.

Ces entrées ne portent **aucune note de benchmark**, parce que la bibliothèque publie des tailles puis des descriptions, pas des résultats de classement. Elles se classent donc **sous** tout modèle noté, jusqu'à ce qu'une source notée les remplisse. C'est le but plutôt qu'une limite : cela élargit ce que l'outil sait dimensionner puis tirer sans changer ce qu'il recommande ; une note inventée vaudrait moins qu'une note absente — un `null` se classe bas puis reste honnête, une invention se classe mal tout en ayant l'air d'une autorité.

Les tailles viennent d'une constante **mesurée** sur les quatorze entrées Q4 du catalogue de base, pas devinée : 0,646 Go par milliard de paramètres pour un modèle texte, 0,714 pour un modèle vision, puisqu'une tour d'image est réellement plus lourde par paramètre. L'écart aux chiffres connus du catalogue reste sous les 5 %. Une famille qui n'annonce aucune taille est écartée plutôt qu'enregistrée à zéro, ce qui l'aurait fait paraître tenir sur n'importe quelle machine.

`--arena` fusionne en plus les notes de préférence conversationnelle issues des miroirs de [LM Arena](https://lmarena.ai). Deux faits mesurés méritent d'être connus avant d'y recourir.

![Chaque source Arena essayée tour à tour, puis la raison de son échec aujourd'hui](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/arena-staleness.png)

**Cet axe sert le catalogue cloud, pas le catalogue local.** L'Arena note ce avec quoi ses votants peuvent discuter. Apparié aux catalogues livrés (mesuré le 2026-10-19 contre le miroir vivant le plus frais), il couvrait **6 des 10 modèles cloud** de `pricing.yaml` mais seulement **3 des 20 modèles locaux** de `models.yaml`.

Les trois appariements locaux en disent plus que le rapport : `qwen2.5-coder:32b`, `qwen3:32b-q4_k_m` et `qwen3:32b-q8_0` — chaque appariement était un modèle 32B, rien de plus petit n'a été apparié. Les quatre modèles d'embedding (`nomic-embed-text`, `mxbai-embed-large`, `snowflake-arctic-embed2`, `bge-m3`) ne peuvent pas être appariés par construction : personne ne discute avec un encodeur, donc aucun classement de préférences conversationnelles n'en notera jamais un. L'axe n'est donc pas simplement « biaisé cloud » : il note de gros modèles conversationnels, ce qui décrit l'essentiel d'une grille tarifaire cloud puis une minorité d'un catalogue local. C'est l'inverse de ce qu'on attend d'un « classement de modèles » ; c'est toute la différence entre bien se servir de cet axe et attendre qu'il départage ce qu'il ne verra jamais. La commande affiche son propre `matched/total` à chaque exécution : vous n'avez pas à croire ce paragraphe sur parole.

**Il peut très bien ne rien retourner du tout.** L'Arena ne publie aucune API, donc chaque source ici est le scrape d'un tiers et un scrape pourrit : au 2026-10 le site officiel répond 403, un miroir rend des classements vides puis le miroir vivant le plus frais a plus d'un an. L'adaptateur refuse une capture au-delà de sa limite de péremption en nommant la raison plutôt que de la fusionner, parce qu'un Elo d'une génération précédente classerait les modèles de 2025 au-dessus de ceux de 2026 — strictement pire que pas d'Elo. Le cas échéant la commande le dit et laisse l'axe vide ; elle n'annonce pas un succès qui n'a rien enrichi.

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
machine et la qualité du choix dépend de la précision avec laquelle cette tâche est décrite :
c'est le texte de la tâche qui se traduit en axe de score et qui décide si un VLM est
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

   Le backend est choisi par un arbre de décision à trois branches, qui reflète ce que chaque
   moteur supporte réellement bien plutôt que ce sur quoi il tourne tant bien que mal :

   - **macOS -> Ollama.** vLLM n'a pas de runtime natif macOS.
   - **CPU seul (Linux ou macOS) -> Ollama.** Le chemin CPU seul de vLLM — notamment sous
     Linux — est son propre point faible signalé ; le chemin CPU d'Ollama est le plus éprouvé.
   - **GPU discret (NVIDIA/AMD) sous Linux — le vrai cas de production -> vLLM**, notamment
     pour sa gestion de la concurrence et du batching de requêtes sous charge réelle, qu'Ollama
     n'égale pas.

   Windows retombe aussi sur Ollama (pas de wheel vLLM natif, WSL uniquement), donc en
   résumé : **vLLM uniquement sous Linux avec un GPU discret ; Ollama partout ailleurs.** Le
   choix reste prudent par ailleurs : la marge mémoire est plafonnée à 0,5 et parmi les modèles
   à quelques points de benchmark du meilleur, il prend le plus léger et le plus rapide, pas le
   plus gros qui tient tout juste. Les choix vLLM sont dimensionnés sur les poids FP16 complets
   (plus lourds que l'estimation Ollama Q4), pour qu'un choix vLLM soit réaliste sur le vrai
   GPU. La sortie est spécifique au matériel ; ajoutez-la au `.gitignore` :

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

## Deux modes : local (gratuit) et cloud (payant)

Chaque brief choisit un des deux modes avec `mode: local` (le défaut) ou `mode: cloud`. Les
deux se résolvent vers le même type de fichier moteur et le même point d'appel
`llm.chat(engine=..., kind=...)` en aval : seuls le transport et le coût changent.

### Local (gratuit, par défaut)

`mode: local` — ou l'absence de champ `mode` — correspond à [la promesse](#la-promesse) : la
détection matérielle, la sélection du modèle et chaque garde qualité tournent sur cette
machine, contre un modèle déjà tiré via Ollama ou servi via vLLM. Chaque appel coûte **0,0 $**,
toujours (voir [Journal d'activité](#journal-dactivité)) : il n'y a aucun appel API payant à
chiffrer.

### Cloud (payant)

`mode: cloud` route plutôt vers un fournisseur payant : OpenAI, Mistral, OpenRouter, Together
ou Azure OpenAI (tous compatibles OpenAI), plus Anthropic et Gemini (formats propres à chacun),
tout en gardant le même point d'appel `llm.chat(engine=..., kind=...)` en aval. Deux façons de
choisir le modèle :

- **Le fixer** : nommer `provider` et `model` explicitement dans le brief, exactement comme
  avant.
- **Le choisir automatiquement** : omettre `model` (et `provider`, pour chercher chez tous les
  fournisseurs) et best-engine choisit le meilleur modèle payant depuis un petit catalogue
  embarqué (`pricing.yaml`, enrichi de scores de benchmark par modèle), de la même façon que le
  mode local choisit depuis `models.yaml`, sauf que la ressource budgétée est le **prix**, pas
  la mémoire, puisque tout modèle payant tourne sur n'importe quelle machine. Un curseur
  `quality_vs_cost` (0 à 1, défaut 0,7) oriente le choix : `1.0` choisit uniquement sur le
  score, `0.0` uniquement sur le prix et le défaut privilégie la qualité avec le prix en
  départage.

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

Voir [la section `resolve` d'EXEMPLES.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXEMPLES.md#resolve) pour la recette complète
(settings.yaml, trousseau, sortie structurée, chaîne de repli) et [GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md) pour le
tableau de bord d'activité.

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
