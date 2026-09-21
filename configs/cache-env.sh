#!/usr/bin/env bash
# Core Equity local cache policy.
# Keep rebuildable AI/Python/Node caches on D: so Windows C: does not fill up.

export HF_HOME="/mnt/d/ai-cache/huggingface"
export HUGGINGFACE_HUB_CACHE="/mnt/d/ai-cache/huggingface/hub"
export TRANSFORMERS_CACHE="/mnt/d/ai-cache/huggingface/transformers"
export PIP_CACHE_DIR="/mnt/d/ai-cache/pip-wsl"
export UV_CACHE_DIR="/mnt/d/ai-cache/uv-wsl"
export TORCH_HOME="/mnt/d/ai-cache/torch"
export npm_config_cache="/mnt/d/ai-cache/npm"
export PLAYWRIGHT_BROWSERS_PATH="/mnt/d/ai-cache/playwright"

mkdir -p \
  "$HF_HOME" \
  "$HUGGINGFACE_HUB_CACHE" \
  "$TRANSFORMERS_CACHE" \
  "$PIP_CACHE_DIR" \
  "$UV_CACHE_DIR" \
  "$TORCH_HOME" \
  "$npm_config_cache" \
  "$PLAYWRIGHT_BROWSERS_PATH"
