# DCC Stage 1: offline calibration package

**State: `STAGE1_READY_FOR_REVIEW` means the technical package is ready for independent review, not that its science is approved.** This directory is an English, self-contained diagnostic for clause-reference existence (T1) and conditional sending obligations (T2). Eight hand-authored cases, two families × four variants, calibrate the schema and Gold process; they are not a model evaluation set or evidence that MemoryFlow works. No real contract or third-party replication material is included.

Read [SCHEMA.md](SCHEMA.md) for the data separation and fixed rule semantics, [REVIEW_PACKET.md](reports/REVIEW_PACKET.md) for all public materials and per-object evidence, and [STAGE1_REPORT.md](reports/STAGE1_REPORT.md) for the delivery gate. The three `data/calibration_*.jsonl` files intentionally separate model-visible text, evaluator-only Gold, and condition-specific location indices. The `preview/` files are **DRY_RUN_NOT_SENT** and contain no model response.

From the repository root, Python 3.10+ standard library is sufficient:

```powershell
python -m unittest discover -s experiments/dcc_diagnostic_v0/tests -p 'test_*.py' -v
python experiments/dcc_diagnostic_v0/stage1.py validate
python experiments/dcc_diagnostic_v0/stage1.py render-preview
python experiments/dcc_diagnostic_v0/stage1.py report
```

`validate` recomputes all 32 object states from the fixed evaluator, checks spans and separated views, and writes `reports/validation.json`. `render-preview` creates T1 A/B and T2 A/B/C inputs (20 files), without sending them. `report` creates the review packet, model/budget placeholder, delivery manifest, and summary. The command has no API client, GPU path, or online fallback. Re-running it only regenerates deterministic Stage 1 files in this directory; it never launches the 20 proposed future calls.

Human review is still needed for object completeness, whether each English statement supports the structured facts, possible side channels, and the intended research interpretation. The future tested model and financial authorization are **UNSELECTED**. The Sol implementing this package is not the tested model. Historical experiments, Reserve/Blind, and old metrics are outside this directory and unchanged. Stage 2 and the full Pilot require a separate authorization.
