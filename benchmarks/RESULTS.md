# Measured results

Measurements below were taken on one RTX 5090 with one active stream. They are
not guarantees: throughput depends on the prompt and DFlash acceptance rate.

| Workload | Result |
| --- | ---: |
| Matched short-context prose at 152 Ki (median, 3 measured runs after one warmup) | 204.7 tok/s |
| Matched short-context code at 152 Ki (median, 3 measured runs after one warmup) | 405.5 tok/s |
| 8,187-token input plus 1,024-token output (one production cold-start gate) | 130.6 tok/s |
| 154,515-token input plus 1,024-token output (second production cold-start repeat) | 138.3 tok/s |

The short-context rows used one sequential OpenAI-compatible streaming request,
one discarded warm-up before three measured runs, and decode tokens/second after
the first reasoning or content token. The 8K+1K figure is one production
cold-start gate with the Task 6 bounded/legacy parity hash. The near-cap figure
is the second production cold-start repeat; its hash matched the first and the
two rates were 138.65 and 138.34 tok/s. Neither capacity row is a median. Save
fresh raw JSONL outside version control (for example `.state/`).

`prompts/matched-prose.txt` is the recovered prose prompt used for the matched
prose result. The original measured code input was not recoverable, so
`prompts/harness-code.txt` is a reproducible harness example only; it does not
claim to reproduce the measured code row.

## Native-MTP NVFP4 evidence

These are **this-machine measurements**, not universal promises. On the same
RTX 5090 with one active request, MTP-3 at 32K produced 121.28, 127.52, and
126.91 tok/s for 512-token short runs after warmup. The tuned 131K profile
produced 117.84, 126.09, and 123.57 tok/s for the same short-run method.

The current public checkpoint was also measured with the recovered identical
prose harness and the checked-in reproducible code harness, using streaming
decode with one discarded warm-up and three measured runs:

| Workload | Median decode | Measured runs (tok/s) |
| --- | ---: | --- |
| Recovered identical matched-prose harness | 138.7309 tok/s | 138.9612, 138.5336, 138.7309 |
| Current reproducible code harness | 159.6329 tok/s | 159.6329, 159.5224, 159.8960 |

The matched-prose median is 32.2% slower than the prior DFlash 204.7 tok/s
result under that recovered identical harness. The prior 405.5 code input was unrecoverable, so the
current code-harness result is not apples-to-apples with that historical row.

| Workload | Result |
| --- | ---: |
| 100008+8 tokens | 26.143s |
| 128008+8 tokens | 40.365s |

SGLang auto-profiled the physical pool to 129241 tokens; the native profile
therefore uses that as `MAX_TOTAL_TOKENS` under its 131072-token logical
context limit.
