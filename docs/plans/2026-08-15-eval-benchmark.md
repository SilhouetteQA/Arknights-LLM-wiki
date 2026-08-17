# W0 实施计划 v3：Evaluation Benchmark 建库（TDD 执行）

> 关联 Spec：docs/specs/2026-08-15-eval-benchmark.md（v3，2026-08-15 重写）
> 执行模式：TDD（test-driven-development）· 里程碑 M0-M5 · 全部外部调用前 dry-run + 征求用户同意

---

## 任务总览

| # | 任务 | 里程碑 | 外部调用 | 依赖 |
|---|------|--------|----------|------|
| T1 | DeepEval 连通性冒烟 | M0 | 1 条样例打分（<¥0.01） | 安装完成 |
| T2 | 接入层（config/llm/firecrawl） | M0 | 无（mock 测试） | — |
| T3 | 6 角度材料探索（子代理并行） | M1 | 无 | T2 |
| T4 | 生成管线 v3（grounded + 校验 + 元评估） | M2 | 生成 100 题 + 元评估 | T2+T3 |
| T5 | 候选审查 + 三环校验流程 | M3 | 无 | T4 |
| T6 | runner 双路径执行 | M4 | 跑批（dry-run 后） | T2 |
| T7 | DeepEval 打分层 + 规则指标 | M4 | judge 打分 | T1+T6 |
| T8 | 报告（含交叉盲区分析）+ 基线 | M4 | 无 | T7 |
| T9 | 收尾：devlog + 路线图 + commit | M5 | 无 | T8 |

---

## T1: DeepEval 连通性冒烟（M0）

- [ ] `pip install deepeval` 完成
- [ ] 冒烟脚本 `scripts/smoke_deepeval.py`：DeepEval 自定义模型（`DeepEvalBaseLLM` 子类）指向火山引擎
  （`arkcode_api` + `https://ark.cn-beijing.volces.com/api/coding/v3` + `doubao-seed-1-6-flash-250828`）
- [ ] 1 条样例 `AnswerCorrectness` 打分通过（中文样例），成本记录 cost_log
- **验证**：冒烟输出 score + reason；失败则记录错误并触发回退方案（官方 judge 模型 / promptfoo）
- **注意**：deepeval 首次运行可能要求 login/telemetry——用 `deepeval login --offline` 或环境变量禁用

## T2: 接入层（M0，复用 v2 归档代码）

- [ ] `arknights_wiki/eval/config.py`：环境变量读取（进程 → HKCU 注册表回退）、模型/端点配置
- [ ] `arknights_wiki/eval/llm.py`：火山 chat 封装 + 成本计算 + JSON 解析（可从 output/_w0_v2_archive/eval/ 复用）
- [ ] `arknights_wiki/eval/firecrawl.py`：搜索封装
- [ ] `arknights_wiki/eval/pricing.json`：模型单价表
- **验证**：`tests/eval/test_config.py / test_llm.py / test_firecrawl.py`（mock，零网络）

## T3: 6 角度材料探索（M1，子代理并行）

- [ ] 派 6 个子代理，各探索一个角度，产出**材料清单 JSON**（`benchmarks/arknights_bench/materials/{angle}.json`）：
  - 每条：{name, source_file, excerpt（内容抽样 ≤800 字）, meta（章节/活动/类型）}
  - character（v2_characters + v1_events participants）：50 条候选人物 + 代表档案/事件抽样
  - event（v1_events + timeline）：50 条候选事件 + 因果相关事件
  - region（v3_wiki factions/locations）：30 个国家/地区 + 页面抽样
  - organization（v3_wiki factions + v2_characters）：30 个组织 + 页面抽样
  - combat_power（v2_characters abilities/power_level）：40 角色战力条目 + 评级与证据抽样
  - worldview（v3_wiki concepts + timeline）：40 概念/大事件 + 定义与时间线抽样
- [ ] 材料清单校验：条数达标、excerpt 非空、source_file 存在
- **验证**：`tests/eval/test_materials.py`（清单 schema 校验）

## T4: 生成管线 v3（M2）

- [ ] `scripts/generate_benchmark_questions.py` v3：
  - 读材料清单 → 按角度 × 简单/复杂路由抽样（simple 抽单页材料，complex 抽多源材料）
  - 注入模板（角度定义 + 路由要求 + 材料片段）→ 模型只能基于材料出题（题目/答案/evidence 含材料引用）
  - 生成模型：`doubao-seed-1-6-flash-250828`
  - 校验①：章节/活动名比对 `config/chapter_timeline.json` + `story_taxonomy.json`（不匹配标记）
  - 校验②：kb_check（EntityIndexStore/WikiStore 定位 evidence）
  - 校验③：题目质量元评估（judge 打分：有明确答案/可作答/无歧义 → 低分过滤或标记）
  - 输出 `questions_draft.jsonl`（source=grounded_llm，含 material_refs）
- [ ] 生成执行（dry-run 预估 → 用户同意 → 100 题）
- **验证**：`tests/eval/test_generate.py`（mock LLM 全链路）；章节比对通过率 ≥95%

## T5: 候选审查 + 三环校验（M3，用户参与）

- [ ] 生成 `review_candidates.md`（按角度/路由分组，含材料引用）
- [ ] **三环校验流程**（Spec §3.2）：用户审查每道题「答案 key ← 材料 ← 剧情事实」；材料错误标记 `material_issue` → `output/eval/material_issues.md`
- [ ] 用户确认后执行 firecrawl 搜索验证（`scripts/verify_benchmark_questions.py`，复用 v2 归档）
- [ ] 定稿 `questions.jsonl`（100 题 + 人工附加集 no_answer/hallucination_bait）
- **验证**：题目 schema 校验测试（`tests/eval/test_benchmark_schema.py`）

## T6: runner 双路径执行（M4）

- [ ] `arknights_wiki/eval/runner.py`：`--mode direct|http|both`、`--limit/--category/--dry-run`
  - direct：route_query → simple_search / graph.stream（收集 answer/route/tools/latency）
  - http：POST /chat + SSE 解析
  - 结果 JSONL 断点续跑；cost_log 记录
- **验证**：`tests/eval/test_runner.py`（mock agent/graph/httpx）

## T7: DeepEval 打分层 + 规则指标（M4）

- [ ] `arknights_wiki/eval/scoring.py`：
  - DeepEval：AnswerCorrectness（vs answer_key）、Faithfulness（vs 材料/证据）、Hallucination
  - 自定义 citation_accuracy（DeepEval 自定义 metric）
  - 规则指标（纯函数）：tool_selection_accuracy、task_completion（含无答案正确拒绝）
- [ ] judge 模型 = 火山 doubao（T1 冒烟验证的接入方式）
- **验证**：`tests/eval/test_scoring.py`（规则指标纯函数 + mock DeepEval）

## T8: 报告 + 基线（M4）

- [ ] `arknights_wiki/eval/report.py`：总分/六指标/分角度×分路由/双路径对比/系统指标/成本/
  **交叉盲区分析（faithfulness×correctness 矩阵）**
- [ ] 基线跑批：dry-run → 用户同意 → both 模式 → `output/eval/report_v1.md`（Agent V1 基线）
- **验证**：`tests/eval/test_report.py`（已知 results 生成报告快照）

## T9: 收尾（M5）

- [ ] devlog 记录（指标/决策/材料问题）；路线图 W0 ⏳→✅
- [ ] review 后 commit（G 规则）

---

## 风险对照（Spec §5）

- DeepEval 兼容失败 → T1 触发回退（官方 judge / promptfoo），不影响 T2-T6
- 材料探索不足 → T3 清单校验兜底，可补探索轮次
- 章节比对通过率低 → T4 校验①标记 + 报告，人工审查时优先处理
