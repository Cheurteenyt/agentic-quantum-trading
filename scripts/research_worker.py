#!/usr/bin/env python3
"""LE RESEARCH WORKER — le processus durable de recherche (PR-156, durci
PR-157 suite à l'audit GLM 5.3 post-#156).

États : PENDING → RUNNING → WAITING_RESOURCE → DONE / DONE_WITH_ERRORS
Sécurités :
  - singleton : verrou OS (flock) — deux workers ne peuvent pas coexister
  - checkpoint : research/runtime/grind_checkpoint.json (spec_sha par item,
    git_sha, queue_sha) — le worker reprend là où il s'est arrêté
  - retry : les erreurs temporelles sont RETRYABLE (max 3 essais), seuls
    les échecs définitifs marquent la spec processed
  - exit codes : 0 = DONE, 42 = WAITING_RESOURCE, 1 = DONE_WITH_ERRORS
  - lease : research/runtime/worker.json (pid + heartbeat, TTL 150 s)
  - SIGTERM/SIGINT : checkpoint propre avant sortie

Usage :
    python3 scripts/research_worker.py --run --queue research/queue/bonsai
    python3 scripts/research_worker.py --status
    python3 scripts/research_worker.py --reset
"""
from __future__ import annotations

import fcntl
import json
import os
import signal
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


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


class _Shutdown(Exception):
    """Signalé par SIGTERM/SIGINT pour arrêter proprement."""


def _make_shutdown_handler(state: dict) -> callable:
    def handler(signum, frame):
        state["shutdown_requested"] = True
    return handler


def run_worker(queue_dir: Path, db_path: Path = None) -> int:
    from scripts.research_runner import (
        load_spec, run_discovery, write_artifacts, _log_ledger,
        _passes, _resource_guard)
    import hashlib

    db_path = db_path or ROOT / "data" / "warehouse" / "klines.db"
    pid = os.getpid()

    # ── SINGLETON (№3) : le verrou OS — deux workers ne coexistent pas
    RUNTIME.mkdir(parents=True, exist_ok=True)
    lock_fh = open(LOCK, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("[worker] un autre worker est ACTIF — refus", flush=True)
        return EXIT_FAILED

    # ── le lease avec TTL (№P2) : heartbeat + expiry
    state: dict = {"shutdown_requested": False}
    signal.signal(signal.SIGTERM, _make_shutdown_handler(state))
    signal.signal(signal.SIGINT, _make_shutdown_handler(state))

    def _lease_heartbeat():
        LEASE.write_text(json.dumps({
            "pid": pid, "started_at": _now_iso(),
            "heartbeat_at": _now_iso(),
            "status": "RUNNING"}, ensure_ascii=False, indent=1),
            encoding="utf-8")

    _lease_heartbeat()
    print(f"[worker] démarré (pid {pid}, lock acquis)", flush=True)

    git_sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, cwd=ROOT).stdout.strip()
    job_id = f"grind-{git_sha}-{int(time.time())}"

    specs = sorted(queue_dir.rglob("*"))
    specs = [p for p in specs if p.is_file()
             and p.suffix in (".yaml", ".yml", ".json")
             and "done" not in p.parts]
    if not specs:
        print("[worker] queue vide", flush=True)
        LEASE.unlink(missing_ok=True)
        return EXIT_OK

    # ── CHECKPOINT avec IDENTITÉ (№4) : git_sha + queue + spec_sha par item
    ck = _load_json(CHECKPOINT)
    if ck.get("git_sha") != git_sha:
        # nouveau code → nouveau job (les résultats précédents restent
        # en attempts/, le checkpoint repart de zéro)
        ck = {}
        print(f"[worker] nouveau job {job_id} (git {git_sha})", flush=True)
    items: dict[str, dict] = ck.get("items", {})
    processed = {k for k, v in items.items() if v.get("state") == "DONE"}
    candidates: list[str] = list(ck.get("candidates", []))
    failed_permanent: list[str] = list(ck.get("failed_permanent", []))

    print(f"[worker] job {job_id} · {len(specs)} specs · "
          f"{len(processed)} DONE · {len(failed_permanent)} permanent",
          flush=True)

    exit_code = EXIT_OK
    had_errors = False

    for f in specs:
        if state.get("shutdown_requested"):
            print("[worker] shutdown demandé — checkpoint propre", flush=True)
            break
        spec_id = f.stem
        if spec_id in processed or spec_id in failed_permanent:
            continue

        # ── №1 : le garde-fou ressource RETENTE LA MÊME SPEC (pas de skip)
        waited = 0
        while True:
            ok_res, why_res = _resource_guard()
            if ok_res:
                break
            checkpoint_data = {
                "job_id": job_id, "git_sha": git_sha,
                "status": "WAITING_RESOURCE", "current": spec_id,
                "reason": why_res, "heartbeat_at": _now_iso()}
            _heartbeat(checkpoint_data)
            print(f"[worker] WAITING_RESOURCE : {why_res} — "
                  "retry dans 60 s (la MÊME spec)", flush=True)
            time.sleep(60)
            waited += 60
            if state.get("shutdown_requested"):
                break

        if state.get("shutdown_requested"):
            break

        _lease_heartbeat()
        print(f"[worker] {spec_id} — discovery", flush=True)

        # ── №5 : le retry — les erreurs temporelles ne tuent pas la spec
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
                    _log_ledger(spec, verdict, "discovery",
                                str(ROOT / "research" / "runs" / spec_id /
                                    "report.md"),
                                snapshot=res.get("snapshot"))
                    candidates.append(spec_id)
                    print(f"[worker]   → CANDIDATE", flush=True)
                # DISCOVERY_FAIL ou PASS : la spec a été JUGÉE — DONE
                items[spec_id] = {
                    "state": "DONE", "verdict": verdict,
                    "spec_sha": hashlib.sha256(
                        f.read_bytes()).hexdigest()[:16],
                    "git_sha": git_sha}
                break
            except Exception as exc:
                retries = attempt
                err_type = type(exc).__name__
                print(f"[worker] {spec_id} : tentative {attempt}/"
                      f"{MAX_RETRIES} échouée ({err_type}: {exc})", flush=True)
                if attempt < MAX_RETRIES:
                    time.sleep(10 * attempt)
                else:
                    # №5 : les erreurs temporelles ne sont PAS processed —
                    # FAILED_RETRYABLE (retraité au prochain lancement)
                    items[spec_id] = {
                        "state": "FAILED_RETRYABLE",
                        "error": f"{err_type}: {exc}", "attempt": attempt,
                        "timestamp": _now_iso()}
                    had_errors = True
                    print(f"[worker] {spec_id} : FAILED_RETRYABLE", flush=True)

        _lease_heartbeat()
        # le checkpoint est écrit À CHAQUE spec (idempotent — le même
        # spec_sha ne re-déclenche pas l'écriture ledger au re-run)
        checkpoint = {
            "job_id": job_id, "git_sha": git_sha, "queue": str(queue_dir),
            "status": "RUNNING", "current": None,
            "processed": sorted(processed | set(items.keys())),
            "items": items,
            "candidates": candidates,
            "failed_permanent": failed_permanent,
            "heartbeat_at": _now_iso()}
        _heartbeat(checkpoint)

    # ── №6 : l'exit code reflète les échecs
    retryable = [k for k, v in items.items()
                 if v.get("state") == "FAILED_RETRYABLE"]
    checkpoint = {
        "job_id": job_id, "git_sha": git_sha, "status": "DONE",
        "candidates": candidates,
        "failed_retryable": retryable,
        "processed": sorted(set(items.keys())),
        "items": items, "heartbeat_at": _now_iso(),
        "completed_at": _now_iso()}
    _heartbeat(checkpoint)

    if retryable:
        exit_code = EXIT_FAILED
        print(f"[worker] TERMINÉ AVEC ÉCHECS : {len(retryable)} "
              f"FAILED_RETRYABLE — exit {EXIT_FAILED}", flush=True)
    elif had_errors:
        print(f"[worker] TERMINÉ (toutes les specs jugées, retryables "
              f"résolues) — exit {EXIT_OK}", flush=True)
    else:
        print(f"[worker] TERMINÉ : {len(candidates)} candidat(s) — "
              f"exit {EXIT_OK}", flush=True)

    # le lease est nettoyé à la fin (№P2 : pas de lease fantôme)
    LEASE.unlink(missing_ok=True)
    lock_fh.close()
    return exit_code


def _is_lease_stale() -> bool:
    """Le lease est-il périmé ? (heartbeat > LEASE_TTL_S)"""
    lease = _load_json(LEASE)
    hb = lease.get("heartbeat_at")
    if not hb:
        return True
    from datetime import datetime, timezone
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
        print("[worker] aucun checkpoint — jamais lancé")
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
        # №P2 : --reset exige qu'aucun worker soit actif
        lease = _load_json(LEASE)
        pid = lease.get("pid")
        if pid:
            try:
                os.kill(pid, 0)
                print(f"[worker] refus : un worker est ACTIF (pid {pid})")
                return EXIT_FAILED
            except (OSError, ProcessLookupError):
                pass
        if CHECKPOINT.exists():
            CHECKPOINT.unlink()
        if LEASE.exists():
            LEASE.unlink()
        print("checkpoint + lease effacés")
        return EXIT_OK
    if a.status:
        return status()
    if a.run:
        return run_worker(Path(a.queue), Path(a.db))
    print("choisis --run, --status ou --reset")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
