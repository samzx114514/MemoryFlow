# Full-call replay implementation plan

**Goal:** Build the recorded context forest, persist one complete fixed-head matrix per call, and query output spans over multiple calls.

**Design:** Reuse provenance_v2 ingestion and forest data models and rich replay spans. Store row/column provenance separately from float32 matrix arrays. Query by stable call ID and half-open output span.

- [x] Verify CLAUSE and SP1 request/response fields and freeze the replay rendering rules.
- [x] Implement full-call replay with one tokenization of the output and bounded fixed-head attention reduction.
- [x] Bind candidates to producer spans, separately record dispatch, and walk paths with local row selection.
- [x] Verify multiple queries reuse one CLAUSE matrix and verify three local scores and branching.
- [x] Save commands, matrix coverage and audit results.
