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

### W0 eval 参考探索（旧 worktree 分析）

- 可复用：5 个 worktree（agent-a04b3204261ff60b7 等）含 eval 配置且逐字节一致——registry/evals/wiki_quality.yaml（编排）+ registry/modelgraded/ 4 个 judge 模板（entity/character/source_traceability + wiki_overview_fusion，ABCDE 五档 + cot_classify）+ completion_fns.py（DeepSeekCompletionFn 桥接 deepseek_api）
- 主分支残留：scripts/run_eval.py（oaieval 入口 + OpenAI SDK monkey-patch）、generate_eval_data.py + 3 个 traceability 生成脚本可直接复用
- 缺失：eval/registry/data/ 全部 JSONL 不在磁盘（需重新生成）；output/qa_log.jsonl 不存在（真实对话日志需重新采集）；06-25 五维 100 题无文件残留（仅 devlog 指标：综合 2.20/3.0，answer_accuracy 1.36 方法论缺陷——需拆「来源忠实度 + 事实正确性」）
- W0 决策（用户未回复，按推荐执行）：100 题 · LLM 生成+人工审核（无答案/易幻觉类人工构造）· 自建轻量 runner（arknights_wiki/eval/）· judge MiniMax-M3 · 核心 6 项指标

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

---

## W0 v3 实施（2026-08-15/16，全链路验证通过）

### 会话过程（v2 推翻重来 → v3 落地）

1. **v2 失败与回退**：轻量模型凭记忆出题（张冠李戴：第十二章配史尔特尔等）、自研 judge 维护成本高 → 用户决定推翻重来，W0 产物归档至 `output/_w0_v2_archive/`
2. **v3 方案（用户定义）**：内容层 6 角度（人物/事件/国家地区/组织/战斗力/世界观）× 简单/复杂路由 · grounded 生成（材料注入）· DeepEval 打分层 · 先出题后验证 · 材料三环校验（答案←材料←事实）· 交叉盲区分析（faithfulness×correctness）
3. **材料探索**：6 子代理并行产出 282 条材料（人物 50/事件 92/国家地区 30/组织 30/战斗力 40/世界观 40），excerpt 全部源文件原文，source_file 逐条核验
4. **100 题生成**：doubao-seed-2-0-mini + 材料注入，元评估 91 pass/3 review/6 reject；简单题按用户反馈重生成（答案含事实+依据，禁单字词）；并发版提速 10 倍
5. **DeepEval 落地（Docker）**：宿主 pip 安装受阻（缺编译工具链）→ Docker 方案：宿主交叉下载 Linux wheel（67 个）→ 构建 deepeval-local 镜像（4.1.8）→ 冒烟通过（GEval/Faithfulness 1.0）
6. **Pilot 20 题**：agent direct 模式跑批 + DeepEval 打分 + 试点报告

### 关键技术结论（下会话直接复用）

| 项 | 结论 |
|----|------|
| 模型可用性 | coding 端点仅部分模型可用：doubao-seed-2-0-mini-260428、deepseek-v4-flash-ga-260731 ✅；doubao-seed-1-6-flash 系列 404 UnsupportedModel |
| judge 模型 | deepseek-v4-flash-ga-260731（火山，经 arkcode_api + https://ark.cn-beijing.volces.com/api/coding/v3） |
| deepeval 4.x API | GEval（evaluation_params 用 SingleTurnParams 枚举）+ FaithfulnessMetric + HallucinationMetric（需 LLMTestCase.context）；is_successful()；必须禁遥测（`telemetry_opt_out = True`，否则 measure 极慢） |
| 打分 context | faithfulness/hallucination 的上下文 = **Agent 实际检索上下文**（非出题材料）；simple 路径 sources 仅元数据 → 回退材料（近似） |
| rule_metrics | simple 路由不调工具是正确行为（tool_selection=1.0）；complex 题预期工具未调用=0 |
| Docker 环境 | deepeval-local 镜像 + 挂载 /workspace + -e arkcode_api；冒烟 `python scripts/smoke_deepeval.py`；打分 `python scripts/score_runner.py` |
| 生成管线 | scripts/generate_benchmark_questions.py（并发 4 路、材料注入、章节比对、kb_check、元评估过滤） |

### Agent V1 试点指标（20 题 direct 模式）

| 指标 | 得分 |
|------|------|
| answer_correctness | 0.750 |
| faithfulness | 0.233 |
| citation_accuracy | 0.540 |
| hallucination_rate | 20% |
| task_completion_rate | 100% |

**发现的真实 Agent 问题**：① 路由偏差——character_complex 11 题 8 条被 router 误判 simple（复杂度分类对剧情题不敏感）② 角色题 faithfulness 低+幻觉 20%（回答超出检索内容）③ 事件题正确性 0.608（多事件综合弱）

### 成本

- 生成+元评估：¥0.29（含 v2 重复轮次）；pilot agent + DeepEval 打分另计——全部记入 `output/eval/cost_log.jsonl`

### 文件清单（本次新增，未提交）

- docs/specs/2026-08-15-eval-benchmark.md（v3）、docs/plans/2026-08-15-eval-benchmark.md（v3）
- arknights_wiki/eval/（config/llm/firecrawl/judge/runner/metrics/report/scoring/pricing）
- scripts/（generate_benchmark_questions.py、verify_benchmark_questions.py、smoke_deepeval.py、score_runner.py、docker_setup_deepeval.sh）
- benchmarks/arknights_bench/（materials/ 6 角度、questions_draft.jsonl 100 题、review_candidates.md、categories.md、manual_draft.jsonl 26 道人工题）
- tests/eval/（58 测试全绿）
- output/eval/（cost_log.jsonl、results_v1.jsonl、results_scored.jsonl、report_pilot.md）
- Dockerfile.deepeval、D:wheelhouse_linux（67 wheel）

### 遗留事项（下会话优先）

1. **全量 100 题基线**：agent 跑批（~3-4 小时）+ DeepEval 打分（~6-10 小时）→ report_v1.md；或用自研 judge 全量 + DeepEval 抽样校准
2. **路由偏差修复**：router 复杂度分类改进（complex 题误判 simple 24%）——W4 Planner 前置
3. **题目审查**：用户已确认整体质量较高暂不动；9 条 review/reject（世界观类多问混杂题）待处理；人工题 26 道（no_answer/hallucination_bait）待终审
4. **http 双路径**：pilot 仅 direct；http 路径（POST /chat + SSE）需启动 server 后补跑
5. **deepeval 镜像复用**：Dockerfile.deepeval + wheelhouse_linux 保留；冒烟/打分命令见上表
6. **firecrawl 搜索验证**：题目确认后执行（verify_benchmark_questions.py）
7. 未提交变更量大（见文件清单），下会话 review 后分批 commit

### 会话恢复指南（下会话）

1. 读本文件末尾（本段）+ README.md
2. 读 docs/specs/2026-08-15-eval-benchmark.md（v3）+ docs/plans/2026-08-15-eval-benchmark.md（v3）
3. 读 output/eval/report_pilot.md（试点基线）
4. 下一步：按「遗留事项」优先级推进（全量基线 / 路由修复 / 题目审查）

---

### opcode 网关并发并发实验

| workers | 现象 |
|---------|------|
| 4 | ~82s/条 稳定（4 指标串行 judge） |
| 8 | 无提速（~80s/条）——opencode 网关同火山有并发限制（约 4） |

### mimo-v2.5 judge 适配（关键）

- **推理模型 JSON 不稳定**：mimo-v2.5 带思考过程，DeepEval 指标内部要求 judge 输出 JSON，偶发 `invalid JSON`（8/13 条失败率）→ **VolcEngineLLM.generate 加 `json_mode=True`**（chat() 的 response_format=json_object）→ 单条冒烟 4 指标全过
- 8 workers 无提速 → 固定 4 workers
- 全量重打分（mimo-v2.5，json_mode，4 workers，4 指标统一 judge）进行中

### 待办

- 重打分完成 → 生成 mimo 版 report（统一 judge 基线），与火山版（results_scored_final_volc.jsonl）对比
- 题目修复 + 26 人工题接入（八类覆盖）

---

## W0 全量基线完成（2026-08-17，火山 judge 版 report_v1.md）

### 产出

`output/eval/report_v1.md` — Agent V1 全量 100 题基线（direct 模式，火山 judge 修复后）

| 指标 | 值 | 备注 |
|------|-----|------|
| overall | 0.784 | |
| answer_correctness | 0.748 | |
| faithfulness | 0.540 | 96/100（GEval 单次版；4 缺失） |
| citation_accuracy | 0.539 | 99/100 |
| tool_selection_accuracy | 0.990 | 规则修复后 |
| hallucination（无幻觉率） | 0.899 | **幻觉率 10.1%**（89/100，11 缺失） |
| task_completion | 0.990 | 100/100 |

- **最弱类别：事件**（correctness 0.433 / faithfulness 0.341 / 无幻觉率 0.667 / task 0.944）——与 pilot 发现的"事件题多事件综合弱"一致，Agent 层面待 W4 Planner 等改进
- 成本：judge 1887 次 ¥20.05（含多轮 buggy 重打分叠加），总计 ¥21.23
- 缺陷题：8 条 review/reject 未处置（用户决策保留）+ event_complex_003 空回答
- 11 条 hallucination / 4 条 faithfulness 缺失（火山并发断开 + 空回答），后续用 mimo-v2.5 补齐

### opencode 切换验证完成

- 宿主 `get_opencode_go_key()` 读 HKCU 注册表（用户指定来源）；Linux 容器无注册表 → 回退 `-e opencode_go_api=<注册表值>`（同一 key）
- 容器冒烟：mimo-v2.5 调用成功（16s/次含推理，252 in / 111 out）
- 155 tests passed（agent + eval）

---

## W0 完成收尾（2026-08-17，git 提交）

### 提交

```
7e6737b fix(agent): 路由复杂度分类修复（本地 64→92%，真实 93%，pilot 100%）
e8477ae refactor(agent): 模型层统一（deepseek-chat 下线 → 三 provider）
06d9293 feat(eval): W0 Evaluation Benchmark 建库（mimo 统一 judge 基线 overall 0.857）
```

未提交：`data/extractions/v3_seed_db_v2.json`（早期会话遗留，2 行改动，与本会话无关）。

### W0 交付清单

- `arknights_wiki/eval/`（9 模块）+ `tests/eval/`（70 tests）
- `benchmarks/arknights_bench/`（100 题 + 26 人工题 + 材料 + 审查清单）
- `output/eval/report_v1_mimo.md`（基线）+ 全部打分中间产物归档
- `scripts/`（生成/打分/冒烟/Docker）+ `Dockerfile.deepeval`
- 路线图 W0 标记 ✅

### 下一窗口

**W1 Observability / Tracing（Langfuse + OTel）**：每次 Agent 执行产出完整 Trace。
进入 W1 前需与用户确认 Langfuse 部署方式（本地 docker / 云端 / 仅本地文件导出）。

---

## 评估器测试补全 + rule_metrics 单一数据源统一（2026-08-17）

### 背景

用户要求审视评估器测试缺口。审计发现：
- **scoring.py 零测试**——DeepEvalScorer（faithfulness GEval/hallucination 转换/tool_selection 规则）所有改动无测试保护，全靠真实跑批暴露 bug
- **两份 rule_metrics 漂移**：scoring.py（score_runner 用）已改交集逻辑，judge.py（runner 用）仍是旧 strict 逻辑（`actual<=expected`，62/100 误伤）+ 无用 judged 参数——违反单一数据源
- scoring.py 内不一致：correctness 失败置 0.0，其它指标失败置 None（失败≠错误）

### 重构

- **rule_metrics 统一到 metrics.py**（纯函数单一数据源，交集语义，去 judged 参数）：judge.py/scoring.py 均从 metrics import；runner.py 调用去 judged 参数
- **hallucination_rate(raw_score)** 抽纯函数到 metrics.py（deepeval 原始分→幻觉率 0/1）
- scoring.py correctness 失败统一置 None（与其它指标一致）
- **tests/eval/test_scoring.py 新建**（fake deepeval 模块注入，宿主可测）：VolcEngineLLM.generate json_mode/max_retries/timeout 传递、score_answer metric_set 过滤、hallucination 转换、faithfulness 走 GEval(RETRIEVAL_CONTEXT)
- test_metrics.py +rule_metrics 全分支 + hallucination_rate + None 回归

### 验证

- eval 58→70 tests，全量 424 passed（3 个 stats 预存失败除外）
- 事件类重构生成器留档：scripts/generate_event_questions.py（题材约束，minimax-m3 思考块问题待解决——qwen 503、minimax 思考无闭合标记、deepseek-v4-flash 可用）

---

## mimo-v2.5 统一 judge 基线完成（2026-08-17，report_v1_mimo.md）

全量 100 题用 mimo-v2.5（opencode zen/go 网关）重新打分（4 指标统一 judge，json_mode 修复后 4 workers，~1h）。缺失极少（仅 event_complex_003 空回答 + 2 条 halluc judge 失败）。

### 两版 judge 基线对比

| 指标 | 火山版（report_v1） | mimo 版（report_v1_mimo） | 变化 |
|------|--------------------|--------------------------|------|
| overall | 0.784 | **0.857** | +0.073 |
| answer_correctness | 0.748 | 0.765 | +0.017 |
| faithfulness | 0.540 | **0.779** | +0.239 |
| citation_accuracy | 0.539 | **0.733** | +0.194 |
| 无幻觉率 | 0.899 | 0.887 | -0.012 |
| tool_selection | 0.990 | 0.990 | = |
| task_completion | 0.990 | 0.990 | = |

分析：faithfulness/citation 提升主因 (a) 火山版有 15 条缺失/失败拉低 (b) mimo 判分标准更稳。事件类仍最弱（correctness 0.417）。

### 关键经验

- **mimo-v2.5 推理模型 judge JSON 不稳定** → `json_mode=True`（response_format）根治
- **opencode 网关并发限制 ~4**（8 workers 无提速），固定 4 workers
- judge 调用 ~16-20s/次（含思考），落后于火山 50-60s
- 成本：judge 2817 次 ¥25.28（含多轮重打分及火山历史，mimo 单价为估算）
- 产物：`output/eval/results_scored.jsonl`（mimo 版）+ `report_v1_mimo.md`；火山版归档 `results_scored_final_volc.jsonl`

### 会话恢复指南（下会话）

1. 读本文件末尾（本段）+ README.md
2. 基线：`output/eval/report_v1_mimo.md`（mimo 统一 judge）
3. 下一步：评估器相关收尾（题目修复 / 26 人工题接入 / W0 提交）

---

## Judge 切换 opencode zen/go + mimo-v2.5（2026-08-17）

### 背景

用户指定：judge 从火山 Ark（deepseek-v4-flash-ga-260731）切换到 opencode zen/go 网关（https://opencode.ai/zen/go/v1）+ mimo-v2.5。Key 从 **HKCU 注册表** `opencode_go_api` 读取（进程环境同名 OPENCODE_GO_API 为另一 key，弃用）。

### mimo-v2.5 能力评估（实测）

| 能力项 | 结果 | 详情 |
|--------|------|------|
| JSON 判分 | ✅ | 矛盾识别准确（"源石能治愈矿石病" → score=0），JSON 可解析 |
| 长上下文 | ✅ | 4470 tokens 输入判分准确 |
| 延迟 | 8-15s/次 | 比火山（50-60s）快 5-6 倍 |
| 推理模型 | ⚠️ 注意 | 带 reasoning_content（思考过程），content 为纯回答不影响判分；judge max_tokens 需 ≥4096（思考占预算，短预算 finish=length 截断） |
| 模型可用 | ✅ | models 列表含 mimo-v2.5（另有 mimo-v2.5-pro / minimax-m3 / deepseek-v4-flash 等 26 个） |

### 代码变更（未提交）

```
arknights_wiki/eval/config.py   # +get_opencode_go_key(只读注册表)/get_opencode_go_base；judge 默认 mimo-v2.5
arknights_wiki/eval/llm.py      # chat() 改用 opencode 网关 key/base
arknights_wiki/eval/pricing.json# +mimo-v2.5 价格条目
arknights_wiki/eval/runner.py   # key 检查改 opencode_go_api
tests/eval/test_llm.py          # patch 对象同步 get_opencode_go_key
```

### 待办

- 当前火山打分（pwsh-22）完成后：合并指标 → report_v1.md（火山版基线）
- opencode 网关冒烟验证（容器内 judge 调用）
- 后续评估器工作（题目修复/人工题接入/重打分）走 mimo-v2.5；并发上限待实测（Cloudflare CDN 或高于火山 3-4）

---

## 打分 Bug 修复（2026-08-17，全量打分审计发现 3 处问题）

### 问题

全量 100 题打分完成后审计发现 3 处评测脚本缺陷（**非 Agent 行为问题**）：

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 1 | **hallucination 转换反转**：deepeval 4.x HallucinationMetric score 0 = 无幻觉（judge reason 实证 "aligns with all provided contexts...no contradictions"），原代码 `0.0 if score>=0.5 else 1.0` 完全反转 | scoring.py:148 | 幻觉率虚高至 92%（真值约 8%） |
| 2 | **tool_selection 规则过严**：`actual ⊆ expected` 要求 Agent 只用题目标注的固定工具，ReAct 自适应多调探索工具（search_dialogue 等）即判 0 | scoring.py:76 | 62/100 误判 0（修正后 0.990） |
| 3 | **faithfulness 大量假 0**：65/100 判 0 的根因是 judge LLM 调用失败（火山 "Server disconnected without sending a response"，5 次重试全败），非回答不忠实 | 打分运行期 | faithfulness 0.331 不可信，需重打分 |

### 修复

- scoring.py：hallucination 转换改为 `1.0 if score >= 0.5 else 0.0`，失败时 `None`（不再假 1.0）；tool_selection 改为 `actual ∩ expected 非空`（调了至少一个预期工具即正确）
- 重打分：`--metrics hallucination,faithfulness --workers 2`（降低并发减少火山断开）
- 旧打分归档 `results_scored_v1_buggy.jsonl`；合并脚本保留可信的 correctness/citation

### 验证

- tool_selection_accuracy：0.380 → **0.990**（纯规则重算，无需重打分）
- task_completion：0.990（唯一失败 = event_complex_003 空回答）

### 会话恢复指南（下会话）

1. 读本文件末尾（本段）
2. 重打分完成 → 合并指标 → 生成 report_v1.md（2 个 LLM 指标重跑中，works 2 workers）

---

## 题目审查诊断（2026-08-17，用户决策：暂不处理）

### 审查现状核对

benchmark 100 题中 **3 review + 5 reject = 8 条缺陷题**未处置，已混入全量打分基线：

| 题 | verdict | 根因 |
|----|---------|------|
| region_complex_006 | review | 答案未体现"对比"（仅分别陈述） |
| worldview_simple_002 | review | 材料末尾截断（不影响作答） |
| worldview_complex_003 | review | 答案含材料外知识（源石虫发酵体液镇痛剂） |
| worldview_complex_002/004/005/006/007 | reject | 材料 excerpt 尾部截断 + 答案编造材料外内容 + 多问混杂超范围（005 材料2 无凯尔希内容无法作答） |

**reject 根因一致**：材料 excerpt 截断 → LLM 生成答案时编造材料外知识（"源石虫""驱逐巨兽行动"等）。

### 文件问题

- **manual_draft.jsonl（26 道人工题：no_answer 13 + hallucination_bait 13）主目录丢失**——已从 `output/_w0_v2_archive/benchmarks/arknights_bench/manual_draft.jsonl` 恢复（2026-08-15 归档，内容完整）。W0 验收要求"无答案/易幻觉类必须人工构造"，恢复后待接入跑批/打分流程
- **categories.md 丢失**（分类文档，次要，可从 review_candidates.md 恢复结构）

### 用户决策（2026-08-17）

1. **缺陷题暂不处理**：保留 8 条在基准中，report_v1 标注为已知缺陷题
2. **打分跑完再说**：当前 DeepEval 打分（100 题）跑完出第一版 report_v1，修题后下轮重打对比

### 待办（下轮）

- 修复 8 条缺陷题（重提取材料全文 → 重生成 5 reject + 修订 3 review，成本 <¥0.1）
- 26 道人工题接入评测流程（补"无答案/易幻觉"两类覆盖）
- **打分性能**：当前 4min/条（16/100 用时 1h+），全量约 6h——下轮优化（judge 指标并行 / 响应缓存）

---

## 模型层统一同步（2026-08-17，DeepSeek 官方 deepseek-chat 下线）

### 背景

DeepSeek 官方 API 模型 `deepseek-chat` 已下线，替换为非思考模式 `deepseek-4-flash`；同时按用户要求给 agent 补充火山引擎模型选择（用火山 deepseek-v4-flash 跑全量 100 题基线）。

### 架构决策

- **统一模型层 `_get_model_config()`**（llm_client.py）：显式 provider 选择 `arknights_llm_provider`（volcengine|deepseek|minimax），默认优先级 **火山(arkcode_api) > DeepSeek官方(deepseek_api) > MiniMax(minimax_api)**
- **模型名**：火山 = `deepseek-v4-flash-ga-260731`（ark_agent_model/ark_api_base 可 env 覆盖，对齐 eval/config.py 模式）；DeepSeek 官方 = `deepseek-4-flash`（非思考模式）
- **硬编码清除**：router.py `_llm_intent_rewrite`、simple_search.py 回答生成原硬编码 `model="deepseek-chat"` → 改从 `_get_model_config()` 取（graph.py 走 chat_completion 本就跟随）
- **eval 侧同步**：runner.py `_estimate_llm_cost` 默认模型改从统一模型层惰性读取；pricing.json 新增 `deepseek-v4-flash-ga-260731` / `deepseek-4-flash` 价格条目（deepseek-chat 保留兼容历史 cost_log）；scripts/ 两个提取测试脚本 mock 模型名同步
- **runner 并发跑批**：`--workers N` 参数 + `_run_and_score` worker 单元（ThreadPoolExecutor），断点续跑保持（results_v1.jsonl 已存在 id 跳过）；旧 pilot 20 题结果归档为 results_v1_pilot_old.jsonl / results_scored_pilot_old.jsonl（旧路由+旧模型，已过时）

### 验证

- 火山 `deepseek-v4-flash-ga-260731` 真实调用冒烟通过（chat_completion 响应正常）
- 模型配置层三 provider 选择逻辑验证通过
- 测试：155 passed（agent + eval）；全量 412 passed（3 个 stats 预存失败除外）

### 全量 100 题跑批（火山 deepseek-v4-flash，6 workers 并发）

- 耗时：~30 min（pilot 20 题旧串行 ~80 min → 提速约 10 倍）
- **路由准确率 93/100**：52 complex 全对（修复生效）；7 个 simple→complex 保守误判（与诊断一致）
- **event_complex_003 空回答**：Agent 调 16 次工具无产出——事件时间线类综合检索弱（pilot 已发现的同类问题，真实基线暴露项）
- character_simple_007 / organization_simple_006 保守误判但回答质量良好（complex 路径多检索答对）
- 结果：`output/eval/results_v1.jsonl`（100 条 direct）；DeepEval 打分进行中 → `results_scored.jsonl` + report_v1.md

### 代码变更（未提交）

```
arknights_wiki/extraction/llm_client.py   # _get_model_config 重写（三 provider + 优先级）
arknights_wiki/agent/router.py            # LLM 兜底 model 从配置取
arknights_wiki/agent/simple_search.py     # 回答生成 model 从配置取
arknights_wiki/eval/runner.py             # +--workers 并发跑批 + _run_and_score 抽取
arknights_wiki/eval/pricing.json          # +2 模型价格条目
scripts/test_extraction.py / test_granularity.py  # mock 模型名同步
```

### 会话恢复指南（下会话）

1. 读本文件末尾（本段）+ README.md
2. 全量 100 题跑批结果：`output/eval/results_v1.jsonl`（火山 deepseek-v4-flash，6 workers 并发）
3. 下一步：DeepEval 打分（Docker deepeval-local 镜像已就绪）→ report_v1.md

---

## W0 路由修复（2026-08-17，benchmark 100 题驱动）

### 背景

devlog 遗留事项 #2：pilot 20 题 complex 预期题大量被 router 误判 simple（character_complex 11 题 8 条）。本次以全量 100 题诊断驱动修复。

### 诊断（基准：本地规则 64/100 = 64%）

| 误判类型 | 数量 | 根因 |
|----------|------|------|
| A. complex→simple | 12 | 双主体"分别/对比"结构未识别（意图被 chapter_summary/character_profile 抢占）；国家/概念实体提取不到 → 多实体信号失效 |
| B. simple→complex | 24 | "实体空 + 跨章"无条件兜底 complex（time_scope 默认即 cross_arc）；实体提取只覆盖角色/章节，国家/组织/概念题实体为空被误兜底 |

### 架构决策

- **Step 1（classify 层结构信号）**：
  - 多主体信号：≥2 实体 +（分别/各自/两者/二者/两人/双方/对比/异同/区别/差异/关系/关联/以及）→ complex
  - 多时间点：≥2 个不同年份 → complex
  - 事件枚举：`哪些.{0,12}(事件|事)` → complex（裸"哪些标志性影响"不触发）
  - 全面综合：≥2 实体 +（全部/所有/综合）→ complex
  - **兜底修正**："实体空 → complex" 增加 has_deep 前置条件（原无条件，误判 24 题）
  - deep_keywords 移除 '原因'（"直接原因是什么" 单事实查询实证误判；因果类由 causal_reasoning 意图路径覆盖）
- **Step 2（实体提取层）**：
  - **v3_wiki 世界观实体层**：factions(247) + locations(257) + concepts(1252) 文件名并入实体提取
  - **统一匹配算法 `_match_entities_ordered`**：长度降序（'源石外燃机' 优先于 '源石'）+ 区间占用（已匹配文本禁止子串重复匹配）+ 2 字前边界（仅角色层：'多利' 不匹配 '维多利亚'、'领袖' 不匹配 '的领袖'；世界观层不做边界——'使用源石' 中概念名常作宾语）
  - **跨层共享占用区间**：世界观层先匹配，角色层'多利'被'维多利亚'占用拦截
  - `_load_character_names` / `_load_worldbuilding_names` 加 lru_cache（路由层此前无缓存）
- **不修复项（保守方向误判 7 题，simple→complex）**：多检索不丢答案；根因多为 benchmark grounded 措辞（材料注入前置）或 concepts 库低质词条（'权力'、'游击队'），非路由逻辑缺陷
- **数据缺失记录**：'坍缩体' 无概念词条 → worldview_complex_010 本地规则 miss，真实路径由 LLM 兜底救回（判 complex）——补词条是数据层工作

### 验证指标（U-03 基线对比）

| 版本 | 本地规则（100 题） | 真实路径 | pilot 20 题（真实路径） |
|------|-------------------|----------|------------------------|
| 修复前 | 64% | — | 9/20 (45%) |
| 修复后 | **92%** | **93%** | **20/20 (100%)** |

- 剩余 8 题误判：1 题数据缺失（坍缩体词条）+ 7 题保守方向（simple→complex）
- 测试：tests/agent/test_router.py 28→50 tests（+22），全量 419 passed（3 个 test_stats_collector 预存失败，与本次无关，2026-06-17 起存在）
- 性能：本地路由 ~25ms/次；LLM 兜底路径 1.5-3s（网络主导，既有行为）；实体提取扩展无性能回归
- 本地命中率提升：实体提取增强后更多题本地直达，LLM 兜底调用显著减少

### 代码变更（未提交）

```
arknights_wiki/agent/router.py   # +_match_entities_ordered/_load_worldbuilding_names/lru_cache,
                                 #  classify 4 条新路径 + 兜底修正 + deep_keywords 调整
tests/agent/test_router.py       # +22 tests（匹配算法 6 + 实体提取 4 + 结构信号 9 + 补充 5）
```

### 遗留

- 全量 100 题 Agent 跑批基线（遗留事项 #1，3-4h）+ DeepEval 打分 → report_v1.md
- 题目审查（9 条 review/reject + 26 人工题）
- W4 Planner 前置后复杂度分类可进一步交给显式规划

### 会话恢复指南（下会话）

1. 读本文件末尾（本段）+ README.md
2. 下一步：全量 100 题 Agent 跑批基线 → report_v1.md（或先处理题目审查）

---

## W1 Observability / Tracing 完成（2026-08-18，Langfuse v4 本地 Docker + SDK 4.14）

### 用户决策

- **部署方式**：本地 Docker 部署 Langfuse v4（`docker/langfuse/docker-compose.yml`，6 容器：web+worker+postgres17+clickhouse25.12+redis7+minio）
- **埋点技术**：Langfuse Python SDK 4.14.4（`@observe` 装饰器 + `get_client()`，OTel 基础）
- headless 初始化：`LANGFUSE_INIT_*` 自动建组织/项目（arknights-wiki-main），免手动注册

### 架构决策

- **新包 `arknights_wiki/observability/`**：`client.py`（is_enabled 三键开关 + 懒加载 get_client + record_llm_usage）/ `decorators.py`（traced 可开关装饰器，关闭态原函数直通零开销）/ `schema.py`（节点名常量 + cost 复用 eval/pricing.json RMB 口径，预留 W2 retry/W4 planner/W5 critic 节点）
- **开关**：`LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASE_URL` 齐备且 `ARKNIGHTS_TRACING != "0"` 时启用；装饰时判断，关闭态返回原函数（保持身份、零侵入）
- **LLM 统一埋点**：`chat_completion` 加 `@traced(as_type="generation")`（llm_call 节点），函数内 `record_llm_usage` → `update_current_generation`（SDK v4 只有该 API 接受 usage/cost；`update_current_span` 无此参数——**踩坑**）
- **trace 根**：server.py executor 线程内 `start_as_current_observation`（OTel context 同线程传播，graph/simple_search 的 traced span 自然嵌套）；eval runner direct 模式每题一个根（metadata.benchmark_id）
- **v4 events_only 模式**：observations 存 ClickHouse events（非 postgres）；v2 observations 列表 API 为 lightweight view（不含 usage/cost/metadata），详情需查 ClickHouse `events_full.provided_*` 字段
- **成本日志路径可配置**：`ARKNIGHTS_COST_LOG` 环境变量覆盖（因 cost_log.jsonl 被进程锁，见遗留）

### 埋点清单（验收 trace 树实测）

```
simple:  chat_request → router → simple_search → retrieval → answer_generation
complex: chat_request → router → agent_call_model×N → (llm_call + tool_call×k) → synthesize → llm_call
```

### 冒烟与验收

- `scripts/trace_smoke.py`：最小链路冒烟（fake LLM，验证结构+usage/cost 写入）
- 真实问答（eval run_direct）：simple 42.9s / complex 131.4s（Agent 7 轮 28 次工具调用）；ClickHouse 确认 llm_call/answer_generation 的 model=deepseek-v4-flash-ga-260731、usage（如 {input:4755,output:813}）、cost（¥0.016）完整记录
- `scripts/trace_cost_summary.py`：ClickHouse 聚合成本 → `output/observability/cost_summary.md`（冒烟 4 traces ¥0.003120）
- 测试：tests/observability/ 16 tests（开关三态/traced no-op/cost 计算/LLM 埋点）；agent 核心 78 tests 无回归

### 部署踩坑（可复用）

1. **Docker Hub 直连不通** → daemon.json 配 registry-mirrors（docker.1ms.run / daocloud / dockerproxy.net）实测可用；Docker Desktop 需重启
2. **DATABASE_URL 默认硬编码 postgres:postgres**，改 POSTGRES_PASSWORD 后必须同步 DATABASE_URL
3. **S3 凭据必须与 MINIO_ROOT_USER/PASSWORD 一致**（默认 miniosecret 与自定义 root 密码不符 → "Failed to upload JSON to S3"）
4. **SDK v4 `update_current_span` 无 usage/cost 参数**，必须用 `update_current_generation`
5. **v2 observations 列表 API 无 usage/cost**，验证用 ClickHouse `events_full`

### 遗留

- **cost_log.jsonl 被进程锁**（WinError 5，psutil 无法定位持有者，疑似沙箱/杀软）：已用 ARKNIGHTS_COST_LOG 绕过，用户重启后需清理锁或删除文件
- `data/extractions/v3_seed_db_v2.json` 被某测试写入（git 显示 M，非 W1 改动，需确认是否合法）
- worker 每分钟任务日志偶发停顿（v4 dual write 正常，观察即可）

### 会话恢复指南（下会话）

1. 读本文件末尾（本段）+ README.md
2. Langfuse UI：http://localhost:3000（admin@arknights-wiki.local / ArknightsWiki2026!，或 headless key）
3. 启动 Langfuse：`cd docker/langfuse && docker compose up -d`
4. 开启 trace：设置 LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASE_URL（见 docker/langfuse/.env）
5. 下一步：W2 Failure Recovery 恢复链（依赖 W1 trace 可见性）

---

## Observability Dashboard 可视化页面（2026-08-18，ECharts）

### 功能

独立可视化服务（端口 8001，区别于 agent server 8000），数据直连 Langfuse ClickHouse（events_full 事件表）：
- **`arknights_wiki/observability/dashboard.py`**：FastAPI + clickhouse-connect（127.0.0.1:8123，凭据读 docker/langfuse/.env）
  - `GET /` dashboard.html；`/api/overview`（指标卡+按小时时间序列+节点类型分布+延迟直方图）；`/api/traces`（列表）；`/api/trace/{id}`（span_id/parent_span_id 建树）
- **`arknights_wiki/observability/static/dashboard.html`**：ECharts 5.5.1（本地 static/，免 CDN），深色监控面板风
  - 5 张指标卡（trace 数/总成本/平均延迟/P95/LLM 调用）；请求量&延迟时间序列；成本&Toke 趋势；节点类型饼图；延迟直方图；trace 列表表格（点击弹 ECharts 树图看完整 trace 树）
- 时间范围切换 6h/24h/7d + 手动刷新

### 启动

```bash
cd docker/langfuse && docker compose up -d        # 先起 Langfuse
python -m arknights_wiki.observability.dashboard  # 端口 8001
# 浏览器 http://127.0.0.1:8001
```

### 踩坑

- ClickHouse `toFloat64OrZero` 只接受 String 参数（数值用 `ifNull(avgOrNull(...), 0)`）
- dashboard.py 读 .env 的 parents[2]（项目根），写成 parents[3] 会读不到凭据（认证失败 516）
- 总成本需从 GENERATION 聚合（根节点无 provided_cost_details）

---

## Git 历史恢复 + W0/W1 首次提交（2026-08-18 收尾）

- **背景**：本地 `.git` 目录消失（对象库先损坏后目录丢失，疑似杀软/同步工具，未定位到确切原因）；工作区文件完整
- **远程仓库**：github.com/SilhouetteQA/Arknights-LLM-wiki（154 条提交，最后推送 2026-07-04，main + feature/langgraph-agent）
- **恢复**（零删除，用户否决 rm -rf 后采用）：`git remote add origin` + `git fetch origin` + 手动 `git update-ref refs/heads/main <sha>`（此环境 refs 写入不稳定，refs/remotes 不持久）+ `git reset --mixed`
- **提交**：`a5478a6` feat: W0 评测体系 + W1 Observability（覆盖 7-04 后全部本地工作，工作区干净）
- 提示：push 用 `git push -u origin main`（自动重建 origin/main 跟踪）；密钥（docker/langfuse/.env）已被 .gitignore 排除



## 会话收尾（2026-08-18 15:50）— W1 完成，交接 W2

### 本会话完成

- **W1 Observability/Tracing 全部落地**：Langfuse v4 Docker 部署、observability 包（可开关 traced 埋点 + usage/cost 精确记录）、ECharts Dashboard（8001 独立服务）、真实问答验收（莱茵十杰 ¥0.27 / 维多利亚 ¥0.33，trace 树完整）
- **前端多轮迭代**（用户反馈驱动）：任务/工具 log 刻度分布、trace 详情改为路由信息卡+节点时间线表
- **双问题实测**：验证 trace 过程与成本比对，发现 run_direct 成本估算低估 ~100 倍（只算 output）——W1 精确成本的价值
- **Git 历史找回**：回收站调查发现 11:13 被移走的完整 `.git`（160 条历史，含 W0 6 条本地提交）→ 替换恢复 → W1 提交 `aa6d9e9`（共 161 条）
- **回收站真相**：3061 项 `.git/objects` 删除 = git fetch/commit 时自动 repack 的正常内部行为（本环境将 unlink 重定向到回收站）；项目源码零删除

### 服务运行状态（下会话直接用）

| 服务 | 地址 | 状态 |
|------|------|------|
| Langfuse UI | http://localhost:3000（admin@arknights-wiki.local / ArknightsWiki2026!） | ✅ 6 容器 Up |
| Observability Dashboard | http://127.0.0.1:8001 | ✅ 运行中 |
| agent server（PRTS） | http://localhost:8000（未启动） | — |

### 会话恢复指南（下会话）

1. 读本文件末尾（本段）+ README.md
2. 若容器未运行：`cd docker/langfuse && docker compose up -d`
3. 开启 trace：设置 LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASE_URL（docker/langfuse/.env）
4. Dashboard：`python -m arknights_wiki.observability.dashboard`（8001）
5. **建议先 `git push -u origin main`**（161 条历史尚未同步远程，做异地备份）
6. **下一步 W2 Failure Recovery 恢复链**（依赖 W1 trace 可见性）：
   - Spec 要点：router/simple/graph 关键环节失败埋点（error/retry 字段已有部分）、异常检测与降级链、恢复重试策略
   - 相关文件：arknights_wiki/observability/schema.py（已预留 NODE_TYPE_RETRY）、graph.py 工具异常（已有 error 记录）
   - 建议先读 docs/specs/2026-08-18-w1-observability.md 的 W2 预留设计

---

## W2 Failure Recovery 完成（2026-08-18，恢复链全落地）

### 交付物

| 模块 | 说明 |
|------|------|
| `arknights_wiki/agent/resilience.py` | 恢复链核心（新）：OperationTimeoutError/BreakerOpenError/ResilienceError、ResilienceConfig（可环境变量覆盖）、with_timeout（线程池跨平台）、CircuitBreaker（closed/open/half_open 状态机，线程安全）、retry_call（指数退避）、execute_with_resilience（统一入口：主函数重试→fallback 链→ResilienceError） |
| `tools.py` | @tool 注册表新增 fallback 字段 → TOOL_FALLBACKS；4 个工具声明降级（get_entity_page/lookup_entity_index/semantic_search→search_wiki；get_chapter_summary→search_events） |
| `graph.py` | 工具执行经恢复链（timeout 30s / max_retries 2 / 退避 1-8s / breaker 阈值 5+60s 可 ARKNIGHTS_TOOL_* 覆盖）；同名工具共享熔断器；失败文本带 `[已降级: X]` 标注；trace metadata 加 retries/breaker_state/fallback_used/error + retry 子 span（NODE_TYPE_RETRY）；fallback 参数适配（_adapt_fallback_args） |
| `llm_client.py` | chat_completion 对 APIConnectionError/APITimeoutError/RateLimitError/InternalServerError 指数退避重试（默认 2 次，ARKNIGHTS_LLM_* 覆盖；4xx 不重试）；retries 入 llm_call metadata |
| `simple_search.py` | 回答生成改走 chat_completion 统一入口（顺带获得重试+埋点，删裸调 client） |
| `router.py` | _llm_intent_rewrite 补重试（网络/限流类，1 次） |
| `server_checkpoint.py` | checkpoint 工厂（新）：SqliteSaver 持久化 output/checkpoints/agent.sqlite（ARKNIGHTS_CHECKPOINT=0 或异常降级 MemorySaver） |
| `server.py` | complex 路径 build_agent_graph(checkpointer)，thread_id=sha1(question)[:16]，同问题重试断点续跑 |
| 测试 | 新增 36 个（resilience 20 + graph_resilience 7 + checkpoint 6 + llm_retry 3）；全量 483 passed / 3 failed（预存 stats，无新增） |
| 依赖 | pyproject agent extra + langgraph-checkpoint-sqlite>=2.0 |

### 验收（scripts/failure_demo.py，15/15 PASS）

1. **超时→重试→fallback**：timeout 0.05s 的 slow 函数 → retries=2 → fallback 结果，总耗时 0.18s（而非 1.5s）
2. **报错→重试→fallback**：get_entity_page 抛 ConnectionError → retries=2 → search_wiki 命中，文本 `[已降级: search_wiki]`
3. **熔断**：连续 3 次失败 → open → 短路（函数不执行）→ 抛 BreakerOpenError
4. **LLM 重试**：chat_completion 前 2 次 APIConnectionError → 第 3 次成功（调用 3 次）
5. **trace 可见性**（Langfuse ClickHouse 实证）：tool_call 节点 retries=2 / fallback_used=search_wiki / breaker_state=closed；retry 子 span node_type=retry；根 span benchmark_id=w2-acceptance 可过滤

### 回归（U-03）

- **10 题 character_complex 子集**（direct+mimo judge）：overall 0.936，correctness 0.91 / faithfulness 0.89 / 无幻觉率 0.90 / tool_selection 1.0
  vs 基线（report_v1_mimo.md 人物类 18 题）：correctness 0.906 / faithfulness 0.85 / 无幻觉率 0.889 → **无回落**
- 全量 pytest：483 passed（+73 新测试），3 failed 全为预存 stats 测试

### 踩坑记录

1. `update_current_span(name=...)` 在 SDK v4 不可靠 → 重试标记改用嵌套 `retry` 子 span（node_type 元数据）
2. fallback 工具签名不同 → 需 _adapt_fallback_args 参数映射（name→query 等）
3. checkpoint serde 不支持 MagicMock（msgpack 序列化失败）→ 测试用真实结构对象
4. 回归跑批需 --bench 指定 questions_draft.jsonl（默认路径文件名不匹配）+ 独立 --out 目录（results_v1.jsonl 断点续跑会跳过已有 id）

### 后续交接（W3 MCP Server）

- resilience/checkpoint 与 observability 解耦，MCP 工具执行可直接复用 execute_with_resilience
- checkpoint DB（output/checkpoints/agent.sqlite）已 gitignore 候选；确认后加入
- Langfuse 容器/Dashboard 运行状态见上一节（未变）

---

## W3 MCP Server 完成（2026-08-18，知识库标准协议化）

### 交付物

| 模块 | 说明 |
|------|------|
| `arknights_wiki/mcp_server/server.py` | MCPServer（mcp 2.0 SDK）5 个只读工具：search_entities / search_events / query_relationship / query_timeline / search_story；复用 retrieval.py Store；`python -m arknights_wiki.mcp_server.server` stdio 启动 |
| `arknights_wiki/mcp_server/client.py` | 同步封装（asyncio.run 每次调用生命周期）；W2 resilience 重试（ARKNIGHTS_MCP_TIMEOUT/MAX_RETRIES）；call_tool_traced 包 mcp_call span（mcp_tool/args/retries）；get_mcp_client 懒加载单例 |
| `tools.py` 双轨 | ARKNIGHTS_USE_MCP=1 时 TOOL_EXECUTORS 切 MCP 包装（工具名/签名不变，LLM 无感知）；映射表 8 工具→5 MCP 工具（semantic_search/get_chapter_summary 为近似映射）；MCP 失败回退内部函数并标注 |
| 测试 | 新增 23 个（server 单测 11 + client stdio 集成 6 + 双轨 6）；全量 506 passed（3 failed 预存 stats） |
| 依赖 | pyproject agent extra + mcp>=2.0 |

### 验收（全过）

1. **独立启动**：client list_tools 返回 5 工具，schema 完整
2. **真实问答**（ARKNIGHTS_USE_MCP=1）：complex 路径 14-19 次工具调用，回答正常产出
3. **trace 层级**：ClickHouse 实证 tool_call→mcp_call 父子完整（mcp_call=14/tool_call=14，parent 精确匹配）
4. **评测 A/B**（同 10 题 character_complex）：**MCP 路径 overall 0.967 vs 内部函数路径 0.936**（correctness 0.94/0.91，faithfulness 0.92/0.89，hallucination 1.0/0.9）→ 不降反升
5. **可开关**：未设 ARKNIGHTS_USE_MCP 行为与现状一致

### ⚠️ 重要修复（W2 遗留）

- **`resilience.with_timeout` 线程池不传播 OTel context**：工具经 with_timeout 在子线程执行时，子线程创建的 span（mcp_call）丢失父 context → 不落库。修复：`contextvars.copy_context()` + `ctx.run(fn, ...)` 传播 context（resilience.py）。修复后子线程 span 正确挂到调用方 trace
- 影响面：W2 的 tool_call 内 retry 子 span 在主线程创建不受影响；但所有经 with_timeout 的嵌套 span 均受益

### 性能观察

- MCP 路径每题延迟 ~110-180s（stdio 子进程每次调用启动 + 数据加载），vs 内部函数路径 ~120-180s（量级相近，MCP 略优/持平）
- 单次 MCP 工具调用 ~1-5s（子进程启动 + 检索）；若需提速可后续改长驻 session（范围外）

### 后续交接（W4 Planner）

- MCP server/client 为独立可复用层，W4 Planner 的任务执行器可直接调用 MCP 工具
- `ARKNIGHTS_USE_MCP=1` 已可作为默认部署开关（A/B 证明无质量损失）
- 遗留：`output/eval/w3_mcp/` 结果已提交；`data/extractions/v3_seed_db_v2.json` 若再被测试改写需还原

---

## W4 增强：任务级 ReAct 混合 + Planner 崩溃兜底（2026-08-19）

### 背景（用户自测暴露局限）

用户 5 问自测（scripts/w4_user_test.py，报告 output/eval/w4_user_test_report.md）显示：
- Planner 在开放综述/多跳探索题（Q2 各国政权 / Q4 莱茵十杰 / Q5 三大矿脉）弱于 ReAct
  （coverage 0.4-0.5 vs 0.8-0.95），Q5 直接崩溃（"让我继续检索"空答）
- 根因：任务图一次拆解固定执行，无反馈回路；LLM 规划波动大（同 Q5 重跑任务图质量差异显著）
- benchmark 10 题 character_complex 仍 Planner 优（0.915 vs 0.895）——结构明确题 Planner 擅长

### 两项增强（用户决策）

1. **任务级 ReAct 混合**（`ARKNIGHTS_PLANNER_TASK_REACT=1`）：
   - `graph.py` 新增 `_execute_task_react`（子 ReAct 循环：任务描述→LLM 自主多步检索，≤3 步，复用 chat_completion + _execute_tool_traced）+ `execute_task_react_graph`
   - 任务图的任务从"固定工具调用"升级为"检索子目标"，保留显式拆解 + 子任务探索灵活性

2. **Planner 崩溃兜底**（`ARKNIGHTS_PLANNER_FALLBACK=1` 默认开）：
   - `should_fallback_to_react(state)`：collected_docs 为空 或 弱证据（"未找到/无法/不足以"等信号）占比 ≥60% → 切 ReAct
   - `build_planner_graph` 加条件边：execute → (fallback → agent ⇄ tools 循环 → synthesize | continue → synthesize)
   - 保证开放题/知识库覆盖不足时仍有回答（Q5 类不再空答）

### 测试

- 新增 tests/agent/test_planner_fallback.py（6 个：空证据/弱证据/开关/图级 fallback 与跳过）；planner 系测试 32 passed
- 全量 pytest 待确认

### 自测重测（Q5，带 fallback）

- LLM 规划任务图质量好时（27 工具调用）fallback 不触发（continue），回答完整覆盖三大矿脉/乌萨斯枯竭/岁兽
- 弱证据场景由单测覆盖（图级验证 fallback → agent → synthesize 全链路）

---

## W4 收尾：三路对比结论 + 最终路由决策（2026-08-19 14:40）

### 三路对比（同环境，scripts/w4_three_mode_compare.py）

**Benchmark 10 题（六指标 judge）**：
| 模式 | overall | correctness | faithfulness | 工具选择 | 工具数 | 延迟 |
|---|---|---|---|---|---|---|
| **ReAct（默认）** | **0.942** | 0.92 | 0.91 | 1.0 | 18.8 | 80s |
| Planner | 0.903 | 0.84 | 0.85 | 1.0 | 8.0 | 68s |
| Planner+任务级ReAct | 0.758 | 0.82 | 0.81 | **0.2** | 9.4 | 159s |

**用户自测 5 问（质量评估，complex 题 Q2/Q4/Q5）**：Planner Q5 最优（fth 0.9/54s）、Q2 覆盖弱（0.75 但有 fallback）；任务级 ReAct Q2 覆盖好但延迟爆炸（452s/31 工具）、Q4 反而最差（0.4）。

### 最终决策（用户，质量优先）

1. **默认路由 = ReAct**（`ARKNIGHTS_AGENT_MODE` 默认 "react"）：server.py / runner.py 默认值已改
2. **Planner 保留为选项**（`ARKNIGHTS_AGENT_MODE=planner`：Plan→Execute→Synthesize + 崩溃自动切 ReAct）
3. **任务级 ReAct**（`ARKNIGHTS_PLANNER_TASK_REACT=1`）保留实验开关，默认关（tool_selection 0.2 结构性缺陷）
4. **ReAct 步数限制维持 8**（Q2 证明探索充分有价值）

### 其他收尾

- execute_task_graph / execute_task_react_graph 升级为**分层并行**（无依赖任务并行 ≤4 并发，contextvars 传播），测试 +3
- 产出：output/eval/w4_cmp_{react,planner,planner_task_react}/report_v1.md + w4_three_mode_report.md（已提交）

---

## W10 收尾：工程化总结 + 远程推送准备（2026-08-19 15:00-）

### 本次升级工程化总结（P0 全部完成）

| 阶段 | 交付 | 关键数据 |
|------|------|----------|
| W0 Evaluation | Benchmark 100 题 + mimo 统一 judge | 基线 overall 0.857 |
| W1 Observability | Langfuse trace + ECharts Dashboard | 全链路埋点，ClickHouse 直查 |
| W2 Failure Recovery | 六层恢复链 + checkpoint | 验收 15/15，10 题回归无回落 |
| W3 MCP Server | 5 只读工具标准协议化 + 双轨 | A/B：MCP 0.967 vs 内部 0.936 |
| W4 Planner | 显式规划 + 崩溃兜底 + 并行执行 | 三路对比：ReAct 0.942 / Planner 0.903 / task_react 0.758 |

最终路由决策（用户，质量优先）：默认 ReAct（ARKNIGHTS_AGENT_MODE=react），Planner 保留选项。

### 远程推送准备

- 本地 11 个未推送提交（W0-W4 全部工作，从 b6704a8 文档恢复历史后）
- 远程 origin/main 最新 9ec03d2（2026-07-04 历史），无远程独有提交，可快进 push
- 安全核对：无密钥被跟踪（.env 已 gitignore）、无 >5MB 大文件、checkpoints 已忽略
- 待用户确认 push 清单后 `git push -u origin main`

---

## Foundation Contract Cycle 1 开工（2026-09-10）

### 背景

用户提供 `06_双旗舰Agent_统一工程化路线.md`，要求把两个旗舰项目（Arknights LLM Wiki × Knowledge-Augmented Autonomous Coding Agent）的**公共工程层**以证据驱动方式统一。经 brainstorming 收敛后的关键判断：

- **不做 agent 层合并，不做单体仓库，不统一实现**。两仓领域语义不对称（Wiki 围绕 retrieval/memory/KG；Coding 另有 sandbox/GitHub/approval/durable execution），立即抽取公共实现会把项目专有字段固化为公共 API。
- 两仓共同存在同一类**语义债务**：把"没有用量/单价/成本信息"归一为 `0`，导致真实零成本、未知成本、估算成本无法区分。结构再统一，Trace/Evaluation/Dashboard 的结论也不可信。这就是 v0.1 唯一要解决的问题。
- Phase 1 只统一**跨边界契约**：两仓各留一份逐字节相同的 `agent_core.contracts` 镜像，Wiki 是唯一 canonical author，Coding 只能由 bundle 原子提升。

### 架构决策

| 决策 | 内容 | 来源 |
|------|------|------|
| 渐进式契约族抽取 | Phase 1（镜像 + 双仓验证）→ family extraction gate → Phase 2（独立 `agent-core` distribution）。抽取资格以 Contract Family 为单位，每个 family 需两个真实 Cycle，其中第二轮必须由真实 L2/L3 反馈驱动 | ADR-0001 |
| presence-aware 事实语义 | `Unknown is not Zero` / `Estimated is not Reported` / `USD is not CNY` / `Raw Cost is not Converted Cost`。禁止 `get(...,0)`、`or 0`、由 legacy total 反推组成项 | ADR-0002 |
| 非侵入旁路拓扑 | `Input → Legacy 业务路径 → 现有结果` ∥ `└→ Foundation Adapter → Validation Evidence`。Foundation 永不驱动主路径（不参与模型选择/路由/评分/成本报告/Dashboard/恢复/审批/副作用） | ADR-0002 |
| Contract Mode | `off`（零开销跳过）/ `observe`（只记录，任何失败不得改变业务结果）/ `strict`（仅验证命令失败用，非生产主路径） | ADR-0002 |
| ErrorEnvelope 定位 | 仅跨序列化/API/IPC/MCP/Adapter/Evidence 边界的 DTO；禁止 `raise ErrorEnvelope` / `except ErrorEnvelope` / 用它建内部 Result 模式 | ADR-0002 |
| 包白名单 | Phase 1 `agent_core/` 只允许 `__init__.py` + `contracts/**`；出现 provider/retry/checkpoint/Adapter/领域模型/配置即 Local Contract Gate 失败 | 母 Spec §3.1 |
| 状态账本 | `docs/specs/foundation-contract/execution-status-events.jsonl` append-only，是**唯一动态状态源**；子 Spec 内的状态是 genesis，不随进度改写；非法转换返回 `SPEC_STATUS_CONFLICT` | 母 Spec Appendix I |
| Candidate 冻结边界 | Spec 01–10 必须预先交付全部 post-freeze 能力；Spec 11 冻结 A 后不得再新增/修改任何 replay/sanitizer/smoke/invariance/publisher/coordinator/reducer/workflow 工具，缺工具只能 `SUPERSEDED` 回所属 Spec 形成 A2 | 母 Spec §16 / 执行索引 §5 |

### 产出文档

| 文件 | 说明 |
|------|------|
| `docs/specs/2026-09-10-dual-agent-foundation-contract-master-spec.md` | 母 Spec（2867 行）：Part I Foundation v0.1 可执行 / Part II Cycle 2 `FEEDBACK-BOUND` / Part III 抽取门禁 `GATE-DEFINED`；Appendix A 规范规则注册表 / B producer 注册表 / C 命令与环境矩阵 / D 产物 schema 与路径 / E 已知基线失败指纹 / F 文件级变更矩阵 / G 交接清单 / H 需求追溯 / I 状态治理 |
| `docs/specs/foundation-contract/00-execution-index.md` | 子 Spec 执行索引：Authority 分级、DAG、Candidate 冻结硬边界、状态归约链 |
| `docs/specs/foundation-contract/01–18-*.md` | 18 个工作单元执行投影 |
| `docs/adr/0001-progressive-contract-family-extraction.md` | ADR：渐进式契约族抽取 |
| `docs/adr/0002-foundation-fact-semantics-and-shadow-governance.md` | ADR：事实语义与旁路治理 |
| `docs/plans/2026-09-10-foundation-contract-cycle1-kickoff.md` | 非规范性开工准备：环境、基线快照、worktree 布局、全程红线、风险登记 |

### 环境与基线（2026-09-10 核验）

| 项 | Wiki | Coding |
|---|---|---|
| 仓库 | `D:\AI project\Arknights LLM Wiki` | `D:\AI project\Knowledge-Augmented Autonomous Coding Agent` |
| 分支 / worktree | `feature/foundation-contract` → `D:\AI project\_worktrees\foundation-contract\wiki` | 同名分支 → `...\_worktrees\foundation-contract\coding` |
| 分支起点 SHA | `bc954d3`（main 上的纯文档提交） | `08a8275` |
| 权威解释器 | `D:\CodexPython312\python.exe`（3.12.10 + pydantic 2.13.4） | 同左 |
| 权威测试命令 | `python -m pytest tests/`（**禁止**仓库根裸 `pytest`） | 同左 |
| 基线 | 552 collected / 542 PASS / 7 SKIP / 3 known-fail | 394 collected / 381 PASS / 13 SKIP / 0 FAIL |

Wiki 三条 known failure（`tests/test_stats_collector.py` 三个用例，根因 `stats.collector._get_raw_data` 假定 story JSON 顶层为对象而实际遇到列表）属 **DEFERRED，本 Cycle 禁止顺手修复**，仅允许 baseline comparator 按 Appendix E 指纹精确 allow。

> 开工环境坑（可复用）：本机 Bash 沙箱会拦截 git 对 `.git/refs/heads/<name>/…` 新子目录的创建，`git branch` / `git worktree add -b` **静默成功但不生成 ref**。可靠做法：先手工写 loose ref，再 `git pack-refs --all`。

### 执行进度（Spec 01–09 全部 COMPLETE）

账本已追加 35 条 append-only 事件，逐条含 evidence_refs。

| Spec | 内容 | 验证结果 |
|---|---|---|
| 01 | 基线冻结与治理骨架 | Wiki 542P/7S/3known、Coding 381P/13S/0F；producer 全覆盖（Wiki 3 in-scope/7 deferred，Coding 4/6）；`config/contracts/{producer-registry,known-test-baseline}.json` |
| 02 | Foundation 语义模型 | 174 cases / 6 conformance 文件；41 条规则落地；`agent_core` 根 `__init__` 仅 docstring |
| 03 | Schema / Descriptor / Hash / Mirror bundle | payload `sha256:21104487…`(32 文件)；Windows 与 Linux 容器产出**完全相同**的 payload/descriptor/schema-set/archive hash；DIVERGED 可检测；check 模式不写盘 |
| 04 | Evidence 契约与项目本地 sink | 218 cases；两仓各自 FileEvidenceSink，61 项检查（原子发布、并发唯一 event_id、`.tmp` 不当作证据、注入 I/O 失败 → `SinkFailure` + 失败计数）× |
| 05 | Wiki facts / mapping / runtime | `arknights_wiki/adapters/foundation/*`；50 cases；full suite 595P/7S/0F；源码扫描强制禁止零值默认；estimate→`source=estimated`，缺失/`tbd` 价格→`amount=null`+`source=unknown` 且保留 CNY 语境 |
| 06 | Coding facts / mapping / runtime / component provenance | `adapters/foundation/*` + `observation_ledger.py`；59 cases；sidecar 不持久化、不暴露公共契约、不跨项目依赖；客户端隔离；off 不分配 |
| 07 | Wiki 六个 producer observation seam | chat_completion / intent_rewrite / runner / judge / scoring / cost_log_summary；13+14 cases；full suite 622P/7S/0F；**顺带修出真实缺陷**：facts 未读 `prompt_tokens`/`completion_tokens`，真实 provider 响应恒为 unknown |
| 08 | Coding 七个 seam | openai_compat / langfuse_generation / normal / environment_error / error / sdk / clickhouse；12+9 cases；contract facts 绝不进 Langfuse `extra`/metadata；同一模型调用产出两条 producer evidence（agent.llm_usage + trace.generation_usage）属预期而非重复计数 |
| 09 | 共享 conformance + 项目契约测试 | `conformance/rules.py` 79 条 statement；`test_traceability` 6 例；两仓 sink 行为测试各 7 例；baseline comparator 各 10 例逐字节复现 Appendix E 三条 anchor 指纹；**Rule coverage 68 = 56 conformance + 6 项目 + 6 deferral**；conformance 224 cases 双仓；Wiki full 637P/10S/0F，Coding full 470P/13S/8F（8 条全为 git-ref 沙箱伪失败） |

### 契约与代码基线

| 项 | 值 |
|---|---|
| contract_version | `0.1.0`（lockstep，单一 Contract Set） |
| canonicalization_version | `1` |
| pydantic | `2.13.4` |
| Payload 文件数 / hash | 40 文件 / `sha256:df479f0c…`（两仓逐字节一致） |
| schema_set_hash | `sha256:d785d52d…` |
| Schema 清单 | Usage / Cost / CostSummary / ErrorEnvelope / FoundationObservation / EvidenceRecord |
| 规范规则总数 | 68（56 conformance + 6 项目落地 + 6 deferral） |
| 项目侧新增 | `arknights_wiki/adapters/foundation/`(5 文件)、`adapters/foundation/`(6 文件)、`config/contracts/`、`tests/contracts/`(5 文件) |

### 已知问题 / 遗留

1. **devlog 与 README 在本轮开工时未同步**（本次会话补记）：Foundation Contract 连续 5 天、9 个子 Spec 的进展此前只存在于账本与计划文档，违反 CLAUDE.md §3.3 / N-03。
2. **未推送远程**：Wiki `main` 领先 origin/main 17 个提交，`feature/foundation-contract` 领先 36 个；Coding 仓 `feature/foundation-contract` 无远程副本（Coding `main` 有 188 个提交从未推送，origin/main 仅初始导入）。
3. **Coding 8 条 git-ref 沙箱伪失败**：数量在 8–12 之间浮动，全部为环境诱发（`fatal: not a git repository` 类），非代码回归；已登记且在 baseline comparator 中排除。
4. **Wiki 三条 stats known failure** 仍为 `DEFERRED`，Cycle 1 内不修复。
5. **Spec 07/08 各一笔 deviation**：`adapters/foundation/runtime.py` 增加进程级 accessor 与少量窄 helper（不在原 Allowed Changes 内但为 seam 必需）；**Spec 09 一笔 deviation**：`evidence_sink.py` 的 `Path.resolve()` 目录穿越检查在 Windows 并发下存在竞态（实测 30–50 轮里 2–3 次误拒合法并发写，违反 `EVD-SINK-004`），改为 `os.path.abspath`（纯词法规范化），修后 50 轮 0 失败。三笔均已记入账本事件。
6. **Spec 10 尚未开工**：`pyproject.toml` 仍无 `pydantic==2.13.4` / `agent_core*` package discovery / package data；`scripts/contracts/`、`config/contracts/{smoke,replay}-v0.1.json`、`.github/workflows/`、`tests/contracts/test_packaging.py` 均不存在。

### 全程红线（违反即 Contract Defect）

```text
off == observe 四类不变性（Output / Decision / Side Effects / Legacy Telemetry）
```

- Legacy 主路径永不消费 Foundation 对象；未提交 Event 不得改写既有 Trace / cost log / report / Dashboard / 评分 / 路由 / 恢复 / 审批。
- facts extractor 禁止 `get(...,0)` / `or 0` / 由 legacy total 反推组成项。
- 只有 Wiki 写 canonical payload；Coding 只能由 bundle 原子提升，禁止手工修补镜像；Coding 不得保存子 Spec 副本 / DAG / 状态摘要 shadow copy。
- 账本 append-only；第一条事件必须是真实工程动作，不能记"文档已生成"。
- 证据发布只允许 allowlist 重建，禁止"先全量序列化再删敏感字段"。

### 会话恢复指南

1. 进入 worktree：`cd "D:\AI project\_worktrees\foundation-contract\wiki"`（Coding 同理）
2. 读 `docs/plans/2026-09-10-foundation-contract-cycle1-kickoff.md`（环境/基线/红线）+ 母 Spec §0/§1/§17 + 目标子 Spec 全文
3. 当前动态状态**只看** `docs/specs/foundation-contract/execution-status-events.jsonl`（不要看子 Spec 里的 genesis 状态）
4. 下一步：**Spec 10 Packaging and Local Contract CI**（唯一解锁的 `IMPLEMENTATION-READY` 单元，DAG 上 09 → 10 → 11）
5. Spec 16（Cycle 2）需真实 L2/L3 反馈；Spec 17/18 是门禁，只评估不实现

---

## Foundation Contract Spec 10：Packaging and Local Contract CI（2026-09-16）

### 背景与授权

Spec 09 `COMPLETE` 后，DAG 上唯一解锁的 `IMPLEMENTATION-READY` 单元是 Spec 10 —— **Candidate A 冻结前最后一个实施单元**。它必须在 A 冻结前把 Spec 12–15 需要的**全部**工具交付并开发验证（`GOV-FRZ-001`）；冻结后再缺工具只能把 A 标 `SUPERSEDED` 回所属 Spec 形成 A2（`GOV-FRZ-002`）。

分支：Wiki / Coding 各 `feature/foundation-contract-spec10`（自 `feature/foundation-contract` 分出）。

### 规范提取发现阻断 → 用户裁定

实施前用子代理对母 Spec §11–§17 + Appendix A–I + 子 Spec 10–15 做了规范性提取（产出 `output/spec10-normative-extraction-report.md`，418 行），识别出 **21 条冲突/缺口**，其中 3 条为 `SPEC_INCOMPLETE`（规范完全未定义必要语义），而母 Spec 明文规定这种情况**不得自行设计**：

| 缺口 | 内容 |
|---|---|
| G-02 | `replay-v0.1.json` 全文没有任何字段规范 |
| G-01 | `smoke-v0.1.json` 只有 YAML 伪字段，无 JSON 键名/必填性 |
| G-03 | pending suffix 要求"有 canonical hash + 记录目标持久化边界"，但 Event Schema 无对应字段、无路径格式 |

**用户裁定**（本次会话）：按**最小可行语义**实现 + 显式标注 provisional + 入账本 `SPEC_INCOMPLETE` 事件 + 留 Spec 11 Stage 0 校准。同时裁定 G-07（Wiki 三条登记 known failure 现已全 PASS，与规范硬写的 `542/7/3` 冲突）按规范自身的 `KNOWN_BASELINE_FAILURE_RESOLVED_UNEXPECTEDLY` 分支处理：**不使 gate 失败、标记需 review、不静默改基线**。

### 交付

| 产物 | Wiki | Coding | 说明 |
|---|---|---|---|
| `pyproject.toml` | ✅ | ✅ | 显式 `[build-system]`、`pydantic==2.13.4` 精确固定、显式 package discovery（含 `agent_core*`）、payload 非 Python 文件注册为 package data、`dev` extra 加 `build>=1.2` |
| `scripts/contracts/validate_local.py` | ✅ | ✅ | `--gate pr`（8 步）/ `candidate`（+全量回归+nodeid/指纹门+L1/L2/L3 证据闭合）/ `smoke`（§11.2 八项） |
| `scripts/contracts/replay_history.py` | ✅ | ✅ | allowlist 历史来源 + strict mapping + 四态分类 + sanitized corpus + 六类扫描 |
| `scripts/contracts/publish_evidence.py` | ✅ | ✅ | 冻结 CLI `--candidate <A_SHA> --release-version 0.1.0`；allowlist 构造（非 denylist）；Evidence Manifest 不含自身 hash 与 B SHA |
| `scripts/contracts/status_ledger.py` | ✅ | — | Event Schema / genesis / DAG+Authority / 8 条 reducer 规则 / append-only / pending suffix |
| `scripts/contracts/coordinate_cycle.py` | ✅ | — | 9 项校验；17 字段输出；**绝不**输出 `COMPLETE` |
| `scripts/contracts/finalize_cycle.py` | ✅ | — | hash 精确复制；`current.json` 仅 4 字段；不记 C 自身 SHA；**拒绝写真实账本** |
| `config/contracts/{smoke,replay}-v0.1.json` | ✅ | ✅ | L2/L3 run 预登记（provisional 键名） |
| `tests/contracts/test_packaging.py` | ✅ | ✅ | `FND-PKG-003` 落点：wheel / package-data / clean-env import |
| `tests/contracts/test_validate_local_tools.py` | ✅ | ✅ | 工具自测（扫描/junit/指纹/判定/子集/用法门） |
| `tests/contracts/test_status_ledger.py` | ✅ | — | 64 tests：Spec10:79 的 8 类用例正反双向 + genesis + 真实账本 + index 一致性 |
| `tests/contracts/test_cycle_tools.py` | ✅ | — | 57 tests：coordinator/finalizer 真实 git fixture + **真实 reducer** 集成 |
| `tests/contracts/test_replay_publish_tools.py` | ✅ | ✅ | 47 tests：manifest 校验 / 扫描器 / sanitize 不调 adapter / corpus 白名单 / publish 不变量 |
| `.github/workflows/contract-local.yml` | ✅ | ✅ | Windows L1 gate，无密钥、不跨仓、每条命令独立 step |
| `.github/workflows/contract-payload-linux.yml` | ✅ | ✅ | Linux 最小依赖 canonical hash job |
| `.github/workflows/contract-coordinate.yml` | ✅ | — | 仅 `workflow_dispatch`；固定 A/B SHA（机器校验 `^[0-9a-f]{40}$`）；只读 token |

### 关键实现决策

1. **脚本自举**：`python scripts/contracts/x.py` 的 `sys.path[0]` 是脚本目录，仓库根不在其中（只有 `python -m` 才加 CWD）→ 所有脚本顶部自行插入仓库根。**不得**依赖 editable install：两仓都提供顶层 `agent_core`，同一解释器无法同时可编辑安装两者。
2. **64 KiB 上限的语义**：它是**单条 Evidence 记录**的约束（`EVD-DATA-001` / D.4），不是整个 artifact 文件 → `.jsonl` 逐行判定、`events/*.json` 整文件判定、报告类文件不设尺寸门。首轮验收曾因把它当"单文件上限"而误报 214 KB 的 220 条语料文件。
3. **run manifest 的 `repository_commit: null` 约定**：该字段不在 §13.3 的预登记清单内，而 Candidate A 的 SHA 在 Spec 11 冻结前不可知、Spec 13/14 又禁止改 config → 约定 `null` = 运行期由 `AGENT_CONTRACT_COMMIT` 解析，**不自动推断 HEAD**。
4. **PR gate 的 package smoke 用 `pip install --target`** 而非新建 venv：装进临时 target、`sys.path` 前置、并断言 `agent_core.__file__` 确实位于 target 内（否则说明落回 editable 安装），再经 `importlib.resources` 读 descriptor 与 6 个 schema。
5. **`--gate candidate` / `--gate smoke` 设计为 fail-closed**：缺 Evidence Manifest / 缺 run-summary.json → 明确失败，不静默通过（无法验证 ≠ 通过）。

### Contract Payload 变更与双仓重新收敛

`FND-PKG-003` 原在 `DEFERRED_PAYLOAD_RULES`（defer 给 Spec 10）。本 Spec 交付 clean wheel smoke 后，它移出 deferral、登记进 `test_traceability.PROJECT_SCOPED_RULES`，落点在两仓 `tests/contracts/test_packaging.py`。Rule coverage 仍闭环：`68 = 56 conformance + 7 project + 5 deferred`。

两个 payload 文件（`conformance/rules.py`、`conformance/test_traceability.py`）变更 → 按 §12.7 重新生成确定性 bundle 并原子提升 Coding 镜像，两仓 payload 身份重新收敛为 `sha256:64049830…`（40 文件）。

### 验证基线（实测）

| 命令 | Wiki | Coding |
|---|---|---|
| `generate_schemas --check` | exit 0（6 schemas / 68 rules / `d785d52d`） | 同 |
| `verify_payload` | exit 0（40 files / `64049830`） | 同 |
| `pytest agent_core/contracts/conformance -q` | **224 passed** | **224 passed** |
| `pytest tests/contracts -q` | **311 passed / 3 skipped**（Spec 09 末为 102/3） | **195 passed**（Spec 09 末为 107） |
| `validate_local.py --gate pr` | **exit 0，8/8 步** | **exit 0，8/8 步** |
| `python -m build`（sdist→wheel） | exit 0，payload 完整 | exit 0 |
| `pytest tests/ -q`（全量） | **854 passed / 10 skipped / 0 failed**（Spec 09 末 637/10/0） | **527 passed / 13 skipped / 0 failed**（Spec 09 末 470/13/8 沙箱伪失败） |
| Wiki fixture 三条 | `status_ledger validate` 真实账本 exit 0（01–09 COMPLETE、10 NOT_STARTED、35 事件）；`coordinate_cycle` + `finalize_cycle` synthetic 全链路 exit 0，coordination `PASS / READY_FOR_FINALIZATION`，B→C diff 恰好 4 项 | — |

**独立复核**（不只依赖子代理自测）：空账本归约到正确 genesis（01 READY / 02–18 NOT_STARTED）；7 类非法事件（跳跃 / 重复 event_id / 缺前置 / VALIDATED 无 evidence / correction 缺 references / 非 canonical JSON / pending suffix hash 不符）全部 exit 1 + `SPEC_STATUS_CONFLICT`；5 个 workflow 的 YAML 结构与禁止事项（单 job、`contents: read`、timeout、无 `secrets`、无跨仓）全部通过；两仓 run manifest 与本仓 registry/币种自洽。

真实 L2 试跑（未绑定 Candidate，仅验证管线）：Wiki 220 条记录全部 `REPRODUCTION_RESTRICTED`（其中 120 条 mapping OBSERVED、100 条 `expected semantic correction`）；Coding 3 条全部 `LEGACY_DATA_INSUFFICIENT`（本仓盘上无 cost log/trace，只有 benchmark 用例定义）。`publish_evidence --dry-run` 两仓各 7 个产物、未写盘。

### 实施期新发现的规范缺口（G-22 – G-27）

| 编号 | 缺口 | 是否必须在 A 冻结前处理 |
|---|---|---|
| **G-22** | rule 4/8 的"互斥后继"无操作性定义；14 个 `reason_code` 从未映射到状态转换，5 个边界码（`FREEZE_BOUNDARY_REACHED`/`CANDIDATE_FROZEN`/`EVIDENCE_PUBLISHED`/`COORDINATION_PASSED`/`FINALIZATION_COMPLETE`）完全没有定义对应转换 | **是** |
| **G-26** | Spec10:109 冻结的 CLI 只有 `validate --ledger <path>`，但 coordinator 的 check 8 依赖扩展参数 `--spec-dir` / `--index`（并要求脚本存在于候选 A 树内） | **是** |
| G-23 | rule 7 只写"01–11 pre-freeze 允许 null"，从未写"12–18 必须非空" | 建议 |
| G-24 | A 被 `SUPERSEDED` 后已 `COMPLETE` 的 spec 如何回到工作态未定义 | 建议 |
| G-25 | 未定义 reducer 如何定位 genesis 来源（子 Spec 目录） | 建议 |
| G-27 | I.4 边界表与 rule 7 的"01–11 pre-freeze"只有隐式一致 | 建议 |

### Deviation 记录

| # | 位置 | 内容 | 理由 |
|---|---|---|---|
| 1 | `agent_core/contracts/conformance/{rules.py,test_traceability.py}`（两仓，经 bundle） | `FND-PKG-003` 移出 deferral → `PROJECT_SCOPED_RULES` | 该规则本就 defer 给 Spec 10 |
| 2 | `tests/contracts/test_test_baseline.py`（两仓） | 新增 `test_project_scoped_rules_have_real_landings` | `test_traceability` docstring 声称由它反向核验真实落点，Spec 09 未实现 |
| 3 | `.gitignore`（两仓） | 新增 `build/`、`dist/` | Spec 10 自身的 `python -m build` 与 `test_packaging.py` 会在源树产生它们 |
| 4 | `pyproject.toml`（两仓） | `dev` extra 增加 `build>=1.2` | G-19：`python -m build` 的前置模块未声明 |
| 5 | `scripts/contracts/*.py`（两仓全部脚本） | 顶部把仓库根插入 `sys.path` | 权威命令以脚本方式直跑，`sys.path[0]` 是脚本目录 |

### 残余验证缺口（不得冒充通过）

1. **Linux 跨平台 payload hash 未在本环境复跑**：Docker 守护进程未运行；WSL Ubuntu 是 Python 3.14.4 且无 pip/venv（与规范要求的 py3.12 + pydantic 2.13.4 不符）。Spec 03 已为**当时**的 payload 证明过 Windows≡Linux；本次变更只涉及两个纯 Python 源文件，hash 输入只含文件内容。复核由本 Spec 新建的 `contract-payload-linux.yml` 在 CI 完成。
2. **5 个 workflow 未在真实 GitHub runner 执行过**：只完成 YAML 解析、结构断言与命令一致性核对；action 未 pin SHA（仓库无既有约定）。
3. **`--gate candidate` / `--gate smoke` 当前预期失败**：Candidate-bound 证据（Spec 12–14）与 L3 `run-summary.json`（Spec 13）尚不存在；失败路径已验证为干净失败（明确 stderr + 退出码，无 traceback）。
4. **Wiki `output/eval/cost_log.jsonl` 是 tracked 且会被测试追加**（本会话中被追加 12 行）→ 即使同一 commit，L2 语料也非逐字节稳定。已用 per-source sha256 + `REPRODUCTION_RESTRICTED` 缓解；Spec 11/12 需决定是否在 A 前冻结来源快照。该文件的改动**不随本次提交**。

### 会话恢复指南

1. 进入 worktree：`cd "D:\AI project\_worktrees\foundation-contract\wiki"`（Coding 同理）
2. 读 `docs/plans/2026-09-16-foundation-contract-spec10-plan.md`（执行计划 + provisional 决策表）+ `...-spec10-handoff.md`（交接 + P0 校准清单）
3. 动态状态只看 `docs/specs/foundation-contract/execution-status-events.jsonl`
4. **下一步 = Spec 11（Candidate A Freeze / L1 / 全量回归）**，但 Stage 0 必须先完成 handoff §5 的 **P0 两项校准**（pending suffix 载体、两个 run manifest 的键名与 `repository_commit` 约定）与 **G-22 / G-26 的固化**，再冻结 A
5. Candidate A 的起点必须是两个 worktree 分支的 HEAD，**不是两仓 `main`**（两仓 main 都没有任何 Foundation 产物）

### 提交与推送（2026-09-16 收尾）

| 仓 | 分支 | 本地/远程 HEAD | 本次提交 |
|---|---|---|---|
| Wiki | `feature/foundation-contract-spec10` | `7372bbd`（已推送） | `72beba2` packaging + FND-PKG-003 落点 / `14cb22a` 本地契约工具与 run manifest / `be4cad2` CI workflows / `7372bbd` 文档+账本 |
| Wiki | `feature/foundation-contract` | `102de4c`（已推送，含 Spec 09 收尾） | — |
| Coding | `feature/foundation-contract-spec10` | `210be5f`（已推送） | `fbd79d9` packaging+镜像同步 / `e4df1b9` 工具与 manifest / `210be5f` CI workflows |
| Coding | `feature/foundation-contract` | `1798859`（已推送） | — |

**基线偏离登记（必须记录，不得静默复用）**：本次提交**排除了两个与本 Spec 无关的既有改动**——`data/extractions/v3_seed_db_v2.json`（早前会话遗留）与 `output/eval/cost_log.jsonl`（项目测试会追加写入，本会话中又被追加 12 行）。两者仍为 `M` 状态留在工作区。

**Wiki `main` 未推送（分叉，需决策）**：push 前 fetch 发现远程 `main` 已前进到 `f51f7c4`（含 `889747a fix: 修复 #2【知识纠错】试点二…` + 合并 PR #3），而本地 `main` 停在 `bc954d3`（Foundation 母 Spec 文档）。merge-base 为 `838ba4c`：**本地领先 1 个提交，远程领先 2 个提交**。按 G-04 禁止强制推送，推进 main 需要一次 merge，且会改动主工作区（`D:\AI project\Arknights LLM Wiki`，当前仍有上述 2 个未提交文件）并混入另一条 fix/issue-2 工作线 —— 属需用户裁定的仓库状态变更，故本轮**只推分支、不动 main**。

> 风险已排除：`bc954d3`（Foundation 母 Spec + 18 子 Spec + 2 ADR）已随两个 feature 分支进入远程（`git branch -r --contains bc954d3` 命中 `origin/feature/foundation-contract` 与 `...-spec10`），**没有任何工作只存在于本地**。

### 首次真实 CI 运行：3 个只在 runner 上暴露的缺陷（2026-09-16）

push 触发 workflow 后收到失败通知。**这批失败极有价值**：本地全绿，因为本机恰好具备 runner 上不存在的前提条件。三个缺陷逐个查明并修复，最终两仓 4 个 job 全部转绿。

| # | 现象 | 根因 | 修复 |
|---|---|---|---|
| 1 | Wiki gate 在 `[4/6] Project contract tests` 失败：`assert 'COMPLETE' in {'IN_PROGRESS','NOT_STARTED'}` | `test_status_ledger.py::TestRealLedger::test_real_ledger_reduces_cleanly` **写死了 Spec 10 的允许状态集**。我在跑完验收**之后**才追加 Spec 10 完成事件 → 本地测试看到的是旧账本 | 改为不硬编码进度：断言归约不冲突、每个 spec 状态在 `STATUSES` 闭集内、早期已 `COMPLETE` 的 Spec 01–09 仍为 COMPLETE、事件数与行数自洽。**教训：追加账本事件后必须重跑验收** |
| 2 | Coding gate 在 `[5/6]` 失败：`tools.approval.ApprovalError: git commit … Author identity unknown` | `tests/test_issue_agent.py::test_auto_approve_eligible_pushes` 会创建真实提交，而 GitHub runner **没有 git 身份**；本地已配置全局身份故通过 | workflow 内 `git config --global user.email/user.name`（环境前置条件，不引入凭据） |
| 3 | 修复 #2 后两仓 gate 在 `[5/6]` 失败：`UnicodeEncodeError: 'charmap' codec can't encode '\uff08'` | GitHub Actions **Windows runner 的 stdout 默认是 cp1252**，而 `validate_local.py` 的步骤名含全角括号（`payload allowlist（FND-PKG-001/002）`） | `validate_local.py` 与 `status_ledger.py` 入口 `reconfigure(encoding="utf-8")`（`replay_history` / `publish_evidence` / `coordinate_cycle` / `finalize_cycle` 早已有该保护） |
| 4 | 修复 #3 后 Wiki gate 仍在 `[5/6]` 失败：3 个测试报 `RuntimeError: 未设置 arkcode_api / deepseek_api / minimax_api` | `tests/agent/test_graph.py`（2 个）与 `test_router.py`（1 个）要求 provider 配置**存在**；本机有真实 key，CI 按规范**无密钥** | job 级提供**占位环境值**（非凭据）。对照实验：env 清空 → 恰好这 3 个失败（3 failed / 136 passed）；占位值 → 139 passed / 13.5s 无网络往返。若真有网络请求只会 401 失败，故占位值不可能掩盖真实网络依赖 |

同时发现并修复：Wiki gate 只装 `[dev]` 不足以覆盖 `--gate pr` 第 6 步的**契约相关回归子集**（`tests/agent/test_graph.py`、`test_checkpoint.py` 顶层 import `langgraph`，`numpy` 是 `vector_index.py` 顶层依赖）→ 按 Appendix C.4「本仓完整/测试依赖」改为 `[dev,agent]`（`faiss`/`sentence-transformers` 在 `vector_index.py` 内懒加载、`deepeval` 由测试注入 fake 模块，均不需要）。

### 最终 CI 状态（两仓全绿）

| 仓 | job | 结果 | 耗时 |
|---|---|---|---|
| Wiki | Contract Local Gate (windows-latest, py3.12) | **success** | 5m40s |
| Wiki | Contract Canonical Payload Hash (ubuntu-latest) | **success** | 21s |
| Coding | Contract Local Gate (windows-latest, py3.12) | **success** | 2m35s |
| Coding | Contract Canonical Payload Hash (ubuntu-latest) | **success** | 19s |

**因此 Spec 10 交接文档 §7 的残余缺口 #1（Linux 跨平台 payload hash 未复跑）与 #2（workflow 未在真实 runner 执行过）已经关闭**：Linux job 用同一共享实现在 `ubuntu-latest` 上重算并比较通过，两仓 payload 均为 `sha256:64049830…`。

### Wiki `main` 已按用户裁定 (a) 合并推送

`git merge --no-ff origin/main` → `c2d39c5`（合入远程 `889747a fix/issue-2` + 合并 PR #3 与本仓 `bc954d3` Foundation 母 Spec 文档）。远端那 2 个提交只动 `data/extractions/**`，与主工作区两个脏文件不重叠，merge 无冲突。已 push，本地=远程=`c2d39c5`。

> 推送期间遇到 `github.com`（20.205.243.166）边缘 IP 不可达（`api.github.com` 正常、SSH-over-443 可连通但本机无授权密钥），多次重试后网络自行恢复。本地提交全程安全。

---

## Spec 11 Stage 0 准备工作完成（2026-09-16）

### 交付

| 产物 | 说明 |
|---|---|
| `docs/plans/2026-09-16-foundation-contract-spec11-stage0-calibration.md` | **核心**：把 Spec 10 的全部 provisional 发明物逐条写成"已冻结 / 保留为开放"，含冻结语义表、守卫、Spec 11 Stage 0 行动清单、机器可验证命令 |
| `scripts/contracts/status_ledger.py` | 新增 `PENDING_JSONL_FILENAME` / `PENDING_ENVELOPE_FILENAME` / `canonical_pending_paths()`（G-03 载体命名冻结，供 Spec 12/13 工具引用）；`REASON_BY_TRANSITION` 与 CLI 表加冻结标记 |
| `tests/contracts/test_status_ledger.py` | 新增 `TestFrozenSurface`（8 个测试）：用**字面量表**钉住 G-22 耦合表、G-26 CLI 表面、G-03 载体命名、G-01/G-02 manifest 键集 |
| `tests/contracts/test_replay_publish_tools.py`（Coding） | 独立钉住 manifest 键集（Coding 无 status_ledger，故在其唯一位置守卫） |

### 三项"必须冻结"的语义（Stage 0 结论）

1. **G-22 reason_code ↔ 转换耦合表**：`NOT_STARTED→READY`=`PREREQUISITES_SATISFIED`；`READY→IN_PROGRESS`=`EXECUTION_STARTED`；`IN_PROGRESS→VALIDATED`∈{VALIDATION_PASSED, FREEZE_BOUNDARY_REACHED, CANDIDATE_FROZEN, EVIDENCE_PUBLISHED, COORDINATION_PASSED}；`VALIDATED→COMPLETE`∈{ACCEPTANCE_COMPLETE, 上述 4 个边界码, FINALIZATION_COMPLETE}；`COMPLETE→IN_PROGRESS`=`STATUS_CORRECTION`（references 必填）。BLOCK/UNBLOCK/SUPERSEDE 分支运行时判定（解除 BLOCKED 必须回到进入前的状态；A2 重启为 `SUPERSEDED→IN_PROGRESS`+`CANDIDATE_SUPERSEDED`）。附加不变式：14 个理由码必须全部可用、`from==to` 非法、不用 last-line-wins。
2. **G-26 reducer CLI 表面**：`validate` 自定义 flag 恰为 `--ledger`（必填）/`--pending-jsonl`/`--pending-envelope`/`--spec-dir`/`--index`/`--self-commit`/`--json`。coordinator 的 check 8 以 `cwd=A树` + `--spec-dir` + `--index` 调用，并要求 reducer 脚本存在于候选 A 内。
3. **G-03 pending suffix 载体**：与账本同目录的 `execution-status-events.pending.jsonl` + `.pending.json`（envelope 字段闭集 5 个、`pending_version="1"`、`target_boundary∈{candidate_a,evidence_b_wiki,finalization_c_wiki}`、`suffix_hash` 为 jsonl 原始字节 sha256 且 envelope 不自 hash）。下一持久化边界必须原样 append。

### 未冻结 / 留给后续

`contract-coordinate.yml` 真实执行（Spec 15）· action pin SHA（可选）· 母 Spec 中"未定义语义"本身（本文档只是校准记录，未改母 Spec；建议 Spec 16 或母 Spec 回修补全）· Wiki 3 个隐含依赖 provider 配置的测试（项目测试卫生，用 CI 占位值绕过存在性检查）。

### 验证

`tests/contracts`：Wiki **319 passed / 3 skipped**（新增 8 个冻结测试）；Coding **196 passed**（新增 1 个）。真实账本（41 事件）归约仍 exit 0。`--gate pr` 8/8 通过。

---

## Spec 11 完成：Candidate A 已冻结（2026-09-16）

### 交付

| 产物 | 说明 |
|---|---|
| **A_wiki `b726c09` / A_coding `c8e06e5`** | 两个固定候选提交，取自 `feature/foundation-contract-spec10` 的 HEAD（**不是 `main`**，两仓 main 都没有 Foundation 产物）。此后验证一律用 SHA，不用分支名 |
| **Cycle 分支 `contract-cycle/foundation-0.1.0-cycle-1`** | 在 A 处创建，作为 A/B/C 的唯一承载分支。母 Spec §16.3 要求 `diff(A,B) ⊆ evidence publication allowlist`，故 README/devlog 等非 allowlist 提交必须留在 feature 分支，不得插入 A→B 之间 |
| `docs/specs/foundation-contract/execution-status-events.jsonl` | 追加 Spec 11 `NOT_STARTED→READY→IN_PROGRESS` 两条 canonical 事件（共 43 条；`candidate_commit=null`，rule 7 对 Spec 01–11 的 pre-freeze 事件允许 null） |
| `docs/specs/foundation-contract/execution-status-events.pending.{jsonl,json}` | **受控 staging，故意不提交**：Spec 11 `IN_PROGRESS→VALIDATED`（`FREEZE_BOUNDARY_REACHED`）+ `VALIDATED→COMPLETE`（`CANDIDATE_FROZEN`），两条均绑定 `candidate_commit=A_wiki`；envelope `target_boundary=candidate_a`、`event_count=2`、`suffix_hash=sha256:bd5e2dcf…` |
| 校准记录 §3.1 + §9 | G-20 逐字节复核记录 + Spec 11 pre-freeze inventory（契约身份、仓库本地身份、工具链、工作树归属） |

### 为什么 boundary 事件在 pending suffix 而不是 canonical 账本

`FREEZE_BOUNDARY_REACHED` / `CANDIDATE_FROZEN` 属于"无论 spec 为何都必须绑定非空 `candidate_commit`"的 5 个边界/发布类理由码（G-23 收严），而 A 冻结前这个 SHA 还不存在 → 只能等 A 形成后写进 controlled pending suffix（母 Spec §16.2 正是这样规定的）。Spec 14 必须把该 suffix **逐字节** append 到 B_wiki 账本，否则 Spec 12/13 依赖它的证据无效。

### 正式验证（在两个 A 的干净 detached checkout 上重跑，不引用 Spec 09/10 开发期 PASS）

| L1 步骤 | Wiki A `b726c09` | Coding A `c8e06e5` |
|---|---|---|
| `generate_schemas --check` | exit 0（6 schemas / 68 rules） | exit 0 |
| `verify_payload` | exit 0（40 文件 / `sha256:64049830…`） | exit 0（同 hash） |
| `pytest agent_core/contracts/conformance` | **224 passed** | **224 passed** |
| `pytest tests/contracts` | **319 passed / 3 skipped** | **196 passed** |
| `validate_local --gate pr` | exit 0（**8/8**） | exit 0（**8/8**） |
| `python -m build` | exit 0（sdist + wheel，wheel 内 payload 完整） | exit 0（sdist + wheel） |
| `pytest tests/`（全量回归） | **864 passed / 10 skipped / 0 failed** | **577 passed / 13 skipped / 0 failed** |

**G-07 口径**：Wiki 规范基线登记 3 条 known failure（`tests/test_stats_collector.py`），实测**全部 PASS** → 按 `KNOWN_BASELINE_FAILURE_RESOLVED_UNEXPECTEDLY` 处理：**不算 gate 失败**、标记需 review、基线文件不改写。Coding 期望 `PASS`，实测 `PASS`。

**Suffix 校验不是空转**：三个负例均按预期 exit 1 + `SPEC_STATUS_CONFLICT` —— 篡改 `suffix_hash` → `PENDING_2_SUFFIX_HASH_MISMATCH`；envelope 与事件 `candidate_commit` 不符 → `PENDING_3_CANDIDATE_MISMATCH`；`event_count` 不符 → `PENDING_2_EVENT_COUNT_MISMATCH`。

### G-20 逐字节复核（本轮新发现，已按冻结语义接受）

Spec 10 的提取报告只记了 descriptor 一处磁盘字节差异。本轮对**全部 40 个 payload 文件**做了逐字节 + canonical 双重比对：

```text
磁盘字节不同        7  （descriptor + 全部 6 个 schema）
canonical 内容不同   0  → payload_hash / descriptor_hash / schema_set_hash 两仓完全一致
差异量              每文件恰 1 字节：Wiki 结尾多一个 LF（1797 vs 1796）
```

**根因定位到行**：`tooling/generate_schemas.py:182,187` 写快照用 `canonical_json_dumps(x) + "\n"`（多一个装饰性 LF）；`bundle.py:143` 落盘的是 `file_canonical_content()` 的结果 —— 该函数对 `.json` 重新序列化为 canonical JSON（无尾随 LF），对其它文本只做换行规范化。所以 **Coding 收到的就是 canonical 形态，Wiki 自己生成的快照反而多一字节**；`--check` 比较的是 `canonical_json_dumps(...)`，对该字节不敏感，故两仓都通过。

**本 Cycle 不修的理由**（写入校准记录 §3.1）：① 无任何消费者按原始字节比较两仓（`coordinate_cycle` 只比 `payload_hash`/`payload_descriptor_hash`/`schema_set_hash`；本地 gate 按 G-06 不读另一仓）；② 要同时满足"逐字节相同"与"生成器幂等"必须改 payload 内的 `generate_schemas.py` 或 `bundle.py`，会**变更 `contract_payload_hash`**，使账本中已 `COMPLETE` 的 Spec 09/10 事件所引用的 `sha256:64049830…` 变成悬空身份（append-only 账本无法回改）；③ 只重写那 7 个 JSON 快照虽 hash 不变，却会让提交状态与生成器输出不一致（下次 `--write` 即再分叉），形成"看似逐字节相同、实则随时会漂"的假象。**结论：按已冻结的 G-20 语义接受，记为显式残留，建议随下一个 payload 版本修。**

### 工作树归属（Freeze Procedure 步骤 1）

Wiki 的 2 个长期 `M` 文件明确归属为运行期/数据改动、**不纳入 A**（均未提交，天然不进 A）：`output/eval/cost_log.jsonl`（`+42`，项目测试会追加）、`data/extractions/v3_seed_db_v2.json`（`+1/−1`，2026-08-18 起未提交）。Coding 工作树**完全干净**，无未跟踪文件。

---

## Spec 12 完成 / Spec 13 阻断（2026-09-16）

### 先做了结构修正：cycle worktree

Spec 12 必须绑定 **A 的已提交 blob** 的 sha256，而被长期改写的 `output/eval/cost_log.jsonl` 在工作区里与提交内容不同（`9f4bd645…` 3479 行 vs `88108f88…` 3521 行）。因此在 `_worktrees/foundation-contract/cycle/{wiki,coding}` 新建了**检出在 cycle 分支上的 pristine worktree**（`git status` 0 改动）：
- Spec 12/13 从这里跑（Candidate-bound、可复现）；
- Spec 14 也将在这里形成 B；
- `candidate_a` pending suffix 一并**移到 cycle worktree**（与 canonical ledger 同目录，G-03），feature worktree 的副本已删除以避免两份 staging 歧义。

### Spec 12（L2 Historical Replay）= `COMPLETE`

命令（受控手动，非 workflow，G-06）：`AGENT_CONTRACT_MODE=strict` + `AGENT_CONTRACT_RUN_ID=<manifest run_id>` + `AGENT_CONTRACT_COMMIT=<A SHA>` + `python scripts/contracts/replay_history.py --run-manifest config/contracts/replay-v0.1.json`。

| | Wiki | Coding |
|---|---|---|
| result | `PASS` | `PASS` |
| 记录 / 来源 | 220 / 2 | 3 / 3 |
| status | `REPRODUCTION_RESTRICTED` ×220 | `LEGACY_DATA_INSUFFICIENT` ×3 |
| mapping_outcome | `OBSERVED` ×220 | `LEGACY_DATA_INSUFFICIENT` ×3 |
| difference_class | `NONE` ×120 + `expected semantic correction` ×100 | `legacy insufficiency` ×3 |
| adapter_defects | 0 | 0 |
| scan.failed / findings | 0 / `[]` | 0 / `[]` |
| raw retention | `…RETAINED_IN_CONTROLLED_SOURCE_LOCATION`，未进 contract staging、未进 Git | 同 |

绑定核验：`repository_commit` = A 且 `repository_commit_matches_head=True`（`repository_commit_source=AGENT_CONTRACT_COMMIT`）、`contract_payload_hash` = `64049830…` 且 `payload_hash_verified=True`。语料 record 形状稳定（8 键），只有 presence-aware 最小事实——**无 raw prompt / response / code / diff / path / credential**。

这也**顺带结清了校准记录 §5 的悬置问题**：真实执行确认 Wiki 220 条全 `REPRODUCTION_RESTRICTED`、Coding 3 条 `LEGACY_DATA_INSUFFICIENT`，因此"管线跑通但数据不足"作为 Cycle 1 的 L2 结论被接受（补造语料会超出 v0.1 范围且需改冻结的 config）。

**PR gate 第 [7] 步不再空转**：两仓 cycle worktree 上 `--gate pr` 均 exit 0（8/8），且 `evidence publication safety scan — 2 文件无命中`（此前 staging 为空时是 vacuous）。

### Spec 13（L3 Fresh Smoke）= `BLOCKED`

准备阶段即发现**三个独立、可复现的 Candidate A 缺陷**，Spec 13 无法闭合：

| 编号 | 缺陷 | 决定性证据 |
|---|---|---|
| **B1** | gate 第 [8] 步要求 `<evidence_root>/<run_id>/run-summary.json`（G-04 冻结 8 键），**两仓无任何组件写它** | 全仓扫描：Wiki 命中 5 文件、Coding 1 文件，**全部是文档 + 要求它的 gate 本身**；A 的 runtime 8 键中只原生暴露 `sink_failure_count`，`rejected_records`/`actual_calls`/`actual_tokens`/`duration_seconds`/`producer_coverage`/`known_cost_components`/`unknown_cost_components` 均无 accessor。→ 无论业务运行多成功，gate 永远无法通过 |
| **B2** | G-13（Spec 11 Stage 0 冻结）把 `--gate smoke` 定为"只校验已完成的 run"，业务运行交给"受控手动命令"——**该命令在 A 中不存在** | `contract-local.yml` 末尾记录的 L2/L3 命令只有 validate-only 的 smoke 调用自身；`gate_smoke()` 只读 `events/` + `run-summary.json`，不驱动任何业务路径 |
| **B3** | smoke manifest 预登记 `case_ids=[character_complex_002]` 却**无法被选中** | `eval/runner.py` 只有 `--bench/--out/--mode/--limit/--category/--server/--dry-run/--no-judge/--workers`；默认 bench `benchmarks/arknights_bench/questions.jsonl` **不存在**；草稿 bench 里该 case 在第 2 位，`--limit 1` 会跑成 `character_complex_001` |

Spec 13 的 No-implementation Boundary 禁止热修 smoke harness / Adapter / sink / config / tests / 业务代码 / workflow，其 Stop Conditions（"需要修改工具、接线或 tests"、"Evidence 无法落盘或 run 不闭合"）已触发；Spec 11 的 Stop Conditions 也早已列明"任一 post-freeze 工具缺失"。

**处置（严格按规范，不自行发明）**：按 Index §5 与 `GOV-FRZ-002`，post-freeze 工具缺失/错误 ⇒ **A `SUPERSEDED`，回到拥有该文件的 pre-freeze Spec（Spec 10 —— 它拥有 post-freeze 工具集与 smoke harness，且其验收证据曾声称"Spec 12–15 零剩余工具工作"）形成 A2**。

**本轮未越界**：没有修改任何实现文件、没有执行业务运行、没有改 config/tests/workflow ⇒ 无需回退。Spec 12 的 L2 staging 与本结论无关，仍然有效。

**待批准**：A2 需要写新工具（L3 驱动 + `run-summary` 生产者 + case 选择），属项目规则 **N-04（迁移/架构变更需用户同意）** 范畴，因此停在这里等用户裁定，未自行开工。

### 账本与分支状态

- canonical 账本仍 **43 条**（A 内的 canonical prefix 未动）。
- `candidate_a` pending suffix 现为 **9 条**：Spec 11 ×2、Spec 12 ×4、Spec 13 ×3（`NOT_STARTED→READY→IN_PROGRESS→BLOCKED(SPEC_INCOMPLETE)`）；`suffix_hash` = `sha256:67f60a19…`。
- 归约结果：Spec 01–12 `COMPLETE`、**Spec 13 `BLOCKED`**、14–18 `NOT_STARTED`（14 正确地**未**解锁）。
- 已推送：Wiki `contract-cycle/foundation-0.1.0-cycle-1`（`b726c09`）、Wiki `feature/foundation-contract-spec10`（`9847101`）、Coding `contract-cycle/foundation-0.1.0-cycle-1`（`c8e06e5`）。

---

## A2 决策与实施（2026-09-16）

### 决策

用户按 **N-04** 批准走规范路径：**A `SUPERSEDED` → 回到拥有缺陷的 pre-freeze Spec（Spec 10）修工具 → 形成 A2**。理由链：Spec 13 的 Stop Conditions 已触发（需改工具/Evidence 无法闭合），Index §5 与 `GOV-FRZ-002` 规定 post-freeze 工具缺失/错误必须 SUPERSEDED，Spec 13 自身禁止热修。用户同时否决了"最小可行 + provisional 覆盖冻结规则"与"停在 BLOCKED"两个选项。

### A2 的关键有利事实：payload 不变

`scripts/contracts/**` 与两仓业务代码（`arknights_wiki/**`、`adapters/**`、`benchmark/**`、`tools/**`）**都不在 40 文件 Contract Payload 内**（payload 只含 `agent_core/__init__.py` + `agent_core/contracts/**`）。因此 A2 是**纯工具级修复**：

```text
contract_version       0.1.0        （不变）
contract_payload_hash  sha256:64049830…  （不变）
descriptor / schema_set hash              （不变）
```

⇒ Spec 09/10 的契约身份与 rule coverage 证据**继续有效**，不需要版本升级，`agent_core.contracts` 两仓镜像也不动。

### A2 变更范围（非 payload）

1. **新增 `scripts/contracts/run_l3_smoke.py`**（两仓各一份）：受控 L3 驱动 —— 校验 manifest（与 `gate_smoke` 同键集）、强制 `mode=observe` 与 `run_id` 一致、从 `--case-source` 解析并**强制**满足预登记 `case_ids`（缺失即 exit 2 + `SPEC_INCOMPLETE`）、子进程驱动真实业务路径、测量时长、按 `RUN_SUMMARY_KEYS` 从**durable evidence** 聚合出 `<evidence_root>/<run_id>/run-summary.json`。
2. **sink 失败落盘**（`*/adapters/foundation/evidence_sink.py`）：业务路径跑在子进程里，进程内 `sink_failure_count` 读不到 ⇒ 让 sink 在 emit 失败时追加 run 级失败标记文件；缺失即 0 次失败。`run-summary` 的 `sink_failure_count` / `rejected_records` 由此可证据化。
3. **case 选择（B3）**：由 driver 强制预登记 `case_ids`，并把投影出的单 case bench 放进受控 staging —— **不需要改动 runner 的业务代码或已冻结的 `config/`**。
4. **workflow 注释**：按 G-06 把新的受控 L3 驱动命令写进两仓 `contract-local.yml` 末尾注释块（不新增 workflow 文件、不改 job 步骤）。
5. **G-13 校正**：Spec 11 Stage 0 冻结的"业务运行由受控手动命令完成"原本**没有定义那条命令**，A2 必须把它定义为上面的 driver。

### A2 的账本建模

写入 **A2 自身的 canonical 账本**（这是 pre-A2 边界事实，与 Spec 11 的 pre-A 事件同期同理），三条事件：

```text
11  IN_PROGRESS → SUPERSEDED    CANDIDATE_SUPERSEDED  candidate_commit=A_wiki
10  COMPLETE    → SUPERSEDED    CANDIDATE_SUPERSEDED  candidate_commit=A_wiki  references=[Spec10 COMPLETE event]
10  SUPERSEDED  → IN_PROGRESS   CANDIDATE_SUPERSEDED  candidate_commit=A_wiki  （A2 重启）
```

**旧 `candidate_a` pending suffix 必须被 reducer 拒绝**（`PENDING_3_CANDIDATE_SUPERSEDED`："a pending suffix cannot be reused across candidates"）—— 这是设计使然，也验证了 supersede 生效。旧 suffix 已作为审计材料归档到 `docs/specs/foundation-contract/void/candidate-a.*`（**不覆盖、不删除历史**），并在新边界改用绑定 **A2** 的 suffix。

Spec 11/12 在旧 suffix 里的 `COMPLETE`、Spec 13 的 `BLOCKED` 随 A 一起作废（canonical 里 Spec 11 是 `IN_PROGRESS`、Spec 12/13 是 `NOT_STARTED`），所以三者在 A2 上从各自合法起点重做。

### CI 触发的一个既知约束

`contract-cycle/**` **不在** G-06 冻结的推送触发集合内（只含 `main` / `feature/**`）。所以 A2 提交到 cycle 分支后默认**不会**跑 CI —— 必须用已冻结的 `workflow_dispatch` 手动触发两条 workflow，才能拿到 A2 的 GitHub CI 证据。

### 本轮已验证的 CI（A 及记账提交）

| 仓 / 分支 | SHA | 结果 |
|---|---|---|
| Wiki `feature/foundation-contract-spec10` | `9223916` | Contract Local Gate ✅ + Linux canonical hash ✅ |
| Coding `feature/foundation-contract-spec10`（= A_coding） | `c8e06e5` | Contract Local Gate ✅ + Linux canonical hash ✅ |

---

## L3 收敛裁定（2026-09-16，用户授权）

A2 的驱动部分完成后，L3 仍跑不通。经母 Spec §7.3（分层覆盖要求）逐条比对，问题分两类：

**A 类 —— gate 缺陷，规范明确要求，直接修（B7）**
`gate_smoke` 忽略 per-pair `evidence_requirement`，只用顶层 `coverage_policy` 一刀切，导致 Coding `trace.summary`（登记为 `ONE_OF`）被要求 sdk 与 clickhouse **都**出现。母 Spec §7.3 与 Spec 13:51（"`ONE_OF` 按预登记策略判断"）都要求按预登记策略判定，§7.3:887 更明写 **"未观察到"不等于失败**。

**B 类 —— 规范硬要求 vs 本机环境能力（B4 / B5 / B6）**

| # | 项 | §7.3 原文要求 | 实测现实 |
|---|---|---|---|
| B4 | Wiki `wiki.eval.cost_log` | L3 需 **runner/judge/scoring 全部** | `scoring.py` 顶层 `import deepeval`；deepeval **未声明在 pyproject 也未安装**（项目只在 `deepeval-local` 容器跑） ⇒ 6 条 pair 只能观测到 5 条 |
| B5 | Coding `coding.benchmark.case_cost` | L3 **`normal` required；错误 stage 可 `NOT_OBSERVED`** | 冻结 manifest 把三个 stage **全标 `ALL_STAGES`** ⇒ manifest 本身偏离 §7.3；且 `benchmark/runner.py::_run_one_case` 每个 case 只产出一个 stage，而 `case_ids` 冻结为 1 个 case ⇒ 三个全观测在结构上不可能 |
| B6 | Coding `coding.trace.summary` | L3 **`ONE_OF(sdk, clickhouse)`** | 两个 stage 都无法从 `--benchmark` 路径产生（唯一生产者 `tools/report_trace.py` 只能经 `main.py --trace-report`），且需要 Langfuse 凭据或 127.0.0.1:8123 的 ClickHouse |

**用户裁定**：授权**按环境实际可观测收敛 L3**（选项 b）。具体做法：

1. 为 per-pair `evidence_requirement` 增加一个**自述式**词表值 `NOT_OBSERVED_ALLOWED`（直接引用 §7.3:896 的"可 `NOT_OBSERVED`"用词，便于审计）。
2. 按 §7.3 修正 Coding manifest：`case_cost/normal` 保持 required；`case_cost/environment_error`、`case_cost/error` 改为 `NOT_OBSERVED_ALLOWED`（这一步是**回归规范**，不是偏离）。
3. 对 B4/B6 做**显式偏离**：Wiki `wiki.eval.cost_log/scoring`、Coding `coding.trace.summary/{sdk,clickhouse}` 标为 `NOT_OBSERVED_ALLOWED`，并在以下四处留痕，不静默：
   - 校准记录新增偏离条目（含 §7.3 原文、本机不可观测的确切原因、恢复条件）；
   - pending suffix 事件里记 `SPEC_INCOMPLETE` 供 **Spec 16（Cycle 2）校准**；
   - Evidence / validation report 明写"本环境不可观测"，不得写成 PASS 或伪造观测；
   - 恢复条件写明：装并声明 `deepeval` 后 Wiki `scoring` 可观测；提供 Langfuse 凭据或 ClickHouse 后 Coding `trace.summary` 可观测。
4. `gate_smoke` 对 `NOT_OBSERVED_ALLOWED` 的 pair：未观测 → 记 `NOT_OBSERVED` 并**不**判失败，但必须在 step 摘要里显式列出（"未观测 ≠ 通过"）。

**为什么这不是"放水"**：§7.3:887 已经确立"未观察到不等于失败"；B5 是把 manifest 修回规范；B4/B6 的偏离被逐条具名、具因、带恢复条件地记录，而不是从要求里删掉。用户明确签字授权该偏离。

---

## A2 实施状态快照（2026-09-16，第 8 轮）

**一句话**：A2 的 L3 驱动与 gate 逐对判定已完成（本地未提交），phase 2（覆盖策略收敛）正在实施。A2 **尚未提交**，A 仍是当前候选。

### 已完成（工作区未提交，两仓 cycle worktree）

| 文件 | 内容 | 状态 |
|---|---|---|
| `scripts/contracts/run_l3_smoke.py` | 新增 L3 驱动：强制 mode/run_id、强制预登记 `case_ids`、子进程驱动真实业务路径、按 `RUN_SUMMARY_KEYS` 聚合出 `run-summary.json`、收尾调用冻结的 `gate_smoke` | ✅ 两仓 |
| `tests/contracts/test_run_l3_smoke.py` | 驱动测试（Wiki +29、Coding +22），含 fixture seam 的离线 e2e 与扰动负例 | ✅ 两仓 |
| `*/adapters/foundation/evidence_sink.py` | sink 失败落盘 `<evidence_root>/<run_id>/sink-failures.jsonl`（append-only，缺文件=0 次失败）—— 修复"业务跑在子进程、进程内计数读不到" | ✅ 两仓 |
| `.github/workflows/contract-local.yml` | 末尾注释块记录受控 L3 驱动命令（G-06；不新增 workflow、不改 job） | ✅ 两仓 |
| `scripts/contracts/validate_local.py` | gate 第 7 步改为**逐对**判定：`ALL_STAGES` 逐对必观测；`ONE_OF` 按 `producer_id` 分组成组，组内至少一条；无 per-pair 要求回退顶层 `coverage_policy`（修复 B7） | ✅ 两仓，**逐字节相同** `4ef4c27e…` |
| `tests/contracts/test_validate_local_tools.py` | 逐对判定测试 | ✅ 两仓 |

已在早前验证通过：Wiki `tests/contracts` **348 passed / 3 skipped**、`--gate pr` **8/8**；Coding **218 passed**、`--gate pr` **8/8**；两仓 `verify_payload` payload hash 仍为 `64049830…`（40 文件）。

### 进行中

**phase 2（覆盖策略收敛）** —— 施工单 `C:\Users\Public\dsh-tmp\phase2_brief.md`。要点：
1. 新增 per-pair 词表值 **`NOT_OBSERVED_ALLOWED`**（引用 §7.3:896 原话），gate 接受它；未观测不判失败，但必须在 step 7 摘要**显式点名**（未观测 ≠ 通过）；**不得**作为顶层 `coverage_policy`。
2. **manifest 与 registry 必须成对改**（`publish_evidence.py` 会交叉核对，不一致即报错）：
   - **回归规范（A 类）**：Coding `case_cost/environment_error`、`case_cost/error` → `NOT_OBSERVED_ALLOWED`（§7.3 原本就写"错误 stage 可 `NOT_OBSERVED`"，是冻结的 manifest 写错了）
   - **授权偏离（B 类）**：Wiki `wiki.eval.cost_log/scoring`、Coding `coding.trace.summary/{sdk,clickhouse}` → `NOT_OBSERVED_ALLOWED`
3. `publish_evidence.py` 的 run-manifest 投影与覆盖表必须如实显示新值与 `covered: false`。
4. 更新冻结面守卫测试（`TestFrozenSurface::test_manifest_key_sets_are_frozen` + Coding 侧 manifest 守卫）：继续钉住**键集与嵌套**，并说明哪些值是规范必需、哪些是授权偏离。
5. 校准记录追加偏离章节（§7.3 原文 + 不可观测的确切文件行号证据 + 恢复条件 + 用户按 N-04 授权的声明），并明确区分 A 类回归与 B 类偏离，留待 **Spec 16（Cycle 2）校准**。

### A2 提交前必须做的事

1. 两仓合并验证：`tests/contracts` + `--gate pr`（覆盖 B7 + phase 2 全部改动）。
2. **还原 `output/eval/cost_log.jsonl`**（测试会追加写这个被跟踪文件；A2 提交绝不能含它，否则 B 阶段 `diff(A2,B) ⊆ allowlist` 门禁直接失败）。
3. 跑 `C:\Users\Public\dsh-tmp\a2_supersede_canonical.py`：向 **A2 自身的 canonical 账本**追加 `11 IN_PROGRESS→SUPERSEDED`、`10 COMPLETE→SUPERSEDED`、`10 SUPERSEDED→IN_PROGRESS`（`CANDIDATE_SUPERSEDED`，`candidate_commit=A_wiki`）；脚本会同时验证旧 `candidate_a` suffix 被 `PENDING_3_CANDIDATE_SUPERSEDED` 正确拒绝。
4. 形成 **A2 提交**（两仓 cycle 分支）；cycle 分支**不在** CI 推送触发集合内 ⇒ 必须用已冻结的 `workflow_dispatch` 手动触发两条 workflow 才能拿到 A2 的 GitHub CI 证据。
5. 在 A2 的干净 checkout 重跑 L1 + 全量回归（复用 `%TEMP%\run_l1.ps1`）。
6. 用 `C:\Users\Public\dsh-tmp\suffix_tool.py create --candidate <A2_SHA>` 建**绑定 A2 的新 suffix**（旧 9 条已归档在 `docs/specs/foundation-contract/void/`），再 `append` 各 spec 事件。
7. 重做 L2（`replay_history.py`）→ 跑**真实 L3**（`run_l3_smoke.py`；Wiki 约 4 次 LLM 调用、上限 12 次 / ≤5 CNY；跑完记得还原 `cost_log.jsonl`）。
8. Spec 14：`publish_evidence.py --candidate <A2> --release-version 0.1.0`（Coding 侧需 `AGENT_CONTRACT_CANONICAL_PAYLOAD_COMMIT=A_wiki`）→ 形成 B。
9. Spec 15：构造 **A/B tree 之外**的闭合 cycle plan → `coordinate_cycle.py` → `finalize_cycle.py` → C_wiki（需 `AGENT_CONTRACT_ALLOW_REAL_COORDINATION` / `ALLOW_REAL_LEDGER` / `ALLOW_REAL_RELEASE` 守卫）→ 合并 canonical branch 后复验 → Cycle COMPLETE。

### 已核查、**不需要**修的两项（省掉重复排查）

- `coordinate_cycle.evidence_publication_allowlist` **已包含** Wiki 账本（L322-323），`check_ledger_append_only` 存在 ⇒ B 阶段允许账本 append。
- `coordinate_cycle` 对 Wiki 回归接受 `PASS` **或** `PASS_WITH_KNOWN_BASELINE_FAILURES`（L171）；`gate_candidate` 已按裁定实现 G-07（`RESOLVED_UNEXPECTEDLY` = 允许 + `needs_review`）。`publish_evidence` 的 `full_regression` 硬编码为 Spec 14 字面要求值，属**已记残余**，不阻塞。

---

## A2 冻结完成 + L3 provider 阻断与 LLM 整合裁定（2026-09-16）

### A2 已形成并通过全量验证

| | A2_wiki | A2_coding |
|---|---|---|
| SHA | `ca24a199f3300a2e9e1390f6186acbb5c9dfdaad` | `339768dd2f9e3b26c8820408ec93bf30e378e50e` |
| L1（6 命令） | 全 exit 0 | 全 exit 0 |
| conformance | 224 passed | 224 passed |
| tests/contracts | 368 passed / 3 skipped | 242 passed |
| `--gate pr` | 8/8 | 8/8 |
| `python -m build` | exit 0 | exit 0 |
| 全量回归 | **913 passed / 10 skipped / 0 failed** | **623 passed / 13 skipped / 0 failed** |
| payload hash | `64049830…` 不变 | `64049830…` 不变 |

CI：cycle 分支不在推送触发集合内（G-06），已用 `workflow_dispatch` 手动触发 4 条（wiki local 35114299175 / hash 35114304298；coding local 35114309620 / hash 35114318323）。

账本：A 的 supersede 已落 canonical（`11 IN_PROGRESS→SUPERSEDED`、`10 COMPLETE→SUPERSEDED→IN_PROGRESS`）；旧 `candidate_a` suffix 被 **`PENDING_3_CANDIDATE_SUPERSEDED`** 正确拒绝（证明 pending 机制真能挡住跨候选复用），已归档 `void/`。新 suffix 绑定 `ca24a199`，9 事件，hash `ce40a77a…`：**Spec 10/11/12 `COMPLETE`**、Spec 13 `NOT_STARTED`。

Spec 12 在 A2 上重跑 L2 **PASS** 且结果与旧候选逐项一致（Wiki 220 `REPRODUCTION_RESTRICTED` / Coding 3 `LEGACY_DATA_INSUFFICIENT`）→ 证明 A2 修复**对 L2 行为保持**。

### 真实 L3 失败：不是 A2 缺陷，但驱动失败路径被验证

volcengine 返回 `InvalidSubscription`（订阅过期）。**驱动行为完全正确**：

```text
SPEC_STATUS_CONFLICT / GATE FAILED: 业务路径退出码 1 != 0；拒绝为一次未跑完的 run 写 run-summary
```

即：**拒绝为未完成的 run 伪造 `run-summary.json`**。而且失败前已成功执行 ① 校验 manifest ② **选中预登记 case_ids（B3）** ③ **构造并启动业务命令（B2）**。失败 run 已按 Spec 13 要求归档到 `failed-runs/`。⇒ B1/B2/B3 机制在**真实路径**上均被触发过，比合成测试更有说服力。

### provider 实测（三死一活）

| provider | 实测 |
|---|---|
| command_goat（`command_goat_api`，已设置） | ✅ **真实调用成功** |
| DeepSeek 官方（`deepseek_api`） | ⚠️ 密钥有效；但 `GET /models` **只有** `deepseek-flash`、`deepseek-v4-pro` |
| volcengine（`arkcode_api`） | ❌ `InvalidSubscription` 订阅过期 |
| minimax（`minimax_api`） | ❌ 429 配额用完 |

### 用户裁定：全项目 LLM key 整合

用户指令：整理当前项目所有 LLM key，改用 **DeepSeek 官方 + `command_goat_api`**（base `https://api.commandcode.ai/provider/v1`），都路由到 `deepseek-v4.1-flash`，做好测试，**优先使用订阅的模型**。

**两条与实测冲突之处，按"显式标注而非静默处理"处理**：
1. command_goat 要求**命名空间 ID** `deepseek/deepseek-v4.1-flash`（裸名被拒 `unsupported_model`，已实测）。
2. DeepSeek 官方**没有** `v4.1-flash`（`/models` 只有两个），故该档用 `deepseek-flash`，实现与文档中明确写为**替代**，不得假装等价。

优先级：**`command_goat_api`（订阅）→ `deepseek_api`**；volcengine/minimax **不再作为静默 fallback**（否则会掩盖真实故障）。价格未知必须报**未知**而非 0（presence-aware 契约要求）。

施工单：`C:\Users\Public\dsh-tmp\llm_consolidation_brief.md`。**范围只含 Wiki**；Coding 的 LLM 入口与 `opencode_go_api` 可用性由同一交付**报告**但**不许改动**，待报告后再决定是否同步。

---

## 候选轮次 A→A4 全记录与接手要点（2026-09-16，第 37 轮）

### 候选演进（每一步都由真实缺陷推动，非返工浪费）

| 候选 | SHA | 触发原因 | 结果 |
|---|---|---|---|
| **A** | `b726c09` / `c8e06e5` | 初次冻结 | L1+回归全绿，但 Spec 13 无法闭合（B1–B7） |
| **A2** | `ca24a199` / `339768dd` | B1–B7：无 run-summary 生产者 / 无 L3 驱动 / case_ids 选不中 / gate 忽略 per-pair / §7.3 硬要求不可观测 | L1+回归全绿（913/623 passed，0 failed） |
| **A3** | `3972c887`（仅 Wiki） | provider 三死一活 + judge 网关限流 + 驱动编码缺陷 | **L3 技术上 8/8 通过**，但**全量回归 1 failed** |
| **A4** | `554bce2f`（仅 Wiki） | A3 的回归根因＝**定价歧义零** | L1+回归**待验证** |

**A3 的 L3 通过细节**（这是关键里程碑，可复现）：`ALL_STAGES 5/5`（含 judge）、`NOT_OBSERVED_ALLOWED 0/1`（gate 显式列出 `wiki.eval.cost_log/scoring` 为"未观测（豁免登记，**不计为通过/覆盖**）"）、`run-summary` 闭合（sink=0 / 无拒绝 / 54s 在预算内）、业务路径 exit 0、12 条 evidence 事件。

### 三个必须记住的"命令成功但语义错误"陷阱

1. **`workflow_dispatch` 按远程 ref 取 HEAD**：本地提交未推送时 dispatch 会**成功返回 URL，但测的是旧 HEAD**。必须用 `git ls-remote origin <branch>` **独立确认**远程 HEAD = 目标 SHA，再 dispatch。（已踩过一次。）
2. **`subprocess.run(text=True)` 在 Windows 按 gbk 解码**：业务路径 UTF-8 中文输出会让读取线程抛 `UnicodeDecodeError` 并**丢掉全部业务输出**，使失败无法诊断。须显式 `encoding="utf-8", errors="replace"`。（Coding 驱动本有此修复，Wiki 侧漏了。）
3. **`_use_legacy_*` 不能用"环境变量存在"作判据**：`opencode_go_api` 在本机恒存在，若以它为准会把 opencode 的 key 发给新端点 → **401**。必须显式要求（设 `opencode_go_base` 或 `arknights_judge_use_opencode=1`）才回退。

### provider 实测（2026-09-16，四选一）

| provider | 结果 |
|---|---|
| `command_goat_api` → `https://api.commandcode.ai/provider/v1` | ✅ **可用**；模型 ID **必须**带命名空间：`deepseek/deepseek-v4.1-flash`（裸名被拒 `unsupported_model`） |
| `deepseek_api` → `https://api.deepseek.com/v1` | ⚠️ 密钥有效，但 `/models` **只有** `deepseek-flash`、`deepseek-v4-pro`；**无** v4.1-flash（属替代，ID 不等价） |
| `opencode_go_api` | ❌ 鉴权通过（`/models` 200）但**推理 429 Too Many Requests** |
| `arkcode_api`(volcengine) | ❌ 订阅过期 `InvalidSubscription`（`/models` 200，仅推理失败） |
| `minimax_api` | ❌ 429 配额用尽 |

该模型是**推理型**：`max_tokens` 太小（如 16）会返回**空 content**，需给足预算。

### A3 引入的回归与修法（示范契约原则）

`tests/observability/test_llm_tracing.py::test_enabled_records_usage` 断言 `cost_details["total"] > 0` 得到 `0.0` —— 因新模型 ID 在 `arknights_wiki/eval/pricing.json` 无条目，**未知单价被静默当成 0**，正是契约要消灭的 `Unknown is not Zero`。修法：按该表既有惯例（所有 DeepSeek/MiniMax 条目均 `in 2.0 / out 8.0` + `estimate: true`）补两条，并在 `note` 写明**沿用 flash 档估算、未经供应商账单核对、属 estimate 待核对** —— 沿用约定并标注不确定性，而非编造价格。

### 剩余步骤（严格顺序）

1. **A4 验证**：L1 六条命令 + 全量回归（后台 `pwsh-53`，日志 `%TEMP%\l1-a4-wiki.log`）。期望 913 passed / 0 failed。
2. **CI**：A4 已 dispatch（run `35119905641` / `35119909715`）；须先 `git ls-remote` 确认远程 HEAD = `554bce2f…`。
3. **新 suffix 绑定 A4**：`%TEMP%\suffix_tool.py create --repo <cycle-wiki> --candidate 554bce2f…`，再 `append` Spec 10/11/12 事件（模板见 `%TEMP%\a2_new_suffix.py`、`a2_spec12_events.py`）。A3 的 suffix（hash `ce40a77a…`，绑定 `ca24a199`）须先归档到 `void/` 再作废。
4. **L3 用 A4 重跑**：`AGENT_CONTRACT_MODE=observe`、`AGENT_CONTRACT_RUN_ID=foundation-0_1_0-c1-wiki-smoke`、`AGENT_CONTRACT_COMMIT=554bce2f…`、`python scripts/contracts/run_l3_smoke.py --run-manifest config/contracts/smoke-v0.1.json`。**跑完必须 `git checkout -- output/eval/cost_log.jsonl`**（业务运行会追加污染这个被跟踪文件；混入候选会让 B 阶段 allowlist 门禁失败）。失败 run 要归档到 `failed-runs/`（已有 4 份）。
5. **Coding 侧**：其 smoke manifest 预登记 `provider=opencode_go` / `model=mimo-v2.5`，而 opencode **推理 429** ⇒ Coding L3 很可能同样跑不通，需要把同一套 provider 整合应用到 Coding（可能要 **A5_coding**）。**先实测再决定，不要凭猜测做候选。**
6. **Spec 14**：`python scripts/contracts/publish_evidence.py --candidate <A4> --release-version 0.1.0`（Coding 侧需 `AGENT_CONTRACT_CANONICAL_PAYLOAD_COMMIT=<A_wiki>`）→ 形成 B_wiki/B_coding。注意 `evidence_publication_allowlist` 已含 Wiki 账本（L322-323）。
7. **Spec 15**：构造 **A/B tree 之外**的闭合 cycle plan → `coordinate_cycle.py --plan <plan> --output <out>` → `finalize_cycle.py --coordination <out> --release docs/contracts/releases/0.1.0` → C_wiki → 合并 canonical branch 后复验 → Cycle COMPLETE。需 `AGENT_CONTRACT_ALLOW_REAL_COORDINATION` / `ALLOW_REAL_LEDGER` / `ALLOW_REAL_RELEASE` 守卫。

### 已核查、不需要修的项（省重复排查）

- `coordinate_cycle.evidence_publication_allowlist` **已包含** Wiki 账本；`check_ledger_append_only` 存在。
- `coordinate_cycle` 对 Wiki 回归接受 `PASS` **或** `PASS_WITH_KNOWN_BASELINE_FAILURES`；`gate_candidate` 已按裁定实现 G-07（`RESOLVED_UNEXPECTEDLY` = 允许 + `needs_review`）。
- `publish_evidence` 的 `full_regression` 硬编码为 Spec 14 字面要求值，属**已记残余**，不阻塞。
- **agent/judge 模型分离**目前丢失（旧 judge 默认 `mimo-v2.5` 只在已限流的 opencode 上）；保留 `ark_judge_model` 覆盖开关，网关恢复后应重建分离以缓解自评偏差 —— 记为待办。

---

## Spec 13 完成：L3 fresh smoke 在 A4 上闭合（2026-09-16，第 39 轮）

**A4 = Wiki `554bce2f2ebd00f5f4e6ac722680a8a57ab8cc66` / Coding `339768dd2f9e3b26c8820408ec93bf30e378e50e`**

A4_wiki 干净 checkout 全量验证：L1 六条命令全 exit 0、conformance 224 passed、`tests/contracts` 368 passed / 3 skipped、`--gate pr` 8/8、`python -m build` exit 0、**全量回归 913 passed / 10 skipped / 0 failed**。

**真实 L3（`run_l3_smoke.py`，`AGENT_CONTRACT_COMMIT=554bce2f…`）8/8 通过**：

```text
[1] OK  run_id 与 manifest 一致 + mode=observe
[2] OK  无 .tmp 残留
[3] OK  EvidenceRecord 模式校验 — 12 条全部通过
[4] OK  event_id 唯一 — 12 唯一
[5] OK  repository / commit / version / payload hash 一致   ← 真正绑定 A4
[6] OK  全部事件 contract_mode=observe — 12 条
[7] OK  ALL_STAGES 5/5；NOT_OBSERVED_ALLOWED 0/1
        未观测（豁免登记，不计为通过/覆盖）：wiki.eval.cost_log/scoring
[8] OK  run-summary 闭合（sink=0 / 无拒绝 / 时长在预算内）
L3 fresh smoke PASSED   （业务 exit 0，51.2s，12 事件）
```

**关键区分**：`[5]` 证明证据**真正绑定 A4**（A3 那次是用未提交改动跑却绑定旧 SHA，绑定不成立，故作废重做）；`[7]` 证明已豁免的 `scoring` 被**显式列为"未观测、不计入覆盖"** —— B7 的反放水要求在真实运行中生效；业务成功与 evidence 成功**分开报告**（Spec 13 step 4）。

失败 run 历史保留 4 份于 `staging/failed-runs/`（provider 订阅过期 / judge 429 / judge 缺失），符合 Spec 13 "必须保留失败 run 历史"。

账本：`candidate_a` suffix 13 事件、hash `a4ff9899…`、绑定 `554bce2f…`；**Spec 10/11/12/13 `COMPLETE`**，**Spec 14/15 已解锁**。A 与 A2 两代被作废的边界证据已归档 `void/`。

### 下一步（Spec 14 → 15）

1. **Coding 侧 L3 先实测**：其 smoke manifest 预登记 `provider=opencode_go` / `model=mimo-v2.5`，而 opencode 推理 **429** ⇒ 很可能需要把同一套 provider 整合应用到 Coding（可能要 **A5_coding**）。不要凭猜测做候选。
2. **Spec 14**：`python scripts/contracts/publish_evidence.py --candidate <A4> --release-version 0.1.0`（Coding 侧需 `AGENT_CONTRACT_CANONICAL_PAYLOAD_COMMIT=<A_wiki>`）→ 形成 B_wiki / B_coding。allowlist 已含 Wiki 账本。
3. **Spec 15**：构造 **A/B tree 之外**的闭合 cycle plan → `coordinate_cycle.py --plan <plan> --output <out>` → `finalize_cycle.py --coordination <out> --release docs/contracts/releases/0.1.0` → C_wiki → 合并 canonical branch 后复验 → Cycle COMPLETE。需 `ALLOW_REAL_COORDINATION` / `ALLOW_REAL_LEDGER` / `ALLOW_REAL_RELEASE` 守卫。

---

## 会话恢复指南（供上下文压缩后接手）

**当前状态一句话**：Foundation Contract **Spec 01–12 已 `COMPLETE`，但 A 因 Spec 13 的 B1/B2/B3 缺陷被 `SUPERSEDED`**（用户按 N-04 批准规范路径）；正在实施 **A2**（纯工具级修复，payload hash 不变）。A2 完成后须重跑 L1/回归（2 仓）、重做 L2、跑真实 L3，再进 Spec 14/15。Spec 14/15 未解锁。

### 第一步：读三份文件（按序）

1. `README.md` — 项目状态与 Foundation Contract 章节
2. `output/devlog.md` 末尾 — 本指南 + Spec 10/CI 全过程
3. `docs/plans/2026-09-16-foundation-contract-spec11-stage0-calibration.md` — **Spec 11 的直接输入**

### 第二步：进入 worktree 并确认状态

```powershell
cd "D:\AI project\_worktrees\foundation-contract\wiki"   # Coding 同理
# canonical 账本单独归约
D:\CodexPython312\python.exe scripts/contracts/status_ledger.py validate --ledger docs/specs/foundation-contract/execution-status-events.jsonl
# canonical 前缀 + candidate_a pending suffix（Spec 11 之后应看到 11 COMPLETE pending=True）
$d='docs/specs/foundation-contract'
D:\CodexPython312\python.exe scripts/contracts/status_ledger.py validate --ledger "$d/execution-status-events.jsonl" --pending-jsonl "$d/execution-status-events.pending.jsonl" --pending-envelope "$d/execution-status-events.pending.json"
D:\CodexPython312\python.exe scripts/contracts/validate_local.py --gate pr
```

> **注意**：`--self-commit` **不要**传 A_wiki。pending suffix 的事件绑定 `candidate_commit=A_wiki`，而 `A_wiki` 正是封装 canonical 前缀的那次提交；传 `--self-commit A_wiki` 会正确地报 `RULE_7_SELF_COMMIT_REFERENCE`。该 suffix **本就不属于 A**，它是 A 之外的受控 staging，Spec 14 才把它 append 进 B_wiki。

- 权威解释器：`D:\CodexPython312\python.exe`（3.12.10 + pydantic 2.13.4）。PATH 里的 python **没有**项目依赖。
- 动态状态**只看** `docs/specs/foundation-contract/execution-status-events.jsonl`（canonical 43 条事件；子 Spec 里的状态是 genesis，不反映进度）。加上 `candidate_a` pending suffix 后 Spec 11 = `COMPLETE (pending=True)`。
- 契约身份：`contract_version=0.1.0`、payload `sha256:64049830…`（40 文件，两仓一致）、rule coverage `68 = 56 conformance + 7 项目 + 5 deferral`。

### 第三步：下一步是等 N-04 批准后做 A2（Spec 13 被阻断）

Spec 13 无法在 A 上闭合，三个缺陷 B1/B2/B3 见上一节。**规范给出的唯一合法路径**是 A `SUPERSEDED` → 回到 **Spec 10**（拥有 post-freeze 工具集与 smoke harness）修工具 → 形成 **A2** → 从 A2 重跑 L1 + 全量回归 + 重做 L2（Spec 12）/ L3（Spec 13）→ 再进 Spec 14/15。

A2 需要新增的代码（都属 N-04 范畴，须先获批准）：

1. **L3 driver**：一条受控手动命令，以 `observe` 驱动真实业务路径并让 runtime 在进程内累计 counters（B2）。
2. **`run-summary` 生产者**：在 run 结束时把 8 个冻结键写入 `<evidence_root>/<run_id>/run-summary.json`（B1）。其中 7 键需要 runtime 暴露 accessor，或由 sark 侧聚合 —— 两者都是 A 内实现变更。
3. **case 选择**：让预登记 `case_ids` 可被选中（runner 增加 `--case-id`，或由 driver 从草稿 bench 投影出预登记的 case，且不改动已冻结的 `config/`）（B3）。

**A2 之后的重跑成本**（估）：两仓 L1（6 条命令 × 2）+ 全量回归（Wiki 864 / Coding 577）+ L2 重放 + 真实 L3 运行（Wiki 约 4 次 LLM 调用、上限 12 次 / ≤5 CNY；Coding ≤1 USD）。这一轮的成本决策必须由用户拍板。

**若用户选择"不修"**：Spec 14 依赖 `11 + 12 + 13 COMPLETE`，Cycle 1 将停在此处无法 COMPLETE（`publish_evidence` 把 `fresh_smoke` 记为 `NOT_OBSERVED` 只是 §11.5 的合法状态，并不能替代 Spec 13 的 COMPLETE 依赖）。

### 远程与分支（2026-09-16 Spec 11 收盘）

| 仓 | 分支 | HEAD | 说明 |
|---|---|---|---|
| Wiki | `main` | `c2d39c5` | 含 Foundation 母 Spec 文档 + 远程 fix/issue-2 合并；**不含任何 Foundation 代码** |
| Wiki | `contract-cycle/foundation-0.1.0-cycle-1` | `b726c09` = **A_wiki** | **A/B/C 唯一承载分支** |
| Wiki | `feature/foundation-contract-spec10` | Spec 11 记账提交 | 全部实现 + 校准 + 冻结前记账（README/devlog 留在此分支，不插入 A→B） |
| Wiki | `feature/foundation-contract` | `102de4c` | Spec 09 收尾 |
| Coding | `contract-cycle/foundation-0.1.0-cycle-1` | `c8e06e5` = **A_coding** | **A/B/C 唯一承载分支** |
| Coding | `feature/foundation-contract-spec10` | `c8e06e5` | Spec 10 全部工作 |
| Coding | `feature/foundation-contract` | `1798859` | Spec 09 镜像 |

> Coding 主工作区 `D:\AI project\Knowledge-Augmented Autonomous Coding Agent` 当前 `08a8275 [main]` —— 本轮**未触碰** Coding `main`。

### 环境坑（可复用，别再踩）

1. **脚本自举**：`python scripts/contracts/x.py` 的 `sys.path[0]` 是脚本目录，仓库根不在其中（只有 `python -m` 才加 CWD）→ 所有脚本顶部自行插入仓库根。两仓都提供顶层 `agent_core`，同一解释器**无法**同时可编辑安装两者。
2. **CI runner 三件事**：Windows runner 的 stdout 默认 **cp1252**（脚本须 `reconfigure(encoding="utf-8")`）；runner **没有 git 身份**（需 workflow 内配置）；L1 gate **无密钥**，而 3 个 Wiki 测试要求 provider 配置**存在** → job 级占位环境值（非凭据）。
3. **依赖档位**：Wiki gate 需 `[dev,agent]`（回归子集顶层 import `langgraph`/`numpy`）；`faiss`/`torch` 在 `vector_index.py` 内懒加载、`deepeval` 由测试注入 fake 模块。
4. **追加账本事件后必须重跑验收**：曾因先跑验收再追加事件，导致写死状态的测试在 CI 上失败。
5. **不要提交** `data/extractions/v3_seed_db_v2.json` 与 `output/eval/cost_log.jsonl`（项目测试会改写后者，前者是历史遗留）；两者长期处于 `M` 状态属正常。
6. **网络**：`github.com` 边缘 IP 偶尔不可达（`api.github.com` 正常）；push 失败时重试即可，本地提交始终安全。
7. **`.gitignore` 已含** `output/contract-validation/{staging,raw,private}/`、`build/`、`dist/`；scratch 脚本请放 `%TEMP%`，不要放 `staging/`（publication safety scan 会扫该目录并命中绝对路径）。
8. **PowerShell 传 JSON 给原生命令会吃掉引号**：`--event '{"a":1}'` 到 Python 时变成 `{a:1}` 而解析失败。所有需要传 JSON 的场合**改走临时文件**。同理 `echo` 在 pwsh 里是 `Write-Output` 别名，空参报错 —— 用 `Write-Host ''` 或 `"..."; ""` 之外的写法。
9. **cycle 分支不能混入记账提交**：`diff(A,B) ⊆ allowlist` 是硬门禁，README/devlog 不在 allowlist 内 → 记账提交必须留在 `feature/foundation-contract-spec10`，A/B/C 只走 `contract-cycle/foundation-0.1.0-cycle-1`。
10. **pending suffix 是 untracked 的**：`docs/specs/foundation-contract/execution-status-events.pending.{jsonl,json}` **故意不提交**（提交它会污染 A→B 的 diff）。切分支不会动 untracked 文件，但 `git clean -fd` 会删掉它 —— **不要**在 spec 目录跑 `git clean`；重建脚本见本轮写法（用 `canonical_pending_paths()` + `compute_suffix_hash()`）。
11. **不要 `git worktree add` 到仓库内部**：干净 checkout 用 `git worktree add --detach <path> <A_SHA>` 建在 `%TEMP%` 下，跑完 `git worktree remove --force`。Coding 与 Wiki 都提供顶层 `agent_core`，**同一解释器无法同时可编辑安装两者**，所以干净 checkout 只能靠 CWD + 自举，不要试图 `pip install -e`。

---

## 2026-09-17（续）A5_coding：provider 整合 + Coding 半边 L3 实测阻断（Spec 13 退回 IN_PROGRESS → BLOCKED）

### 触发：发现上一轮的 Spec 13 `COMPLETE` 证据不足

回看账本时对照母 Spec，发现 **Spec 13 的 Coding 半边从未真实运行过**：账本里 Spec 13 的 evidence_refs
只引用了 `foundation-0_1_0-c1-wiki-smoke`，而子 Spec 13 的 `Expected Outputs` 明写「双仓闭合 L3 run
artifacts」、`Validation Commands` 分别给出 Wiki 与 Coding 两条命令、Index §3 的 Target 也是 `BOTH`。
即上一轮写下的 `13 COMPLETE` 是**过早状态**（不是伪造证据，但结论不成立）。

处理：不改写历史事件，改用账本自带的 `COMPLETE → IN_PROGRESS` + `reason_code=STATUS_CORRECTION`
并 `references=[<被纠正的 event_id>]` 把它退回重做（reducer 自带规则 8 正是为此设计）。

### A5_coding（provider 整合，用户已授权 N-04）

| 项 | 值 |
|---|---|
| A_coding | `c5d0af0f4c9110259945fc90151da4336a07d639`（取代 A2 `339768dd2f9e3b26c8820408ec93bf30e378e50e`） |
| A_wiki | `554bce2f…`（未变） |
| payload | `sha256:64049830…` / 40 文件 / 0.1.0 —— **未变**，A5 是 payload-neutral |
| 改动 | `agent/llm.py`（新增 `command_goat` + `_resolve_provider_name()` 自动选择）、`config/contracts/smoke-v0.1.json`（provider/model 与 Wiki 锁步，**键集未变**）、`tests/test_llm.py`（+4 项覆盖）、`.env.example` |
| L1 | 6 条全 exit 0；conformance 224；`tests/contracts` 242；`--gate pr` 8/8 |
| 全量回归 | **638 passed / 3 skipped / 0 failed** |
| L2 | `foundation-0_1_0-c1-coding-replay` PASS，3 records / 3 sources，全 `LEGACY_DATA_INSUFFICIENT` |

证据（全部实测）：`command_goat/deepseek-v4.1-flash` **可用**（也支持 tool calling，2.9s 返回）；
`opencode_go/mimo-v2.5` **429 `GoUsageLimitError`「Monthly usage limit reached」**；
`deepseek_api/deepseek-flash` 可用。

### Coding 半边 L3：四条实测原因（每层都留下了证据）

1. **F1 预登记 provider 不可用** → 429 月度额度耗尽。
2. **F2 宿主执行器不可能通过**：`schedule-99` 的 fixture 测试 `test_schedule.py:30` 调用
   POSIX-only `time.tzset()`，Windows 下必然 `environment_error`（`AttributeError` 直接复现），
   Agent 不运行 → `coding.benchmark.case_cost/normal` 不可观测。
3. **F3 候选缺陷（关键）**：`benchmark/runner.py::_run_one_case` 先进入 `sandbox_executor(repo_dir)`
   再调用 `_ensure_repository()`，而 `DockerExecutor.create()` 要求 `workspace_root` 已存在
   （`tools/docker_sandbox.py`）→ **任何全新 workspace** 下 docker 执行器都以
   「沙箱工作区不存在」失败，只有复用旧 workspace 才偶然通过。
   即：宿主要 gh 才能做 repo 就绪、容器要 POSIX 才能跑测试，**唯一同时满足两者的 docker 执行器路径本身是坏的**。
4. **F4 修正顺序后仍不闭合**：把 `_ensure_repository` 移到 `with` 之外（临时试验、**已还原未提交**）
   并预建 workspace + 开放容器网络后，宿主 `gh` 克隆成功、沙箱创建成功，但业务路径在冻结的
   `timeout_seconds=600` 内始终拿不到任何 provider 响应（0 事件；600.016s wall / ~17s CPU；
   期间容器完全空闲）。
5. **F5 对照**：同一 agent + 同一 provider + 同一 case 在 **local** 执行器下 **12 次调用 / 83s**
   全部正常（prompt 到 170KB 仍 5.6s 返回）→ provider 与 agent 本身健康，问题在 docker 执行器路径。
6. **F6**：把整个 driver 放进项目自己的 Linux 沙箱镜像（`ka-sandbox:py312-v1`，Python 3.12.14，
   有 `time.tzset`）又暴露 `get_repository()` 依赖**宿主** `gh` CLI（`tools/github_tools.py`
   设计上「凭据不进沙箱」），镜像内无 gh。

### 本轮刻意不做的事

- **不热修** `benchmark/runner.py`：Spec 13 `No-implementation Boundary` 明确禁止在本步骤改业务代码，
  缺陷必须回到 pre-freeze 子 Spec 形成新候选后重跑 L1/L2/L3。
- **不**事后调高冻结 manifest 的 `timeout_seconds` / cost cap，**不**删除任何未观测 stage
  （Spec 13 明令禁止「根据运行结果事后删除未覆盖 stage 或提高成本上限」）。
- **不**把 F2/F3/F4 的失败 run 发布为 Evidence；失败 run 全部保留在
  `output/contract-validation/{staging/,}failed-runs/`。

### 账本与状态

pending suffix 由 13 → **23 事件**（`suffix_hash=sha256:673486d1…`），归约结果：

```text
10 COMPLETE(pending) | 11 COMPLETE(pending) | 12 COMPLETE(pending) | 13 BLOCKED(pending)
14 NOT_STARTED | 15 NOT_STARTED
```

- Spec 11 / 12：`COMPLETE → SUPERSEDED → IN_PROGRESS → VALIDATED → COMPLETE`，绑定 A5 的真实证据。
- Spec 13：`COMPLETE → IN_PROGRESS`（`STATUS_CORRECTION`，引用被纠正事件）→ `BLOCKED`（`BLOCKED`）。
- Spec 10：未改任何工具，其 `COMPLETE` 保持不变（A5 的 L1.1–L1.6 已重新验证其工具链）。
- Spec 14/15：依赖未满足，**保持锁定**，本轮未创建 B/C。

### 教训

1. **"半边证据"必须对照子 Spec 的 `Expected Outputs` 与 `Target Repository` 逐条核**：母 Spec 说
   「未观察到 ≠ 失败」，但**没观察到却写成 COMPLETE** 是另一种错误；账本自带的
   `STATUS_CORRECTION` 就是为这种情形准备的，不要用 `SUPERSEDED` 掩盖。
2. **同一 run_id 会被驱动重建**：失败 run 必须在下次运行前挪到 `failed-runs/`，否则即使报错文本
   已抄进文档，原始产物也已被覆盖。
3. **业务产物不得落到 staging**：`report.json` 含 `diff` 字段与绝对路径，`--gate pr` 的发布扫描会因此
   失败 —— 这就是驱动把业务输出放 `run-scratch/`、只让派生摘要进 staging 的原因；搬运失败 run 时
   同样要遵守（archive 的业务部分放 `output/contract-validation/failed-runs/`，不放 `staging/`）。
4. **诊断"卡住"要拿栈，不要猜**：`faulthandler.dump_traceback_later` + 逐次调用计时（包装
   `client.chat`）把"provider 慢 / docker exec 卡 / 本机 I/O 慢"三种假设一次区分开 ——
   本轮先后否掉了「Docker 挂载 I/O 慢」（实测 `git status` 0.5s、pytest 收集 0.7s）与
   「provider 坏」（对照组 12 次调用全正常）两个**错误**假设。

---

## 2026-09-17（再续）A6_coding：修复 F3（沙箱创建顺序），并记录外部阻塞 F7

### A6_coding = `5e780fd`（取代 A5 `c5d0af0f`；A_wiki 不变）

| 项 | 结果 |
|---|---|
| 改动 | `benchmark/runner.py`：`_ensure_repository()` 移到 `with sandbox_executor(...)` **之前**；`tests/test_benchmark_runner.py`：新增回归钉子 `test_sandbox_entered_only_after_repository_is_ready` |
| 钉子有效性 | 旧顺序下该测试**实测 FAIL**（"沙箱在 workspace 就绪之前被进入…"），修复后 PASS；相关套件 98 passed |
| L1.1–L1.6 | 全部 exit 0（三哈希未变 / conformance 224 / tests/contracts 242 / --gate pr 8/8 / build） |
| 全量回归 | `638 passed / 3 skipped / **1 failed**` —— 唯一失败 `test_docker_integration.py::test_clone_repo_when_empty`（容器内克隆 github.com），**环境性**，故 Spec 11 停在 `IN_PROGRESS` |
| L2 | `foundation-0_1_0-c1-coding-replay` **PASS**（3 records / 3 sources，全 `LEGACY_DATA_INSUFFICIENT`，绑定 A6） |
| L3 | Coding 半边**仍未闭合**（见 F7） |

### F7：GitHub 网络故障（本轮新的外部阻塞）

`github.com:443` 持续不可达：`git ls-remote https://github.com/dbader/schedule.git` 连续 8 次失败，
`gh repo clone` 报 `Recv failure: Connection was reset`。

关键点：**Coding 的基准路径在基线之前必须先做 repo 就绪**，而 `_ensure_repository` →
`sync_repository` 需要 `git fetch origin`（首次 clone 亦然）→ **网络不可达时基准根本无法启动**，
L3 拿不到任何 `case_cost/normal` 观测。同一故障也阻断了两个候选分支的 push。

我没有因此放宽任何冻结字段、没有补写证据、没有把失败 run 发布为 Evidence —— 账本如实记
`Spec 11 IN_PROGRESS`、`Spec 13 BLOCKED`，并把恢复命令写进校准记录 §11.8。

### 账本（suffix 31 事件，`suffix_hash=sha256:1d76da31…`）

```text
10 COMPLETE | 11 IN_PROGRESS(pending) | 12 COMPLETE(pending) | 13 BLOCKED(pending) | 14/15 NOT_STARTED
```

- 11：`COMPLETE → SUPERSEDED → IN_PROGRESS`（A5 因 F3 被取代；A6 的 L1 通过但回归含一条环境性失败）。
- 12：`COMPLETE → SUPERSEDED → IN_PROGRESS → VALIDATED → COMPLETE`（A6 上 L2 PASS）。
- 13：维持 `BLOCKED`，并记录"F3 已修复 → 重启 → 被 F7 重新阻塞"的完整过程。

### 教训

1. **一个"恰好在旧工作区能通过"的缺陷，单测和 local 执行器都抓不到**：F3 只在「全新 workspace +
   docker 执行器」组合下暴露。修完之后**必须把那个组合固化成测试**（替身沙箱检查前置条件），
   否则下次重构还会把它改回来。
2. **环境性失败要如实归类**：`test_clone_repo_when_empty` 失败与 A6 改动无关，但它确实让
   "Coding 回归 = PASS" 这一验收项不成立 —— 正确做法是记 `IN_PROGRESS` 并写明原因，
   而不是把它当 flaky 略过。
3. **先确认外部依赖再选执行路径**：Coding 基准对 github.com 有硬依赖（repo 就绪），
   在这个前提下"离线也能跑 L3"的假设不成立。

---

## 2026-09-17（三续）网络恢复窗口内的复测：F4 收窄 + 两仓已推送

GitHub 短暂恢复后完成/观察到：

1. **两仓推送成功**：Wiki `feature/foundation-contract-spec10` → `0423d5b`；
   Coding `contract-cycle/foundation-0.1.0-cycle-1` → `5e780fd`（`git ls-remote` 与本地一致）。
2. **F4 在 A6 上复现**：`KA_EXECUTOR=docker` + `command_goat` 跑 Coding L3 →
   `business_timed_out=true`、`duration_seconds=600.25`、`producer_coverage=[]`、`actual_calls=0`；
   `faulthandler` 采样（30s × 5）全部停在 `plan_node`/`decide_node` → `chat` → `ssl.read`（等响应头）。
3. **F4 收窄（重要）**：用 `real_agent_timing.py` 以**同一** `KA_EXECUTOR=docker`、**同一** provider
   单独驱动同一 agent/case，**12 次调用全部成功、总计 110.5s**（单次 1.2–24.2s，prompt 最大 ~92KB）。
   → 否证了"docker 执行器会让 provider 调用挂死"这一假设。
4. **网络自身在抖动**：同一窗口内 `gh repo clone` / `git fetch origin` 反复
   `Recv failure: Connection was reset`；全量回归重跑仍是 `638 passed / 3 skipped / 1 failed`，
   唯一失败仍是容器内 `git clone https://github.com/octocat/Hello-World.git`。

据此把 F4 记为**未定论、高度怀疑外部网络不稳定**：好窗口内同组合 110.5s 正常，坏窗口内 provider
请求停在等响应头且 GitHub 同时被 reset。要区分"网络抖动"与"某条特定请求触发网关长时间不响应"，
必须在**稳定网络**下重跑一次 L3。

账本无需改动（也**不该**改动）：`Spec 11 IN_PROGRESS`（回归含 1 条网络性失败）、`Spec 12 COMPLETE`、
`Spec 13 BLOCKED`、Spec 14/15 锁定，仍然是当前真实状态。

### 本轮最重要的一条纪律

**不要让"环境不好"变成"把门槛降低"**。F4 复现后最省事的做法是调大冻结 manifest 的
`timeout_seconds`，让 L3 "通过" —— 而 Spec 13 恰好明文禁止"根据运行结果事后提高成本上限",
§7.3 也写着"未观察到 ≠ 失败"（反过来同样成立：**没通过也不等于可以改写标准**）。
所以本轮的选择是：如实记 BLOCKED、把 F4 的证据与收窄写进校准记录 §11.9、把复测命令留给下一个窗口。

---

## 2026-09-17（四续）A7_coding：F4 根因定案（runtime 不采纳 run_id）+ Spec 11/12 完成

### F4 的真实根因 —— 不是网络，不是 provider，是接线

`adapters/foundation/runtime.py::_build_runtime_from_env()` 构造进程级 runtime 时**没有读
`AGENT_CONTRACT_RUN_ID`**，于是 `CodingFoundationRuntime` 在 observe 下回落到进程级随机 UUID：
所有 producer 证据写进 `<evidence_root>/<uuid>/events/`，而 L3 gate 只认
`<evidence_root>/<manifest run_id>/events/` → 症状正是「**0 事件 + required stage 未观测**」，
业务路径却完全正常。此前把 F4 归因为"网络抖动/provider 挂死"是**错的**。

证据链：
1. 磁盘事实：A6 上一次**跑通且判 PASS（resolution_rate=100%）**的运行留下 **102 条**格式完全正确
   的事件（`repository_commit=5e780fdd…`、`mode=observe`、`openai_compat`×51 +
   `langfuse_generation`×51），但它们位于 `<staging>/7e3c49b5-…/events/`。
2. 探针：同一脚本 → Coding `runtime.run_id=<uuid>`；Wiki `runtime.run_id=<env 值>`（正确）。
3. 代码对照：两仓 `_resolve_run_id()` **完全相同**；差异只在 `_build_runtime_from_env()` 是否读环境变量。

**A7_coding = `b763fc70b2bb902c08cdf7ed5f05e6508ad5c521`**（取代 A6 `5e780fd`；A_wiki 未变）
- 新增 `CONTRACT_RUN_ID_ENV` 并导出；`_build_runtime_from_env()` 读取 + `is_safe_run_id` 校验 +
  `run_id=run_id`（与 Wiki 同款机制；不安全值忽略并记结构化日志）。
- 回归钉子 `test_env_built_runtime_adopts_agent_contract_run_id` **实测 RED**（断言得到 uuid）→ GREEN；
  另加 `test_env_built_runtime_ignores_unsafe_run_id`。
- 修复后实证：L3 产出 **65 条事件落在正确 run_id**，`producer_coverage` 恢复为 3 对。

### A7 上的验证（Spec 11/12 已完成）

| 项 | 结果 |
|---|---|
| L1.1–L1.6 | 全部 exit 0（三哈希未变 / conformance 224 / tests/contracts **244** / --gate pr 8/8 / build） |
| 全量回归 | **641 passed / 3 skipped / 0 failed** |
| L2 | `foundation-0_1_0-c1-coding-replay` **PASS**（3 records / 3 sources，绑定 A7） |

**一次插曲值得记下**：首轮回归得到 `631 passed / **13 skipped** / 0 failed` —— Docker 守护进程在
跑测途中退出，10 个 docker 集成测试被跳过。**0 failed 不等于通过**；重启 Docker 重跑才得到
`641 passed / 3 skipped / 0 failed`。跳过数上升要当成"没测"，不能当成"没事"。

### 账本（suffix 41 事件，`suffix_hash=sha256:72e780c8…`）

```text
10 COMPLETE | 11 COMPLETE(pending) | 12 COMPLETE(pending) | 13 BLOCKED(pending) | 14/15 NOT_STARTED
```

### Spec 13 仍未闭合：原因已换成"预登记自相矛盾"（F8）

唯一剩余违反项始终是 `coding.benchmark.case_cost / normal`（§7.3:896 硬要求）。6 次尝试：

| 形态 | 次数 | 观测 |
|---|---|---|
| 撞冻结 `timeout_seconds=600` | 4 | provider 调用 122 / 156 / 204 / 232 次 |
| 业务结束但 Agent 调用 `Connection error.` | 1 | 546s / 64 次调用 |
| repo 就绪阶段 GitHub `EOF` | 1 | 环境抖动 |

对照：**同一 case 早前带插桩的一次运行以 32 次调用 / 444s 收敛并判 PASS(100%)** → 收敛可能，方差极大。

结论：冻结 manifest 的 `max_calls: 12` 与其预登记的 case（`max_iterations: 30`，实测最多 232 次调用）
**根本不兼容** —— 这是 Spec 11 Stage 0 预登记的缺陷。按 Spec 13，**没有**事后调高任何冻结字段，
而是如实记 `BLOCKED`，把"新候选重新推导预登记值"的恢复条件写进校准记录 §11.10。

### 教训

1. **"证据在哪"和"证据有没有"是两件事**：gate 报 0 事件时，我先后怀疑过网络、provider、docker、
   I/O，全错；真相是证据一直在，只是写在 gate 找不到的目录。**先把磁盘上的事实找干净，再谈归因**。
2. **对称性假设会骗人**：两仓 `_resolve_run_id` 逐字相同，差异只在调用点是否读环境变量 ——
   只读"看起来该负责的那个函数"永远发现不了。
3. **0 failed + 跳过数暴涨不是绿灯**：Docker 中途退出让 10 个集成测试静默跳过，必须重跑确认。
