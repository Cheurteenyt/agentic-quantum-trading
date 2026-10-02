# VOL-SPIKE-AMP — le filtre de volatilité absolue minimum
domaine : aster · famille : fade · stratégie : vol_spike_6h + filtre abs
Mécanisme : ne fader que les spikes dont la barre trigger a un range absolu ≥ 2 %.
Prédiction : les trades filtrés ont une espérance > le baseline.
PASS si E[filtré] > E[baseline] aux 2 splits · FAIL si E[filtré] ≤ E[baseline]
Verdict : **FAIL (02/10)** — les 57 trades ont déjà un range ≥ 2,56 % (le gate 4× fait le travail), l'espérance est plate +0,31-0,32 % à tous les seuils. Le filtre ne filtre rien.
