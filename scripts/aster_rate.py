#!/usr/bin/env python3
"""LE COMPTEUR DE POIDS RATE-LIMIT ASTER (30/09) — l'audit docs/24.

Le budget REST fapi.asterdex.com : X-MBX-USED-WEIGHT-1M = 2 400/min/IP
(429 → backoff, ban 418 = 2 min → 3 jours). Chaque collecteur REST appelle
note_weight(resp.headers, "<source>") après CHAQUE réponse 200 (le header
est global IP : chaque lecture est la vérité). État :
data/warehouse/aster_rate_state.json {updated_at, max_recent: {source: poids}}.
Rotation : le max par source est remis à zéro après ROTATE_S sans écriture
(un vieux max ne doit pas alerter éternellement). worst_weight() = le max
toutes sources, pour la sonde aster_health (seuil ALERT = 75 % du budget).
Tolérant aux échecs : header absent, JSON corrompu ou dispo pleine ne doit
JAMAIS bloquer un collecteur — tout est avalé proprement (None)."""
import json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "warehouse" / "aster_rate_state.json"
LIMIT = 2400   # weight/min/IP (fapi.asterdex.com)
ALERT = 1800   # 75 % du budget = le seuil de la sonde aster_health
ROTATE_S = 120  # 2 fenêtres de 60 s : au-delà, le max par source est périmé


def _read() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def note_weight(headers, source: str):
    """Lit X-MBX-USED-WEIGHT-1M (HTTPMessage urllib OU dict simple) et note
    le max récent de la source. Retourne le poids lu, None si absent/échec.
    Rotation PAR SOURCE (fix 30/09) : un max vu il y a > ROTATE_S pour CETTE
    source expire, même si d'autres collecteurs rafraîchissent le fichier
    entre-temps (sinon un pic vieux de 10 min reste épinglé et fausse la
    sonde aster_health)."""
    try:
        raw = headers.get("X-MBX-USED-WEIGHT-1M") if headers is not None else None
        if raw is None:
            return None
        w = int(str(raw).strip())
        now = time.time()
        st = _read()
        seen = dict(st.get("seen_at") or {})
        recent = dict(st.get("max_recent") or {})
        recent = {s: v for s, v in recent.items()
                  if now - float(seen.get(s) or 0) <= ROTATE_S}
        seen = {s: t for s, t in seen.items()
                if now - float(t) <= ROTATE_S}
        recent[source] = max(w, int(recent.get(source) or 0))
        seen[source] = now
        STATE.parent.mkdir(parents=True, exist_ok=True)
        out = dict(st)                       # préserve toute clé inconnue
        out.update({"updated_at": int(now), "max_recent": recent, "seen_at": seen})
        STATE.write_text(json.dumps(out, indent=1))
        return w
    except Exception:
        return None


def worst_weight():
    """Le max toutes sources confondues — None si aucune lecture fraîche
    (< ROTATE_S) : pas de donnée n'est PAS une alerte (les sondes de
    fraîcheur d'aster_health couvrent déjà un collecteur mort)."""
    st = _read()
    if not st or time.time() - float(st.get("updated_at") or 0) > ROTATE_S:
        return None
    vals = [int(v) for v in (st.get("max_recent") or {}).values()
            if isinstance(v, (int, float))]
    return max(vals) if vals else None
