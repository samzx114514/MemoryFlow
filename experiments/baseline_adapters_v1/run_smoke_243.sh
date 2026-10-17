#!/usr/bin/env bash
set -euo pipefail
MF=/data2/pkuiti/songzhengxing_intern/memoryflow
PY="$MF/artifacts/legacy/.conda_env_cf/bin/python"
export CUDA_VISIBLE_DEVICES=7 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=2
"$PY" "$MF/scripts/baseline_adapters_v1/run_local_models.py" clm --root "$MF" --output "$MF/runs/baseline_adapters_v1/models_20261018_v1/clm"
"$PY" "$MF/scripts/baseline_adapters_v1/run_local_models.py" yifeng --root "$MF" --output "$MF/runs/baseline_adapters_v1/models_20261018_v1/yifeng"
