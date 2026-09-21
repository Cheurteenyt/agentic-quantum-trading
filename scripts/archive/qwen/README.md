# Qwen Sidecar Scripts

Local Qwen review and benchmark utilities live here.

Active entrypoints:

- `local_qwen_review.py`
- `benchmark_local_qwen_profiles.py`
- `benchmark_core_equity_qwen_reviews.py`

Compatibility:

- Root-level wrappers remain in `scripts/` so older RAG commands and habits keep
  working.

Safety:

- These scripts are review/benchmark sidecars. They do not own Core Equity DB
  writes, labels, mappings, signals, trades, wallet orders or client opt-ins.
