# MemoryFlow Checkpoint C5B-Local Implementation Plan

1. Reuse the audited SP request boundaries and the Python 3.12 audit parser; verify their hashes and raw-log paths before export.
2. Convert every recoverable request into stable raw-memory nodes without semantic rewriting or citation-derived links.
3. Validate node identity, ordering, parent evidence, raw-text replay, and quality flags; select a deterministic structural pilot-20.
4. Write `sp_nodes.jsonl`, `manifest.json`, and `checksums.sha256`, then run focused and full existing tests.

Success means all available SP requests are attempted, failures are recorded rather than hidden, integrity checks pass, and the raw logs remain untouched.
