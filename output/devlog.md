# 明日方舟 LLM Wiki — 开发日志

> 重构项目，来源 `D:\AI project\mrfz`（原项目保持不动，逐步迁移）。

---

## Phase 0: 项目初始化 (2026-06-15)

### 决策

- 规则体系继承全局 CLAUDE.md，项目规则仅保留差异化内容
- 开发流程采用 Superpowers 方法论： brainstorming → writing-plans → subagent-driven-development + TDD → Codex Review → diagnose修复
- 数据质量从自动化 QA 改为用户预设问题 + 抽查
- 技术栈整体保持 mrfz 验证的选型（SQLite/FAISS/BGE/FastAPI），核心改变在代码组织
- 代码从 `scripts/` 松散结构迁移到 `arknights_wiki/` Python 包

### 文件

| 文件 | 说明 |
|------|------|
| docs/project-rules.md | 四章项目规则 |
| config/hooks/session-start.sh | 会话启动 Hook |
| config/hooks/session-end.sh | 会话结束 Hook |
| .claude/settings.local.json | Hook + 权限配置 |
| .claude/skills/architecture-diagrams/ | 架构图 skill |

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/ 下最新文件 — 上次会话详情
4. 下一步：开新会话 → 产出第一份 Spec（整体架构+迁移策略）

---

## Phase 1: 原始内容提取 (2026-06-15)

### 架构决策

- 代码从 `scripts/` 迁移到 `arknights_wiki/` Python 包
- `pipeline.py` 改名 `orchestrate.py` 避免与包名冲突
- 工具函数拆分为 `config.py`（配置）+ `_utils.py`（纯工具），LLM 工具留到 Phase 2
- 干员档案解析器适配 PRTS Wiki 的 `<table class="wikitable">` 格式

### 数据基线

| 指标 | 值 |
|------|-----|
| 故事节点 | 1,663/1,669 |
| 干员档案 | 420/420 (1,134,547 字) |
| 测试数 | 87 |

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策和数据基线
3. 读 output/sessions/ 下日期最新的会话总结
4. 下一步：M0 质量评估（用户审阅 entity md 后），然后进入 M1 chapter 页面生成

---

## M0 store/ 完成 (2026-06-15)

### 架构决策

- 4 张 SQLite 表：entities / entity_aliases / source_index / wiki_pages
- 3 个 Repository 类每表一个，seed.py 编排种子流程
- 异格自动提取：PRTS Wiki API `Category:异格干员` → `config/identity_map.json` (40 条)
- 概念关键词索引：`config/concept_keywords.json` (9 个概念) → source_index match_type=concept_keyword
- 无名 NPC 过滤：5 类正则模式，行级过滤，边界 case 保留供 M3 处理
- 实施方法：Spec → Plan → Subagent-Driven TDD (8 commits, 31 new tests)

### 数据基线

| 指标 | 值 |
|------|-----|
| character | 3,766 (420 干员 + 3,346 NPC) |
| faction | 44 |
| region | 34 |
| concept | 9 |
| aliases | 40 |
| source_index(exact) | 246,214 |
| source_index(concept_keyword) | 4,794 |
| 章节覆盖 | 109/109 (100%) |
| 测试 | 119 全部通过 |

### 已知问题

- 少量泛型 NPC 未被过滤（路过的观众A、黑帮A/B、老奶奶 等）
- seed_concept_keywords O(n*m) 复杂度，当前够用但可优化
- chapter 实体未种子（M1 处理）
- 23/1663 节点未索引

### 审阅文档

- `output/m0_seed_summary.md` — 总体统计
- `output/m0_entities_by_chapter/` — 109 章实体覆盖 md

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 memory/session_20250615_m0_store.md — 完整会话记录
4. 下一步：用户审阅 entity md → M0 质量评估修复 → 通过后进入 M1 chapter

---

## M0 质量修复 (2026-06-16)

### 架构决策

- **M0 职责收缩**：M0 只做确定性种子数据（干员/faction/region/别名/档案索引），NPC 实体和概念索引移除，留到 M1/M3 按需创建
- **组合过滤策略失败**：尝试用正则+台词行数过滤 NPC 不可行，根本问题是 M0 纯规则层不应创建低信息量实体
- **异格去重**：identity_map 中的异格干员不建独立 entity，只作为基体 alias，档案索引挂在基体上。character 从 418 降到 381
- **岁兽误报**：概念关键词"岁"单字匹配 89% 误报，移除单字关键词。概念索引整体移入 M3 LLM 提取

### 数据基线

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| character | 3,766 (含 NPC) | 381 (仅干员) |
| source_index(exact) | 246,214 | 3,615 (仅档案) |
| source_index(concept) | 4,794 | 0 (移入 M3) |

### 修改文件

- `seed.py` — 3 步简化流程，移除 NPC/概念/章节种子
- `entity_repository.py` — `seed_from_operators` 接受 idmap 跳过异格
- `source_repository.py` — `seed_operator_archives` 异格档案挂基体
- `config/concept_keywords.json` — 移除单字"岁"关键词

---

## 统计系统 (2026-06-16)

### 架构决策

- **JSONL 存储**：选 JSONL 而非 SQLite stats_log 表，schema 漂移友好
- **Subagent-Driven 执行**：12 tasks 逐个派独立 agent 实现 + spec review + code review
- **成本追踪粒度**：按模型拆分（deepseek-v4-flash / deepseek-v4-flash-think）
- **进度可见性**：stderr 实时输出 + 每 10 分钟后台自动快照
- **Windows 兼容**：RMB 符号导致 GBK 编码崩溃，替换为 RMB + stdout UTF-8 reconfigure

### 代码基线

```
arknights_wiki/stats/
├── __init__.py      # 导出 StatsCollector, StatsReporter
├── __main__.py      # CLI: python -m arknights_wiki.stats
├── collector.py     # 生命周期+记录+JSONL写入+成本估算
└── reporter.py      # 读取JSONL+详情/表格/diff 渲染
```

### 数据基线

| 指标 | 值 |
|------|-----|
| stats 测试 | 16 (10 collector + 6 reporter) |
| 全部测试 | 135 pass |
| 模块行数 | ~440 |
| commits | 10 on feature/stats-system |

---

## 架构 v3 重设计 (2026-06-16)

### 架构决策

- **三遍独立提取**替代 M0-M9：剧情骨架 -> 世界观概念 -> 角色 Wiki，每遍独立扫描原文，互不依赖
- **source_index 表砍掉**：提取结果自带 line_range 源引用
- **entity_aliases 表砍掉**：干员别名在 config/identity_map.json 维护
- **concept_keywords.json 砍掉**：LLM 自行发现概念
- **事件数量随内容密度浮动**，不设固定上限
- **概念由 LLM 自行判断**是否被实质性讨论
- **角色双源融合**：operators.json 档案 + 故事对话出场
- **模型选定 MiniMax M3**：经 5 模型对比测试（慈悲灯塔 122K tokens），M3 提取最全面

### mrfz 失败根因确认

- 1,475 concepts 全部 appear_node_count=0，2,314 relations 全部 total_nodes=0
- 根因：逐 chunk 提取 + 无源链接 + LLM 聚合失败

### 成本估算

~590 次 LLM 调用，估算 $8-15 (MiniMax M3)

---

## 数据整理 (2026-06-17)

### 架构决策

- **5级剧情分类**：`config/story_taxonomy.json` 将 109 章分为 full(91)/is(6)/ra(2)/light(7)/skip(3)。Why: 不同类型剧情在 KG 中的意义权重不同，不能一刀切全量提取
- **IS 仅保留结局**：藏品/事件/月度小队全部删除。结局完整叙事文本从 PRTS Wiki 记录页（深蓝记录仪/冬夜展览馆/巫仪档案库/见字图册）提取，写入 `{node}_ending.json` 与 story node 并列。Why: 结局文本是最核心的叙事数据（每结局 3-4 Parts，50-100 行），藏品/事件属于碎片化侧面信息
- **向下兼容**：taxonomy 新增字段，保留 index.json 的 category

### 数据基线

| 指标 | 值 |
|------|-----|
| 剧情纯文本 | 560万字 (~310万 tokens) |
| IS 结局覆盖 | 水月(4) + 探索者(4) + 萨卡兹(5) + 岁(5) = 18 个 ~90K chars |
| IS 未覆盖 | 傀影(无对应 PRTS 格式)、刻俄柏(无记录页) |

---

## Pass 1 剧情骨架提取 (2026-06-16)

### 架构决策

- **模型选定 DeepSeek v4-flash**：MiniMax M3 的 `<think>` 块占满输出 token（14.5K/16K），JSON 解析近 100% 失败。DeepSeek 0% 失败，25-76s/章，$0.08/6章
- **json-repair**：LLM JSON 含中文双引号/控制字符/换行，`json-repair` 库可靠修复
- **max_tokens**：DeepSeek 8192 足够，MiniMax 需 32768
- **事件类型自由 snake_case**：不设枚举，覆盖更广
- **>128K 章切 2 批**：自然 node 边界切断
- **移除 §1.3 预设问题规则**：v3 架构用 line_range 溯源代替

### 代码基线

```
arknights_wiki/extraction/ (5 模块, 28 tests)
```

### 试跑基线 (DeepSeek v4-flash)

| 章节 | Events | 耗时 | 成本 |
|------|--------|------|------|
| 黑暗时代·上 | 19 | 25s | <$0.01 |
| 怒号光明 | 12 | 34s | $0.02 |
| 慈悲灯塔 | 30 | 63s | $0.02 |
| 孤星 | 41 | 68s | $0.02 |
| 相见欢 | 19 | 37s | $0.01 |
| 长夜临光 | 58 | 76s | $0.02 |

### 已知问题

1. llm_client 默认模型仍是 MiniMax-M3，需改为 deepseek-chat
2. 怒号光明仅 12 events（max_tokens=8192 可能限制大章输出）
3. 长夜临光 0 concepts
4. 大量 NPC 角色名未匹配（需补充 identity_map）

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-16-4.md — 完整会话记录
4. 下一步：审阅试跑 Markdown → 修复质量问题 → 全量 109 章

---

## Pass 1 质量修复 (2026-06-17)

### 架构决策

- **场景级行号**：对话按 Scene（node）组织，Scene 内行号独立编号。LLM 输出 scene-relative line_range，后处理转换为章全局行号。彻底消除 [1, 200] 整数估算和 [1, 3464] 章级范围
- **游戏顺序**：从 data/index.json 提取 PRTS Wiki 原始抓取顺序生成 _order.json。`load_chapter` 读取 _order.json 确保 ST 节点正确穿插
- **自然节点分块**：<=2000 行不分，2000-5000 分 2 段，>5000 分 3 段。多批间传递摘要+事件列表作上下文
- **行号偏移**：`_offset_line_ranges` 将批次行号加前批累计偏移，合并后全局无重叠
- **概念严格化**：`_reject_broad_concepts` 拒绝 span>200 行的伪概念。prompt 要求 concepts/factions/locations 都用实质性讨论范围
- **DeepSeek 自动检测**：`create_client` 优先读 `deepseek_api`，回退 `minimax_api`
- **角色匹配升级**：identity_map 120+ 条（真名→代号+异格+别名），复合名 `·` 拆分匹配
- **factions/locations**：与 concepts 同格式输出，支持同名多处讨论（不合并去重）

### 试跑基线

| 章节 | 行数 | 批 | Events | Concepts | Factions | Locations |
|------|------|-----|--------|----------|----------|-----------|
| 怀黍离 | 3038 | 2 | 67 | 15 | 6 | 5 |
| 相见欢 | 3714 | 2 | 63 | 11 | - | - |
| 长夜临光 | 6646 | 3 | 89 | 13 | - | - |

### 已知问题

- 3 tests 预存失败（test_stats_collector，无关本次修改）
- 部分 factions/locations 仍为短 span（2-4 行），属合理的一带而过
- HD 节点（逃离/选择/路漫漫）排在末尾而非游戏实际穿插位置

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-17-1.md — 完整会话记录
4. 下一步：原始数据分支处理数据问题 → feature/pass1-event-extraction 全量 109 章

---

## IS 结局适配 (2026-06-17)

### 架构决策

- **_ending.json 按 PART 拆分**：`_split_by_parts()` 用 `^PART \d+` 正则将结局文本拆为独立 Scene（每个结局 4 PART = 4 场景）。Why: 整个结局作为单一场景时 LLM 会在 PART 之间夹断叙事
- **IS 专用提示词**：`IS_PROMPT_APPENDIX` 注入来源说明（想象未来/IF线）、总结格式要求（结局→PART 层级）、is_imaginary 强制规则。`build_system_prompt("is")` 拼接完整 prompt
- **Taxonomy 驱动**：`run_all/run_trial` 加载 `config/story_taxonomy.json`，自动跳过 skip 章节，IS 章节传 `chapter_type="is"`
- **is_imaginary 全域标记**：所有 IS 章节事件（含序章框架和结局文本）标记 `is_imaginary: true`

### 萨卡兹试跑 (4 轮调优)

| 轮次 | 场景 | Events | Concepts | 关键改进 |
|------|------|--------|----------|----------|
| #1 | 15 | 31 | 6 | 基础 prompt，_ending 重复加载 |
| #2 | 10 | 25 | 14 | summary 按 Ending+PART 分节 |
| #3 | 10 | 22 | 9 | 全部 is_imaginary=true |
| #4 | 25 | 29 | 11 | **PART 拆分为独立 Scene** |

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 memory/session_20260617_is_adapter.md — 完整会话记录
4. 下一步：全量 109 章 Pass 1 批量执行 → 质量检验

---

## Pass 1 质量修复与全量完成 (2026-06-18)

### 架构决策

- **JSON schema 重排**：`OUTPUT_SCHEMA` 中 concepts/factions/locations 移到 events 之前。Why: 大章事件列表长，tok_out 打满 8K 时元数据 categories 被截断
- **分批阈值降低**：`split_chapter` 从 2000/5000 改为 1500/3000。Why: 2000-5000 行的大章分 2 批仍导致每批 tok_out 饱和，降到 1500/3000 后每批负担减轻 30-50%
- **三维质量审计**：对全部 106 章执行 (1) 尾部行号缺口 (2) 事件描述质量退化 (3) 元数据密度异常 三维检查，交叉验证消除假阳性

### 修复统计

| 轮次 | 章节数 | 问题类型 | 修复方式 |
|------|--------|----------|----------|
| #1 | 3 | 0 events (JSON 损坏/LLM未输出) | 重提取 |
| #2 | 4 | Missing factions/locations (tok_out 饱和) | Schema 重排 + 重提取 |
| #3 | 4 | Low events/early-end coverage | 新阈值重提取 |
| #4 | 3 | Reversed line_ranges | 手动交换 |
| #5 | 4 | Early-end (第二/三批事件丢失) | 新阈值重提取 |
| #6 | 1 | 慈悲灯塔三维全中 (100%饱和+41%质降+7%尾缺) | 新设置重提取 |

### 最终基线

| 指标 | 值 |
|------|-----|
| 已提取章节 | 106 (main 18 + side 68 + special 20) |
| 事件 | 4,129 |
| 概念 | 957 |
| 阵营 | 1,152 |
| 地点 | 771 |
| 估算成本 | ~$3.0 USD (DeepSeek) |
| 质量评估 | 104/106 通过三维审计 |
| 已知缺口 | 集成战略 (IS, 0 events, 需子页面抓取), 生息演算 (RA, 90行尾缺28行)

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-20-1.md — 完整会话记录
4. 下一步：writing-plans → TDD → 试跑 17 角色

---

## Pass 2 Spec 完成 (2026-06-20)

### 架构决策

- **Pass 2 = 角色 Wiki 页面生成**：原 v3 架构 Pass 2（概念合成）+ Pass 3（角色 Wiki）合并为 Pass 2，角色优先，概念/地点后续
- **不做关系提取**：敌对/同盟/友谊/师徒等动态关系不单独提取，通过 participated_events 隐式表达
- **先聚合再提取**（方法 3）：角色跨章出场全部聚合后一次 LLM 调用，所有角色统一质量不降级
- **power_level 九级体系**：战场中坚 → 军事精锐 → 大国将军 → 传奇英雄 → 王庭之主 → 神明碎片 → 崛起之物 → 文明之敌 → 灭世灾厄，每级 4 子级（下位/标准/上位/顶尖）
- **summary 核心字段**：按出场章数限字数（500/350/250/150/100），覆盖性格+能力+剧情弧线
- **participated_events 合并**：LLM 自行合并同战役多阶段为一个条目，琐碎对话忽略但信息吸收到 summary
- **角色名规范化**：Pass 1 participants 自由文本导致同角色多名字，Pass 2 预处理阶段解决

### 范围基线

| 来源 | 数量 |
|------|------|
| 干员（M0 baseline） | 381 |
| 多章 NPC（去泛称） | 254 |
| 用户 KEEP 单章 NPC | 23 |
| **合计** | **~658** |

### 试跑计划

17 角色：博士(40章)、凯尔希(32)、阿米娅(32)、能天使(7)、玛恩纳(5)、玛嘉烈·临光(6)、莫斯提马(4)、刻俄柏(4)、塞雷娅(4)、望(4)、菲亚梅塔(2)、余(2)、Guard(5)、白垩(1)、龙舌兰(1)、奥达(1)

### 成本估算

~658 角色独立调用，~$2.0 USD (DeepSeek)

### 文件

- `docs/specs/2026-06-20-pass2-character-extraction.md` — Pass 2 Spec v2
- `output/pass2_single_appearance_npc.md` — NPC 三轮过滤 + 用户 KEEP 标注

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-20-1.md — 完整会话记录
4. 下一步：writing-plans → TDD 开发 → 试跑 17 角色

---

## Pass 2 实施完成 (2026-06-20)

### 架构决策

- **Subagent-Driven TDD**：4 Task（character_aggregator / prompt_builder / post_processor / orchestrator），每 task 经三轮审查（implementer → spec reviewer → code quality reviewer）
- **filter_targets +min_events=8**：单章 NPC >=8 事件自动纳入，+113 角色（537 → 650）。Why: 原"多章"规则漏掉单章重要配角（白垩19事件、安多恩31事件等）
- **LLM 辅助身份映射发现**：`run_identity_discovery.py` 批处理，LLM 识别人名→干员映射，错误率 ~60%，必须人工审核
- **identity_map +27 条**：覆盖异格、真名、别名、英文代号、称号五类
- **identity_map 错误修正**：删除 Guard→阿米娅（Guard 是独立 NPC），补充埃内斯托→龙舌兰

### 关键 Bug

- `inject_context` 路径缺失 category 前缀（`data/stories/{chapter}` → `data/stories/{category}/{chapter}`），所有原文注入静默失败
- `get_operator_archive` 只返回 archives 子 dict，已修复为完整 operator 对象

### 试跑基线

| 指标 | 值 |
|------|-----|
| 提取角色 | 17/17 成功 |
| JSON 解析成功率 | 100% |
| power_level "信息不足" | 2/17（12%） |
| 成本 | ~$0.50 |
| 耗时 | ~3.5 min |

### 代码基线

```python
arknights_wiki/extraction/
  character_aggregator.py  # 新建 — 8 functions, 31 tests
  prompt_builder.py        # 扩展 — +3 functions, +9 tests
  post_processor.py        # 扩展 — +1 function, +6 tests
  orchestrator.py          # 扩展 — +4 functions, +3 tests
```

210 tests passing.

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-20-2.md — 完整会话记录
4. 下一步：用户审阅试跑 → 全量 650 角色提取

---

## Pass 2 试跑审阅 + 全量提取完成 (2026-06-21)

### 试跑审阅修复

- **博士 power_level**：直接修改 JSON，"战场中坚·顶尖" → "信息不足"
- **能天使 alias "堕天使"**：模糊匹配误伤（SequenceMatcher "堕天使"→"能天使" ratio≥0.6）。identity_map 加 `"堕天使": "character:堕天使"` 阻断匹配
- **菲亚梅塔 alias**：identity_map 加 `"苦难陈述者": "菲亚梅塔"`
- **阿米娅 alias "Guard"**：上次会话已修复 identity_map，试跑使用的是旧数据

### filter_targets 空名修复

- Pass 1 参与者中出现空字符串（无名旁观者），通过 filter_targets（多章多事件）产生 `.json` 文件
- `filter_targets` 循环开头加空名过滤

### 全量提取

| 指标 | 值 |
|------|-----|
| 目标 | 641（空名过滤后） |
| 成功 | 641/641 (100%) |
| JSON 解析失败 | 0 |
| 校验错误 | 0 |
| tokens | 14,969,572 in / 534,594 out |
| 费用 | $4.63 USD (~¥33 RMB) |
| 耗时 | 1h48m |
| 输出 | `data/extractions/v2_characters/` |

### 战力评级审计发现

九级战力体系分布严重不均：
- **战场中坚过度集中**（271人，61.8%）—— LLM 将大部分战斗干员塞入最低战斗档
- **大国将军断档**（仅 1 人）—— 阵营领袖未正确评级
- **王庭之主偏多**（44人，10%）—— 远超该档位合理范围
- **中间档位大量空白**（军事精锐·下位/顶尖等均为 0）
- **信息不足 204 人**（31.8%）—— 164 NPC + 31 低出场干员

根因：prompt 缺乏九级体系锚点示例，LLM 无法区分相邻档位边界。下个会话单独处理。

### 代码基线

```
arknights_wiki/extraction/
  character_aggregator.py  # +4 行（空名过滤）
config/
  identity_map.json        # +2 条（堕天使、苦难陈述者）
data/extractions/
  v2_characters/           # 新建 — 641 角色 Wiki JSON
run_pass2_full.py          # 新建 — 全量提取脚本
```

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-21-1.md — 完整会话记录
4. 下一步：战力评级体系重新设计（九级锚点示例 + prompt 优化）

---

## Pass 2 战力评级重设计 (2026-06-21)

### 架构决策

- **去掉上下位子级**：旧格式「战场中坚·标准」-> 新格式「战场中坚」
- **每级增加锚点基准角色**：用户提供 9 级定义，每级含 2-7 个基准角色示例
- **移除"灭世灾厄"**：已并入"文明之敌"，VALID_POWER_LEVELS 从 30 个值收敛为 10 个
- **power_level_evidence 字段**：新增，LLM 列出支撑评级的 1-3 个关键战斗事件，实现战力评级到具体章节事件的追溯链路

### 执行结果

| 指标 | 值 |
|------|-----|
| 成功/失败 | 641/641 (全量重提取) |
| 输入 tokens | 15,167,618 |
| 输出 tokens | 520,356 |
| 费用 | $4.67 USD |
| 耗时 | 111 min |

### 分布对比

| 等级 | 旧版 | 新版 |
|------|------|------|
| 信息不足 | 204 (31.8%) | 359 (56.0%) |
| 战场中坚 | 271 (61.8%) | 166 (25.9%) |
| 军事精锐 | — | 56 (8.7%) |
| 传奇英雄 | 19 (4.3%) | 28 (4.4%) |
| 王庭之主 | 44 (10.0%) | 21 (3.3%) |
| 神明碎片 | — | 7 (1.1%) |

### 代码变更

- `prompt_builder.py` — 战力评级 prompt 重写（9级锚点+去子级）+ power_level_evidence 输出指令
- `post_processor.py` — VALID_POWER_LEVELS 简化 + power_level_evidence 校验
- `data/extractions/v2_characters/*.json` — 641 角色全量重提取

---

## Pass 2 Mantra 修复 + Pass 3 预研 (2026-06-21)

### 架构决策

- **Mantra 误合并修复**：`SequenceMatcher("Mantra", "Mon3tr")` = 0.667 超过模糊匹配 0.6 阈值。根因：Mon3tr 在 operators.json 中但不在 identity_map，导致 normalizer 将 Mantra 模糊匹配到 Mon3tr。修复：identity_map 加 `"Mantra": "character:Mantra"` 阻断
- **Pass 3 方案选定 C**：世界观专用重提取 — 每章额外 LLM 调用，专门提取世界观实体（带实体辨析+分类+关系），跨章聚合生成 Wiki 页面。成本 ~$3-5
- **Pass 3 输出**：三层独立（概念/阵营/地点），统一 schema，有层次有实际内容

### Pass 1 数据基线

| 维度 | 唯一值 | 1次占比 | 3+次实体 |
|------|--------|---------|----------|
| 概念 | 890 | 94.4% | 18 |
| 阵营 | 389 | 57.1% | 105 |
| 地点 | 441 | 70.3% | 60 |

### 世界观概念诊断

Pass 1 概念提取只能做章节级"这段在讨论什么"标注，无法做实体辨析。所有巨兽（耶拉冈德、岁兽、海神等）被无差别标为"巨兽"，萨卡兹本质上是个政治概念而非种族（凯尔希原话）但 Pass 1 没捕捉到这个层次。Pass 3 的 C 方案从根本解决此问题。

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-21-3.md — 完整会话记录
4. 下一步：用户准备补充材料 → 新会话继续 Pass 3 brainstorming → Spec → Plan → 实施

---

## Pass 3 brainstorming 第一轮 (2026-06-22)

### 架构决策

- **数据源三合一**：Pass 1 剧情文本 + data/videos/ 视频字幕 + 《大地巡旅》设定集
- **视频内容补充**：37 个视频分 4 类（探泰拉/前探泰拉/特别映像/一分钟看泰拉），含大量游戏内文本未覆盖的世界观信息
- **视频定位 C 方案**：分类处理 — 特别映像作为补充上下文，探泰拉系列作为独立提取源
- **提取方法论 B+**：视频种子提取 → 逐章原文重提取（实体链接+新实体发现）→ 跨章聚合
- **概念六子类体系**：自然现象/物质、种族/血脈、超自然存在、技术/技艺体系、社会制度/文化、特殊地域/异域
- **不设频率门槛**：分类体系做唯一门禁，单次出现的关键信息保留并标注 `coverage: single`
- **阵营精简为 2 子类**：国家/政权 + 势力/组织（标注 parent_nation）
- **地点精简为 2 子类**：城市/移动城市 + 设施/建筑。特殊地貌/异域归入概念层
- **概念页面 Schema**：通用字段（name/aliases/category/definition/summary）+ 各子类差异化属性字段 + 关系字段 + 证据字段
- **验证 7 章**：孤星、相见欢、慈悲灯塔、怒号光明、长夜临光、愚人号、火山旅梦
- **《大地巡旅》**：426 页官方设定集，用户持有实体书，待扫描 OCR

### 数据

| 项目 | 数量 |
|------|------|
| data/videos/ | 37 个视频字幕（多语言，含 STT 错误） |
| 《大地巡旅》目录 | 6章/19国/35+种族/20+组织 |

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-22-1.md — 完整会话记录
4. 下一步：用户完成《大地巡旅》扫描 OCR → 恢复概念页面 Schema 设计 → 加入设定集作为第三数据源

---

## 大地巡旅 OCR 完成 (2026-06-22)

### 架构决策

- **MiniMax M3 视觉 OCR**：用原生多模态 M3 模型逐页提取扫描图片文字，模型 MiniMax-M1 不支持图片
- **thinking 模式禁用**：`extra_body={"thinking": {"type": "disabled"}}`，输出 token 从 ~2000 降至 ~500（省 70%），质量无损
- **重试 3 次指数退避**：2s/4s/8s，解决 API Connection error
- **续跑机制**：JSON state 文件（`ocr_state.json`）记录每页 completed/failed，中断重跑不丢进度
- **中文提示词优于英文**：内容审查场景下中文提示词成功率更高
- **输出格式**：`[图：...]` 标记图片描述，`【手写批注：...】` 标记凯尔希批注，`[推测：X]` 标注模糊字

### 数据基线

| 指标 | 值 |
|------|-----|
| 扫描页 | 403 张 JPG（扫描全能王） |
| OCR 成功 | 401/403 (99.5%) |
| 失败 | 2 页（201, 269）MiniMax 图片内容审查永拒 |
| 产出字符 | ~428,000 |
| 总费用 | RMB 5.23 |
| 速率 | ~2 页/分钟 |
| 单页输出 | `data/lorebook/terra_a_journey/page_XXX.md` (401 个) |
| 合并全文 | `data/lorebook/terra_a_journey_full.md` (1.2MB) |

### 代码

- `run_ocr_full.py` — 批量 OCR 脚本（可复用）

### 已知问题

- Pages 201, 269 被 MiniMax 输入审查（error 1026）拦截，缩小到 30% 仍被拒
- 编年史页（403）图片旋转 90°，OCR 质量差，用户手动处理

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-22-2.md — 完整会话记录
4. 下一步：Pass 3 概念页面 Schema 最终确定 → 加入设定集作为第三数据源

---

## Pass 3 Phase 1+2 大地巡旅+视频提取 (2026-06-23)

### 架构决策

- **Schema 确认**：概念 6 子类独有字段、阵营 2 子类（国家含 key_figures/historical_events/foreign_relations，组织含 member_composition）、地点 2 子类
- **story_events 通用字段**：Phase 3 原文阶段填充
- **国家间用 foreign_relations** 替代 allies/enemies 二元对立
- **两遍提取策略**：DeepSeek 8192 token 输出上限导致 concepts 抢占 factions/locations 空间。Phase 1a（factions+locations 优先输出）+ Phase 1b（concepts 专用提取）
- **Ch5 拆分**：原 240 页国家与地区超出 token 预算，拆为 4 段
- **时间线统一**：正文散布年份事件 + 附录泰拉纪年 -> 统一 timeline_events 字段，49 条（34 附录 + 15 视频），跨度 759-1099

### 数据基线

| 指标 | 值 |
|------|-----|
| 概念 | 110（种族 45 + 技术 20 + 社会制度 19 + 自然现象 15 + 超自然 6 + 异域 5） |
| 阵营 | 74（31 国家 + 43 组织） |
| 地点 | 23 |
| 时间线 | 49 |
| 国家覆盖 | 17/18（缺萨米） |
| tokens | 304,874 in / 84,560 out |
| 成本 | ~$0.18 USD |

### 新建文件

```
arknights_wiki/extraction/
├── book_splitter.py + tests
├── video_merger.py + tests
├── worldbuilding_schema.py + tests
├── worldbuilding_prompts.py + tests
├── worldbuilding_processor.py + tests
└── worldbuilding_orchestrator.py + tests
```

---

## Pass 3 Phase 3 试跑调优 (2026-06-23)

### 架构决策

- **实体清单按章过滤**：`build_entity_checklist(filter_text=chapter_text)` — 子串匹配实体名+aliases，只传文本中出现的实体给 LLM。种子库 452 实体 → 过滤后 ~40 实体，prompt 缩减 90%。保底 10/5/2 防止空清单
- **分批策略字符数驱动**：`split_chapter(max_chars_per_batch=42000)` — 行数无法反映 token 消耗（"嗯。"和 200 字独白都算 1 行），改为字符数。批数动态计算 `ceil(total_chars/42000)` 替代硬编码 3 批。切分边界仍用 node 自然边界
- **别名匹配增强**：`_resolve_entity` 处理 LLM 输出简名（"炎武"）匹配种子库全名（"炎武（皇子）"）的情况，通过 alias 索引 + 去括号匹配 + 前缀匹配三层回退
- **Prompt v4 演进**：三级事件体系 (revelation/major/minor) + 角色型实体 ABC 分类 + 关键对话场景识别 + 成员强制关联
- **合并逻辑 6 项增强**：source_chapter 回填、member name-only 去重、占位事件过滤、跨层去重(concepts vs factions)、层内同名去重、source_records story_text 补全

### 试跑结果

| 阶段 | 章节 | 成功率 | 实体 | 事件 | Revelations | 成本 |
|------|------|--------|------|------|-------------|------|
| 第1轮 (7章通用) | 孤星等 7 章 | 100% | 262c/100f/57l | 696 | 112 | ~$0.18 |
| 第2轮 (炎国7章) | 画中人等 7 章 | 修复后 100% | 338c/100f/58l | 1,461 | 259 | ~$0.23 |

### 关键验证

- 天镜阁炎武-真龙重逢: 4 层 revelation + 原文引用 ✅
- 炎武=魏彦吾 alias 链接 ✅
- 炎景→陈晖洁之母 alias 补充 ✅

### 已知问题

- 天机阁/天师府 member_composition 仍偏弱 — prompt 驱动效果有限，需 entity_checklist 预填 known members
- 事件跨 batch 轻微重复（同名不同描述，互补性）

### 代码基线

```
arknights_wiki/extraction/
  dialogue_loader.py        — split_chapter 字符数驱动
  worldbuilding_prompts.py  — entity checklist filter + prompt v4
  worldbuilding_orchestrator.py — merge 6 项增强 + alias match
  worldbuilding_processor.py — Wiki revelation blockquote 渲染
```

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-23-3.md — 完整会话记录
4. 下一步：全量 106 章 Phase 3 执行（过滤+字符分批已就位）

---

## Pass 3 Phase 3 全量执行 (2026-06-23)

### 架构决策

- **三批执行逐步修复**：第1批 API 挂起 -> max_chars_per_batch 42K->35K + API 300s 超时 + 指数退避重试；第2批崩溃 -> LLM 输出 `new_entities` 混入字符串，加 `isinstance(entity, dict)` 类型保护
- **断点续跑机制**：每章完成保存检查点到 `v3_seed_db_v3_checkpoint.json`，恢复时从 source_records 提取已处理章节名自动跳过
- **跳过策略**：7 个炎国章节（已正确跑过）+ 3 个空内容章（预期 0 mentions）
- **分批字符数阈值**：从 42K 降至 35K，批数动态计算替代硬编码 3 批

### 最终基线

| 指标 | 值 |
|------|-----|
| 概念 | 1,199 |
| 阵营 | 234 |
| 地点 | 245 |
| 时间线事件 | 49 |
| 有 story_events 的实体 | 1,427 |
| 总 story_events | 5,088 |
| Wiki 页面 | 1,679 |
| 成本 | ~$3.00 USD |

---

## Pass 3 质量修复 (2026-06-24)

### 架构决策

- **阵营成员去重机制**：`operators.json` team/group → `faction_roster_index.json` (25阵营/134干员) + `identity_map.json` (141条) → 276条名字规范化器。解决跨 batch 同名不同写的合并失败问题。
- **概述质量诊断**：Phase 3 的 `summary` 字段 100% 来自大地巡旅段落拼接（`_dedup_summary()`），剧情事件仅追加为 `story_events`，从未反馈到概述。属于架构级缺陷。
- **Phase 3.5 概述 LLM 重写**：用 story_events + 原文摘录 → LLM → 新概述，替代纯大地巡旅版。16 个核心阵营验证可行，~$0.36。
- **兽主/巨兽手动补全**：新建 5 兽主 + 2 巨兽词条 + 重写兽主总括页。AUS = 日落即漸为同一实体，合并至 AUS 页面。
- **岁兽碎片**：9/12 碎片有独立词条（新建 重岳/夕/年/黍），缺失颉及两个未知碎片。

### 代码基线

```
scripts/fix_faction_members.py      — 阵营成员去重补全
scripts/regenerate_overviews.py     — 概述 LLM 重写
data/faction_roster_index.json      — 干员→组织基准索引
```

### 数据基线

| 指标 | 值 |
|------|-----|
| 阵营 wiki 页面 | 247 |
| 阵营成员修复 | 去重 253 + 补全 283 (18 个阵营) |
| 顾筌系重复去重 | 6→4 词条 |
| 概述 LLM 重写 | 16 个阵营 |
| 新建兽主词条 | 5 个 |
| 新建/补充巨兽词条 | 3 个 (睚、萨米、AUS=日落即漸) |
| 新建岁兽碎片词条 | 4 个 (9/12 已覆盖) |

### 已知问题

- `generate_wiki_pages()` 从 seed DB 重建会覆盖手动编辑的 wiki 页面
- 仅 16/234 阵营完成概述重写，其余仍是纯大地巡旅版
- 睚、宁茵、顾筌案等手动修复需从 seed DB 层面重新应用

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-24-1.md — 完整会话记录
4. 下一步：引入 OpenEval 对当前 v3_wiki 数据做系统质量评估

---

## OpenAI Evals 评估框架集成 (2026-06-24)

### 架构决策

- **OpenAI Evals 3.0.1.post1**: 选型而非自建。ModelBasedClassify 作为核心执行类，配合自定义 modelgraded YAML 做 LLM-as-judge 评估
- **DeepSeek 适配**: `DeepSeekCompletionFn` 继承 `OpenAIChatCompletionFn`，通过 `api_base=https://api.deepseek.com/v1` + `deepseek_api` 环境变量接入。需桥接 `OPENAI_API_KEY`（evals 包 import 时创建全局 client 需要）
- **Monkey-patch `add_token_usage_to_result`**: 新版 OpenAI SDK 的 `usage` 包含 `prompt_tokens_details` (对象) 等非 int 字段，原代码 `sum()` 操作报 TypeError
- **评估 = 数据层(JSONL) + 评分模板(modelgraded YAML) + 执行层(eval YAML + CLI)**: 三层分离，每项评估只需新增 modelgraded YAML + 数据生成脚本 + eval 注册
- **30% 抽样策略**: 全量规则检查（零成本）+ 30% 抽样 LLM 验证（可控成本）。覆盖面足够，误差 < 3%

### 评估基线

| 维度 | 均分 | A+B 准确率 | 关键问题 |
|------|------|-----------|----------|
| 概述融合度 (P3) | 3.18/4.0 | 69% | 29% C级纯设定集未融合 |
| 索引可追踪性 (P1) | 2.47/3.0 | 90% | 9% D级，短span+描述越界 |
| 索引可追踪性 (P2) | 2.39/3.0 | 96% | 角色总结偏泛化 |
| 索引可追踪性 (P3) | 2.19/3.0 | 87% | 12% 无有效来源标记 |

P1 D级失效根因: (1) 短 span/短原文 26-29% (2) 描述越界推断 ~45% (3) locations D率最高 16%

### 代码基线

```
arknights_wiki/eval/                      # 新建
scripts/generate_eval_data.py             # 新建
scripts/generate_traceability_p1_data.py  # 新建
scripts/generate_traceability_p2_data.py  # 新建
scripts/generate_traceability_p3_data.py  # 新建
scripts/run_eval.py                       # 新建
```

pyproject.toml: `eval = ["evals>=3.0"]`

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-24-2.md — 完整会话记录
4. 下一步：LangGraph AI Agent 构建（RAG 问答/剧情分析/世界观查询）

---

## LangGraph AI Agent 核心实施 (2026-06-24)

### 架构决策

- **方案 C（混合路由 + LangGraph Agent）**：Query Router 本地规则分类 simple/complex → simple 走 4 层检索 + LLM 直接回答，complex 走 LangGraph ReAct Agent 多步检索
- **不引入 LangChain，仅用 LangGraph**：LangChain 的 `create_react_agent` 底层就是 LangGraph，直接用更灵活。Retrieval 层不是标准 Document/VectorStore 模式
- **FAISS 语义检索 + chunk_id 溯源**：参照 mrfz 模式，`concept:源石` → 精确实体。BGE-small-zh-v1.5 (ModelScope 下载，HuggingFace 被墙)，IndexFlatIP 内积搜索
- **SentenceTransformer segfault 修复**：Windows PyTorch 2.11.0 上 SentenceTransformer 加载模型 C 层段错误。改用 `AutoModel` + 手动 mean pooling（生成相同 BGE 嵌入）
- **FP16 在 CPU 反而慢 9x**：FP32 23s/128条 vs FP16 214s/128条。CPU 上 FP16 需额外转换开销
- **7 个 LangGraph tools**：search_wiki / get_entity_page / search_events / search_dialogue / search_timeline / get_chapter_summary / semantic_search
- **Subagent-Driven TDD**：10 Tasks 并行派发，45 tests

### 数据基线

| 指标 | 值 |
|------|-----|
| FAISS 向量 | 6,666 (512-dim BGE) |
| 模块文件 | 7 agent + 1 build script |
| 测试 | 45 passed |
| 编码耗时 | 43min (FP32 CPU) |

### 代码基线

```
arknights_wiki/agent/ (新建, 10 模块)
tests/agent/          (新建, 45 tests)
scripts/build_agent_index.py (新建)
```

### 已知问题

- 前端 UI 简陋（无步骤可视化、来源展开）
- 评估器未运行
- complex 路径未端到端测试
- 索引无增量更新机制

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-24-3.md — 完整会话记录
4. 下一步：前端重构 → 评估器测试

---

## Agent 前端 UI 重设计 (2026-06-24)

### 架构决策

- **PRTS 终端美学**: 模拟游戏内 PRTS 系统。Share Tech Mono + Source Code Pro 等宽字体，罗德岛靛蓝 (#4fc3f7) + 源石琥珀 (#ffb000) + 金色高亮 (#e6b422)。10 个 CSS 变量统一管理配色
- **双栏布局**: 左侧聊天面板 (flex:1) + 右侧检索追踪面板 (280px)。5 种 SSE 事件完整映射到 UI 组件
- **纯 HTML/CSS/JS**：无框架，FastAPI StaticFiles 挂载。SSE ReadableStream 逐行解析，tokenCount 实时计数
- **3 种视觉效果**: 文字 glow (text-shadow) + 发光边框角标 (::before L 形) + 自定义光标 (caret-color amber / cursor crosshair)
- **Subagent-Driven TDD**: brainstorming (visual companion) → writing-plans → 5 Tasks subagent 实施 → 每 task 双审 (spec + code quality)

### 代码基线

```
arknights_wiki/agent/
├── server.py           # 修改: -53 行 (删除内嵌 HTML), +StaticFiles mount
└── static/             # 新建
    ├── index.html      # 1,731 B
    ├── style.css       # 8,463 B (365 行)
    └── app.js          # 6,415 B (205 行)
```

### 验证

| 指标 | 值 |
|------|-----|
| 测试 | 45/45 passed |
| 端点 | 4/4 200 (/, /static/style.css, /static/app.js, /health) |
| Commits | 6 |

### 已知问题

- Firefox scrollbar 兼容性 (-webkit- 前缀)
- 四角 L 形装饰仅顶角 (plan 本身如此)
- 部分背景色硬编码 #0a1020 未提取 CSS 变量

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-24-4.md — 完整会话记录
4. 下一步：浏览器验证 UI → finishing-a-development-branch → 评估器测试

---

## Agent 提示词工程 (2026-06-25)

### 架构决策

- **CASUAL persona 固定**：所有回答采用"朋友聊天补课"风格 — 口语化、先核心答案再展开、禁止 [N] 引用标记、禁止事件罗列。识别了 4 种用户 persona（CORE/CASUAL/OUTSIDER/MAKER），当前固定 CASUAL
- **意图识别 + 问题改写合并**：关键词规则（7 类意图）先行 → LLM 兜底（`INTENT_REWRITE_PROMPT`）。本地规则：concept_definition / chapter_summary / character_profile / causal_reasoning / comparison / fact_lookup / list_enumeration
- **复杂度路由更新**：concept_definition / comparison / list_enumeration / causal_reasoning / 多实体（>1 clean_entity）→ 强制 complex（LangGraph Agent 多步检索）
- **预构建双向实体索引**：`scripts/build_entity_index.py` 一次性构建 `entity_source_map.json`（5,213 实体, 25,300 双向引用）。数据源：Pass1 events + Pass2 characters + Pass3 wiki + operators.json + 大地巡旅。原文路径存储但不默认加载
- **第 8 个 tool**：`lookup_entity_index` — LangGraph Agent 可查询实体关联和出现章节
- **检索策略意图驱动**：concept_definition → get_page 优先；chapter_summary → get_chapter_summary + 限定章 events；FAISS 阈值 0.3→0.4 减少噪声
- **Superpowers 升级**：v5.0.7 → v6.0.3（手动 tarball 安装），13/14 skills 变更，SDD 审查流程重写
- **grill-with-docs 引入**：建立 `CONTEXT.md`（领域术语 + persona + 意图分类 + 索引设计）

### 代码基线

```
arknights_wiki/agent/
├── prompts.py          # 重写: 4 prompt (INTENT_REWRITE + 3 CASUAL)
├── router.py           # 重写: 意图+改写合并, 更新复杂度规则
├── retrieval.py        # +EntityIndexStore
├── tools.py            # +lookup_entity_index (8 tools total)
├── simple_search.py    # CASUAL prompt + 意图驱动检索
├── graph.py            # CASUAL 错误消息
scripts/
└── build_entity_index.py  # 新建
data/
└── entity_source_map.json # 新建, 2.3MB, 5,213实体
CONTEXT.md              # 新建: 领域术语
```

### 数据基线

| 指标 | 值 |
|------|-----|
| 测试 | 71/71 passed (+26 from 45 baseline) |
| 工具数 | 8 (新增 lookup_entity_index) |
| 实体索引 | 5,213 实体, 25,300 双向引用 |
| 路由 "巨兽是什么" | concept_definition + complex ✅ |
| 路由 "最新怪猎活动" | chapter_summary + complex, LLM改写 ✅ |

### 已知问题

- **怪猎联动消歧**：有两期联动（落叶逐火 CF + 泡影苍霆 TD），"最新"应指向泡影苍霆但 LLM 改写只输出落叶逐火。缺少章节发布时序元数据
- 评估器已实施（5 维体系，100 题基线），未做真机端到端测试

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-25-2.md — 完整会话记录
4. 下一步：修复 CASUAL prompt 幻觉 → 评估方法论改进 → 真机验证

---

## Agent 五维评估器实施 (2026-06-25)

### 架构决策

- **五维评估 + MiniMax M3 judge**：entity_link_precision / source_relevance / answer_accuracy / answer_focus / routing_correctness，MiniMax M3 独立评估（与 agent DeepSeek 解耦），`thinking: disabled` 防止 think 块污染
- **100 题测试集**：吸收 mrfz 项目 `batch_qa.py` (165题/13类) + `qa_log.json` (15条真实用户查询) 的模式，覆盖 14 类别/5 维/3 难度/7 意图
- **路由器修复**：`_infer_intent_local` 优先级 chapter_summary → character_profile → concept_definition。根因：`'是什么' in "孤星讲了什么"` 被 concept_definition 先匹配。修复后意图 100%，路由 92%
- **评估方法论缺陷**：answer_accuracy (1.36/3.0) 混入了检索失败与真实幻觉。案例 q063 "罗德岛精英干员"：Sharp 真实存在于 `factions/罗德岛.md` 但 agent 检索未命中 → MiniMax judge 判 D。需拆分为来源忠实度 + 事实正确性子维度
- **CASUAL persona 幻觉问题**：22/100 题 answer_accuracy=D，LLM 自由发挥超出检索来源

### 评估基线

| 维度 | 均分 | A+B率 | A | B | C | D |
|------|------|-------|---|---|---|---|---|
| entity_link_precision | 2.67 | 89% | 82 | 7 | 7 | 4 |
| source_relevance | 2.17 | 90% | 31 | 59 | 6 | 4 |
| answer_accuracy | 1.36 | 49% | 9 | 40 | 29 | 22 |
| answer_focus | 2.50 | 96% | 56 | 40 | 2 | 2 |
| routing_correctness | 2.30 | 83% | 55 | 28 | 9 | 8 |
| **综合** | **2.20** | — | — | — | — | — |

### 代码基线

```
arknights_wiki/eval/agent_evaluator.py              # 新建
arknights_wiki/eval/registry/data/agent_eval_questions.jsonl  # 新建 — 100题
arknights_wiki/eval/registry/modelgraded/{5-dim}.yaml         # 新建
scripts/run_agent_eval.py                           # 新建
arknights_wiki/agent/router.py                      # 修改 — 意图优先级
output/agent_eval_20260625_233940.json              # 766KB
output/agent_eval_report.md                         # 评估报告
```

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-27-1.md — 完整会话记录
4. 下一步：实体噪声过滤 → search_dialogue bugfix → 意图关键词补充

---

## Agent Persona 重写 (2026-06-27)

### 架构决策

- **Persona 三轮迭代至百科编纂者**：CASUAL "朋友聊天" → "知识解说" → "百科编纂者"。Why: CASUAL 不适合讲述性质内容，复杂问题回答过短；知识解说介于聊天和百科之间仍不满意；最终确定准确、逻辑严密、行文有前后逻辑脉络的百科全书风格
- **来源忠实度维持不动**：首次 prompt 修复中的"首要原则：忠于来源"验证通过（8/10 D 级题提升），本轮不改
- **回答结构按问题类型**：剧情按时间线/因果链，概念从定义到展开，角色从概括到细节
- **去口语化**：禁止口语闲聊、碎片罗列、分点列表
- **QA 日志机制**：server.py 中 `_log_and_stream` 包装 SSE 流，每次对话自动写入 `output/qa_log.jsonl`
- **evidence 格式优化**：graph.py 去掉 `[来源N]` 标记改为 `--- 资料 N: tool ---` 分隔，消除 prompt 中"禁止输出引用标记"与 evidence 格式的认知冲突

### 前端验证发现

通过 5 个实际提问发现三个系统性缺陷：
1. **实体提取噪声** — WikiStore name 匹配引入大量弱相关实体（如"相变临界"匹配到"罗德岛""乌萨斯"）
2. **search_dialogue 崩溃** — `'list' object has no attribute 'get'`，连崩 5 次
3. **意图关键词缺失** — "肉鸽""结局""集成战略"未映射

### 代码基线

```
arknights_wiki/agent/
├── prompts.py           # 重写: QA/AGENT/SYNTHESIS 三 prompt 转为百科编纂者
├── server.py            # +_log_and_stream Q&A 日志包装器
├── graph.py             # evidence 格式去 [来源N] + 无docs消息去口语化
└── simple_search.py     # build_answer_prompt 转为百科编纂者
output/
└── qa_log.jsonl          # 新建 — 前端 Q&A 日志 (5 条)
```

---

## Agent Pipeline 系统性优化 (2026-06-27)

### 诊断方法

基于 qa_log.jsonl 14 条真实对话，按 5 阶段逐条诊断：意图识别→实体提取→复杂度路由→多源检索→回答合成。

发现 12 个缺陷，按影响面优先修复 8 个。

### 架构决策

- **实体提取砍掉 WikiStore 全量扫描**：5213 实体子串匹配 → identity_map(150) + operators(340) + chapter_timeline(109) 三层精确提取。实体噪声从 5-9 降至 1-2
- **章节感知事件检索**：自动识别实体中的章节名（通过 get_chapter_summary 试探），将章节实体与角色/概念实体分离，事件搜索始终按章节过滤。解决 "相变临界中凯尔希怎么样" 检索漏配问题
- **expansion_hints 与 canonical_entities 分离**：LLM 返回的扩展词不再参与路由决策和事件检索，仅用于 wiki 补充搜索。避免 "界园肉鸽" 被 LLM 扩展的 "探索者的银凇止境" 带偏
- **LLM 章节名幻觉过滤**：LLM 返回的 canonical_entities 中，如实体在 chapter_timeline 中存在但不在问题文本中，自动降为 expansion_hints
- **复杂度路由修正**：concept_definition 不再强制 complex；多实体阈值 >1→>3
- **叙事弧线 prompt**：章节总结类回答强制 "起因→经过→关键转折→高潮→结局" 结构，禁止事件罗列
- **来源忠实度强化**：新增 "不自行补充具体方式/机制""不添加资料中没有的数字/序号" 规则。经查 "第2068次复生实验" 实为数据源中存在的原文
- **search_dialogue 类型守卫**：`_order.json` 为纯数组导致 `'list' has no 'get'`，加 `isinstance(data, dict)` 跳过

### 代码基线

```
arknights_wiki/agent/
├── retrieval.py       # +2 行: DialogueStore isinstance 守卫 + EventStore == 精确匹配
├── router.py          # 重写: 实体提取 + 意图关键词 + LLM 章节幻觉过滤 + hints 分离
├── simple_search.py   # 重写: 章节感知检索 + hints 降权 search_and_collect
├── prompts.py         # 4 处: 叙事弧线 + 来源忠实度 + 章节名约束
├── tools.py           # 文本截断 500→1000/2000
└── graph.py           # 文本截断 500→1000
tests/agent/
├── conftest.py        # +operators.json fixture
└── test_router.py     # 3 处断言匹配新路由规则
```

### 验证基线

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 测试 | 76 passed | 76 passed |
| search_dialogue 崩溃 | 15 次/5 问题 | 0 |
| simple 路由占比 | ~20% | ~83% |
| 平均实体数 | 5-9 | 1.3 |
| 相变临界+凯尔希 | "未提及" | 正确追踪完整弧线 |
| 界园肉鸽 | IS4 银凇止境 | IS5 岁的界园志异 |

### 会话恢复指南

1. 读 README.md — 项目状态、快速启动命令
2. 读本文件末尾 — 最新决策
3. 读 output/sessions/2026-06-27-2.md — 完整修复清单
4. 下一步：用户手动测试前端 → 评估器重跑基线

---

## Agent 技术债务修复 (2026-06-29)

### 架构决策

- **brooks:debt 扫描**：发现 26 项技术债务，按 PxS 优先级修复 8 项（PxS 3-9）
- **FAISS 嵌入失败静默回退修复 (PxS=9)**：移除 `build_faiss_index` 和 `semantic_search` 中 `except Exception: np.random.randn` 静默回退，改为明确 `RuntimeError`
- **提示词重复消除**：4 处重复 -> 提取 5 个共享规则块（来源忠实度/逻辑组织/禁止列表）
- **`search_and_collect` 拆分**：108 行单体函数 -> `_resolve_chapter_context` + `_collect_structured_sources` + `_collect_semantic_fallback`
- **`_BaseStore` 基类**：5 个 Store 类统一 `__init__` 模式 + `SearchResult` TypedDict
- **`@tool` 装饰器注册**：TOOL_DEFINITIONS 从手动 3 处同步 -> 自动生成 `TOOL_DEFINITIONS` + `TOOL_EXECUTORS`
- **router.py 职责分离**：提取 `_llm_intent_rewrite` + `_make_intent_result`/`_make_complexity_result` 工厂函数
- **Persona 命名修正**：4 处 "CASUAL persona" 改为 "百科风格"（实际为严肃百科，非闲聊）
- **主线章节映射**：identity_map 添加主线别名 -> 创建 `主线章节.md` 概念页（18 章）

### 代码基线

| 分支 | 提交 | 说明 |
|------|------|------|
| fix/tech-debt-agent-priority | 542c00f | 8 项债务修复 |
| feature/langgraph-agent | 94d5063 | 合并修复 + persona + 主线映射 |

---

## Agent 检索质量全面修复 + 前端重设计 (2026-07-03)

### 关键修复

#### 数据加载 Bug（3 个静默失效）

- `_load_operators` 结构错误：operators.json 结构为 `{fetched_at, total, operators: [...]}`，原代码遍历顶层 key 只拿到 4 个字段名 -> 修复后正确读取 420 个干员
- `_load_identity_map` 结构错误：identity_map.json 结构为 `{_description, mappings: {alias: canonical}}`，原代码遍历顶层 key 只拿到 4 个元数据 -> 修复后正确读取 137 条映射
- **NPC 无法匹配**：新增 `_load_character_names()` 从 `v2_characters/*.json` 提取 642 个角色名，实体提取覆盖 identity_map(137) + operators(420) + characters(642) + chapters(109)

#### 检索质量核心修复

- **角色查询跨章均匀采样**：从 entity_source_map 获取全部出场章节，按时间线排序后均匀选取 5 个代表性章节（0%/25%/50%/75%/100%），每章取 2-3 个事件
- **LLM 意图幻觉校验**：`_llm_intent_rewrite` 返回非 7 种有效意图时回退本地意图
- **非角色查询 limit 提升**：3 -> 6

#### 流式体验

- **SSE 事件不刷新**：每个 `yield` 后加 `await asyncio.sleep(0)` 强制刷新事件循环
- **simple_search 阻塞**：改为 `loop.run_in_executor` + `queue.Queue` 实时推送检索进度
- **token 一次性到达**：块间加 15ms 延迟模拟逐字流式

#### 前端重设计：Noir Archive 风格

- **配色**：冷蓝+琥珀 PRTS 终端 -> "Noir Archive" 暗暖色系（古铜金 #d4b56a + 奶油白 #f0ebe1）
- **字体**：13px mono -> 15px 系统无衬线，行高 1.85
- **文本可读性**：textContent -> innerHTML，支持段落/粗体/标题/分隔线
- **新增功能**：智能滚动、流式闪烁光标、hover 复制按钮、Shift+Enter 换行

### 代码基线

| 分支 | 提交 | 说明 |
|------|------|------|
| feature/langgraph-agent | 7b5e1e9 | intent校验 + 删QA日志 |
| feature/langgraph-agent | 49bbd70 | 检索质量全面修复 + 前端重设计 |

### 清理

- 删除 `arknights_wiki/eval/` 全部评估器文件
- 删除 server.py 中 QA 日志功能（`_log_and_stream`）

---

## Ultracode 对抗式审查 (2026-07-03)

### 审查方法

19 个代理并行侦察/审查/验证 6 维度（正确性/安全/性能/架构/测试/LLM），237 工具调用，967K tokens，~12 分钟。评分：C+ (63/100)

### 修复清单（5 commits, 14 项修复）

#### 提交 7f00553 — 3 CRITICAL

- C-1: identity_map 路径错误 (DATA_DIR -> PROJECT_ROOT)
- C-2: 提示注入零防护 -> wrap_user_input + _INJECTION_DEFENSE
- C-3: 无输入长度/速率限制 -> max_length=2000 + rate limiter 30/min

#### 提交 8a45b1d — 7 HIGH

- H-1: EventStore 内存缓存
- H-2: DialogueStore 内存缓存
- H-3: Mock LLM 默认返回真实答案
- H-4: 工具测试添加内容断言
- H-5: search_future.result() 异常处理
- H-6: build_tool_listing() 从 @tool 注册表自动生成
- H-7: 已在 C-3 中修复

#### 提交 8897bfa — 3 架构改进

- 配置加载约定文档化 (router.py docstring)
- _BaseStore 缓存抽象 (_ensure_loaded + _do_load 模板方法)
- _RETRIEVAL_STRATEGY 提取为独立常量

#### 提交 29d4f83 — INTENT_META 单一数据源

- M-1: VALID_INTENTS 自动生成，_build_intent_listing 单一数据源
- 顺手修复: INTENT_REWRITE_PROMPT 改为 f-string，_INJECTION_DEFENSE 正确插值

#### 提交 c1cb347 — Agent SSE 修复

- 根因: graph.stream() 同步阻塞在 async generator 中，阻塞事件循环
- 修复: run_in_executor + queue.Queue，与 _simple_search_events 模式一致

### 代码基线

| 分支 | 提交 | 说明 |
|------|------|------|
| master | a43fc02 | feature/langgraph-agent 合并（1266 files, 37856 lines） |
| feature/langgraph-agent | 7f00553 -> c1cb347 | 5 commits, 14 fixes |

测试: **76/76 passed**（全程保持）

---

## 会话历史摘要

| 日期 | 会话 | 主要工作 | 关键产出 |
|------|------|----------|----------|
| 2026-06-15 | #1 | Phase 1 原始内容提取：Spec -> Plan -> TDD，mrfz scraper 管线迁移 | 87 tests, 1663 节点, 420 干员档案 |
| 2026-06-16 | #1 | M0 质量修复：职责收缩，移除 NPC/概念索引，异格去重 | 381 干员, 3,615 索引 |
| 2026-06-16 | #2 | 统计系统：Spec -> Subagent TDD -> 135 tests | stats/ 模块, JSONL 存储 |
| 2026-06-16 | #3 | 架构 v3 重设计：grill-with-docs 深挖，三遍独立提取替代 M0-M9 | 5 模型对比测试，确认 MiniMax M3 |
| 2026-06-16 | #4 | Pass 1 剧情骨架提取：Spec -> TDD -> 试跑 6 章 | extraction/ 5 模块, 28 tests, DeepSeek 选定 |
| 2026-06-17 | #1 | Pass 1 质量修复：场景级行号、自然节点分块、概念严格化 | identity_map 120+ 条, factions/locations 支持 |
| 2026-06-17 | IS | IS 结局适配 + 数据整理：5 级 taxonomy，PART 拆分 | 18 个 IS 结局，560 万字基线 |
| 2026-06-18 | #1 | Pass 1 全量质量修复：JSON schema 重排，三维质量审计 | 4,129 事件/957 概念/1,152 阵营, ~$3.0 |
| 2026-06-20 | #1 | Pass 2 Spec: brainstorming + grill-with-docs + NPC 清单 | 九级战力体系, ~658 目标角色 |
| 2026-06-20 | #2 | Pass 2 实施: Subagent TDD 4 Tasks | character_aggregator, filter_targets +113, 210 tests |
| 2026-06-21 | #1 | Pass 2 全量提取: 641 角色, 100% 成功, $4.63 | v2_characters/ 641 JSON, 战力评级审计 |
| 2026-06-21 | #2 | Pass 2 战力评级重设计：去子级、锚点基准、power_level_evidence | 641 重提取, $4.67, 分布显著改善 |
| 2026-06-21 | #3 | Mantra 修复 + Pass 3 预研：方案 C 选定 | Pass 1 数据摸底（1,678 实体） |
| 2026-06-22 | #1 | Pass 3 brainstorming：视频 37 部 + 大地巡旅 426 页 | 6 子类概念体系, 2 子类阵营/地点, 验证 7 章 |
| 2026-06-22 | #2 | 大地巡旅 OCR: MiniMax M3 视觉 403 页 | 401/403 成功, RMB 5.23, 1.2MB Markdown |
| 2026-06-23 | #1 | Pass 3 Phase 1+2: 大地巡旅+视频提取, Subagent TDD | 110 概念/74 阵营/23 地点/49 时间线, $0.18 |
| 2026-06-23 | #2 | Pass 3 Phase 3 试跑: prompt 4 轮演进 + merge 6 次增强 | 实体清单按章过滤(缩减 90%), 字符数驱动分批 |
| 2026-06-23 | #3 | Pass 3 炎国验证: 实体清单过滤 + 字符分批修复 | 炎国 7 章重跑 100% 成功, 338c/100f/58l |
| 2026-06-23 | #4 | Pass 3 Phase 3 全量: 三批执行 + 断点续跑 | 1,199 概念/234 阵营/245 地点, 5,088 events, ~$3.0 |
| 2026-06-24 | #1 | Pass 3 质量修复: 阵营成员去重 + 概述 LLM 重写 + 兽主/巨兽补全 | faction_roster_index, 16 阵营概述重写, 5 兽主+3 巨兽 |
| 2026-06-24 | #2 | OpenAI Evals 集成: 三 Pass 可追溯性评估 | P1 90% A+B, P2 96%, P3 87%, D 级失效根因诊断 |
| 2026-06-24 | #3 | LangGraph AI Agent: Spec -> 10 Tasks TDD | 7 tools, FAISS 6,666 向量, 45 tests |
| 2026-06-24 | #4 | Agent 前端 UI: PRTS 终端双栏 SSE 聊天 | 365 行 CSS, 205 行 JS, 6 commits |
| 2026-06-25 | #1 | Agent 提示词工程: grill-with-docs + SDD | CASUAL persona, 意图改写合并, 实体索引 5,213/25,300 |
| 2026-06-25 | #2 | Agent 五维评估器: 100 题 + MiniMax M3 judge | 综合 2.20/3.0, answer_accuracy 方法论缺陷发现 |
| 2026-06-27 | #1 | Agent Persona 重写: CASUAL -> 百科编纂者 | QA 日志机制, 3 个系统性缺陷发现 |
| 2026-06-27 | #2 | Agent Pipeline 系统性优化: 5 阶段诊断 -> 8 缺陷修复 | 实体噪声 5-9->1.3, simple 路由 20%->83% |
| 2026-06-29 | #1 | Agent 技术债务修复: brooks:debt 26 项 -> 修复 8 项 | _BaseStore, @tool 注册器, 提示词共享块 |
| 2026-07-03 | #1 | Agent 检索修复 + 前端重设计: 数据加载 3 bug + Noir Archive | 跨章采样, SSE 刷新, 新前端配色 |
| 2026-07-03 | #2 | Ultracode 对抗式审查: 19 代理/967K tokens/6 维度 | 14 项修复, 5 commits, C+ -> 76 tests 保全
---

## 升级阶段启动 (2026-08-15)

### 背景

- 用户提供《01_现有明日方舟LLM_Wiki项目评估与升级方案.md》（当前未跟踪，待提交）
- 方案核心结论：项目已超出普通 RAG 问答，**停止扩大数据量**，从「问答 Agent」升级为「**领域自治研究 Agent**」，目标是可评测 / 可观测 / 可控 / 可恢复的生产级 Agent 系统
- 优先级：P0 = Evaluation · Observability · MCP · Planner · Failure Recovery；P1 = Multi-Agent · Memory · HITL · Guardrails · 成本优化

### 本次产出

| 文件 | 说明 |
|------|------|
| CLAUDE.md | 新增第五章「升级阶段规则」U-01~U-14 + 第六章「升级工作流」（窗口任务制 / 数据冻结 / 评测优先 / 可观测 / MCP / 规划 / 恢复链 / 护栏 / HITL / 成本量化 / Memory / 上下文预算 / Benchmark 建库） |
| docs/plans/2026-08-15-upgrade-roadmap.md | 窗口任务制路线图：W0-W10 共 11 个任务，每窗口一个任务，含依赖图 / 验收标准 / 交接协议 |

### 子代理探索（三路并行，符合 U-13 上下文预算）

1. **Agent 与 Web 层**：8 个工具 @tool 注册表、LangGraph ReAct（无 checkpoint）、SSE 流式（run_in_executor + queue）；与升级规则逐条对照确认差距：eval/tracing/MCP/planner/memory 均为 0 痕迹；retrieval.py 5 个 Store 接口干净（MCP 低成本包装点）、@tool 注册表是权限分级理想注入点、ChatRequest.history 声明未接线（Memory 切入点）（补充：retrieval.py 的 5 个 Store 直接读 data/extractions 的 JSON/MD 文件，**非 SQLite**——Agent 检索层未用 store/ 的 M0 SQLite 层，W3 MCP 后端应基于文件读取层）
2. **抽取管线与数据层**：Pass1/2/3 三遍提取（13 模块），DeepSeek 优先 / MiniMax 回退，temperature=0.1，max_retries=3 + 指数退避 + 300s timeout；**无 LLM 结果缓存**（仅文件级 resume）→ 升级价值高（U-10）；store/ 4 张 SQLite 表；scripts/ 19 个；BGE-small-zh-v1.5 FAISS 6666 向量；任何 extraction schema 变更会波及 vector_index / router（补充：store/ SQLite 与 extraction/agent **零接线**——grep 仅命中 store 内部，三轨独立运行，升级时需决策三轨合一；stats/ 模块仅接入 store/seed.py 未接入 extraction；Pass3 逐章 checkpoint 续跑；FAISS 实际约 8.5k 向量，chunk 无文本级切分）
3. **测试、文档与工程规范**：350 个 test 函数（76 agent tests），**全 mock 零 API**（conftest mock_llm_client + ARKNIGHTS_SKIP_EMBED_MODEL）→ eval 基建底子好；**无 CI / 无 lint 配置 / 无 langfuse-langsmith-otel 依赖**；devlog 1261 行记录完整（06-15 → 07-03）；arknights_wiki/eval/ 已在 9ec03d2 删除，但旧 worktree 残留 OpenAI Evals 配置（wiki_quality / modelgraded traceability yaml）可作 W0 重建参考

### 关键差距（对照升级方案）

| 能力 | 现状 | 备注 |
|------|------|------|
| Evaluation | 有先例（06-24 可追溯性 P1 90%/P2 96%/P3 87%、06-25 100 题 2.20/3.0）但 eval/ 已删，无固定 Benchmark | W0 重建 |
| Observability | 0 配置，仅 stats/ JSONL | W1 Langfuse+OTel |
| MCP | 0，检索硬编码在 tools.py | W3 |
| Planner / Multi-Agent / Memory / HITL | 0 | W4-W7 |
| Failure Recovery | 仅 try/except 单层；call_llm 有重试但 agent 用 chat_completion 无 | W2 |
| Guardrails | 已有注入防御（wrap_user_input）、限流 30/min、长度 2000 | W8 补权限/输出校验 |

### 遗留事项

- output/frontend-comparison.html 未跟踪（临时对比产物，建议清理或归档）
- output/qa_log.jsonl 不在 .gitignore 白名单（核实是否会被误提交）
- CONTEXT.md 仍写 CASUAL persona，与 devlog 已改的「百科编纂者」不一致（文档分层同步瑕疵）
- 升级方案 md 与 CLAUDE.md/路线图变更均未 commit（按规则 review 后提交）
- 旧 worktree（.claude/worktrees/，已 gitignore）中保留 eval 参考配置

### 会话恢复指南

1. 读 README.md — 项目状态
2. 读本文件末尾 — 升级启动决策
3. 读 docs/plans/2026-08-15-upgrade-roadmap.md — 窗口任务清单
4. 下一步：开新窗口执行 **W0 Evaluation Benchmark 建库**（U-14 P0 首任务），参考旧 worktree 中 eval 配置重建评测体系

