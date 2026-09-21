from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv-win" / "Scripts" / "python.exe"
REVIEW_SCRIPT = ROOT / "scripts" / "qwen" / "local_qwen_review.py"


DEFAULT_PROMPT = (
    "Micro-benchmark Core Equity read-only. Reponds court. "
    "Dis seulement si ce profil est utilisable comme reviewer local, "
    "et rappelle qu'il ne doit jamais ecrire en DB."
)


def _run_profile(profile: str, prompt: str, max_tokens: int, timeout: int) -> dict[str, Any]:
    cmd = [
        str(PYTHON if PYTHON.exists() else sys.executable),
        str(REVIEW_SCRIPT),
        "--profile",
        profile,
        "--prompt",
        prompt,
        "--max-tokens",
        str(max_tokens),
        "--timeout",
        str(timeout),
    ]
    started = __import__("time").time()
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout + 220)
    elapsed = round(__import__("time").time() - started, 2)
    if proc.returncode != 0:
        return {
            "profile": profile,
            "ok": False,
            "elapsed_seconds": elapsed,
            "returncode": proc.returncode,
            "stderr_tail": proc.stderr[-2000:],
            "stdout_tail": proc.stdout[-2000:],
        }
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "profile": profile,
            "ok": False,
            "elapsed_seconds": elapsed,
            "returncode": proc.returncode,
            "parse_error": "stdout_not_json",
            "stdout_tail": proc.stdout[-2000:],
        }
    payload["wall_seconds"] = elapsed
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark local Qwen sidecar profiles.")
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["qwen25-fast", "qwen3-2507-fast", "qwen3-coder-fast"],
        help="Profiles from scripts/qwen/local_qwen_review.py to test.",
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--max-tokens", type=int, default=180)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    results = [_run_profile(profile, args.prompt, args.max_tokens, args.timeout) for profile in args.profiles]
    report = {
        "ok": all(bool(row.get("ok")) for row in results),
        "profiles": args.profiles,
        "results": results,
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    try:
        sys.stdout.write(output + "\n")
    except UnicodeEncodeError:
        sys.stdout.buffer.write((output + "\n").encode("utf-8", errors="replace"))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
