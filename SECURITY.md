# Security policy

Do not commit Hugging Face tokens, model files, Docker exports, benchmark logs,
or local profiles. `HF_TOKEN` is passed only to the download container process
environment and is never printed or written by these scripts.

To report a vulnerability, open a private security advisory for this repository
instead of a public issue. Rotate any token that may have been exposed.
