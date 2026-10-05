#!/usr/bin/env python3
"""BONSAI BATCH → QUEUE SPECS — la conversion hypothèses → expériences.

Le pont entre le modèle local (research/bonsai/hypotheses-batch-NNN.json)
et la file du Research OS (research/queue/bonsai/). Chaque hypothèse
devient une spec JSON exécutable par le runner : les conditions du masque
sont vérifiées contre le langage du runner (features, opérateurs, quantile
OU threshold), l'univers est la liste --symbols, les critères de découverte
sont injectés (min_n/min_mean par classe de compute). Rien n'est jugé ici :
la découverte et la confirmation restent les seules autorités.

Usage :
    python3 scripts/bonsai_batch_to_queue.py --batch 2 \
        --symbols BTCUSDT,ETHUSDT,SOLUSDT [--min-n 50] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BONSAI_DIR = ROOT / "research" / "bonsai"
QUEUE = ROOT / "research" / "queue" / "bonsai"

ALLOWED_FEATURES = {"range_pct", "volume_z", "ret_1h", "fund_last"}
ALLOWED_OPS = {">=", "<="}
HORIZONS = {1, 2, 4, 6, 12, 24, 48, 72}
# par classe de compute : la profondeur d'univers et les critères de découverte
CLASS_RULES = {
    "tiny": {"min_n": 50, "min_mean": 0.02},
    "small": {"min_n": 50, "min_mean": 0.02},
    "medium": {"min_n": 30, "min_mean": 0.02},
}


def _check_conditions(conds: list) -> list[str]:
    errs = []
    for j, c in enumerate(conds):
        if not isinstance(c, dict) or "feature" not in c or "op" not in c:
            errs.append(f"condition {j} : structure invalide")
            continue
        if c["feature"] not in ALLOWED_FEATURES:
            errs.append(f"condition {j} : feature '{c['feature']}' inconnue")
        if c["op"] not in ALLOWED_OPS:
            errs.append(f"condition {j} : op '{c['op']}' interdit (causalité)")
        if "quantile" in c:
            q = float(c["quantile"])
            if not 0.0 < q < 1.0:
                errs.append(f"condition {j} : quantile {q} hors (0,1)")
        elif "threshold" not in c:
            errs.append(f"condition {j} : ni quantile ni threshold")
    return errs


def convert(batch: dict, symbols: list[str], min_n_default: int = 50,
            min_mean: float = 0.02) -> tuple[list[dict], list[str]]:
    """Convertit les hypothèses en specs. Retourne (specs, erreurs)."""
    specs, errors = [], []
    for h in batch.get("hypotheses", []):
        hid = str(h.get("id", "?"))
        conds = h.get("conditions") or []
        if not conds:
            errors.append(f"{hid} : pas de conditions exécutables")
            continue
        errs = _check_conditions(conds)
        if errs:
            errors.extend(f"{hid} : {e}" for e in errs)
            continue
        h1 = int(h.get("horizon_h", 6))
        if h1 not in HORIZONS:
            errors.append(f"{hid} : horizon {h1} horsmur {sorted(HORIZONS)}")
            continue
        cls = str(h.get("compute_class", "small"))
        rules = CLASS_RULES.get(cls, CLASS_RULES["small"])
        sid = f"EXP-bonsai-{hid.lower()}"
        side = 1 if str(h.get("side", "short")).lower() == "long" else -1
        spec = {
            "id": sid,
            "domain": "aster",
            "family": f"bonsai_{h.get('feature', 'x')}",
            "strategy": str(h.get("mechanism", hid))[:60].replace(" ", "_").lower(),
            "hypothesis": (f"[{hid}] {h.get('mechanism', '?')} — "
                           f"{h.get('prediction', '')} "
                           f"(falsification : {h.get('falsification', '?')})"),
            "data": {"symbols": symbols, "timeframe": "1h",
                     "train_start": 1609459200000,
                     "train_end": 1756684800000,
                     "validation_start": 1756684800000,
                     "validation_end": 1790000000000},
            "mode": "discovery",
            "cost_pct": 0.28,
            "signal": {"conditions": conds, "side": side},
            "horizons": [h1],
            "criteria": {"min_n": int(rules["min_n"]),
                         "min_mean": float(rules["min_mean"])},
            "compute": {"class": cls},
            "bonsai": {"novelty": h.get("novelty"),
                       "mask_text": h.get("mask", "")},
        }
        specs.append(spec)
    return specs, errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--batch", type=int, required=True)
    ap.add_argument("--symbols",
                    default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--min-n", type=int, default=50)
    ap.add_argument("--min-mean", type=float, default=0.02)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    src = BONSAI_DIR / f"hypotheses-batch-{a.batch:03d}.json"
    batch = json.loads(src.read_text(encoding="utf-8"))
    symbols = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    specs, errors = convert(batch, symbols, a.min_n, a.min_mean)
    for e in errors:
        print(f"[rejet] {e}")
    print(f"{len(specs)} spec(s) convertible(s) sur "
          f"{len(batch.get('hypotheses', []))} hypothèse(s)")
    if a.dry_run:
        for s in specs:
            print(f"  {s['id']} : {s['strategy']} · {s['signal']['conditions']}")
        return 0
    QUEUE.mkdir(parents=True, exist_ok=True)
    for s in specs:
        out = QUEUE / f"{s['id']}.json"
        out.write_text(json.dumps(s, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print(f"  écrit : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
