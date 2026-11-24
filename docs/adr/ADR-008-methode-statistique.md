# ADR-008 — Médiane, IC bootstrap, Mann-Whitney, delta de Cliff, correction de Holm

**Statut :** acceptée

## Contexte
Il y a 5 répétitions par cas. Les distributions sont souvent **non normales** : bornées à 0 % et 100 %, bimodales quand le disjoncteur s'ouvre ou non, avec des valeurs plafonnées à 10 s. De nombreuses comparaisons sont faites, ce qui augmente le risque de trouver une différence « significative » par hasard.

## Décision
- **Valeur rapportée** : la **médiane** des 5 répétitions, comme annoncé dans la proposition, avec un **IC à 95 % par bootstrap** (percentiles, 10 000 tirages). La moyenne, le minimum et le maximum sont aussi dans `aggregate.csv`.
- **Test** : **Mann-Whitney U** bilatéral. Il est non paramétrique et ne suppose pas de distribution normale.
- **Taille d'effet** : **delta de Cliff**, entre −1 et +1. Il dit *de combien* une configuration domine l'autre, pas seulement si elle la domine.
- **Comparaisons multiples** : correction de **Holm** par famille (campagne × scénario × mesure).
- Tout est calculé par `scripts/analyze.py`, avec des versions de bibliothèques figées (`analysis/requirements.txt`) et dans un conteneur Docker.

## Alternatives considérées
- **Moyenne et test t** : ils supposent des distributions normales, ce qui est faux ici. La moyenne a été utilisée dans une première version de l'analyse. Elle donnait les mêmes conclusions (écarts de quelques dixièmes de point).
- **Correction de Bonferroni** : plus conservatrice que Holm, sans avantage.
- **Plus de répétitions** : elles donneraient plus de puissance statistique, mais rendraient la campagne trop longue.

## Conséquences
- (+) Les conclusions ne dépendent pas d'une hypothèse de normalité.
- (−) Avec 5 contre 5 répétitions, la **plus petite valeur p possible est d'environ 0,008**. Après Holm, seules des séparations complètes entre les deux groupes deviennent significatives. Le delta de Cliff et les IC sont donc plus informatifs que la valeur p.
- (−) Un IC bootstrap sur 5 valeurs est grossier. Il indique la dispersion observée, pas une précision fine.
