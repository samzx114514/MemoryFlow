# DCC 完整回放与三模型采集

2026-11-11。沿用 DCCv2 `1fa314da`，森林与逐片段查询基于 `b6fe3ff`。

## 当前结果

2026-11-12更新：三模型共同30输入已全部完成，NBA／CLAUSE／FinAuditing各10个，来自17个原始任务，共90次生成和180张完整输出矩阵。`run_native_batch.sh`只计算新增17个输入，`assemble_batch.py`复用已有13个并核对完整请求与来源身份。输入SHA为`ce914a6426e584d9f71b5481d9ce31013d927f9be6ac06526545ab`。90份输出逐条审阅并冻结157个实际陈述，[首版质量表](reports/QUALITY_20261112.md)已产出；标签为AI辅助、代码规划侧语义审阅版。

CLAUSE完整任务已实际完成12次调用、12张完整矩阵和3个最终片段查询。效率最新入口为`run_efficiency_parallel.sh`，使用独立A800设备对4/6和0/2；每组同一执行与分析配置，预热后3次测量，显式统一8192输出token上限。默认4096截断的失败预热保留在v1。实验2的12条完整轨迹待用户提供。

以下为已保存的早期批次记录。

第一版冻结输入为 NBA、CLAUSE、FinAuditing 各 10 个调用。三模型均完成 30 次生成和对应回放，共 90 对调用、180 张完整输出矩阵。头分别为 27B L51/Q20/KV3、7B L19/H15/KV2、1.5B L16/H2/KV0，编号从 0 开始。

首批抽样只限定输入中有实际工具材料，包含较多读文件、检索和调度阶段。人工检查 27B 输出发现其中 25/30 只有工具操作；部分其余输出是运行状态说明。这批输入不足以提供计划中的 180–270 个分析陈述。原始输出完整保留。

上一版分析输入 SHA256 为 `d8e8bf47e7c3ca8338b247cf56ebdd41fdf74280748fe1398f0680cd142e65c3`，保存在服务器 `experiment1_final_20261111/`。27B 的 30 次生成／回放已完成；NBA 输入超过小模型 32K 原生窗口，7B 异常输出已保存，后续自动运行已停止。该版保留为 27B 补充数据。标注草案不作为已审阅标签，暂未生成正式质量表。

## 入口与数据

服务器根目录：`/data1/songzhengxing_intern_dccv2/mf_complete_20261111`。代码位于 `code/`，使用 `/data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3`。依赖已安装的作者 vLLM 插件与 `yf_driver/client_frozen.py`；报告保存作者文件 SHA。未改动作者共享包。

```bash
root=/data1/songzhengxing_intern_dccv2/mf_complete_20261111
py=/data2/xyf/conda_envs/xuyf/vllm_hook_env/bin/python3
# 专用服务；MF_GPU、MF_PORT、MF_CONTEXT 指定实际设备、端口、上下文上限。
bash "$root/code/serve.sh" /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct 16 2
# 在另一个终端运行。输出目录必须为新目录。
"$py" "$root/code/pipeline.py" "$root/formal_inputs.json" "$root/new_run" /data2/pkuiti/songzhengxing_intern/model/Qwen2.5-1.5B-Instruct --max-tokens 1024
```

`pipeline.py` 验证服务权重路径。捕获文件另外核对指定层、query head 和实际 KV head。完整输入及输出 token、原始请求与响应、来源字符区间、输出 token 区间、Q/K、逐行矩阵、引用结果均落盘。预测行从 `prompt_tokens-1` 开始，回放输入为原输入 token 加原输出的前 `T-1` 个 token。

单轮两侧使用作者原始句子划分、短句合并、来源聚合、前三候选、半最大值阈值及熵筛选，保留多来源输出。每个模型内部两侧共用候选；各模型使用自己的原始生成输出。

## 三项优化

- **同调用合并：**完整输出一次回放，全部输出行落盘；查询按字符区间取行。开发例两句分别使用 `[0,81)`、`[81,165)`，共用同一矩阵。
- **跨调用 packing：**vLLM 独立变长序列合批，保留每请求的状态、位置与缓存。服务在两条回放全部入队后恢复调度，避免 HTTP 批量请求实际逐条执行。记录实际 batch、请求 ID、序列偏移与 CUDA event。
- **流水线：**生成完成后提交后台回放，与后续生成重叠。新入口也在后台归约矩阵。第一版 30 调用实测生成与回放窗口重叠分别为 1.5B 16.50 秒、7B 54.91 秒、27B 275.33 秒。

`check_packing.py` 保存逐条、合批与邻居扰动数据。`diagnostics.py --packing-test` 正确地以同样合批的 A 对比更换邻居后的 A；历史检查中的 `altered_neighbour` 字段曾与逐条执行比较，使用补充的 `isolation*.json` 查看隔离结果。三模型已检查的 A 均不受邻居替换影响。27B 逐条与合批仍有分数差异，必须结合语义标注核对引用质量。

## 森林与真实 DCC 在线入口

`live_gateway.py` 复用已有 DCC transport 的工具通道与整数参数恢复。执行端保存解析前 token；分析端完整回放，包含历史工具参数、JSON 解码视图和本次输出前文。`rich_sources.py` 复用现有 `span_views`，原文坐标按实际 token 对齐。27B/7B/1.5B 的六个已保存真实调用均通过区间检查。

`forest_bridge.py` 将新矩阵适配现有 `provenance_v2` 建图与查询。每个独立单轮输入单独建根；同一个真实任务按原始调用顺序提供 ID 列表。保留调度、工具配对与逐片段转交。查询可使用作者的多来源筛选规则；现有 top-k 默认行为保留。

```bash
export PYTHONPATH="$root:$root/code"
"$py" "$root/code/forest_bridge.py" export "$root/dev27_measured" "$root/new_episode" --model /data/Qwen3.8-27B-FP8 --ids dev-nba
"$py" "$root/code/forest_bridge.py" query "$root/new_episode" "$root/target.json" --model /data/Qwen3.8-27B-FP8 --call call00 --span 224 423
```

`live_gateway.py` 支持 `execution`、`serial`、`full`。串行组在任务结束后，按目标分别回放，关闭三项优化；完整组后台合批回放并共用矩阵。`/finish` 需传入实际目标区间、任务起止时间和原生完成状态。记录分析批次、构图查询、尾部等待、CUDA event、各卡和同时总进程显存。正式效率实验使用两侧独立服务与同一套资源配置。

`native_probe.py` 是接线检查，自动选择两段输出。它的输出单列，不作为人工质量标签或正式效率表。首次将子 Agent 限到 4 轮的检查完成两次调用回放与查询，任务未交付。恢复正常预算后发现输入会超过 32K，执行端正在用 64K 配置继续检查。

## 标注、评分与测量

```bash
"$py" "$root/code/evaluate.py" review "$root/formal_27b" "$root/review.json"
# 根据原始输出和全部材料逐条审阅；冻结后将 review_complete 设为 true。
"$py" "$root/code/evaluate.py" score "$root/formal_27b" "$root/quality.json" --gold "$root/reviewed_gold.json"
"$py" "$root/code/diagnostics.py" "$root/formal_27b" "$root/timing.json"
"$py" "$root/code/verify_artifacts.py" "$root" "$root/verified.json"
```

`annotate_draft.py` 只读取原始输出与材料，生成待审阅草案。草案已发现漏掉工具调用前的事实说明，必须逐条检查；评分入口拒绝未冻结的草案。标签列出所有合理替代来源和完整支持组合。Precision 按回答中的正确引用数／返回引用数算；Recall 为完整 1、部分 0.5、缺失 0；回答内合成 F1 后汇总。没有事实陈述的调用另外列出。

`measure_capture.py` 对同一请求预热后交错测量采集开关各三次，保存原始 token 数和时间。第一组 27B 的中位差为 -0.96 秒，尚未测到额外耗时。正式效率三组表另测；30 个独立单轮调用的窗口时间不替代完整任务时间。

测试：证据组合与回答级指标、完整输出行和因果偏移、原有三调用分叉与复用，以及作者筛选回调。真实数据另外核对 90 对调用与 180 张矩阵的形状、完整输出覆盖、原文区间及文件 SHA。

## 效率入口的服务与预热

`run_efficiency_parallel.sh [全新输出目录]`要求两份相同27B执行服务分别位于8770（GPU4）和8771（GPU0），8781／8783分析端口空闲。执行服务均使用作者`vllm_hook_piecewise`插件、PIECEWISE、上下文65536、缓存预算0.70、TP1；所有测量请求关闭采集，显式设置8192输出上限。两个设备对各自独立，按模型记录实际GPU与资源。

执行模型先用真实DCC任务预热，随后三次测量。回放模型由`warm_replay.py`复用本次执行预热保存的完整调用、最终目标和原始token，分别预热完整和串行流程，再运行各三次真实DCC任务。预热文件有`warmup=true`，复用日志的预热另有`warmup_replay_only=true`；两者都不进入正式计时汇总。已开始的7B组保留原先两次完整任务预热。模型启动到首次健康检查的时间单列在`model_setup_*.json`。

当前CLAUSE首例的执行端三次测量为2次成功、1次超时；成功耗时和完成率一并保留。原生任务的调用数与token量会因实际分工和恢复步骤而变化。成本表按成功运行取条件中位数，同时保留全部尝试及失败耗时；未全部完成三次成功时明确标记。
