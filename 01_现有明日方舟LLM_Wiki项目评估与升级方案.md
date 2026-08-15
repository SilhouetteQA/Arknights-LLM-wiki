# 项目一：现有《明日方舟》LLM Wiki 项目评估与升级方案

## 1. 当前项目定位

项目名称建议统一包装为：

> **基于大规模剧情知识图谱与 LangGraph Agent 的《明日方舟》领域智能问答系统**

项目当前已经明显超过普通的「RAG Chatbot / PDF 问答」项目。

已具备的核心能力：

- 覆盖主线第 1–15 章、67 个支线/插曲活动、21 个故事集、6 个集成战略主题
- 共 109 章剧情数据
- 三遍 LLM 信息抽取 Pipeline
- 非结构化剧情 → 结构化知识
- 知识图谱 / 结构化知识库
- LangGraph
- ReAct Agent
- 自然语言问答
- 领域知识检索

因此，下一阶段**不建议继续扩大剧情数据量，也不建议简单增加更多 RAG 功能**。

核心目标应该从：

> 「证明我会 LLM + RAG + Agent」

升级为：

> **「证明我能把 Agent 做成可评测、可观测、可控、可恢复的生产级系统」**

---

# 2. 当前能力评价

| 能力 | 当前判断 | 说明 |
|---|---|---|
| Python / 后端基础 | 🟢 | 已具备项目落地能力 |
| LLM API | 🟢🟢 | 已经不是简单 API Demo |
| Prompt Engineering | 🟢🟢 | 三遍 LLM 抽取 Pipeline 已体现 |
| LLM 数据处理 | 🟢🟢 | 项目亮点 |
| RAG | 🟢🟢 | 已经有领域知识检索闭环 |
| Knowledge Graph | 🟢🟢 | 明显区别于普通 RAG 项目 |
| LangGraph | 🟢🟢 | 已经有实际应用 |
| ReAct Agent | 🟢🟢 | 已经有实际 Agent |
| Agent Tool Use | 🟡 | 建议进一步系统化 |
| Multi-Agent | 🟡 | 当前项目可升级 |
| Memory | 🟡 | 建议补充 |
| Human-in-the-loop | 🟡 | 建议补充 |
| MCP | 🔴/🟡 | 建议重点补 |
| Agent Evaluation | 🔴 | 当前最值得补的能力之一 |
| Observability / Tracing | 🔴 | 当前最值得补的能力之一 |
| Agent Security | 🔴 | 建议补 |
| Long-running Agent | 🔴 | 建议通过新项目补 |
| Sandbox / Code Execution | 🔴 | 建议通过 Coding Agent 补 |
| Agent Deployment | 🟡 | 建议进一步生产化 |
| Cost / Latency Optimization | 🟡 | 建议加入量化指标 |

---

# 3. 当前项目最大的提升方向

## 3.1 从「问答 Agent」升级成「Research Agent」

当前：

```text
User
 ↓
ReAct Agent
 ↓
Knowledge Retrieval
 ↓
Answer
```

建议升级：

```text
User
 ↓
Task / Intent Analysis
 ↓
Planner
 ↓
┌──────────────────────────────┐
│ Knowledge Agent              │
│ Web Research Agent           │
│ Character / Event Agent      │
│ Timeline Agent               │
└──────────────────────────────┘
 ↓
Evidence Aggregation
 ↓
Critic / Fact Checker
 ↓
Answer Generator
 ↓
Citation / Evidence Validation
 ↓
Final Answer
```

这样项目从「问答系统」升级为：

> **领域自治研究 Agent**

---

# 4. 建议增加 Planner

目前 ReAct 更偏向：

```text
Observe → Think → Act → Observe
```

可以增加显式任务规划：

```text
Question
 ↓
Planner
 ↓
Task Graph
 ↓
Parallel / Sequential Execution
 ↓
Result Aggregation
```

例如：

> 「分析凯尔希与罗德岛的历史关系，并按照时间线整理。」

Planner 可以拆成：

1. 找凯尔希相关人物实体
2. 找罗德岛历史事件
3. 找关键时间节点
4. 建立人物—组织—事件关系
5. 生成时间线
6. 检查证据
7. 最终回答

这样能够体现真正的 Agent Workflow Engineering。

---

# 5. 建议增加 Multi-Agent

不建议为了「多 Agent」而多 Agent。

应该根据职责划分：

```text
Research Manager
       │
 ┌─────┼───────────┐
 ↓     ↓           ↓
KG    Timeline   Character
Agent   Agent      Agent
 │       │          │
 └───────┼──────────┘
         ↓
      Critic
         ↓
    Final Writer
```

重点展示：

- Agent routing
- Agent handoff
- Parallel execution
- State sharing
- Failure recovery

---

# 6. 建议增加 MCP

把现有知识库包装成 MCP Server。

例如：

```text
Arknights Agent
       ↓
      MCP
       ↓
Arknights Knowledge Server
       ↓
┌─────────────────────────┐
│ search_entities()       │
│ search_events()         │
│ query_relationship()    │
│ query_timeline()        │
│ search_story()          │
└─────────────────────────┘
```

这样项目可以证明：

> Agent 不只是调用内部 Python function，而是可以通过标准化 Tool Protocol 访问外部能力。

进一步可以加入：

```text
Knowledge MCP
Web Search MCP
Database MCP
Filesystem MCP
```

---

# 7. 最重要：增加 Evaluation

这是现有项目最值得补的能力。

建立一个固定 Benchmark：

```text
100–500 条高质量问题
```

至少分成：

- 单跳事实问题
- 多跳关系问题
- 时间线问题
- 人物关系问题
- 跨章节问题
- 需要多工具的问题
- 无答案问题
- 容易产生幻觉的问题

建立指标：

```text
Answer Correctness
Faithfulness
Context Precision
Context Recall
Citation Accuracy
Tool Selection Accuracy
Task Completion Rate
Hallucination Rate
Latency
Token Usage
Cost
```

形成：

```text
Agent V1 → 82%
Agent V2 → 89%
Agent V3 → 94%
```

这比单纯展示 Demo 的说服力高很多。

---

# 8. 增加 Observability / Tracing

每次 Agent 执行都记录完整 Trace：

```text
Trace
├── User Request
├── Planner
├── Agent Handoff
├── Retrieval
├── Tool Call
├── LLM Call
├── Retry
├── Critic
└── Final Answer
```

每一步记录：

- latency
- input/output tokens
- model
- tool
- error
- retry
- cost
- final score

建议技术方向：

- OpenTelemetry
- Langfuse
- LangSmith
- Phoenix

不需要全部使用。

优先选择：

> **Langfuse + OpenTelemetry**

---

# 9. 增加 Memory

可以加入：

## Short-term Memory

保存当前任务状态：

```text
messages
current_plan
tool_results
agent_state
```

## Long-term Memory

保存：

- 用户偏好
- 用户常问主题
- 历史研究任务
- 用户明确保存的信息

## Episodic Memory

保存：

> 「之前做过什么任务、结果是什么」

让系统能够：

```text
当前问题
 ↓
读取历史任务
 ↓
复用已有研究结果
 ↓
减少重复检索
```

---

# 10. 增加 Human-in-the-loop

例如用户要求：

> 「根据当前知识库生成一份完整人物关系报告并发布。」

系统可以：

```text
Agent 生成报告
       ↓
Human Review
       ↓
Approve / Reject / Modify
       ↓
Final Action
```

尤其是：

- 高风险 Tool
- 修改数据
- 删除数据
- 发布内容
- 外部 API 写操作

必须支持人工确认。

---

# 11. 增加 Guardrails / Security

至少演示：

### Prompt Injection

外部内容：

```text
Ignore previous instructions...
```

Agent 不应该执行。

### Tool Permission

定义：

```text
READ
WRITE
DELETE
ADMIN
```

不同 Agent 具有不同权限。

### Data Isolation

确保：

```text
User A Memory
≠
User B Memory
```

### Input / Output Validation

使用结构化 Schema 验证：

```text
LLM
 ↓
Pydantic / JSON Schema
 ↓
Validated Output
```

---

# 12. 增加 Failure Recovery

这是从 Demo 到工程系统的重要一步。

例如：

```text
Tool Failed
 ↓
Retry
 ↓
仍失败？
 ↓
Fallback Tool
 ↓
仍失败？
 ↓
Human Escalation
```

需要考虑：

- timeout
- retry
- exponential backoff
- circuit breaker
- checkpoint
- resume
- idempotency
- partial failure

LangGraph 的状态与 checkpoint 能很好地承载这一层。

---

# 13. 增加成本和性能优化

不要只说：

> 「系统能运行。」

应该能回答：

> 「一次复杂问题平均多少钱？多久？如何优化？」

建议记录：

```text
P50 Latency
P95 Latency
Tokens / Request
Cost / Request
Tool Calls / Request
Retry Rate
Success Rate
```

优化手段：

- Prompt Cache
- Retrieval Cache
- Result Cache
- Model Routing
- Small Model / Large Model 分工
- Parallel Tool Calls
- Context Compression
- Streaming

---

# 14. 最终建议的升级架构

```text
                         User
                          │
                          ↓
                    API Gateway
                          │
                          ↓
                   Intent / Router
                          │
                          ↓
                       Planner
                          │
             ┌────────────┼────────────┐
             ↓            ↓            ↓
       Knowledge Agent  Research   Timeline
             │           Agent       Agent
             ↓            ↓            ↓
            MCP          MCP         MCP
             │            │            │
             └────────────┼────────────┘
                          ↓
                  Evidence Aggregator
                          ↓
                       Critic
                          ↓
                    Fact Checker
                          ↓
                  Human Approval
                          ↓
                    Final Answer
                          │
          ┌───────────────┼────────────────┐
          ↓               ↓                ↓
       Memory         Evaluation      Observability
          │               │                │
          ↓               ↓                ↓
     PostgreSQL        Dataset          Langfuse
     Vector DB         Metrics          OTel
```

---

# 15. 项目升级后的简历定位

不要再只写：

> 「基于《明日方舟》剧情的 AI 问答系统」

建议包装为：

> **大规模领域知识图谱与自治研究 Agent**

突出：

- 109 章剧情知识工程
- 三阶段 LLM 信息抽取 Pipeline
- Knowledge Graph
- LangGraph Agent
- ReAct
- Planner / Multi-Agent
- MCP
- Memory
- Evaluation
- Observability
- Guardrails
- Human-in-the-loop
- Failure Recovery

最终形成一个真正能代表你 Agent Engineering 能力的旗舰项目。

---

# 16. 优先级

### P0：强烈建议

- [ ] Agent Evaluation
- [ ] Observability / Tracing
- [ ] MCP
- [ ] Planner
- [ ] Failure Recovery

### P1：建议

- [ ] Multi-Agent
- [ ] Memory
- [ ] Human-in-the-loop
- [ ] Guardrails
- [ ] Cost / Latency Optimization

### P2：有时间再做

- [ ] Browser Agent
- [ ] Long-running Task
- [ ] Agent Self-improvement
- [ ] 更复杂的 Knowledge Graph reasoning

---

# 17. 最终目标

这个项目不要继续追求「功能更多」。

最终应该证明：

> **我能够设计、实现、评测、调试和部署一个生产级 Agent System。**

这是你从：

> LLM 应用开发者

走向：

> **AI Agent Engineer**

最重要的一次升级。
