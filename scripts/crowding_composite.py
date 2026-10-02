#!/usr/bin/env python3
"""crowding_composite.py — LE COMPOSITE CROWDING (Rail A, domaine ASTER).

═══════════════════════════════════════════════════════════════════════
PRE-ENREGISTREMENT 2026-10-02 — AVANT tout calcul de score, AVANT tout test.
Hypothèse falsifiable : docs/lab/hypotheses/crowding-composite.md
SEAL sha256 (du fichier d'hypothese, verifie a CHAQUE run) :
  8df0b11b994b3bd68aea58164abed4b908142fcb1aca70d4fb4cefab8ab17d8c
Gouvernance : docs/38-gouvernance-recherche.md (freeze-2026-10-02, §61).
Ceci est un CONDITIONNEUR D'ETAT pour les flux existants — JAMAIS un signal
autonome (SENS=0). Le TEST est VERROUILLE jusqu'au 2026-10-30 (OI bulk 30 j).
═══════════════════════════════════════════════════════════════════════

HYPOTHESE FIGEE (H-CROWD-1, ecrite avant tout chiffre) :
  Les entrees des flux machine 1h (cascade gated AL p66, vol_spike_6h) prises
  en etat LATE ou EXHAUSTED ont une esperance nette 24-72h INFERIEURE a l'etat
  FRESH, aux deux splits chrono, et chaque etat est separement SOUS le
  base-rate inconditionnel du flux (regle PAR ETAT, lecon INV-H).

SEUILS FIGES (avant tout test, nombres ronds non ajustes, zero grille) :
  Score continu C ∈ [-1, +1] par symbole/heure (close 1h ; + = foule LONGUE
  crowdée). Composantes OPTIONNELLES, score = moyenne des PRESENTES ;
  < 2 presentes → UNKNOWN (jamais score) :
    c_funding : z du dernier funding rate vs 30 j glissants (>= 30 obs)
                → clip(z/3, -1, 1)
    c_oi      : dOI% sur 4 h (2 snapshots MEME source, 3-5 h d'ecart ;
                priorite oi_history, sinon oi_history_bulk)
                → clip(d_oi_pct/1.5, -1, 1)
    c_premium : z du dernier premium_pct vs 7 j glissants (>= 500 obs)
                → clip(z/3, -1, 1)
    c_volume  : vol24h / mediane des 30 sommes quotidiennes des 31 j
                precedents (>= 20 j), SIGNE par sign(ret24h)
                → clip(log2(vol_rel)/2, -1, 1) * sign(ret24h)
    c_liq     : pression nette 24 h (notional LONGS liquides − SHORTS
                liquides)/(total+eps), convention Binance fapi forceOrder
                (S : SELL ⇒ LONG liquide, BUY ⇒ SHORT liquide — collecteur
                ws_forceOrder) → clip(-pression, -1, 1)
  ETATS (figes, symetriques en |C|) :
    FRESH      |C| < 0.50
    CROWDED    0.50 <= |C| < 0.80
    LATE       |C| >= 0.80
    EXHAUSTED  flush avere : densite liq 24 h >= 0.5 % de l'OI notionnel
               courant ET dOI 4 h <= -1.0 % (override prioritaire)
    UNKNOWN    < 2 composantes presentes
  Prior declare : NEGATIF (al_score_v2_composite REJECTED — les composites
  ont deja inverse dans ce projet). FAIL attendu honnetement.

TEST VERROUILLE : fenetre 2026-10-30 → 2027-01-30, split chrono 70/30 interne,
n >= 60/etat TRAIN et >= 30/etat VAL, C1-C4 + controle inverse + garde-fou
compose-des-mois (docs/lab/hypotheses/crowding-composite.md). Aucune stat de
performance avant le 30/10 ; ce script n'implemente AUCUN join vers des
resultats de trades — il ne produit que score/etat (descriptif).

UNITES (pieges du projet — verifiees EXPLICITEMENT a chaque run) :
  klines.open_time / funding_time / *_captured_at_ms = MILLISECONDES (>= 13 digits)
  liq_events.event_time = auto-detecte (historiquement ns) — conversion au run
  oi_history.open_interest     = unites de BASE (notional = oi * prix)
  oi_history_bulk.open_interest = NOTIONAL x2 (conversion ÷2 vs base)
  premium_pct en % ; funding rate en unite brute ; cadence funding MIXTE
  (1 h plupart / 4 h ASTERUSDT) → z-funding toujours TIME-BASED (30 j).

Usage :
  .venv/bin/python scripts/crowding_composite.py            # SMOKE (defaut) :
      unites + couverture par composante et par symbole, AUCUNE stat resultat
  .venv/bin/python scripts/crowding_composite.py --full     # timeline score/etat
      (refuse avant le 2026-10-30 ; --force-early = observation forward seule,
      le TEST reste verrouille par la doctrine)
Lecture SEULE des DB (mode=ro). Exit 0 en smoke, 2 si seal rompu.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import math
import sqlite3
import statistics
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse" / "klines.db"
HYP = ROOT / "docs" / "lab" / "hypotheses" / "crowding-composite.md"
OUT_DIR = ROOT / "reports" / "aster"

EXPECTED_SEAL = "8df0b11b994b3bd68aea58164abed4b908142fcb1aca70d4fb4cefab8ab17d8c"
TEST_LOCK = date(2026, 10, 30)          # date de test verrouillee (OI bulk 30 j)

# ── parametres FIGES (voir docstring — ne JAMAIS toucher sans nouveau
#    pre-enregistrement : PARAMETER_MUTATION) ─────────────────────────────
Z_SIGMA = 3.0                           # clip(z/3)
FUNDING_LOOKBACK_D = 30
FUNDING_MIN_OBS = 30
PREMIUM_LOOKBACK_D = 7
PREMIUM_MIN_OBS = 500
D_OI_WINDOW_H = 4                       # vitesse d'OI
D_OI_SCALE_PCT = 1.5                    # ±1.5 %/4h = ±1
D_OI_GAP_MIN_H, D_OI_GAP_MAX_H = 3.0, 5.0
OI_MAX_STALE_H = 6.0
VOL_REF_DAYS = 30
VOL_MIN_DAYS = 20
VOL_SCALE_LOG2 = 2.0                    # vol 4x mediane = +1
LIQ_WINDOW_H = 24
LIQ_OI_THR = 0.005                      # 0.5 % de l'OI notionnel / 24 h
FLUSH_D_OI_PCT = -1.0                   # et dOI <= -1 %/4h
T_CROWD, T_LATE = 0.50, 0.80
MIN_COMPONENTS = 2
COMPONENTS = ("funding", "oi", "premium", "volume", "liq")


# ─────────────────────────── utilitaires ───────────────────────────
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


def check_seal() -> None:
    """Verifie que l'hypothese pre-enregistree n'a pas bouge depuis le sceau."""
    if not HYP.exists():
        print(f"[seal] !! ABSENT : {HYP} — pre-enregistrement introuvable")
        sys.exit(2)
    digest = hashlib.sha256(HYP.read_bytes()).hexdigest()
    if digest != EXPECTED_SEAL:
        print(f"[seal] !! ROMPU : sha256(hypothese)={digest} != sceau grave "
              f"{EXPECTED_SEAL} — hypothese modifiee APRES pre-enregistrement")
        sys.exit(2)
    print(f"[seal] OK {digest[:16]}… (docs/lab/hypotheses/crowding-composite.md)")


def check_units(con: sqlite3.Connection) -> None:
    """Checks d'unites explicites — affiches sur CHAQUE run."""
    r = con.execute("SELECT MIN(funding_time), MAX(funding_time), COUNT(*), "
                    "COUNT(DISTINCT symbol) FROM funding_history").fetchone()
    u, ms = ts_unit(r[0])
    print(f"[unites] funding_time detecte={u} | n={r[2]} sym={r[3]} "
          f"[{ms2iso(ms)} -> {ms2iso(ts_unit(r[1])[1])}]")

    r = con.execute("SELECT MIN(event_time), MAX(event_time), COUNT(*), "
                    "COUNT(DISTINCT symbol) FROM liq_events").fetchone()
    u, ms = ts_unit(r[0])
    print(f"[unites] liq_events.event_time detecte={u} | n={r[2]} sym={r[3]} "
          f"[{ms2iso(ms)} -> {ms2iso(ts_unit(r[1])[1])}]")

    for tbl, conv in (("oi_history", "BASE (notional=oi*prix)"),
                      ("oi_history_bulk", "NOTIONAL x2")):
        vals = [x[0] for x in con.execute(
            f"SELECT open_interest*price FROM {tbl} "
            "WHERE price IS NOT NULL AND price > 0 AND open_interest > 0 "
            "ORDER BY RANDOM() LIMIT 200")]
        if vals:
            med = statistics.median(vals)
            ok = 1e2 <= med <= 1e12
            print(f"[unites] {tbl}: mediane oi*prix={med:.4g} => attendu {conv} "
                  f"({'plausible' if ok else '?? magnitude inattendue'})")
        r = con.execute(f"SELECT COUNT(*), COUNT(DISTINCT symbol), "
                        f"MIN(captured_at_ms), MAX(captured_at_ms) FROM {tbl}").fetchone()
        print(f"[unites] {tbl}: n={r[0]} sym={r[1]} [{ms2iso(r[2])} -> {ms2iso(r[3])}]"
              f" = {(r[3]-r[2])/86_400_000:.2f} j")

    p = [x[0] for x in con.execute("SELECT premium_pct FROM premium_history "
                                   "WHERE premium_pct IS NOT NULL LIMIT 5000")]
    if p:
        sp = sorted(p)
        print(f"[unites] premium_pct: mediane={statistics.median(p):.5f} "
              f"p1={sp[len(sp)//100]:.4f} p99={sp[-1-len(sp)//100]:.4f} (en %)")
    r = con.execute("SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(captured_at_ms), "
                    "MAX(captured_at_ms) FROM premium_history").fetchone()
    print(f"[unites] premium_history: n={r[0]} sym={r[1]} [{ms2iso(r[2])} -> {ms2iso(r[3])}]"
          f" = {(r[3]-r[2])/86_400_000:.2f} j")

    # diagnostic de conversion bulk vs base (meme symbole, snapshots < 5 min) :
    # attendu bulk/(base*prix) = 2.00 (bulk = notional USD x2, base = contrats)
    rows = con.execute("""
        SELECT b.symbol, AVG(b.open_interest / NULLIF(o.open_interest * o.price, 0))
        FROM oi_history_bulk b JOIN oi_history o
          ON o.symbol = b.symbol
         AND ABS(o.captured_at_ms - b.captured_at_ms) < 300000
        GROUP BY b.symbol HAVING COUNT(*) >= 5""").fetchall()
    ratios = [x[1] for x in rows if x[1] and 0.01 < x[1] < 1e6]
    if ratios:
        med = statistics.median(ratios)
        ok = 1.5 <= med <= 2.5
        print(f"[unites] bulk/(base*prix): mediane={med:.3f} sur {len(ratios)} "
              f"symboles apparies => attendu ~2.00 "
              f"({'OK — bulk = notional x2 USD, base = contrats' if ok else '?? ANOMALIE'})")
    else:
        print("[unites] bulk/base: aucun snapshot apparie < 5 min (diag n/a)")


# ─────────────────────────── SMOKE : couverture ───────────────────────────
def load_component_coverage(con: sqlite3.Connection) -> dict[str, dict[str, tuple]]:
    cov: dict[str, dict[str, tuple]] = {}
    cov["funding"] = {s: (n, lo, hi) for s, n, lo, hi in con.execute(
        "SELECT symbol, COUNT(*), MIN(funding_time), MAX(funding_time) "
        "FROM funding_history GROUP BY symbol")}
    cov["klines1h"] = {s: (n, lo, hi) for s, n, lo, hi in con.execute(
        "SELECT symbol, COUNT(*), MIN(open_time), MAX(open_time) FROM klines "
        "WHERE interval='1h' GROUP BY symbol")}
    cov["liq"] = {s: (n, lo, hi) for s, n, lo, hi in con.execute(
        "SELECT symbol, COUNT(*), MIN(event_time), MAX(event_time) "
        "FROM liq_events GROUP BY symbol")}
    cov["oi_history"] = {s: (n, lo, hi) for s, n, lo, hi in con.execute(
        "SELECT symbol, COUNT(*), MIN(captured_at_ms), MAX(captured_at_ms) "
        "FROM oi_history GROUP BY symbol")}
    cov["oi_history_bulk"] = {s: (n, lo, hi) for s, n, lo, hi in con.execute(
        "SELECT symbol, COUNT(*), MIN(captured_at_ms), MAX(captured_at_ms) "
        "FROM oi_history_bulk GROUP BY symbol")}
    cov["premium"] = {s: (n, lo, hi) for s, n, lo, hi in con.execute(
        "SELECT symbol, COUNT(*), MIN(captured_at_ms), MAX(captured_at_ms) "
        "FROM premium_history GROUP BY symbol")}
    # normalisation des unites de temps (event_time ns possible)
    for comp in cov:
        fixed = {}
        for s, (n, lo, hi) in cov[comp].items():
            _, lo_ms = ts_unit(lo)
            _, hi_ms = ts_unit(hi)
            fixed[s] = (n, lo_ms, hi_ms)
        cov[comp] = fixed
    return cov


def smoke(con: sqlite3.Connection) -> None:
    cov = load_component_coverage(con)
    universe = sorted(set(cov["klines1h"]) | set(cov["oi_history"])
                      | set(cov["premium"]) | set(cov["liq"]))
    comps = ("klines1h", "funding", "oi_history", "oi_history_bulk", "premium", "liq")
    today = date.today().isoformat()

    print(f"\n[smoke] couverture reelle au {today} — composantes x symboles "
          f"(univers {len(universe)} symboles), AUCUNE stat de resultat\n")
    hdr = f"{'symbole':<16}" + "".join(f"{c[:12]:>14}" for c in comps)
    print(hdr)
    print("-" * len(hdr))
    rows_csv = []
    for s in universe:
        cells = []
        for c in comps:
            if s in cov[c]:
                n, lo, hi = cov[c][s]
                days = (hi - lo) / 86_400_000
                cad = n / days if days > 0 else 0.0
                if days >= 0.5 and n >= 5:
                    cells.append(f"{days:5.1f}j/{cad:4.0f}j")
                else:                     # span minuscule : cadence absurde
                    cells.append(f"n={n}".rjust(12))
                rows_csv.append([c, s, n, ms2iso(lo), ms2iso(hi),
                                 round(days, 2), round(cad, 1)])
            else:
                cells.append(f"{'—':>12}")
        print(f"{s:<16}" + "".join(f"{x:>14}" for x in cells))
    print(f"\n[smoke] resume par composante (tous symboles confondus) :")
    for c in comps:
        d = cov[c]
        if not d:
            print(f"  {c:<16} VIDE")
            continue
        days_all = [(hi - lo) / 86_400_000 for _, lo, hi in d.values()]
        print(f"  {c:<16} sym={len(d):>3}  n_total={sum(n for n, _, _ in d.values()):>7}"
              f"  profondeur mediane={statistics.median(days_all):5.1f} j"
              f"  debut le plus tardif={ms2iso(max(lo for _, lo, _ in d.values()))}")
    # bulk : la longue traine hors univers 1h
    bulk_only = set(cov["oi_history_bulk"]) - set(universe)
    if bulk_only:
        print(f"  oi_history_bulk : +{len(bulk_only)} symboles hors univers 1h "
              f"(small caps) — couverture identique en fenetre")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"crowding_coverage_{today}.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["component", "symbol", "n_obs", "first_ts", "last_ts",
                    "span_days", "obs_per_day"])
        w.writerows(rows_csv)
    print(f"[smoke] couverture complete -> {out}")

    # readyness du test du 30/10 (purement structurel)
    bulk_days = max((hi - lo) / 86_400_000 for _, lo, hi in cov["oi_history_bulk"].values())
    print(f"[smoke] readiness TEST 2026-10-30 : OI bulk {bulk_days:.1f}/30 j "
          f"(atteint ~{(date(2026,10,30)-date.today()).days} j restants) ; "
          f"composantes profondes des maintenant : klines1h, funding, liq")


# ─────────────────────── calcul complet (--full) ───────────────────────
def _z(last: float, obs: list[float]) -> float | None:
    if len(obs) < 2:
        return None
    m = statistics.fmean(obs)
    sd = statistics.pstdev(obs)
    if sd <= 0:
        return None
    return (last - m) / sd


def clip(x: float) -> float:
    return max(-1.0, min(1.0, x))


def compute_symbol(con: sqlite3.Connection, sym: str) -> list[dict]:
    """Timeline horaire score/etat d'un symbole (descriptif, aucune perf)."""
    bars = con.execute(
        "SELECT open_time, close, quote_volume FROM klines WHERE symbol=? AND "
        "interval='1h' ORDER BY open_time", (sym,)).fetchall()
    if len(bars) < 48:
        return []
    fund = con.execute("SELECT funding_time, rate FROM funding_history WHERE "
                       "symbol=? ORDER BY funding_time", (sym,)).fetchall()
    fund_ts = [ts_unit(t)[1] for t, _ in fund]
    prem = con.execute("SELECT captured_at_ms, premium_pct FROM premium_history "
                       "WHERE symbol=? AND premium_pct IS NOT NULL ORDER BY "
                       "captured_at_ms", (sym,)).fetchall()
    prem_ts = [float(t) for t, _ in prem]

    snaps: dict[str, list] = {}
    for tbl, kind in (("oi_history", "base"), ("oi_history_bulk", "bulk")):
        snaps[kind] = con.execute(
            f"SELECT captured_at_ms, open_interest, price FROM {tbl} WHERE "
            f"symbol=? ORDER BY captured_at_ms", (sym,)).fetchall()
    liq = [(ts_unit(t)[1], side, notional or 0.0) for t, side, notional in
           con.execute("SELECT event_time, side, notional FROM liq_events "
                       "WHERE symbol=? ORDER BY event_time", (sym,))]
    liq_ts = [e[0] for e in liq]

    # sommes quotidiennes de volume pour la reference 30 j
    day_vol: dict[str, float] = {}
    for ot, _, qv in bars:
        d = datetime.fromtimestamp(ot / 1000, tz=timezone.utc).date().isoformat()
        day_vol[d] = day_vol.get(d, 0.0) + (qv or 0.0)
    day_keys = sorted(day_vol)

    H = 3600_000
    out = []
    for i in range(24, len(bars)):
        ot, close_i, _ = bars[i]
        t_close = ot + H
        if close_i <= 0:
            continue
        comps: dict[str, float] = {}
        # volume dirige
        vol24 = sum(b[2] or 0.0 for b in bars[i - 23:i + 1])
        d0 = datetime.fromtimestamp(t_close / 1000, tz=timezone.utc).date()
        lo_date = d0 - timedelta(days=31)
        ref_keys = [k for k in day_keys if d0.isoformat() > k >= lo_date.isoformat()]
        if vol24 > 0 and len(ref_keys) >= VOL_MIN_DAYS:
            med = statistics.median(day_vol[k] for k in ref_keys)
            if med > 0:
                ret24 = close_i / bars[i - 24][1] - 1.0
                sign = 1.0 if ret24 > 0 else (-1.0 if ret24 < 0 else 0.0)
                comps["volume"] = clip(math.log2(max(vol24 / med, 1e-9))
                                       / VOL_SCALE_LOG2) * sign
        # funding z
        j = bisect.bisect_right(fund_ts, t_close)
        if j:
            lo = bisect.bisect_left(fund_ts, t_close - FUNDING_LOOKBACK_D * 86_400_000)
            win = [r for _, r in fund[lo:j]]
            if len(win) >= FUNDING_MIN_OBS:
                z = _z(win[-1], win)
                if z is not None:
                    comps["funding"] = clip(z / Z_SIGMA)
        # premium z
        k = bisect.bisect_right(prem_ts, t_close)
        if k:
            lo = bisect.bisect_left(prem_ts, t_close - PREMIUM_LOOKBACK_D * 86_400_000)
            win = [p for _, p in prem[lo:k]]
            if len(win) >= PREMIUM_MIN_OBS:
                z = _z(win[-1], win)
                if z is not None:
                    comps["premium"] = clip(z / Z_SIGMA)
        # dOI% (meme source, 3-5 h d'ecart) + oi notionnel
        d_oi_pct = None
        oi_notional = None
        for kind in ("base", "bulk"):
            ss = snaps[kind]
            if len(ss) < 2:
                continue
            s_ts = [float(r[0]) for r in ss]
            m = bisect.bisect_right(s_ts, t_close)
            if m == 0:
                continue
            last_t = s_ts[m - 1]
            if t_close - last_t > OI_MAX_STALE_H * H:
                continue
            lo = bisect.bisect_left(s_ts, last_t - D_OI_GAP_MAX_H * H)
            prev = None
            for q in range(m - 2, lo - 1, -1):
                gap_h = (last_t - s_ts[q]) / H
                if D_OI_GAP_MIN_H <= gap_h <= D_OI_GAP_MAX_H:
                    prev = ss[q]
                    break
            if prev is None or prev[1] <= 0:
                continue
            d_oi_pct = (ss[m - 1][1] - prev[1]) / prev[1] * 100.0
            if kind == "base" and ss[m - 1][2]:
                oi_notional = ss[m - 1][1] * ss[m - 1][2]
            elif kind == "bulk":
                oi_notional = ss[m - 1][1] / 2.0     # notional x2 -> USD
            break
        if d_oi_pct is not None:
            comps["oi"] = clip(d_oi_pct / D_OI_SCALE_PCT)
        # liquidations 24 h
        a = bisect.bisect_left(liq_ts, t_close - LIQ_WINDOW_H * H)
        b = bisect.bisect_right(liq_ts, t_close)
        if b > a:
            long_liq = sum(e[2] for e in liq[a:b] if e[1] == "SELL")  # SELL⇒long liq
            short_liq = sum(e[2] for e in liq[a:b] if e[1] == "BUY")
            tot = long_liq + short_liq
            if tot > 0:
                press = (long_liq - short_liq) / (tot + 1e-9)
                comps["liq"] = clip(-press)
                flush = (oi_notional and oi_notional > 0
                         and tot / oi_notional >= LIQ_OI_THR
                         and d_oi_pct is not None and d_oi_pct <= FLUSH_D_OI_PCT)
            else:
                flush = False
        else:
            flush = False

        if len(comps) < MIN_COMPONENTS:
            state = "UNKNOWN"
            score = None
        else:
            score = statistics.fmean(comps.values())
            if flush:
                state = "EXHAUSTED"
            elif abs(score) >= T_LATE:
                state = "LATE"
            elif abs(score) >= T_CROWD:
                state = "CROWDED"
            else:
                state = "FRESH"
        out.append({"symbol": sym, "hour": ms2iso(t_close),
                    "score": None if score is None else round(score, 4),
                    "state": state,
                    "n_comp": len(comps),
                    "components": ",".join(sorted(comps))})
    return out


def full(con: sqlite3.Connection, force_early: bool) -> None:
    if date.today() < TEST_LOCK and not force_early:
        print(f"[full] !! TEST VERROUILLE jusqu'au {TEST_LOCK.isoformat()} "
              f"(OI bulk < 30 j) — couverture insuffisante, mode SMOKE seul.")
        print("[full] le test (C1-C4, split chrono, base-rate par etat) ne "
              "commence pas avant. Rien n'est calcule.")
        return
    if force_early and date.today() < TEST_LOCK:
        print("[full] --force-early : observation forward du score/etat SEULE — "
              "le TEST reste verrouille par la doctrine, aucune stat de perf "
              "n'existe dans ce script.")
    universe = sorted(set(r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'")))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"crowding_states_{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M')}.csv"
    dist: dict[str, int] = {}
    n_rows = 0
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "hour", "score", "state", "n_components", "components"])
        for sym in universe:
            for row in compute_symbol(con, sym):
                w.writerow([row["symbol"], row["hour"], row["score"],
                            row["state"], row["n_comp"], row["components"]])
                dist[row["state"]] = dist.get(row["state"], 0) + 1
                n_rows += 1
    print(f"[full] timeline ecrite -> {out} ({n_rows} heures-symboles)")
    print("[full] repartition d'etats (descriptif structurel — PAS une stat de "
          "resultat) :", dict(sorted(dist.items())))


def main() -> None:
    ap = argparse.ArgumentParser(description="Composite Crowding (Rail A, ASTER)")
    ap.add_argument("--full", action="store_true",
                    help="calcule la timeline score/etat (verrouillee avant "
                         f"{TEST_LOCK.isoformat()} sans --force-early)")
    ap.add_argument("--force-early", action="store_true",
                    help="observation forward avant la date de test (le TEST "
                         "reste verrouille)")
    ap.add_argument("--smoke", action="store_true",
                    help="mode couverture seul (defaut)")
    args = ap.parse_args()
    check_seal()
    con = connect_ro()
    try:
        check_units(con)
        if args.full:
            full(con, args.force_early)
        else:
            smoke(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
