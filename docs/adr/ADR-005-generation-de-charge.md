# ADR-005 — Charge en modèle ouvert (k6, débit constant)

**Statut :** acceptée

## Contexte
Dans un modèle **fermé**, des utilisateurs virtuels attendent chaque réponse avant d'envoyer la requête suivante. Quand le système ralentit, la charge baisse toute seule, et la défaillance en cascade est **cachée** (problème appelé « coordinated omission »). Or les vrais clients d'un service web n'attendent pas les autres.

## Décision
- **k6 0.52.0** avec l'exécuteur `constant-arrival-rate` : un débit fixe (100 ou 200 req/s au total), quelle que soit la vitesse des réponses. On a jusqu'à 600 utilisateurs virtuels par endpoint.
- Le **client abandonne après 10 s**. Cela borne la durée maximale mesurée.
- **Chaque requête est écrite** dans `requests.log` : heure, endpoint, statut, durée, raison de l'échec. L'analyse part de ce journal, pas des moyennes de k6.
- k6 tourne dans un conteneur limité à 1 CPU et 2 Go, sur le même réseau Docker que A.

## Alternatives considérées
- **JMeter / Gatling** : ils sont capables de faire la même chose, mais leurs scripts sont plus lourds. k6 se lance en une ligne dans Docker.
- **Modèle fermé** (`constant-vus`) : il est rejeté pour la raison donnée plus haut.
- **Lire Prometheus seulement** : le pilote a montré que Prometheus devient **aveugle** quand A est saturé, parce qu'il n'arrive plus à lire les métriques de A. Le journal k6 est donc la source principale.

## Conséquences
- (+) Les effets de saturation (catalogue à 0,8 % en C0/S5b) sont visibles. Un modèle fermé les aurait masqués.
- (+) Toutes les mesures (percentiles, succès, débit, récupération seconde par seconde) se recalculent à partir des données brutes.
- (−) Si A ne répond plus, k6 peut manquer d'utilisateurs virtuels et ne pas envoyer certaines requêtes. Elles sont comptées comme des échecs (voir ADR-006).
- (−) Le générateur et le système sont sur la même machine. Les limites CPU des conteneurs réduisent ce problème sans le supprimer.
