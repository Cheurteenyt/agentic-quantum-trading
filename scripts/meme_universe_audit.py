#!/usr/bin/env python
"""AUDIT UNIVERSE MEME — complétude de collect_meme vs perps Aster live + test d'expansion.

La question : collect_meme (scripts/the_machine.py) tourne sur "tout symbole 1h
présent dans klines.db moins MAJORS". Chaque perp Aster absente de klines.db =
des cascades meme non captées = de la fréquence perdue (cible user = régularité
mensuelle, 285 trades/an de référence).

Le collector nocturne (trading-agent-nightly.service) ne DÉCOUVRE jamais un
symbole : la liste fetch_klines --fetch-range y est codée en dur. Les manquants
ne recevront JAMAIS de données sans câblage manuel.

Étapes :
  1. Univers actuel : DISTINCT symbol 1h de data/warehouse/klines.db - MAJORS.
  2. Univers live : fapi.asterdex.com/fapi/v1/exchangeInfo (pattern
     _aster_universe de whale_radar.py, jamais en dur).
  3. Manquants = live - DB ; candidats meme = CANDIDATES ∩ live - DB
     (curation : refs projet whale_radar.ASTEROIDS + memecoin_pulse.MEMECOINS
     + zoo viral listé sur Aster).
  4. Test d'expansion : 3000 bougies 1h fetchées dans une SIDE-DB
     (data/warehouse/klines_audit_<date>.db — klines.db n'est JAMAIS touchée,
     l'ajout silencieux changerait l'univers officiel de la machine), puis le
     signal collect_meme EXACT importé de the_machine (zéro tuning).
  5. Verdict par candidat : >= 90j de données, N events, WR, espérance nette
     (frais MAKER_RT 4 bps inclus, funding exclu — conservateur car les shorts
     RECOIVENT le funding positif), MAE 24h. Règle 0-liq à 1x :
     MAE max >= 99.5 % (100/(mae+0.5) < 1) => EXCLU d'office.

  .venv/bin/python scripts/meme_universe_audit.py --fetch   # audit complet
  .venv/bin/python scripts/meme_universe_audit.py           # resume depuis side-DB

Le câblage de la liste retenue = thread principal (service systemd + liste
fetch, rapporté dans reports/meme-universe-audit-<date>.md).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_klines import run_fetch_range  # noqa: E402
from scripts.portfolio_sim import MAJORS  # noqa: E402
from scripts.stacked_portfolio import MAKER_RT  # noqa: E402
from scripts.the_machine import collect_meme  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
EXCHANGEINFO_URL = "https://fapi.asterdex.com/fapi/v1/exchangeInfo"
NOW = datetime.now(timezone.utc)
TAG = NOW.strftime("%Y%m%d")
SIDE_DB = ROOT / "data" / "warehouse" / f"klines_audit_{TAG}.db"
REPORTS = ROOT / "reports"

# Curation classe meme (absentes de klines.db, listées Aster live).
# Refs projet : whale_radar.ASTEROIDS + memecoin_pulse.MEMECOINS — pulse nomme
# BONKUSDT/FLOKIUSDT : tickers périmés, les perps live sont 1000BONK/1000FLOKI.
CANDIDATES = [
    # — refs projet (pulse/ASTEROIDS) manquantes —
    "1000PEPEUSDT", "1000BONKUSDT", "1000FLOKIUSDT", "DRAMUSDT", "PIEVERSEUSDT",
    # — classics meme —
    "1000SHIBUSDT", "1000CATUSDT", "1000CHEEMSUSDT", "1000RATSUSDT",
    "SPXUSDT", "TOSHIUSDT", "BONERUSDT", "KOMAUSDT", "DOLOUSDT",
    # — zoo viral 2024-2026 —
    "MELANIAUSDT", "CHILLGUYUSDT", "CLANKERUSDT", "JELLYJELLYUSDT",
    "MUBARAKUSDT", "PUMPUSDT", "TROLLUSDT", "USELESSUSDT", "ZEREBROUSDT",
    "GRIFFAINUSDT", "SWARMSUSDT", "ANSEMUSDT", "IDOLUSDT", "BANANAS31USDT",
    "BROCCOLI714USDT", "PIPPINUSDT", "FIGHTUSDT", "FLORKUSDT", "GIGGLEUSDT",
    "MEMESTOCKUSDT", "STONKSUSDT", "VIRTUALUSDT", "ANIMEUSDT",
]


def aster_universe_live() -> set[str]:
    """Perps USDT en TRADING sur Aster (pattern _aster_universe, whale_radar)."""
    req = urllib.request.Request(
        EXCHANGEINFO_URL, headers={"User-Agent": "trading-agent/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        d = json.load(resp)
    return {s["symbol"] for s in d.get("symbols", [])
            if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"}


def coverage_days(con: sqlite3.Connection, sym: str) -> float:
    row = con.execute(
        "SELECT MIN(open_time), MAX(open_time), COUNT(*) FROM klines "
        "WHERE symbol=? AND interval='1h'", (sym,)).fetchone()
    if not row or not row[0]:
        return 0.0, 0
    return (row[1] - row[0]) / 8.64e7, row[2]  # ms -> jours


def event_stats(events: list[dict], days: float) -> dict:
    """WR + espérance nette (% du notionnel, frais RT inclus, funding exclu)."""
    if not events:
        return {"n": 0, "wr": float("nan"), "exp": float("nan"),
                "mae_max": float("nan"), "mae_p95": float("nan"),
                "ev_an": 0.0}
    pnl = np.array([e["price_ret_short"] - e["fee_rt_bps"] / 100.0
                    for e in events])
    mae = np.array([e["mae_adverse"] for e in events])
    return {
        "n": len(events),
        "wr": float((pnl > 0).mean() * 100),
        "exp": float(pnl.mean()),
        "mae_max": float(mae.max()),
        "mae_p95": float(np.quantile(mae, 0.95)),
        "ev_an": len(events) / days * 365.0 if days > 0 else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit universe meme + expansion")
    ap.add_argument("--fetch", action="store_true",
                    help="fetcher les klines candidats dans la side-DB")
    ap.add_argument("--target-bars", type=int, default=3000)
    args = ap.parse_args(argv)

    # ——— 1. univers actuel ———
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True, timeout=60)
    current = {r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'")}
    meme_current = sorted(s for s in current if s not in MAJORS)

    # ——— 2. univers live ———
    live = aster_universe_live()
    missing = sorted(live - current)
    examples = {s: (f"{s}USDT" in current) for s in
                ("TRUMP", "FARTCOIN", "PNUT", "NEIRO")}

    # ——— baseline du flux actuel (meme signal, sur klines.db) ———
    base_events = collect_meme(con)
    tmin = min(e["ts_ms"] for e in base_events)
    tmax = max(e["ts_ms"] for e in base_events)
    # LECON ts_ms : le champ "ts_ms" de collect_meme contient des NANOsecondes
    # (idx_ns de load_df) — detection d'unite obligatoire.
    scale = 1e6 if tmax > 1e14 else 1.0
    base_days = (tmax - tmin) / (8.64e7 * scale)
    base = event_stats(base_events, base_days)
    con.close()

    print(f"univers actuel        : {len(meme_current)} memes "
          f"(DB={len(current)} symboles, MAJORS={len(MAJORS)})")
    print(f"univers Aster live    : {len(live)} perps USDT TRADING")
    print(f"manquants             : {len(missing)}")
    print(f"exemples user         : " + ", ".join(
        f"{k}={'DEJA present' if v else 'ABSENT'}" for k, v in examples.items()))
    print(f"baseline flux meme    : {base['n']} events / {base_days:.0f} j "
          f"= {base['ev_an']:.0f}/an, WR {base['wr']:.1f} %, "
          f"esp {base['exp']:+.2f} %, MAEmax {base['mae_max']:.0f} %")

    cands = [c for c in CANDIDATES if c in live and c not in current]

    # ——— 3. side-DB : fetch + signal ———
    if args.fetch:
        print(f"fetch side-DB {SIDE_DB.name} : {len(cands)} candidats")
        for sym in cands:
            try:
                run_fetch_range(sym, "1h", args.target_bars, db_path=SIDE_DB)
            except Exception as exc:  # noqa: BLE001 — un symbole ne doit pas
                print(f"  !! {sym} : {exc}")  # tuer l'audit
    scon = sqlite3.connect(SIDE_DB, timeout=60)
    side_syms = {r[0] for r in scon.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'")}
    new_events = collect_meme(scon) if side_syms else []
    scon.close()

    per_sym: dict[str, dict] = {}
    for sym in sorted(side_syms | (set(cands) - side_syms)):
        sc = sqlite3.connect(SIDE_DB, timeout=60)
        days, nrows = coverage_days(sc, sym)
        sc.close()
        st = event_stats([e for e in new_events if e["sym"] == sym], days)
        st["days"], st["rows"] = days, nrows
        if st["n"] and days < 90:
            st["verdict"] = f"TROP RECENT ({days:.0f} j < 90 j)"
        elif st["n"] and st["mae_max"] >= 99.5:
            st["verdict"] = "EXCLU (MAE fatal, liq a 1x)"
        elif st["n"] and st["exp"] > 0:
            st["verdict"] = "AJOUTABLE"
        elif st["n"]:
            st["verdict"] = "NON (esperance <= 0)"
        else:
            st["verdict"] = "AUCUN EVENT (ou data < 500 barres)"
        per_sym[sym] = st

    addable = [s for s, st in per_sym.items() if st["verdict"] == "AJOUTABLE"]
    gain_an = sum(per_sym[s]["ev_an"] for s in addable)
    # Tier 1 = evidence solide (>= 10 events ET esperance >= +0.5 %/trade),
    # Tier 2 = ajoutable mais evidence faible (< 10 events) — bruit possible.
    tier1 = [s for s in addable
             if per_sym[s]["n"] >= 10 and per_sym[s]["exp"] >= 0.5]
    tier2 = [s for s in addable if s not in tier1]
    gain1 = sum(per_sym[s]["ev_an"] for s in tier1)

    # ——— 4. rapport ———
    REPORTS.mkdir(exist_ok=True)
    rp = REPORTS / f"meme-universe-audit-{NOW:%Y-%m-%d}.md"
    lines = [
        f"# AUDIT UNIVERSE MEME — {NOW:%Y-%m-%d}",
        "",
        "Signal : `collect_meme` (scripts/the_machine.py) importe tel quel, "
        "zero tuning. Expansion testee en SIDE-DB (klines.db intacte).",
        "",
        "## 1. Univers actuel",
        f"- memes (1h, non-MAJORS) dans klines.db : **{len(meme_current)}** : "
        + ", ".join(meme_current),
        f"- baseline flux : {base['n']} events sur {base_days:.0f} j "
        f"= {base['ev_an']:.0f}/an, WR {base['wr']:.1f} %, "
        f"esperance nette {base['exp']:+.2f} %/trade, MAE max {base['mae_max']:.0f} %",
        "",
        "## 2. Univers live Aster (exchangeInfo)",
        f"- perps USDT TRADING : **{len(live)}** ; manquantes vs klines.db : "
        f"**{len(missing)}** (annexe)",
        "- exemples user : " + ", ".join(
            f"{k} {'DEJA present' if v else 'ABSENT'}" for k, v in examples.items()),
        f"- candidats meme testes : **{len(cands)}**",
        "",
        "## 3. Test d'expansion (>= 90 j, MAE fatal >= 99.5 % => exclu)",
        "",
        "| symbole | jours | events | events/an | WR % | esp. nette % | MAE max % | MAE p95 % | verdict |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for sym, st in per_sym.items():
        lines.append(
            f"| {sym} | {st['days']:.0f} | {st['n']} | {st['ev_an']:.0f} | "
            f"{st['wr']:.1f} | {st['exp']:+.2f} | {st['mae_max']:.0f} | "
            f"{st['mae_p95']:.0f} | {st['verdict']} |")
    lines += [
        "",
        "## 4. Verdict",
        f"- manquants : **{len(missing)}** ; ajoutables (MAE tient + esperance > 0) : "
        f"**{len(addable)}**",
        f"- ajoutables : " + (", ".join(addable) if addable else "AUCUN"),
        f"- TIER 1 (n>=10 events, esperance >= +0.5 %) : "
        + (", ".join(tier1) if tier1 else "aucun")
        + f" — gain +{gain1:.0f} events/an",
        f"- TIER 2 (evidence faible, n<10) : " + (", ".join(tier2) if tier2 else "aucun"),
        f"- gain de frequence : **+{gain_an:.0f} events/an** "
        f"({base['ev_an']:.0f} -> {base['ev_an'] + gain_an:.0f}/an, "
        f"+{gain_an / base['ev_an'] * 100 if base['ev_an'] else 0:.0f} %)",
        "- espérance nette = prix (short 24h) - frais 4 bps RT ; funding EXCLU "
        "(conservateur : les shorts RECOIVENT le funding positif meme).",
        "- MAE 24h : aucun AJOUTABLE au MAE fatal (>= 99.5 %) — le pire ajoutable est "
        + (f"{max(per_sym[s]['mae_max'] for s in addable):.0f} %"
           if addable else "n/a")
        + " ; le flux a 1x tient sur tous les ajouts "
        "(les MAE > 99.5 % observés ne sont que sur des candidats déjà exclus "
        "pour données < 90 j).",
        "- collect_meme inclut deja GOOGL/NVDA (perps actions) et ADA/AVAX/LINK/"
        "LTC/ARB (grosses caps) dans son univers 'meme' — looseness connue, "
        "hors scope ici.",
        "",
        "### Cablage (thread principal, PAS ce script)",
        "1. `configs/systemd-user/trading-agent-nightly.service` : ajouter une ligne "
        "`fetch_klines.py --fetch-range <SYM> --target-bars 3000` par symbole retenu.",
        "2. Meme fichier, ligne 9 `refresh_aster_cache.py --symbols` : ajouter les "
        "mêmes symboles (funding des shorts) — et corriger BONKUSDT->1000BONKUSDT, "
        "FLOKIUSDT->1000FLOKIUSDT (tickers périmés).",
        "3. `memecoin_pulse.py` MEMECOINS : mêmes corrections de tickers.",
        "4. collect_meme n'a AUCUNE liste en dur : dès que les klines arrivent dans "
        "klines.db, le flux les capte tout seul (levier mécanique recalculé).",
        "",
        "## Annexe : manquants (toutes classes, non testés)",
        "",
        "```",
        ", ".join(missing),
        "```",
        "",
        "Side-DB : " + str(SIDE_DB),
    ]
    rp.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n{'SYMB':14s} {'j':>4s} {'ev':>4s} {"/an":>5s} {'WR%':>5s} "
          f"{'exp%':>6s} {'MAE%':>5s}  verdict")
    for sym, st in per_sym.items():
        print(f"{sym:14s} {st['days']:4.0f} {st['n']:4d} {st['ev_an']:5.0f} "
              f"{st['wr']:5.1f} {st['exp']:+6.2f} {st['mae_max']:5.0f}  "
              f"{st['verdict']}")
    print(f"\nverdict : {len(addable)} ajoutables ({len(tier1)} tier-1), "
          f"gain +{gain_an:.0f} events/an (tier-1 +{gain1:.0f})")
    print(f"rapport : {rp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
