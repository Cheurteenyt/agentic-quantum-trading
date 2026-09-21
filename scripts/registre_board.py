#!/usr/bin/env python3
"""Registre X — scoreboard HTML + draft de post, generes a chaque cycle.

    python scripts/registre_board.py

Ecrit :
  - reports/registre-board.html           (chemin fixe, a ouvrir)
  - reports/registre-board-<ts>.html      (historise)
  - reports/registre-draft-post.txt       (draft a reviser avant publication)

Le board n'invente rien : il lit x_posts.db (posts, calls, scores, verdicts).
Les agregats par compte restent absents sous 10 calls verdicts — regle
anti-petits-echantillons, pre-enregistree avant que les donnees n'arrivent.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_x_posts import _connect  # noqa: E402

REPORTS = ROOT / "reports"
BOARD = REPORTS / "registre-board.html"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pct(v: float | None) -> str:
    return f"{v * 100:+.2f} %" if v is not None else "—"


def _load(con: sqlite3.Connection) -> dict:
    posts = con.execute("SELECT COUNT(*) FROM x_posts").fetchone()[0]
    accounts = con.execute(
        "SELECT COUNT(*) FROM x_accounts WHERE active = 1"
    ).fetchone()[0]
    calls = con.execute(
        """
        SELECT p.author_handle, p.posted_at_raw, c.symbol, c.direction,
               c.entry_price, c.tp_price, c.sl_price, c.confidence,
               s.status, s.entry_resolved, s.ret_1h, s.ret_24h, s.ret_7d,
               v.verdict
        FROM x_calls c
        JOIN x_posts p ON p.post_id = c.post_id
        LEFT JOIN x_call_scores s ON s.call_id = c.call_id
        LEFT JOIN x_call_verdicts v ON v.call_id = c.call_id
        WHERE c.parser_version = (SELECT MAX(parser_version) FROM x_calls)
        ORDER BY c.call_id
        """
    ).fetchall()
    positioning = con.execute(
        "SELECT day, symbol, n_calls, pct_long FROM x_positioning "
        "ORDER BY day DESC, symbol LIMIT 10"
    ).fetchall()
    mentions = con.execute(
        "SELECT symbol, day, n, total_likes, total_views FROM x_mentions "
        "ORDER BY day DESC, n DESC LIMIT 10"
    ).fetchall()
    return {"posts": posts, "accounts": accounts, "calls": calls,
            "positioning": positioning, "mentions": mentions}


def _render(data: dict) -> str:
    now = _utc_now()
    n_win = sum(1 for c in data["calls"] if c[13] == "win")
    n_loss = sum(1 for c in data["calls"] if c[13] == "loss")
    n_live = sum(1 for c in data["calls"] if c[13] in ("en_cours", None))
    pos_rows = "\n".join(
        f"<tr><td>{day}</td><td>{sym}</td><td>{n}</td>"
        f"<td class=\"{'long' if pct >= 50 else 'short'}\">{pct:.0f} % long</td></tr>"
        for day, sym, n, pct in data["positioning"]
    ) or "<tr><td colspan='4'>positionnement observé à partir du 1er call</td></tr>"
    men_rows = "\n".join(
        f"<tr><td>${sym}</td><td>{day}</td><td>{n} posts</td>"
        f"<td>{likes:,} likes</td><td>{views:,} vues</td></tr>".replace(",", " ")
        for sym, day, n, likes, views in data["mentions"]
    ) or "<tr><td colspan='5'>vélocité des mentions : s'accumule chaque nuit</td></tr>"
    rows_html = []
    for (handle, when, sym, direction, declared, tp, sl, conf,
         status, resolved, r1, r24, r7, verdict) in data["calls"]:
        entry = (
            f"{declared:,.0f}".replace(",", " ") if declared
            else (f"{resolved:,.0f}".replace(",", " ") if resolved else "—")
        )
        tpsl = f"{tp:,.0f} / {sl:,.0f}".replace(",", " ") if tp and sl else "—"
        v_class = {"win": "win", "loss": "loss", "indecis": "flat"}.get(verdict or "", "flat")
        v_label = {"win": "✓ win", "loss": "✗ loss", "indecis": "— indécis"}.get(
            verdict or "", "⏳ en cours" if status == "partiel" else (status or "—")
        )
        rows_html.append(
            f"<tr><td>@{handle}</td><td>{sym}</td>"
            f"<td class=\"{'long' if direction == 'long' else 'short'}\">"
            f"{direction.upper()}</td><td>{entry}</td><td>{tpsl}</td>"
            f"<td>{_pct(r1)}</td><td>{_pct(r24)}</td>"
            f"<td class=\"{v_class}\">{v_label}</td></tr>"
        )
    calls_rows = "\n".join(rows_html) or "<tr><td colspan='8'>aucun call</td></tr>"
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>Le Registre — crypto twitter tenu au score</title>
<style>
  body {{ background:#0d1117; color:#c9d1d9; font-family:ui-sans-serif,system-ui;
         max-width:960px; margin:2rem auto; padding:0 1rem; }}
  h1 {{ color:#58a6ff; font-size:1.5rem; }} h2 {{ font-size:1.1rem; margin-top:2rem; }}
  .cards {{ display:flex; gap:1rem; flex-wrap:wrap; margin:1rem 0; }}
  .card {{ background:#161b22; border:1px solid #30363d; border-radius:8px;
           padding:0.8rem 1.2rem; }}
  .card b {{ display:block; font-size:1.6rem; color:#e6edf3; }}
  table {{ border-collapse:collapse; width:100%; font-size:0.85rem; }}
  th, td {{ border:1px solid #30363d; padding:0.35rem 0.6rem; text-align:left; }}
  th {{ background:#161b22; color:#8b949e; }}
  .long {{ color:#3fb950; font-weight:600; }} .short {{ color:#f85149; font-weight:600; }}
  .win {{ color:#3fb950; }} .loss {{ color:#f85149; }} .flat {{ color:#8b949e; }}
  .note {{ color:#8b949e; font-size:0.8rem; border-left:3px solid #30363d;
           padding-left:0.8rem; }}
  .meta {{ color:#8b949e; font-size:0.75rem; }}
</style></head><body>
<h1>📋 Le Registre — crypto twitter, tenu au score</h1>
<p class="meta">généré : {now} UTC — moteur : lecture seule de x_posts.db</p>
<div class="cards">
  <div class="card"><b>{data['posts']}</b>posts en base</div>
  <div class="card"><b>{data['accounts']}</b>comptes en watchlist</div>
  <div class="card"><b>{len(data['calls'])}</b>calls trackés</div>
  <div class="card"><b>{n_win}</b><span style="color:#3fb950">wins</span></div>
  <div class="card"><b>{n_loss}</b><span style="color:#f85149">loss</span></div>
  <div class="card"><b>{n_live}</b>en cours</div>
</div>
<h2>Calls</h2>
<table>
<tr><th>compte</th><th>actif</th><th>direction</th><th>entrée</th>
<th>TP / SL</th><th>+1h</th><th>+24h</th><th>verdict</th></tr>
{calls_rows}
</table>
<h2>Règle de lecture</h2>
<p class="note">Rendements directionnels (short = inverse), frais et slippage
exclus : on mesure les comptes, pas une stratégie exécutable. Les agrégats
par compte apparaissent seulement à partir de 10 calls avec verdict —
un hit rate sur 2-3 posts, c'est se mentir avec un petit échantillon.
Verdict « indécis » = TP et SL touchés dans la même bougie : l'ordre
intra-bougie est inconnaissable, et deviner serait mentir.</p>
<h2>Positionnement de la foule (observé)</h2>
<table>
<tr><th>jour</th><th>actif</th><th>calls</th><th>consensus</th></tr>
{pos_rows}
</table>
<p class="note">Un consensus extrême (>&nbsp;80 % d'un côté) est le candidat
idéal pour un facteur contrarian — à backtester sur 2-4 semaines
d'accumulation, pas avant.</p>
<h2>Vélocité des mentions (échantillon nocturne)</h2>
<table>
<tr><th>cashtag</th><th>jour</th><th>posts</th><th>engagement</th></tr>
{men_rows}
</table>
<p class="note">Échantillon de nos collectes, pas un total absolu —
comparable d'une nuit à l'autre car le protocole est constant.</p>
<p class="meta">Le Registre ne prouve aucun edge. Il tient le score.</p>
</body></html>
"""


def _draft_post(data: dict) -> str:
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    n_win = sum(1 for c in data["calls"] if c[13] == "win")
    n_loss = sum(1 for c in data["calls"] if c[13] == "loss")
    n = len(data["calls"])
    lines = [
        f"📋 Le Registre — {now}",
        "",
        f"{n} calls $BTC / $ETH trackés depuis crypto twitter.",
    ]
    if n_win + n_loss:
        lines.append(f"Verdicts rejoués sur les bougies réelles : "
                     f"{n_win} win / {n_loss} loss.")
    else:
        lines.append("Premiers verdicts en maturation (TP/SL rejoués "
                     "bougie par bougie, ou rendements à +24h/+7j).")
    lines += [
        "",
        "Pas de hit rate affiché : aucun compte n'a encore 10 calls verdicts.",
        "Un taux de réussite sur 3 posts, c'est du bruit qui se déguise en talent.",
        "",
        "#crypto #bitcoin",
    ]
    return "\n".join(lines)


def main() -> int:
    con = _connect()
    data = _load(con)
    con.close()
    REPORTS.mkdir(parents=True, exist_ok=True)
    html = _render(data)
    BOARD.write_text(html, encoding="utf-8")
    ts = _utc_now().replace(":", "").replace("-", "")
    (REPORTS / f"registre-board-{ts}.html").write_text(html, encoding="utf-8")
    draft = _draft_post(data)
    (REPORTS / "registre-draft-post.txt").write_text(draft, encoding="utf-8")
    # canal push : le produit vendable du registre (no-op si non configure)
    from scripts.telegram_notify import send_if_configured
    send_if_configured(draft)
    print(f"[registre] board : {BOARD}")
    print("[registre] draft post : reports/registre-draft-post.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
