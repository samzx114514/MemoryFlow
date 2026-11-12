#!/usr/bin/env bash
# One executor/analysis GPU pair; never share either service with another trial.
set -euo pipefail
root=${MF_ROOT:-/data1/songzhengxing_intern_dccv2/mf_complete_20261111}
out=$1; label=$2; executor=$3; export MF_GPU=$4 MF_PORT=$5
gateway_port=$6; export MF_RESOURCE_GPUS=$7
python=/data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3
tree=/data1/songzhengxing_intern_dccv2/sp2_dccv2_1fa314da_mf_yf
export PYTHONPATH="$root:$root/code" MF_URL="http://127.0.0.1:$MF_PORT/v1/completions"
export OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 OMP_NUM_THREADS=4
case "$label" in
  1_5b) model=/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct; layer=16; head=2; export MF_MEMORY=.20 MF_CONTEXT=32768 ;;
  7b) model=/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct; layer=19; head=15; export MF_MEMORY=.40 MF_CONTEXT=32768 ;;
  27b) model=/data/Qwen3.8-27B-FP8; layer=51; head=20; export MF_MEMORY=.72 MF_CONTEXT=65536 ;;
  *) exit 2 ;;
esac
mkdir -p "$out"
if curl -fsS "http://127.0.0.1:$MF_PORT/health" >/dev/null 2>&1; then
  echo "Analysis port already occupied: $MF_PORT"; exit 1
fi
load_started=$("$python" -c 'import time; print(time.time())')
nohup bash "$root/code/serve.sh" "$model" "$layer" "$head" > "$out/serve_${label}.log" 2>&1 < /dev/null &
pid=$!
echo "$pid" > "$out/analysis_${label}.pid"
for i in $(seq 1 300); do
  if curl -fsS "http://127.0.0.1:$MF_PORT/health" >/dev/null 2>&1; then break; fi
  if ! kill -0 "$pid" 2>/dev/null; then echo "Analysis service failed"; exit 1; fi
  sleep 1
done
curl -fsS "http://127.0.0.1:$MF_PORT/health" >/dev/null
"$python" - "$out/model_setup_${label}.json" "$model" "$load_started" "$pid" <<'PY'
import json,os,pathlib,sys,time
output,model,started,pid=sys.argv[1:]
ready=time.time()
pathlib.Path(output).write_text(json.dumps({'model':model,'load_started':float(started),
    'first_healthy':ready,'service_load_seconds':ready-float(started),
    'gpu':os.environ['MF_GPU'],'context':int(os.environ['MF_CONTEXT']),
    'cache_fraction':float(os.environ['MF_MEMORY']),
    'argv':pathlib.Path(f'/proc/{pid}/cmdline').read_bytes().decode().rstrip('\0').split('\0')},indent=2)+'\n')
PY
run_task() {
  local mode=$1 repeat=$2 warmup=${3:-}
  "$python" "$root/code/efficiency_task.py" "$out/${label}_${mode}_${repeat}" \
    --task /data1/songzhengxing_intern_dccv2/mf_yf_batch12_20261109/assets/clause/test/public/mf-eff-native32-clause.jsonl \
    --config "$tree/configs/stackplanner_benchmarks.yaml" --tree "$tree" \
    --bundle /data1/songzhengxing_intern_dccv2/mf_yf_batch12_20261109/assets/clause/test \
    --benchmark clause --analysis-model "$model" --mode "$mode" --executor "$executor" \
    --port "$gateway_port" --execution-max-tokens 8192 $warmup
  if [ -n "$warmup" ]; then
    "$python" - "$out/${label}_${mode}_${repeat}/result.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x['completed'] and x['calls']==x['successful_calls'] and len(x['final_targets'])>=2, x
PY
  fi
}
run_task full warm --warmup
run_task serial warm --warmup
for repeat in 1 2 3; do
  run_task serial "$repeat"
  run_task full "$repeat"
done
args=$(ps -p "$pid" -o args= || true)
case "$args" in *"$root/code/server.py serve "*"--port $MF_PORT"*) kill -TERM "$pid" ;;
  *) echo "Unexpected analysis process: $args"; exit 1 ;;
esac
for i in $(seq 1 60); do
  if ! kill -0 "$pid" 2>/dev/null; then date -u +%FT%TZ > "$out/${label}_finished.utc"; exit; fi
  sleep 1
done
echo "Analysis service has not exited"; exit 1
