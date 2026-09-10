# 双旗舰 Agent 项目统一工程化路线：Shared Agent Engineering Layer

> 适用项目：
>
> 1. LLM Wiki —— Knowledge Agent
> 2. Knowledge-Augmented Autonomous Coding Agent —— Action Agent
>
> 目标不是把两个项目硬合并成一个仓库，而是抽取**真正稳定、跨项目通用的 Agent Engineering 能力**。

---

# 1. 最终职业叙事

两个旗舰项目分别证明：

```text
LLM Wiki
→ Agent 如何获得正确知识、组织上下文、维持记忆并生成可信答案

Coding Agent
→ Agent 如何安全使用工具、改变环境、验证结果并从失败中恢复
```

共同证明：

> **我具备构建 Knowledge Agent 和 Action Agent 的完整 Agent Engineering 能力。**

---

# 2. 不要“为了统一而统一”

本轮统一的判断标准：

只有满足以下条件才抽公共模块：

1. 两个项目都需要；
2. 行为语义基本一致；
3. 接口稳定；
4. 抽取后不会让调试更困难。

优先统一：

```text
model provider
runtime state primitives
tracing
metrics
cost
error taxonomy
retry policy
evaluation primitives
tool schema / registry
context budget primitives
checkpoint abstraction
```

暂时不要统一：

```text
Wiki KG implementation
FAISS retrieval details
Coding AST graph
Docker sandbox internals
GitHub API domain logic
Wiki story schema
Coding patch/test domain
```

---

# 3. 推荐共享结构

不必立刻独立发布 package。

可以先在两个项目中复制一个稳定接口，验证后再抽成 package。

目标：

```text
agent_core/
├── models/
│   ├── provider.py
│   ├── router.py
│   └── usage.py
├── runtime/
│   ├── state.py
│   ├── checkpoint.py
│   └── execution.py
├── tools/
│   ├── schema.py
│   ├── registry.py
│   ├── result.py
│   └── policy.py
├── context/
│   ├── budget.py
│   └── messages.py
├── resilience/
│   ├── errors.py
│   ├── retry.py
│   └── circuit_breaker.py
├── observability/
│   ├── trace.py
│   ├── metrics.py
│   └── cost.py
├── evaluation/
│   ├── dataset.py
│   ├── result.py
│   ├── runner.py
│   └── regression.py
└── security/
    └── redaction.py
```

---

# 4. 统一数据契约

## 4.1 Model Call

```python
ModelRequest:
    messages
    model
    temperature
    tools
    response_schema
    trace_context
```

```python
ModelResult:
    content
    tool_calls
    usage
    latency_ms
    provider
    model
```

---

## 4.2 Tool

```python
ToolSpec:
    name
    description
    input_schema
    risk_level
    timeout
```

```python
ToolResult:
    success
    data
    error_type
    duration_ms
    metadata
```

Wiki：

```text
knowledge.search
knowledge.entity
knowledge.event
```

Coding：

```text
fs.read
code.search
shell.run
git.diff
github.create_pr
```

共享的是 contract，不是 tool implementation。

---

# 5. 统一 Trace 模型

统一顶层：

```python
AgentTrace:
    trace_id
    task_id
    project
    session_id
    agent_version
    model_version
    prompt_version
    benchmark_case_id
```

统一 span categories：

```text
MODEL
TOOL
RETRIEVAL
CONTEXT
MEMORY
SANDBOX
TEST
POLICY
APPROVAL
```

这样两个项目可以共用 dashboard。

---

# 6. 统一 Error Taxonomy

公共：

```text
ModelTimeout
ModelRateLimit
InvalidModelOutput
ToolTimeout
ToolFailure
ContextOverflow
CheckpointFailure
PolicyDenied
Cancelled
InternalError
```

项目特有：

Wiki：

```text
RetrievalFailure
KnowledgeNotFound
CitationMismatch
```

Coding：

```text
SandboxFailure
TestFailure
PatchConflict
GitFailure
GitHubFailure
ApprovalExpired
```

---

# 7. 统一 Evaluation Result

所有评估输出公共 envelope：

```json
{
  "run_id": "...",
  "project": "wiki|coding",
  "case_id": "...",
  "agent_version": "...",
  "model": "...",
  "scores": {},
  "latency_ms": 0,
  "tokens": 0,
  "cost": 0,
  "status": "pass|fail",
  "failure_type": null
}
```

Wiki scores：

```text
correctness
faithfulness
citation
hallucination
tool_selection
```

Coding scores：

```text
resolved
tests_passed
hidden_tests
patch_acceptance
sandbox_violation
```

这样统一的是**评估基础设施**，不是把指标强行做成一样。

---

# 8. 统一 Benchmark 生命周期

```text
Dataset
→ Runner
→ Agent
→ Trace
→ Evaluator
→ Result
→ Report
→ Regression Decision
```

每个 Benchmark 必须记录：

```text
dataset version
agent commit
prompt version
model/provider
temperature
judge version
timestamp
```

避免出现：

> 0.857、0.942、0.903 等不同实验数字失去上下文后互相比较。

---

# 9. 统一可观测性 Dashboard

至少做 4 个视图。

## Quality

```text
score / resolution rate
hallucination
test pass
regression
```

## Reliability

```text
error rate
retry
recovery
failure category
```

## Performance

```text
p50/p95 latency
tool latency
sandbox time
retrieval time
```

## Cost

```text
tokens
cost/task
cost by model
cost by tool / stage
```

---

# 10. 统一版本语义

建议：

```text
agent_version = git commit
prompt_version = explicit id
dataset_version = semantic version
tool_schema_version = explicit version
```

所有 Benchmark Report 顶部打印：

```text
Project:
Commit:
Dataset:
Prompt:
Model:
Judge:
Date:
```

---

# 11. 统一 Runtime，但保留不同状态

公共 base：

```python
BaseAgentState:
    task_id
    status
    messages
    iteration
    started_at
    trace_id
```

Wiki State 扩展：

```text
query
intent
memory
retrieved_sources
entities
answer
```

Coding State 扩展：

```text
repo
issue
plan
files
patches
tests
approval
```

不要创建一个 50 字段的万能 AgentState。

---

# 12. Memory 不强行完全共享

共享：

```text
checkpoint abstraction
short-term state interface
context budget
summary interface
```

Wiki 重点：

```text
conversation / user memory
```

Coding 重点：

```text
task state / durable execution
```

Coding Agent 不需要为了“统一”强行增加用户长期偏好记忆。

---

# 13. 统一 Task Service（P2）

后期可以做：

```text
                Agent Gateway
                    ↓
             Task / Run Service
               /          \
              ↓            ↓
          Wiki Worker   Coding Worker
```

统一：

```text
task id
status
trace
cancel
resume
result
```

项目内部 runtime 保持独立。

这一步不是当前 P0。

---

# 14. 两项目交叉验证

这是非常好的求职展示。

## 14.1 Coding Agent 改 LLM Wiki

使用 Coding Agent 解决 Wiki 的真实 Issue：

```text
Issue
→ Code Search
→ Knowledge MCP
→ Patch
→ Wiki Unit Test
→ Wiki Benchmark
→ Regression Decision
→ Human Approval
→ PR
```

这是最强的组合 Demo。

不仅测试 Coding Agent 是否“测试通过”，还测试：

> 修改有没有让 Wiki 的 Agent Quality Benchmark 退化。

---

## 14.2 Wiki 为 Coding Agent 提供 Domain Knowledge

在领域 Issue 上做：

```text
Coding Agent only
vs
Coding Agent + Wiki Knowledge MCP
```

这会成为第二个核心实验。

---

# 15. 跨项目 End-to-End Benchmark

选择 5～8 个 Wiki 自身 Issue：

### 类型

```text
Bug
Test
Refactor
Extraction Domain Logic
KG Compatibility
Agent Routing
Evaluation
```

完整链：

```text
GitHub Issue
→ Coding Agent
→ Modify Wiki
→ Unit / Integration Tests
→ Wiki Agent Benchmark
→ Compare Baseline
→ Review
→ Approval
→ PR
```

成功标准：

```text
code tests pass
+
no critical wiki benchmark regression
+
policy pass
+
human approval
```

这非常接近真实 AI 工程团队的 change validation。

---

# 16. 实施路线

## Sprint 0：Audit

两个项目分别输出 audit。

不要写任何大重构。

---

## Sprint 1：Observability 统一

先实现 shared trace schema。

接入两个项目。

产出：

```text
Wiki Trace
Coding Trace
Shared dashboard
```

---

## Sprint 2：Evaluation Infrastructure 统一

统一：

```text
run metadata
result schema
report generator
regression gate
```

保留两个独立 evaluator。

---

## Sprint 3：Reliability

Wiki：

```text
retry / fallback / circuit breaker
```

Coding：

```text
checkpoint / resume / replay safety
```

公共：

```text
error taxonomy
```

---

## Sprint 4：Context / Memory

Wiki：

```text
short-term
summary
long-term
context budget
```

Coding：

```text
durable task state
context selection
```

---

## Sprint 5：Policy / Tool Registry

统一 Tool contract。

Coding Agent 做完整 risk policy。

Wiki 做 read-only / retrieval policy。

---

## Sprint 6：Cross-project Demo

让 Coding Agent 真正修一个 Wiki issue。

自动跑：

```text
pytest
+
Wiki benchmark subset
```

这是最值得录 Demo / 写 README 的阶段。

---

# 17. P0 / P1 / P2 总表

| Priority | Shared | Wiki | Coding |
|---|---|---|---|
| P0 | Audit schema | 保留 W0 | Audit |
| P0 | Trace schema | Observability | Observability |
| P0 | Eval run metadata | Regression Gate | Issue Benchmark |
| P0 | Error taxonomy | Retry/Fallback | Durable Execution |
| P0 | CI primitives | Fast Eval | Deterministic CI |
| P1 | Tool contract | MCP Knowledge Tools | Tool Policy |
| P1 | Context primitives | Memory/Context | Task Context |
| P1 | Metrics/cost | QA cost | Issue cost |
| P1 | Fault framework | Retrieval/LLM faults | Sandbox/API faults |
| P2 | Task service | Worker | Worker |
| P2 | Model router | Model experiments | Model experiments |
| P2 | Shared package | Extract stable modules | Extract stable modules |

---

# 18. 不建议做的“统一”

不要：

- 建一个巨大的 monorepo 然后重写两个项目
- 把 KG、AST Graph 抽成一个“Graph”接口只为了形式统一
- 把 Wiki Memory 塞给 Coding Agent
- 把 Sandbox 放进 Wiki
- 把所有指标压成一个总分
- 为统一而改变成熟的数据 schema
- 把所有模型 prompt 放进一个万能 Prompt Manager
- 上 Kubernetes / 微服务拆分来制造复杂度

---

# 19. 求职展示最终结构

README / Portfolio 中用这个结构：

```text
Flagship 1
Knowledge Agent
LLM Wiki
→ Knowledge Engineering
→ KG/RAG
→ Memory/Context
→ Evaluation
→ Observability

Flagship 2
Action Agent
Coding Agent
→ Planning
→ Tool Use
→ AST Code Intelligence
→ Sandbox
→ Verification
→ Recovery
→ HITL

Shared Engineering Layer
→ Runtime
→ Tool Contract
→ Evaluation
→ Tracing
→ Error Handling
→ CI
```

---

# 20. 最有价值的最终 Demo

输入：

```text
LLM Wiki GitHub Issue:
“修改事件检索路由，解决复杂事件问题中错误工具选择。”
```

Coding Agent：

```text
Read Issue
→ Search Code
→ Query Wiki Domain Knowledge
→ Plan
→ Patch
→ Run Unit Tests
→ Run Wiki Eval Subset
→ Detect Regression
→ Retry
→ Eval Pass
→ Generate Diff
→ Human Approval
→ Create PR
```

最终报告：

```text
Tests: pass
Wiki Benchmark: baseline → new
Tool Selection: baseline → new
Hallucination: no regression
Iterations:
Tokens:
Cost:
Trace:
PR:
```

这一条 Demo 同时连接：

```text
Agent
Coding
RAG/KG
MCP
Sandbox
Testing
Evaluation
Observability
Recovery
HITL
GitHub
```

它比第三个旗舰项目更有求职价值。

---

# 21. 总体 Definition of Done

当两个项目达到：

- [ ] 每次运行都有 Trace
- [ ] 每个 Benchmark 都有版本化元数据
- [ ] 每个失败都有分类
- [ ] 有回归门禁
- [ ] Wiki 有 Memory/Context 实验
- [ ] Coding 有 crash/resume 与 side-effect safety
- [ ] Coding 有固定 Issue Benchmark
- [ ] 两项目共享一套稳定 Agent Core contract
- [ ] Coding Agent 能解决至少一个 Wiki 真实 Issue
- [ ] Wiki Benchmark 能成为 Coding Agent 修改后的质量门禁

就已经形成非常完整的 AI Agent Engineer 项目组合。

---

# 22. 执行原则

最后再次强调：

> **不要等全部做完再投简历。**

建议每完成一个可量化阶段，就同步更新：

```text
README
architecture diagram
benchmark report
resume bullet
interview Q&A
```

你的下一阶段目标不是“再学习更多 Agent 概念”，而是：

> **把已经做过的 Agent 项目转化成一组可验证、可复现、可量化的工程证据。**
