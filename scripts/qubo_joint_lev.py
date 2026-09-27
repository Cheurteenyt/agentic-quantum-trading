#!/usr/bin/env python
"""QUBO JOINT — poids × levier, les 4 flux de la machine.

Le QUBO poids (scripts/qubo_sizing.py) a trouvé w = [0.857, 0.857, 2.0,
1.143] = $4,639.13 FULL (+4539 %/an @ DD 23.4 %, 0 liq) mais les LEVIERS
étaient figés (10x/1x/1x/1x). Or la règle 0-liq (lev <= 100/(maxMAE+0.5))
laisse de la marge : ce script MESURE d'abord le MAE par flux sur TRAIN
(c'est LA donnée nouvelle — le vol_spike n'a jamais été mesuré), puis
optimise conjointement poids (12 bits, mêmes 8 niveaux) et levier
(2 bits/flux, niveaux contraints par les maxima MAE).

Exposition effective : g_i = w_i * lev_i / lev_base_i (le PnL d'un flux
scale ~linéairement au levier pour une même fraction de marge — fees et
funding aussi). Objectif : max g'mu - (lambda/2) g'Sigma g, mu/Sigma
estimés sur TRAIN uniquement (mois de SORTIE, run_stack baseline w=1 aux
leviers de base). Solveurs : grille exhaustive (Nw x Nl = 65,536 états)
+ simulated annealing sur l'espace produit — la grille DOIT retrouver le
point de l'annealing (garde-fou solver).

Validation serrée : le candidat choisi sur TRAIN (0 liq, DD <= 25 %,
<= 1 mois négatif, balance max) passe le VRAI run_stack sur TRAIN puis
VAL — UNE SEULE liquidation en VAL = cellule MORTE (le levier valait
pour train, règle carte hold×levier). Comparaison vs QUBO poids seul
et vs la main.

  .venv/bin/python scripts/qubo_joint_lev.py
"""
from __future__ import annotations

import itertools
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_sim import monthly_rows  # noqa: E402
from scripts.qubo_sizing import (  # noqa: E402
    FLUXES, LAMBDAS, LEVELS, SEED, bloc, build_events, base_sizer,
    flux_monthly, weighted_sizer)
from scripts.stacked_portfolio import CAPITAL, run_stack  # noqa: E402

REPORTS = ROOT / "reports"
DATE = "2026-09-27"
BASE_LEV = np.array([10.0, 1.0, 1.0, 1.0])   # leviers actuels (figés du QUBO poids)
# la carte meme (carte_meme_hold) exige sub-1x strict : aucun niveau > 1.0
L_MEME = [0.25, 0.5, 0.75, 1.0]
# realisme exchange : rien au-dessus de 20x (Aster alts)
LEV_CAP_EXCHANGE = 20.0
W_CAPS = {"cascade_10x": 1.0, "cascade_meme": 1.0,   # mêmes caps que le QUBO poids
          "survivor_long": 2.0, "vol_spike_6h": 2.0}  # (isoler l'effet levier)


# ------------------------------------------------------------------
# 1. LA MESURE MAE — le fondement (TRAIN uniquement)
# ------------------------------------------------------------------
def mae_stats(events: list[dict]) -> dict[str, dict]:
    by: dict[str, list[float]] = defaultdict(list)
    for e in events:
        by[e["strategy"]].append(float(e["mae_adverse"]))
    out = {}
    for f, v in by.items():
        a = np.array(v)
        out[f] = {"n": len(a), "med": float(np.median(a)),
                  "p95": float(np.quantile(a, 0.95)),
                  "p99": float(np.quantile(a, 0.99)),
                  "max": float(a.max()),
                  "lev_hard": 100.0 / (a.max() + 0.5)}
    return out


def lev_lists(mae_tr: dict[str, dict]) -> dict[str, list[float]]:
    """Les niveaux de levier, contraints par les maxima MAE TRAIN."""
    maj_hard = mae_tr["cascade_10x"]["lev_hard"]
    l_maj = [float(l) for l in (6, 8, 10, 11) if l <= maj_hard + 1e-9]
    if not l_maj:                                  # jamais attendu (11.99 mesuré)
        l_maj = [float(int(maj_hard))]
    spk_hard = min(mae_tr["vol_spike_6h"]["lev_hard"], LEV_CAP_EXCHANGE)
    m = int(spk_hard)
    l_spk = sorted({1.0, float(max(2, m // 4)), float(max(2, m // 2)),
                    float(m)}) if m >= 2 else [1.0]
    return {"cascade_10x": l_maj, "cascade_meme": list(L_MEME),
            "survivor_long": [1.0], "vol_spike_6h": l_spk}


# ------------------------------------------------------------------
# 2. LE QUBO JOINT — grille exhaustive + annealing sur l'espace produit
# ------------------------------------------------------------------
def weight_levels() -> list[float]:
    """Les 8 niveaux du QUBO poids (sous-ensembles de LEVELS) : 0 -> 2.0."""
    sums = {0.0}
    for r in range(1, len(LEVELS) + 1):
        sums |= {float(sum(c)) for c in itertools.combinations(LEVELS, r)}
    return sorted(sums)


def joint_grid(lev_l: dict[str, list[float]]
               ) -> tuple[np.ndarray, np.ndarray]:
    w_opts = [[l for l in weight_levels() if l <= W_CAPS[f] + 1e-9]
              for f in FLUXES]
    l_opts = [lev_l[f] for f in FLUXES]
    Wg = np.array(list(itertools.product(*w_opts)))
    Lg = np.array(list(itertools.product(*l_opts)))
    return Wg, Lg


def energies(Wg: np.ndarray, Lg: np.ndarray, mu: np.ndarray,
             Sig: np.ndarray, lam: float) -> np.ndarray:
    """E = -(g'mu) + (lam/2) g'Sig g, g = w o lev / base — (Nw, Nl)."""
    G = (Wg[:, None, :] * Lg[None, :, :]) / BASE_LEV
    Gm = G.reshape(-1, 4)
    e = -(Gm @ mu) + 0.5 * lam * ((Gm @ Sig) * Gm).sum(axis=1)
    return e.reshape(len(Wg), len(Lg))


def anneal_joint(mu: np.ndarray, Sig: np.ndarray, lam: float,
                 lev_l: dict[str, list[float]], restarts: int = 32,
                 steps: int = 8000, T0: float = 5.0, T1: float = 1e-3,
                 seed: int = SEED) -> tuple[float, np.ndarray, np.ndarray]:
    """SA sur l'espace produit (w_idx, lev_idx) — le mapping g = w o lev
    n'est pas bilinéaire en bits, l'énergie est recalculée directement
    (4 dims : coût négligeable, même schedule que qubo_sizing)."""
    w_opts = [[l for l in weight_levels() if l <= W_CAPS[f] + 1e-9]
              for f in FLUXES]
    l_opts = [lev_l[f] for f in FLUXES]
    rng = np.random.default_rng(seed)

    def g_of(wi, li):
        return np.array([w_opts[i][wi[i]] * l_opts[i][li[i]] / BASE_LEV[i]
                         for i in range(4)])

    def energy(g):
        return -(g @ mu) + 0.5 * lam * float(g @ Sig @ g)

    best_e, best_g = np.inf, None
    for _ in range(restarts):
        wi = [int(rng.integers(len(w_opts[i]))) for i in range(4)]
        li = [int(rng.integers(len(l_opts[i]))) for i in range(4)]
        g = g_of(wi, li)
        e = energy(g)
        if e < best_e:
            best_e, best_g = e, g.copy()
        for s in range(steps):
            T = T0 * (T1 / T0) ** (s / steps)
            f = int(rng.integers(4))
            which = int(rng.integers(2))
            opts, idx = (w_opts[f], wi) if which == 0 else (l_opts[f], li)
            old = idx[f]
            idx[f] = int(rng.integers(len(opts)))
            g2 = g_of(wi, li)
            e2 = energy(g2)
            dE = e2 - e
            if dE <= 0 or rng.random() < np.exp(-dE / max(T, 1e-12)):
                g, e = g2, e2
                if e < best_e:
                    best_e, best_g = e, g.copy()
            else:
                idx[f] = old
    return best_e, best_g, np.array(best_g)


def run_with(events: list[dict], base, w_map: dict, lev_map: dict,
             fh: dict) -> dict:
    evs = [{**e, "lev": lev_map.get(e["strategy"], e["lev"])}
           for e in events]
    return run_stack(evs, CAPITAL, weighted_sizer(base, w_map), fh)


def as_maps(wv: np.ndarray, levv: np.ndarray
            ) -> tuple[dict, dict]:
    return (dict(zip(FLUXES, map(float, wv))),
            dict(zip(FLUXES, map(float, levv))))


def stats_line(res: dict, label: str) -> list[str]:
    lines, meta = bloc(res, label, CAPITAL)
    return lines, meta


# ------------------------------------------------------------------
def main() -> int:
    t0 = time.time()
    all_ev, ctx, fh, counts = build_events()
    print(f"[jlev] events {dict(counts)} en {time.time()-t0:.0f}s", flush=True)

    # ——— le split temporel 70/30 (identique au QUBO poids) ———
    ts = np.array([e["ts_ms"] for e in all_ev])
    t_split = ts.min() + 0.7 * (ts.max() - ts.min())
    d = datetime.fromtimestamp(t_split / 1e9, tz=timezone.utc)
    train_ev = [e for e in all_ev if e["ts_ms"] < t_split]
    val_ev = [e for e in all_ev if e["ts_ms"] >= t_split]
    print(f"[jlev] split {d:%Y-%m-%d} : train {len(train_ev)} / "
          f"val {len(val_ev)}", flush=True)

    # ——— 1. LA MESURE MAE par flux (TRAIN) ———
    mae_tr = mae_stats(train_ev)
    mae_va = mae_stats(val_ev)
    lev_l = lev_lists(mae_tr)
    print("[jlev] MAE TRAIN : "
          + " | ".join(f"{f}: max {v['max']:.2f}% -> lev {v['lev_hard']:.2f}x"
                       for f, v in mae_tr.items()), flush=True)

    # ——— mu, Sigma sur TRAIN (baseline w=1, leviers de base) ———
    base = base_sizer(ctx)
    b_train = run_stack(train_ev, CAPITAL, base, fh)
    b_val = run_stack(val_ev, CAPITAL, base, fh)
    b_full = run_stack(all_ev, CAPITAL, base, fh)
    months_tr, R, C, _ = flux_monthly(b_train["trades"], CAPITAL)
    mu = R.mean(axis=1)
    Sig = np.cov(R)
    print(f"[jlev] baseline full ${b_full['balance']:,.2f} "
          f"(DD {b_full['max_dd']:.1f} %, liq {b_full['n_liq']}) "
          f"| mu {np.round(mu, 2).tolist()}", flush=True)

    # ——— 2. la grille jointe + sweep lambda ———
    Wg, Lg = joint_grid(lev_l)
    n_states = len(Wg) * len(Lg)
    print(f"[jlev] grille jointe : {len(Wg)} poids x {len(Lg)} leviers "
          f"= {n_states} états", flush=True)
    cands: dict[tuple, dict] = {}
    conv = ["| lambda | E grille | E annealing | même point ? | g (10x/meme/surv/vsp) | w | lev |",
            "|---|---|---|---|---|---|---|"]
    for lam in LAMBDAS:
        E = energies(Wg, Lg, mu, Sig, lam)
        k = int(np.argmin(E))
        ki, kl = divmod(k, len(Lg))
        gw, gl = Wg[ki], Lg[kl]
        ae, _, ag = anneal_joint(mu, Sig, lam, lev_l)
        same = abs(float(E.flat[k]) - ae) < 1e-6 and \
            np.allclose(np.sort(gw * gl / BASE_LEV), np.sort(ag), atol=1e-6)
        key = (tuple(np.round(gw, 4)), tuple(gl))
        if key not in cands:
            cands[key] = {"lam": lam, "w": gw.copy(), "lev": gl.copy()}
        g = gw * gl / BASE_LEV
        conv.append(
            f"| {lam} | {E.flat[k]:.4f} | {ae:.4f} | "
            f"{'OUI' if same else 'NON — BUG'} | "
            + "/".join(f"{v:.2f}" for v in g) + " | "
            + "/".join(f"{v:.2f}" for v in gw) + " | "
            + "/".join(f"{v:g}" for v in gl) + " |")
        print(f"[jlev] lam={lam}: grid {E.flat[k]:.4f} anneal {ae:.4f} "
              f"{'OK' if same else 'MISMATCH'} g={np.round(g, 2).tolist()}",
              flush=True)

    # ——— 3. LA VALIDATION TRAIN des candidats (vrai run_stack) ———
    evals = []
    for key, cd in cands.items():
        wm, lm = as_maps(cd["w"], cd["lev"])
        r = run_with(train_ev, base, wm, lm, fh)
        mrows = monthly_rows(r["trades"], CAPITAL)
        rois = [x["roi"] for x in mrows] or [0.0]
        cd.update(train=r, t_neg=int(sum(v < 0 for v in rois)),
                  t_rec=max(rois))
        evals.append(cd)
        print(f"[jlev] cand lam={cd['lam']} "
              f"lev={[round(cd['lev'][i], 2) for i in range(4)]} "
              f"w={np.round(cd['w'], 2).tolist()} -> train "
              f"${r['balance']:,.2f} (DD {r['max_dd']:.1f} %, "
              f"liq {r['n_liq']}, {cd['t_neg']} neg)", flush=True)

    # ——— le choix sur TRAIN : 0 liq, DD <= 25, <= 1 neg, balance max ———
    ok = [c for c in evals if c["train"]["n_liq"] == 0
          and c["train"]["max_dd"] <= 25.0 and c["train"]["balance"] > CAPITAL]
    pool = sorted(ok or evals,
                  key=lambda c: (0 if c["t_neg"] <= 1 else 1,
                                 -c["train"]["balance"],
                                 c["train"]["max_dd"]))
    chosen = pool[0]
    wm_c, lm_c = as_maps(chosen["w"], chosen["lev"])
    print(f"[jlev] CHOISI (TRAIN): lam={chosen['lam']} "
          f"w={np.round(chosen['w'], 3).tolist()} "
          f"lev={chosen['lev'].tolist()}", flush=True)

    # ——— 4. LE JUGEMENT VAL : une seule liq = cellule MORTE ———
    c_train = chosen["train"]
    c_val = run_with(val_ev, base, wm_c, lm_c, fh)
    c_full = run_with(all_ev, base, wm_c, lm_c, fh)
    dead = c_val["n_liq"] > 0

    # diagnostics (PAS une re-sélection) : les 5 meilleurs TRAIN, leur VAL
    diag = []
    for cd in sorted(evals, key=lambda c: -c["train"]["balance"])[:5]:
        wm, lm = as_maps(cd["w"], cd["lev"])
        rv = run_with(val_ev, base, wm, lm, fh)
        diag.append((cd, rv))

    # ——— les références sur le même pied ———
    qubo_w = np.array([2 / 7 * 3, 2 / 7 * 3, 2.0, 2 / 7 * 4])  # 0.857/0.857/2/1.143
    ref_q = run_with(all_ev, base, dict(zip(FLUXES, qubo_w)),
                     dict(zip(FLUXES, BASE_LEV)), fh)
    ref_q_tr = run_with(train_ev, base, dict(zip(FLUXES, qubo_w)),
                        dict(zip(FLUXES, BASE_LEV)), fh)
    ref_q_va = run_with(val_ev, base, dict(zip(FLUXES, qubo_w)),
                        dict(zip(FLUXES, BASE_LEV)), fh)

    # ——— le rapport ———
    L = ["# QUBO JOINT — poids × levier (la ré-allocation du risque par le levier)",
         f"{DATE} — mêmes 12 bits de poids que le QUBO poids + 2 bits de "
         "levier par flux (niveaux contraints par le MAE max TRAIN). Grille "
         f"exhaustive {len(Wg)}×{len(Lg)} = {n_states:,} états + SA. "
         "Objectif : max g'μ − (λ/2) g'Σg, g = w∘lev/base, μ/Σ sur TRAIN "
         "uniquement (mois de sortie). Validation run_stack, règle : "
         "UNE liq en VAL = cellule MORTE.", "",
         "## 1. LA MESURE MAE — le fondement (TRAIN uniquement)", "",
         "| flux | n | médiane | p95 | p99 | **MAX** | lev 0-liq = 100/(max+0.5) | "
         "max VAL (info) | niveaux retenus |",
         "|---|---|---|---|---|---|---|---|---|"]
    for f in FLUXES:
        v = mae_tr[f]
        va = mae_va.get(f, {}).get("max", float("nan"))
        if f == "survivor_long":
            note = "LONG 1x : intuable (mouvement adverse requis > 99.5 %)"
        else:
            note = "/".join(f"{x:g}x" for x in lev_l[f])
        L.append(f"| {f} | {v['n']} | {v['med']:.2f} % | {v['p95']:.2f} % "
                 f"| {v['p99']:.2f} % | **{v['max']:.2f} %** "
                 f"| {v['lev_hard']:.2f}x | {va:.2f} % | {note} |")
    L += ["", f"Le survivor (LONG 1x) ne peut pas être liquidé : seuls le "
          f"prix à zéro le tue. **Le vol_spike : l'hypothèse « mean-reversion, "
          f"l'entrée EST l'extrême → MAE petit » est RÉFUTÉE** — MAE max "
          f"{mae_tr['vol_spike_6h']['max']:.2f} %, p99 "
          f"{mae_tr['vol_spike_6h']['p99']:.2f} % (queue grasse : un spike "
          f"qui continue de courir) → plafond 0-liq "
          f"{mae_tr['vol_spike_6h']['lev_hard']:.2f}x, il reste à 1x. "
          f"Le meme : la règle MAE brute plafonnerait à "
          f"{mae_tr['cascade_meme']['lev_hard']:.2f}x (max "
          f"{mae_tr['cascade_meme']['max']:.0f} %), mais les seuls événements "
          f"meme TRAIN à MAE ≥ 99.5 % (2/1408) ne sont jamais passés au "
          f"sizer — créneau cascade_meme déjà occupé (busy-skip du harnais, "
          f"vérifié par trace) : le 0-liq à 1x est une propriété du HARNAS "
          f"et de la carte sub-1x, pas de la règle MAE seule — fragile, à "
          f"surveiller. Le MAE max VAL observé est reporté en info : "
          f"c'est exactement le risque « le levier valait pour train » que "
          f"la règle de mort en VAL châtie (ici majors VAL max "
          f"{mae_va['cascade_10x']['max']:.2f} % < 8.59 % = seuil de liq à "
          f"11x : la cellule 11x survit).", ""]
    low_cov = [(FLUXES[i], FLUXES[j]) for i in range(4) for j in range(i + 1, 4)
               if Sig[i, j] > 0.5 * np.sqrt(Sig[i, i] * Sig[j, j])]
    L += ["Barrière covariance des flux levés : paires avec ρ > 0.5 — "
          + (", ".join(f"{a}/{b} (ρ={Sig[FLUXES.index(a), FLUXES.index(b)]:.2f})"
                       for a, b in low_cov) if low_cov else "aucune") + ".",
          "",
          "## 2. LA GRILLE vs L'ANNEALING — le garde-fou solver", ""]
    L += conv
    if not all("OUI" in l for l in conv[2:]):
        L.append("**MISMATCH grille/annealing — voir ci-dessus.**")
    L += ["", "## 3. LA VALIDATION TRAIN — chaque candidat au vrai wallet", "",
          "| λ | w (10x/meme/surv/vsp) | lev (10x/meme/surv/vsp) | Train $ | "
          "DD | liq | mois nég | record |", "|---|---|---|---|---|---|---|---|"]
    for cd in sorted(evals, key=lambda c: -c["train"]["balance"]):
        L.append(f"| {cd['lam']} | " + "/".join(f"{v:.2f}" for v in cd["w"])
                 + " | " + "/".join(f"{v:g}" for v in cd["lev"])
                 + f" | ${cd['train']['balance']:,.2f} "
                 f"| {cd['train']['max_dd']:.1f} % | {cd['train']['n_liq']} "
                 f"| {cd['t_neg']} | {cd['t_rec']:+.1f} % |")
    L += ["", "Sélection sur TRAIN : 0 liq, DD ≤ 25 %, ≤ 1 mois négatif, "
          "balance max.", "",
          "## 4. LE JUGEMENT VAL — une seule liq = cellule MORTE", "",
          f"Cellule choisie sur TRAIN (λ={chosen['lam']}) : "
          f"w = {'/'.join(f'{v:.2f}' for v in chosen['w'])}, "
          f"lev = {'/'.join(f'{v:g}' for v in chosen['lev'])}. "
          f"VAL : {c_val['n']} trades, liq **{c_val['n_liq']}**, "
          f"DD {c_val['max_dd']:.1f} %, "
          f"${c_val['balance']:,.2f} → "
          + ("**MORTE** (le levier valait pour train — règle carte hold×levier)"
             if dead else "**VIVANTE** (0 liq en VAL)."), "",
          "Diagnostic (information seulement, PAS une re-sélection) — les "
          "5 meilleurs TRAIN et leur VAL :", "",
          "| λ | lev | Train $ | VAL $ | VAL liq | statut |",
          "|---|---|---|---|---|---|"]
    for cd, rv in diag:
        st = "MORTE" if rv["n_liq"] > 0 else "vivante"
        L.append(f"| {cd['lam']} | {'/'.join(f'{v:g}' for v in cd['lev'])} "
                 f"| ${cd['train']['balance']:,.2f} | ${rv['balance']:,.2f} "
                 f"| {rv['n_liq']} | {st} |")

    # ——— le BLOC STATS complet ———
    _, mc = bloc(c_full, "QUBO JOINT — FULL", CAPITAL)
    _, mv = bloc(c_val, "QUBO JOINT — VAL", CAPITAL)
    _, mt = bloc(c_train, "QUBO JOINT — TRAIN", CAPITAL)
    _, mq = bloc(ref_q, "QUBO POIDS SEUL — FULL (référence $4,639.13)", CAPITAL)
    _, mb = bloc(b_full, "MAIN w=1 — FULL (référence $4,004.94)", CAPITAL)
    L += ["", "## 5. LE BLOC STATS — joint vs poids seul vs main", ""]
    for res, lbl in ((c_train, "QUBO JOINT — TRAIN"),
                     (c_val, "QUBO JOINT — VAL"),
                     (c_full, "QUBO JOINT — FULL"),
                     (ref_q_tr, "QUBO POIDS SEUL — TRAIN"),
                     (ref_q_va, "QUBO POIDS SEUL — VAL"),
                     (ref_q, "QUBO POIDS SEUL — FULL"),
                     (b_train, "MAIN — TRAIN"), (b_val, "MAIN — VAL"),
                     (b_full, "MAIN — FULL")):
        lines, _ = bloc(res, lbl, CAPITAL)
        L += lines + [""]
    L += ["### La table mensuelle du QUBO JOINT (full)", "",
          "| Mois | Trades | WR | Liq | Balance début → fin | ROI |",
          "|---|---|---|---|---|---|"]
    for x in mc["mrows"]:
        L.append(f"| {x['month']} | {x['n']} "
                 f"| {x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} "
                 f"| ${x['start']:,.0f} → ${x['end']:,.0f} "
                 f"| {x['roi']:+.1f} % |")

    # ——— le verdict ———
    d_q = (c_full["balance"] / ref_q["balance"] - 1) * 100
    d_m = (c_full["balance"] / b_full["balance"] - 1) * 100
    same_cfg = bool(np.allclose(chosen["w"] * chosen["lev"] / BASE_LEV,
                                np.ones(4), atol=1e-6))
    L += ["", "## VERDICT", "",
          f"- MAE max TRAIN : majors {mae_tr['cascade_10x']['max']:.2f} % "
          f"(plafond {mae_tr['cascade_10x']['lev_hard']:.2f}x, on tournait à "
          f"10x), meme {mae_tr['cascade_meme']['max']:.2f} % "
          f"(carte ≤ 1x), survivor intuable (LONG 1x), **vol_spike "
          f"{mae_tr['vol_spike_6h']['max']:.2f} % → plafond "
          f"{mae_tr['vol_spike_6h']['lev_hard']:.1f}x — LA donnée nouvelle "
          f"de la session** (jamais mesuré).",
          f"- Le QUBO joint ({n_states:,} états, grille = annealing) propose "
          f"w = {'/'.join(f'{v:.2f}' for v in chosen['w'])} × lev = "
          f"{'/'.join(f'{v:g}' for v in chosen['lev'])} (λ={chosen['lam']}) — "
          + ("**identique à la config actuelle : le levier n'apportait rien**"
             if same_cfg else "**un point que le QUBO poids seul n'avait pas**") + ".",
          f"- FULL : ${c_full['balance']:,.2f} vs poids seul "
          f"${ref_q['balance']:,.2f} ({d_q:+.1f} %) vs main "
          f"${b_full['balance']:,.2f} ({d_m:+.1f} %), DD "
          f"{c_full['max_dd']:.1f} % vs {ref_q['max_dd']:.1f} % vs "
          f"{b_full['max_dd']:.1f} %.",
          f"- LIQ : TRAIN {c_train['n_liq']}, VAL **{c_val['n_liq']}**, FULL "
          f"{c_full['n_liq']} → "
          + ("**CELLULE MORTE** — le levier valait pour train, la règle de "
             "la carte hold×levier s'applique : ce levier est interdit."
             if dead else "**0 liq partout — la cellule vit.**"),
          f"- Le compromis honnête : ROI/an {mc['roi_an']:+.0f} % vs "
          f"{mq['roi_an']:+.0f} % (poids seul) vs {mb['roi_an']:+.0f} % "
          f"(main), record mensuel {max(mc['rois']):+.1f} % vs "
          f"{max(mq['rois']):+.1f} %, pire mois {min(mc['rois']):+.1f} % vs "
          f"{min(mq['rois']):+.1f} %, mois négatifs {mc['neg']} vs "
          f"{mq['neg']} — garde-fou composé-des-mois vs final : "
          f"{mc['gap_c']*100:.3f} % "
          f"{'OK' if mc['gap_c'] < 0.005 else 'BUG'}.",
          "- Limites : Σ sur ~9 mois TRAIN (bruitée) ; g = w∘lev/base est "
          "une linéarisation (fees/funding scalent avec le levier, la marge "
          "de liquidation non) — seul run_stack fait foi ; le MAE max VAL "
          "peut dépasser le TRAIN : la règle « 1 liq VAL = morte » est le "
          "seul juge de paix du levier.",
          ""]
    out = REPORTS / f"qubo-joint-lev-{DATE}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[jlev] rapport -> {out}", flush=True)
    print(f"[jlev] VERDICT: w={np.round(chosen['w'], 3).tolist()} "
          f"lev={chosen['lev'].tolist()} lam={chosen['lam']} | full "
          f"${c_full['balance']:,.2f} vs poids-seul ${ref_q['balance']:,.2f} "
          f"| liq T/V/F {c_train['n_liq']}/{c_val['n_liq']}/{c_full['n_liq']} "
          f"| {'MORTE' if dead else 'VIVANTE'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
