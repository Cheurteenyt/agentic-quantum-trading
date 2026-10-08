#!/usr/bin/env python3
"""LE WATCHDOG DE SANTÉ ASTER (30/09) — le symétrique de fomo_health.py pour
le domaine Aster. 14 sondes toutes les 5 min, l'alerte SUR TRANSITION :
1. klines 1h fraîches (< 25 h — le nocturne 03:00)
2. oi_history fraîche (< 30 min — timer 15 min, la munition H4/H5 du 06-07)
3. oi_history_bulk fraîche (< 30 min — la passe bulk bapi de oi_collector,
   ~642 symboles en 1 appel, unités notional ×2)
4. liq_events fraîche (< 30 min)
5. block_trades fraîche (< 30 min)
6. premium_history fraîche (< 10 min — WS !markPrice@arr @1s, service
   aster-markprice-ws 24/7, remplace le REST 15 min depuis le 30/09)
7. depth_meta fraîche (< 10 min — le collecteur 24/7, cadence ~1 min)
8. depth CONTINUITÉ : 0 trou > 15 min dans depth_meta sur 24 h (le tir
   depth/murs du 06-07 exige 14 j sans coupure — tolérance zéro)
9. funding_meta fraîche (< 90 min — le timer aster-funding-bulk 2×/h,
   764 symboles, les intervalles 1/2/4/8 h par symbole pour funding_fade)
10. le cache funding (< 25 h — le nocturne)
10 bis. la COUVERTURE du cache funding (≥ 80 % des symboles < 25 h — le
   MAX du n°10 est aveugle au cache PARTIELLEMENT frais : 23/73 suffisaient
   à le rendre vert pendant que le scanner rangeait sur un univers résiduel)
11. rate_weight : le budget X-MBX-USED-WEIGHT-1M vu par les collecteurs
   (< 1800 = 75 % de 2 400/min — seuil INCHANGÉ ; le bulk bapi n'expose pas
   le header, seul fapi alimente le compteur)
12. traders_registry : le registre longitudinal des traders (< 30 h — le
   timer 06:50 aster-traders-registry, leaderboard + points par adresse)
13. survivors_forward : le ledger papier des survivants T21 (< 30 h — le
   timer quotidien 06:55 aster-survivors-forward ; fraîcheur = l'epoch du
   dernier tir réussi, aster_survivors_meta.last_run_epoch écrit APRÈS commit
   — un marché sans signal ne fait pas vieillir la sonde)
État : data/warehouse/aster_health_state.json. Journal [aster-health].
Exit 0 toujours (un timer ne doit pas spammer d'unités failed)."""
import json, os, sqlite3, subprocess, sys, time
from pathlib import Path

import aster_rate  # le compteur de poids X-MBX-USED-WEIGHT-1M (docs/24)

ROOT = Path(__file__).resolve().parents[1]
KL = ROOT / "data" / "warehouse" / "klines.db"
DEPTH = ROOT / "data" / "warehouse" / "depth.db"
STATE = ROOT / "data" / "warehouse" / "aster_health_state.json"
STATE_REG = ROOT / "data" / "warehouse" / "aster_traders_state.json"
CACHE = ROOT / "backend" / "services" / "onchain" / "aster" / "aster_public_funding_history_cache.json"


def ro(db):
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)


def _norm_ms(v):
    return v / 1000.0 if v and v > 1e12 else float(v or 0)


def max_age(db, sql):
    """L'âge en secondes du MAX(col) — sql renvoie une valeur ms OU s."""
    try:
        con = ro(db)
        v = con.execute(sql).fetchone()[0]
        con.close()
        return round(time.time() - _norm_ms(v), 1) if v else None
    except Exception:
        return None


def depth_gaps_24h() -> int:
    """Le nombre de trous > 15 min dans depth_meta sur les dernières 24 h.
    ATTENTION aux unités : depth_meta.ts est en SECONDES (vérifié 30/09 —
    un filtre en ms ne renvoyait AUCUNE ligne = vert mensonger)."""
    try:
        con = ro(DEPTH)
        rows = [r[0] for r in con.execute(
            "SELECT DISTINCT ts FROM depth_meta WHERE ts > ? ORDER BY ts",
            (int(time.time() - 86400),)).fetchall()]
        con.close()
        if len(rows) < 2:
            return 0
        gaps = sum(1 for a, b in zip(rows, rows[1:]) if b - a > 15 * 60)
        return gaps
    except Exception:
        return -1  # -1 = la sonde elle-même a échoué (alerte)


def funding_cache_age() -> float:
    """L'âge du cache funding — le MAX des `cached_at` par symbole.
    (FIX R3/B-B : la docstring disait « MIN » depuis F-042 alors que le code
    fait bien un MAX — cf. la preuve ci-dessous.)

    FIX F-041 : l'ancienne sonde lisait le `mtime` du FICHIER (15,5 h en
    prod) alors que 48 des 73 symboles ont un `cached_at` > 25 h, dont
    9 > 30 j et un à 127 j. Le mtime ne bouge que quand le fichier est
    réécrit — un symbole non rafraîchi garde sa vieille valeur ET le
    fichier est touché par les autres symboles. La sonde était donc
    structurellement incapable de voir la péremption.

    Le MAX des `cached_at` est la seule lecture honnête : c'est l'âge du
    symbole le PLUS FRAIS. Si même lui est vieux, tout le cache l'est.
    """
    try:
        with CACHE.open(encoding="utf-8") as fh:
            blob = json.load(fh)
    except Exception:
        return None
    stamps: list[float] = []
    for entry in (blob.get("symbols") or {}).values():
        if isinstance(entry, dict):
            val = entry.get("cached_at")
            if isinstance(val, (int, float)) and val > 0:
                stamps.append(float(val))
    if not stamps:
        return None
    return round(time.time() - max(stamps), 1)


def funding_cache_coverage() -> float:
    """FIX R3 (C-C4) : la fraction de symboles du cache funding frais (< 25 h).

    La sonde MAX (funding_cache_age) ne voit pas le cache partiellement
    frais : la vague nocturne du 07/10 ne rafraîchissait que 23 des 73
    symboles (cf. C-C2) et la sonde restait VERTE à 0,89 j, pendant que
    funding_scanner/carry_hedged rangeaient sur un univers résiduel.
    -1.0 = la sonde elle-même a échoué (convention depth_gaps_24h → alerte).
    """
    try:
        with CACHE.open(encoding="utf-8") as fh:
            blob = json.load(fh)
    except Exception:
        return -1.0
    stamps: list[float] = []
    for entry in (blob.get("symbols") or {}).values():
        if isinstance(entry, dict):
            val = entry.get("cached_at")
            if isinstance(val, (int, float)) and val > 0:
                stamps.append(float(val))
    if not stamps:
        return -1.0
    fresh = sum(1 for s in stamps if time.time() - s < 25 * 3600)
    return fresh / len(stamps)


def _age_or_inf(age: float | None) -> float:
    """FIX R3 (C-C5) : le patron `(x() or 9e9)` transformait un âge
    fraîchement arrondi à 0.0 (falsy !) en 9e9 → sonde faussement rouge.
    Mesuré : premium_history est écrit par le WS (flush 5 s) → P(age < 50 ms)
    ≈ 1 % par tir × 288 tirs/jour ≈ 2,9 fausses alertes/jour.
    Seul None (donnée absente) est un état dégradé."""
    return 9e9 if age is None else age


def traders_registry_fresh() -> bool:
    """La fraîcheur du registre des traders Aster : < 30 h depuis le dernier
    tir du timer quotidien 06:50 (aster-traders-registry). captured_day est une
    DATE (minuit local) : un âge brut sur minuit donnerait une fausse fenêtre
    06:00-06:50 chaque jour (le tir de 06:50 écrit la date du jour) → on exige
    captured_day <= 1 jour puis l'epoch du dernier tir réussi
    (aster_traders_state.json, écrit APRÈS commit) ; fallback minuit si absent."""
    from datetime import date, datetime
    try:
        con = ro(KL)
        v = con.execute("SELECT MAX(captured_day) FROM aster_traders").fetchone()[0]
        con.close()
        if not v:
            return False
        if (date.today() - date.fromisoformat(str(v))).days >= 2:
            return False
        try:
            epoch = json.loads(STATE_REG.read_text()).get("last_run_epoch")
        except Exception:
            epoch = None
        if epoch:
            return (time.time() - epoch) < 30 * 3600
        d = datetime.strptime(str(v), "%Y-%m-%d")
        return (time.time() - d.timestamp()) < 30 * 3600
    except Exception:
        return False


def timer_age(unit: str) -> float:
    """L'âge du dernier déclenchement d'un timer. La bonne sonde pour les
    tables d'ÉVÉNEMENTS : un vieux MAX = un marché calme, un timer qui ne
    tire plus = un collecteur mort. systemctl rend une date formatée même
    avec --value (« Wed 2026-09-30 00:45:11 CEST ») → parser en forçant C."""
    from datetime import datetime
    try:
        env = {**os.environ, "LC_ALL": "C"}
        r = subprocess.run(["systemctl", "--user", "show", unit,
                            "-p", "LastTriggerUSec", "--value"],
                           capture_output=True, text=True, timeout=15, env=env)
        v = r.stdout.strip()
        if not v or v in ("0", "n/a"):
            return None
        dt = datetime.strptime(" ".join(v.split()[:3]),
                               "%a %Y-%m-%d %H:%M:%S")
        return round(time.time() - dt.timestamp(), 1)
    except Exception:
        return None


def svc_active(unit: str) -> bool:
    return subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit],
                          capture_output=True).returncode == 0


CHECKS = [
    ("klines_1h", lambda: _age_or_inf(max_age(KL, "SELECT MAX(close_time) FROM klines WHERE interval='1h'")) < 25 * 3600,
     "klines 1h > 25 h — le nocturne 03:00 n'a pas tourné"),
    ("oi_history", lambda: _age_or_inf(max_age(KL, "SELECT MAX(captured_at_ms) FROM oi_history")) < 1800,
     "oi_history > 30 min — le timer 15 min est mort (la munition H4/H5 du 06-07)"),
    ("oi_history_bulk", lambda: _age_or_inf(max_age(KL, "SELECT MAX(captured_at_ms) FROM oi_history_bulk")) < 1800,
     "oi_history_bulk > 30 min — la passe bulk bapi (ticker/pair, ~642 syms) de oi_collector ne couvre plus"),
    ("funding_meta", lambda: _age_or_inf(max_age(KL, "SELECT MAX(captured_at_ms) FROM funding_meta")) < 5400,
     "funding_meta > 90 min — le timer aster-funding-bulk (2×/h) ne tire plus"),
    ("liq_events", lambda: svc_active("aster-liq-collector.service"),
     "le collecteur liq 24/7 est down"),
    ("block_trades", lambda: _age_or_inf(timer_age("aster-blocktrades.timer")) < 1800,
     "le timer block_trades ne tire plus (> 30 min)"),
    ("premium_history", lambda: svc_active("aster-markprice-ws.service") and
     _age_or_inf(max_age(KL, "SELECT MAX(captured_at_ms) FROM premium_history")) < 600,
     "premium_history > 10 min ou aster-markprice-ws down (le WS 1 s a remplacé le REST 15 min)"),
    ("depth_meta", lambda: _age_or_inf(max_age(DEPTH, "SELECT MAX(ts) FROM depth_meta")) < 600,
     "depth_meta > 10 min — le collecteur 24/7 stalle sans exit"),
    ("depth_continuity", lambda: depth_gaps_24h() == 0,
     "trous > 15 min dans depth sur 24 h — la continuité 14 j du tir 06-07 est amputée"),
    ("funding_cache", lambda: _age_or_inf(funding_cache_age()) < 25 * 3600,
     "le cache funding > 25 h — le nocturne n'a pas rafraîchi"),
    ("funding_cache_coverage", lambda: funding_cache_coverage() >= 0.8,
     "moins de 80 % du cache funding est frais (< 25 h) — refresh partiel que la sonde MAX ne voit pas"),
    ("traders_registry", traders_registry_fresh,
     "le registre traders Aster > 30 h — le timer quotidien 06:50 (aster-traders-registry) ne tire plus"),
    ("survivors_forward", lambda: _age_or_inf(max_age(KL, "SELECT MAX(CAST(value AS INTEGER)) FROM "
                                                   "aster_survivors_meta WHERE key='last_run_epoch'")) < 30 * 3600,
     "survivors_forward > 30 h — le timer quotidien 06:55 (aster-survivors-forward) ne tire plus"),
    ("rate_weight", lambda: (aster_rate.worst_weight() or 0) < aster_rate.ALERT,
     "budget weight >= 1800/2400/min (75 %) — réduire le pacing, risque 429/ban 418"),
]


def main() -> int:
    prev = {}
    if STATE.exists():
        try:
            prev = json.loads(STATE.read_text()).get("checks", {})
        except Exception:
            prev = {}
    now = int(time.time())
    alerts, checks = [], {}
    for name, ok, msg in CHECKS:
        # FIX R3 (C-C6) : une sonde qui lève tuait main() (promesse
        # « Exit 0 toujours », docstring) et laissait l'état sans mise à
        # jour — ex. funding_cache_age sur un blob JSON au mauvais format
        # (AttributeError hors try). Une sonde en échec ALERTE au lieu de
        # crasher.
        try:
            good = bool(ok())
        except Exception as exc:  # noqa: BLE001
            print(f"[aster-health] SONDE {name} a levé : {exc!r}", file=sys.stderr)
            good = False
        checks[name] = {"ok": good, "at": now}
        was = prev.get(name, {}).get("ok", True)
        if not good:
            alerts.append(f"{name} : {msg}")
            if was:
                print(f"[aster-health] ALERTE {name} : {msg}")
        elif not was and good:
            print(f"[aster-health] rétabli : {name}")
    # FIX R3 (C-C10) : écriture atomique — un état tronqué (kill pendant
    # write_text) serait une perte de la mémoire de transition (fausses
    # alertes « rétabli » au tir suivant). Même patron que les caches.
    _tmp_state = STATE.with_name(STATE.name + ".tmp")
    _tmp_state.write_text(json.dumps({"checks": checks, "updated_at": now}, indent=1))
    os.replace(_tmp_state, STATE)
    if not alerts:
        print("[aster-health] OK : " + ", ".join(c for c, _, _ in CHECKS))
    else:
        print(f"[aster-health] {len(alerts)} sonde(s) en alerte (voir ci-dessus)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
