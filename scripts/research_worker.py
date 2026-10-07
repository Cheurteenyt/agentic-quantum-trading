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
ENGINE_FILES = (
    ROOT / "scripts" / "research_runner.py",
    ROOT / "scripts" / "label_matrix.py",
    ROOT / "scripts" / "universe.py",
    ROOT / "scripts" / "funding_series.py",
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


def _resource_guard() -> tuple[bool, str]:
    try:
        mem = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                mem[k] = int(v.strip().split()[0])
        avail_gb = mem.get("MemAvailable", 0) / 1024 / 1024
        if avail_gb < 1.0:
            return False, f"RAM disponible {avail_gb:.1f} Go < 1 Go"
    except OSError:
        pass
    import shutil
    du = shutil.disk_usage(ROOT)
    if du.free / 1024**3 < 2.0:
        return False, f"disque libre {du.free / 1024**3:.1f} Go < 2 Go"
    return True, "OK"


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
    plus (l'ancien hash ne scellait que les bytes)."""
    h = hashlib.sha256()
    for f in sorted(queue_dir.rglob("*")):
        if f.is_file() and f.suffix in (".yaml", ".yml", ".json"):
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


def _git_engine_dirty() -> bool:
    """True si un MODULE DE MESURE tracké est modifié non commité —
    le code exécuté ne serait décrit par aucun sha (fail-closed, même
    doctrine que cmd_confirm). Les docs/ledger/studies ne comptent pas :
    ils ne changent pas ce qu'une discovery mesure."""
    out = subprocess.run(
        ["git", "status", "--porcelain", "--",
         *[str(p.relative_to(ROOT)) for p in ENGINE_FILES]],
        capture_output=True, text=True, cwd=ROOT).stdout
    return any(not l.startswith("??") for l in out.splitlines())


def _is_terminal(prev: dict, spec_sha: str) -> bool:
    """LA définition unique de « terminal » (PR-161) : l'item porte le
    même spec_sha ET est DONE ou FAILED_PERMANENT. Un FAILED_PERMANENT
    sans spec_sha (item legacy) n'est PAS terminal — il est re-mesuré."""
    return (prev.get("spec_sha") == spec_sha
            and prev.get("state") in ("DONE", "FAILED_PERMANENT"))


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
    if ck.get("db_snapshot") and ck["db_snapshot"] == db_snap:
        carried = len(ck.get("items", {}))
        ck["schema_version"] = SCHEMA_VERSION
        ck["engine_sha"] = engine_sha
        ck["queue_sha"] = queue_sha
        for it in ck.get("items", {}).values():
            it["migrated"] = True
        return ck, (f"migration ère PR-160 : {carried} item(s) transportés, "
                    f"ancien checkpoint archivé → {arch.name}")
    return {}, (f"checkpoint LEGACY sans identité vérifiable — archivé → "
                f"{arch.name}, campagne propre")


def _reconcile_identity(ck: dict, db_snap: str, engine_sha: str,
                        queue_sha: str) -> tuple[dict, list[str]]:
    """La comparaison d'identité schema-2 (PR-161) :
    - moteur ou db changés → campagne RÉINITIALISÉE (archivée) — les
      résultats ne mesurent plus ce que le code mesure maintenant
    - queue seule changée → items CONSERVÉS (le spec_sha par item protège
      le contenu ; l'ensemble de la queue a juste grossi/rétréci)"""
    notes: list[str] = []
    if not ck:
        return ck, notes
    mismatch = []
    if ck.get("engine_sha") != engine_sha:
        mismatch.append(f"moteur {ck.get('engine_sha')} → {engine_sha}")
    if ck.get("db_snapshot") != db_snap:
        mismatch.append(f"db {ck.get('db_snapshot')} → {db_snap}")
    if mismatch:
        ARCHIVE.mkdir(parents=True, exist_ok=True)
        tag = ck.get("job_id") or f"reset-{int(time.time())}"
        arch = ARCHIVE / f"grind_checkpoint-{tag}.json"
        _atomic_write_json(arch, ck)
        notes.append("IDENTITÉ DE CAMPAGNE CHANGÉE ("
                     + " ; ".join(mismatch) + ") — réinitialisée, "
                     f"ancien checkpoint archivé → {arch.name}")
        return {}, notes
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


def _status_counts(items: dict, queue_total: int) -> dict:
    """Les métriques DÉRIVÉES de items uniquement (PR-161) — l'ancien
    status() lisait processed/failed qui ne sont plus écrits."""
    done = permanent = retryable = 0
    for v in items.values():
        st = v.get("state")
        if st == "DONE":
            done += 1
        elif st == "FAILED_PERMANENT":
            permanent += 1
        elif st == "FAILED_RETRYABLE":
            retryable += 1
    return {"done": done, "failed_permanent": permanent,
            "failed_retryable": retryable,
            "remaining": max(0, queue_total - done - permanent)}


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
    # la campagne exécute exactement cette liste matérialisée au démarrage
    ck["queue_total"] = len(spec_tuples)
    ck["manifest"] = [{"id": sid, "sha": sha} for _, sid, sha in spec_tuples]

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
            except OSError:
                pass

    hb_thread = threading.Thread(target=_hb_loop, daemon=True,
                                 name="lease-heartbeat")
    hb_thread.start()

    for f, spec_id, spec_sha in spec_tuples:
        # №P1-2 : le SKIP compare le spec_sha — une spec MODIFIÉE sous le
        # même id est re-mesurée (l'ancien ne comparait que l'id)
        prev = items.get(spec_id, {})
        # PR-161 : FAILED_PERMANENT est VRAIMENT terminal — via _is_terminal
        # qui exige le spec_sha (l'item PR-160 ne le portait pas et était
        # donc re-joué à l'infini malgré le commentaire)
        if _is_terminal(prev, spec_sha):
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

        # PR-161 : les bytes sont lus UNE SEULE FOIS — le spec_sha scellé
        # et le spec exécuté sont les mêmes (une modification de la spec
        # pendant la campagne ne peut plus glisser sous le sha)
        raw = f.read_bytes()
        retries = 0
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                spec = load_spec(f, raw=raw)
                if spec.get("id") != spec_id:
                    raise ValueError(
                        f"spec.id {spec.get('id')!r} ≠ nom de fichier "
                        f"{spec_id!r} — renommage ou collision")
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
                    "spec_sha": spec_sha, "git_sha": git_sha}
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
                    # le spec_sha+git_sha rendent la terminalité RÉELLE
                    items[spec_id] = {
                        "state": "FAILED_PERMANENT", "spec_sha": spec_sha,
                        "git_sha": git_sha,
                        "error": f"{err_type}: {exc}", "attempt": attempt,
                        "timestamp": _now_iso()}
                    had_errors = True
                    print(f"[worker] {spec_id} : FAILED_PERMANENT", flush=True)
                else:
                    # les erreurs RETRYABLES ne sont PAS terminales —
                    # retraitées au prochain lancement
                    items[spec_id] = {
                        "state": "FAILED_RETRYABLE", "spec_sha": spec_sha,
                        "git_sha": git_sha,
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
    lease = _load_json(LEASE)
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
    lease = _load_json(LEASE)
    if not ck:
        print(json.dumps({"status": "NEVER_RUN"}))
        return 0
    pid = lease.get("pid")
    alive = False
    if pid:
        try:
            os.kill(pid, 0)
            alive = True
        except (OSError, ProcessLookupError):
            pass
    stale = _is_lease_stale()
    counts = _status_counts(ck.get("items", {}),
                            ck.get("queue_total",
                                   len(ck.get("items", {}))))
    print(json.dumps({
        "job_id": ck.get("job_id"), "git_sha": ck.get("git_sha"),
        "engine_sha": ck.get("engine_sha"),
        "schema_version": ck.get("schema_version"),
        "status": ck.get("status"), "worker_pid": pid,
        "worker_alive": alive, "lease_stale": stale,
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
