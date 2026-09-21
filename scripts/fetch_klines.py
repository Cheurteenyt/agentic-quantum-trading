#!/usr/bin/env python3
"""Telechargement des bougies OHLCV publiques Aster vers un warehouse SQLite.

Contexte : aucune campagne de backtest ne vaut quoi que ce soit sans VRAIES
bougies. Ce script est le seul chemin propre pour en obtenir, avec provenance.

Principes (identiques a scripts/refresh_aster_cache.py) :
  - `--check` est le mode par DEFAUT : lecture seule, n'ecrit RIEN.
  - Rate limiting systematique entre les appels API publics.
  - Aucune authentification : endpoint public read-only uniquement.
  - Jamais `except: pass`, timeouts partout.

Garanties du warehouse :
  - PRIMARY KEY (symbol, interval, open_time) : un re-fetch ne duplique jamais.
  - CHECK SQL sur prix > 0, high >= low, volume >= 0 : le schema defend, la
    discipline humaine ne suffit pas.
  - snapshot_id stocke avec chaque barre : sans provenance, un run n'est pas
    reproductible.
  - detect_gaps : un trou dans les bougies fausse SILENCIEUSEMENT un backtest.

Stdlib pure (urllib.request, sqlite3, json, argparse, time).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.baselines import Bar  # noqa: E402

ASTER_BASE = "https://fapi.asterdex.com"
DB_PATH = ROOT / "data" / "warehouse" / "klines.db"

SCHEMA_VERSION = 1
MIN_SLEEP_S = 0.25
DEFAULT_TIMEOUT = 15.0
MAX_LIMIT = 1500
USER_AGENT = "trading-agent-fetch-klines/1.0 (stdlib urllib)"
SOURCE = "aster_public_klines_fapi_v3"

# Duree theorique de chaque interval en millisecondes. Sert de base a
# detect_gaps : sans duree attendue, un trou est indetectable.
INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 3 * 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 3_600_000,
    "2h": 2 * 3_600_000,
    "4h": 4 * 3_600_000,
    "6h": 6 * 3_600_000,
    "8h": 8 * 3_600_000,
    "12h": 12 * 3_600_000,
    "1d": 86_400_000,
    "3d": 3 * 86_400_000,
    "1w": 7 * 86_400_000,
}


class AsterFetchError(RuntimeError):
    """Echec d'un appel HTTP public Aster. Jamais avale silencieusement."""


class KlineParseError(ValueError):
    """Kline malformee. On leve plutot que de filtrer : une serie trouee en
    silence produit un backtest plausible et faux."""


def interval_ms(interval: str) -> int:
    """Duree theorique d'un interval, en ms. Leve si l'interval est inconnu."""
    key = (interval or "").strip()
    if key not in INTERVAL_MS:
        raise ValueError(f"interval inconnu: {interval!r}")
    return INTERVAL_MS[key]


# --------------------------------------------------------------- HTTP bas niveau


def http_get_json(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable[..., Any] | None = None,
) -> Any:
    """GET JSON avec timeout. Toute erreur reseau devient AsterFetchError."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise AsterFetchError(f"HTTP {exc.code} sur {url}") from exc
    except urllib.error.URLError as exc:
        raise AsterFetchError(f"reseau indisponible sur {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise AsterFetchError(f"timeout ({timeout}s) sur {url}") from exc
    except OSError as exc:
        raise AsterFetchError(f"erreur socket sur {url}: {exc}") from exc

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AsterFetchError(f"reponse non-JSON depuis {url}") from exc


# ------------------------------------------------------------------- warehouse


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS klines (
    symbol      TEXT    NOT NULL,
    interval    TEXT    NOT NULL,
    open_time   INTEGER NOT NULL,
    open        REAL    NOT NULL CHECK (open  > 0),
    high        REAL    NOT NULL CHECK (high  > 0),
    low         REAL    NOT NULL CHECK (low   > 0),
    close       REAL    NOT NULL CHECK (close > 0),
    volume      REAL    NOT NULL CHECK (volume >= 0),
    close_time  INTEGER NOT NULL,
    snapshot_id TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    fetched_at  REAL    NOT NULL,
    CHECK (high >= low),
    CHECK (open_time > 0),
    PRIMARY KEY (symbol, interval, open_time)
);
"""

META_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

SNAPSHOT_SQL = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    symbol      TEXT NOT NULL,
    interval    TEXT NOT NULL,
    min_ts      INTEGER NOT NULL,
    max_ts      INTEGER NOT NULL,
    bar_count   INTEGER NOT NULL,
    source      TEXT NOT NULL,
    created_at  REAL NOT NULL
);
"""


def init_db(path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Ouvre (et cree si besoin) le warehouse. Retourne une connexion prete.

    `:memory:` est accepte tel quel, ce qui rend les tests hermetiques.
    """
    if str(path) == ":memory:":
        con = sqlite3.connect(":memory:")
    else:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    # Les CHECK ne servent a rien si les contraintes ne sont pas appliquees.
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(CREATE_SQL + META_SQL + SNAPSHOT_SQL)
    con.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_klines_lookup "
        "ON klines(symbol, interval, open_time)"
    )
    con.commit()
    return con


# --------------------------------------------------------------------- parsing


def parse_kline_row(row: Any, index: int = 0) -> tuple:
    """Valide une ligne brute klines -> tuple normalise.

    Format attendu : [openTime, open, high, low, close, volume, closeTime, ...]
    Leve KlineParseError sur toute anomalie : mieux vaut une erreur bruyante
    qu'un backtest silencieusement faux.
    """
    if row is None or not isinstance(row, (list, tuple)) or len(row) < 6:
        raise KlineParseError(f"kline #{index}: ligne trop courte ({row!r})")
    try:
        open_time = int(row[0])
        o, h, l, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
        v = float(row[5])
    except (TypeError, ValueError) as exc:
        raise KlineParseError(f"kline #{index}: valeur non numerique ({row!r})") from exc

    close_time = open_time
    if len(row) >= 7:
        try:
            close_time = int(row[6])
        except (TypeError, ValueError) as exc:
            raise KlineParseError(f"kline #{index}: closeTime invalide ({row[6]!r})") from exc

    for name, price in (("open", o), ("high", h), ("low", l), ("close", c)):
        if not price > 0:
            raise KlineParseError(f"kline #{index}: {name}={price} <= 0")
    if v < 0:
        raise KlineParseError(f"kline #{index}: volume negatif ({v})")
    if h < l:
        raise KlineParseError(f"kline #{index}: high {h} < low {l}")
    if open_time <= 0:
        raise KlineParseError(f"kline #{index}: open_time invalide ({open_time})")

    return (open_time, o, h, l, c, v, close_time)


# --------------------------------------------------------------------- fetchers


def fetch_klines(
    symbol: str,
    interval: str = "1h",
    limit: int = MAX_LIMIT,
    base_url: str = ASTER_BASE,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable[..., Any] | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
) -> list[list]:
    """Recupere les klines brutes depuis l'endpoint PUBLIC read-only.

    `limit` est borne a MAX_LIMIT (contrainte API) : on ne demande jamais plus
    que ce que le serveur accepte, sinon la reponse est tronquee sans le dire.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbole vide")
    interval_ms(interval)  # valide l'interval avant de sortir sur le reseau
    lim = max(1, min(int(limit), MAX_LIMIT))

    url = f"{base_url}/fapi/v3/klines?symbol={sym}&interval={interval}&limit={lim}"
    if start_time is not None:
        url += f"&startTime={int(start_time)}"
    if end_time is not None:
        url += f"&endTime={int(end_time)}"

    payload = http_get_json(url, timeout=timeout, opener=opener)
    if not isinstance(payload, list):
        raise AsterFetchError(f"reponse klines inattendue pour {sym} ({type(payload).__name__})")
    return payload


def fetch_klines_paginated(
    symbol: str,
    interval: str = "1h",
    target_bars: int = 3000,
    base_url: str = ASTER_BASE,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable[..., Any] | None = None,
) -> tuple[list, dict]:
    """Recupere `target_bars` bougies en paginant par blocs de MAX_LIMIT.

    Retourne (raw_rows, meta) ou meta contient au moins :
      {'requests', 'fetched', 'first_ts', 'last_ts', 'reached_target', 'reason'}

    - Respecte MIN_SLEEP_S entre deux requetes (aucune pause avant la premiere).
    - Decale start_time = derniere open_time + interval_ms(interval) : aucun
      recouvrement, donc aucune bougie comptee deux fois.
    - S'arrete proprement si l'API renvoie moins que demande (fin d'historique).
    - Une erreur reseau (AsterFetchError) arrete la pagination SANS lever :
      on renvoie ce qui a deja ete recupere, meta['reason'] = 'error: ...'.
      Mieux vaut stocker 3000 bougies sur 5000 voulues que zero.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbole vide")
    step = interval_ms(interval)
    target = max(1, int(target_bars))

    rows: list = []
    seen_times: set[int] = set()
    requests_done = 0
    reason = "target atteint"
    reached = False
    # Premiere requete calee assez tot pour couvrir la fenetre demandee :
    # sans startTime l'API renvoie la fin de l'historique et la pagination
    # avancerait dans le vide.
    start_time: int | None = int(time.time() * 1000) - (target + 2) * step

    while len(rows) < target:
        want = min(MAX_LIMIT, target - len(rows))
        if requests_done:
            time.sleep(MIN_SLEEP_S)
        try:
            page = fetch_klines(
                sym,
                interval=interval,
                limit=want,
                base_url=base_url,
                timeout=timeout,
                opener=opener,
                start_time=start_time,
            )
        except (AsterFetchError, ValueError) as exc:
            reason = f"error: {exc}"
            break
        requests_done += 1

        if not page:
            reason = "fin d'historique (page vide)"
            break

        fresh = []
        for row in page:
            try:
                open_time = int(row[0])
            except (TypeError, ValueError, IndexError) as exc:
                reason = f"error: kline malformee ({exc})"
                page = []
                break
            if open_time in seen_times:
                continue
            seen_times.add(open_time)
            fresh.append(row)
        if reason.startswith("error:"):
            break

        rows.extend(fresh)
        if not fresh:
            reason = "fin d'historique (aucune bougie nouvelle)"
            break

        last_open = max(int(r[0]) for r in fresh)
        start_time = last_open + step

        if len(page) < want:
            reason = "fin d'historique (page incomplete)"
            break

    if len(rows) >= target:
        reached = True
        reason = "target atteint"

    times = [int(r[0]) for r in rows]
    meta = {
        "symbol": sym,
        "interval": interval,
        "target_bars": target,
        "requests": requests_done,
        "fetched": len(rows),
        "first_ts": min(times) if times else None,
        "last_ts": max(times) if times else None,
        "reached_target": reached,
        "reason": reason,
    }
    return rows, meta


# ---------------------------------------------------------------- provenance


def snapshot_id_for(symbol: str, interval: str, con: sqlite3.Connection) -> str:
    """Identifiant de provenance derive de l'etat REEL du warehouse.

    Forme : aster-{symbol}-{interval}-{min_ts}-{max_ts}-{count}
    Deterministe pour un contenu donne, et il change des que les donnees
    changent : c'est exactement ce qu'on veut pour tracer un run.
    """
    sym = (symbol or "").strip().upper()
    row = con.execute(
        "SELECT MIN(open_time) AS lo, MAX(open_time) AS hi, COUNT(*) AS n "
        "FROM klines WHERE symbol = ? AND interval = ?",
        (sym, interval),
    ).fetchone()
    n = int(row["n"] or 0)
    lo = int(row["lo"]) if row["lo"] is not None else 0
    hi = int(row["hi"]) if row["hi"] is not None else 0
    return f"aster-{sym}-{interval}-{lo}-{hi}-{n}"


def snapshot_id_for_rows(symbol: str, interval: str, rows: Sequence[tuple]) -> str:
    """Meme forme que snapshot_id_for, mais calcule sur un lot en memoire."""
    sym = (symbol or "").strip().upper()
    if not rows:
        return f"aster-{sym}-{interval}-0-0-0"
    times = [r[0] for r in rows]
    return f"aster-{sym}-{interval}-{min(times)}-{max(times)}-{len(rows)}"


# ------------------------------------------------------------------- stockage


def store_klines(
    con: sqlite3.Connection,
    symbol: str,
    interval: str,
    raw: Sequence[Any],
    snapshot_id: str | None = None,
) -> dict:
    """Insere un lot de klines. Renvoie {'inserted', 'skipped', 'gaps'}.

    INSERT OR IGNORE + PRIMARY KEY (symbol, interval, open_time) : un re-fetch
    du meme intervalle ne cree jamais de doublon, il compte des `skipped`.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbole vide")
    interval_ms(interval)

    parsed = [parse_kline_row(row, i) for i, row in enumerate(raw)]
    parsed.sort(key=lambda r: r[0])

    snap = snapshot_id or snapshot_id_for_rows(sym, interval, parsed)
    now = time.time()

    inserted = 0
    skipped = 0
    for open_time, o, h, l, c, v, close_time in parsed:
        cur = con.execute(
            "INSERT OR IGNORE INTO klines "
            "(symbol, interval, open_time, open, high, low, close, volume, "
            " close_time, snapshot_id, source, fetched_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (sym, interval, open_time, o, h, l, c, v, close_time, snap, SOURCE, now),
        )
        if cur.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    if parsed:
        con.execute(
            "INSERT OR REPLACE INTO snapshots "
            "(snapshot_id, symbol, interval, min_ts, max_ts, bar_count, source, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                snap,
                sym,
                interval,
                min(r[0] for r in parsed),
                max(r[0] for r in parsed),
                len(parsed),
                SOURCE,
                now,
            ),
        )
    con.commit()

    return {
        "inserted": inserted,
        "skipped": skipped,
        "snapshot_id": snap,
        "gaps": detect_gaps(con, sym, interval),
    }


# ---------------------------------------------------------------------- lecture


def load_bars(
    con: sqlite3.Connection,
    symbol: str,
    interval: str,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> list[Bar]:
    """Charge des objets `Bar` (baselines.py) tries par timestamp croissant.

    Contrat : la sortie est strictement equivalente a ce que produirait
    `bars_from_klines` sur les klines brutes correspondantes.
    """
    sym = (symbol or "").strip().upper()
    sql = (
        "SELECT open_time, open, high, low, close, volume FROM klines "
        "WHERE symbol = ? AND interval = ?"
    )
    params: list[Any] = [sym, interval]
    if start_ts is not None:
        sql += " AND open_time >= ?"
        params.append(int(start_ts))
    if end_ts is not None:
        sql += " AND open_time <= ?"
        params.append(int(end_ts))
    sql += " ORDER BY open_time ASC"

    return [
        Bar(
            ts=int(r["open_time"]),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=float(r["volume"]),
        )
        for r in con.execute(sql, params).fetchall()
    ]


def detect_gaps(
    con: sqlite3.Connection, symbol: str, interval: str
) -> list[tuple[int, int]]:
    """Trous dans la serie : liste de (dernier_ts_avant, premier_ts_apres).

    Un trou fausse silencieusement un backtest (le moteur croit a une
    continuite qui n'existe pas). On compare chaque ecart a la duree theorique
    de l'interval : tout ecart > 1 pas est signale.
    """
    step = interval_ms(interval)
    sym = (symbol or "").strip().upper()
    rows = con.execute(
        "SELECT open_time FROM klines WHERE symbol = ? AND interval = ? "
        "ORDER BY open_time ASC",
        (sym, interval),
    ).fetchall()

    gaps: list[tuple[int, int]] = []
    prev: int | None = None
    for r in rows:
        ts = int(r["open_time"])
        if prev is not None and ts - prev > step:
            gaps.append((prev, ts))
        prev = ts
    return gaps


def warehouse_stats(con: sqlite3.Connection) -> dict:
    """Etat du warehouse : total, series presentes, trous, provenance."""
    total = int(con.execute("SELECT COUNT(*) FROM klines").fetchone()[0])
    series: list[dict] = []
    rows = con.execute(
        "SELECT symbol, interval, COUNT(*) AS n, MIN(open_time) AS lo, "
        "MAX(open_time) AS hi FROM klines GROUP BY symbol, interval "
        "ORDER BY symbol, interval"
    ).fetchall()
    for r in rows:
        sym, itv = r["symbol"], r["interval"]
        gaps = detect_gaps(con, sym, itv)
        series.append(
            {
                "symbol": sym,
                "interval": itv,
                "bars": int(r["n"]),
                "min_ts": int(r["lo"]),
                "max_ts": int(r["hi"]),
                "gaps": len(gaps),
                "snapshot_id": snapshot_id_for(sym, itv, con),
            }
        )
    ver = con.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    return {
        "schema_version": int(ver["value"]) if ver else None,
        "total_bars": total,
        "series_count": len(series),
        "series": series,
    }


# ------------------------------------------------------------------ operations


def fetch_and_store(
    con: sqlite3.Connection,
    symbols: Sequence[str],
    interval: str = "1h",
    limit: int = MAX_LIMIT,
    base_url: str = ASTER_BASE,
    timeout: float = DEFAULT_TIMEOUT,
    sleep_s: float = MIN_SLEEP_S,
    fetcher: Callable[..., list] | None = None,
) -> dict:
    """Boucle fetch -> store sur plusieurs symboles, avec rate limiting.

    `fetcher` permet d'injecter une source (tests) sans toucher au reseau.
    """
    fetch_fn = fetcher or fetch_klines
    results: dict[str, Any] = {"ok": 0, "failed": [], "details": {}}

    for i, sym in enumerate(symbols):
        if i:
            # Rate limiting : jamais moins de MIN_SLEEP_S entre deux appels.
            time.sleep(max(MIN_SLEEP_S, sleep_s))
        try:
            raw = fetch_fn(
                sym,
                interval=interval,
                limit=limit,
                base_url=base_url,
                timeout=timeout,
            )
            res = store_klines(con, sym, interval, raw)
        except (AsterFetchError, KlineParseError, ValueError, sqlite3.Error) as exc:
            results["failed"].append(sym)
            results["details"][sym] = {"error": str(exc)}
            print(f"  ! {sym} : {exc}")
            continue
        results["ok"] += 1
        results["details"][sym] = res
        print(
            f"  · {sym} {interval} : +{res['inserted']} nouvelles, "
            f"{res['skipped']} deja presentes, {len(res['gaps'])} trou(s)  "
            f"[{res['snapshot_id']}]"
        )
    return results


# ------------------------------------------------------------------------- CLI


def run_check(db_path: Path | str = DB_PATH) -> int:
    """Mode par defaut : lecture seule, aucune ecriture de donnees."""
    print("=== Etat du warehouse de klines (lecture seule) ===")
    print(f"  base : {db_path}")
    p = Path(db_path) if str(db_path) != ":memory:" else None
    if p is not None and not p.exists():
        print("  base ABSENTE — rien n'a encore ete telecharge.")
        print("  Remede : python scripts/fetch_klines.py --fetch --symbols BTCUSDT "
              "--interval 1h --limit 500")
        return 1

    con = init_db(db_path)
    try:
        stats = warehouse_stats(con)
        print(f"  schema v{stats['schema_version']} — {stats['total_bars']} barres, "
              f"{stats['series_count']} serie(s)")
        if not stats["series"]:
            print("  Aucune serie stockee.")
            return 1
        for s in stats["series"]:
            verdict = "OK" if s["gaps"] == 0 else f"{s['gaps']} TROU(S)"
            print(f"  · {s['symbol']:<12} {s['interval']:<4} {s['bars']:>6} barres  "
                  f"[{s['min_ts']} -> {s['max_ts']}]  -> {verdict}")
            print(f"      provenance : {s['snapshot_id']}")
        holes = sum(s["gaps"] for s in stats["series"])
        if holes:
            print(f"\nRESULTAT : {holes} trou(s) detecte(s) — backtest non fiable en l'etat.")
            return 1
        print("\nRESULTAT : warehouse continu, exploitable.")
        return 0
    finally:
        con.close()


def run_export(symbol: str, interval: str, db_path: Path | str = DB_PATH) -> int:
    """Statistiques d'une serie. Volontairement PAS de dump massif."""
    p = Path(db_path) if str(db_path) != ":memory:" else None
    if p is not None and not p.exists():
        print(f"  base absente : {db_path}")
        return 1
    con = init_db(db_path)
    try:
        sym = symbol.strip().upper()
        bars = load_bars(con, sym, interval)
        if not bars:
            print(f"  aucune barre pour {sym} {interval}")
            return 1
        closes = [b.close for b in bars]
        gaps = detect_gaps(con, sym, interval)
        print(f"=== {sym} {interval} ===")
        print(f"  barres      : {len(bars)}")
        print(f"  periode     : {bars[0].ts} -> {bars[-1].ts}")
        print(f"  close min   : {min(closes)}")
        print(f"  close max   : {max(closes)}")
        print(f"  close first : {closes[0]}")
        print(f"  close last  : {closes[-1]}")
        print(f"  trous       : {len(gaps)}")
        for lo, hi in gaps[:10]:
            print(f"      trou {lo} -> {hi}")
        print(f"  provenance  : {snapshot_id_for(sym, interval, con)}")
        return 0 if not gaps else 1
    finally:
        con.close()


def run_fetch_range(
    symbol: str,
    interval: str,
    target_bars: int,
    db_path: Path | str = DB_PATH,
    base_url: str = ASTER_BASE,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable[..., Any] | None = None,
) -> int:
    """Pagination + stockage d'une serie longue, avec resume lisible."""
    sym = (symbol or "").strip().upper()
    print(f"=== Fetch pagine {sym} {interval} — cible {target_bars} bougies ===")
    print(f"  base : {db_path}  |  pause {MIN_SLEEP_S}s entre requetes")

    raw, meta = fetch_klines_paginated(
        sym,
        interval=interval,
        target_bars=target_bars,
        base_url=base_url,
        timeout=timeout,
        opener=opener,
    )

    print(f"  requetes    : {meta['requests']}")
    print(f"  recuperees  : {meta['fetched']} / {meta['target_bars']}")
    print(f"  plage       : {meta['first_ts']} -> {meta['last_ts']}")
    print(f"  cible       : {'ATTEINTE' if meta['reached_target'] else 'NON atteinte'}")
    print(f"  motif d'arret : {meta['reason']}")

    if not raw:
        print("  RESULTAT : rien a stocker.")
        return 1

    con = init_db(db_path)
    try:
        parsed = [parse_kline_row(row, i) for i, row in enumerate(raw)]
        snap = snapshot_id_for_rows(sym, interval, parsed)
        res = store_klines(con, sym, interval, raw, snapshot_id=snap)
    finally:
        con.close()

    print(f"  stockage    : +{res['inserted']} nouvelles, {res['skipped']} deja presentes")
    print(f"  trous       : {len(res['gaps'])}")
    print(f"  provenance  : {res['snapshot_id']}")
    if meta["reason"].startswith("error:"):
        return 1
    return 0 if meta["reached_target"] else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Telecharge et stocke les klines publiques Aster. "
                    "Mode par defaut : --check (lecture seule).",
    )
    p.add_argument("--check", action="store_true",
                   help="Mode par defaut : etat du warehouse, n'ecrit rien.")
    p.add_argument("--fetch", action="store_true",
                   help="Telecharge et stocke les klines des --symbols.")
    p.add_argument("--fetch-range", default="", metavar="SYMBOL",
                   help="Telecharge en PAGINANT jusqu'a --target-bars bougies.")
    p.add_argument("--target-bars", type=int, default=3000,
                   help="Nombre de bougies visees par --fetch-range (defaut 3000).")
    p.add_argument("--export", default="", metavar="SYMBOL",
                   help="Affiche les statistiques d'une serie (pas de dump).")
    p.add_argument("--symbols", default="BTCUSDT",
                   help="Liste separee par des virgules (ex: BTCUSDT,ETHUSDT).")
    p.add_argument("--interval", default="1h",
                   help=f"Interval de bougie ({'/'.join(sorted(INTERVAL_MS))}).")
    p.add_argument("--limit", type=int, default=MAX_LIMIT,
                   help=f"Bougies par requete (max {MAX_LIMIT}).")
    p.add_argument("--sleep", type=float, default=MIN_SLEEP_S,
                   help=f"Pause entre appels API (min {MIN_SLEEP_S}s).")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                   help="Timeout HTTP en secondes.")
    p.add_argument("--base-url", default=ASTER_BASE, help="Base API publique.")
    p.add_argument("--db", default=str(DB_PATH), help="Chemin du warehouse SQLite.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        interval_ms(args.interval)
    except ValueError as exc:
        print(f"  ECHEC : {exc}")
        return 2

    if args.export:
        return run_export(args.export, args.interval, db_path=args.db)

    if args.fetch_range:
        return run_fetch_range(
            args.fetch_range,
            args.interval,
            args.target_bars,
            db_path=args.db,
            base_url=args.base_url,
            timeout=args.timeout,
        )

    if not args.fetch:
        return run_check(db_path=args.db)

    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not syms:
        print("  ECHEC : aucun symbole fourni")
        return 2

    print(f"=== Telechargement klines {args.interval} — {len(syms)} symbole(s) ===")
    print(f"  base : {args.db}  |  pause {max(MIN_SLEEP_S, args.sleep)}s entre appels")
    con = init_db(args.db)
    try:
        res = fetch_and_store(
            con,
            syms,
            interval=args.interval,
            limit=args.limit,
            base_url=args.base_url,
            timeout=args.timeout,
            sleep_s=args.sleep,
        )
    finally:
        con.close()

    print(f"  succes : {res['ok']} / {len(syms)}")
    if res["failed"]:
        print(f"  en echec : {', '.join(res['failed'])}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
