# W11-α T7 复现性判定

- 基线：`output/eval/w11a_baseline`
- 复跑：`output/eval/w11a_baseline_run2`
- 预登记容差：确定性指标完全一致 · 随机指标均值差 ≤ 0.03 且逐题一致率 ≥ 90%（一致 = 差值 ≤ 0.1，hallucination 须相等）· judge 失败率 ≤ 5% · 安全零容忍

## 判定：**NOT_REPRODUCIBLE**

### 未达项

- 复跑存在失败行 27 条（示例 ['character_complex_005:direct', 'character_complex_001:direct', 'character_complex_007:direct']）
- 确定性指标必须完全一致，但 54 处不同（示例 ['character_complex_001:direct/task_completion: 1.0 vs None', 'character_complex_001:direct/tool_selection_accuracy: 1.0 vs None', 'character_complex_005:direct/task_completion: 1.0 vs None']）
- answer_correctness: 均值差 0.004874892148403753 / 一致率 82.1% 未达预登记要求
- faithfulness: 均值差 0.042238999137187205 / 一致率 57.9% 未达预登记要求
- citation_accuracy: 均值差 0.031238413051538738 / 一致率 59.3% 未达预登记要求
- hallucination: 均值差 0.06937014667817085 / 一致率 72.6% 未达预登记要求

### 说明

判定规则在跑批**之前**固化于 `arknights_wiki/eval/freeze.py:PREREGISTERED_TOLERANCES`；
本判定不调整任何容差（母 Spec §24：不得事后决定容差）。
