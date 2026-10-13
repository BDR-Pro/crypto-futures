#!/usr/bin/env bash
# Serve the decision models locally (llama.cpp via llama-cpp-python, OpenAI-compatible API).
#   Jev-style decision model -> http://127.0.0.1:8081/v1   ([jev] in config.toml)
#   generative LLM           -> http://127.0.0.1:8080/v1   ([llm] in config.toml)
# Weights are downloaded once into ./models; after that nothing leaves your machine.
#
# Usage: scripts/serve_local.sh [jev|llm|both|download]   (default: both)
#   download: only fetch the GGUFs. The decision models (nimble, jev) load in-process; no server needed.
# Env:   LLM_REPO / LLM_FILE to pick another GGUF, THREADS, CTX, GPU_LAYERS (-1 = all on GPU)
set -euo pipefail
cd "$(dirname "$0")/.."
MODELS=models
mkdir -p "$MODELS" results

NIMBLE_REPO=${NIMBLE_REPO:-ggml-org/Bespoke-Nimble-9B-v3-GGUF}   # CC BY-NC 4.0: non-commercial use only
NIMBLE_FILE=${NIMBLE_FILE:-Bespoke-Nimble-9B-v3-Q4_K_M.gguf}
JEV_REPO=${JEV_REPO:-chaoliangUNSW/Jev-Style-Qwen3.5-2B-Decision-GGUF}
JEV_FILE=${JEV_FILE:-Jev-Style-Qwen3.5-2B-Decision-Q8_0.gguf}
LLM_REPO=${LLM_REPO:-Qwen/Qwen3-8B-GGUF}
LLM_FILE=${LLM_FILE:-Qwen3-8B-Q4_K_M.gguf}
THREADS=${THREADS:-$(nproc 2>/dev/null || sysctl -n hw.ncpu)}
CTX=${CTX:-4096}
GPU_LAYERS=${GPU_LAYERS:-0}

python -c "import llama_cpp" 2>/dev/null || pip install "llama-cpp-python[server]"

fetch() {  # repo file
  if [ ! -f "$MODELS/$2" ]; then
    echo "downloading $1/$2 (one time)"
    curl -L --fail --retry 5 -o "$MODELS/$2.part" "https://huggingface.co/$1/resolve/main/$2"
    mv "$MODELS/$2.part" "$MODELS/$2"
  fi
}

serve() {  # file alias port
  echo "serving $1 as '$2' on http://127.0.0.1:$3/v1 (log: results/server_$2.log)"
  python -m llama_cpp.server --model "$MODELS/$1" --model_alias "$2" --n_ctx "$CTX" \
    --n_threads "$THREADS" --n_gpu_layers "$GPU_LAYERS" --host 127.0.0.1 --port "$3" \
    > "results/server_$2.log" 2>&1 &
}

what=${1:-both}
if [ "$what" = download ]; then fetch "$NIMBLE_REPO" "$NIMBLE_FILE"; fetch "$JEV_REPO" "$JEV_FILE"; fetch "$LLM_REPO" "$LLM_FILE"; exit 0; fi
if [ "$what" = jev ] || [ "$what" = both ]; then fetch "$JEV_REPO" "$JEV_FILE"; serve "$JEV_FILE" jev-style-2b 8081; fi
if [ "$what" = llm ] || [ "$what" = both ]; then fetch "$LLM_REPO" "$LLM_FILE"; serve "$LLM_FILE" local-llm 8080; fi
echo "servers running - press Ctrl+C to stop them"
trap "kill 0" INT TERM
wait
