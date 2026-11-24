# ADR-007 — Orchestrateur automatique : ordre aléatoire, remise à zéro, vérification d'état

**Statut :** acceptée

## Contexte
La campagne comprend 275 exécutions d'environ 3 minutes chacune, soit plus de 15 heures. Plusieurs biais sont possibles :
- un état qui reste d'une exécution à la suivante (fils bloqués, disjoncteur ouvert, connexions) ;
- une dérive de la machine dans le temps (température, autres processus), qui toucherait toujours la même configuration si l'ordre était fixe ;
- une panne qui n'est pas réellement appliquée. C'est arrivé pendant le développement : une démonstration C3/S5b était invalide parce que B démarrait encore.

## Décision
`scripts/campaign.py` exécute, pour chaque exécution :
1. un redémarrage de A, B et Toxiproxy avec la bonne configuration, et une vérification de `/config` ;
2. 15 s de préchauffage sans panne (non analysées) ;
3. l'application de la panne, suivie d'une **lecture de l'état réel** (Toxiproxy et B), comparé à l'état attendu ;
4. 120 s de mesure, puis une **deuxième vérification** de l'état ;
5. la sauvegarde des compteurs avant et après, des séries Prometheus et d'un `metadata.json` (paramètres, commit git, horodatage, statut `ok` ou `invalide`) ;
6. une remise à zéro et une pause.

L'ordre des exécutions est **mélangé au hasard avec une graine fixe** (42), ce qui le rend reproductible. Une exécution déjà `ok` n'est jamais refaite : relancer la commande reprend la campagne.

## Alternatives considérées
- **Lancer les exécutions à la main** : trop long, et une source d'erreurs.
- **Ordre fixe** (toutes les C0, puis toutes les C1…) : la dérive dans le temps se confondrait avec l'effet de la configuration.
- **Ne pas redémarrer entre les exécutions** : plus rapide, mais l'état serait transmis d'une exécution à l'autre.

## Conséquences
- (+) 275 exécutions valides sur 275. Chacune est traçable jusqu'au commit qui l'a produite (`52430bc`).
- (+) La campagne a survécu à un arrêt de Docker (mémoire WSL) grâce à la reprise.
- (−) Le redémarrage et le préchauffage ajoutent environ 80 s par exécution.
- (−) Le préchauffage de 15 s est plus court que les 30 s de la proposition. Le pilote P3 a montré une variabilité faible.
