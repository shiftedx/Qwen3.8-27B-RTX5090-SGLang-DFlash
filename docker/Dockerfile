ARG BASE_IMAGE=lmsysorg/sglang:nightly-dev-cu13-20260830-a1fe4e30
ARG BASE_DIGEST=sha256:43816c14aaaf6a4d09b6d19e6bac9802774b23c43298d70552e93fd4d202848a
FROM ${BASE_IMAGE}@${BASE_DIGEST}

ARG BASE_IMAGE
ARG BASE_DIGEST
ARG BASE_COMMIT=a1fe4e30a983b04bbb74099dfc71bc7148c5c577
ARG PATCH_SHA256

LABEL org.opencontainers.image.title="SGLang bounded DFlash" \
      org.opencontainers.image.base.name="${BASE_IMAGE}" \
      org.opencontainers.image.base.digest="${BASE_DIGEST}" \
      io.qwen38.sglang.base.revision="${BASE_COMMIT}" \
      io.qwen38.sglang.patch.sha256="${PATCH_SHA256}"

COPY patches/sglang-bounded-dflash.patch /tmp/sglang-bounded-dflash.patch
RUN test "$(sha256sum /tmp/sglang-bounded-dflash.patch | awk '{print $1}')" = "${PATCH_SHA256}" && \
    cd /sgl-workspace/sglang && \
    test "$(git rev-parse HEAD)" = "${BASE_COMMIT}" && \
    git apply --check /tmp/sglang-bounded-dflash.patch && \
    git apply /tmp/sglang-bounded-dflash.patch
