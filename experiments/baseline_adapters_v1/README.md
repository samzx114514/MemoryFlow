# CLM 与艺峰方法：第一轮复现接入

2026-10-17：**组件已运行，真实轨迹输入已适配，完整模型效果尚未评测。** 保险任务暂停。

## 已做成什么

- CLM 官方代码固定为 `Contrastive-LM/CLM@d5f9ef0fd9bde185df0ceaad4f4ecc6cfe8c34f6`，Apache-2.0。官方投影头固定为 HF revision `e939398d4556fcd9400c76fa8c5a513202f42b0a`，75,557,149 字节，已下载到 243 并核对官方 LFS SHA256。没有下载完整 Qwen3-8B。
- 复用艺峰补充材料中的作者实现，不修改源码；第三方源码和数据不入 Git。未见单独许可文件，继续按组内研究材料使用。
- 本地与服务器适配层有 12 项单元测试；243 上 9 项作者组件测试通过，见 [component_report.json](reports/component_report.json)。CLM 是真实发布的投影头加模拟 encoder 向量；艺峰数值测试和小型随机 Qwen2 解码测试不是正式语言模型评测。
- 两份真实样例已转换：SP1 短报告 10 个来源，CUAD 单例 13 个来源。原文只保留在 243 `memoryflow/runs/baseline_adapters_v1/inputs_20261017/`；Git 只保存 [准备报告](reports/preparation_report.json)。这两个整段 Summary 仅验证接口，不是已冻结的原子信息评测集。

## 两种方法怎么接

| 方法 | 本轮接口 | 能回答什么 | 不能据此声称什么 |
|---|---|---|---|
| CLM 参考头 | Target 作为 state；来源文本作为 action candidates；固定指令询问哪个来源支持 Target | 对既有目标与候选来源排序 | CLM 原论文的行动选择效果；已校准的语义边概率；因果影响 |
| 艺峰原生归因 | 原始 Query + 检索片段拼成的上下文 → 重新自然生成回答 → 读取选定 head 的注意力并添加引用 | 新生成回答在该模型中的注意力引用 | 对原 SP1/DeepSeek 输出读取注意力；与固定 Target 的 LC-Sent-15 直接同协议比较 |

CLM 使用作者 `Engine.answer`，以来源 ID 为 choice key，避免相同文本不同来源被合并。候选顺序不变，排序时分数降序、source ID 升序打破精确同分。候选间 softmax 不是“存在来源关系”的概率；当前没有拒答/多来源阈值，不拿它做二分类边准确率。

CLM 适配属于**来源排序迁移 baseline**，不是原论文任务的原样复现。参考头必须搭配 **Qwen3-8B、last-token pooling**；不能接上旧 Qwen2.5 的平均向量后仍沿用 CLM 名称。第一版固定 Target→state、Source→action，不根据两个展示样例的表现翻转方向或调 Prompt。

艺峰输入不包含已知 Target，不强迫它生成原答案。保留字符偏移侧表，后续可把作者的句子级引用映射回检索片段；跨片段句子和多来源情况需保留边界，不能直接改写为一个正确 chunk。当前没有实现或默认启用 teacher forcing，也不把任意 head 冒充论文选头。

## 如何运行已经通过的部分

243 的固定路径：

```bash
MF=/data2/pkuiti/songzhengxing_intern/memoryflow
PY=$MF/artifacts/legacy/.conda_env_cf/bin/python
CLM=$MF/artifacts/third_party/clm_d5f9ef0
YF=$MF/artifacts/third_party/yifeng_20261016/AAAI27_supplementary_material
HEAD=$MF/artifacts/models/clm_reference_e939398/CLM_v0.1-8B.pt

$PY -m unittest discover -s "$MF/scripts/baseline_adapters_v1" -p test_adapters.py -v
```

已交付结果目录（只读）：

```text
memoryflow/runs/baseline_adapters_v1/
  inputs_20261017/           两份真实轨迹的未评分输入
  components_20261017_v3/    成功的 CPU 作者组件测试
```

前两次组件运行因测试错误要求浮点结果逐位相等而中止，未产生方法指标；保留原目录。最终使用 `rtol=1e-6, atol=1e-7` 比较公式结果，记录到的候选置换误差约 `1.9e-8`，重复文本偏差约 `2.4e-7`。这只是测试容差，不对正式分数四舍五入、不更改排名规则。

如需复跑组件，输出必须换成一个不存在的新目录；示例以下目录尚未运行：

```bash
$PY "$MF/scripts/baseline_adapters_v1/component_smoke.py" \
  --clm-root "$CLM" --yifeng-root "$YF" --head "$HEAD" \
  --output "$MF/runs/baseline_adapters_v1/components_independent_check"
```

## 后续真正跑模型前需要什么

**CLM：** Qwen3-8B 权重约 16 GB，另有缓存/环境空间；一张有足够空闲显存的 GPU 与作者要求的 pooling 服务。243 当次检查磁盘约剩 47 GB，8 张卡均已有显存占用，因此没有启动 GPU 服务，也未安装会连带拉取大依赖的全套 requirements。既有 Python 环境未修改。243 到 HF 不通时，本次只用本机中转了小投影头。

准备好的 `run_clm.py` 只接受本机环回地址的 encoder，禁止隐式模型下载；超出 token 上限明确退出，不静默截断。它调用作者 Engine 和发布头，保留来源 ID、输入哈希与 token 长度；在服务建好前没有运行。正式调用还需记录 encoder 的权重 revision、pooling 和服务配置，不能仅按服务名字认定模型身份。

**艺峰：** Qwen2.5-7B 本地权重已有。优先取得该模型对应的 `head_ranking.json` 和选头来源说明；没有则按作者 probe 流程重建，需 BGE-M3 和合规的选头数据。补充材料提供 200 例不代表已经核实它与本项目封存切分互不污染，因此本轮没有打开它来选头；也没有沿用旧报告中的“必须先下载全量 5.7 GB 数据”作为唯一途径。取得可用的固定 head 或独立校准集后直接推进，不重复泛化审计。

不启动 GPT-4o Judge，不产生付费调用。完整方法比较时分开报告：固定 Target 排名、重新生成回答后的引用质量、工程开销；不能混成一张 Hit@1 表。真实轨迹没有 Gold，先输出分数和引用供核查，不算准确率。

## 文件职责

- `adapters.py`：固定输入契约与 CLM ID 保真评分。
- `prepare.py`：从本轮已提取轨迹生成无标签输入，输出目录只新建。
- `acquire_head.py`：只下载一个固定 revision/大小/哈希的小型官方头，不下载 backbone。
- `component_smoke.py`：在 243 CPU 调用作者组件；报告明确标记非模型效果。
- `run_clm.py`：资源准备完毕后使用的真实评分入口；当前未执行。
- `test_adapters.py`：12 项不依赖模型的接口测试。

上游：[CLM](https://github.com/Contrastive-LM/CLM/tree/d5f9ef0fd9bde185df0ceaad4f4ecc6cfe8c34f6)、[官方参考头](https://huggingface.co/Contrastive-LM/CLM-v0.1-8B/tree/e939398d4556fcd9400c76fa8c5a513202f42b0a)。
