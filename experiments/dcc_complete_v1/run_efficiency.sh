#!/usr/bin/env bash
# Keep quality collection and assisted annotation off the efficiency devices.
set -euo pipefail
root=${MF_ROOT:-/data1/songzhengxing_intern_dccv2/mf_complete_20261111}
batch="$root/experiment1_native32_30"
out="$root/efficiency_clause_native32_v1"
python=/data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3
tree=/data1/songzhengxing_intern_dccv2/sp2_dccv2_1fa314da_mf_yf
export PYTHONPATH="$root:$root/code" MF_GPU=6 MF_CONTEXT=65536 MF_RESOURCE_GPUS=4,6
export OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 OMP_NUM_THREADS=4
while [ ! -f "$batch/finished.utc" ] || [ ! -f "$batch/added17/annotation_drafts_v2/complete.json" ] || [ ! -f "$root/compatibility_native32_13/annotation_drafts_v2/complete.json" ]; do sleep 5; done
"$python" - "$root/full_clause_preflight_1_5b/result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x['completed'] and x['calls']==x['successful_calls'] and len(x['final_targets'])>=2, x
PY
pid=$(cat "$root/sources_nba_native32_v2.pid")
while ps -p "$pid" -o args= | grep -Fq "$root/code/collect_sources.py"; do sleep 5; done
mkdir "$out"
touch "$out/active"
cp "$root/efficiency_clause_task_lock.json" "$out/source_tasks_lock.json"
stop_model() {
  local pid args
  pid=$(cat "$root/serve.pid")
  args=$(ps -p "$pid" -o args= || true)
  case "$args" in *"$root/code/server.py serve "*"--port 8781"*) kill -TERM "$pid" ;;
    *) echo "Unexpected analysis service: $args"; return 1 ;;
  esac
  for i in $(seq 1 60); do
    if ! kill -0 "$pid" 2>/dev/null; then return; fi
    sleep 1
  done
  echo "Analysis service has not exited"; return 1
}
start_model() {
  local model=$1 layer=$2 head=$3 label=$4
  nohup bash "$root/code/serve.sh" "$model" "$layer" "$head" > "$out/serve_${label}.log" 2>&1 < /dev/null &
  echo $! > "$root/serve.pid"
  for i in $(seq 1 300); do
    if curl -fsS http://127.0.0.1:8781/health >/dev/null 2>&1; then return; fi
    if ! kill -0 "$(cat "$root/serve.pid")" 2>/dev/null; then break; fi
    sleep 1
  done
  echo "Analysis service failed: $out/serve_${label}.log"; return 1
}
run_task() {
  local label=$1 model=$2 mode=$3 repeat=$4 warmup=${5:-}
  "$python" "$root/code/efficiency_task.py" "$out/${label}_${mode}_${repeat}" \
    --task /data1/songzhengxing_intern_dccv2/mf_yf_batch12_20261109/assets/clause/test/public/mf-eff-native32-clause.jsonl \
    --config "$tree/configs/stackplanner_benchmarks.yaml" --tree "$tree" \
    --bundle /data1/songzhengxing_intern_dccv2/mf_yf_batch12_20261109/assets/clause/test \
    --benchmark clause --analysis-model "$model" --mode "$mode" $warmup
  if [ -n "$warmup" ]; then
    "$python" - "$out/${label}_${mode}_${repeat}/result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x['completed'] and x['calls']==x['successful_calls'] and len(x['final_targets'])>=2, x
PY
  fi
}
small=/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct
stop_model
run_task baseline "$small" execution warm --warmup
for repeat in 1 2 3; do run_task baseline "$small" execution "$repeat"; done
for label in 1_5b 7b 27b; do
  case "$label" in
    1_5b) model=$small; layer=16; head=2; export MF_MEMORY=.20 MF_CONTEXT=32768 ;;
    7b) model=/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct; layer=19; head=15; export MF_MEMORY=.40 MF_CONTEXT=32768 ;;
    27b) model=/data/Qwen3.8-27B-FP8; layer=51; head=20; export MF_MEMORY=.72 MF_CONTEXT=65536 ;;
  esac
  start_model "$model" "$layer" "$head" "$label"
  run_task "$label" "$model" full warm --warmup
  run_task "$label" "$model" serial warm --warmup
  for repeat in 1 2 3; do
    run_task "$label" "$model" serial "$repeat"
    run_task "$label" "$model" full "$repeat"
  done
  stop_model
done
"$python" "$root/code/summarize_efficiency.py" "$out" "$out/summary.json"
rm "$out/active"
date -u +%FT%TZ > "$out/finished.utc"
