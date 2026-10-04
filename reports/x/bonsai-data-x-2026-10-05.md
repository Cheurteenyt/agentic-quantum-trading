# LE RELANCE DU DOMAINE X — le design Bonsai (05/10) + le filtre de l'agent

## Ce que Bonsai a vu juste (ancré, rare)
- L'inventaire d'accessibilité est HONNÊTE : profils/replies/lists = faisables via le browser
  connecté (les JSON du harvest le prouvent), DMs/données supprimées/historique profond =
  inaccessibles, l'engagement-horodaté = limité.
- Le FIX DU SCORING en priorité 1 : les colonnes ret_1h/ret_24h vides = les verdicts se
  calculent à T0, les rendements exigent les prix à T+1h/T+24h — le backfill du join est le
  chantier bloquant. CORRECTION : pas de table x_price_ticks à créer (fabrication) — les prix
  EXISTENT dans klines.db (586 syms × 5,1 ans en 1h), le join = symbol+USDT, ts en ms.
- Les 3 signaux : (1) la cohérence profil-appel (un filtre de scoring, espace ouvert),
  (2) le consensus des replies (fuzzy, testable), (3) fix scoring d'abord — le bon ordre.

## Ce qui a été rejeté
- « rate-limit ~180 req/min », « 15 tweets par page » : des précisions inventées.
- x_price_history/x_price_ticks : n'existent pas, klines.db suffit.

## LE PLAN (agent, intégré)
1. **Le backfill des rendements des 592 calls** (le premier verdict X du registre) :
   join x_calls → klines.db (symbol+USDT 1h), remplir ret_1h/ret_24h, recomputer le WR/edge
   réel des calls — gate lab_ledger famille x, 1 créneau.
2. **La profondeur de collecte** : 50 tweets/compte/nuit au lieu de 15 (49 comptes, risque
   bas) — alimente le signal cohérence-profil.
3. **Les poids de profil** : x_profiles (followers/bio) étendu aux 49 comptes → le score
   pondéré par la réputation.
4. **Le consensus replies** : parser latest-replies.json (déjà harvesté).
5. **L'hygiène ban** : pacing humain, budget/nuit plafonné, JAMAIS le compte principal en
   risque — le profil browser est la seule clé du royaume.
