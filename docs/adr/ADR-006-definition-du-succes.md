# ADR-006 — Succès = réponse 200 en moins de 1 s ; requêtes non envoyées = échecs

**Statut :** acceptée (issue du pilote P2)

## Contexte
Une réponse correcte qui arrive après 8 s est **inutile** pour un client. Compter seulement les statuts 200 donnerait un avantage à C0, qui attend indéfiniment. Par ailleurs, quand A est bloqué, k6 n'arrive plus à envoyer toutes les requêtes prévues. Les ignorer ferait **monter** artificiellement le taux de succès de la pire configuration.

## Décision
- **Succès** : statut HTTP 200 **et** durée de moins de 1000 ms, mesurée côté client. Le seuil de 1 s est le même que le Timeout (ADR-004).
- **Dénominateur** : `max(débit prévu × durée, requêtes envoyées)`. Une requête prévue mais non envoyée compte comme un échec.
- On rapporte aussi, séparément :
  - le **débit** (réponses par seconde, succès et échecs) ;
  - le **débit utile** (succès par seconde) ;
  - les percentiles p50, p95 et p99 ;
  - la répartition des raisons d'échec (TIMEOUT, CIRCUIT_OPEN, PAYMENT_ERROR, CLIENT_TIMEOUT…).

## Alternatives considérées
- **Succès = statut 200 seulement** : rejetée pour la raison donnée plus haut.
- **Seuil de 2 s ou 500 ms** : choix arbitraire. Le seuil de 1 s a l'avantage d'être cohérent avec le Timeout.

## Conséquences
- (+) Le « succès » mesuré correspond à ce que voit un utilisateur.
- (+) Les configurations sont comparées sur la même base, même quand le système est saturé.
- (−) Le taux de succès dépend du seuil choisi. C'est pourquoi les percentiles sont aussi rapportés.
- (−) Les pourcentages du pilote, calculés avant cette règle, ne sont pas directement comparables à ceux de la campagne.
