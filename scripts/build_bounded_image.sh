#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="${REPO_ROOT:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
readonly BASE_IMAGE="lmsysorg/sglang:nightly-dev-cu13-20260830-a1fe4e30"
readonly BASE_DIGEST="sha256:43816c14aaaf6a4d09b6d19e6bac9802774b23c43298d70552e93fd4d202848a"
readonly BASE_COMMIT="a1fe4e30a983b04bbb74099dfc71bc7148c5c577"
readonly PATCH_FILE="$REPO_ROOT/patches/sglang-bounded-dflash.patch"
readonly PATCH_SHA256="d080d3e087f56c9cfb338f9a3302fde70baab26857a9c7df17b4987ab8187d53"
readonly IMAGE_TAG="${BOUNDED_IMAGE_REF:-local/sglang:qwen38-bounded-dflash-a1fe4e30}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ -f "$PATCH_FILE" ]] || fail "missing bundled patch: $PATCH_FILE"
[[ "$(sha256sum "$PATCH_FILE" | awk '{print tolower($1)}')" == "$PATCH_SHA256" ]] || fail "bundled patch checksum mismatch"

source_dir="$(mktemp -d "${TMPDIR:-/tmp}/sglang-base.XXXXXX")"
trap 'rm -rf -- "$source_dir"' EXIT
git clone --quiet --filter=blob:none https://github.com/sgl-project/sglang.git "$source_dir"
git -C "$source_dir" fetch --quiet --depth=1 origin "$BASE_COMMIT"
git -C "$source_dir" checkout --quiet --detach FETCH_HEAD
[[ "$(git -C "$source_dir" rev-parse HEAD)" == "$BASE_COMMIT" ]] || fail "pinned SGLang base checkout mismatch"
git -C "$source_dir" apply --check "$PATCH_FILE"

docker build --pull=false --provenance=false \
  --build-arg "BASE_IMAGE=$BASE_IMAGE" \
  --build-arg "BASE_DIGEST=$BASE_DIGEST" \
  --build-arg "BASE_COMMIT=$BASE_COMMIT" \
  --build-arg "PATCH_SHA256=$PATCH_SHA256" \
  --tag "$IMAGE_TAG" \
  --file "$REPO_ROOT/docker/Dockerfile" "$REPO_ROOT"

labels="$(docker image inspect "$IMAGE_TAG" --format '{{index .Config.Labels "io.qwen38.sglang.base.revision"}} {{index .Config.Labels "io.qwen38.sglang.patch.sha256"}} {{index .Config.Labels "org.opencontainers.image.base.digest"}}')"
expected="$BASE_COMMIT $PATCH_SHA256 $BASE_DIGEST"
[[ "$labels" == "$expected" ]] || fail "image provenance labels do not match pinned inputs"
printf 'Built %s with verified SGLang base, patch, and provenance labels.\n' "$IMAGE_TAG"
