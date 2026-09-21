from __future__ import annotations

import ast
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend" / "src"
OUT = ROOT / "rag" / "memory" / "generated_project_map.md"

ROUTE_RE = re.compile(r"@router\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']")
API_CALL_RE = re.compile(
    r"(?:api\.)?(?:get|post|put|patch|delete)<[^>]*>?\(\s*[\"']([^\"']+)[\"']|"
    r"(?:api\.)?(?:get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']|"
    r"fetch\(\s*[\"']([^\"']+)[\"']"
)
TO_THREAD_RE = re.compile(r"asyncio\.to_thread\(\s*([A-Za-z_][A-Za-z0-9_]*)")
DIRECT_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\(")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def iter_files(base: Path, patterns: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(base.glob(pattern))
    return sorted({path for path in files if path.is_file() and "__pycache__" not in path.parts})


def py_functions(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return set()
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def service_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for path in iter_files(BACKEND / "services", ("*.py",)):
        for name in py_functions(path):
            index.setdefault(name, rel(path))
    return index


def parse_router(path: Path, services: dict[str, str]) -> list[dict[str, object]]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    routes: list[dict[str, object]] = []
    for i, line in enumerate(lines):
        match = ROUTE_RE.search(line)
        if not match:
            continue
        method, route_path = match.groups()
        func_name = ""
        body_lines: list[str] = []
        requires_admin = False
        for j in range(i + 1, min(i + 80, len(lines))):
            current = lines[j]
            if "@router." in current and j > i + 1:
                break
            if "Depends(_require_data_admin)" in current:
                requires_admin = True
            def_match = re.search(r"async\s+def\s+([A-Za-z_][A-Za-z0-9_]*)", current)
            if def_match and not func_name:
                func_name = def_match.group(1)
            body_lines.append(current)
        body = "\n".join(body_lines)
        called = []
        for call in TO_THREAD_RE.findall(body):
            if call in services and call not in called:
                called.append(call)
        for call in DIRECT_CALL_RE.findall(body):
            if call in services and call not in called and call != func_name:
                called.append(call)
        routes.append(
            {
                "method": method.upper(),
                "path": route_path,
                "handler": func_name or "?",
                "admin": requires_admin,
                "services": called[:8],
            }
        )
    return routes


def frontend_calls() -> dict[str, list[str]]:
    calls: dict[str, list[str]] = defaultdict(list)
    for path in iter_files(FRONTEND, ("**/*.ts", "**/*.tsx")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in API_CALL_RE.finditer(text):
            endpoint = next((group for group in match.groups() if group), "")
            if not endpoint:
                continue
            if endpoint.startswith(("http://", "https://")):
                continue
            normalized = endpoint if endpoint.startswith("/") else f"/{endpoint}"
            if rel(path) not in calls[normalized]:
                calls[normalized].append(rel(path))
    return dict(sorted(calls.items()))


def route_groups(routes_by_file: dict[str, list[dict[str, object]]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for router_file, routes in routes_by_file.items():
        for route in routes:
            first = str(route["path"]).strip("/").split("/", 1)[0] or "root"
            groups[first].append(f"{route['method']} {route['path']} ({router_file}:{route['handler']})")
    return dict(sorted(groups.items()))


def build_markdown() -> str:
    services = service_index()
    router_files = iter_files(BACKEND / "routers", ("*.py",))
    routes_by_file = {rel(path): parse_router(path, services) for path in router_files}
    calls = frontend_calls()
    groups = route_groups(routes_by_file)

    lines: list[str] = []
    lines.append("# Generated Project Map")
    lines.append("")
    lines.append(f"Generated at: `{datetime.now(timezone.utc).isoformat()}`")
    lines.append("")
    lines.append("Purpose: give Core Equity RAG a compact operating map for long coding sessions.")
    lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    lines.append("- Follow `Frontend -> API -> Router -> Service -> Data` before patching.")
    lines.append("- Treat `label_candidates` as untrusted until strict admin promotion.")
    lines.append("- Treat `label_candidate_evidence` as evidence bundles, not trusted labels.")
    lines.append("- Treat `wallet_chain_state` as observed RPC/explorer state with source attribution.")
    lines.append("- Treat `data_jobs` as the audit trail for automated ingestion/enrichment/corroboration.")
    lines.append("- Any endpoint with `Depends(_require_data_admin)` requires `CORE_ADMIN_TOKEN`.")
    lines.append("")
    lines.append("## Router Surface")
    lines.append("")
    for router_file, routes in sorted(routes_by_file.items()):
        lines.append(f"### `{router_file}`")
        if not routes:
            lines.append("- No router endpoints detected.")
            continue
        for route in routes:
            admin = " admin" if route["admin"] else " read"
            service_bits = ", ".join(f"`{name}`" for name in route["services"]) or "no direct service detected"
            lines.append(f"- `{route['method']} {route['path']}` -> `{route['handler']}` [{admin}] -> {service_bits}")
        lines.append("")
    lines.append("## Endpoint Groups")
    lines.append("")
    for group, items in groups.items():
        lines.append(f"### `{group}`")
        for item in items[:20]:
            lines.append(f"- {item}")
        if len(items) > 20:
            lines.append(f"- ... {len(items) - 20} more")
        lines.append("")
    lines.append("## Frontend API Calls")
    lines.append("")
    if not calls:
        lines.append("- No frontend API calls detected by static regex.")
    for endpoint, files in calls.items():
        files_str = ", ".join(f"`{file}`" for file in files[:6])
        suffix = f" (+{len(files) - 6} more)" if len(files) > 6 else ""
        lines.append(f"- `{endpoint}` <- {files_str}{suffix}")
    lines.append("")
    lines.append("## Service Function Index")
    lines.append("")
    by_file: dict[str, list[str]] = defaultdict(list)
    for func, path in sorted(services.items()):
        by_file[path].append(func)
    for path, funcs in sorted(by_file.items()):
        preview = ", ".join(f"`{name}`" for name in funcs[:18])
        suffix = f", ... +{len(funcs) - 18}" if len(funcs) > 18 else ""
        lines.append(f"- `{path}`: {preview}{suffix}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_markdown(), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
