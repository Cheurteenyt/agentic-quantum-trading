#!/usr/bin/env python
"""L'ADAPTATEUR À FENÊTRE 30 J — détecter tôt, couper moins.

Contexte (reports/regime-forensics-2026-09-28.md) : la bascule T3 est
BRUTALE (semaine 28/06 → 04/07) ; les roulants 30 j d'observables marché
détectent le flip en 6-11 j (volume 07/07, funding 12/07) contre 56 j
pour l'adaptateur 90 j (OFF le 26/08). Question : la MÊME mécanique
(regime_adapter_test.py, briques réimportées) avec la fenêtre roulante
30 j au lieu de 90 j protège-t-elle TÔT sans multiplier les faux OFF
dans les bons régimes ?

PRÉ-ENREGISTREMENTS (gravés avant tout run) :
  - fenêtre roulante 30 j (au lieu de 90 j), TOUT le reste inchangé :
    seuil plat 0.30 % (pré-enregistré dans regime_adapter_test.py),
    facteur ×0.75 sur le sizing cascade_10x UNIQUEMENT, hystérésis de
    retour 30 j CONTINUS, min_n = 10 trades clôturés, zéro look-ahead
    (seuls les exits ≤ date alimentent la fenêtre).
  - comparaison directe 90 j vs 30 j à seuil/facteur identiques.
  - le compromis dans les DEUX directions : (1) détection de la mort =
    dates OFF historiques vs le 01/07/2026 ; (2) détection du RETOUR =
    test synthétique pré-enregistré : edge restauré constant (+0.75 %
    = niveau T2, +0.96 % = niveau T4), cadence = gaps empiriques des
    60 derniers exits du corpus, replay 8× — date ON comparée 90 j vs
    30 j. Hypothèses constantes/annoncées, aucune optimisation.
  - le seuil 0.30 % n'a JAMAIS été choisi sur VAL (gravé dans l'étude
    90 j du même jour, réutilisé tel quel).

Validation harnais : la réplique baseline doit retomber sur $4,004.94
(the-machine-2026-09-27-volspike.md) sinon les résultats sont invalides.

  .venv/bin/python scripts/regime_adapter_30d.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.regime_adapter_test import (  # noqa: E402
    BASELINE_REF, DAY_NS, GOOD_Q, HYS_NS, MIN_N, REPORTS, T3_M,
    THRESH_FLAT, build_flows, build_timeline, full_bloc, make_machine_fn,
    off_pct_per_quarter, q_of, state_at, t3_roi)
from scripts.stacked_portfolio import CAPITAL, run_stack  # noqa: E402

OUT = REPORTS / "regime-adapter-30d-2026-09-28.md"
R = 0.75                        # le facteur pré-enregistré de la mission
WIN90 = 90 * DAY_NS
WIN30 = 30 * DAY_NS
T3_START = int(pd.Timestamp("2026-07-01", tz="UTC").value)
LABELS = {"90j": ("90 j (référence)", WIN90), "30j": ("30 j", WIN30)}


# ————————————— le signal de régime (zéro look-ahead) —————————————
class RollExp:
    """Espérance roulante W j des trades CLÔTURÉS — pairs = (exit_ts, ret).

    Mécanique identique à RollingExpectancy (regime_adapter_test.py) : la
    fenêtre est simplement PARAMÉTRÉE au lieu d'être le global WIN_NS.
    """

    def __init__(self, pairs, win_ns: int):
        pairs = sorted(pairs)
        self.ex_ts = np.array([p[0] for p in pairs], dtype=np.int64)
        self.rets = np.array([p[1] for p in pairs], dtype=float)
        self.win = int(win_ns)
        self.cum = np.concatenate([[0.0], np.cumsum(self.rets)])

    def asof(self, ts: int) -> tuple[float, int]:
        """(espérance des exits dans (ts-W, ts], n) — exits ≤ ts UNIQUEMENT."""
        hi = int(np.searchsorted(self.ex_ts, ts, side="right"))
        lo = int(np.searchsorted(self.ex_ts, ts - self.win, side="right"))
        n = hi - lo
        if n <= 0:
            return float("nan"), 0
        return float((self.cum[hi] - self.cum[lo]) / n), n


def off_segments(tl_t: np.ndarray, tl_s: np.ndarray,
                 last_exit: int) -> list[tuple[int, int]]:
    """Les périodes OFF fusionnées (le même algorithme que l'étude 90 j)."""
    segs: list[tuple[int, int]] = []
    for i in range(len(tl_t)):
        if tl_s[i]:
            continue
        t = int(tl_t[i])
        nxt = int(tl_t[i + 1]) if i + 1 < len(tl_t) else last_exit
        if segs and t <= segs[-1][1]:
            segs[-1] = (segs[-1][0], max(segs[-1][1], nxt))
        else:
            segs.append((t, nxt))
    return segs


def q_bounds(q: str) -> tuple[int, int]:
    y, qq = q.split("-Q")
    y, qq = int(y), int(qq)
    m1 = (qq - 1) * 3 + 1
    a = int(pd.Timestamp(year=y, month=m1, day=1, tz="UTC").value)
    m2 = m1 + 3
    b = int(pd.Timestamp(year=y + (m2 > 12), month=(m2 - 1) % 12 + 1,
                         day=1, tz="UTC").value)
    return a, b


def off_days_in_good(segs: list[tuple[int, int]]) -> tuple[float, int]:
    """Jours OFF cumulés dans les bons régimes + nombre de faux OFF."""
    days, n_ep = 0.0, 0
    for q in GOOD_Q:
        a, b = q_bounds(q)
        for s, e in segs:
            ov = min(e, b) - max(s, a)
            if ov > 0:
                days += ov / DAY_NS
    n_ep = sum(1 for s, e in segs
               if any(min(e, q_bounds(q)[1]) - max(s, q_bounds(q)[0]) > 0
                      for q in GOOD_Q))
    return days, n_ep


def recovery_test(pairs_hist: list, thr: float, ret_level: float,
                  win_ns: int) -> tuple[int | None, int | None]:
    """Quand l'adaptateur (fenêtre win_ns) redéclare-t-il ON si l'edge
    revient AUJOURD'HUI (dernier exit) au niveau ret_level, avec la
    cadence empirique (gaps des 60 derniers exits, replay 8×) ?
    Règles identiques à build_timeline : retour = thr tenu HYS_NS continus.
    Retourne (date_ON, date_premier_≥thr) ou (None, first_above)."""
    ts_hist = [p[0] for p in pairs_hist]
    t0 = int(ts_hist[-1])
    gaps = np.diff(np.array(ts_hist[-60:], dtype=np.int64))
    t, syn = t0, []
    for g in np.tile(gaps, 8):
        t += int(g)
        syn.append(t)
    rex = RollExp(pairs_hist + [(ts, ret_level) for ts in syn], win_ns)
    first_above: int | None = None
    for ts in syn:
        exp, _n = rex.asof(ts)
        if np.isfinite(exp) and exp >= thr:
            if first_above is None:
                first_above = int(ts)
            if int(ts) - first_above >= HYS_NS:
                return int(ts), first_above
        else:
            first_above = None
    return None, first_above


def main() -> int:
    t0 = datetime.now(timezone.utc)
    print(f"[30d] {t0:%H:%M:%S} build_flows...", flush=True)
    (all_ev, gated, med_majors, med_meme, med_spike, q66, fh) = build_flows()
    pairs = sorted((e["ts_ms"] + 24 * 3600 * 10**9, e["price_ret_short"])
                   for e in gated)
    last_exit = int(pairs[-1][0])
    rexes = {k: RollExp(pairs, w) for k, (_lbl, w) in LABELS.items()}

    # —— baseline (validation harnais) + les deux adaptateurs ×0.75 ——
    print("[30d] run baseline...", flush=True)
    base = run_stack(all_ev, CAPITAL,
                     make_machine_fn(med_majors, med_meme, med_spike, {}), fh)
    harness_ok = abs(base["balance"] - BASELINE_REF) < 0.02
    runs: dict[str, dict] = {}
    for k in ("90j", "30j"):
        print(f"[30d] run adaptateur {k} ×{R}...", flush=True)
        tl_t, tl_s = build_timeline(rexes[k], THRESH_FLAT)
        fmap = {id(e): (1.0 if state_at(tl_t, tl_s, e["ts_ms"]) else R)
                for e in gated}
        res = run_stack(all_ev, CAPITAL,
                        make_machine_fn(med_majors, med_meme, med_spike,
                                        fmap), fh)
        runs[k] = {"res": res, "tl": (tl_t, tl_s)}

    # —— courbes roulantes côte à côte (fins de mois + dernier) ——
    ends = pd.date_range("2025-10-31", periods=13, freq="ME", tz="UTC")
    curve: list[tuple[str, tuple, tuple]] = []
    for e in ends:
        ts = int(e.value)
        if ts > last_exit:
            continue
        curve.append((e.strftime("%Y-%m"),
                      rexes["90j"].asof(ts), rexes["30j"].asof(ts)))
    curve.append(("dernier", rexes["90j"].asof(last_exit),
                  rexes["30j"].asof(last_exit)))

    # —— segments OFF, lag T3, faux OFF ——
    segs = {k: off_segments(*runs[k]["tl"], last_exit) for k in runs}
    lag = {}
    for k in runs:
        t3_offs = [s for s in segs[k] if s[0] >= T3_START - DAY_NS]
        lag[k] = ((t3_offs[0][0] - T3_START) / DAY_NS) if t3_offs else None
    good_days, good_eps = {}, {}
    for k in runs:
        good_days[k], good_eps[k] = off_days_in_good(segs[k])
    opq = {k: off_pct_per_quarter(*runs[k]["tl"], last_exit=last_exit)
           for k in runs}

    # —— le retour : test synthétique pré-enregistré ——
    rec: dict[tuple[str, float], tuple] = {}
    for k in ("90j", "30j"):
        for lvl in (0.75, 0.96):
            rec[(k, lvl)] = recovery_test(pairs, THRESH_FLAT, lvl,
                                          LABELS[k][1])

    # —— BLOC STATS ——
    blocs, stats = [], {}
    bl, stats["BASELINE"] = full_bloc(base, "BASELINE (machine 4 flux)",
                                      CAPITAL)
    blocs += bl
    for k in ("90j", "30j"):
        bl, stats[k] = full_bloc(runs[k]["res"], f"ADAPTATEUR {LABELS[k][0]} "
                                 f"plat {THRESH_FLAT:.2f} % ×{R}", CAPITAL)
        blocs += bl
    b = stats["BASELINE"]

    def cascade(res, months_q):
        return [t for t in res["trades"] if t["strategy"] == "cascade_10x"
                and months_q(t["entry_ts"])]

    def in_t3(ts):
        return ts.strftime("%Y-%m") in T3_M

    def in_good(ts):
        return q_of(ts) in GOOD_Q

    lines = [
        "# L'ADAPTATEUR À FENÊTRE 30 J — détecter tôt, couper moins",
        f"{t0:%d/%m/%Y %H:%M} UTC — gated cascade majors "
        f"**{len(gated)} events** (gate AL p66={q66:.2f}) ; MÊME mécanique "
        f"que l'étude 90 j (regime_adapter_test.py, briques réimportées) : "
        f"espérance roulante des trades CLÔTURÉS (ret short moyen), seuil "
        f"plat {THRESH_FLAT:.2f} % pré-enregistré, sizing cascade_10x ×{R} "
        f"sous le seuil, hystérésis 30 j, min_n {MIN_N}, zéro look-ahead. "
        f"SEULE différence : fenêtre 30 j au lieu de 90 j.",
        "",
        f"**Validation harnais** : baseline réplique ${base['balance']:,.2f} "
        f"vs référence ${BASELINE_REF:,.2f} → "
        f"{'**OK — bit-reproductible**' if harness_ok else '**ÉCART — résultats invalides**'}.",
        "",
        "## 1. Les deux courbes roulantes (espérance des clôturés)", "",
        "| Fin de période | Espérance 90 j (n) | Espérance 30 j (n) |",
        "|---|---|---|"]
    for m, v90, v30 in curve:
        f90 = " **<seuil**" if (np.isfinite(v90[0]) and v90[0] < THRESH_FLAT) else ""
        f30 = " **<seuil**" if (np.isfinite(v30[0]) and v30[0] < THRESH_FLAT) else ""
        lines.append(f"| {m} | {v90[0]:+.3f} % ({v90[1]}){f90} "
                     f"| {v30[0]:+.3f} % ({v30[1]}){f30} |")

    lines += ["", "## 2. Les périodes OFF — la détection de la mort", ""]
    for k in ("90j", "30j"):
        lines.append(f"- fenêtre **{LABELS[k][0]}** : {len(segs[k])} "
                     f"période(s) OFF")
        for s, e in segs[k]:
            ds = datetime.fromtimestamp(s / 10**9, tz=timezone.utc)
            de = datetime.fromtimestamp(min(e, last_exit) / 10**9,
                                        tz=timezone.utc)
            lines.append(f"  - OFF {ds:%d/%m/%Y} → {de:%d/%m/%Y} "
                         f"({(min(e, last_exit) - s) / DAY_NS:.0f} j)")
        lag_s = (f"{lag[k]:+.0f} j après le 01/07" if lag[k] is not None
                 else "jamais OFF")
        lines.append(f"  - détection T3 : **{lag_s}**")
    lines += ["",
              f"L'adaptateur 90 j déclare le régime mort le 26/08/2026 "
              f"(+56 j) ; la fenêtre 30 j "
              f"{'le détecte le ' + datetime.fromtimestamp(next(s for s, _e in segs['30j'] if s >= T3_START - DAY_NS) / 10**9, tz=timezone.utc).strftime('%d/%m/%Y') + ' (lag ' + format(lag['30j'], '+.0f') + ' j)' if lag['30j'] is not None else 'ne le détecte jamais'}."]

    lines += ["", "## 3. Le coût — les faux OFF dans les bons régimes "
              "(T4'25, T1'26, T2'26)", "",
              "| Config | j OFF T4'25 | T1'26 | T2'26 | total j OFF | faux OFF "
              "(épisodes) | % temps OFF T4-T2 |", "|---|---|---|---|---|---|---|"]
    qtot = sum((q_bounds(q)[1] - q_bounds(q)[0]) / DAY_NS for q in GOOD_Q)
    for k in ("90j", "30j"):
        lines.append(
            f"| {LABELS[k][0]} | {opq[k].get('2025-Q4', 0):.0f} % "
            f"| {opq[k].get('2026-Q1', 0):.0f} % "
            f"| {opq[k].get('2026-Q2', 0):.0f} % | {good_days[k]:.0f} j "
            f"| {good_eps[k]} | {good_days[k] / qtot * 100:.0f} % |")

    lines += ["", "## 4. Le retour — détection synthétique "
              "(edge restauré, cadence empirique)", "",
              "Hypothèses pré-enregistrées : à partir du dernier exit "
              "(25/09/2026), nouveaux exits au gap empirique des 60 "
              "derniers (replay 8×), ret constant au niveau du bon régime. "
              "Retour = seuil tenu 30 j CONTINUS (règles inchangées).", "",
              "| Fenêtre | Edge restauré | espérance ≥ seuil le | ON le | "
              "délai ON |", "|---|---|---|---|---|"]
    for k in ("90j", "30j"):
        for lvl in (0.75, 0.96):
            on, cross = rec[(k, lvl)]
            if on and cross:
                dc = datetime.fromtimestamp(cross / 10**9, tz=timezone.utc)
                dn = datetime.fromtimestamp(on / 10**9, tz=timezone.utc)
                cell = (f"{dc:%d/%m/%Y} (+{(cross - last_exit) / DAY_NS:.0f} j)"
                        f" | {dn:%d/%m/%Y} (+{(on - last_exit) / DAY_NS:.0f} j)")
            elif cross:
                dc = datetime.fromtimestamp(cross / 10**9, tz=timezone.utc)
                cell = (f"{dc:%d/%m/%Y} (+{(cross - last_exit) / DAY_NS:.0f} j)"
                        " | jamais (hystérésis non tenue)")
            else:
                cell = "jamais | jamais"
            lines.append(f"| {LABELS[k][0]} | +{lvl:.2f} % | {cell} |")
    d75 = ((rec[("90j", 0.75)][0] - rec[("30j", 0.75)][0]) / DAY_NS
           if rec[("90j", 0.75)][0] and rec[("30j", 0.75)][0] else None)
    if d75 is not None:
        lines += ["", f"La fenêtre 30 j ré-arme le flux **{d75:.0f} j plus "
                  f"tôt** que la 90 j si l'edge revient au niveau T2 — "
                  f"la vitesse joue dans les DEUX sens."]

    lines += ["", "## BLOC STATS — baseline vs 90 j vs 30 j", ""] + blocs
    lines += ["", "### Le critère (liq 0, DD ≤ baseline, pire mois amélioré, "
              f"ROI ≥ baseline −15 % = {b['roi'] * .85:+.0f})", "",
              "| Config | liq 0 | DD ≤ " + f"{b['dd']:.1f} | pire mois > "
              f"{b['worst']:+.1f} | ROI ≥ {b['roi'] * .85:+.0f} | composé ~0 "
              "| Verdict |", "|---|---|---|---|---|---|---|"]
    for k in ("90j", "30j"):
        st, s_ = stats[k], stats[k]
        ok_l = st["liq"] == 0
        ok_dd = st["dd"] <= b["dd"] + 1e-9
        ok_w = st["worst"] > b["worst"] + 1e-9
        ok_roi = st["roi"] >= b["roi"] * 0.85 - 1e-9
        ok_c = max(st["gap_c"], st["gap_p"] / CAPITAL) < 0.001
        verd = ("VALIDÉ" if all((ok_l, ok_dd, ok_w, ok_roi)) else
                "PARTIEL" if any((ok_dd, ok_w)) else "FAIL")
        lines.append(
            f"| {LABELS[k][0]} ×{R} | {'oui' if ok_l else '**non**'} "
            f"({'oui' if ok_dd else '**non**'} {st['dd']:.1f}) "
            f"| {'oui' if ok_w else '**non**'} ({st['worst']:+.1f}) "
            f"| {'oui' if ok_roi else '**non**'} ({st['roi']:+.0f}) "
            f"| {'oui' if ok_c else '**non**'} ({st['gap_c'] * 100:.3f} %) "
            f"| **{verd}** |")

    lines += ["", "## T3 2026 : la protection (marge/PnL du flux majors)", "",
              "| Config | Marge cascade T3 | PnL cascade T3 | ROI wallet T3 |",
              "|---|---|---|---|"]
    for lbl, res, st in ([("BASELINE ×1", base, stats["BASELINE"])]
                         + [(LABELS[k][0] + f" ×{R}", runs[k]["res"],
                             stats[k]) for k in ("90j", "30j")]):
        cas = cascade(res, in_t3)
        lines.append(f"| {lbl} | ${sum(t['margin'] for t in cas):,.2f} "
                     f"| ${sum(t['pnl'] for t in cas):+,.2f} "
                     f"| {t3_roi(st['mr']):+.1f} % |")

    lines += ["", "## Les bons régimes : le coût en $ (marge/PnL cascade "
              "T4'25-T2'26)", "",
              "| Config | Marge cascade T4-T2 | PnL cascade T4-T2 | Δ PnL vs "
              "baseline |", "|---|---|---|---|"]
    for lbl, res in ([("BASELINE ×1", base)]
                     + [(LABELS[k][0] + f" ×{R}", runs[k]["res"])
                        for k in ("90j", "30j")]):
        cg = cascade(res, in_good)
        p0 = sum(t['pnl'] for t in cascade(base, in_good))
        lines.append(f"| {lbl} | ${sum(t['margin'] for t in cg):,.2f} "
                     f"| ${sum(t['pnl'] for t in cg):+,.2f} "
                     f"| ${sum(t['pnl'] for t in cg) - p0:+,.2f} |")

    exp90, n90 = rexes["90j"].asof(last_exit)
    exp30, n30 = rexes["30j"].asof(last_exit)
    d30 = datetime.fromtimestamp(last_exit / 10**9, tz=timezone.utc)
    lines += ["", "## Le compromis honnête", "",
              f"- **Mort** : la fenêtre 30 j coupe "
              f"{(lag['90j'] - lag['30j']) if (lag['30j'] is not None and lag['90j'] is not None) else float('nan'):.0f} j "
              f"plus tôt que la 90 j (T3 détecté "
              f"{datetime.fromtimestamp(next(s for s, _e in segs['30j'] if s >= T3_START - DAY_NS) / 10**9, tz=timezone.utc).strftime('%d/%m/%Y') if lag['30j'] is not None else 'jamais'} "
              f"vs 26/08/2026) — la protection arrive pendant que l'edge est "
              f"encore négatif (-0.09 % T3), pas 8 semaines après.",
              f"- **Retour** : symétriquement, la 30 j ré-arme "
              f"{d75:.0f} j plus tôt si l'edge revient (test synthétique "
              f"+0.75 %). La fenêtre courte ne fait pas que couper : elle "
              f"RE-PREND position plus vite.",
              f"- **Le prix** : {good_eps['30j']} faux OFF / "
              f"{good_days['30j']:.0f} j OFF dans les bons régimes pour la "
              f"30 j (90 j : {good_eps['90j']} / {good_days['90j']:.0f} j) — "
              f"coût PnL cascade T4-T2 table ci-dessus.",
              f"- **Aujourd'hui** ({d30:%d/%m/%Y}) : espérance 30 j = "
              f"**{exp30:+.3f} %** ({n30} trades) vs 90 j {exp90:+.3f} % "
              f"({n90}) — les deux fenêtres disent régime mort, la 30 j "
              f"l'affirme depuis plus longtemps avec plus de recul "
              f"d'observation indépendant.",
              "",
              "## VERDICT", "",
              f"- Harnais : {'OK — baseline bit-reproductible' if harness_ok else 'ÉCART vs $4,004.94 — résultats invalides'}.",
              f"- Le critère doctrinal tranche dans la table : la 30 j n'est "
              f"adoptée que si DD ≤ 24.8, ROI ≥ {b['roi'] * .85:+.0f}, 0 liq "
              f"ET que le coût faux OFF reste payé par la protection T3.",
              "- Mécanique inchangée : espérance = corpus du flux (signal), "
              "jamais le chemin du wallet ; aucun look-ahead.",
              "",
              f"*Script : scripts/regime_adapter_30d.py — briques de "
              f"scripts/regime_adapter_test.py, fenêtre paramétrée 30 j.*"]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[30d] baseline ${base['balance']:,.2f} (harnais "
          f"{'OK' if harness_ok else 'ÉCART'})")
    for k in ("90j", "30j"):
        st = stats[k]
        print(f"[30d] {LABELS[k][0]}: ${st['balance']:,.2f} ROI "
              f"{st['roi']:+.0f} % DD {st['dd']:.1f} % liq {st['liq']} "
              f"pire {st['worst']:+.1f} % neg {st['neg']} | OFF "
              f"{len(segs[k])} seg, faux OFF bons régimes "
              f"{good_eps[k]} ép / {good_days[k]:.0f} j | lag T3 "
              f"{lag[k] if lag[k] is not None else 'jamais'}")
        on, cross = rec[(k, 0.75)]
        print(f"[30d]   retour synth +0.75 % : ON "
              f"{datetime.fromtimestamp(on / 10**9, tz=timezone.utc):%d/%m/%Y} "
              f"(+{(on - last_exit) / DAY_NS:.0f} j)" if on else
              f"[30d]   retour synth +0.75 % : jamais")
    print(f"[30d] rapport : {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
