#!/usr/bin/env python
"""LE LEDGER FORWARD des lancements fomo — le paper-trading forward-first.

Forward-first : pas de fake backtest — les mints détectés FRAIS par le
collector live (< 6h de première apparition) sont ouverts en paper au
prix réel du moment ; chaque passe --run fait vieillir le ledger, qui
DEVIENT du backtest en vieillissant. Doctrine lifecycle v2 : TEMPS-FIXE
écrase le trailing — 3 horizons PARALLÈLES par mint (24h/48h/72h, une
ligne chacune) ; le trailing -35 % ne sert que de garde anti-rug.

DB PROPRE : data/fomo/fomo_paper.db (SÉPARÉE — fomo.db appartient au
top-up timer, on ne la lit qu'en mode=ro).

  .venv/bin/python scripts/fomo_paper_forward.py --run     # une passe
  .venv/bin/python scripts/fomo_paper_forward.py --report  # l'état
"""
from __future__ import annotations

import argparse
import fcntl
import sqlite3
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LIVE_DB = ROOT / "data" / "fomo" / "fomo.db"        # LECTURE SEULE (mode=ro)
PAPER_DB = ROOT / "data" / "fomo" / "fomo_paper.db"  # NOTRE écriture

# l'anti-verrou : jamais 2 instances du paper-forward (chevauchement timer)
_lock_fh = open(ROOT / "data" / "fomo" / ".paper_forward.lock", "w")
try:
    fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("[paper] une autre instance tourne déjà — sortie", flush=True)
    sys.exit(0)

# les faux mints : les actifs de cotation (SOL wrappé, WETH, cbBTC,
# stables) + les 0x EVM = jamais des tokens fomo — filtre à la source
QUOTE_MINTS = frozenset({
    "So11111111111111111111111111111111111111112",  # SOL wrappé
    "7vfCXTUXxzBN6xej7ucn7NNvi3orD1vs8HN4cBwpfA2Z",  # WETH Wormhole
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij",  # cbBTC Coinbase
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",  # WBTC
})


def _is_tradeable_mint(mint: str) -> bool:
    if not mint or len(mint) < 32:
        return False
    if mint in QUOTE_MINTS or mint.startswith("0x"):
        return False
    return True


HORIZONS = (("24h", 86400), ("48h", 172800), ("72h", 259200))
FRESH_WINDOW_S = 6 * 3600        # détecté FRAIS = première apparition < 6h
ANTI_RUG_TRIGGER = 0.65          # multiple < 0.65 × max (le -35 % de garde)
ANTI_RUG_MIN_MAX = 1.2           # …et seulement si le max ≥ 1.2

# ── LA RÉPLICATION PASSIVE derek518 (rapport derek-replication 2026-09-27) ──
# achats derek518 ≥ $5k sur un token âgé ≥ 7j, entrée ≤ 15 min après son swap,
# hold 24h + garde anti-rug (les CONSTANTES du dessus), ≤ 10 positions OPEN.
SWAPS_DB = ROOT / "data" / "fomo" / "fomo_swaps.db"  # LECTURE SEULE (mode=ro)
REPL_RULE = "replication_derek"
DEREK_HANDLE = "derek518"        # _swaps_meta = le cache handle→user_id fait foi
REPL_MIN_USD = 5000.0            # achat derek ≥ $5k
REPL_MIN_AGE_S = 7 * 86400       # token âgé ≥ 7j (1re bougie 1h du mint)
REPL_ENTRY_WINDOW_S = 900        # entrée ≤ 15 min après son swap
REPL_MAX_OPEN = 10               # ≤ 10 positions simultanées (exposition bornée)


def open_live() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True, timeout=45)
    con.execute("PRAGMA busy_timeout=45000")
    return con


def open_paper() -> sqlite3.Connection:
    con = sqlite3.connect(PAPER_DB, timeout=45)
    con.execute("PRAGMA busy_timeout=45000")
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS fomo_paper_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mint TEXT NOT NULL, ticker TEXT, rule TEXT NOT NULL,
        horizon TEXT, entry_ts REAL, entry_price REAL,
        exit_ts REAL, exit_price REAL,
        multiple REAL, max_multiple REAL,
        status TEXT NOT NULL DEFAULT 'OPEN',
        opened_at REAL NOT NULL, closed_at REAL);
    CREATE INDEX IF NOT EXISTS idx_paper_mint
        ON fomo_paper_trades (mint, status);
    """)
    # la réplication derek : l'IDEMPOTENCE par swap_id (PK métier) — un swap
    # déjà répliqué ne se ré-ouvre JAMAIS, même re-scanné après coup
    cols = {r[1] for r in con.execute("PRAGMA table_info(fomo_paper_trades)")}
    if "swap_id" not in cols:
        con.execute("ALTER TABLE fomo_paper_trades ADD COLUMN swap_id TEXT")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_swap "
                "ON fomo_paper_trades (swap_id) WHERE swap_id IS NOT NULL")
    con.execute("CREATE TABLE IF NOT EXISTS fomo_paper_state "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    return con


def last_price(con_live: sqlite3.Connection, mint: str):
    """Le dernier close 1m de fomo_ohlcv, sinon le dernier tick. → (ts_s, px)"""
    r = con_live.execute(
        "SELECT time, close FROM fomo_ohlcv WHERE asset=? AND period='1m' "
        "ORDER BY time DESC LIMIT 1", (mint,)).fetchone()
    if r and r[1]:
        return r[0] / 1000.0, float(r[1])
    r = con_live.execute(
        "SELECT ts_s, priceUsd FROM fomo_ticks WHERE mint=? "
        "ORDER BY ts_s DESC LIMIT 1", (mint,)).fetchone()
    if r and r[1]:
        return float(r[0]), float(r[1])
    return None, None


def max_since_entry(con_live: sqlite3.Connection, mint: str, entry_ts: float) -> float:
    """Le max observé DEPUIS l'entrée (highs 1m + ticks) — le forward pur."""
    best = 0.0
    r = con_live.execute(
        "SELECT MAX(high) FROM fomo_ohlcv WHERE asset=? AND period='1m' AND time>=?",
        (mint, int(entry_ts * 1000))).fetchone()
    if r and r[0]:
        best = float(r[0])
    r = con_live.execute(
        "SELECT MAX(priceUsd) FROM fomo_ticks WHERE mint=? AND ts_s>=?",
        (mint, int(entry_ts))).fetchone()
    if r and r[0]:
        best = max(best, float(r[0]))
    return best


def fresh_mints(con_live: sqlite3.Connection, now: float):
    """Les mints FRAIS : première apparition (fomo_tokens OU fomo_ticks) < 6h."""
    rows = con_live.execute("""
        SELECT mint, MIN(first_seen) FROM (
            SELECT mint, resolved_at AS first_seen FROM fomo_tokens
            WHERE mint IS NOT NULL
            UNION ALL
            SELECT mint, captured_at AS first_seen FROM fomo_ticks
        ) GROUP BY mint HAVING MIN(first_seen) IS NOT NULL
    """).fetchall()
    out = []
    for mint, fs in rows:
        if not _is_tradeable_mint(mint):
            continue
        if fs is None or fs > now or now - fs >= FRESH_WINDOW_S:
            continue
        out.append((mint, float(fs)))
    return out


def resolve_ticker(con_live: sqlite3.Connection, mint: str) -> str:
    r = con_live.execute(
        "SELECT ticker FROM fomo_tokens WHERE mint=? "
        "ORDER BY resolved_at DESC LIMIT 1", (mint,)).fetchone()
    return (r[0] or mint[:10]).upper() if r else mint[:10]


def open_swaps() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{SWAPS_DB}?mode=ro", uri=True, timeout=45)
    con.execute("PRAGMA busy_timeout=45000")
    return con


def replication_derek(con: sqlite3.Connection, con_live: sqlite3.Connection,
                      con_swaps: sqlite3.Connection, now: float):
    """La règle 'replication_derek' : répliquer PASSIF les achats derek518.

    Swaps frais du collector (fomo_swaps.db en mode=ro, page 1 = les plus
    frais) : buy ≥ $5k, token âgé ≥ 7j (1re bougie 1h), entrée ≤ 15 min
    après le swap → OPEN rule='replication_derek', horizon='24h' → la
    SORTIE est gérée par la boucle commune (hold 24h + garde anti-rug,
    MÊME convention last_price/max_since_entry que les autres règles).
    Idempotent : swap_id en PK métier ; la fenêtre par défaut (1re passe)
    = now-15min → strictement forward-only, aucun backfill du passé.
    → (ouverts, sautés hors-fenêtre/filtre, sautés cap)
    """
    r = con_swaps.execute("SELECT user_id FROM _swaps_meta WHERE handle=?",
                          (DEREK_HANDLE,)).fetchone()
    if not r:
        print("[repl] derek518 absent du cache _swaps_meta — skip", flush=True)
        return 0, 0, 0
    uid = r[0]
    last = con.execute("SELECT value FROM fomo_paper_state "
                       "WHERE key='derek_last_ts'").fetchone()
    since = float(last[0]) if last else now - REPL_ENTRY_WINDOW_S
    rows = con_swaps.execute(
        "SELECT swap_id, mint, ts, size_usd FROM fomo_swaps "
        "WHERE user_id=? AND side='buy' AND size_usd>=? AND ts>? AND ts<=? "
        "ORDER BY ts", (uid, REPL_MIN_USD, since - 120, now)).fetchall()
    n_open = con.execute(
        "SELECT COUNT(*) FROM fomo_paper_trades "
        "WHERE rule=? AND status='OPEN'", (REPL_RULE,)).fetchone()[0]
    seen = {x[0] for x in con.execute(
        "SELECT swap_id FROM fomo_paper_trades WHERE swap_id IS NOT NULL")}
    opened = skipped = capped = 0
    newest = since
    for swap_id, mint, ts, size_usd in rows:
        newest = max(newest, float(ts))
        if swap_id in seen or not _is_tradeable_mint(mint):
            continue  # déjà répliqué / faux mint = jamais ré-ouvert
        if now - ts > REPL_ENTRY_WINDOW_S:
            skipped += 1  # entrée > 15 min après le swap = hors règle validée
            continue
        if n_open >= REPL_MAX_OPEN:
            capped += 1   # exposition bornée : skip, noté (pas de file)
            continue
        r = con_live.execute(
            "SELECT MIN(time) FROM fomo_ohlcv WHERE asset=? AND period='1h'",
            (mint,)).fetchone()
        if not r or not r[0] or now - r[0] / 1000.0 < REPL_MIN_AGE_S:
            skipped += 1  # age < 7j ou pas de 1re bougie 1h = non vérifiable
            continue
        # l'entrée = le dernier close 1h, sinon le dernier tick
        r = con_live.execute(
            "SELECT time, close FROM fomo_ohlcv WHERE asset=? AND period='1h' "
            "ORDER BY time DESC LIMIT 1", (mint,)).fetchone()
        ts_px = r[0] / 1000.0 if r and r[0] else None
        px = float(r[1]) if r and r[1] else None
        if not px:
            r = con_live.execute(
                "SELECT ts_s, priceUsd FROM fomo_ticks WHERE mint=? "
                "ORDER BY ts_s DESC LIMIT 1", (mint,)).fetchone()
            if r and r[1]:
                ts_px, px = float(r[0]), float(r[1])
        if not px or px <= 0 or not ts_px or now - ts_px > 2 * 3600:
            skipped += 1  # pas de prix vivant = pas d'entrée (fake forward)
            continue
        tk = resolve_ticker(con_live, mint)
        con.execute(
            "INSERT INTO fomo_paper_trades (mint, ticker, rule, horizon, "
            "entry_ts, entry_price, status, opened_at, swap_id) "
            "VALUES (?,?,?,?,?,?, 'OPEN', ?, ?)",
            (mint, tk, REPL_RULE, "24h", now, px, now, swap_id))
        con.commit()  # COMMIT explicite par swap (pas de transaction fantôme)
        seen.add(swap_id)
        n_open += 1
        opened += 1
        print(f"[repl] OPEN derek518 {tk} ({mint[:12]}…) "
              f"swap={size_usd:.0f}$ @ {px:.8g} (hold 24h)", flush=True)
    if newest > since:
        con.execute("INSERT INTO fomo_paper_state (key, value) "
                    "VALUES ('derek_last_ts', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(newest),))
        con.commit()
    return opened, skipped, capped


def run_pass() -> None:
    now = time.time()
    con_live = open_live()
    con = open_paper()
    have = {r[0] for r in con.execute(
        "SELECT DISTINCT mint FROM fomo_paper_trades")}

    # ── L'ENTRÉE : les mints frais pas encore dans le ledger (idempotent) ──
    n_opened, n_skipped = 0, 0
    for mint, _fs in fresh_mints(con_live, now):
        if mint in have:
            continue  # un mint déjà dans la table ne se ré-ouvre JAMAIS
        ts_px, px = last_price(con_live, mint)
        if not px or px <= 0 or not ts_px:
            continue  # pas de prix = pas d'entrée
        if now - ts_px > 2 * 3600:
            # le garde forward-first : un dernier prix > 2h = un marché
            # mort (token découvert tard, déjà rug/gradué) — on n'entre
            # PAS, entrer sur un prix qui ne bouge plus = du fake forward
            n_skipped += 1
            continue
        tk = resolve_ticker(con_live, mint)
        for rule, _h in HORIZONS:
            con.execute(
                "INSERT INTO fomo_paper_trades (mint, ticker, rule, horizon, "
                "entry_ts, entry_price, status, opened_at) "
                "VALUES (?,?,?,?,?,?, 'OPEN', ?)",
                (mint, tk, rule, rule, now, float(px), now))
        con.commit()  # COMMIT explicite par mint (pas de transaction fantôme)
        have.add(mint)
        n_opened += 1
        print(f"[paper] OPEN {tk} ({mint[:12]}…) @ {px:.8g} "
              f"× 3 règles 24h/48h/72h", flush=True)

    # ── LA RÉPLICATION derek518 : les swaps frais → OPEN (idempotent) ──
    con_swaps = open_swaps()
    rep_open, rep_skip, rep_cap = replication_derek(con, con_live, con_swaps, now)
    con_swaps.close()

    # ── LA SORTIE : la gestion de chaque trade OPEN ──
    n_closed_rug, n_closed_horizon = 0, 0
    opens = con.execute(
        "SELECT id, mint, ticker, rule, horizon, entry_ts, entry_price, "
        "max_multiple FROM fomo_paper_trades WHERE status='OPEN'").fetchall()
    by_mint: dict[str, list] = {}
    for row in opens:
        by_mint.setdefault(row[1], []).append(row)

    for mint, rows in by_mint.items():
        ts_px, px = last_price(con_live, mint)
        if not px or px <= 0 or not ts_px:
            continue
        entry_ts0 = min(r[5] for r in rows)
        hist_max = max_since_entry(con_live, mint, entry_ts0)
        for (tid, _m, tk, rule, horizon, entry_ts, entry_px, max_m) in rows:
            mult = px / entry_px if entry_px else 0.0
            max_m = max(max_m or 0.0, hist_max, mult)
            if mult < ANTI_RUG_TRIGGER * max_m and max_m >= ANTI_RUG_MIN_MAX:
                # le GARDE ANTI-RUG : le trailing ne sert que de garde —
                # il écrase l'horizon (un rug = on sort, les 3 règles)
                # le GARDE ANTI-RUG : le trailing ne sert que de garde —
                # il écrase l'horizon (un rug = on sort, les 3 règles).
                # rule reste INTACT : l'écraser fausserait le WR par règle
                # (chaque bucket ne garderait que les survivants anti-rug)
                con.execute(
                    "UPDATE fomo_paper_trades SET exit_ts=?, exit_price=?, "
                    "multiple=?, max_multiple=?, status='CLOSED', "
                    "closed_at=? WHERE id=?",
                    (ts_px, px, mult, max_m, now, tid))
                n_closed_rug += 1
                print(f"[paper] CLOSED anti-rug {tk} {rule} "
                      f"mult={mult:.2f}x max={max_m:.2f}x", flush=True)
            elif horizon and now >= entry_ts + dict(HORIZONS).get(horizon, 0):
                # la SORTIE TEMPS-FIXE : l'horizon écrase le trailing
                con.execute(
                    "UPDATE fomo_paper_trades SET exit_ts=?, exit_price=?, "
                    "multiple=?, max_multiple=?, status='CLOSED', closed_at=? "
                    "WHERE id=?", (ts_px, px, mult, max_m, now, tid))
                n_closed_horizon += 1
                print(f"[paper] CLOSED {rule} {tk} mult={mult:.2f}x "
                      f"max={max_m:.2f}x", flush=True)
            else:
                con.execute(
                    "UPDATE fomo_paper_trades SET multiple=?, max_multiple=? "
                    "WHERE id=?", (mult, max_m, tid))
        con.commit()  # COMMIT explicite par mint

    n_open = con.execute(
        "SELECT COUNT(*) FROM fomo_paper_trades WHERE status='OPEN'").fetchone()[0]
    n_tot = con.execute("SELECT COUNT(*) FROM fomo_paper_trades").fetchone()[0]
    print(f"[paper] passe : +{n_opened} mints ouverts, {n_skipped} sautés "
          f"(prix > 2h), {n_closed_rug} anti-rug, {n_closed_horizon} horizon, "
          f"repl +{rep_open} (derek518 : {rep_skip} hors-fenêtre/filtre, "
          f"{rep_cap} cap) — ledger {n_tot} lignes ({n_open} OPEN)", flush=True)
    con.close()
    con_live.close()


def report() -> None:
    con = open_paper()
    n_tot, n_open = con.execute(
        "SELECT COUNT(*), SUM(status='OPEN') FROM fomo_paper_trades"
    ).fetchone()
    n_open = n_open or 0
    print(f"LEDGER FORWARD fomo — {n_tot} trades ({n_open} OPEN, "
          f"{n_tot - n_open} CLOSED)")
    if not n_tot:
        return
    rules = con.execute(
        "SELECT rule, COUNT(*), SUM(status='OPEN') FROM fomo_paper_trades "
        "GROUP BY rule ORDER BY rule").fetchall()
    print(f"{'rule':<10}{'n':>5}{'open':>6}{'WR':>8}"
          f"{'médiane':>10}{'moyenne':>10}")
    for rule, n, o in rules:
        closed = [r[0] for r in con.execute(
            "SELECT multiple FROM fomo_paper_trades "
            "WHERE rule=? AND status='CLOSED' AND multiple IS NOT NULL",
            (rule,))]
        wr = (sum(1 for m in closed if m >= 1.0) / len(closed) * 100) if closed else 0.0
        med = statistics.median(closed) if closed else 0.0
        mean = (sum(closed) / len(closed)) if closed else 0.0
        print(f"{rule:<10}{n:>5}{o or 0:>6}{wr:>7.1f}%"
              f"{med:>9.2f}x{mean:>9.2f}x")
    # la ligne dédiée réplication : sépare derek518 des règles de détection
    rep = con.execute(
        "SELECT COUNT(*), SUM(status='OPEN') FROM fomo_paper_trades "
        "WHERE rule='replication_derek'").fetchone()
    print(f"REPLICATION derek518 : {rep[1] or 0} OPEN / {REPL_MAX_OPEN} cap, "
          f"{rep[0]} trades au total (idempotent par swap_id, hold 24h+anti-rug)")
    opens = con.execute(
        "SELECT ticker, rule, multiple, max_multiple FROM fomo_paper_trades "
        "WHERE status='OPEN' ORDER BY max_multiple DESC LIMIT 12").fetchall()
    if opens:
        print("OPEN (top max_multiple) :")
        for tk, rule, m, mm in opens:
            print(f"  {tk:<12}{rule:<5} cur={(m or 0):.2f}x  "
                  f"max={(mm or 0):.2f}x")
    con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="une passe du ledger")
    ap.add_argument("--report", action="store_true", help="l'état du ledger")
    args = ap.parse_args()
    if args.run:
        run_pass()
    if args.report or not (args.run or args.report):
        report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
