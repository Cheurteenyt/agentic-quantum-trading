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
  - ledger idempotent : la ligne existe déjà = skip

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
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUNTIME = ROOT / "research" / "runtime"
CHECKPOINT = RUNTIME / "grind_checkpoint.json"
LEASE = RUNTIME / "worker.json"
LOCK = RUNTIME / "worker.lock"
HEARTBEAT_INTERVAL = 60
MAX_RETRIES = 3
LEASE_TTL_S = 150

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_WAITING_RESOURCE = 42

# les erreurs PERMANENTES (spec invalide, code bug) vs RETRYABLES (I/O, DB)
_PERMANENT_ERRORS = (ValueError, KeyError, TypeError, NameError,
                     AttributeError, json.JSONDecodeError)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, data: dict) -> None:
    """Écriture ATOMIQUE : tmp + flush + fsync + rename (№P2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    with open(tmp, "rb") as fh:
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
    """Le heartbeat ATOMIQUE — checkpoint + lease en une écriture (P0 fix)."""
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
    """Le hash du CONTENU de la queue (№P1-3) — le chemin seul ne suffit pas."""
    h = hashlib.sha256()
    for f in sorted(queue_dir.rglob("*")):
        if f.is_file() and f.suffix in (".yaml", ".yml", ".json"):
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


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

    # №P2 : le job_id est STABLE — repris du checkpoint s'il existe
    ck = _load_json(CHECKPOINT)
    job_id = ck.get("job_id") or f"grind-{git_sha}-{int(time.time())}"

    # FIX v20 (PR-160 №1-№3) : les TROIS identifiants de campagne sont
    # PERSISTÉS au checkpoint et COMPARÉS à la reprise — tout changement
    # (git, DB, queue) = nouveau job (les anciens DONE restent en attempts/)
    cur_queue_sha = _queue_sha(queue_dir)
    identity_mismatch = []
    if ck.get("git_sha") and ck["git_sha"] != git_sha:
        identity_mismatch.append(f"git {ck['git_sha']} → {git_sha}")
    if ck.get("db_snapshot") and ck["db_snapshot"] != db_snap:
        identity_mismatch.append(f"db {ck['db_snapshot']} → {db_snap}")
    if ck.get("queue_sha") and ck["queue_sha"] != cur_queue_sha:
        identity_mismatch.append(f"queue {ck['queue_sha']} → {cur_queue_sha}")
    if identity_mismatch:
        print(f"[worker] IDENTITÉ DE CAMPAGNE CHANGÉE : "
              f"{' ; '.join(identity_mismatch)} — nouveau job", flush=True)
        ck = {}
        job_id = f"grind-{git_sha}-{int(time.time())}"

    # les 3 identifiants sont SCELLÉS au checkpoint (№1/№2 : l'ancien code
    # les calculait mais ne les persistait jamais)
    ck["job_id"] = job_id
    ck["git_sha"] = git_sha
    ck["db_snapshot"] = db_snap
    ck["queue_sha"] = cur_queue_sha
    job_id = ck["job_id"]

    specs = sorted(queue_dir.rglob("*"))
    specs = [p for p in specs if p.is_file()
             and p.suffix in (".yaml", ".yml", ".json")
             and "done" not in p.parts]
    if not specs:
        print("[worker] queue vide", flush=True)
        LEASE.unlink(missing_ok=True)
        return EXIT_OK

    items: dict[str, dict] = ck.get("items", {})
    candidates: list[str] = list(ck.get("candidates", []))

    print(f"[worker] job {job_id} · {len(specs)} specs · "
          f"{len(items)} déjà traitées", flush=True)

    exit_code = EXIT_OK
    had_errors = False

    last_hb = time.monotonic()

    def _heartbeat_if_due():
        """Le heartbeat est émis si HEARTBEAT_INTERVAL s'est écoulé —
        une discovery longue ne laisse plus le lease devenir stale."""
        nonlocal last_hb
        now_mono = time.monotonic()
        if now_mono - last_hb >= HEARTBEAT_INTERVAL:
            _lease_heartbeat()
            last_hb = now_mono

    for f in specs:
        spec_id = f.stem
        spec_sha = hashlib.sha256(f.read_bytes()).hexdigest()[:16]

        # №P1-2 : le SKIP compare le spec_sha — une spec MODIFIÉE sous le
        # même id est re-mesurée (l'ancien ne comparait que l'id)
        prev = items.get(spec_id, {})
        # FIX v21 (PR-160 №4) : FAILED_PERMANENT est TERMINAL — la spec
        # ne sera pas re-jouée à l'infini (l'ancien code ne skipait que
        # les DONE : un FAILED_PERMANENT était re-tenté chaque nuit)
        if (prev.get("state") in ("DONE", "FAILED_PERMANENT")
                and prev.get("spec_sha") == spec_sha):
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
            _heartbeat_if_due()
            time.sleep(60)
            if state.get("shutdown_requested"):
                break

        if state.get("shutdown_requested"):
            break

        _heartbeat_if_due()
        print(f"[worker] {spec_id} — discovery", flush=True)

        retries = 0
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                spec = load_spec(f)
                res = run_discovery(spec, db_path=db_path)
                verdict = res.get("verdict", "?")
                n = res.get("n", 0)
                mean = res.get("mean", float("nan"))
                print(f"[worker] {spec_id} : {verdict} · n {n} · "
                      f"mean {mean:.3f}", flush=True)

                if _passes(res, spec):
                    write_artifacts(spec_id, spec, res, "discovery",
                                    db_path=db_path)
                    # №P1-9 : le ledger IDEMPOTENT — on vérifie que la
                    # ligne n'existe pas déjà avant d'écrire
                    _log_ledger(spec, verdict, "discovery",
                                str(ROOT / "research" / "runs" / spec_id /
                                    "report.md"),
                                snapshot=res.get("snapshot"))
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
                    # №P1-8 : les erreurs PERMANENTES sont FAILED_PERMANENT
                    items[spec_id] = {
                        "state": "FAILED_PERMANENT",
                        "error": f"{err_type}: {exc}", "attempt": attempt,
                        "timestamp": _now_iso()}
                    had_errors = True
                    print(f"[worker] {spec_id} : FAILED_PERMANENT", flush=True)
                else:
                    # les erreurs RETRYABLES ne sont PAS processed —
                    # retraitées au prochain lancement
                    items[spec_id] = {
                        "state": "FAILED_RETRYABLE",
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
          f"{len(retryable)} retryable(s) — exit {exit_code}", flush=True)

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
    print(json.dumps({
        "job_id": ck.get("job_id"), "git_sha": ck.get("git_sha"),
        "status": ck.get("status"), "worker_pid": pid,
        "worker_alive": alive, "lease_stale": stale,
        "processed": len(ck.get("processed", [])),
        "candidates": ck.get("candidates", []),
        "failed_retryable": ck.get("failed_retryable", []),
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
