#!/usr/bin/env bash
# Controlled two-round provenance sample: build spec, generate, score, analyze.
# Usage: bash run_case.sh <physical_gpu> <sample_slug>
set -euo pipefail

GPU=${1:?physical gpu index}
SAMPLE=${2:?sample slug}
ROOT=/data2/pkuiti/songzhengxing_intern/memoryflow
PY=$ROOT/artifacts/legacy/.conda_env_cf/bin/python
ARCHIVE=$ROOT/artifacts/raw/genmem_batch10_v3/genmem_batch10_selection_v1.zip
MODEL=/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct
RUN=${3:-$ROOT/runs/provenance_rounds_v1/20261106_v1}
RECIPE=$ROOT/experiments/provenance_rounds_v1/recipes/${SAMPLE}.json

mkdir -p "$RUN"
export PYTHONIOENCODING=utf-8
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
cd "$ROOT"

echo "== nvidia-smi =="
nvidia-smi --query-gpu=index,memory.total,memory.free,utilization.gpu --format=csv,noheader
FREE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i "$GPU" | tr -d ' ')
echo "gpu=$GPU free_mib=$FREE"
if [ "$FREE" -lt 20000 ]; then
  echo "refusing to use GPU $GPU: free < 20000 MiB" >&2
  exit 2
fi
nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader || true

echo "== build_spec =="
$PY experiments/provenance_rounds_v1/build_spec.py \
  --source "$ARCHIVE" \
  --recipe "$RECIPE" \
  --out "$RUN/spec_${SAMPLE}.json" | tee "$RUN/build_spec_${SAMPLE}.log"

echo "== generate =="
$PY experiments/provenance_rounds_v1/generate.py \
  --spec "$RUN/spec_${SAMPLE}.json" \
  --out "$RUN/frozen_${SAMPLE}.json" \
  --model "$MODEL" \
  --physical-gpu "$GPU" | tee "$RUN/generate_${SAMPLE}.log"

echo "== score =="
$PY experiments/provenance_rounds_v1/score.py \
  --frozen "$RUN/frozen_${SAMPLE}.json" \
  --out "$RUN/scores_${SAMPLE}.json" \
  --root "$ROOT" \
  --physical-gpu "$GPU" | tee "$RUN/score_${SAMPLE}.log"

echo "== analyze =="
$PY experiments/provenance_rounds_v1/analyze.py \
  --frozen "$RUN/frozen_${SAMPLE}.json" \
  --scores "$RUN/scores_${SAMPLE}.json" \
  --out "$RUN/analysis_${SAMPLE}.json" | tee "$RUN/analyze_${SAMPLE}.log"

echo "== done =="
ls -la "$RUN"
