#!/usr/bin/env python
"""LA VALIDATION DU PARSEUR X — l'étude scellée du protocole Bonsai (05/10).

La question : le WR du feed X-calls est-il du BRUIT DE PARSING ou un PHÉNOMÈNE ?
Le protocole : échantillon stratifié par horizon, les taux de NULL par seuil
(entry < 20 % acceptable, horizon 'none' < 50 %), et LA RE-EXTRACTION depuis le
texte du post — si le texte CONTIENT l'info que le parseur a manquée, c'est un
bug de parseur ; si elle n'y est pas, c'est la nature du feed.

Le tranchage du WR : WR(avec entry) vs WR(sans entry) — si les deux collent,
la sélection ne biais rien et le WR reflète le feed entier.

Verdicts relatifs seulement — les absos dépendent de l'engine de scoring.
"""
from __future__ import annotations

import random
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "warehouse" / "x_posts.db"
N_SAMPLE = 100

ENTRY_PAT = re.compile(
    r"(?:entry|entrée|@|at|prix|price)\s*:?\s*\$?(\d+(?:[.,]\d+)?)", re.I)
DIRECTION_PAT = re.compile(
    r"\b(long|short|buy|sell|bullish|bearish|achat|vente|acheter|vendre)\b", re.I)
HORIZON_PAT = re.compile(
    r"\b(scalp|intraday|day ?trade|short ?term|swing|mid ?term|long ?term|week|month)\b", re.I)
TP_PAT = re.compile(r"\b(?:tp|take ?profit|target|objectif)\s*[:\-$]?\s*(\d+(?:[.,]\d+)?)", re.I)
SL_PAT = re.compile(r"\b(?:sl|stop ?loss|stop)\s*[:\-$]?\s*(\d+(?:[.,]\d+)?)", re.I)


def re_extract(text: str) -> dict:
    """Ce que le TEXTE contient, indépendamment du parseur (les patterns larges)."""
    t = text or ""
    return {
        "has_direction": bool(DIRECTION_PAT.search(t)),
        "has_entry": bool(ENTRY_PAT.search(t)),
        "has_horizon": bool(HORIZON_PAT.search(t)),
        "has_tp": bool(TP_PAT.search(t)),
        "has_sl": bool(SL_PAT.search(t)),
    }


def main() -> None:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    calls = con.execute("""SELECT c.call_id, c.symbol, c.direction, c.entry_price,
                           c.horizon, c.tp_price, c.sl_price, p.text
                           FROM x_calls c LEFT JOIN x_posts p USING(post_id)""").fetchall()
    n_total = len(calls)

    # ——— 1. les taux de NULL (population entière, pas l'échantillon) ———
    n_none = sum(1 for c in calls if (c["horizon"] or "none") == "none")
    n_entry = sum(1 for c in calls if c["entry_price"] and c["entry_price"] > 0)
    n_exit = sum(1 for c in calls if c["direction"] not in ("long", "short"))
    print("=== POPULATION (627 calls) ===")
    print(f"horizon 'none'   : {n_none}/{n_total} ({n_none / n_total:.0%}) — seuil 50 %")
    print(f"entry_price > 0  : {n_entry}/{n_total} ({n_entry / n_total:.0%}) — seuil 80 %")
    print(f"directions invalides : {n_exit} (les 'exit' du parseur)")

    # ——— 2. l'échantillon stratifié par horizon (proportionnel) ———
    random.seed(20261005)
    by_h: dict[str, list] = {}
    for c in calls:
        by_h.setdefault(c["horizon"] or "none", []).append(c)
    sample = []
    for h, rows in by_h.items():
        k = round(N_SAMPLE * len(rows) / n_total)
        sample += random.sample(rows, min(k, len(rows)))
    print(f"\n=== ÉCHANTILLON STRATIFIÉ (n={len(sample)}) ===")

    # ——— 3. la re-extraction : ce que le TEXTE contient vs le parseur ———
    missed = {"entry": 0, "horizon": 0, "direction": 0, "texte_vide": 0}
    has_tp_sl_text = 0
    for c in sample:
        rx = re_extract(c["text"])
        if not (c["text"] or "").strip():
            missed["texte_vide"] += 1
            continue
        if rx["has_entry"] and not (c["entry_price"] and c["entry_price"] > 0):
            missed["entry"] += 1
        if rx["has_horizon"] and (c["horizon"] or "none") == "none":
            missed["horizon"] += 1
        if rx["has_direction"] and c["direction"] not in ("long", "short"):
            missed["direction"] += 1
        if rx["has_tp"] or rx["has_sl"]:
            has_tp_sl_text += 1
    n_texte = len(sample) - missed["texte_vide"]
    print(f"posts sans texte : {missed['texte_vide']}/{len(sample)}")
    if n_texte:
        print(f"entry DANS le texte mais non parsée  : {missed['entry']}/{n_texte}")
        print(f"horizon DANS le texte mais non parsé : {missed['horizon']}/{n_texte}")
        print(f"TP/SL dans le texte : {has_tp_sl_text}/{n_texte}")

    # ——— 4. le tranchage du WR (population scorée entière) ———
    wr_with = con.execute("""SELECT AVG(CASE WHEN s.ret_24h>0 THEN 1.0 ELSE 0 END), COUNT(*)
        FROM x_call_scores s JOIN x_calls c USING(call_id)
        WHERE c.entry_price IS NOT NULL AND c.entry_price>0""").fetchone()
    wr_without = con.execute("""SELECT AVG(CASE WHEN s.ret_24h>0 THEN 1.0 ELSE 0 END), COUNT(*)
        FROM x_call_scores s JOIN x_calls c USING(call_id)
        WHERE c.entry_price IS NULL OR c.entry_price<=0""").fetchone()
    wr_all = con.execute("""SELECT AVG(CASE WHEN ret_24h>0 THEN 1.0 ELSE 0 END), COUNT(*)
        FROM x_call_scores""").fetchone()
    print("\n=== LE WR : BRUIT OU PHÉNOMÈNE (24 h, engine courant) ===")
    print(f"WR global          : {wr_all[0]:.1%} (n={wr_all[1]})")
    print(f"WR avec entry>0    : {wr_with[0]:.1%} (n={wr_with[1]})")
    print(f"WR sans entry      : {wr_without[0]:.1%} (n={wr_without[1]})")
    delta = abs((wr_with[0] or 0) - (wr_without[0] or 0))
    print(f"delta |avec−sans|  : {delta:.1%} — si < 5 pts : la sélection ne biais rien")

    # ——— 5. le verdict mécanique ———
    print("\n=== VERDICT (les seuils du protocole) ===")
    v_entry = "PASS" if n_entry / n_total >= 0.8 else "FAIL"
    v_horizon = "PASS" if n_none / n_total <= 0.5 else "FAIL"
    v_bias = "PAS DE BIAIS DE SÉLECTION" if delta < 0.05 else "BIAIS DE SÉLECTION"
    print(f"entry_price ≥ 80 %  : {v_entry} ({n_entry / n_total:.0%})")
    print(f"horizon 'none' ≤ 50 % : {v_horizon} ({n_none / n_total:.0%})")
    print(f"WR : {v_bias} — WR global {wr_all[0]:.1%} < 50 % = le feed perd sous 0 avant coûts")
    con.close()


if __name__ == "__main__":
    main()
