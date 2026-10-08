#!/usr/bin/env python3
"""Rafraichissement des caches publics Aster (exchangeInfo + fundingRate).

Contexte : les caches locaux sont geles depuis juin 2026 et
`backend/services/backtest_v2/costs.py` refuse toute donnee de funding de plus
de MAX_FUNDING_AGE_DAYS jours. Sans refresh, aucune campagne de backtest.

Principes :
  - `--check` est le mode par DEFAUT : lecture seule, n'ecrit RIEN.
  - Toute ecriture est atomique (fichier temporaire + os.replace).
  - Toute ecrasement est precede d'un backup horodate.
  - Rate limiting systematique entre les appels API publics.
  - Aucune authentification : endpoints publics read-only uniquement.

Stdlib pure (urllib.request, json, argparse).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request

import aster_rate  # le compteur X-MBX-USED-WEIGHT-1M (audit docs/24)
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ASTER_BASE = "https://fapi.asterdex.com"

ROOT = Path(__file__).resolve().parents[1]
ASTER_DIR = ROOT / "backend" / "services" / "onchain" / "aster"
EXCHANGE_INFO_CACHE = ASTER_DIR / "aster_public_exchange_info_cache.json"
FUNDING_CACHE = ASTER_DIR / "aster_public_funding_history_cache.json"

MAX_FUNDING_AGE_DAYS = 30.0
MIN_SLEEP_S = 0.2
DEFAULT_TIMEOUT = 10.0
USER_AGENT = "trading-agent-refresh-aster-cache/1.0 (stdlib urllib)"

FUNDING_SOURCE = "aster_public_funding_history_fapi_v3"


class AsterFetchError(RuntimeError):
    """Echec d'un appel HTTP public Aster. Jamais avale silencieusement."""


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
            aster_rate.note_weight(getattr(resp, "headers", None), "refresh_cache")
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


# ------------------------------------------------------------------ cache utils


def cache_age_days(path: Path) -> float | None:
    """Age du cache en jours, None si le fichier est absent ou illisible.

    Utilise `cached_at` / `updated_at` du contenu quand disponible (c'est ce que
    lit costs.py) ; retombe sur le mtime du fichier sinon.
    """
    path = Path(path)
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    stamps: list[float] = []
    if isinstance(blob, dict):
        for key in ("cached_at", "updated_at"):
            val = blob.get(key)
            if isinstance(val, (int, float)) and val > 0:
                stamps.append(float(val))
        symbols = blob.get("symbols")
        if isinstance(symbols, dict):
            for entry in symbols.values():
                if isinstance(entry, dict):
                    val = entry.get("cached_at")
                    if isinstance(val, (int, float)) and val > 0:
                        stamps.append(float(val))

    if stamps:
        newest = max(stamps)
    else:
        try:
            newest = path.stat().st_mtime
        except OSError:
            return None
    return max(0.0, (time.time() - newest) / 86400.0)


def backup_existing(path: Path) -> Path | None:
    """Copie horodatee avant tout ecrasement. None si rien a sauvegarder."""
    path = Path(path)
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    n = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak-{stamp}-{n}")
        n += 1
    shutil.copy2(path, backup)
    return backup


def write_cache_atomic(path: Path, payload: dict) -> None:
    """Ecriture atomique : temporaire dans le meme dossier puis os.replace().

    Si la serialisation echoue, le fichier original reste strictement intact et
    aucun fichier temporaire ne subsiste.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{int(time.time() * 1000)}")
    try:
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"payload non serialisable pour {path}: {exc}") from exc
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except OSError:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError as cleanup_exc:  # pragma: no cover - rare
                print(f"  ! nettoyage du temporaire impossible: {cleanup_exc}")
        raise


# ------------------------------------------------------------------- API probes


def probe_api(
    base_url: str = ASTER_BASE,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable[..., Any] | None = None,
) -> dict:
    """Tape /fapi/v3/ping puis /fapi/v3/time. N'echoue jamais par exception."""
    out: dict[str, Any] = {
        "reachable": False,
        "latency_ms": None,
        "clock_drift_ms": None,
        "error": None,
    }
    t0 = time.time()
    try:
        http_get_json(f"{base_url}/fapi/v3/ping", timeout=timeout, opener=opener)
        out["latency_ms"] = round((time.time() - t0) * 1000.0, 1)
        out["reachable"] = True
    except AsterFetchError as exc:
        out["error"] = str(exc)
        return out

    time.sleep(MIN_SLEEP_S)
    try:
        payload = http_get_json(f"{base_url}/fapi/v3/time", timeout=timeout, opener=opener)
        server_ms = payload.get("serverTime") if isinstance(payload, dict) else None
        if isinstance(server_ms, (int, float)):
            out["clock_drift_ms"] = round(time.time() * 1000.0 - float(server_ms), 1)
        else:
            out["error"] = "reponse /time sans serverTime"
    except AsterFetchError as exc:
        out["error"] = f"ping ok mais /time en echec: {exc}"
    return out


# -------------------------------------------------------------------- fetchers


def _norm_symbol_entry(raw: dict) -> dict:
    """Aplati un symbole exchangeInfo au format exact du cache existant."""
    filters = {f.get("filterType"): f for f in raw.get("filters", []) if isinstance(f, dict)}
    price = filters.get("PRICE_FILTER", {})
    lot = filters.get("LOT_SIZE", {})
    mlot = filters.get("MARKET_LOT_SIZE", {})
    notional = filters.get("MIN_NOTIONAL", {})
    pct = filters.get("PERCENT_PRICE", {})

    return {
        "base_asset": raw.get("baseAsset"),
        "contract_type": raw.get("contractType"),
        "exchange_info_status": "ok",
        "liquidation_fee_rate": raw.get("liquidationFee"),
        "lot_max_qty": lot.get("maxQty"),
        "lot_min_qty": lot.get("minQty"),
        "margin_asset": raw.get("marginAsset"),
        "market_lot_max_qty": mlot.get("maxQty"),
        "market_lot_min_qty": mlot.get("minQty"),
        "market_step_size": mlot.get("stepSize"),
        "market_take_bound": raw.get("marketTakeBound"),
        "max_num_algo_orders": raw.get("maxNumAlgoOrders"),
        "max_num_orders": raw.get("maxNumOrders"),
        "min_notional": notional.get("notional"),
        "order_types": ",".join(raw.get("orderTypes") or []),
        "percent_price_down": pct.get("multiplierDown"),
        "percent_price_up": pct.get("multiplierUp"),
        "price_max": price.get("maxPrice"),
        "price_min": price.get("minPrice"),
        "quote_asset": raw.get("quoteAsset"),
        "step_size": lot.get("stepSize"),
        "symbol": raw.get("symbol"),
        "symbol_status": raw.get("status"),
        "tick_size": price.get("tickSize"),
        "time_in_force": ",".join(raw.get("timeInForce") or []),
        "trigger_protect": raw.get("triggerProtect"),
    }


def fetch_exchange_info(
    base_url: str = ASTER_BASE,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable[..., Any] | None = None,
) -> dict:
    """Construit le payload cache exchangeInfo, format identique a l'existant."""
    payload = http_get_json(f"{base_url}/fapi/v3/exchangeInfo", timeout=timeout, opener=opener)
    raw_symbols = payload.get("symbols") if isinstance(payload, dict) else None
    if not isinstance(raw_symbols, list):
        raise AsterFetchError("exchangeInfo: champ 'symbols' absent ou invalide")

    symbols: dict[str, Any] = {}
    for raw in raw_symbols:
        if not isinstance(raw, dict):
            continue
        sym = raw.get("symbol")
        if not sym:
            continue
        symbols[str(sym)] = _norm_symbol_entry(raw)

    return {
        "cached_at": time.time(),
        "status": "ok",
        "symbol_count": len(symbols),
        "symbols": symbols,
    }


def fetch_funding_history(
    symbol: str,
    limit: int = 100,
    base_url: str = ASTER_BASE,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable[..., Any] | None = None,
) -> dict:
    """Renvoie le bloc `data` funding d'un symbole, format lu par costs.py."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbole vide")
    lim = max(1, min(int(limit), 1000))
    url = f"{base_url}/fapi/v3/fundingRate?symbol={sym}&limit={lim}"
    rows = http_get_json(url, timeout=timeout, opener=opener)
    return parse_funding_rows(sym, rows)


def parse_funding_rows(symbol: str, rows: Any) -> dict:
    """Transforme la reponse brute /fapi/v3/fundingRate en bloc `data`."""
    if not isinstance(rows, list) or not rows:
        return {
            "symbol": symbol,
            "status": "empty",
            "source": FUNDING_SOURCE,
            "cache_status": "miss",
            "funding_count": 0,
        }

    parsed: list[tuple[int, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            ts = int(row.get("fundingTime"))
            rate = float(row.get("fundingRate"))
        except (TypeError, ValueError):
            continue
        parsed.append((ts, rate))

    if not parsed:
        return {
            "symbol": symbol,
            "status": "empty",
            "source": FUNDING_SOURCE,
            "cache_status": "miss",
            "funding_count": 0,
        }

    parsed.sort(key=lambda p: p[0])
    rates = [r for _, r in parsed]
    avg_rate = sum(rates) / len(rates)
    latest_rate = rates[-1]
    # FIX lot2 (F12) : l'intervalle de funding est MESURÉ (médiane des gaps) —
    # les intervalles Aster ne sont pas universellement 8h.
    gaps = [b[0] - a[0] for a, b in zip(parsed, parsed[1:]) if b[0] > a[0]]
    if gaps:
        sg = sorted(gaps)
        mid = len(sg) // 2
        median_gap_ms = sg[mid] if len(sg) % 2 else 0.5 * (sg[mid - 1] + sg[mid])
        interval_h = median_gap_ms / 3_600_000.0
    else:
        interval_h = 8.0

    return {
        "symbol": symbol,
        "status": "ok",
        "source": FUNDING_SOURCE,
        "cache_status": "miss",
        "funding_count": len(parsed),
        "funding_interval_hours": interval_h,
        "first_funding_time": parsed[0][0],
        "last_funding_time": parsed[-1][0],
        "avg_funding_rate": avg_rate,
        "avg_funding_bps_per_8h": avg_rate * 10_000.0,
        "latest_funding_rate": latest_rate,
        "latest_funding_bps_per_8h": latest_rate * 10_000.0,
        "max_funding_rate": max(rates),
        "min_funding_rate": min(rates),
    }


# ------------------------------------------------------------------ operations


def load_json_safe(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  ! cache existant illisible ({exc}) — il sera reconstruit")
        return {}
    return blob if isinstance(blob, dict) else {}


def default_symbols(limit: int | None = None) -> list[str]:
    """Symboles connus du cache funding existant (a defaut de --symbols)."""
    blob = load_json_safe(FUNDING_CACHE)
    syms = sorted((blob.get("symbols") or {}).keys())
    if not syms:
        syms = ["BTCUSDT", "ETHUSDT"]
    return syms[:limit] if limit else syms


def refresh_funding(
    symbols: list[str],
    cache_path: Path = FUNDING_CACHE,
    limit: int = 100,
    base_url: str = ASTER_BASE,
    timeout: float = DEFAULT_TIMEOUT,
    sleep_s: float = MIN_SLEEP_S,
    opener: Callable[..., Any] | None = None,
) -> dict:
    """Rafraichit le cache funding pour `symbols`. Fusionne avec l'existant."""
    blob = load_json_safe(cache_path)
    existing = blob.get("symbols")
    merged: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}

    ok, failed = 0, []
    for i, sym in enumerate(symbols):
        if i:
            time.sleep(max(MIN_SLEEP_S, sleep_s))
        try:
            data = fetch_funding_history(
                sym, limit=limit, base_url=base_url, timeout=timeout, opener=opener
            )
        except (AsterFetchError, ValueError) as exc:
            failed.append(sym)
            print(f"  ! {sym} : {exc}")
            continue
        # FIX audit v3 (C13) : le cache est un SNAPSHOT live (diagnostic de
        # fraicheur) — JAMAIS l'historique de comptabilite : celle-ci lit
        # klines.db funding_history (append-only) via funding_series. Le
        # merged remplace le bloc du symbole : une moyenne de diagnostics,
        # pas une donnee historique.
        merged[sym] = {"cached_at": time.time(), "data": data}
        ok += 1
        print(f"  · {sym} : {data.get('funding_count', 0)} points, "
              f"moyenne {data.get('avg_funding_bps_per_8h', 0.0):.4f} bps/8h")

    if ok == 0:
        print("  Aucun symbole rafraichi : cache laisse intact.")
        return {"written": False, "ok": 0, "failed": failed, "backup": None}

    payload = {"symbols": merged, "updated_at": time.time()}
    backup = backup_existing(cache_path)
    write_cache_atomic(cache_path, payload)
    return {"written": True, "ok": ok, "failed": failed, "backup": backup}


def refresh_exchange_info(
    cache_path: Path = EXCHANGE_INFO_CACHE,
    base_url: str = ASTER_BASE,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable[..., Any] | None = None,
) -> dict:
    payload = fetch_exchange_info(base_url=base_url, timeout=timeout, opener=opener)
    backup = backup_existing(cache_path)
    write_cache_atomic(cache_path, payload)
    return {
        "written": True,
        "symbol_count": payload["symbol_count"],
        "backup": backup,
    }


# ------------------------------------------------------------------------- CLI


def _fmt_age(age: float | None) -> str:
    if age is None:
        return "ABSENT"
    return f"{age:.1f} jours"


def run_check(base_url: str = ASTER_BASE, timeout: float = DEFAULT_TIMEOUT) -> int:
    print("=== Verification des caches Aster (lecture seule, aucune ecriture) ===")
    stale = False
    for label, path in (
        ("exchangeInfo", EXCHANGE_INFO_CACHE),
        ("funding    ", FUNDING_CACHE),
    ):
        age = cache_age_days(path)
        verdict = "OK"
        if age is None:
            verdict = "MANQUANT"
            stale = True
        elif age > MAX_FUNDING_AGE_DAYS:
            verdict = f"PERIME (> {MAX_FUNDING_AGE_DAYS:.0f} j)"
            stale = True
        print(f"  {label} : age = {_fmt_age(age):>12}   -> {verdict}")
        print(f"      {path}")

    print("\n--- Sante de l'API publique Aster ---")
    probe = probe_api(base_url=base_url, timeout=timeout)
    if probe["reachable"]:
        drift = probe["clock_drift_ms"]
        print(f"  joignable : oui  (latence {probe['latency_ms']} ms"
              + (f", derive horloge {drift} ms)" if drift is not None else ")"))
        if probe["error"]:
            print(f"  avertissement : {probe['error']}")
    else:
        print(f"  joignable : NON — {probe['error']}")

    if stale:
        print("\nRESULTAT : au moins un cache est perime ou absent.")
        print("Rafraichir avec : python scripts/refresh_aster_cache.py --refresh-all --limit 50")
        return 1
    print("\nRESULTAT : caches a jour.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Rafraichit les caches publics Aster. Mode par defaut : --check (lecture seule).",
    )
    p.add_argument("--check", action="store_true",
                   help="Mode par defaut : rapporte l'age des caches, n'ecrit rien.")
    p.add_argument("--refresh-funding", action="store_true", help="Rafraichit le cache funding.")
    p.add_argument("--refresh-exchange-info", action="store_true",
                   help="Rafraichit le cache exchangeInfo.")
    p.add_argument("--refresh-all", action="store_true", help="Les deux caches.")
    p.add_argument("--symbols", default="", help="Liste separee par des virgules (ex: BTCUSDT,ETHUSDT).")
    p.add_argument("--limit", type=int, default=25, help="Nombre max de symboles funding (defaut 25).")
    p.add_argument("--funding-limit", type=int, default=100,
                   help="Nombre de points de funding par symbole (defaut 100).")
    p.add_argument("--sleep", type=float, default=MIN_SLEEP_S,
                   help=f"Pause entre appels API en secondes (min {MIN_SLEEP_S}).")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Timeout HTTP en secondes.")
    p.add_argument("--base-url", default=ASTER_BASE, help="Base API (defaut fapi.asterdex.com).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    do_funding = args.refresh_funding or args.refresh_all
    do_exchange = args.refresh_exchange_info or args.refresh_all

    if not do_funding and not do_exchange:
        return run_check(base_url=args.base_url, timeout=args.timeout)

    rc = 0
    if do_exchange:
        print("=== Rafraichissement exchangeInfo ===")
        try:
            res = refresh_exchange_info(base_url=args.base_url, timeout=args.timeout)
            print(f"  ecrit : {res['symbol_count']} symboles")
            if res["backup"]:
                print(f"  backup : {res['backup'].name}")
        except (AsterFetchError, OSError, ValueError) as exc:
            print(f"  ECHEC : {exc}")
            rc = 1

    if do_funding:
        print("=== Rafraichissement funding ===")
        if args.symbols.strip():
            # FIX R3 (C-C2) : une liste --symbols explicite est un CONTRAT de
            # l'opérateur — ne jamais la tronquer. L'ancienne troncature à
            # --limit (25) laissait les 4 derniers symboles de la ligne 9 du
            # nocturne (1000BONKUSDT, 1000FLOKIUSDT, DRAMUSDT, PIEVERSEUSDT,
            # ajoutés le 22/09/2026) hors de toute vague de refresh : absents
            # ou figés dans le cache, mesuré 25/73 symboles frais < 25 h =
            # exactement le plafond. Le --limit ne concerne que
            # default_symbols (l'échantillon « prix cassé »).
            syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        else:
            syms = default_symbols(limit=args.limit)
        print(f"  {len(syms)} symbole(s), pause {max(MIN_SLEEP_S, args.sleep)}s entre appels")
        try:
            res = refresh_funding(
                syms,
                limit=args.funding_limit,
                base_url=args.base_url,
                timeout=args.timeout,
                sleep_s=args.sleep,
            )
        except (OSError, ValueError) as exc:
            print(f"  ECHEC ecriture : {exc}")
            return 1
        print(f"  rafraichis : {res['ok']} / {len(syms)}")
        if res["failed"]:
            print(f"  en echec : {', '.join(res['failed'])}")
            rc = 1
        if res.get("backup"):
            print(f"  backup : {res['backup'].name}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
