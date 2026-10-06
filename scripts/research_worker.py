#!/usr/bin/env python3
"""LE RESEARCH WORKER — le processus durable de recherche (PR-156).

Remplace la boucle synchrone du grind par un worker avec états :
  PENDING → RUNNING → WAITING_RESOURCE → DONE / FAILED
  + checkpoint/resume (le worker reprend là où il s'est arrêté)
  + lease (le watchdog Bonsai ne coupe pas si le worker est actif)
  + le verdict scientifique est vérifié à CHAQUE étage

Usage :
    python3 scripts/research_worker.py --run --queue research/queue/bonsai
    python3 scripts/research_worker.py --status
    python3 scripts/research_worker.py --reset

Le worker écrit son état dans research/runtime/worker.json (heartbeat)
et son checkpoint dans research/runtime/grind_checkpoint.json.
"""
from __future__ import annotations

import json
import os
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
HEARTBEAT_INTERVAL = 60   # secondes

# les codes de sortie distincts (le scheduler ne doit pas confondre)
EXIT_OK = 0
EXIT_WAITING_RESOURCE = 42
EXIT_FAILED = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _write_lease(pid: int) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    LEASE.write_text(json.dumps({
        "pid": pid, "started_at": _now_iso(),
        "heartbeat_at": _now_iso(),
        "expires_at": "never (worker runtime)",
    }, ensure_ascii=False, indent=1), encoding="utf-8")


def _heartbeat(checkpoint: dict) -> None:
    """Le heartbeat : lease + checkpoint à chaque itération."""
    RUNTIME.mkdir(parents=True, exist_ok=True)
    LEASE.write_text(json.dumps({
        **_load_json(LEASE),
        "heartbeat_at": _now_iso(),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    CHECKPOINT.write_text(json.dumps(checkpoint, ensure_ascii=False,
                                     indent=1), encoding="utf-8")


def _resource_guard() -> tuple[bool, str]:
    """Le garde-fou ressources (RAM + disque)."""
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


def _spec_already_processed(spec_id: str, runs_dir: Path) -> bool:
    """Le spec a-t-il déjà un summary_discovery avec le MÊME git_sha ?"""
    import hashlib
    sfile = runs_dir / spec_id / "summary_discovery.json"
    if not sfile.exists():
        return False
    try:
        s = json.loads(sfile.read_text(encoding="utf-8"))
        git = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True,
                             cwd=ROOT).stdout.strip()
        return s.get("git_sha") == git and s.get("verdict") in (
            "DISCOVERY_PASS", "DISCOVERY_FAIL")
    except (json.JSONDecodeError, OSError):
        return False


def run_worker(queue_dir: Path, db_path: Path = None) -> int:
    """La boucle principale du worker durable — avec checkpoint/resume."""
    from scripts.research_runner import (
        load_spec, run_discovery, write_artifacts, _log_ledger,
        _passes, _resource_guard, _env_versions)
    db_path = db_path or ROOT / "data" / "warehouse" / "klines.db"
    pid = os.getpid()
    _write_lease(pid)
    print(f"[worker] démarré (pid {pid})", flush=True)

    specs = sorted(queue_dir.rglob("*"))
    specs = [p for p in specs if p.is_file()
             and p.suffix in (".yaml", ".yml", ".json")
             and "done" not in p.parts]
    if not specs:
        print("[worker] queue vide", flush=True)
        return EXIT_OK

    ck = _load_json(CHECKPOINT)
    processed = set(ck.get("processed", []))
    print(f"[worker] {len(specs)} specs · {len(processed)} déjà traitées "
          f"({len(specs) - len(processed)} restantes)", flush=True)

    checkpoint = {
        "status": "RUNNING", "pid": pid, "started_at": _now_iso(),
        "queue": str(queue_dir), "processed": sorted(processed),
        "candidates": [], "failed": [], "remaining": [],
        "heartbeat_at": _now_iso(),
    }
    candidates: list[str] = []
    failed: list[str] = []
    processed_this_run: list[str] = []

    for f in specs:
        spec_id = f.stem
        if spec_id in processed:
            continue

        # heartbeat
        checkpoint["current"] = spec_id
        checkpoint["heartbeat_at"] = _now_iso()
        _heartbeat(checkpoint)

        # garde-fou ressources → WAITING_RESOURCE (PAS exit 0)
        ok_res, why_res = _resource_guard()
        if not ok_res:
            checkpoint["status"] = "WAITING_RESOURCE"
            checkpoint["reason"] = why_res
            _heartbeat(checkpoint)
            print(f"[worker] WAITING_RESOURCE : {why_res} — "
                  "reprise dans 60 s", flush=True)
            time.sleep(60)
            checkpoint["status"] = "RUNNING"
            continue

        print(f"[worker] {spec_id} — discovery", flush=True)
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
            else:
                failed.append(spec_id)
            processed_this_run.append(spec_id)
            processed.add(spec_id)
        except Exception as exc:
            print(f"[worker] {spec_id} : ERREUR {exc}", flush=True)
            failed.append(spec_id)
            processed_this_run.append(spec_id)
            processed.add(spec_id)

        checkpoint["processed"] = sorted(processed)
        checkpoint["candidates"] = candidates
        checkpoint["failed"] = failed
        _heartbeat(checkpoint)

    checkpoint["status"] = "DONE"
    checkpoint["current"] = None
    checkpoint["completed_at"] = _now_iso()
    checkpoint["candidates"] = candidates
    _heartbeat(checkpoint)
    print(f"[worker] TERMINÉ : {len(candidates)} candidat(s), "
          f"{len(failed)} éliminé(s)", flush=True)
    return EXIT_OK


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
    print(f"[worker] status {ck.get('status')} · pid {pid} "
          f"({'ACTIF' if alive else 'mort'})")
    print(f"  candidats : {ck.get('candidates', [])}")
    print(f"  traitées : {len(ck.get('processed', []))}")
    print(f"  heartbeat : {lease.get('heartbeat_at', ck.get('heartbeat_at', '?'))}")
    return 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="efface le checkpoint (repart de zéro)")
    ap.add_argument("--queue", default=str(ROOT / "research" / "queue" / "bonsai"))
    ap.add_argument("--db", default=str(ROOT / "data" / "warehouse" / "klines.db"))
    a = ap.parse_args()
    if a.reset:
        if CHECKPOINT.exists():
            CHECKPOINT.unlink()
        print("checkpoint effacé")
        return EXIT_OK
    if a.status:
        return status()
    if a.run:
        return run_worker(Path(a.queue), Path(a.db))
    print("choisis --run, --status ou --reset")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
