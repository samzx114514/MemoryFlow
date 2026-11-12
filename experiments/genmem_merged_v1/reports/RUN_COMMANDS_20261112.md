# 已运行命令记录

服务器243；本轮原目录均已产生结果。复跑使用新输出目录，并把MF_URL指向相应权重的服务。完整输入重建规则与限制见上级README。

```bash
r=/data1/songzhengxing_intern_dccv2/mf_complete_20261111
py=/data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3
legacy=/data2/pkuiti/songzhengxing_intern/memoryflow
export PYTHONPATH="$r:$r/code" OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4

# 三模型分别启动独立服务后运行；每轨迹完整输出一次建表。
MF_URL=http://127.0.0.1:8786/v1/completions "$py" "$r/genmem_source96_20261112/batch.py" "$r/genmem_merged96_20261112_v1" "$r/genmem_tables7_20261112_v1" --model /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct
MF_URL=http://127.0.0.1:8788/v1/completions "$py" "$r/genmem_source96_20261112/batch.py" "$r/genmem_merged96_20261112_v1" "$r/genmem_tables1_5_20261112_v1" --model /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct
MF_URL=http://127.0.0.1:8787/v1/completions "$py" "$r/genmem_source96_20261112/batch.py" "$r/genmem_merged96_20261112_v1" "$r/genmem_tables27_20261112_v1" --model /data/Qwen3.8-27B-FP8

python3 "$r/genmem_source96_20261112/root_review.py" "$r/genmem_merged96_20261112_v1" "$r/genmem_root_review_20261112_v2"
python3 "$r/genmem_source96_20261112/candidates.py" --dataset "$r/genmem_merged96_20261112_v1" --review "$r/genmem_root_review_20261112_v2" --replay "$r/genmem_tables7_20261112_v1" --output "$r/genmem_common96_20261112_v1"

# 三模型分别按同一cases查询；这里展示7B，另两种使用对应模型和表目录。
"$py" "$r/genmem_source96_20261112/rank.py" --common "$r/genmem_common96_20261112_v1" --replay "$r/genmem_tables7_20261112_v1" --model /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct --output "$r/genmem_rank7_20261112_v1"

# 原基线及权重，不重新训练；DFAMS三个原seed。
"$py" "$legacy/experiments/genmem_baselines_v2/run.py" --root "$legacy" --inputs "$r/genmem_common96_20261112_v1/inputs" --output "$r/genmem_baselines96_20261112_v1" --methods bm25 dfull clm --gpu 1 --batch-size 8 --mem-cap-gib 32

PYTHONPATH="$r:$r/code:$legacy/experiments" python3 "$r/genmem_source96_20261112/metrics.py" --common "$r/genmem_common96_20261112_v1"  --method MF27 "$r/genmem_rank27_20261112_v1/rankings.json"  --method MF7 "$r/genmem_rank7_20261112_v1/rankings.json"  --method MF1.5 "$r/genmem_rank1_5_20261112_v1/rankings.json"  --method DFAMS "$r/genmem_baselines96_20261112_v1/scores/dfull/scores.jsonl"  --method BM25 "$r/genmem_baselines96_20261112_v1/scores/bm25/scores.jsonl"  --method CLM "$r/genmem_baselines96_20261112_v1/scores/clm/scores.jsonl"  --output "$r/genmem_quality92_20261112_v3.json"
```

离线原日志建表实际使用同调用合并与独立变长合批；在线流水线由DCC实验三实际运行，见dcc_complete_v1报告及21次原始测量记录。
