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
