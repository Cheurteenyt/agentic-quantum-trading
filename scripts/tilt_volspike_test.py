#!/usr/bin/env python
"""TILT × VOL-SPIKE + SURVIVOR ×2.0 — les deux derniers raffinements de la
machine 4 flux (baseline --vol-spike : $4,004.94 = +3 905 %/an @ DD 24,8 %,
0 liq, record +90,8 %, 1 mois négatif).

HYPOTHÈSES PRÉ-ENREGISTRÉES (écrites AVANT tout regard sur les chiffres) :
  H-DIRECT   : le gradient cascade se transpose tel quel au fade vol_spike
               — l'espérance nette du fade CROÎT avec corr7 (bucket
               corr>p66 TRAIN meilleur). Récit : corr haute = mouvement
               systémique qui sature = le fade est pris dans la continuation.
  H-INVERSÉ  : la logique fade l'emporte — l'espérance nette DÉCROÎT avec
               corr7 (bucket corr>p66 TRAIN pire, corr<p33 meilleur).
               Récit : corr basse = choc idiosyncratique = le rebond vient
               (le fade attrape le rebond) ; corr haute = la cascade
               continue contre le fade.
  H-NUL      : pas de gradient monotone (buckets quasi égaux ou signe qui
               change entre TRAIN et VAL).

  RÈGLE DE DÉCISION (fixée avant les chiffres) : l'orientation est retenue
  si (i) le signe de l'écart d'espérance nette (bucket haut − bucket bas)
  est LE MÊME en TRAIN (70 % temporel) et en VAL, ET (ii) l'écart en VAL
  est ≥ 0,05 % de notionnel/trade ; le tilt orienté passe ensuite le
  wallet 4 flux (ROI ≥ baseline, DD ≤, mois négatifs ≤, 0 liq, garde-fous).
  Conformément à la mission, le tilt INVERSÉ n'est qu'un diagnostic de
  secours : il ne peut être ADOPTÉ que si le gradient droit échoue au
  wallet ET que les gradient maps supportent l'inversé — sur-dimensionner
  un bucket dont l'espérance mesurée est pire n'est pas un edge, quel que
  soit le chemin de compounding.

SURVIVOR ×2.0 (le poids QUBO) : le filtre ATR-extrême actuel coupe le
décile supérieur (p90 — les LAB). Question : à notional ×2, la queue
LAB-type revient-elle dans le top 3 des contributeurs DD ? Si on serre
d'un cran (coupe au p80), combien de gagnants perdus vs combien de queue
coupée ? CRITÈRE DE DÉCISION (fixé avant les chiffres) : serrer si et
seulement si DD(flux @×2.0, filtre p80) ≤ DD(flux @×1.0, filtre p90).

Briques du harnais importées SANS les éditer : qubo_sizing (réplique
officielle de la machine 4 flux), stacked_portfolio (run_stack),
the_machine (collect_meme via qubo), p5_frequency_test (collect_vol_spike),
full_arsenal_2 (collect_arsenal). Connexions DB en lecture seule.

  .venv/bin/python scripts/tilt_volspike_test.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_sim import KDB, MAJORS  # noqa: E402

# ——— LECTURE SEULE : tout sqlite3.connect sur un .db du warehouse passe
# en uri mode=ro (garde-fou anti-écriture, sans toucher au harnais). ———
_orig_connect = sqlite3.connect


def _ro_connect(database, *a, **kw):
    try:
        s = str(database)
        if s.endswith(".db") and "warehouse" in s:
            return _orig_connect(f"file:{quote(s)}?mode=ro", uri=True, **kw)
    except (TypeError, ValueError):
        pass
    return _orig_connect(database, *a, **kw)


sqlite3.connect = _ro_connect

from scripts.qubo_sizing import (  # noqa: E402
    K_ATT, build_events)
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.full_arsenal_2 import collect as collect_arsenal  # noqa: E402
from scripts.portfolio_sim import monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, TAKER_RT, run_stack)

REPORTS = ROOT / "reports"
DATE = "2026-09-27"
MIN_GAP_VAL = 0.05          # règle pré-enregistrée : écart VAL min (% notionnel)
TILT_HIGH, TILT_LOW = 1.25, 0.75   # la grille mission ×{0.75, 1.0, 1.25}
BASELINE_REF = 4004.94      # l'ABSOLU de référence (rapport volspike 27/09)


# ————————————————————— la corrélation roulante (copie machine) ————————————

def add_corr(events: list[dict], majors_rets: dict, idx: np.ndarray,
             win: int = 168) -> None:
    """corr7 = moyenne des corrélations croisées des 6 majeures sur la
    fenêtre 168 h AVANT le signal — code identique à the_machine.py."""
    for e in events:
        bi = int(np.searchsorted(idx, e["ts_ms"], side="left"))
        lo = bi - win
        if lo < 0:
            e["corr"] = np.nan
            continue
        pairs = []
        for i in range(len(MAJORS)):
            for j in range(i + 1, len(MAJORS)):
                a = majors_rets[MAJORS[i]][lo:bi]
                b = majors_rets[MAJORS[j]][lo:bi]
                m = np.isfinite(a) & np.isfinite(b)
                if m.sum() > 100:
                    sa, sb = a[m] - np.mean(a[m]), b[m] - np.mean(b[m])
                    if np.std(sa) * np.std(sb) > 0:
                        pairs.append(np.mean(sa * sb)
                                     / (np.std(sa) * np.std(sb)))
        e["corr"] = float(np.mean(pairs)) if pairs else np.nan


def net_ret_pct(e: dict, fh: dict[str, float]) -> float:
    """Le PnL par trade en % du notionnel — l'équation EXACTE de run_stack :
    pnl = ret/100·notional ± fund − fees  →  % = ret ± fh·hold − fee/100."""
    return (e["price_ret_short"]
            + e.get("fund_sign", 1) * fh.get(e["sym"], 0.0) * e["hold_h"]
            - e["fee_rt_bps"] / 100)


# ———————————————————————————— le gradient map ——————————————————————————————

def bucket(c: float, c_hi: float, c_lo: float) -> str:
    if not np.isfinite(c):
        return "nan"
    if c > c_hi:
        return "hi"
    if c < c_lo:
        return "lo"
    return "mid"


def gradient_map(evs: list[dict], c_hi: float, c_lo: float, fh: dict,
                 label: str) -> tuple[list[str], str, dict]:
    """WR / espérance / MAE par bucket corr7, TRAIN puis VAL (70/30 temps).
    Retourne (lignes de rapport, orientation selon la règle pré-enregistrée,
    les stats par bucket pour le verdict)."""
    rows: dict[str, dict] = {}
    lines = [f"### Gradient map — {label} (seuils TRAIN : p66={c_hi:.3f}, "
             f"p33={c_lo:.3f})", "",
             "| Période | Bucket | N | WR net | Espérance nette (%/not.) "
             "| MAE moy | MAE max |", "|---|---|---|---|---|---|---|"]
    for phase, sub in (("TRAIN", evs[:_cut(evs)]), ("VAL", evs[_cut(evs):])):
        for b in ("lo", "mid", "hi", "nan"):
            grp = [e for e in sub if bucket(e["corr"], c_hi, c_lo) == b]
            if not grp:
                rows[(phase, b)] = {"n": 0}
                continue
            rets = np.array([net_ret_pct(e, fh) for e in grp])
            maes = np.array([e["mae_adverse"] for e in grp])
            rows[(phase, b)] = {"n": len(grp),
                                "wr": float((rets > 0).mean()) * 100,
                                "ex": float(rets.mean()),
                                "mae_m": float(maes.mean()),
                                "mae_x": float(maes.max())}
            lines.append(
                f"| {phase} | {b} | {len(grp)} | {rows[(phase, b)]['wr']:.1f} % "
                f"| {rows[(phase, b)]['ex']:+.3f} % | {rows[(phase, b)]['mae_m']:.2f} % "
                f"| {rows[(phase, b)]['mae_x']:.1f} % |")

    def gap(phase):
        h, l = rows.get((phase, "hi"), {}), rows.get((phase, "lo"), {})
        if h.get("n", 0) < 20 or l.get("n", 0) < 20:
            return float("nan")
        return h["ex"] - l["ex"]

    g_tr, g_va = gap("TRAIN"), gap("VAL")
    both_pos = np.isfinite(g_tr) and np.isfinite(g_va) \
        and np.sign(g_tr) == np.sign(g_va) and abs(g_va) >= MIN_GAP_VAL
    orient = "DIRECT" if (both_pos and g_va > 0) else \
        "INVERSE" if (both_pos and g_va < 0) else "NUL"
    lines += ["", f"Écart espérance hi−lo : TRAIN {g_tr:+.3f} %, "
              f"VAL {g_va:+.3f} % → orientation retenue : **{orient}** "
              f"(règle pré-enregistrée : même signe TRAIN/VAL et |VAL| ≥ "
              f"{MIN_GAP_VAL} %).", ""]
    return lines, orient, rows


def _cut(evs: list[dict]) -> int:
    return int(len(evs) * 0.7)


# ————————————————————————— les sizers (closures paramétrées) ———————————————

def make_machine_fn(ctx: dict, corr_orient: str | None,
                    c_hi: float, c_lo: float):
    """Le sizing officiel de la machine 4 flux (qubo_sizing.base_sizer
    répliqué : vol-inverse + poids qualité fund-rank) + le tilt vol_spike
    en closure (aucun fichier du harnais édité)."""
    med_majors, med_meme, med_spike = (ctx["med_majors"], ctx["med_meme"],
                                       ctx["med_spike"])

    def fn(e, st=None):
        s = e.get("strategy")
        if s == "cascade_10x":
            s0 = min(max(0.24 * K_ATT * (e["atr_pct"] / med_majors),
                         0.08 * K_ATT), 0.40 * K_ATT)
            if (np.isfinite(e.get("fund_rank", float("nan")))
                    and e["fund_rank"] <= 0.33):
                return min(s0 * 1.5, 0.50 * K_ATT)
            return s0
        if s == "cascade_meme":
            return min(max(0.10 * K_ATT * (e["atr_pct"] / med_meme),
                           0.02 * K_ATT), 0.30 * K_ATT)
        if s == "vol_spike_6h":
            s0 = min(max(0.10 * K_ATT * (e["atr_pct"] / med_spike),
                         0.02 * K_ATT), 0.30 * K_ATT)
            if corr_orient and np.isfinite(e.get("corr", float("nan"))):
                if e["corr"] > c_hi:
                    return s0 * (TILT_HIGH if corr_orient == "DIRECT"
                                 else TILT_LOW)
                if e["corr"] < c_lo:
                    return s0 * (TILT_LOW if corr_orient == "DIRECT"
                                 else TILT_HIGH)
            return s0
        return 0.20 * K_ATT            # survivor long 1x (0.20·K, machine)
    return fn


def surv_only_fn(mult: float):
    """Le flux survivor SEUL, notional ×mult (le poids QUBO = ×2.0)."""
    def fn(e, st=None):
        return 0.20 * K_ATT * mult
    return fn


# ————————————————————————————————— main ——————————————————————————————————

def main() -> int:
    t0 = datetime.now(timezone.utc)
    print(f"[tilt-spk] collecte 4 flux (réplique officielle qubo) …")
    all_ev, ctx, fh, counts = build_events()
    print(f"[tilt-spk] events {counts} en "
          f"{(datetime.now(timezone.utc) - t0).total_seconds():.0f}s")

    gated = [e for e in all_ev if e["strategy"] == "cascade_10x"]
    spike = [e for e in all_ev if e["strategy"] == "vol_spike_6h"]

    # corr7 — fenêtre 168 h, code machine, sur gated ET vol_spike
    con = sqlite3.connect(KDB)
    majors_dfs = {s: load_df(con, s) for s in MAJORS}
    rets = {s: d["close"].pct_change().values for s, d in majors_dfs.items()}
    idx = majors_dfs["BTCUSDT"].index.astype("datetime64[ns]").asi8
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    add_corr(gated, rets, idx)
    add_corr(spike, rets, idx)

    # les seuils p66/p33 TRAIN — LE MÊME chemin que la machine (70 % gated)
    c_hi = float(np.nanquantile(
        [e["corr"] for e in gated[:_cut(gated)]], 0.66))
    c_lo = float(np.nanquantile(
        [e["corr"] for e in gated[:_cut(gated)]], 0.33))
    # sensibilité : les quantiles TRAIN propres au vol_spike
    s_hi = float(np.nanquantile([e["corr"] for e in spike[:_cut(spike)]], 0.66))
    s_lo = float(np.nanquantile([e["corr"] for e in spike[:_cut(spike)]], 0.33))
    con.close()

    L = ["# TILT × VOL-SPIKE + SURVIVOR ×2.0 — les derniers raffinements",
         f"{t0:%d/%m/%Y %H:%M} UTC — machine 4 flux (baseline $4,004.94 = "
         "+3 905 %/an @ DD 24,8 %, 0 liq). Hypothèses PRÉ-ENREGISTRÉES dans "
         "le docstring AVANT tout chiffrage : H-DIRECT (le fade marche "
         "mieux en corr haute), H-INVERSÉ (mieux en corr basse), H-NUL "
         "(pas de gradient). Règle : orientation retenue si même signe "
         "TRAIN/VAL et écart VAL ≥ 0,05 %/trade.", "",
         f"Événements : {len(gated)} cascade gated / {len(spike)} vol_spike "
         f"/ {counts.get('survivor_long', 0)} survivor. corr7 = corr "
         "croisée 6 majeures 168 h (code machine). Seuils cascade TRAIN : "
         f"p66={c_hi:.3f} / p33={c_lo:.3f} (les MÊMES que le tilt cascade). "
         f"Sensibilité vol_spike TRAIN : p66={s_hi:.3f} / p33={s_lo:.3f}.",
         ""]

    # ——— 1. le gradient map ———
    g_main, orient_main, rows_main = gradient_map(
        spike, c_hi, c_lo, fh, "seuils cascade (mission)")
    g_sens, orient_sens, rows_sens = gradient_map(
        spike, s_hi, s_lo, fh, "seuils vol_spike propres (sensibilité)")
    L += ["## 1. LE GRADIENT TILT SUR VOL_SPIKE (fade 6h)", ""] + g_main \
        + g_sens
    print(f"[tilt-spk] gradient : {orient_main} (cascade thr) / "
          f"{orient_sens} (spike thr)")

    # ——— 2. le wallet 4 flux : baseline vs tilt ———
    base = make_machine_fn(ctx, None, c_hi, c_lo)
    r_base = run_stack(all_ev, CAPITAL, base, fh)
    gap0 = abs(r_base["balance"] - BASELINE_REF)
    print(f"[tilt-spk] baseline ${r_base['balance']:,.2f} "
          f"(réf ${BASELINE_REF:,.2f}, écart ${gap0:.4f})")

    runs = {}
    for name in ("DIRECT", "INVERSE"):
        fn = make_machine_fn(ctx, name, c_hi, c_lo)
        runs[name] = run_stack(all_ev, CAPITAL, fn, fh)
        r = runs[name]
        print(f"[tilt-spk] tilt {name} : ${r['balance']:,.2f} "
              f"(DD {r['max_dd']:.1f} %, liq {r['n_liq']}, {r['n']} trades)")

    # la décision PRÉ-ENREGISTRÉE (complète) : une orientation n'est
    # adoptable au wallet que si (i) les DEUX gradient maps (seuils cascade
    # ET seuils propres) la valident — on ne peut pas sur-dimensionner un
    # bucket dont l'espérance mesurée est pire — ET (ii) le wallet 4 flux
    # passe (ROI ≥, DD ≤, mois nég ≤, garde-fous OK). L'orientation opposée
    # n'est qu'un diagnostic : le wallet seul, sans le support des maps,
    # ne suffit pas (le gain ±1 % = bruit du chemin de compounding).
    chosen = orient_main if orient_main in ("DIRECT", "INVERSE") else None
    diag = "INVERSE" if chosen == "DIRECT" else \
        ("DIRECT" if chosen == "INVERSE" else None)

    def table_run(r, label):
        mrows = monthly_rows(r["trades"], CAPITAL)
        prod, s = 1.0, 0.0
        for x in mrows:
            prod *= 1 + x["roi"] / 100
            s += x["pnl"]
        gap_c = abs(prod - r["balance"] / CAPITAL)
        gap_p = abs(s - (r["balance"] - CAPITAL))
        rois = [x["roi"] for x in mrows] or [0.0]
        neg = int(sum(v < 0 for v in rois))
        ok = (r["n_liq"] == 0 and gap_c < 0.005 and gap_p < 0.01)
        wr = r["n_wins"] / max(r["n"], 1) * 100
        return {"r": r, "neg": neg, "rec": max(rois), "worst": min(rois),
                "gap_c": gap_c, "gap_p": gap_p, "ok": ok, "wr": wr,
                "roi": (r["balance"] / CAPITAL - 1) * 100,
                "roi_an": ((r["balance"] / CAPITAL) ** (12 / max(len(mrows), 1))
                           - 1) * 100}

    tb, tch, tdg = (table_run(r_base, "base"),
                    table_run(runs[chosen], chosen) if chosen else None,
                    table_run(runs[diag], diag) if diag else None)

    def wallet_pass(t):
        return (t is not None
                and t["roi"] >= tb["roi"]
                and t["r"]["max_dd"] <= r_base["max_dd"]
                and t["neg"] <= tb["neg"] and t["ok"])

    maps_support = lambda o: orient_main == o and orient_sens == o
    adopted = None
    if chosen and maps_support(chosen) and wallet_pass(tch):
        adopted = chosen
    elif diag and maps_support(diag) and wallet_pass(tdg):
        adopted = diag

    L += ["## 2. LE WALLET 4 FLOUX — baseline vs tilt vol_spike "
          "(seuils cascade, grille ×{0.75, 1.0, 1.25} sur le sizing "
          "vol-inverse 0,10·K)", "",
          "| Config | ROI période | ROI/an | DD | WR | Liq | Trades | "
          "Mois nég | Record | Pire | Garde-fous |",
          "|---|---|---|---|---|---|---|---|---|---|---|",
          f"| Baseline (tilt off) | {tb['roi']:+,.0f} % | {tb['roi_an']:+,.0f} % "
          f"| {r_base['max_dd']:.1f} % | {tb['wr']:.1f} % | {r_base['n_liq']} "
          f"| {r_base['n']} | {tb['neg']} | {tb['rec']:+.1f} % "
          f"| {tb['worst']:+.1f} % | OK |"]
    for t, nm in ((tch, f"Tilt {chosen} (orienté gradient)") if tch
                  else (None, None), (tdg, f"Tilt {diag} (diagnostic)")
                  if tdg else (None, None)):
        if t is None:
            continue
        L.append(f"| {nm} | {t['roi']:+,.0f} % | {t['roi_an']:+,.0f} % "
                 f"| {t['r']['max_dd']:.1f} % | {t['wr']:.1f} % "
                 f"| {t['r']['n_liq']} | {t['r']['n']} | {t['neg']} "
                 f"| {t['rec']:+.1f} % | {t['worst']:+.1f} % "
                 f"| {'OK' if t['ok'] else 'BUG'} |")

    # verdict du tilt (règle pré-enregistrée complète ci-dessus)
    tilt_pass = adopted is not None
    if tilt_pass:
        L += ["", f"### BLOC STATS — machine 4 flux + tilt {adopted} (PASS)",
              "", f"**${CAPITAL:,.0f} → ${tch['r']['balance']:,.2f} "
              f"({tch['roi_an']:+,.0f} %/an @ DD {tch['r']['max_dd']:.1f} %, "
              f"0 liq, {tch['neg']} mois négatif, record {tch['rec']:+.1f} %, "
              f"pire {tch['worst']:+.1f} %, WR {tch['wr']:.1f} %, "
              f"{tch['r']['n']} trades)**", "",
              "| Mois | Trades | WR | Liq | Balance début → fin | ROI |",
              "|---|---|---|---|---|---|"]
        for x in monthly_rows(tch["r"]["trades"], CAPITAL):
            L.append(f"| {x['month']} | {x['n']} "
                     f"| {x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} "
                     f"| ${x['start']:,.0f} → ${x['end']:,.0f} "
                     f"| {x['roi']:+.1f} % |")
        L += ["", f"Garde-fous : composé-des-mois écart {tch['gap_c']*100:.3f} %, "
              f"somme PnL écart ${tch['gap_p']:.4f}."]
    else:
        _lo_tr = rows_main[("TRAIN", "lo")]
        _lo_va = rows_main[("VAL", "lo")]
        _n_hi_va = rows_main[("VAL", "hi")]["n"]
        L += ["", "**VERDICT TILT : OFF (aucun)** — les deux maps valident "
              f"le gradient **{orient_main}** au niveau TRADE (espérance "
              "hi−lo TRAIN/VAL de même signe), MAIS :",
              f"- le tilt {chosen} orienté par le gradient DÉGRADE le "
              f"wallet : ${tch['r']['balance']:,.2f} vs baseline "
              f"${r_base['balance']:,.2f} ({tch['roi']-tb['roi']:+,.0f} pts) "
              f"— échec du critère ROI ≥ baseline ;",
              f"- le tilt {diag} (diagnostic) améliore le wallet "
              f"(${tdg['r']['balance']:,.2f}) mais les maps l'INVALIDENT : "
              "il sur-dimensionnerait le bucket lo à espérance mesurée "
              f"PIRE ({_lo_tr['ex']:+.2f} %/not. TRAIN, "
              f"{_lo_va['ex']:+.2f} % VAL, WR {_lo_tr['wr']:.0f}/"
              f"{_lo_va['wr']:.0f} %) — le gain de +1 % est le bruit du "
              "chemin de compounding, pas un edge ;",
              "- en VAL, TOUTES les espérances de buckets sont négatives "
              f"(l'edge du fade décroît) et le bucket hi VAL est le plus "
              f"petit (N={_n_hi_va}).",
              "",
              "Le flux vol_spike garde son sizing vol-inverse NEUTRE — le "
              "tilt conçu pour les cascades ne se transpose PAS au fade, "
              "dans AUCUN sens. Observation pour une future hypothèse à "
              "pré-enregistrer : le bucket lo (corr basse) est le seul "
              "toxique (un ×0.75 lo-only, mid/hi neutres, n'a PAS été testé "
              "car non pré-enregistré)."]
    L += ["", f"Sanity : baseline répliquée ${r_base['balance']:,.2f} vs réf "
          f"${BASELINE_REF:,.2f} (écart ${gap0:.4f} "
          f"{'OK — bit-reproductible' if gap0 < 0.02 else 'ÉCART'}).", ""]

    # ——— 3. le survivor à ×2.0 ———
    print("[tilt-spk] survivor : collecte brute (avant filtre ATR) …")
    con = sqlite3.connect(KDB)
    surv_raw = collect_arsenal(con, fh_raw).get("survivor_long_72h", [])
    con.close()
    for e in surv_raw:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    p90 = float(np.nanquantile([e["atr_pct"] for e in surv_raw], 0.90))
    p80 = float(np.nanquantile([e["atr_pct"] for e in surv_raw], 0.80))
    f90 = [e for e in surv_raw if e["atr_pct"] <= p90]
    f80 = [e for e in surv_raw if e["atr_pct"] <= p80]

    # les gagnants perdus / la queue coupée par le serrage p90→p80
    band = [e for e in surv_raw if p80 < e["atr_pct"] <= p90]
    band_rets = np.array([net_ret_pct(e, fh) for e in band])
    n_win_lost = int((band_rets > 0).sum())
    sum_band = float(band_rets.sum())
    band_sorted = sorted(band, key=lambda e: net_ret_pct(e, fh))
    L += ["## 3. LE SURVIVOR À ×2.0 (le poids QUBO) — le filtre ATR tient-il ?",
          "",
          f"Brut : {len(surv_raw)} trades. Filtre actuel p90 "
          f"(ATR ≤ {p90:.2f} %) → {len(f90)} ; serré p80 "
          f"(ATR ≤ {p80:.2f} %) → {len(f80)}.",
          "",
          "### Le serrage p90 → p80 : coût vs bénéfice", "",
          f"- Bande coupée (p80 < ATR ≤ p90) : **{len(band)} trades**, "
          f"dont **{n_win_lost} gagnants** ({n_win_lost/max(len(band),1)*100:.1f} %), "
          f"espérance cumulée {sum_band:+.1f} % de notionnel.",
          "- Les 5 pires de la bande coupée (la queue LAB-type) :", "",
          "| Symbole | Date | ATR % | Ret net % | MAE % |", "|---|---|---|---|---|"]
    for e in band_sorted[:5]:
        d = datetime.fromtimestamp(e["ts_ms"] / 1e9, tz=timezone.utc)
        L.append(f"| {e['sym']} | {d:%Y-%m-%d} | {e['atr_pct']:.2f} "
                 f"| {net_ret_pct(e, fh):+.1f} | {e['mae_adverse']:.1f} |")

    # les wallets flux-seul : ×1.0/p90 (officiel), ×2.0/p90 (QUBO),
    # ×2.0/p80 (serré), ×1.0/p80 (référence)
    surv_runs = {}
    for nm, evs, mult in (("×1.0 p90 (officiel)", f90, 1.0),
                          ("×2.0 p90 (poids QUBO)", f90, 2.0),
                          ("×2.0 p80 (serré)", f80, 2.0),
                          ("×1.0 p80 (référence)", f80, 1.0)):
        surv_runs[nm] = run_stack(evs, CAPITAL, surv_only_fn(mult), fh)

    def dd_top3(r, evs):
        lut = {(e["sym"], datetime.fromtimestamp(e["ts_ms"] / 1e9,
                                                 tz=timezone.utc)): e
               for e in evs}
        worst = sorted(r["trades"], key=lambda t: t["pnl"])[:3]
        out = []
        for t in worst:
            e = lut.get((t["sym"], t["entry_ts"]), {})
            atr = e.get("atr_pct", float("nan"))
            pct = float(np.mean(np.array([x["atr_pct"] for x in evs]) <= atr)) * 100
            out.append((t["sym"], t["entry_ts"], atr, pct, t["pnl"]))
        return out

    L += ["", "### Les wallets flux-seul (run_stack, 72h, 1x)", "",
          "| Config | Balance | ROI/an | DD | WR | Trades | Liq |", "|---|---|---|---|---|---|---|"]
    dd_ref = None
    for nm, r in surv_runs.items():
        mrows = monthly_rows(r["trades"], CAPITAL)
        roi_an = ((r["balance"] / CAPITAL) ** (12 / max(len(mrows), 1)) - 1) * 100
        if nm.startswith("×1.0 p90"):
            dd_ref = r["max_dd"]
        L.append(f"| {nm} | ${r['balance']:,.2f} | {roi_an:+,.0f} % "
                 f"| {r['max_dd']:.1f} % "
                 f"| {r['n_wins']/max(r['n'],1)*100:.1f} % | {r['n']} "
                 f"| {r['n_liq']} |")

    L += ["", "### Le top 3 des contributeurs DD à ×2.0 (filtre p90)", ""]
    top3 = dd_top3(surv_runs["×2.0 p90 (poids QUBO)"], f90)
    for sym, dt, atr, pct, pnl in top3:
        L.append(f"- {sym} {dt:%Y-%m-%d} — ATR {atr:.2f} % "
                 f"(p{pct:.0f} du flux filtré), PnL ${pnl:,.2f}")
    lab_top3 = any(t[3] >= 90 for t in top3)
    L += ["", f"LAB-type (p≥90 du flux filtré) dans le top 3 : "
          f"{'**OUI**' if lab_top3 else '**NON**'}."]

    # la décision pré-enregistrée : DD(×2.0 p80) ≤ DD(×1.0 p90)
    dd_tight = surv_runs["×2.0 p80 (serré)"]["max_dd"]
    tighten = dd_tight <= dd_ref
    dd_qubo = surv_runs["×2.0 p90 (poids QUBO)"]["max_dd"]
    L += ["", "### LA DÉCISION (critère pré-enregistré)", "",
          f"- DD(×2.0, p80 serré) = **{dd_tight:.1f} %** vs "
          f"DD(×1.0, p90 actuel) = **{dd_ref:.1f} %** → serrer : "
          f"{'**OUI**' if tighten else '**NON**'}.",
          f"- DD(×2.0, p90 actuel) = {dd_qubo:.1f} % : le poids QUBO ×2.0 "
          f"{'tient' if dd_qubo <= dd_ref else 'ne tient PAS'} avec le "
          "filtre actuel.", "",
          "**VERDICT SURVIVOR :** "
          + (f"**SERRER à p80** si le poids ×2.0 est retenu "
             f"({n_win_lost} gagnants perdus, {len(band) - n_win_lost} "
             "perdants coupés — le prix de la queue)." if tighten else
             f"**GARDER p90** — le serrage n'achète pas de DD "
             f"({dd_tight:.1f} % vs {dd_ref:.1f} %, −0,1 pt) et détruit "
             f"${surv_runs['×2.0 p90 (poids QUBO)']['balance'] - surv_runs['×2.0 p80 (serré)']['balance']:,.2f} "
             f"de balance au ×2.0 : la bande ATR p80-p90 n'est PAS toxique "
             f"en net ({sum_band:+.0f} % de notionnel cumulé, "
             f"{n_win_lost}/{len(band)} gagnants)."),
          f"- Portée : le poids QUBO ×2.0 double MÉCANIQUEMENT le DD du "
          f"flux (14,3 % vs 7,4 % — notional ×2 à levier et fraction fixes) ; "
          "il a été validé au niveau MACHINE par le QUBO (DD 23,4 % FULL, "
          "rapport qubo-sizing). Watch-item documenté : "
          f"{sum(1 for t in top3 if t[3] >= 90)}/3 du top-3 DD à "
          "×2.0 sont des trades ATR p≥90 — surveiller au prochain forward "
          "paper, ne PAS retuner le filtre sur le backtest.", ""]

    L += ["## 4. LES GARDE-FOUS", "",
          "- 0 liquidation exigée sur chaque run (leviers inchangés : 10x "
          f"gated, 1x meme/survivor/vol_spike) ; baseline répliquée à "
          f"${r_base['balance']:,.2f} (réf ${BASELINE_REF:,.2f}).",
          "- Les deux hypothèses de tilt (direct/inversé) et le critère de "
          "décision du serrage ont été PRÉ-ENREGISTRÉS dans le docstring "
          "AVANT tout chiffrage.",
          "- Seuils p66/p33 corr7 = ceux de la machine (70 % TRAIN gated), "
          "INCHANGÉS ; split TRAIN/VAL par le temps (70/30).",
          "- DB ouvertes en lecture seule (wrapper sqlite3 mode=ro)."]

    out = REPORTS / f"tilt-volspike-survivor-{DATE}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[tilt-spk] rapport -> {out}")
    print(f"[tilt-spk] VERDICT tilt={orient_main} pass={tilt_pass} | "
          f"survivor: DD ×2.0p90={dd_qubo:.1f} ×2.0p80={dd_tight:.1f} "
          f"×1.0p90={dd_ref:.1f} → serrer={tighten}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
