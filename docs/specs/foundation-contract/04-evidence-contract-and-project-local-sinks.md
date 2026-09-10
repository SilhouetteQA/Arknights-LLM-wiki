# Spec 04 — Evidence Contract and Project-local Sinks

> Spec ID：`04`  
> Execution Authority：`IMPLEMENTATION-READY`  
> Executable：YES，前提是依赖完成  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Specs 02、03 `COMPLETE`  
> Target Repository：shared payload in BOTH；sink implementations project-local  
> Candidate Phase：pre-A

## Normative References

- Master §4.6–4.7、§10–11、Appendix A.5、Appendix D.4
- `EVD-RUN-*`、`EVD-SINK-*`、`EVD-DATA-001`、`EVD-PUB-*`

## Objective

完成 FoundationObservation、EvidenceRecord、EvidenceSink Protocol、发布 DTO 基础约束，以及两个仓库独立的 FileEvidenceSink。共享层定义数据与能力，不共享文件 I/O 实现。

## Allowed Changes

Shared Wiki authoring payload and Coding mirror：

```text
agent_core/contracts/enums/evidence.py
agent_core/contracts/models/evidence.py
agent_core/contracts/protocols/{__init__,evidence_sink}.py
agent_core/contracts/conformance/test_evidence.py
agent_core/contracts/schemas/{foundation-observation,evidence-record}.schema.json
agent_core/contracts/contract.md
agent_core/contracts/payload-descriptor.json
```

Project-local：

```text
WIKI_REPO/arknights_wiki/adapters/foundation/{__init__,evidence_sink}.py
CODING_REPO/adapters/foundation/{__init__,evidence_sink}.py
```

## Forbidden Changes

- 共享 FileEvidenceSink、目录策略、rotation 或 cleanup 实现。
- 原始 Prompt、response、trace、code、diff、credential 或未脱敏路径。
- 在 sink I/O 失败时再次调用同一 sink 记录失败。
- observe 中因 Evidence 失败改变业务结果。
- 把 staging 称为 raw business evidence。

## Implementation Steps

1. 定义 FoundationObservation，允许表达 Usage、Cost、CostSummary 与边界 ErrorEnvelope，但不成为业务 Result。
2. 定义 EvidenceRecord，包含安全 ID、repository/commit、contract identity、mode、producer/stage、allowlisted input facts、foundation output/error 和 validation status。
3. 强制 `PASS → output present/error null`、`FAIL → error present`，单事件 canonical JSON 不超过 64 KiB。
4. 定义 run_id regex 与 UUID/ULID event_id；任何 ID 均不可参与任意路径拼接。
5. 定义窄 EvidenceSink Protocol，只要求接受合法 record 并显式报告持久化失败。
6. 分别实现两个 FileEvidenceSink：同目录 `.tmp`、flush/close、`os.replace`、正式文件只用 `.json`。
7. sink failure 只写结构化应用日志与内存 failure counter，使用 `evidence.*` infrastructure code，不污染 Foundation semantic error。
8. 定义 publishable Evidence DTO 的 allowlist/size/schema 基础，使 Spec 10 的 publisher 不需要再修改共享模型。
9. 更新 Schema/descriptor/hash，并通过 Spec 03 bundle 重新同步 Coding；禁止在 Coding 手改。

## Required Invariants

```text
Shared DTO / Protocol != shared I/O implementation
Staging evidence != raw business payload
Sink failure != business failure
Sink failure = evidence gate failure
partial .tmp != valid evidence
```

## Validation Commands

```powershell
python -m pytest agent_core/contracts/conformance/test_evidence.py -q
python -m agent_core.contracts.tooling.generate_schemas --check
python -m agent_core.contracts.tooling.verify_payload
```

项目 sink tests 的完整位置与跨模式注入由 Spec 09完成；本步骤至少验证合法写入、原子 replace、invalid ID、超限和 injected I/O failure。

## Expected Outputs

- Shared Evidence DTO、Enum、Protocol 和 Schema。
- Wiki/Coding 独立 FileEvidenceSink。
- 明确的 failure counter/log 最后防线。
- publishable Evidence allowlist model 基础。

## Acceptance Criteria

- Shared payload 不 import 任一项目。
- 合法并发事件不互相覆盖，event_id 唯一。
- `.tmp` 不被读取为证据。
- observe sink failure 不改变注入的业务返回；该 run 明确失效。
- 所有敏感/非 JSON/超限 record 被拒绝。
- 更新后双仓 Payload Hash 重新一致。

## Stop Conditions

- 需要共享本地文件目录或项目配置才能定义 Protocol。
- EvidenceRecord 必须携带业务原文才能通过某个 producer。
- sink failure 无法与 Foundation semantic error 分离。
- Coding mirror 出现局部修改需求。

## Rollback / Handoff

关闭尚未接线的 sink 并删除两个项目本地实现即可；共享 Evidence payload 变更必须经 Wiki canonical 回退和 bundle 重同步，不能只回退一仓。Handoff 列出 Schema/hash、最大 event size、失败诊断方式和两个 sink 的原子写验证。
