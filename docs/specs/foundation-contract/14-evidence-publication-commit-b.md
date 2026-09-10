# Spec 14 — Evidence Publication Commit B

> Spec ID：`14`  
> Execution Authority：`IMPLEMENTATION-READY — PUBLICATION ONLY`  
> Executable：YES，前提是全部依赖完成  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Specs 11、12、13 effective status `COMPLETE`，且pending suffix可原样append  
> Target Repository：`WIKI_REPO`、`CODING_REPO`；Ledger only in Wiki  
> Candidate Phase：Evidence Publication B

## Normative References

- Master §11.3–11.5、§12.5、§16.3/16.7、Appendix D/F.4/I.4
- `EVD-PUB-*`、`FND-VER-004/005`、`GOV-STAT-004`

## Objective

把针对固定A的L1/L2/L3、回归和coverage结果转为最小publishable Evidence，并分别形成B_wiki和B_coding。B只声明验证事实，不改变被验证对象。

## Allowed Changes

两仓各自：

```text
docs/contracts/releases/0.1.0/contract-manifest.json
docs/contracts/releases/0.1.0/changelog.md
docs/contracts/releases/0.1.0/validation/<wiki|coding>/run-manifest.json
docs/contracts/releases/0.1.0/validation/<wiki|coding>/evidence-manifest.json
docs/contracts/releases/0.1.0/validation/<wiki|coding>/validation-report.md
docs/contracts/releases/0.1.0/validation/<wiki|coding>/rule-traceability.json
docs/contracts/releases/0.1.0/validation/<wiki|coding>/sanitized-replay-corpus.jsonl
```

Wiki B额外只允许append：

```text
docs/specs/foundation-contract/execution-status-events.jsonl
```

Coding B不得创建Ledger、Spec状态摘要、cycle-report或current pointer。

## Forbidden Changes

- Payload、Adapter、producer、tests、scripts、config、pyproject、lock或workflow。
- 修改/删除/reorder A中的Ledger行。
- 在Evidence Manifest保存自身hash或B SHA。
- 在B中保存包含B SHA的cycle-plan。
- 发布raw prompt/response/code/diff/trace/credential/private path。

## Publication Steps

1. 对每仓确认A仍是被验证SHA，Specs11–13 Evidence全部绑定A和expected Payload。
2. 用A中publisher从allowlist重新构造release DTO并运行全部安全扫描。
3. 生成共同contract manifest；其canonical payload provenance固定指向A_wiki，Coding副本内容相同。
4. 生成项目独立Evidence Manifest，`verified_repository_commit`分别指A_wiki/A_coding。
5. Validation Report包含semantic mapping、coverage、reproducibility、回归和benchmark reference，不复制敏感证据。
6. Rule traceability只引用test/evidence IDs；sanitized corpus保存最小事实。
7. Wiki ledger先逐字节append已验证的Spec11–13 pending suffix，再追加绑定A的Spec14 publication events；事件不写B SHA。
8. 分别形成B_wiki/B_coding固定提交。
9. 验证`A is ancestor of B`且`diff(A,B)`完全属于allowlist；Wiki ledger必须为纯字节追加。

## Evidence Manifest Required Results

```text
contract tests = PASS
historical replay = PASS
fresh smoke = PASS
Wiki regression = PASS_WITH_KNOWN_BASELINE_FAILURES
Coding regression = PASS
producer coverage = required stages satisfied
benchmark = historical reference only
```

## Validation Commands

```powershell
python scripts/contracts/publish_evidence.py --candidate <A_SHA> --release-version 0.1.0
```

形成B后使用已有validator检查ancestry、diff allowlist、manifest schema、secret scan、payload binding和Ledger append-only。具体CLI参数以A中的已冻结接口为准，不得在本步骤修改。

## Expected Outputs

- B_wiki与B_coding SHA。
- 两份独立Evidence Manifest及其待协调canonical hash。
- 同一Contract Manifest/Payload identity。
- Wiki canonical状态事件追加。
- 无cycle plan/cycle report/current pointer。

## Acceptance Criteria

- B tree等于A tree加允许Evidence文件；无其他变化。
- 两Evidence均引用各自A和相同Payload。
- 发布扫描全通过。
- Wiki Ledger历史前缀逐字节不变且新events可合法归约。
- Coding不含Spec/Ledger shadow copy。

## Stop Conditions

- Evidence揭示Candidate实现/契约/test defect。
- publisher必须修改才能正确净化。
- manifest需要引用B自身才能闭合。
- A/B之间混入无关commit或文件。
- 敏感扫描失败。

## Retry / Rollback

Candidate defect：A superseded，回到前置Spec并重做L1/L2/L3。Publication/sanitization formatting defect：A保持，失败B append-only保留，使用同A形成B2。不得覆盖旧B或静默删除失败Evidence。
