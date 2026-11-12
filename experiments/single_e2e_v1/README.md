# 实验一：生成到引用就绪的端到端效率

复用共同30个真实DCC输入，NBA／CLAUSE／FinAuditing各10个，以及各模型原有冻结目标。质量表不重跑。本目录单独测两条真实路线：

- 艺峰：正常生成并采集Q/K，完整归约并筛选引用。
- MemoryFlow：正常生成时关闭采集，然后回放本次完整输出，归约并筛选引用。

2026-11-12三模型均完成，每路线三次30输入。[最终六行表](reports/RESULTS_20261112.md) 与 [逐次小型证据](evidence/completed_all3_20261112.json) 保留实际共同目标数和输出变化。540张正式矩阵与12张预热矩阵通过完整行覆盖检查；新增模型服务已释放。[调度证据](evidence/optimization_20261112.json) 通过正常生成响应ID核对其与回放同批调度，关闭采集的生成在原GPU日志中标作other。

每模型一张A800、一个常驻权重服务。两路线分开运行，模型加载和两个固定财务调用的预热另存。正式三次交错运行，各指标分别取三次中位数。首个生成请求至全部引用落盘的实际墙钟为主耗时，重叠阶段不重复相加。

生成并发2、服务最大序列数4、CPU处理并发2。MF独立序列回放合批2，和后续生成、CPU归约重叠。每调用完整矩阵只建一次，多目标共享矩阵。保存实际GPU合批及调度信息；27B状态由现有请求隔离服务分别管理。

重新生成可能改变原句。`locate`只精确匹配冻结目标；没有出现或出现位置不明确的目标单列。每次两路线的共同可定位目标作为同一次均摊分母，所有30次生成仍计时。保存两路线输出token数、序列哈希与原输出的一致情况，不能将时间差全部解释为分析开销。秒/目标是整批完成时间均摊，不是单个请求的独立响应时间。

显存每100毫秒使用NVML采样，仅合计本服务进程树，逐PID去重，排除同卡他人进程。模型和预留缓存均包含；共享权重只计一次。固定缓存可能使两路线峰值相同。

## 运行

沿用 `dcc_complete_v1/serve.sh` 启动对应权重和原头服务。每个输出目录必须全新：

```sh
MF_URL=http://127.0.0.1:PORT/v1/completions PYTHONPATH="$r:$r/code" python "$r/single_e2e_v1/runner.py" \
  --formal "$r/experiment1_native32_30/formal_MODEL_TAG" \
  --gold "$r/experiment1_native32_30/gold_all_MODEL_TAG_v1.json" \
  --model MODEL_PATH --gpu PHYSICAL_GPU --server-pid OWNED_SERVER_PID \
  --output NEW_MEASUREMENT_DIRECTORY
```

实际测量根目录为243的 `/data1/songzhengxing_intern_dccv2/mf_complete_20261111/single_e2e_20261112_v1`。正式每次原生成参数固定 `max_tokens=2048, temperature=0, seed=0`。脚本先核对输入与标签哈希、服务权重和预检，再自动继续30个输入。`results.json`仅在三次成对测量全部完成后生成。

下载计时与显存记录后，可独立复算：

```sh
python -m experiments.single_e2e_v1.summarize DOWNLOADED_ROOT SUMMARY_JSON
python -m unittest experiments.single_e2e_v1.test_runner
```

`summarize`核对逐调用端点、共同分母、NVML原始采样哈希与峰值及三次中位数。完整请求、响应、Q/K和矩阵保留在服务器，不进入Git。`model_setup.json`中的启动到确认时间含开发等待，不能当成模型冷加载时间。
