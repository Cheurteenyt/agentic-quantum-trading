# Local Qwen Review Playbook

## Purpose

Local Qwen is a read-only review sidecar for Core Equity. It is useful for checking focused code snippets, safety gates, test coverage, DB side effects, and architecture risks before Codex makes the final decision.

Qwen is not an operator. It must not write files, run Core Equity endpoints, access DB directly, create labels, create mappings, trigger trades, create client signals, or make final product decisions.

## Recommended Profiles

- `qwen25-fast`: quick fallback for small sanity checks.
- `qwen3-2507-fast`: current recommended local default for balanced read-only review; more stable than the older Qwen3 MoE on abstract prompts.
- `qwen3-coder-fast`: stronger code-focused sidecar, but use only with concrete snippets because it can invent line references on abstract prompts.
- `qwen3-coder-kvq`: code-focused profile with K/V cache quantization for memory-sensitive checks.
- `qwen35-a3b-fast`: experimental stronger reviewer. It loads on RTX 3070 8GB, but can over-alert and expose reasoning if the answer is truncated; use as lab-only until more checks pass.
- `moe-fast`: Qwen3 30B A3B MoE, 4k context, stronger focused review.
- `moe-fast-kvq`: experimental 4k MoE profile with K/V cache quantized to `q4_1`.
- `moe-fast-partial-moe`: experimental 4k MoE profile with only the first 44 MoE layers forced to CPU.
- `moe-deep`: Qwen3 30B A3B MoE, 8k context, slower review for larger snippets.
- `moe-deep-kvq`: experimental 8k MoE profile with K/V cache quantized to `q4_1`.

Use MoE on demand, then stop it. Do not keep it always on unless running multiple consecutive reviews with `--keep-server`.
Keep `qwen3-2507-fast` as the safe local default for serious read-only reviews. Use `qwen3-coder-fast` for code-specific second opinions, and verify every line reference before acting.

## Preferred Commands

Quick review:

```powershell
.\.venv-win\Scripts\python.exe scripts\local_qwen_review.py `
  --profile qwen25-fast `
  --prompt "Review this guard for unintended DB writes." `
  --symbol backend\services\onchain_engine.py:preview_source_backed_venue_mapping `
  --symbol backend\services\onchain_engine.py:upsert_source_backed_venue_mapping
```

Recommended focused review:

```powershell
.\.venv-win\Scripts\python.exe scripts\local_qwen_review.py `
  --profile qwen3-2507-fast `
  --prompt "Review this code for source-backed mapping safety. Do not decide; list risks only." `
  --symbol backend\services\onchain_engine.py:preview_source_backed_venue_mapping `
  --symbol backend\services\onchain_engine.py:upsert_source_backed_venue_mapping `
  --grep backend\services\onchain_engine.py:"OKX DEX" `
  --max-tokens 700
```

Deep review:

```powershell
.\.venv-win\Scripts\python.exe scripts\local_qwen_review.py `
  --profile moe-deep `
  --prompt "Review these snippets for architecture consistency and unintended side effects." `
  --symbol backend\services\onchain_engine.py:SOME_FUNCTION `
  --grep backend\routers\onchain.py:"some-route" `
  --max-tokens 1200
```

Profile benchmark:

```powershell
.\.venv-win\Scripts\python.exe scripts\benchmark_local_qwen_profiles.py `
  --profiles qwen25-fast qwen3-2507-fast qwen3-coder-fast `
  --max-tokens 180
```

Core Equity quality benchmark:

```powershell
.\.venv-win\Scripts\python.exe scripts\benchmark_core_equity_qwen_reviews.py `
  --profiles qwen3-2507-fast qwen3-coder-fast `
  --scenarios radar-read-only source-backed-mapping `
  --max-tokens 420
```

## Output Contract

The wrapper forces Qwen to return:

1. Verdict: `coherent`, `risky`, or `blocked`.
2. Real risks with line references.
3. Possible false positives or missing context.
4. Minimal tests/cleanup.
5. Surfaces that must remain disabled.

If a claim is not proven by the snippets, Qwen should mark it as a hypothesis. Codex must verify every Qwen concern before acting on it.

## Known Quirks

- Qwen3 30B A3B may emit empty `<think></think>` tags even with reasoning disabled. The wrapper strips these.
- If given abstract prompts, Qwen can become over-critical and invent missing safeguards. Always provide concrete snippets, tests, and runtime results.
- `--fit` must not be combined with `--cpu-moe` in IK llama.cpp. Use `--cpu-moe -ngl 99`.
- `moe-fast-kvq` reduced KV cache from about 384 MiB to about 120 MiB at 4k context, but short-prompt speed was not clearly better than the baseline.
- `moe-fast-partial-moe` loaded successfully on RTX 3070 8GB and was slightly faster in a tiny smoke, but it is still experimental and should be checked on real snippets before becoming default.
- `qwen25-fast` remains the fastest fallback and is useful when we only need a quick sanity pass.
- `qwen3-2507-fast` loaded and produced the cleanest answer on a real `get_token_market_local_candidate_discovery_radar` snippet. Treat it as the best default local reviewer for now.
- `qwen3-coder-fast` loaded and can reason about code, but in a prompt-only benchmark it invented line references. Use it only with concrete snippets and Codex verification.
- `qwen35-a3b-fast` loaded, but gave an over-cautious review and may expose `<think>` text if generation is truncated. Keep it experimental, not default.
- Core Equity quality benchmark now exists in `scripts/benchmark_core_equity_qwen_reviews.py`. It uses real snippets instead of toy prompts and scores structure, disabled-surface coverage, think leakage, mojibake, and repetition noise.
- Latest source-backed mapping scenario: `qwen3-2507-fast` and `qwen3-coder-fast` both loaded cleanly with no think leak or mojibake. `qwen3-2507-fast` remains the default because its concerns were more balanced. `qwen3-coder-fast` was useful but more aggressive and can raise context-level concerns such as admin auth that may belong to router/middleware rather than the service snippet.

## GLM / MTP Lessons

GLM 4.7 Flash is not installed for Core Equity. It is a reference point for local-model optimization only.

- MLA-style long context is model-architecture-specific. It does not automatically improve Qwen unless the model itself supports that architecture.
- `ncmoe` tuning maps conceptually to controlling how many MoE layers/experts stay on CPU vs GPU. For the current Qwen MoE setup, keep using the proven `--cpu-moe -ngl 99` baseline unless a separate benchmark shows a better local profile.
- MTP/speculative decoding can improve speed only when the runtime and model/GGUF support it correctly. Do not enable MTP blindly on Core Equity reviews.
- GLM reports show strong context stability but also hard hallucination failures. Any local model output remains advisory: it can suggest risks, but it cannot create facts, sources, labels, mappings, trades, client signals, or final decisions.
- If GLM is tested later, test it as a separate sidecar profile with hallucination checks, source-grounded prompts, and no access to Core Equity writes.

## Final Authority

Codex/GPT-5.5 keeps implementation, validation, product direction, and final decisions. Spark/Rawls remains the primary Core Equity verification sidecar when available. Qwen is a local read-only reviewer only.
