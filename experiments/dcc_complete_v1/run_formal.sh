#!/usr/bin/env bash
set -euo pipefail
root=/data1/songzhengxing_intern_dccv2/mf_complete_20261111
python=/data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3
start_model() {
  local model=$1 layer=$2 head=$3 label=$4
  local pid args
  pid=$(cat "$root/serve.pid")
  args=$(ps -p "$pid" -o args= || true)
  case "$args" in *--port*8781*) kill -TERM "$pid" ;; *) echo "Unexpected server owner: $args"; return 1 ;; esac
  for i in $(seq 1 40); do
    if ! kill -0 "$pid" 2>/dev/null; then break; fi
    sleep 1
  done
  nohup bash "$root/serve.sh" "$model" "$layer" "$head" > "$root/serve_${label}_formal.log" 2>&1 < /dev/null &
  echo $! > "$root/serve.pid"
  for i in $(seq 1 180); do
    if curl -fsS http://127.0.0.1:8781/health >/dev/null 2>&1; then return; fi
    sleep 1
  done
  return 1
}
# Current dedicated server is the verified 1.5B instance.
"$python" "$root/code/pipeline.py" "$root/formal_inputs.json" "$root/formal_1_5b" /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct --max-tokens 1024
start_model /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct 19 15 7b
"$python" "$root/code/check_packing.py" "$root/dev_7b" "$root/packing_7b_barrier"
"$python" "$root/code/pipeline.py" "$root/formal_inputs.json" "$root/formal_7b" /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct --max-tokens 1024
start_model /data/Qwen3.8-27B-FP8 51 20 27b
"$python" "$root/code/check_packing.py" "$root/dev27_measured" "$root/packing27_barrier"
"$python" "$root/code/pipeline.py" "$root/formal_inputs.json" "$root/formal_27b" /data/Qwen3.8-27B-FP8 --max-tokens 1024
date -u +%FT%TZ > "$root/formal_finished.utc"
