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

Relevé à nouveau le 2026-10-29, ce qui a ajouté trois entrées puis déplacé la conclusion.
Neuf critères, douze outils. Les deux colonnes que ce projet perd sont écrites plutôt
qu'enterrées — voir [les colonnes que ce projet perd](#les-colonnes-que-ce-projet-perd).

## En un coup d'œil

<!-- TABLE:START -->
| Sélection de modèle | Détection du matériel | Tenue en mémoire locale | Mesure la vitesse sur cette machine | Modèles payants dans la même décision | Route selon les clés présentes | Provenance des scores | Largeur du catalogue | Éprouve la qualité avant qu'on en dépende | API programmatique |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **best-engine-ai-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| llmfit | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| AMD Lemonade | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| Passerelle IA ngrok | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| RouteLLM | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| LiteLLM | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| OpenRouter | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ |
| Not Diamond | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Ollama | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ |
| LM Studio | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ |
| Calculateurs VRAM en ligne | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ |
| Calculateurs de seuil de rentabilité | ⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐ | ⭐ | ⭐ |
<!-- TABLE:END -->

## Trois aptitudes, puis la seule région à occupant unique

![Trois familles d'outils : connaît cette machine, joint les fournisseurs payants, chiffre l'un contre l'autre — puis le centre où les trois se rejoignent](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/diagrams/trois-familles.png)

Avant la carte, la forme du terrain en clair. Trois aptitudes sont en jeu puis presque
personne n'en a plus d'une. **Connaître cette machine** — détecter sa mémoire puis y
dimensionner un modèle — appartient à `llmfit`, Ollama, LM Studio puis aux calculateurs
VRAM en ligne. **Joindre les fournisseurs payants** par une seule surface appartient à
LiteLLM, OpenRouter, Not Diamond, RouteLLM puis à la passerelle IA ngrok. **Chiffrer les
deux mondes l'un contre l'autre** n'appartient qu'aux calculateurs de seuil de
rentabilité, qui le font à partir d'un volume mensuel de jetons que vous saisissez.

Un seul outil siège dans une intersection à deux : AMD Lemonade détecte processeur, carte
graphique puis NPU, enfin un réglage expérimental de déport cloud confie une requête à un
fournisseur compatible OpenAI. Les deux autres intersections à deux sont vides. Tout le
reste du milieu aussi.

## Carte de positionnement

<!-- FIGURE:START -->
Représentation 2D du tableau ci-dessus, par ACP (voir [`standpoint`](https://github.com/warith-harchaoui/standpoint)).

![Carte de positionnement](https://raw.githubusercontent.com/warith-harchaoui/best-engine-ai-helper/main/assets/paysage.png)

À lire comme une forme, pas comme un classement. La figure affiche **Horizontal — Richesse
↔ Efficacité** puis **Vertical — Simplicité ↔ Maîtrise**, puis ces noms de pôles sont
écrits par le modèle qui a dessiné la carte — les contributions dessous sont la part qui ne
change pas d'une exécution à l'autre, donc lisez celles-là. L'horizontal se construit
presque entièrement sur la tenue en mémoire locale (0,50), la vitesse de décodage mesurée
(0,50) puis la détection du matériel (0,49) : *à droite* signifie **connaît la machine
devant soi**. Le vertical se construit sur le routage selon les clés présentes (0,51), les
modèles payants dans la même décision (0,50), la qualité éprouvée (0,45) puis l'API
programmatique (0,43) : *en haut* signifie **décide à travers les deux mondes, puis
vérifie la réponse**. Les deux portent 70 % de la variance à elles deux, donc près d'un
tiers du tableau n'est pas sur cette image — moins que les 75 % que portait la version à
neuf outils, ce qui est l'effet d'ajouter trois outils qui se contredisent entre eux.
<!-- FIGURE:END -->

## Ce que la carte montre vraiment

Trois lectures. La troisième est nouvelle puis c'est elle qui coûte à ce projet une phrase
qu'il aimait écrire.

**À gauche — la portée, aveugle à la machine.** LiteLLM, OpenRouter, Not Diamond,
RouteLLM, la passerelle ngrok. Ils joignent des centaines de modèles par une seule surface
puis répondent à *« chez quel fournisseur cette requête doit-elle partir puis combien
coûtera-t-elle ? »*. Excellents à cela. La passerelle sait viser un point d'accès Ollama
ou vLLM local, ce qui la distingue réellement du reste de sa colonne puis n'est toujours
pas la même chose : elle routera *vers* un modèle local que vous avez déjà choisi puis n'a
aucun moyen de vous dire lequel tient.

**En bas — la tenue, aveugle à la facture.** Ollama, LM Studio, les calculateurs VRAM en
ligne. Ils répondent à *« ce modèle tiendra-t-il, puis comment le démarrer ? »*, sur le
matériel qu'on leur donne. Excellents aussi, puis parfaitement ignorants de l'existence
d'une API payante.

**En haut à droite — puis ce n'est plus un coin vide où ce projet se trouve seul.**
`best-engine-ai-helper` atterrit en (2,68 ; 1,93) puis les deux chiffres sont des égalités
plutôt que des victoires. `llmfit` siège **exactement à la même abscisse**, 2,68 : sur
« connaît la machine devant soi » les deux sont indiscernables, ce qui est la bonne
lecture — tous deux détectent le matériel puis *mesurent* la vitesse de décodage au lieu
de l'estimer. La passerelle IA ngrok siège **exactement à la même ordonnée**, 1,93 : sur
« décide à travers les deux mondes » les deux sont indiscernables aussi, parce qu'une
passerelle qui mélange fournisseurs hébergés puis points d'accès auto-hébergés sous une
même politique, avec repli à travers modèles, fournisseurs puis clés, fait précisément
cela.

L'affirmation honnête est donc plus étroite que « seul dans le coin », puis plus nette :
**ce projet n'est le meilleur sur aucun des deux axes puis il est la seule entrée qui ne
soit près du bas d'aucun.** `llmfit` est à -0,03 à la verticale ; ngrok est à -2,34 à
l'horizontale. Couvrir les deux est tout le produit, puis la carte le dit maintenant par
l'arithmétique au lieu de le dire par une absence.

### Les colonnes que ce projet perd

Deux, puis la seconde est nouvelle.

**Largeur du catalogue : ⭐⭐⭐⭐ face aux ⭐⭐⭐⭐⭐ de `llmfit`.** Cette colonne affichait ⭐⭐
jusqu'au 2026-10-20 puis la raison qu'elle en donnait était fausse. Elle accusait la
discipline de provenance : vingt entrées maintenues à la main, chacune portant un
`source:` puis un `fetched_at`, parce qu'une entrée sans provenance vaut moins que pas
d'entrée. Cela sonnait comme un arbitrage de principe. C'était un mauvais diagnostic.
`catalog update --ollama` atteint désormais **420 tags tirables** en une seule requête —
la bibliothèque officielle liste 257 familles, dont 221 annoncent les tailles qu'elles
livrent, puis une famille plus une taille font un tag de téléchargement. Chacune de ces
entrées porte le même `source:` puis le même `fetched_at` que la graine. Ce n'est jamais la
provenance qui tenait le catalogue à vingt ; c'était une discordance de nommage. ApXML
nomme les modèles par le slug de l'article, qu'`ollama pull` ne sait pas résoudre, donc la
seule source automatique disponible pouvait ajouter des centaines d'entrées sans élargir ce
qu'on pouvait réellement servir.

Ce qui n'a *pas* changé est la part qui mérite d'être précise. Ces 420 entrées portent des
scores nuls sur les cinq axes de benchmark, parce que la bibliothèque publie des tailles
puis des descriptions plutôt que des résultats de classement — elles se classent donc *sous*
tout modèle noté jusqu'à ce qu'une source notée les remplisse. La largeur de ce que cet
outil sait dimensionner, loger puis télécharger se compte maintenant en centaines ; la
largeur de ce qu'il sait **classer sur la qualité** reste les entrées curées plus ce sur
quoi deux sources s'accordent. Un nul se classe bas puis reste honnête, là où un score
deviné se classerait mal tout en ayant l'air d'une autorité.

C'est aussi pourquoi c'est ⭐⭐⭐⭐ plutôt que ⭐⭐⭐⭐⭐ : `llmfit` livre ses centaines dans la
boîte, sans appel réseau ni rien à activer. Ici la largeur est à une commande puis une
requête de distance, ce qui est assez proche pour compter sans être la même chose.

**La couverture des accélérateurs, qui n'a pas de colonne puis qui se lit dans « détection
du matériel ».** AMD Lemonade route à travers processeur, carte graphique **puis NPU** —
`lemonade backends` dit ce qu'il y a sur la machine, puis sur du Ryzen AI il met le
traitement du prompt sur le NPU XDNA2 puis la génération de jetons sur la carte graphique.
Ce projet connaît trois réservoirs de mémoire : l'unifiée Apple, la VRAM discrète, la RAM
système. Il n'a **aucune notion de NPU**, donc sur un portable Ryzen AI il dimensionne
contre la carte graphique ou la RAM puis ignore silencieusement le troisième accélérateur
posé là. Les deux outils marquent ⭐⭐⭐⭐⭐ en détection du matériel, ce qui est généreux
envers celui-ci : l'étoile porte sur le fait que la machine soit *détectée*, puis sur
*quels accélérateurs sont utilisables* Lemonade est simplement devant. Écrit ici plutôt
qu'en inventant une dixième colonne, parce qu'une colonne ajoutée à l'instant où un
concurrent la gagne n'est pas un critère, c'est un tableau d'affichage.

Les deux colonnes restent sur la carte exprès. Un paysage où l'auteur gagne toutes les
colonnes est un paysage que personne ne croit — puis la leçon utile est celle que la
largeur du catalogue a démontrée contre elle-même : une page qui explique une faiblesse
affirme une cause, puis une cause se périme exactement comme un chiffre. L'ancien ⭐⭐ a
survécu un jour de plus que la limitation qu'il décrivait.

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
  catalogue.
- **`llmfit` encore : une mesure vaut davantage partagée.** `llmfit bench --share` renvoie
  un débit mesuré au projet, si bien que l'*estimation* du suivant s'appuie sur le vrai
  matériel de quelqu'un. Ce projet mesure la vitesse de décodage sur `pull` puis
  `validate` puis garde le chiffre strictement local — un choix délibéré, puisque la
  promesse en tête du LISEZMOI est que rien ne quitte la machine, donc un bénéfice
  réellement abandonné plutôt qu'une idée que personne n'a eue.
- **AMD Lemonade : l'accélérateur est une décision de routage, pas une constante.** Il
  choisit un *moteur* par modèle puis par appareil — llama.cpp pour le GGUF, ONNX Runtime
  pour les graphes optimisés, un moteur NPU sur Ryzen AI — là où ce projet choisit entre
  exactement deux moteurs sur une règle unique (vLLM sur Linux avec carte graphique
  discrète, Ollama partout ailleurs). Le manque côté NPU ci-dessus est la moitié visible
  de cette idée.
- **RouteLLM : router sur la requête, pas sur le compte.** Son classifieur par prompt est
  d'une granularité plus fine que les briefs par profil d'usage de ce projet.
  L'arbitrage est délibéré — un brief est déclaratif, relisible puis testable, là où un
  routeur appris n'est aucun des trois — mais l'idée de router sur *ce qui est demandé*
  plutôt que sur *qui demande* leur revient.
- **Les routeurs cloud : le coût est un axe de première classe.** Les chiffres publiés
  situent les économies de routage entre 60 % puis 85 % sur des charges mixtes. C'est la
  raison pour laquelle `pricing.yaml` porte des tarifs publics et que le sélecteur expose
  un poids qualité-contre-coût plutôt que de classer sur la seule qualité.
- **Les calculateurs de rentabilité : demander ce que l'autre monde aurait coûté.** Tout
  leur genre compare exécuter un modèle ici contre le payer là-bas, puis la soudure faible
  est toujours la même — vous saisissez un volume mensuel de jetons avant d'avoir exécuté
  la charge, puis la durée d'amortissement que vous lisez hérite de la devinette. Le
  journal d'activité tient déjà la charge, mesurée, donc
  `best-engine-ai-helper activity --what-if` la croise avec la table de prix contre
  laquelle le journal facture déjà les appels payants : ce que les appels locaux que vous
  avez **déjà faits** auraient coûté au tarif public, du moins cher au plus cher. C'est
  rapporté comme une *facture évitée*, jamais comme une économie — l'électricité, le
  disque puis le temps d'un modèle plus lent sont des coûts réels dont ce journal ne mesure
  aucun.
- **lightweight : « est-ce que ça tient ? » est la mauvaise question pour un transformeur
  séquentiel.** Tous les outils de cette carte, celui-ci compris, répondaient à *quel
  modèle tient dans la mémoire que j'ai*. lightweight fait remarquer qu'un décodeur lit ses
  couches dans l'ordre, donc que seule la couche en cours de calcul doit être résidente
  — puis la mémoire qu'exige un modèle s'effondre de son nombre de paramètres à sa plus
  large couche. C'est une idée réellement différente plutôt qu'une meilleure estimation,
  puis c'est désormais le moteur `lightweight` ici (voir LISEZMOI). Ce que ce projet ajoute
  par-dessus est la part qu'lightweight n'a aucune raison de posséder : si *cette* machine
  devrait prendre le marché, quel modèle diffuser, puis ce que le meilleur modèle coûtera
  en secondes par jeton face à celui qui tient déjà. Le moteur est importé, pas recopié —
  l'arithmétique puis la décision sont natives.

## Notice par outil

### llmfit

Le plus proche voisin sur la carte, puis celui qui égale exactement ce projet sur l'axe
horizontal. Détecte le processeur, la RAM système, les cartes graphiques, la VRAM puis la
configuration d'accélérateurs, puis note son catalogue sur la tenue en mémoire, la vitesse
estimée, la qualité puis le contexte, à travers GGUF, AWQ, GPTQ puis EXL2, avec les couches
à mélange d'experts traitées à part. Son modèle de vitesse repose sur la bande passante
mémoire puis s'appuie sur des mesures communautaires ; `llmfit bench` mesure le débit réel
sur la machine puis `llmfit bench --share` renvoie le chiffre. `llmfit info` montre les
entrées derrière n'importe quel chiffre — le même réflexe de transparence que ce projet.
Ses « fournisseurs » sont des *moteurs locaux* — Ollama, llama.cpp, MLX, Docker Model
Runner, LM Studio — pas des API payantes. Là où il s'arrête : le local uniquement, ce qui
est tout l'axe vertical.

### AMD Lemonade

Nouveau dans ce relevé. Un serveur local adossé à AMD qui sert les modèles de langage, la
génération d'images puis la parole depuis une seule installation, en exposant un point
d'accès compatible OpenAI plus une ligne de commande puis un binaire intégrable. La part
intéressante est le matériel : il détecte puis route à travers processeurs (x86_64,
ARM64), cartes graphiques (CUDA, ROCm, Vulkan, Metal) puis **NPU** (XDNA2, Ryzen AI), en
choisissant un moteur par modèle puis par appareil, puis le routeur Lemonade ajouté en
v11.5.0 envoie une requête au modèle *déjà installé* le plus adapté. Un réglage
expérimental de déport cloud sait confier une requête à un fournisseur compatible OpenAI.
Là où il s'arrête : aucun classement de qualité publié — il choisit entre des modèles que
vous avez installés plutôt que de vous dire lesquels installer — puis la moitié cloud est
une configuration que vous écrivez, pas une décision qu'il prend. Le manque côté NPU qu'il
révèle ici est réel, puis la raison honnête pour laquelle ce n'est pas une action à mener
est que ce projet n'a pas de NPU à tester.

### Passerelle IA ngrok

Nouvelle dans ce relevé ; disponibilité générale le 2026-06-23. Un seul point d'accès
devant des fournisseurs hébergés *puis* auto-hébergés — Ollama, vLLM, LM Studio ou
n'importe quel fournisseur compatible OpenAI — avec des expressions CEL qui décident quel
modèle reçoit une requête, un repli automatique à travers modèles, fournisseurs puis clés,
des identifiants gérés ou fournis par vous, un compte de jetons puis un inspecteur de
trafic. C'est la première entrée de ce relevé qui mélange réellement inférence locale puis
payante dans une même décision, ce qui lui vaut d'égaler l'ordonnée de ce projet. Là où
elle s'arrête est l'axe horizontal : elle n'a aucune idée de ce que la machine derrière le
point d'accès local sait exécuter. Elle routera vers `ollama/llama3:70b` sur un portable de
16 Go puis rapportera l'échec après coup. Service infogéré, donc la politique vit sur le
réseau de ngrok.

### RouteLLM

De LMSYS puis de UC Berkeley. Un classifieur par prompt qui choisit entre un modèle
frontière fort puis un modèle faible bon marché, avec des économies publiées allant
jusqu'à 85 % à environ 95 % de la qualité de GPT-4. Granularité plus fine qu'un brief
d'usage et ni relisible ni testable comme l'est un brief en YAML. Complémentaire : un
brief pourrait raisonnablement résoudre *vers* RouteLLM.

### LiteLLM

La passerelle open-source de fait : une surface au format OpenAI par-dessus une centaine
de fournisseurs, avec clés, budgets, replis puis réessais. Elle route ; elle ne choisit
pas et elle ignore que la machine existe. Ce projet lit sa table de prix publique — la
seule source qui a transformé `pricing.yaml` d'une liste saisie à la main en une liste
rafraîchissable.

### OpenRouter

La version infogérée de la même idée, avec une place de marché puis une marge. Aucune
charge opérationnelle, au prix du départ de chaque requête hors de votre réseau.

### Not Diamond

Un recommandeur appris et infogéré qui optimise la qualité par euro. Le plus proche de ce
projet par l'intention, l'opposé par la posture : la décision se prend sur les serveurs de
quelqu'un d'autre, contre un catalogue qu'on ne peut pas lire et les modèles locaux n'y
sont pas.

### lightweight

Pas un sélecteur du tout, puis sans chercher à l'être : un *moteur* de lecture des couches
en flux. Il découpe un checkpoint en tranches par couche puis les relit une à une, donc un
modèle de 70 milliards de paramètres s'exécute dans environ 4 Go résidents au lieu de 141
— sans quantification, sans distillation, sans élagage. Le coût est que chaque jeton relit
tout le checkpoint depuis le disque, ce qui le place à des secondes par jeton plutôt qu'à
des jetons par seconde.

L'entrée la plus intéressante de cette carte, parce qu'elle ne concurrence rien d'autre
dessus : elle change le sens du mot « tient ». Là où elle s'arrête est exactement là où ce
projet commence — lightweight diffusera volontiers un modèle de 671 milliards de paramètres
vers un disque qui n'a pas la place pour la découpe, à deux minutes par jeton, puis il n'a
aucun avis sur l'opportunité de le faire. Ces jugements (empreinte résidente, disque exigé
par la découpe, secondes par jeton, puis natif contre flux tarifés dans la même unité)
sont natifs ici ; le moteur est importé comme dépendance de plein droit plutôt que
caché derrière un extra. Apache-2.0.

Il n'est pas noté dans le tableau ci-dessus, pour la raison que ce paragraphe donne : il
répond à une autre question, puis une note en étoiles face à « quel modèle dois-je
utiliser ? » serait une erreur de catégorie déguisée en mesure.

### Ollama

Le serveur local que cette suite utilise réellement. Tire puis sert les modèles en une
commande. Délibérément tranché puis délibérément pas un sélecteur : `ollama run` suppose
que vous avez déjà décidé.

### LM Studio

Une application de bureau avec un navigateur de modèles qui, lui, avertit quand un modèle
ne tiendra pas. Ce qu'une interface graphique fait de plus proche d'une sélection — et elle
s'arrête à l'avertissement : pas de classement, pas de validation, pas de surface
scriptable.

### Calculateurs VRAM en ligne

`modelfit.io`, `llmconfigurator.com`, `willitrunai.com`, `llmhardware.io` puis d'autres.
On saisit sa VRAM, on lit quelles tailles tiennent, en général avec l'arithmétique du cache
KV affichée. Réellement utiles pour une vérification de cinq secondes avant un achat et
structurellement incapables de faire partie d'un pipeline. Ils marquent ⭐⭐⭐⭐ en tenue
mémoire puis ⭐ en détection du matériel pour la même raison : l'arithmétique est juste puis
les entrées sont saisies à la main.

### Calculateurs de seuil de rentabilité

Nouveaux dans ce relevé, puis un genre plutôt qu'un outil : le calculateur coût-API-contre-
local de `runyard.dev`, le guide local-contre-cloud de `llmconfigurator.com` puis une
longue traîne de billets de 2026 adossés au même tableur. Vous saisissez un volume mensuel
de jetons, un prix de carte graphique puis un tarif d'électricité ; ils rendent une durée
d'amortissement, typiquement située entre 5 puis 20 millions de jetons par mois selon les
modèles comparés. Ce sont les seules entrées dont le sujet *est* « ici contre là-bas »,
puis les seules sans catalogue, sans détection du matériel ni moyen d'être appelées depuis
du code. La soudure faible est le volume : une devinette faite avant que la charge
n'existe, dont tout l'aval hérite. C'est cette observation qui a donné `activity --what-if`.

## Quand choisir quoi

La réponse honnête est souvent un autre outil de cette carte.

**Choisissez `llmfit`** quand la question est purement locale puis que vous voulez le
catalogue le plus large livré dans la boîte, sans appel réseau ni rien à configurer. Il est
à égalité avec ce projet sur la détection du matériel puis sur la vitesse de décodage
mesurée, puis il livre des centaines de modèles notés là où celui-ci livre une graine curée
plus ce qu'y ajoute `catalog update`. Si aucune API payante n'entrera jamais dans la
décision, la machinerie supplémentaire d'ici n'apporte rien.

**Choisissez AMD Lemonade** quand la machine a un NPU ou quand le but est de servir
plutôt que de décider : il emploiera des accélérateurs que ce projet ne sait pas voir puis
il sert texte, images puis parole depuis une seule installation. Associez les deux plutôt
que de choisir, si vous voulez — rien n'empêche un brief de résoudre vers un modèle que
Lemonade sert ensuite.

**Choisissez la passerelle IA ngrok** quand la décision est déjà prise puis que le problème
est le trafic : un seul point d'accès devant des modèles hébergés puis auto-hébergés, avec
repli, politique puis identifiants gérés au même endroit. C'est la seule autre entrée qui
couvre les deux mondes, puis elle les couvre à la couche du routage plutôt qu'à celle du
choix.

**Choisissez LiteLLM ou OpenRouter** quand chaque appel part déjà chez un fournisseur puis
que le problème est de la plomberie : une surface par-dessus plusieurs fournisseurs, avec
les clés, les budgets, les réessais puis les replis. Ni l'un ni l'autre ne proposera jamais
d'exécuter la tâche en local pour rien, ce qui est le bon comportement quand cela n'a
jamais été envisagé. LiteLLM si vous voulez opérer la passerelle vous-même ; OpenRouter si
vous préférez éviter.

**Choisissez RouteLLM ou Not Diamond** quand la décision de routage doit se prendre par
requête plutôt que par dépôt. Un routeur appris voit le prompt ; un brief ne voit que la
description du travail. En échange, un brief est un fichier relisible sous gestion de
versions là où un classifieur est un modèle.

**Choisissez Ollama ou LM Studio** quand vous avez déjà décidé quel modèle exécuter puis
que vous voulez simplement le servir. C'est le cas la plupart du temps, puis c'est la
raison pour laquelle ce projet résout *vers* Ollama au lieu de le remplacer.

**Choisissez lightweight directement** quand vous savez déjà que vous voulez la lecture des
couches en flux puis que vous n'avez besoin de rien pour la dimensionner, la refuser ou la
tarifer face au modèle qui tient.

**Choisissez un calculateur VRAM en ligne** quand vous voulez une réponse en cinq secondes
avant un achat de matériel puis que rien n'a besoin de finir dans un pipeline.

**Choisissez un calculateur de rentabilité** quand la question est du capital, pas de la
configuration : acheter la carte graphique ou non. Il réclame une charge que vous ne pouvez
qu'estimer ; une fois la charge existante, `activity --what-if` répond à la même question
depuis ce qui a réellement tourné.

**Choisissez celui-ci** quand la décision couvre les deux mondes : quand *« l'exécuter en
local gratuitement »* puis *« payer un fournisseur au jeton »* sont deux options vivantes,
quand la réponse doit différer d'une machine à l'autre sans que le dépôt change, puis quand
vous voulez qu'un choix soit **refusé** au lieu d'être simplement rapporté s'il est trop
lent, trop gros pour le disque ou adossé à une clé que vous ne détenez pas.

## Sources et date de relevé

**Relevé à nouveau le 2026-10-29.** Chaque affirmation sur un autre projet dans cette page
a été lue dans sa propre documentation publique, son dépôt ou l'aide de sa ligne de
commande — rien ici n'est un benchmark que ce projet aurait fait tourner contre un
concurrent. La passe du 2026-10-29 a ajouté AMD Lemonade, la passerelle IA ngrok puis le
genre des calculateurs de rentabilité, relu le dépôt de `llmfit` (d'où viennent les faits
sur `bench --share` puis sur ses moteurs locaux, ce qui remplace la note du relevé
précédent disant qu'aucune URL n'avait été consignée), puis laissé les autres entrées à
leur lecture du 2026-10-19. Là où une entrée n'a pas été revérifiée, c'est cette date
antérieure qu'un lecteur doit lui rapporter.

Où les entrées ont été lues. Les liens ci-dessous visent le domicile canonique
de chaque projet, pas une page datée : aucun numéro de version n'est cité dans
cette page, délibérément, parce que la version est la part d'une affirmation qui
se périme le plus vite puis qu'aucune lecture faite ici n'en dépendait. Les deux
exceptions sont nommées comme des dates dans le texte — le routeur de Lemonade
puis la disponibilité générale de ngrok — parce que ce sont des faits du type
« cela n'existait pas au relevé précédent » puis que la date *est* l'affirmation.

- **streaming de couches** — implémenté dans ce paquet (`streaming.py`) sur
  torch, transformers, accelerate puis safetensors. C'était `airllm` ; cette
  dépendance est partie parce qu'elle ne savait pas faire tourner une
  architecture autre que Llama sur Apple Silicon puis écrivait une seconde
  copie de chaque checkpoint sur le disque avant de rien lancer. Le chiffre
  « 70 milliards de paramètres dans environ 4 Go résidents » venait de
  l'annonce de ce projet-là ; ici il est calculé par `lightweight plan`, qui
  dit aussi ce que ça coûte en secondes par jeton.
- **llmfit** — [github.com/AlexsJones/llmfit](https://github.com/AlexsJones/llmfit),
  lu le 2026-10-29. Plusieurs forks publient le même README avec des comptes de modèles
  différents en accroche ; c'est pourquoi ces comptes ne sont pas cités ici.
- **AMD Lemonade** — [github.com/lemonade-sdk/lemonade](https://github.com/lemonade-sdk/lemonade),
  lu le 2026-10-29. L'achèvement du routeur en v11.5.0 (2026-07-22) puis les chiffres du
  partage NPU/GPU sont des affirmations publiées par AMD.
- **Passerelle IA ngrok** — [ngrok.com/docs/ai-gateway](https://ngrok.com/docs/ai-gateway/overview),
  lue le 2026-10-29. La disponibilité générale au 2026-06-23 est l'annonce de ngrok.
- **LiteLLM** — [github.com/BerriAI/litellm](https://github.com/BerriAI/litellm).
- **RouteLLM** — [github.com/lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM), LMSYS
  puis UC Berkeley. Le chiffre « jusqu'à 85 % d'économies à environ 95 % de la qualité de
  GPT-4 » vient des résultats publiés par le projet.
- **OpenRouter** — [openrouter.ai](https://openrouter.ai).
- **Not Diamond** — [notdiamond.ai](https://www.notdiamond.ai).
- **Ollama** — [ollama.com](https://ollama.com).
- **LM Studio** — [lmstudio.ai](https://lmstudio.ai).
- **Calculateurs VRAM en ligne** — `modelfit.io`, `llmconfigurator.com`,
  `willitrunai.com`, `llmhardware.io`, lus comme pages publiées.
- **Calculateurs de seuil de rentabilité** — l'outil coût-API-contre-coût-local de
  `runyard.dev` puis le guide local-contre-cloud de `llmconfigurator.com`, lus le
  2026-10-29, plus la littérature de billets de 2026 qui les entoure. La fourchette « 5 à
  20 millions de jetons par mois » est celle que ces pages citent, pas une mesure
  indépendante, puis elle dépend entièrement des deux modèles comparés.

La fourchette de **60 à 85 %** d'économies de routage citée sous [Idées reprises du
terrain](#idées-reprises-du-terrain) est un intervalle de chiffres publiés par les
fournisseurs de routeurs cloud, pas une mesure indépendante, puis les économies sur une
charge mixte dépendent entièrement du mélange. À prendre comme la raison d'être d'un axe de
coût ici, pas comme un chiffre sur lequel bâtir un budget.

D'où viennent les chiffres propres à ce projet :

- **Les notes en étoiles sont un jugement, pas une mesure.** Elles notent les capacités
  documentées de chaque outil face au travail énoncé en tête de page. Un outil bâti pour un
  autre travail obtient une note basse ici sans être critiqué pour autant.
- **Les deux axes, leurs contributions puis chaque coordonnée citée ci-dessus** sont une
  ACP sur `assets/paysage.csv`, calculée par
  [`standpoint`](https://github.com/warith-harchaoui/standpoint) : la figure se redérive
  donc du tableau ci-dessus au lieu d'être dessinée à la main. Les *noms* de pôles, eux,
  sont écrits par un modèle puis bougent d'une exécution à l'autre ; les contributions puis
  les coordonnées non.
- **Les chiffres du catalogue** — 420 tags tirables, 257 familles, dont 221 annonçant leurs
  tailles — sont une mesure propre à ce projet, issue de l'exécution de
  `catalog update --ollama` du 2026-10-20 contre la bibliothèque officielle d'Ollama.
- **Les scores de benchmark puis les tarifs** des catalogues embarqués
  (`best_engine_ai_helper/data/models.yaml`, `pricing.yaml`) portent chacun leur propre
  champ `source:` puis `fetched_at` : c'est là qu'il faut chercher la provenance d'un
  chiffre précis, pas ici.

## Idées à reprendre

Étudié plutôt que deviné : ce que chaque voisin fait mieux, puis ce que cette bibliothèque devrait changer pour l'égaler. Rien ici n'est un engagement : c'est la liste de lecture dont part la version suivante.

- **`RouteLLM` — router par requête, non une fois par machine** — Il apprend à envoyer les invites faciles vers un modèle bon marché puis les difficiles vers un modèle fort, en jugeant la difficulté avant de répondre. Cet assistant choisit le plus gros modèle qui tient dans la machine : la bonne question posée une fois. La question par requête en est une autre, complémentaire.

- **`AMD Lemonade` — le NPU est une troisième destination** — Router entre processeur puis carte graphique couvre la plupart des machines aujourd'hui ; cela ne durera pas. Lemonade route processeur, carte graphique puis NPU ; un assistant dont tout le métier est « que possède réellement cette machine » devrait connaître la troisième.

- **`LiteLLM` — budgets puis limites de débit dans le routeur lui-même** — Choisir un modèle puis gouverner sa dépense sont d'ordinaire deux bibliothèques. Pour le catalogue payant que cet assistant porte désormais, un budget par clé est la moitié manquante d'une recommandation consciente des prix.

- **`OpenRouter` — publier le prix avec la latence derrière chaque choix** — Il montre le coût puis la vitesse par modèle au moment de choisir. Cet assistant croise déjà une table de prix avec un classement de qualité ; afficher les deux nombres sur la recommandation rend le choix vérifiable plutôt qu'asséné.
