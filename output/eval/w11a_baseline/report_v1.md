# Agent 评测报告

> 生成时间：2026-10-14T14:14:28
> 题目数：122 条结果 · 模式：direct

## 〇、冻结元数据（母 Spec §24 BenchmarkSpec）

- spec_version `w11a-1` · aggregation_rules_version `w11a-1`
- harness `b0f2ff68f8e0bb375d95564833ce369344bc90a0`（feature/pre-extraction-baseline）
- corpus `122` 题 · sha256 `238d2e88148a95f9e7a92de8`
- agent `deepseek/deepseek-v4.1-flash` @ `command_goat`
- judge `deepseek/deepseek-v4.1-flash` @ `command_goat`
- temperature_policy `{"agent_graph_default": 0.1, "agent_graph_extended": 0.3, "router": 0.1, "planner": 0.1, "simple_search": 0.3, "judge": 0.1}`
- max_tokens_policy `{"agent_nodes": 4096, "judge": 4096}`
- ⚠️ **judge 与 agent 同模型 = 自评**：指标存在系统性偏差，属已知限制，必须随报告披露。
- ⚠️ **与历史基线不可比**：`output/eval/report_v1_mimo.md` 的 judge 是 `mimo-v2.5`（overall 0.857），与本报告不同源 —— 禁止把两者并列比较。
- 预登记容差（跑批前固化，禁止事后修改）：`{"deterministic_metrics": "exact_match", "deterministic_metrics_list": ["tool_selection_accuracy", "task_completion"], "stochastic_metric_mean_delta_max": 0.03, "stochastic_per_case_agreement_min": 0.9, "judge_failure_rate_max": 0.05, "safety_violations_max": 0, "declared_at": "2026-10-12", "declared_by": "W11-α Spec §3.5（用户批准 2026-10-12）"}`

## 一、总分与分指标

| 指标 | 总分 | direct |
|------|------|------|
| overall | 0.702 | 0.702 |
| answer_correctness | 0.782 | 0.782 |
| faithfulness | 0.614 | 0.614 |
| citation_accuracy | 0.626 | 0.626 |
| tool_selection_accuracy | 0.877 | 0.877 |
| hallucination | 0.311 | 0.311 |
| task_completion | 1.0 | 1.0 |

## 二、分八类

| 类别 | 题数 | overall | correctness | faithfulness | 无幻觉率 | task_completion |
|------|------|---------|-------------|--------------|----------|-----------------|
| 世界观 | 16 | 0.734 | 0.831 | 0.666 | 0.375 | 1.0 |
| 事件 | 18 | 0.616 | 0.517 | 0.483 | 0.222 | 1.0 |
| 人物 | 18 | 0.807 | 0.844 | 0.686 | 0.5 | 1.0 |
| 国家地区 | 16 | 0.744 | 0.869 | 0.644 | 0.312 | 1.0 |
| 战斗力 | 16 | 0.754 | 0.803 | 0.681 | 0.312 | 1.0 |
| 无答案 | 11 | 0.662 | 0.882 | 0.564 | 0.364 | 1.0 |
| 易幻觉 | 11 | 0.429 | 0.755 | 0.373 | 0.0 | 1.0 |
| 组织 | 16 | 0.764 | 0.803 | 0.734 | 0.312 | 1.0 |

## 三、成本汇总

- **总计：¥3.191**
- 分步骤：
  - agent_direct:complex: 69 次 · ¥0.58916
  - agent_direct:simple: 55 次 · ¥0.209176
  - judge: 124 次 · ¥2.39271

## 四、双路径对比（direct vs http）

（当前仅单一模式，无对比）

## 五、覆盖率与失败（W11-α：分母必须可见）

- 结果行数：122 · judge 失败行数：0 · 失败率：0.0%

| 指标 | 有效值 | null（未评/失败） |
|------|--------|------------------|
| answer_correctness | 122 | 0 |
| faithfulness | 122 | 0 |
| citation_accuracy | 116 | 6 |
| tool_selection_accuracy | 122 | 0 |
| hallucination | 122 | 0 |
| task_completion | 122 | 0 |
