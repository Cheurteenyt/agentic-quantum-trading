# Primitives vivantes — seules bases autorisées pour composer

Une **primitive** = signal ou filtre déjà passé par falsification (CANDIDAT/VALIDÉ/CONTEXTE utile) et encore utiliséable.

Composer = combiner 2 primitives ou étendre une primitive **sans** retomber dans le mortuary.

## ASTER

| id | description courte | statut | notes |
|---|---|---|---|
| `cascade_al_gated` | cascade majeurs + gate AL score p66 | machine | noyau the_machine flux 1 |
| `vol_inverse_sizing` | sizing ∝ ATR inverse borné | machine | base 24 % × K |
| `fund_rank_low` | rank funding bas vs 6 majeures | candidat qualité | WR élevé en backtest — affiner mécanisme |
| `mae_lev_cap` | levier ≤ 100/(MAE+0.5) | machine / T8 | mae_state.json |
| `survivor_long_72h` | coins >90j au-dessus prix-90j, ATR≤p90 | machine flux 3 | 1x |
| `cascade_meme_1x` | même logique cascade hors majors | machine flux 2 | levier mécanique MAE |
| `vol_spike_6h` | fade range ≥4× médiane 14j | expérimental | flag --vol-spike, défaut OFF |
| `corr_regime_majors` | corr croisée 6 majeures fenêtre 168h | contexte | tilt optionnel |

## FOMO

| id | description courte | statut | notes |
|---|---|---|---|
| `swaps_skill_weighted` | réplication swaps pondérée skill | PASS étude | forward séparé |
| `replication_derek` | règle derek dans fomo_paper_forward | candidat forward | ≥5 CLOSED pour juger |
| `fomo_tick_1m` | OHLCV 1m depuis ticks maison | data | pas un signal seul |

## OPENMARKET

| id | description courte | statut | notes |
|---|---|---|---|
| `x501_signature_*` | familles kScript signature / maker | QA + baselines | **domaine isolé** — pas brancher dans the_machine |
| `x501_absorption_walls` | murs natifs maxBid/maxAsk | vague 2 | rester dans studies/x501 |

## X

| id | description courte | statut | notes |
|---|---|---|---|
| `x_calls_scored` | scoring calls harvest | pipeline | ne pas merger ROI avec Aster |

## Règle de composition

- Nouveau signal = `primitive_a × primitive_b` ou extension documentée d’une ligne ci-dessus.
- Si tu ne peux pas nommer les primitives parents → ce n’est pas une composition, c’est du Rail A brut (hypothèse + mortuary check).
- **Jamais** composer FOMO × Aster dans un même portefeuille “officiel” sans protocole dédié et domaine déclaré `MIX` (interdit par défaut).
