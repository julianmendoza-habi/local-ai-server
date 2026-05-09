#!/bin/sh
set -e

ollama serve &
OLLAMA_PID=$!

echo "[ollama] Waiting for server to be ready..."
until ollama list > /dev/null 2>&1; do
  sleep 1
done
echo "[ollama] Server ready."

# ALLOWED_MODELS is a JSON array: ["model1", "model2", ...]
# Strip brackets, quotes, and spaces — split on commas.
if [ -n "$ALLOWED_MODELS" ]; then
  MODELS=$(printf '%s' "$ALLOWED_MODELS" | tr -d '[] "' | tr ',' '\n')
  for model in $MODELS; do
    echo "[ollama] Pulling $model ..."
    ollama run "$model" && echo "[ollama] $model ready." || echo "[ollama] WARNING: failed to pull $model"
  done
else
  echo "[ollama] ALLOWED_MODELS not set — skipping automatic pull."
fi

wait "$OLLAMA_PID"
