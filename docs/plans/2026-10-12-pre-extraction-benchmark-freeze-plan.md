# W11-α — Pre-extraction Benchmark Baseline 实施计划（2026-10-12）

> 关联 Spec：`docs/specs/2026-10-12-pre-extraction-benchmark-freeze.md`（已批准 2026-10-12）
> 规则：CLAUDE.md G-01（功能分支）· G-02（小步提交）· G-03（提交前检查）· U-03（评测优先）· U-13（子代理处理大文件）· N-01/N-02
> 上游成果：Step 1 只读探测与审计见 `output/_w11_probe/w11a_step1_report.md`

---

## 任务分解

### T1 — 建 feature 分支（G-01）

- **动作**：从 `main`（`8ea42e0`）建 `feature/pre-extraction-baseline`
- **文件变更**：无
- **验证**：`git status -sb` 显示新分支；`main` 不被直接改动

### T2 — Wiki 测量仪表化（Spec §3.3）

- **文件变更**
  - `arknights_wiki/eval/runner.py`：结果行增补 `model` / `provider` / `base_host` / `temperature` / `max_tokens` / `commit` / `prompt_sha256`
  - `arknights_wiki/eval/report.py`：报告头写完整 metadata；删除硬编码的过期 judge note
  - `arknights_wiki/eval/metrics.py`：输出 `judge_failure_count` / `null_metric_count` 与 `overall` 显式分母
  - `arknights_wiki/eval/freeze.py`（新增，职责：计算并写出 corpus/materials/prompt 哈希与 `benchmark-spec.json`；N-02 说明：唯一职责是"冻结件的哈希与清单生成"，不做评测逻辑）
  - `tests/eval/test_freeze_metadata.py`（新增）：字段存在性、分母显式性、哈希可复算
- **验证标准**：`D:\CodexPython312\python.exe -m pytest tests/eval -q` 全绿；旧 `results_*.jsonl`（无新字段）仍可被 `report.py` 读取
- **前置**：T1

### T3 — Coding 测量仪表化（Spec §3.3）

- **文件变更**
  - `benchmark/report.py`：metadata 增补 provider / base_url / temperature / max_tokens / **实际** executor / sandbox policy / iteration+timeout / resolution 定义版本 / `side_effect_policy` / judge prompt sha
  - `benchmark/loader.py`：case schema 增可选 `repository_commit`；读取 `benchmark/frozen/<ver>/cases.lock.json`
  - `benchmark/runner.py`：`cost_usd` 由恒 `0.0` 改为 `null` + `cost_source: "unknown"`；渲染层兼容 `None`
  - `tools/docker_sandbox.py`：暴露**实际**执行器（`local` / `docker`）供报告读取，消除"报告写 docker 实际跑 local"
  - `tests/`（对应新增测试）：锁文件解析、真实 executor 记录、`cost_usd=None` 渲染不崩
- **验证标准**：Coding 仓 `pytest -q` 相关测试全绿；生成的 `report.json` 里 `cost_usd` 为 `null` 且 `cost_source="unknown"`
- **前置**：T1

### T4 — 新题草稿（Spec §3.2，交用户抽验）

- **文件变更**
  - `benchmarks/arknights_bench/drafts/w11a_new_categories.jsonl`（草稿，**不入冻结集**）
  - `benchmarks/arknights_bench/drafts/w11a_review_notes.md`（逐题依据：预期行为、证据出处）
  - 若判定逻辑缺失：`arknights_wiki/eval/metrics.py` 增纯规则指标 `abstention_accuracy`
- **内容**：`no_answer` ≥10 条（语料确实无答案）+ `hallucination_bait` ≥10 条（错误前提），依据 `materials/**` 与 `data/entity_source_map.json`（大文件交由子代理检索，U-13）
- **验证标准**：**用户抽验通过**（N-01）；抽验前不得进入 T5
- **前置**：无（可与 T2/T3 并行）

### T5 — 语料冻结与 MANIFEST（Spec §3.4）

- **文件变更**
  - `benchmarks/arknights_bench/frozen/w11a-v1/questions.jsonl`（100 题 + 新题，≥120）
  - `benchmarks/arknights_bench/frozen/w11a-v1/MANIFEST.json`（corpus hash / 有序 case IDs / materials hashes）
- **验证标准**：canonical-JSONL 字节哈希可被独立重算；8 类计数各 ≥10；文件生成后**只读**
- **前置**：T4 抽验通过

### T6 — 跑 baseline 并冻结产物（Spec §3.4 / §3.6）

- **动作**：`--dry-run` 报数 → **用户确认** → Wiki direct 全量跑批 + 评分；Coding 全量（`local` 执行器）跑批
- **文件变更**
  - `output/eval/w11a_baseline/{results.jsonl, results_scored.jsonl, report.md, benchmark-spec.json, SHA256SUMS}`
  - `output/benchmark/w11a-baseline/{report.json, report.md, benchmark-spec.json, SHA256SUMS}`
- **验证标准**：产物齐全且哈希自洽；报告写明 harness commit、judge 身份、**实际**执行器；安全零容忍项 = 0
- **前置**：T2、T3、T5

### T7 — 复跑校验（Spec §3.5）

- **动作**：同 corpus / config / model / judge / runner **再跑一遍全量**；用预登记容差判定
- **文件变更**：`scripts/eval/check_reproducibility.py`（新增）+ `output/eval/w11a_baseline/reproducibility.md`
- **验证标准**：确定性指标完全一致；随机指标均值差 ≤ ±0.03 且逐题一致率 ≥ 90%；judge 失败率 ≤ 5%；结论为
  `REPRODUCIBLE`（若 `NOT_REPRODUCIBLE` → **如实记录并停止**，不得调容差复活）
- **前置**：T6

### T8 — Review 与收口

- **动作**：`codex:code-review` 审查 T2/T3/T5/T7 代码 → 修复 → commit（G-02/G-03）→ 更新 devlog +
  在 Spec 17 证据引用处登记「`reproducible_quality_gate` 已冻结并可复算」（**不改 Gate 总判定**）
- **验证标准**：审查问题清零；`git status` 无临时文件/密钥；devlog 记录指标与决策
- **前置**：T7

---

## 里程碑

| 里程碑 | 内容 | 判据 |
|---|---|---|
| M1 | 两仓仪表化完成 | T2/T3 测试全绿 |
| M2 | 语料冻结 | T4 抽验通过 + T5 MANIFEST 可复算 |
| M3 | 基线冻结 | T6 产物 + SHA256SUMS 齐全 |
| M4 | 可重现判定 | T7 输出 `REPRODUCIBLE` |
| M5 | 收口 | T8 Review 通过并提交 |

---

## 关键实现细节

1. **向后兼容**：Wiki 结果行**追加**字段，不重命名既有字段；旧 `results_*.jsonl` 必须仍可被报告层读取
   （读取端一律用 `.get()`）。
2. **分母显式化会改变历史可比性**：`_mean` 不再静默丢 null 后，`overall` 与历史 `report_v1_mimo.md`
   的口径不同。报告中必须显式声明，禁止把新旧数字并列比较。
3. **`cost_usd=None`**：Coding 报告渲染（`report.md` / `report.json` / 汇总行）需容忍 `None`，
   渲染为 `unknown` 而非 `0.0000`；`main.py:194-195` 的既有告警保留。
4. **真实 executor**：由 `tools/docker_sandbox.py` 在执行时写入模块级"实际执行器"记录，报告读取该值；
   若该改造被判定超出"元数据"边界，则退化为记录 `KA_EXECUTOR` + 运行时探测结果，并在报告中标注为**推断值**。
5. **冻结件不可变**：`frozen/w11a-v1/**` 与 `w11a_baseline/**` 生成后只读；任何修正形成 `w11a-v2` 并登记
   `SUPERSEDED` 原因。
6. **成本纪律**：T6 必须先 `--dry-run` 报数并获用户确认；不擅自全量跑批（U-10 / Step 1 实测 judge 侧
   120 题 ≈ ¥0.22/轮，复跑 ×2）。
7. **U-13**：`data/entity_source_map.json`（2.3MB）、`materials/**` 的检索与候选构造派子代理执行，
   主会话只收结构化结果。

---

## 验证清单（逐条可执行）

```powershell
# Wiki 测量层
D:\CodexPython312\python.exe -m pytest tests/eval -q
# 仪表化后旧数据兼容
D:\CodexPython312\python.exe -m arknights_wiki.eval.runner --bench benchmarks/arknights_bench/questions_draft.jsonl --dry-run
# 冻结件哈希可复算（T5/T6）
D:\CodexPython312\python.exe -c "from arknights_wiki.eval import freeze; print(freeze.verify_manifest('benchmarks/arknights_bench/frozen/w11a-v1/MANIFEST.json'))"
# 复跑判定（T7）
D:\CodexPython312\python.exe scripts/eval/check_reproducibility.py --base output/eval/w11a_baseline --rerun output/eval/w11a_baseline_run2
# Coding 测量层（在 Coding 仓根执行）
D:\CodexPython312\python.exe -m pytest tests -q -k "benchmark or report or sandbox"
```

---

## 回滚与停止条件

- 全程在 `feature/pre-extraction-baseline` 上，`main` 不动；回滚 = 丢弃分支。
- **停止条件**：① T4 抽验不通过 → 停在 T4 重新起草；② T7 判 `NOT_REPRODUCIBLE` → 如实记录并停止，
  不得放宽容差；③ 出现任何安全零容忍项 → 立即停止并上报；④ 若为实现元数据而必须改动
  imports/packaging/Adapter → **停止**（越出 Spec 边界，需重新审批）。
