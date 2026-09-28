#!/usr/bin/env python3
"""Le garde de la fenêtre fomo (28/09) : la fenêtre fomo-whale doit vivre
sur special:fomo (-98). La course au démarrage du daemon peut la poser
sur le workspace actif (visible par le user) → si dérive : restart du
daemon (la window rule la re-assigne à la création) + restart du
collector (son CDP meurt avec le browser). Silencieux si propre."""
import subprocess, sys, json, time

def fomo_window_ws() -> tuple[str, str]:
    out = subprocess.run(["hyprctl", "-j", "clients"], capture_output=True, text=True).stdout
    for w in json.loads(out or "[]"):
        if w.get("class") == "fomo-whale":
            return w["address"], str(w["workspace"]["id"])
    return "", "absente"

addr, ws = fomo_window_ws()
if not addr:
    print("[window-guard] pas de fenêtre fomo-whale — le daemon ne tourne pas ?")
    sys.exit(0)
if ws == "-98":
    print("[window-guard] OK : la fenêtre est sur special:fomo")
    sys.exit(0)
print(f"[window-guard] DÉRIVE : la fenêtre est sur le workspace {ws} — restart daemon+collector")
subprocess.run(["systemctl", "--user", "restart", "fomo-browser.service"], capture_output=True)
time.sleep(8)
subprocess.run(["systemctl", "--user", "restart", "fomo-tick-collector.service"], capture_output=True)
addr2, ws2 = fomo_window_ws()
print(f"[window-guard] après fix : workspace {ws2}")
sys.exit(0 if ws2 == "-98" else 1)
