#!/usr/bin/env python3
"""LE WATCHDOG DE SANTÉ FOMO (29/09) — 4 sondes toutes les 5 min, l'alerte
SUR TRANSITION seulement (une alerte à l'entrée en état mauvais, une au
retour à la normale — jamais de spam) :
1. fomo_ticks figé > 300 s = le flush du daemon est mort (la panne du 29/09)
2. fomo_rest_snapshots plus vieux que 40 min = le collector REST ne passe plus
3. les 2 caches JWT expirent < 10 min et le ws_daemon est down = la chaîne
   JWT cassée (le re-mint CDP du daemon est le seul renouvelleur)
4. > 10 « database is locked » en 30 min dans les journaux = un écrivain
   parasite est revenu (la leçon du tri-écrivain)
État : data/fomo/health_state.json (le statut par sonde + la dernière alerte).
Sortie : journal [health] + exit 0 toujours (un timer ne doit pas spamer
d'unités failed)."""
import json, sqlite3, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "fomo" / "health_state.json"
TICKS = ROOT / "data" / "fomo" / "fomo.db"
REST = ROOT / "data" / "fomo" / "fomo_rest.db"


def ro(db):
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def max_age(db, table, col="captured_at"):
    try:
        con = ro(db)
        mx, = con.execute(f"SELECT MAX({col}) FROM {table}").fetchone()
        con.close()
        return round(time.time() - mx, 1) if mx else None
    except Exception:
        return None


def jwt_exp_ok():
    """True si au moins un cache JWT tient encore > 10 min."""
    import base64
    best = 0
    for p in (ROOT / "data" / "fomo" / "ws_jwt_cache.txt",
              ROOT / "data" / "fomo" / "jwt_cache.json"):
        try:
            raw = p.read_text().strip()
            jwt = (json.loads(raw).get("jwt") if raw.startswith("{") else raw.strip('"'))
            pl = jwt.split(".")[1]
            pl += "=" * (-len(pl) % 4)
            best = max(best, json.loads(base64.urlsafe_b64decode(pl)).get("exp", 0))
        except Exception:
            continue
    return best - time.time() > 600


def daemon_active() -> bool:
    r = subprocess.run(["systemctl", "--user", "is-active", "--quiet",
                        "fomo-ws-daemon.service"], capture_output=True)
    return r.returncode == 0


def locks_recent(minutes=30) -> int:
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - minutes * 60))
    r = subprocess.run(["journalctl", "--user", "--since", since, "--no-pager",
                        "-g", "database is locked"], capture_output=True, text=True)
    return len(r.stdout.strip().splitlines()) if r.stdout.strip() else 0


CHECKS = [
    ("ticks", lambda: (max_age(TICKS, "fomo_ticks") or 9e9) < 300,
     "fomo_ticks figé — le flush du daemon est mort"),
    ("rest_collector", lambda: (max_age(REST, "fomo_rest_snapshots") or 9e9) < 2400,
     "fomo_rest_snapshots > 40 min — le collector REST ne passe plus"),
    ("jwt_chain", lambda: jwt_exp_ok() or daemon_active(),
     "JWT < 10 min et ws_daemon down — la chaîne de re-mint est cassée"),
    ("locks", lambda: locks_recent(30) <= 10,
     "> 10 « database is locked » en 30 min — un écrivain parasite est revenu"),
]


def main() -> int:
    prev = {}
    if STATE.exists():
        try:
            prev = json.loads(STATE.read_text()).get("checks", {})
        except Exception:
            prev = {}
    now = int(time.time())
    alerts = []
    checks = {}
    for name, ok, msg in CHECKS:
        good = bool(ok())
        checks[name] = {"ok": good, "at": now}
        was = prev.get(name, {}).get("ok", True)
        if not good:
            alerts.append(f"{name} : {msg}")
            if was:
                print(f"[health] ALERTE {name} : {msg}")
        elif not was and good:
            print(f"[health] rétabli : {name}")
    STATE.write_text(json.dumps({"checks": checks, "updated_at": now},
                                indent=1))
    if not alerts:
        print("[health] OK : " + ", ".join(c for c, _, _ in CHECKS))
    else:
        print(f"[health] {len(alerts)} sonde(s) en alerte (voir ci-dessus)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
