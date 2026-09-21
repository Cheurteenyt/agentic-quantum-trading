"""Compatibility wrapper for the relocated Tailscale ACL validator."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.security.validate_tailscale_acl import main


if __name__ == "__main__":
    raise SystemExit(main())
