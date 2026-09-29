#!/usr/bin/env python3
"""Le parseur de la table HOLDERS d'une page token fomo — l'intelligence
par token que le flux WS ne donne pas : QUI détient, combien, son PnL,
son MC d'entrée moyen, son hold moyen, sa thèse.

La structure du texte (validée sur PARASITE) :
  Handle
  4d 16h avg. hold
  $47,914.43            ← la valeur de la position
  19.4M PARASITE        ← la quantité
  +
  $51,490.97            ← le PnL $
  ▲
  3,455.19%             ← le PnL %
  $66K MC               ← le MC d'entrée moyen
  $0.046888             ← le prix d'entrée moyen
  191                   ← les likes de la thèse (optionnel)
  <le texte de la thèse>  (optionnel)
"""
import re

HOLD_BLOCK = re.compile(
    r"(?m)^([^\n$]+)\n(\d+[dhm\d ]*) avg\. hold\n"
    r"(?:Received from external wallet\n)?"
    r"\$([\d,]+(?:\.\d+)?)\n"
    r"([\d.,]+[KMB]?) ([A-Z0-9\u4e00-\u9fff/\-]+)\n"
    r"([+\-])\n\$([\d,]+(?:\.\d+)?)\n[▲▼]\n([\d.,]+)%\n"
    r"\$([\d.,]+[KMB]?) MC\n\$([\d.,]+)\n")


def parse_holders(text, ticker):
    """Les holders : le nom, la valeur, la qty, le ±PnL$/%, le MC d'entrée,
    le prix d'entrée, le hold. La thèse = le texte après le bloc jusqu'au
    prochain handle (lignes suivantes non structurées)."""
    out = []
    matches = list(HOLD_BLOCK.finditer(text))
    for i, m in enumerate(matches):
        (handle, hold, value, qty, tk, sign, pnl, pct, entry_mc, entry_px) = m.groups()
        # les likes = la ligne pure-digits juste après le bloc ; la thèse = le reste
        tail = text[m.end():matches[i + 1].start() if i + 1 < len(matches) else m.end() + 400]
        lines = [l.strip() for l in tail.split("\n") if l.strip()]
        likes, thesis = None, ""
        if lines and re.fullmatch(r"\d{1,4}", lines[0]):
            likes = int(lines[0])
            lines = lines[1:]
        if lines and not re.match(r"^\$", lines[0]):
            thesis = lines[0][:300]
        out.append({
            "handle": handle.strip(),
            "avg_hold": hold.strip(),
            "position_usd": float(value.replace(",", "")),
            "qty": qty,
            "ticker": tk,
            "pnl_usd": float(pnl.replace(",", "")) * (1 if sign == "+" else -1),
            "pnl_pct": float(pct.replace(",", "")) * (1 if sign == "+" else -1),
            "entry_mc": entry_mc,
            "entry_price": float(entry_px),
            "thesis_likes": likes,
            "thesis": thesis,
        })
    return out


def parse_token_header(text):
    """Le header de la page token : MC, prix, holders, liquidité, top-10
    holding, la pression acheteurs/vendeurs du panneau droit."""
    def grab(label):
        m = re.search(re.escape(label) + r"\s*\n?\s*\$?([\d.,]+[KMBkmb]?)", text)
        return m.group(1) if m else None

    holders = re.search(r"Holders\s*\n?\s*([\d.,]+[KMBkmb]?)", text)
    top10 = re.search(r"Top 10 holding\s*\n?\s*([\d.]+)%", text)
    liq = re.search(r"Liquidity\s*\n?\s*\$?([\d.,]+[KMBkmb]?)", text)
    mc = re.search(r"Market cap\s*\n?\s*\$([\d.,]+[KMB]?)", text)
    buys = re.search(r"([\d,]+) buys\s*\n?\s*([\d,]+) sells", text)
    buyers = re.search(r"([\d,]+) buyers\s*\n?\s*([\d,]+) sellers", text)
    return {
        "market_cap": mc.group(1) if mc else None,
        "holders": holders.group(1) if holders else None,
        "liquidity": liq.group(1) if liq else None,
        "top10_holding_pct": float(top10.group(1)) if top10 else None,
        "buys": int(buys.group(1).replace(",", "")) if buys else None,
        "sells": int(buys.group(2).replace(",", "")) if buys else None,
        "buyers": int(buyers.group(1).replace(",", "")) if buyers else None,
        "sellers": int(buyers.group(2).replace(",", "")) if buyers else None,
    }
