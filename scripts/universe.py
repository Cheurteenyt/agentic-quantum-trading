#!/usr/bin/env python3
"""L'UNIVERS HISTORIQUE — PR-5 (audit GLM 5.3 №30, §35).

Un backtest sur « les 10 majeures actuelles + backfill » n'est PAS un
univers historique : sans manifest de tradabilité, on ne sait pas quand
chaque actif existait réellement, quand son funding a commencé, ni où sont
les trous. Ce module GÉNÈRE le manifest depuis le warehouse (zéro saisie
manuelle — le rapport exige « aucun chiffre manuel ») et fournit le moteur
de tradabilité.

Manifest (research/universe/<nom>.yaml) par symbole :
    observed_start / observed_end : le span RÉEL des klines 1h
    bars / gaps / coverage_pct    : la qualité de la série
    funding_start / prints        : quand le funding a commencé, couverture
    delisted_at                   : null (Observation : à tenir à jour)
    source                        : le snapshot de données

Usage :
    python3 scripts/universe.py --generate --name univ10 \
        --symbols BTCUSDT,ETHUSDT,...
    python3 scripts/universe.py --check --name univ10 \
        --symbols BTCUSDT,...
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.label_matrix import snapshot_id  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
UNIVERSE_DIR = ROOT / "research" / "universe"


def _ms_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%d")


def generate(name: str, symbols: list[str], db_path: Path = KDB) -> Path:
    """Le manifest généré DEPUIS les données — la source de vérité est la
    base, jamais une main."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    snap = snapshot_id(db_path)
    entries = {}
    try:
        for sym in symbols:
            rows = con.execute(
                "SELECT open_time FROM klines WHERE symbol=? AND "
                "interval='1h' ORDER BY open_time",
                (sym,)).fetchall()
            if not rows:
                entries[sym] = {"observed_start": None,
                                "observed_end": None, "bars": 0,
                                "gaps": 0, "coverage_pct": 0.0,
                                "funding_start": None, "funding_prints": 0,
                                "funding_coverage_pct": 0.0,
                                "delisted_at": None, "source": snap}
                continue
            ts = np.array([r[0] for r in rows], dtype=np.int64)
            start, end = int(ts[0]), int(ts[-1])
            span_hours = (end - start) // 3_600_000 + 1
            gaps = int(np.sum(np.diff(ts) != 3_600_000))
            frows = con.execute(
                "SELECT MIN(funding_time), COUNT(*) FROM funding_history "
                "WHERE symbol=?", (sym,)).fetchone()
            fstart, fprints = (int(frows[0]) if frows and frows[0] else None), \
                int(frows[1]) if frows else 0
            f_cov = (fprints / span_hours * 100.0) if span_hours else 0.0
            entries[sym] = {
                "observed_start": _ms_iso(start),
                "observed_end": _ms_iso(end),
                "bars": int(len(ts)),
                "gaps": gaps,
                "coverage_pct": round(len(ts) / span_hours * 100.0, 2),
                "funding_start": _ms_iso(fstart) if fstart else None,
                "funding_prints": fprints,
                "funding_coverage_pct": round(f_cov, 2),
                "delisted_at": None,   # Observation : à tenir à jour
                "source": snap}
    finally:
        con.close()
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    out = UNIVERSE_DIR / f"{name}.yaml"
    doc = {"universe": name, "generated": datetime.now(
        timezone.utc).strftime("%Y-%m-%d"), "source_snapshot": snap,
        "symbols": entries}
    out.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=True),
                   encoding="utf-8")
    return out


def load(name: str) -> dict:
    return yaml.safe_load((UNIVERSE_DIR / f"{name}.yaml").read_text(
        encoding="utf-8"))


def _iso_ms(d: str | None) -> int | None:
    if not d:
        return None
    return int(datetime.strptime(d, "%Y-%m-%d")
               .replace(tzinfo=timezone.utc).timestamp() * 1000)


def tradable_window_ms(manifest: dict, symbol: str) -> tuple[int, int] | None:
    """Le span tradable en ms — pour filtrer les masques vectoriellement."""
    e = manifest.get("symbols", {}).get(symbol)
    if not e or e.get("observed_start") is None:
        return None
    start = _iso_ms(e["observed_start"])
    end = _iso_ms(e.get("delisted_at") or e["observed_end"])
    return (start, end)


def tradable(manifest: dict, symbol: str, ts_ms: int) -> bool:
    """L'actif existait-il à l'instant ts ? — le masque anti-survivorship :
    avant observed_start (listing) ou après observed_end/delisted_at, NON."""
    e = manifest.get("symbols", {}).get(symbol)
    if not e or e.get("observed_start") is None:
        return False
    start = _iso_ms(e["observed_start"])
    end = _iso_ms(e.get("delisted_at") or e["observed_end"])
    return bool(start <= ts_ms <= end)


def check(manifest: dict, symbols: list[str]) -> tuple[list[str], list[str]]:
    """Les symboles d'une spec sont-ils dans le manifest et leurs spans
    observés contiennent-ils au moins une barre ? Retourne (absents, vides)."""
    missing = [s for s in symbols if s not in manifest.get("symbols", {})]
    empty = [s for s in symbols if s in manifest.get("symbols", {})
             and not manifest["symbols"][s].get("bars")]
    return missing, empty


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--name", default="univ10")
    ap.add_argument("--symbols", default="")
    ap.add_argument("--db", default=str(KDB))
    a = ap.parse_args()
    symbols = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    if a.generate:
        out = generate(a.name, symbols, Path(a.db))
        m = load(a.name)
        print(f"manifest écrit : {out}")
        for sym, e in m["symbols"].items():
            print(f"  {sym:14} {e['observed_start']} → {e['observed_end']}"
                  f" · {e['bars']:6} barres · gaps {e['gaps']}"
                  f" · funding dès {e['funding_start']}"
                  f" ({e['funding_coverage_pct']} %)")
        return 0
    if a.check:
        m = load(a.name)
        missing, empty = check(m, symbols)
        for s in missing:
            print(f"[ÉCHEC] {s} : absent du manifest {a.name}")
        for s in empty:
            print(f"[ÉCHEC] {s} : aucune barre observée")
        for s in symbols:
            if s not in missing and s not in empty:
                print(f"  {s} : tradable selon le manifest")
        return 1 if (missing or empty) else 0
    print("choisis --generate ou --check")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
