#!/usr/bin/env python3
"""LE RESEARCH RUNNER — Research OS PR 6 (brief V3 §6-7, §166, §203 PR6).

LA porte d'entrée unique de la recherche : une spécification YAML détermine
toute l'expérience, le runner orchestre data → masque → statistiques →
contrôles → verdict → artefacts → ledger. Le modèle ne choisit plus quel
script lancer, quelle DB lire, où écrire : il produit une intention.

Chaîne discovery (TRAIN only, hors budget scientifique) :
    python3 scripts/research_runner.py discovery --spec research/experiments/EXP-001.yaml
Chaîne confirmation (pré-enregistrée, budget strict, protocole-v2) :
    python3 scripts/research_runner.py confirm --spec research/experiments/EXP-001.yaml
Portefeuille (le wallet 100 $ d'un run — couche PR-B) :
    python3 scripts/research_runner.py portfolio --id EXP-001 [--view validation]
Comparaison :
    python3 scripts/research_runner.py compare EXP-A EXP-B
Statut :
    python3 scripts/research_runner.py status

Le masque de signal est évalué CAUSALEMENT : le seuil d'une feature est le
quantile EXPANDING des valeurs passées (warmup 50) — un trade ancien ne
connaît jamais la distribution future (leçon C10). La découverte ne voit
que la vue TRAIN du DataScope et gèle ses seuils ; la confirmation JUGE
SOUS PROTOCOLE (research/protocols/active.yaml) : fenêtres gelées évaluées
une par une (windows_pass_required), seuils gelés (jamais re-calibrés sur
la validation), embargo 72h, stress de coûts ×1,5, dégradation bornée —
et CONSOMME un slot (journal d'états + lab_ledger).

Artefacts par run : research/runs/<id>/ avec spec.json (copie gelée),
manifest.json (git sha, spec sha, label hash, snapshot), summary (les
chiffres utiles au LLM), report.md (le rapport humain + le bloc WALLET
quand la confirmation passe). Reproductible par experiment_id + git_sha +
spec_sha + label_hash (brief §41).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.aster_indicators import volume_z  # noqa: E402
from scripts.label_matrix import (  # noqa: E402
    LABEL_VERSION, build_matrix, snapshot_id)
from scripts.research_os import (  # noqa: E402
    DataScope, DataView, Mode, ScopeViolation, load_confirmation_protocol)

KDB = ROOT / "data" / "warehouse" / "klines.db"
RUNS = ROOT / "research" / "runs"
JOURNAL = ROOT / "research" / "ledger" / "experiments.jsonl"
WARMUP = 50

# FIX v8 (rapport GLM 5.3 №1) : la table d'opérateurs EXPLICITE. L'ancien
# code faisait « >= → >=, tout le reste → <= » : un "<" de spec était
# silencieusement exécuté "<=" — le langage d'exécution différait du langage
# pré-enregistré. Tout opérateur hors table = ValueError.
OPS = {">=": np.greater_equal, "<=": np.less_equal,
       ">": np.greater, "<": np.less}


def apply_op(values, op: str, thr):
    try:
        fn = OPS[op]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"opérateur interdit : {op!r} "
                         f"(autorisés : {sorted(OPS)})") from exc
    return fn(values, thr)


# ------------------------------------------------------------------ spec
def load_spec(path: Path) -> dict:
    spec = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for k in ("id", "hypothesis", "data", "signal", "horizons"):
        if k not in spec:
            raise ValueError(f"spec incomplète : champ requis manquant '{k}'")
    d = spec["data"]
    for k in ("symbols", "train_start", "train_end", "validation_start",
              "validation_end"):
        if k not in d:
            raise ValueError(f"spec.data incomplète : '{k}' manquant")
    # FIX v8 (rapport GLM 5.3 №1) : la spec doit déclarer des opérateurs
    # EXISTANTS — refus précoce plutôt qu'interprétation fausse au masque
    sig = spec["signal"]
    for cond in ([sig] if "feature" in sig else sig.get("conditions", [])):
        if cond.get("op", ">=") not in OPS:
            raise ValueError(f"opérateur interdit {cond.get('op')!r} dans "
                             f"{spec['id']} (autorisés : {sorted(OPS)})")
    if "universe" in spec:
        from scripts.universe import check as _ucheck, load as _uload
        manifest = _uload(str(spec["universe"]))
        missing, empty = _ucheck(manifest, d["symbols"])
        if missing or empty:
            raise ValueError(
                f"{spec['id']} : univers {spec['universe']!r} incohérent — "
                f"absents {missing} · vides {empty}")
    return spec


def spec_sha(spec: dict) -> str:
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]


def spec_execution_sha(spec: dict) -> str:
    """Le sha d'EXÉCUTION d'une spec — seule la mode sort (PR-150, audit
    GLM 5.3 post-#149 №1 : l'ancien core excluaient AUSSI l'univers, donc
    une découverte sur univ10 pouvait fonder une confirmation sur un autre
    univers avec le même pin). L'univers change la population statistique :
    il est scellé, complété par universe_sha (le hash du manifest)."""
    body = {k: v for k, v in spec.items() if k != "mode"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


def universe_sha(name: str) -> str | None:
    """Le sha du CONTENU du manifest d'univers — l'identifiant seul ne
    scelle pas (un univ10.yaml modifié garde son nom)."""
    from scripts.universe import UNIVERSE_DIR
    f = Path(UNIVERSE_DIR) / f"{name}.yaml"
    if not f.exists():
        return None
    return hashlib.sha256(f.read_text(encoding="utf-8").encode()).hexdigest()[:16]


def protocol_sha() -> str:
    """Le sha du CONTENU d'active.yaml (PR-150 №7 de l'audit : un seuil
    peut changer sous le même protocol_id — le contenu est le sceau)."""
    f = ROOT / "research" / "protocols" / "active.yaml"
    return hashlib.sha256(f.read_text(encoding="utf-8").encode()).hexdigest()[:16]


def _git() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True,
                              cwd=ROOT).stdout.strip()
    except OSError:
        return "?"


def _env_versions() -> dict:
    """L'environnement NUMÉRIQUE scellé (PR-150 №13) — le git_sha seul ne
    fige pas numpy/pandas : deux dates d'installation produisent des
    chiffres différents du même commit."""
    import platform
    env = {"python": platform.python_version()}
    for mod in ("numpy", "pandas", "yaml"):
        try:
            env[mod] = __import__(mod).__version__
        except Exception:
            env[mod] = "?"
    return env


def _provenance() -> dict:
    """La provenance COMPLÈTE du code exécuté (fix v10, audit GLM 5.3
    post-#135) : le manifest ne doit pas seulement citer le commit HEAD —
    un run lancé sur un arbre sale exécute du code que git_sha ne décrit
    pas. On enregistre commit intégral + drapeau dirty + hash du diff."""
    prov = {"git_sha": _git(), "git_dirty": False, "diff_sha": None}
    try:
        full = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, cwd=ROOT).stdout.strip()
        if full:
            prov["git_sha"] = full
        status = subprocess.run(["git", "status", "--porcelain"],
                                capture_output=True, text=True,
                                cwd=ROOT).stdout
        prov["git_dirty"] = bool(status.strip())
        if prov["git_dirty"]:
            diff = subprocess.run(
                ["git", "diff", "HEAD"], capture_output=True, text=True,
                cwd=ROOT).stdout + "\n--untracked--\n" + "\n".join(
                l[3:] for l in status.splitlines() if l.startswith("??"))
            prov["diff_sha"] = hashlib.sha256(diff.encode()).hexdigest()[:16]
    except OSError:
        pass
    return prov


# ------------------------------------------------------------------ données
def compute_features(con: sqlite3.Connection, sym: str,
                     db_path: Path = KDB) -> dict[str, np.ndarray]:
    """Les features causales par barre 1h : range_pct, volume_z, ret_1h.
    Toutes connues au CLOSE de leur barre (availability = close_t).
    FIX v8 (rapport GLM 5.3 №2) : le funding vient de LA MÊME DB que les
    prix (db_path) — plus jamais le warehouse global en implicit."""
    rows = con.execute(
        "SELECT open_time, open, high, low, close, volume FROM klines "
        "WHERE symbol=? AND interval='1h' ORDER BY open_time",
        (sym,)).fetchall()
    if len(rows) < 60:
        raise ValueError(f"{sym} : pas assez de klines ({len(rows)})")
    ts = np.array([r[0] * 10**6 for r in rows], dtype=np.int64)
    o = np.array([r[1] for r in rows])
    h = np.array([r[2] for r in rows])
    l = np.array([r[3] for r in rows])
    c = np.array([r[4] for r in rows])
    v = pd.Series([r[5] for r in rows])
    cs = pd.Series(c)
    # fund_last : le dernier taux de funding CONNU au moment de la barre
    # (as-of strict, searchsorted — le print futur ne fuite pas)
    # FIX v8 : funding ABSENT ≠ funding nul. Le 0.0 inventé faisait matcher
    # les conditions « fund_last <= 0 » (le candidat H-01) sur des symboles
    # sans AUCUNE donnée de funding. NaN = inconnu, exclu des masques.
    # Et : la série vient de la DB DU RUN (provenance, fix v8).
    fund_last = np.full(len(ts), np.nan)
    try:
        from scripts.funding_series import funding_series_for
        fser = funding_series_for(sym, db_path=db_path)
        if fser is not None and len(fser.times_ms):
            # FIX v9 : times_ms déjà en ms ; ts/1e6 (ns→ms) — l'ancien
            # /1e6 double rendait fund_last CONSTANT (le dernier print
            # jamais vu, pour toutes les barres)
            k = np.searchsorted(fser.times_ms, ts / 1e6, side="right") - 1
            fund_last = np.where(k >= 0, fser.rates_pct[np.maximum(k, 0)], np.nan)
    except ValueError:
        # PR-166 (P2 bug-hunter) : seul l'ABSENCE de funding est tolérée —
        # l'ancien except Exception avalait une vraie erreur (DB lock,
        # corruption) et rendait fund_last tout-NaN en silence
        pass
    return {"open_time_ns": ts,
            "range_pct": (h - l) / c * 100.0,
            "volume_z": volume_z(v, n=20).values,
            "ret_1h": cs.pct_change().values * 100.0,
            "fund_last": fund_last}


def expanding_threshold(values: np.ndarray, q: float,
                        warmup: int = WARMUP) -> np.ndarray:
    """Le seuil EXPANDING : à la barre i, le quantile des valeurs passées.
    Causal par construction (leçon C10) ; NaN pendant le warmup."""
    out = np.full(len(values), np.nan)
    for i in range(len(values)):
        past = values[:i]
        if len(past) >= warmup:
            out[i] = np.nanquantile(past, q)
    return out


_THR_CACHE: dict[tuple, np.ndarray] = {}


def expanding_cached(values: np.ndarray, q: float, key: tuple | None) -> np.ndarray:
    """Le quantile expanding, mémoïsé par (db, symbole, feature, quantile).
    La boucle O(n²) ne doit payer qu'UNE fois par clé et par process —
    la confirmation multiplie les appels (train, fenêtres, stress)."""
    if key is not None and key in _THR_CACHE:
        return _THR_CACHE[key]
    out = expanding_threshold(values, q)
    if key is not None:
        _THR_CACHE[key] = out
    return out


def _db_key(db_path: Path) -> tuple:
    """L'identité bon marché d'une DB pour les clés de cache : chemin +
    (mtime_ns, size) — une DB modifiée pendant un process ne réutilise pas
    un cache périmé (rapport GLM 5.3 №23)."""
    st = Path(db_path).stat()
    return (str(db_path), st.st_mtime_ns, st.st_size)


def _mask_for(cols, fvals, op, thr, view):
    # FIX v8 : bornes [start, end) — une barre frontière n'appartient qu'à
    # UNE période (les fenêtres protocolaires sont adjacentes)
    in_view = ((cols["open_time_ns"] >= view.start_ms * 10**6)
               & (cols["open_time_ns"] < view.end_ms * 10**6))
    finite = np.isfinite(fvals) & (np.isfinite(thr) if np.ndim(thr) else True)
    base = apply_op(fvals, op, thr)   # FIX v8 : opérateurs explicites
    return base & finite & in_view


def _signal_conditions(sig: dict) -> list[dict]:
    """Multi-conditions (Bonsai) ou mono-feature (legacy), même interface."""
    return list(sig["conditions"]) if "conditions" in sig else [sig]


def _multi_mask(feats: dict, conditions: list[dict], view, frozen=None,
                thr_key: tuple | None = None) -> np.ndarray:
    """Le masque ET de plusieurs conditions (brief V3 §7 de la spec).
    Chaque condition : {feature, op, quantile OU threshold}.
    Quantile = expanding (causal) ; threshold = valeur absolue déclarée.
    frozen = liste de seuils GELÉS alignée sur les conditions — la
    confirmation n'a pas le droit de re-calibrer un quantile SUR la
    validation (recalibrer sur le test = ré-estimer sur le test, rapport
    v6). Un seuil None (non gelable) → aucun event, conservateur."""
    n = len(next(iter(feats.values())))
    mask = np.ones(n, dtype=bool)
    for j, cond in enumerate(conditions):
        v = feats[cond["feature"]]
        if frozen is not None:
            ft = frozen[j] if j < len(frozen) else None
            if ft is None:
                mask &= np.zeros(n, dtype=bool)
            else:
                mask &= apply_op(v, cond["op"], ft)
        elif "quantile" in cond:
            thr = expanding_cached(v, float(cond["quantile"]),
                                   (*thr_key, cond["feature"],
                                    float(cond["quantile"]))
                                   if thr_key else None)
            mask &= apply_op(v, cond["op"], thr)
        else:
            mask &= apply_op(v, cond["op"], cond["threshold"]) & np.isfinite(v)
    # FIX v8 : bornes [start, end)
    in_view = ((feats["open_time_ns"] >= view.start_ms * 10**6)
               & (feats["open_time_ns"] < view.end_ms * 10**6))
    return mask & in_view


# l'horizon large pour l'évaluation BRUTE des signaux (le filtre de vue
# s'applique à la barre d'ENTRÉE, après le décalage)
_FAR_FUTURE_MS = 4102444800000   # 2100-01-01


def event_mask(spec: dict, feats: dict, view, frozen=None,
               min_event_ms: int = 0, thr_key: tuple | None = None) -> np.ndarray:
    """Le masque d'une spec sur les features d'UN symbole — le point
    partagé entre l'étude d'événement et la couche portefeuille.

    FIX v14 (PR-143, audit GLM 5.3 — P0 look-ahead CONFIRMÉ par mutation
    test) : le signal évalué sur la barre i n'est CONNU qu'au close(i) —
    l'entrée ne peut donc être qu'à open(i+1). L'ancien code entrait à
    open(i) AVEC la connaissance de close(i) : le trade mesurait sa propre
    bougie de sélection (h-31, horizon 1h : WR 99,6 % par construction).
    Convention du registre appliquée : signal=close(t) → entry=open(t+1).
    TOUTES les bornes (vue, embargo, sortie-dans-fenêtre) s'appliquent à
    la barre d'ENTRÉE."""
    sig = spec["signal"]
    wide = DataView(getattr(view, "snapshot_id", "unknown"),
                    getattr(view, "mode", "train"), 0, _FAR_FUTURE_MS)
    if "conditions" in sig:
        raw = _multi_mask(feats, _signal_conditions(sig), wide,
                          frozen=frozen, thr_key=thr_key)
    else:
        fvals = feats[sig["feature"]]
        if frozen is not None:
            ft = frozen[0] if frozen else None
            if ft is None:
                raw = np.zeros(len(fvals), dtype=bool)
            else:
                raw = _mask_for(cols=feats, fvals=fvals,
                                op=sig.get("op", ">="),
                                thr=np.full(len(fvals), float(ft)), view=wide)
        else:
            if "threshold" in sig:
                # PR-166 (P1 bug-hunter) : un threshold DÉCLARÉ doit être
                # honoré — l'ancienne branche ne lisait que quantile
                # (défaut 0.95) alors que le gel repart du threshold
                # déclaré : la confirmation aurait jugé un AUTRE signal
                # que la discovery qui a produit le candidat
                thr = np.full(len(fvals), float(sig["threshold"]))
            else:
                q = float(sig.get("quantile", 0.95))
                thr = expanding_cached(fvals, q,
                                       (*thr_key, sig["feature"], q)
                                       if thr_key else None)
            raw = _mask_for(cols=feats, fvals=fvals, op=sig.get("op", ">="),
                            thr=thr, view=wide)
    # LE DÉCALAGE : l'entrée est la bougie SUIVANTE (le signal de i entre
    # à open(i+1)) — un trade ne mesure plus sa propre bougie de sélection
    mask = np.empty_like(raw)
    mask[0] = False
    mask[1:] = raw[:-1]
    # les bornes s'appliquent à la barre d'ENTRÉE
    in_view = ((feats["open_time_ns"] >= view.start_ms * 10**6)
               & (feats["open_time_ns"] < view.end_ms * 10**6))
    mask &= in_view
    if min_event_ms:
        mask &= feats["open_time_ns"] >= min_event_ms * 10**6
    return mask


def apply_universe(spec: dict, sym: str, mask: np.ndarray,
                   feats: dict, horizon_h: int,
                   manifest: dict | None = None) -> np.ndarray:
    """LA primitive anti-survivorship (PR-147, durcie PR-148) : entry et
    sortie (entry + horizon) dans le span tradable du manifest. Une SEULE
    interprétation de l'univers pour discovery/confirmation/wallet/forward.

    PR-166 : `manifest` permet au forward d'injecter une copie CLAMPÉE
    (borne finie étendue à maintenant pour les vivants) — le backtest,
    lui, passe toujours par le manifest gelé.

    FAIL-CLOSED (audit GLM 5.3 post-#147 №2) : un univers DÉCLARÉ mais non
    résoluble (manifest absent, symbole absent, bornes invalides) lève
    UniverseViolation — JAMAIS « continue sans contrainte ». Le seul retour
    sans contrainte est une spec qui ne déclare PAS d'univers."""
    if not spec.get("universe"):
        return mask
    from scripts.research_os import UniverseViolation
    from scripts.universe import load as _uload, tradable_window_ms
    try:
        man = (manifest if manifest is not None
               else _uload(str(spec["universe"])))
        tw = tradable_window_ms(man, sym)
    except FileNotFoundError as exc:
        raise UniverseViolation(
            f"univers {spec['universe']!r} introuvable — fail-closed") from exc
    if tw is None:
        raise UniverseViolation(
            f"symbole {sym!r} absent de l'univers {spec['universe']!r} "
            "— fail-closed")
    t0, t1 = tw
    if t1 <= t0:
        raise UniverseViolation(f"span tradable invalide pour {sym}: {tw}")
    ns = feats["open_time_ns"]
    return mask & (ns >= t0 * 10**6) &         (ns + horizon_h * 3_600_000 * 10**6 <= t1 * 10**6)


def _features_by_sym(spec: dict, db_path: Path) -> dict[str, dict]:
    """Les features causales par symbole, calculées UNE fois par run —
    la confirmation multiplie les études (train, fenêtres, stress)."""
    out = {}
    for sym in spec["data"]["symbols"]:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            out[sym] = compute_features(con, sym, db_path=db_path)
        finally:
            con.close()
    return out


def _frozen_thresholds(feats_by_sym: dict, conditions: list[dict],
                       view) -> dict[str, list[float | None]]:
    """Le seuil GELÉ par (symbole, condition) : la valeur du quantile
    expanding à la DERNIÈRE barre de la vue train. La confirmation réutilise
    CE nombre (artefact de découverte s'il existe, sinon recalcul TRAIN
    only) — les conditions à seuil absolu se gèlent telles quelles."""
    end_ns = view.end_ms * 10**6
    out = {}
    for sym, feats in feats_by_sym.items():
        vals: list[float | None] = []
        for cond in conditions:
            if "quantile" not in cond:
                vals.append(float(cond["threshold"]))
                continue
            v = feats[cond["feature"]]
            thr = expanding_cached(v, float(cond["quantile"]), None)
            idx = int(np.searchsorted(feats["open_time_ns"], end_ns,
                                      side="right")) - 1
            tv = thr[idx] if 0 <= idx < len(thr) else float("nan")
            vals.append(float(tv) if np.isfinite(tv) else None)
        out[sym] = vals
    return out


def _study(spec, matrix, view, side_mult: float, db_path: Path,
           feats_by_sym: dict | None = None, frozen: dict | None = None,
           min_event_ms: int = 0, cost_pct: float | None = None) -> dict:
    """L'étude d'événement sur la vue donnée (train, validation, fenêtre)."""
    from scripts.label_matrix import event_study
    sig = spec["signal"]
    side = int(sig.get("side", -1))
    cost = float(cost_pct if cost_pct is not None
                 else spec.get("cost_pct", 0.28))
    horizons = tuple(int(h) for h in spec.get("horizons", [24]))
    if feats_by_sym is None:
        feats_by_sym = _features_by_sym(spec, db_path)
    out = {}
    for sym in spec["data"]["symbols"]:
        if sym not in matrix or sym not in feats_by_sym:
            continue
        feats = feats_by_sym[sym]
        fz = frozen.get(sym) if frozen is not None else None
        if frozen is not None and fz is None:
            # symbole absent du gel → aucun seuil gelable → 0 event
            # (JAMAIS de re-calibration expanding sur la vue testée)
            fz = [None] * len(_signal_conditions(sig))
        mask = event_mask(spec, feats, view, frozen=fz,
                          min_event_ms=min_event_ms,
                          thr_key=(*_db_key(db_path), sym))
        # PR-147 : la primitive UNIQUE anti-survivorship (entry + sortie
        # dans le span tradable du manifest — une seule interprétation de
        # l'univers pour discovery/confirmation/wallet/forward)
        if mask.any():
            view.assert_range(
                int(feats["open_time_ns"][mask][0]) // 10**6,
                int(feats["open_time_ns"][mask][-1]) // 10**6)
        for H in horizons:
            # FIX v8 (№7) + FIX v15 (№3 post-#147) : la SORTIE reste dans
            # la vue ET dans le span tradable — PAR HORIZON (l'ancien
            # horizons[0] laissait un H=72 sortir de l'univers)
            mask_h = apply_universe(spec, sym, mask, feats, H)
            m_h = mask_h & (feats["open_time_ns"]
                            <= (view.end_ms - H * 3_600_000) * 10**6)
            out[f"{sym}@{H}h"] = event_study(matrix[sym], m_h, H,
                                             side=int(side * side_mult),
                                             cost_pct=cost)
    return out


BH_Q = 0.10


def bh_min_perms(m: int, q: float = BH_Q) -> int:
    """N1 — combien de permutations pour que le BH soit ATTEIGNABLE.

    Le plancher d'une p-value par permutation est `1 / (n_perm + 1)`. Pour
    que le MEILLEUR candidat d'un lot de `m` specs puisse franchir le BH au
    rang 1, il faut `p <= q / m`. Donc :

        1 / (n_perm + 1) <= q / m   ⇔   n_perm >= m / q - 1

    Avec le défaut historique `n_perm = 99`, le plancher est 0,01. Le BH
    n'est donc franchissable que si `0,01 <= 0,10 / m`, soit **m ≤ 10**.
    Sur un lot de 43 specs, AUCUN candidat ne peut jamais passer le BH,
    quel que soit son edge : le contrôle n'était pas un filtre, c'était un
    refus automatique. Un vrai edge de +0,4 % était écarté au même titre
    qu'un bruit.

    | lot m | n_perm requis (≥ m/q − 1) |
    |---|---|
    | 10  | 99   |
    | 43  | 429  |
    | 100 | 999  |

    Le plancher de 99 est conservé pour ne pas dégrader les petits lots.
    """
    return max(99, int(math.ceil(m / q)) - 1)


def bh_reachable(p_min: float, m: int, q: float = BH_Q) -> bool:
    """Le seuil BH du rang 1 est-il atteignable avec cette résolution ?"""
    return bool(m) and p_min <= q / m


def sequential_perm_pvalue(exceed, n_max: int,
                           h_stop: int = 10) -> tuple[float, int]:
    """p-value par permutation SÉQUENTIELLE (Besag–Clifford, forme).

    `exceed()` renvoie le booléen « ce tirage dépasse l'observé » — la
    comparaison est DANS le callback, donc l'observé n'est pas passé ici :
    un paramètre mort ferait croire qu'il sert à quelque chose.
    On tire, on compte les dépassements, et on S'ARRÊTE dès `h_stop`
    dépassements : au-delà, aucune suite de tirages ne peut plus rendre la
    p-value petite, donc le coût supplémentaire est du temps perdu.

    Returns `(p, n_tirages_effectues)`.

    ## Pourquoi (N1b, audit 2026-10-08)

    PR #198 a rendu le BH franchissable en dimensionnant la résolution :
    `n_perm = bh_min_perms(m) = max(99, m/q − 1)`. C'était juste, mais
    appliqué à CHAQUE spec du lot, ça donne **m × (m/q − 1) permutations** :
    le coût croît en m². Sur un lot de 43, ≈ 18 000 appels à
    `event_study` ; sur un lot de 500, ≈ 2,5 M — plusieurs heures, et
    le moteur avorte en `WAITING_RESOURCE`.

    Sous H0, les dépassements suivent une binomiale — s'arrêter au
    `h_stop`-ième ne biaise donc pas la p-value : c'est la forme
    séquentielle classique, et `test_p0_perm_calibration.py` la MESURE
    (FPR ≤ 8 % sous H0, puissance ≥ 90 % à +0,4 %).

    Les vraies p-valeurs petites demandent les tirages complets ; les
    candidates qui ne le sont pas s'arrêtent en quelques dizaines. C'est
    le compromis correct : on paie le prix seulement quand le prix compte.
    """
    exc = 0
    for i in range(1, int(n_max) + 1):
        exc += 1 if exceed(i) else 0
        if exc >= h_stop:
            return (exc + 1) / (i + 1), i
    return (exc + 1) / (int(n_max) + 1), int(n_max)


def _perm_loop(pairs: list[tuple[dict, np.ndarray]], h1: int, side: int,
               cost: float, mean_obs: float, n_perm: int = 99,
               seed: int = 0, h_stop: int = 10) -> float:
    """La boucle de permutation (pure, testable) : p one-sided supérieur.

    SÉQUENTIELLE depuis N1b : on arrête dès `h_stop` dépassements. Sous H0
    un tirage dépasse l'observé une fois sur deux, donc `h_stop = 10`
    arrête en ~20 tirages au lieu de `n_perm` (43 pour un lot de 43, ×9
    moins). Un edge réel ne dépasse pas, il part une fois sur vingt : il
    va jusqu'à `n_perm` et atteint le plancher dont le BH a besoin.

    `h_stop=0` désactive l'arrêt précoce (l'ancien comportement fixe),
    pour les tests qui veulent mesurer le nombre de tirages.
    """
    from scripts.label_matrix import event_study
    if not pairs:
        return float("nan")
    n_min = min(len(m) for _, m in pairs)
    lo_shift = max(1, min(168, n_min // 4))
    rng = np.random.default_rng(seed)

    def exceed(_i: int) -> bool:
        k = int(rng.integers(lo_shift, max(lo_shift + 1, n_min - lo_shift)))
        num = den = 0.0
        for cols, m in pairs:
            st = event_study(cols, np.roll(m, k), h1, side=side,
                             cost_pct=cost)
            if st.get("n", 0):
                num += st["mean"] * st["n"]
                den += st["n"]
        mean_perm = num / den if den else float("nan")
        return bool(np.isfinite(mean_perm) and mean_perm >= mean_obs)

    if not h_stop:
        ge = sum(1 for _ in range(int(n_perm)) if exceed(0))
        return (1 + ge) / (int(n_perm) + 1)

    p, _n = sequential_perm_pvalue(exceed, n_perm, h_stop=h_stop)
    return p


def _perm_pvalue(spec, matrix, view, db_path, feats_by_sym, frozen,
                 min_event_ms: int, mean_obs: float, min_n: int,
                 kept_syms: list[str], n_perm: int = 99,
                 seed: int = 0) -> float:
    """PR-176 (B4 audit Sonnet 5.5) : la p-value par PERMUTATION
    CIRCULAIRE du masque — le décalage circulaire garde l'autocorrélation
    et le regroupement de volatilité des labels ET du masque, il ne
    détruit que leur alignement. Le n nominal ne se croit pas (les events
    24 h sur lignes horaires se chevauchent). One-sided supérieur (l'edge
    recherché est ≥ 0 ; le contrôle inverse couvre l'autre côté).
    Calibration de l'audit : P(p<0,05) = 4,7 % sous H0 (300 marches),
    puissance 100 % à +0,4 % d'edge (n≈490)."""
    sig = spec["signal"]
    side = int(sig.get("side", -1))
    cost = float(spec.get("cost_pct", 0.28))
    h1 = int(spec.get("horizons", [24])[0])
    pairs = []
    for sym in kept_syms:
        if sym not in matrix or sym not in feats_by_sym:
            continue
        feats = feats_by_sym[sym]
        fz = frozen.get(sym) if frozen is not None else None
        if frozen is not None and fz is None:
            fz = [None] * len(_signal_conditions(sig))
        mask = event_mask(spec, feats, view, frozen=fz,
                          min_event_ms=min_event_ms,
                          thr_key=(*_db_key(db_path), sym))
        mask_h = apply_universe(spec, sym, mask, feats, h1)
        m_h = mask_h & (feats["open_time_ns"]
                        <= (view.end_ms - h1 * 3_600_000) * 10**6)
        if m_h.any():
            pairs.append((matrix[sym], m_h))
    return _perm_loop(pairs, h1, side, cost, mean_obs, n_perm, seed)


def _aggregate(per_symbol: dict, min_n: int) -> tuple[int, float]:
    """La moyenne agrégée PONDÉRÉE par n (rapport v6) : une moyenne de
    moyennes non pondérée donnait le même poids à un symbole à 3 events
    qu'à un symbole à 3 000. n_total reste le compte toutes fenêtres."""
    kept = [(float(s["mean"]), int(s.get("n", 0)))
            for s in per_symbol.values() if s.get("n", 0) >= min_n]
    n_total = sum(int(s.get("n", 0)) for s in per_symbol.values())
    if not kept:
        return n_total, float("nan")
    w = np.array([n for _, n in kept], dtype=float)
    m = np.array([mu for mu, _ in kept], dtype=float)
    return n_total, float((m * w).sum() / w.sum())


# ------------------------------------------------------------------ runs
def run_discovery(spec: dict, db_path: Path = KDB,
                   n_perm: int = 99) -> dict:
    """L'expérience DISCOVERY : vue TRAIN du DataScope uniquement, et
    production des seuils GELÉS que la confirmation réutilisera tels quels."""
    d = spec["data"]
    scope = DataScope(snapshot_id(db_path), int(d["train_start"]),
                      int(d["train_end"]), int(d["validation_start"]),
                      int(d["validation_end"]))
    view = scope.discovery_view()     # la validation n'y est pas résolvable
    use_cache = Path(db_path).resolve() == Path(KDB).resolve()
    lh, matrix = build_matrix(d["symbols"],
                              tuple(int(h) for h in spec.get("horizons", [24])),
                              db_path=db_path, use_cache=use_cache)
    try:
        feats_by_sym = _features_by_sym(spec, db_path)
        frozen = _frozen_thresholds(feats_by_sym,
                                    _signal_conditions(spec["signal"]), view)
        per_symbol = _study(spec, matrix, view, +1.0, db_path,
                            feats_by_sym=feats_by_sym)
    except ScopeViolation as exc:
        return {"verdict": "SCOPE_VIOLATION", "reason": str(exc)}
    min_n = int(spec.get("criteria", {}).get("min_n", 30))
    # PR-166 (P1 bug-hunter) : n et mean publiés = HORIZON 1 SEUL —
    # l'agrégat tous horizons comptait chaque trigger ×H (preuve : n
    # publié ×7,3) et le contrôle inverse (h1 seul) comparait deux
    # populations différentes. Miroir exact de la confirmation (h1 seul).
    h1 = spec.get("horizons", [24])[0]
    per_h1 = {k: v for k, v in per_symbol.items()
              if k.endswith(f"@{h1}h")}
    n_total, mean_all = _aggregate(per_h1, min_n)
    # le contrôle inverse : le côté inversé doit être pire sur l'horizon 1
    inv = _study(spec, matrix, view, -1.0, db_path,
                 feats_by_sym=feats_by_sym)
    inv_h1 = {k: v for k, v in inv.items()
              if k.endswith(f"@{spec.get('horizons', [24])[0]}h")}
    inv_n, inv_mean = _aggregate(inv_h1, min_n=min_n)
    # FIX v8 (rapport GLM 5.3 №9) : le contrôle inverse est un GATE — le
    # sens codé doit battre le sens inversé d'au moins min_edge_advantage_pct
    # (seuil du protocole, discovery_gate). Si l'inverse n'a pas assez
    # d'events pour être mesuré (inv_n < min_window_events), il ne gate pas.
    proto = load_confirmation_protocol()
    min_adv = float(proto.get("discovery_gate", {})
                    .get("min_edge_advantage_pct", 0.0))
    min_inv_n = int(proto.get("confirmation_gate", {})
                    .get("min_window_events", 5))
    advantage = (mean_all - inv_mean
                 if np.isfinite(mean_all) and np.isfinite(inv_mean)
                 else float("nan"))
    advantage_ok = (not np.isfinite(inv_mean) or inv_n < min_inv_n
                    or advantage > min_adv)
    verdict = ("DISCOVERY_PASS" if (n_total >= min_n
                                    and mean_all > float(spec.get("criteria",
                                                                 {}).get("min_mean", 0.0))
                                    and advantage_ok)
               else "DISCOVERY_FAIL")
    # PR-176 (B4 audit Sonnet 5.5) : la p-value par PERMUTATION
    # CIRCULAIRE — le n nominal ne se croit pas (events 24 h horaires
    # chevauchants) ; la sélection des candidats applique BH sur ce p
    kept_syms = sorted({k.split("@")[0] for k, v in per_h1.items()
                        if v.get("n", 0) >= min_n})
    p_perm = float("nan")
    if np.isfinite(mean_all) and kept_syms:
        p_perm = _perm_pvalue(spec, matrix, view, db_path, feats_by_sym,
                              frozen, 0, mean_all, min_n, kept_syms,
                              n_perm=n_perm)
    # FIX v19 (PR-155 №3) : publier le PIRE mean par symbole — la sélection
    # Pareto en a besoin (l'ancien NaN silencieux cassait la dominance)
    worst_sym = min((s["mean"] for s in per_symbol.values()
                     if s.get("n", 0) >= min_n and np.isfinite(s.get("mean", float("nan")))),
                    default=float("nan"))
    return {"verdict": verdict, "n": n_total, "mean": mean_all,
            "inverse_mean": inv_mean, "edge_advantage": advantage,
            "p_perm": p_perm,
            "worst": worst_sym, "per_symbol": per_symbol,
            "frozen_thresholds": frozen,
            "label_hash": lh, "label_version": LABEL_VERSION,
            "universe": spec.get("universe"),
            "spec_execution_sha": spec_execution_sha(spec),
            "universe_sha": universe_sha(spec["universe"]) if spec.get("universe") else None,
            "protocol_sha": protocol_sha(),
            "protocol_id": load_confirmation_protocol().get("protocol_id"),
            "snapshot": snapshot_id(db_path),
            "scope": {"mode": Mode.DISCOVERY.value,
                      "start": view.start_ms, "end": view.end_ms}}


def _month_ms(m: str) -> int:
    dt = datetime.strptime(m, "%Y-%m").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _frozen_windows_ms(proto: dict) -> list[tuple[str, int, int]]:
    """Les fenêtres gelées d'active.yaml en (nom, start_ms, end_ms)."""
    return [(str(w["start"]), _month_ms(str(w["start"])),
             _month_ms(str(w["end"])))
            for w in proto.get("frozen_windows", [])]


def run_confirmation(spec: dict, db_path: Path = KDB,
                     protocol: dict | None = None,
                     repair: bool = False) -> dict:
    """La CONFIRMATION sous protocole-v2 (rapport v6 — la porte conforme) :

      1. garde MODE : une spec déclarée « discovery » ne passe JAMAIS la
         porte (MODE_MISMATCH, 0 slot) ;
      2. les fenêtres : la validation de la spec doit couvrir les fenêtres
         gelées d'active.yaml, et l'évaluation est FAITE PAR FENÊTRE
         (verdict = ≥ windows_pass_required fenêtres PASS) — le verdict
         « CONFIRMED » d'une seule masse n'existe plus ;
      3. preflight (0 slot sur un échec d'infra, §47) ;
      4. seuils GELÉS depuis la découverte (artefact fait foi, sinon
         recalcul TRAIN only) + embargo à la frontière train→validation ;
      5. moyennes pondérées par n, dégradation train→validation ≤
         degradation_max_pct, et l'edge doit SURVIVRE au stress de coûts
         ×cost_stress_multiplier.

    max_window_loss_pct (15 %) s'applique au DD par fenêtre du WALLET —
    porté par la couche portefeuille (scripts/portfolio_runner.py).
    """
    d = spec["data"]
    if str(spec.get("mode", "confirmation")).lower() != "confirmation":
        return {"verdict": "MODE_MISMATCH", "slots_consumed": 0,
                "reason": (f"spec déclarée mode={spec.get('mode')!r} — la "
                           "confirmation est réservée aux specs pré-enregistrées "
                           "en mode confirmation")}
    proto = protocol if protocol is not None else load_confirmation_protocol()
    windows = _frozen_windows_ms(proto)
    vs, ve = int(d["validation_start"]), int(d["validation_end"])
    # chaque fenêtre gelée doit INTERSECTER la validation de la spec ; une
    # couverture partielle est tracée (coverage_pct) et rend la fenêtre
    # INÉLIGIBLE au PASS — une spec bâclée ne peut pas atteindre 5/6
    windows_cut: list[tuple[str, int, int, float]] = []
    for name, ws, we in windows:
        cs, ce_ = max(ws, vs), min(we, ve)
        if cs >= ce_:
            return {"verdict": "WINDOW_MISMATCH", "slots_consumed": 0,
                    "reason": (f"la fenêtre gelée {name} n'intersecte pas la "
                               "validation de la spec — research/protocols/"
                               "active.yaml est l'autorité (protocole-v2)")}
        windows_cut.append((name, cs, ce_, (ce_ - cs) / (we - ws) * 100.0))
    from scripts.preflight import preflight
    try:
        snap = snapshot_id(db_path)
    except sqlite3.Error:
        snap = "unknown"       # schéma cassé : preflight le dira, pas ici
    scope = DataScope(snap, int(d["train_start"]), int(d["train_end"]), vs, ve)
    conditions = _signal_conditions(spec["signal"])
    feats_used = {c.get("feature") for c in conditions}
    needs_funding = any(f and str(f).startswith("fund")
                        for f in feats_used)
    pre = preflight(scope, d["symbols"], db_path=db_path,
                    needs_funding=needs_funding)
    if pre["verdict"] != "PREFLIGHT_OK":
        return {"verdict": "PREFLIGHT_FAILED", "preflight": pre,
                "slots_consumed": 0}       # §47 : 0 slot sur un échec d'infra
    # FIX v16 (PR-149 Bloc B5) : le run_discovery doit avoir été mesuré
    # SOUS le protocole actif — un artefact d'un ancien protocole ne fonde
    # pas une confirmation courante (re-discovery obligatoire)
    active_proto = proto.get("protocol_id")
    d_proto_early = None
    sfile_early = RUNS / str(spec["id"]) / "summary_discovery.json"
    if sfile_early.exists():
        try:
            d_proto_early = json.loads(
                sfile_early.read_text(encoding="utf-8")).get("protocol_id")
        except json.JSONDecodeError:
            d_proto_early = None
    if d_proto_early != active_proto:
        return {"verdict": "CONFIRMATION_BLOCKED", "slots_consumed": 0,
                "reason": (f"la découverte a été mesurée sous le protocole "
                           f"{d_proto_early!r}, l'actif est {active_proto!r} "
                           "— re-discovery obligatoire (artefact pré-v16)")}
    use_cache = Path(db_path).resolve() == Path(KDB).resolve()
    lh, matrix = build_matrix(d["symbols"],
                              tuple(int(h) for h in spec.get("horizons", [24])),
                              db_path=db_path, use_cache=use_cache)
    train_view, val_view = scope.confirmation_view()
    feats_by_sym = _features_by_sym(spec, db_path)
    # — les seuils gelés : l'artefact de découverte EST OBLIGATOIRE sur le
    #   chemin officiel (fix v8, rapport GLM 5.3 №17 — un re-calcul sur le
    #   train actuel ne correspondrait plus à la découverte qui a produit
    #   le candidat). Le re-calcul ne survit qu'en mode réparation explicite.
    frozen, frozen_src = None, "missing"
    sfile = RUNS / str(spec["id"]) / "summary_discovery.json"
    disc_meta = {}
    if sfile.exists():
        s = json.loads(sfile.read_text(encoding="utf-8"))
        if s.get("frozen_thresholds"):
            frozen, frozen_src = s["frozen_thresholds"], "discovery_artifact"
            # FIX v16 (PR-149 Bloc B4) : la confirmation est LIÉE à
            # l'artefact de découverte qui l'a fondée — même spec_sha, même
            # snapshot, même protocole, sinon la porte est bloquée (une
            # spec A + des seuils de découverte B ne fait pas une preuve)
            cur_snap = snapshot_id(db_path)
            problems = []
            if s.get("spec_execution_sha") != spec_execution_sha(spec):
                problems.append(f"spec d'exécution {s.get('spec_execution_sha')} ≠ "
                                f"courant {spec_execution_sha(spec)}")
            if s.get("snapshot") != cur_snap:
                problems.append(f"snapshot {s.get('snapshot')} ≠ courant "
                                f"{cur_snap}")
            d_proto = s.get("protocol_id")
            cur_proto = load_confirmation_protocol().get("protocol_id")
            if d_proto and d_proto != cur_proto:
                problems.append(f"protocole {d_proto} ≠ actif {cur_proto}")
            if problems:
                return {"verdict": "CONFIRMATION_BLOCKED", "slots_consumed": 0,
                        "reason": ("l'artefact de découverte ne correspond "
                                   "pas au run courant : " + " ; ".join(problems))}
            disc_meta = {"spec_execution_sha": s.get("spec_execution_sha"),
                                 "universe_sha": s.get("universe_sha"),
                                 "protocol_sha": s.get("protocol_sha"),
                         "snapshot": cur_snap,
                         "protocol_id": d_proto}
    if frozen is None and not repair:
        return {"verdict": "CONFIRMATION_BLOCKED", "slots_consumed": 0,
                "reason": ("aucun artefact de découverte avec frozen_thresholds "
                           f"pour {spec['id']} — le re-calcul est interdit sur "
                           "le chemin officiel (re-lancez la découverte ou "
                           "passez repair=True en connaissance de cause)")}
    if frozen is None:
        frozen = _frozen_thresholds(feats_by_sym, conditions, train_view)
        frozen_src = "recomputed_train_repair"
    embargo_ms = (int(d["train_end"])
                  + int(proto.get("embargo_hours", 0)) * 3_600_000)
    cost = float(spec.get("cost_pct", 0.28))
    stress_mult = float(proto.get("cost_stress_multiplier", 1.5))
    deg_max = float(proto.get("degradation_max_pct", 70))
    need = int(proto.get("windows_pass_required", 5))
    # FIX v10 (audit GLM 5.3 post-#135) : l'agrégat validation est évalué sur
    # LE MÊME UNIVERS que les fenêtres gelées — la zone entre la dernière
    # fenêtre et validation_end n'appartient à aucun univers protocolaire.
    ve_eval = min(ve, max((we for _, _, we, _c in windows_cut), default=ve))
    # FIX v8 (rapport GLM 5.3 №10/№22) : TOUS les seuils de jugement viennent
    # du protocole — le plancher d'events par fenêtre n'est plus une
    # constante Python (ex WINDOW_MIN_N) mais confirmation_gate.
    gate = proto.get("confirmation_gate", {})
    min_window_events = int(gate.get("min_window_events", 5))
    min_fund_cov = float(gate.get("min_fund_coverage", 0.5))
    h1 = int(spec.get("horizons", [24])[0])
    min_n = int(spec.get("criteria", {}).get("min_n", 30))

    # — le train : la référence de dégradation (seuils expanding sur le
    #   passé, identiques à la découverte) —
    tr = _study(spec, matrix, train_view, +1.0, db_path,
                feats_by_sym=feats_by_sym)
    _, tr_mean = _aggregate({k: v for k, v in tr.items()
                             if k.endswith(f"@{h1}h")}, min_n)

    # — les fenêtres gelées, une par une, seuils gelés + embargo —
    # FIX v10 : chaque fenêtre est jugée sur TROIS gates (mean, STRESS ×1,5,
    # DD MTM ≤ max_window_loss_pct) — l'ancien code laissait une fenêtre
    # « PASS » survivre à un stress ou un DD catastrophique
    from scripts.portfolio_runner import (  # import tardif (cycle évité)
        _fetch_marks, collect_events, run_wallet_mtm)
    max_w_loss = float(proto.get("max_window_loss_pct", 15))
    per_window: dict[str, dict] = {}
    for name, ws, we, cov in windows_cut:
        wview = DataView(snap, Mode.CONFIRMATION.value, ws, we)
        wst = _study(spec, matrix, wview, +1.0, db_path,
                     feats_by_sym=feats_by_sym, frozen=frozen,
                     min_event_ms=embargo_ms)
        wst_s = _study(spec, matrix, wview, +1.0, db_path,
                       feats_by_sym=feats_by_sym, frozen=frozen,
                       min_event_ms=embargo_ms, cost_pct=cost * stress_mult)
        n_w, mean_w = _aggregate({k: v for k, v in wst.items()
                                  if k.endswith(f"@{h1}h")},
                                 min_n=min_window_events)
        _ns, stress_w = _aggregate({k: v for k, v in wst_s.items()
                                    if k.endswith(f"@{h1}h")},
                                   min_n=min_window_events)

        dd_w = None
        try:
            ev_w, _cov = collect_events(spec, matrix, feats_by_sym, wview,
                                        frozen=frozen,
                                        min_event_ms=embargo_ms,
                                        db_path=db_path)
            mk_w = _fetch_marks(db_path, spec["data"]["symbols"], ws, we)
            if ev_w and mk_w:
                dd_w = run_wallet_mtm(ev_w, mk_w, capital=100.0,
                                      cap_pct=1.0, lev=1.0)["max_dd_mtm"]
        except Exception:
            dd_w = None
        eligible = cov >= 99.9     # une fenêtre tronquée ne démontre rien
        # FIX v17 (PR-150 №2) : la couverture funding est un gate PAR
        # FENÊTRE — 5 fenêtres à 100 % + 1 à 0 % doit échouer sur la 6e
        # (l'ancienne moyenne pondérée globale la laissait passer)
        w_cov = [(float(v.get("fund_cov", 0.0)), int(v.get("n", 0)))
                 for v in wst.values() if v.get("n", 0) >= min_window_events]
        window_fund_cov = (sum(c * n for c, n in w_cov)
                           / sum(n for _, n in w_cov)) if w_cov else 0.0
        pass_funding = bool(eligible
                            and window_fund_cov >= min_fund_cov)
        pass_base = bool(eligible and n_w >= min_window_events
                         and mean_w > 0.0)
        pass_stress = bool(eligible and stress_w > 0.0)
        # FIX v14 (audit GLM 5.3 №5) : FAIL-CLOSED — un DD inconnu n'est
        # plus un PASS (l'ancien or dd_w is None était un fail-open sur un
        # gate de risque)
        dd_status = ("UNKNOWN" if dd_w is None
                     else ("PASS" if dd_w <= max_w_loss else "FAIL"))
        pass_dd = bool(eligible and dd_status == "PASS")
        per_window[name] = {"n": n_w, "mean": mean_w,
                            "stress_mean": stress_w, "max_dd_mtm": dd_w,
                            "dd_status": dd_status,
                            "fund_coverage": window_fund_cov,
                            "coverage_pct": cov, "eligible": eligible,
                            "pass_base": pass_base, "pass_stress": pass_stress,
                            "pass_dd": pass_dd, "pass_funding": pass_funding,
                            "pass": bool(pass_base and pass_stress
                                         and pass_dd and pass_funding)}

    # — la validation d'un bloc : l'agrégat + le stress de coûts —
    val_view_eval = DataView(snap, Mode.CONFIRMATION.value, vs, ve_eval)
    val = _study(spec, matrix, val_view_eval, +1.0, db_path,
                 feats_by_sym=feats_by_sym, frozen=frozen,
                 min_event_ms=embargo_ms)
    val_h1 = {k: v for k, v in val.items() if k.endswith(f"@{h1}h")}
    n_total, val_mean = _aggregate(val_h1, min_n)
    stress = _study(spec, matrix, val_view_eval, +1.0, db_path,
                    feats_by_sym=feats_by_sym, frozen=frozen,
                    min_event_ms=embargo_ms, cost_pct=cost * stress_mult)
    _, stress_mean = _aggregate({k: v for k, v in stress.items()
                                 if k.endswith(f"@{h1}h")}, min_n)
    deg = float("nan")
    if np.isfinite(tr_mean) and tr_mean > 0 and np.isfinite(val_mean):
        deg = (tr_mean - val_mean) / tr_mean * 100.0

    n_pass = sum(1 for w in per_window.values() if w["pass"])
    min_mean = float(spec.get("criteria", {}).get("min_mean", 0.0))
    # FIX v8 (rapport GLM 5.3 №4) : la couverture de funding de l'agrégat
    # est un gate du protocole — un funding massivement inconnu ne peut plus
    # passer inaperçu (la contribution inconnue reste 0, jamais inventée).
    kept_cov = [(float(v.get("fund_cov", 0.0)), int(v.get("n", 0)))
                for v in val_h1.values() if v.get("n", 0) >= min_n]
    if kept_cov and sum(n for _, n in kept_cov) > 0:
        fund_cov = float(sum(c * n for c, n in kept_cov)
                         / sum(n for _, n in kept_cov))
    else:
        fund_cov = 0.0
    dd_breach = [k for k, w in per_window.items()
                 if w["eligible"] and not w["pass_dd"]]
    verdict = ("CONFIRMED" if (n_total >= min_n and val_mean > min_mean
                               and n_pass >= need
                               and stress_mean > 0.0
                               and fund_cov >= min_fund_cov
                               and not dd_breach
                               # PR-166 (P2 bug-hunter) : FAIL-CLOSED —
                               # un dégagement incalculable (tr_mean ≤ 0,
                               # NaN) est un REJET, pas un passage
                               and (np.isfinite(deg) and deg <= deg_max))
               else "REJECTED")
    return {"verdict": verdict, "n": n_total, "mean": val_mean,
            "train_mean": tr_mean, "degradation_pct": deg,
            # PR-166 (P2 bug-hunter) : l'horloge de maturation est STAMPÉE
            # ICI — le manifest peut être réécrit par une re-discovery
            # (preuve réelle : EXP-bonsai-h-18), jamais ce champ
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "stress_mean": stress_mean, "stress_multiplier": stress_mult,
            "fund_coverage": fund_cov,
            "dd_breach_windows": dd_breach,
            "max_window_loss_pct": max_w_loss,
            "universe": spec.get("universe"),
            "protocol_id": proto.get("protocol_id"),
            "label_version": LABEL_VERSION,
            "discovery_artifact": {"frozen_src": frozen_src,
                                   **disc_meta},
            "per_window": per_window, "windows_pass": n_pass,
            "windows_required": need, "embargo_ms": embargo_ms,
            "frozen_src": frozen_src, "per_symbol": val,
            "slots_consumed": 1, "label_hash": lh, "snapshot": snap,
            "validation_window": [val_view.start_ms, val_view.end_ms]}


# ------------------------------------------------------------------ artefacts
def write_artifacts(run_id: str, spec: dict, result: dict, kind: str,
                    db_path: Path = KDB) -> Path:
    rdir = RUNS / run_id
    rdir.mkdir(parents=True, exist_ok=True)
    sha = spec_sha(spec)
    # FIX v11 (PR-4, audit GLM 5.3 №20) : le dossier de run est APPEND-ONLY
    # en PROVENANCE — si un manifeste existe avec une provenance DIFFÉRENTE
    # (snapshot, git, diff), l'ancienne preuve est archivée sous attempts/<n>/
    # avant réécriture. Une réécriture à provenance IDENTIQUE reste
    # idempotente (le même run re-jeté, pas une nouvelle expérience).
    mfile = rdir / "manifest.json"
    attempt = 1
    if mfile.exists():
        try:
            old_m = json.loads(mfile.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            old_m = {}
        prov_now = _provenance()
        # PR-166 (P2 bug-hunter) : le `kind` fait partie de l'identité —
        # une réécriture discovery↔confirmation à provenance égale
        # écrasait report.md sans archivage (le ref du ledger discovery
        # pointait alors vers le rapport de l'AUTRE phase)
        same = (old_m.get("spec_sha") == sha
                and old_m.get("kind") == kind
                and old_m.get("snapshot") == result.get("snapshot")
                and old_m.get("git_sha") == prov_now.get("git_sha")
                and old_m.get("diff_sha") == prov_now.get("diff_sha"))
        if not same:
            prev = int(old_m.get("attempt", 1))
            attempt = prev + 1
            adir = rdir / "attempts" / f"{prev:03d}"
            adir.mkdir(parents=True, exist_ok=True)
            import shutil
            for f in ("manifest.json", "spec.json", "summary_discovery.json",
                      "summary_confirmation.json", "wallet.json",
                      "report.md", "report_wallet.md"):
                if (rdir / f).exists():
                    # ARCHIVAGE PAR COPIE (fix v13) : le déplacement cassait
                    # l'auto-contenance du run — la confirmation a besoin du
                    # summary_discovery (seuils gelés) au niveau racine pour
                    # le forward et le wallet. L'historique reste intact.
                    shutil.copy2(rdir / f, adir / f)
    (rdir / "spec.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8")
    snap = result.get("snapshot")
    if snap is None:
        try:
            snap = snapshot_id(db_path)
        except sqlite3.Error:
            snap = "unknown"   # DB absente (CI) : le manifest reste écrit
    prov = _provenance()
    try:
        proto_id = load_confirmation_protocol().get("protocol_id")
    except Exception:
        proto_id = None
    (rdir / "manifest.json").write_text(json.dumps({
        "run_id": run_id, "kind": kind, "spec_sha": sha,
        "attempt": attempt,
        "git_sha": prov["git_sha"], "git_dirty": prov["git_dirty"],
        "diff_sha": prov["diff_sha"],
        "label_hash": result.get("label_hash"), "snapshot": snap,
        "label_version": result.get("label_version"),
        "protocol_id": result.get("protocol_id") or proto_id,
        "spec_execution_sha": result.get("spec_execution_sha"),
        "universe_sha": result.get("universe_sha"),
        "protocol_sha": result.get("protocol_sha"),
        "env": _env_versions(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = {k: v for k, v in result.items() if k != "per_symbol"}
    summary.update({"run_id": run_id, "spec_sha": sha,
                    "per_symbol": result.get("per_symbol", {})})
    (rdir / f"summary_{kind}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=float),
        encoding="utf-8")
    lines = [f"# {run_id} — {kind}", "",
             f"Hypothèse : {spec.get('hypothesis', '')}", "",
             f"- spec_sha {sha} · git {_git()} · snapshot {snap}",
             f"- verdict : **{result.get('verdict')}** · n {result.get('n')} · "
             f"mean {result.get('mean')}", ""]
    for key, st in result.get("per_symbol", {}).items():
        lines.append(f"- {key} : n {st.get('n')} · mean "
                     f"{float(st.get('mean', float('nan'))):.3f}")
    (rdir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rdir


def _ledger_params(spec: dict) -> list[str]:
    """F-045 — les PARAMÈTRES du spec, au format `k=v` de lab_ledger.

    Le garde anti grid-sweep de la gouvernance est
    `max_parameter_variants` (policy.yaml), application dans
    `lab_ledger.assess` :

        same_h = [e for e in entries if e["_hh"] == hh]
        variants = len({e["_ph"] for e in same_h})
        if variants + 1 > budget["max_parameter_variants"]: STOP

    où `ph = sha(json.dumps(params))`. Or les deux appels subprocess
    (ici et dans `_budget_precheck`) ne passaient PAS `--params` :
    `params` valait toujours `{}`, donc `ph` une constante et le compteur
    `variants` ne comptait que le nombre d'ENTRÉES, jamais des variantes
    RÉELLES. Concrètement : re-tester la même hypothèse avec
    `threshold` 1.5 puis 1.6 puis 1.7 ne déclenchait pas le plafond, et le
    `parameter_hash` du dedup (`dedup_hashes` de policy.yaml) ne
    discriminait rien. Le garde existait, il était inerte.

    On dérive `params` de ce qui fait DEUX ÉTUDES DIFFÉRENTES la même
    hypothèse : la définition du signal, les horizons, les critères de
    passage, le coût et l'univers. On EXCLUT délibérément `id`,
    `hypothesis` (déjà le `hypothesis_hash`), `family`/`strategy`
    (déjà des colonnes du ledger), les fenêtres temporelles (elles
    avancent avec le snapshot : c'est une réplication, pas une variante)
    et `compute` (l'infrastructure n'est pas une variable d'expérience).
    """
    def _flat(v):
        return json.dumps(v, sort_keys=True, separators=(",", ":"))

    p: dict[str, str] = {}
    if spec.get("signal") is not None:
        p["signal"] = _flat(spec["signal"])
    if spec.get("horizons") is not None:
        p["horizons"] = _flat(spec["horizons"])
    if spec.get("criteria") is not None:
        p["criteria"] = _flat(spec["criteria"])
    if spec.get("cost_pct") is not None:
        p["cost_pct"] = str(spec["cost_pct"])
    data = spec.get("data") or {}
    if data.get("symbols") is not None:
        p["symbols"] = ",".join(sorted(str(s) for s in data["symbols"]))
    if data.get("timeframe") is not None:
        p["timeframe"] = str(data["timeframe"])
    return [f"{k}={v}" for k, v in sorted(p.items())]


def _log_ledger(spec: dict, verdict: str, mode: str, ref: str,
                snapshot: str | None = None,
                fail_closed: bool = True) -> None:
    """FIX v8 (№21) : le snapshot du ledger est CELUI DU RUN — jamais
    recalculé implicitement sur une autre DB.
    FIX v16 (PR-149 Bloc B6) : au CONFIRM, l'écriture au ledger est
    FAIL-CLOSED — un CONFIRMED sans sa ligne de budget est une
    sous-déclaration de gouvernance (l'ancien check=False laissait passer).
    PR-163 (P2 bug-hunter) : fail-closed PARTOUT — un PASS discovery
    sans sa ligne de ledger est une pression de sélection invisible
    (l'ancien défaut False laissait un ledger en erreur passer
    silencieusement ; le worker enregistre alors FAILED_RETRYABLE et
    re-tentera la SPEC au prochain lancement)."""
    if snapshot is None:
        try:
            snapshot = str(snapshot_id())
        except sqlite3.Error:
            snapshot = "unknown"
    result = subprocess.run([
        sys.executable, "scripts/lab_ledger.py", "log",
        "--family", str(spec.get("family", "research")),
        "--strategy", str(spec.get("strategy", "runner")),
        "--hypothesis", str(spec.get("hypothesis", ""))[:300],
        "--verdict", verdict, "--mode", mode,
        "--snapshot", snapshot, "--ref", ref,
        "--params", *_ledger_params(spec)],   # F-045
        capture_output=fail_closed, text=fail_closed, cwd=ROOT)
    if fail_closed and result.returncode != 0:
        raise RuntimeError(
            f"écriture au ledger ÉCHOUÉE (rc {result.returncode}) : "
            f"{(result.stderr or result.stdout).strip()[:300]} — le verdict "
            "n'est PAS publié (gouvernance fail-closed)")


# ------------------------------------------------------------------ CLI
def cmd_discovery(a) -> int:
    spec = load_spec(Path(a.spec))
    res = run_discovery(spec, db_path=Path(a.db))
    rdir = write_artifacts(spec["id"], spec, res, "discovery", db_path=Path(a.db))
    _log_ledger(spec, res["verdict"], Mode.DISCOVERY.value,
                str(rdir / "report.md"), snapshot=res.get("snapshot"))
    print(f"{spec['id']} : {res['verdict']} · n {res['n']} · mean "
          f"{res['mean']:.3f} · inverse {res['inverse_mean']:.3f} · "
          f"p_perm {res.get('p_perm', float('nan')):.3f}")
    print("DISCOVERY = TRAIN only — jamais promote sans confirmation.")
    return 0


def cmd_confirm(a) -> int:
    spec = load_spec(Path(a.spec))
    # FIX v14 (audit GLM 5.3 post-#142) : une confirmation OFFICIELLE exige
    # un arbre propre — git_dirty=true signifie que le code exécuté n'est
    # dans AUCUN commit (le diff_sha aide mais ne reconstruit pas). Le
    # workflow est : committer d'abord, confirmer ensuite.
    prov = _provenance()
    if prov["git_dirty"]:
        print(f"{spec['id']} : EXECUTION_NOT_SEALED — l'arbre Git est sale "
              f"(diff_sha {prov['diff_sha']}) : committer le code d'abord, "
              "confirmer ensuite (0 slot consommé)")
        return 1
    # FIX v8 (rapport GLM 5.3 №18) : la réservation du slot est sérialisée
    # par un verrou fichier — deux process ne peuvent plus croire
    # simultanément qu'il reste un slot (le budget est jugé au log, sous
    # le même verrou).
    import fcntl
    lock_path = ROOT / "research" / "ledger" / "confirm.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        return _confirm_locked(spec, a)


def _budget_precheck(spec: dict, db_path: Path) -> tuple[bool, str]:
    """Le budget JUGE AVANT de laisser courir (fix v10 : contrôle bloquant,
    plus seulement une journalisation). Le sous-commande `check` de
    lab_ledger évalue sans écrire : 0 = GO, 4 = STOP.
    FIX v15 (audit GLM 5.3 post-#147 №1) : le snapshot est calculé sur la
    DB DU RUN (--db) — l'ancien snapshot_id() implicite interrogeait le
    warehouse par défaut et pouvait retourner un mauvais DUPLICATE/REVERIFY
    une fois que #147 a rendu le snapshot déterminant pour le budget."""
    out = subprocess.run(
        [sys.executable, "scripts/lab_ledger.py", "check",
         "--family", str(spec.get("family", "research")),
         "--strategy", str(spec.get("strategy", "runner")),
         "--hypothesis", str(spec.get("hypothesis", ""))[:300],
         "--mode", "confirmation",
         "--snapshot", str(snapshot_id(db_path)),
         "--params", *_ledger_params(spec)],   # F-045
        capture_output=True, text=True, cwd=ROOT)
    ok = out.returncode == 0
    return ok, (out.stdout + out.stderr).strip()


def _confirm_locked(spec: dict, a) -> int:
    ok, why = _budget_precheck(spec, db_path=Path(a.db))
    if not ok:
        print(f"{spec['id']} : BUDGET_STOP — 0 slot consommé (le budget est "
              "une barrière, pas une journalisation)")
        for line in why.splitlines():
            print("  " + line)
        return 1
    res = run_confirmation(spec, db_path=Path(a.db))
    if res["verdict"] in ("MODE_MISMATCH", "WINDOW_MISMATCH",
                          "CONFIRMATION_BLOCKED"):
        print(f"{spec['id']} : {res['verdict']} — 0 slot consommé\n"
              f"  {res.get('reason', '')}")
        return 1
    if res["verdict"] == "PREFLIGHT_FAILED":
        print(f"{spec['id']} : PREFLIGHT_FAILED — 0 slot consommé")
        for c in res["preflight"]["checks"]:
            if not c["ok"]:
                print(f"  [ÉCHEC] {c['check']} — {c['detail']}")
        return 1
    # FIX v18 (PR-150 №4) : l'ORDRE transactionnel — le ledger D'ABORD
    # (fail-closed : pas de ligne = pas de verdict), puis le wallet
    # (obligatoire, plus de except aval), puis les artefacts : CONFIRMED
    # est un état terminal impossible à moitié écrit
    _log_ledger(spec, "FAIL" if res["verdict"] == "REJECTED" else "PASS",
                Mode.CONFIRMATION.value,
                # PR-166 (P0 bug-hunter) : `rr` n'existe PAS dans ce module
                # (résidu PR-150) — TOUTE confirmation CLI crashait en
                # NameError APRÈS le calcul : verdict jeté, ledger jamais
                # écrit, budget jamais décompté
                str(RUNS / spec["id"] / "report.md"),
                snapshot=res.get("snapshot"), fail_closed=True)
    pw = res.get("windows_pass")
    print(f"{spec['id']} : {res['verdict']} · n {res['n']} · mean "
          f"{res['mean']:.3f} · fenêtres {pw}/{res.get('windows_required')} "
          f"PASS · stress ×{res.get('stress_multiplier')} mean "
          f"{res.get('stress_mean', float('nan')):.3f} · fund_cov "
          f"{res.get('fund_coverage', 0.0):.2f} · slot consommé")
    rdir = write_artifacts(spec["id"], spec, res, "confirmation",
                           db_path=Path(a.db))
    if res["verdict"] == "CONFIRMED":
        # PR-B + FIX v18 (№4) : le wallet est OBLIGATOIRE — plus de except
        # aval : un échec wallet = échec du confirm (exit non nul), les
        # artefacts ne masquent plus un run incomplet
        from scripts.portfolio_runner import wallet_for_run, wallet_report_block
        # la vue validation est EXPLICITE : l'artefact summary_confirmation
        # n'est pas encore écrit à ce stade de l'ordre transactionnel
        w = wallet_for_run(spec["id"], db_path=Path(a.db),
                           view_kind="validation")
        (rdir / "wallet.json").write_text(
            json.dumps(w, ensure_ascii=False, indent=1, default=float),
            encoding="utf-8")
        (rdir / "report_wallet.md").write_text(
            wallet_report_block(w), encoding="utf-8")
        with open(rdir / "report.md", "a", encoding="utf-8") as fh:
            fh.write(wallet_report_block(w))
        wl = w["wallet"]
        print(f"  WALLET {wl['capital']:.0f}$ cap {w['cap_pct']:.1f} % "
              f"lev {w['lev']:.0f}x : solde {wl['solde']:.2f}$ · DD "
              f"{wl['max_dd_pct']:.2f} % · liq {wl['liqs']} · mois nég "
              f"{wl['months_neg']}")
    return 0


def cmd_compare(a) -> int:
    print(f"{'id':<28} {'n':>6} {'verdict':<18} {'mean':>8} {'inverse':>8}")
    for rid in a.ids:
        f = None
        for k in ("summary_discovery.json", "summary_confirmation.json"):
            if (RUNS / rid / k).exists():
                f = RUNS / rid / k
                break
        if f is None:
            print(f"{rid} : aucun summary")
            continue
        s = json.loads(f.read_text(encoding="utf-8"))
        print(f"{rid:<28} {s.get('n', 0):>6} {str(s.get('verdict')):<18} "
              f"{float(s.get('mean', float('nan'))):>8.3f} "
              f"{float(s.get('inverse_mean', float('nan'))):>8.3f}")
    print("\nrobust winner ≠ absolute winner : compare aussi inverse et n.")
    return 0


def _resource_guard() -> tuple[bool, str]:
    """Le gouverneur de ressources (brief V3 §27, §138) : une limite
    PHYSIQUE, pas un plafond arbitraire. RAM disponible et disque libre."""
    try:
        mem = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                mem[k] = int(v.strip().split()[0])  # kB
        avail_gb = mem.get("MemAvailable", 0) / 1024 / 1024
        if avail_gb < 1.0:
            return False, f"RAM disponible {avail_gb:.1f} Go < 1 Go — pause"
    except OSError:
        pass
    du = shutil.disk_usage(ROOT)
    if du.free / 1024**3 < 2.0:
        return False, f"disque libre {du.free / 1024**3:.1f} Go < 2 Go"
    return True, "OK"


def _stage1_screen(spec: dict, db_path: Path) -> dict:
    """STAGE 1 — le screen bon marché : l'horizon PRINCIPAL seulement."""
    mini = dict(spec)
    mini["horizons"] = [int(spec["horizons"][0])]
    return run_discovery(mini, db_path=db_path)


def _passes(res: dict, spec: dict) -> bool:
    """FIX v19 (PR-155 №2) : le VERDICT doit être DISCOVERY_PASS —
    l'ancien code ne vérifiait que n et mean, un run rejeté par le gate
    inverse (edge_advantage ≤ 0) ou par la couverture funding pouvait
    ré-entrer la file de candidats."""
    if res.get("verdict") != "DISCOVERY_PASS":
        return False
    crit = spec.get("criteria", {})
    return (res.get("n", 0) >= int(crit.get("min_n", 30))
            and (res.get("mean", float("nan")) > float(crit.get("min_mean", 0.0))))


def cmd_grind(a) -> int:
    """LE GRIND (brief V3 §167-169) : la queue → screen bon marché → prune
    → screen complet → candidats. Successive halving : le calcul cher est
    réservé aux hypothèses qui méritent du calcul (§25-26)."""
    q = Path(a.queue)
    # récursif (rapport v6) : les sous-dossiers de la queue (bonsai/…) sont
    # grindés aussi ; done/ reste exclu (les specs jugées ne re-passent pas)
    specs = [p for p in sorted(q.rglob("*"))
             if p.is_file() and p.suffix in (".yaml", ".yml", ".json")
             and "done" not in p.parts]
    if not specs:
        print(f"queue vide : {q}")
        return 0
    order = {"tiny": 0, "small": 1, "medium": 2, "large": 3}
    specs.sort(key=lambda f: order.get(
        (json.loads(f.read_text(encoding="utf-8")).get("compute", {})
         .get("class", "small")), 1))
    ok_guard, why = _resource_guard()
    if not ok_guard:
        print(f"grind : WAITING_RESOURCE — {why} (exit 42, pas un succès)")
        return 42
    # N1 — dimensionner la permutation selon la taille du LOT, connue
    # avant le moindre run. À n_perm=99 le plancher de p est 0,01, et le
    # BH au rang 1 exige p <= q/m : sur un lot > 10 specs, aucun candidat
    # ne pouvait JAMAIS passer, même avec un edge réel. Le contrôle
    # multiplicatif était donc un refus automatique déguisé en filtre.
    n_perm = bh_min_perms(len(specs))
    p_min = 1.0 / (n_perm + 1)
    print(f"[grind] lot de {len(specs)} spec(s) — {n_perm} permutations/spec "
          f"(plancher de p = {p_min:.4f}, seuil BH rang 1 = "
          f"{BH_Q / max(1, len(specs)):.4f})")
    if not bh_reachable(p_min, len(specs)):
        print("[grind] ATTENTION : le seuil BH reste hors de portée — "
              "réduire la taille du lot ou augmenter n_perm")
    if n_perm > 99:
        print(f"[grind]   coût de la permutation multiplié par "
              f"{n_perm / 99:.1f} vs le défaut (99) : c'est le prix d'un "
              f"BH qui filtre vraiment")
    survivors = []
    for f in specs:
        spec = load_spec(f)
        print(f"[grind] stage 1 : {spec['id']} — screen {spec['horizons'][0]}h",
              flush=True)
        r1 = _stage1_screen(spec, Path(a.db))
        if not _passes(r1, spec):
            print(f"[grind]   éliminé (stage 1 : n {r1.get('n')}, "
                  f"mean {r1.get('mean', float('nan')):.3f})")
            continue
        print(f"[grind] stage 2 : {spec['id']} — tous les horizons + inverse")
        r2 = run_discovery(spec, db_path=Path(a.db), n_perm=n_perm)
        if _passes(r2, spec):
            write_artifacts(spec["id"], spec, r2, "discovery")
            _log_ledger(spec, r2["verdict"], Mode.DISCOVERY.value,
                        str(RUNS / spec["id"] / "report.md"),
                        snapshot=r2.get("snapshot"))
            survivors.append(spec["id"])
            print(f"[grind]   CANDIDATE discovery : {r2['verdict']} "
                  f"(n {r2['n']}, mean {r2['mean']:.3f})")
        else:
            print(f"[grind]   éliminé (stage 2)")
        ok_guard, why = _resource_guard()
        if not ok_guard:
            print(f"[grind] {why} — arrêt propre de la file")
            break
    print(f"\ngrind terminé : {len(survivors)} candidat(s) discovery "
          f"→ confirmation sur go du propriétaire (jamais promote automatiquement)")
    return 0


def _cluster_key(spec: dict) -> str:
    """La clé de MECHANISM CLUSTER (brief V3 §61-62) : même famille + même
    feature + même opérateur = une seule idée conceptuelle, peu importe les
    seuils (RSI 29/30/31 ne sont pas 3 idées)."""
    s = spec.get("signal", {})
    return (f"{spec.get('family', '?')}|{s.get('feature', '?')}|"
            f"{s.get('op', '?')}|{s.get('side', -1)}")


def _pareto_frontier(rows: list[dict]) -> list[dict]:
    """La frontière de Pareto sur (mean ↑, n ↑, worst ↑) — brief V3 §61."""
    front = []
    for r in rows:
        dominated = any(
            (o["mean"] >= r["mean"] and o["n"] >= r["n"] and o["worst"] >= r["worst"])
            and (o["mean"] > r["mean"] or o["n"] > r["n"] or o["worst"] > r["worst"])
            for o in rows if o is not r)
        if not dominated:
            front.append(r)
    return front


def cmd_select(a) -> int:
    """PR 9 : la sélection des candidats — clusters + Pareto + diversité +
    pression de sélection (brief V3 §63-64, §73). AUCUNE valeur de PASS ici :
    la sélection produit des CANDIDATS, la confirmation juge."""
    rows = []
    for f in sorted(RUNS.glob("*/summary_discovery.json")):
        s = json.loads(f.read_text(encoding="utf-8"))
        spec_f = RUNS / s.get("run_id", f.parent.name) / "spec.json"
        spec = json.loads(spec_f.read_text(encoding="utf-8")) if spec_f.exists() else {}
        rows.append({"id": s.get("run_id"), "n": s.get("n", 0),
                     "mean": s.get("mean", float("nan")),
                     "worst": s.get("worst", float("nan")),
                     "cluster": _cluster_key(spec),
                     "verdict": s.get("verdict"),
                     "p_perm": s.get("p_perm", float("nan"))})
    # PR-166 (P1 bug-hunter) : seuls les DISCOVERY_PASS à mean fini sont
    # éligibles — un FAIL (mean NaN) n'est jamais dominé (NaN compare
    # toujours False) et sortait SUR la frontière comme CANDIDAT
    rows = [r for r in rows
            if r["verdict"] == "DISCOVERY_PASS"
            and np.isfinite(r["mean"])]
    # PR-176 (B4 audit Sonnet 5.5) : le CONTRÔLE BH sur le lot — la
    # découverte reste illimitée, les faux positifs se contrôlent ICI
    # (q = 0.10 sur la p par permutation circulaire). Les summaries
    # pré-PR-176 (sans p_perm) ne peuvent pas prouver leur p : hors sélection.
    ps = sorted((r for r in rows if np.isfinite(r.get("p_perm", float("nan")))),
                key=lambda r: r["p_perm"])
    m = len(ps)
    k_max = 0
    for i, r in enumerate(ps, 1):
        if r["p_perm"] <= i * 0.10 / m:
            k_max = i
    bh_ok = {r["id"] for r in ps[:k_max]}
    dropped = len(rows) - len(bh_ok)
    if rows:
        print(f"BH (q={BH_Q:.2f}, m={m}) : {len(bh_ok)} survivant(s) — "
              f"{dropped} écarté(s) du lot")
        # N1 : si le seuil du rang 1 est hors de portée de la résolution
        # disponible, le BH ne filtre rien : il écarte tout. Le dire.
        if ps and not bh_reachable(ps[0]["p_perm"], m):
            print(f"  ATTENTION BH : le meilleur p du lot est "
                  f"{ps[0]['p_perm']:.4f}, le seuil du rang 1 est "
                  f"{BH_Q / m:.4f} — sur les {m} specs sélectionnées, "
                  f"ce lot ne peut produire aucun survivant. "
                  f"Il faut n_perm >= {bh_min_perms(m)}.")
    rows = [r for r in rows if r["id"] in bh_ok]
    if not rows:
        print("aucune discovery à sélectionner")
        return 0
    frontier = _pareto_frontier(rows)
    clusters: dict[str, list[dict]] = {}
    for r in frontier:
        clusters.setdefault(r["cluster"], []).append(r)
    picked = []
    for cl, items in clusters.items():
        items.sort(key=lambda r: -r["mean"])
        picked.extend(items[:a.per_cluster])   # la diversité : ≤ N par cluster
    pressure = len(rows)
    print(f"{pressure} discoveries considérées · {len(frontier)} sur la frontière "
          f"de Pareto · {len(clusters)} mécanismes clusters · {len(picked)} "
          f"candidats (≤ {a.per_cluster}/cluster)\n")
    for r in picked:
        pct = r["n"] / pressure * 100 if pressure else 0
        print(f"  {r['id']} : mean {r['mean']:.3f} · n {r['n']} · "
              f"cluster {r['cluster']} · pression {pct:.1f} %")
    if picked:
        print("\nbloc registry prêt à coller (la curation reste au "
              "propriétaire — le registre est un fichier de gouvernance) :")
        for r in picked:
            print(f"- id: {r['id']}\n  status: CANDIDATE\n"
                  f"  cluster: {r['cluster']}")
    print("\n⚠️ CANDIDAT ≠ PREUVE : la confirmation juge (le slot scientifique).")
    return 0


def cmd_status(a) -> int:
    import shutil
    runs = sorted(RUNS.glob("*/manifest.json")) if RUNS.exists() else []
    print(f"{len(runs)} run(s) :")
    for m in runs:
        d = json.loads(m.read_text(encoding="utf-8"))
        print(f"  {d.get('run_id')} [{d.get('kind')}] spec {d.get('spec_sha')} "
              f"· git {d.get('git_sha')} · snapshot {d.get('snapshot')}")
    return 0


def cmd_portfolio(a) -> int:
    from scripts.portfolio_runner import cli_portfolio
    return cli_portfolio(a)


def cmd_forward(a) -> int:
    """La 3e étape du protocole : la maturation des confirmés (PAPER)."""
    from scripts import research_forward
    if a.collect:
        ids = [a.id] if a.id else research_forward.confirmed_runs()
        for rid in ids:
            r = research_forward.collect(rid, db_path=Path(a.db))
            print(f"[forward] {rid} : {r['collected']} nouvel(s) event(s) · "
                  f"total {r.get('journal_total', '?')}")
        return 0
    ids = [a.id] if a.id else research_forward.confirmed_runs()
    for rid in ids:
        s = research_forward.status(rid, db_path=Path(a.db))
        m = s["maturation"]
        tr = s["trades_closed"]
        line = (f"{rid} : {s['events_journaled']} events · "
                f"{tr['n']} trades fermés")
        if tr["mean"] is not None:
            line += f" · mean {tr['mean']:+.3f} %/trade · WR {tr['wr']:.1f} %"
            if s["wallet"]:
                w = s["wallet"]
                line += (f" · wallet ${w['solde']:.2f} (DD "
                         f"{w['max_dd_pct']:.2f} %, liq {w['liqs']})")
        line += (f" · maturation {m['days']:.1f}/{m['days_required']:.0f} j · "
                 f"{'READY pour review' if m['ready'] else 'en cours'}")
        print(line)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d1 = sub.add_parser("discovery")
    d1.add_argument("--spec", required=True)
    d1.add_argument("--db", default=str(KDB))
    d2 = sub.add_parser("confirm")
    d2.add_argument("--spec", required=True)
    d2.add_argument("--db", default=str(KDB))
    d3 = sub.add_parser("compare")
    d3.add_argument("ids", nargs="+")
    gr = sub.add_parser("grind")
    gr.add_argument("--queue", default=str(ROOT / "research" / "queue"))
    gr.add_argument("--db", default=str(KDB))
    sel = sub.add_parser("select")
    sel.add_argument("--per-cluster", type=int, default=2)
    sub.add_parser("status")
    pf = sub.add_parser("portfolio",
                        help="le wallet 100 $ d'un run (couche portefeuille)")
    pf.add_argument("--id", required=True)
    pf.add_argument("--capital", type=float, default=100.0)
    pf.add_argument("--cap-pct", type=float, default=1.0,
                    help="marge max %% de l'équité par trade (défaut 1)")
    pf.add_argument("--lev", type=float, default=1.0)
    pf.add_argument("--view", choices=["train", "validation"], default=None)
    pf.add_argument("--baseline", action="store_true",
                    help="baseline equal-weight long-and-hold uniquement")
    pf.add_argument("--db", default=str(KDB))
    fw = sub.add_parser("forward",
                        help="la maturation des confirmés (collect/status)")
    fw.add_argument("--collect", action="store_true")
    fw.add_argument("--id", default=None)
    fw.add_argument("--db", default=str(KDB))
    a = ap.parse_args()
    return {"discovery": cmd_discovery, "confirm": cmd_confirm,
            "compare": cmd_compare, "status": cmd_status,
            "grind": cmd_grind, "select": cmd_select,
            "portfolio": cmd_portfolio, "forward": cmd_forward}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
