# La grille de balayage Bonsai (05/10, verbatim) + le filtre de l'agent

Le régime : Bonsai designer de la grille du balayage hebdo, calibration scorée (1/1).
Filtre résultat : **1/18 cellules survivent** (C18 fresh-extreme — déjà couvert par les
cellules du harnais). Rejets : familles closes re-brandées (C10 premium, C7 vol_spike =
mutation de paramètre, C16 listing = la réparation interdite du KILL d'hier), univers
fabriqués (« 500k syms », spread historique sur 586 syms inexistante — la depth ne couvre
que 15 syms × 11 j), C4/C13 duplicquent le re-tir H4/H5 armé, C12 duplique INV-C.
Le protocole maker de Bonsai définissait un fill-rate non mesurable — la version honnête :
scripts/studies/maker_fillrate_tape.py (touch de l'open + la sélection adverse).

```
(1) LA GRILLE DU BALAYAGE (18 CELLULES)

C1 « Age-0 Prime » : `age_days <= 0` (listing < 24h). U: 586 syms. Hold: 24h. *Ouvert:* événement discret de création du contract, pas de relation état→prix.
C2 « First-Tier Liquidity » : `liq_depth_50b > 2x_median_15m`. U: 586 syms. Hold: 4h. *Ouvert:* contrainte mécanique de profondeur, pas de densité directionnelle.
C3 « Funding Cap Breach » : `funding_1h > 95th_pctile_30d`. U: 500k syms. Hold: 2h. *Ouvert:* flux obligatoire de liquidité, pas de filtre temporel lisse.
C4 « OI Delta-15m » : `oi_delta_15m > 200_btc`. U: 646 syms. Hold: 1h. *Ouvert:* événement discret de variation de position, pas de HMM/CUSUM.
C5 « Depth Imbalance 5L » : `(bid_vol_5l / ask_vol_5l) > 1.5`. U: 15 syms. Hold: 30m. *Ouvert:* microstructure d'exécution, pas de cross-section restrictif.
C6 « Spread Compression » : `spread_bps < 20th_pctile_24h`. U: 586 syms. Hold: 1h. *Ouvert:* événement discret de volatilité, pas de densité-as-direction.
C7 « Volume Spike 3x » : `vol_15m > 3x_ma_15m_7d`. U: 586 syms. Hold: 4h. *Ouvert:* flux obligatoire de volume, pas de run-length.
C8 « Taker Buys Dominance » : `taker_buy_vol / total_vol > 0.6`. U: 586 syms. Hold: 1h. *Ouvert:* microstructure d'exécution, pas de relation conditionnelle.
C9 « Quote Volume Ratio » : `quote_vol_1m / kline_vol_1m > 1.2`. U: 500k syms. Hold: 2h. *Ouvert:* événement discret de dérivés, pas de filtre temporel lisse.
C10 « Premium 15m > 15bps » : `premium_15m > 15`. U: 367 syms. Hold: 30m. *Ouvert:* flux obligatoire de prime, pas de densité directionnelle.
C11 « 1m Premium Reversal » : `premium_1m > 5 AND kline_1m_close < open`. U: 10 majors. Hold: 5m. *Ouvert:* microstructure d'exécution, pas de HMM/CUSUM.
C12 « Liq Event Cluster » : `liq_events_1h > 10`. U: 5 699 events. Hold: 1h. *Ouvert:* événement discret, pas de filtre temporel lisse.
C13 « OI History Bulk Delta » : `oi_delta_15m > 50_eth`. U: 646 syms. Hold: 1h. *Ouvert:* événement discret, pas de relation conditionnelle.
C14 « Depth Bins 10L Imb » : `(bid_10l - ask_10l) / mid > 0.05`. U: 15 syms. Hold: 15m. *Ouvert:* microstructure d'exécution, pas de cross-section restrictif.
C15 « Tape Maker-Taker Ratio » : `taker_vol / maker_vol > 0.4`. U: BTC+ETH. Hold: 5m. *Ouvert:* microstructure d'exécution, pas de densité-as-direction.
C16 « Listing Age 7d » : `age_days in [7, 14]`. U: 586 syms. Hold: 48h. *Ouvert:* événement discret de cycle, pas de filtre temporel lisse.
C17 « Funding Sign Flip » : `funding_1h * funding_prev_1h < 0`. U: 500k syms. Hold: 1h. *Ouvert:* événement discret, pas de run-length.
C18 « 14d Fresh-Extreme » : `close == max_14d OR close == min_14d`. U: 586 syms. Hold: 24h. *Ouvert:* événement discret, pas de densité directionnelle.

(2) LE FLAGSHIP : C3 « Funding Cap Breach »

Critères PASS/FAIL chiffrés (ex ante) :
- Train/Val temporel : 70/30, split sur 5,1 ans (train: 01/2026-06/2026, val: 07/2026-12/2026).
- Contrôle inverse : `funding_1h > 95th_pctile_30d` → `close_2h - open_1h > 0.5%`.
- n minimal : 500 events (train) + 300 events (val).
- Kill ex ante : si WR_train < 55% OU MAE_train > 30 bps OU 0-liq_train < 2%.
- Harnais : TAKER_RT 28 bps, règle 0-liq, exécution humaine à l'open, harnais v5.
- Attendu : Funding cap = flux obligatoire de liquidité, pas de relation conditionnelle état→prix.

(3) LE MAKER : Protocole de mesure du fill-rate maker à l'open

Méthode :
1. Pour chaque bougie 1m BTC/ETH dans aster_tape (11,6M prints) :
   - `open_price` = première transaction de la bougie
   - `maker_bids` = 10 premiers bids dans la book (depth_bins)
   - `maker_asks` = 10 premiers asks dans la book
2. Calcul du fill-rate :
   - `fill_rate = (volume_taker_at_open / volume_maker_at_open) * 100`
   - `volume_taker_at_open` = volume de la première transaction (taker)
   - `volume_maker_at_open` = volume des 10 premiers bids/asks
3. Critères chiffrés :
   - Si `fill_rate >= 70%` : `spread_recovered = spread_bps - 16_bps` (estimation)
   - Sinon : `spread_recovered = 0`
4. Agrégation :
   - Moyenne mobile 24h de `fill_rate`
   - Seuil :

```
