#!/usr/bin/env python3
"""LE BRIEFING QUOTIDIEN (28/09) — un seul document, chaque matin :
l'état du régime, le forward Aster, le forward fomo, les watchlists,
et les actions du jour. La lecture = 1 minute, l'action = claire."""
import sys, sqlite3, time
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
fo = sqlite3.connect(str(ROOT / "data" / "fomo" / "fomo.db"), timeout=30)
try:
    hot = fo.execute("""SELECT ticker, bonding_pct, age_minutes FROM fomo_new_coins
                        WHERE tab='bonding' AND bonding_pct >= 88
                        AND captured_at = (SELECT MAX(captured_at) FROM fomo_new_coins)
                        ORDER BY bonding_pct DESC LIMIT 5""").fetchall()
    if hot:
        add("◆ GRADUATIONS imminentes (bonding ≥ 88 %) :")
        for t in hot:
            age = f"{t[2]} min" if t[2] is not None else "?"
            add(f"   {t[0]:<12} {t[1]} % (âge {age})")
    else:
        add("◆ GRADUATIONS : aucune ≥ 88 % au dernier scan")
except Exception as e:
    add(f"◆ GRADUATIONS : indispo ({e})")

# 5. LES BALEINES 7 J (les top achats)
try:
    hot2 = fo.execute("""SELECT ticker, SUM(size_usd), COUNT(*) FROM fomo_swaps
                         WHERE side='buy' AND ts > ?
                         GROUP BY ticker ORDER BY 2 DESC LIMIT 3""",
                      ((now.timestamp() - 7 * 86400) * 1000,)).fetchall()
    if hot2:
        add("◆ BALEINES 7 j (top achats) : " +
            ", ".join(f"{t} ${v/1000:.0f}k ({n})" for t, v, n in hot2))
except Exception:
    pass

# 6. LES ACTIONS DU JOUR
add("◆ ACTIONS du jour :")
add("   1. Lis les signaux machine_* ouverts ci-dessus — l'exécution = tes mains, la sortie = l'horizon du signal")
add("   2. derek518 CLOSED ≥ 5 ? → le verdict réplication tombe")
add("   3. Le 06-08/10 : les 5 couches institutionnelles tirent (pré-construites)")

out = "\n".join(L)
print(out)
with open(LOG, "a") as f:
    f.write(out + "\n")
