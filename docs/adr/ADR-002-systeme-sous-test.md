# ADR-002 — Deux services aux ressources bornées et un endpoint témoin

**Statut :** acceptée

## Contexte
Une défaillance en cascade n'apparaît que si les ressources sont **limitées** : un nombre de fils fini, du CPU borné. Sur une machine puissante sans limites, A ne saturerait jamais. Pour répondre à la question RQ3 (isolation), il faut aussi pouvoir observer si la panne de B touche une partie de A qui **ne dépend pas** de B.

## Décision
- **B (paiement)** : 10 fils Tomcat, 50 ms de traitement, 0,5 CPU, 512 Mo. Un endpoint `/admin/config` règle à chaud le taux d'erreurs 500 et le délai.
- **A (commandes)** : 50 fils Tomcat, 1 CPU, 512 Mo.
  - `/order` appelle B une fois.
  - `/catalog` répond sans appeler B. C'est le **témoin d'isolation** : il partage le pool de fils de A avec `/order`.
- La charge est répartie à 50 % sur `/order` et 50 % sur `/catalog`.
- Les limites sont fixées dans `docker-compose.yml` et sont les mêmes pour toutes les exécutions.

## Alternatives considérées
- **Une chaîne de 3 services ou plus** : plus réaliste, mais plus de variables à contrôler et plus d'exécutions nécessaires.
- **Une application de démonstration existante** (Online Boutique, TeaStore) : beaucoup de composants sans rapport avec la question, et la capacité est difficile à calibrer.
- **Des cloisons (bulkhead) séparées pour `/catalog`** : elles cacheraient justement l'effet qu'on veut mesurer.

## Conséquences
- (+) La loi de Little permet de prévoir la saturation de A (capacité ≈ 50 fils ÷ durée d'un appel à B), à comparer aux 50 commandes/s envoyées :
  - **C0 en S2** (2 s par appel) : 25 commandes/s au maximum. La file d'attente grossit sans fin, et le débit mesuré tombe à 3,3 réponses/s.
  - **C1 en S2** (coupé à 1 s) : 50/s, exactement la demande. A tient « de justesse », et le catalogue p95 monte à ~300 ms.
  - **C2 en S2** (3 tentatives ≈ 3,3 s) : ≈ 15/s. Effondrement, avec un débit mesuré de 1,2 réponse/s.
- (+) La propagation de la panne se lit directement sur le taux de succès et la latence de `/catalog`.
- (−) Le système est volontairement simple : un seul appel par requête et une seule dépendance. La généralisation est limitée (voir le rapport, « Menaces à la validité »).
