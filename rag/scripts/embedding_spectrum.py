from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from rag_tool import (
    CONFIG_PATH,
    _embedding_device,
    _load_yaml,
    _root,
    apply_domain,
    collect_files,
    print_json,
)


REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"


def _chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    normalized = "\n".join(line.rstrip() for line in text.splitlines())
    if not normalized.strip():
        return []
    chunks: list[str] = []
    step = max(1, chunk_size - chunk_overlap)
    for start in range(0, len(normalized), step):
        chunk = normalized[start : start + chunk_size].strip()
        if len(chunk) >= 80:
            chunks.append(chunk)
        if start + chunk_size >= len(normalized):
            break
    return chunks


def _collect_chunks(config: dict[str, Any], max_chunks: int) -> list[dict[str, str]]:
    root = _root(config)
    chunk_size = int(config["chunking"]["chunk_size"])
    chunk_overlap = int(config["chunking"]["chunk_overlap"])
    per_file: list[list[dict[str, str]]] = []
    for path in collect_files(config):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.resolve().relative_to(root).as_posix()
        file_chunks = [
            {"path": rel, "chunk_id": f"{rel}#{index}", "text": chunk}
            for index, chunk in enumerate(_chunk_text(text, chunk_size, chunk_overlap))
        ]
        if file_chunks:
            per_file.append(file_chunks)
    chunks: list[dict[str, str]] = []
    cursor = 0
    while len(chunks) < max_chunks and any(cursor < len(items) for items in per_file):
        for items in per_file:
            if cursor < len(items):
                chunks.append(items[cursor])
                if len(chunks) >= max_chunks:
                    break
        cursor += 1
    return chunks


def _embed(config: dict[str, Any], texts: list[str]) -> np.ndarray:
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    model = HuggingFaceEmbedding(
        model_name=config["embeddings"]["model"],
        device=_embedding_device(config),
        embed_batch_size=int(config["embeddings"].get("batch_size", 32)),
    )
    vectors = model.get_text_embedding_batch(texts, show_progress=True)
    matrix = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _spectrum(matrix: np.ndarray) -> dict[str, Any]:
    centered = matrix - matrix.mean(axis=0, keepdims=True)
    sample_count, nominal_dim = centered.shape
    if sample_count < 2:
        return {
            "sample_count": sample_count,
            "nominal_dim": nominal_dim,
            "effective_dim": 0.0,
            "components_95": 0,
            "anisotropy_top1_pct": 0.0,
            "avg_pairwise_cosine": 0.0,
            "warning": "need_at_least_two_chunks",
        }

    singular_values = np.linalg.svd(centered, compute_uv=False)
    eigenvalues = (singular_values ** 2) / max(1, sample_count - 1)
    total = float(eigenvalues.sum())
    if total <= 0:
        explained = np.zeros_like(eigenvalues)
        effective_dim = 0.0
    else:
        explained = eigenvalues / total
        effective_dim = float((eigenvalues.sum() ** 2) / np.square(eigenvalues).sum())
    cumulative = np.cumsum(explained)
    components_95 = int(np.searchsorted(cumulative, 0.95) + 1) if len(cumulative) else 0
    cosine = matrix @ matrix.T
    upper = cosine[np.triu_indices(sample_count, k=1)]
    avg_pairwise = float(upper.mean()) if upper.size else 0.0
    return {
        "sample_count": sample_count,
        "nominal_dim": nominal_dim,
        "effective_dim": round(effective_dim, 2),
        "effective_dim_ratio": round(effective_dim / nominal_dim, 4) if nominal_dim else 0.0,
        "components_95": components_95,
        "components_95_ratio": round(components_95 / nominal_dim, 4) if nominal_dim else 0.0,
        "anisotropy_top1_pct": round(float(explained[0] * 100), 2) if len(explained) else 0.0,
        "avg_pairwise_cosine": round(avg_pairwise, 4),
        "first_12_variance_pct": [round(float(value * 100), 3) for value in explained[:12]],
    }


def _recommendations(metrics: dict[str, Any]) -> list[str]:
    recommendations: list[str] = []
    effective_ratio = float(metrics.get("effective_dim_ratio") or 0.0)
    avg_cosine = float(metrics.get("avg_pairwise_cosine") or 0.0)
    top1 = float(metrics.get("anisotropy_top1_pct") or 0.0)
    if effective_ratio < 0.25:
        recommendations.append("LOW-RISK: keep retrieval hybrid; embeddings are compressed enough that BM25/path boosts remain valuable.")
    if avg_cosine > 0.35:
        recommendations.append("VERIFY: chunks may be too similar; inspect duplicate generated memory or repeated boilerplate.")
    if top1 > 20:
        recommendations.append("VERIFY: strong first-component dominance; consider query-specific reranking before increasing vector top_k.")
    if not recommendations:
        recommendations.append("LOW-RISK: current embedding spectrum looks usable; tune retrieval with evals before changing models.")
    recommendations.append("DO-NOT-DO: do not switch embedding model only because nominal dimensions are larger; measure effective dimension first.")
    return recommendations


def _compression_policy(metrics: dict[str, Any]) -> dict[str, Any]:
    effective_dim = float(metrics.get("effective_dim") or 0.0)
    components_95 = int(metrics.get("components_95") or 0)
    avg_cosine = float(metrics.get("avg_pairwise_cosine") or 0.0)
    top1 = float(metrics.get("anisotropy_top1_pct") or 0.0)

    if effective_dim < 35 and avg_cosine > 0.55:
        regime = "tight_low_deff"
        decision = "centroid_or_summary_can_help"
        guidance = (
            "Use consolidation for repeated memory/playbook style content. "
            "Centroid-like summaries may improve downstream answers by removing duplicates."
        )
    elif effective_dim <= 75 and components_95 <= 120:
        regime = "middle_deff"
        decision = "neutral_measure_with_eval"
        guidance = (
            "Consolidation is likely neutral. Keep hybrid retrieval and compare answer quality with evals before changing."
        )
    else:
        regime = "spread_high_deff"
        decision = "avoid_centroid_compression"
        guidance = (
            "Avoid replacing retrieved chunks with one centroid/summary. Keep multiple chunks or use medoid/no-consolidation."
        )

    if top1 > 20:
        guidance += " First component is dominant, so add reranking or dedupe before increasing vector top_k."

    return {
        "regime": regime,
        "decision": decision,
        "recommended_strategy": (
            "centroid_summary"
            if decision == "centroid_or_summary_can_help"
            else "no_consolidation_or_medoid"
            if decision == "avoid_centroid_compression"
            else "eval_gated_hybrid"
        ),
        "why": guidance,
        "safety": "Use this as a routing prior, not proof. Validate with eval_rag.py or task-specific QA before changing production retrieval.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit effective dimensionality of Core Equity RAG embeddings.")
    parser.add_argument("--domain", default="data", help="RAG domain to audit.")
    parser.add_argument("--max-chunks", type=int, default=256, help="Maximum chunks to embed for the spectrum sample.")
    parser.add_argument("--save", action="store_true", help="Write a markdown report in rag/reports.")
    args = parser.parse_args()

    raw_config = _load_yaml(CONFIG_PATH)
    config = apply_domain(raw_config, args.domain)
    chunks = _collect_chunks(config, max(16, min(args.max_chunks, 2048)))
    if len(chunks) < 2:
        print_json({"ok": False, "domain": config.get("_domain"), "error": "not_enough_chunks", "chunk_count": len(chunks)})
        return 1

    matrix = _embed(config, [chunk["text"] for chunk in chunks])
    metrics = _spectrum(matrix)
    payload = {
        "ok": True,
        "mode": "embedding_effective_dimension_audit",
        "domain": config.get("_domain", "full"),
        "collection": config["project"]["collection"],
        "embedding_model": config["embeddings"]["model"],
        "embedding_device": _embedding_device(config),
        "chunk_size": config["chunking"]["chunk_size"],
        "chunk_overlap": config["chunking"]["chunk_overlap"],
        "sampled_chunks": len(chunks),
        "sampled_files": len({chunk["path"] for chunk in chunks}),
        "metrics": metrics,
        "compression_policy": _compression_policy(metrics),
        "recommendations": _recommendations(metrics),
        "source_policy": "read-only local RAG embedding audit; no index, source file, or vector store is modified",
    }
    if args.save:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_embedding_spectrum_{payload['domain']}.md"
        report_path.write_text(
            "\n".join(
                [
                    "# Embedding Effective Dimension Audit",
                    "",
                    f"- Domain: `{payload['domain']}`",
                    f"- Model: `{payload['embedding_model']}`",
                    f"- Sampled chunks: `{payload['sampled_chunks']}`",
                    "",
                    "```json",
                    json.dumps(payload["metrics"], indent=2),
                    "```",
                    "",
                    "## Compression Policy",
                    "",
                    "```json",
                    json.dumps(payload["compression_policy"], indent=2),
                    "```",
                    "",
                    "## Recommendations",
                    "",
                    *(f"- {item}" for item in payload["recommendations"]),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        payload["report_path"] = str(report_path)
    print_json(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
