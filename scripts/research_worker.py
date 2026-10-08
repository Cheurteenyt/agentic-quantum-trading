#!/usr/bin/env python3
"""LE RESEARCH WORKER — le processus durable de recherche (PR-158).

États : RUNNING → WAITING_RESOURCE → DONE / DONE_WITH_ERRORS / STOPPED
Sécurités :
  - singleton : verrou OS (flock) — deux workers ne peuvent pas coexister
  - checkpoint ATOMIQUE : tmp + fsync + rename (jamais de JSON tronqué)
  - checkpoint COMPLET en WAITING_RESOURCE (jamais de perte de progression)
  - spec_sha comparé au skip (une spec modifiée est re-mesurée)
  - retry CLASSIFIÉ : PERMANENT (spec invalide) vs RETRYABLE (I/O, DB)
  - exit codes : 0 = DONE, 1 = DONE_WITH_ERRORS/STOPPED, 42 = WAITING_RESOURCE
  - SIGTERM/SIGINT : status STOPPED (jamais DONE)
  - ledger idempotent : la dédup est dans lab_ledger.cmd_log (même code,
    mêmes données, même verdict déjà logué = NO-OP) — pas ici
  - heartbeat THREAD (30 s, indépendant de run_discovery) — une discovery
    longue ne laisse plus le lease devenir stale
  - identité de campagne = (engine_sha, db_snapshot, queue_sha) :
    engine_sha = hash des MODULES DE MESURE (pas le git grossier — un commit
    docs/worker ne réinitialise pas la campagne, un fix moteur oui)
  - checkpoint schema_version=2 : un checkpoint legacy est ARCHIVÉ et
    migré explicitement (jamais de tolérance silencieuse)
  - arbre sale sur les modules de mesure = refus de démarrer (fail-closed)

Usage :
    python3 scripts/research_worker.py --run --queue research/queue/bonsai
    python3 scripts/research_worker.py --status
    python3 scripts/research_worker.py --reset
"""
from __future__ import annotations

import ast
import fcntl
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scripts.label_matrix import dataset_window_sha  # noqa: E402 (P0-③)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUNTIME = ROOT / "research" / "runtime"
ARCHIVE = RUNTIME / "archive"
CHECKPOINT = RUNTIME / "grind_checkpoint.json"
LEASE = RUNTIME / "worker.json"
LOCK = RUNTIME / "worker.lock"
HEARTBEAT_INTERVAL = 30
MAX_RETRIES = 3
LEASE_TTL_S = 150
SCHEMA_VERSION = 2

# PR-161 : l'identité de campagne est le MOTEUR DE MESURE, pas git entier.
# Ces fichiers définissent ce qu'une discovery MESURE — leur changement
# invalide les résultats (leçon v14) ; un commit docs/worker non.
#
# P1 (audit 2026-10-08) : la liste était ÉCRITE À LA MAIN et elle était
# INCOMPLÈTE. `ENGINE_FILES` couvrait 4 fichiers alors que la clôture
# transitive réelle en compte 18. Deux modules du cœur scientifique étaient
# ABSENTS : `aster_indicators.py` (importé au niveau module par
# research_runner:56, il fournit `volume_z` — une des features) et
# `research_os.py` (importé au niveau module :91). Conséquence directe :
#
#     aster_indicators.py modifié   →   mesure différente
#                                   →   engine_sha IDENTIQUE
#                                   →   la spec DONE n'est PAS rejouée
#
# C'est précisément ce que l'identité de campagne doit empêcher.
#
# On ne corrige pas en ajoutant 2 lignes à la main : la main ne couvre
# pas, elle sous-estime par construction (le prochain import ajouté
# silencieusement n'entre pas dans la liste). `measurement_files()` calcule
# la CLÔTURE TRANSITIVE des imports, et les tests exigent que tout module
# atteignable soit soit haché, soit explicitement exclu.
MEASUREMENT_ROOTS = (
    "research_runner.py",   # l'orchestrateur : découverte + confirmation
    "label_matrix.py",      # event_study : la mesure
    "universe.py",          # fenêtre tradable (lazy import, cycle évité)
    "funding_series.py",    # funding as-of (lazy import)
    "aster_indicators.py",  # volume_z : une des features
    "research_os.py",       # contrat d'univers, DataScope
)

# Sorties de la clôture, et POURQUOI. Toute exclusion doit se défendre :
# l'exclusion d'un module de mesure est un trou silencieux.
NOT_MEASUREMENT = {
    # CLI de confirmation, importé tardivement par research_runner pour
    # éviter un cycle. Il ne change pas ce qu'une DISCOVERY mesure — mais
    # le dire « ne change pas ce qu'une discovery mesure » serait faux
    # pour la confirmation : `portfolio_sim` (dans la clôture) calcule
    # lui aussi, donc la confirmation reste couverte.
    "scripts/portfolio_runner.py",
    # le worker lui-même
    "scripts/research_worker.py",
}


def _imports_de(path: Path) -> set[str]:
    """Modules importés par `path`, au niveau module ET en local.

    Les imports locaux (dans une fonction) comptent : `research_runner`
    importe `universe` et `funding_series` ainsi, pour casser un cycle.
    Ne les ignorer laisserait exactement le trou qu'on veut fermer.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return set()
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            # les imports relatifs ne sont pas résolvables sans le module
            if n.level == 0 and n.module:
                out.add(n.module)
    return out


def _resoudre(mod: str) -> Path | None:
    """`scripts.<a>.<b>` ou `<a>.<b>` -> fichier sous scripts/."""
    parts = mod.split(".")
    for prefix in (("scripts",), ()):
        cand = ROOT.joinpath(*prefix, *parts).with_suffix(".py")
        if cand.exists():
            return cand
        pkg = ROOT.joinpath(*prefix, *parts) / "__init__.py"
        if pkg.exists():
            return pkg
    return None


def measurement_files() -> tuple[Path, ...]:
    """Clôture transitive des modules de mesure, DÉTERMINISTE.

    Triée par chemin pour que le sha ne dépende pas de l'ordre de
    découverte (donc du système de fichiers) : deux exécutions sur le même
    contenu donnent le même sha, sur n'importe quelle machine.
    """
    vus: set[Path] = set()

    def promener(p: Path) -> None:
        if p in vus:
            return
        vus.add(p)
        for mod in sorted(_imports_de(p)):
            cible = _resoudre(mod)
            if cible is None:
                continue
            rel = str(cible.relative_to(ROOT))
            if rel in NOT_MEASUREMENT:
                continue
            promener(cible)

    for nom in MEASUREMENT_ROOTS:
        racine = ROOT / "scripts" / nom
        if racine.exists():
            promener(racine)
    return tuple(sorted(vus, key=lambda p: str(p.relative_to(ROOT))))


ENGINE_FILES = measurement_files()


# ─── L'IDENTITÉ D'EXÉCUTION ────────────────────────────────────────────────
# L'audit du 2026-10-08 (action 5) : `engine_sha` seul ne suffit pas à dire
# « ce résultat est le même ». Le hash du moteur couvre les modules de
# mesure, mais deux autres choses peuvent changer la MESURE sans le
# changer :
#
#   - les SEUILS du protocole (`active.yaml` peut changer un seuil sous le
#     même `protocol_id` — d'où `protocol_sha`, PR-150) ;
#   - l'UNIVERS (`univ10.yaml` modifié garde son nom — d'où `universe_sha`) ;
#   - les VERSIONS des bibliothèques qui font les calculs (un patch numpy
#     change un quantile au 16ᵉ chiffre, donc un t au 3ᵉ) ;
#   - la SPEC elle-même.
#
# `execution_identity()` les compose en UN sha. C'est cet identifiant, et
# non `engine_sha`, qui doit autoriser un `skip`.
#
# Ce qui n'entre PAS, et doit donc pouvoir changer sans invalider :
#   - la documentation ;
#   - ce fichier (le worker) ;
#   - la configuration de CI.
#
# Une règle qui n'est pas testée n'est pas une règle : `TestMatriceDIdentite`
# modifie chaque entrée, une par une, et exige que l'identité change — et
# exige l'inverse pour les trois éléments hors périmètre. C'est ce seul
# test qui vaut plus que des dizaines de tests unitaires isolés.
EXECUTION_IDENTITY_PARTS = (
    "engine", "spec", "universe", "protocol", "db_snapshot",
    "deps", "git",
)


def execution_identity(engine_sha: str, *, spec_sha: str = "",
                       universe_sha: str = "", protocol_sha: str = "",
                       db_snapshot: str = "", deps_sha: str = "",
                       git_sha: str = "") -> str:
    """SHA256 du CANONICAL JSON des composantes d'exécution.

    Volontairement une fonction PURE et testable : l'oracle de matrice
    l'appelle directement avec des valeurs connues, sans base, sans git,
    sans réseau. C'est ce qui permet d'affirmer que chaque composante
    compte au lieu de le supposer.

    `engine_sha` seul (le cas d'avant ce PR) est conservé comme
    composante ET comme sous-clé : un run ancien reste comparable.
    """
    canonique = json.dumps(
        {
            "engine": engine_sha,
            "spec": spec_sha,
            "universe": universe_sha,
            "protocol": protocol_sha,
            "db_snapshot": db_snapshot,
            "deps": deps_sha,
            "git": git_sha,
        },
        sort_keys=True,          # l'ordre des clés ne doit pas compter
        separators=(",", ":"),   # pas d'espace : le canonique est stable
    )
    return hashlib.sha256(canonique.encode("utf-8")).hexdigest()[:16]


def deps_sha() -> str:
    """Le sha des VERSIONS des bibliothèques qui font les calculs.

    Un patch de numpy/pandas change un quantile au 16ᵉ chiffre, donc un
    t-statistique au 3ᵉ, donc un verdict. Deux runs « identiques » sur
    deux patchs de numpy ne sont pas le même résultat.

    Stdlib seule : `importlib.metadata.version` lit la distribution
    INSTALLÉE. Une version absente contribute une chaîne vide, pas une
    exception — l'absence de numpy serait un autre problème, signalé
    ailleurs, et ne doit pas faire tomber l'identité.
    """
    from importlib.metadata import PackageNotFoundError, version
    parts = []
    for dist in ("numpy", "pandas", "scipy", "pyarrow"):
        try:
            parts.append(f"{dist}={version(dist)}")
        except PackageNotFoundError:
            parts.append(f"{dist}=absent")
    return "|".join(parts)


def _execution_identity_for(engine_sha: str, spec_sha: str = "",
                            db_snapshot: str = "", git_sha: str = "") -> str:
    """L'identité d'exécution complète, lue sur disque.

    `protocol_sha` est lu ici (et non passé) parce qu'il décrit un fichier
    du dépôt, pas un paramètre du run : l'oublier serait exactement le trou
    que l'oracle de matrice ferme — un seuil de protocole peut changer sous
    le même `protocol_id`.

    `universe_sha` est laissé vide ici : il dépend de l'univers de la spec,
    donc c'est à l'appelant de le passer (il a la spec en main). Le canal
    reste ouvert et l'oracle le vérifie.
    """
    proto = ""
    try:
        from scripts.research_runner import protocol_sha as _proto
        proto = _proto()
    except (OSError, ImportError, ValueError):
        proto = ""
    return execution_identity(
        engine_sha, spec_sha=spec_sha, db_snapshot=db_snapshot,
        protocol_sha=proto, deps_sha=deps_sha(), git_sha=git_sha or "",
    )

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_WAITING_RESOURCE = 42

# les erreurs PERMANENTES (spec invalide, code bug) vs RETRYABLES (I/O, DB)
_PERMANENT_ERRORS = (ValueError, KeyError, TypeError, NameError,
                     AttributeError, json.JSONDecodeError)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, data: dict) -> None:
    """Écriture ATOMIQUE : tmp unique + flush + fsync + rename.
    Le tmp est UNIQUE par appel (PR-161) : le thread de heartbeat écrit le
    lease en parallèle du thread principal — un tmp partagé se corromperait."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(
        f".tmp{os.getpid()}.{time.monotonic_ns()}")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=1))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _load_json(path: Path) -> dict:
    """Lecture FAIL-CLOSED : un JSON corrompu lève (pas de {} silencieux)."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"checkpoint corrompu : {path} ({exc}) — "
                           "supprime-le manuellement ou utilise --reset") from exc


def _heartbeat(checkpoint: dict) -> None:
    """Deux écritures atomiques INDÉPENDANTES (checkpoint puis lease) —
    pas une transaction : un crash entre les deux laisse un lease frais
    avec un checkpoint légèrement plus vieux, ce qui est bénin."""
    _atomic_write_json(CHECKPOINT, checkpoint)
    _atomic_write_json(LEASE, {
        "pid": os.getpid(),
        "heartbeat_at": _now_iso(),
        "status": checkpoint.get("status", "RUNNING"),
    })


def _lease_heartbeat() -> None:
    """Le heartbeat du LEASE seul (entre les specs, pas de checkpoint)."""
    _atomic_write_json(LEASE, {
        "pid": os.getpid(),
        "heartbeat_at": _now_iso(),
        "status": "RUNNING",
    })


def _queue_sha(queue_dir: Path) -> str:
    """Le hash de la queue LIÉ AUX CHEMINS (PR-161) — relative_path + NUL +
    bytes : deux files de noms différents avec le même contenu ne collodent
    plus (l'ancien hash ne scellait que les bytes). PR-163 : même filtre
    done/ que _load_specs — le sel et le manifeste décrivent le MÊME
    ensemble (déplacer une spec en done/ ne changeait que l'un des deux)."""
    h = hashlib.sha256()
    for f in sorted(queue_dir.rglob("*")):
        if (f.is_file() and f.suffix in (".yaml", ".yml", ".json")
                and "done" not in f.parts):
            h.update(str(f.relative_to(queue_dir)).encode())
            h.update(b"\0")
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


def _engine_sha() -> str:
    """Le hash des MODULES DE MESURE (PR-161) — lié aux chemins.
    C'est l'identité moteur de la campagne : un fix research_runner.py
    réinitialise honnêtement, un commit de docs/worker non."""
    h = hashlib.sha256()
    for p in ENGINE_FILES:
        h.update(str(p.relative_to(ROOT)).encode())
        h.update(b"\0")
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _engine_sha_at(commit: str) -> str | None:
    """Le sha moteur TEL QU'IL ÉTAIT au commit (PR-162) — `git show` des
    modules de mesure : la migration peut PROUVER (ou réfuter) que le
    moteur du checkpoint ère PR-160 est celui d'aujourd'hui.
    None = invérifiable (commit inconnu, fichier absent, git en erreur)."""
    h = hashlib.sha256()
    for p in ENGINE_FILES:
        rel = str(p.relative_to(ROOT))
        proc = subprocess.run(["git", "show", f"{commit}:{rel}"],
                              capture_output=True, cwd=ROOT)
        if proc.returncode != 0:
            return None
        h.update(rel.encode())
        h.update(b"\0")
        h.update(proc.stdout)
    return h.hexdigest()[:16]


def _git_engine_dirty() -> bool:
    """True si un MODULE DE MESURE tracké est modifié non commité —
    le code exécuté ne serait décrit par aucun sha (fail-closed, même
    doctrine que cmd_confirm). Les docs/ledger/studies ne comptent pas :
    ils ne changent pas ce qu'une discovery mesure. PR-162 : une erreur
    git (repo corrompu, git absent) est aussi un refus — on ne peut pas
    PROUVER l'arbre propre, donc on ne démarre pas."""
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--",
         *[str(p.relative_to(ROOT)) for p in ENGINE_FILES]],
        capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        return True
    return any(not l.startswith("??") for l in proc.stdout.splitlines())


def _is_terminal(prev: dict, spec_sha: str, dws: str | None) -> bool:
    """LA définition unique de « terminal » (PR-161, P0-③ audit 2026-10-08) :
    l'item porte le même spec_sha, le MÊME état des données sous sa
    fenêtre scientifique (dataset_window_sha) ET est DONE ou
    FAILED_PERMANENT.
    - item sans dataset_window_sha (ère pré-P0-③) : PAS terminal — il est
      re-mesuré une fois puis scellé (fail-closed, comme l'item PR-160
      sans spec_sha) ;
    - dws incalculable (None) : PAS terminal — on ne peut pas prouver que
      la mesure DONE décrit les données d'aujourd'hui.
    Un FAILED_PERMANENT sans spec_sha (item legacy) n'est PAS terminal."""
    return (prev.get("spec_sha") == spec_sha
            and dws is not None
            and prev.get("dataset_window_sha") == dws
            and prev.get("state") in ("DONE", "FAILED_PERMANENT"))


def _spec_validation_end(path: Path) -> int | None:
    """P0-③ : validation_end de la spec (int ms epoch) — parse TOLÉRANT.
    Au SKIP la spec n'est pas encore passée par load_spec (elle n'est lue
    qu'après le garde ressource) et un fichier illisible ne doit pas
    casser la boucle : None = dws incalculable = pas de skip (fail-closed,
    le run normal classera la spec)."""
    try:
        spec = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        v = (spec.get("data") or {}).get("validation_end")
        return int(v) if v is not None else None
    except Exception:
        return None


def _dws_now(db_path: Path, v_end: int | None) -> str | None:
    """Le dataset_window_sha COURANT pour une fenêtre — None (non
    terminal, pas de skip) si la fenêtre est inconnue ou si la db est
    présente mais illisible (fail-closed)."""
    if v_end is None:
        return None
    try:
        return dataset_window_sha(db_path, v_end)
    except sqlite3.Error:
        return None


def _migrate_checkpoint(ck: dict, db_snap: str, engine_sha: str,
                        queue_sha: str) -> tuple[dict, str]:
    """La migration schema (PR-161) — JAMAIS de tolérance silencieuse.
    Retourne (checkpoint migré, note lisible).
    - legacy absolu (sans identité racine, pré-PR-160) : ARCHIVÉ, aucune
      progression transportée (on ne peut PAS vérifier la db d'origine)
    - ère PR-160 (identité racine, sans schema_version) : les items sont
      transportés SI la db correspond — le moteur n'a pas changé depuis
      (engine_sha adopté), la queue est re-scellée au nouvel algorithme"""
    if not ck:
        return ck, "première campagne"
    if ck.get("schema_version") == SCHEMA_VERSION:
        return ck, ""
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    tag = ck.get("job_id") or f"legacy-{int(time.time())}"
    arch = ARCHIVE / f"grind_checkpoint-{tag}.json"
    _atomic_write_json(arch, ck)
    if ck.get("db_snapshot"):
        # PR-162 : le transport n'est autorisé que si le moteur du
        # checkpoint est PROUVÉ identique à celui d'aujourd'hui — le
        # checkpoint ère PR-160 ne stockait pas d'engine_sha, on le
        # reconstruit depuis son git_sha. Invérifiable ou différent =
        # campagne propre (les résultats d'un autre moteur ne méritent
        # pas de skip).
        old_engine = (_engine_sha_at(ck["git_sha"])
                      if ck.get("git_sha") else None)
        if old_engine is None:
            return {}, ("checkpoint ère PR-160 : moteur d'origine "
                        f"invérifiable (git {ck.get('git_sha')}) — "
                        f"archivé → {arch.name}, campagne propre")
        if old_engine != engine_sha:
            return {}, ("checkpoint ère PR-160 mais le MOTEUR a changé "
                        f"depuis {ck['git_sha']} ({old_engine} → "
                        f"{engine_sha}) — archivé → {arch.name}, "
                        "campagne propre")
        carried = len(ck.get("items", {}))
        ck["schema_version"] = SCHEMA_VERSION
        ck["engine_sha"] = engine_sha
        ck["queue_sha"] = queue_sha
        for it in ck.get("items", {}).values():
            it["migrated"] = True
        # PR-163 (P0 du bug-hunter) : la db dérive en CONTINU (le nightly
        # et les collecteurs appendent des barres) — ce n'est plus un
        # critère de refus, seulement une note. Les fenêtres de mesure des
        # discovery sont HISTORIQUES (train/validation figés) : un append
        # en queue de db ne les touche pas. Un REMPLACEMENT réel de la db
        # reste un geste opérateur (--reset).
        drift = ""
        if ck.get("db_snapshot") != db_snap:
            drift = (f" · db dérivée depuis ({ck['db_snapshot']} → "
                     f"{db_snap}) — append en continu, fenêtres "
                     "historiques inchangées")
            ck["db_snapshot"] = db_snap
        return ck, (f"migration ère PR-160 : {carried} item(s) transportés "
                    f"(moteur prouvé identique à {ck['git_sha']}){drift}, "
                    f"ancien checkpoint archivé → {arch.name}")
    return {}, ("checkpoint LEGACY sans identité racine (pré-PR-160) — "
                f"archivé → {arch.name}, campagne propre")


def _reconcile_identity(ck: dict, db_snap: str, engine_sha: str,
                        queue_sha: str) -> tuple[dict, list[str]]:
    """La comparaison d'identité schema-2 (PR-161) :
    - moteur changé → campagne RÉINITIALISÉE (archivée) — les résultats
      ne mesurent plus ce que le code mesure maintenant
    - db dérivée → items CONSERVÉS avec note (PR-163, P0 du bug-hunter :
      la db est appendée en continu, les fenêtres de mesure sont
      historiques ; un remplacement réel reste un geste --reset)
    - queue changée → items CONSERVÉS (le spec_sha par item protège
      le contenu ; l'ensemble de la queue a juste grossi/rétréci)"""
    notes: list[str] = []
    if not ck:
        return ck, notes
    if ck.get("engine_sha") != engine_sha:
        ARCHIVE.mkdir(parents=True, exist_ok=True)
        tag = ck.get("job_id") or f"reset-{int(time.time())}"
        arch = ARCHIVE / f"grind_checkpoint-{tag}.json"
        _atomic_write_json(arch, ck)
        notes.append("IDENTITÉ DE CAMPAGNE CHANGÉE (moteur "
                     f"{ck.get('engine_sha')} → {engine_sha}) — "
                     "réinitialisée, ancien checkpoint archivé → "
                     f"{arch.name}")
        return {}, notes
    if ck.get("db_snapshot") != db_snap:
        notes.append(f"db a dérivé ({ck.get('db_snapshot')} → {db_snap}) "
                     "— items conservés (append en continu, fenêtres de "
                     "mesure historiques inchangées)")
        ck["db_snapshot"] = db_snap
    if ck.get("queue_sha") != queue_sha:
        notes.append(f"queue changée ({ck.get('queue_sha')} → {queue_sha}) "
                     "— items conservés (le spec_sha par item protège "
                     "le contenu)")
        ck["queue_sha"] = queue_sha
    return ck, notes


def _load_specs(queue_dir: Path) -> list[tuple[Path, str, str]]:
    """La liste matérialisée des specs — (chemin, spec_id, sha) figée au
    démarrage : la campagne exécute exactement ce manifest. Une collision
    de spec_id (même stem dans deux sous-dossiers) = REFUS fail-closed."""
    files = [p for p in sorted(queue_dir.rglob("*"))
             if p.is_file() and p.suffix in (".yaml", ".yml", ".json")
             and "done" not in p.parts]
    seen: dict[str, Path] = {}
    out: list[tuple[Path, str, str]] = []
    for f in files:
        sid = f.stem
        if sid in seen:
            raise ValueError(
                f"collision de spec_id : {seen[sid]} et {f} donnent tous "
                f"deux '{sid}' — renomme l'un des deux")
        seen[sid] = f
        out.append((f, sid, hashlib.sha256(f.read_bytes()).hexdigest()[:16]))
    return out


def _status_counts(items: dict, manifest: list | None = None,
                   queue_total: int = 0) -> dict:
    """Les métriques DÉRIVÉES de items (PR-161) — PR-163 : quand le
    manifeste scellé existe, done/remaining ne comptent que les specs qui
    y sont ENCORE (une spec supprimée de la queue ne masque plus une
    remaining, un item DONE orphelin ne masque plus une spec restante) ;
    le spec_sha du manifeste doit aussi correspondre (spec modifiée =
    à re-mesurer)."""
    terminal = ("DONE", "FAILED_PERMANENT")

    if manifest:
        ids = [m.get("id") for m in manifest]
        shas = {m.get("id"): m.get("sha") for m in manifest}
        # P0-③ : le dws attendu par le manifeste — un item DONE dont la
        # fenêtre de données a changé depuis sa mesure n'est plus done
        # (dws=None au manifeste = incalculable, aucune exigence ajoutée)
        dwss = {m.get("id"): m.get("dws") for m in manifest}

        def _terminal_ok(iid: str) -> bool:
            it = items.get(iid) or {}
            return (it.get("state") in terminal
                    and it.get("spec_sha") == shas.get(iid)
                    and (dwss.get(iid) is None
                         or it.get("dataset_window_sha") == dwss.get(iid)))

        done = sum(1 for i in ids if (items.get(i) or {}).get("state")
                   == "DONE" and items[i].get("spec_sha") == shas.get(i)
                   and (dwss.get(i) is None
                        or items[i].get("dataset_window_sha") == dwss.get(i)))
        permanent = sum(1 for i in ids
                        if (items.get(i) or {}).get("state")
                        == "FAILED_PERMANENT"
                        and items[i].get("spec_sha") == shas.get(i)
                        and (dwss.get(i) is None
                             or items[i].get("dataset_window_sha")
                             == dwss.get(i)))
        remaining = sum(1 for i in ids if not _terminal_ok(i))
    else:
        done = sum(1 for v in items.values() if v.get("state") == "DONE")
        permanent = sum(1 for v in items.values()
                        if v.get("state") == "FAILED_PERMANENT")
        remaining = max(0, queue_total - done - permanent)
    retryable = sum(1 for v in items.values()
                    if v.get("state") == "FAILED_RETRYABLE")
    return {"done": done, "failed_permanent": permanent,
            "failed_retryable": retryable, "remaining": remaining}


def _is_permanent_error(exc: Exception) -> bool:
    """№8 : la CLASSIFICATION — certaines erreurs ne serviront à rien de
    retenter (spec invalide, bug de code, YAML cassé)."""
    return isinstance(exc, _PERMANENT_ERRORS)


def run_worker(queue_dir: Path, db_path: Path = None) -> int:
    from scripts.research_runner import (
        load_spec, run_discovery, write_artifacts, _log_ledger,
        _passes, _resource_guard)

    db_path = db_path or ROOT / "data" / "warehouse" / "klines.db"
    pid = os.getpid()

    from scripts import research_runner as _rr
    RUNTIME.mkdir(parents=True, exist_ok=True)
    lock_fh = open(LOCK, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("[worker] un autre worker est ACTIF — refus", flush=True)
        return EXIT_FAILED
    # PR-163 : worker.lock est gitigné — s'il a été recréé entre notre
    # open() et notre flock() (git clean, ménage), un 2e worker peut avoir
    # acquis le NOUVEL inode pendant que nous tenons l'ancien. On refuse
    # plutôt que de coexister (preuve bug-hunter : inodes 1125200 ≠ 1125201).
    try:
        if os.fstat(lock_fh.fileno()).st_ino != os.stat(LOCK).st_ino:
            print("[worker] REFUS : worker.lock a été recréé (inode "
                  "différent) — possible 2e worker", flush=True)
            lock_fh.close()
            return EXIT_FAILED
    except OSError:
        pass
    # PR-163 : le lease existe DÈS le flock — snapshot_id (hash de Go),
    # migration et _load_specs tournent AVANT la première heartbeat du
    # thread (+30 s) : sans ceci le watchdog pouvait couper bonsai dans
    # la fenêtre de démarrage
    try:
        _lease_heartbeat()
    except OSError:
        pass

    def _make_shutdown_handler(state: dict) -> callable:
        def handler(signum, frame):
            state["shutdown_requested"] = True
        return handler

    state: dict = {"shutdown_requested": False}
    signal.signal(signal.SIGTERM, _make_shutdown_handler(state))
    signal.signal(signal.SIGINT, _make_shutdown_handler(state))

    git_sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, cwd=ROOT).stdout.strip()
    db_snap = _rr.snapshot_id(db_path) if db_path.exists() else "unknown"
    queue_sha = _queue_sha(queue_dir)
    engine = _engine_sha()

    # PR-161 : un module de MESURE sale = le code exécuté n'est décrit par
    # aucun sha — refus fail-closed (même doctrine que cmd_confirm). Les
    # docs/ledger/studies sales ne bloquent pas : ils ne changent pas la mesure.
    if _git_engine_dirty():
        print("[worker] REFUS : un module de mesure est modifié non "
              "commité (research_runner/label_matrix/universe/"
              "funding_series) — committer d'abord", flush=True)
        lock_fh.close()
        return EXIT_FAILED

    ck = _load_json(CHECKPOINT)
    ck, note = _migrate_checkpoint(ck, db_snap, engine, queue_sha)
    if note:
        print(f"[worker] {note}", flush=True)
    ck, notes = _reconcile_identity(ck, db_snap, engine, queue_sha)
    for n in notes:
        print(f"[worker] {n}", flush=True)

    job_id = ck.get("job_id") or f"grind-{git_sha}-{int(time.time())}"

    # l'identité est SCELLÉE au checkpoint à chaque démarrage
    ck["job_id"] = job_id
    ck["git_sha"] = git_sha
    ck["engine_sha"] = engine
    # L'identité d'EXÉCUTION (audit 2026-10-08, action 5) : engine_sha seul
    # ne suffit pas à dire « ce résultat est le même ». Un seuil de
    # protocole peut changer sous le même protocol_id, un univers peut
    # changer sous le même nom, et un patch numpy décale un t-statistique.
    # Ces trois choses-là ne touchent aucun module de mesure — donc
    # engine_sha reste identique — alors que le résultat, si.
    ck["execution_identity"] = _execution_identity_for(
        engine, spec_sha="", db_snapshot=db_snap, git_sha=git_sha)
    ck["db_snapshot"] = db_snap
    ck["queue_sha"] = queue_sha
    ck["schema_version"] = SCHEMA_VERSION

    try:
        spec_tuples = _load_specs(queue_dir)
    except ValueError as exc:
        print(f"[worker] REFUS : {exc}", flush=True)
        lock_fh.close()
        return EXIT_FAILED
    if not spec_tuples:
        print("[worker] queue vide", flush=True)
        LEASE.unlink(missing_ok=True)
        lock_fh.close()
        return EXIT_OK

    items: dict[str, dict] = ck.get("items", {})
    candidates: list[str] = list(ck.get("candidates", []))

    # le MANIFEST de la campagne est scellé au checkpoint (auditable) —
    # la campagne exécute exactement cette liste matérialisée au démarrage.
    # P0-③ : le manifeste scelle AUSSI l'état des données sous la fenêtre
    # scientifique de chaque spec (dws), FIGÉ AU DÉMARRAGE — sémantique
    # « la campagne exécute exactement ce manifest ». Les specs qui
    # partagent la même validation_end partagent UN SEUL calcul (le hash
    # complet d'une fenêtre est coûteux : déduplication côté appelant,
    # dataset_window_sha est volontairement pure et sans cache). Une
    # correction qui arrive PENDANT la campagne sera détectée au prochain
    # démarrage (le manifeste est alors recalculé sur le nouvel état).
    dws_by_spec: dict[str, str | None] = {}
    dws_by_end: dict[int | None, str | None] = {}
    for mf, msid, msha in spec_tuples:
        v_end = _spec_validation_end(mf)
        if v_end not in dws_by_end:
            dws_by_end[v_end] = _dws_now(db_path, v_end)
        dws_by_spec[msid] = dws_by_end[v_end]
    ck["queue_total"] = len(spec_tuples)
    ck["manifest"] = [{"id": msid, "sha": msha, "dws": dws_by_spec[msid]}
                      for _, msid, msha in spec_tuples]

    print(f"[worker] job {job_id} · {len(spec_tuples)} specs · "
          f"{len(items)} déjà traitées · moteur {engine}", flush=True)

    exit_code = EXIT_OK
    had_errors = False

    # PR-161 : le heartbeat est un THREAD indépendant de la boucle —
    # run_discovery() peut durer des heures, le lease reste vivant
    hb_stop = threading.Event()

    def _hb_loop() -> None:
        while not hb_stop.wait(HEARTBEAT_INTERVAL):
            try:
                _lease_heartbeat()
            except Exception as exc:
                # PR-163 (P1 du bug-hunter) : une mort SILENCIEUSE du
                # heartbeat = lease stale = le watchdog arrête bonsai en
                # pleine discovery sans aucun signal. On marque la mort
                # DANS le lease (status HB_DEAD + erreur) et on sort.
                try:
                    _atomic_write_json(LEASE, {
                        "pid": os.getpid(),
                        "heartbeat_at": _now_iso(),
                        "status": "HB_DEAD",
                        "hb_error": f"{type(exc).__name__}: {exc}"})
                except OSError:
                    pass
                return

    hb_thread = threading.Thread(target=_hb_loop, daemon=True,
                                 name="lease-heartbeat")
    hb_thread.start()

    for f, spec_id, start_sha in spec_tuples:
        # №P1-2 : le SKIP compare le spec_sha — une spec MODIFIÉE sous le
        # même id est re-mesurée (l'ancien ne comparait que l'id)
        prev = items.get(spec_id, {})
        # P0-③ (audit 2026-10-08) : le spec_sha ne voit pas les DONNÉES —
        # une correction historique DANS la fenêtre scientifique d'une
        # spec DONE exige une re-mesure ; un append AU-DELÀ de
        # validation_end (l'actif continue d'exister) ne doit pas la
        # provoquer. Le dws est celui du manifeste (figé au démarrage de
        # campagne) ; None = incalculable = pas de skip (fail-closed).
        dws_now = dws_by_spec.get(spec_id)
        # PR-161 : FAILED_PERMANENT est VRAIMENT terminal — via _is_terminal
        # qui exige le spec_sha (l'item PR-160 ne le portait pas et était
        # donc re-joué à l'infini malgré le commentaire)
        if _is_terminal(prev, start_sha, dws_now):
            continue

        # №P1-1 : le garde-fou ressource RETENTE LA MÊME SPEC et le
        # checkpoint préserve les items (jamais de perte de progression)
        while True:
            ok_res, why_res = _resource_guard()
            if ok_res:
                break
            # PRÉSERVE les items — on ne construit pas un nouvel objet
            ck["status"] = "WAITING_RESOURCE"
            ck["current"] = spec_id
            ck["reason"] = why_res
            ck["heartbeat_at"] = _now_iso()
            _heartbeat(ck)
            print(f"[worker] WAITING_RESOURCE : {why_res} — "
                  "retry dans 60 s (la MÊME spec)", flush=True)
            time.sleep(60)
            if state.get("shutdown_requested"):
                break

        if state.get("shutdown_requested"):
            break

        print(f"[worker] {spec_id} — discovery", flush=True)

        retries = 0
        spec_sha = start_sha  # par défaut ; l'essai qui réussit le rescelle
        dws_exec = None  # P0-③ : le dws d'EXÉCUTION (scellé sur la spec exécutée)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # PR-162 : le sha EXÉCUTÉ fait foi — lecture, parse, puis
                # relecture de vérification : une spec modifiée pendant la
                # lecture annule l'essai (RETRYABLE, pas _PERMANENT) et la
                # prochaine tentative repart de zéro
                raw = f.read_bytes()
                spec = load_spec(f)
                if f.read_bytes() != raw:
                    raise RuntimeError(
                        "spec modifiée pendant la lecture — reprise")
                spec_sha = hashlib.sha256(raw).hexdigest()[:16]
                if spec_sha != start_sha:
                    print(f"[worker] {spec_id} : la spec a changé depuis le "
                          f"démarrage de campagne ({start_sha} → "
                          f"{spec_sha}) — le sha EXÉCUTÉ est scellé",
                          flush=True)
                if spec.get("id") != spec_id:
                    raise ValueError(
                        f"spec.id {spec.get('id')!r} ≠ nom de fichier "
                        f"{spec_id!r} — renommage ou collision")
                # P0-③ : le dws d'EXÉCUTION — scellé sur la spec exécutée
                # (miroir du « sha EXÉCUTÉ fait foi »), calculé PRÉ-mesure :
                # si une correction historique arrive PENDANT la mesure, le
                # dws scellé (pré) ≠ dws courant (post) → re-mesure
                # (fail-closed). None (spec mal typée / db illisible) =
                # item JAMAIS terminal.
                dws_exec = _dws_now(
                    db_path, int(spec["data"]["validation_end"]))
                res = run_discovery(spec, db_path=db_path)
                verdict = res.get("verdict", "?")
                n = res.get("n", 0)
                mean = res.get("mean", float("nan"))
                print(f"[worker] {spec_id} : {verdict} · n {n} · "
                      f"mean {mean:.3f}", flush=True)

                if _passes(res, spec):
                    write_artifacts(spec_id, spec, res, "discovery",
                                    db_path=db_path)
                    # la dédup du ledger est dans lab_ledger.cmd_log (PR-161)
                    _log_ledger(spec, verdict, "discovery",
                                str(ROOT / "research" / "runs" / spec_id /
                                    "report.md"),
                                snapshot=res.get("snapshot"))
                    if spec_id not in candidates:
                        candidates.append(spec_id)
                    print(f"[worker]   → CANDIDATE", flush=True)
                items[spec_id] = {
                    "state": "DONE", "verdict": verdict,
                    "spec_sha": spec_sha, "git_sha": git_sha,
                    "dataset_window_sha": dws_exec}
                break
            except Exception as exc:
                retries = attempt
                err_type = type(exc).__name__
                print(f"[worker] {spec_id} : tentative {attempt}/"
                      f"{MAX_RETRIES} échouée ({err_type}: {exc})", flush=True)
                if attempt < MAX_RETRIES:
                    time.sleep(10 * attempt)
                elif _is_permanent_error(exc):
                    # №P1-8 : les erreurs PERMANENTES sont FAILED_PERMANENT —
                    # le spec_sha+git_sha+dataset_window_sha rendent la
                    # terminalité RÉELLE
                    items[spec_id] = {
                        "state": "FAILED_PERMANENT", "spec_sha": spec_sha,
                        "git_sha": git_sha, "dataset_window_sha": dws_exec,
                        "error": f"{err_type}: {exc}", "attempt": attempt,
                        "timestamp": _now_iso()}
                    had_errors = True
                    print(f"[worker] {spec_id} : FAILED_PERMANENT", flush=True)
                else:
                    # les erreurs RETRYABLES ne sont PAS terminales —
                    # retraitées au prochain lancement
                    items[spec_id] = {
                        "state": "FAILED_RETRYABLE", "spec_sha": spec_sha,
                        "git_sha": git_sha, "dataset_window_sha": dws_exec,
                        "error": f"{err_type}: {exc}", "attempt": attempt,
                        "timestamp": _now_iso()}
                    had_errors = True
                    print(f"[worker] {spec_id} : FAILED_RETRYABLE",
                          flush=True)

        _lease_heartbeat()
        ck["items"] = items
        ck["candidates"] = candidates
        ck["status"] = "RUNNING"
        ck["heartbeat_at"] = _now_iso()
        _heartbeat(ck)

    # PR-161 : le thread de heartbeat s'arrête AVANT les écritures finales
    # (aucune course entre la fin de campagne et le lease)
    hb_stop.set()
    hb_thread.join(timeout=2)

    # ── №P1-5/№6 + FIX v21 (PR-160 №5) : le status final dépend de TOUTES
    # les erreurs — FAILED_PERMANENT produit aussi DONE_WITH_ERRORS
    retryable = [k for k, v in items.items()
                 if v.get("state") == "FAILED_RETRYABLE"]
    permanent = [k for k, v in items.items()
                 if v.get("state") == "FAILED_PERMANENT"]
    if state.get("shutdown_requested"):
        final_status = "STOPPED"
        exit_code = EXIT_FAILED
    elif retryable or permanent:
        final_status = "DONE_WITH_ERRORS"
        exit_code = EXIT_FAILED
    else:
        final_status = "DONE"
        exit_code = EXIT_OK

    ck["items"] = items
    ck["candidates"] = candidates
    ck["status"] = final_status
    ck["failed_retryable"] = retryable
    ck["heartbeat_at"] = _now_iso()
    ck["completed_at"] = _now_iso()
    _heartbeat(ck)
    print(f"[worker] {final_status} : {len(candidates)} candidat(s) · "
          f"{len(retryable)} retryable(s) · {len(permanent)} permanent(s) "
          f"— exit {exit_code}", flush=True)

    LEASE.unlink(missing_ok=True)
    lock_fh.close()
    return exit_code


def _is_lease_stale() -> bool:
    # PR-163 : un lease corrompu = aucun heartbeat prouvable = stale
    try:
        lease = _load_json(LEASE)
    except RuntimeError:
        return True
    hb = lease.get("heartbeat_at")
    if not hb:
        return True
    try:
        hb_dt = datetime.fromisoformat(hb.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - hb_dt).total_seconds()
        return age > LEASE_TTL_S
    except ValueError:
        return True


def status() -> int:
    ck = _load_json(CHECKPOINT)
    # PR-163 : un lease corrompu ne doit pas tuer --status (traceback)
    try:
        lease = _load_json(LEASE)
    except RuntimeError:
        lease = {}
    if not ck:
        print(json.dumps({"status": "NEVER_RUN"}))
        return 0
    pid = lease.get("pid")
    alive = False
    if pid:
        # PR-163 : comme le watchdog — le PID doit être VIVANT ET porter
        # research_worker.py comme BASENAME d'un argument (un PID recyclé
        # ne ment plus ; une sous-chaîne confondrait test_research_worker.py)
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                argv = fh.read().split(b"\0")
            alive = any(a.rsplit(b"/", 1)[-1] == b"research_worker.py"
                        for a in argv)
        except OSError:
            alive = False
    stale = _is_lease_stale()
    counts = _status_counts(
        ck.get("items", {}), ck.get("manifest"),
        ck.get("queue_total", len(ck.get("items", {}))))
    print(json.dumps({
        "job_id": ck.get("job_id"), "git_sha": ck.get("git_sha"),
        "engine_sha": ck.get("engine_sha"),
        "schema_version": ck.get("schema_version"),
        "status": ck.get("status"), "worker_pid": pid,
        "worker_alive": alive, "lease_stale": stale,
        "hb_dead": lease.get("status") == "HB_DEAD",
        **counts,
        "candidates": ck.get("candidates", []),
        "heartbeat": lease.get("heartbeat_at", ck.get("heartbeat_at")),
    }, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split(chr(10))[0])
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--queue",
                    default=str(ROOT / "research" / "queue" / "bonsai"))
    ap.add_argument("--db",
                    default=str(ROOT / "data" / "warehouse" / "klines.db"))
    a = ap.parse_args()
    if a.reset:
        # №P2 : --reset utilise le MÊME verrou que le worker
        lock_fh = open(LOCK, "w")
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("[worker] refus : un worker est ACTIF")
            return EXIT_FAILED
        if CHECKPOINT.exists():
            CHECKPOINT.unlink()
        if LEASE.exists():
            LEASE.unlink()
        print("checkpoint + lease effacés")
        lock_fh.close()
        return EXIT_OK
    if a.status:
        return status()
    if a.run:
        return run_worker(Path(a.queue), Path(a.db))
    print("choisis --run, --status ou --reset")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
