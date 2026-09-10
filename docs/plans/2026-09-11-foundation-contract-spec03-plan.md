# Spec 03 执行计划 — Schema, Payload Descriptor, Hash and Mirror Bundle

> 关联 Spec：`docs/specs/foundation-contract/03-schema-payload-descriptor-hash-and-mirror-bundle.md`
> 规范真相源：Master Spec §3.1、§12、Appendix A.1
> 目标仓库：author in `WIKI_REPO`；verified mirror in `CODING_REPO`
> 前置：Spec 02 `COMPLETE` ✅（commit `207044d`）

## 1. 目标

建立**无自引用、跨 Windows/Linux 确定**的 Schema 与 Contract Payload 身份，并用受控
bundle 把 Wiki canonical payload 原子提升到 Coding mirror。

这是 **Coding 仓第一次真正参与** Foundation Contract：镜像只能来自验证后的 bundle。

## 2. 文件清单

Wiki（canonical authoring）：

| 文件 | 职责 |
|---|---|
| `agent_core/contracts/tooling/__init__.py` | tooling 包标识 |
| `agent_core/contracts/tooling/canonical_json.py` | canonical JSON 与文件束规范化、SHA256 |
| `agent_core/contracts/tooling/generate_schemas.py` | 由 Pydantic 生成 Schema；默认 check 模式不写工作区 |
| `agent_core/contracts/tooling/verify_payload.py` | 校验 descriptor / Schema / 文件束 / Payload Hash 自洽 |
| `agent_core/contracts/tooling/bundle.py` | 确定性 transport bundle 的生成与消费端原子提升 |
| `agent_core/contracts/schemas/*.schema.json` | 受控生成的 Schema 快照（不手改） |
| `agent_core/contracts/payload-descriptor.json` | 无自引用的 payload 目录 |
| `agent_core/contracts/conformance/test_versioning.py` | FND-PKG-001/002/004、FND-VER-001…006 的证明 |

Coding（mirror consumer）：`agent_core/__init__.py`、`agent_core/contracts/**`
—— **只能**由验证后的 bundle 原子提升，禁止手工复制或局部修补。

## 3. 关键设计决策

### 3.1 Schema 采用 `mode="serialization"`

实测 `model_json_schema` 两种模式：

```text
validation      amount → anyOf[number, string(pattern), null]   ← 与「拒绝 float」矛盾
serialization   amount → anyOf[string(pattern), string, null]  ← 与「十进制字符串」一致
```

Master §4 把金额的**跨边界**表示定义为十进制字符串，且 FND-COST-003 拒绝 float 输入。
validation 模式的 Schema 会错误地宣称 JSON number 合法，因此取 **serialization 模式**
作为快照来源。`anyOf` 中两个 string 分支是 Pydantic 对 `Decimal | str` 的产物，语义等价、不去重
（保持"Schema 只是 Pydantic 受控机器快照、不手工编辑"）。

### 3.2 单一 canonical JSON 实现

`canonical_json_dumps` 的实现保留在 `models/base.py`（Spec 02 已提交，本步骤不得修改未列文件），
`tooling/canonical_json.py` 复用它，避免出现第二套规范化实现。
tooling → models 的依赖方向本身是必然的：Schema 生成器必须 import 模型。

### 3.3 canonical file bundle

```text
相对路径分隔符统一为 /
按路径排序
UTF-8、不带 BOM
文本 CRLF/CR → LF
JSON 文件重新做 canonical JSON
拼接 path + NUL + content + NUL
SHA256
```

Python 与 Markdown 不做 AST/语义规范化，只做编码与换行规范化；
因此注释或格式变化也会改变 Payload Hash —— 这是镜像一致性检查的**预期行为**。

### 3.4 transport bundle 采用 ZIP_STORED

archive 只是 transport，**永远不等于或替代** Contract Payload Hash。
使用 STORED（不压缩）而非 DEFLATE：deflate 输出依赖 zlib 版本，会破坏跨平台确定性。
ZIP 条目的时间戳、外部属性固定，条目按路径排序。

### 3.5 `schema_set_hash` 口径

按 schema ID 排序后，对 `schema_id + NUL + schema_hash` 逐项以 NUL 连接后取 SHA256。
它只用于快速诊断 Payload 差异，**不是**第三套治理身份。

## 4. 执行顺序

1. `tooling/canonical_json.py`（规范化 + 哈希原语）
2. `tooling/generate_schemas.py` + 生成 4 份 Schema 快照并提交
3. `payload-descriptor.json`（Schema hashes + `normative_rule_set`，来源于 `contract.md` 索引）
4. `tooling/verify_payload.py`（自洽校验）
5. `tooling/bundle.py`（生成 / 消费 / 原子提升）
6. `conformance/test_versioning.py`
7. 跨平台：Windows 计算 Payload Hash；Linux 侧见「已知限制」
8. Coding：解包到临时目录 → 全量验证 → 原子替换 mirror

## 5. 验证命令（Spec 03 官方）

```powershell
python -m agent_core.contracts.tooling.generate_schemas --check
python -m agent_core.contracts.tooling.verify_payload
python -m pytest agent_core/contracts/conformance/test_versioning.py -q
```

Coding 接收流程必须在替换前后分别计算目标 hash，并证明没有 unexpected file。

## 6. 跨平台比对记录（Windows / Linux）

Spec 03 步骤 10 要求"在 Windows 开发环境和最小 Linux 环境使用同一实现验证相同 Payload Hash"。
已在 Docker Desktop（Engine `29.7.2`，`linux/amd64`）中完成实测。

- Windows 权威解释器：`D:\CodexPython312\python.exe`（Python 3.12.10 / pydantic 2.13.4）
- Linux 容器：镜像 `deepeval-local:latest`（Python 3.12.14 / pydantic 2.13.4）
  —— 与 `PYDANTIC_PIN = 2.13.4` 完全一致；worktree 以 `:ro` 只读挂载，容器内不写宿主目录
- 执行时间：2026-09-11

| 身份 | Wiki / Windows | Wiki / Linux | Coding / Windows | Coding / Linux |
|---|---|---|---|---|
| `payload_hash` | `sha256:21104487…45be7` | 同 | 同 | 同 |
| `descriptor_hash` | `sha256:8d10f56a…e34dac` | 同 | 同 | 同 |
| `schema_set_hash` | `sha256:387e84e8…f3cf513` | 同 | 同 | 同 |
| `file_count` | 32 | 32 | 32 | 32 |

transport bundle 的 archive hash 亦跨平台一致：

| bundle | 计算平台 | `archive_hash` |
|---|---|---|
| `contract-payload-0.1.0.zip` | Windows | `sha256:ec105f09d7992bf54cb4c0e25a7fbddcc396a94891e4c8eb2bc5e4bb152cbcb9` |
| 同内容 bundle | Linux 容器 | 同 |

四路身份（双仓 × 双平台）逐字节一致，**无 DIVERGED**。平台无关性的算法依据：
无 mtime / permissions / 绝对路径参与身份、文本换行规范化为 LF、路径统一 `/`、排序确定、
JSON canonical、transport 使用 `ZIP_STORED` 且 `date_time` 与 `external_attr` 固定。

说明：archive hash 仅为 transport 身份，**不是**契约身份（Master 禁止以 ZIP hash 冒充 Payload Hash）。

## 7. 验收对照

- [x] 相同内容在 Windows/Linux 得到相同 Schema/Payload Hash —— 四路一致，见 §6
- [x] `same version + different payload hash` 能被检测为 `DIVERGED`
      （`test_same_version_different_payload_is_detected_as_diverged`）
- [x] Schema 漂移在 check 模式失败且不修改工作区
      （`generate_schemas --check` 只比较不写盘；`test_schema_drift_is_detected`）
- [x] Payload、descriptor、manifest 的依赖图无自引用
      （`test_payload_does_not_contain_its_own_hash`、`test_descriptor_is_fully_derivable_before_hashing`）
- [x] Coding mirror 只能由 verified bundle 得到
      （`bundle apply --expect-payload-hash` 强制校验，失败保留原 mirror）

## 8. 结论与后续

Spec 03 全部验收条件达成，官方验证命令全绿（`generate_schemas --check` / `verify_payload` /
`test_versioning.py` 20 passed；全量 conformance 194 passed）。

尚未执行：**Spec 03 的状态事件与提交**（等 review）。提交后 Spec 04 才解锁
（Evidence DTO/Protocol + 两类 Evidence Schema + 两个独立 FileEvidenceSink）。

## 9. 回滚

Wiki 可回到 Spec 02 的 semantic source（删除 schemas/、descriptor、tooling）；
Coding 原子提升失败必须保留原 mirror 不变。
