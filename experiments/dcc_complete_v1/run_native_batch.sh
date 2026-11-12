#!/usr/bin/env bash
set -euo pipefail
r=${MF_ROOT:-/data1/songzhengxing_intern_dccv2/mf_complete_20261111}
out="$r/experiment1_native32_30"
python=/data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3
export PYTHONPATH="$r:$r/code" OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 OMP_NUM_THREADS=4 MF_GPU=6
while [ ! -f "$out/formal_lock.json" ]; do sleep 5; done
# Finish the independent source-collection requests on this GPU first.
pid=$(cat "$r/sources_fin_native32_v1.pid")
while ps -p "$pid" -o args= | grep -Fq "$r/collect_fin_native32.sh"; do sleep 5; done
mkdir "$out/added17"
cp "$out/added17_inputs.json" "$out/added17/formal_inputs.json"
nohup "$python" "$r/code/stream_review.py" "$out/added17" > "$out/added17/stream_review.log" 2>&1 < /dev/null &
echo $! > "$out/added17/stream_review.pid"
"$python" "$r/code/pipeline.py" "$out/added17/formal_inputs.json" "$out/added17/formal_27b" /data/Qwen3.8-27B-FP8 --max-tokens 2048 > "$out/added17/formal_27b.log" 2>&1
start_model() {
  local model=$1 layer=$2 head=$3 label=$4 pid args
  pid=$(cat "$r/serve.pid");args=$(ps -p "$pid" -o args= || true)
  case "$args" in *"$r/code/server.py serve "*"--port 8781"*) kill -TERM "$pid";;*) echo "Unexpected service: $args";return 1;;esac
  for i in $(seq 1 60);do if ! curl -fsS http://127.0.0.1:8781/health >/dev/null 2>&1;then break;fi;sleep 1;done
  export MF_CONTEXT=32768
  nohup bash "$r/code/serve.sh" "$model" "$layer" "$head" > "$out/added17/serve_${label}.log" 2>&1 < /dev/null &
  echo $! > "$r/serve.pid"
  for i in $(seq 1 300);do
    if curl -fsS http://127.0.0.1:8781/health >/dev/null 2>&1;then return;fi
    if ! kill -0 "$(cat "$r/serve.pid")" 2>/dev/null;then break;fi
    sleep 1
  done
  return 1
}
start_model /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct 19 15 7b
"$python" "$r/code/pipeline.py" "$out/added17/formal_inputs.json" "$out/added17/formal_7b" /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct --max-tokens 2048 > "$out/added17/formal_7b.log" 2>&1
start_model /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct 16 2 1_5b
"$python" "$r/code/pipeline.py" "$out/added17/formal_inputs.json" "$out/added17/formal_1_5b" /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct --max-tokens 2048 > "$out/added17/formal_1_5b.log" 2>&1
"$python" "$r/code/assemble_batch.py" "$out" "$r/compatibility_native32_13"
"$python" "$r/code/verify_artifacts.py" "$out" "$out/artifact_manifest.json"
date -u +%FT%TZ > "$out/finished.utc"
