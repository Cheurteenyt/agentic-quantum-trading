from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.util
import json
import math
import re
import copy
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "rag.yaml"
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|0x[a-fA-F0-9]{6,}|[A-Z]{2,}(?=[A-Z][a-z]|\b)|[a-z0-9]{2,}")


def print_json(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    try:
        sys.stdout.write(text + "\n")
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        return _load_simple_yaml(path)

    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _coerce_scalar(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        return value


def _load_simple_yaml(path: Path) -> dict[str, Any]:
    """Tiny parser for rag/config/rag.yaml so health/dry-run work before installs."""
    items: list[tuple[int, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        items.append((len(raw_line) - len(raw_line.lstrip(" ")), raw_line.strip()))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(items):
            return {}, index

        is_list = items[index][1].startswith("- ")
        if is_list:
            values: list[Any] = []
            while index < len(items):
                line_indent, stripped = items[index]
                if line_indent != indent or not stripped.startswith("- "):
                    break
                values.append(_coerce_scalar(stripped[2:].strip()))
                index += 1
            return values, index

        values: dict[str, Any] = {}
        while index < len(items):
            line_indent, stripped = items[index]
            if line_indent < indent:
                break
            if line_indent > indent or stripped.startswith("- "):
                break
            if ":" not in stripped:
                index += 1
                continue

            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            index += 1
            if value:
                values[key] = _coerce_scalar(value)
                continue
            if index < len(items) and items[index][0] > line_indent:
                values[key], index = parse_block(index, items[index][0])
            else:
                values[key] = {}
        return values, index

    parsed, _ = parse_block(0, items[0][0] if items else 0)
    return parsed if isinstance(parsed, dict) else {}


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _embedding_device(config: dict[str, Any]) -> str:
    configured = str(config["embeddings"].get("device", "auto")).lower()
    if configured != "auto":
        return configured
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _root(config: dict[str, Any]) -> Path:
    return Path(config["project"]["root"]).resolve()


def domain_names(config: dict[str, Any]) -> list[str]:
    domains = config.get("domains") or {}
    return sorted(domains.keys())


def apply_domain(config: dict[str, Any], domain: str | None) -> dict[str, Any]:
    domain = domain or str(config.get("project", {}).get("default_domain", "full"))
    if domain in {"default", "project"}:
        domain = str(config.get("project", {}).get("default_domain", "full"))
    if domain in {"", "full"} and "full" not in (config.get("domains") or {}):
        scoped = copy.deepcopy(config)
        scoped["_domain"] = "full"
        return scoped

    domains = config.get("domains") or {}
    if domain not in domains:
        available = ", ".join(domain_names(config)) or "full"
        raise SystemExit(f"Unknown RAG domain '{domain}'. Available domains: {available}")

    scoped = copy.deepcopy(config)
    domain_cfg = domains[domain] or {}
    scoped["_domain"] = domain
    scoped["project"]["collection"] = domain_cfg.get("collection", scoped["project"]["collection"])
    if domain_cfg.get("include"):
        scoped["include"] = list(domain_cfg["include"])
    if domain_cfg.get("bm25_path"):
        scoped.setdefault("storage", {})["bm25_path"] = domain_cfg["bm25_path"]
    return scoped


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in TOKEN_RE.findall(text.replace("-", "_").replace("/", " ")):
        lowered = token.lower()
        tokens.append(lowered)
        if "_" in lowered:
            tokens.extend(part for part in lowered.split("_") if len(part) > 1)
        camel_parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", token).split()
        tokens.extend(part.lower() for part in camel_parts if len(part) > 1)
    return tokens


def _bm25_path(config: dict[str, Any]) -> Path:
    return Path(config["storage"].get("bm25_path", _root(config) / "rag" / "cache" / "bm25_chunks.jsonl"))


def _qdrant_mode(config: dict[str, Any]) -> str:
    return str(config["storage"].get("qdrant_mode", "local")).lower()


def _qdrant_location(config: dict[str, Any]) -> str:
    if _qdrant_mode(config) == "server":
        return str(config["storage"].get("qdrant_url", "http://127.0.0.1:6333"))
    return str(config["storage"]["qdrant_path"])


def _qdrant_client(config: dict[str, Any]) -> Any:
    from qdrant_client import QdrantClient

    if _qdrant_mode(config) == "server":
        timeout = float(config["storage"].get("qdrant_timeout", 300))
        return QdrantClient(url=str(config["storage"].get("qdrant_url", "http://127.0.0.1:6333")), timeout=timeout)

    qdrant_path = Path(config["storage"]["qdrant_path"])
    qdrant_path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(qdrant_path))


def _qdrant_status(config: dict[str, Any]) -> dict[str, Any]:
    if not _has_module("qdrant_client"):
        return {"available": False, "error": "qdrant-client is not installed"}
    client = None
    try:
        client = _qdrant_client(config)
        collections = client.get_collections()
        names = [collection.name for collection in collections.collections]
        return {
            "available": True,
            "mode": _qdrant_mode(config),
            "location": _qdrant_location(config),
            "collections": names,
            "collection_exists": config["project"]["collection"] in names,
        }
    except Exception as exc:
        return {
            "available": False,
            "mode": _qdrant_mode(config),
            "location": _qdrant_location(config),
            "error": str(exc),
        }
    finally:
        if client is not None:
            client.close()


def _write_bm25_cache(config: dict[str, Any], nodes: list[Any]) -> int:
    path = _bm25_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for node in nodes:
            text = node.get_text()
            metadata = dict(node.metadata or {})
            chunk_id = hashlib.sha256(
                f"{metadata.get('path')}::{text[:800]}".encode("utf-8", errors="ignore")
            ).hexdigest()
            record = {
                "id": chunk_id,
                "path": metadata.get("path"),
                "module": metadata.get("module"),
                "text": text,
                "tokens": _tokenize(text + " " + str(metadata.get("path") or "")),
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def _load_bm25_cache(config: dict[str, Any]) -> list[dict[str, Any]]:
    path = _bm25_path(config)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _bm25_search(config: dict[str, Any], question: str) -> list[dict[str, Any]]:
    records = _load_bm25_cache(config)
    if not records:
        return []

    query_terms = _tokenize(question)
    if not query_terms:
        return []

    avgdl = sum(len(record.get("tokens", [])) for record in records) / max(len(records), 1)
    doc_freq: dict[str, int] = {}
    for record in records:
        for term in set(record.get("tokens", [])):
            doc_freq[term] = doc_freq.get(term, 0) + 1

    k1 = 1.5
    b = 0.75
    total_docs = len(records)
    scored: list[dict[str, Any]] = []
    for record in records:
        tokens = record.get("tokens", [])
        if not tokens:
            continue
        freqs: dict[str, int] = {}
        for token in tokens:
            freqs[token] = freqs.get(token, 0) + 1
        score = 0.0
        doc_len = len(tokens)
        for term in query_terms:
            tf = freqs.get(term, 0)
            if tf == 0:
                continue
            idf = math.log(1 + (total_docs - doc_freq.get(term, 0) + 0.5) / (doc_freq.get(term, 0) + 0.5))
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / max(avgdl, 1)))
        if score > 0:
            scored.append(
                {
                    "score": score,
                    "path": record.get("path"),
                    "module": record.get("module"),
                    "text": record.get("text", "")[:1200],
                    "source": "bm25",
                }
            )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[: int(config["retrieval"].get("bm25_top_k", 12))]


def _normalize_scores(items: list[dict[str, Any]], score_key: str = "score") -> list[dict[str, Any]]:
    if not items:
        return items
    max_score = max(float(item.get(score_key) or 0) for item in items) or 1.0
    for item in items:
        item["normalized_score"] = float(item.get(score_key) or 0) / max_score
    return items


def _intent_boost(question: str, item: dict[str, Any]) -> float:
    query = set(_tokenize(question))
    path = str(item.get("path") or "").lower()
    compact_query = "".join(sorted(query))
    compact_path = path.replace("_", "").replace("-", "").replace("/", "").replace(".", "")
    boost = 0.0

    if "frontend" in query and path.startswith("frontend/"):
        boost += 0.35
    if "frontend" in query and path.startswith("backend/"):
        boost -= 0.75
    if "backend" in query and path.startswith("backend/"):
        boost += 0.35
    if "backend" in query and path.startswith("frontend/"):
        boost -= 0.75
    if {"page", "renders", "render", "tsx", "component"} & query and "frontend/src/pages/" in path:
        boost += 0.35
    if {"router", "endpoint", "api"} & query and "backend/routers/" in path:
        boost += 0.25
    if {"service", "services"} & query and "backend/services/" in path:
        boost += 0.2

    path_tokens = set(_tokenize(path))
    direct_overlap = len(query & path_tokens)
    boost += min(direct_overlap * 0.08, 0.4)
    if {"alpha", "lab"} <= query and "alphalab" in compact_path:
        boost += 0.9
    if {"wallet", "analyzer"} <= query and "walletanalyzer" in compact_path:
        boost += 0.9
    if {"dashboard"} <= query and "dashboard" in compact_path:
        boost += 0.7
    if {"arkham"} <= query and "arkham" in compact_path:
        boost += 0.45
    if {"aster"} & query and ("backend/services/onchain/aster/" in path or path.startswith("docs/aster") or path.startswith("docs/core-equity-aster")):
        boost += 0.85
    if {"rl", "policy", "reinforcement", "lane"} & query and "asterrllanepolicy" in compact_path:
        boost += 1.1
    if {"backtest", "strategy", "discovery"} & query and "backteststrategydiscovery" in compact_path:
        boost += 0.9
    if {"domain", "domains", "backend", "frontend", "data", "memory", "aster"} & query and path == "rag/config/rag.yaml":
        boost += 0.6
    if {"seed", "ingestion"} <= query and "seedingestion" in compact_path:
        boost += 1.1
    if {"chunk", "embeddings", "qdrant", "llama", "settings", "configured"} & query and path == "rag/config/rag.yaml":
        boost += 1.25
    if {"daily", "commands", "qdrant", "rtx", "3070", "settings", "playbook"} & query and path == "rag/memory/rag_operating_playbook.md":
        boost += 1.4
    return boost


def _fuse_results(config: dict[str, Any], vector_items: list[dict[str, Any]], bm25_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vector_weight = float(config["retrieval"].get("vector_weight", 0.58))
    bm25_weight = float(config["retrieval"].get("bm25_weight", 0.42))
    fused: dict[str, dict[str, Any]] = {}

    for item in _normalize_scores(vector_items):
        key = hashlib.sha256(f"{item.get('path')}::{item.get('text', '')[:500]}".encode("utf-8", errors="ignore")).hexdigest()
        fused[key] = {
            **item,
            "fusion_score": item.get("normalized_score", 0.0) * vector_weight + _intent_boost(config.get("_question", ""), item),
            "sources": ["vector"],
        }

    for item in _normalize_scores(bm25_items):
        key = hashlib.sha256(f"{item.get('path')}::{item.get('text', '')[:500]}".encode("utf-8", errors="ignore")).hexdigest()
        if key in fused:
            fused[key]["fusion_score"] += item.get("normalized_score", 0.0) * bm25_weight
            fused[key]["sources"].append("bm25")
        else:
            fused[key] = {
                **item,
                "fusion_score": item.get("normalized_score", 0.0) * bm25_weight + _intent_boost(config.get("_question", ""), item),
                "sources": ["bm25"],
            }

    results = sorted(fused.values(), key=lambda item: item["fusion_score"], reverse=True)
    return results[: int(config["retrieval"].get("fusion_top_k", 12))]


def _retrieve_hybrid(config: dict[str, Any], question: str) -> tuple[list[dict[str, Any]], str | None]:
    config["_question"] = question
    try:
        from llama_index.core import Settings, VectorStoreIndex
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        from llama_index.vector_stores.qdrant import QdrantVectorStore
    except ImportError as exc:
        raise SystemExit("Missing RAG packages. Run the install command from docs/rag-hardcore-setup.md.") from exc

    Settings.embed_model = HuggingFaceEmbedding(
        model_name=config["embeddings"]["model"],
        device=_embedding_device(config),
        embed_batch_size=int(config["embeddings"].get("batch_size", 32)),
    )

    vector_payload = []
    vector_error = None
    seen_chunks: set[str] = set()
    client = None
    try:
        client = _qdrant_client(config)
        vector_store = QdrantVectorStore(client=client, collection_name=config["project"]["collection"])
        index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
        retriever = index.as_retriever(similarity_top_k=int(config["retrieval"]["similarity_top_k"]))
        nodes = retriever.retrieve(question)

        for node in nodes:
            text = node.node.get_text()[:1200]
            chunk_key = hashlib.sha256(
                f"{node.node.metadata.get('path')}::{text[:500]}".encode("utf-8", errors="ignore")
            ).hexdigest()
            if chunk_key in seen_chunks:
                continue
            seen_chunks.add(chunk_key)
            vector_payload.append(
                {
                    "score": node.score,
                    "path": node.node.metadata.get("path"),
                    "module": node.node.metadata.get("module"),
                    "text": text,
                    "source": "vector",
                }
            )
    except Exception as exc:
        vector_error = str(exc)
    finally:
        if client is not None:
            client.close()

    bm25_payload = _bm25_search(config, question)
    payload = _fuse_results(config, vector_payload, bm25_payload)[: int(config["retrieval"]["response_top_k"])]
    return payload, vector_error


def _build_rag_prompt(question: str, matches: list[dict[str, Any]]) -> str:
    context_blocks = []
    for index, match in enumerate(matches, start=1):
        context_blocks.append(
            "\n".join(
                [
                    f"[Source {index}] {match.get('path')}",
                    str(match.get("text") or "").strip(),
                ]
            )
        )

    context = "\n\n---\n\n".join(context_blocks)
    return f"""You are Core Equity's local coding RAG assistant.
Answer only from the provided repository context.
If the context is insufficient, say exactly what is missing.
Always cite source paths inline.
Prefer concise, actionable engineering guidance.

Question:
{question}

Repository context:
{context}
"""


def _call_llama_cpp(
    config: dict[str, Any],
    prompt: str,
    *,
    max_tokens: int | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    llama_config = config.get("llama_cpp", {})
    api_base = str(llama_config.get("api_base", "http://127.0.0.1:8080/v1")).rstrip("/")
    url = f"{api_base}/chat/completions"
    payload = {
        "model": llama_config.get("chat_model", "qwen3.5-9b"),
        "messages": [
            {"role": "system", "content": "You are a precise local coding assistant for the Core Equity repo."},
            {"role": "user", "content": prompt},
        ],
        "temperature": float(llama_config.get("temperature", 0.15)),
        "max_tokens": int(max_tokens if max_tokens is not None else llama_config.get("max_tokens", 4096)),
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=int(timeout if timeout is not None else llama_config.get("timeout_seconds", 180))) as response:
        return json.loads(response.read().decode("utf-8"))


def _clean_llm_answer(text: str) -> str:
    text = re.sub(r"<think>\s*</think>\s*", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def _llama_cpp_status(config: dict[str, Any]) -> dict[str, Any]:
    llama_config = config.get("llama_cpp", {})
    api_base = str(llama_config.get("api_base", "http://127.0.0.1:8080/v1")).rstrip("/")
    url = f"{api_base}/models"
    try:
        request = urllib.request.Request(url, headers={"Authorization": "Bearer local"})
        with urllib.request.urlopen(request, timeout=2) as response:
            server_header = response.headers.get("Server")
            payload = json.loads(response.read().decode("utf-8"))
        return {
            "available": True,
            "api_base": api_base,
            "server": server_header,
            "backend": llama_config.get("backend", "unknown"),
            "configured_model": llama_config.get("chat_model", "qwen3.5-9b"),
            "models": [item.get("id") for item in payload.get("data", []) if isinstance(item, dict)],
        }
    except Exception as exc:
        return {
            "available": False,
            "api_base": api_base,
            "configured_model": llama_config.get("chat_model", "qwen3.5-9b"),
            "error": str(exc),
        }


def _as_posix_relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _is_excluded(path: Path, root: Path, config: dict[str, Any]) -> bool:
    rel = _as_posix_relative(path, root)
    parts = set(Path(rel).parts)

    for excluded_dir in config.get("exclude_dirs", []):
        normalized = excluded_dir.replace("\\", "/").strip("/")
        if normalized in parts or rel == normalized or rel.startswith(normalized + "/"):
            return True

    return any(fnmatch.fnmatch(rel, pattern) for pattern in config.get("exclude_globs", []))


def collect_files(config: dict[str, Any]) -> list[Path]:
    root = _root(config)
    seen: set[Path] = set()

    for pattern in config.get("include", []):
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            if _is_excluded(path, root, config):
                continue
            seen.add(path.resolve())

    return sorted(seen)


def file_metadata(path: Path, root: Path) -> dict[str, Any]:
    rel = _as_posix_relative(path, root)
    text_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "path": rel,
        "extension": path.suffix.lower(),
        "module": rel.split("/")[0] if "/" in rel else "root",
        "sha256": text_hash,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }


def _manifest_path(config: dict[str, Any]) -> Path:
    domain = str(config.get("_domain", "full"))
    return _root(config) / "rag" / "sources" / f"project_manifest_{domain}.json"


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _index_freshness(config: dict[str, Any], files: list[Path]) -> dict[str, Any]:
    root = _root(config)
    manifest_path = _manifest_path(config)
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    indexed_at = _parse_dt(manifest.get("indexed_at"))
    latest_mtime = 0.0
    stale_files: list[dict[str, Any]] = []
    for path in files:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        latest_mtime = max(latest_mtime, mtime)
        if indexed_at and mtime > indexed_at.timestamp() + 1:
            stale_files.append(
                {
                    "path": _as_posix_relative(path, root),
                    "modified_at": datetime.fromtimestamp(mtime, timezone.utc).isoformat(),
                }
            )
    latest_modified_at = datetime.fromtimestamp(latest_mtime, timezone.utc).isoformat() if latest_mtime else None
    stale_files.sort(key=lambda item: str(item["modified_at"]), reverse=True)
    return {
        "manifest_path": str(manifest_path),
        "manifest_exists": manifest_path.exists(),
        "indexed_at": indexed_at.isoformat() if indexed_at else None,
        "latest_source_modified_at": latest_modified_at,
        "is_stale": (not indexed_at and bool(files)) or bool(stale_files),
        "stale_file_count": len(stale_files) if indexed_at else len(files),
        "stale_files_preview": stale_files[:10] if indexed_at else [],
    }


def _refresh_generated_project_map() -> dict[str, Any]:
    try:
        from build_project_map import OUT, build_markdown

        OUT.write_text(build_markdown(), encoding="utf-8")
        return {"ok": True, "path": str(OUT)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:500]}


def command_health(_: argparse.Namespace) -> int:
    raw_config = _load_yaml(CONFIG_PATH)
    config = apply_domain(raw_config, getattr(_, "domain", None))
    root = _root(config)
    files = collect_files(config)
    required = {
        "llama_index": "llama-index",
        "qdrant_client": "qdrant-client",
        "llama_index.vector_stores.qdrant": "llama-index-vector-stores-qdrant",
        "llama_index.embeddings.huggingface": "llama-index-embeddings-huggingface",
        "yaml": "pyyaml",
    }
    modules = {module: _has_module(module) for module in required}

    report = {
        "config": str(CONFIG_PATH),
        "root": str(root),
        "root_exists": root.exists(),
        "files_indexable": len(files),
        "packages": modules,
        "missing_packages": [required[m] for m, ok in modules.items() if not ok],
        "qdrant_path": config["storage"]["qdrant_path"],
        "qdrant_mode": _qdrant_mode(config),
        "qdrant_location": _qdrant_location(config),
        "qdrant_status": _qdrant_status(config),
        "bm25_path": str(_bm25_path(config)),
        "bm25_ready": _bm25_path(config).exists(),
        "collection": config["project"]["collection"],
        "domain": config.get("_domain", "full"),
        "available_domains": domain_names(raw_config),
        "embedding_model": config["embeddings"]["model"],
        "embedding_device": _embedding_device(config),
        "llama_cpp_status": _llama_cpp_status(config),
        "chunk_size": config["chunking"]["chunk_size"],
        "chunk_overlap": config["chunking"]["chunk_overlap"],
        "freshness": _index_freshness(config, files),
    }
    print_json(report)
    return 0 if report["root_exists"] else 1


def command_ingest(args: argparse.Namespace) -> int:
    raw_config = _load_yaml(CONFIG_PATH)
    project_map = {"ok": None, "skipped": bool(args.dry_run)}
    if not args.dry_run:
        project_map = _refresh_generated_project_map()
    if args.domain == "all":
        results = []
        for domain in domain_names(raw_config):
            scoped_args = argparse.Namespace(**{**vars(args), "domain": domain})
            results.append(_ingest_domain(raw_config, scoped_args))
        print_json({"mode": "multi-domain", "project_map": project_map, "domains": results})
        return 0

    result = _ingest_domain(raw_config, args)
    result["project_map"] = project_map
    print_json(result)
    return 0


def _ingest_domain(raw_config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    config = apply_domain(raw_config, getattr(args, "domain", None))
    root = _root(config)
    files = collect_files(config)

    if args.dry_run:
        preview = [_as_posix_relative(path, root) for path in files[:50]]
        return {
            "mode": "dry-run",
            "domain": config.get("_domain", "full"),
            "collection": config["project"]["collection"],
            "bm25_path": str(_bm25_path(config)),
            "count": len(files),
            "preview": preview,
        }

    try:
        from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
        from llama_index.core.node_parser import SentenceSplitter
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        from llama_index.vector_stores.qdrant import QdrantVectorStore
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise SystemExit("Missing RAG packages. Run the install command from docs/rag-hardcore-setup.md.") from exc

    Settings.embed_model = HuggingFaceEmbedding(
        model_name=config["embeddings"]["model"],
        device=_embedding_device(config),
        embed_batch_size=int(config["embeddings"].get("batch_size", 32)),
    )
    Settings.text_splitter = SentenceSplitter(
        chunk_size=int(config["chunking"]["chunk_size"]),
        chunk_overlap=int(config["chunking"]["chunk_overlap"]),
    )

    documents: list[Document] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text.strip():
            continue
        documents.append(Document(text=text, metadata=file_metadata(path, root)))

    nodes = Settings.text_splitter.get_nodes_from_documents(documents)
    bm25_count = _write_bm25_cache(config, nodes)

    client = _qdrant_client(config)
    collection_name = config["project"]["collection"]
    if not args.append and client.collection_exists(collection_name):
        client.delete_collection(collection_name)

    vector_store = QdrantVectorStore(
        client=client,
        collection_name=collection_name,
    )
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    VectorStoreIndex(nodes, storage_context=storage_context, show_progress=True)

    domain = str(config.get("_domain", "full"))
    manifest_dir = root / "rag" / "sources"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"project_manifest_{domain}.json"
    manifest = {
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "collection": config["project"]["collection"],
        "document_count": len(documents),
        "file_count": len(files),
        "chunk_count": len(nodes),
        "bm25_chunk_count": bm25_count,
        "qdrant_mode": _qdrant_mode(config),
        "qdrant_location": _qdrant_location(config),
        "embedding_model": config["embeddings"]["model"],
        "embedding_device": _embedding_device(config),
        "chunk_size": config["chunking"]["chunk_size"],
        "chunk_overlap": config["chunking"]["chunk_overlap"],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if domain == "full":
        (manifest_dir / "project_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    client.close()
    return manifest


def command_query(args: argparse.Namespace) -> int:
    config = apply_domain(_load_yaml(CONFIG_PATH), args.domain)
    payload, vector_error = _retrieve_hybrid(config, args.question)
    response = {
        "question": args.question,
        "mode": "hybrid_vector_bm25",
        "domain": config.get("_domain", "full"),
        "collection": config["project"]["collection"],
        "matches": payload,
    }
    if vector_error:
        response["vector_warning"] = "Qdrant local is locked; served BM25 fallback."
        response["vector_error"] = vector_error
    print_json(response)
    return 0


def command_ask(args: argparse.Namespace) -> int:
    config = apply_domain(_load_yaml(CONFIG_PATH), args.domain)
    matches, vector_error = _retrieve_hybrid(config, args.question)
    prompt = _build_rag_prompt(args.question, matches)
    unique_sources = list(dict.fromkeys(str(match.get("path")) for match in matches if match.get("path")))
    response: dict[str, Any] = {
        "question": args.question,
        "mode": "rag_llama_cpp",
        "domain": config.get("_domain", "full"),
        "collection": config["project"]["collection"],
        "sources": unique_sources,
    }
    if vector_error:
        response["vector_warning"] = "Vector retrieval failed; answer uses BM25/vector fallback context."
        response["vector_error"] = vector_error
    if args.prompt_only:
        response["prompt"] = prompt
        print_json(response)
        return 0

    try:
        completion = _call_llama_cpp(config, prompt)
        message = completion["choices"][0]["message"]
        response["answer"] = _clean_llm_answer(message.get("content") or message.get("reasoning_content") or "")
        response["model"] = completion.get("model")
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
        response["llm_error"] = str(exc)
        response["hint"] = "Start llama-server on the configured llama_cpp.api_base, or rerun with --prompt-only."
        response["prompt"] = prompt

    print_json(response)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Core Equity local RAG tool")
    subcommands = parser.add_subparsers(dest="command", required=True)

    health = subcommands.add_parser("health")
    health.add_argument("--domain", default=None, help="RAG domain to inspect, e.g. full/backend/frontend/data/memory.")

    ingest = subcommands.add_parser("ingest")
    ingest.add_argument("--dry-run", action="store_true")
    ingest.add_argument("--domain", default=None, help="RAG domain to ingest, or 'all' for every configured domain.")
    ingest.add_argument(
        "--append",
        action="store_true",
        help="Append to the existing collection instead of rebuilding it.",
    )

    query = subcommands.add_parser("query")
    query.add_argument("question")
    query.add_argument("--domain", default=None, help="RAG domain to query.")

    ask = subcommands.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--domain", default=None, help="RAG domain to ask.")
    ask.add_argument("--prompt-only", action="store_true")

    args = parser.parse_args()
    if args.command == "health":
        return command_health(args)
    if args.command == "ingest":
        return command_ingest(args)
    if args.command == "query":
        return command_query(args)
    if args.command == "ask":
        return command_ask(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
