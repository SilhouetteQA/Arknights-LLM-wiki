# Spec 12 — Historical Replay and Sanitized Corpus

> Spec ID：`12`  
> Execution Authority：`IMPLEMENTATION-READY — EXECUTION ONLY AFTER FREEZE`  
> Executable：YES，前提是依赖完成且Candidate未被取代  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Spec 11 effective status `COMPLETE`（canonical prefix + Candidate-bound pending suffix）  
> Target Repository：`WIKI_REPO`、`CODING_REPO`  
> Candidate Phase：post-A staging；no implementation changes

## Normative References

- Master §11.3–11.5、§13.2/13.4、§17 Stage 7、Appendix C/D
- `EVD-PUB-001` 至 `EVD-PUB-007`
- `GOV-FRZ-002`

## Objective

使用Candidate A中已经存在的replay/sanitization能力，对双仓真实历史产物执行L2 semantic replay，生成最小化、可发布的sanitized corpus和Legacy→Foundation语义差异证据。

## No-implementation Boundary

本步骤不得新增或修改任何runner、sanitizer、assertion、Schema、Adapter、test、config或workflow。工具不足、bug或新语义缺口必须停止：Candidate defect回到01–10形成A2；真实contract语义反馈记录为Cycle evidence，不在本步骤改契约。

## Allowed Runtime Outputs

```text
ignored controlled staging directories
sanitized replay candidate artifacts outside Git until Spec14
structured run logs without business payload
status events in controlled staging, not yet canonical Ledger
```

## Source Selection

1. 从两个仓库已存在的真实cost log、trace、benchmark或其他登记artifact选择样本。
2. 来源可跨runtime scope，但每条必须记录source domain、runtime adapter status和evidence role。
3. Wiki offline extraction可用于estimated/unknown/USD/CNY语义，但必须标`historical_replay_only`，不能证明runtime wiring。
4. 原始内容只在受控环境处理；发布输入通过allowlist重新构造，不能先全量序列化再删字段。

## Execution Steps

1. 在A_wiki/A_coding的clean checkout核验Payload Hash与tool identity。
2. 设置strict mode和显式safe run_id，加载预先存在的replay manifest。
3. 运行allowlist extraction，保存observed legacy facts；sanitizer不得执行contract mapping。
4. 用Candidate A Adapter得到actual Foundation mapping，与预登记expected mapping比较。
5. 为每个Rule/Semantic case统计OBSERVED、NOT_OBSERVED、LEGACY_DATA_INSUFFICIENT、REPRODUCTION_RESTRICTED等真实状态。
6. 生成sanitized replay corpus candidate，每条包含record_id、source_class、minimal legacy facts、expected、actual和sanitized record hash。
7. 执行secret/path/forbidden-field/size/Schema扫描。
8. 保留raw business evidence到Cycle policy允许的受控位置；不得复制进contract staging或Git。

## Validation Commands

Wiki：

```powershell
$env:AGENT_CONTRACT_MODE = 'strict'
$env:AGENT_CONTRACT_RUN_ID = 'foundation-0_1_0-c1-wiki-replay'
python scripts/contracts/replay_history.py --run-manifest config/contracts/replay-v0.1.json
```

Coding：

```powershell
$env:AGENT_CONTRACT_MODE = 'strict'
$env:AGENT_CONTRACT_RUN_ID = 'foundation-0_1_0-c1-coding-replay'
python scripts/contracts/replay_history.py --run-manifest config/contracts/replay-v0.1.json
```

## Expected Outputs

- 两仓Candidate-bound L2 run结果。
- sanitized replay corpus candidates。
- observed/expected/actual mapping matrix。
- reproduction restriction与legacy insufficiency说明。
- 可供Spec14发布的Evidence IDs和hashes。

## Acceptance Criteria

- 所有记录绑定正确A SHA与同一Payload Hash。
- 至少使用真实历史artifact而非纯fixture。
- raw prompt/model output/code/diff/path/credential未进入publishable candidate。
- 每个差异明确分类为Adapter defect、Contract feedback、legacy insufficiency或expected semantic correction。
- Deferred source未被误报为runtime integration。

## Stop Conditions

- 工具需要修改。
- 只能通过保存业务原文复现语义。
- sanitizer改变Legacy facts使其等于expected。
- artifact无法绑定来源或Candidate。
- 出现未定义的公共语义，触发`SPEC_INCOMPLETE`。

## Rollback / Handoff

本步骤无tracked实现变化；失败时删除/隔离本次staging并保留诊断。Candidate defect使A superseded；publication-only问题可在Spec14形成B2。Handoff列出样本类别、每个语义状态、受限原因和真实contract feedback候选。
