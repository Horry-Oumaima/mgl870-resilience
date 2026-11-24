# ADR-009 — Périmètre de la campagne : 275 exécutions, S5a retiré

**Statut :** acceptée (issue des pilotes P1 à P3, voir `docs/pilote.md`)

## Contexte
Croiser 5 configurations, 8 scénarios, 2 charges et 5 répétitions donnerait 400 exécutions (plus de 22 h). Le temps machine disponible était limité, et certaines combinaisons apportent peu d'information.

## Décision
- **Charges** : 100 req/s (modérée) et 200 req/s (élevée). Le pilote P1 place le point de rupture du système entre 200 et 300 req/s.
- **À 100 req/s** : S0, S1, S2, S3, S4, S5b, S6, soit 7 × 5 × 5 = **175 exécutions**.
- **À 200 req/s** : S0, S3, S4, S5b, soit 4 × 5 × 5 = **100 exécutions**. Ce sont les scénarios où la charge peut changer le classement des configurations, en particulier S4, où le Retry multiplie les appels à B.
- **S5a (connexion refusée) retiré** : en pilote, toutes les configurations échouent en moins de 2 ms et le catalogue reste intact. Ce scénario ne distingue pas les tactiques.
- **Durée** : 15 s de préchauffage + 120 s de mesure. S6 = 60 s normal, 30 s de panne, 30 s de retour.

## Alternatives considérées
- **Plan complet (400 exécutions)** : trop long pour le temps disponible.
- **3 répétitions au lieu de 5** : trop peu pour les tests statistiques (ADR-008).
- **Forte charge sur S6** (proposition) : remplacée par S4, plus révélatrice des risques du Retry.

## Conséquences
- (+) La campagne a duré environ 15 h, en une nuit et une journée.
- (+) Le résultat le plus marquant de l'étude est visible : à 200 req/s en S4, C2 s'effondre (3,3 % de succès, catalogue à 8,4 %).
- (−) S1, S2 et S6 n'ont pas été mesurés à forte charge.
- (−) La proposition annonçait 325 exécutions et « 9 scénarios ». Cet écart est expliqué dans le rapport.
