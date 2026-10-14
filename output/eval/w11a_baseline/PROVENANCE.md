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


## T7 复现性判定：NOT_REPRODUCIBLE（未放宽容差）

复跑 output/eval/w11a_baseline_run2（同 corpus / 同参数 --mode direct --workers 4）。

| 指标 | 均值差 | 逐题一致率 | 预登记要求 |
|---|---|---|---|
| answer_correctness | 0.005 | 82.1% | ≤0.03 / ≥90% |
| faithfulness | 0.042 | 57.9% | 同上 |
| citation_accuracy | 0.031 | 59.3% | 同上 |
| hallucination | 0.069 | 72.6% | 同上 |

- **均值稳（answer_correctness 0.005），但逐题一致率 58–82% 远低于预登记的 90%** —— LLM 自评 judge 在 0.1 网格上的固有抖动。
- 确定性指标在「两次都跑成功」的题上一致；报告里的 54 处不一致全部来自复跑的 27 行 provider 400 失败（1.0 vs None）。
- 复跑的 provider 失败率 27/122 = 22.1%（首次 47/122，重试后仍失败 27），**远超预登记的 5% 上限** ⇒ 该网关在 workers=4 下不稳定。
- 判定规则见 scripts/eval/check_reproducibility.py，容差固化于 rknights_wiki/eval/freeze.py:PREREGISTERED_TOLERANCES（跑批前登记，未修改）。
