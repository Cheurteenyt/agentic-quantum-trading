from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv-win" / "Scripts" / "python.exe"
REVIEW_SCRIPT = ROOT / "scripts" / "qwen" / "local_qwen_review.py"
ONCHAIN_ENGINE = ROOT / "backend" / "services" / "onchain_engine.py"


SCENARIOS: dict[str, dict[str, Any]] = {
    "radar-read-only": {
        "prompt": (
            "Review the local candidate discovery radar. Decide if the snippet supports "
            "Core Equity data progress without DB writes. Do not invent line refs."
        ),
        "symbols": ["get_token_market_local_candidate_discovery_radar"],
        "greps": [],
        "expected_terms": [
            "read-only",
            "dry_run",
            "would_write",
            "label",
            "trade",
            "opt-in",
        ],
    },
    "manipulation-usability": {
        "prompt": (
            "Review the manipulation data usability audit. Check whether it correctly blocks "
            "profit/client decisions when data quality is insufficient."
        ),
        "symbols": ["get_token_manipulation_data_usability_audit"],
        "greps": ["usable_for_manipulation", "source_backed_candidates"],
        "expected_terms": [
            "usable_for_manipulation",
            "research",
            "blocked",
            "source",
            "client",
            "trade",
        ],
    },
    "source-backed-mapping": {
        "prompt": (
            "Review the source-backed venue mapping preview/apply flow. Check narrow writes, "
            "source guards, duplicate safety, and disabled client/trading surfaces."
        ),
        "symbols": ["preview_source_backed_venue_mapping", "upsert_source_backed_venue_mapping"],
        "greps": ["UPSERT_SOURCE_BACKED_VENUE_MAPPING", "would_create_cex_label"],
        "expected_terms": [
            "source",
            "dedupe",
            "mapping",
            "label",
            "trade",
            "opt-in",
        ],
    },
}


def _run_review(profile: str, scenario: dict[str, Any], max_tokens: int, timeout: int) -> dict[str, Any]:
    cmd = [
        str(PYTHON if PYTHON.exists() else sys.executable),
        str(REVIEW_SCRIPT),
        "--profile",
        profile,
        "--prompt",
        scenario["prompt"],
        "--max-tokens",
        str(max_tokens),
        "--timeout",
        str(timeout),
    ]
    for symbol in scenario["symbols"]:
        cmd.extend(["--symbol", f"{ONCHAIN_ENGINE}:{symbol}"])
    for grep in scenario["greps"]:
        cmd.extend(["--grep", f"{ONCHAIN_ENGINE}:{grep}"])

    started = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout + 240)
    wall_seconds = round(time.time() - started, 2)
    if proc.returncode != 0:
        return {
            "ok": False,
            "profile": profile,
            "wall_seconds": wall_seconds,
            "returncode": proc.returncode,
            "stderr_tail": proc.stderr[-2000:],
            "stdout_tail": proc.stdout[-2000:],
        }
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "profile": profile,
            "wall_seconds": wall_seconds,
            "parse_error": "stdout_not_json",
            "stdout_tail": proc.stdout[-2000:],
        }
    payload["wall_seconds"] = wall_seconds
    return payload


def _score_answer(answer: str, expected_terms: list[str]) -> dict[str, Any]:
    lowered = answer.lower()
    expected_hits = sorted(term for term in expected_terms if term.lower() in lowered)
    line_refs = re.findall(r"\b(?:ligne|l\.|line)\s*[#: ]?\s*\d+\b", lowered)
    mojibake_hits = len(re.findall(r"[ÃÂâ][^\s]{0,5}", answer))
    repeated_separators = answer.count("---")
    arrow_noise = answer.count("→") + answer.count("â†’")
    disabled_hits = sorted(
        term
        for term in ["db", "write", "label", "mapping", "trade", "wallet", "signal", "opt-in"]
        if term in lowered
    )
    score = 0
    score += 1 if answer.strip() else 0
    score += 1 if "<think" not in lowered else 0
    score += 1 if "verdict" in lowered else 0
    score += 1 if disabled_hits else 0
    score += 1 if len(expected_hits) >= max(2, min(4, len(expected_terms))) else 0
    score += 1 if ("hypoth" in lowered or "contexte" in lowered or "non prouv" in lowered) else 0
    if mojibake_hits >= 3 or repeated_separators >= 6 or arrow_noise >= 8:
        score = max(0, score - 2)
    return {
        "score_0_to_6": score,
        "think_leak": "<think" in lowered,
        "mojibake_hits": mojibake_hits,
        "repeated_separator_count": repeated_separators,
        "arrow_noise_count": arrow_noise,
        "line_reference_count": len(line_refs),
        "disabled_surface_terms": disabled_hits,
        "expected_terms_hit": expected_hits,
        "answer_chars": len(answer),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark local Qwen profiles on real Core Equity snippets.")
    parser.add_argument("--profiles", nargs="+", default=["qwen3-2507-fast", "qwen3-coder-fast"])
    parser.add_argument("--scenarios", nargs="+", default=["radar-read-only", "source-backed-mapping"])
    parser.add_argument("--max-tokens", type=int, default=650)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    unknown = [name for name in args.scenarios if name not in SCENARIOS]
    if unknown:
        raise SystemExit(f"unknown scenarios: {', '.join(unknown)}")

    results: list[dict[str, Any]] = []
    for scenario_name in args.scenarios:
        scenario = SCENARIOS[scenario_name]
        for profile in args.profiles:
            review = _run_review(profile, scenario, args.max_tokens, args.timeout)
            answer = str(review.get("answer") or "")
            results.append(
                {
                    "scenario": scenario_name,
                    "profile": profile,
                    "ok": bool(review.get("ok")),
                    "wall_seconds": review.get("wall_seconds"),
                    "elapsed_seconds": review.get("elapsed_seconds"),
                    "score": _score_answer(answer, list(scenario["expected_terms"])) if answer else None,
                    "answer": answer,
                    "error": {
                        key: review.get(key)
                        for key in ["returncode", "parse_error", "stderr_tail", "stdout_tail"]
                        if review.get(key)
                    },
                }
            )

    report = {
        "ok": all(row["ok"] for row in results),
        "profiles": args.profiles,
        "scenarios": args.scenarios,
        "results": results,
        "interpretation": (
            "Higher score means the local reviewer stayed structured, avoided think leakage, "
            "mentioned disabled surfaces, and covered expected Core Equity terms. Codex must still verify every claim."
        ),
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    try:
        sys.stdout.write(output + "\n")
    except UnicodeEncodeError:
        sys.stdout.buffer.write((output + "\n").encode("utf-8", errors="replace"))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
