#!/usr/bin/env python3
"""Carry hedgé multi-venues — transformer le funding en rendement net.

Le scanner de funding RANGEOUE les extrêmes (MEME +88 %/an...). Ce script
cherche la SECONDE JAMBE : pour chaque extrême, le prix perp Aster contre
le prix SPOT de la même actif sur Binance (ccxt, endpoints publics, sans
clé). Si le spot existe, un short perp Aster + long spot Binance =
position neutre au prix qui ENCAISSE le funding, moins les coûts.

Calculs :
  - basis = (perp - spot) / spot : le prix d'entrée du carry
  - funding annuel (du cache nocturne)
  - coût d'un aller-retour (hypothèses : taker Aster 5 bps/side,
    taker Binance spot 10 bps/side — constantes à ajuster)
  - funding quotidien net vs coût : le point mort en jours de détention

Limites assumées (affichées dans le rapport) : le funding varie à chaque
règlement (8h), le basis bouge (risque de unwind), la jambe spot n'existe
pas pour les perps d'actions (INTC, GOOGL... -> exclus), les perps 1000x
ont un multiplicateur implicite.

    python scripts/carry_hedged.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.funding_scanner import load_ranked, REPORTS

CACHE = ROOT / "backend" / "services" / "onchain" / "aster" / \
    "aster_public_funding_history_cache.json"
ASTER_PREMIUM = "https://fapi.asterdex.com/fapi/v3/premiumIndex?symbol="
ASTER_FAPI_PREFIX = "https://fapi.asterdex.com/fapi/"
TAKER_ASTER_BPS = 5.0   # hypothese : taker 0.05 %/side
TAKER_SPOT_BPS = 10.0   # hypothese : Binance spot taker 0.10 %/side
TOP_N = 8


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _aster_mark(symbol: str) -> float | None:
    import urllib.request

    try:
        with urllib.request.urlopen(ASTER_PREMIUM + symbol, timeout=10) as resp:
            data = json.loads(resp.read())
        return float(data.get("markPrice") or 0) or None
    except Exception:
        return None


def _binance_spot(ex, symbol: str) -> float | None:
    """Prix spot Binance via ccxt public. Les perps d'actions (INTC...)
    n'ont pas de spot -> None."""
    try:
        base = symbol[:-4] if symbol.endswith("USDT") else symbol
        for prefix in ("1000", "1M"):
            if base.startswith(prefix):
                base = base[len(prefix):]
        ticker = ex.fetch_ticker(f"{base}/USDT")
        price = ticker.get("last")
        return float(price) if price else None
    except Exception:
        return None


def _funding_bps_per_8h(symbol: str) -> float | None:
    with CACHE.open(encoding="utf-8") as fh:
        cache = json.load(fh)
    entry = cache.get("symbols", {}).get(symbol) or {}
    return (entry.get("data") or {}).get("latest_funding_bps_per_8h")


def analyse(top_n: int = TOP_N) -> list[dict]:
    """Top extrêmes du scanner -> carry net si la seconde jambe existe."""
    import ccxt

    ex = ccxt.binance({"enableRateLimit": True})
    rows = load_ranked()[:top_n]
    out: list[dict] = []
    for r in rows:
        sym = r["symbol"]
        perp = _aster_mark(sym)
        spot = _binance_spot(ex, sym)
        bps8h = _funding_bps_per_8h(sym)
        funding_daily_pct = (bps8h or 0) * 3 / 100
        round_trip_pct = (TAKER_ASTER_BPS * 2 + TAKER_SPOT_BPS) / 100
        basis_pct = (
            (perp - spot) / spot * 100 if perp and spot else None
        )
        # garde-fou : un basis absurde = actifs differents entre les deux
        # venues (MEME d'Aster != MEME de Binance). Presenter un "hedge"
        # sur ces paires serait offrir une perte garantie a l'utilisateur.
        sane = basis_pct is not None and abs(basis_pct) <= 20
        breakeven_days = (
            round_trip_pct / funding_daily_pct
            if funding_daily_pct > 0 and sane
            else None
        )
        out.append({
            "symbol": sym,
            "latest_ann": r["latest_ann"],
            "who_collects": r["who_collects"],
            "perp": perp,
            "spot": spot,
            "basis_pct": basis_pct,
            "hedgable": bool(perp and spot and sane),
            "basis_incoherent": bool(basis_pct is not None and not sane),
            "funding_daily_pct": funding_daily_pct,
            "round_trip_pct": round_trip_pct,
            "breakeven_days": breakeven_days,
        })
    return out


def write_report(rows: list[dict]) -> Path:
    now = _utc_now()
    hedgable = [r for r in rows if r["hedgable"]]
    lines = [
        "# Carry hedgé — Aster perp vs Binance spot",
        "",
        f"Genere : {now} UTC — hypothèses de frais : Aster taker "
        f"{TAKER_ASTER_BPS:g} bps/side, Binance spot taker {TAKER_SPOT_BPS:g} bps/side",
        "",
        "Un carry hedgé = short perp Aster + long spot Binance (funding "
        "positif). Position neutre au prix : l'argent vient du funding, pas "
        "de la direction. Basis d'entrée non nul = P&L au unwind.",
        "",
        "| symbole | perp | spot | basis | funding/jour | aller-retour | point mort |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in hedgable:
        if r["funding_daily_pct"] > 0:
            structure = "short perp / long spot"
            breakeven = f"{r['breakeven_days']:.1f} j"
        else:
            structure = "funding négatif : structure inversée"
            breakeven = "n/a"
        lines.append(
            f"| {r['symbol']} | {r['perp']:.4g} | {r['spot']:.4g} "
            f"| {r['basis_pct']:+.2f} % | {r['funding_daily_pct']:.3f} % "
            f"| {r['round_trip_pct']:.2f} % "
            f"| {breakeven} ({structure}) |"
        )
    skipped = [r["symbol"] for r in rows if not r["hedgable"]]
    incoherent = [
        (r["symbol"], r["basis_pct"]) for r in rows if r.get("basis_incoherent")
    ]
    if skipped:
        lines += [
            "",
            f"Non hedgables (pas de spot Binance : perps d'actions ou "
            f"multiplicateurs) : {', '.join(skipped)}",
        ]
    if incoherent:
        lines += [
            "",
            "**Basis incohérent — actifs probablement différents entre les "
            "deux venues, EXCLUS du carry :**",
        ]
        lines += [f"- {sym} : basis {basis:+.0f} %" for sym, basis in incoherent]
    lines += [
        "",
        "Limites assumées : le funding varie à chaque règlement de 8 h (le",
        "+88 %/an d'hier peut être 20 % demain) ; le basis bouge ; le risque",
        "de liquidation dépend du levier de la jambe perp. Le point mort est",
        "le nombre de JOURS de détention pour payer les frais aller-retour",
        "avec le funding — le risque de prix est couvert, pas éliminé.",
    ]
    out = REPORTS / f"carry-hedged-{now.replace(':', '').replace('-', '')}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (REPORTS / "carry-hedged.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return out


def main() -> int:
    rows = analyse()
    out = write_report(rows)
    print(f"[carry] {len(rows)} extrêmes analysés — rapport : {out}")
    for r in rows:
        if not r["hedgable"]:
            reason = ("basis incohérent — actifs différents"
                      if r.get("basis_incoherent") else "pas de spot")
            print(f"  {r['symbol']:16} non hedgable ({reason})")
            continue
        be = (f"{r['breakeven_days']:.1f} j"
              if r["breakeven_days"] is not None else "n/a (funding négatif)")
        print(f"  {r['symbol']:16} basis {r['basis_pct']:+.2f} % | "
              f"funding {r['funding_daily_pct']:.3f} %/jour | point mort {be}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
