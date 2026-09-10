# Spec 13 — Fresh Smoke, Producer Coverage and Business Invariance

> Spec ID：`13`  
> Execution Authority：`IMPLEMENTATION-READY — EXECUTION ONLY AFTER FREEZE`  
> Executable：YES，前提是依赖完成且Candidate未被取代  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Spec 11 effective status `COMPLETE`（canonical prefix + Candidate-bound pending suffix）  
> Target Repository：`WIKI_REPO`、`CODING_REPO`  
> Candidate Phase：post-A staging；parallel with Spec 12

## Normative References

- Master §7.3、§10、§11.1–11.2、§13.3–13.4、§14.1/14.3、§17 Stage 8
- `FND-MODE-*`、`EVD-RUN-*`、`EVD-SINK-*`、`FND-REG-005`

## Objective

使用Candidate A现有harness完成L3真实路径旁路Smoke、Registry stage coverage和fixed-response off/observe BusinessInvariant。真实运行证明接线当前有效；确定性不变性证明接线未改变业务。

## No-implementation Boundary

不得修改smoke harness、producer checker、invariance comparator、Adapter、sink、config、tests、business code或workflow。任何工具/接线缺陷使A superseded并回到01–10；不能在本步骤热修。

## Pre-registered Run Manifest

每次真实运行前固定：

```text
Candidate A SHA and Payload Hash
model/provider
case IDs
required (producer_id, mapping_stage) set
expected/max calls
estimated cost cap
network requirements
side-effect policy
timeout/duration cap
Evidence directory and explicit run_id
```

不得根据运行结果事后删除未覆盖stage或提高成本上限。

## Execution Steps

1. 在两仓clean A checkout验证mode、payload、registry和sink配置。
2. Wiki只执行read/query/eval路径；Coding只使用local fixture repo/sandbox，允许本地测试，禁止push/create PR。
3. 以`AGENT_CONTRACT_MODE=observe`执行真实模型/Trace/Eval/Benchmark相关路径。
4. 业务结束后独立检查Evidence目录；业务成功不等于Evidence成功。
5. 验证所有event version/payload/repository/A SHA/mode一致、event ID唯一、无`.tmp`、sink_failure_count=0。
6. Registry要求`ALL_STAGES`时覆盖每个stage；`ONE_OF`按预登记策略判断。一个成功event不能代表完整run。
7. 使用固定input和固定model response分别执行off与observe，比较output、decision、side effects、Legacy telemetry。
8. 记录actual calls/tokens、known/unknown cost、duration、producer coverage和Evidence status。
9. historical benchmark只记录reference/reproducibility，不能参与Cycle PASS。

## Validation Commands

Wiki：

```powershell
$env:AGENT_CONTRACT_MODE = 'observe'
$env:AGENT_CONTRACT_RUN_ID = 'foundation-0_1_0-c1-wiki-smoke'
python scripts/contracts/validate_local.py --gate smoke --run-manifest config/contracts/smoke-v0.1.json
```

Coding：

```powershell
$env:AGENT_CONTRACT_MODE = 'observe'
$env:AGENT_CONTRACT_RUN_ID = 'foundation-0_1_0-c1-coding-smoke'
python scripts/contracts/validate_local.py --gate smoke --run-manifest config/contracts/smoke-v0.1.json
```

确定性不变性使用A中既有项目tests/harness，不调用随机live model比较精确分数。

## Expected Outputs

- 双仓闭合L3 run artifacts。
- producer/stage coverage matrix。
- off/observe四类BusinessInvariant comparison。
- sink/adapter failure counts和semantic coverage。
- side-effect policy compliance record。

## Acceptance Criteria

- 所有预登记required stages满足。
- observe失败不会改变业务，但任何Evidence failure使L3 Gate失败。
- fixed-response off/observe四类结果精确一致。
- Coding无push/PR/approval/sandbox violation；Wiki无超范围写入。
- Event与run manifest绑定正确A和Payload。
- 未观察合法语义如实标NOT_OBSERVED而非FAIL或伪造。

## Stop Conditions

- 达到max calls/cost/duration cap。
- 发生未授权外部副作用。
- Evidence无法落盘或run不闭合。
- 需要修改工具、接线或tests。
- live provider变化使预登记运行无法解释。

## Rollback / Handoff

停止新调用，将mode切off；保留已产生的受控诊断，不把无效run发布为Evidence。Candidate defect使A superseded；provider/环境暂时问题可使用同A和新run_id重跑，但必须保留失败run历史。Handoff分别报告业务结果与Evidence结果。
