# Spec 03 — Schema, Payload Descriptor, Hash and Mirror Bundle

> Spec ID：`03`  
> Execution Authority：`IMPLEMENTATION-READY`  
> Executable：YES，前提是依赖完成  
> Initial Status：`NOT_STARTED`  
> Current Status Source：`execution-status-events.jsonl`  
> Depends On：Spec 02 `COMPLETE`  
> Target Repository：author in `WIKI_REPO`；verified mirror in `CODING_REPO`  
> Candidate Phase：pre-A

## Normative References

- Master §3.1、§12、Appendix A.1
- `FND-PKG-001`、`FND-VER-001` 至 `FND-VER-006`

## Objective

建立无自引用、跨 Windows/Linux 确定的 Schema 与 Contract Payload 身份，并用受控 bundle 将 Wiki canonical payload 原子提升到 Coding mirror。

## Allowed Changes

Wiki：

```text
agent_core/contracts/schemas/**
agent_core/contracts/tooling/{__init__,canonical_json,generate_schemas,verify_payload,bundle}.py
agent_core/contracts/payload-descriptor.json
agent_core/contracts/conformance/test_versioning.py
```

Coding：

```text
agent_core/__init__.py
agent_core/contracts/**
```

Coding 内容只能来自验证后的 bundle。

## Forbidden Changes

- 将 `contract_payload_hash` 写回 payload descriptor。
- 将 maturity state、repository commit、Evidence 或时间戳放入 Payload。
- 对 ZIP/archive hash 冒充 Payload Hash。
- Coding 接收后局部修补共享镜像。
- Schema generator 自动覆盖已提交快照的 `--check` 行为。

## Implementation Steps

1. 实现 canonical JSON：sorted keys、compact separators、UTF-8、no BOM。
2. 实现 Schema generator，默认输出临时目录并与 committed snapshots 比较；显式生成模式才写 snapshot。
3. 计算每个 schema hash 和按 schema ID 排序的 `schema_set_hash`。
4. 从实际版本、工具版本、schema hashes 和 Rule IDs 生成无自引用 `payload-descriptor.json`。
5. 实现 canonical file bundle：相对路径统一 `/`、排序、文本换行 LF、JSON canonical、`path + NUL + content + NUL`。
6. 计算 `contract_payload_hash` 与 `payload_descriptor_hash`；descriptor 自身参与前者但不保存前者。
7. 实现 deterministic transport bundle；排除 mtime、permissions、absolute path、cache 和 temp files。
8. Coding 接收时先解包到临时目录，验证 allowlist、完整性、descriptor、Schema regeneration 和 expected payload hash。
9. 全部通过后才原子替换 Coding mirror；失败时保留原 mirror 不变。
10. 在 Windows 开发环境和最小 Linux 环境使用同一实现验证相同 Payload Hash。

## Validation Commands

```powershell
python -m agent_core.contracts.tooling.generate_schemas --check
python -m agent_core.contracts.tooling.verify_payload
python -m pytest agent_core/contracts/conformance/test_versioning.py -q
```

Coding 接收流程还必须在替换前后分别计算目标 hash，并证明没有 unexpected file。

## Expected Outputs

- 六类 v0.1 Schema snapshot，后续 Evidence schema 在 Spec 04补齐。
- `payload-descriptor.json`。
- canonical hash 与 deterministic bundle tools。
- 两仓逐文件相同、hash 相同的 mirror。
- Windows/Linux hash comparison 记录。

## Acceptance Criteria

- 相同内容在 Windows/Linux 得到相同 Schema/Payload Hash。
- `same version + different payload hash` 能被检测为 `DIVERGED`。
- Schema 漂移在 check 模式失败且不修改工作区。
- Payload、descriptor、manifest 的依赖图无自引用。
- Coding mirror 只能由 verified bundle 得到。

## Stop Conditions

- Pydantic/tooling 版本无法在两仓固定一致。
- 规范文件集合不能确定或出现项目文件渗入。
- Windows/Linux hash 不一致。
- Coding 需要手工修补才能导入。

## Rollback / Handoff

Wiki 可回到 Spec 02 的 semantic source；Coding 原子提升失败必须保留原 mirror。Handoff 必须记录 contract version、schema set hash、payload hash、bundle transport hash及两仓验证结果，并明确 transport hash不是契约身份。
