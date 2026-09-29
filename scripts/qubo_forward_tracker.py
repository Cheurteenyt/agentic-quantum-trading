#!/usr/bin/env python
"""QUBO FORWARD TRACKER — suivi parallèle des 2 wallets sur les MÊMES trades paper.

Le QUBO a trouvé les poids [majors 0.857, meme 0.857, survivor 2.0, vol_spike 1.143]
(full backtest +4539 %/an @ DD 23,4 % vs main +3905 @ 24,8). La promotion exige
2-4 semaines de forward : les DEUX wallets sont rejoués sur les MÊMES trades du
ledger paper_trades (les poids = recombinaison linéaire des retours des flux,
PAS de nouveaux signaux).

CONVENTIONS (reprises telles quelles des harnais) :
- ret_pct du ledger = rendement au niveau PRIX, net (coûts + funding déjà
  déduits par paper_forward.py à la clôture), SANS levier.
- Exposition d'un trade = base[flux] × lev[flux] × poids[flux] (paper_forward
  L359-375 : majors base 0.24 @ 10x, meme/survivor/vol_spike base 0.10 @ 1x).
  PnL fraction = ret_pct / 100 × exposition ; wallet séquentiel composé.
- Créneaux run_stack (stacked_portfolio.py L161) : 1 slot par flux — un flux
  ne re-trade pas tant qu'une position est ouverte (entry_ts < busy_until) ;
  les flux se croisent librement. Les trades bloqués par le créneau sont
  comptés mais n'affectent aucun wallet. Ordre chronologique entry_ts.
- Le flux machine_survivor_long n'a pas encore de trades en ledger : le poids
  2.0 est prêt, le spread bougera dès ses ouvertures.

Idempotent : recalcul intégral depuis paper_trades en LECTURE SEULE.
Sortie : --report (stdout ET append vers reports/qubo-forward.log — le
tracker s'appende lui-même, l'unité nocturne ne redirige pas).
"""
from __future__ import annotations

import argparse
import sqlite3
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KDB = ROOT / "data" / "warehouse" / "klines.db"

# les 4 flux de la machine : (base marge, levier) — paper_forward.py L359-362
FLOWS: dict[str, tuple[float, float]] = {
    "machine_cascade_majors": (0.24, 10.0),
    "machine_cascade_meme": (0.10, 1.0),
    "machine_survivor_long": (0.10, 1.0),
    "machine_vol_spike_6h": (0.10, 1.0),
}
WEIGHTS: dict[str, dict[str, float]] = {
    "MAIN": {f: 1.0 for f in FLOWS},
    "QUBO": {"machine_cascade_majors": 0.857, "machine_cascade_meme": 0.857,
             "machine_survivor_long": 2.0, "machine_vol_spike_6h": 1.143},
    # la variante SANS MEME (28/09) : le forward meme 0/10 gagnants (-49 %)
    # + la VAL négative + aucun gate possible → le forward tranche entre
    # la loterie décorrelante (QUBO) et la sortie franche (SANS_MEME)
    "SANS_MEME": {"machine_cascade_majors": 0.857, "machine_cascade_meme": 0.0,
                  "machine_survivor_long": 2.0, "machine_vol_spike_6h": 1.143},
}


def load_machine_trades(con: sqlite3.Connection) -> tuple[list[dict], dict[str, int]]:
    """Trades machine_* (open + closed), ordre chronologique déterministe.
    Les tags hors FLOWS (ex. machine_deep_fast en quarantaine) sont COMPTÉS
    et remontés au rapport — jamais silencieusement perdus."""
    rows = con.execute(
        "SELECT rowid, signal, symbol, entry_ts, exit_ts, ret_pct, status "
        "FROM paper_trades WHERE signal LIKE 'machine_%' "
        "ORDER BY entry_ts, rowid").fetchall()
    out = []
    unknown: dict[str, int] = {}
    for rid, sig, sym, ets, xts, ret, status in rows:
        if sig not in FLOWS:
            unknown[sig] = unknown.get(sig, 0) + 1
            continue
        out.append({"rowid": rid, "flow": sig, "symbol": sym,
                    "entry_ts": int(ets), "exit_ts": int(xts) if xts else None,
                    "ret": float(ret) if ret is not None else None,
                    "status": status})
    return out, unknown


def slot_filter(trades: list[dict]) -> tuple[list[dict], list[dict]]:
    """Créneaux run_stack : 1 slot par flux, flux croisés librement.
    Un trade est JOUÉ si le flux est libre à son entry_ts (busy <= entry_ts,
    cf. stacked_portfolio.py L161 : skip si busy > ts). Un trade ouvert
    occupe le slot indéfiniment (exit_ts NULL -> busy = +inf) jusqu'à sa
    clôture en ledger ; le re-run recalcule tout depuis le ledger."""
    played, blocked = [], []
    busy: dict[str, int] = {}
    for t in trades:
        f = t["flow"]
        if busy.get(f, -(1 << 62)) > t["entry_ts"]:
            blocked.append(t)
            continue
        played.append(t)
        end = t["exit_ts"] if t["exit_ts"] is not None else (1 << 62)
        busy[f] = end
    return played, blocked


def run_wallet(name: str, played: list[dict]) -> dict:
    """Wallet séquentiel composé, convention paper_forward : PnL fraction =
    ret_pct/100 × base × lev × poids. Ordre entry_ts (fidèle à run_stack)."""
    w = WEIGHTS[name]
    bal = peak = 100.0
    dd = 0.0
    months: dict[str, dict] = {}
    n_played = 0
    for t in played:
        base, lev = FLOWS[t["flow"]]
        if t["status"] != "closed" or t["ret"] is None:
            continue  # ouvert : occupe le slot, PnL latent non compté
        frac = t["ret"] / 100.0 * base * lev * w[t["flow"]]
        bal *= (1.0 + frac)
        peak = max(peak, bal)
        dd = max(dd, (peak - bal) / peak * 100.0)
        m = datetime.fromtimestamp(t["exit_ts"] / 1000, tz=timezone.utc)
        fm = months.setdefault(m.strftime("%Y-%m"), {"roi": 0.0, "n": 0, "w": 0})
        fm["roi"] += frac * 100.0
        fm["n"] += 1
        fm["w"] += frac > 0
        n_played += 1
    return {"name": name, "bal": bal, "dd": dd, "n": n_played,
            "months": months}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true",
                    help="imprime la table des deux wallets")
    args = ap.parse_args()

    uri = "file:" + urllib.parse.quote(str(KDB)) + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    trades, unknown = load_machine_trades(con)
    con.close()

    played, blocked = slot_filter(trades)
    played_ids = {t["rowid"] for t in played}
    open_n = sum(1 for t in trades if t["status"] == "open")
    per_flow = {f: {"played": 0, "blocked": 0, "open": 0} for f in FLOWS}
    for t in trades:
        if t["flow"] in per_flow:
            if t["status"] == "open":
                per_flow[t["flow"]]["open"] += 1
            elif t["rowid"] in played_ids:
                per_flow[t["flow"]]["played"] += 1
            else:
                per_flow[t["flow"]]["blocked"] += 1
    wallets = {n: run_wallet(n, played) for n in WEIGHTS}
    wm, wq, ws = wallets["MAIN"], wallets["QUBO"], wallets["SANS_MEME"]
    spread_abs = wq["bal"] - wm["bal"]
    spread_rel = (wq["bal"] / wm["bal"] - 1.0) * 100.0 if wm["bal"] > 0 else 0.0
    spread_sm = ws["bal"] - wq["bal"]

    if not args.report:
        print("[qubo-tracker] rien à faire sans --report")
        return 0

    now = datetime.now(timezone.utc)
    L = []
    L.append(f"=== QUBO FORWARD TRACKER — {now:%d/%m/%Y %H:%M} UTC ===")
    L.append("Convention : ret_pct = ret PRIX net (coûts+funding déduits, sans "
             "levier) ; PnL frac = ret/100 × base × lev × poids ; base/lev = "
             "paper_forward (majors 0.24@10x, meme/survivor/vol 0.10@1x) ; "
             "créneaux run_stack (1 slot/flux, flux croisés), ordre entry_ts.")
    L.append(f"Ledger : {len(trades)} trades machine_* ({len(trades) - open_n} "
             f"closed, {open_n} open) ; joués aux créneaux : {len(played)}, "
             f"bloqués slot : {len(blocked)}")
    for f, c in per_flow.items():
        base, lev = FLOWS[f]
        L.append(f"  - {f} (base {base} @ {lev:.0f}x) : joués {c['played']}, "
                 f"bloqués {c['blocked']}, ouverts {c['open']}")
    if unknown:
        L.append("  ⚠ TAGS HORS FLOWS ignorés (quarantaine/probe, hors "
                 "scoreboard) : " + ", ".join(f"{k} ×{v}"
                                              for k, v in sorted(unknown.items())))
    for w in wallets.values():
        tag = w["name"]
        wts = WEIGHTS[tag]
        L.append(f"WALLET {tag:<4} [{wts['machine_cascade_majors']:.3f}/"
                 f"{wts['machine_cascade_meme']:.3f}/"
                 f"{wts['machine_survivor_long']:.3f}/"
                 f"{wts['machine_vol_spike_6h']:.3f}] : "
                 f"balance ${w['bal']:,.2f} (départ 100) | DD {w['dd']:.2f} % | "
                 f"{w['n']} trades joués")
        for m in sorted(w["months"]):
            fm = w["months"][m]
            wr = fm["w"] / fm["n"] * 100 if fm["n"] else 0.0
            L.append(f"    {m} : ROI {fm['roi']:+.2f} % ({fm['n']} trades, "
                     f"WR {wr:.0f} %)")
    rois_m = [fm["roi"] for fm in wm["months"].values()]
    rois_q = [fm["roi"] for fm in wq["months"].values()]
    if rois_m:
        L.append(f"  MAIN  mois : record {max(rois_m):+.2f} %, pire "
                 f"{min(rois_m):+.2f} %, négatifs "
                 f"{sum(1 for r in rois_m if r < 0)}/{len(rois_m)}")
        L.append(f"  QUBO  mois : record {max(rois_q):+.2f} %, pire "
                 f"{min(rois_q):+.2f} %, négatifs "
                 f"{sum(1 for r in rois_q if r < 0)}/{len(rois_q)}")
    L.append(f"SPREAD QUBO − MAIN : {spread_abs:+.2f} $ / 100 $ "
             f"({spread_rel:+.2f} % rel)")
    L.append("Idempotent : recalcul intégral depuis paper_trades (lecture "
             "seule). Verdict promotion : 2-4 semaines de spread.")
    L.append("NB : le wallet QUBO = les POIDS SEULS (bases/leviers "
             "paper_forward) — le point officiel JOINT (majors 11x) se "
             "recalcule a posteriori sur les mêmes rets.")

    report = "\n".join(L)
    print(report)
    log_f = ROOT / "reports" / "qubo-forward.log"
    try:
        with open(log_f, "a") as fh:
            fh.write(report + "\n")
    except OSError as e:
        print(f"[qubo-tracker] append {log_f.name} impossible : {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
