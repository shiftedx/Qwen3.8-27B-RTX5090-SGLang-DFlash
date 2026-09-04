#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
readonly DEFAULT_REPO_ROOT="${REPO_ROOT:-$SCRIPT_REPO_ROOT}"
readonly PROFILE_FILE="${QWEN_PROFILE:-$DEFAULT_REPO_ROOT/profile.env}"
PROFILE_TEMPLATE="${QWEN_PROFILE_TEMPLATE:-profiles/rtx5090-152k.env.example}"
[[ "$PROFILE_TEMPLATE" = /* ]] || PROFILE_TEMPLATE="$SCRIPT_REPO_ROOT/$PROFILE_TEMPLATE"
readonly PROFILE_TEMPLATE
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
write_default_profile() {
  [[ -f "$PROFILE_TEMPLATE" ]] || fail "missing profile example: $PROFILE_TEMPLATE"
  mkdir -p "$(dirname "$PROFILE_FILE")"
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      REPO_ROOT=*) printf 'REPO_ROOT=%q\n' "$DEFAULT_REPO_ROOT" ;;
      DEPLOY_ROOT=*) printf 'DEPLOY_ROOT=%q\n' "$DEFAULT_REPO_ROOT" ;;
      *) printf '%s\n' "$line" ;;
    esac
  done < "$PROFILE_TEMPLATE" > "$PROFILE_FILE"
}
if [[ ! -f "$PROFILE_FILE" ]]; then write_default_profile; fi
if [[ "${1:-}" == "--write-profile-only" ]]; then exit 0; fi
# shellcheck disable=SC1090
source "$PROFILE_FILE"
[[ -d "$REPO_ROOT" ]] || fail "REPO_ROOT does not exist: $REPO_ROOT"
validate_repo_id() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || fail "invalid model repository ID: $1"; }
validate_repo_id "$TARGET_REPO"
readonly CANONICAL_MODEL_ROOT="$(realpath -m "$MODEL_ROOT")"
mkdir -p "$DEPLOY_ROOT/.state" "$CANONICAL_MODEL_ROOT"
bash "$SCRIPT_DIR/preflight.sh"
case "${SETUP_MODE:-download}" in
  download) docker pull "${IMAGE_TAG}@${IMAGE_DIGEST}" ;;
  existing)
    REPO_ROOT="$REPO_ROOT" BOUNDED_IMAGE_REF="$BOUNDED_IMAGE_REF" bash "$SCRIPT_DIR/build_bounded_image.sh"
    ;;
  *) fail "unknown SETUP_MODE: ${SETUP_MODE}" ;;
esac

quarantine_snapshot() {
  local destination="$1"
  local quarantine="$CANONICAL_MODEL_ROOT/.qwen38-quarantine/$(basename "$destination").$(date -u +%Y%m%dT%H%M%SZ).$$"
  mkdir -p "$(dirname "$quarantine")" || fail "cannot create snapshot quarantine; check permissions"
  mv "$destination" "$quarantine" || fail "cannot quarantine stale snapshot (possibly root-owned files): $destination"
  printf 'Quarantined stale snapshot at %s\n' "$quarantine"
}

snapshot_is_complete() {
  local destination="$1" revision="$2"
  local marker="$destination/.qwen38-snapshot-revision-$revision"
  local inventory="$destination/.qwen38-shards-$revision.txt"
  [[ -s "$marker" && "$(cat "$marker")" == "$revision" && -s "$destination/config.json" && -s "$destination/model.safetensors.index.json" && -s "$inventory" ]] || return 1
  while IFS= read -r shard; do [[ -s "$destination/$shard" ]] || return 1; done < "$inventory"
}

download_snapshot() {
  local repo="$1" revision="$2" destination marker inventory
  destination="$(realpath -m "$CANONICAL_MODEL_ROOT/$repo")"
  [[ "$destination" != "$CANONICAL_MODEL_ROOT" ]] || fail "refusing MODEL_ROOT itself as a snapshot destination"
  [[ "$destination" == "$CANONICAL_MODEL_ROOT/"* ]] || fail "snapshot destination escapes MODEL_ROOT"
  [[ "$destination" == "$(realpath -m "$CANONICAL_MODEL_ROOT/$repo")" ]] || fail "snapshot destination does not match repository ID"
  marker="$destination/.qwen38-snapshot-revision-$revision"
  inventory="$destination/.qwen38-shards-$revision.txt"
  if [[ -e "$destination" ]] && ! snapshot_is_complete "$destination" "$revision"; then quarantine_snapshot "$destination"; fi
  mkdir -p "$destination"
  [[ -w "$destination" ]] || fail "snapshot destination is not writable (possibly root-owned files): $destination"
  # --env forwards a token only from the caller's environment; its value is never persisted or printed.
  docker run --rm --env HF_TOKEN --env HF_XET_HIGH_PERFORMANCE=1 \
    -v "$CANONICAL_MODEL_ROOT:/models" --entrypoint python3 "${IMAGE_TAG}@${IMAGE_DIGEST}" -c \
    "from huggingface_hub import snapshot_download; snapshot_download('$repo', revision='$revision', local_dir='/models/$repo')"
  printf '%s\n' "$revision" > "$marker" || fail "cannot write revision marker (possibly root-owned files): $destination"
  python3 - "$destination" "$revision" "$marker" "$inventory" <<'PY'
import json
import sys
from pathlib import Path

destination, revision, marker, inventory = map(Path, sys.argv[1:])
if marker.read_text(encoding="utf-8").strip() != str(revision):
    raise SystemExit("revision marker mismatch")
index = destination / "model.safetensors.index.json"
if not index.is_file():
    raise SystemExit("missing model.safetensors.index.json")
weights = sorted(set(json.loads(index.read_text(encoding="utf-8"))["weight_map"].values()))
if not weights or any(not (destination / weight).is_file() or (destination / weight).stat().st_size == 0 for weight in weights):
    raise SystemExit("incomplete safetensors shard inventory")
inventory.write_text("\n".join(weights) + "\n", encoding="utf-8")
PY
  snapshot_is_complete "$destination" "$revision" || fail "pinned snapshot is incomplete: $repo@$revision"
}

case "${SETUP_MODE:-download}" in
  download)
    validate_repo_id "$DRAFT_REPO"
    download_snapshot "$TARGET_REPO" "$TARGET_REVISION"
    download_snapshot "$DRAFT_REPO" "$DRAFT_REVISION"
    REPO_ROOT="$REPO_ROOT" BOUNDED_IMAGE_REF="$BOUNDED_IMAGE_REF" bash "$SCRIPT_DIR/build_bounded_image.sh"
    printf 'Profile and pinned model snapshots are ready.\n'
    ;;
  existing)
    [[ -s "$CANONICAL_MODEL_ROOT/$TARGET_REPO/config.json" ]] || fail "missing native checkpoint config: $CANONICAL_MODEL_ROOT/$TARGET_REPO/config.json"
    printf 'Profile and existing native checkpoint are ready.\n'
    ;;
  *) fail "unknown SETUP_MODE: ${SETUP_MODE}" ;;
esac
