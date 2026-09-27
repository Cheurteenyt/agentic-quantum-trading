#!/usr/bin/env python
"""H2bis (CAPITULATION) + H3bis (SWEEP) — PRÉ-ENREGISTREMENT ÉCRIT AVANT
TOUT CALCUL (le rapport reprend ce bloc verbatim en tête).

Corpus : 230 events cascade majors (anti_liq.collect_featured +
add_rolling_scores, hold 24h), CVD 1h taker_buy_volume 100 % couvert.
Features EX-ANTE sur les bougies PRÉCÉDANT l'entrée (code identique au
test H2/H3 : scripts/h2_h3_cvd_test.attach_cvd_features — comparabilité
directe avec les hints). Split TRAIN/VAL PAR LE TEMPS 70/30.

H2bis — CAPITULATION (hint post-hoc consigné 27/09 au registre :
MAE 2.48 % tr / 3.10 % va, n=30/12, exp tr −0.9 / va −17.8).
  Flag (ex-ante) : close de la bougie signal (entry−1h) = min des 24
  closes précédentes (nouveau bas 24h) ET pente CVD 6h ex-ante
  (régression du delta cumulé 2×taker_buy−vol sur les 6 bougies
  entry−6h..entry−1h, normalisée par le vol moyen) ≤ p25 des pentes
  des events TRAIN uniquement (p25 figé sur TRAIN, appliqué tel quel
  à VAL).
  Prédiction : MAE (mae_adverse 24h) CROISSANT le long des états
    sain (new_low=0) < nouveau-bas doux (new_low=1, pente>p25)
    < capitulation (new_low=1, pente≤p25),
  tenu en TRAIN ET en VAL (cellules non vides), ET espérance marge de
  la capitulation STRICTEMENT < espérance du reste en VAL.
  Mécanisme : la capitulation précède le squeeze — le rebond frappe le
  short dans les ≤12h (MAE 12h rapporté en descriptif, l'outcome
  primaire reste le MAE 24h du corpus = les chiffres du hint).
  PASS = gradient monotone TRAIN+VAL ET espérance dégradée en VAL.

H3bis — SWEEP (hint post-hoc : MAE 2.66 vs 1.84 tr / 3.00 vs 1.84 va).
  Flag (ex-ante) : low d'une des 6 bougies avant l'entrée < min des 48
  lows précédentes avec volume > 2× sa moyenne 20 bougies (code du
  hint H3, >2× — équivalent ≥2× sur floats non exacts).
  Prédiction : MAE 24h du short plus haut quand sweep=1, en TRAIN ET
  en VAL (gradient binaire no_sweep < sweep≥2×) ET espérance du sweep
  STRICTEMENT < espérance du no-sweep en VAL. Descriptif annoncé
  sous-puissant d'office : gradient par buckets no_sweep < 2-3× <
  3-5× < ≥5× (n=3-4 dans les queues, hint fragile par construction).
  PASS = mêmes critères que H2bis.

Puissance honnête : n par état affiché partout, test binomial exact
deux-côtés (H0 : P(MAE_flag > médiane MAE du reste TRAIN, seuil figé
sur TRAIN) = 0.5), et RAPPEL : les deux hints viennent de buckets
n=12-30 — fragiles par construction.

Si PASS : sizing ×0.75 sur les trades flagués dans la machine 4 flux
(--vol-spike ON) — JAMAIS un gate, la TAILLE seulement (levier 10x /
ligne de mort 9.5 % / règle 0-liq intacts). Critère BLOC STATS vs
baseline officielle $4 004.94 (+3 905 %/an @ DD 24.8 %, pire −10.1 %)
ET vs baseline répliquée mult≡1 (relative, anti-bug) :
  pire mois > pire mois baseline  ET  DD ≤ DD baseline  ET
  ROI ≥ 90 % du ROI baseline (lecture stricte en points, baseline−10
  pts, rapportée aussi).
Garde-fou doctrine : composé-des-mois ≈ final (écart < 0.5 %) sinon BUG.

  .venv/bin/python scripts/capitulation_sweep_test.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from math import comb
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.h2_h3_cvd_test import (  # noqa: E402
    LIQ_MOVE_10X, attach_cvd_features, bloc, build_machine, exp_pct, monotone)
from scripts.portfolio_sim import btc_regime_series  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, funding_hourly_all, monthly_rows, run_stack)

H2B_STATES = ["sain", "nvbas_doux", "capitulation"]
H3B_BUCKETS = ["no_sweep", "sweep_2_3x", "sweep_3_5x", "sweep_ge5x"]
LEV_M = 10

PREREG = [
    "## PRÉ-ENREGISTREMENT (écrit AVANT tout calcul — docstring du script)",
    "",
    "- **H2bis capitulation** : flag ex-ante = close signal (entry−1h) = min",
    "  des 24 closes précédentes ET pente CVD 6h ≤ p25 des pentes TRAIN.",
    "  Prédiction : MAE 24h croissant le long de sain < nv-bas doux <",
    "  capitulation, tenu TRAIN ET VAL, ET espérance capitulation <",
    "  espérance du reste en VAL. Outcome primaire = mae_adverse 24h",
    "  (les chiffres du hint), MAE 12h descriptif (le squeeze vient après).",
    "- **H3bis sweep** : flag ex-ante = low d'une des 6 bougies avant",
    "  l'entrée casse le min 48h avec volume > 2× sa moyenne 20.",
    "  Prédiction : MAE 24h no_sweep < sweep≥2×, TRAIN ET VAL, ET",
    "  espérance sweep < espérance no-sweep en VAL. Buckets 2-3×/3-5×/",
    "  ≥5× descriptifs (queues n=3-4, sous-puissant annoncé).",
    "- **PASS** = gradient monotone en TRAIN ET en VAL + espérance",
    "  dégradée en VAL. Si PASS : sizing ×0.75 sur l'état actif dans la",
    "  machine 4 flux (--vol-spike ON) — JAMAIS un gate. Critère : pire",
    "  mois amélioré ET DD ≤ baseline ET ROI ≥ 90 % du ROI baseline.",
    "- Puissance honnête : n par état, binomial exact vs seuil = médiane",
    "  MAE du reste TRAIN ; hints issus de buckets n=12-30 (fragiles).",
]


def attach_mae12(events: list[dict]) -> None:
    """MAE 12h descriptif : max(high entry..entry+11h) − entrée, %."""
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    px: dict[str, dict[int, float]] = {}
    for s, ot, hi in con.execute(
            "SELECT symbol, open_time, high FROM klines WHERE interval='1h'"):
        px.setdefault(s, {})[int(ot)] = float(hi or 0)
    con.close()
    for e in events:
        ems = int(e["ts_ms"] / 10**6)
        hs = [px.get(e["sym"], {}).get(ems + k * 3600_000) for k in range(12)]
        e["mae_12h"] = ((max(h for h in hs if h is not None) - e["entry"])
                        / e["entry"] * 100
                        if e["entry"] > 0 and any(h is not None for h in hs)
                        else float("nan"))


def capit_state(e, p25: float) -> str | None:
    s = e.get("cvd_slope", float("nan"))
    if not np.isfinite(s) or e.get("new_low", -1) not in (0, 1):
        return None
    if e["new_low"] == 1:
        return "capitulation" if s <= p25 else "nvbas_doux"
    return "sain"


def h3_state(e) -> str | None:
    sw = e.get("sweep", -1)
    if sw == 0:
        return "no_sweep"
    if sw == 1:
        m = e.get("sweep_mult", 0.0)
        if m < 3.0:
            return "sweep_2_3x"
        if m < 5.0:
            return "sweep_3_5x"
        return "sweep_ge5x"
    return None


def binom_two_sided(k: int, n: int) -> float:
    """Binomial exact deux-côtés, H0 p=0.5."""
    if n == 0:
        return float("nan")
    pk = comb(n, k) * 0.5 ** n
    return min(1.0, sum(comb(n, i) * 0.5 ** n for i in range(n + 1)
                        if comb(n, i) * 0.5 ** n <= pk * (1 + 1e-9)))


def state_table(split: list[dict], states: list[str], key, fh) -> list[str]:
    lines = ["| État | n | MAE 24h % | MAE 12h % | Liq @9.5 | WR % | "
             "Espérance marge % |", "|---|---|---|---|---|---|---|"]
    for st in states:
        m = [e for e in split if key(e) == st]
        if not m:
            lines.append(f"| {st} | 0 | — | — | — | — | — |")
            continue
        mae = np.mean([e["mae_adverse"] for e in m])
        m12 = [e["mae_12h"] for e in m if np.isfinite(e["mae_12h"])]
        liq = np.mean([e["mae_adverse"] >= LIQ_MOVE_10X for e in m]) * 100
        wr = np.mean([e["price_ret_short"] > 0 for e in m]) * 100
        exp = float(np.mean([exp_pct(e, fh) for e in m]))
        lines.append(f"| {st} | {len(m)} | {mae:.2f} "
                     f"| {np.mean(m12):.2f} | {liq:.1f} % | {wr:.1f} % "
                     f"| {exp:+.1f} |")
    return lines


def grad(split: list[dict], states: list[str], key) -> list[float]:
    return [float(np.mean([e["mae_adverse"] for e in split if key(e) == st]))
            if any(key(e) == st for e in split) else float("nan")
            for st in states]


def binom_block(flag_ev: list[dict], rest_tr_thr: float) -> str:
    """k = #flag trades avec MAE > seuil (médiane du reste TRAIN)."""
    out = []
    for tag, grp in (("TRAIN", flag_ev[0]), ("VAL", flag_ev[1])):
        k = sum(1 for e in grp if e["mae_adverse"] > rest_tr_thr)
        n = len(grp)
        out.append(f"{tag} {k}/{n} (p={binom_two_sided(k, n):.3f})")
    return " ; ".join(out)


def main() -> int:
    fh = funding_hourly_all()
    regime = btc_regime_series()
    events = collect_featured(regime, "majors")
    add_rolling_scores(events)
    missing = attach_cvd_features(events)
    attach_mae12(events)
    events.sort(key=lambda e: e["ts_ms"])

    # — H2bis : p25 des pentes figé sur TRAIN —
    h2_ev = [e for e in events if np.isfinite(e.get("cvd_slope", float("nan")))
             and e.get("new_low", -1) in (0, 1)]
    k2 = int(len(h2_ev) * 0.7)
    tr2, va2 = h2_ev[:k2], h2_ev[k2:]
    p25 = float(np.quantile([e["cvd_slope"] for e in tr2], 0.25))
    key2 = lambda e: capit_state(e, p25)  # noqa: E731

    # — H3bis : binaire + buckets descriptifs —
    h3_ev = [e for e in events if e.get("sweep", -1) in (0, 1)]
    k3 = int(len(h3_ev) * 0.7)
    tr3, va3 = h3_ev[:k3], h3_ev[k3:]
    key3b = lambda e: ("sweep" if e.get("sweep") == 1 else "no_sweep")  # noqa: E731

    L = [f"# H2bis (capitulation) + H3bis (sweep) — pré-enregistré 27/09",
         f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — corpus "
         f"anti_liq.collect_featured + add_rolling_scores, majors, hold 24h : "
         f"**{len(events)} events** ; CVD 1h manquante : "
         f"{missing if missing else 'aucune (100 % couvert)'}.",
         f"H2bis exploitable {len(h2_ev)} (train {len(tr2)} / val {len(va2)}), "
         f"H3bis exploitable {len(h3_ev)} (train {len(tr3)} / val {len(va3)}) "
         f"— split PAR LE TEMPS 70/30.", ""]
    L += PREREG
    print("\n".join(PREREG))          # pré-enregistrement AVANT les résultats
    L += ["", f"p25 des pentes CVD TRAIN (figé) : **{p25:.4f}** ; "
          f"seuil binomial = médiane MAE du reste TRAIN.", ""]
    print(f"[h2bis] p25 pentes TRAIN = {p25:.4f}")

    # ---------------- H2bis
    tr_g2, va_g2 = grad(tr2, H2B_STATES, key2), grad(va2, H2B_STATES, key2)
    mono2_tr, mono2_va = monotone(tr_g2), monotone(va_g2)
    cap_tr = [e for e in tr2 if key2(e) == "capitulation"]
    cap_va = [e for e in va2 if key2(e) == "capitulation"]
    rest_tr = [e for e in tr2 if key2(e) != "capitulation"]
    rest_va = [e for e in va2 if key2(e) != "capitulation"]
    thr2 = float(np.median([e["mae_adverse"] for e in rest_tr])) if rest_tr \
        else float("nan")
    exp_cap_va = float(np.mean([exp_pct(e, fh) for e in cap_va])) if cap_va \
        else float("nan")
    exp_rest_va = float(np.mean([exp_pct(e, fh) for e in rest_va])) if rest_va \
        else float("nan")
    pass2 = bool(mono2_tr and mono2_va
                 and np.isfinite(exp_cap_va) and exp_cap_va < exp_rest_va)

    L += ["## H2bis — capitulation (nouveau bas × pente CVD ≤ p25 TRAIN)", ""]
    L += ["**TRAIN**", ""]
    L += state_table(tr2, H2B_STATES, key2, fh)
    L += ["", f"Gradient MAE : {['%.2f' % x for x in tr_g2]} — monotone : "
              f"{'OUI' if mono2_tr else 'NON'}", ""]
    L += ["**VAL**", ""]
    L += state_table(va2, H2B_STATES, key2, fh)
    L += ["", f"Gradient MAE : {['%.2f' % x for x in va_g2]} — monotone : "
              f"{'OUI' if mono2_va else 'NON'}", ""]
    if cap_tr and rest_tr:
        L += [f"Capitulation vs reste — TRAIN : MAE "
              f"{np.mean([e['mae_adverse'] for e in cap_tr]):.2f} vs "
              f"{np.mean([e['mae_adverse'] for e in rest_tr]):.2f} %, exp "
              f"{np.mean([exp_pct(e, fh) for e in cap_tr]):+.1f} vs "
              f"{np.mean([exp_pct(e, fh) for e in rest_tr]):+.1f} "
              f"(n {len(cap_tr)} vs {len(rest_tr)}) ; VAL : MAE "
              f"{np.mean([e['mae_adverse'] for e in cap_va]):.2f} vs "
              f"{np.mean([e['mae_adverse'] for e in rest_va]):.2f} %, exp "
              f"{exp_cap_va:+.1f} vs {exp_rest_va:+.1f} "
              f"(n {len(cap_va)} vs {len(rest_va)}).", ""]
    L += [f"Binomial (MAE capitulation > médiane reste TRAIN {thr2:.2f}) : "
          f"{binom_block((cap_tr, cap_va), thr2)}.", ""]
    print(f"[h2bis] grad tr {['%.2f' % x for x in tr_g2]} mono {mono2_tr} | "
          f"va {['%.2f' % x for x in va_g2]} mono {mono2_va} | "
          f"exp va capit {exp_cap_va:+.1f} vs reste {exp_rest_va:+.1f} "
          f"-> {'PASS' if pass2 else 'FAIL'}")

    # ---------------- H3bis
    tr_g3, va_g3 = grad(tr3, ["no_sweep", "sweep"], key3b), \
        grad(va3, ["no_sweep", "sweep"], key3b)
    mono3_tr, mono3_va = monotone(tr_g3), monotone(va_g3)
    sw_tr = [e for e in tr3 if key3b(e) == "sweep"]
    sw_va = [e for e in va3 if key3b(e) == "sweep"]
    nsw_tr = [e for e in tr3 if key3b(e) == "no_sweep"]
    nsw_va = [e for e in va3 if key3b(e) == "no_sweep"]
    thr3 = float(np.median([e["mae_adverse"] for e in nsw_tr])) if nsw_tr \
        else float("nan")
    exp_sw_va = float(np.mean([exp_pct(e, fh) for e in sw_va])) if sw_va \
        else float("nan")
    exp_nsw_va = float(np.mean([exp_pct(e, fh) for e in nsw_va])) if nsw_va \
        else float("nan")
    pass3 = bool(mono3_tr and mono3_va
                 and np.isfinite(exp_sw_va) and exp_sw_va < exp_nsw_va)

    L += ["## H3bis — sweep ≥2× → MAE du short", ""]
    L += ["**TRAIN (binaire)**", ""]
    L += state_table(tr3, ["no_sweep", "sweep"], key3b, fh)
    L += ["", f"Gradient MAE : {['%.2f' % x for x in tr_g3]} — monotone : "
              f"{'OUI' if mono3_tr else 'NON'}", ""]
    L += ["**VAL (binaire)**", ""]
    L += state_table(va3, ["no_sweep", "sweep"], key3b, fh)
    L += ["", f"Gradient MAE : {['%.2f' % x for x in va_g3]} — monotone : "
              f"{'OUI' if mono3_va else 'NON'}", ""]
    L += ["**Buckets descriptifs (annoncés sous-puissants, queues n=3-4)**",
          ""]
    L += state_table(tr3, H3B_BUCKETS, h3_state, fh)
    L += state_table(va3, H3B_BUCKETS, h3_state, fh)
    if sw_tr and nsw_tr:
        L += [f"Sweep vs no-sweep — TRAIN : MAE "
              f"{np.mean([e['mae_adverse'] for e in sw_tr]):.2f} vs "
              f"{np.mean([e['mae_adverse'] for e in nsw_tr]):.2f} %, exp "
              f"{np.mean([exp_pct(e, fh) for e in sw_tr]):+.1f} vs "
              f"{np.mean([exp_pct(e, fh) for e in nsw_tr]):+.1f} "
              f"(n {len(sw_tr)} vs {len(nsw_tr)}) ; VAL : MAE "
              f"{np.mean([e['mae_adverse'] for e in sw_va]):.2f} vs "
              f"{np.mean([e['mae_adverse'] for e in nsw_va]):.2f} %, exp "
              f"{exp_sw_va:+.1f} vs {exp_nsw_va:+.1f} "
              f"(n {len(sw_va)} vs {len(nsw_va)}).", ""]
    L += [f"Binomial (MAE sweep > médiane no-sweep TRAIN {thr3:.2f}) : "
          f"{binom_block((sw_tr, sw_va), thr3)}.", ""]
    print(f"[h3bis] grad tr {['%.2f' % x for x in tr_g3]} mono {mono3_tr} | "
          f"va {['%.2f' % x for x in va_g3]} mono {mono3_va} | "
          f"exp va sweep {exp_sw_va:+.1f} vs no-sweep {exp_nsw_va:+.1f} "
          f"-> {'PASS' if pass3 else 'FAIL'}")

    # ---------------- verdict stat
    if not pass2 and not pass3:
        L += ["## VERDICT : FAIL H2bis ET FAIL H3bis", "",
              "Aucun sizing branché — la machine reste la baseline "
              "(thé-machine 4 flux, $4 004,94). Les deux hints, issus de",
              "buckets n=12-30, ne survivent pas à leur pré-enregistrement :",
              "enterrés CONTEXTE/NUL au registre avec les chiffres ci-dessus.",
              "",
              "**Prochaine action** : inscrire les 2 rows au registre "
              "(20-registre-indicateurs.md) et passer aux hints suivants."]
        (REPORTS / "capitulation-sweep-2026-09-27.md").write_text(
            "\n".join(L) + "\n", encoding="utf-8")
        print(f"[h2b3b] FAIL H2bis (tr {mono2_tr} va {mono2_va}) / "
              f"H3bis (tr {mono3_tr} va {mono3_va})")
        return 0

    # ---------------- PARTIE B : machine 4 flux, sizing ×0.75
    flags = {(e["sym"], e["ts_ms"]):
             (int(key2(e) == "capitulation"), int(e.get("sweep", 0) == 1))
             for e in events}
    all_ev, make_fn, st = build_machine(flag_features=False)
    for e in all_ev:
        e["capit"], e["sweep"] = flags.get((e["sym"], e["ts_ms"]), (0, 0))

    variants: list[tuple[str, object]] = [("baseline (mult ≡ 1.0)",
                                           lambda e: 1.0)]
    if pass2:
        variants.append(("capitulation ×0.75 / reste ×1.0",
                         lambda e: 0.75 if e.get("capit") else 1.0))
    if pass3:
        variants.append(("sweep ×0.75 / reste ×1.0",
                         lambda e: 0.75 if e.get("sweep") else 1.0))
    if pass2 and pass3:
        variants.append(("capit|sweep ×0.75 / reste ×1.0",
                         lambda e: 0.75 if (e.get("capit") or e.get("sweep"))
                         else 1.0))

    n_cap = sum(1 for e in all_ev if e.get("strategy") == "cascade_10x"
                and e.get("capit"))
    n_sw = sum(1 for e in all_ev if e.get("strategy") == "cascade_10x"
               and e.get("sweep"))
    L += ["## PARTIE B — machine 4 flux (--vol-spike ON), sizing ×0.75 "
          "sur l'état actif (JAMAIS un gate)", "",
          f"Trades cascade_10x flagués : capitulation {n_cap} / sweep {n_sw} "
          f"/ {st['n_gated']} gated. Critère par variante : pire mois > "
          f"pire mois baseline ET DD ≤ baseline ET ROI ≥ 90 % du ROI "
          f"baseline (lecture stricte baseline−10 pts rapportée). Levier "
          f"10x intact (ligne de mort 9.5 %, MAE gated "
          f"{st['mae_gated']:.2f} %, règle 0-liq).", ""]
    results = []
    for label, mf in variants:
        res = run_stack(all_ev, CAPITAL, make_fn(mf), st["fh"])
        res["_neg_worst"] = min(x["roi"] for x in
                                monthly_rows(res["trades"], CAPITAL))
        results.append((label, res))
        L += bloc(res, label)
    base = results[0][1]
    roi_b = (base["balance"] / CAPITAL - 1) * 100
    L += [f"**Machine répliquée** : gate AL p66={st['q66']:.2f}, MAE gated "
          f"{st['mae_gated']:.2f} % → levier sûr {st['lev_safe']:.1f}x, "
          f"flux : gated {st['n_gated']} / meme {st['n_meme']} "
          f"({st['lev_meme']}x) / surv {st['n_surv']} / spike {st['n_spike']}.",
          ""]
    best_label, best = None, None
    for label, res in results[1:]:
        roi_v = (res["balance"] / CAPITAL - 1) * 100
        ok = (res["_neg_worst"] > base["_neg_worst"]
              and res["max_dd"] <= base["max_dd"]
              and roi_v >= 0.9 * roi_b)
        ok_pts = roi_v >= roi_b - 10.0
        L.append(f"- {label} : {'PASS' if ok else 'fail'} "
                 f"(${res['balance']:,.2f}, {roi_v:+.0f} %/an, DD "
                 f"{res['max_dd']:.1f} %, pire mois {res['_neg_worst']:+.1f} % "
                 f"[base {base['_neg_worst']:+.1f}], {res['_neg']} mois nég) "
                 f"— lecture stricte −10 pts : {'OK' if ok_pts else 'NON'}")
        if ok and (best is None or res["balance"] > best["balance"]):
            best_label, best = label, res
    L += ["", f"## VERDICT MACHINE : "
              f"{'PASS — ' + best_label + ' adopté en CANDIDAT' if best else 'FAIL — rejeté, la machine reste la baseline'}",
          "",
          "Verdict RELATIF (composé-des-mois = garde-fou, pas le final nu).",
          "Baseline officielle 27/09 : $4 004,94 (+3 905 %/an, DD 24,8 %,",
          "0 liq, record +90,8 %, pire −10,1 %).",
          "",
          "**Prochaine action** : si PASS → re-catégoriser l'indicateur au "
          "registre (CANDIDAT) + câbler le mapping au paper forward ; "
          "sinon CONTEXTE/NUL enterré avec les chiffres."]
    (REPORTS / "capitulation-sweep-2026-09-27.md").write_text(
        "\n".join(L) + "\n", encoding="utf-8")
    for label, res in results:
        print(f"[h2b3b] {label}: ${res['balance']:,.2f} DD "
              f"{res['max_dd']:.1f} % liq {res['n_liq']} "
              f"pire {res.get('_neg_worst', float('nan')):+.1f}")
    print(f"[h2b3b] verdict machine : {'PASS ' + best_label if best else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
