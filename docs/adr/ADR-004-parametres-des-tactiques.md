# ADR-004 — Paramètres des tactiques et ordre Retry → Circuit Breaker

**Statut :** acceptée

## Contexte
Chaque tactique a des paramètres, et le résultat dépend d'eux. Il faut des valeurs **courantes en pratique** et cohérentes entre elles. Il faut aussi choisir dans quel ordre combiner les tactiques en C4.

## Décision
| Tactique | Paramètres | Justification |
|---|---|---|
| Timeout | 1 s (connexion et lecture) | ≈ 20 × le temps normal de B (50 ms) : aucun faux timeout en S0 et S1, et il coupe S2 (2 s). |
| Retry | 3 tentatives au total ; attente exponentielle 100 ms × 2 avec aléa de 0,5 ; seulement sur erreur 5xx et erreur réseau ; jamais sur disjoncteur ouvert | Valeurs par défaut courantes. L'aléa évite que toutes les tentatives repartent en même temps (Brooker, AWS). |
| Circuit Breaker | fenêtre des 20 derniers appels (minimum 20) ; ouverture à 50 % d'échecs ; 10 s ouvert ; 3 appels de test en semi-ouvert | Valeurs proches des défauts de Resilience4j, adaptées à 50 commandes/s. |

Les configurations sont **cumulatives** : C1 = Timeout, C2 = C1 + Retry, C3 = C1 + CB, C4 = toutes. Le Timeout est toujours présent dès C1, car sans lui, ni le Retry ni le Circuit Breaker ne voient jamais d'échec en cas de silence.

En **C4**, le Retry **entoure** le Circuit Breaker : `Retry(CircuitBreaker(appel))`.

## Alternatives considérées
- **Circuit Breaker autour du Retry** : le disjoncteur ne verrait qu'un échec par commande, même après 3 tentatives. Les tentatives seraient alors cachées au disjoncteur.
- **Fenêtre basée sur le temps** au lieu du nombre d'appels : avec un débit constant, les deux sont presque équivalentes. La fenêtre en nombre d'appels est plus simple à expliquer.
- **Faire varier les paramètres** (analyse de sensibilité) : elle était prévue au départ, puis retirée pour garder une campagne réalisable.

## Conséquences
- (+) Ce sont des réglages typiques. Les conclusions concernent les tactiques « telles qu'on les configure souvent », pas des réglages optimisés.
- (−) Avec cet ordre, en C4, **chaque nouvelle tentative compte comme un échec de plus dans la fenêtre du disjoncteur**. Le disjoncteur s'ouvre donc aussi souvent qu'en C3, et C4 ≈ C3 dans les résultats. Ce résultat est inattendu et il est discuté dans le rapport.
- (−) Un seuil de 50 % est trop bas pour S3 (30 % d'erreurs). Les variations aléatoires sur 20 appels dépassent souvent 50 %, ce qui déclenche des **ouvertures à tort**. Avec ce réglage, C3 ne réussit que 12,7 % des commandes, contre 70 % sans disjoncteur.
- (−) Les résultats valent pour **un seul jeu de paramètres** (limite déclarée).
