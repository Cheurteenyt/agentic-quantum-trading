# L'ORGANISATION DATA DU DOMAINE X (05/10 — le dictionnaire, le contrat, la validation)

Statut du domaine : **collecteur passif assumé** (verdict x-calls-fade KILL au registre —
le chase est toxique −37/−58 bps, le fade sous les coûts). Cette organisation prépare la
donnée à MÛRIR (le pattern premium_history : 30 jours accumulés → le test devient possible)
sans construire d'infrastructure sans hypothèse vivante.

## 1. LE DICTIONNAIRE (fiabilité A = fiable, B = à valider, C = bruité)

| Table | Ligne-type | Fraîcheur | Fiabilité | Notes d'unité |
|---|---|---|---|---|
| x_posts (2 244) | 1 post | H+1 | **A** | metrics = JSON int ; fetched_at en s ; posted_at_raw en ISO |
| x_accounts (49) | 1 handle | nocturne | **B** | PAS de champ followers (il est dans x_profiles) |
| x_calls (592) | 1 signal parsé | H+1 | **C** — parseur non validé | entry_price USD souvent NULL ; horizon 'none' 443/592 ; direction enum |
| x_call_scores (586) | 1 score | D+1 | **B** | entry_resolved = le PRIX résolu (pas un flag) ; ret_1h/ret_24h VIDES (jamais backfillés — le join klines.db est écrit, x_calls_fade_test.py le démontre) |
| x_call_verdicts (82) | 1 verdict | D+7 | **B** | dérivé de scores ; 21 win / 27 loss / 15 incohérents / 19 en cours |
| x_mentions (835) | (symbol, day) | D+1 | **A** | agrégation simple |
| x_positioning (217) | (day, symbol) | D+1 | **A** | pct_long en % |
| x_pressure (19) | (ticker, capture) | H+1 | **B** | velocity = Δ24h ; funding_pct en % |
| x_profiles (20) | 1 handle | ~S | **C** — 20/49 seulement, échantillon biaisé | followers int, pinned texte |
| x_trends (33) | 1 tag | H+1 | **C** — bruit sémantique | count int |
| x_lists_found (22) | 1 liste | H+1 | **B** | subscribers int |
| x_signal_history (75) | (day, ticker) | D+1 | **A** | l'archive D+1 de x_pressure |

## 2. L'AUDIT DE SCHÉMA (verdicts nommés)

- **x_trends → DÉPRÉCIER** : sous-ensemble sémantique bruité de x_mentions ; le signal vit
  dans x_mentions.symbol. Le nocturne cesse d'écrire (flag).
- **x_pressure (H+1, live) vs x_signal_history (D+1, archive)** : NE PAS fusionner — deux
  rôles (l'intraday vs le backtest), la source de vérité backtest = x_signal_history.
- **x_call_scores + x_call_verdicts → fusionner à terme en x_call_outcome** (1 ligne =
  1 sort final) — à faire au prochain refactor, pas en pleine nuit.
- **Champs morts-nés** : ret_7d (souvent NULL car resolved < D+7) ; x_calls.horizon (443
  'none' = inauditables — le parseur doit cesser d'écrire 'none' ou le champ se vide).
- **ret_1h/ret_24h ne sont PAS morts** : jamais remplis — le correctif = le join klines.db
  (démontré par x_calls_fade_test.py), à câbler au nocturne quand une hypothèse les réclame.

## 3. LE CONTRAT DE COLLECTE

| Collecteur | Cadence | Risque ban | Règle d'unité verrouillée |
|---|---|---|---|
| x_harvest (browser headless) | nocturne 03:21 | **HAUTE** (le profil = la clé du royaume) | posted_at_raw ISO → normalisé UTC ms à l'entrée |
| x_aster_pulse (le pont) | nocturne | nulle à la capture (lit la DB + le cache funding) | captured_at en s → jamais joint à du ms sans _norm |
| x_rotation (4 tickers/nuit) | nocturne | HAUTE (cumulée) | l'univers couvert en len(univers)/4 nuits |
| x_list_build | à la demande | moyenne | la liste privée = la page de couverture unique |

**LA RÈGLE DU ROYAUME** : 1 profil = 1 IP = 1 User-Agent ; chaque augmentation de volume
paie son risque ; un ban du profil = le domaine meurt — aucun budget nocturne ne vaut la clé.

## 4. LE PROTOCOLE DE VALIDATION DU PARSEUR (à exécuter avant de re-croire quoi que ce soit)

Échantillon : 100 calls stratifiés par direction, relus à la main.
- checks par champ : symbol ∈ univers (100 %), direction ∈ {long,short} (100 %),
  entry_price non-NULL (> 80 %), horizon ≠ 'none' (> 50 %), confidence ∈ [0,1] (100 %)
- **trancher le 44 % WR** : WR du sous-ensemble entry_price-NULL vs entry_price-valide —
  si le NULL-side WR << le valide-side → bruit de parsing ; si semblables → phénomène.
  (Le verdict chase-toxique −37/−58 bps du 05/10 tient INDÉPENDAMMENT : il mesure le join prix,
  pas le parse.)

## 5. LA CAPTURE LONGITUDINALE (ce qui mûrit chaque nuit — le pattern premium_history)

| Table cible | Contenu | Clé anti-doublon | Coût |
|---|---|---|---|
| x_profile_state | 49 handles : followers, bio_hash, pinned | handle + captured_at | nul (déjà harvesté) |
| x_engagement_delta | likes/replies par post (diff vs veille) | post_id + captured_at | nul (re-lit les posts connus) |
| x_deletions | post_id présent hier, absent aujourd'hui | post_id + detected_at | nul (diff des snapshots) |

Ces trois captures sont GRATUITES (réutilisent le harvest existant) et font mûrir la donnée
pour TOUTE hypothèse future de réputation/consensus/délétion — sans construire d'infrastructure
sans hypothèse vivante : les tables naissent au nocturne, les tests attendent leur mécanisme.

## 6. LE MIROIR

Ce que cette organisation rend possible : qu'un tiers ouvre x_posts.db et sache en 10 minutes
quoi croire, quoi douter, et quoi attendre — et que le jour où une hypothèse vivante réclame
de la donnée X, elle soit déjà là, propre, datée, et sans une ligne à récolter en urgence.

## 7. LE MÉDIA (05/10 — la couche que le user réclame : « les images disent tout »)

Les attaches des posts sont maintenant CAPTURÉES : x_posts +3 colonnes (media_count,
media_types JSON, media_urls JSON) + la table x_media (post_id, media_type, url — UNIQUE
anti-doublon). Le harvest DOM extrait les images de post (pbs.twimg.com/media — les avatars
exclus) et le testid videoPlayer.

**La taxonomy du média X et ce qu'elle dit** (les hypothèses à tester quand la donnée aura mûri) :
- **le CHART joint** = le call a été analysé (une conviction construite) — hypothèse : le WR
  des calls-avec-chart > les calls-texte-seul
- **le SCREENSHOT de position** = la preuve de skin-in-the-game (l'appât se montre rempli) —
  hypothèse : le follow du caller-screenshot surperforme, et sa SUPPRESSION plus tard = le signal
  de délétion le plus fort du domaine
- **le MEME seul** = le shill sans analyse — hypothèse : bruit pur, à filtrer du parse
- **la VIDÉO** = la démo/le live-trade — rare et lourd, à compter avant de télécharger
- **L'absence de média + un ticker cashtag** = le spam de rotation — la classe la plus bruitée

**La règle de stockage** : les URL d'abord (l'inventaire), le téléchargement des fichiers
seulement si une hypothèse vivante les réclame (le disque n'est pas gratuit, le CDN de X
expire les médias anciens — les URL d'aujourd'hui ne seront PAS résolubles dans 6 mois :
si un jour les images comptent, il faudra les télécharger À LA CAPTURE, décision à prendre
avec l'hypothèse).
