# Agent V1 试点评测报告（20 题 pilot · direct 模式）

> 生成时间：2026-08-16 · 题目：questions_draft.jsonl 前 20 题（character 11 + event 9）
> 打分层：DeepEval 4.1.8（Docker）· judge：deepseek-v4-flash-ga-260731（火山引擎）
> context 依据：Agent 实际检索上下文（simple 路径回退出题材料）

## 一、总指标

| 指标 | 得分 | 解读 |
|------|------|------|
| answer_correctness | 0.75 | 答案事实正确性 |
| faithfulness | 0.233 | 答案基于检索上下文程度 |
| citation_accuracy | 0.54 | 引用准确性 |
| hallucination_rate | 0.2 | 幻觉率（越低越好） |
| task_completion_rate | 1.0 | 任务完成率 |

## 二、关键发现

1. **路由偏差**：多条 complex 预期题被 router 判为 simple（character_complex 11 题中 8 条）→ 不走工具链
2. **角色题 faithfulness 低**：agent 回答超出检索上下文（幻觉率 20%）
3. **事件题正确性 0.608**：多事件综合弱

## 三、明细摘录

- [character_complex_001] route=simple | correct=0.8 faith=0.0 halluc=0.0 cit=0.7
- [character_complex_002] route=complex | correct=1.0 faith=0.0 halluc=1.0 cit=0.6
- [character_complex_003] route=simple | correct=0.3 faith=0.0 halluc=0.0 cit=0.0
- [character_complex_004] route=complex | correct=1.0 faith=0.0 halluc=1.0 cit=0.9
- [character_complex_005] route=simple | correct=1.0 faith=0.0 halluc=1.0 cit=0.0
- [character_complex_006] route=complex | correct=1.0 faith=0.0 halluc=1.0 cit=0.3
- [character_complex_007] route=complex | correct=0.7 faith=0.0 halluc=1.0 cit=0.3
- [character_complex_008] route=complex | correct=1.0 faith=0.0 halluc=1.0 cit=0.4
- [character_complex_009] route=simple | correct=1.0 faith=0.0 halluc=1.0 cit=1.0
- [character_complex_010] route=simple | correct=1.0 faith=0.0 halluc=1.0 cit=1.0
- [character_complex_011] route=simple | correct=1.0 faith=0.0 halluc=1.0 cit=1.0
- [event_complex_001] route=simple | correct=1.0 faith=1.0 halluc=1.0 cit=0.6
- [event_complex_002] route=simple | correct=0.5 faith=0.0 halluc=1.0 cit=0.5
- [event_complex_003] route=complex | correct=0.5 faith=0.0 halluc=1.0 cit=0.4
- [event_complex_004] route=complex | correct=1.0 faith=1.0 halluc=1.0 cit=1.0
- [event_complex_005] route=simple | correct=0.3 faith=1.0 halluc=0.0 cit=0.4
- [event_complex_006] route=complex | correct=0.5 faith=0.0 halluc=1.0 cit=0.5
- [event_complex_007] route=simple | correct=0.4 faith=0.889 halluc=1.0 cit=0.3
- [event_complex_008] route=complex | correct=1.0 faith=0.0 halluc=1.0 cit=0.7
- [event_complex_009] route=simple | correct=0.0 faith=0.778 halluc=0.0 cit=0.2
