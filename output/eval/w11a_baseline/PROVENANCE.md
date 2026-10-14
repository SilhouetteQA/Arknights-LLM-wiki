# W11-alpha 冻结基线 provenance（Wiki 侧）

- corpus: 122 题 · sha256 238d2e88148a95f9e7a92de80bbd79d15dc307e7b01f2700f040e3041bd0f797
- 冻结清单: enchmarks/arknights_bench/frozen/w11a-v1/MANIFEST.json（harness 2ded09512fb9）
- 模型: agent deepseek/deepseek-v4.1-flash @ command_goat；judge deepseek/deepseek-v4.1-flash（**与 agent 同模型 = 自评**，已知限制）
- 执行: --mode direct --workers 4（见 RUN_COMMAND.txt）
- 结果: 122 行 · 失败行 0 · 回退文案 0 · judge 失败 0
- 指标: overall 0.700 / correctness 0.769 / faithfulness 0.609 / citation 0.632 / tool_selection 0.877 / hallucination 0.328 / task_completion 0.984

## 两次 harness commit 的 provenance（必须披露）

本基线由两段组成：**109 行**在 6bbe159（D1–D4 修复后）跑出，**13 行**在 2ded095（D5/D6 修复后）重试跑出。
两次之间的 arknights_wiki 改动仅 eval/metrics.py(+7/−2) 与 eval/runner.py(+44/−1) ——
**agent / extraction / judge 代码零改动**。因此答案生成与评分语义跨这两段是一致的；
D5 只影响聚合展示，D6 只影响失败行的 category 字段。

- 原始 13 行失败：provider 400 invalid request error（偶发，重试 13/13 全部成功）
- 重试使用 --retry-errors（显式移除失败行后断点续跑），日志见 output/_w11_probe/t6a_retry.log

## 已知限制

1. judge 与 agent 同模型（自评），指标存在系统性偏差。
2. 与历史 0.857 基线**不可比**（judge 身份、provider、代码均不同）。
3. citation_accuracy 有 8 行为 null：答案为「不涉及引用」时的设计行为，不是失败。
4. D4 后 faithfulness/hallucination 才真正以「实际检索资料」为判据；修复前的同名列不是同一口径。
`