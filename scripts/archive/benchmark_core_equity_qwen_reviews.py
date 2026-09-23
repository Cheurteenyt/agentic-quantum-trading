"""Compatibility wrapper for the relocated Core Equity Qwen benchmark."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qwen.benchmark_core_equity_qwen_reviews import main


if __name__ == "__main__":
    raise SystemExit(main())
