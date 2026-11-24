# Décisions d'architecture (ADR)

Chaque fichier décrit **une** décision : son contexte, le choix fait, les alternatives écartées et ses conséquences. Le format suit Nygard (2011).

| N° | Décision | Statut |
|---|---|---|
| [ADR-001](ADR-001-pile-technologique.md) | Spring Boot + Resilience4j au lieu de Quarkus + SmallRye | Acceptée |
| [ADR-002](ADR-002-systeme-sous-test.md) | Deux services aux ressources bornées et un endpoint témoin `/catalog` | Acceptée |
| [ADR-003](ADR-003-injection-de-pannes.md) | Pannes injectées par Toxiproxy (réseau) et par B (erreurs HTTP) | Acceptée |
| [ADR-004](ADR-004-parametres-des-tactiques.md) | Paramètres des tactiques et ordre Retry → Circuit Breaker | Acceptée |
| [ADR-005](ADR-005-generation-de-charge.md) | Charge en modèle ouvert (k6, débit constant) | Acceptée |
| [ADR-006](ADR-006-definition-du-succes.md) | Succès = 200 en moins de 1 s, requêtes non envoyées = échecs | Acceptée |
| [ADR-007](ADR-007-orchestration.md) | Orchestrateur automatique : ordre aléatoire, remise à zéro, vérification d'état | Acceptée |
| [ADR-008](ADR-008-methode-statistique.md) | Médiane, bootstrap, Mann-Whitney, delta de Cliff, Holm | Acceptée |
| [ADR-009](ADR-009-perimetre-campagne.md) | Périmètre de la campagne : 275 exécutions, S5a retiré | Acceptée |
