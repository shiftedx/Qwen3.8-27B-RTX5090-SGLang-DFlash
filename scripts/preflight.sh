#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
readonly PROFILE_FILE="${QWEN_PROFILE:-${REPO_ROOT:-$SCRIPT_REPO_ROOT}/profile.env}"
[[ -s "$PROFILE_FILE" ]] || { printf 'ERROR: missing %s; run scripts/setup_profile.sh first.\n' "$PROFILE_FILE" >&2; exit 1; }
# shellcheck disable=SC1090
source "$PROFILE_FILE"
: "${REPO_ROOT:=$SCRIPT_REPO_ROOT}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
for command_name in stat df nvidia-smi ss awk uname; do command -v "$command_name" >/dev/null || fail "missing command: $command_name"; done
[[ -n "${WSL_INTEROP:-}" ]] || fail "must run inside WSL2"
wsl_kernel="$(uname -r)"
[[ "$wsl_kernel" == *WSL2* || "$wsl_kernel" == *microsoft-standard* ]] || fail "WSL2 is required"
mkdir -p "$DEPLOY_ROOT/.state" "$MODEL_ROOT"
require_ext4() { local label="$1" path="$2" filesystem_type; filesystem_type="$(stat -f -c %T "$path")"; [[ "$filesystem_type" == "ext2/ext3" || "$filesystem_type" == "ext4" ]] || fail "$label must be on WSL ext4, not a mounted Windows drive"; }
require_ext4 DEPLOY_ROOT "$DEPLOY_ROOT"
require_ext4 MODEL_ROOT "$MODEL_ROOT"
gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)"
[[ "$gpu_name" == *"RTX 5090"* ]] || fail "an RTX 5090 is required (found: $gpu_name)"
free_bytes="$(df --output=avail -B1 "$MODEL_ROOT" | awk 'NR==2 {print $1}')"
(( free_bytes >= 70000000000 )) || fail "at least 70 GB free is required under MODEL_ROOT"
free_vram_mib="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -n 1 | tr -d ' ')"
(( free_vram_mib >= 30000 )) || fail "at least 30000 MiB free VRAM is required"
[[ -z "$(ss -H -ltn "sport = :$PORT" || true)" ]] || fail "port $PORT is already in use"
printf 'PASS: WSL2, ext4 deploy/model roots, RTX 5090, free disk/VRAM, and port %s.\n' "$PORT"
