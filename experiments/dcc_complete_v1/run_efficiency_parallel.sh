#!/usr/bin/env bash
# Fixed independent A800 pairs: executor4/analysis6 and executor0/analysis2.
set -euo pipefail
root=${MF_ROOT:-/data1/songzhengxing_intern_dccv2/mf_complete_20261111}
out="$root/efficiency_clause8192_v2"
python=/data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3
tree=/data1/songzhengxing_intern_dccv2/sp2_dccv2_1fa314da_mf_yf
export PYTHONPATH="$root:$root/code" MF_RESOURCE_GPUS=4,6
export OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 OMP_NUM_THREADS=4
test -f "$root/experiment1_native32_30/finished.utc"
"$python" - "$root/full_clause_preflight_1_5b/result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x['completed'] and x['calls']==x['successful_calls'] and len(x['final_targets'])>=2, x
PY
for port in 8770 8771; do curl -fsS "http://127.0.0.1:$port/health" >/dev/null; done
if curl -fsS http://127.0.0.1:8781/health >/dev/null 2>&1; then
  echo "Baseline requires the analysis service to be stopped"; exit 1
fi
mkdir "$out"
touch "$out/active"
cp "$root/efficiency_clause_task_lock.json" "$out/source_tasks_lock.json"
run_baseline() {
  "$python" "$root/code/efficiency_task.py" "$out/baseline_execution_$1" \
    --task /data1/songzhengxing_intern_dccv2/mf_yf_batch12_20261109/assets/clause/test/public/mf-eff-native32-clause.jsonl \
    --config "$tree/configs/stackplanner_benchmarks.yaml" --tree "$tree" \
    --bundle /data1/songzhengxing_intern_dccv2/mf_yf_batch12_20261109/assets/clause/test \
    --benchmark clause --analysis-model /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct \
    --mode execution --executor http://127.0.0.1:8770 --port 8792 --execution-max-tokens 8192 ${2:-}
}
run_baseline warm --warmup
"$python" - "$out/baseline_execution_warm/result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x['completed'] and x['calls']==x['successful_calls'] and len(x['final_targets'])>=2, x
PY
# The second pair runs independently while baseline uses pair4/6.
(
  bash "$root/code/run_efficiency_pair.sh" "$out/pair_0_2" 7b http://127.0.0.1:8771 2 8783 8793 0,2
  bash "$root/code/run_efficiency_pair.sh" "$out/pair_0_2" 1_5b http://127.0.0.1:8771 2 8783 8793 0,2
) > "$out/pair_0_2.log" 2>&1 &
other=$!
echo "$other" > "$out/pair_0_2.pid"
for repeat in 1 2 3; do run_baseline "$repeat"; done
bash "$root/code/run_efficiency_pair.sh" "$out/pair_4_6" 27b http://127.0.0.1:8770 6 8781 8792 4,6 > "$out/pair_4_6.log" 2>&1
wait "$other"
"$python" "$root/code/summarize_efficiency.py" "$out" "$out/summary.json"
rm "$out/active"
date -u +%FT%TZ > "$out/finished.utc"
