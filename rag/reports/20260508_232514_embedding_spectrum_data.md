# Embedding Effective Dimension Audit

- Domain: `data`
- Model: `BAAI/bge-small-en-v1.5`
- Sampled chunks: `160`

```json
{
  "sample_count": 160,
  "nominal_dim": 384,
  "effective_dim": 34.13,
  "effective_dim_ratio": 0.0889,
  "components_95": 87,
  "components_95_ratio": 0.2266,
  "anisotropy_top1_pct": 8.83,
  "avg_pairwise_cosine": 0.6985,
  "first_12_variance_pct": [
    8.833,
    6.505,
    5.891,
    4.754,
    4.234,
    3.398,
    3.3,
    2.94,
    2.542,
    2.438,
    2.36,
    2.111
  ]
}
```

## Recommendations

- LOW-RISK: keep retrieval hybrid; embeddings are compressed enough that BM25/path boosts remain valuable.
- VERIFY: chunks may be too similar; inspect duplicate generated memory or repeated boilerplate.
- DO-NOT-DO: do not switch embedding model only because nominal dimensions are larger; measure effective dimension first.
