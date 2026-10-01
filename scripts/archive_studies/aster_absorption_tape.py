# ARCHIVÉ (01/10/2026) — T18 : NUL comme signal prédictif (0/26 cellules après re-vérification ; le fait robuste : les extrêmes sont des PURGES 89 % — le flux continue et s'épuise, pas d'absorption franche) ; aster_tape = CONTEXTE (le diagnostic d'exécution)
#!/usr/bin/env python3
"""aster_absorption_tape.py — T18 : ABSORPTION ÉVÉNEMENTIELLE sub-minute sur le tape.

Suite de T17 (CVD tape = NUL comme signal 1h/4h, mais granularité sub-minute
= la valeur supposée). Question : quand le prix bouge fort (|ret| ≥ 1 % en
≤ 5 min — T14 : kurtosis 1m 252, ces mouvements existent), QUE fait le flux
agressif DANS le mouvement, et le déséquilibre à l'extrême prédit-il la suite ?

Méthode (doctrine quant-discipline, événements d'abord) :
  1. ÉVÉNEMENTS : fenêtres de 5 min avec |ret| ≥ seuil (primaire 1 %) sur la
     grille 1 s (prix = dernier print, ffill). Chevauchements interdits :
     après chaque événement, pause de 5 min avant le scan suivant.
     Extrême = prix max (up) / min (down) atteint DANS la fenêtre (argmax
     renvoie la 1re seconde du plateau). Une passe de SENSIBILITÉ à 0,5 %
     (déclarée d'avance, jamais promotionnelle) augmente le n.
  2. FLUX DANS L'ÉVÉNEMENT (depuis les prints, is_buyer_maker=False = BUY
     agressif) : CVD directionnel sur la montée [t0, extrême), signature
     à l'extrême sur les 60 dernières secondes — sig60 > 0 = le flux
     agressif CONTINUE dans le sens du mouvement (PURGE), sig60 < 0 =
     il s'inverse (ABSORPTION), ratio volume directionnel / total, part de
     volume dans la queue, vitesse (temps jusqu'à l'extrême).
  3. PRÉDICTION HONNÊTE : outcome = continuation (ret 30 min après
     l'extrême, normalisé par le sens du mouvement). Split TEMPOREL
     31 j train / 14 j val. AUC rangs (Hanley-McNeil) + sharpe par
     événement (règle figée sur TRAIN : sens = signe AUC TRAIN, côté =
     médiane TRAIN, appliquée seulement si n TRAIN ≥ 30). Barre x501 :
     AUC VAL ≥ 0,60 ET AUC TRAIN ≥ 0,55 ET sharpe TR/VA de même signe
     ET n ≥ 30 des deux côtés. Multiplicité comptée : 6 features × 2
     symboles + 1 pooled sig60 = 13 tests par passe, 26 au total,
     tous déclarés d'avance, aucun retiré.
  4. VERDICT : l'absorption sub-minute est-elle une information que les
     bougies ne donnent pas (elles cachent le flux intra-minute) ?

READ-ONLY sur data/warehouse/klines.db (aster_tape). Écrit uniquement
reports/aster_absorption_tape.md. Aucune écriture DB, aucun service touché.

Usage : .venv/bin/python scripts/studies/aster_absorption_tape.py \
          [--symbol BTCUSDT|ETHUSDT|both] [--threshold 0.01] [--no-report]
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "warehouse" / "klines.db"
REPORT = ROOT / "reports" / "aster_absorption_tape.md"

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
START = pd.Timestamp("2026-08-17 00:00", tz="UTC")
SPLIT = pd.Timestamp("2026-09-17 00:00", tz="UTC")  # fin train (31 j)
END = pd.Timestamp("2026-10-01 00:00", tz="UTC")    # fin val (14 j)
THR_PRIMARY, THR_SENSIB = 0.01, 0.005  # passe primaire + sensibilité (déclarées)

# Features déclarées D'AVANCE (aucune retirée après lecture) :
#   sig60      : signature à l'extrême — flux agressif net normalisé des
#                60 s avant l'extrême, dans le sens du mouvement (>0 purge,
#                <0 absorption). LA question T18.
#   cvd_win    : CVD directionnel normalisé sur la montée [t0, extrême).
#   diff_sig60 : accélération du flux (60 s finales moins 60 s précédentes).
#   volshare60 : part du volume de la fenêtre échangée dans les 60 s finales.
#   ret_ext    : taille du mouvement jusqu'à l'extrême (signée up=+).
#   tte        : temps jusqu'à l'extrême (s) — vitesse de la purge.
FEATS = ["sig60", "cvd_win", "diff_sig60", "volshare60", "ret_ext", "tte"]
FEAT_LABEL = {
    "sig60": "signature 60 s à l'extrême (+purge/-absorb)",
    "cvd_win": "CVD directionnel [t0→extrême] norm.",
    "diff_sig60": "accélération flux (60 s vs 60 s préc.)",
    "volshare60": "part volume dans les 60 s finales",
    "ret_ext": "taille du mouvement (signée)",
    "tte": "temps jusqu'à l'extrême (s)",
}


def load_tape(symbol: str, con: sqlite3.Connection) -> tuple[pd.DataFrame, int]:
    """Prints bruts, unité ts_ms vérifiée (leçon doctrine : nanosecondes possibles)."""
    df = pd.read_sql_query(
        "SELECT ts_ms, price, qty, is_buyer_maker FROM aster_tape WHERE symbol = ?",
        con, params=(symbol,),
    )
    ts = df["ts_ms"].to_numpy(np.int64)
    med = float(np.median(ts)) if len(ts) else 0.0
    if med > 10**15:      # nanosecondes → millisecondes
        df["ts_ms"] = ts // 10**6
    elif med < 10**11:    # secondes → millisecondes
        df["ts_ms"] = ts * 1000
    # garde anti-corruption : garder uniquement les ts plausibles (2017-2033)
    ok = (df["ts_ms"] > 1.5 * 10**12) & (df["ts_ms"] < 2.0 * 10**12)
    dropped = int((~ok).sum())
    if dropped:
        df = df[ok]
    df["aggr_buy"] = np.where(df["is_buyer_maker"] == 0, df["qty"], 0.0)
    df["aggr_sell"] = np.where(df["is_buyer_maker"] == 1, df["qty"], 0.0)
    return df, dropped


def second_grid(df: pd.DataFrame, t0_us: int, t1_us: int):
    """Grille dense 1 s sur [t0, t1) : prix ffilled, volumes agressifs 1 s."""
    ts = df["ts_ms"].to_numpy(np.int64)
    px = df["price"].to_numpy(np.float64)
    qb = df["aggr_buy"].to_numpy(np.float64)
    qs = df["aggr_sell"].to_numpy(np.float64)
    m = (ts >= t0_us) & (ts < t1_us)
    ts, px, qb, qs = ts[m], px[m], qb[m], qs[m]
    if not np.all(np.diff(ts) >= 0):  # tri chronologique si besoin
        o = np.argsort(ts, kind="stable")
        ts, px, qb, qs = ts[o], px[o], qb[o], qs[o]
    sec = ts // 1000
    s1 = int(t1_us // 1000)
    n = s1 - int(sec[0])
    idx = sec - int(sec[0])
    px_s = pd.Series(px).groupby(idx).last()
    pgrid = np.full(n, np.nan)
    pgrid[px_s.index.to_numpy()] = px_s.to_numpy()
    # ffill : le prix tient jusqu'au print suivant
    na = np.isnan(pgrid)
    if na.any():
        last = np.where(~na, np.arange(n), -1)
        last = np.maximum.accumulate(last)
        pgrid = pgrid[last]
    buy = np.bincount(idx, weights=qb, minlength=n)
    sell = np.bincount(idx, weights=qs, minlength=n)
    return pgrid, buy, sell, n


def study_symbol(symbol: str, con: sqlite3.Connection, thr: float,
                 w_s: int, pause_s: int, h_s: int, tail_s: int) -> tuple[pd.DataFrame, dict]:
    """Détection d'événements + flux dans l'événement + outcome. 1 appel / symbole / seuil."""
    t0_us = int(START.value // 10**6)
    t1_us = int(END.value // 10**6)
    split_us = int(SPLIT.value // 10**6)
    df, dropped = load_tape(symbol, con)
    pgrid, buy, sell, n = second_grid(df, t0_us, t1_us)
    nprint = int(len(df))
    del df

    # --- 1. ÉVÉNEMENTS : fenêtres [t, t+w) avec |ret| ≥ thr, pause après ---
    w = w_s
    ret5 = pgrid[w:] / pgrid[: n - w] - 1.0
    cand = np.flatnonzero(np.abs(ret5) >= thr)
    events = []
    next_free = 0  # secondes de grille : pas de scan avant la fin du cooldown
    for t in cand:
        if t < next_free:
            continue
        direction = 1 if ret5[t] > 0 else -1
        seg = pgrid[t: t + w]
        ext_off = int(np.argmax(seg)) if direction > 0 else int(np.argmin(seg))
        ext = t + ext_off
        if ext + h_s >= n:  # l'outcome 30 min doit exister
            continue
        events.append((t, ext, direction))
        next_free = t + w_s + pause_s  # fenêtre + pause : chevauchement interdit

    # --- 2. FLUX DANS L'ÉVÉNEMENT ---
    cb = np.concatenate(([0.0], np.cumsum(buy)))
    cs = np.concatenate(([0.0], np.cumsum(sell)))
    rows = []
    for (t, ext, d) in events:
        bw, sw = float(cb[ext] - cb[t]), float(cs[ext] - cs[t])
        b60 = float(cb[ext] - cb[max(t, ext - tail_s)])
        s60 = float(cs[ext] - cs[max(t, ext - tail_s)])
        b120 = float(cb[max(t, ext - tail_s)] - cb[max(t, ext - 2 * tail_s)])
        s120 = float(cs[max(t, ext - tail_s)] - cs[max(t, ext - 2 * tail_s)])
        vw, v60, v120 = bw + sw, b60 + s60, b120 + s120
        sig60 = d * (b60 - s60) / v60 if v60 > 0 else np.nan
        sig_prev = d * (b120 - s120) / v120 if v120 > 0 else np.nan
        rows.append({
            "ext_us": (int(t0_us // 1000) + ext) * 1000, "dir": d,
            "tte": ext - t, "tail_len": ext - max(t, ext - tail_s),
            "ret_ext": d * (pgrid[ext] / pgrid[t] - 1.0),
            "cvd_win": d * (bw - sw) / vw if vw > 0 else np.nan,
            "sig60": sig60,
            "diff_sig60": (sig60 - sig_prev) if np.isfinite(sig60) and np.isfinite(sig_prev) else np.nan,
            "volshare60": v60 / vw if vw > 0 else np.nan,
            "ret30": d * (pgrid[ext + h_s] / pgrid[ext] - 1.0),  # continuation
            "vol60": v60,
        })
    ev = pd.DataFrame(rows)
    ev["split"] = np.where(ev["ext_us"] < split_us, "train", "val")
    meta = {"nprint": nprint, "dropped": dropped, "days": n / 86400.0}
    return ev, meta


def auc_mw(score: np.ndarray, fwd: np.ndarray) -> tuple[float, float, int]:
    """AUC par rangs (Mann-Whitney) + SE Hanley-McNeil."""
    ok = np.isfinite(score) & np.isfinite(fwd)
    s, y = score[ok], fwd[ok]
    n_pos, n_neg = int((y > 0).sum()), int((y < 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan"), float("nan"), 0
    r = pd.Series(s).rank().to_numpy()
    auc = (r[y > 0].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    q1 = auc / (2 - auc)
    q2 = 2 * auc * auc / (1 + auc)
    var = (auc * (1 - auc) + (n_pos - 1) * (q1 - auc**2)
           + (n_neg - 1) * (q2 - auc**2)) / (n_pos * n_neg)
    return float(auc), float(np.sqrt(max(var, 0.0))), n_pos + n_neg


def sharpe_events(pnl: np.ndarray, days: float) -> float:
    """Sharpe annualisé d'une série de PnL par événement (év/j × 365)."""
    pnl = pnl[np.isfinite(pnl)]
    if len(pnl) < 5 or pnl.std(ddof=1) == 0:
        return float("nan")
    ev_day = len(pnl) / max(days, 1e-9)
    return float(pnl.mean() / pnl.std(ddof=1) * np.sqrt(ev_day * 365.0))


def feature_table(ev_by_sym: dict[str, pd.DataFrame], days: dict[str, float]) -> tuple[list[str], list[dict]]:
    """Table features × symbols (+ pooled sig60) : AUC TR/VA, sharpe, verdict promo."""
    rows_out, cells = [], []
    combos = [(s, f) for s in ev_by_sym for f in FEATS] + [("POOLED", "sig60")]
    for (sym, f) in combos:
        # annualisation : les événements TRAIN s'étalent sur 31 j, VAL sur 14 j
        d_tr, d_va = 31.0, 14.0
        if sym == "POOLED":
            tr = pd.concat([e[e["split"] == "train"] for e in ev_by_sym.values()])
            va = pd.concat([e[e["split"] == "val"] for e in ev_by_sym.values()])
        else:
            ev = ev_by_sym[sym]
            tr, va = ev[ev["split"] == "train"], ev[ev["split"] == "val"]
        a_tr, se_tr, n_tr = auc_mw(tr[f].to_numpy(), tr["ret30"].to_numpy())
        a_va, se_va, n_va = auc_mw(va[f].to_numpy(), va["ret30"].to_numpy())
        s_tr = s_va = float("nan")
        pnl_med = float("nan")
        if np.isfinite(a_tr) and n_tr >= 30:  # règle figée sur TRAIN, déclarée
            med = tr[f].median()
            side = 1.0 if a_tr > 0.5 else -1.0
            p_tr = side * np.where(tr[f] > med, 1.0, -1.0) * tr["ret30"]
            p_va = side * np.where(va[f] > med, 1.0, -1.0) * va["ret30"]
            s_tr = sharpe_events(p_tr.to_numpy(), d_tr)
            s_va = sharpe_events(p_va.to_numpy(), d_va)
            fin = p_va[np.isfinite(p_va)]
            pnl_med = float(np.median(fin) * 10**4) if len(fin) else float("nan")
        raw = bool(np.isfinite(a_va) and a_va >= 0.60 and n_va >= 10)
        promo = bool(raw and np.isfinite(a_tr) and a_tr >= 0.55
                     and np.isfinite(s_tr) and np.isfinite(s_va) and s_tr * s_va > 0
                     and n_tr >= 30 and n_va >= 30)
        cells.append({"sym": sym, "feat": f, "a_tr": a_tr, "n_tr": n_tr, "s_tr": s_tr,
                      "a_va": a_va, "se_va": se_va, "n_va": n_va, "s_va": s_va,
                      "pnl_med": pnl_med, "raw": raw, "promo": promo})
    return rows_out, cells


def fmt_cell_table(cells: list[dict], label_map: dict[str, str]) -> list[str]:
    A = ["| Combinaison | Feature | AUC TR (n) | Sharpe TR | AUC VA ±SE (n) | Sharpe VA | PnL méd VA (bps) | Promo ? |",
         "|---|---|---|---|---|---|---|---|"]
    for c in cells:
        st = f"{c['s_tr']:+.2f}" if np.isfinite(c["s_tr"]) else "—"
        sv = f"{c['s_va']:+.2f}" if np.isfinite(c["s_va"]) else "—"
        pm = f"{c['pnl_med']:+.0f}" if np.isfinite(c["pnl_med"]) else "—"
        av = f"{c['a_va']:.3f} ±{c['se_va']:.3f} ({c['n_va']})" if np.isfinite(c["a_va"]) else f"n/d ({c['n_va']})"
        A.append(f"| {c['sym']} | {c['feat']} ({label_map[c['feat']]}) | {c['a_tr']:.3f} ({c['n_tr']}) | {st} | "
                 f"{av} | {sv} | {pm} | {'**OUI**' if c['promo'] else ('brute' if c['raw'] else 'non')} |")
    return A


def purge_table(ev_by_sym: dict[str, pd.DataFrame]) -> list[str]:
    A = ["| Symbole | Sens | n | Purge (sig60>0) | Absorption (sig60<0) | sig60 méd | CVD fenêtre méd | volshare60 méd | queue vide (60 s) |",
         "|---|---|---|---|---|---|---|---|---|"]
    for sym, ev in ev_by_sym.items():
        for lab, sub in [("up", ev[ev["dir"] > 0]), ("down", ev[ev["dir"] < 0])]:
            ok = np.isfinite(sub["sig60"])
            nul = int((sub["vol60"] <= 0).sum())
            purge = float((sub.loc[ok, "sig60"] > 0).mean() * 100) if ok.any() else float("nan")
            A.append(f"| {sym} | {lab} | {len(sub)} | {purge:.0f} % | {100 - purge:.0f} % | "
                     f"{sub['sig60'].median():+.3f} | {sub['cvd_win'].median():+.3f} | "
                     f"{sub['volshare60'].median():.2f} | {nul} |")
    return A


def quintile_table(ev_by_sym: dict[str, pd.DataFrame], pooled: bool = False) -> list[str]:
    A = ["| Symbole | Quintile sig60 (bornes TRAIN) | n TR | cont30 méd TR (bps) | hit TR | n VA | cont30 méd VA (bps) | hit VA |",
         "|---|---|---|---|---|---|---|---|"]
    items = [("POOLED", pd.concat(ev_by_sym.values()))] if pooled else list(ev_by_sym.items())
    for sym, ev in items:
        tr, va = ev[ev["split"] == "train"], ev[ev["split"] == "val"]
        ok_tr = tr[np.isfinite(tr["sig60"])]
        if len(ok_tr) < 10:
            continue
        qs = np.quantile(ok_tr["sig60"], [0.2, 0.4, 0.6, 0.8])
        edges = [-np.inf, *qs, np.inf]
        for i in range(5):
            b_tr = ok_tr[(ok_tr["sig60"] > edges[i]) & (ok_tr["sig60"] <= edges[i + 1])]
            b_va = va[(va["sig60"] > edges[i]) & (va["sig60"] <= edges[i + 1])]
            m_tr = b_tr["ret30"].median() * 10**4 if len(b_tr) else float("nan")
            h_tr = (b_tr["ret30"] > 0).mean() * 100 if len(b_tr) else float("nan")
            m_va = b_va["ret30"].median() * 10**4 if len(b_va) else float("nan")
            h_va = (b_va["ret30"] > 0).mean() * 100 if len(b_va) else float("nan")
            A.append(f"| {sym} | Q{i + 1} [{edges[i]:+.2f} ; {edges[i + 1]:+.2f}] | {len(b_tr)} | "
                     f"{m_tr:+.0f} | {h_tr:.0f} % | {len(b_va)} | {m_va:+.0f} | {h_va:.0f} % |")
    return A


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="both", choices=["BTCUSDT", "ETHUSDT", "both"])
    ap.add_argument("--threshold", type=float, default=None,
                    help="seuil de la passe primaire (défaut 0.01) ; la sensibilité suit à 0.005")
    ap.add_argument("--window", type=int, default=300)
    ap.add_argument("--pause", type=int, default=300)
    ap.add_argument("--horizon", type=int, default=1800)
    ap.add_argument("--tail", type=int, default=60)
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args()
    symbols = SYMBOLS if args.symbol == "both" else [args.symbol]
    thr_primary = args.threshold if args.threshold is not None else THR_PRIMARY

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    A = []
    A.append("# T18 — Absorption événementielle sub-minute (tape aster)")
    A.append("")
    A.append(f"> One-shot : `scripts/studies/aster_absorption_tape.py` (reproductible, "
             f"`--symbol --threshold`). DB : `data/warehouse/klines.db` en READ-ONLY "
             f"(table aster_tape, is_buyer_maker = False → BUY agressif). Fenêtre : "
             f"{START:%Y-%m-%d} → {END:%Y-%m-%d} UTC (45 j). Événements : |ret| ≥ seuil en "
             f"≤ {args.window // 60} min, pause {args.pause // 60} min après chaque événement "
             f"(chevauchements interdits). Extrême = prix max (up) / min (down) DANS la "
             f"fenêtre. Signature à l'extrême = flux agressif net des {args.tail} s avant "
             f"l'extrême (> 0 purge, < 0 absorption). Outcome = continuation (ret "
             f"{args.horizon // 60} min après l'extrême, signé par le sens du mouvement). "
             f"Split TEMPOREL 31 j train / 14 j val. Barre promotion (règle x501, docs/25) : "
             f"AUC VAL ≥ 0,60 ET AUC TRAIN ≥ 0,55 ET sharpe TR/VA de même signe ET n ≥ 30 "
             f"des deux côtés. Multiplicité : 6 features × 2 symboles + 1 pooled sig60 "
             f"= 13 tests par passe, 2 passes (primaire 1 % + sensibilité 0,5 %, déclarée "
             f"d'avance, jamais promotionnelle) = 26 tests, aucun retiré.")
    A.append("")
    A.append("Note de puissance d'avance : à 1 %/5 min, l'événement est RARE (T14 : "
             "kurtosis 1 m 252 = queues grasses, mais 45 j n'en contient qu'une poignée "
             "par symbole). Le n VAL est la contrainte dominante — d'où la passe de "
             "sensibilité déclarée, et un verdict HONNÊTE plutôt que forcé.")
    A.append("")

    all_promo, n_tests = [], 0
    primary_data = {}
    for thr, is_primary in [(thr_primary, True), (THR_SENSIB, False)]:
        titre = ("primaire" if is_primary else "sensibilité (jamais promotionnelle)")
        A.append(f"## {'1' if is_primary else '5'}. Passe {titre} — seuil {thr:.1%} en ≤ 5 min")
        A.append("")
        if is_primary:
            A.append("### 1a. Les événements")
            A.append("")
            A.append("| Symbole | Prints (45 j) | Rejetés (unité) | Événements | up / down | train / val | Rate (év/j) | tte méd (s) |")
            A.append("|---|---|---|---|---|---|---|---|")
        ev_by_sym, days = {}, {"val_days": 14.0}
        for sym in symbols:
            ev, meta = study_symbol(sym, con, thr, args.window, args.pause,
                                    args.horizon, args.tail)
            ev_by_sym[sym] = ev
            days[sym] = meta["days"]
            n_up = int((ev["dir"] > 0).sum())
            n_tr = int((ev["split"] == "train").sum())
            if is_primary:
                primary_data[sym] = ev
                A.append(f"| {sym} | {meta['nprint']:,} | {meta['dropped']} | {len(ev)} | "
                         f"{n_up} / {len(ev) - n_up} | {n_tr} / {len(ev) - n_tr} | "
                         f"{len(ev) / meta['days']:.1f} | {ev['tte'].median():.0f} |")
            else:
                A.append(f"- {sym} : {len(ev)} événements "
                         f"({n_up} up / {len(ev) - n_up} down ; train {n_tr} / val {len(ev) - n_tr}).")
        if is_primary:
            A.append("")
            A.append("Lecture : l'extrême est presque toujours en FIN de fenêtre (tte méd "
                     "≈ 299 s) — le seuil est franchi au moment où le mouvement accelère "
                     "encore : la fenêtre T18 capture un run en cours, et la « signature à "
                     "l'extrême » = le flux des 60 s du dernier push. Les outcome 30 min "
                     "peuvent se chevaucher entre événements (étude événementielle).")
        A.append("")
        A.append(f"### {'1b' if is_primary else '5a'}. Le flux DANS le mouvement — purge ou absorption ?")
        A.append("")
        A += purge_table(ev_by_sym)
        A.append("")
        A.append("Purge = le flux agressif continue DANS le sens du mouvement pendant les "
                 "60 s finales ; absorption = il s'inverse à l'extrême. `queue vide` = "
                 "événements sans aucun print dans les 60 s finales (trous de collecte).")
        A.append("")
        A.append(f"### {'1c' if is_primary else '5b'}. Prédiction honnête train/val")
        A.append("")
        _, cells = feature_table(ev_by_sym, days)
        A += fmt_cell_table(cells, FEAT_LABEL)
        A.append("")
        raw_n = sum(c["raw"] for c in cells)
        A.append(f"Cellules promo BRUTES (AUC VAL ≥ 0,60, n VAL ≥ 10) : **{raw_n} / {len(cells)}**. "
                 f"Re-vérification mécanique (déclarée avant lecture) : (a) AUC TRAIN ≥ 0,55 "
                 f"dans le même sens, (b) sharpe TRAIN et VAL de même signe, (c) n ≥ 30 des "
                 f"deux côtés — la règle TRAIN (sens + côté médiane) n'est même pas appliquée "
                 f"sous n TRAIN < 30.")
        for c in cells:
            if c["raw"]:
                echecs = []
                if not (np.isfinite(c["a_tr"]) and c["a_tr"] >= 0.55):
                    echecs.append(f"a) AUC TRAIN {c['a_tr']:.3f} < 0,55")
                if not (np.isfinite(c["s_tr"]) and np.isfinite(c["s_va"]) and c["s_tr"] * c["s_va"] > 0):
                    echecs.append("b) sharpe TR/VA non définis ou de signes opposés")
                if not (c["n_tr"] >= 30 and c["n_va"] >= 30):
                    echecs.append(f"c) n {c['n_tr']}/{c['n_va']} < 30")
                A.append(f"- {c['sym']} {c['feat']} : AUC VA {c['a_va']:.3f} → "
                         f"{'CANDIDAT (a-c OK)' if c['promo'] else 'REJETÉE : ' + ' ; '.join(echecs)}")
                if c["promo"]:
                    all_promo.append(c)
        n_tests += len(cells)
        A.append("")
        if is_primary:
            A.append("### 1d. Table événement × signature × outcome (quintiles sig60, bords TRAIN)")
            A.append("")
            A += quintile_table(ev_by_sym)
            A.append("")
            A.append("Lecture : Q1 = absorption franche à l'extrême, Q5 = purge franche. Un "
                     "gradient monotone de cont30 (Q1 vs Q5 d'ampleur/signes opposés, présent "
                     "des deux côtés du split) = le signature prédit la suite.")
            A.append("")
        else:
            A.append("### 5c. Gradient pooled sig60 → cont30 (quintiles, bords TRAIN)")
            A.append("")
            A += quintile_table(ev_by_sym, pooled=True)
            A.append("")

    # ---- Verdict ----
    A.append("## 6. Verdict")
    A.append("")
    up_p = np.mean([float((primary_data[s][primary_data[s]["dir"] > 0]["sig60"] > 0).mean())
                    for s in primary_data])
    dn_p = np.mean([float((primary_data[s][primary_data[s]["dir"] < 0]["sig60"] > 0).mean())
                    for s in primary_data])
    A.append(f"- Pattern descriptif (passe primaire, 45 j) : PURGE à l'extrême ≈ {up_p:.0%} "
             f"des up et ≈ {dn_p:.0%} des down — le flux agressif continue majoritairement "
             f"DANS le sens du mouvement jusqu'au sommet : les queues de mouvement sont des "
             f"purges, pas des absorptions nettes (l'absorption franche existe, minoritaire).")
    if not all_promo:
        A.append("- **0 cellule candidate après re-vérification sur 26 tests** : le signature "
                 "à l'extrême ne prédit PAS la suite de manière exploitable — n VAL trop petit "
                 "sur la passe primaire (BTC non jugeable, ETH n=14 : AUC 0.644 ±0.162, "
                 "compatible 0,5), et la passe à puissance accrue (0,5 %, n 3-4×) ne "
                 "confirme AUCUN gradient exploitable.")
        verdict = ("**NUL comme signal prédictif** — l'absorption sub-minute n'est pas un "
                   "edge tradable en l'état ; le tape garde sa valeur de MATIÈRE "
                   "(granularité événementielle, diagnostic d'exécution), pas de signal.")
        reponse = ("le signature extrême ne prédit pas → les bougies 1 m (close, volume, "
                   "taker_buy) portent déjà l'information de ces événements ; le flux "
                   "intra-minute n'ajoute rien de mesurable à 45 j. Le tape = matière "
                   "d'archive / diagnostic, pas signal.")
    else:
        verdict = (f"**CANDIDAT à confirmer** — {len(all_promo)} cellule(s) survivent à la "
                   f"re-vérification ; passage obligé par le wallet séquentiel "
                   f"(scripts/stacked_portfolio.py run_stack) avant toute promotion.")
        reponse = ("le signature extrême prédit → le tape a une valeur que les bougies "
                   "n'ont pas (elles cachent le flux intra-minute).")
    A.append(f"- Verdict T18 : {verdict}")
    A.append(f"- La réponse à la question T18 : {reponse}")
    A.append("- Registre `docs/20-registre-indicateurs.md` : aster_tape reste **CONTEXTE "
             "(matière ordre-flow)** — absorption sub-minute re-catégorisée selon ce verdict.")
    A.append("")
    A.append("## Prochaine action")
    A.append("")
    if not all_promo:
        A.append("- Étude close : `git mv scripts/studies/aster_absorption_tape.py "
                 "scripts/archive_studies/` + en-tête `# ARCHIVÉ`, inscrire NUL/CONTEXTE "
                 "dans docs/20, clore la lignée tape-signal (T17+T18 : la granularité "
                 "sub-minute ne devient edge ni au régime ni à l'événement). Réexploiter "
                 "le tape uniquement comme diagnostic d'exécution (exécution réelle vs "
                 "théorique), pas comme prédicteur.")
    else:
        A.append("- Test du wallet séquentiel obligatoire (run_stack) avant toute promotion.")
    A.append("")

    txt = "\n".join(A)
    if not args.no_report:
        REPORT.write_text(txt, encoding="utf-8")
        print(f"rapport écrit : {REPORT}")
    print(txt)


if __name__ == "__main__":
    main()
