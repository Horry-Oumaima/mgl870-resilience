# MGL870 — Stratégies de résilience dans une architecture à microservices

**Étude comparative de Timeout, Retry et Circuit Breaker**
Projet individuel MGL870 (ÉTS, automne 2026) — Oumaima Elhorry

Ce dépôt contient tout ce qu'il faut pour **refaire l'expérience de bout en bout** :

- les deux services ;
- l'injection de pannes ;
- la génération de charge ;
- l'orchestrateur de campagne ;
- le script d'analyse statistique ;
- le tableau de bord Grafana.

---

## 1. Ce que fait l'expérience

Un service **A (commandes)** appelle un service **B (paiement)**. On rend B lent ou défaillant, et on mesure comment A se comporte selon la protection qu'il utilise.

```
            k6 (charge constante)
                    │  50 % /order    50 % /catalog
                    ▼
        ┌─────────────────────────┐
        │  A : order-service      │  /catalog : ne dépend PAS de B
        │  Spring Boot, 50 fils   │  /order   : appelle B
        │  + Resilience4j         │
        └───────────┬─────────────┘
                    │ HTTP
                    ▼
        ┌─────────────────────────┐
        │  Toxiproxy (pannes)     │  latence, silence, coupure
        └───────────┬─────────────┘
                    ▼
        ┌─────────────────────────┐
        │  B : payment-service    │  50 ms, 10 fils,
        │  Spring Boot            │  taux d'erreur 500 réglable
        └─────────────────────────┘

  Prometheus (relevé chaque seconde) → Grafana (tableau de bord)
```

L'endpoint `/catalog` sert de **témoin d'isolation**. Il n'utilise pas B, donc s'il ralentit quand B tombe, c'est que la panne s'est propagée dans A (épuisement des fils).

### Configurations comparées (cumulatives)

| Code | Protection dans A | Paramètres |
|---|---|---|
| C0 | aucune | — |
| C1 | Timeout | 1 s (connexion + lecture) |
| C2 | Timeout + Retry | 3 tentatives, attente exponentielle 100 ms ×2, aléa 0,5, sur 5xx et erreurs réseau |
| C3 | Timeout + Circuit Breaker | fenêtre de 20 appels, seuil 50 %, ouvert 10 s, 3 appels de test en semi-ouvert |
| C4 | les trois | le Retry enveloppe le Circuit Breaker |

La configuration est choisie au démarrage de A par la variable `RESILIENCE_CONFIG` (`docker-compose.yml`). Le code est dans `order-service/.../ResilienceConfig.java` et `OrderController.java`.

### Scénarios de panne

| Code | Panne | Comment elle est injectée |
|---|---|---|
| S0 | aucune (référence) | — |
| S1 | latence 500 ms | Toxiproxy `latency` |
| S2 | latence 2 s | Toxiproxy `latency` |
| S3 | 30 % d'erreurs HTTP 500 | B, `/admin/config?errorRate=0.3` |
| S4 | 70 % d'erreurs HTTP 500 | B, `/admin/config?errorRate=0.7` |
| S5b | B ne répond plus | Toxiproxy `timeout` (connexion ouverte, aucune réponse) |
| S6 | 60 s normal → 30 s de panne S5b → retour | `scripts/scenario.sh S6` |

S5a (proxy désactivé, « connexion refusée ») existe dans les scripts mais a été **exclu de la campagne finale**. Voir la section 9.

---

## 2. Prérequis

| Outil | Version utilisée | Remarque |
|---|---|---|
| Docker + Docker Compose v2 | Docker Desktop (WSL2) | seul outil indispensable |
| Python 3 | 3.10 ou plus | uniquement pour lancer l'orchestrateur (aucune bibliothèque externe) |
| Git | — | — |
| Java 21 / Maven | facultatif | la compilation se fait dans Docker |

**Machine de la campagne :** PC Windows, WSL2 Ubuntu, 12 cœurs logiques, 10 Gio de mémoire pour WSL.

Le fichier `%UserProfile%\.wslconfig` contenait :
```
[wsl2]
memory=11GB
swap=4GB
```
Le mode « Resource Saver » de Docker Desktop était désactivé, et la mise en veille de Windows aussi.

Les limites de chaque conteneur sont fixées dans `docker-compose.yml` et sont les mêmes pour toutes les exécutions :

| Conteneur | CPU | Mémoire |
|---|---|---|
| order (A) | 1,0 | 512 Mo |
| payment (B) | 0,5 | 512 Mo |
| k6 | 1,0 | 2 Go |

Le projet a aussi été développé et pré-testé dans GitHub Codespaces (4 cœurs, 15 Go). Le dossier `.devcontainer/` est fourni pour ça.

### Ports utilisés sur la machine

| Port | Service |
|---|---|
| 18080 | A (order-service) — 18080 au lieu de 8080, car 8080 était pris par Oracle sur le PC de mesure |
| 8081 | B (payment-service) |
| 8474 | API Toxiproxy |
| 9090 | Prometheus |
| 3000 | Grafana (sans mot de passe) |

À l'intérieur du réseau Docker, A écoute toujours sur 8080 (`k6` vise `http://order:8080`).

---

## 3. Démarrage rapide (5 minutes)

```bash
git clone https://github.com/Horry-Oumaima/mgl870-resilience.git
cd mgl870-resilience

# Construire et démarrer tout le laboratoire (ici avec la configuration C3)
RESILIENCE_CONFIG=C3 docker compose up -d --build

# Vérifier
curl http://localhost:18080/config     # doit afficher C3
curl http://localhost:18080/order      # une commande
curl http://localhost:18080/catalog    # le témoin
./scripts/scenario.sh status           # état de B et de Toxiproxy
```

### Tester une panne à la main

```bash
./scripts/scenario.sh S5b              # B ne répond plus
./scripts/load.sh essai_c3 100 60s     # 60 s de charge à 100 req/s
./scripts/scenario.sh reset            # retour à la normale
python3 scripts/summarize.py results/essai_c3   # résumé rapide
```

Pendant ce temps, ouvre Grafana sur http://localhost:3000. Le tableau de bord **MGL870 — Résilience** se trouve dans le dossier MGL870. On y voit le disjoncteur s'ouvrir, puis faire un appel de test toutes les 10 s.

Pour changer de configuration :
```bash
RESILIENCE_CONFIG=C0 docker compose up -d order
```

> ⚠️ **Ne lance pas `docker compose down`** si tu veux garder l'historique Prometheus : cette commande supprime le conteneur et ses données. Pour arrêter les conteneurs sans rien perdre, utilise `docker compose stop`.

---

## 4. Reproduire la campagne complète

L'orchestrateur `scripts/campaign.py` fait tout automatiquement, pour chaque exécution, dans un **ordre aléatoire reproductible** (graine 42) :

1. redémarrer A, B et Toxiproxy ;
2. vérifier la configuration ;
3. préchauffer 15 s sans panne ;
4. appliquer la panne **et vérifier qu'elle est active** ;
5. mesurer 120 s ;
6. vérifier que la panne était encore active à la fin ;
7. sauvegarder les métriques ;
8. tout remettre à zéro.

Une exécution qui échoue à une vérification est marquée `invalide` dans son `metadata.json`.

```bash
# Toujours vérifier le plan avant de lancer
python3 scripts/campaign.py --name campagne_r100 --rate 100 --duration 120s --warmup 15s \
        --scenarios S0,S1,S2,S3,S4,S5b,S6 --dry-run

# Campagne 1 : charge modérée, 7 scénarios × 5 configurations × 5 répétitions = 175 exécutions (~10 h)
python3 scripts/campaign.py --name campagne_r100 --rate 100 --duration 120s --warmup 15s \
        --scenarios S0,S1,S2,S3,S4,S5b,S6

# Campagne 2 : charge élevée, 4 scénarios × 5 × 5 = 100 exécutions (~6 h)
python3 scripts/campaign.py --name campagne_r200 --rate 200 --duration 120s --warmup 15s \
        --scenarios S0,S3,S4,S5b
```

- **Reprise :** si la machine s'arrête, relance exactement la même commande. Les exécutions déjà `ok` ne sont pas refaites.
- **Pendant la campagne,** n'utilise pas la machine pour d'autres tâches lourdes (navigateur chargé, analyse, compilation). Elles fausseraient les mesures.
- **Vérifier les paramètres réellement utilisés :** ils sont écrits dans chaque `metadata.json`.
  ```bash
  python3 -c "import json;m=json.load(open('results/campagne_r100/C0_S0_r1/metadata.json'));print({k:m[k] for k in ['rate','duration','warmup','seed','git_commit','status']})"
  ```
- **Compter les exécutions valides :**
  ```bash
  grep -l '"status": "ok"' results/campagne_r*/*/metadata.json | wc -l    # attendu : 275
  ```

Résultat obtenu : **275 exécutions sur 275 valides** (commit `52430bc`).

### Ce qui est enregistré pour chaque exécution

Chaque exécution a son dossier : `results/<campagne>/<config>_<scénario>_r<rép>/`.

| Fichier | Contenu |
|---|---|
| `requests.log` | une ligne JSON par requête k6 : heure, endpoint, statut, durée, raison de l'échec |
| `summary.json` | résumé k6 |
| `metrics_before_*.txt` / `metrics_after_*.txt` | compteurs Prometheus de A et B avant et après la mesure (sert à calculer l'amplification) |
| `prometheus_series.json` | séries seconde par seconde : fils occupés de A et B, état du disjoncteur, CPU, mémoire |
| `metadata.json` | paramètres, commit git, heures de début et de fin, vérifications de l'état, statut |
| `events.log` | S6 seulement : heures exactes du début et de la fin de la panne |

Le dossier `results/` n'est **pas versionné** (trop volumineux). Une copie a été gardée à part.

---

## 5. Analyse

```bash
./scripts/analyze.sh                 # analyse campagne_r100 et campagne_r200
python3 scripts/grafana_links.py     # liens Grafana pour chaque exécution (option --rep 1 à 5)
```

`analyze.sh` lance l'analyse dans un conteneur `python:3.12-slim`, avec les versions figées de `analysis/requirements.txt` (numpy 2.1.3, pandas 2.2.3, scipy 1.14.1, matplotlib 3.9.2). Il n'y a rien à installer sur la machine.

### Fichiers produits dans `analysis/`

| Fichier | Contenu |
|---|---|
| `runs.csv` | une ligne par exécution (275 lignes), avec toutes les mesures |
| `aggregate.csv` | par campagne × scénario × configuration : médiane, IC 95 %, moyenne, min, max |
| `comparisons.csv` | tests statistiques entre configurations (voir plus bas) |
| `recovery_timeline.csv` | S6 : taux de succès seconde par seconde |
| `decision_matrix.md` | les tableaux de synthèse utilisés dans le rapport |
| `key_numbers.md` | les chiffres clés par hypothèse |
| `figures/*.png` | 11 figures |
| `grafana_links.html` | un lien Grafana par scénario × configuration |

### Définitions des mesures

| Mesure | Définition |
|---|---|
| **Succès** | réponse HTTP 200 reçue en **moins de 1 s**. Une requête prévue mais non envoyée (k6 saturé) compte comme un échec : le dénominateur est `max(débit prévu × durée, requêtes envoyées)`. |
| **Débit utile** (goodput) | succès par seconde |
| **Débit** | réponses reçues par seconde, succès et échecs confondus |
| **p50 / p95 / p99** | percentiles de la durée vue par le client (k6). Le client abandonne à 10 s. |
| **Amplification** | appels reçus par B ÷ commandes envoyées, calculée à partir des compteurs avant/après. Valeur absente (« – ») quand A était bloqué et que Prometheus ne pouvait pas lire ses compteurs. |
| **Disjoncteur ouvert** | % des secondes de mesure où l'état est `open` |
| **Temps de récupération (S6)** | délai entre la fin de la panne et la première fenêtre de 5 secondes consécutives à au moins 99 % de succès |

### Méthode statistique

- 5 répétitions par cas. On rapporte la **médiane** avec un **intervalle de confiance à 95 % par bootstrap** (percentiles, 10 000 tirages).
- Les comparaisons se font avec le test de **Mann-Whitney** bilatéral et la taille d'effet **delta de Cliff**.
- Correction de **Holm** par famille (campagne, scénario, mesure).
- Avec 5 contre 5 répétitions, la plus petite valeur p possible est environ 0,008. Un résultat « significatif après Holm » demande donc une séparation complète des deux groupes.

---

## 6. Tableau de bord Grafana

Le tableau de bord est chargé automatiquement depuis `grafana/provisioning/dashboards/`. Il affiche :

- l'état de A et de B (up) ;
- l'état du disjoncteur ;
- les fils Tomcat occupés de A et de B ;
- les commandes par résultat ;
- les appels reçus par B ;
- les tentatives du Retry ;
- la configuration active.

`analysis/grafana_links.html` ouvre ce tableau de bord exactement sur la période d'une exécution : 25 s avant le début et 10 s après la fin. Cela ne marche que si le conteneur Prometheus de la campagne existe toujours (voir l'avertissement de la section 3).

---

## 7. Organisation du dépôt

```
.devcontainer/          environnement GitHub Codespaces
payment-service/        Service B (Spring Boot) : /payment, /admin/config
order-service/          Service A (Spring Boot + Resilience4j) : /order, /catalog, /config
toxiproxy/              définition du proxy entre A et B
prometheus/             configuration du relevé (1 s)
grafana/provisioning/   source de données + tableau de bord
k6/load.js              charge à débit constant, journal de chaque requête
scripts/
  scenario.sh           applique un scénario (S0 à S6, reset, status)
  load.sh               lance une charge k6 seule
  campaign.py           orchestrateur de la campagne
  summarize.py          résumé rapide d'une exécution
  analyze.sh / .py      analyse statistique et figures
  grafana_links.py      page de liens Grafana
analysis/               résultats de l'analyse (versionnés)
docs/pilote.md          essais pilotes : choix du débit, balayage, stabilité
docs/adr/               décisions d'architecture (ADR)
results/                données brutes (non versionnées)
```

---

## 8. Choix de calibrage (essais pilotes)

Ces choix sont détaillés dans `docs/pilote.md` et ses fichiers CSV :

- **B limité à 10 fils, 50 ms et 0,5 CPU** : le système sature entre 200 et 300 req/s au total (pilote P1). Les ressources sont donc assez petites pour que la saturation soit observable.
- **A limité à 50 fils** : avec un timeout de 1 s, A peut absorber environ 50 commandes lentes par seconde avant d'épuiser ses fils (loi de Little).
- **Charges de 100 et 200 req/s** : 200 req/s est juste sous le point de rupture. En S4, les nouvelles tentatives du Retry (×2,2) poussent alors B au-delà de sa capacité.
- **Durées 15 s + 120 s** : la variabilité entre répétitions était déjà faible avec cette durée en pilote.

---

## 9. Écarts par rapport à la proposition

| Proposition | Réalisé | Raison |
|---|---|---|
| Quarkus / SmallRye | Spring Boot / Resilience4j | écosystème mieux documenté, métriques Micrometer prêtes à l'emploi |
| semi-ouvert : « 3 succès requis » | 3 appels de test autorisés | comportement réel de Resilience4j |
| 3 min dont 30 s de préchauffage | 15 s de préchauffage séparé + 120 s de mesure | pilotes stables ; campagne réalisable en une nuit et demie |
| S5a (connexion refusée) | exclu | en pilote, toutes les configurations échouent immédiatement (~2 ms) et le catalogue reste intact : scénario peu discriminant (`docs/pilote.md`) |
| forte charge sur S6 | forte charge sur S0, S3, S4, S5b | S4 est le cas où le Retry peut saturer B |
| 325 exécutions, « 9 scénarios » | 275 exécutions, 8 scénarios définis (7 retenus) | le « 9 » de la proposition était une erreur de compte |
| notebook Jupyter | script Python reproductible | s'exécute en une commande, versions figées |

## 10. Limites connues

- Un seul jeu de paramètres pour le Circuit Breaker et le Retry : il n'y a pas d'analyse de sensibilité.
- S1, S2 et S6 n'ont été mesurés qu'à 100 req/s.
- Il n'y a qu'une machine et un seul appel entre deux services. Les erreurs injectées sont indépendantes entre elles, ce qui n'est pas toujours le cas des pannes réelles.
- L'amplification est absente pour C0 et C2 en S2 et S5b : A était bloqué et ses compteurs n'ont pas pu être lus.
- Les 41 premières exécutions ont tourné avec 7,7 Gio de mémoire pour WSL au lieu de 10 Gio. Les limites de chaque conteneur étaient les mêmes.
- La mémoire de A et de B est enregistrée mais n'est pas analysée.
