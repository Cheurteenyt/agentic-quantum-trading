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
    delisted_at                   : P3 (audit Sonnet 5.5 R4) — DÉRIVÉ, plus
                                    « à tenir à jour » : le croisement des
                                    données (dernière barre) et du snapshot
                                    LIVE d'Aster (data/warehouse/
                                    aster_universe.json, captured_at +
                                    status par symbole). Un symbole ABSENT du
                                    snapshot live ou en status != TRADING est
                                    délisté — delisted_at = sa dernière
                                    observation (la dernière barre EST le
                                    dernier trade observé ; la date OFFICIELLE
                                    de délisting n'existe pas dans nos
                                    données, on ne l'invente pas). Un symbole
                                    TRADING au snapshot reste vivant (null)
                                    MÊME si ses barres sont anciennes —
                                    l'absence de barres récentes est un trou
                                    de COLLECTE, pas une mort.
    deliste_source                : la provenance OBLIGATOIRE quand
                                    delisted_at est non nul (leçon F7 : un
                                    chiffre sans provenance est une
                                    invention) — vérifié par I011.
    source                        : le snapshot de données

Usage :
    python3 scripts/universe.py --generate --name univ10 \
        --symbols BTCUSDT,ETHUSDT,...
    python3 scripts/universe.py --generate --name alts --auto alts
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


LIVE_SNAPSHOT = ROOT / "data" / "warehouse" / "aster_universe.json"
STABLES = {"USDC", "USD1", "FDUSD", "TUSD", "PYUSD", "DAI", "USDE"}
GRACE_H = 72          # heures de grâce : plus récent que ça = vivant
MAJEURES = "univ10"   # le manifest des majeures (la référence existante)


def _live_status(live: dict | None, sym: str) -> str | None:
    """Le status du symbole au snapshot live, ou None s'il y est absent."""
    if not live:
        return None
    e = (live.get("symbols") or {}).get(sym)
    return e.get("status") if isinstance(e, dict) else None


def _deliste_de_donnees(sym: str, observed_end: str | None,
                        live: dict | None) -> tuple[str | None, str | None]:
    """P3 (R4) : le delisting DÉRIVÉ du croisement données × snapshot live.

    Règle : le symbole est délisté s'il est ABSENT du snapshot live ou en
    status != TRADING. delisted_at = la dernière observation (la dernière
    barre est le dernier trade observé — la date officielle de délisting
    n'existe pas dans nos données, on ne l'invente pas). Un symbole TRADING
    reste vivant même si ses barres sont anciennes : c'est un trou de
    COLLECTE, pas une mort."""
    if observed_end is None or not live:
        return None, None
    status = _live_status(live, sym)
    cap = f"snapshot live du {datetime.fromtimestamp(live['captured_at'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    if status is None:
        return observed_end, f"absent du {cap}"
    if status != "TRADING":
        return observed_end, f"status={status} au {cap}"
    return None, None


def _classe_auto(classe: str, db_path: Path) -> list[str]:
    """P3 : l'appartenance des classes OBJECTIVE —
    majeures = le manifest univ10 existant (la référence) ;
    meme    = MEMECOINS de memecoin_pulse (LA liste machine, source unique) ;
    alts    = tout symbole 1h du warehouse − majeures − meme − stables.
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tous = [r[0] for r in con.execute(
            "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
            "ORDER BY symbol").fetchall()]
    finally:
        con.close()
    if classe == "majeures":
        m = load(MAJEURES)
        return sorted((m.get("symbols") or {}).keys())
    from scripts.memecoin_pulse import MEMECOINS
    if classe == "meme":
        return sorted(set(tous) & set(MEMECOINS))
    if classe == "alts":
        majeures = set(_classe_auto("majeures", db_path))
        meme = set(_classe_auto("meme", db_path))
        # USDT perps SEULEMENT : les suffixes USD1/BTCU… sont des produits
        # pré-launch ou d'autres quotes — pas des alts.
        return sorted(s for s in tous
                      if s.endswith("USDT")
                      and s not in majeures and s not in meme
                      and s.removesuffix("USDT") not in STABLES)
    raise ValueError(f"classe inconnue : {classe}")


def generate(name: str, symbols: list[str], db_path: Path = KDB,
             live_path: Path | None = None) -> Path:
    """Le manifest généré DEPUIS les données — la source de vérité est la
    base, jamais une main. P3 : le delisting est dérivé du croisement avec
    le snapshot live d'Aster (jamais saisi à la main)."""
    live = None
    lp = live_path if live_path is not None else LIVE_SNAPSHOT
    try:
        live = json.loads(Path(lp).read_text(encoding="utf-8"))
    except Exception:
        live = None     # pas de snapshot → tout vivant (honnête, noté)
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
                                "delisted_at": None, "deliste_source": None,
                                "source": snap}
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
            # PR-166 (P2 bug-hunter) : la couverture funding se lit en
            # prints ATTENDUS (span / intervalle 8h du calendrier), pas
            # par heure — une série parfaite affichait 12,5 %.
            f_cov = (fprints / max(1.0, span_hours / 8.0)
                     * 100.0) if span_hours else 0.0
            # PR-166 (P1 bug-hunter, 271/589 symboles) : le funding prouve
            # une existence ANTÉRIEURE à la première kline (backfill de
            # klines tardif) — la borne tradeable est le MIN des deux,
            # sinon apply_universe jetait les premiers mois tradeables.
            first_bar = min(start, fstart) if fstart else start
            deliste, deliste_src = _deliste_de_donnees(sym, _ms_iso(end),
                                                       live)
            entries[sym] = {
                "observed_start": _ms_iso(start),
                "observed_end": _ms_iso(end),
                # FIX v15 (№8) : la précision HORAIRE — les dates ISO sont
                # de la présentation, les ms sont la vérité (l'arrondi au
                # jour rendait la dernière journée non tradable)
                "first_bar_ms": first_bar,
                "last_bar_ms": end,
                "bars": int(len(ts)),
                "gaps": gaps,
                "coverage_pct": round(len(ts) / span_hours * 100.0, 2),
                "funding_start": _ms_iso(fstart) if fstart else None,
                "funding_prints": fprints,
                "funding_coverage_pct": round(f_cov, 2),
                # P3 (R4) : DÉRIVÉ du croisement données × snapshot live —
                # plus le « à tenir à jour » qui ne serait jamais tenu à jour
                "delisted_at": deliste,
                "deliste_source": deliste_src,
                "source": snap}
    finally:
        con.close()
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    out = UNIVERSE_DIR / f"{name}.yaml"
    doc = {"universe": name, "generated": datetime.now(
        timezone.utc).strftime("%Y-%m-%d"), "source_snapshot": snap,
        "point_in_time": True,
        "deliste_source_snapshot": (
            datetime.fromtimestamp(live["captured_at"], tz=timezone.utc)
            .strftime("%Y-%m-%d %H:%M UTC") if live else None),
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
    """Le span tradable en ms — pour filtrer les masques vectoriellement.
    Les champs ms précis sont préférés aux dates ISO (précision jour).
    FIX v15 (№5) : la borne de fin = last_bar_open + 1h — last_bar_ms est
    l'OPEN de la dernière bougie ; les données s'étendent jusqu'à sa
    clôture (fin EXCLUSIVE), sinon la dernière tranche est perdue."""
    e = manifest.get("symbols", {}).get(symbol)
    if not e or e.get("observed_start") is None:
        return None
    start = e.get("first_bar_ms") or _iso_ms(e["observed_start"])
    end = e.get("last_bar_ms")
    if end is not None:
        end = int(end) + 3_600_000     # la clôture de la dernière bougie
    if e.get("delisted_at_ms"):
        end = int(e["delisted_at_ms"])   # №10 : la précision ms d'abord
    elif e.get("delisted_at"):
        end = _iso_ms(e["delisted_at"])
    return (int(start), int(end))


def tradable(manifest: dict, symbol: str, ts_ms: int) -> bool:
    """L'actif existait-il à l'instant ts ? — FIX v16 (№11) : un simple
    wrapper de tradable_window_ms (UNE seule sémantique d'univers)."""
    w = tradable_window_ms(manifest, symbol)
    if w is None:
        return False
    return bool(w[0] <= ts_ms < w[1])


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
    ap.add_argument("--auto", choices=("majeures", "alts", "meme"),
                    help="P3 : l'appartenance OBJECTIVE — majeures = le "
                         "manifest univ10, meme = MEMECOINS de "
                         "memecoin_pulse, alts = le reste − stables")
    ap.add_argument("--db", default=str(KDB))
    a = ap.parse_args()
    symbols = ([s.strip().upper() for s in a.symbols.split(",") if s.strip()]
               if not a.auto else _classe_auto(a.auto, Path(a.db)))
    if a.generate:
        if not symbols:
            # PR-166 : FAIL-CLOSED — l'ancien comportement écrivait un
            # manifest VIDE en silence (boucle sur rien) : tout
            # apply_universe suivant échouait en UniverseViolation sans
            # que la cause soit évidente
            print("REFUS : --generate exige --symbols ou --auto (liste "
                  "vide) — un manifest vide ne sera pas écrit")
            return 2
        if not a.name:
            a.name = a.auto
        out = generate(a.name, symbols, Path(a.db))
        m = load(a.name)
        n_del = sum(1 for e in m["symbols"].values()
                    if e.get("delisted_at"))
        print(f"manifest écrit : {out} ({len(m['symbols'])} symboles, "
              f"{n_del} délisté(s) dérivés du snapshot live)")
        for sym, e in m["symbols"].items():
            deliste = (f" · DÉLISTÉ {e['delisted_at']}"
                       if e.get("delisted_at") else "")
            print(f"  {sym:16} {e['observed_start']} → {e['observed_end']}"
                  f" · {e['bars']:6} barres · gaps {e['gaps']}"
                  f" · funding dès {e['funding_start']}"
                  f" ({e['funding_coverage_pct']} %){deliste}")
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
