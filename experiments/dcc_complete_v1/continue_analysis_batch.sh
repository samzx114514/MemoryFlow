#!/usr/bin/env bash
# Continue the frozen analysis batch after the already launched 27B process.
set -euo pipefail
root=${MF_ROOT:-/data1/songzhengxing_intern_dccv2/mf_complete_20261111}
out="$root/experiment1_final_20261111"
python=/data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3
export PYTHONPATH="$root:$root/code" MF_GPU=6 MF_CONTEXT=65536
export OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 OMP_NUM_THREADS=4

pid=$(cat "$out/formal_27b.pid")
while [ ! -f "$out/formal_27b/completed.json" ]; do
  args=$(ps -p "$pid" -o args= || true)
  case "$args" in *"pipeline.py $out/formal_inputs.json $out/formal_27b"*) sleep 5 ;;
    *) echo "27B stopped without a completion receipt; inspect $out/formal_27b.log"; exit 1 ;;
  esac
done

start_model() {
  local model=$1 layer=$2 head=$3 label=$4 pid args
  pid=$(cat "$root/serve.pid")
  args=$(ps -p "$pid" -o args= || true)
  case "$args" in *"$root/code/server.py serve "*"--port 8781"*) kill -TERM "$pid" ;;
    *) echo "Unexpected service: $args"; return 1 ;;
  esac
  for i in $(seq 1 60); do
    if ! curl -fsS http://127.0.0.1:8781/health >/dev/null 2>&1; then break; fi
    sleep 1
  done
  nohup bash "$root/code/serve.sh" "$model" "$layer" "$head" > "$out/serve_${label}.log" 2>&1 < /dev/null &
  echo $! > "$root/serve.pid"
  for i in $(seq 1 300); do
    if curl -fsS http://127.0.0.1:8781/health >/dev/null 2>&1; then return; fi
    if ! kill -0 "$(cat "$root/serve.pid")" 2>/dev/null; then break; fi
    sleep 1
  done
  echo "Service did not start: $out/serve_${label}.log"; return 1
}

start_model /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct 19 15 7b
"$python" "$root/code/pipeline.py" "$out/formal_inputs.json" "$out/formal_7b" /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct --max-tokens 2048 > "$out/formal_7b.log" 2>&1
start_model /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct 16 2 1_5b
"$python" "$root/code/pipeline.py" "$out/formal_inputs.json" "$out/formal_1_5b" /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct --max-tokens 2048 > "$out/formal_1_5b.log" 2>&1
"$python" "$root/code/verify_artifacts.py" "$out" "$out/artifact_manifest.json"
date -u +%FT%TZ > "$out/finished.utc"
