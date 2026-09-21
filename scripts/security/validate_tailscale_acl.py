from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _strip_hujson_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        lines.append(re.sub(r"\s//.*$", "", line))
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_tailscale_acl.py <policy.hujson>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    data = json.loads(_strip_hujson_comments(path.read_text(encoding="utf-8")))
    acls = data.get("acls") or []
    problems: list[str] = []

    for idx, rule in enumerate(acls, start=1):
        src = rule.get("src") or []
        dst = rule.get("dst") or []
        if "*" in src and any(target in {"*:*", "*"} for target in dst):
            problems.append(f"rule {idx}: global allow '* -> *:*' is forbidden")
        for target in dst:
            if target.endswith(":*") and "autogroup:admin" not in src:
                problems.append(f"rule {idx}: non-admin wildcard destination port: {target}")
            if target in {"100.114.51.121:*", "*:*"} and "autogroup:admin" not in src:
                problems.append(f"rule {idx}: client access is broader than TCP 8000: {target}")

    if problems:
        print("ACL validation failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print(f"ACL validation passed: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
