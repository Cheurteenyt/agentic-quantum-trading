#!/usr/bin/env python3
"""LE BRIEFING QUOTIDIEN (28/09) — un seul document, chaque matin :
l'état du régime, le forward Aster, le forward fomo, les watchlists,
et les actions du jour. La lecture = 1 minute, l'action = claire."""
import sys, sqlite3, time, json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOG = ROOT / "reports" / "daily-brief.log"
L = []


def add(s=""):
    L.append(s)


now = datetime.now(timezone.utc)
add(f"════ BRIEFING QUOTIDIEN — {now:%d/%m/%Y %H:%M} UTC ════")

# 1. LE RÉGIME (l'adaptateur) — la dernière ligne du moniteur
log = ROOT / "reports" / "edge-regime-monitor.log"
if log.exists():
    add("◆ RÉGIME cascade : " + log.read_text().strip().split("\n")[-1].split("| ")[-1])

# 2. LE FORWARD ASTER (les 7 derniers jours clôturés + les totaux par flux)
try:
    con = sqlite3.connect(str(ROOT / "data" / "warehouse" / "klines.db"), timeout=30)
    cut = (now.timestamp() - 7 * 86400) * 1000
    add("◆ FORWARD Aster (7 j clôturés) :")
    for r in con.execute("""SELECT signal, COUNT(*), SUM(CASE WHEN ret_pct>0 THEN 1 ELSE 0 END),
                            ROUND(SUM(ret_pct),1) FROM paper_trades
                            WHERE status='closed' AND exit_ts > ? AND signal LIKE 'machine%'
                            GROUP BY signal""", (cut,)).fetchall():
        n, w, tot = r[1], r[2] or 0, r[3]
        add(f"   {r[0]:<28} {n:3d} trades | WR {w/n*100:.0f} % | ret cum {tot:+.1f} %")
    n_open = con.execute("SELECT COUNT(*) FROM paper_trades WHERE status='open' AND signal LIKE 'machine%'").fetchone()[0]
    add(f"   ouverts : {n_open}")

    # 2bis. CE QUE LES 24 H ONT APPRIS (le learn du jour — exigence user 02/10)
    cut24 = (now.timestamp() - 24 * 3600) * 1000
    add("◆ LEARN 24 h (les trades clos des dernières 24 h — indicatif horizons, le wallet juge) :")
    for r in con.execute("""SELECT signal, COUNT(*), SUM(CASE WHEN ret_pct>0 THEN 1 ELSE 0 END),
                            ROUND(AVG(ret_pct),2) FROM paper_trades
                            WHERE status='closed' AND exit_ts > ? AND signal LIKE 'machine%'
                            GROUP BY signal ORDER BY 4 DESC""", (cut24,)).fetchall():
        n, w, avg = r[1], r[2] or 0, r[3]
        flag = "  <<<" if abs(avg) >= 2.0 and n >= 5 else ""
        add(f"   {r[0]:<32} {n:3d} clos | WR {w/n*100:.0f} % | moy {avg:+.2f} %{flag}")
    sv = con.execute("SELECT COUNT(*), ROUND(AVG(ret_pct),2) FROM aster_survivors_paper WHERE status='closed'").fetchone()
    sv_open = con.execute("SELECT COUNT(*) FROM aster_survivors_paper WHERE status='open'").fetchone()[0]
    add(f"   survivants (verdict 90 j) : {sv_open} ouverts | {sv[0]} clos, ret moy {sv[1] or 0:+.2f} %")

    # 2ter. LES COMPTEURS DE MATURITÉ (quand chaque invention débloque — calendrier Ariad id 18)
    liq_n = con.execute("SELECT COUNT(*) FROM liq_events").fetchone()[0]
    oi_days = con.execute("SELECT ROUND((MAX(captured_at_ms)-MIN(captured_at_ms))/86400000.0,1) FROM oi_history").fetchone()[0]
    con.close()
    try:
        con2 = sqlite3.connect(f"file:{ROOT / 'data' / 'warehouse' / 'depth.db'}?mode=ro", uri=True)
        dd = con2.execute("SELECT ROUND((MAX(ts)-MIN(ts))/86400.0,1) FROM depth_meta").fetchone()[0]
        con2.close()
    except Exception as e2:
        dd = -1
    maturite = f"liq {liq_n} evts (seuil gelable ~22/10) | OI {oi_days} j (tir H4/H5 06-07) | depth {dd} j (tir murs 13/10) | premium/OI-bulk ~28-30/10"
    add("◆ MATURITÉ : " + maturite)
except Exception as e:
    add(f"◆ FORWARD Aster : indispo ({e})")

# 3. LE FORWARD FOMO (les règles, le derek)
fp = ROOT / "data" / "fomo" / "fomo_paper.db"
if fp.exists():
    c2 = sqlite3.connect(str(fp), timeout=30)
    add("◆ FORWARD fomo :")
    for r in c2.execute("""SELECT rule, SUM(status='OPEN'), SUM(status='CLOSED'),
                           SUM(CASE WHEN status='CLOSED' AND multiple>1 THEN 1 ELSE 0 END)
                           FROM fomo_paper_trades GROUP BY rule""").fetchall():
        add(f"   {r[0]:<20} open {r[1]:3d} | closed {r[2]:3d} | WR {r[3]/max(r[2],1)*100:.0f} %")
    derek_open = c2.execute("SELECT COUNT(*) FROM fomo_paper_trades WHERE rule='replication_derek' AND status='OPEN'").fetchone()[0]
    derek_clo = c2.execute("SELECT COUNT(*) FROM fomo_paper_trades WHERE rule='replication_derek' AND status='CLOSED'").fetchone()[0]
    add(f"   → derek518 : verdict à ≥ 5 CLOSED (actuellement {derek_clo} closed, {derek_open} open)")

# 4. LES GRADUATIONS IMMINENTES (bonding_pct ≥ 88 %, les plus fraîches)
# MIGRATION REST (29/09) : fomo_new_coins mort → snapshot REST bonding
# (fomo_rest.db fomo_rest_snapshots endpoint='bonding_snapshot', même forme).
# D-10 (ronde 6) : le connect était HORS du try — un répertoire data/fomo
# absent tuait le brief entier (traceback, sections 5-6 + log perdus) au
# lieu d'une section « indispo » comme les autres.
try:
    fo = sqlite3.connect(str(ROOT / "data" / "fomo" / "fomo_rest.db"), timeout=30)
    rows = []
    for mint, raw, cap in fo.execute(
            "SELECT entity_id, data, captured_at FROM fomo_rest_snapshots "
            "WHERE endpoint='bonding_snapshot'").fetchall():
        d = json.loads(raw)
        tok = d.get("token") or {}
        pct = (tok.get("launchpad") or {}).get("graduationPercent")
        if pct is None:
            continue
        age = max(0, int((cap - (tok.get("createdAt") or cap)) / 60))
        rows.append((tok.get("symbol") or mint[:8], round(float(pct), 2), age))
    hot = sorted((r for r in rows if r[1] >= 88), key=lambda r: -r[1])[:5]
    if hot:
        add("◆ GRADUATIONS imminentes (bonding ≥ 88 %) :")
        for t in hot:
            age = f"{t[2]} min" if t[2] is not None else "?"
            add(f"   {t[0]:<12} {t[1]} % (âge {age})")
    else:
        add("◆ GRADUATIONS : aucune ≥ 88 % au dernier scan")
except Exception as e:
    add(f"◆ GRADUATIONS : indispo ({e})")

# 5. LES BALEINES 7 J (les top achats) — fomo_swaps vit dans fomo_swaps.db, ts en SECONDES
try:
    fs = sqlite3.connect(str(ROOT / "data" / "fomo" / "fomo_swaps.db"), timeout=30)
    hot2 = fs.execute("""SELECT ticker, SUM(size_usd), COUNT(*) FROM fomo_swaps
                         WHERE side='buy' AND ts > ?
                         GROUP BY ticker ORDER BY 2 DESC LIMIT 3""",
                      (now.timestamp() - 7 * 86400,)).fetchall()
    if hot2:
        add("◆ BALEINES 7 j (top achats) : " +
            ", ".join(f"{t} ${v/1000:.0f}k ({n})" for t, v, n in hot2))
    else:
        add("◆ BALEINES 7 j : aucun achat")
except Exception as e:
    add(f"◆ BALEINES : indispo ({e})")

# 6. LES ACTIONS DU JOUR
add("◆ ACTIONS du jour :")
add("   1. Lis les signaux machine_* ouverts ci-dessus — l'exécution = tes mains, la sortie = l'horizon du signal")
add("   2. derek518 CLOSED ≥ 5 ? → le verdict réplication tombe")
add("   3. Le 06-08/10 : les 5 couches institutionnelles tirent (pré-construites)")

out = "\n".join(L)
print(out)
with open(LOG, "a") as f:
    f.write(out + "\n")
