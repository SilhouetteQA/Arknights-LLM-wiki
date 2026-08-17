# Agent V1 评测报告

> 生成时间：2026-08-17T21:54:10
> 题目数：100 条结果 · 模式：direct
> judge：opencode zen/go 网关 mimo-v2.5（judge 精确计费；agent 侧成本为字符估算，含 estimate 标记）

## 一、总分与分指标

| 指标 | 总分 | direct |
|------|------|------|
| overall | 0.857 | 0.857 |
| answer_correctness | 0.765 | 0.765 |
| faithfulness | 0.779 | 0.779 |
| citation_accuracy | 0.733 | 0.733 |
| tool_selection_accuracy | 0.99 | 0.99 |
| hallucination | 0.887 | 0.887 |
| task_completion | 0.99 | 0.99 |

## 二、分八类

| 类别 | 题数 | overall | correctness | faithfulness | 无幻觉率 | task_completion |
|------|------|---------|-------------|--------------|----------|-----------------|
| 世界观 | 16 | 3.058 | 0.894 | 0.85 | 0.938 | 1.0 |
| 事件 | 18 | 3.179 | 0.417 | 0.588 | 0.765 | 0.944 |
| 人物 | 18 | 3.36 | 0.906 | 0.85 | 0.889 | 1.0 |
| 国家地区 | 16 | 3.028 | 0.838 | 0.719 | 0.875 | 1.0 |
| 战斗力 | 16 | 3.017 | 0.794 | 0.794 | 0.875 | 1.0 |
| 组织 | 16 | 3.06 | 0.769 | 0.875 | 1.0 | 1.0 |

## 三、成本汇总

- **总计：¥26.4583**
- 分步骤：
  - agent_direct:complex: 87 次 · ¥0.586128
  - agent_direct:simple: 53 次 · ¥0.225192
  - deepeval_smoke: 8 次 · ¥0.0
  - generate:character:complex: 23 次 · ¥0.039613
  - generate:character:simple: 23 次 · ¥0.026174
  - generate:combat_power:complex: 10 次 · ¥0.018025
  - generate:combat_power:simple: 12 次 · ¥0.016429
  - generate:event:complex: 11 次 · ¥0.013224
  - generate:event:simple: 14 次 · ¥0.018321
  - generate:organization:complex: 10 次 · ¥0.021325
  - generate:organization:simple: 13 次 · ¥0.018906
  - generate:region:complex: 10 次 · ¥0.015693
  - generate:region:simple: 12 次 · ¥0.015871
  - generate:worldview:complex: 10 次 · ¥0.019383
  - generate:worldview:simple: 12 次 · ¥0.014414
  - judge: 2817 次 · ¥25.276106
  - meta_eval: 158 次 · ¥0.133464

## 四、双路径对比（direct vs http）

（当前仅单一模式，无对比）
