#!/usr/bin/env python3
"""LA COUCHE D'ACCÈS UNIFIÉE fomo — scrapling Fetcher (impersonation TLS).

L'historique : le 28/09 l'IP a été flaggée par Cloudflare sur TOUT le
domaine fomo (le site + prod-api + mobula-api = 403 depuis urllib ET le
headless). Le 29/09 : le Fetcher scrapling (impersonation navigateur)
PASSE — testé 200 sur fomo.family. LA RÈGLE : toute collecte fomo passe
par ce module ; les fetchs urllib directs sont bannis (le pattern qui a
coûté le flag).

Les fonctions :
  fetch_fomo(url)                  — le site (pages/API front fomo.family)
  fetch_mobula(path, token, params) — mobula-api.fomo.family (OHLCV de l'app)
  fetch_prod_api(path, token)      — prod-api.fomo.family/v2 (auth Privy)
  fetch_json(resp)                 — le body parsé (dict/list) ou None

Intégré : rate-limit global (délai min entre 2 appels réseau fomo),
retries backoffés — 429 → 20/40 s, 403 → un seul retry après 45 s,
401 → échec immédiat (le même jeton rejeté le sera encore ; le mur d'auth
Privy du 29/09 est un 401, PAS un Cloudflare). NE JAMAIS marteler : le
403 martelé est exactement le pattern qui a coûté le flag.

Test : .venv/bin/python -c "from scripts.fomo_access import fetch_fomo; \
print(fetch_fomo('/').status)"
"""
from __future__ import annotations

import json
import threading
import time

try:
    from scrapling.fetchers import Fetcher
except ImportError:  # le venv projet l'a ; le garde-fou reste explicite
    Fetcher = None

SITE = "https://fomo.family"
PROD_API = "https://prod-api.fomo.family"
MOBULA = "https://mobula-api.fomo.family"

MIN_INTERVAL = 1.5            # s entre 2 appels réseau fomo (toutes fonctions)
RETRIES = 3
BACKOFF_429 = (20.0, 40.0)    # rate-limit explicite de l'API
BACKOFF_403 = 45.0            # Cloudflare : on recule LARGE, une fois

_lock = threading.Lock()
_last = [0.0]


def _throttle() -> None:
    with _lock:
        wait = _last[0] + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()


def _abs(url_or_path: str, base: str) -> str:
    s = str(url_or_path)
    return s if s.startswith("http") else base + (s if s.startswith("/") else "/" + s)


def _get(url: str, *, headers: dict | None = None, params: dict | None = None,
         timeout: int = 40):
    """Un GET via le Fetcher, retries backoffés sur 429/403/5xx.
    Retourne la Response scrapling (resp.status, resp.body, resp.json()).
    Lève la dernière exception après épuisement des essais."""
    if Fetcher is None:
        raise RuntimeError("scrapling absent — utiliser .venv/bin/python")
    last: Exception | None = None
    for attempt in range(RETRIES):
        _throttle()
        try:
            resp = Fetcher.get(url, impersonate="chrome", timeout=timeout,
                               stealthy_headers=True, retries=0,
                               headers=headers or None, params=params)
        except Exception as exc:  # réseau/timeout : backoff court puis retry
            last = exc
            if attempt < RETRIES - 1:
                time.sleep(3.0 * (attempt + 1))
            continue
        st = int(getattr(resp, "status", 0) or 0)
        if st == 200:
            return resp
        last = RuntimeError(f"HTTP {st} sur {url}")
        if st == 401:
            break  # le jeton est refusé — le réessayer ne sert à rien
        if st == 429 and attempt < RETRIES - 1:
            time.sleep(BACKOFF_429[min(attempt, len(BACKOFF_429) - 1)])
            continue
        # D-06 (ronde 6) : la docstring promet UN SEUL retry 403 — l'ancien
        # `attempt < RETRIES - 1` en accordait 2 (403 aux tentatives 0 ET 1
        # passaient toutes deux) : le pattern martelé qui a coûté le flag.
        if st == 403 and attempt == 0:
            time.sleep(BACKOFF_403)  # un seul retry espacé, jamais de martèle
            continue
        if st >= 500 and attempt < RETRIES - 1:
            time.sleep(5.0 * (attempt + 1))
            continue
        break  # les autres 4xx : inutile de réessayer
    raise last if last else RuntimeError(f"échec {url}")


def fetch_fomo(url_or_path: str, *, params: dict | None = None,
               headers: dict | None = None):
    """Le site fomo.family — URL absolue ou chemin ('/api/...', 'trending')."""
    return _get(_abs(url_or_path, SITE), headers=headers, params=params)


def fetch_mobula(path: str, token: str | None = None, *,
                 params: dict | None = None, headers: dict | None = None):
    """mobula-api.fomo.family — l'endpoint OHLCV de l'app
    ('/api/2/token/ohlcv-history?...'). Le token Bearer est optionnel
    (les endpoints publics existent ; l'OHLCV historique en veut un)."""
    h = {"accept": "*/*", "origin": SITE, "referer": SITE + "/"}
    if token:
        h["authorization"] = f"Bearer {token}"
    if headers:
        h.update(headers)
    return _get(_abs(path, MOBULA), headers=h, params=params)


def fetch_prod_api(path: str, token: str, *, params: dict | None = None,
                   headers: dict | None = None):
    """prod-api.fomo.family — l'API authentifiée Privy ('/v2/users/...')."""
    h = {"authorization": f"Bearer {token}", "accept": "*/*",
         "origin": SITE, "referer": SITE + "/"}
    if headers:
        h.update(headers)
    return _get(_abs(path, PROD_API), headers=h, params=params)


def fetch_json(resp):
    """Le body parsé (dict/list) — None si non-JSON (HTML de challenge...)."""
    try:
        return resp.json()
    except Exception:
        try:
            return json.loads(resp.body)
        except Exception:
            return None
