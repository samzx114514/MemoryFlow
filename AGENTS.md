# MemoryFlow repository rules

This is a private research record and continuation workspace. Read [the research brief](docs/RESEARCH_BRIEF.md), [status](docs/STATUS.md), and [experiment index](docs/EXPERIMENT_INDEX.md) before changing an experiment.

- Infer completion from checksum-bound reports, manifests, and actual outputs, never from chat memory or a historic “running” note.
- Keep Reserve/Blind sealed. Do not tune, select, or repeatedly inspect either split.
- Preserve the established labels, candidate membership/order, split, scoring, tie rule, and evaluation protocol. Version a scientifically changed protocol; never silently edit it.
- Keep keys, tokens, private paths with embedded credentials, model weights, caches, raw logs, full datasets, and third-party restricted material out of Git.
- Never overwrite old experiment artifacts. New runs use new directories and record inputs, checksums, config, seed, model revision, runtime, and outputs.
- After a bounded preflight passes, continue the already authorized task. Do not repeat an audit for an unchanged, previously checked artifact; verify its identity instead.
- Do not treat semantic support as observed use or causal influence. Do not promote SP workflow/containment edges to semantic Gold.
