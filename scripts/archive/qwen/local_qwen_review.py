from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SERVER_EXE = Path(r"D:\ik_llama.cpp\build\bin\llama-server.exe")
QWEN30_MOE = Path(r"D:\llama-server\models\moe\Qwen3-30B-A3B-UD-Q4_K_XL.gguf")
QWEN30_CODER = Path(r"D:\llama-server\models\moe\Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf")
QWEN30_2507 = Path(r"D:\llama-server\models\moe\Qwen3-30B-A3B-Instruct-2507-UD-Q4_K_XL.gguf")
QWEN35_A3B = Path(r"D:\llama-server\models\moe\Qwen3.5-35B-A3B-UD-IQ4_XS.gguf")
QWEN25 = Path(r"D:\llama-server\models\Qwen 2.5 Instruct\Qwen2.5-7B-Instruct-Q5_K_M.gguf")
LOG_DIR = Path(r"D:\ik_llama.cpp")


PROFILES: dict[str, dict[str, Any]] = {
    "moe-fast": {
        "model": QWEN30_MOE,
        "ctx": "4096",
        "cache_ram": "8192",
        "batch": "256",
        "ubatch": "256",
        "extra": ["--cpu-moe", "-ngl", "99"],
        "timeout": 180,
    },
    "moe-fast-kvq": {
        "model": QWEN30_MOE,
        "ctx": "4096",
        "cache_ram": "8192",
        "batch": "256",
        "ubatch": "256",
        "extra": [
            "--cpu-moe",
            "-ngl",
            "99",
            "--cache-type-k",
            "q4_1",
            "--cache-type-v",
            "q4_1",
        ],
        "timeout": 180,
    },
    "moe-fast-partial-moe": {
        "model": QWEN30_MOE,
        "ctx": "4096",
        "cache_ram": "8192",
        "batch": "256",
        "ubatch": "256",
        "extra": ["--n-cpu-moe", "44", "-ngl", "99"],
        "timeout": 180,
    },
    "qwen3-coder-fast": {
        "model": QWEN30_CODER,
        "ctx": "4096",
        "cache_ram": "8192",
        "batch": "256",
        "ubatch": "256",
        "extra": ["--cpu-moe", "-ngl", "99"],
        "timeout": 240,
    },
    "qwen3-coder-kvq": {
        "model": QWEN30_CODER,
        "ctx": "4096",
        "cache_ram": "8192",
        "batch": "256",
        "ubatch": "256",
        "extra": [
            "--cpu-moe",
            "-ngl",
            "99",
            "--cache-type-k",
            "q4_1",
            "--cache-type-v",
            "q4_1",
        ],
        "timeout": 240,
    },
    "qwen3-2507-fast": {
        "model": QWEN30_2507,
        "ctx": "4096",
        "cache_ram": "8192",
        "batch": "256",
        "ubatch": "256",
        "extra": ["--cpu-moe", "-ngl", "99"],
        "timeout": 240,
    },
    "qwen35-a3b-fast": {
        "model": QWEN35_A3B,
        "ctx": "4096",
        "cache_ram": "8192",
        "batch": "256",
        "ubatch": "256",
        "extra": ["--cpu-moe", "-ngl", "99"],
        "timeout": 300,
    },
    "moe-deep": {
        "model": QWEN30_MOE,
        "ctx": "8192",
        "cache_ram": "8192",
        "batch": "256",
        "ubatch": "256",
        "extra": ["--cpu-moe", "-ngl", "99"],
        "timeout": 300,
    },
    "moe-deep-kvq": {
        "model": QWEN30_MOE,
        "ctx": "8192",
        "cache_ram": "8192",
        "batch": "256",
        "ubatch": "256",
        "extra": [
            "--cpu-moe",
            "-ngl",
            "99",
            "--cache-type-k",
            "q4_1",
            "--cache-type-v",
            "q4_1",
        ],
        "timeout": 300,
    },
    "qwen25-fast": {
        "model": QWEN25,
        "ctx": "4096",
        "cache_ram": "4096",
        "batch": "256",
        "ubatch": "256",
        "extra": ["--fit"],
        "timeout": 120,
    },
}


def _strip_think(text: str) -> str:
    cleaned = re.sub(r"<think>\s*</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<think>.*\Z", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.strip()


def _server_running() -> bool:
    req = urllib.request.Request("http://127.0.0.1:8080/health", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def _start_server(profile_name: str, profile: dict[str, Any]) -> subprocess.Popen[Any]:
    model = Path(profile["model"])
    if not SERVER_EXE.exists():
        raise SystemExit(f"llama-server missing: {SERVER_EXE}")
    if not model.exists():
        raise SystemExit(f"model missing: {model}")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stdout_path = LOG_DIR / f"local_qwen_review_{profile_name}_stdout.log"
    stderr_path = LOG_DIR / f"local_qwen_review_{profile_name}_stderr.log"
    stdout = stdout_path.open("w", encoding="utf-8", errors="replace")
    stderr = stderr_path.open("w", encoding="utf-8", errors="replace")

    args = [
        str(SERVER_EXE),
        "-m",
        str(model),
        "--host",
        "127.0.0.1",
        "--port",
        "8080",
        "-c",
        str(profile["ctx"]),
        "--flash-attn",
        "on",
        "--cache-ram",
        str(profile["cache_ram"]),
        "--threads",
        "8",
        "--batch-size",
        str(profile["batch"]),
        "--ubatch-size",
        str(profile["ubatch"]),
        "--reasoning",
        "off",
        "--reasoning-budget",
        "0",
        "--reasoning-tokens",
        "none",
        "--chat-template-kwargs",
        '{"enable_thinking":false}',
        *profile["extra"],
    ]
    return subprocess.Popen(args, stdout=stdout, stderr=stderr)


def _wait_ready(proc: subprocess.Popen[Any] | None, seconds: int) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _server_running():
            return
        if proc is not None and proc.poll() is not None:
            raise SystemExit(f"local qwen server exited early with code {proc.returncode}")
        time.sleep(2)
    raise SystemExit("local qwen server did not become ready in time")


def _read_task(args: argparse.Namespace) -> str:
    chunks: list[str] = []
    if args.prompt:
        chunks.append(args.prompt)
    for symbol_arg in args.symbol or []:
        path_text, _, symbol = symbol_arg.rpartition(":")
        if not path_text or not symbol:
            raise SystemExit("--symbol must use PATH:SYMBOL")
        path = Path(path_text)
        chunks.append(f"[symbol: {symbol_arg}]\n{_extract_symbol_snippet(path, symbol, args.symbol_context)}")
    for grep_arg in args.grep or []:
        path_text, _, pattern = grep_arg.rpartition(":")
        if not path_text or not pattern:
            raise SystemExit("--grep must use PATH:PATTERN")
        path = Path(path_text)
        chunks.append(f"[grep: {grep_arg}]\n{_extract_grep_snippets(path, pattern, args.grep_context, args.max_grep_hits)}")
    for file_arg in args.file or []:
        path = Path(file_arg)
        text = path.read_text(encoding="utf-8", errors="replace")
        if args.max_file_chars > 0:
            text = text[: args.max_file_chars]
        chunks.append(f"[file: {path}]\n{text}")
    task = "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip())
    if not task:
        raise SystemExit("Provide --prompt and/or --file.")
    return task


def _extract_symbol_snippet(path: Path, symbol: str, context: int) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    pattern = re.compile(rf"\b(def|class)\s+{re.escape(symbol)}\b|{re.escape(symbol)}\s*=")
    hit = next((idx for idx, line in enumerate(lines) if pattern.search(line)), None)
    if hit is None:
        return f"symbol not found in {path}: {symbol}"
    start = max(0, hit - max(0, context))
    end = min(len(lines), hit + max(20, context * 4))
    return "\n".join(f"{idx + 1}: {lines[idx]}" for idx in range(start, end))


def _extract_grep_snippets(path: Path, pattern: str, context: int, max_hits: int) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    hits = [idx for idx, line in enumerate(lines) if pattern.lower() in line.lower()]
    if not hits:
        return f"pattern not found in {path}: {pattern}"
    blocks: list[str] = []
    for hit in hits[: max(1, max_hits)]:
        start = max(0, hit - max(0, context))
        end = min(len(lines), hit + context + 1)
        blocks.append("\n".join(f"{idx + 1}: {lines[idx]}" for idx in range(start, end)))
    return "\n\n---\n\n".join(blocks)


def _call_qwen(prompt: str, timeout: int, max_tokens: int) -> str:
    payload = {
        "model": "local-qwen-review",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Tu es un reviewer backend local read-only. "
                    "Ne montre jamais ton raisonnement interne. "
                    "Cherche incoherences, effets de bord DB, writes non voulus, tests manquants. "
                    "Codex garde la decision finale."
                ),
            },
            {"role": "user", "content": "/no_think\n" + prompt},
        ],
        "temperature": 0.1,
        "top_p": 0.8,
        "top_k": 20,
        "presence_penalty": 0.2,
        "frequency_penalty": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
    }
    req = urllib.request.Request(
        "http://127.0.0.1:8080/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    message = data["choices"][0]["message"]
    return _strip_think(str(message.get("content") or message.get("reasoning_content") or ""))


def _build_review_prompt(task: str) -> str:
    return (
        "Contexte Core Equity: enorme codebase, eviter code inutile. "
        "Reponds en francais avec exactement ces sections:\n"
        "1. Verdict: coherent / risky / blocked\n"
        "2. Risques reels avec references de lignes\n"
        "3. Faux positifs possibles ou contexte manquant\n"
        "4. Tests/cleanup minimaux\n"
        "5. Surfaces qui doivent rester desactivees\n"
        "Si une conclusion n'est pas prouvee par les extraits, marque-la comme hypothese.\n\n"
        + task
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local Qwen read-only code review sidecar.")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="moe-fast")
    parser.add_argument("--prompt", help="Review prompt/task.")
    parser.add_argument("--file", action="append", help="Optional file snippet to include. Repeatable.")
    parser.add_argument("--symbol", action="append", help="Extract a targeted symbol snippet as PATH:SYMBOL. Repeatable.")
    parser.add_argument("--symbol-context", type=int, default=8, help="Lines before a symbol hit.")
    parser.add_argument("--grep", action="append", help="Extract grep snippets as PATH:PATTERN. Repeatable.")
    parser.add_argument("--grep-context", type=int, default=8, help="Lines around each grep hit.")
    parser.add_argument("--max-grep-hits", type=int, default=4)
    parser.add_argument("--max-file-chars", type=int, default=6000)
    parser.add_argument("--max-tokens", type=int, default=700)
    parser.add_argument("--timeout", type=int, help="Override generation timeout.")
    parser.add_argument("--keep-server", action="store_true", help="Leave llama-server running after review.")
    parser.add_argument("--no-start", action="store_true", help="Use an already-running server only.")
    args = parser.parse_args()

    profile = PROFILES[args.profile]
    task = _read_task(args)
    timeout = args.timeout or int(profile["timeout"])
    proc: subprocess.Popen[Any] | None = None
    started = False
    start_time = time.time()
    if not _server_running():
        if args.no_start:
            raise SystemExit("local qwen server is not running")
        proc = _start_server(args.profile, profile)
        started = True
        _wait_ready(proc, 180)

    review_prompt = _build_review_prompt(task)
    try:
        answer = _call_qwen(review_prompt, timeout=timeout, max_tokens=max(128, min(args.max_tokens, 2000)))
    finally:
        if started and proc is not None and not args.keep_server:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    result = {
        "ok": True,
        "profile": args.profile,
        "started_server": started,
        "kept_server": bool(args.keep_server),
        "elapsed_seconds": round(time.time() - start_time, 2),
        "answer": answer,
    }
    output = json.dumps(result, ensure_ascii=False, indent=2)
    try:
        sys.stdout.write(output + "\n")
    except UnicodeEncodeError:
        sys.stdout.buffer.write((output + "\n").encode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
