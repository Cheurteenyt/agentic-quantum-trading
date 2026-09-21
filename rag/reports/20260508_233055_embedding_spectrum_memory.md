# Embedding Effective Dimension Audit

- Domain: `memory`
- Model: `BAAI/bge-small-en-v1.5`
- Sampled chunks: `96`

```json
{
  "sample_count": 96,
  "nominal_dim": 384,
  "effective_dim": 34.12,
  "effective_dim_ratio": 0.0889,
  "components_95": 67,
  "components_95_ratio": 0.1745,
  "anisotropy_top1_pct": 7.5,
  "avg_pairwise_cosine": 0.672,
  "first_12_variance_pct": [
    7.5,
    6.377,
    6.007,
    5.2,
    4.18,
    3.927,
    3.501,
    3.458,
    2.768,
    2.64,
    2.475,
    2.164
  ]
}
```

## Compression Policy

```json
{
  "regime": "tight_low_deff",
  "decision": "centroid_or_summary_can_help",
  "recommended_strategy": "centroid_summary",
  "why": "Use consolidation for repeated memory/playbook style content. Centroid-like summaries may improve downstream answers by removing duplicates.",
  "safety": "Use this as a routing prior, not proof. Validate with eval_rag.py or task-specific QA before changing production retrieval."
}
```

## Recommendations

- LOW-RISK: keep retrieval hybrid; embeddings are compressed enough that BM25/path boosts remain valuable.
- VERIFY: chunks may be too similar; inspect duplicate generated memory or repeated boilerplate.
- DO-NOT-DO: do not switch embedding model only because nominal dimensions are larger; measure effective dimension first.
