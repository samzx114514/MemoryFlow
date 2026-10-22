# LC-Sent-15：补测 CLM 与艺峰方法

只评测原来的 228 条 Dev，每条 15 个候选、一个 Silver 正例。候选、顺序、标签和旧基线分数不变。没有训练、重新选头、阈值调参或 Reserve/Blind 访问。

CLM 使用作者参考投影头、Qwen3-8B 和已有 Transformers 末 token 编码适配器，不额外训练。艺峰使用 Qwen2.5-7B-Instruct 的固定头 `(19,15)`，回放已有目标句，沿用作者的注意力聚合给 15 个候选排序。注意力读取位置与原生逐词生成一致，但目标文本不是该模型自行生成的。

CLM 输入目标句及候选；艺峰的原生提示模板还使用数据中的原问题。这是方法使用信息的差别，不能把分数差完全归因于打分器。两者保留全文、不截断。本次 CLM 上限 8,192 tokens，实际最大 6,385；初次运行因沿用小样例的 2,048 上限而在加载模型前停止，保留失败记录。

## 运行

服务器已有环境和权重即可。`prepare` 校验两个冻结输入的 SHA，把模型输入与 Gold 分开；Gold 只在全部打分完成后用于指标计算。`launch` 从当前空闲显存至少 40 GiB、利用率为零的卡里选择两张不同 GPU，每个进程张量显存上限为 32 GiB。不占用正在工作的卡，也不下载权重。

```bash
ROOT=/data2/pkuiti/songzhengxing_intern/memoryflow
PY=$ROOT/artifacts/legacy/.conda_env_cf/bin/python
CODE=$ROOT/scripts/lc_sent15_external_v1
RUN=$ROOT/runs/lc_sent15_external_v1/new_run
$PY $CODE/evaluate.py prepare --root "$ROOT" --output "$RUN/inputs"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=$ROOT/artifacts/third_party/yifeng_20261016/AAAI27_supplementary_material \
  $PY -m pytest "$CODE/test_evaluate.py" -q
$PY $CODE/launch.py --root "$ROOT" --run "$RUN"
```

代码部署时，`baseline_adapters_v1` 与本目录须同级。每个新运行使用不存在的输出目录。历史结果不覆盖。

## 输出和指标

每个方法输出 `scores.json`、`metrics.json`、`report.json`。艺峰还逐条保存 `predictions.jsonl`。不保存大型注意力矩阵。整体、中文、英文分别计分：

- Hit@1：正确来源排第一的比例；随机为 1/15，即 6.67%。
- MRR：正确来源名次倒数的平均，排第二得 1/2，第三得 1/3。
- nDCG@5：正确来源排前五时得 `1/log2(rank+1)`，否则为 0。

分数相同时按 Source ID 升序，与旧协议一致。完成报告必须覆盖 228 个唯一目标和 3,420 个有限分数；缺项、重复或候选集合变化直接报错。8 项服务器测试包含用小型随机模型逐 token 验证回放与作者原生解码的注意力完全一致。

指标只说明这个引用来源代理任务上的排序效果，不代表已恢复真实 Agent 因果信息流。正式对照表见 [RESULTS](../../docs/RESULTS.md)。
