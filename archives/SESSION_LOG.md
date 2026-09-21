# Trading Agent — Session Log

## Structure
- Backend FastAPI port 8000 : `backend/main.py`
- Frontend Vite/React port 5173 : `frontend/`
- Services : `backend/services/arkham_scraper.py`, `arkham_tracker.py`
- Routers : `backend/routers/arkham.py`

## Modifications Backend
1. `ArkhamDatabase.search_tokens()` ajouté (lignes ~193-248) — manquait, appelée par router ligne 217
2. Covalent GoldRush intégré : constante `COVALENT_API_KEY_ENV`, `self.covalent_api_key` dans `__init__`
3. `_fetch_token_holders` cascade : Covalent → Etherscan tokenholderlist → Transfer events fallback
4. Clé Covalent dans `.env` : `COVALENT_API_KEY=cqt_rQmPYyqtrxC9rmxQ79YpH7DfBYyq`
5. Nouveaux endpoints router : `GET /token/{symbol}/holders` et `GET /token/{symbol}/transfers`

## Modifications Frontend
1. `index.css` — CSS layout complet : app-shell, sidebar 52px, topbar, ticker chips, arkham-overlay (hero, stats, tabs, tables)
2. `ArkhamEntityPage.tsx` — réécrit : hero prix+sparkline SVG, stats row, tabs Overview/Holders/Transfers, tables avec labels Arkham

## Comment lancer
```bash
cd /mnt/d/trading-agent/backend && python3 main.py
cd /mnt/d/trading-agent/frontend && npm run dev
```

## À faire
- Pages entities (arkham_) et addresses (0x...) sont des placeholders vides dans ArkhamEntityPage
- Sparkline est statique — à connecter à CoinGecko /market_chart pour les vrais prix historiques
- Vérifier les autres pages (Agents, Vision, Desktop, Chat, Terminal)
