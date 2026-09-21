# Audit des capacites Aster MCP

Genere le: `2026-05-31T10:32:30.031067+00:00`

Ce document separe ce qu'Aster/MCP peut fournir maintenant, ce qui demande des credentials read-only, et ce qui doit rester bloque.

## Roadmap conseillee

1. **mark_index_replay_filter** - Les donnees mark/index publiques existent deja; elles peuvent reduire les faux edges issus du last-price. (credentials: False)
2. **public_websocket_sampler** - Les monitors forward doivent sortir du polling REST repetitif et lire un flux public plus proche du temps reel. (credentials: False)
3. **funding_fee_proxy_replacement** - L'historique funding public peut remplacer notre proxy fixe de 1 bps par 8h. (credentials: False)
4. **readonly_signed_testnet_probe** - Utile pour les leverage brackets et frais reels, mais seulement apres une politique credentials read-only. (credentials: True)

## Disponible maintenant - REST public

| Capacite | Securite | Statut | Safe now | Valeur backtest | Prochaine action |
|---|---|---|---:|---|---|
| exchange_info | PUBLIC | integrated | True | high | Use filters in execution-quality validation before promoting lanes. |
| ticker_24h | PUBLIC | integrated | True | high | Keep as liquidity gate in reality check. |
| order_book_depth | PUBLIC | integrated | True | high | Use to reject thin lanes and estimate slippage proxy. |
| last_price_klines | PUBLIC | integrated | True | high | Base replay remains last-price kline until mark/index replay is added. |
| mark_price_klines | PUBLIC | integrated | True | very_high | Add mark-price replay variant to compare against last-price replay. |
| index_price_klines | PUBLIC | integrated | True | very_high | Use mark-index divergence as a pre-trade filter. |
| premium_index | PUBLIC | integrated | True | very_high | Use premium_bps to filter longs/shorts when perp is too far from index. |
| funding_rate_history | PUBLIC | integrated | True | high | Replace fixed 1 bps/8h proxy with recent funding history. |
| funding_info | PUBLIC | integrated | True | medium | Keep in reality check as a risk warning. |
| index_references | PUBLIC | integrated | True | medium | Warn when reference count is too low. |


## Disponible maintenant - WebSocket public non integre

| Capacite | Securite | Statut | Safe now | Valeur backtest | Prochaine action |
|---|---|---|---:|---|---|
| public_websocket_trades | PUBLIC_WS | available_not_integrated | True | very_high | Create read-only websocket sampler before using for paper forward. |
| public_websocket_depth | PUBLIC_WS | available_not_integrated | True | very_high | Add sampler with sequence/update-id checks; no trading. |
| public_websocket_mark_price | PUBLIC_WS | available_not_integrated | True | high | Use for forward paper monitoring once sampler exists. |


## Demande des credentials signes read-only

| Capacite | Securite | Statut | Safe now | Valeur backtest | Prochaine action |
|---|---|---|---:|---|---|
| leverage_bracket | USER_DATA_SIGNED | blocked_until_readonly_credentials_policy | False | very_high | Test on V3 testnet/read-only credentials only; never with trade permissions. |
| commission_rate | USER_DATA_SIGNED | blocked_until_readonly_credentials_policy | False | high | Use only after credential policy exists. |
| account_balance | USER_DATA_SIGNED | blocked_until_readonly_credentials_policy | False | medium | Not needed before paper strategy has strong evidence. |
| positions | USER_DATA_SIGNED | blocked_until_readonly_credentials_policy | False | medium | Not needed until a real read-only account phase exists. |
| user_data_stream | USER_DATA_SIGNED_WS | blocked_until_readonly_credentials_policy | False | high_later | Only after signed read-only testnet phase. |


## Bloque - trade ou transfer

| Capacite | Securite | Statut | Safe now | Valeur backtest | Prochaine action |
|---|---|---|---:|---|---|
| create_or_cancel_order | TRADE_SIGNED | blocked | False | none_now | Do not enable. Paper trading evidence is insufficient. |
| set_leverage_or_margin | TRADE_SIGNED | blocked | False | none_now | Do not enable in Core Equity agent. |
| transfers | TRANSFER_SIGNED | blocked | False | none_now | Never expose to the agent. |


## Le plus utile pour les backtests

| Capacite | Securite | Statut | Safe now | Valeur backtest | Prochaine action |
|---|---|---|---:|---|---|
| exchange_info | PUBLIC | integrated | True | high | Use filters in execution-quality validation before promoting lanes. |
| ticker_24h | PUBLIC | integrated | True | high | Keep as liquidity gate in reality check. |
| order_book_depth | PUBLIC | integrated | True | high | Use to reject thin lanes and estimate slippage proxy. |
| last_price_klines | PUBLIC | integrated | True | high | Base replay remains last-price kline until mark/index replay is added. |
| mark_price_klines | PUBLIC | integrated | True | very_high | Add mark-price replay variant to compare against last-price replay. |
| index_price_klines | PUBLIC | integrated | True | very_high | Use mark-index divergence as a pre-trade filter. |
| premium_index | PUBLIC | integrated | True | very_high | Use premium_bps to filter longs/shorts when perp is too far from index. |
| funding_rate_history | PUBLIC | integrated | True | high | Replace fixed 1 bps/8h proxy with recent funding history. |
| public_websocket_trades | PUBLIC_WS | available_not_integrated | True | very_high | Create read-only websocket sampler before using for paper forward. |
| public_websocket_depth | PUBLIC_WS | available_not_integrated | True | very_high | Add sampler with sequence/update-id checks; no trading. |
| public_websocket_mark_price | PUBLIC_WS | available_not_integrated | True | high | Use for forward paper monitoring once sampler exists. |
| leverage_bracket | USER_DATA_SIGNED | blocked_until_readonly_credentials_policy | False | very_high | Test on V3 testnet/read-only credentials only; never with trade permissions. |
| commission_rate | USER_DATA_SIGNED | blocked_until_readonly_credentials_policy | False | high | Use only after credential policy exists. |
| user_data_stream | USER_DATA_SIGNED_WS | blocked_until_readonly_credentials_policy | False | high_later | Only after signed read-only testnet phase. |


## Pas utile maintenant

| Capacite | Securite | Statut | Safe now | Valeur backtest | Prochaine action |
|---|---|---|---:|---|---|
| create_or_cancel_order | TRADE_SIGNED | blocked | False | none_now | Do not enable. Paper trading evidence is insufficient. |
| set_leverage_or_margin | TRADE_SIGNED | blocked | False | none_now | Do not enable in Core Equity agent. |
| transfers | TRANSFER_SIGNED | blocked | False | none_now | Never expose to the agent. |


## Safety

- Aucun appel externe pendant cet audit.
- Aucun credential.
- Aucun wallet.
- Aucun trade.
- Aucun write DB.