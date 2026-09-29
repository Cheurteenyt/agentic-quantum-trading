---
name: fomo-rest-api
description: La carte de l'API REST de fomo.family (prod-api) et la recette anti-Cloudflare. Utiliser dès qu'on touche fomo.family — holders, thèses, swaps élite, trades fermés, leaderboard, clans, trending — qu'on veut « scraper » fomo, qu'un appel renvoie 403/400/401, ou qu'on cherche une alternative au DOM, même si l'utilisateur dit juste « récupère les holders » ou « l'API est bloquée ».
---

# L'API REST de fomo.family

## Le principe

TOUT ce que les onglets du site affichent (holders, thèses, swaps, trades
fermés, leaderboard, clans) vient d'appels **XHR REST** sur
`https://prod-api.fomo.family` — PAS du WebSocket. Le WS (le daemon) ne porte
que `prices`, `token_details`, `trading_activity`, `trending_tokens`,
`pre_graduated_tokens`. « Pas d'API de données » était FAUX : les endpoints
n'apparaissent qu'en naviguant les onglets d'un token (la sonde les capture).

## La recette anti-WAF (le 403 n'est PAS une auth)

Cloudflare bloque le **fingerprint TLS**, pas l'API :

```python
from curl_cffi import requests as cffi   # le moteur de scrapling, déjà dans le venv
H = {"user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
     "authorization": f"Bearer {jwt}", "origin": "https://fomo.family", "referer": "https://fomo.family/"}
r = cffi.get(url, headers=H, impersonate="chrome131", timeout=15)
```

- python-requests/urllib (TLS nu) → **403 Forbidden**
- `impersonate="chrome"` générique → **400 Bad Request** (profil trop vieux)
- `impersonate="chrome131"` → **200** partout
- pacing ≥ 1 s entre appels (le WS du site, lui, tolère 0,05 s par topic)

## Le JWT

- `data/fomo/ws_jwt_cache.txt` (le ws_daemon le re-mint via CDP 24/7) et
  `data/fomo/jwt_cache.json` (le top-up mobula) — **même token privy**, les
  deux transports (WS et REST) l'acceptent. Lire le plus frais des deux,
  vérifier `exp > now + 600` (durée de vie ~60 min). Si périmé : ne pas
  forcer, la passe se skippe (le ws_daemon le re-mint).
- Le voler en 5 s si besoin : ouvrir une page sur le navigateur du worker
  (:9222) et lire la frame `challengeResponse` via `page.on("websocket")`.

## La carte des endpoints (validés 200 le 29/09)

| Endpoint | Params EXACTS | Réponse |
|---|---|---|
| `GET /v2/leaderboard/24h` | — | `{leaderboard: [150]}` → les user ids pour la rotation élite |
| `POST /proxy/trendingTokens` | body `{}` | `[50]` : `{token:{address,networkId}, marketCap, liquidity, holders, volume24}` |
| `GET /hodlers/top` | `?tokens=[{"address":MINT,"networkId":1399811149}]` (URL-encodé ; `networkId` NUMÉRIQUE — `"network":"solana"` = 400) | `[{tokenAddress, networkId, topHolders:[~97], totalHolders}]` — holder : `user, pnl, unrealizedPnl, realizedPnl, costBasis, averageEntryPrice, humanAmount, value` |
| `GET /hodlers/devs` | `?tokenAddress=&networkId=` | `{devHoldings}` |
| `GET /feed/token/thesis` | `?tokenAddress=&networkId=&threshold=1000` | `{items:[25]}` — `threshold` OBLIGATOIRE |
| `GET /feed/token/sortedThesis` | `?tokenAddress=&networkId=&afterTime=<ms>&beforeTime=<ms>&limit=500&threshold=0` | `{items:[364-500/24h]}` — la **fenêtre temporelle est OBLIGATOIRE** sinon 400 ; thèse : `type, id, userId, userHandle, comment, numReplies` |
| `GET /v2/users/<uuid>/swaps` | `?limit=100` | `{swaps:[100], hasNextPage}` — swap : `id, inToken/outToken, humanUsdAmountIn/Out, createdAt` |
| `GET /trades` | `?userId=&orderBy=closedAt` | `{activeTrades, closedTrades, closedCount, hasNextPage}` — les trades fermés SANS les 28 pages DOM |
| `GET /v2/clans/leaderboard` | `?window=24h&limit=50` | `{leaderboard:[50]}` |
| `GET /v2/users/<uuid>` · `/v2/users/userHandle/<handle>` · `/v2/users/<uuid>/spotlight` · `/watchlist` · `/config` | — | profils, spotlight, watchlist |

`networkId=1399811149` = solana. Pagination : `hasNextPage:true` — le nom du
curseur se découvre par sondage (`before/after=<dernier id>`, `cursor=`,
`offset=`) ou en capturant un scroll de profil (voir le one-shot `rest_probe`).

## Le collector (ne pas réécrire)

`scripts/fomo_rest_collector.py` — timer systemd `fomo-rest-collector.timer`
(30 min), base **dédiée** `data/fomo/fomo_rest.db` (tables
`fomo_rest_snapshots` PK(endpoint,entity_id) + `fomo_rest_swaps` idempotent
par swap id), pacing 1 s, ~37 appels ≈ 60 s/passe. L'étendre, jamais le
dupliquer. Les one-shots RE : `scripts/studies/fomo_rest_probe.py` (capture
XHR + rejoue) et `fomo_ws_frame_capture.py` (frames WS via
`page.on("websocket")` — insensible aux mondes isolés de patchright).

Scrapling 0.4.15 est dans le venv : son Fetcher (curl_cffi) fait le même
bypass TLS pour du HTML — inutile pour du JSON direct, garder en fallback DOM.
