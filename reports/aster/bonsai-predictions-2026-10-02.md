# LE TOURNOI DE PRÉDICTIONS — Bonsai (02/10/2026)

Le modèle local Bonsai (Ternary-Bonsai-2-27B-Abliterated) prédit l'issue des 4 expériences en attente.
Vérification à chaque verdict : si Bonsai va 4/4, il gagne un siège d'oracle ; si 0/4, son jugement vaut zéro.

| Exp | Prédiction | Confiance | Raison | Verdict réel | Bonsai a-t-il vu juste ? |
|---|---|---|---|---|---|
| EXP 1 H4/H5 re-tir (07-08/10) | **INSUFFISANT** | 60 % | 2 jours de plus n'atteindront pas n≥10/quadrant | _en attente_ | — |
| EXP 2 H-CROWD-1 (30/10) | **FAIL** | 75 % | fenêtre 24-72h trop courte vs le bruit premium/z-funding | _en attente_ | — |
| EXP 3 INV-N torsion premium (~28/10) | **FAIL** | 80 % | la reversion < 2h ne couvre pas les coûts sur 18 symboles | _en attente_ | — |
| EXP 4 INV-C écho de liq (~mi-nov) | **PASS** | 85 % | 30 j de donnée atteignent n≥30, la causalité liq→flux sera isolée | _en attente_ | — |

Score à jour : **0/4 tranchés** — 1 verdict demain (EXP 1), le reste fin octobre / mi-nov.
Généré par le modèle local en 64 s (medium thinking). Source : /tmp/bonsai_tournoi_out.txt.
