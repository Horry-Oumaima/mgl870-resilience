# Notes du pilote

## P0 : environnement d'exécution
- GitHub Codespaces : 4 cœurs, 15 Go de mémoire
- Limites des conteneurs : A = 1 CPU / 512 Mo, B = 0,5 CPU / 512 Mo, k6 = 1 CPU / 2 Go

## P1 : capacité du système (C0, S0, 60 s par niveau)
| Charge totale (req/s) | p95 commandes | Threads B max | Threads A max | p95 catalogue |
|---|---|---|---|---|
| 50  | 54 ms   | 3  | 3  | 2 ms    |
| 100 | 53 ms   | 3  | 5  | 1 ms    |
| 200 | 55 ms   | 9  | 9  | 1 ms    |
| 300 | 101 ms  | 10 | 29 | 1 ms    |
| 400 | 1868 ms | 10 | 50 | 1618 ms |

Constat : point de rupture entre 200 et 300 req/s ; B atteint 100 % de son CPU (0,5) à 300 req/s.
Décision provisoire : charge modérée = 100 req/s, charge élevée = 200 req/s.

## P2 : balayage configurations x scénarios (60 s, 1 répétition)
- S0 : aucun surcoût mesurable des tactiques (p95 = 54 ms partout).
- S1 : aucune différence entre configurations (latence sous le Timeout).
- S2/S5b : C0 et C2 font s'effondrer le catalogue ; C1 le protège de justesse (A saturé) ; C3/C4 l'isolent totalement.
- S3 : Retry 97,6 % (théorie 97,3 %), amplification 1,39 ; disjoncteur ouvert à tort 65-79 % du temps (succès 16-23 %).
- S4 : Retry 65,6 % (théorie 65,7 %), amplification 2,20 ; disjoncteur ouvert 94 %.
- S4 à 200 req/s : le Retry surcharge B, cascade jusqu'au catalogue (p95 5,5 s).
- S5a : peu discriminant, retiré de la campagne.
Leçons : (1) Prometheus aveugle quand A est saturé, k6 = source principale ;
(2) succès = réponse 2xx en moins de 1 s ; (3) requêtes non envoyées = échecs.
