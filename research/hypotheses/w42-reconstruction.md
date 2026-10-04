# W42-RECON-1 — la reconstruction : le wallet joint survivor_long + vol_spike sous cap de marge
domaine : aster · famille : reconstruction · stratégie : w42-portfolio
Mécanisme (pourquoi ça devrait exister, 3 lignes) :
  Les deux seuls flux VIVANTS du grand audit post-fix (survivor_long +1,127 %/event,
  DD 7,4 %, 0 liq ; vol_spike_6h +0,101 %/event, DD 13,4 %, 0 liq) sont décorrelés
  par construction : le survivor = LONG 1x inliquidable sur la queue de liquidation
  (gate ATR p90, 89/1 655 events), le vol_spike = fade 6h court-terme (corr mesurée
  −0,50/-0,35 avec les cascades). La loi gravée : la décorrélation vaut un edge en
  plus — le wallet séquentiel joint doit lisser le chemin (mois creux remplis) et
  améliorer ret/DD vs chaque flux seul.
Prédiction chiffrée (signe, magnitude, horizon) :
  ret/DD joint VAL ≥ ret/DD survivor seul VAL (≥ 1,00×) ; mois négatifs joint VAL
  strictement < min(mois négatifs survivor solo, mois négatifs vol_spike solo) ;
  corr(rets d'events survivor, vol_spike) < 0,3 ; tout ça à DD joint ≤ 15 %.
Données / split / protocole / coûts (réels ET ×1,5) :
  Données fixées post fetch_deep_klines (l'ère corrompue est morte — PR #91/#95).
  Période complète 2021→2026. Split TEMPOREL 70/30 run_stack (inchangé). Coûts
  TAKER_RT 28 bps RT (inchangés) + stress ×1,5 obligatoire. run_stack inchangé.
  Gates inchangés (ATR p90 survivor — JAMAIS assoupli, gate ATR vol_spike).
  Sizing w=1 codifié (base_sizer) + cap de marge 1 % en wrapper (sz ≤ 1/100,
  doctrine W41 CH1 validée mécaniquement).
PASS si … · FAIL si … · SOUS_PUISSANT si … (écrits AVANT le run) :
  PASS si les 4 : (1) ret/DD joint VAL ≥ 1,00× ret/DD survivor solo VAL ;
  (2) mois négatifs joint VAL < min des deux solos VAL ; (3) 0 liquidation ;
  (4) coûts ×1,5 → solde joint VAL > capital initial.
  FAIL si (1) OU (2) non atteint — « FAIL — hypothèse réfutée », budget consommé,
  STOP. Interdit de réparer par un filtre.
  SOUS_PUISSANT si < 30 events survivor pris en VAL (le gate p90 en prend peu :
  89 sur 5 ans) — re-tir sur fenêtre plus longue uniquement.
Contrôles : inverse (le wallet short-survivor doit être pire — sinon artefact) ;
  corr jointe mesurée sur les rets d'events ; comparaison APPARIÉE aux solos
  (mêmes events, même split, mêmes coûts) ; hors top 5 % des trades (la tail
  survivor porte tout — le verdict doit survivre sans ses 3 meilleurs trades).
Hash de commit du gel : 12465ab — protocol-v1
Jugé sous : protocol_v1 · Exécution : semaine W41 (budget W40 épuisé 22/20 —
  verrou lab_ledger exit 4 le 04/10, un seul run à la reset du lundi 06/10).
Baseline anti-dérive : les wallets solo du grand audit (survivor $155/DD 7,4 % ;
  vol_spike $122/DD 13,4 %, w=1) doivent se REPRODUIRE au run — si reproduction
  ≠, STOP, le sol a bougé.
