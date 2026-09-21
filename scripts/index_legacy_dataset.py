#!/usr/bin/env python3
"""Indexe le dataset legacy Aster (442 Mo de CSV) en une base SQLite interrogeable.

POURQUOI
--------
442 Mo de CSV pour 17 148 lignes = 26 Ko par ligne. 96 % du volume est dans
trois colonnes `*_json` (candidate_json, perps_scenarios_json,
leverage_scenarios_json) qui ne sont jamais requetees. Le dataset est donc
illisible non pas parce qu'il est gros, mais parce qu'il est mal range.

Ce script produit `data/warehouse/legacy_lanes.db` : les 51 colonnes communes
aux 6 variantes de schema, plus les colonnes de la generation corrigee quand
elles existent, plus une IDENTITE DE LANE canonique (le bug structurel du
legacy : `truth_match_scope = identity_missing`).

Les colonnes `*_json` sont EXCLUES par defaut (--with-json pour les garder).
Les CSV sources ne sont ni modifies ni supprimes.

USAGE
-----
    python scripts/index_legacy_dataset.py            # construit la base
    python scripts/index_legacy_dataset.py --stats    # + rapport d'analyse

Lecture seule sur les sources. Idempotent : rebuild complet a chaque run.
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import os
import sqlite3
import sys
from pathlib import Path

csv.field_size_limit(10**9)

ROOT = Path(__file__).resolve().parents[1]
SRC = (
    ROOT
    / "backend/services/onchain/aster/archive/research_artifacts/legacy_discovery_batches"
)
OUT = ROOT / "data/warehouse/legacy_lanes.db"

# Les 6 champs qui definissent une lane (contrat d'identite, docs/03-methodology.md)
IDENTITY = ["symbol", "interval", "side", "risk_profile", "execution_model", "best_tradable_leverage"]

# Colonnes lourdes jamais requetees : 96 % du volume
HEAVY = {"candidate_json", "perps_scenarios_json", "leverage_scenarios_json", "perps_assumptions_json"}

NUMERIC_HINTS = (
    "_pct", "_usd", "_bps", "_ms", "_count", "_score", "_ratio", "_rate",
    "win_rate", "profit_factor", "entries", "closed_trades", "wins", "losses",
    "rank", "leverage", "lookback_days", "windows",
)


def is_numeric(col: str) -> bool:
    return any(h in col for h in NUMERIC_HINTS)


def coerce(col: str, val: str):
    if val is None or val == "":
        return None
    if is_numeric(col):
        try:
            return float(val)
        except ValueError:
            return val
    return val


def scan_schema(files: list[str], with_json: bool) -> list[str]:
    """Union de toutes les colonnes, ordonnee par frequence d'apparition."""
    freq: dict[str, int] = {}
    for f in files:
        with open(f, newline="", encoding="utf-8", errors="replace") as fh:
            for col in next(csv.reader(fh), []):
                freq[col] = freq.get(col, 0) + 1
    cols = [c for c in freq if with_json or c not in HEAVY]
    return sorted(cols, key=lambda c: (-freq[c], c))


def lane_identity(row: dict) -> tuple[str, str]:
    """Renvoie (identity_key lisible, identity_hash stable)."""
    parts = [str(row.get(k) or "?") for k in IDENTITY]
    key = "|".join(parts)
    return key, hashlib.sha1(key.encode()).hexdigest()[:12]


def build(with_json: bool = False) -> sqlite3.Connection:
    files = sorted(glob.glob(str(SRC / "*.csv")))
    if not files:
        sys.exit(f"Aucun CSV dans {SRC}")

    cols = scan_schema(files, with_json)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()

    con = sqlite3.connect(OUT)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")

    meta = ["source_file", "identity_key", "identity_hash", "schema_variant"]
    decl = ", ".join(
        f'"{c}" {"REAL" if is_numeric(c) else "TEXT"}' for c in cols
    )
    con.execute(f'CREATE TABLE lanes ({", ".join(f"{m} TEXT" for m in meta)}, {decl})')

    placeholders = ",".join("?" * (len(meta) + len(cols)))
    insert = f"INSERT INTO lanes VALUES ({placeholders})"

    variants: dict[tuple, str] = {}
    total = 0

    for f in files:
        name = os.path.basename(f)
        with open(f, newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            sig = tuple(reader.fieldnames or [])
            if sig not in variants:
                variants[sig] = f"v{len(variants)}_{len(sig)}cols"
            variant = variants[sig]

            batch = []
            for row in reader:
                key, h = lane_identity(row)
                batch.append(
                    [name, key, h, variant] + [coerce(c, row.get(c)) for c in cols]
                )
                if len(batch) >= 500:
                    con.executemany(insert, batch)
                    total += len(batch)
                    batch = []
            if batch:
                con.executemany(insert, batch)
                total += len(batch)

    for idx in ("identity_hash", "symbol", "verdict", "schema_variant"):
        if idx in cols or idx in meta:
            con.execute(f'CREATE INDEX ix_{idx} ON lanes("{idx}")')

    con.commit()

    src_size = sum(os.path.getsize(f) for f in files)
    db_size = OUT.stat().st_size
    print(f"Source : {len(files)} CSV, {src_size/1e6:.0f} Mo")
    print(f"Base   : {OUT.relative_to(ROOT)}, {db_size/1e6:.1f} Mo, {total} lignes")
    print(f"Gain   : {src_size/db_size:.0f}x plus compact")
    print(f"Colonnes retenues : {len(cols)} ({len(variants)} variantes de schema)")
    return con


def q(con, sql: str):
    return con.execute(sql).fetchall()


def stats(con: sqlite3.Connection) -> None:
    print("\n" + "=" * 66)
    print("RAPPORT — ce que le dataset legacy dit vraiment")
    print("=" * 66)

    cols = {r[1] for r in q(con, "PRAGMA table_info(lanes)")}

    print("\n-- Volume par variante de schema")
    for v, n, f in q(
        con,
        "SELECT schema_variant, COUNT(*), COUNT(DISTINCT source_file) "
        "FROM lanes GROUP BY 1 ORDER BY 2 DESC",
    ):
        print(f"   {v:<14} {n:>6} lignes   {f:>3} fichiers")

    print("\n-- Contrat d'identite de lane")
    tot = q(con, "SELECT COUNT(*) FROM lanes")[0][0]
    uniq = q(con, "SELECT COUNT(DISTINCT identity_hash) FROM lanes")[0][0]
    incomplete = q(con, "SELECT COUNT(*) FROM lanes WHERE identity_key LIKE '%?%'")[0][0]
    print(f"   lignes totales        : {tot}")
    print(f"   identites distinctes  : {uniq}")
    print(f"   identite INCOMPLETE   : {incomplete}  ({100*incomplete/tot:.1f} %)")
    print("   -> une identite incomplete = resultat non comparable = a jeter")

    dupes = q(
        con,
        "SELECT COUNT(*) FROM (SELECT identity_hash FROM lanes "
        "GROUP BY 1 HAVING COUNT(*) > 1)",
    )[0][0]
    print(f"   identites testees >1x : {dupes}")

    if "verdict" in cols:
        print("\n-- Verdicts")
        for v, n in q(
            con,
            "SELECT COALESCE(verdict,'(vide)'), COUNT(*) FROM lanes "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 8",
        ):
            print(f"   {str(v):<28} {n:>6}")

    if "pnl_total_usd" in cols:
        print("\n-- PnL (toutes lanes confondues)")
        r = q(
            con,
            "SELECT COUNT(*), SUM(pnl_total_usd>0), AVG(pnl_total_usd), "
            "SUM(pnl_total_usd) FROM lanes WHERE pnl_total_usd IS NOT NULL",
        )[0]
        n, pos, avg, tot_pnl = r
        print(f"   lanes avec PnL   : {n}")
        print(f"   PnL > 0          : {pos}  ({100*(pos or 0)/n:.1f} %)")
        print(f"   PnL moyen        : {avg:+.3f} USD")
        print(f"   PnL cumule       : {tot_pnl:+.1f} USD")

    if "out_of_sample_status" in cols:
        print("\n-- Generation corrigee : train / validation OOS")
        for v, n in q(
            con,
            "SELECT COALESCE(out_of_sample_status,'(absent)'), COUNT(*) "
            "FROM lanes GROUP BY 1 ORDER BY 2 DESC LIMIT 6",
        ):
            print(f"   {str(v):<28} {n:>6}")

    if {"train_pnl_total_usd", "validation_pnl_total_usd"} <= cols:
        r = q(
            con,
            "SELECT COUNT(*), SUM(train_pnl_total_usd>0 AND validation_pnl_total_usd<=0), "
            "SUM(train_pnl_total_usd>0 AND validation_pnl_total_usd>0) FROM lanes "
            "WHERE train_pnl_total_usd IS NOT NULL AND validation_pnl_total_usd IS NOT NULL",
        )[0]
        n, overfit, robust = r
        if n:
            print(f"\n   lanes avec split train/val : {n}")
            print(f"   OVERFIT (train+ / val-)    : {overfit}  ({100*overfit/n:.1f} %)")
            print(f"   robustes (train+ / val+)   : {robust}  ({100*robust/n:.1f} %)")
            print("   -> le taux d'overfit est LA metrique a battre par le nouveau moteur")

    if {"pnl_realized_usd", "open_unrealized_pnl_usd"} <= cols:
        r = q(
            con,
            "SELECT COUNT(*), SUM(pnl_realized_usd), SUM(open_unrealized_pnl_usd) "
            "FROM lanes WHERE pnl_realized_usd IS NOT NULL",
        )[0]
        if r[0]:
            print(f"\n-- PnL realise vs latent (le mensonge n.4)")
            print(f"   lanes            : {r[0]}")
            print(f"   PnL REALISE cumule : {r[1]:+.2f} USD")
            print(f"   PnL LATENT cumule  : {r[2]:+.2f} USD")
            print("   -> les additionner produit un chiffre qui ne veut rien dire")

    print("\n" + "=" * 66)
    print("Requetes libres :")
    print(f'  sqlite3 "{OUT.relative_to(ROOT)}" "SELECT * FROM lanes LIMIT 1"')
    print("=" * 66)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true", help="rapport d'analyse")
    ap.add_argument("--with-json", action="store_true", help="garder les colonnes *_json (+96 %% de volume)")
    a = ap.parse_args()

    conn = build(with_json=a.with_json)
    if a.stats:
        stats(conn)
    conn.close()
