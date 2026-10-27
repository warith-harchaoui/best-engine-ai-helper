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
   mais optionnelle : le catalogue intégré suffit pour un usage courant. Le flux
   de couches (l'extra optionnel `[airllm]`) suit la même règle : un
   téléchargement depuis le Hub HuggingFace, puis le modèle s'exécute depuis
   votre propre disque — dans votre propre processus, sans aucun serveur.

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
- Optionnel : `[airllm]` pour exécuter un modèle qui ne tient **pas** en
  mémoire, en lisant ses couches en flux depuis le disque (voir [Trop gros pour
  tenir en
  mémoire](#trop-gros-pour-tenir-en-mémoire-exécutable-quand-même--le-flux-de-couches)),
  `[cloud]` pour le mode fournisseur cloud (retry, cache,
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

# Rien de bon ne tient ? Voir ce que cette machine pourrait exécuter en lisant
# les couches en flux depuis le disque, puis ce que le meilleur modèle coûterait
# en secondes par jeton
best-engine-ai-helper airllm compare --tokens 300
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
que la recommandation soit reproductible et discutable. (Un moteur est jugé sur
d'autres facteurs, parce qu'une autre ressource le borne : voir [le flux de
couches](#trop-gros-pour-tenir-en-mémoire-exécutable-quand-même--le-flux-de-couches)
plus bas.)

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

Quand aucun modèle ne tient, l'outil sélectionne le plus petit du catalogue puis
le signale — puis, sur une machine qui a le disque pour cela, propose d'exécuter
un *bon* modèle à la place en lisant ses couches en flux (voir [plus
bas](#trop-gros-pour-tenir-en-mémoire-exécutable-quand-même--le-flux-de-couches)).

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

## Trop gros pour tenir en mémoire, exécutable quand même : le flux de couches

Tout ce qui précède répond à une question : **quel modèle tient ?** Cette
section traite de la question suivante, celle qui vient quand la réponse
honnête est *aucun des bons*.

Un transformeur n'a jamais besoin de toutes ses couches en mémoire à la fois. Le
décodage lit la couche 1, puis la couche 2, puis la couche 3 ; seule la couche
en cours de calcul doit être résidente. En gardant une tranche de couche en
mémoire puis en lisant les autres depuis le disque, la mémoire qu'exige un
modèle cesse d'être proportionnelle à son nombre de paramètres : elle devient
proportionnelle à sa **plus large couche**. Un modèle de 70 milliards de
paramètres passe ainsi de 141 Go à environ **4 Go résidents**.

Le moteur qui fait cela est [airllm](https://github.com/lyogavin/airllm)
(Apache-2.0), une dépendance optionnelle de ce paquet :

```sh
pip install 'best-engine-ai-helper[airllm]'
```

Tout le reste — la détection, le catalogue, la recommandation, Ollama, vLLM, la
GUI, la surface MCP — fonctionne sans elle.

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

**2. Le prompt est quasi gratuit.** Un prompt de 2000 jetons est traité dans la
même passe unique qu'un prompt de 10 jetons. Aucun autre moteur n'offre cette
propriété : sous Ollama ou sous vLLM, un long prompt est du vrai travail de
préremplissage. Le flux de couches est donc comparativement bon pour « long
document en entrée, verdict court en sortie » : classification, extraction,
jugement, une réponse d'une ligne sur un long contexte. Au-delà de quelques
milliers de jetons, le calcul par couche commence à compter puis l'estimation le
signale au lieu de faire comme si de rien n'était.

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
- `tranches_résidentes` vaut 2 avec le préchargement d'airllm (la tranche
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

| Modèle | Checkpoint | Couches | Résident (préchargé / série) | s/jeton | Disque libre pour la découpe |
|---|---|---|---|---|---|
| Llama-3.3-70B | 140 Go | 80 | 6,1 Go / 3,9 Go | 41 s | 294 Go |
| Qwen2.5-VL-72B | 146 Go | 80 | 6,3 Go / 4,0 Go | 43 s | 307 Go |
| Mixtral-8x22B (141B, MoE) | 282 Go | 56 | 14,0 Go / 7,7 Go | 83 s | 592 Go |
| Qwen3-235B-A22B (MoE) | 470 Go | 94 | 14,5 Go / 8,2 Go | 138 s | 987 Go |
| DeepSeek-V3 (671B, fp8, MoE) | 671 Go | 61 | 29,0 Go / 15,2 Go | 197 s | 1409 Go |
| Llama-3.1-405B | 810 Go | 126 | 18,5 Go / 10,5 Go | 238 s | 1701 Go |

C'est la profondeur qui rend la dernière ligne possible : 405 milliards de
paramètres sur 126 couches donnent une tranche *plus légère* que 141 milliards
sur 56. Un mélange d'experts (MoE) brise la relation habituelle entre taille et
profondeur — DeepSeek-V3 fait 671 milliards sur 61 couches là où la tendance
dense en prédirait le double — donc une entrée MoE qui ne déclare pas ses
`layers` est **refusée** plutôt que devinée : une devinette s'y trompe d'un
facteur deux, dans le sens qui promet trop.

Lisez la dernière colonne en premier. **C'est l'espace disque, pas la mémoire,
qui refuse d'ordinaire un modèle** : airllm écrit les tranches par couche à côté
du checkpoint téléchargé, donc le cache contient les deux en même temps puis la
découpe exige à peu près le double du checkpoint en libre. Un modèle de 405
milliards de paramètres, c'est 810 Go de téléchargement avant d'être quoi que ce
soit d'autre. La mémoire est la moitié facile du problème.

Ces chiffres ont été vérifiés contre ceux que publie airllm, puis la
vérification mérite d'être énoncée précisément, parce que le « 70B sur un GPU de
4 Go » de l'affiche est vrai à une longueur de contexte que personne ne
mentionne : le même modèle fait 3,0 Go en série à 1k de contexte — la démo —
3,9 Go en série à 4k puis 6,1 Go à 4k avec le préchargement. Les poids sont
identiques dans les trois cas. Ce qui bouge, c'est le cache qui n'est pas
diffusé.

### Modèle natif ou modèle en flux ? `airllm compare` répond en un écran

C'est la décision que le flux de couches impose vraiment, puis aucun des deux
classements n'y répond seul. Une machine qui exécute confortablement un modèle
de 14 milliards de paramètres peut aussi en diffuser un de 70 : les deux
diffèrent de quelques points de référence dans un sens puis de trois ordres de
grandeur de latence dans l'autre.

Une colonne en jetons par seconde ne peut pas trancher — 26 puis 0,024 ne se
situent pas sur une échelle dont quiconque raisonne. Des secondes pour la même
réponse, oui :

```sh
best-engine-ai-helper airllm compare --tokens 300
```

```
=== LLM: ollama vs airllm, for a 300-token answer ===
  budgets: 11.04 GB resident (ollama) · 22.08 GB per shard (airllm) · disk 4.0 GB/s (declared)
model                       backend  score  resident  tok/s  answer  runs
--------------------------  -------  -----  --------  -----  ------  ----
qwen3:72b-q8_0              ollama   89     78.0      8.4    36 s    NO
qwen3:72b-q4_k_m            ollama   87     48.0      13.7   22 s    NO
qwen3:14b                   ollama   78     10.5      62.4   5 s     yes
gemma3:12b                  ollama   77     9.2       71.2   4 s     yes
Qwen/Qwen3-72B-Instruct     airllm   89     6.2       0.024  3.5 h   yes
Qwen/Qwen3-VL-72B-Instruct  airllm   88     6.2       0.024  3.5 h   yes

  Streaming buys 11 benchmark points (89 vs 78) for 2647x the wait: 3.5 h
  instead of 5 s for a 300-token answer.
```

Lisez la colonne `runs` : le modèle de 72 milliards de paramètres qui marque 89
est bien présent dans le catalogue Ollama puis **il ne tient pas** sur cette
carte de 24 Go. Le flux de couches est ce qui met la même classe de modèle à
portée, au prix affiché dans la colonne `answer`.

Chaque côté est classé selon les règles de son propre moteur, puis le côté en
flux inverse la règle habituelle. Partout ailleurs, ce paquet choisit le modèle
le **plus léger** à quelques points de référence du meilleur, parce qu'un
gigaoctet de résidence se paie à chaque exécution puis entre en concurrence avec
votre propre charge. Le flux de couches brise cette prémisse : la résidence est
une tranche quelle que soit la taille du modèle, donc la légèreté n'achète rien
puis la règle anti-gourmandise atterrit sur un modèle de 8 milliards de
paramètres — le seul résultat absurde, puisqu'un 8B tourne nativement cent fois
plus vite. Le choix en flux est donc le modèle le **plus capable** qui s'exécute,
au score de référence, la taille ne tranchant que là où aucun score ne le fait.

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

**Automatique** — le moteur conventionnel n'a rien résolu qui *tienne* sur cette
machine pour un genre que votre cahier des charges demande. Le flux de couches
est alors la différence entre un modèle puis aucun, donc `resolve` le propose
avec son coût énoncé. Le secours est **par genre** : si votre LLM tient puis
qu'aucun VLM ne tient, seul le VLM bascule, puis le fichier moteur est
honnêtement mixte (Ollama pour un genre, `airllm` pour l'autre —
`model_for()` lit d'abord le moteur du genre). Le descripteur enregistre la
décision puis sa raison sous `airllm:`, *y compris quand la réponse est non*,
pour qu'une machine qui ne peut pas diffuser dise pourquoi au lieu de rester
muette.

**Manuelle** — vous le demandez :

```sh
best-engine-ai-helper resolve --brief llm.brief.yaml --backend airllm
```

ou dans le cahier des charges versionné :

```yaml
kind: llm
task: juger la qualité de descriptions produit générées
airllm: always          # auto (défaut) | always | never
airllm_compression: 4bit
```

ou dans l'environnement, qui ne surclasse que les valeurs par défaut :

```sh
export BEST_ENGINE_AIRLLM=always   # ou never, pour couper toute la voie
```

`never` gagne sur tout, y compris sur le déclencheur automatique. Qui veut un
modèle de 235 milliards de paramètres sur un portable pendant la nuit fait un
choix légitime qu'aucune règle automatique ne devrait avoir à deviner, puis qui
ne veut jamais voir son disque malmené mérite un seul interrupteur qui le dise
vraiment.

### Les commandes

```sh
# Cette machine peut-elle diffuser, devrait-elle, puis qu'est-ce qui bloque ?
best-engine-ai-helper airllm status
best-engine-ai-helper airllm status --measure      # mesurer le disque au lieu de le supposer

# Que pourrait-elle diffuser, le plus capable d'abord ?
best-engine-ai-helper airllm plan --kind llm --compression 4bit

# Natif ou en flux, même longueur de réponse, les deux prix
best-engine-ai-helper airllm compare --tokens 300 --batch 8

# Payer le téléchargement puis la découpe maintenant, pas dans le premier appel
best-engine-ai-helper airllm prepare --model meta-llama/Llama-3.3-70B-Instruct
```

`--measure` mérite d'être connu. Le disque fixe toute la vitesse de ce moteur,
donc supposer sa classe (NVMe interne Apple, NVMe générique, SSD SATA, disque à
plateaux) est une entrée plus faible que la mesurer. La mesure écrit puis relit
environ 256 Mo **en contournant le cache de pages** (`F_NOCACHE` sur macOS,
`O_DIRECT` sur Linux) ; sans cette étape, la lecture est servie depuis la RAM
puis rapporte la bande passante mémoire — c'est ainsi que cette sonde a d'abord
annoncé 13 Go/s sur un disque dont la fiche technique plafonne près de 7. Sur une
plateforme sans moyen de contourner le cache, elle ne renvoie rien plutôt qu'un
chiffre flatteur, puis chaque surface étiquette la valeur `measured` ou
`declared`.

### Les limites, énoncées franchement

- **Pas de sortie structurée.** airllm expose une génération brute, sans
  équivalent du `format` contraint par grammaire d'Ollama. Tout modèle en flux
  est donc `structured_output: false` — un fait sur le moteur, pas sur les poids
  — puis les tâches de la suite pilotées par schéma restent sur un modèle
  Ollama. `llm.chat` lève une erreur au lieu d'honorer un schéma de nom
  seulement.
- **Texte uniquement.** L'adaptateur renvoie un modèle de langage causal nu,
  sans le processeur d'images qu'exige un prompt de VLM. Les images lèvent une
  erreur au lieu d'être silencieusement traitées depuis le seul texte.
- **Pas de serveur.** airllm est une bibliothèque, donc un modèle en flux
  s'exécute *dans votre propre processus* ; le `base_url` du fichier moteur est
  vide à dessein, parce qu'inventer un port local enverrait un consommateur
  chercher un démon qui n'existera jamais. `llm.chat` garde le modèle chargé
  entre les appels — découper un checkpoint de 141 Go à chaque appel rendrait le
  transport inutilisable.
- **Expérimental sur processeur.** La voie CPU d'airllm ne fonctionne que pour
  les modèles non découpés, donc une machine sans accélérateur ne reçoit pas le
  flux de couches automatiquement. Elle peut toujours le demander.

### Pourquoi airllm est importé plutôt que recopié ici

Question légitime pour un paquet qui redérive l'arithmétique. Quatre raisons :

1. **Le poids des dépendances.** airllm exige torch, transformers, accelerate,
   safetensors, scipy puis sentencepiece — des centaines de mégaoctets. Ce
   paquet est du Python pur qui s'installe en quelques secondes. Faire payer une
   pile d'apprentissage profond à qui veut une *recommandation* serait le mauvais
   marché ; en extra, c'est un choix, exactement comme `[cloud]` puis
   `[filtered]`.
2. **C'est une cible mouvante.** La valeur d'airllm est son code de découpe par
   famille de modèles (Llama, Qwen, DeepSeek, Mixtral, ChatGLM, Kimi), réécrit à
   chaque nouvelle famille. Recopié, il serait figé au jour de la copie puis
   pourrirait dès la version suivante.
3. **Hygiène de licence.** airllm est en Apache-2.0 ; ce paquet est en
   BSD-3-Clause. L'import garde les deux arbres, puis leurs obligations de
   notice, séparés.
4. **Le partage du travail est réel, pas une esquive.** airllm décide *comment*
   diffuser. Rien chez lui ne décide *si* cette machine devrait le faire, *quel*
   modèle diffuser, ni *ce que ça vous coûtera en temps* — et ce sont les trois
   questions que pose réellement l'appelant de ce paquet.

Le moteur est donc importé puis la **décision** est native : `offload.py` possède
l'arithmétique d'empreinte, le modèle de temps borné par le disque, la politique
d'activation, la comparaison natif contre flux puis les métadonnées de catalogue
dont tout cela a besoin (`layers`, `dtype`, `moe`). Rien de cela n'importe
airllm : c'est pourquoi `airllm status` puis `airllm compare` fonctionnent sur
une machine où l'extra n'a jamais été installé — en vous disant ce que son
installation vous apporterait.

### Depuis Python

```python
import best_engine_ai_helper as beah

hw, disk = beah.available_memory(), beah.disk_profile()

# Cette machine devrait-elle diffuser ?
decision = beah.airllm_decide(conventional_resolved=False)
print(decision["activate"], decision["reason"], decision["blockers"])

# Que coûterait un 70B ici ?
entry = {
    "id": "llama3.3:70b",
    "size_b": 70,
    "layers": 80,
    "hf_id": "meta-llama/Llama-3.3-70B-Instruct",
}
print(beah.airllm_footprint_gb(entry))  # 6,1 Go résidents
print(beah.airllm_generation_time(entry, disk["read_gbs"], new_tokens=300, batch=8))

# Natif ou en flux, pour une réponse de 300 jetons ?
report = beah.airllm_compare(
    beah.load_catalog(),
    hw=hw,
    disk=disk,
    bandwidth_gbs=beah.compute_profile()["bandwidth_gbs"],
    new_tokens=300,
)
print(report["verdict"])

# Puis, avec l'extra installé, l'exécuter vraiment
text = beah.airllm_generate(
    "Juge cette description :…", model="meta-llama/Llama-3.3-70B-Instruct", max_new_tokens=64
)
```

La surface HTTP répond aux mêmes questions en un seul appel —
`GET /api/airllm?answer_tokens=300&batch=8` renvoie la décision, le profil de
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
| `airllm status` | Cette machine peut-elle lire les couches en flux depuis le disque, devrait-elle, puis qu'est-ce qui bloque (`--measure` pour mesurer le disque) |
| `airllm plan` | Ce qu'un modèle trop gros coûterait ici, classé : tranche résidente, secondes par jeton, disque pour la découpe |
| `airllm compare` | Modèle natif contre modèle en flux, même longueur de réponse, les deux tarifés en secondes |
| `airllm prepare` | Télécharger puis découper un checkpoint maintenant, plutôt que dans le premier appel |

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
