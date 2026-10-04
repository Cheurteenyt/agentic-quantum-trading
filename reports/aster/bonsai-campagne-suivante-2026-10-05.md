# Le design de campagne Bonsai (05/10, verbatim tronqué) + le filtre de l'agent

**Confirmation du Piège :** Le mur structurel est confirmé. À 28 bps RT, le seuil de survie exige un edge > 28 bps. Les horizons courts (<24h) sont tués par la volatilité intrabar (MAE > 7,66% déclenche la cascade 12x, mais le coût de 28 bps sur 24h est ~70 bps, tuant l'edge). Les horizons longs (+168h) sont tués par la règle 0-liq (un hold de 30 jours traverse forcement un -95%, soit 15/32 confirmées mortes). La fenêtre viable est donc étroite : **6-72h** avec un MAE < 7,66%.

**La Zone Échappée :** Il existe une zone non-cartographiée : **Horizon 12-48h × Fréquence Hebdos × MAE < 5%**.
*   **Pourquoi ?** Nos 356 cellules ont testé des horizons binaires (24h vs 168h) et des MAE bruts (7,66% vs 94%). Elles n'ont pas testé la **windowing** du MAE.
*   **L'Hypothèse :** Si l'on restreint le trade à la fenêtre 12-48h et qu'on exige un MAE < 5% (au lieu de 7,66%), on évite la cascade 12x (coût de sizing) ET on reste sous le seuil de liquidation (0-liq).
*   **Pourquoi 356 cellules l'ont manqué :** Elles ont corrélé MAE global avec horizon global. Or, le MAE est une distribution. Un trade avec MAE 6% à la 6h et MAE 8% à la 40h est viable si on coupe à la 6h. Le backtest actuel ne mesure pas la *dépendance temporelle* du MAE. C'est la zone **MAE-Dépendant-Horizon**.

---

### (2) LES 3 CAMPAGNES DE BACKTEST PRIORITAIRES (2 Semaines)

**1. Campagne : "Le MAE-Snapshot" (Sizing Layer)**
*   **Hypothèse :** Le coût de la cascade 12x (sizing réduit) est le principal tueur des trades viables à 12-48h. Si on conditionne la taille *avant* le MAE (ex: size = 0.5x si MAE_6h < 4%), on récupère 15-20% de PnL perdu.
*   **Design :** Re-jouer les 32 confirmées avec le harnais v5, mais en injectant un filtre de sizing conditionnel : `if (MAE_intrabar_6h < 4%) size *= 1.5 else size *= 0.5`. Comparer le DD et le Sharpe contre la baseline.
*   **Critère Chiffré :** Sharpe > 1.8 (actuellement ~1.5) et DD < 20%.
*   **Espace Ouvert :** Les couches de sizing sont ROUVERTES. Le corr-tilt est passé. C'est un test de *conditionnement temporel* du sizing, pas de direction.

**2. Campagne : "Le Funding-Alpha" (Exécution)**
*   **Hypothèse :** La règle "delta famille 5/32" (funding clos) tue les longs. Mais si on exploite le funding *comme* un signal de réversion (et pas juste un filtre), on peut capturer les 5/32 morts.
*   **Design :** Ajouter un flux "Funding-Reversal" : si Funding > 2bps et Price < MA_2h, ouvrir Long. Tester sur les 15 syms premium (15m).
*   **Critère Chiffré :** 3 confirmations sur 15 trades avec PnL > +5% et DD < 15%.
*   **Espace Ouvert :** Le flux "survivor 1x" est sous-exploité. Le funding est un data stream premium (15 min) non utilisé comme trigger, seulement comme filtre.

**3. Campagne : "La Tape-Volume" (Exécution)**
*   **Hypothèse :** Le harnais v5 utilise la MAE intrabar. Mais la tape BTC/ETH (15m) contient un signal de *timing* intrabar plus fin que le MAE.
*   **Design :** Conditionner l'entrée sur le ratio `Volume_Tape / Volume_Kline_15m`. Si Ratio > 1.5 dans les 5 premières minutes, entry. Sinon, skip.
*   **Critère Chiffré :** Amélioration du Ratio PnL/Trade de +10% sans augmentation du DD.
*   **Espace Ouvert :** La tape BTC/ETH est disponible. Le harnais v5 ne l'utilise pas pour le *timing d'entrée*, seulement pour le MAE. C'est un test de micro-structure.

---

### (3) LA PRÉDICTION

**

## Le filtre de l'agent (post-hoc, 3 rejets + 1 découverte partielle)
- **La « zone échappée » MAE-dépendant-horizon est PARTIELLEMENT connue** : la frontière
  conjointe hold×levier (26/09) a déjà cartographié le MAE par hold (3,6 % à 6h → 7,8 % à 24h
  → 17,1 % à 72h). Son twist (tronquer le hold selon le MAE réalisé) = un STOP déguisé —
  T23 a tué 0/30 configs TP/SL et la loi d'exécution prédit la mort.
- **La Campagne 1 a un LOOK-AHEAD** : sizer sur « MAE_intrabar_6h < 4 % » = conditionner la
  taille sur une donnée FUTURE du trade. Rejeté tel quel ; la version propre = conditionner
  sur des variables CONNUES à l'entrée (le pattern corr-tilt).
- **La Campagne 2 (Funding-Alpha) = l'espace interdit** : « funding × prix < MA → long » est
  une relation conditionnelle état→prix, famille funding close 4 fois.
- **La Campagne 3 (timing tape) = plausible mais adjacente** à INV-O (open=optimum, le
  raffinement intrabar a payé −39 bps) ; le conditionneur volume-burst est nouveau — à
  pré-enregistrer avec le kill INV-O si un jour la tape s'étend.
- Sa prédiction finale a été coupée (budget tokens) — non réclamée, le scorecard est assez chargé.
