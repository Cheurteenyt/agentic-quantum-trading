#!/usr/bin/env python3
"""La couche signaux fomo — lit ws_swaps/ws_theses (le flux WS) et détecte :

  1. SORTIE CONSENSUS : ≥ N top traders vendent le MÊME token dans la fenêtre
     → le signal de sortie des réplications (le smart money quitte).
  2. THÈSE TOP TRADER : un des 8 meilleurs publie une thèse → le signal social
     (le texte + la mise + le PnL live de l'auteur).
  3. POMPE CONSENSUS : ≥ N top traders achètent le même token dans la fenêtre
     → l'entrée de replication (l'extension du consensus AGI identifié).

Les signaux vont dans ws_signals (fomo_swaps.db) + le journal. Idempotent :
les signaux déjà émis (kind, token, fenêtre) ne se réémettent pas.
Le rythme : 1×/5 min (le timer fomo-ws-signals.timer).
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "fomo" / "fomo_swaps.db"
STATE = ROOT / "data" / "fomo" / "ws_signals_state.json"

WINDOW_MIN = 30          # la fenêtre de consensus
EXIT_THRESHOLD = 2       # ≥ 2 top traders vendent = signal de sortie
BUY_THRESHOLD = 2        # ≥ 2 top traders achètent = signal d'entrée
LOOKBACK_MIN = 35        # le regard en arrière (> la fenêtre)


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"emitted": []}  # ["exit|addr|yyyymmddHH:MM-bucket", ...]


def emit(con, state, kind, token, ticker, handles, detail):
    # l'idempotence : une clé par (kind, token, bucket de 30 min)
    bucket = time.strftime("%Y%m%d%H", time.localtime()) + f"{time.localtime().tm_min // WINDOW_MIN}"
    key = f"{kind}|{token}|{bucket}"
    if key in state["emitted"]:
        return False
    state["emitted"].append(key)
    state["emitted"] = state["emitted"][-500:]  # la taille bornée
    con.execute("INSERT INTO ws_signals VALUES (?,?,?,?,?,?,?)",
                (key, kind, token, ticker, json.dumps({"handles": handles, **detail}),
                 int(time.time()), int(time.time())))
    log(f"  ⚡ {kind} {ticker} : {', '.join(sorted(handles))}")
    return True


def main():
    con = sqlite3.connect(DB, timeout=30)
    con.execute("""CREATE TABLE IF NOT EXISTS ws_signals (
        signal_key TEXT PRIMARY KEY, kind TEXT, token_addr TEXT, ticker TEXT,
        detail TEXT, created_at INTEGER, captured_at INTEGER)""")
    con.commit()

    state = load_state()
    since = int(time.time()) - LOOKBACK_MIN * 60
    n_new = 0

    # 1) les SORTIES consensus (les ventes des top traders par token)
    rows = con.execute("""
        SELECT token_addr, MAX(ticker), COUNT(DISTINCT handle), GROUP_CONCAT(DISTINCT handle),
               ROUND(SUM(usd_amount), 0), MAX(captured_at)
        FROM ws_swaps
        WHERE top_trader=1 AND type='swap_sell' AND captured_at > ? AND token_addr IS NOT NULL
        GROUP BY token_addr
        HAVING COUNT(DISTINCT handle) >= ?
        ORDER BY SUM(usd_amount) DESC""", (since, EXIT_THRESHOLD)).fetchall()
    for addr, ticker, n, handles, usd, _ in rows:
        if emit(con, state, "exit_consensus", addr, ticker, handles.split(","),
                {"traders": n, "usd_sold_window": usd, "window_min": WINDOW_MIN}):
            n_new += 1

    # 2) les ENTRÉES consensus (les achats des top traders par token)
    rows = con.execute("""
        SELECT token_addr, MAX(ticker), COUNT(DISTINCT handle), GROUP_CONCAT(DISTINCT handle),
               ROUND(SUM(usd_amount), 0), MAX(market_cap)
        FROM ws_swaps
        WHERE top_trader=1 AND type='swap_buy' AND captured_at > ? AND token_addr IS NOT NULL
        GROUP BY token_addr
        HAVING COUNT(DISTINCT handle) >= ?
        ORDER BY SUM(usd_amount) DESC""", (since, BUY_THRESHOLD)).fetchall()
    for addr, ticker, n, handles, usd, mc in rows:
        if emit(con, state, "buy_consensus", addr, ticker, handles.split(","),
                {"traders": n, "usd_bought_window": usd, "market_cap": mc,
                 "window_min": WINDOW_MIN}):
            n_new += 1

    # 3) les THÈSES des top traders (chaque thèse = un signal social)
    rows = con.execute("""
        SELECT thesis_id, handle, ticker, token_addr, comment, usd_value,
               pnl_pct_unrealized, mc_at_creation, captured_at
        FROM ws_theses
        WHERE top_trader=1 AND captured_at > ?""", (since,)).fetchall()
    for tid, handle, ticker, addr, comment, usd, pnl, mc, _ in rows:
        key = f"thesis_top|{tid}"
        if key in state["emitted"]:
            continue
        state["emitted"].append(key); state["emitted"] = state["emitted"][-500:]
        con.execute("INSERT INTO ws_signals VALUES (?,?,?,?,?,?,?)",
                    (key, "thesis_top", addr, ticker,
                     json.dumps({"handle": handle, "comment": comment, "usd": usd,
                                 "pnl_pct_author": pnl, "market_cap": mc}),
                     int(time.time()), int(time.time())))
        log(f"  ⚡ thesis_top {ticker} par {handle} : « {(comment or '')[:60]} »")
        n_new += 1

    con.commit()
    con.close()
    STATE.write_text(json.dumps(state))
    print(f"[signaux] {n_new} nouveau(x) signal(aux) sur la fenêtre {LOOKBACK_MIN} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
