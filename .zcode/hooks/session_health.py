#!/usr/bin/env python3
"""Hook SessionStart : injecte l'état de santé fomo dans le contexte de la
session (les 4 sondes du watchdog + l'état persisté) — la session démarre
en sachant si le pipeline est vert. Échoue DOUCEMENT (jamais de session
bloquée par le hook)."""
import json, subprocess, sys
from pathlib import Path

ROOT = Path("/run/media/cheurteen/Jeux SSD/trading-agent")
lines = []
try:
    r = subprocess.run([str(ROOT / ".venv" / "bin" / "python"),
                        str(ROOT / "scripts" / "fomo_health.py")],
                       capture_output=True, text=True, timeout=120)
    lines = [l for l in (r.stdout or "").splitlines() if "[health]" in l]
except Exception as e:
    lines = [f"[health] indisponible : {e}"]
try:
    st = json.loads((ROOT / "data" / "fomo" / "health_state.json").read_text())
    checks = st.get("checks", {})
    bad = [k for k, v in checks.items() if not v.get("ok", True)]
    if bad:
        lines.append(f"[health] sondes en alerte au dernier passage : {', '.join(bad)}")
except Exception:
    pass
print(json.dumps({"additionalContext": " | ".join(lines[-3:]) or "[health] aucune donnée"}))
sys.exit(0)
