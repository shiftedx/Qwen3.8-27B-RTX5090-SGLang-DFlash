---
base_model: Jackrong/Qwopus3.8-27B-Flash
base_model_relation: quantized
library_name: transformers
license: apache-2.0
language:
- en
- zh
- es
- ru
- ja
pipeline_tag: text-generation
tags:
- qwen3_8
- text-generation
- sglang
- modelopt
- nvfp4
- mtp
- speculative-decoding
- rtx-5090
- safetensors
---

# Qwopus3.8-27B-Flash NVFP4 + MTP

Text-only NVIDIA NVFP4 quantization of
[`Jackrong/Qwopus3.8-27B-Flash`](https://huggingface.co/Jackrong/Qwopus3.8-27B-Flash),
packaged for single-GPU SGLang inference on a 32 GB RTX 5090. The model's native
MTP layer is preserved for EAGLE/NEXTN speculative decoding.

## Important: text only

This checkpoint does **not** support image or video input. The source model is
multimodal, but this conversion intentionally removes its 333 vision tensors to
reserve VRAM for the 27B language model, native MTP draft, and KV cache. SGLang
supports Qwen vision models; this particular artifact does not.

## Conversion

- Source revision: `44d24e8cb20ceb3cdf4fe200b5a0afd970ee748a`
- Quantizer: NVIDIA ModelOpt 0.46
- Quantization: NVFP4 weights and activations, group size 16
- Calibration: CNN/DailyMail, 512 samples, sequence length 512, batch size 1
- KV metadata: FP8 E4M3
- Quantized modules: 400
- Native MTP tensors: 15, retained bit-for-bit from the source checkpoint
- Vision tensors removed: 333
- Safetensors: 2 shards, 19,671,389,312 tensor bytes

The export passed safetensors index/header validation, complete NVFP4 scale
triplet checks, MTP equality checks, SGLang load validation, API generation,
and long-context request tests.

## Qualified RTX 5090 profile

The tested single-stream profile uses:

```bash
python3 -m sglang.launch_server \
  --model-path /model \
  --served-model-name qwopus3.8-27b-nvfp4-mtp \
  --host 0.0.0.0 --port 1234 \
  --kv-cache-dtype fp8_e4m3 \
  --attention-backend flashinfer \
  --context-length 131072 \
  --max-total-tokens 129241 \
  --chunked-prefill-size 1024 \
  --mamba-radix-cache-strategy extra_buffer \
  --mamba-ssm-dtype bfloat16 \
  --max-mamba-cache-size 1 \
  --mem-fraction-static 0.96 \
  --max-running-requests 1 \
  --speculative-algorithm EAGLE \
  --speculative-draft-model-path /model \
  --speculative-num-steps 3 \
  --speculative-eagle-topk 1 \
  --speculative-num-draft-tokens 4 \
  --disable-radix-cache \
  --disable-prefill-cuda-graph \
  --weight-loader-drop-cache-after-load \
  --random-seed 42 \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder
```

Do not add `--language-only`: the checkpoint already declares
`language_model_only=true`, and the extra runtime flag is incompatible with
this wrapper configuration in the qualified SGLang build.

Reproducible setup scripts and the pinned SGLang build are in
[`shiftedx/Qwen3.8-27B-RTX5090-SGLang-DFlash`](https://github.com/shiftedx/Qwen3.8-27B-RTX5090-SGLang-DFlash).

## Measured results

Measured on one RTX 5090 with one active request. Results depend on prompt and
MTP acceptance and are not universal performance guarantees.

| Workload | Result |
| --- | ---: |
| Recovered matched-prose harness, 3-run streaming decode median | 138.7 tok/s |
| 512-token synthetic runs after warm-up, end-to-end | 121.3–128.3 tok/s |
| 100,008-token prompt + 8 output tokens | 26.143 s |
| 128,008-token prompt + 8 output tokens | 40.365 s |
| Physical resident token pool | 129,241 tokens |

At the qualified 131K profile, GPU residency was approximately 27.6 GB and the
SGLang container used approximately 4.9 GiB of host RAM. No CPU weight offload
was enabled.

## Limitations

- Text only; no vision encoder is present.
- Experimental ModelOpt NVFP4 format; use the pinned SGLang profile above.
- No broad post-quantization quality evaluation has been completed yet.
- SGLang reports that no explicit FP8 KV scaling factors are present and falls
  back to 1.0; evaluate quality for your workload before production use.
- The physical token pool is 129,241 tokens, so prompt plus generated output
  must fit within that total even though the logical context is 131,072.

## License and attribution

Apache-2.0, following the source checkpoint. Credit belongs to the Qwopus
authors and the Qwen team; this repository only provides the quantized,
text-only packaging and measured RTX 5090 serving profile.
