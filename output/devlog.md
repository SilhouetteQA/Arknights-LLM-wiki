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
