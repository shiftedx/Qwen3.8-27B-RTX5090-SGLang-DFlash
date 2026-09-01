#!/usr/bin/env bash
set -Eeuo pipefail
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
readonly PROFILE_FILE="${QWEN_PROFILE:-${REPO_ROOT:-$SCRIPT_REPO_ROOT}/profile.env}"
[[ -s "$PROFILE_FILE" ]] || exit 1
# shellcheck disable=SC1090
source "$PROFILE_FILE"
: "${REPO_ROOT:=$SCRIPT_REPO_ROOT}"
bash "$SCRIPT_DIR/server.sh" start
while [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || true)" == true ]]; do sleep 20; done
