# Pass 2 — 角色 Wiki 页面生成

**日期:** 2026-06-20
**状态:** 已完成
**关联:** 架构 v3 三遍独立提取，第二遍（原计划概念合成，调整为角色 Wiki 优先）
**分支:** feature/pass2-entity-extraction

---

## 一、背景

Pass 1 产出了 106 章的剧情骨架：4,129 事件 / 1,873 出场角色 / 957 概念。但 Pass 1 的角色信息是碎片化的——一个角色在 32 章中各有各的 `role_in_chapter`，无法直接回答"这个角色的性格是什么、她在整部剧情中的定位如何"。

Pass 2 做跨章合成：对每个出场角色，聚合其在全量原文中所有出场段落的对话和上下文，由 LLM 生成一份结构化的角色 Wiki 档案。核心增量不是新信息提取，而是 **Pass 1 碎片 → 可读的角色档案** 的聚合总结。

---

## 二、目标

1. 为 ~660 个有效角色生成结构化 Wiki 档案
2. 覆盖干员（381，含 M0 基线 + operators.json 档案）+ 多章 NPC（~254）+ 用户标注单章 NPC（~23）
3. 全量高质量：所有角色传入完整事件列表 + 原文，不因出场少而降低输入
4. 角色档案包含：性格特征、能力概况、战力等级、参与事件、跨章 summary
5. 产出 `data/extractions/v2_characters/` 目录

---

## 三、范围统计

| 来源 | 数量 | 说明 |
|------|------|------|
| 干员（M0 baseline） | 381 | 284 在 Pass 1 有出场记录，97 仅有档案 |
| 多章 NPC（≥2 章，去泛称） | 254 | 从 1,873 个 participant 名字聚合去重后 |
| 用户 KEEP 单章 NPC | ~23 | 见 `output/pass2_single_appearance_npc.md` |
| **合计** | **~658** | |

1,325 个单章非干员为泛称/路人/无名 NPC，不纳入 Pass 2。

---

## 四、不在此阶段的范围

- **概念/阵营/地点 Wiki**：Pass 2 仅做角色，概念/地点在后续阶段处理
- **角色间关系**：不单独提取关系类型（友谊/敌对/师徒等），通过 participated_events 隐式表达
- **名台词**：不提取
- **地点层级**：人工补全，不纳入 LLM 提取
- **IS 子页面抓取**：不再处理

---

## 五、输入源

| 数据源 | 用途 | 路径 |
|--------|------|------|
| Pass 1 提取结果 | 角色名 × 章节 × 事件列表 + line_range × participants | `data/extractions/v1_events/` |
| 原始对话文本 | 按 line_range 截取对应原文上下文（含前后各 3 行缓冲） | `data/stories/` |
| 干员档案 | M0 operators.json（race/nation/team/group + 完整 archive 文本） | `data/operators.json` |
| identity_map | 别名→规范名映射（120+ 条） | `config/identity_map.json` |
| 用户 NPC 标注 | KEEP 标注的单章 NPC | `output/pass2_single_appearance_npc.md` |

---

## 六、输出 Schema

每个角色一个 JSON 文件，路径 `data/extractions/v2_characters/{entity_id}.json`：

```json
{
  "entity_id": "character:{oid} 或 character:npc_{slug}",
  "name_zh": "规范中文名",
  "aliases": ["出场时使用的别名"],
  "archive": {
    "race": "种族（仅干员）",
    "affiliations": ["阵营归属（仅干员）"]
  },
  "summary": "跨章角色总结：性格全貌 + 能力定位 + 剧情弧线 + 关键转变。根据出场章数有最大字数限制，涵盖所有从原文可得的性格、能力和剧情信息。",
  "personality": {
    "traits": ["标签1", "标签2"],
    "description": "1-2句性格具体描述"
  },
  "abilities": {
    "description": "一句话能力概括",
    "power_level": "战场中坚·标准 或 信息不足"
  },
  "participated_events": [
    {
      "chapter": "章节名",
      "nodes": "大致节点或阶段描述",
      "event": "LLM识别的大型事件概述（琐碎对话忽略，同场战役多阶段合并）",
      "role": "角色在此事件中的作用和表现",
      "pass1_index": 3
    }
  ],
  "first_appearance": "首次出场章节名",
  "appearance_count": 15,

  "generated_at": "ISO 8601",
  "model": "deepseek-chat",
  "source_pass1_chapters": ["章名列表"],
  "source_pass1_event_indices": [3, 17, 42]
}
```

### 字段说明

**summary（核心字段）**
- 不是每章 role_in_chapter 的拼接，而是对角色整体的判断和跨章总结
- 覆盖：性格全貌、能力定位、剧情弧线、关键转变
- 琐碎对话（闲聊/问候）不列入 events，但其蕴含的角色信息需吸收到 summary 中
- 字数上限按出场章数分档：

| 出场章数 | summary 最大字数 |
|----------|-----------------|
| ≥ 20 | 500 字 |
| 10-19 | 350 字 |
| 5-9 | 250 字 |
| 2-4 | 150 字 |
| 1 | 100 字 |

**archive**
- 仅干员填充，直接从 operators.json 复制（race/nation→affiliations），LLM 不重新生成

**abilities.description**
- 一句话概括（源石技艺/战斗方式/特殊技能），不展开细项

**abilities.power_level**
- 采用明日方舟社区战力分级体系：

| 等级 | 说明 | 子级 |
|------|------|------|
| 战场中坚 | 标准作战人员，多数干员 | 下位 / 标准 / 上位 / 顶尖 |
| 军事精锐 | 精英战斗/军事人员 | 下位 / 标准 / 上位 / 顶尖 |
| 大国将军 | 国家级军事领袖 | 下位 / 标准 / 上位 / 顶尖 |
| 传奇英雄 | 跨国家喻户晓的传奇强者 | 下位 / 标准 / 上位 / 顶尖 |
| 王庭之主 | 萨卡兹王庭级存在 | 下位 / 标准 / 上位 / 顶尖 |
| 神明碎片 | 神明/巨兽的碎片或化身 | 下位 / 标准 / 上位 / 顶尖 |
| 崛起之物 | 正在觉醒/崛起的超凡存在 | 下位 / 标准 / 上位 / 顶尖 |
| 文明之敌 | 威胁文明级别的存在 | 下位 / 标准 / 上位 / 顶尖 |
| 灭世灾厄 | 灭世级别的终极威胁 | — |

- LLM 综合干员档案、参与事件、概念提及内容判断
- 保守评估：不确定时标注 "信息不足"
- 运行报告统计 "信息不足" 占比，目标 < 15%

**participated_events**
- LLM 自行判断"有意义的大型事件"，琐碎对话（闲聊/问候/转场）忽略
- 同一战役/冲突的多个阶段合并为一个条目
- 不使用 line_range（聚合后不再是单一原文位置），改用 chapter + nodes 定位
- pass1_index 保留对应 Pass 1 event 数组索引，方便回溯原文

**source_pass1_event_indices**
- 该角色参与的所有 Pass 1 事件索引列表，用于后续验证和统计

---

## 七、角色名规范化

Pass 1 的 participants 是 LLM 自由文本输出，存在以下不一致：

| 问题 | 示例 |
|------|------|
| 真名 vs 代号 | "陈晖洁"→"陈"、"Rosmontis"→"迷迭香" |
| 英文 vs 中文 | "Mon3tr"→"Mon3tr"、"Logos"→"Logos" |
| 带问号形式 | "凯尔希？""陈晖洁？"→ 去掉 `?` 后缀 |
| 别名字符串 | "科西切"="黑蛇"="不死的黑蛇"（同一个人） |
| identity_map 未覆盖的真名 | 后续发现的新别名 |

### 处理策略

1. **预处理阶段**：加载 identity_map（120+ 条）+ operators.json（420 干员名）→ 构建别名表
2. **角色聚合时**：对 Pass 1 的 1,873 个 participant 字符串做：
   - 去 `?` / `？` / `「」` / 括号内容后缀
   - identity_map 精确映射
   - 干员名精确匹配
   - 复合名 `·` 拆分匹配
   - 模糊匹配（difflib，threshold 0.6）
3. **未匹配的新别名**：输出到报告供人工确认，后续补充到 identity_map
4. **仍然分离的别名**（如"黑蛇" vs "科西切"）：依赖 identity_map 手动维护，不做 LLM 自动合并

---

## 八、提取策略

### 8.1 调用策略

**所有角色统一处理**：每角色一次独立 LLM 调用，传入完整事件列表 + 对应原文。不打包、不分档降级。

单章角色输入量自然小（几百行原文），高频角色输入量大（博士 ~40 章，估算 40-50K tokens），均远低于 DeepSeek 128K 上下文上限。

### 8.2 Prompt 构建

**user prompt 结构：**
```
角色名: {name_zh}
出场章节数: {N}
最大 summary 字数: {limit}

[干员档案]（仅干员）
基础信息: race={race}, nation={nation}, team={team}, group={group}
档案文本:
{archive_text}

## 出场事件与原文

### 第一章：{chapter_name}

**Event (index=3)**
节点描述: {从Pass 1 event推断}
原文:
  [line_start-line_end] {dialogue_text}
  参与情况: {role / significance from Pass 1}

**Event (index=7)**
...
```

**system prompt 核心规则：**
- 基于提供的对话原文总结，不编造
- summary 是核心产出，覆盖性格 + 能力 + 剧情定位 + 关键转折，不超过字数上限
- 琐碎对话（闲聊/问候/转场）不列入 participated_events，但其蕴含的角色信息需吸收到 summary 中
- participated_events 合并同一战役/冲突的多个阶段为一个条目
- power_level 按九级体系保守评估，不确定标注"信息不足"
- JSON 字符串内禁止英文双引号，用「」代替
- 严格遵守 JSON 格式，不包含 markdown 标记

### 8.3 原文截取

对每个 Pass 1 event，按 `line_range` 从原始 dialogue JSON 中截取原文，附带前后各 3 行上下文缓冲。

### 8.4 干员档案注入

从 `data/operators.json` 提取：
- `race` / `nation` / `team` / `group` → archive 字段（直接复制，非 LLM 生成）
- `archives` 中的完整文本（基础档案/综合体检/客观履历/临床诊断/档案资料一~四）→ 注入 user prompt

---

## 九、代码模块

基于 Pass 1 的 extraction/ 模块扩展：

| 文件 | 职责 | 状态 |
|------|------|------|
| `arknights_wiki/extraction/character_aggregator.py` | 角色名规范化 × 跨章聚合 × 原文截取 | 新增 |
| `arknights_wiki/extraction/prompt_builder.py` | 新增 `build_character_system_prompt()` + `build_character_user_prompt()` | 扩展 |
| `arknights_wiki/extraction/orchestrator.py` | 新增 `run_character_extraction()` + 批量编排 | 扩展 |
| `arknights_wiki/extraction/post_processor.py` | 新增 `validate_character_output()` | 扩展 |
| `tests/test_extraction/test_character_extraction.py` | TDD 测试 | 新增 |

已有模块复用：
- `llm_client.py` — 复用 create_client / call_llm
- `dialogue_loader.py` — 复用 load_chapter 读取原文
- `config.py` / `_utils.py` — 复用配置和工具函数

---

## 十、试跑计划

### 10.1 试跑角色

| 角色 | 章数 | 重点验证 |
|------|------|----------|
| 博士 | 40 | 最大输入压力测试、summary 500 字上限 |
| 凯尔希 | 32 | 长跨章总结、战力评估可回溯性 |
| 阿米娅 | 32 | Schema 完整性、事件合并正确性 |
| 能天使 | 7 | 中高频角色 summary 250 字质量 |
| 玛恩纳 | 5 | 关键 NPC 的事件参与和角色弧光 |
| 玛嘉烈·临光 | 6 | 大型活动主角的跨章表现 |
| 莫斯提马 | 4 | 低出场高频提及角色的信息聚合 |
| 刻俄柏 | 4 | 档案丰富型干员 |
| 塞雷娅 | 4 | 多势力归属角色的总结 |
| 望 | 4 | 岁兽阵营关键 NPC |
| 菲亚梅塔 | 2 | 中低频干员 |
| 余 | 2 | 岁兽碎片角色 |
| Guard | 5 | 多面性 NPC（整合→罗德岛） |
| 白垩 | 1 | 单章关键 NPC（尘影余音） |
| 龙舌兰 | 1 | 单章干员 |
| 奥达 | 1 | 单章 NPC（巴别塔） |

### 10.2 验证标准

- JSON 解析成功率 100%
- summary 无编造（可逐条回溯原文验证）
- participated_events 无琐碎对话混入
- power_level "信息不足" 占比 < 15%
- 输入 token 不超 128K 上限

---

## 十一、成本估算

| 类别 | 数量 | 每角色输入(估) | 总输入 tokens | 估算成本 |
|------|------|---------------|-------------|----------|
| ≥20 章 | ~3 | ~45K | 135K | ~$0.04 |
| 10-19 章 | ~8 | ~25K | 200K | ~$0.05 |
| 5-9 章 | ~80 | ~12K | 960K | ~$0.26 |
| 2-4 章 | ~250 | ~5K | 1.25M | ~$0.34 |
| 1 章 | ~317 | ~2K | 634K | ~$0.17 |
| **合计** | **~658** | | **~3.2M** | **~$0.86** |

输出 token 估算约 1M（每角色平均 ~1,500 tokens），成本 ~$1.10。
**总估算：~$2.0 USD**（DeepSeek chat：input $0.27/M, output $1.10/M）。

---

## 十二、文件结构

```
data/extractions/v2_characters/
  character:R001.json         # 阿米娅
  character:R002.json         # 凯尔希
  character:npc_guard.json    # Guard
  ...

output/
  pass2_run_report.md         # 全量运行报告（含 power_level 信息不足统计）
  pass2_trial_review/         # 试跑审阅 markdown
```

---

## 十三、下一步

1. 用户审阅本 Spec v2 → 确认
2. `writing-plans` 产出实施计划（文件变更 + 任务拆解 + 验收标准）
3. TDD 开发
4. 试跑 5 角色验证质量
5. 全量执行 → 质量审计 → 生成报告
