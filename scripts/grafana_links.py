#!/usr/bin/env python3
"""
Crée une page HTML avec un lien Grafana pour chaque combinaison scénario x configuration.
Chaque lien ouvre le tableau de bord « MGL870 — Résilience » sur la période exacte de l'exécution.

Usage : python3 scripts/grafana_links.py [--rep 1] [--grafana http://localhost:3000]
Résultat : analysis/grafana_links.html
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = ["C0", "C1", "C2", "C3", "C4"]
CONFIG_LABELS = {"C0": "C0 aucune protection", "C1": "C1 Timeout", "C2": "C2 Timeout + Retry",
                 "C3": "C3 Timeout + Circuit Breaker", "C4": "C4 les trois"}
SCENARIOS = ["S0", "S1", "S2", "S3", "S4", "S5b", "S6"]
SCENARIO_LABELS = {"S0": "S0 normal", "S1": "S1 latence 500 ms", "S2": "S2 latence 2 s", "S3": "S3 30 % d'erreurs",
                   "S4": "S4 70 % d'erreurs", "S5b": "S5b B ne répond plus", "S6": "S6 panne puis retour"}
CAMPAIGNS = [("campagne_r100", "Charge modérée : 100 req/s"), ("campagne_r200", "Charge élevée : 200 req/s")]
BEFORE_S, AFTER_S = 25, 10   # marge affichée avant et après la mesure (secondes)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rep", type=int, default=1, help="répétition à afficher (1 à 5)")
    p.add_argument("--grafana", default="http://localhost:3000")
    args = p.parse_args()

    base = f"{args.grafana}/d/mgl870-resilience"
    parts = ["<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Liens Grafana MGL870</title>",
             "<style>body{font-family:Arial,sans-serif;margin:24px;color:#0b0b0b;background:#fcfcfb}"
             "table{border-collapse:collapse;margin-bottom:28px}th,td{border:1px solid #d9d9d9;padding:8px 12px;text-align:center}"
             "th{background:#1f3a5f;color:#fff}td.sc{text-align:left;font-weight:bold}a{color:#2a78d6}"
             "small{color:#52514e}</style></head><body>",
             f"<h1>Liens Grafana — répétition {args.rep}</h1>",
             "<p><small>Chaque lien ouvre le tableau de bord sur la mesure de l'exécution "
             f"({BEFORE_S} s avant le début, {AFTER_S} s après la fin). "
             "Le préchauffage sans panne apparaît juste avant la mesure.</small></p>"]
    found = 0
    for camp, title in CAMPAIGNS:
        camp_dir = ROOT / "results" / camp
        if not camp_dir.exists():
            continue
        parts.append(f"<h2>{title}</h2><table><tr><th>Scénario</th>"
                     + "".join(f"<th>{CONFIG_LABELS[c]}</th>" for c in CONFIGS) + "</tr>")
        for sc in SCENARIOS:
            cells, any_run = [], False
            for cfg in CONFIGS:
                meta_file = camp_dir / f"{cfg}_{sc}_r{args.rep}" / "metadata.json"
                if not meta_file.exists():
                    cells.append("<td>—</td>")
                    continue
                meta = json.loads(meta_file.read_text())
                if meta.get("status") != "ok" or "load_start" not in meta:
                    cells.append("<td>invalide</td>")
                    continue
                start = int((meta["load_start"] - BEFORE_S) * 1000)
                end = int((meta["load_end"] + AFTER_S) * 1000)
                hour = datetime.fromtimestamp(meta["load_start"]).strftime("%d/%m %H:%M")
                cells.append(f"<td><a href='{base}?from={start}&to={end}' target='_blank'>ouvrir</a>"
                             f"<br><small>{hour}</small></td>")
                any_run = True
                found += 1
            if any_run:
                parts.append(f"<tr><td class='sc'>{SCENARIO_LABELS[sc]}</td>{''.join(cells)}</tr>")
        parts.append("</table>")
    parts.append("</body></html>")

    out = ROOT / "analysis" / "grafana_links.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"{found} liens écrits dans {out}")


if __name__ == "__main__":
    main()
