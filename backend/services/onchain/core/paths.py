"""Filesystem paths for Core Equity on-chain storage.

Keep these defaults side-effect-light and importable from small services. The
large `services.onchain_engine` facade still exposes mutable aliases for legacy
tests that patch paths directly.
"""

from __future__ import annotations

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]
DATA_ROOT = BACKEND_DIR / "data"

DATA_DIR = DATA_ROOT / "onchain"
DB_PATH = DATA_DIR / "onchain.db"
BACKUP_DIR = DATA_DIR / "backups"

CEX_LABEL_PROMOTION_BACKUP_DIR = DATA_ROOT / "backups" / "cex_label_promotions"
CEX_CONFIDENCE_UPGRADE_BACKUP_DIR = DATA_ROOT / "backups" / "cex_confidence_upgrades"

LABEL_LEDGER_PATH = DATA_ROOT / "arkham" / "label_ledger.db"
ARKHAM_CACHE_PATH = DATA_ROOT / "arkham" / "cache.json"

ENTITY_LABELS_DATA_PATH = DATA_ROOT / "entity" / "entity_labels.db"
ENTITY_LABELS_LEGACY_PATH = DATA_ROOT / "legacy" / "entity_labels.db"
ENTITY_LABELS_PATH = ENTITY_LABELS_DATA_PATH if ENTITY_LABELS_DATA_PATH.exists() else ENTITY_LABELS_LEGACY_PATH

