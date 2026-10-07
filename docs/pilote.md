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

### Tableau P2 (une exécution de 60 s par combinaison)

| Charge | Exécution | Cmd OK % | Cmd p95 (ms) | Catalogue OK % | Catalogue p95 (ms) | Amplification | Threads A | Disjoncteur ouvert % | Perdues |
|---|---|---|---|---|---|---|---|---|---|
| 100 | C0_S0_r1 | 100.0 | 54 | 100.0 | 1 | 1.00 | 4 | 0 | 0 |
| 100 | C0_S1_r1 | 100.0 | 554 | 100.0 | 1 | 1.00 | 29 | 0 | 0 |
| 100 | C0_S2_r1 | 14.3 | 10001 | 17.7 | 10001 | 1.00 | 15 | 0 | 392 |
| 100 | C0_S3_r1 | 71.8 | 55 | 100.0 | 1 | 1.00 | 4 | 0 | 0 |
| 100 | C0_S4_r1 | 29.8 | 55 | 100.0 | 1 | 1.00 | 4 | 0 | 0 |
| 100 | C0_S5a_r1 | 0.0 | 2 | 100.0 | 1 | 0.00 | 1 | 0 | 0 |
| 100 | C0_S5b_r1 | 0.0 | 10001 | 1.8 | 10001 | 1.02 | 21 | 0 | 401 |
| 100 | C0_S6_r1 | 81.0 | 10001 | 83.3 | 10001 | 1.02 | 50 | 0 | 305 |
| 100 | C1_S0_r1 | 100.0 | 54 | 100.0 | 1 | 1.00 | 6 | 0 | 0 |
| 100 | C1_S1_r1 | 100.0 | 554 | 100.0 | 1 | 1.00 | 29 | 0 | 0 |
| 100 | C1_S2_r1 | 0.0 | 1155 | 100.0 | 169 | 1.00 | 50 | 0 | 0 |
| 100 | C1_S3_r1 | 70.1 | 55 | 100.0 | 1 | 1.00 | 4 | 0 | 0 |
| 100 | C1_S4_r1 | 30.6 | 55 | 100.0 | 1 | 1.00 | 4 | 0 | 0 |
| 100 | C1_S5a_r1 | 0.0 | 2 | 100.0 | 1 | 0.00 | 1 | 0 | 0 |
| 100 | C1_S5b_r1 | 0.0 | 1160 | 100.0 | 174 | 1.00 | 50 | 0 | 0 |
| 100 | C1_S6_r1 | 68.3 | 1038 | 100.0 | 39 | 1.02 | 50 | 0 | 0 |
| 100 | C2_S0_r1 | 100.0 | 54 | 100.0 | 1 | 1.00 | 5 | 0 | 0 |
| 100 | C2_S1_r1 | 100.0 | 554 | 100.0 | 1 | 1.00 | 31 | 0 | 0 |
| 100 | C2_S2_r1 | 0.0 | 10001 | 8.9 | 10001 | 1.75 | 19 | 0 | 393 |
| 100 | C2_S3_r1 | 97.6 | 447 | 100.0 | 1 | 1.39 | 12 | 0 | 0 |
| 100 | C2_S4_r1 | 65.6 | 564 | 100.0 | 1 | 2.20 | 21 | 0 | 0 |
| 100 | C2_S5a_r1 | 0.0 | 405 | 100.0 | 1 | 0.00 | 19 | 0 | 0 |
| 100 | C2_S5b_r1 | 0.0 | 10001 | 8.9 | 10001 | 1.77 | 30 | 0 | 393 |
| 100 | C2_S6_r1 | 82.3 | 10001 | 90.4 | 10000 | 1.23 | 50 | 0 | 246 |
| 100 | C3_S0_r1 | 100.0 | 54 | 100.0 | 1 | 1.00 | 4 | 0 | 0 |
| 100 | C3_S1_r1 | 100.0 | 554 | 100.0 | 1 | 1.00 | 29 | 0 | 0 |
| 100 | C3_S2_r1 | 0.0 | 2 | 100.0 | 1 | 0.02 | 44 | 87 | 0 |
| 100 | C3_S3_r1 | 23.3 | 54 | 100.0 | 1 | 0.33 | 4 | 65 | 0 |
| 100 | C3_S4_r1 | 1.0 | 2 | 100.0 | 1 | 0.03 | 4 | 94 | 0 |
| 100 | C3_S5a_r1 | 0.0 | 2 | 100.0 | 1 | 0.00 | 4 | 95 | 0 |
| 100 | C3_S5b_r1 | 0.0 | 2 | 100.0 | 1 | 0.02 | 37 | 85 | 0 |
| 100 | C3_S6_r1 | 62.8 | 55 | 100.0 | 1 | 0.65 | 35 | 32 | 0 |
| 100 | C4_S0_r1 | 100.0 | 54 | 100.0 | 1 | 1.00 | 6 | 0 | 0 |
| 100 | C4_S1_r1 | 100.0 | 554 | 100.0 | 1 | 1.00 | 31 | 0 | 0 |
| 100 | C4_S2_r1 | 0.0 | 2 | 100.0 | 1 | 0.02 | 47 | 85 | 0 |
| 100 | C4_S3_r1 | 16.1 | 159 | 100.0 | 1 | 0.23 | 9 | 79 | 0 |
| 100 | C4_S4_r1 | 0.3 | 2 | 100.0 | 1 | 0.01 | 11 | 95 | 0 |
| 100 | C4_S5a_r1 | 0.0 | 2 | 100.0 | 1 | 0.00 | 5 | 95 | 0 |
| 100 | C4_S5b_r1 | 0.0 | 2 | 100.0 | 1 | 0.02 | 50 | 87 | 0 |
| 100 | C4_S6_r1 | 62.8 | 54 | 100.0 | 1 | 0.65 | 34 | 32 | 0 |
| 200 | C0_S3_r1 | 70.1 | 62 | 100.0 | 1 | 1.00 | 8 | 0 | 0 |
| 200 | C0_S4_r1 | 29.0 | 73 | 100.0 | 1 | 1.00 | 7 | 0 | 0 |
| 200 | C1_S3_r1 | 71.0 | 56 | 100.0 | 1 | 1.00 | 11 | 0 | 0 |
| 200 | C1_S4_r1 | 30.4 | 63 | 100.0 | 1 | 1.00 | 8 | 0 | 0 |
| 200 | C2_S3_r1 | 97.4 | 447 | 100.0 | 1 | 1.39 | 20 | 0 | 0 |
| 200 | C2_S4_r1 | 65.0 | 6212 | 100.0 | 5493 | 2.20 | 50 | 0 | 479 |
| 200 | C3_S3_r1 | 3.3 | 51 | 100.0 | 1 | 0.05 | 6 | 90 | 0 |
| 200 | C3_S4_r1 | 0.3 | 1 | 100.0 | 1 | 0.01 | 3 | 95 | 0 |
| 200 | C4_S3_r1 | 10.0 | 53 | 100.0 | 1 | 0.14 | 17 | 85 | 0 |
| 200 | C4_S4_r1 | 0.5 | 2 | 100.0 | 1 | 0.02 | 4 | 95 | 0 |

## P3 : stabilité (120 s, 3 répétitions)
- C1/S3 : 69,7 / 70,4 / 69,8 % ; C1/S5b : catalogue p95 289 / 274 / 292 ms ; C3/S5b : quasi identique.
- C2/S4 à 200 req/s : 64,8 / 66,1 / 65,1 % ; catalogue p95 environ 6,2 s ; amplification 2,18-2,21.
- C3/S3 plus variable (10,6 / 18,2 / 17,8 %), à cause des ouvertures aléatoires du disjoncteur ;
  l'écart avec C1 (environ 70 %) reste très supérieur à la variation.
- Certains effets s'aggravent avec la durée (C1/S5b : catalogue p95 169 ms à 60 s, environ 285 ms à 120 s).

## Décisions pour la campagne principale
- Charges : 100 req/s (modérée) et 200 req/s (élevée).
- Scénarios : S0, S1, S2, S3, S4, S5b, S6 à 100 req/s ; S0, S3, S4, S5b à 200 req/s. S5a retiré.
- Mesure de 120 s après 15 s de préchauffage ; S6 = 60 s normal, 30 s de panne, 30 s de retour.
- 5 répétitions, ordre aléatoire (graine 42). Total : 275 exécutions.
- Analyse : succès = réponse 2xx en moins de 1 s ; requêtes non envoyées comptées comme échecs.

### Tableau P3 (3 répétitions de 120 s par combinaison)

| Charge | Exécution | Cmd OK % | Cmd p95 (ms) | Catalogue OK % | Catalogue p95 (ms) | Amplification | Threads A | Disjoncteur ouvert % | Perdues |
|---|---|---|---|---|---|---|---|---|---|
| 100 | C1_S3_r1 | 69.7 | 55 | 100.0 | 1 | 1.00 | 6 | 0 | 0 |
| 100 | C1_S3_r2 | 70.4 | 54 | 100.0 | 1 | 1.00 | 6 | 0 | 0 |
| 100 | C1_S3_r3 | 69.8 | 55 | 100.0 | 1 | 1.00 | 5 | 0 | 0 |
| 100 | C1_S5b_r1 | 0.0 | 1290 | 100.0 | 289 | 1.00 | 50 | 0 | 0 |
| 100 | C1_S5b_r2 | 0.0 | 1276 | 100.0 | 274 | 1.00 | 50 | 0 | 0 |
| 100 | C1_S5b_r3 | 0.0 | 1279 | 100.0 | 292 | 1.00 | 50 | 0 | 0 |
| 100 | C3_S3_r1 | 10.6 | 53 | 100.0 | 1 | 0.15 | 4 | 83 | 0 |
| 100 | C3_S3_r2 | 18.2 | 53 | 100.0 | 1 | 0.26 | 5 | 72 | 0 |
| 100 | C3_S3_r3 | 17.8 | 53 | 100.0 | 1 | 0.25 | 4 | 73 | 0 |
| 100 | C3_S5b_r1 | 0.0 | 2 | 100.0 | 1 | 0.01 | 34 | 88 | 0 |
| 100 | C3_S5b_r2 | 0.0 | 2 | 100.0 | 1 | 0.01 | 43 | 89 | 0 |
| 100 | C3_S5b_r3 | 0.0 | 2 | 100.0 | 1 | 0.01 | 45 | 89 | 0 |
| 200 | C2_S4_r1 | 64.8 | 6988 | 100.0 | 6188 | 2.20 | 50 | 0 | 1258 |
| 200 | C2_S4_r2 | 66.1 | 6903 | 100.0 | 6151 | 2.18 | 50 | 0 | 1106 |
| 200 | C2_S4_r3 | 65.1 | 6976 | 100.0 | 6182 | 2.21 | 50 | 0 | 1344 |
