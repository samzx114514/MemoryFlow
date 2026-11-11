#!/usr/bin/env bash
set -euo pipefail
root=${MF_ROOT:-/data1/songzhengxing_intern_dccv2/mf_complete_20261111}
cache=/data1/songzhengxing_intern_dccv2/vllm_cache
export CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=${MF_GPU:-6}
export PYTHONPATH="$root/code" MF_LAYER=$2 MF_HEAD=$3
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
export VLLM_PLUGINS=vllm_hook VLLM_HOOK_WORKER=qk VLLM_USE_AOT_COMPILE=0
export VLLM_CACHE_ROOT="$cache/vllm" TORCHINDUCTOR_CACHE_DIR="$cache/inductor" TMPDIR="$cache/tmp" TRITON_CACHE_DIR="$cache/triton"
exec /data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3 "$root/code/server.py" serve "$1" \
 --served-model-name mf-model --worker-extension-cls capture_worker.CaptureWorker \
 --enforce-eager --no-enable-prefix-caching --max-model-len "${MF_CONTEXT:-32768}" \
 --max-num-batched-tokens 32768 --max-num-seqs 4 --enable-chunked-prefill \
 --enable-auto-tool-choice --tool-call-parser qwen3_xml \
 --gpu-memory-utilization .72 --host 127.0.0.1 --port "${MF_PORT:-8781}"
