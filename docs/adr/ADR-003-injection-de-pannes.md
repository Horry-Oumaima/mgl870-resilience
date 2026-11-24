# ADR-003 — Injection des pannes : Toxiproxy pour le réseau, B pour les erreurs HTTP

**Statut :** acceptée

## Contexte
Les scénarios demandent quatre sortes de pannes : de la latence (S1, S2), des erreurs HTTP 500 (S3, S4), un service qui ne répond plus (S5b, S6) et une panne temporaire suivie d'un retour (S6). Chaque panne doit pouvoir être **appliquée, vérifiée et retirée** par un script, sans redémarrer A.

## Décision
- **Toxiproxy 2.9.0** est placé entre A et B. A appelle `toxiproxy:8666`, qui relaie vers `payment:8081`.
  - Latence : toxique `latency` (500 ms ou 2000 ms).
  - Silence : toxique `timeout` avec `timeout=0`. La connexion reste ouverte mais aucune réponse n'arrive.
- **Les erreurs 500 sont produites par B lui-même**, via `/admin/config?errorRate=…`. Chaque requête échoue au hasard avec cette probabilité, indépendamment des autres.
- `scripts/scenario.sh` regroupe ces actions (S0 à S6, `reset`, `status`). Pour S6, il note l'heure exacte de chaque événement dans `events.log`.

## Alternatives considérées
- **Arrêter le conteneur B** (`docker stop`) : le redémarrage est lent et imprécis, et le comportement est celui d'une connexion refusée (S5a), pas d'un silence.
- **Chaos Mesh / Litmus** : ces outils demandent Kubernetes, ce qui est trop lourd pour ce projet.
- **Faire produire les erreurs 500 par Toxiproxy** : impossible, Toxiproxy travaille au niveau TCP.

## Conséquences
- (+) Les pannes sont activées et retirées en moins d'une seconde, et leur état peut être lu par l'API (vérifié par l'orchestrateur, voir ADR-007).
- (+) Le silence (S5b) est la panne la plus dangereuse, celle qui bloque des fils. Elle est reproduite fidèlement.
- (−) Les erreurs sont indépendantes entre elles. Les pannes réelles sont souvent groupées dans le temps, ce qui changerait le comportement du Retry et du Circuit Breaker.
- (−) Toxiproxy ajoute un saut réseau. Son coût est mesuré en S0 et il est négligeable (p95 ≈ 54–57 ms pour 50 ms de traitement).
