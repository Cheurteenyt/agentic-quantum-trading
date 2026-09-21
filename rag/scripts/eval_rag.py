from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rag_tool import CONFIG_PATH, _load_yaml, _retrieve_hybrid, apply_domain, domain_names


DEFAULT_EVALS_PATH = Path(__file__).resolve().parents[1] / "evals" / "golden_questions.yaml"


@dataclass
class EvalCase:
    case_id: str
    question: str
    expected_paths: list[str]
    top_k: int
    min_expected_hits: int
    domain: str | None = None


def _normalize_path(path: str | None) -> str:
    return str(path or "").replace("\\", "/").strip().lstrip("./")


def _load_evals(path: Path) -> tuple[list[EvalCase], dict[str, Any]]:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("Missing PyYAML in the RAG venv.") from exc

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults = payload.get("defaults", {}) or {}
    cases: list[EvalCase] = []
    for raw in payload.get("questions", []) or []:
        expected_paths = [_normalize_path(item) for item in raw.get("expected_paths", [])]
        if not raw.get("id") or not raw.get("question") or not expected_paths:
            raise SystemExit(f"Invalid eval case in {path}: {raw}")
        cases.append(
            EvalCase(
                case_id=str(raw["id"]),
                question=str(raw["question"]),
                expected_paths=expected_paths,
                top_k=int(raw.get("top_k", defaults.get("top_k", 5))),
                min_expected_hits=int(raw.get("min_expected_hits", defaults.get("min_expected_hits", 1))),
                domain=str(raw["domain"]) if raw.get("domain") else None,
            )
        )
    if not cases:
        raise SystemExit(f"No eval cases found in {path}")
    return cases, payload


def _run_case(raw_config: dict[str, Any], case: EvalCase, forced_domain: str | None = None) -> dict[str, Any]:
    config = apply_domain(raw_config, forced_domain or case.domain)
    matches, vector_error = _retrieve_hybrid(config, case.question)
    top_matches = matches[: case.top_k]
    returned_paths = [_normalize_path(match.get("path")) for match in top_matches]
    expected_set = set(case.expected_paths)
    hit_paths = [path for path in returned_paths if path in expected_set]
    passed = len(set(hit_paths)) >= case.min_expected_hits

    return {
        "id": case.case_id,
        "domain": config.get("_domain", "full"),
        "collection": config["project"]["collection"],
        "passed": passed,
        "question": case.question,
        "expected_paths": case.expected_paths,
        "returned_paths": returned_paths,
        "hit_paths": sorted(set(hit_paths)),
        "top_k": case.top_k,
        "min_expected_hits": case.min_expected_hits,
        "vector_error": vector_error,
    }


def run_evals(evals_path: Path, fail_under: float, domain: str | None = None) -> tuple[int, dict[str, Any]]:
    raw_config = _load_yaml(CONFIG_PATH)
    cases, eval_payload = _load_evals(evals_path)
    if domain and domain != "all":
        cases = [case for case in cases if (case.domain or "full") == domain]
        if not cases:
            raise SystemExit(f"No eval cases for domain '{domain}'. Available domains: {', '.join(domain_names(raw_config))}")

    results = [_run_case(raw_config, case, None if domain in {None, "all"} else domain) for case in cases]
    passed = sum(1 for result in results if result["passed"])
    total = len(results)
    score = passed / max(total, 1)

    by_domain: dict[str, dict[str, Any]] = {}
    for result in results:
        item = by_domain.setdefault(result["domain"], {"passed": 0, "failed": 0, "total": 0, "score": 0.0})
        item["total"] += 1
        if result["passed"]:
            item["passed"] += 1
        else:
            item["failed"] += 1
    for item in by_domain.values():
        item["score"] = round(item["passed"] / max(item["total"], 1), 4)

    report = {
        "evals_path": str(evals_path),
        "version": eval_payload.get("version"),
        "domain_filter": domain or "case-defined",
        "qdrant_mode": raw_config["storage"].get("qdrant_mode"),
        "embedding_model": raw_config["embeddings"]["model"],
        "chunk_size": raw_config["chunking"]["chunk_size"],
        "chunk_overlap": raw_config["chunking"]["chunk_overlap"],
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "score": round(score, 4),
        "fail_under": fail_under,
        "by_domain": by_domain,
        "results": results,
    }
    return (0 if score >= fail_under else 1), report


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Core Equity RAG retrieval quality.")
    parser.add_argument("--evals", default=str(DEFAULT_EVALS_PATH), help="Path to golden_questions.yaml")
    parser.add_argument("--domain", default=None, help="Run only one domain, or use case-defined domains by default.")
    parser.add_argument("--fail-under", type=float, default=0.85, help="Minimum pass ratio required.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    exit_code, report = run_evals(Path(args.evals), args.fail_under, args.domain)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return exit_code

    print(
        f"RAG eval: {report['passed']}/{report['total']} passed "
        f"(score={report['score']}, fail_under={report['fail_under']})"
    )
    for domain_name, domain_report in sorted(report["by_domain"].items()):
        print(
            f"  {domain_name}: {domain_report['passed']}/{domain_report['total']} "
            f"(score={domain_report['score']})"
        )
    for result in report["results"]:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"- {status} [{result['domain']}] {result['id']}")
        if not result["passed"]:
            print(f"  expected: {', '.join(result['expected_paths'])}")
            print(f"  returned: {', '.join(result['returned_paths'])}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
