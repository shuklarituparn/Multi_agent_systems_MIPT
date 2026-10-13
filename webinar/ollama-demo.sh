#!/usr/bin/env bash

set -eo pipefail
cd "$(dirname "$0")"

MODEL="${1:-${LLM_MODEL:-qwen3:8b}}"
[ $# -gt 0 ] && shift
HOST="${OLLAMA_HOST_URL:-http://localhost:11434}"

command -v ollama >/dev/null || { echo "Ollama is not installed: https://ollama.com/download"; exit 1; }
curl -sf "$HOST/api/version" >/dev/null || {
  echo "Ollama is not running at $HOST. Open the Ollama app, or run: ollama serve"; exit 1; }

if ! ollama show "$MODEL" >/dev/null 2>&1; then
  echo "Model $MODEL not found locally, pulling it (do this BEFORE the class, not live)..."
  ollama pull "$MODEL"
fi
INFO="$(ollama show "$MODEL" 2>/dev/null || true)"
if ! printf '%s' "$INFO" | grep -qi 'tools'; then
  echo "WARNING: $MODEL does not list 'tools' in its capabilities. Tool calls may fail."
fi

echo "Loading $MODEL into memory (first load can take a while)..."
curl -sf "$HOST/api/generate" -d "{\"model\": \"$MODEL\", \"keep_alive\": \"60m\"}" >/dev/null

export LLM_BASE_URL="$HOST/v1"
export LLM_MODEL="$MODEL"
export LLM_TIMEOUT_SECONDS="${LLM_TIMEOUT_SECONDS:-300}"
python3 -m mas_demo --backend live --show-prompts --out runs/live "$@"
