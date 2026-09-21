"""Compatibility wrapper for the relocated Qwen profile benchmark."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qwen.benchmark_local_qwen_profiles import main


if __name__ == "__main__":
    raise SystemExit(main())
