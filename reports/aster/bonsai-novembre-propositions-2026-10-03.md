# Les propositions novembre de Bonsai (03/10 nuit, verbatim) + le filtre de l'agent

Verdict : 0/2 retenues — (1) duplique INV-C avec un split 2022/2023 dont les données n'existent pas (liq WS depuis sept 2026) ; (2) « acheter la volatilité » sans instrument (pas d'options sur Aster). Détail du filtre : research/hypotheses/execution-slippage-protocol.md.

```
PRÉ-ENREGISTREMENT 1 : « LÉCHERIE DE LA LIQUIDATION »
(1) HYPOTHÈSE : La mécanique obligatoire de liquidation des positions levées (levier ≤ 100/(maxMAE%+0,5)) crée un flux de liquidités obligatoires à des prix fixes (liq_price). Contrairement aux patterns conditionnels, ce flux est mécanique et discret, indépendant des relations état→prix. Le mécanisme est la contrainte mécanique de la levier et du maxMAE, qui génère une pression de vente/achat instantanée au moment où le prix atteint le seuil de liquidation.
(2) CONSTRUCTION :
- Données : Tape BTC/ETH (11,6 M prints), Liq WS (flux de liquidations), OI 15 min.
- Formule : Identifier les liquidations (liq_price) sur les 15 syms de depth. À chaque liquidation détectée sur le tape, calculer le delta de volume (ΔV) dans les 30 secondes suivantes sur la même symbole.
- Horizon : 30 secondes après l'événement de liquidation.
- Signal : Si ΔV > 0 (vente forcée) sur les shorts ou ΔV > 0 (achat forcé) sur les longs, générer un signal d'entrée dans le sens inverse (contre-tendance) si le prix est dans la zone de liquidation (±0,5% du liq_price).
(3) CRITÈRES PASS/FAIL :
- Split temporel : 80% train (janv-déc 2022) / 20% test (janv 2023).
- Contrôle inverse : Inverser le signe du signal (acheter en cas de liquidation short au lieu de vendre) doit donner un PnL < 0.
- N minimal : ≥ 500 événements de liquidation sur le test set.
- Coûts : 10 bps (RT 8-18 bps, exécution humaine à l'open).
- Seuil PASS : PnL test > PnL inverse + 2*σ(PnL inverse).
(4) KILL EX ANTE : Ce test ne mourra pas car le mécanisme est mécanique (levier, maxMAE) et non observé. Le marché ne peut pas "effacer" le flux de liquidations car il est imposé par les contraintes du broker (levier, marge). L'edge vient de l'asymétrie temporelle (la liquidation est un événement discret, le prix met du temps à réagir). Les 22 morts mouraient parce qu'ils dépendaient de relations conditionnelles état→prix (ex: si prix baisse, volume augmente) qui s'effondrent à la généralisation. Ici, la relation est causale et mécanique (levier→liquidation→volume), pas statistique.

PRÉ-ENREGISTREMENT 2 : « CASCADES DE LISTINGS »
(1) HYPOTHÈSE : Les listings datés (nouveaux symboles) sur un exchange créent une cascade d'events discrets : (a) announcement, (b) first trade, (c) first depth, (d) first funding. Cette cascade est un événement discret, pas un pattern. Le mécanisme est la contrainte mécanique de l'exchange (les listings sont datés, les premières données sont obligatoires). L'edge vient du fait que les premiers trades sont souvent des "noise trades" (testers, bots) qui créent une volatilité artificielle, puis la microstructure s'installe.
(2) CONSTRUCTION :
- Données : Listings datés (dates), klines 15m/1h (586 syms), depth (102 M bins, 15 syms).
- Formule : Pour chaque listing, identifier la date du "first trade" (première kline non nulle). Calculer la volatilité (std dev des retours) sur les 24 klines 1h suivantes (horizon 1 jour). Comparer à la volatilité moyenne des 10 derniers listings (contrôle).
- Signal : Si la volatilité du premier jour > 1,5*volatilité moyenne des 10 derniers listings, générer un signal "VOLUME" (acheter la volatilité, ex: options ou pairs de symboles).
- Horizon : 1 jour (24 klines 1h).
(3) CRITÈRES PASS/FAIL :
- Split temporel : 80% train / 20% test (par date de listing).
- Contrôle inverse : Inverser le signal (vendre la volatilité si vol > moyenne) doit donner un PnL < 0.
- N minimal : ≥ 50 listings sur le test set.
- Coûts : 15 bps (RT 8-18 bps, exécution humaine à l'open).
- Seuil PASS : PnL test > PnL inverse + 2*σ(PnL inverse).
(4) KILL EX ANTE : Ce test ne mourra pas car l'event est discret (listing) et le mécanisme est mécanique (l'exchange impose les dates, les premières données sont obligatoires). Le marché ne peut pas "effacer" le listing car c'est un événement exogène imposé par le marché (l'exchange). L'edge vient de l'asymétrie temporelle (les premiers jours sont plus volatils à cause des tests, bots, etc.). Les 22 morts mouraient parce qu'ils dépendaient de relations conditionnelles état→prix (ex: si volume augmente, prix monte) qui s'effondrent à la généralisation. Ici, la relation est causale et mécanique (listing→premières données→volatilité

```
