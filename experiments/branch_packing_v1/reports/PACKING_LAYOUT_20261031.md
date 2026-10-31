# G7 分支 packing：布局与隔离检查

日期：2026-10-31。仅 CPU layout/mask 检查；未加载 7B、未跑 D/P 性能、未读取 GPU。

## 已实现

`experiments/branch_packing_v1/layout.py`：

- 共享 tokenized prefix 一次写入 packed 序列；
- 每个 branch 只追加自己的 target tokens；
- 使用显式 4-D mask：prefix 只做 causal；每个 target 只看 shared prefix + 自己的 target 前缀，不看 sibling；
- position ids 对每个 branch 从 prefix 长度重新开始；
- 输出 target positions，供后续目标行读取；
- `assert_isolated` 检查 sibling suffix 泄漏。

示例：

```text
prefix = [101,102,103]
b1 target = [201,202] -> positions [3,4]
b2 target = [301]     -> positions [5]
```

## 已通过的局部检查

```text
python -m unittest discover -s experiments/branch_packing_v1/tests -p 'test_*.py'
6 passed
```

覆盖：

1. 单分支 packed mask 等于普通 causal mask；
2. 双分支 sibling suffix 不可见，shared prefix 可见；
3. 不同 target 长度仍保持各自 target positions；
4. 改另一分支内容，不改变本分支 target positions 与其 prefix+own suffix mask；
5. 单 token target 正确；
6. 空 prefix、空 branches、空 target 被拒绝。

产物：

```text
experiments/branch_packing_v1/layout_example.json
```

## 尚未完成

- 没有真实 P（packed）与 D（串行前缀复用）的模型前向、分数对齐、显存/时间对照；不能报告加速比。
- 没有把 layout 接入 `prefix_reuse_v1` 的 KV cache/crop 路径。
- 未验证不同 dtype、长度、目标行位置编码在真实模型中的误差。
- 未做 88 目标/36 前缀组的整批测试。

本报告只说明布局与 mask 的局部正确性，不构成 G7 性能完成。
