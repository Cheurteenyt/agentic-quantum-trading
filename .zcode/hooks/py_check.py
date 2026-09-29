#!/usr/bin/env python3
"""Hook PostToolUse (matcher Edit|Write) : py_compile immédiat de tout .py
édité — l'erreur de syntaxe remonte à l'agent DANS le tour (exit 2), pas au
prochain lancement du script. Silencieux (exit 0) sinon. Zéro réseau."""
import json, os, subprocess, sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
fp = (data.get("tool_input") or {}).get("file_path") or ""
if not fp.endswith(".py") or not os.path.exists(fp):
    sys.exit(0)
r = subprocess.run([sys.executable, "-m", "py_compile", fp],
                   capture_output=True, text=True, timeout=30)
if r.returncode != 0:
    print("PY_COMPILE FAIL — " + fp + " :\n" + (r.stderr or r.stdout)[:1500])
    sys.exit(2)
sys.exit(0)
