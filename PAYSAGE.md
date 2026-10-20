# Paysage

🇫🇷 Français · [🇬🇧 LANDSCAPE.md](LANDSCAPE.md)

Outils qui répondent à une version ou une autre de *« quel modèle dois-je utiliser ? »*,
comparés à `best-engine-ai-helper`. Les notes vont de ⭐ (1) à ⭐⭐⭐⭐⭐ (5), selon la
pertinence pour le travail que ce projet s'est donné : **choisir entre un modèle local
gratuit puis un modèle cloud payant, sur le matériel dont on dispose réellement puis avec
les clés d'API qu'on détient réellement puis prouver que le choix fonctionne.**

Un outil optimisé pour un autre travail n'est pas critiqué ici ; la note reflète
l'adéquation à *cette* niche. Plusieurs des entrées ci-dessous sont excellentes dans la
leur.

Relevé le 2026-10-19. Neuf critères, dont deux ajoutés après que ce projet a commencé à
mesurer la vitesse de décodage au lieu de l'estimer. Une case a été remesurée le
2026-10-20 — voir [la colonne que ce projet perd](#la-colonne-que-ce-projet-perd).

## Vue d'ensemble

<!-- TABLE:START -->
| Sélection de modèle | Détection du matériel | Tenue en mémoire locale | Mesure la vitesse sur cette machine | Modèles payants dans la même décision | Route selon les clés présentes | Provenance des scores | Largeur du catalogue | Éprouve la qualité avant qu'on en dépende | API programmatique |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **best-engine-ai-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| llmfit | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| RouteLLM | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| LiteLLM | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| OpenRouter | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ |
| Not Diamond | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Ollama | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ |
| LM Studio | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ |
| Calculateurs VRAM en ligne | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ |
<!-- TABLE:END -->

## Carte de positionnement

<!-- FIGURE:START -->
Représentation 2D du tableau ci-dessus, par ACP (voir [`standpoint`](https://github.com/warith-harchaoui/standpoint)).

![Carte de positionnement](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/paysage.png)

À lire comme une forme, pas comme un classement. La figure imprime **Horizontal —
Richesse ↔ Efficacité** puis **Vertical — Diversité ↔ Maîtrise**. Ces noms de pôles sont
écrits par le modèle qui a tracé la carte : ce sont les contributions sous-jacentes qui ne
bougent pas d'une exécution à l'autre, donc ce sont elles qu'il faut lire. L'horizontale est
bâtie presque entièrement sur la détection du matériel, la tenue en mémoire locale puis la
vitesse de décodage mesurée, chacune contribuant pour environ 0,50 : *à droite* signifie
**connaît la machine qu'il a devant lui**. La verticale est bâtie sur les modèles payants
dans la même décision, le routage selon les clés présentes, l'API programmatique puis la
qualité éprouvée, chacune entre 0,44 et 0,50 : *en haut* signifie **décide entre les deux
mondes puis vérifie la réponse**. À elles deux elles portent 75 % de la variance, donc un
quart du tableau n'est pas sur cette image.
<!-- FIGURE:END -->

## Ce que la carte montre vraiment

Deux lectures ; c'est la seconde qui a bougé.

**À gauche — la portée, aveugle à la machine.** LiteLLM, OpenRouter, Not Diamond,
RouteLLM. Ils atteignent des centaines de modèles à travers une seule surface puis
répondent à *« vers quel fournisseur cette requête doit-elle partir et combien cela
coûtera-t-il ? »*. Excellents à cela et parfaitement ignorants de la machine devant
laquelle l'appelant est assis : aucun ne répondra jamais « en fait, lancez-le en local
pour rien ».

**En bas — la tenue en mémoire, aveugle à la facture.** Ollama, LM Studio, les
calculateurs VRAM en ligne. Ils répondent à *« ce modèle tiendra-t-il et comment le
démarrer ? »*, sur n'importe quel matériel. Excellents aussi et parfaitement ignorants de
l'existence d'une API payante.

**En haut à droite — une décision qui a été vérifiée.** `best-engine-ai-helper` y est
seul — le détail honnête étant qu'il ne l'est pas sur l'horizontale : `llmfit` se pose à la
*même* coordonnée, tous deux à son maximum. Sur « connaît la machine qu'il a devant lui »
les deux sont à égalité, ce qui est la bonne lecture — `llmfit` comme ce projet **mesurent**
désormais la vitesse de décodage au lieu de l'estimer. L'écart est vertical puis vaut deux
unités pleines : `llmfit` mesure puis rapporte, là où ce projet mesure, puis laisse le
chiffre disqualifier un modèle et recalculer toutes les estimations suivantes.

**Le trou reste le haut à droite.** Aucun outil recensé ne combine *« que fait tourner
cette machine »* avec *« que facturerait un fournisseur et ai-je seulement cette clé »*
dans une seule décision. Ce n'est pas une affirmation sur la qualité, c'est une
affirmation sur la couverture et c'est la raison d'être de ce projet.

### La colonne que ce projet perd

**Largeur du catalogue : ⭐⭐⭐⭐ contre les ⭐⭐⭐⭐⭐ de `llmfit`.** Cette colonne affichait
⭐⭐ jusqu'au 2026-10-20 puis la raison qu'elle en donnait était fausse. Elle accusait la
discipline de provenance : vingt entrées maintenues à la main, chacune portant un `source:`
puis un `fetched_at`, parce qu'une entrée sans provenance vaut moins que pas d'entrée. Cela
sonnait comme un arbitrage assumé. C'était un mauvais diagnostic — `catalog update --ollama`
atteint désormais **420 tags tirables** en une seule requête — la bibliothèque officielle
liste 257 familles, 221 d'entre elles annoncent les tailles qu'elles livrent puis ce sont
ces tailles qui font un tag — et chacune de ces entrées porte le même `source:` puis le
même `fetched_at` que le catalogue de base. Ce n'est jamais la provenance qui a maintenu le
catalogue à vingt : c'est une discordance de nommage. ApXML nomme les modèles d'après le
slug du papier, qu'`ollama pull` ne sait pas résoudre, si bien que la seule source
automatique disponible pouvait ajouter des centaines d'entrées sans élargir d'un pouce ce
qui pouvait réellement être servi.

Ce qui n'a *pas* changé mérite d'être dit précisément. Ces 420 entrées portent des notes
nulles sur les cinq axes de benchmark, parce que la bibliothèque publie des tailles puis des
descriptions, pas des résultats de classement — elles se classent donc *sous* tout modèle
noté jusqu'à ce qu'une source notée les remplisse. La largeur de ce que cet outil sait
dimensionner, éprouver puis tirer se compte maintenant en centaines ; la largeur de ce qu'il
sait **classer sur la qualité** reste les vingt entrées curées. Un `null` se classe bas puis
reste honnête, là où une note inventée se classerait mal en ayant l'air d'une autorité.

C'est aussi pourquoi la note est ⭐⭐⭐⭐ plutôt que ⭐⭐⭐⭐⭐ : `llmfit` livre ses centaines
dans la boîte, sans appel réseau ni rien à activer. Ici la largeur est à une commande puis
une requête de distance, ce qui est assez proche pour compter sans être la même chose.

La colonne reste sur la carte exprès. Un paysage où l'auteur gagne toutes les colonnes est
un paysage auquel personne ne croit — et la leçon utile est celle que cette entrée vient de
démontrer contre elle-même : une page qui explique une faiblesse affirme une cause ; une
cause se périme exactement comme un chiffre. L'ancien ⭐⭐ a survécu un jour de plus que la
limite qu'il décrivait.

## Positionnement

`best-engine-ai-helper` répond à une question que les autres coupent en deux : **local
gratuit ou cloud payant, pour ce besoin, sur cette machine, avec ces clés.**

Quatre conséquences découlent du fait de traiter cela comme une seule question.

**Le brief nomme un besoin, jamais un modèle.** Un appelant dit qu'il veut du SQL
contraint par un schéma sous un plancher de latence ; le sélecteur dit quel modèle c'est,
en local ou dans le cloud. Le nom du modèle est une *sortie*, ce qui fait d'un changement
de modèle une modification de configuration.

**Le repli cloud va dans la direction sûre.** Un brief cloud résout un modèle payant
**et** un repli local depuis le même brief, si bien qu'un appel payant en échec se dégrade
vers le modèle local toujours disponible. Payant → local, jamais l'inverse.

**Un fournisseur dont la clé est absente n'est pas un candidat.** Les clés sont résolues
via `settings.yaml`, `.env`, l'environnement, puis le trousseau du système. Une
recommandation sur laquelle on ne peut pas agir n'est pas une recommandation.

**Chaque score dit d'où il vient.** Les benchmarks sont étiquetés de leur classement puis
de leur date de rafraîchissement ; une note d'Arena porte sa capture et une capture trop
vieille pour être crue est refusée plutôt que fusionnée — une note vieille de quatorze
mois classerait une génération précédente de modèles en tête, ce qui est pire que pas de
note du tout.

## Idées reprises du terrain

Autant le dire clairement, rien de tout cela n'a été inventé ici.

- **`llmfit` : chaque estimation livre ses entrées.** Sa commande `info` montre ce qu'un
  chiffre suppose puis comment le vérifier sur sa propre machine. Le même réflexe anime
  les drapeaux `--report` de ce projet puis le champ `source:` sur chaque chiffre du
  catalogue. C'est également de `llmfit` qu'est venue l'idée de **mesurer** le débit
  plutôt que de l'estimer.
- **RouteLLM : router sur la requête, pas sur le compte.** Son classifieur par prompt est
  d'une granularité plus fine que les briefs par profil d'usage de ce projet.
  L'arbitrage est délibéré — un brief est déclaratif, relisible puis testable, là où un
  routeur appris n'est aucun des trois — mais l'idée de router sur *ce qui est demandé*
  plutôt que sur *qui demande* leur revient.
- **Les routeurs cloud : le coût est un axe de première classe.** Les chiffres publiés
  situent les économies de routage entre 60 % puis 85 % sur des charges mixtes. C'est la
  raison pour laquelle `pricing.yaml` porte des tarifs publics et que le sélecteur expose
  un poids qualité-contre-coût plutôt que de classer sur la seule qualité.

## Notice par outil

### llmfit

Le plus proche voisin sur la carte. Détecte le CPU, la RAM, la mémoire discrète puis
unifiée sur CUDA, Metal, ROCm puis OneAPI, puis note des centaines de modèles sur la tenue
en mémoire, la vitesse estimée, la qualité puis le contexte. Son modèle de vitesse repose
sur la bande passante mémoire et s'appuie sur des mesures communautaires et `llmfit info`
montre les entrées derrière n'importe quel chiffre — le même réflexe de transparence que
ce projet. Sa commande `bench` mesure le débit réel sur la machine, ce qui a directement
inspiré le travail de mesure livré ici. Là où il s'arrête : le local uniquement.

### RouteLLM

De LMSYS puis de UC Berkeley. Un classifieur par prompt qui choisit entre un modèle
frontière fort puis un modèle faible bon marché, avec des économies publiées allant
jusqu'à 85 % à environ 95 % de la qualité de GPT-4. Granularité plus fine qu'un brief
d'usage et ni relisible ni testable comme l'est un brief en YAML. Complémentaire : un
brief pourrait raisonnablement résoudre *vers* RouteLLM.

### LiteLLM

La passerelle open-source de fait : une surface au format OpenAI par-dessus une centaine
de fournisseurs, avec clés, budgets, replis puis réessais. Elle route ; elle ne choisit
pas et elle ignore que la machine existe.

### OpenRouter

La version infogérée de la même idée, avec une place de marché puis une marge. Aucune
charge opérationnelle, au prix du départ de chaque requête hors de votre réseau.

### Not Diamond

Un recommandeur appris et infogéré qui optimise la qualité par euro. Le plus proche de ce
projet par l'intention, l'opposé par la posture : la décision se prend sur les serveurs de
quelqu'un d'autre, contre un catalogue qu'on ne peut pas lire et les modèles locaux n'y
sont pas.

### Ollama

Le serveur local que cette suite utilise réellement. Tire puis sert les modèles en une
commande. Délibérément tranché puis délibérément pas un sélecteur : `ollama run` suppose
que vous avez déjà décidé. Il affiche bien un débit mesuré avec `--verbose`, mais il n'en
fait rien.

### LM Studio

Une application de bureau avec un navigateur de modèles qui, lui, avertit quand un modèle
ne tiendra pas. Ce qu'une interface graphique fait de plus proche d'une sélection — et elle
s'arrête à l'avertissement : pas de classement, pas de validation, pas de surface
scriptable.

### Calculateurs VRAM en ligne

`modelfit.io`, `llmconfigurator.com`, `willitrunai.com` puis d'autres. On saisit sa VRAM,
on lit quelles tailles tiennent. Réellement utiles pour une vérification de cinq secondes
avant un achat et structurellement incapables de faire partie d'un pipeline.
