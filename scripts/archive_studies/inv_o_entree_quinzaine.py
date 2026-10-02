#!/usr/bin/env python
# ARCHIVÉ (02/10/2026) — INV-O : FAIL répliqué, la loi open=optimum survit à la sous-granularité (docs/38)
"""INV-O « L'ENTRÉE À LA QUINZAINE » — étude d'EXÉCUTION (one-shot, gel freeze-2026-10-02).

════════════════════════════════════════════════════════════════════════
PRÉ-ENREGISTREMENT (écrit AVANT toute mesure — rien ci-dessous n'est
calculé avant d'avoir imprimé ce bloc ; le seal sha256 du rapport couvre
ce texte exact).
════════════════════════════════════════════════════════════════════════
DOMAINE : Aster, gouvernance docs/38 (tag freeze-2026-10-02). Étude
d'EXÉCUTION (amplificateur des stratégies vivantes), PAS un signal
nouveau. Budget : 1 expérience, un seul raffinement testé.

FAMILLES MORTES VÉRIFIÉES (research/registry.yaml + docs/20) :
INV-A..M toutes REJECTED — aucune ne touche la sous-granularité
d'exécution. La loi gravée « open = optimum entrée+sortie » a été
mesurée à la granularité 1h ; INV-O pose la question JAMAIS posée :
à l'INTÉRIEUR de la bougie d'entrée, la sous-granularité 15m native
fait-elle mieux ? Aucune variante de seuil d'aucune famille morte
n'est réintroduite.

HYPOTHÈSE (pré-déclarée) :
  le raffinement 15m améliore l'espérance nette d'au moins +3 bps/entrée
  vs l'open 1h, SANS augmenter le MAE max du flux gated (la règle 0-liq
  doit tenir : le MAE gated ne monte pas).

RÈGLE DE CHOIX (UNE seule, zéro grille — pré-déclarée) :
  k* = premier k ∈ {1,2,3} tel que le close de la k-ième bougie 15m
  native de l'heure d'entrée est DU CÔTÉ de l'open 1h
  (LONG : close15m_k > open1h ; SHORT : close15m_k < open1h ; égalité =
  ni l'un ni l'autre, k sauté ; bougie 15m manquante = k sauté).
  Entrée = close15m_k*. Si aucun k ne qualifie → entrée à l'open 1h
  (fallback, identique bit-à-bit à la référence).
  CONTRÔLE INVERSE : miroir exact — premier k dont le close est CONTRE
  notre côté (LONG : close < open ; SHORT : close > open), sinon open.

POPULATION (mêmes signaux, MÊME moteur, seule l'exécution change —
une variable) :
  - flux 1 machine rejoué bit-à-bit EN LECTURE : cascade majors
    (collect_featured + add_rolling_scores + gate AL q66 sur les
    premiers 70 % d'événements, code exact de the_machine.main, sans
    l'écriture mae_state.json) — SHORT, hold 24h, entrée open t+1,
    exit close t+24 inchangé ;
  - flux 4 machine : vol_spike 6h (collect_vol_spike, hold=6, gate ATR
    p90 inclus) — long/short, entrée open t+1, exit close t+6 inchangé.
  Ensemble ÉVALUABLE : entrées dont l'heure d'entrée contient au moins
  une bougie 15m native pour le symbole (les heures sans 15m natif sont
  exclues et comptées — les deux bras y seraient identiques).

PROTOCOLE IMMUTABLE :
  - split 60/40 chrono GLOBAL (une seule estampe, ensemble évaluable
    poolé, les deux flux confondus) ;
  - coûts 18 bps RT identiques des deux côtés (étalon du domaine ;
    les frais machine propres — MAKER 4 / TAKER 28 — s'annulent dans
    le Δ, l'écart des bras en est invariant) ; espérance nette =
    ret directionnel brut (bps) − 18 bps ; funding exclu (fenêtre
    identique ±45 min, deuxième ordre, déclaré) ;
  - exit bit-exact : même close 1h que la référence (le plan de sortie
    ne change pas) ; seule l'ESTAMPE et le PRIX d'entrée changent ;
  - MAE : chemin depuis le prix d'entrée réel jusqu'au exit — à
    l'intérieur de l'heure d'entrée sur la grille 15m native (bougies
    strictement postérieures à la bougie d'entrée ; entrée à l'open =
    bougies 1..4 présentes), ensuite bougies 1h ei+1..exit ;
    LONG : (entry − min low)/entry ; SHORT : (max high − entry)/entry,
    borné à ≥ 0 ; le close d'entrée 15m est dans [low, high] de son
    heure par construction ;
  - critère MAE jugé sur TRAIN (le levier 0-liq se calibre sur TRAIN,
    doctrine) : max MAE gated variante ≤ max MAE gated référence ;
    VAL rapporté en descriptive ;
  - n ≥ 100 entrées TRAIN sinon « SOUS-PUISSENT » déclaré — aucun PASS
    possible ;
  - BLOC STATS mensuel par bras × split (notionnel 1x additif :
    trades, WR net, somme/moyenne bps nets, pire/record mois, mois
    négatifs) ; chevauchements vol_spike inclus des deux côtés — ce
    n'est PAS un wallet séquentiel (le run_stack ne sert qu'une
    promotion éventuelle, jamais le verdict d'exécution) ;
  - PASS (écrits AVANT) : C1 Δespérance nette (variante − référence)
    ≥ +3 bps en TRAIN ET en VAL ; C2 max MAE gated TRAIN variante
    ≤ référence (inchangé ou réduit) ; C3 contrôle inverse battu
    (Δrègle > Δcontrôle) en TRAIN ET en VAL.
  - FAIL = tout le reste → « FAIL — hypothèse réfutée », gravé, STOP.
  - QA : unités open_time (ms) vérifiées sur 1h ET 15m (leçon ts_ms) ;
    cohérence 1h-high vs max(15m highs) de l'heure d'entrée ; référence
    bit-à-bit contre les champs machine (entry/exit/price_ret) ;
    bougies 15m manquantes comptées.

INTERDITS respectés : data/fomo/ intact, aucun service, aucun install,
pas de & ; klines.db ouverte en lecture seule (uri mode=ro) pour les
requêtes propres du script ; les modules machine ne font que SELECT.
════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.p5_frequency_test import collect_vol_spike  # noqa: E402
from scripts.portfolio_sim import MAJORS, btc_regime_series  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
FEE_RT_BPS = 18.0          # étalon du domaine, identique des deux côtés
GATE_MIN = 3.0             # bps — seuil PASS C1
MS_15M = 15 * 60 * 1000

# ─── le bloc pré-enregistré est imprimé AVANT tout calcul ───
PRE_REG = "\n".join(
    l for l in __doc__.splitlines()
    if not l.startswith(('"""', "#!/usr/bin/env", '"""INV-O'))
).strip()
print("===== PRÉ-ENREGISTREMENT INV-O (AVANT toute mesure) =====")
print(PRE_REG[:400] + "\n[… bloc complet scellé dans le rapport …]")


def ro_con() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)


def load_15m(con: sqlite3.Connection) -> dict[str, dict[str, np.ndarray]]:
    out: dict[str, dict[str, np.ndarray]] = {}
    for sym, in con.execute(
            "SELECT DISTINCT symbol FROM klines WHERE interval='15m'"):
        rows = con.execute(
            "SELECT open_time, open, high, low, close FROM klines "
            "WHERE symbol=? AND interval='15m' ORDER BY open_time",
            (sym,)).fetchall()
        if not rows:
            continue
        a = np.array(rows, dtype=float)
        out[sym] = {"ts": a[:, 0].astype(np.int64), "open": a[:, 1],
                    "high": a[:, 2], "low": a[:, 3], "close": a[:, 4]}
    return out


def m15(m: dict[str, dict[str, np.ndarray]], sym: str, ts_ms: int):
    """La bougie 15m native pile à ts_ms, ou None (0 fill-forward)."""
    d = m.get(sym)
    if d is None:
        return None
    i = int(np.searchsorted(d["ts"], ts_ms))
    if i < len(d["ts"]) and d["ts"][i] == ts_ms:
        return d["open"][i], d["high"][i], d["low"][i], d["close"][i]
    return None


def refine(entry_open: float, side: str, d15, sym: str, ts_ms: int,
           inverse: bool):
    """La règle pré-déclarée (ou son miroir). Retourne (prix, k_choisi,
    n_bougies_manquantes). side ∈ {long, short}."""

    def on_side(c):
        return c < entry_open if side == "short" else c > entry_open

    def against(c):
        return c > entry_open if side == "short" else c < entry_open

    test = against if inverse else on_side
    miss = 0
    for k in (1, 2, 3):
        bar = m15(d15, sym, ts_ms + (k - 1) * MS_15M)
        if bar is None:
            miss += 1
            continue
        if test(bar[3]):
            return bar[3], k, miss
    return entry_open, 0, miss


def arm_metrics(e: dict, d15, sym: str, ts_ms: int, entry_px: float,
                entry_bar_k: int, hold_h: int):
    """(gross_bps, mae_pct) pour un prix d'entrée donné — exit bit-exact.
    MAE : grille 15m dans l'heure d'entrée (bougies strictement après la
    bougie d'entrée), puis 1h ei+1..exit."""
    side = e["side"]
    ex = e["exit"]
    gross = ((entry_px - ex) / entry_px * 100 if side == "short"
             else (ex - entry_px) / entry_px * 100) * 100  # bps
    # MAE fine : intérieur de l'heure d'entrée en 15m natif
    hs, ls = [], []
    for k in range(1, 5):
        bar = m15(d15, sym, ts_ms + (k - 1) * MS_15M)
        if bar is None or (entry_bar_k and k <= entry_bar_k):
            continue
        hs.append(bar[1])
        ls.append(bar[2])
    # puis les 1h postérieures à l'heure d'entrée (ei+1..exit_j)
    for j in range(e["ei"] + 1, e["exit_j"] + 1):
        hs.append(e["highs"][j])
        ls.append(e["lows"][j])
    if hs:
        mae = ((max(hs) - entry_px) / entry_px * 100 if side == "short"
               else (entry_px - min(ls)) / entry_px * 100)
        mae = max(mae, 0.0)
    else:
        mae = 0.0
    return gross, mae


def main() -> int:
    print("===== EXÉCUTION (après pré-enregistrement) =====")
    con = ro_con()

    # ── QA unités temporelles (leçon ts_ms) ──
    for iv in ("1h", "15m"):
        lo, hi = con.execute(
            "SELECT MIN(open_time), MAX(open_time) FROM klines "
            "WHERE interval=? AND symbol='BTCUSDT'", (iv,)).fetchone()
        assert 10**11 < lo < 10**14 and 10**11 < hi < 10**14, f"unité {iv}!"
    _mx = con.execute("SELECT MAX(open_time) FROM klines WHERE "
                      "interval='1h' AND symbol='BTCUSDT'").fetchone()[0]
    print(f"[qa] open_time en ms vérifié (1h et 15m) : BTC 1h max "
          f"{datetime.fromtimestamp(_mx / 10**3, tz=timezone.utc):%Y-%m-%d %H:%M} UTC")

    # ── flux 1 : cascade majors gated, code exact the_machine (lecture) ──
    regime = btc_regime_series()
    events = collect_featured(regime, "majors")
    add_rolling_scores(events)
    q66 = float(np.nanquantile(
        [e.get("al_score", float("nan"))
         for e in events[:int(len(events) * 0.7)]], 2 / 3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= q66)]
    print(f"[flux1] cascade majors : {len(events)} événements, gate AL "
          f"q66={q66:.4f} → {len(gated)} gated (code machine bit-exact)")
    for e in gated:
        e["side"] = "short"
        e["hold_h"] = 24
        e["flow"] = "gated"

    # ── flux 4 : vol_spike 6h (gate ATR inclus) ──
    spike = collect_vol_spike(con, hold=6)
    print(f"[flux4] vol_spike : {len(spike)} événements (gate ATR p90 inclus)")
    for e in spike:
        e["hold_h"] = 6
        e["flow"] = "vol_spike"

    # LEÇON ts_ms : les modules machine stockent ts_ms en NANOSECONDES
    # (nom hérité, cf. anti_liq « ts_ms = des NS ») — normalisation en ms
    # AVANT tout join avec klines.open_time (ms).
    for e in gated + spike:
        e["ts_ms"] = int(e["ts_ms"]) // 10**6

    # ── index 1h par flux pour reconstruire ei/exit_j ──
    from scripts.backtest_indicators import load_df  # noqa: E402
    idx1h: dict[str, tuple[np.ndarray, list, list]] = {}
    for sym in sorted({e["sym"] for e in gated + spike}):
        df = load_df(con, sym)
        if df is None:
            continue
        ts = df.index.astype("datetime64[ns]").asi8 // 10**6
        idx1h[sym] = (ts, df["high"].values, df["low"].values)
    for e in gated + spike:
        ts, highs, lows = idx1h[e["sym"]]
        ei = int(np.searchsorted(ts, e["ts_ms"]))
        assert ts[ei] == e["ts_ms"], f"alignement 1h {e['sym']} {e['ts_ms']}"
        e["ei"] = ei
        e["exit_j"] = ei + e["hold_h"] - 1
        e["highs"], e["lows"] = highs, lows

    # ── les 3 bras sur l'ensemble évaluable ──
    m15d = load_15m(con)
    con.close()
    rows: list[dict] = []
    n_excl = n_miss_bars = n_open_fb = n_open_fb_inv = 0
    qa_high_diff = 0.0
    for e in gated + spike:
        ts_ms = e["ts_ms"]
        d15 = m15d.get(e["sym"])
        has15 = m15(m15d, e["sym"], ts_ms) is not None or any(
            m15(m15d, e["sym"], ts_ms + (k - 1) * MS_15M) is not None
            for k in (2, 3))
        if not has15:
            n_excl += 1
            continue
        entry_open = e["entry"]
        # QA cohérence 1h-high vs max(15m highs) de l'heure d'entrée
        h15 = [m15(m15d, e["sym"], ts_ms + (k - 1) * MS_15M)[1]
               for k in (1, 2, 3, 4)
               if m15(m15d, e["sym"], ts_ms + (k - 1) * MS_15M) is not None]
        if h15:
            qa_high_diff = max(qa_high_diff,
                               abs(max(h15) - e["highs"][e["ei"]])
                               / e["highs"][e["ei"]] * 100)
        px_m, k_m, miss_m = refine(entry_open, e["side"], m15d, e["sym"],
                                   ts_ms, inverse=False)
        px_c, k_c, miss_c = refine(entry_open, e["side"], m15d, e["sym"],
                                   ts_ms, inverse=True)
        n_miss_bars += miss_m
        if k_m == 0:
            n_open_fb += 1
        if k_c == 0:
            n_open_fb_inv += 1
        g_ref, mae_ref = arm_metrics(e, m15d, e["sym"], ts_ms,
                                     entry_open, 0, e["hold_h"])
        g_m, mae_m = arm_metrics(e, m15d, e["sym"], ts_ms, px_m, k_m,
                                 e["hold_h"])
        g_c, mae_c = arm_metrics(e, m15d, e["sym"], ts_ms, px_c, k_c,
                                 e["hold_h"])
        # référence bit-à-bit : gross_ref ≡ champ machine price_ret_short
        mach = e["price_ret_short"] * 100
        assert abs(g_ref - mach) < 1e-6, (
            f"référence non bit-exact {e['sym']} {ts_ms}: {g_ref} vs {mach}")
        rows.append({"sym": e["sym"], "ts_ms": ts_ms,
                     "flow": e["flow"],
                     "side": e["side"], "k_m": k_m,
                     "ref": g_ref - FEE_RT_BPS, "var": g_m - FEE_RT_BPS,
                     "ctl": g_c - FEE_RT_BPS,
                     "mae_ref": mae_ref, "mae_var": mae_m,
                     "mae_ctl": mae_c})
    rows.sort(key=lambda r: r["ts_ms"])
    n = len(rows)
    print(f"[pop] évaluable : {n}/{len(gated) + len(spike)} entrées "
          f"(exclues sans 15m natif : {n_excl}) | fallback open règle : "
          f"{n_open_fb}, contrôle : {n_open_fb_inv} | bougies 15m "
          f"manquantes sautées : {n_miss_bars}")
    print(f"[qa] écart max |1h-high − max(15m highs)| heure d'entrée : "
          f"{qa_high_diff:.4f} % | référence bit-à-bit vs champs machine : OK")
    # QA descriptive : MAE machine (1h, tous gated) vs référence fine (15m)
    _mae_mach = max(e["mae_adverse"] for e in gated)
    print(f"[qa] MAE max machine (champ mae_adverse 1h, tous gated "
          f"{len(gated)}) : {_mae_mach:.2f} % (le bras référence fin-15m ne "
          f"peut être que ≤) | histogramme k règle : "
          + ", ".join(f"k={kk}: {sum(1 for r in rows if r['k_m'] == kk)}"
                      for kk in (0, 1, 2, 3)))

    # ── split 60/40 chrono GLOBAL (ensemble évaluable poolé) ──
    k = int(n * 0.6)
    train, val = rows[:k], rows[k:]
    split_ts = rows[k]["ts_ms"] if k < n else float("nan")
    print(f"[split] 60/40 chrono global : {len(train)}/{len(val)} — "
          f"estampe {datetime.fromtimestamp(split_ts/10**3, tz=timezone.utc):%Y-%m-%d %H:%M} UTC")
    if len(train) < 100:
        print(f"VERDICT : SOUS-PUISSENT — n_train {len(train)} < 100, "
              "aucun PASS possible. Budget consommé, STOP.")
        return 0

    def stats(rs: list[dict], key: str) -> tuple[float, float, float]:
        v = np.array([r[key] for r in rs])
        return float(np.mean(v)), float(np.median(v)), float(np.mean(v > 0) * 100)

    def mae_max(rs: list[dict], key: str) -> float:
        return float(np.max([r[key] for r in rs])) if rs else 0.0

    verdicts = {}
    for name, rs in (("TRAIN", train), ("VAL", val)):
        mref = stats(rs, "ref")[0]
        mvar = stats(rs, "var")[0]
        mctl = stats(rs, "ctl")[0]
        d_var = mvar - mref
        d_ctl = mctl - mref
        gm = [r for r in rs if r["flow"] == "gated"]
        mae_ref_g = mae_max(gm, "mae_ref")
        mae_var_g = mae_max(gm, "mae_var")
        verdicts[name] = (d_var, d_ctl, mae_ref_g, mae_var_g, mref, mvar, mctl)
        print(f"\n[{name}] n={len(rs)} (gated {len(gm)} / vol_spike "
              f"{len(rs) - len(gm)})")
        print(f"  espérance nette bps/entrée : référence {mref:+.2f} | "
              f"variante 15m {mvar:+.2f} | contrôle inverse {mctl:+.2f}")
        print(f"  Δ variante−référence {d_var:+.2f} bps | Δ contrôle−référence "
              f"{d_ctl:+.2f} bps")
        print(f"  MAE max gated : référence {mae_ref_g:.2f} % | variante "
              f"{mae_var_g:.2f} %")
        # descriptive par flux
        for fl in ("gated", "vol_spike"):
            sub = [r for r in rs if r["flow"] == fl]
            if sub:
                a, b, c = stats(sub, "ref"), stats(sub, "var"), stats(sub, "ctl")
                print(f"    [{fl}] n={len(sub)} ref {a[0]:+.2f} | var "
                      f"{b[0]:+.2f} (Δ {b[0]-a[0]:+.2f}) | ctl {c[0]:+.2f} "
                      f"(Δ {c[0]-a[0]:+.2f}) bps nets")

    # ── verdict mécanique (critères écrits AVANT) ──
    dt, dv = verdicts["TRAIN"], verdicts["VAL"]
    C1 = dt[0] >= GATE_MIN and dv[0] >= GATE_MIN
    C2 = dt[3] <= dt[2] + 1e-9
    C3 = dt[0] > dt[1] and dv[0] > dv[1]
    print("\n===== VERDICT MÉCANIQUE (critères pré-écrits) =====")
    print(f"C1 Δespérance ≥ +{GATE_MIN} bps TRAIN et VAL : "
          f"{dt[0]:+.2f}/{dv[0]:+.2f} → {'OK' if C1 else 'ECHEC'}")
    print(f"C2 MAE max gated TRAIN variante ≤ référence : "
          f"{dt[3]:.2f} ≤ {dt[2]:.2f} → {'OK' if C2 else 'ECHEC'}")
    print(f"C3 contrôle inverse battu TRAIN et VAL : "
          f"{dt[0]:+.2f}>{dt[1]:+.2f} / {dv[0]:+.2f}>{dv[1]:+.2f} → "
          f"{'OK' if C3 else 'ECHEC'}")
    if C1 and C2 and C3:
        print("VERDICT : PASS — hypothèse confirmée sur les 3 critères.")
    else:
        print("VERDICT : FAIL — hypothèse réfutée. Budget consommé, STOP.")

    # ── BLOC STATS mensuel par bras × split (notionnel 1x additif) ──
    for name, rs in (("TRAIN", train), ("VAL", val)):
        print(f"\n[BLOC STATS MENSUEL {name}] notionnel 1x additif "
              "(chevauchements inclus, pas un wallet séquentiel)")
        for arm, key in (("référence open", "ref"), ("variante 15m", "var"),
                         ("contrôle inverse", "ctl")):
            months: dict[str, list[float]] = {}
            for r in rs:
                m = datetime.fromtimestamp(r["ts_ms"] / 10**3,
                                           tz=timezone.utc).strftime("%Y-%m")
                months.setdefault(m, []).append(r[key])
            ms = sorted(months)
            means = [float(np.mean(months[m])) for m in ms]
            sums = [float(np.sum(months[m])) for m in ms]
            nn = [len(months[m]) for m in ms]
            wrs = [float(np.mean([v > 0 for v in months[m]]) * 100) for m in ms]
            neg = sum(1 for s in sums if s < 0)
            print(f"  {arm:<18} n={len(rs)} WR {stats(rs, key)[2]:.1f} % | "
                  f"mois: {len(ms)} | somme bps {sum(sums):+.0f} | "
                  f"pire mois {min(means):+.2f} bps/entrée | record "
                  f"{max(means):+.2f} | négatifs {neg}/{len(ms)}")
            print("    | Mois | Trades | WR | bps somme | bps moyenne |")
            for m, a, w, s, mu in zip(ms, nn, wrs, sums, means):
                print(f"    | {m} | {a} | {w:.0f} % | {s:+.1f} | {mu:+.2f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
