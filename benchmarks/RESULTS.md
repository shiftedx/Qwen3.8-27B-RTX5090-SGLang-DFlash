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
