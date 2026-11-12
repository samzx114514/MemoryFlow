# GenMem 旧47＋新49：按原日志合并

2026-11-12 用户确认用旧47题＋新49题替代实验2等待中的DCC轨迹，要求参照原始GenMem轨迹。两批旧结果保留，新版重新固定材料与标签再评分。

`intake.py`只做原文接入，不运行或读取方法排名。旧47题身份来自历史coverage清单，排除原开发case_02/case_08；旧8条轨迹从NAS原文件按历史偏移读取，并与归档逐事件核对。新49题来自原日志候选池版本的冻结cases，重新读取真实raw_runs，不导入人工构造的中间句。

实际输出96个不同目标、37条轨迹。全部目标和旧标签区间已核对。17个目标包含生成内容标签，需要沿原日志继续核对原始材料；72个目标存在候选中间调用，语义链路仍待逐项核对。调用顺序不自动变为支持标签，也不证明上下文可见性。原日志不含完整模型请求，重建输入时不得凭空移除旧原文。

```bash
python intake.py \
  --old-archive /data2/pkuiti/songzhengxing_intern/memoryflow/artifacts/raw/genmem_batch10_v3/genmem_batch10_selection_v1.zip \
  --old-metrics /data2/pkuiti/songzhengxing_intern/memoryflow/runs/genmem_quality_v2/20261028_v1/metrics_contextual64/metrics_contextual64_20261028.json \
  --new-archive /data1/songzhengxing_intern_dccv2/mf_complete_20261111/genmem_source96_20261112/genmem_informative30_v1.zip \
  --new-frozen /data2/pkuiti/songzhengxing_intern/memoryflow/artifacts/runs/informative30_20261110_rawhistory \
  --raw-history /mnt/nas/A800-244/data/sp/jxk/xwx/rqk/distilled_data/rich_two_stage_deerflow/raw_rollouts/per_run_experiences.jsonl \
  --output /data1/songzhengxing_intern_dccv2/mf_complete_20261111/genmem_merged96_20261112_v1
```

该命令已实际跑过；再次运行需用全新输出目录。小证据见[evidence/intake_20261112.json](evidence/intake_20261112.json)。完整targets、37条原轨迹和三个已核对案例保留在外部产物目录。标签尚未冻结，不报告新多轮准确率。


## 实际完整回放与统一候选

`replay.py`将目标之前的完整事件前缀作为重建输入，实际Agent输出和工具调用参数作为完整回放输出，复用DCC的完整矩阵、独立变长packing和森林查询。原日志缺少完整请求、工具schema和原token；身份文件明确列出这一点。本次是记录前缀重建，保留全部旧原文，不人为制造最终调用的可见性限制。

固定开发目标的10次调用、两条查询已通过，见[实测](evidence/preflight7_20261112.json)。第一条查询最长3次局部打分；第二条最长5次，但未追回Bob Winch任期材料。路径展开成功与证据找齐分别记录。

`batch.py`按轨迹一次建完整表，标注期间使用`--matrices-only`，先建表、暂不跑目标查询。7B和1.5B已分别完成37条轨迹、350张完整矩阵；7B输入输出合计最大22,220 token。27B在独立GPU6接续，效率任务的0/2设备对继续运行。

`root_review.py`在不读取这四个目标方法分数的前提下，把4条旧Agent标签映射至更早的实际材料，另4条仍缺完整原文支持。用户2026-11-12已确认：质量表92个，另4个留在总96清单说明。原标签不覆盖，原始开发两条的查询披露在review.json。

`candidates.py`用7B表中实际前文的user/tool片段固定共同候选。相同材料文本和相同解码区间合并为一个评测身份；所有出现位置仍保留在原输入和矩阵中。候选平均243.4个，范围54—534个。92条完整标签均能被全候选池覆盖，检查不读取方法分数。

`rank.py`沿原森林调用作者的多来源筛选，路径内分数相乘，同一原材料的多路径相加，查询阶段复用矩阵；最多16次展开，返回上限10。DFAMS、BM25和CLM复用服务器`experiments/genmem_baselines_v2/run.py`及原权重，使用同一份无标签records.json；DFAMS保留0/1/2三个原seed，先计算各seed指标再求均值。基线为最终目标对原文排序，跨调用路径作为MemoryFlow独立诊断，不混称基线已经恢复了链。

`metrics.py`复用旧47/49表的非空白字符区间并集覆盖规则，报告Hit@3、完整证据@5/@10。另报返回前10条中的已标注支持片段比例P、必要证据项覆盖率R及逐目标F1，均为原文片段参考指标；与实验1的语义引用P/R/F1分别解释。4条标签不完整目标为未评分，不填成普通错误。

实际服务器产物：`genmem_tables{7,1_5,27}_20261112_v1`、`genmem_root_review_20261112_v2`、`genmem_common96_20261112_v1`、`genmem_rank{7,1_5,27}_20261112_v1`。质量结果在所有方法完成后统一汇总，旧47和新49的历史分数不拼接。
