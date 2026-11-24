# ADR-001 — Spring Boot + Resilience4j au lieu de Quarkus + SmallRye

**Statut :** acceptée (remplace le choix de la proposition)

## Contexte
La proposition prévoyait Quarkus avec SmallRye Fault Tolerance. Pour l'expérience, il faut :
- les trois tactiques (Timeout, Retry, Circuit Breaker), configurables **sans changer le code** ;
- des métriques détaillées sur chaque tactique (état du disjoncteur, tentatives), lisibles par Prometheus ;
- un outillage simple à faire tourner dans Docker et dans VS Code.

## Décision
Les deux services utilisent **Spring Boot 3 (Java 21)**. A utilise **Resilience4j 2.2.0** en mode programmatique : les tactiques entourent un `Supplier`. Le Timeout est réglé sur le client HTTP (`SimpleClientHttpRequestFactory`, connexion et lecture). Les métriques sont exposées par **Micrometer / Actuator** au format Prometheus.

## Alternatives considérées
- **Quarkus + SmallRye Fault Tolerance** (annotations `@Timeout`, `@Retry`, `@CircuitBreaker`). Les annotations sont fixées à la compilation, ce qui rend plus difficile de changer de configuration au démarrage. Les métriques sont aussi moins détaillées.
- **Service mesh (Istio, Linkerd)** : les tactiques seraient placées hors du code. Mais cette solution est beaucoup plus lourde à installer et ne correspond pas à la question posée, qui porte sur les tactiques dans l'application.

## Conséquences
- (+) Une seule image de A sert pour les cinq configurations. Le choix se fait au démarrage par `RESILIENCE_CONFIG`, ce qui supprime les écarts de compilation entre configurations.
- (+) Les métriques `resilience4j_circuitbreaker_state` et `resilience4j_retry_calls_total` sont disponibles directement.
- (−) C'est un écart par rapport à la proposition, à justifier dans le rapport.
- (−) Les résultats dépendent de l'implémentation Resilience4j, par exemple du fonctionnement de l'état semi-ouvert. D'autres bibliothèques peuvent se comporter un peu différemment.
