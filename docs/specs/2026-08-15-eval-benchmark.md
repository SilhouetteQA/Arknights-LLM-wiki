# W0 设计规格 v3：Evaluation Benchmark 建库（2026-08-15 重写）

> 窗口：W0（P0 首任务）· 关联规则：U-03 / U-14 · 前置文档：docs/plans/2026-08-15-upgrade-roadmap.md
> v3 重写原因（2026-08-15 用户决策）：v2 规格与实施作废归档（output/_w0_v2_archive/）——
> ① 生成质量差根因：模型凭记忆出题无知识库材料注入；② 打分层自研 judge 维护成本高，改用成熟框架 DeepEval；
> ③ 分类体系改为内容层 6 角度 × 简单/复杂路由（用户定义）。

---

## 1. 问题背景

- 升级方案 §7：Evaluation 是当前最值得补的能力；建立固定 Benchmark 作为 Agent 演进标尺（U-14）
- v2 教训（本会话实测）：
  - 轻量模型凭记忆生成题目 → 章节/人物/事件大量错误（第十二章配史尔特尔、愚夜密函配流明、《孤星》误当集成战略、漏萨卡兹/萨米/界园 IS）——**必须基于知识库材料生成（grounded generation）**
  - 自研 LLM-as-judge（prompt + 解析 + 重试 + 聚合 ≈ 200 行）实现与校准成本高——**改用社区验证的 DeepEval 指标库**
- 可复用资产：火山引擎接入（arkcode_api + coding 端点 + 129 个可用模型，已实测）、Firecrawl（firecrawl_api 已就绪）、知识库数据源完好（v1_events 106 章 / v2_characters 642 / v3_wiki 1757 页 / timeline / 实体索引）

## 2. 目标与范围

### 2.1 目标

1. 建立固定 Benchmark：**100 题**，内容层 6 角度（人物/事件/国家地区/组织/战斗力/世界观）× 简单/复杂路由
2. 题目与答案**基于知识库材料生成**（子代理探索文件 → 材料注入 → 出题），人工抽验
3. 打分层采用 **DeepEval**（LLM-as-judge 指向火山 doubao），规则指标自建
4. 产出 Agent V1 基线报告（六项质量指标 + 系统指标 + 分角度/分路由）

### 2.2 范围边界

- 做：材料探索 → 题目生成管线（grounded + 元评估过滤）→ 人工审查流程 → runner（双路径）→ DeepEval 打分层 → 报告
- 不做：Context Precision/Recall（需逐题检索上下文标注，后续补）；Langfuse 集成（W1）；CI（项目无基建）
- 决策（2026-08-15 用户确认）：内容层 6 角度 × 简单/复杂路由 · DeepEval 打分层 · 题目先出后验证（用户审题后再 firecrawl 搜索验证）· 易幻觉类全人工 · 成本统计 + 运行前征求同意

## 3. 技术方案

### 3.1 分类体系（内容层 6 角度 × 简单/复杂路由）

| 内容角度 | key | 简单路由（simple） | 复杂路由（complex） | 材料来源 |
|----------|-----|-------------------|---------------------|----------|
| 人物 | character | 单实体档案事实（种族/职位/归属/基本事迹） | 跨章事迹聚合、人物对比、关系网 | v2_characters + v1_events(participants) |
| 事件 | event | 单事件基本事实（时间/地点/参与者/结果） | 事件因果链、前因后果、多事件串联 | v1_events + timeline |
| 国家地区 | region | 单个国家/地区基础信息 | 多地区对比、地缘关系、区域史 | v3_wiki factions/locations |
| 组织 | organization | 组织宗旨/结构/成员单点查询 | 组织间关系、势力博弈、演变 | v3_wiki factions + v2_characters |
| 战斗力 | combat_power | 单角色战力评级/能力描述 | 战力比较、组织战力层次、if线结局boss战力 | v2_characters abilities/power_level |
| 世界观 | worldview | 单个设定概念定义 | 设定间关联、大事件对世界影响 | v3_wiki concepts + timeline |

**题量分配（共 100 题）**：人物 18（简 7+复 11）· 事件 18（简 7+复 11）· 国家地区 16（简 6+复 10）· 组织 16（简 6+复 10）· 战斗力 16（简 6+复 10）· 世界观 16（简 6+复 10）

- 每道题仍带技术属性：difficulty(1-3)、requires_tools、expected_behavior(simple|complex)（与路由一致）
- 无答案/易幻觉类由人工单独补充（不占 100 题配额，作为附加集；用户此前已确认全人工）

### 3.2 题目生成管线（Grounded Generation）

```text
[探索] 子代理按 6 角度探索知识图谱文件 → 产出材料清单（实体/事件/页面/路径 + 内容抽样）
   ↓
[抽样] 生成脚本按角度从材料清单抽样（平衡：简单题抽单页材料，复杂题抽多源材料）
   ↓
[注入] 材料片段 + 角度模板 + 路由要求 → 模型【只能基于材料】出题与答案
        （章节名/活动名/人物名全部取自材料，禁止模型自行联想）
   ↓
[校验] ① 章节/活动名比对知识库清单（chapter_timeline.json + story_taxonomy.json）
        ② kb_check：答案 evidence 中的实体可定位（EntityIndexStore/WikiStore）
        ③ 题目质量元评估：judge 模型打分（是否有明确答案/可作答/无歧义），低分自动过滤
   ↓
[输出] 候选 questions_draft.jsonl（含 source=grounded_llm + 材料引用）
```

- 生成模型：doubao-seed-1-6-flash-250828（比 v2 的 mini 档强；必要时升 doubao-seed-1-6-250615）
- 元评估模型：同 flash 档
- 用户流程：候选清单交用户审查 → 用户确认后执行 firecrawl 搜索验证（firecrawl_api + 免费模型自动查询）→ 用户终检 → 定稿
- **材料三环校验（用户审查环节，2026-08-15 补充）**：每道题审查时确认「答案 key ← 材料 ← 剧情事实」三环一致——
  ① 答案 key 是否由注入材料支持；② 材料内容是否与剧情事实一致（顺带抽检 Pass 1/2/3 提取质量）。
  发现材料错误 → 标记 `material_issue`（写入题目记录 + 材料问题清单 output/eval/material_issues.md），不删题，修正答案 key 或反馈数据层修复。
  评估器定位边界（2026-08-15 用户确认）：本评估器评估 **Agent 层**（检索/综合/忠实/拒绝/防幻觉）；
  **材料层质量**由独立手段负责（三 Pass 可追溯性评估 + 人工验证 CLAUDE.md §1.3 + 本环节顺带抽检）。

### 3.3 打分层：DeepEval

- 安装：pip install deepeval（冒烟测试先行，见 §6 M0）
- judge 模型：DeepEval 自定义模型指向火山引擎（OpenAI 兼容 https://ark.cn-beijing.volces.com/api/coding/v3 + doubao-seed-1-6-flash-250828，经 arkcode_api）
- 指标映射：

| 本 Benchmark 指标 | DeepEval 实现 | 判定对象 |
|--------------------|---------------|----------|
| answer_correctness | AnswerCorrectness | 答案 vs answer_key |
| faithfulness | Faithfulness | 答案 vs 检索材料/答案证据 |
| hallucination | Hallucination（自定义阈值） | 答案无依据断言 |
| citation_accuracy | 自定义 judge 指标（DeepEval 无现成） | 答案中引用准确性 |
| tool_selection_accuracy | 规则指标（自建，非 LLM） | 实际工具 vs requires_tools |
| task_completion | 规则指标（自建，非 LLM） | 是否完成任务/正确拒绝 |

- 无答案类（人工集）：走规则判定（正确拒绝）而非 judge

### 3.4 执行层（runner）

- 双路径（保留 v2 决策）：direct（route_query → simple_search / graph 进程内）与 http（POST /chat + SSE）
- 每题记录：answer / route / tools_called / latency_ms / tokens / cost
- --dry-run 预估成本 → 用户同意 → 执行；结果 JSONL 断点续跑；cost_log.jsonl 全程记录

### 3.5 报告（report_v1.md）

- 总分 + 六项指标 + 分内容角度 × 分简单/复杂路由 + 双路径对比 + 系统指标（P50/P95 延迟、成本、token 用量、工具调用数）+ 成本汇总
- **交叉盲区分析（2026-08-15 补充）**：faithfulness × correctness 二维矩阵——
  - faithfulness 高 + correctness 低 → 答案忠实引用了**错误材料**（材料可疑信号，联动 material_issue 清单）
  - correctness 高 + faithfulness 低 → 答案正确但未依据材料（可能走捷径/记忆作答）
  - 双低 → Agent 能力缺陷；双高 → 健康
- 演进基准：本报告即 Agent V1 基线，后续版本对比

### 3.6 成本机制（硬约束）

- 所有外部调用（探索无需 LLM、生成、元评估、firecrawl 验证、judge 打分）记录 cost_log.jsonl
- 运行前 dry-run 预估 + 征求用户同意（CLAUDE.md N-01 + 用户明确要求）
- 预估成本：生成 100 题 × ~3K tokens ≈ ¥0.15-0.3（flash 档）；judge 100 题 ≈ ¥0.1-0.3；firecrawl 验证按次（免费额度内）

## 4. 测试计划

- DeepEval 冒烟测试（M0）：1 条样例打分，确认火山模型接入（离线 mock 其余）
- 生成管线：材料注入解析、kb_check、章节清单比对（mock LLM）
- 规则指标：tool_selection / task_completion 纯函数
- runner：mock agent/graph/http，断点续跑
- 沿用 mock 模式（ARKNIGHTS_SKIP_EMBED_MODEL=1 等），无网络测试全离线

## 5. 风险与取舍

| 风险 | 缓解 |
|------|------|
| DeepEval 对火山自定义模型兼容性 | M0 冒烟先行（成本 <¥0.01）；失败则回退方案：DeepEval 官方 judge + 自定义 metric 或换 promptfoo |
| grounded 生成仍可能编造材料外细节 | 校验①章节清单比对 + ②元评估过滤 + ③人工抽验 30% |
| 材料探索工作量 | 6 个子代理并行（U-13），各产材料清单；探索与生成解耦，材料清单可复用 |
| 人工审查 100 题耗时 | 抽验制（30% 强制 + 质量可疑题全查）+ 元评估预过滤 |
| 双路径耗时翻倍 | --limit 分批 + 断点续跑；基线可先 direct 单路径，http 补跑 |

## 6. 里程碑

| # | 里程碑 | 交付 | 依赖 |
|---|--------|------|------|
| M0 | DeepEval 连通性冒烟 | 1 条样例打分通过（火山模型接入） | 安装 deepeval |
| M1 | 6 角度材料探索 | 材料清单（子代理并行，每角度 1 份） | — |
| M2 | 生成管线 v3 | 生成脚本 + 元评估过滤 + 100 题候选 | M0+M1 |
| M3 | 人工审查定稿 | questions.jsonl 100 题（含人工附加集） | M2 |
| M4 | runner + DeepEval 打分 | report_v1.md（Agent V1 基线） | M0+M3 |
| M5 | 收尾 | devlog + 路线图 W0 ✅ + commit | M4 |

## 7. 验收标准

1. M0 冒烟通过：DeepEval 使用火山 doubao 完成样例打分（成本记录在案）
2. M2 生成：100 题候选全部带材料引用；章节/活动名比对通过率 ≥95%；元评估过滤生效
3. M3 定稿：用户抽验通过；questions.jsonl 100 题（6 角度 × 简/复 分布达标）
4. M4 基线：report_v1.md 含总分/六指标/分角度分路由/双路径/成本
5. 全流程成本可追溯（cost_log.jsonl），每次外部调用前 dry-run 征得同意
