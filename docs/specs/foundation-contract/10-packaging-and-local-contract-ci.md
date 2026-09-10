# Spec 10 — Packaging and Local Contract CI

> Spec ID：`10`  
> Execution Authority：`IMPLEMENTATION-READY`  
> Executable：YES，前提是依赖完成  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Spec 09 `COMPLETE`  
> Target Repository：BOTH；coordination/finalization/status tooling only in `WIKI_REPO`  
> Candidate Phase：final pre-A implementation unit

## Normative References

- Master §3.3、§11–17、Appendix C/D/F、Appendix I
- `FND-PKG-*`、`EVD-PUB-*`、`GOV-STAT-*`、`GOV-FRZ-001`

## Objective

在Candidate A冻结前完成并开发验证所有post-freeze依赖：packaging、local gates、L2/L3 harness、sanitizer/publisher、status reducer、Wiki coordinator/finalizer和workflows。Spec 11以后这些实现不得再改变。

## Allowed Changes

Wiki：

```text
pyproject.toml
scripts/contracts/{validate_local,replay_history,publish_evidence,coordinate_cycle,finalize_cycle,status_ledger}.py
config/contracts/{smoke-v0.1,replay-v0.1}.json
.github/workflows/{contract-local,contract-payload-linux,contract-coordinate}.yml
tests/contracts/test_packaging.py
tests/contracts/test_test_baseline.py
必要的contract tooling self-tests
```

Coding：

```text
pyproject.toml
scripts/contracts/{validate_local,replay_history,publish_evidence}.py
config/contracts/{smoke-v0.1,replay-v0.1}.json
.github/workflows/{contract-local,contract-payload-linux}.yml
tests/contracts/test_packaging.py
tests/contracts/test_test_baseline.py
必要的contract tooling self-tests
```

Shared Schema/hash/bundle tooling来自Spec03；若本步骤发现缺陷，必须在A冻结前回到Spec03修正并重验依赖。

## Forbidden Changes

- 在普通PR Local CI clone另一仓。
- Coordination CI调用真实模型或寻找latest successful commit。
- workflow转储环境变量、凭据或private endpoint。
- publisher以denylist删除敏感字段后保存剩余全部对象。
- status reducer忽略非法行、重排events或采用last-line-wins。
- 任何工具延迟到Spec12–15再实现。

## Implementation Steps

### Packaging

1. Wiki/Coding固定`pydantic==2.13.4`，配置build backend和package discovery。
2. 两项目wheel临时包含`agent_core*`；Wiki包含原package，Coding包含当前packages与`adapters*`。
3. `contract.md`、descriptor、schemas作为package data，通过`importlib.resources`读取。
4. clean venv安装wheel并验证import path；不依赖cwd。

### Project validation tools

5. `validate_local.py`实现PR、candidate、smoke gates，复用Spec09 assertions。
6. `replay_history.py`只读取allowlisted historical sources，strict mapping并生成staging facts/results。
7. fresh-smoke harness读取预登记required stages/call/cost/side-effect policy；业务运行结束后独立检查Evidence闭合。
8. invariance comparator运行固定input/response的off/observe并比较四类BusinessInvariant。
9. baseline comparator执行canonical full tests并应用nodeid/fingerprint规则。
10. `publish_evidence.py`从allowlist构造新DTO，执行secret/forbidden-field/path/size/UTF-8/Schema扫描，生成B候选artifacts。

### Status governance

11. Wiki `status_ledger.py`实现Appendix I Event Schema、空ledger genesis、DAG/authority/evidence/transition reducer、append-only diff validation，以及canonical prefix + controlled pending suffix归约。
12. 用合法/非法events测试duplicate ID、missing prerequisite、READY→COMPLETE跳跃、mutually exclusive successors、correction、self-reference、pending suffix hash/append一致性与Candidate隔离。

### Coordination/finalization

13. Wiki coordinator只接受闭合cycle plan和固定A/B，验证ancestry、tree diff、payload/evidence/commit binding、full gate status与coordinator identity。
14. cycle-report generator只输出`PASS/READY_FOR_FINALIZATION`；不得提前COMPLETE。
15. finalizer校验coordination artifact hash，准备严格C allowlist和current pointer，不记录C自身SHA。

### CI

16. 两仓Local Contract Gate独立运行Schema/Payload/L1/project tests/publication safety/package smoke。
17. Windows完整gate；Linux只运行最小同实现canonical hash job。
18. Wiki coordination workflow使用最小只读Coding checkout token，不产生L3。

## Development Validation Commands

两仓：

```powershell
python -m agent_core.contracts.tooling.generate_schemas --check
python -m agent_core.contracts.tooling.verify_payload
python -m pytest agent_core/contracts/conformance -q
python -m pytest tests/contracts -q
python scripts/contracts/validate_local.py --gate pr
python -m build
```

Wiki额外使用完全synthetic、无真实项目Evidence的fixture验证：

```powershell
python scripts/contracts/status_ledger.py validate --ledger docs/specs/foundation-contract/execution-status-events.jsonl
python scripts/contracts/coordinate_cycle.py --plan <FIXTURE_PLAN> --output <TEMP_OUTPUT>
python scripts/contracts/finalize_cycle.py --coordination <TEMP_OUTPUT> --release <TEMP_RELEASE>
```

这里是工具开发验证，不是正式Cycle coordination。

## Expected Outputs

- 两仓可安装wheel与package-data smoke。
- 所有Local/L2/L3/publication工具。
- Wiki status reducer、coordinator、report generator、finalizer。
- 所有workflows与最小权限边界。
- 冻结前工具清单及版本身份。

## Acceptance Criteria

- 从clean environment可import/read schemas。
- Local PR gate不访问另一仓。
- replay/smoke/publisher在synthetic fixtures上可完成并拒绝敏感内容。
- 空Ledger归约到正确genesis；合法pending suffix可临时解锁而不能冒充canonical history；非法events返回`SPEC_STATUS_CONFLICT`。
- Coordinator/finalizer fixtures证明无self-reference且tree allowlists生效。
- Windows/Linux同payload hash。
- Spec 12–15所需能力无待实现项。

## Stop Conditions

- 任一post-freeze步骤仍需要未实现脚本、Schema或workflow。
- package只在repository cwd可import。
- Linux hash与Windows不同。
- coordinator必须使用moving branch或真实模型才能工作。
- reducer无法无歧义归约。

## Rollback / Handoff

在A冻结前可分别回退packaging/scripts/workflows；shared payload变化须双仓重同步。Handoff必须提供完整pre-freeze tooling inventory、版本、synthetic验证结果和“Spec12–15零实现工作”声明。只有本步骤`COMPLETE`才可进入Spec11。
