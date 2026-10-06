#!/usr/bin/env python3
"""Résumé rapide d'une ou plusieurs campagnes : une ligne par exécution.
Usage : python3 scripts/summarize.py <campagne1> [<campagne2> ...]"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def counter_total(text, name):
    """Somme de toutes les séries d'un compteur Prometheus (toutes étiquettes confondues)."""
    total = 0.0
    for line in text.splitlines():
        if line.startswith(name + "{") or line.startswith(name + " "):
            total += float(line.rsplit(" ", 1)[1])
    return total


def order_reasons(path):
    """Répartition des résultats des commandes, lue dans le journal k6."""
    reasons = Counter()
    if not path.exists():
        return reasons
    for line in path.read_text(errors="replace").splitlines():
        i, j = line.find("{"), line.rfind("}")
        if i < 0 or j < 0:
            continue
        fragment = line[i:j + 1]
        try:
            rec = json.loads(fragment)
        except json.JSONDecodeError:
            try:
                rec = json.loads(fragment.replace('\\"', '"'))
            except json.JSONDecodeError:
                continue
        if rec.get("ep") == "order":
            reasons[rec.get("r")] += 1
    return reasons


def series_stats(path):
    """Statistiques des séries Prometheus enregistrées pendant la mesure."""
    out = {}
    if not path.exists():
        return out
    data = json.loads(path.read_text())

    def values(key, keep=lambda m: True):
        vals = []
        series = data.get(key)
        if isinstance(series, list):
            for s in series:
                if keep(s["metric"]):
                    vals += [float(v) for _, v in s["values"] if v not in ("NaN", "+Inf", "-Inf")]
        return vals

    for key, label in (("order_threads_busy", "A_threads_max"), ("payment_threads_busy", "B_threads_max"),
                       ("order_cpu", "A_cpu_max"), ("payment_cpu", "B_cpu_max")):
        v = values(key)
        out[label] = max(v) if v else None
    is_open = values("circuit_breaker_state", lambda m: m.get("state") == "open")
    out["cb_open_pct"] = 100 * sum(is_open) / len(is_open) if is_open else None
    return out


def fmt(x, digits=0, suffix=""):
    if x is None:
        return "-"
    return f"{x:.{digits}f}{suffix}"


def main():
    names = sys.argv[1:]
    if not names:
        raise SystemExit(__doc__)
    rows = []
    for name in names:
        for meta_file in sorted((ROOT / "results" / name).glob("*/metadata.json")):
            run_dir = meta_file.parent
            meta = json.loads(meta_file.read_text())
            row = {"campaign": name, "run": meta["run_id"], "rate": meta.get("rate"), "status": meta.get("status")}
            summary_file = run_dir / "summary.json"
            if summary_file.exists():
                s = json.loads(summary_file.read_text())
                o, c = s["order"], s["catalog"]
                row.update({"order_ok_pct": 100 * o["success_rate"] if o["success_rate"] is not None else None,
                            "order_p50": o["p50_ms"], "order_p95": o["p95_ms"], "order_p99": o["p99_ms"],
                            "catalog_ok_pct": 100 * c["success_rate"] if c["success_rate"] is not None else None,
                            "catalog_p95": c["p95_ms"], "dropped": s["dropped_iterations"],
                            "order_requests": o["requests"]})
                before, after = run_dir / "metrics_before_payment.txt", run_dir / "metrics_after_payment.txt"
                if before.exists() and after.exists() and o["requests"]:
                    calls = (counter_total(after.read_text(), "payment_requests_received_total")
                             - counter_total(before.read_text(), "payment_requests_received_total"))
                    row["amplification"] = calls / o["requests"]
            row.update(series_stats(run_dir / "prometheus_series.json"))
            reasons = order_reasons(run_dir / "requests.log")
            row["reasons"] = " ".join(f"{k}:{v}" for k, v in reasons.most_common(3))
            rows.append(row)

    header = f"{'exécution':<14}{'débit':>6}{'cmd%':>7}{'p50':>7}{'p95':>7}{'p99':>7}{'cat%':>7}{'catp95':>8}" \
             f"{'ampli':>7}{'A_thr':>7}{'B_thr':>7}{'CBouv%':>8}{'perdues':>8}  raisons (commandes)"
    print(header)
    print("-" * len(header))
    for r in rows:
        if r["status"] != "ok":
            print(f"{r['run']:<14}{r['rate']:>6}   INVALIDE")
            continue
        print(f"{r['run']:<14}{r['rate']:>6}{fmt(r.get('order_ok_pct'), 1):>7}{fmt(r.get('order_p50')):>7}"
              f"{fmt(r.get('order_p95')):>7}{fmt(r.get('order_p99')):>7}{fmt(r.get('catalog_ok_pct'), 1):>7}"
              f"{fmt(r.get('catalog_p95')):>8}{fmt(r.get('amplification'), 2):>7}{fmt(r.get('A_threads_max')):>7}"
              f"{fmt(r.get('B_threads_max')):>7}{fmt(r.get('cb_open_pct'), 0):>8}{fmt(r.get('dropped')):>8}"
              f"  {r['reasons']}")

    out = ROOT / "results" / "summary_table.csv"
    fields = sorted({k for r in rows for k in r})
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nTableau complet : {out}")


if __name__ == "__main__":
    main()
