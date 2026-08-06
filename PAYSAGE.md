# Paysage

🇫🇷 Français · [🇬🇧 LANDSCAPE.md](LANDSCAPE.md)

Outils comparables dans le domaine « choisir et lancer un grand modèle de langage local »,
comparés à `best-engine-ai-helper`. Les notes vont de ⭐ (1) à ⭐⭐⭐⭐⭐ (5), selon la
pertinence pour le travail visé par ce projet : détecter le matériel disponible, sélectionner
le modèle au meilleur score qui tient dans la mémoire, le valider par des contrôles de qualité
empiriques et écrire un fichier d'environnement que les projets en aval peuvent sourcer. Un
outil optimisé pour un usage très différent n'est pas pénalisé.

## Vue d'ensemble

<!-- TABLE:START -->
| Sélection de LLM local | Détection matériel auto | Sélection par score | Contrôles Ralph | Catalogue hors ligne | Testable en IC | API programmatique |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| **best-engine-ai-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Ollama (CLI) | ⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| LM Studio | ⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ |
| Jan.ai | ⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ |
| llm (Simon Willison) | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| LocalAI | ⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| text-generation-webui | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐⭐ |
<!-- TABLE:END -->

## Carte de positionnement

<!-- FIGURE:START -->
Représentation 2D du tableau ci-dessus.

![Carte de positionnement](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/paysage.png)

La carte est un résumé en 2D des 6 critères : à lire comme une forme, pas comme un classement. « best-engine-ai-helper » se situe dans le coin en haut à droite. Les axes se lisent **Horizontal — Flexibilité ↔ Automatisation** et **Vertical — Accessibilité ↔ Intégration**.
<!-- FIGURE:END -->

## Positionnement

`best-engine-ai-helper` occupe la zone étroite où la conscience du matériel, la validation
empirique et l'automatisation scriptable se rejoignent. La plupart des outils de cet espace
résolvent le problème du *service* (comment faire tourner un modèle une fois qu'on l'a
choisi). Ce projet résout le problème de la *sélection* (quel modèle choisir et comment
prouver qu'il fonctionne correctement sur cette machine précise).

## Notice par outil

### Ollama

Ollama est le serveur de référence qu'utilise `best-engine-ai-helper` pour télécharger et
servir les modèles. Il fait excellemment ce pour quoi il est conçu : un serveur binaire
unique avec une API REST propre et une vaste bibliothèque de modèles. Il ne sélectionne pas
les modèles en fonction du matériel détecté et ne classe pas les candidats par score. Vous
dites à Ollama quel modèle télécharger ; ce projet vous dit lequel télécharger.

### LM Studio

LM Studio est une application de bureau multiplateforme pour parcourir, télécharger et lancer
des modèles locaux. Sa détection du matériel est partielle : il vous avertit quand un modèle
est trop volumineux, mais il ne classe pas les candidats par score ni ne sélectionne
automatiquement le meilleur. Il ne propose pas d'interface scriptable pour les pipelines
d'intégration continue (IC).

### Jan.ai

Jan.ai offre une expérience d'interface graphique similaire à LM Studio, avec une interface
soignée et un catalogue de modèles. Comme LM Studio, il est avant tout interactif : pas de
sélection automatique basée sur le matériel, pas de contrôles de qualité, pas de surface
programmatique pour l'automatisation.

### llm (Simon Willison)

L'outil en ligne de commande `llm` est une interface élégante, basée sur des greffons, pour
des dizaines de fournisseurs de modèles, qu'ils soient en nuage ou locaux. Son atout est la
largeur : une commande, de nombreux moteurs. Il ne détecte pas le matériel et ne classe pas
les modèles par score. C'est le bon choix quand vous savez quel modèle vous voulez et avez
besoin d'un outil pratique pour lui parler.

### LocalAI

LocalAI est un serveur REST compatible OpenAI qui fait tourner des modèles locaux via
llama.cpp et des moteurs similaires. C'est le bon choix quand vous souhaitez injecter un
point d'entrée local dans du code client OpenAI existant. La sélection et la validation
restent à la charge de l'utilisateur.

### text-generation-webui (Oobabooga)

text-generation-webui est une interface web complète pour faire tourner et affiner des modèles
locaux. Elle est orientée GPU, configurée manuellement et n'est pas conçue pour
l'automatisation scriptée ni les pipelines d'IC. C'est le bon choix pour l'expérimentation
interactive et les flux de travail d'affinage.
