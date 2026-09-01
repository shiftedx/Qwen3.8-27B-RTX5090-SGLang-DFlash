#!/usr/bin/env python3
"""Repeatable single-stream benchmark for the local OpenAI-compatible server."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import urllib.request
from pathlib import Path


def stream_once(args: argparse.Namespace, prompt: str) -> dict[str, object]:
    request = urllib.request.Request(
        args.base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps({"model": args.model, "messages": [{"role": "user", "content": prompt}], "max_tokens": args.max_tokens, "stream": True, "stream_options": {"include_usage": True}, "temperature": args.temperature, "top_p": 1.0, "top_k": -1, "ignore_eos": True, "chat_template_kwargs": {"enable_thinking": False}}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter(); first_payload = None; ended = started; parts: list[str] = []; usage = None
    with urllib.request.urlopen(request, timeout=args.timeout) as response:
        for raw in response:
            ended = time.perf_counter(); line = raw.decode("utf-8").strip()
            if not line.startswith("data:") or line[5:].strip() == "[DONE]": continue
            item = json.loads(line[5:].strip()); usage = item.get("usage") or usage
            for choice in item.get("choices", []):
                delta = choice.get("delta") or {}
                text = (delta.get("reasoning_content") or "") + (delta.get("content") or "")
                if text and first_payload is None: first_payload = ended
                parts.append(text)
    if usage is None or first_payload is None: raise RuntimeError("stream ended without usage or output")
    tokens = int(usage["completion_tokens"]); tpot = (ended - first_payload) / max(1, tokens - 1)
    return {"label": args.label, "usage": usage, "timing": {"ttft_seconds": first_payload - started, "decode_tokens_per_second": 1 / tpot}, "output_sha256": hashlib.sha256("".join(parts).encode()).hexdigest()}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    prompts = result.add_mutually_exclusive_group(required=True)
    prompts.add_argument("--prompt"); prompts.add_argument("--prompt-file", type=Path)
    result.add_argument("--label", required=True); result.add_argument("--output", type=Path, required=True)
    result.add_argument("--base-url", default="http://127.0.0.1:1234"); result.add_argument("--model", default="qwen3.8-27b-nvfp4")
    result.add_argument("--max-tokens", type=int, default=1024); result.add_argument("--warmups", type=int, default=1); result.add_argument("--repeats", type=int, default=3); result.add_argument("--temperature", type=float, default=0.0); result.add_argument("--timeout", type=int, default=900)
    return result


def main() -> int:
    args = parser().parse_args()
    prompt = args.prompt if args.prompt is not None else args.prompt_file.read_text(encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True); measured: list[float] = []
    with args.output.open("a", encoding="utf-8") as sink:
        for index in range(args.warmups + args.repeats):
            record = stream_once(args, prompt); record["warmup"] = index < args.warmups; record["repeat_index"] = index
            sink.write(json.dumps(record) + "\n"); sink.flush()
            if index >= args.warmups: measured.append(record["timing"]["decode_tokens_per_second"])
    print(json.dumps({"median_decode_tokens_per_second": statistics.median(measured), "runs": measured})); return 0


if __name__ == "__main__":
    raise SystemExit(main())
