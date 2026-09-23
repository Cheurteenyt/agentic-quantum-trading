"""Compatibility wrapper for the relocated local Qwen review script."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qwen.local_qwen_review import main


if __name__ == "__main__":
    raise SystemExit(main())
