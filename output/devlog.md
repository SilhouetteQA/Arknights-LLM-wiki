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
