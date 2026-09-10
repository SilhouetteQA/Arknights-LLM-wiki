# Foundation Contract 子 Spec 执行索引

> 文档角色：静态依赖、权限与导航协调器  
> Execution Authority：`COORDINATION-ONLY`  
> Initial Status：不适用  
> Current Status Source：`execution-status-events.jsonl`  
> Normative Source：[Foundation Contract Master Spec](../2026-09-10-dual-agent-foundation-contract-master-spec.md)

## 1. 使用规则

Master Spec 是规范真相源；01–18 是工作单元的执行投影。若两者冲突，触发 `SPEC_CONFLICT` 并停止。若必要语义在两者中均缺失，触发 `SPEC_INCOMPLETE`，不得自行设计。

本文中的状态均为 genesis 状态，不随工程进度改写。动态状态只从空账本和后续 append-only events 归约：

```text
Initial Status in Child Spec
→ execution-status-events.jsonl
→ Candidate-bound deterministic reducer
→ Current Status
```

当前本地仓库解析是非规范性环境信息：

```text
WIKI_REPO   = D:\AI project\Arknights LLM Wiki
CODING_REPO = D:\AI project\Knowledge-Augmented Autonomous Coding Agent
```

子 Spec 正文只使用 `WIKI_REPO`、`CODING_REPO` 与仓库相对路径。Coding 仓不得保存本目录的副本、DAG 或独立状态摘要。

## 2. 执行级别

| Authority | Executable | 含义 |
|---|---:|---|
| `IMPLEMENTATION-READY` | YES | 前置状态满足后可严格按 Spec 实施 |
| `FEEDBACK-BOUND / PROCESS-ONLY` | NO | 只运行反馈接收与分类流程；契约变化需真实 L2/L3 证据另行确定 |
| `GATE-DEFINED / NOT EXECUTABLE YET` | NO | 只评估是否达到未来门禁，不能转换为当前 coding task |

若工作前提依赖尚未发生的 L2/L3、尚未满足的 Extraction Gate 或未来 family maturity，则必须保持非执行型。

## 3. 子 Spec 清单

| ID | 子 Spec | Authority | Initial Status | Depends On | Target | 主要输出 | A/B/C 阶段 |
|---|---|---|---|---|---|---|---|
| 01 | [Baseline and Governance Skeleton](01-baseline-and-governance-skeleton.md) | IMPLEMENTATION-READY | READY | — | BOTH + WIKI canonical docs | 基线、Registry、治理目录 | pre-A |
| 02 | [Foundation Semantic Models](02-foundation-semantic-models.md) | IMPLEMENTATION-READY | NOT_STARTED | 01 COMPLETE | BOTH mirror | v0.1 Models/Enums/contract rules | pre-A |
| 03 | [Schema, Payload Descriptor, Hash and Mirror Bundle](03-schema-payload-descriptor-hash-and-mirror-bundle.md) | IMPLEMENTATION-READY | NOT_STARTED | 02 COMPLETE | BOTH, authored in WIKI | Schema/hash/bundle/mirror | pre-A |
| 04 | [Evidence Contract and Project-local Sinks](04-evidence-contract-and-project-local-sinks.md) | IMPLEMENTATION-READY | NOT_STARTED | 02 + 03 COMPLETE | BOTH | Evidence DTO/Protocol/sinks | pre-A |
| 05 | [Wiki Facts and Adapter](05-wiki-presence-aware-facts-and-adapter.md) | IMPLEMENTATION-READY | NOT_STARTED | 04 COMPLETE | WIKI | Wiki facts/mapping/runtime | pre-A |
| 06 | [Coding Facts, Adapter and Component Provenance](06-coding-presence-aware-facts-adapter-and-component-provenance.md) | IMPLEMENTATION-READY | NOT_STARTED | 04 COMPLETE | CODING | Coding facts/mapping/runtime/sidecar | pre-A |
| 07 | [Wiki Producer Observation Seams](07-wiki-producer-observation-seams.md) | IMPLEMENTATION-READY | NOT_STARTED | 05 COMPLETE | WIKI | Wiki in-scope wiring | pre-A |
| 08 | [Coding Producer Observation Seams](08-coding-producer-observation-seams.md) | IMPLEMENTATION-READY | NOT_STARTED | 06 COMPLETE | CODING | Coding in-scope wiring | pre-A |
| 09 | [Shared Conformance and Project Contract Tests](09-shared-conformance-and-project-contract-tests.md) | IMPLEMENTATION-READY | NOT_STARTED | 02–08 COMPLETE | BOTH | 完整测试/断言 harness | pre-A |
| 10 | [Packaging and Local Contract CI](10-packaging-and-local-contract-ci.md) | IMPLEMENTATION-READY | NOT_STARTED | 09 COMPLETE | BOTH + WIKI coordinator | 全部 post-freeze 工具与 workflows | pre-A |
| 11 | [Candidate A Freeze, L1 and Full Regression](11-candidate-a-freeze-l1-and-full-regression.md) | IMPLEMENTATION-READY | NOT_STARTED | 10 COMPLETE | BOTH | 固定 A、正式 L1/回归 | A |
| 12 | [Historical Replay and Sanitized Corpus](12-historical-replay-and-sanitized-corpus.md) | IMPLEMENTATION-READY | NOT_STARTED | 11 COMPLETE | BOTH | Candidate-bound L2 | post-A staging |
| 13 | [Fresh Smoke, Coverage and Invariance](13-fresh-smoke-producer-coverage-and-business-invariance.md) | IMPLEMENTATION-READY | NOT_STARTED | 11 COMPLETE | BOTH | Candidate-bound L3/不变性 | post-A staging |
| 14 | [Evidence Publication Commit B](14-evidence-publication-commit-b.md) | IMPLEMENTATION-READY | NOT_STARTED | 11 + 12 + 13 COMPLETE | BOTH + WIKI ledger | B_wiki/B_coding | B |
| 15 | [Coordination and Wiki Finalization C](15-cross-repository-coordination-and-wiki-finalization-c.md) | IMPLEMENTATION-READY | NOT_STARTED | 14 COMPLETE | WIKI coordinator | PASS、C_wiki、Cycle COMPLETE | C |
| 16 | [Cycle 2 Feedback Intake and Evolution](16-cycle-2-feedback-intake-and-evolution-process.md) | FEEDBACK-BOUND / PROCESS-ONLY | NOT_STARTED | Cycle 1 COMPLETE + real L2/L3 issue | WIKI canonical | 反馈决策与新 Cycle proposal | not executable now |
| 17 | [Foundation Family Extraction Gate](17-foundation-family-extraction-gate.md) | GATE-DEFINED / NOT EXECUTABLE YET | NOT_STARTED | Foundation C1 + C2 COMPLETE | CROSS-REPO | Extraction eligibility decision | not executable now |
| 18 | [Future Contract Family Entry Gates](18-future-contract-family-entry-gates.md) | GATE-DEFINED / NOT EXECUTABLE YET | NOT_STARTED | Foundation boundary sufficiently stable | CROSS-REPO | family entry decisions | not executable now |

## 4. 技术依赖 DAG

```text
01 → 02 → 03
     02 + 03 → 04

04 → 05 → 07 ─┐
                ├→ 09 → 10 → 11
04 → 06 → 08 ─┘

──────────────── CANDIDATE A FREEZE BOUNDARY ────────────────

11 ─→ 12 L2 ─┐
  └→ 13 L3 ──┼→ 14 Evidence B → 15 Coordination/C_wiki
11 L1 + full regression ─┘

16 = FEEDBACK-BOUND / PROCESS-ONLY
17 = GATE-DEFINED / NOT EXECUTABLE YET
18 = GATE-DEFINED / NOT EXECUTABLE YET
```

编号是阅读顺序；只有 DAG 和归约状态决定执行解锁。依赖默认要求 upstream `COMPLETE`。

## 5. Candidate Freeze 硬边界

01–10 必须已经实现并开发验证全部 replay、sanitization、smoke、coverage、invariance、publication、coordination、cycle-report、status reducer 和 workflow 能力。

11 冻结 A 后：

- 12–13 只能执行 A 已有工具。
- 14 只能发布 Evidence 与 Wiki 账本事件。
- 15 只能验证固定 A/B、生成协调产物并发布 C_wiki。
- 若工具缺失或错误，A 必须 `SUPERSEDED`，回到所属 01–10 子 Spec形成 A2。

## 6. 状态与证据

空账本定义合法 genesis。第一条事件必须来自真实工程动作，例如 Spec 01 `READY → IN_PROGRESS`，不能记录“Markdown 已生成”。

```text
NOT_STARTED → READY → IN_PROGRESS → VALIDATED → COMPLETE
```

`VALIDATED` 需要命令结果与 Evidence 引用；`COMPLETE` 还需要全部输出、Acceptance Criteria 与 handoff。非法转换返回 `SPEC_STATUS_CONFLICT`，不能通过修改本索引或子 Spec“修正”。

在 A/B/C 两个持久化边界之间，执行器可以把 canonical Ledger 作为不可变前缀，并叠加由 Candidate A reducer 验证的 controlled-staging pending suffix 计算 effective status。该状态只用于解锁当前执行；suffix 必须在下一边界原样append，否则依赖它形成的downstream Evidence无效。由此Spec11可在不先制造B提交的情况下解锁并行Specs12/13。

## 7. 文档完成不推进工程状态

本目录创建完成后，genesis 仍是：

```text
01 READY
02–18 NOT_STARTED
execution-status-events.jsonl = empty
```

这只表示执行投影已经可供使用，不表示任何 Foundation Contract 工程工作已经开始。
