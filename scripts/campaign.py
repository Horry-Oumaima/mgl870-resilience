#!/usr/bin/env python3
"""
Orchestrateur de la campagne d'expériences MGL870.
Pour chaque exécution (configuration x scénario x répétition), dans un ordre aléatoire reproductible :
  1. redémarre A, B et Toxiproxy avec la configuration demandée ;
  2. attend que tout soit prêt et vérifie la configuration active ;
  3. préchauffe le système (charge sans panne, non analysée) ;
  4. applique le scénario et VÉRIFIE qu'il est actif ;
  5. lance la charge k6 mesurée ;
  6. vérifie que le scénario était encore actif à la fin ;
  7. sauvegarde les métriques avant/après et les séries Prometheus ;
  8. remet tout à la normale.
Une exécution terminée n'est jamais refaite : relancer la même commande reprend la campagne.
"""
import argparse
import csv
import json
import os
import random
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
A_URL = "http://localhost:8080"
B_URL = "http://localhost:8081"
TOXI_URL = "http://localhost:8474"
PROM_URL = "http://localhost:9090"

# Séries Prometheus enregistrées seconde par seconde pendant la mesure
PROM_QUERIES = {
    "order_threads_busy": 'tomcat_threads_busy_threads{job="order"}',
    "payment_threads_busy": 'tomcat_threads_busy_threads{job="payment"}',
    "circuit_breaker_state": 'resilience4j_circuitbreaker_state{job="order"}',
    "payment_calls_rate": 'sum by (outcome) (rate(payment_requests_received_total[5s]))',
    "order_cpu": 'process_cpu_usage{job="order"}',
    "payment_cpu": 'process_cpu_usage{job="payment"}',
    "order_heap_bytes": 'sum(jvm_memory_used_bytes{job="order",area="heap"})',
}

# État attendu : (sabotages Toxiproxy, proxy actif, taux d'erreur de B, latence en ms)
EXPECTED = {
    "S0":  (set(),       True,  0.0, None),
    "S1":  ({"latence"}, True,  0.0, 500),
    "S2":  ({"latence"}, True,  0.0, 2000),
    "S3":  (set(),       True,  0.3, None),
    "S4":  (set(),       True,  0.7, None),
    "S5a": (set(),       False, 0.0, None),
    "S5b": ({"silence"}, True,  0.0, None),
}
ALL_CONFIGS = ["C0", "C1", "C2", "C3", "C4"]
ALL_SCENARIOS = ["S0", "S1", "S2", "S3", "S4", "S5a", "S5b", "S6"]
LOGFILE = None


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    if LOGFILE:
        with open(LOGFILE, "a") as f:
            f.write(line + "\n")


def parse_seconds(d):
    d = d.strip().lower()
    if d.endswith("ms"):
        return float(d[:-2]) / 1000
    if d.endswith("s"):
        return float(d[:-1])
    if d.endswith("m"):
        return float(d[:-1]) * 60
    return float(d)


def http_get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode()


def sh(cmd, env=None, check=True, timeout=None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(cmd, cwd=ROOT, env=full_env, check=check,
                          capture_output=True, text=True, timeout=timeout)


def git_commit():
    try:
        return sh(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()
    except Exception:
        return "inconnu"


def wait_ready(timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            http_get(f"{A_URL}/actuator/health")
            http_get(f"{B_URL}/actuator/health")
            http_get(f"{TOXI_URL}/version")
            return True
        except Exception:
            time.sleep(1)
    return False


def check_state(expected):
    """Compare l'état réel du laboratoire à l'état attendu."""
    proxy = json.loads(http_get(f"{TOXI_URL}/proxies/payment"))
    cfg = json.loads(http_get(f"{B_URL}/admin/config"))
    toxics = proxy.get("toxics") or []
    names = {t["name"] for t in toxics}
    latency = next((t["attributes"].get("latency") for t in toxics if t["name"] == "latence"), None)
    enabled = proxy.get("enabled", True)
    error_rate = float(cfg["errorRate"])
    exp_names, exp_enabled, exp_err, exp_lat = expected
    ok = (names == exp_names and enabled == exp_enabled and abs(error_rate - exp_err) < 1e-9
          and (exp_lat is None or latency == exp_lat))
    return ok, f"toxics={sorted(names)} enabled={enabled} errorRate={error_rate} latency={latency}"


def scenario(name):
    sh(["./scripts/scenario.sh", name])


def snapshot(run_dir, label):
    for svc, url in (("order", A_URL), ("payment", B_URL)):
        text = http_get(f"{url}/actuator/prometheus", timeout=10)
        (run_dir / f"metrics_{label}_{svc}.txt").write_text(text)


def save_prom_series(run_dir, start, end):
    series = {}
    for key, query in PROM_QUERIES.items():
        params = urllib.parse.urlencode({"query": query, "start": start, "end": end, "step": "1"})
        try:
            series[key] = json.loads(http_get(f"{PROM_URL}/api/v1/query_range?{params}", timeout=30))["data"]["result"]
        except Exception as exc:
            series[key] = {"error": str(exc)}
    (run_dir / "prometheus_series.json").write_text(json.dumps(series))


def execute(run, args, campaign_dir):
    cfg, sc, rep = run["config"], run["scenario"], run["rep"]
    run_id = f"{cfg}_{sc}_r{rep}"
    run_dir = campaign_dir / run_id
    meta_file = run_dir / "metadata.json"

    if meta_file.exists() and json.loads(meta_file.read_text()).get("status") == "ok":
        return "deja_fait"
    if run_dir.exists():
        shutil.rmtree(run_dir)            # une exécution incomplète est refaite entièrement
    run_dir.mkdir(parents=True)

    meta = {"run_id": run_id, "config": cfg, "scenario": sc, "rep": rep, "order": run["order"],
            "rate": args.rate, "duration": args.duration, "warmup": args.warmup, "order_share": 0.5,
            "seed": args.seed, "git_commit": git_commit(), "status": "en_cours"}
    s6_proc = None
    load_timeout = parse_seconds(args.duration) + 180
    try:
        # 1-2. Démarrage propre avec la configuration demandée
        sh(["docker", "compose", "up", "-d", "--force-recreate", "payment", "toxiproxy", "order"],
           env={"RESILIENCE_CONFIG": cfg}, timeout=300)
        if not wait_ready():
            raise RuntimeError("laboratoire non prêt après 180 s")
        active = json.loads(http_get(f"{A_URL}/config"))["resilienceConfig"]
        if active != cfg:
            raise RuntimeError(f"configuration active {active} au lieu de {cfg}")

        # 3. Préchauffage sans panne (non analysé)
        scenario("S0")
        if parse_seconds(args.warmup) > 0:
            sh(["./scripts/load.sh", f"{args.name}/{run_id}/warmup", str(args.rate), args.warmup],
               timeout=parse_seconds(args.warmup) + 180)
        snapshot(run_dir, "before")

        # 4. Application et vérification du scénario
        if sc == "S6":
            env = {**os.environ, "EVENTS_FILE": str(run_dir / "events.log"),
                   "S6_START": str(args.s6_start), "S6_DURATION": str(args.s6_duration)}
            s6_proc = subprocess.Popen(["./scripts/scenario.sh", "S6"], cwd=ROOT, env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
            ok, detail = check_state(EXPECTED["S0"])
        else:
            scenario(sc)
            ok, detail = check_state(EXPECTED[sc])
        meta["state_before"] = detail
        if not ok:
            raise RuntimeError(f"scénario {sc} non appliqué : {detail}")

        # 5. Charge mesurée
        meta["load_start"] = time.time()
        res = sh(["./scripts/load.sh", f"{args.name}/{run_id}", str(args.rate), args.duration],
                 check=False, timeout=load_timeout)
        meta["load_end"] = time.time()
        (run_dir / "k6_output.txt").write_text(res.stdout + res.stderr)
        if res.returncode != 0 or not (run_dir / "summary.json").exists():
            raise RuntimeError("k6 a échoué (voir k6_output.txt)")

        # 6. Le scénario était-il encore actif à la fin ?
        if s6_proc:
            s6_proc.wait(timeout=120)
            events = (run_dir / "events.log").read_text()
            if "fin_panne" not in events:
                raise RuntimeError("S6 incomplet (fin_panne absente)")
            ok, detail = check_state(EXPECTED["S0"])
        else:
            ok, detail = check_state(EXPECTED[sc])
        meta["state_after"] = detail
        if not ok:
            raise RuntimeError(f"scénario {sc} modifié pendant la mesure : {detail}")
        meta["status"] = "ok"
    except Exception as exc:
        meta["status"] = "invalide"
        meta["error"] = str(exc)
    finally:
        if s6_proc and s6_proc.poll() is None:
            s6_proc.terminate()
        try:
            scenario("reset")
        except Exception:
            pass
        # 7. Métriques après et séries Prometheus (non bloquant)
        if "load_end" in meta:
            time.sleep(3)
            for _ in range(10):
                try:
                    snapshot(run_dir, "after")
                    break
                except Exception:
                    time.sleep(3)
            save_prom_series(run_dir, meta["load_start"], meta["load_end"])
        meta_file.write_text(json.dumps(meta, indent=2))
    if meta["status"] != "ok":
        log(f"   ERREUR : {meta.get('error')}")
    return meta["status"]


def main():
    global LOGFILE
    p = argparse.ArgumentParser(description="Orchestrateur de la campagne MGL870")
    p.add_argument("--name", required=True, help="nom de la campagne (dossier dans results/)")
    p.add_argument("--configs", default=",".join(ALL_CONFIGS))
    p.add_argument("--scenarios", default=",".join(ALL_SCENARIOS))
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("--rate", type=int, default=100, help="requêtes par seconde (total)")
    p.add_argument("--duration", default="180s", help="durée de la mesure")
    p.add_argument("--warmup", default="30s", help="durée du préchauffage (0s pour aucun)")
    p.add_argument("--seed", type=int, default=42, help="graine de l'ordre aléatoire")
    p.add_argument("--rest", type=int, default=5, help="pause entre deux exécutions (s)")
    p.add_argument("--s6-start", type=int, default=60)
    p.add_argument("--s6-duration", type=int, default=30)
    p.add_argument("--dry-run", action="store_true", help="affiche le plan sans rien exécuter")
    args = p.parse_args()

    configs = args.configs.split(",")
    scenarios = args.scenarios.split(",")
    if not set(configs) <= set(ALL_CONFIGS) or not set(scenarios) <= set(ALL_SCENARIOS):
        raise SystemExit("Configuration ou scénario inconnu.")
    if "S6" in scenarios and args.s6_start + args.s6_duration >= parse_seconds(args.duration):
        raise SystemExit("Pour S6, s6-start + s6-duration doit être inférieur à la durée de mesure.")

    campaign_dir = ROOT / "results" / args.name
    campaign_dir.mkdir(parents=True, exist_ok=True)
    LOGFILE = campaign_dir / "campaign.log"

    plan = [{"config": c, "scenario": s, "rep": r}
            for c in configs for s in scenarios for r in range(1, args.reps + 1)]
    random.Random(args.seed).shuffle(plan)
    for i, run in enumerate(plan, 1):
        run["order"] = i
    with open(campaign_dir / "plan.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["order", "config", "scenario", "rep"])
        writer.writeheader()
        writer.writerows(plan)

    per_run = 45 + parse_seconds(args.warmup) + parse_seconds(args.duration) + 15 + args.rest
    log(f"Campagne '{args.name}' : {len(plan)} exécutions, durée estimée ~ {len(plan) * per_run / 3600:.1f} h")
    if args.dry_run:
        for run in plan:
            print(f"{run['order']:>4}  {run['config']}  {run['scenario']:<4}  r{run['rep']}")
        return

    # Prometheus et Grafana doivent tourner pour enregistrer les séries
    sh(["docker", "compose", "up", "-d", "prometheus", "grafana"], timeout=300)
    for _ in range(60):
        try:
            http_get(f"{PROM_URL}/-/ready")
            break
        except Exception:
            time.sleep(1)
    else:
        raise SystemExit("Prometheus n'est pas prêt.")

    bilan = {}
    try:
        for run in plan:
            log(f"[{run['order']}/{len(plan)}] {run['config']} {run['scenario']} r{run['rep']}")
            status = execute(run, args, campaign_dir)
            log(f"   -> {status}")
            bilan[status] = bilan.get(status, 0) + 1
            if status != "deja_fait":
                time.sleep(args.rest)
    except KeyboardInterrupt:
        log("Interrompu. Relance la même commande pour reprendre la campagne.")
        try:
            scenario("reset")
        except Exception:
            pass
    log(f"Bilan : {bilan}")


if __name__ == "__main__":
    main()
