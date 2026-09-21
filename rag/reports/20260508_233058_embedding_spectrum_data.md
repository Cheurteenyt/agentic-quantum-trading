# Embedding Effective Dimension Audit

- Domain: `data`
- Model: `BAAI/bge-small-en-v1.5`
- Sampled chunks: `160`

```json
{
  "sample_count": 160,
  "nominal_dim": 384,
  "effective_dim": 42.28,
  "effective_dim_ratio": 0.1101,
  "components_95": 98,
  "components_95_ratio": 0.2552,
  "anisotropy_top1_pct": 7.38,
  "avg_pairwise_cosine": 0.6791,
  "first_12_variance_pct": [
    7.379,
    5.656,
    5.059,
    4.421,
    3.625,
    3.269,
    2.952,
    2.542,
    2.47,
    2.201,
    2.098,
    1.98
  ]
}
```

## Compression Policy

```json
{
  "regime": "middle_deff",
  "decision": "neutral_measure_with_eval",
  "recommended_strategy": "eval_gated_hybrid",
  "why": "Consolidation is likely neutral. Keep hybrid retrieval and compare answer quality with evals before changing.",
  "safety": "Use this as a routing prior, not proof. Validate with eval_rag.py or task-specific QA before changing production retrieval."
}
```

## Recommendations

- LOW-RISK: keep retrieval hybrid; embeddings are compressed enough that BM25/path boosts remain valuable.
- VERIFY: chunks may be too similar; inspect duplicate generated memory or repeated boilerplate.
- DO-NOT-DO: do not switch embedding model only because nominal dimensions are larger; measure effective dimension first.
