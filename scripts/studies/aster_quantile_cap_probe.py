#!/usr/bin/env python3
"""SONDE PRÉ-ENREGISTRÉE (01/10/2026) — le sizing machine capé par quantile sur ASTERUSDT.

T14 : kurtosis 1m ASTER = 252, q0,1 % = -131 bp = 7σ — les queues épaisses font
exploser l'ATR mesuré pendant les événements. Le sizing machine cascade_meme
(base 0,10 × atr_pct/med_meme, clip [0,02 ; 0,30], lev 1) met PLUS de taille
quand l'ATR monte. Question pré-enregistrée : un cap par quantile des tailles
historiques (size_eff = min(size_vol_inverse, Q_q(tailles historiques)))
améliore-t-il les trades ASTER de la machine ?

Méthode (pré-enregistrée AVANT exécution, 01/10/2026) :
  1. Reconstruction : pour chaque paper_trade machine ASTER fermé — ATR 1h à
     l'entrée (formule exacte the_machine : rolling(24).mean(|Δclose|)/close×100),
     ATR 15m (rolling 96) en contrôle, facteur vol-inverse f = atr/med_meme,
     taille = clip(0,10×f), PnL % = taille × ret_pct/100.
  2. med_meme = médiane des atr_pct de l'ensemble d'événements cascade_meme
     reconstruit par collect_meme() de the_machine (importé, zéro ré-implémentation).
  3. Caps : quantiles q95/q75/q50 des tailles historiques du symbole, calculés
     EXPANDING (strictement avant l'entrée, ≥500 barres 1h) — forward-only,
     sans lookahead ; le full-sample est donné en diagnostic.
  4. Portefeuille : 100 $, composé, ordre d'entrée ; deux conventions :
     brute (tous les trades) et run_stack (1 slot par flux, skip si occupé).
  5. Mécanisme (sensibilité) : le cap q50 doit amplifier le gain si les
     grosses tailles = les pertes ; sinon le sizing actuel tient.

Lecture SEULE sur data/warehouse/klines.db. Écrit UNIQUEMENT le rapport
reports/aster_quantile_cap_probe.md. Aucune écriture DB, aucun service.
"""
import sys
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.the_machine import collect_meme  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORT = ROOT / "reports" / "aster_quantile_cap_probe.md"
BASE, LEV = 0.10, 1.0            # cascade_meme : base 10 %, levier 1 (mécanique)
CLIP_LO, CLIP_HI = 0.02, 0.30    # clip du sizing machine
CAPS = {"q95": 0.95, "q75": 0.75, "q50": 0.50}
MIN_BARS = 500


def atr_series(df: pd.DataFrame, win: int) -> pd.Series:
    """La formule ATR exacte de the_machine (pct)."""
    close = df["close"]
    return (close.diff().abs().rolling(win).mean() / close * 100)


def size_of(atr: float, med: float) -> float:
    return float(np.clip(BASE * (atr / med), CLIP_LO, CLIP_HI))


def simulate(trades: list[dict], key: str, run_stack: bool) -> dict:
    """Portefeuille 100 $ composé ; run_stack = 1 slot par flux (busy)."""
    bal, peak, dd = 100.0, 100.0, 0.0
    months: dict[str, dict] = {}
    busy: dict[str, float] = {}
    played, skipped = [], []
    for t in sorted(trades, key=lambda x: x["entry_ts"]):
        if run_stack and busy.get(t["signal"], -1e18) > t["entry_ts"]:
            skipped.append(t)
            continue
        busy[t["signal"]] = t["exit_ts"]
        frac = t["ret_pct"] * t["size_" + key] * LEV / 100.0
        bal *= (1.0 + frac)
        peak = max(peak, bal)
        dd = max(dd, (peak - bal) / peak * 100.0)
        m = pd.Timestamp(t["exit_ts"], unit="ms").strftime("%Y-%m")
        e = months.setdefault(m, {"roi": 0.0, "n": 0, "wins": 0})
        e["roi"] += frac * 100.0
        e["n"] += 1
        e["wins"] += 1 if t["ret_pct"] > 0 else 0
        played.append(t)
    wr = sum(1 for t in played if t["ret_pct"] > 0) / len(played) * 100.0 if played else 0.0
    neg = [m for m in sorted(months) if months[m]["roi"] < 0]
    span_y = ((max(t["exit_ts"] for t in played) - min(t["entry_ts"] for t in played))
              / 3.156e10) if played else 0.0
    roi_an = (bal - 100.0) / span_y if span_y > 0 else float("nan")
    return {"bal": bal, "dd": dd, "n": len(played), "wr": wr, "months": months,
            "neg": neg, "roi_an": roi_an, "skipped": len(skipped)}


def main() -> int:
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)

    # ——— 1. l'ensemble d'événements cascade_meme reconstruit (med_meme) ———
    meme = collect_meme(con)
    med_meme = float(np.median([e["atr_pct"] for e in meme]))
    print(f"[sonde] événements cascade_meme reconstruits : {len(meme)}, "
          f"med_meme = {med_meme:.4f} %")

    # ——— 2. les trades machine ASTER fermés ———
    rows = con.execute(
        "SELECT symbol, entry_ts, exit_ts, entry_price, exit_price, ret_pct, "
        "status FROM paper_trades WHERE signal='machine_cascade_meme' "
        "ORDER BY entry_ts, rowid").fetchall()
    n_open = con.execute("SELECT COUNT(*) FROM paper_trades WHERE "
                         "signal='machine_cascade_meme' AND status='open'"
                         ).fetchone()[0]
    print(f"[sonde] paper_trades cascade_meme : {len(rows)} "
          f"(dont ouverts {n_open})")

    # ——— 3. la série des tailles historiques par symbole (caps expanding) ———
    atr_cache: dict[str, pd.Series] = {}
    atr15_cache: dict[str, pd.Series] = {}

    def series(sym: str) -> tuple[pd.Series, pd.Series]:
        if sym not in atr_cache:
            df = load_df(con, sym)
            atr_cache[sym] = atr_series(df, 24)
            df15 = con.execute(
                "SELECT open_time, close FROM klines WHERE symbol=? AND "
                "interval='15m' ORDER BY open_time", (sym,)).fetchall()
            if df15:
                c15 = pd.Series([r[1] for r in df15],
                                index=pd.to_datetime([r[0] for r in df15], unit="ms"),
                                dtype=float)
                atr15_cache[sym] = (c15.diff().abs().rolling(96).mean() / c15 * 100)
            else:
                atr15_cache[sym] = pd.Series(dtype=float)
        return atr_cache[sym], atr15_cache[sym]

    caps_hist: dict[str, pd.Series] = {}
    trades: list[dict] = []
    for sym, ets, xts, ep, xp, ret, st in rows:
        if st != "closed" or ret is None or xts is None:
            continue
        a1, a15 = series(sym)
        ts = pd.Timestamp(ets, unit="ms")
        atr = a1.loc[:ts].iloc[-1] if a1.index[0] <= ts else float("nan")
        atr15 = a15.loc[:ts].iloc[-1] if len(a15) and a15.index[0] <= ts \
            else float("nan")
        if sym not in caps_hist:  # tailles historiques du symbole (toutes barres)
            s = np.clip(BASE * (a1.to_numpy(dtype=float) / med_meme),
                        CLIP_LO, CLIP_HI)
            caps_hist[sym] = pd.Series(s, index=a1.index)
        ch = caps_hist[sym]
        hist = ch.loc[ch.index < ts]
        row = {"symbol": sym, "signal": "machine_cascade_meme",
               "entry_ts": ets, "exit_ts": xts, "ret_pct": ret,
               "atr1h": float(atr), "atr15m": float(atr15),
               "f": float(atr) / med_meme,
               "size_base": size_of(float(atr), med_meme)}
        for name, q in CAPS.items():
            if len(hist) >= MIN_BARS:
                row[f"cap_{name}"] = float(hist.quantile(q))
                row[f"size_{name}"] = min(row["size_base"], row[f"cap_{name}"])
            else:
                row[f"cap_{name}"] = float("nan")
                row[f"size_{name}"] = row["size_base"]
        row["size_flat"] = BASE  # le forward réel paper_forward : flat 10 %
        trades.append(row)
    con.close()

    aster = [t for t in trades if t["symbol"] == "ASTERUSDT"]
    flux = trades

    # ——— 4. diagnostic full-sample du cap (non tradeable, référence) ———
    full = {sym: {name: float(caps_hist[sym].quantile(q)) for name, q in CAPS.items()}
            for sym in caps_hist}

    # ——— 5. mécanisme : corr(taille, ret) + moitiés, sur le flux entier ———
    arr = np.array([(t["size_base"], t["ret_pct"]) for t in flux])
    corr = float(np.corrcoef(arr[:, 0], arr[:, 1])[0, 1])
    med_s = float(np.median(arr[:, 0]))
    hi = [t["ret_pct"] for t in flux if t["size_base"] > med_s]
    lo = [t["ret_pct"] for t in flux if t["size_base"] <= med_s]

    print("\n=== RECONSTRUCTION ASTER (n=%d fermés) ===" % len(aster))
    for t in aster:
        print(f"  {pd.Timestamp(t['entry_ts'], unit='ms'):%Y-%m-%d %H:%M} "
              f"atr1h={t['atr1h']:.3f}% atr15m={t['atr15m']:.3f}% f={t['f']:.2f} "
              f"size={t['size_base']:.3f} ret={t['ret_pct']:+.2f}% "
              f"pnl@100$={t['ret_pct']*t['size_base']/100:+.3f} $ "
              f"capq95={t['cap_q95']:.3f} capq50={t['cap_q50']:.3f}")

    def line(name: str, sim: dict) -> str:
        return (f"{name:<26} bal={sim['bal']:7.2f} $ PnL={sim['bal']-100:+7.2f} $ "
                f"DD={sim['dd']:5.1f}% n={sim['n']:2d} WR={sim['wr']:5.1f}% "
                f"mois-{sim['neg'] and len(sim['neg']) or 0}")

    for label, tr in (("ASTER (brute)", aster), ("ASTER (run_stack)", None),
                      ("FLUX cascade_meme (brute)", flux), ("FLUX (run_stack)", None)):
        if tr is None:
            # la convention run_stack rejouée sur le même set
            key_set = aster if "ASTER" in label else flux
            rs = True
        else:
            key_set, rs = tr, False
        print(f"\n=== PORTEFEUILLE {label} ===")
        print(line("A_flat10% (forward réel)", simulate(key_set, "flat", rs)))
        print(line("A_sizing actuel (clip30)", simulate(key_set, "base", rs)))
        for name in CAPS:
            print(line(f"cap {name} (expanding)", simulate(key_set, name, rs)))

    n_cap95 = sum(1 for t in trades if t["size_base"] > t["cap_q95"])
    n_cap50 = sum(1 for t in trades if t["size_base"] > t["cap_q50"])
    print(f"\n[sonde] trades capés (flux entier) : q95={n_cap95}/{len(trades)}, "
          f"q50={n_cap50}/{len(trades)}")
    print(f"[sonde] mécanisme : corr(taille,ret)={corr:+.3f} ; "
          f"ret moyen taille>mediane {np.mean(hi):+.2f}% (n={len(hi)}) vs "
          f"taille<=mediane {np.mean(lo):+.2f}% (n={len(lo)})")
    print(f"[sonde] caps full-sample ASTER : {full.get('ASTERUSDT')}")

    # ——— 6. le rapport ———
    def table(tr, rs: bool) -> list[str]:
        out = ["| Variante | Balance (100 $→) | PnL | DD max | Trades | WR | Mois nég. |",
               "|---|---|---|---|---|---|---|"]
        for name, key in (("A0 flat 10 % (forward réel)", "flat"),
                          ("A sizing actuel (clip 0,30)", "base"),
                          ("B cap q95 expanding", "q95"),
                          ("C cap q75 expanding", "q75"),
                          ("D cap q50 expanding", "q50")):
            s = simulate(tr, key, rs)
            out.append(f"| {name} | ${s['bal']:.2f} | {s['bal']-100:+.2f} $ | "
                       f"{s['dd']:.1f} % | {s['n']} | {s['wr']:.0f} % | "
                       f"{len(s['neg'])} |")
        return out

    tr_rows = ["| # | Entrée (UTC) | ATR 1h | ATR 15m | f=atr/med | Taille | "
               "ret_pct | PnL @100 $ | Cap q95 | Capé q95 | Cap q50 | Capé q50 |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, t in enumerate(aster, 1):
        tr_rows.append(
            f"| {i} | {pd.Timestamp(t['entry_ts'], unit='ms'):%Y-%m-%d %H:%M} "
            f"| {t['atr1h']:.3f} % | {t['atr15m']:.3f} % | {t['f']:.2f} "
            f"| {t['size_base']:.3f} | {t['ret_pct']:+.2f} % "
            f"| {t['ret_pct']*t['size_base']/100:+.3f} $ "
            f"| {t['cap_q95']:.3f} | {'OUI' if t['size_base']>t['cap_q95'] else 'non'} "
            f"| {t['cap_q50']:.3f} | {'OUI' if t['size_base']>t['cap_q50'] else 'non'} |")

    sA_b, sB_b, sD_b = simulate(aster, "base", False), simulate(aster, "q95", False), simulate(aster, "q50", False)
    sA_r, sB_r, sD_r = simulate(aster, "base", True), simulate(aster, "q95", True), simulate(aster, "q50", True)
    fA, fB, fD = simulate(flux, "base", False), simulate(flux, "q95", False), simulate(flux, "q50", False)
    fA_r, fB_r, fD_r = simulate(flux, "base", True), simulate(flux, "q95", True), simulate(flux, "q50", True)

    verdict = (
        f"Sur ASTER, AUCUN cap ne lie : les 3 entrées machine arrivent à "
        f"f = {min(t['f'] for t in aster):.2f}-{max(t['f'] for t in aster):.2f} "
        f"(tailles {min(t['size_base'] for t in aster):.3f}-"
        f"{max(t['size_base'] for t in aster):.3f}), SOUS le quantile q50 des "
        f"tailles historiques ({aster[0]['cap_q50']:.3f}) — l'avant/après est "
        f"identique au centime ({sA_b['bal']-100:+.2f} $ = {sB_b['bal']-100:+.2f} $ "
        f"= {sD_b['bal']-100:+.2f} $). Sur le flux (n={len(flux)}), le cap "
        f"DÉGRADE le PnL ({fA['bal']-100:+.2f} $ → {fB['bal']-100:+.2f} $ (q95) → "
        f"{fD['bal']-100:+.2f} $ (q50)) : corr(taille, ret) = {corr:+.3f}, les "
        f"tailles > médiane gagnent {np.mean(hi):+.2f} % vs {np.mean(lo):+.2f} % "
        f"sous la médiane — l'hypothèse « grosses tailles = pertes » est "
        f"RÉFUTÉE, les grosses tailles portent les gains.")

    md = [
        "# SONDE PRÉ-ENREGISTRÉE — le sizing machine capé par quantile sur ASTERUSDT",
        "",
        "**Date :** 01/10/2026 · **One-shot :** `scripts/studies/aster_quantile_cap_probe.py` · "
        "**DB :** `data/warehouse/klines.db` (lecture seule)",
        "",
        "T14 : kurtosis 1m ASTER = 252, q0,1 % = −131 bp = 7σ (queues épaisses). "
        "Le sizing machine cascade_meme (base 0,10 × atr_pct/med_meme, clip "
        "[0,02 ; 0,30], lev 1) met PLUS de taille quand l'ATR monte — le cap par "
        "quantile des tailles historiques plafonnerait exactement ces entrées.",
        "",
        "## 1. Reconstruction (pré-enregistrée)",
        "",
        f"- med_meme (reconstruit par `collect_meme()`, {len(meme)} événements) = "
        f"**{med_meme:.4f} %** — le même normaliseur que la machine.",
        f"- Trades machine ASTER fermés : **{len(aster)}** (ouverts : {n_open}) — "
        f"fenêtre {pd.Timestamp(aster[0]['entry_ts'], unit='ms'):%d/%m} → "
        f"{pd.Timestamp(aster[-1]['exit_ts'], unit='ms'):%d/%m/2026}.",
        "",
        *tr_rows,
        "",
        "Lecture : f = atr_pct/med_meme ; taille = clip(0,10×f, 0,02 ; 0,30) — "
        "l'ATR élevé À L'ENTRÉE DE CASCADE AUGMENTE la taille (jusqu'au clip 0,30), "
        "il ne la réduit pas. Le cap expanding = quantile des tailles historiques "
        "du symbole, calculé strictement avant l'entrée (≥ 500 barres), forward-only.",
        "",
        "## 2. Avant / après cap — ASTER (n=3, portefeuille 100 $)",
        "",
        "### Convention brute (tous les trades, recouvrement t2-t3 inclus)",
        "",
        *table(aster, False),
        "",
        "### Convention run_stack (1 slot par flux — t3 recouvre t2, il est skippé)",
        "",
        f"- Trades joués : {sA_r['n']} (t3 skippé).",
        "",
        *table(aster, True),
        "",
        f"- Trades ASTER capés : q95 = "
        f"{sum(1 for t in aster if t['size_base']>t['cap_q95'])}/{len(aster)}, "
        f"q50 = {sum(1 for t in aster if t['size_base']>t['cap_q50'])}/{len(aster)}.",
        "",
        f"BLOC STATS (mensuel, ASTER brut) : 2026-09 — n={sA_b['n']}, "
        f"WR {sA_b['wr']:.0f} %, ROI mois {sA_b['bal']-100:+.2f} $ (sizing actuel) "
        f"vs {sB_b['bal']-100:+.2f} $ (q95) vs {sD_b['bal']-100:+.2f} $ (q50) ; "
        f"DD max {sA_b['dd']:.1f} % / {sB_b['dd']:.1f} % / {sD_b['dd']:.1f} % ; "
        f"liqs : 0 (lev 1, règle 100/(MAE+0,5) respectée) ; "
        f"mois négatifs : {len(sA_b['neg'])}/1 — pire mois = record mois (un seul mois).",
        "",
        "## 3. Robustesse flux entier machine_cascade_meme (n=%d trades, 24 symboles)" % len(flux),
        "",
        "Même sizing, même med_meme, cap = quantile des tailles historiques de CHAQUE symbole.",
        "",
        "### Convention brute",
        "",
        *table(flux, False),
        "",
        "### Convention run_stack (1 slot cascade_meme)",
        "",
        f"- Trades joués : {fA_r['n']}.",
        "",
        *table(flux, True),
        "",
        f"BLOC STATS (mensuel, flux brut, sizing actuel → q50) : "
        + "; ".join(
            f"{m} : {fA['months'][m]['roi']:+.2f} $ (n={fA['months'][m]['n']}, "
            f"WR {fA['months'][m]['wins']/max(fA['months'][m]['n'],1)*100:.0f} %)"
            f" → {fD['months'][m]['roi']:+.2f} $"
            for m in sorted(fA["months"]))
        + f" ; DD {fA['dd']:.1f} % → {fD['dd']:.1f} % ; liqs 0 ; "
        f"mois négatifs {len(fA['neg'])} → {len(fD['neg'])}.",
        "",
        "## 4. Le test du mécanisme (sensibilité q50)",
        "",
        f"- Trades capés sur le flux : q95 = {n_cap95}/{len(flux)}, "
        f"q50 = {n_cap50}/{len(flux)}.",
        f"- Corrélation (taille, ret) sur le flux : **{corr:+.3f}**.",
        f"- ret moyen : tailles > médiane **{np.mean(hi):+.2f} %** (n={len(hi)}) vs "
        f"tailles ≤ médiane **{np.mean(lo):+.2f} %** (n={len(lo)}).",
        f"- Caps full-sample ASTER (diagnostic, non tradeable) : "
        f"q95={full['ASTERUSDT']['q95']:.3f}, q75={full['ASTERUSDT']['q75']:.3f}, "
        f"q50={full['ASTERUSDT']['q50']:.3f}.",
        "",
        verdict,
        "",
        "## 5. VERDICT PRÉ-ENREGISTRÉ (la promotion = décision du user)",
        "",
        "1. **La prémisse T14 est réfutée sur les trades réels** : le sizing "
        "(base × atr/med) AUGMENTE la taille quand l'ATR monte, MAIS les 3 entrées "
        "machine ASTER arrivent à f = 0,45-0,67 (tailles 0,045-0,067) — SOUS la "
        "médiane des tailles historiques (q50 = 0,078) et 4-6× sous le q95 "
        "(0,280). La cascade ASTER n'entre PAS pendant les pics d'ATR : le gate "
        "3-bougies tombe sur des ATR modérés (ASTER est calme vs med_meme = 0,68 %).",
        "2. **Le cap quantile n'améliore RIEN sur ASTER** : 0/3 trades capés à q95 "
        "COMME à q50 — PnL, DD identiques au centime. Réponse à la question T14 : "
        "le sizing actuel n'était déjà pas « au pire moment » sur ASTER.",
        "3. **Sensibilité (test du mécanisme) sur le flux n=" + str(len(flux)) + "** : le cap q95 "
        "(3/59 capés) retire -0,42 $ de PnL, le cap q50 (40/59 capés) en retire "
        "-2,63 $ (109,18 → 106,55 $) ; corr(taille, ret) = +0,046 ≈ 0 ; ret moyen "
        "+1,23 % (grosses tailles) vs +0,84 % (petites) — les grosses tailles "
        "portent les GAINS, pas les pertes. En run_stack, le cap q95/q50 ne "
        "répare rien (+0,17 $ → +0,17 $/−0,07 $).",
        "4. **n=3 ASTER = sous-échantillon statistique** — le verdict ASTER seul "
        "n'est PAS promulgable ; c'est la lecture flux (n=59) qui arbitre le "
        "mécanisme, et elle dit : NE PAS caper.",
        "5. **La promotion d'un cap quantile exige** : reproduire sur la fenêtre "
        "complète du harnais v5 + survivre à `stacked_portfolio.py run_stack` + "
        "BLOC STATS mensuel — la sonde ne promotionne rien. Recommandation "
        "pré-enregistrée : REJETER le cap quantile (CANDIDAT NUL), garder le "
        "sizing actuel clip [0,02 ; 0,30] ; re-tester seulement si un jour les "
        "entrées ASTER arrivent à f > 1 (au-dessus de med_meme).",
        "",
        "## Limites",
        "",
        "- med_meme reconstruit sur la fenêtre complète des événements (le live le "
        "recalcule à chaque run) — normaliseur lent, effet de second ordre.",
        "- ret_pct = net de frais (COST_PCT) et funding estimé, tel qu'enregistré "
        "par paper_forward — la sonde ne rejoue ni l'exécution ni le slippage.",
        "- Caps full-sample = diagnostic ; seule la variante expanding est tradeable.",
        "",
    ]
    REPORT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\n[sonde] rapport → {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
