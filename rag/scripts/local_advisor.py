from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from rag_tool import (
    CONFIG_PATH,
    _build_rag_prompt,
    _call_llama_cpp,
    _clean_llm_answer,
    _load_yaml,
    _retrieve_hybrid,
    apply_domain,
    print_json,
)


REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
MEMORY_DIR = Path(__file__).resolve().parents[1] / "memory"

ADVISOR_ROLES = {
    "scout": "Find overlooked context, source paths, endpoints and contradictions. Do not design patches.",
    "critic": "Challenge assumptions, find weak evidence, missing tests and unsafe shortcuts.",
    "planner": "Propose a small verification plan that Codex can execute, with rollback and success criteria.",
    "data": "Focus on labels, RPC coverage, dedupe, chain/source separation and Arkham-like data quality.",
    "security": "Focus on client exposure, auth boundaries, secret handling and unsafe admin/data operations.",
    "frontend": "Focus on UI clarity, user flows, loading/error states and places where data may be misleading.",
}

ADVISOR_PRESETS = {
    "priority-data": {
        "role": "data",
        "context_mode": "rag",
        "domain": "data",
        "question": (
            "Core Equity priority data review: inspect current RAG context and project memory. "
            "Give Codex the next 5 verification steps to improve Arkham-like label/RPC coverage, "
            "with candidate-label safety, dedupe, chain/source separation, and no unsafe bulk ingestion."
        ),
    },
    "candidate-labels": {
        "role": "data",
        "context_mode": "rag",
        "domain": "data",
        "question": (
            "Review the label_candidates direction. What should Codex verify next before promoting "
            "any candidate into a trusted label? Focus on evidence, source URLs, dedupe keys, and false positives."
        ),
    },
    "security-client": {
        "role": "security",
        "context_mode": "memory",
        "domain": "memory",
        "question": (
            "Review Core Equity private client exposure from project memory only. "
            "Give Codex the top security checks to verify before exposing more data/admin surfaces."
        ),
    },
    "frontend-alpha": {
        "role": "frontend",
        "context_mode": "rag",
        "domain": "frontend",
        "question": (
            "Review Alpha Lab from retrieved context. Give Codex UI/data clarity checks that would make "
            "wallet analysis feel premium without misleading users or hiding source uncertainty."
        ),
    },
    "critic": {
        "role": "critic",
        "context_mode": "memory",
        "domain": "memory",
        "question": (
            "Critique the current Core Equity plan from memory only. "
            "List weak assumptions Codex should verify before coding further."
        ),
    },
}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:72] or "advisor-report"


def _load_question(args: argparse.Namespace) -> str:
    parts: list[str] = []
    if args.question:
        parts.append(args.question)
    if args.task_file:
        task_path = Path(args.task_file)
        parts.append(task_path.read_text(encoding="utf-8"))
    question = "\n\n".join(part.strip() for part in parts if part and part.strip())
    if not question:
        raise SystemExit("Provide a question or --task-file.")
    return question


def _apply_preset(args: argparse.Namespace) -> None:
    if not args.preset:
        return
    preset = ADVISOR_PRESETS[args.preset]
    if not args.question and not args.task_file:
        args.question = preset["question"]
    if args.role == "scout":
        args.role = preset["role"]
    if args.context_mode == "rag":
        args.context_mode = preset["context_mode"]
    if not args.domain:
        args.domain = preset.get("domain")


def _load_memory_context(enabled: bool, max_chars_per_file: int = 3500) -> tuple[str, list[str]]:
    if not enabled:
        return "", []
    memory_blocks = []
    memory_sources = []
    for name in ("project_state.md", "agent_improvement_protocol.md", "rag_operating_playbook.md", "model_routing_guide.md"):
        path = MEMORY_DIR / name
        if path.exists():
            memory_blocks.append(f"[Memory: {name}]\n{path.read_text(encoding='utf-8')[:max_chars_per_file]}")
            memory_sources.append(f"rag/memory/{name}")
    return "\n\n---\n\n".join(memory_blocks), memory_sources


def _build_advisor_prompt(
    question: str,
    matches: list[dict[str, Any]],
    role: str,
    context_mode: str,
    memory_context: str,
) -> str:
    if context_mode == "task-only":
        base_prompt = f"""You are Core Equity's local advisor.
Answer only from the delegated task below.
If the task is insufficient, say exactly what is missing.

Question:
{question}
"""
    else:
        base_prompt = _build_rag_prompt(question, matches)
    return f"""{base_prompt}

Durable project memory:
{memory_context}

Additional role instructions:

You are the LOCAL READ-ONLY ADVISOR for Core Equity.
You are Codex's subordinate assistant, not an autonomous coding agent.
Codex is smarter, has authority, and is the only agent allowed to decide, patch and verify.
You are running beside Codex to save tokens and surface useful hypotheses.
Your current specialized role is: {role} — {ADVISOR_ROLES[role]}
Your context mode is: {context_mode}.
You do not have direct repository write access.
Treat retrieved snippets as partial evidence, not the whole codebase.
You must never claim you modified files.
You must not provide bulk rewrite instructions.
You must not suggest unsafe data ingestion, secret exposure, or admin bypasses.
You must label every recommendation as one of: VERIFY, LOW-RISK, or DO-NOT-DO.
If you propose SQL, it must be SQLite-compatible and based only on tables/columns shown in retrieved context.
If schema details are missing, say what Codex should inspect instead of inventing SQL.
Do not invent endpoints, tables, columns, status values or metrics.

Return a concise engineering report with exactly these sections:

1. Useful facts, with source paths
2. Hypotheses for Codex to verify
3. Concrete next checks, no edits
4. Risks / false positives / non-goals
5. Tiny experiments Codex may choose to run
6. Confidence and missing context

If the retrieved context is insufficient, say what context should be retrieved next.
"""


def _write_report(question: str, sources: list[str], answer: str, vector_error: str | None = None) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"{stamp}_{_slugify(question)}.md"
    body = [
        "# Local Advisor Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Question",
        "",
        question.strip(),
        "",
        "## Sources",
        "",
        *(f"- `{source}`" for source in sources),
        "",
    ]
    if vector_error:
        body.extend(["## Retrieval Warning", "", vector_error, ""])
    body.extend(["## Advisor Output", "", answer.strip(), ""])
    path.write_text("\n".join(body), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Qwen/RAG advisor in read-only mode.")
    parser.add_argument("question", nargs="?", help="Question or task for the local advisor.")
    parser.add_argument("--preset", choices=sorted(ADVISOR_PRESETS), help="Controlled prompt preset for recurring advisor work.")
    parser.add_argument("--task-file", help="Optional UTF-8 text/markdown file containing the task.")
    parser.add_argument("--domain", help="RAG domain to retrieve from, e.g. backend/frontend/data/memory/full.")
    parser.add_argument("--role", choices=sorted(ADVISOR_ROLES), default="scout")
    parser.add_argument(
        "--context-mode",
        choices=("rag", "memory", "task-only"),
        default="rag",
        help="rag = retrieved snippets + memory, memory = durable memory only, task-only = no project context.",
    )
    parser.add_argument("--max-sources", type=int, default=4, help="Maximum retrieved RAG snippets to show Qwen.")
    parser.add_argument("--answer-tokens", type=int, default=1200, help="Max tokens Qwen may generate for the advisor answer.")
    parser.add_argument("--llm-timeout", type=int, default=90, help="Seconds to wait for the local LLM before falling back to prompt-only.")
    parser.add_argument("--memory-chars", type=int, default=3500, help="Max durable-memory characters per memory file.")
    parser.add_argument("--prompt-only", action="store_true", help="Save the advisor prompt without calling Qwen.")
    parser.add_argument("--no-save", action="store_true", help="Print JSON only, do not write a markdown report.")
    args = parser.parse_args()

    raw_config = _load_yaml(CONFIG_PATH)
    _apply_preset(args)
    config = apply_domain(raw_config, args.domain)
    question = _load_question(args)
    matches: list[dict[str, Any]] = []
    vector_error = None
    if args.context_mode == "rag":
        matches, vector_error = _retrieve_hybrid(config, question)
        matches = matches[: max(1, min(args.max_sources, 8))]
    memory_context, memory_sources = _load_memory_context(
        args.context_mode in {"rag", "memory"},
        max_chars_per_file=max(800, min(args.memory_chars, 9000)),
    )
    sources = list(dict.fromkeys(str(match.get("path")) for match in matches if match.get("path")))
    for memory_name in memory_sources:
        if memory_name not in sources:
            sources.append(memory_name)
    prompt = _build_advisor_prompt(question, matches, args.role, args.context_mode, memory_context)

    response: dict[str, Any] = {
        "ok": True,
        "mode": "local_read_only_advisor",
        "preset": args.preset,
        "role": args.role,
        "context_mode": args.context_mode,
        "domain": config.get("_domain", "full"),
        "collection": config["project"]["collection"],
        "question": question,
        "sources": sources,
    }
    if vector_error:
        response["vector_warning"] = "Vector retrieval failed; advisor used fallback context."
        response["vector_error"] = vector_error

    if args.prompt_only:
        answer = prompt
        response["prompt_only"] = True
    else:
        try:
            completion = _call_llama_cpp(
                config,
                prompt,
                max_tokens=max(256, min(args.answer_tokens, 4096)),
                timeout=max(10, min(args.llm_timeout, 240)),
            )
            message = completion["choices"][0]["message"]
            answer = _clean_llm_answer(message.get("content") or message.get("reasoning_content") or "")
            response["model"] = completion.get("model")
        except Exception as exc:
            answer = prompt
            response["ok"] = False
            response["llm_error"] = str(exc)
            response["hint"] = "Start rag/scripts/run_local_llm.ps1 -UseIkLlama, or rerun with --prompt-only."
            response["prompt_only"] = True

    if not args.no_save:
        report_path = _write_report(question, sources, answer, vector_error)
        response["report_path"] = str(report_path)
    else:
        response["answer"] = answer

    print_json(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
