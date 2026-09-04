#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
readonly PROFILE_FILE="${QWEN_PROFILE:-${REPO_ROOT:-$SCRIPT_REPO_ROOT}/profile.env}"
[[ -s "$PROFILE_FILE" ]] || { printf 'ERROR: missing profile.env; run scripts/setup_profile.sh first.\n' >&2; exit 1; }
# shellcheck disable=SC1090
source "$PROFILE_FILE"
: "${REPO_ROOT:=$SCRIPT_REPO_ROOT}"
readonly TARGET_DIR="$MODEL_ROOT/$TARGET_REPO"
readonly ENGINE="${ENGINE:-dflash}"
readonly SERVER_IMAGE_REF="${SERVER_IMAGE_REF:-$BOUNDED_IMAGE_REF}"
readonly SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-qwen3.8-27b-nvfp4}"
if [[ "$ENGINE" == dflash ]]; then readonly DRAFT_DIR="$MODEL_ROOT/$DRAFT_REPO"; fi
container_exists() { docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; }
container_running() { [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || true)" == true ]]; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

build_args() {
  args=(--model-path /model --served-model-name "$SERVED_MODEL_NAME" --host 0.0.0.0 --port "$PORT"
    --kv-cache-dtype "$KV_CACHE_DTYPE" --attention-backend flashinfer --context-length "$CONTEXT_LENGTH"
    --chunked-prefill-size "$CHUNKED_PREFILL_SIZE" --mamba-radix-cache-strategy extra_buffer
    --mamba-ssm-dtype bfloat16 --max-mamba-cache-size "${MAX_MAMBA_CACHE_SIZE:-8}"
    --mem-fraction-static "$MEM_FRACTION_STATIC" --max-running-requests "$MAX_RUNNING_REQUESTS")
  case "$ENGINE" in
    dflash)
      args+=(--speculative-algorithm DFLASH --speculative-draft-model-path /model_dflash
        --speculative-dflash-block-size "$DFLASH_BLOCK_SIZE" --speculative-draft-window-size "$DFLASH_WINDOW_SIZE"
        --speculative-draft-model-quantization unquant --reasoning-parser qwen3 --tool-call-parser qwen3_coder
        --mm-feature-transport cpu --language-only --weight-loader-drop-cache-after-load --enable-metrics
        --random-seed "$RANDOM_SEED" --speculative-dflash-bounded-cache --disable-radix-cache
        --max-total-tokens "$MAX_TOTAL_TOKENS")
      [[ "$DISABLE_PREFILL_CUDA_GRAPH" == 1 ]] && args+=(--disable-prefill-cuda-graph)
      ;;
    native_mtp)
      args+=(--speculative-algorithm EAGLE --speculative-draft-model-path /model
        --speculative-num-steps 3 --speculative-eagle-topk 1 --speculative-num-draft-tokens 4
        --weight-loader-drop-cache-after-load --enable-metrics --disable-radix-cache
        --disable-prefill-cuda-graph --random-seed "$RANDOM_SEED" --reasoning-parser qwen3
        --tool-call-parser qwen3_coder --max-total-tokens "$MAX_TOTAL_TOKENS")
      ;;
    *) fail "unknown ENGINE: $ENGINE" ;;
  esac
  [[ "$MAX_TOTAL_TOKENS" =~ ^[1-9][0-9]*$ ]] && (( MAX_TOTAL_TOKENS <= CONTEXT_LENGTH )) || { printf 'ERROR: MAX_TOTAL_TOKENS must be a positive integer no greater than CONTEXT_LENGTH.\n' >&2; return 2; }
}
docker_args() {
  docker_run_args=(docker run --gpus all --network host --ipc host --name "$CONTAINER_NAME" -v "$TARGET_DIR:/model:ro")
  [[ "$ENGINE" == dflash ]] && docker_run_args+=(-v "$DRAFT_DIR:/model_dflash:ro")
  docker_run_args+=(--entrypoint python3 "$SERVER_IMAGE_REF" -m sglang.launch_server "${args[@]}")
}
resolve() { build_args; docker_args; printf '%q ' "${docker_run_args[@]}"; printf '\n'; }
case "${1:-status}" in
  start) build_args; docker_args; container_running && { printf '%s is already running.\n' "$CONTAINER_NAME"; exit 0; }; container_exists && docker rm "$CONTAINER_NAME" >/dev/null; [[ -z "$(ss -H -ltn "sport = :$PORT" || true)" ]] || { printf 'ERROR: port %s is already in use.\n' "$PORT" >&2; exit 1; }; docker run -d "${docker_run_args[@]:2}" ;;
  stop) container_exists && { docker stop -t 30 "$CONTAINER_NAME"; docker rm "$CONTAINER_NAME" >/dev/null; } || printf '%s is stopped.\n' "$CONTAINER_NAME" ;;
  status) docker inspect -f 'name={{.Name}} running={{.State.Running}} status={{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || printf '%s is stopped.\n' "$CONTAINER_NAME" ;;
  logs) docker logs --tail "${TAIL_LINES:-200}" -f "$CONTAINER_NAME" ;;
  resolve) resolve ;;
  *) printf 'Usage: %s {start|stop|status|logs|resolve}\n' "$0" >&2; exit 2 ;;
esac
