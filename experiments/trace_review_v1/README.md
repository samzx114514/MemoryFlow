# 实际轨迹提取 v1

只读提取 SP1 短任务、保险未完成任务和一个 CUAD 开发集案例。无模型调用，不修改第三方系统，不产生语义 Gold。

执行顺序：

```bash
python -m unittest -v test_extract.py
python fetch_dcc.py /safe/output/dcc_dev_bundle.json
python extract.py --sp1-root /data2/pkuiti/songzhengxing_intern/memoryflow/runs/sp1 --dcc /safe/output/dcc_dev_bundle.json --output /safe/output/review
```

`fetch_dcc.py` 通过 SSH 245 读取一个固定开发集案例的七份文件，过滤已知凭据和敏感字段；不写 245。

`extract.py` 输出每例的 `flow.json` 和可读说明：

- `source_chunk`：搜索返回的文本片段或合同检索 chunk；网页片段不是完整网页。
- `model_call`：实际输入与调用身份；不按工作流假定谁看过什么。
- `research_summary` / `report_output`：实际保存的总结与报告；缺失保持缺失。
- `text_visible_in_input`：至少 24 个非空白字符的完整文本，去空白后逐字出现在输入中；不是近似语义匹配。
- `model_output_exact_match` / `model_output_contains_analysis`：由保存的模型返回核对输出归属。
- `explicit_chunk_reference_and_verified_offset`：输出明确引用 chunk，且字符偏移能对回原文；不等于法律判断正确。

`organize.py` 是仅针对六个已停止目录的一次性迁移脚本，不要重复执行；原始内容不改，校验迁移前后 SHA256。

原始轨迹与含原文的样例不入 Git。抽样是方便人工讨论的展示样例，不估计准确率或总体覆盖率。
