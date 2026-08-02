# best-engine-ai-helper

[🇫🇷](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/README.md)

[![Licence : BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](#)

Choisit et télécharge le meilleur modèle de langage (LLM, *large language model*) ou modèle
de vision-langage (VLM, *vision-language model*) local adapté au matériel de la machine
courante.

L'outil détecte la mémoire disponible (mémoire unifiée Apple Silicon, mémoire vidéo NVIDIA
ou RAM système), consulte un catalogue de modèles intégré, et sélectionne le modèle au
meilleur score qui tient dans une marge de sécurité configurable. Après la sélection, il
télécharge le modèle via Ollama, exécute deux contrôles de qualité (la boucle Ralph pour la
prose et la boucle Ralph Eyeball pour la vision), et écrit un fichier d'environnement que
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
lecture seule de ce flux (les caractéristiques matérielles, et la recommandation de moteur
à partir d'une tâche) sans passer par le terminal. La page est bilingue : français par
défaut, anglais via `/gui?lang=en`, avec un lien d'en-tête pour basculer. Voir
[GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md) (en anglais).

## Prérequis

- Python 3.10 ou ultérieur
- [Ollama](https://ollama.com) (nécessaire uniquement pour `pull`, `validate` et `env` ; pas
  requis pour `detect`, `recommend` ou `report`)
- psutil, PyYAML, click, requests (installés automatiquement)
- Optionnel : `fastapi` + `uvicorn` pour la GUI navigateur
  (`pip install 'best-engine-ai-helper[api]'`)

## Installation

Le paquet est en Python pur (Python 3.10+). Les seuls éléments spécifiques à
la plateforme sont **Python lui-même** et le runtime **Ollama** optionnel
(nécessaire uniquement pour `pull` / `validate` / `env`, pas pour `detect`,
`recommend`, `report` ni la GUI). Choisissez votre OS ci-dessous.

Partout, `[api]` ajoute l'extra de la GUI navigateur (`fastapi` + `uvicorn`).
Retirez-le (`pip install best-engine-ai-helper`) si vous ne voulez que la CLI.

### 🍎 macOS

```sh
# 1. Python 3.10+ (ignorez si déjà présent : python3 --version)
brew install python

# 2. Installer dans un environnement virtuel isolé (recommandé)
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install 'best-engine-ai-helper[api]'

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
pip install 'best-engine-ai-helper[api]'

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
pip install "best-engine-ai-helper[api]"

# 3. Optionnel : Ollama, uniquement si vous utiliserez `pull`
winget install Ollama.Ollama
```

La VRAM NVIDIA est détectée via `nvidia-smi` (installé avec le pilote). Notez
les guillemets doubles autour de `"...[api]"` : PowerShell les exige, les
guillemets simples ne se comportent pas pareil.

### Depuis les sources (tout OS)

```sh
git clone https://github.com/warith-harchaoui/best-engine-ai-helper
cd best-engine-ai-helper
pip install -e '.[api]'          # Windows PowerShell : pip install -e ".[api]"
```

### Vérifier l'installation

```sh
best-engine-ai-helper --version
best-engine-ai-helper detect     # affiche le matériel de la machine en JSON
```

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

# Lancer la GUI navigateur (nécessite l'extra [api])
best-engine-ai-helper gui
```

Voir [EXAMPLES.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/EXAMPLES.md) pour des recettes complètes avec exemples de sortie, et
[GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md) pour la GUI navigateur.

## GUI

`best-engine-ai-helper gui` sert une GUI mono-page (FastAPI + JS natif, sans étape de
build) sur `http://127.0.0.1:8000/gui` : les mêmes caractéristiques système que `detect`,
et une zone de texte pour la tâche qui renvoie la même recommandation que `report`, sans
terminal. La page est bilingue (français par défaut, anglais sur `/gui?lang=en`), avec un
lien d'en-tête pour basculer.

![Résultats de recommandation](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/screenshots/gui-recommendation.png)

Voir [GUI.md](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/GUI.md) pour le détail complet, l'API JSON sous-jacente, et comment le jeu
d'icônes (favicon / touch-icon) est généré à partir de `assets/logo.png`.

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
| `gui` | Lance la GUI navigateur (nécessite l'extra `[api]`) |

## Intégration avec les projets en aval

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

## Licence

[BSD-3-Clause](https://github.com/warith-harchaoui/best-engine-ai-helper/blob/main/LICENSE). Copyright 2026 Warith Harchaoui.
