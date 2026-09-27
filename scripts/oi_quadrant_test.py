#!/usr/bin/env python3
"""oi_quadrant_test.py — H4/H5 PRE-ENREGISTRES (2026-09-27, AVANT tout calcul).

HYPOTHESES FIGEES (aucun chiffre regarde avant ecriture de ce docstring) :
  H4 : dOI% >= +0.5 % sur la fenetre 90 min (6 bougies de 15 min) + prix qui
       chute (<= -0.5 %)  =  des shorts NOUVEAUX pilent sur la chute
       => le short cascade SUIVANT sur le MEME symbole est de MEILLEURE
       qualite : WR et esperance HAUTS, MAE BAS.
  H5 : dOI% <= -0.5 % + prix qui chute  =  les longs sont flushes, fin de
       vague  =>  le short cascade SUIVANT est DEGRADE : WR/esperance BAS,
       MAE haut.
  Evenements = shorts cascade LIVE (paper_trades, signal LIKE '%cascade%',
  direction = -1). Etat OI ex-ante = snapshots oi_history du symbole dans la
  fenetre [entree - 90 min ; entree] (>= 3 snapshots requis).
  Quadrants testes : Q1 (H4) dOI>=+0.5 & dPx<=-0.5 ; Q2 (H5) dOI<=-0.5 &
  dPx<=-0.5. Les autres etats = neutres, exclus. Seuils +/-0.5 % figes a
  priori (pas de fitting).

VERDICT PASS (a maturite seulement) : split TRAIN/VAL PAR LE TEMPS 70/30 ;
en VAL, les 2 quadrants tiennent leur signe : esperance(Q1) > esperance(Q2),
WR(Q1) > WR(Q2), MAE(Q1) < MAE(Q2), avec n >= 10 par quadrant en VAL et
memes signes en TRAIN (garde-fou compose-des-mois vs final).

GARDE-FOU MATURITE (pattern depth 14 j) : calculs bloques tant que
  - couverture OI < 5 jours, OU
  - cadence mediane < 80 snapshots/symbole/jour, OU
  - n_events (shorts cascade) < 30.
Sinon verdict « COUVERTURE INSUFFISANTE — retente le 07-08/10 ».

UNITES (piege ts du projet — verifiees explicitement au run) :
  oi_history.captured_at_ms  = MILLISECONDES (auto-check >= 13 digits)
  paper_trades.entry_ts      = MILLISECONDES
  liq_events.event_time      = historiquement NANOSECONDES (auto-detect)
  open_interest              = unites de BASE (contrats) ; notional = oi*px
  (check magnitude : mediane oi*px dans [1e4 ; 1e12] USD sinon flag)

Usage :
  .venv/bin/python scripts/oi_quadrant_test.py            # mode maturite
  .venv/bin/python scripts/oi_quadrant_test.py --run      # une passe complete
Lecture SEULE des DB (mode=ro). Exit 0 dans tous les cas.
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse" / "klines.db"

WINDOW_MIN = 90          # 6 bougies de 15 min
MIN_SNAPS = 3            # snapshots min dans la fenetre ex-ante
D_OI_THR = 0.5           # % , fige a priori
D_PX_THR = -0.5          # % , fige a priori
MIN_OI_DAYS = 5          # garde-fou maturite
MIN_SNAPS_PER_DAY = 80   # ~96 attendus a 15 min
MIN_EVENTS = 30
MIN_QUAD = 10            # n min par quadrant pour juger (TRAIN/VAL)

MAE_INTERVALS = ("1m", "5m", "15m", "1h")


def ts_unit(v: int) -> tuple[str, float]:
    """Detecte l'unite d'un timestamp (piege ns/ms/s du projet)."""
    v = int(v)
    d = len(str(abs(v)))
    if d >= 18:
        return "ns", v / 1e6
    if d >= 13:
        return "ms", float(v)
    if d >= 10:
        return "s", float(v) * 1000.0
    return "?", float(v)


def ms2iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def connect_ro() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=15)
    con.execute("PRAGMA busy_timeout = 10000")
    return con


def unit_checks(con: sqlite3.Connection) -> list[str]:
    """Checks d'unites explicites — a afficher sur CHAQUE run."""
    out: list[str] = []
    row = con.execute(
        "SELECT MIN(captured_at_ms), MAX(captured_at_ms), COUNT(*) FROM oi_history"
    ).fetchone()
    if not row or not row[0]:
        return ["[unites] oi_history VIDE (collecteur demarre aujourd'hui ?)"]
    lo, hi, n = row
    u_lo, ms_lo = ts_unit(lo)
    u_hi, ms_hi = ts_unit(hi)
    span_d = (ms_hi - ms_lo) / 86_400_000
    out.append(f"[unites] oi_history.captured_at_ms detecte={u_lo}/{u_hi} "
               f"(attendu ms) | n={n} | span={span_d:.2f} j "
               f"[{ms2iso(ms_lo)} -> {ms2iso(ms_hi)}]")
    if u_lo != "ms" or u_hi != "ms":
        out.append("[unites] !! ANOMALIE : oi_history n'est PAS en ms")

    # unites de l'open_interest : base (contrats) => notional oi*px plausible
    vals = [r[0] for r in con.execute(
        "SELECT open_interest * price FROM oi_history "
        "WHERE price IS NOT NULL AND price > 0 ORDER BY RANDOM() LIMIT 200")]
    if vals:
        med = statistics.median(vals)
        ok = 1e4 <= med <= 1e12
        out.append(f"[unites] open_interest: mediane oi*px={med:.3g} USD "
                   f"=> {'BASE (contrats) OK' if ok else '?? unite inattendue'}")
    else:
        out.append("[unites] open_interest: price manquante, notional non verifiable")

    # paper_trades / liq_events
    pt = con.execute("SELECT MAX(entry_ts) FROM paper_trades").fetchone()
    if pt and pt[0]:
        u, _ = ts_unit(pt[0])
        out.append(f"[unites] paper_trades.entry_ts detecte={u} (attendu ms)"
                   + ("" if u == "ms" else " !! ANOMALIE"))
    liq = con.execute("SELECT MAX(event_time) FROM liq_events").fetchone()
    if liq and liq[0]:
        u, _ = ts_unit(liq[0])
        out.append(f"[unites] liq_events.event_time detecte={u} "
                   f"(historique ns — auto-converti si besoin)")
    return out


def oi_coverage(con: sqlite3.Connection) -> dict:
    rows = con.execute(
        "SELECT symbol, COUNT(*), MIN(captured_at_ms), MAX(captured_at_ms) "
        "FROM oi_history GROUP BY symbol").fetchall()
    spans, dens = [], []
    for _sym, n, lo, hi in rows:
        d = (hi - lo) / 86_400_000
        spans.append(d)
        dens.append(n / d if d > 0.02 else float(n))
    return {
        "n_symbols": len(rows),
        "n_rows": sum(r[1] for r in rows),
        "span_max_d": max(spans) if spans else 0.0,
        "span_med_d": statistics.median(spans) if spans else 0.0,
        "dens_med": statistics.median(dens) if dens else 0.0,
    }


def load_cascade_shorts(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute(
        "SELECT signal, symbol, horizon_h, entry_ts, entry_price, ret_pct, status "
        "FROM paper_trades WHERE signal LIKE '%cascade%' AND direction = -1 "
        "AND entry_ts IS NOT NULL AND entry_price > 0 ORDER BY entry_ts").fetchall()
    return [dict(zip(("signal", "symbol", "horizon_h", "entry_ts",
                      "entry_price", "ret_pct", "status"), r)) for r in rows]


def oi_state(con: sqlite3.Connection, symbol: str, entry_ts: int) -> dict | None:
    """Etat OI ex-ante : fenetre [entry-90min, entry]."""
    rows = con.execute(
        "SELECT open_interest, price, captured_at_ms FROM oi_history "
        "WHERE symbol = ? AND captured_at_ms <= ? AND captured_at_ms >= ? "
        "ORDER BY captured_at_ms",
        (symbol, entry_ts, entry_ts - WINDOW_MIN * 60_000)).fetchall()
    if len(rows) < MIN_SNAPS:
        return None
    oi0, px0, _ = rows[0]
    oi1, px1, _ = rows[-1]
    if not oi0 or not px0 or not px1:
        return None
    return {"d_oi": (oi1 - oi0) / oi0 * 100.0,
            "d_px": (px1 - px0) / px0 * 100.0,
            "n_snaps": len(rows)}


def load_bars(con: sqlite3.Connection, symbol: str) -> tuple[str, list] | None:
    for itv in MAE_INTERVALS:
        bars = con.execute(
            "SELECT open_time, high FROM klines WHERE symbol = ? AND interval = ? "
            "ORDER BY open_time", (symbol, itv)).fetchall()
        if bars:
            return itv, bars
    return None


def mae_short(bars: list, entry_ts: int, horizon_h: int, entry_price: float) -> float | None:
    """MAE d'un short = pire mouvement adverse = (max(high) - entree)/entree."""
    if not bars:
        return None
    end = entry_ts + horizon_h * 3_600_000
    highs = [h for t, h in bars if entry_ts <= t <= end]
    if not highs:
        return None
    return (max(highs) - entry_price) / entry_price * 100.0


def quadrant(d_oi: float, d_px: float) -> str | None:
    if d_oi >= D_OI_THR and d_px <= D_PX_THR:
        return "Q1_H4"
    if d_oi <= -D_OI_THR and d_px <= D_PX_THR:
        return "Q2_H5"
    return None


def stats_block(evs: list[dict]) -> str:
    if not evs:
        return "  n=0"
    rets = [e["ret_pct"] for e in evs if e["ret_pct"] is not None]
    maes = [e["mae"] for e in evs if e["mae"] is not None]
    wr = sum(1 for r in rets if r > 0) / len(rets) * 100 if rets else float("nan")
    lines = [f"  n={len(evs)} (clos={len(rets)}) WR={wr:.1f} % "
             f"esperance={statistics.mean(rets):+.2f} %" if rets else
             f"  n={len(evs)} (clos=0) WR=n/a esperance=n/a"]
    if maes:
        lines.append(f"  MAE: med={statistics.median(maes):.2f} % "
                     f"max={max(maes):.2f} % (base levier <= {100/(max(maes)+0.5):.0f}x)")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="H4/H5 : etat OI ex-ante x short cascade")
    ap.add_argument("--run", action="store_true",
                    help="passe complete (sinon mode maturite seul)")
    args = ap.parse_args()

    con = connect_ro()
    print("=" * 68)
    print("OI QUADRANT TEST — H4/H5 (pre-enregistre 2026-09-27)")
    print("=" * 68)
    for line in unit_checks(con):
        print(line)

    cov = oi_coverage(con)
    mature = (cov["span_max_d"] >= MIN_OI_DAYS
              and cov["dens_med"] >= MIN_SNAPS_PER_DAY)
    print(f"[maturite OI] {cov['n_symbols']} symboles, {cov['n_rows']} snapshots, "
          f"span max {cov['span_max_d']:.2f} j, densite mediane "
          f"{cov['dens_med']:.0f}/j (seuils: >= {MIN_OI_DAYS} j, >= {MIN_SNAPS_PER_DAY}/j) "
          f"-> {'OK' if mature else 'INSUFFISANT'}")

    evs = load_cascade_shorts(con)
    oi_syms = {r[0] for r in con.execute("SELECT DISTINCT symbol FROM oi_history")}
    ev_syms = {e["symbol"] for e in evs}
    joined = sorted(ev_syms & oi_syms)
    print(f"[join] shorts cascade: n={len(evs)} sur {len(ev_syms)} symboles ; "
          f"oi_history: {len(oi_syms)} symboles ; overlap={len(joined)} {joined[:10]}")

    # etat OI ex-ante par event (validation du JOIN lui-meme)
    tagged = 0
    for e in evs:
        st = oi_state(con, e["symbol"], e["entry_ts"])
        if st:
            e.update(st)
            e["quad"] = quadrant(st["d_oi"], st["d_px"])
            tagged += 1
        else:
            e["quad"] = None
    print(f"[join] events avec etat OI ex-ante (>= {MIN_SNAPS} snaps/90min): "
          f"{tagged}/{len(evs)} ; quadrants Q1={sum(1 for e in evs if e.get('quad')=='Q1_H4')} "
          f"Q2={sum(1 for e in evs if e.get('quad')=='Q2_H5')}")

    if evs:
        print(f"[join] derniere entree cascade: {ms2iso(evs[-1]['entry_ts'])} UTC "
              f"({evs[-1]['symbol']})")

    n_q = sum(1 for e in evs if e.get("quad"))
    if not mature or len(evs) < MIN_EVENTS or n_q < MIN_QUAD:
        print("-" * 68)
        print("VERDICT: COUVERTURE INSUFFISANTE — retente le 07-08/10.")
        print(f"  (maturite OI={'OK' if mature else 'NON'}, events={len(evs)}/{MIN_EVENTS}, "
              f"tagges={tagged}, en-quadrant={n_q}/{MIN_QUAD})")
        print("  Le JOIN et les unites sont valides ; aucun verdict statistique.")
        con.close()
        return 0

    if not args.run:
        print("[maturite] OK mais --run absent : passe complete non lancee.")
        con.close()
        return 0

    # --- passe complete : MAE + quadrants + TRAIN/VAL par le temps ---
    bars_cache: dict[str, tuple[str, list] | None] = {}
    for e in evs:
        if e["symbol"] not in bars_cache:
            bars_cache[e["symbol"]] = load_bars(con, e["symbol"])
        b = bars_cache[e["symbol"]]
        e["mae"] = mae_short(b[1], e["entry_ts"], e["horizon_h"], e["entry_price"]) if b else None

    evs_t = [e for e in evs if e.get("quad")]
    if not evs_t:
        print("BLOC STATS: aucun event en quadrant (fenetres OI ex-ante vides) "
              "— insuffisant.")
        con.close()
        return 0
    evs_t.sort(key=lambda e: e["entry_ts"])
    cut = int(len(evs_t) * 0.7)
    splits = {"TRAIN": evs_t[:cut], "VAL": evs_t[cut:]}

    print("=" * 68)
    print("BLOC STATS (shorts cascade x quadrant OI ex-ante)")
    verdict_val = None
    for name, part in splits.items():
        if not part:
            print(f"-- {name}: n=0 — non evalue")
            continue
        print(f"-- {name} (n={len(part)}, {ms2iso(part[0]['entry_ts'])} -> "
              f"{ms2iso(part[-1]['entry_ts'])} UTC)")
        for q in ("Q1_H4", "Q2_H5"):
            sub = [e for e in part if e["quad"] == q]
            print(f"  {q}:")
            print(stats_block(sub))

    def metrics(part, q):
        sub = [e for e in part if e["quad"] == q]
        rets = [e["ret_pct"] for e in sub if e["ret_pct"] is not None]
        maes = [e["mae"] for e in sub if e["mae"] is not None]
        return {"n": len(sub), "wr": (sum(1 for r in rets if r > 0) / len(rets)
                                      if rets else None),
                "exp": statistics.mean(rets) if rets else None,
                "mae_med": statistics.median(maes) if maes else None}

    val = {q: metrics(splits["VAL"], q) for q in ("Q1_H4", "Q2_H5")}
    trn = {q: metrics(splits["TRAIN"], q) for q in ("Q1_H4", "Q2_H5")}
    ok_n = (val["Q1_H4"]["n"] >= MIN_QUAD and val["Q2_H5"]["n"] >= MIN_QUAD)
    ok_exp = (val["Q1_H4"]["exp"] is not None and val["Q2_H5"]["exp"] is not None
              and val["Q1_H4"]["exp"] > val["Q2_H5"]["exp"])
    ok_wr = (val["Q1_H4"]["wr"] is not None and val["Q2_H5"]["wr"] is not None
             and val["Q1_H4"]["wr"] > val["Q2_H5"]["wr"])
    ok_mae = (val["Q1_H4"]["mae_med"] is not None and val["Q2_H5"]["mae_med"] is not None
              and val["Q1_H4"]["mae_med"] < val["Q2_H5"]["mae_med"])
    trn_ok = (trn["Q1_H4"]["exp"] is not None and trn["Q2_H5"]["exp"] is not None
              and trn["Q1_H4"]["exp"] > trn["Q2_H5"]["exp"])
    if not (ok_n and ok_exp and ok_wr and ok_mae):
        verdict_val = "FAIL / INSUFFISANT en VAL (n ou signes non tenus)"
    elif not trn_ok:
        verdict_val = "FAIL: signes VAL ok mais TRAIN contredit (garde-fou compose)"
    else:
        verdict_val = "PASS: H4 et H5 tiennent leur signe en VAL (et TRAIN coherent)"

    print("-" * 68)
    print(f"VERDICT: {verdict_val}")
    print(f"  VAL  Q1(H4): {val['Q1_H4']}")
    print(f"  VAL  Q2(H5): {val['Q2_H5']}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
