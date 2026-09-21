# Embedding Effective Dimension Audit

- Domain: `data`
- Model: `BAAI/bge-small-en-v1.5`
- Sampled chunks: `160`

```json
{
  "sample_count": 160,
  "nominal_dim": 384,
  "effective_dim": 42.46,
  "effective_dim_ratio": 0.1106,
  "components_95": 98,
  "components_95_ratio": 0.2552,
  "anisotropy_top1_pct": 7.39,
  "avg_pairwise_cosine": 0.679,
  "first_12_variance_pct": [
    7.385,
    5.56,
    5.055,
    4.412,
    3.65,
    3.233,
    2.96,
    2.533,
    2.482,
    2.197,
    2.087,
    1.966
  ]
}
```

## Recommendations

- LOW-RISK: keep retrieval hybrid; embeddings are compressed enough that BM25/path boosts remain valuable.
- VERIFY: chunks may be too similar; inspect duplicate generated memory or repeated boilerplate.
- DO-NOT-DO: do not switch embedding model only because nominal dimensions are larger; measure effective dimension first.
