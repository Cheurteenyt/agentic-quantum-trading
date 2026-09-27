#!/usr/bin/env python
"""QUBO PAR SYMBOLE — la granularité dans le flux majors (6 majeures).

Le QUBO joint (scripts/qubo_joint_lev.py) = $5,181.86 FULL (+5082 %/an,
DD 23.3 %, 0 liq) avec les 6 majeures (BTC/ETH/SOL/XRP/BNB/DOGE) traitées
À L'IDENTIQUE : w=0.857 uniforme, lev 11 — sauf le bonus rank-BAS ×1.5 du
sizer officiel (fund_rank ≤ 0.33, WR 81 % au tercile post-hoc n=21).
Couche suivante : le poids PAR SYMBOLE.

Discrétisation (même méthode que qubo_sizing/qubo_joint_lev) :
  rel_i = (1.5/3)·Σ_j 2^j·x_ij,  m=2 bits/symbole, K=3
  → rel ∈ {0, 0.5, 1.0, 1.5} × le poids du flux (12 bits)
  + 2 bits de rang r ∈ {0, 0.5, 1.0, 1.5} — le bonus rank-BAS : r=1.5 =
    le ×1.5 officiel, r=1.0 = pas de bonus, r=0 = les rank-BAS sautés.
14 bits = 16,384 états → grille exhaustive + annealing (garde-fou solver).

Objectif : max Σ rel_i·μ_i(r) − (λ/2)·rel'Σ(r)rel — μ/Σ PAR SYMBOLE des PnL
mensuels TRAIN (mois de SORTIE, run_stack baseline officiel w=1, lev de
base), décomposés rank-BAS (L) / autre (O) : M_i(ρ) = O_i + ρ·L_i, ρ=r/1.5.

Plafonds 0-liq par symbole : le MAE max TRAIN mesuré PAR symbole (la donnée
— le 7.66 % global majors masque les dispersions), lev_hard_sym =
100/(max+0.5) ; un symbole dont lev_hard < 11 (la ligne de mort du flux à
11x = 8.59 %) ne peut pas être surpondéré (barrière rel_i ≤ 1).

Validation : les (rel, r) choisis sur TRAIN passent le VRAI run_stack
TRAIN/VAL/FULL avec la config joint (flux 0.857, lev 11/1/1/1). Calibration
ABSOLU : (rel=1, r=1.5) doit reproduire la cellule joint. Honnêteté :
~230 événements / 6 symboles ≈ 38/symbole, ~10 mois TRAIN → covariance 6×6
BRUYANTE ; la barre de PASS est haute : battre le flux uniforme sur ROI/an
SANS dégrader DD/record/mois négatifs, 0 liq en VAL, composé ~0.

  .venv/bin/python scripts/qubo_per_symbol.py
"""
from __future__ import annotations

import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_sim import MAJORS, monthly_rows  # noqa: E402
from scripts.qubo_sizing import (  # noqa: E402
    K_ATT, LAMBDAS, SEED, base_sizer, bloc, build_events)
from scripts.stacked_portfolio import CAPITAL, run_stack  # noqa: E402

REPORTS = ROOT / "reports"
DATE = "2026-09-27"

# la cellule JOINT validée ($5,181.86 FULL, +5082 %/an, DD 23.3 %, 0 liq)
JOINT_W = {"cascade_10x": 6 / 7, "cascade_meme": 6 / 7,
           "survivor_long": 2.0, "vol_spike_6h": 6 / 7}
JOINT_LEV = {"cascade_10x": 11, "cascade_meme": 1,
             "survivor_long": 1, "vol_spike_6h": 1}
FLOW_W = JOINT_W["cascade_10x"]          # 0.857 — le poids du flux majors

M_BITS = 2                                # bits par symbole
K_DISC = 2 ** M_BITS - 1                  # 3
LEVELS = np.array([1.5 / K_DISC * 2 ** j for j in range(M_BITS)])  # [.5, 1]
R_VALUES = [0.0, 0.5, 1.0, 1.5]           # le multiplicateur rank-BAS
LOW_THR = 0.33                            # rank-BAS = fund_rank ≤ 0.33
LIQ_MOVE_11 = 100.0 / 11 - 0.5            # 8.591 % — la mort à 11x
NS = len(MAJORS)
SHORT = {s: s.replace("USDT", "") for s in MAJORS}


# ------------------------------------------------------------------
# les sizers — la branche majors du sizer OFFICIEL, bonus rank ×r
# ------------------------------------------------------------------
def majors_sizer(ctx: dict, r: float, rank_mode: str = "bas"):
    """Le sizing majors officiel (vol-inverse × K_ATT) avec le bonus rank
    ×r au lieu du ×1.5 figé. r=1.5 ⇒ IDENTIQUE à base_sizer (auto-test)."""
    med = ctx["med_majors"]

    def fn(e, st=None):
        s0 = min(max(0.24 * K_ATT * (e["atr_pct"] / med), 0.08 * K_ATT),
                 0.40 * K_ATT)
        fr = e.get("fund_rank", float("nan"))
        if not np.isfinite(fr):
            return s0
        hit = (fr <= LOW_THR) if rank_mode == "bas" else (fr >= 2 / 3)
        if hit:
            return min(s0 * r, 0.50 * K_ATT)
        return s0
    return fn


def full_sizer(ctx: dict, rel: dict[str, float], r: float,
               rank_mode: str = "bas"):
    """Flux majors : poids du flux × poids relatif du symbole × sizer(r).
    Les 3 autres flux : poids joint × sizer officiel (inchangé)."""
    maj = majors_sizer(ctx, r, rank_mode)
    base = base_sizer(ctx)

    def fn(e, st=None):
        if e.get("strategy") == "cascade_10x":
            return FLOW_W * rel.get(e["sym"], 1.0) * maj(e, st)
        return JOINT_W[e["strategy"]] * base(e, st)
    return fn


def run_with(events: list[dict], ctx: dict, rel: dict[str, float], r: float,
             fh: dict, rank_mode: str = "bas") -> dict:
    evs = [{**e, "lev": JOINT_LEV.get(e["strategy"], e["lev"])}
           for e in events]
    return run_stack(evs, CAPITAL, full_sizer(ctx, rel, r, rank_mode), fh)


def self_test_sizer(ctx: dict, events: list[dict]) -> None:
    """majors_sizer(r=1.5) doit être EXACTEMENT la branche de base_sizer."""
    maj, base = majors_sizer(ctx, 1.5), base_sizer(ctx)
    for e in [x for x in events if x["strategy"] == "cascade_10x"][:300]:
        assert abs(maj(e) - base(e)) < 1e-12, "BUG sizer majors r=1.5"


# ------------------------------------------------------------------
# LA DONNÉE — MAE par symbole (les plafonds 0-liq) et stats rank-BAS
# ------------------------------------------------------------------
def mae_by_symbol(events: list[dict]) -> dict[str, dict]:
    by: dict[str, list[float]] = defaultdict(list)
    for e in events:
        if e["strategy"] == "cascade_10x":
            by[e["sym"]].append(float(e["mae_adverse"]))
    out = {}
    for s, v in by.items():
        a = np.array(v)
        out[s] = {"n": len(a), "med": float(np.median(a)),
                  "p95": float(np.quantile(a, 0.95)),
                  "p99": float(np.quantile(a, 0.99)),
                  "max": float(a.max()),
                  "lev_hard": 100.0 / (a.max() + 0.5)}
    return out


def low_flag_map(events: list[dict]) -> dict[tuple, bool]:
    """(sym, seconde d'entrée) → rank-BAS ? (ts_ms = des NS, nom hérité)."""
    return {(e["sym"], e["ts_ms"] // 10**9):
            bool(np.isfinite(e.get("fund_rank", float("nan")))
                 and e["fund_rank"] <= LOW_THR)
            for e in events}


def symbol_trade_stats(trades: list[dict], flags: dict[tuple, bool]) -> dict:
    by: dict[str, list] = defaultdict(list)
    for t in trades:
        if t["strategy"] != "cascade_10x":
            continue
        key = (t["sym"], int(t["entry_ts"].timestamp()))
        by[t["sym"]].append((t["pnl"], flags.get(key, False)))
    out = {}
    for s, v in by.items():
        p = np.array([x[0] for x in v])
        lo = np.array([x[1] for x in v])
        out[s] = {"n": len(p), "wr": float((p > 0).mean() * 100),
                  "pnl": float(p.sum()),
                  "n_low": int(lo.sum()),
                  "wr_low": float((p[lo] > 0).mean() * 100) if lo.any()
                  else float("nan"),
                  "pnl_low": float(p[lo].sum()),
                  "n_oth": int((~lo).sum()),
                  "wr_oth": float((p[~lo] > 0).mean() * 100) if (~lo).any()
                  else float("nan"),
                  "pnl_oth": float(p[~lo].sum())}
    return out


def symbol_monthly(trades: list[dict], capital: float, flags: dict):
    """PnL mensuel PAR SYMBOLE (mois de SORTIE), split rank-BAS (L) / autre
    (O), en % de la balance de début de mois — même agrégation que
    flux_monthly (qubo_sizing), à l'intérieur du flux majors."""
    rows = monthly_rows(trades, capital)
    start = {r["month"]: r["start"] for r in rows}
    accL: dict = defaultdict(lambda: defaultdict(float))
    accO: dict = defaultdict(lambda: defaultdict(float))
    cntL: dict = defaultdict(lambda: defaultdict(int))
    cntO: dict = defaultdict(lambda: defaultdict(int))
    for t in trades:
        if t["strategy"] != "cascade_10x":
            continue
        m = t["exit_ts"].strftime("%Y-%m")
        key = (t["sym"], int(t["entry_ts"].timestamp()))
        low = flags.get(key, False)
        acc, cnt = (accL, cntL) if low else (accO, cntO)
        acc[m][t["sym"]] += t["pnl"]
        cnt[m][t["sym"]] += 1
    months = sorted(start)
    L = np.zeros((NS, len(months)))
    O = np.zeros((NS, len(months)))
    covL = np.zeros(NS, dtype=int)
    covO = np.zeros(NS, dtype=int)
    for j, m in enumerate(months):
        for i, s in enumerate(MAJORS):
            L[i, j] = accL[m].get(s, 0.0) / start[m] * 100.0
            O[i, j] = accO[m].get(s, 0.0) / start[m] * 100.0
            covL[i] += cntL[m].get(s, 0) > 0
            covO[i] += cntO[m].get(s, 0) > 0
    return months, L, O, covL, covO


# ------------------------------------------------------------------
# LE QUBO — grille exhaustive 4^6 × 4 + annealing (garde-fou)
# ------------------------------------------------------------------
def rel_states() -> np.ndarray:
    codes = np.arange(2 ** (NS * M_BITS))
    bits = ((codes[:, None] >> np.arange(NS * M_BITS)) & 1).astype(float)
    return bits.reshape(-1, NS, M_BITS) @ LEVELS          # (4096, 6)


def barrier_idx(mae_tr: dict[str, dict]) -> list[int]:
    """Les symboles dont le MAE max TRAIN implique lev_hard < 11 : surpoids
    interdit (rel ≤ 1) — ils concentrament la marge près de la ligne de mort."""
    return [i for i, s in enumerate(MAJORS)
            if s in mae_tr and mae_tr[s]["lev_hard"] < 11.0 - 1e-9]


def energy_of(rel: np.ndarray, ri: int, mu_list, Sig_list, lam: float) -> float:
    return float(-rel @ mu_list[ri]
                 + 0.5 * lam * (rel @ Sig_list[ri] @ rel))


def grid_search(Rel: np.ndarray, mu_list, Sig_list, lam: float,
                ok: np.ndarray) -> tuple[float, np.ndarray, int]:
    E = np.empty((len(Rel), len(R_VALUES)))
    for k in range(len(R_VALUES)):
        e = -(Rel @ mu_list[k]) + 0.5 * lam * ((Rel @ Sig_list[k]) * Rel).sum(1)
        E[:, k] = np.where(ok, e, np.inf)
    flat = int(np.argmin(E))
    ki, kr = divmod(flat, len(R_VALUES))
    return float(E.flat[flat]), Rel[ki], kr


def anneal(mu_list, Sig_list, lam: float, barred: list[int],
           restarts: int = 32, steps: int = 8000, T0: float = 5.0,
           T1: float = 1e-3, seed: int = SEED) -> tuple[float, np.ndarray, int]:
    rng = np.random.default_rng(seed)

    def valid(rel: np.ndarray) -> bool:
        return all(rel[i] <= 1.0 + 1e-9 for i in barred)

    best_e, best_rel, best_ri = np.inf, None, None
    for _ in range(restarts):
        bits = (rng.random(NS * M_BITS) < 0.5).astype(float)
        ri = int(rng.integers(len(R_VALUES)))
        rel = bits.reshape(NS, M_BITS) @ LEVELS
        if not valid(rel):
            for i in barred:                     # départ valide
                if rel[i] > 1.0:
                    bits[i * M_BITS + M_BITS - 1] = 0.0
            rel = bits.reshape(NS, M_BITS) @ LEVELS
        e = energy_of(rel, ri, mu_list, Sig_list, lam)
        if e < best_e:
            best_e, best_rel, best_ri = e, rel.copy(), ri
        for s in range(steps):
            T = T0 * (T1 / T0) ** (s / steps)
            k = int(rng.integers(NS * M_BITS + 1))
            if k < NS * M_BITS:
                bits[k] = 1 - bits[k]
                rel2 = bits.reshape(NS, M_BITS) @ LEVELS
                if not valid(rel2):
                    bits[k] = 1 - bits[k]
                    continue
                ri2 = ri
            else:
                rel2, ri2 = rel, int(rng.integers(len(R_VALUES)))
            e2 = energy_of(rel2, ri2, mu_list, Sig_list, lam)
            dE = e2 - e
            if dE <= 0 or rng.random() < np.exp(-dE / max(T, 1e-12)):
                rel, ri, e = rel2, ri2, e2
                if e < best_e:
                    best_e, best_rel, best_ri = e, rel.copy(), ri
            elif k < NS * M_BITS:
                bits[k] = 1 - bits[k]
    return best_e, best_rel, best_ri


# ------------------------------------------------------------------
def main() -> int:
    t0 = time.time()
    all_ev, ctx, fh, counts = build_events()
    print(f"[psym] events {dict(counts)} en {time.time()-t0:.0f}s", flush=True)
    self_test_sizer(ctx, all_ev)
    print("[psym] self-test sizer majors r=1.5 == base_sizer : OK", flush=True)

    # ——— le split temporel 70/30, IDENTIQUE au joint ———
    ts = np.array([e["ts_ms"] for e in all_ev])
    t_split = ts.min() + 0.7 * (ts.max() - ts.min())
    d = datetime.fromtimestamp(t_split / 1e9, tz=timezone.utc)
    train_ev = [e for e in all_ev if e["ts_ms"] < t_split]
    val_ev = [e for e in all_ev if e["ts_ms"] >= t_split]
    maj_tr = [e for e in train_ev if e["strategy"] == "cascade_10x"]
    maj_va = [e for e in val_ev if e["strategy"] == "cascade_10x"]
    print(f"[psym] split {d:%Y-%m-%d} : train {len(train_ev)} / val "
          f"{len(val_ev)} | majors {len(maj_tr)} / {len(maj_va)}", flush=True)

    # ——— 1. LA DONNÉE : MAE max PAR symbole (TRAIN) → plafonds 0-liq ———
    mae_tr = mae_by_symbol(train_ev)
    mae_va = mae_by_symbol(val_ev)
    barred = barrier_idx(mae_tr)
    print("[psym] MAE TRAIN : " + " | ".join(
        f"{SHORT[s]} {mae_tr[s]['max']:.2f}%→{mae_tr[s]['lev_hard']:.1f}x"
        for s in MAJORS if s in mae_tr), flush=True)

    # ——— 2. la mesure μ/Σ par symbole (baseline officiel w=1, TRAIN) ———
    base = base_sizer(ctx)
    b_train = run_stack(train_ev, CAPITAL, base, fh)
    b_val = run_stack(val_ev, CAPITAL, base, fh)
    flags_tr = low_flag_map(maj_tr)
    months, Lm, Om, covL, covO = symbol_monthly(
        b_train["trades"], CAPITAL, flags_tr)
    stats_tr = symbol_trade_stats(b_train["trades"], flags_tr)
    T = len(months)
    mu_list, Sig_list = [], []
    for r in R_VALUES:
        M = Om + (r / 1.5) * Lm
        mu_list.append(M.mean(axis=1))
        Sig_list.append(np.cov(M))
    mu15 = mu_list[R_VALUES.index(1.5)]
    print(f"[psym] μ majors (r=1.5) = "
          f"{np.round(mu15, 2).tolist()} sur {T} mois TRAIN", flush=True)

    # ——— 3. la calibration ABSOLU : uniforme = la cellule joint ———
    uni_rel = {s: 1.0 for s in MAJORS}
    uni_tr = run_with(train_ev, ctx, uni_rel, 1.5, fh)
    uni_va = run_with(val_ev, ctx, uni_rel, 1.5, fh)
    uni_full = run_with(all_ev, ctx, uni_rel, 1.5, fh)
    calib = abs(uni_full["balance"] - 5181.86) < 1.0
    print(f"[psym] calibration uniforme FULL ${uni_full['balance']:,.2f} "
          f"vs joint $5,181.86 -> {'OK' if calib else 'ECART (DB bougée ?)'}",
          flush=True)

    # ——— 4. le QUBO : grille exhaustive + annealing, sweep λ ———
    Rel = rel_states()
    ok = np.ones(len(Rel), dtype=bool)
    for i in barred:
        ok &= Rel[:, i] <= 1.0 + 1e-9
    cands: dict[tuple, dict] = {}
    conv = ["| λ | E grille | E annealing | même point ? | rel "
            "(BTC/ETH/SOL/BNB/XRP/DOGE) | r |", "|---|---|---|---|---|---|"]
    grid_ok = []
    for lam in LAMBDAS:
        ge, grel, gri = grid_search(Rel, mu_list, Sig_list, lam, ok)
        ae, arel, ari = anneal(mu_list, Sig_list, lam, barred)
        same_e = abs(ge - ae) < 1e-6
        same_state = np.allclose(grel, arel, atol=1e-9) and gri == ari
        # plateau dégénéré : rel=0 tue tout, r devient sans objet (E=0)
        ok_flag = same_e and (same_state or abs(ge) < 1e-9)
        flag = ("OUI" if same_state else
                ("OUI (plateau E=0)" if ok_flag else "NON — BUG"))
        grid_ok.append(ok_flag)
        key = (tuple(np.round(grel, 4)), R_VALUES[gri])
        if key not in cands:
            cands[key] = {"lam": lam, "rel": dict(zip(MAJORS, grel)),
                          "r": R_VALUES[gri], "relv": grel.copy()}
        conv.append(
            f"| {lam} | {ge:.4f} | {ae:.4f} | {flag} | "
            + "/".join(f"{v:.2f}" for v in grel) + f" | {R_VALUES[gri]:g} |")
        print(f"[psym] lam={lam}: grid {ge:.4f} anneal {ae:.4f} "
              f"{'OK' if ok_flag else 'MISMATCH'} rel="
              f"{np.round(grel, 2).tolist()} r={R_VALUES[gri]:g}", flush=True)

    # ——— 5. LA VALIDATION TRAIN des candidats (vrai run_stack) ———
    evals = []
    for key, cd in cands.items():
        r = run_with(train_ev, ctx, cd["rel"], cd["r"], fh)
        mrows = monthly_rows(r["trades"], CAPITAL)
        rois = [x["roi"] for x in mrows] or [0.0]
        cd.update(train=r, t_neg=int(sum(v < 0 for v in rois)),
                  t_rec=max(rois))
        evals.append(cd)
        print(f"[psym] cand lam={cd['lam']} r={cd['r']:g} "
              f"rel={np.round(cd['relv'], 2).tolist()} -> train "
              f"${r['balance']:,.2f} (DD {r['max_dd']:.1f} %, "
              f"liq {r['n_liq']}, {cd['t_neg']} neg)", flush=True)

    ok_pool = [c for c in evals if c["train"]["n_liq"] == 0
               and c["train"]["max_dd"] <= 25.0
               and c["train"]["balance"] > CAPITAL]
    pool = sorted(ok_pool or evals,
                  key=lambda c: (0 if c["t_neg"] <= 1 else 1,
                                 -c["train"]["balance"],
                                 c["train"]["max_dd"]))
    chosen = pool[0]
    print(f"[psym] CHOISI (TRAIN): lam={chosen['lam']} r={chosen['r']:g} "
          f"rel={np.round(chosen['relv'], 3).tolist()}", flush=True)

    # ——— 6. le jugement VAL : une seule liq = cellule MORTE ———
    c_val = run_with(val_ev, ctx, chosen["rel"], chosen["r"], fh)
    c_full = run_with(all_ev, ctx, chosen["rel"], chosen["r"], fh)
    dead = c_val["n_liq"] > 0 or c_full["n_liq"] > 0
    diag = []
    for cd in sorted(evals, key=lambda c: -c["train"]["balance"])[:5]:
        rv = run_with(val_ev, ctx, cd["rel"], cd["r"], fh)
        diag.append((cd, rv))

    # ——— le CONTRÔLE INVERSE (diagnostic, TRAIN seulement) ———
    rel_inv = {s: 1.5 - chosen["rel"][s] for s in MAJORS}
    inv = run_with(train_ev, ctx, rel_inv, chosen["r"], fh, rank_mode="haut")

    # ——— le rapport ———
    uni_rows, mu = bloc(uni_full, "UNIFORME (joint) — FULL", CAPITAL)
    ch_rows, mc = bloc(c_full, "QUBO PAR SYMBOLE — FULL", CAPITAL)
    L = ["# QUBO PAR SYMBOLE — la granularité dans le flux majors",
         f"{DATE} — 6 majeures × 2 bits (rel ∈ {{0, 0.5, 1.0, 1.5}}×le poids "
         "du flux) + 2 bits de rang (le bonus rank-BAS ×r, r=1.5 = officiel) "
         "= 14 bits, 16,384 états, grille exhaustive + annealing. Objectif : "
         "max Σ relᵢμᵢ(r) − (λ/2) rel'Σ(r)rel, μ/Σ PAR SYMBOLE sur TRAIN "
         "(mois de sortie, run_stack baseline w=1), Mᵢ(ρ)=Oᵢ+ρ·Lᵢ avec "
         "ρ=r/1.5. La couche au-dessus du joint $5,181.86 (+5082 %/an @ "
         "DD 23.3 %, 0 liq) — flux 0.857, lev 11/1/1/1 inchangés.", "",
         "## 1. LA DONNÉE — le MAE max PAR symbole (TRAIN uniquement)", "",
         "| sym | n | médiane | p95 | p99 | **MAX** | lev 0-liq = 100/(max+0.5) "
         "| max VAL (info) | barrière (lev<11) |",
         "|---|---|---|---|---|---|---|---|---|"]
    for s in MAJORS:
        v = mae_tr.get(s)
        if v is None:
            L.append(f"| {SHORT[s]} | 0 | — | — | — | — | — | — | — |")
            continue
        va = mae_va.get(s, {}).get("max", float("nan"))
        L.append(f"| {SHORT[s]} | {v['n']} | {v['med']:.2f} % | {v['p95']:.2f} % "
                 f"| {v['p99']:.2f} % | **{v['max']:.2f} %** "
                 f"| {v['lev_hard']:.2f}x | {va:.2f} % | "
                 f"{'OUI' if s in [MAJORS[i] for i in barred] else 'non'} |")
    bar_txt = (", ".join(SHORT[MAJORS[i]] for i in barred) if barred
               else "aucun — tous les MAE max TRAIN tolèrent 11x "
                    "(plafond non liant, le surpoids par symbole est libre)")
    L += ["", f"Barrière active pour {len(barred)} symbole(s) : {bar_txt}."]
    L += ["", "## 2. LE RANK-BAS PAR SYMBOLE — la métrique validée au niveau "
          "de la granularité (TRAIN, baseline officiel)", "",
          "| sym | trades | WR | PnL $ | rank-BAS n | WR bas | PnL bas $ | "
          "autre n | WR autre | PnL autre $ |", "|---|---|---|---|---|---|"
          "---|---|---|---|"]
    for s in MAJORS:
        v = stats_tr.get(s)
        if v is None:
            continue
        L.append(f"| {SHORT[s]} | {v['n']} | {v['wr']:.0f} % | {v['pnl']:+.2f} "
                 f"| {v['n_low']} | {v['wr_low']:.0f} % | {v['pnl_low']:+.2f} "
                 f"| {v['n_oth']} | {v['wr_oth']:.0f} % | {v['pnl_oth']:+.2f} |")
    L += ["", "## 3. LA MESURE μ/Σ PAR SYMBOLE — et son bruit (l'honnêteté)", "",
          f"{T} mois TRAIN, {len(maj_tr)} événements majors TRAIN "
          f"(≈ {len(maj_tr)/6:.0f}/symbole) → Σ 6×6 = 21 entrées estimées sur "
          "~10 observations : **la covariance est BRUYANTE**, la barre de "
          "PASS est haute. Mᵢ(ρ) = Oᵢ + ρ·Lᵢ (L = PnL rank-BAS à ×1.5, "
          "linéarisation — le cap 0.50·K_ATT interne est ignoré dans le QUBO, "
          "run_stack tranche).", "",
          "| sym | μ à r=1.5 (%/mois) | μ rank-BAS (μL) | μ autre (μO) | "
          "mois couverts L/O |", "|---|---|---|---|---|"]
    muL = Lm.mean(axis=1)
    muO = Om.mean(axis=1)
    for i, s in enumerate(MAJORS):
        L.append(f"| {SHORT[s]} | {mu15[i]:+.2f} | {muL[i]:+.2f} | "
                 f"{muO[i]:+.2f} | {covL[i]}/{covO[i]} |")
    L += ["", "Σ à r=1.5 (%², mois de sortie) :", "",
          "| sym | " + " | ".join(SHORT[s] for s in MAJORS) + " |",
          "|---|" + "---|" * NS]
    Sig15 = Sig_list[R_VALUES.index(1.5)]
    for i, s in enumerate(MAJORS):
        L.append(f"| {SHORT[s]} | "
                 + " | ".join(f"{Sig15[i, j]:.2f}" for j in range(NS)) + " |")
    L += ["", "## 4. LA GRILLE vs L'ANNEALING — le garde-fou solver", ""]
    L += conv
    if not all("OUI" in l for l in conv[2:]):
        L.append("**MISMATCH grille/annealing — voir ci-dessus.**")
    L += ["", "## 5. LA VALIDATION TRAIN — chaque candidat au vrai wallet", "",
          "| λ | rel (BTC/ETH/SOL/BNB/XRP/DOGE) | r | Train $ | DD | liq | "
          "mois nég | record |", "|---|---|---|---|---|---|---|---|"]
    for cd in sorted(evals, key=lambda c: -c["train"]["balance"]):
        L.append(f"| {cd['lam']} | "
                 + "/".join(f"{cd['rel'][s]:.2f}" for s in MAJORS)
                 + f" | {cd['r']:g} | ${cd['train']['balance']:,.2f} "
                 f"| {cd['train']['max_dd']:.1f} % | {cd['train']['n_liq']} "
                 f"| {cd['t_neg']} | {cd['t_rec']:+.1f} % |")
    L += [f"| uniforme (= joint) | " + "/".join("1.00" for _ in MAJORS)
          + f" | 1.5 | ${uni_tr['balance']:,.2f} "
          f"| {uni_tr['max_dd']:.1f} % | {uni_tr['n_liq']} | — | — |", "",
          "Sélection sur TRAIN : 0 liq, DD ≤ 25 %, ≤ 1 mois négatif, balance "
          "max (règle du joint).", "",
          "## 6. LE JUGEMENT VAL — une seule liq = cellule MORTE", "",
          f"Cellule choisie sur TRAIN (λ={chosen['lam']}) : rel = "
          + "/".join(f"{chosen['rel'][s]:.2f}" for s in MAJORS)
          + f", r = {chosen['r']:g}. VAL : {c_val['n']} trades, liq "
          f"**{c_val['n_liq']}**, DD {c_val['max_dd']:.1f} %, "
          f"${c_val['balance']:,.2f} → "
          + ("**MORTE**" if dead else "**VIVANTE** (0 liq en VAL)."), "",
          "Diagnostic (information seulement, PAS une re-sélection) :", "",
          "| λ | r | rel | Train $ | VAL $ | VAL liq | statut |",
          "|---|---|---|---|---|---|---|"]
    for cd, rv in diag:
        st = "MORTE" if rv["n_liq"] > 0 else "vivante"
        L.append(f"| {cd['lam']} | {cd['r']:g} | "
                 + "/".join(f"{cd['rel'][s]:.2f}" for s in MAJORS)
                 + f" | ${cd['train']['balance']:,.2f} "
                 f"| ${rv['balance']:,.2f} | {rv['n_liq']} | {st} |")
    L += [f"", "Contrôle inverse (diagnostic TRAIN) : rel inversé "
          f"(1.5−rel) + bonus rank déplacé sur le rank-HAUT → "
          f"${inv['balance']:,.2f} (DD {inv['max_dd']:.1f} %) vs choisi "
          f"${chosen['train']['balance']:,.2f} — "
          + ("le contrôle est battu, la direction du signal porte."
             if chosen["train"]["balance"] > inv["balance"] else
             "**le contrôle inverse GAGNE : chance de chemin, non-adoptable"
             " (précédent registre sizing funding_rank).**"), "",
          "## 7. LE BLOC STATS — par symbole vs uniforme (= joint)", ""]
    for res, lbl in ((uni_tr, "UNIFORME (joint) — TRAIN"),
                     (run_with(train_ev, ctx, chosen["rel"], chosen["r"], fh),
                      "QUBO PAR SYMBOLE — TRAIN"),
                     (uni_va, "UNIFORME (joint) — VAL"),
                     (c_val, "QUBO PAR SYMBOLE — VAL"),
                     (uni_full, "UNIFORME (joint) — FULL (réf. $5,181.86)"),
                     (c_full, "QUBO PAR SYMBOLE — FULL")):
        lines, _ = bloc(res, lbl, CAPITAL)
        L += lines + [""]
    L += ["### La table mensuelle du QUBO PAR SYMBOLE (full)", "",
          "| Mois | Trades | WR | Liq | Balance début → fin | ROI |",
          "|---|---|---|---|---|---|"]
    for x in mc["mrows"]:
        L.append(f"| {x['month']} | {x['n']} "
                 f"| {x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} "
                 f"| ${x['start']:,.0f} → ${x['end']:,.0f} "
                 f"| {x['roi']:+.1f} % |")

    # ——— le verdict ———
    d_roi = (c_full["balance"] / uni_full["balance"] - 1) * 100
    beats_train = chosen["train"]["balance"] > uni_tr["balance"]
    same_point = (chosen["r"] == 1.5
                  and all(abs(chosen["rel"][s] - 1.0) < 1e-9 for s in MAJORS))
    pass_full = (not dead and c_full["n_liq"] == 0
                 and c_full["balance"] >= uni_full["balance"]
                 and c_full["max_dd"] <= uni_full["max_dd"] + 0.5
                 and mc["neg"] <= 1 and mc["gap_c"] < 0.005)
    if same_point:
        verdict = ("LE QUBO RETOMBE SUR L'UNIFORME — la différenciation par "
                   "symbole n'apporte rien au-dessus du flux uniforme + rank")
    elif pass_full and beats_train:
        verdict = ("PASS — la différenciation par symbole ajoute du ROI sans "
                   "dégrader DD/record/mois négatifs, 0 liq, composé OK")
    else:
        verdict = ("CONTEXTE — la différenciation ne passe pas la barre "
                   "(covariance bruitée, ~38 événements/symbole) : le flux "
                   "uniforme + rank-BAS ×1.5 reste la config")
    L += ["", "## VERDICT", "",
          f"- MAE max TRAIN par symbole (LA donnée) : "
          + ", ".join(f"{SHORT[s]} {mae_tr[s]['max']:.2f} % "
                      f"(plafond {mae_tr[s]['lev_hard']:.1f}x)"
                      for s in MAJORS if s in mae_tr)
          + f" — le global 7.66 % masquait la dispersion ; barrière "
          f"surpoids : {len(barred)} symbole(s).",
          f"- Calibration ABSOLU : uniforme (rel=1, r=1.5) FULL "
          f"${uni_full['balance']:,.2f} vs joint $5,181.86 → "
          f"{'OK' if calib else 'ÉCART (les ABSOLUS bougent avec la DB, les relatifs restent)'}",
          f"- Le QUBO (grille = annealing, 16,384 états) choisit rel = "
          + "/".join(f"{chosen['rel'][s]:.2f}" for s in MAJORS)
          + f", r = {chosen['r']:g} (λ={chosen['lam']}) — "
          + ("**identique à l'uniforme**" if same_point
             else "**un point que l'uniforme n'a pas**") + ".",
          f"- TRAIN : ${chosen['train']['balance']:,.2f} vs uniforme "
          f"${uni_tr['balance']:,.2f} ({(chosen['train']['balance']/uni_tr['balance']-1)*100:+.1f} %) — "
          f"en échantillon la différenciation "
          f"{'gagne' if beats_train else 'NE gagne PAS'}.",
          f"- FULL : ${c_full['balance']:,.2f} vs uniforme "
          f"${uni_full['balance']:,.2f} ({d_roi:+.1f} %), DD "
          f"{c_full['max_dd']:.1f} % vs {uni_full['max_dd']:.1f} %, record "
          f"{max(mc['rois']):+.1f} % vs {max(mu['rois']):+.1f} %, mois "
          f"négatifs {mc['neg']} vs {mu['neg']}, garde-fou composé "
          f"{mc['gap_c']*100:.3f} % {'OK' if mc['gap_c'] < 0.005 else 'BUG'}.",
          f"- LIQ : TRAIN {chosen['train']['n_liq']}, VAL "
          f"**{c_val['n_liq']}**, FULL {c_full['n_liq']} → "
          + ("**CELLULE MORTE**" if dead else "**0 liq partout**") + ".",
          f"- VERDICT : **{verdict}**.",
          "- Limites honnêtes : ~38 événements/symbole, Σ 6×6 sur ~10 mois "
          "= bruit dominant ; le contrôle inverse est le juge du chemin ; "
          "le QUBO linéarise (Mᵢ = Oᵢ+ρLᵢ, cap 0.50·K ignoré, busy-skip "
          "invariant aux tailles supposé) — seul run_stack fait foi.",
          ""]
    out = REPORTS / f"qubo-per-symbol-{DATE}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[psym] rapport -> {out}", flush=True)
    print(f"[psym] VERDICT: rel={np.round(chosen['relv'], 3).tolist()} "
          f"r={chosen['r']:g} lam={chosen['lam']} | full "
          f"${c_full['balance']:,.2f} vs uniforme "
          f"${uni_full['balance']:,.2f} (joint $5,181.86) | liq "
          f"{chosen['train']['n_liq']}/{c_val['n_liq']}/{c_full['n_liq']} | "
          f"{verdict}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
