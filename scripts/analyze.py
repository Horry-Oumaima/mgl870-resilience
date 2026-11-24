#!/usr/bin/env python3
"""
Analyse de la campagne MGL870 (Timeout, Retry, Circuit Breaker).

Lit les dossiers produits par l'orchestrateur (results/<campagne>/<exécution>/) et produit,
dans le dossier analysis/ :
  - runs.csv              une ligne par exécution (toutes les métriques)
  - aggregate.csv         médiane et IC 95 % (bootstrap de la médiane) par charge x scénario x configuration ;
                          la moyenne, le minimum et le maximum sont aussi fournis
  - comparisons.csv       tests de Mann-Whitney entre une configuration et celle dont elle dérive
                          (taille d'effet : delta de Cliff ; correction de Holm par scénario et par métrique)
  - recovery_timeline.csv taux de succès seconde par seconde autour de la fin de panne (S6)
  - decision_matrix.md    tableaux lisibles (matrice de décision) pour le rapport
  - key_numbers.md        chiffres clés reliés aux hypothèses H1, H2 et H3 (sans verdict)
  - figures/*.png         graphiques du rapport

Définitions (voir docs/pilote.md) :
  - succès = réponse HTTP 200 obtenue en moins de SUCCESS_MS (1 s) ;
  - dénominateur = requêtes prévues par k6 (débit x durée) : une requête non envoyée compte comme un échec ;
  - amplification = appels reçus par B / commandes envoyées ;
  - débit = réponses reçues par seconde ; débit utile = réponses réussies en moins de 1 s par seconde ;
  - temps de récupération (S6) = délai entre la fin de la panne et la première seconde à partir de laquelle
    5 fenêtres consécutives d'une seconde ont au moins 99 % de commandes réussies.

Usage : python3 scripts/analyze.py [campagne ...]   (par défaut : campagne_r100 campagne_r200)
"""
import argparse
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SUCCESS_MS = 1000
ORDER_SHARE = 0.5
RECOVERY_THRESHOLD = 0.99
RECOVERY_WINDOWS = 5
BOOTSTRAP_SAMPLES = 10000
RNG = np.random.default_rng(42)

CONFIGS = ["C0", "C1", "C2", "C3", "C4"]
CONFIG_LABELS = {
    "C0": "C0 aucune protection",
    "C1": "C1 Timeout",
    "C2": "C2 Timeout + Retry",
    "C3": "C3 Timeout + Circuit Breaker",
    "C4": "C4 les trois",
}
SCENARIOS = ["S0", "S1", "S2", "S3", "S4", "S5b", "S6"]
SCENARIO_LABELS = {
    "S0": "S0 normal",
    "S1": "S1 latence 500 ms",
    "S2": "S2 latence 2 s",
    "S3": "S3 30 % d'erreurs",
    "S4": "S4 70 % d'erreurs",
    "S5b": "S5b B ne répond plus",
    "S6": "S6 panne puis retour",
}
# Comparaisons : chaque configuration contre celle dont elle dérive (configurations cumulatives)
COMPARISONS = [("C1", "C0"), ("C2", "C1"), ("C3", "C1"), ("C4", "C2"), ("C4", "C3")]
TESTED_METRICS = ["order_success_pct", "order_p95_ms", "catalog_success_pct", "catalog_p95_ms", "amplification"]
METRIC_LABELS = {
    "order_success_pct": "Commandes réussies en moins de 1 s (%)",
    "order_success_any_pct": "Commandes réussies, sans limite de temps (%)",
    "order_throughput_rps": "Débit des commandes : réponses reçues par seconde",
    "order_goodput_rps": "Débit utile des commandes : réussies en moins de 1 s par seconde",
    "catalog_throughput_rps": "Débit du catalogue : réponses reçues par seconde",
    "order_p50_ms": "Latence p50 des commandes (ms)",
    "order_p95_ms": "Latence p95 des commandes (ms)",
    "order_p99_ms": "Latence p99 des commandes (ms)",
    "catalog_success_pct": "Catalogue : requêtes réussies en moins de 1 s (%)",
    "catalog_p95_ms": "Latence p95 du catalogue (ms)",
    "amplification": "Amplification (appels à B / commande)",
    "cb_open_pct": "Disjoncteur ouvert (% du temps)",
    "A_threads_max": "Threads occupés dans A (max)",
    "B_threads_max": "Threads occupés dans B (max)",
    "not_sent_pct": "Requêtes non envoyées (%)",
    "recovery_s": "Temps de récupération (s)",
}

# Palette catégorielle validée (validate_palette.js, mode clair) ; une couleur fixe par configuration
COLORS = {"C0": "#2a78d6", "C1": "#eb6834", "C2": "#1baf7a", "C3": "#eda100", "C4": "#e87ba4"}
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"


# ---------------------------------------------------------------- lecture des fichiers

def parse_requests(path):
    """Journal k6 : une ligne JSON par requête (t = début en ms, ep, s = statut, d = durée ms, r = raison)."""
    rows = []
    with open(path, errors="replace") as f:
        for line in f:
            i, j = line.find("{"), line.rfind("}")
            if i < 0 or j < 0:
                continue
            frag = line[i:j + 1]
            try:
                rec = json.loads(frag)
            except json.JSONDecodeError:
                try:
                    rec = json.loads(frag.replace('\\"', '"'))
                except json.JSONDecodeError:
                    continue
            if "ep" in rec:
                rows.append((rec.get("t"), rec.get("ep"), rec.get("s"), rec.get("d"), rec.get("r")))
    return pd.DataFrame(rows, columns=["t", "ep", "s", "d", "r"])


def counter_total(text, name):
    total = 0.0
    for line in text.splitlines():
        if line.startswith(name + "{") or line.startswith(name + " "):
            try:
                total += float(line.rsplit(" ", 1)[1])
            except ValueError:
                pass
    return total


def series_values(data, key, keep=lambda m: True):
    vals = []
    series = data.get(key)
    if isinstance(series, list):
        for s in series:
            if keep(s.get("metric", {})):
                for _, v in s.get("values", []):
                    try:
                        x = float(v)
                    except ValueError:
                        continue
                    if math.isfinite(x):
                        vals.append(x)
    return vals


def parse_seconds(d):
    d = str(d).strip().lower()
    if d.endswith("ms"):
        return float(d[:-2]) / 1000
    if d.endswith("s"):
        return float(d[:-1])
    if d.endswith("m"):
        return float(d[:-1]) * 60
    return float(d)


def read_events(path):
    events = {}
    if path.exists():
        for line in path.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 3:
                events[parts[2]] = float(parts[0])
    return events


# ---------------------------------------------------------------- métriques par exécution

def pct(x):
    return 100.0 * x


def analyze_run(run_dir, meta, timelines):
    rate = int(meta["rate"])
    duration = parse_seconds(meta["duration"])
    order_rate = max(1, round(rate * ORDER_SHARE))
    catalog_rate = max(1, rate - order_rate)

    df = parse_requests(run_dir / "requests.log")
    out = {"campaign": run_dir.parent.name, "run": meta["run_id"], "rate": rate, "config": meta["config"],
           "scenario": meta["scenario"], "rep": meta["rep"], "order": meta.get("order"),
           "git_commit": meta.get("git_commit")}
    if df.empty:
        out["error"] = "journal k6 vide"
        return out

    ok_fast = (df["s"] == 200) & (df["d"] < SUCCESS_MS)
    for ep, planned_rate in (("order", order_rate), ("catalog", catalog_rate)):
        sel = df["ep"] == ep
        sent = int(sel.sum())
        planned = max(int(round(planned_rate * duration)), sent)
        d = df.loc[sel, "d"].to_numpy(dtype=float)
        out[f"{ep}_sent"] = sent
        out[f"{ep}_planned"] = planned
        out[f"{ep}_success_pct"] = pct((ok_fast & sel).sum() / planned)
        out[f"{ep}_success_any_pct"] = pct(((df["s"] == 200) & sel).sum() / planned)
        for q in (50, 95, 99):
            out[f"{ep}_p{q}_ms"] = float(np.percentile(d, q)) if len(d) else np.nan
        # Débit : réponses reçues (statut HTTP > 0) et réponses réussies en moins de 1 s, par seconde
        out[f"{ep}_throughput_rps"] = float(((df["s"] > 0) & sel).sum()) / duration
        out[f"{ep}_goodput_rps"] = float((ok_fast & sel).sum()) / duration
    out["not_sent_pct"] = pct(1 - (out["order_sent"] + out["catalog_sent"])
                              / (out["order_planned"] + out["catalog_planned"]))

    # Répartition des résultats des commandes (en % des commandes envoyées)
    reasons = Counter(df.loc[df["ep"] == "order", "r"])
    for reason, n in reasons.items():
        out[f"reason_{reason}_pct"] = pct(n / max(out["order_sent"], 1))

    # Amplification : appels reçus par B pendant la mesure / commandes envoyées
    before, after = run_dir / "metrics_before_payment.txt", run_dir / "metrics_after_payment.txt"
    if before.exists() and after.exists() and out["order_sent"]:
        calls = (counter_total(after.read_text(), "payment_requests_received_total")
                 - counter_total(before.read_text(), "payment_requests_received_total"))
        out["amplification"] = calls / out["order_sent"]

    # Séries Prometheus (secondaires : Prometheus peut être « aveugle » quand A est saturé)
    series_file = run_dir / "prometheus_series.json"
    if series_file.exists():
        data = json.loads(series_file.read_text())
        for key, label in (("order_threads_busy", "A_threads"), ("payment_threads_busy", "B_threads"),
                           ("order_cpu", "A_cpu"), ("payment_cpu", "B_cpu")):
            v = series_values(data, key)
            out[f"{label}_max"] = max(v) if v else np.nan
            out[f"{label}_mean"] = float(np.mean(v)) if v else np.nan
        is_open = series_values(data, "circuit_breaker_state", lambda m: m.get("state") == "open")
        out["cb_open_pct"] = pct(np.mean(is_open)) if is_open else np.nan

    # S6 : récupération, seconde par seconde, à partir de la fin de la panne
    if meta["scenario"] == "S6":
        events = read_events(run_dir / "events.log")
        if "fin_panne" in events:
            end = events["fin_panne"]
            start = events.get("debut_panne", np.nan)
            orders = df[df["ep"] == "order"].copy()
            orders["offset"] = np.floor(orders["t"] / 1000.0 - end).astype(int)
            orders["ok"] = (orders["s"] == 200) & (orders["d"] < SUCCESS_MS)
            per_sec = orders.groupby("offset")["ok"].agg(["mean", "size"])
            for off, row in per_sec.iterrows():
                timelines.append({"campaign": out["campaign"], "rate": rate, "config": meta["config"],
                                  "rep": meta["rep"], "offset_s": int(off), "success": row["mean"],
                                  "n": int(row["size"])})
            after_end = per_sec[per_sec.index >= 0]
            recovery = np.nan
            offsets = list(after_end.index)
            for k, off in enumerate(offsets):
                window = after_end.loc[offsets[k:k + RECOVERY_WINDOWS], "mean"]
                if len(window) == RECOVERY_WINDOWS and (window >= RECOVERY_THRESHOLD).all():
                    recovery = float(off)
                    break
            out["recovery_s"] = recovery
            out["recovery_censored"] = bool(np.isnan(recovery))
            out["outage_s"] = end - start if math.isfinite(start) else np.nan
            during = orders[(orders["offset"] >= math.floor(start - end)) & (orders["offset"] < 0)] \
                if math.isfinite(start) else orders.iloc[0:0]
            out["outage_success_pct"] = pct(during["ok"].mean()) if len(during) else np.nan
    return out


# ---------------------------------------------------------------- statistiques

def bootstrap_ci(values, n=BOOTSTRAP_SAMPLES):
    """Médiane des répétitions et IC 95 % obtenu par bootstrap de la médiane (méthode des percentiles)."""
    v = np.asarray([x for x in values if not (isinstance(x, float) and math.isnan(x))], dtype=float)
    if len(v) == 0:
        return np.nan, np.nan, np.nan
    med = float(np.median(v))
    if len(v) == 1 or np.all(v == v[0]):
        return med, med, med
    meds = np.median(RNG.choice(v, size=(n, len(v)), replace=True), axis=1)
    return med, float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))


def cliffs_delta(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if len(a) == 0 or len(b) == 0:
        return np.nan
    gt = sum((x > y) for x in a for y in b)
    lt = sum((x < y) for x in a for y in b)
    return (gt - lt) / (len(a) * len(b))


def holm(pvalues):
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(np.where(np.isnan(p), np.inf, p))
    adjusted = np.full(len(p), np.nan)
    running = 0.0
    m = int(np.sum(~np.isnan(p)))
    for rank, idx in enumerate(order):
        if np.isnan(p[idx]):
            continue
        running = max(running, min(1.0, (m - rank) * p[idx]))
        adjusted[idx] = running
    return adjusted


def aggregate(runs):
    metrics = [m for m in METRIC_LABELS if m in runs.columns]
    rows = []
    for (camp, rate, sc, cfg), g in runs.groupby(["campaign", "rate", "scenario", "config"]):
        row = {"campaign": camp, "rate": rate, "scenario": sc, "config": cfg, "n_reps": len(g)}
        for m in metrics:
            med, lo, hi = bootstrap_ci(g[m].tolist())
            row[f"{m}_median"], row[f"{m}_ci_low"], row[f"{m}_ci_high"] = med, lo, hi
            row[f"{m}_mean"] = g[m].mean()
            row[f"{m}_min"], row[f"{m}_max"] = g[m].min(), g[m].max()
        rows.append(row)
    return pd.DataFrame(rows)


def compare(runs):
    rows = []
    for (camp, rate, sc), g in runs.groupby(["campaign", "rate", "scenario"]):
        for new, base in COMPARISONS:
            a, b = g[g["config"] == new], g[g["config"] == base]
            if a.empty or b.empty:
                continue
            for m in TESTED_METRICS:
                if m not in g.columns:
                    continue
                x, y = a[m].dropna().to_numpy(), b[m].dropna().to_numpy()
                p = np.nan
                if len(x) >= 2 and len(y) >= 2 and not (np.all(x == x[0]) and np.all(y == y[0]) and x[0] == y[0]):
                    p = float(mannwhitneyu(x, y, alternative="two-sided", method="auto").pvalue)
                rows.append({"campaign": camp, "rate": rate, "scenario": sc, "comparison": f"{new} vs {base}",
                             "metric": m, "median_new": float(np.median(x)) if len(x) else np.nan,
                             "median_base": float(np.median(y)) if len(y) else np.nan,
                             "difference": (float(np.median(x) - np.median(y)) if len(x) and len(y) else np.nan),
                             "cliffs_delta": cliffs_delta(x, y), "p_value": p})
    out = pd.DataFrame(rows)
    if not out.empty:
        # Correction de Holm par famille : les 5 comparaisons d'une même métrique, dans un même scénario
        out["p_holm"] = np.nan
        for _, idx in out.groupby(["campaign", "scenario", "metric"]).groups.items():
            out.loc[idx, "p_holm"] = holm(out.loc[idx, "p_value"].to_numpy())
        out["significatif_holm_5pct"] = out["p_holm"] < 0.05
    return out


# ---------------------------------------------------------------- figures

def style_axes(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def grouped_bars(agg, rate, metric, path, ylabel, ylim=None, log=False):
    sub = agg[agg["rate"] == rate]
    scenarios = [s for s in SCENARIOS if s in set(sub["scenario"])]
    if not scenarios or f"{metric}_median" not in sub.columns:
        return False
    fig, ax = plt.subplots(figsize=(11, 4.6), facecolor=SURFACE)
    style_axes(ax)
    width = 0.16
    for k, cfg in enumerate(CONFIGS):
        xs, means, errs = [], [], [[], []]
        for i, sc in enumerate(scenarios):
            r = sub[(sub["scenario"] == sc) & (sub["config"] == cfg)]
            if r.empty or pd.isna(r[f"{metric}_median"].iloc[0]):
                continue
            mean = r[f"{metric}_median"].iloc[0]
            xs.append(i + (k - 2) * width)
            means.append(mean)
            errs[0].append(max(mean - r[f"{metric}_ci_low"].iloc[0], 0))
            errs[1].append(max(r[f"{metric}_ci_high"].iloc[0] - mean, 0))
        if not xs:
            continue
        if log:
            ax.errorbar(xs, means, yerr=errs, fmt="o", markersize=6, color=COLORS[cfg], ecolor=COLORS[cfg],
                        elinewidth=1.2, capsize=0, label=CONFIG_LABELS[cfg],
                        markeredgecolor=SURFACE, markeredgewidth=1)
        else:
            ax.bar(xs, means, width=width, color=COLORS[cfg], edgecolor=SURFACE, linewidth=1.5,
                   label=CONFIG_LABELS[cfg])
            ax.errorbar(xs, means, yerr=errs, fmt="none", ecolor=INK_2, elinewidth=1, capsize=2)
    ax.set_xticks(range(len(scenarios)))
    ax.set_xticklabels([SCENARIO_LABELS[s] for s in scenarios], color=INK, fontsize=9)
    ax.set_ylabel(ylabel, color=INK, fontsize=10)
    if log:
        ax.set_yscale("log")
    if ylim:
        ax.set_ylim(*ylim)
    ax.set_title(f"{ylabel} — charge {rate} req/s (médiane de 5 répétitions, IC 95 %)",
                 color=INK, fontsize=11, loc="left")
    ax.legend(ncol=5, fontsize=8.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12),
              labelcolor=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    return True


def recovery_figure(timeline, rate, path):
    sub = timeline[timeline["rate"] == rate]
    if sub.empty:
        return False
    fig, ax = plt.subplots(figsize=(11, 4.6), facecolor=SURFACE)
    style_axes(ax)
    lo, hi = -40, 30
    for cfg in CONFIGS:
        g = sub[(sub["config"] == cfg) & (sub["offset_s"] >= lo) & (sub["offset_s"] <= hi)]
        if g.empty:
            continue
        m = g.groupby("offset_s")["success"].median() * 100
        ax.plot(m.index, m.values, color=COLORS[cfg], linewidth=2, label=CONFIG_LABELS[cfg])
    ax.axvline(0, color=INK_2, linewidth=1, linestyle="--")
    ax.text(0.5, 50, "fin de la panne", color=INK_2, fontsize=9)
    ax.set_xlim(lo, hi)
    ax.set_ylim(-2, 102)
    ax.set_xlabel("Secondes par rapport à la fin de la panne", color=INK, fontsize=10)
    ax.set_ylabel("Commandes réussies en moins de 1 s (%)", color=INK, fontsize=10)
    ax.set_title(f"S6 : panne de B puis retour — charge {rate} req/s (médiane des répétitions)",
                 color=INK, fontsize=11, loc="left")
    ax.legend(ncol=5, fontsize=8.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14),
              labelcolor=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    return True


# ---------------------------------------------------------------- tableaux lisibles

def fmt_ci(row, metric, digits=1, unit=""):
    if f"{metric}_median" not in row or pd.isna(row[f"{metric}_median"]):
        return "-"
    m, lo, hi = row[f"{metric}_median"], row[f"{metric}_ci_low"], row[f"{metric}_ci_high"]
    return f"{m:.{digits}f}{unit} [{lo:.{digits}f}–{hi:.{digits}f}]"


def matrix_table(agg, rate, metric, digits=1, unit=""):
    sub = agg[agg["rate"] == rate]
    lines = ["| Scénario | " + " | ".join(CONFIG_LABELS[c] for c in CONFIGS) + " |",
             "|---" * (len(CONFIGS) + 1) + "|"]
    for sc in SCENARIOS:
        cells = []
        for cfg in CONFIGS:
            r = sub[(sub["scenario"] == sc) & (sub["config"] == cfg)]
            cells.append(fmt_ci(r.iloc[0], metric, digits, unit) if not r.empty else "-")
        if any(c != "-" for c in cells):
            lines.append(f"| {SCENARIO_LABELS[sc]} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_decision_matrix(agg, path):
    parts = ["# Matrice de décision (médiane des 5 répétitions [IC 95 % bootstrap])", "",
             f"Succès = réponse 200 en moins de {SUCCESS_MS} ms ; requêtes non envoyées comptées comme échecs.", ""]
    for rate in sorted(agg["rate"].unique()):
        parts += [f"## Charge {rate} req/s", ""]
        for metric, digits, unit in (("order_success_pct", 1, " %"), ("order_goodput_rps", 1, ""),
                                     ("order_throughput_rps", 1, ""), ("order_p95_ms", 0, ""),
                                     ("catalog_success_pct", 1, " %"), ("catalog_p95_ms", 0, ""),
                                     ("amplification", 2, ""), ("cb_open_pct", 0, " %"),
                                     ("recovery_s", 1, " s")):
            if f"{metric}_median" in agg.columns:
                table = matrix_table(agg, rate, metric, digits, unit)
                if table.count("\n") > 1:
                    parts += [f"### {METRIC_LABELS[metric]}", "", table, ""]
    path.write_text("\n".join(parts))


def get(agg, rate, sc, cfg, metric):
    r = agg[(agg["rate"] == rate) & (agg["scenario"] == sc) & (agg["config"] == cfg)]
    return r.iloc[0] if not r.empty and f"{metric}_median" in r.columns else None


def key_line(agg, rate, sc, cfg, metric, digits=1, unit=""):
    r = get(agg, rate, sc, cfg, metric)
    val = fmt_ci(r, metric, digits, unit) if r is not None else "-"
    return f"- {SCENARIO_LABELS.get(sc, sc)}, {CONFIG_LABELS[cfg]}, {rate} req/s : {METRIC_LABELS[metric]} = {val}"


def write_key_numbers(agg, path):
    L = ["# Chiffres clés par hypothèse (sans verdict : l'interprétation se fait dans le rapport)", ""]
    L += ["## H1 — Timeout (C1 contre C0) : latence extrême et faux échecs", ""]
    for sc in ("S1", "S2", "S5b"):
        for cfg in ("C0", "C1"):
            L.append(key_line(agg, 100, sc, cfg, "order_p99_ms", 0))
            L.append(key_line(agg, 100, sc, cfg, "order_success_any_pct", 1, " %"))
            L.append(key_line(agg, 100, sc, cfg, "catalog_success_pct", 1, " %"))
    L += ["", "## H2 — Retry (C2 contre C1) : erreurs passagères et amplification", ""]
    for rate in (100, 200):
        for sc in ("S3", "S4"):
            for cfg in ("C1", "C2"):
                L.append(key_line(agg, rate, sc, cfg, "order_success_pct", 1, " %"))
                L.append(key_line(agg, rate, sc, cfg, "amplification", 2))
                L.append(key_line(agg, rate, sc, cfg, "catalog_p95_ms", 0))
    for sc in ("S2", "S5b"):
        for cfg in ("C1", "C2"):
            L.append(key_line(agg, 100, sc, cfg, "catalog_success_pct", 1, " %"))
    L += ["", "## H3 — Circuit Breaker (C3 contre C1) : isolation, déclenchements à tort, récupération", ""]
    for rate in (100, 200):
        for sc in ("S5b", "S3", "S4"):
            for cfg in ("C1", "C3", "C4"):
                L.append(key_line(agg, rate, sc, cfg, "catalog_success_pct", 1, " %"))
                L.append(key_line(agg, rate, sc, cfg, "catalog_p95_ms", 0))
                L.append(key_line(agg, rate, sc, cfg, "order_success_pct", 1, " %"))
    for cfg in CONFIGS:
        L.append(key_line(agg, 100, "S6", cfg, "recovery_s", 1, " s"))
    path.write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------- programme principal

def main():
    p = argparse.ArgumentParser(description="Analyse de la campagne MGL870")
    p.add_argument("campaigns", nargs="*", default=["campagne_r100", "campagne_r200"])
    p.add_argument("--out", default="analysis")
    args = p.parse_args()

    out_dir = ROOT / args.out
    fig_dir = out_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    runs, timelines, skipped = [], [], []
    for name in args.campaigns:
        camp_dir = ROOT / "results" / name
        if not camp_dir.exists():
            print(f"Campagne absente : {camp_dir}")
            continue
        for meta_file in sorted(camp_dir.glob("*/metadata.json")):
            meta = json.loads(meta_file.read_text())
            if meta.get("status") != "ok":
                skipped.append(meta.get("run_id"))
                continue
            runs.append(analyze_run(meta_file.parent, meta, timelines))
        print(f"{name} : {sum(r['campaign'] == name for r in runs)} exécutions valides lues")
    if not runs:
        raise SystemExit("Aucune exécution valide trouvée.")
    if skipped:
        print(f"Exécutions invalides ignorées ({len(skipped)}) : {', '.join(skipped)}")

    runs = pd.DataFrame(runs)
    runs.to_csv(out_dir / "runs.csv", index=False)
    agg = aggregate(runs)
    agg.to_csv(out_dir / "aggregate.csv", index=False)
    comp = compare(runs)
    comp.to_csv(out_dir / "comparisons.csv", index=False)
    timeline = pd.DataFrame(timelines)
    if not timeline.empty:
        timeline.to_csv(out_dir / "recovery_timeline.csv", index=False)
    write_decision_matrix(agg, out_dir / "decision_matrix.md")
    write_key_numbers(agg, out_dir / "key_numbers.md")

    made = []
    for rate in sorted(runs["rate"].unique()):
        specs = [("order_success_pct", "Commandes réussies en moins de 1 s (%)", (0, 105), False, "succes_commandes"),
                 ("catalog_success_pct", "Catalogue : requêtes réussies en moins de 1 s (%)", (0, 105), False,
                  "succes_catalogue"),
                 ("order_p95_ms", "Latence p95 des commandes (ms, échelle log)", None, True, "p95_commandes"),
                 ("catalog_p95_ms", "Latence p95 du catalogue (ms, échelle log)", None, True, "p95_catalogue"),
                 ("amplification", "Amplification (appels à B par commande)", None, False, "amplification")]
        for metric, label, ylim, log, stem in specs:
            path = fig_dir / f"{stem}_r{rate}.png"
            if grouped_bars(agg, rate, metric, path, label, ylim, log):
                made.append(path.name)
        if not timeline.empty and recovery_figure(timeline, rate, fig_dir / f"recuperation_s6_r{rate}.png"):
            made.append(f"recuperation_s6_r{rate}.png")

    n_sig = int(comp["significatif_holm_5pct"].sum()) if not comp.empty else 0
    print(f"\nRésultats écrits dans {out_dir}/ :")
    print("  runs.csv, aggregate.csv, comparisons.csv, decision_matrix.md, key_numbers.md"
          + (", recovery_timeline.csv" if not timeline.empty else ""))
    print(f"  figures : {', '.join(made)}")
    print(f"  {len(comp)} comparaisons, dont {n_sig} significatives après correction de Holm (5 %)")


if __name__ == "__main__":
    main()
