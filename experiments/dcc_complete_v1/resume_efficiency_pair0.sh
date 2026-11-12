#!/usr/bin/env bash
# Continue the two remaining 7B attempts after the preserved malformed-call failure.
set -euo pipefail
root=${MF_ROOT:-/data1/songzhengxing_intern_dccv2/mf_complete_20261111}
out="$root/efficiency_clause8192_v2"
pair="$out/pair_0_2"
python=/data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3
tree=/data1/songzhengxing_intern_dccv2/sp2_dccv2_1fa314da_mf_yf
export PYTHONPATH="$root:$root/code" MF_URL=http://127.0.0.1:8783/v1/completions
export MF_RESOURCE_GPUS=0,2 OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4
mkdir "$out/continuation_pair_0_2"
test -f "$pair/7b_full_2/result.json"
"$python" "$root/code/measure_capture.py" "$root/experiment1_native32_30/formal_7b" "$pair/7b_capture_overhead"
for mode in serial full; do
  test ! -e "$pair/7b_${mode}_3"
  "$python" "$root/code/efficiency_task.py" "$pair/7b_${mode}_3" \
    --task /data1/songzhengxing_intern_dccv2/mf_yf_batch12_20261109/assets/clause/test/public/mf-eff-native32-clause.jsonl \
    --config "$tree/configs/stackplanner_benchmarks.yaml" --tree "$tree" \
    --bundle /data1/songzhengxing_intern_dccv2/mf_yf_batch12_20261109/assets/clause/test \
    --benchmark clause --analysis-model /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct \
    --mode "$mode" --executor http://127.0.0.1:8771 --port 8793 --execution-max-tokens 8192
done
pid=$(cat "$pair/analysis_7b.pid")
args=$(ps -p "$pid" -o args= || true)
case "$args" in *"$root/code/server.py serve "*"--port 8783"*) kill -TERM "$pid" ;;
  *) echo "Unexpected 7B service process: $args"; exit 1 ;;
esac
for i in $(seq 1 60); do
  if ! kill -0 "$pid" 2>/dev/null; then break; fi
  sleep 1
done
if kill -0 "$pid" 2>/dev/null; then echo "7B service has not exited"; exit 1; fi
date -u +%FT%TZ > "$pair/7b_finished.utc"
bash "$root/code/run_efficiency_pair.sh" "$pair" 1_5b http://127.0.0.1:8771 2 8783 8793 0,2
while [ ! -f "$out/pair_4_6/27b_full_3/result.json" ]; do
  driver=$(cat "$root/efficiency_clause8192_v2_driver.pid")
  if ! kill -0 "$driver" 2>/dev/null; then echo "27B driver stopped before its final result"; exit 1; fi
  sleep 5
done
"$python" "$root/code/summarize_efficiency.py" "$out" "$out/summary.json"
"$python" - "$out/summary.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert len(x['attempts']) == 21 and len(x['table']) == 7, x['table']
assert all(row['attempts'] == 3 for row in x['table']), x['table']
PY
rm -f "$out/active"
date -u +%FT%TZ > "$out/finished.utc"
