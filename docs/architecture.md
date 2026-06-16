# 明日方舟 LLM Wiki — 架构 v3

## mrfz 为什么失败了

原项目 187MB chunks.db，8 个阶段，累计 ~¥45 API 成本。核心产出全部残废：

| 产出 | 数据 | 为什么废了 |
|------|------|-----------|
| concepts | 1,475 条 | **全部** appear_node_count=0，一条都没链接到源文本 |
| relations | 2,314 条 | **全部** total_nodes=0，一条都没链接到源文本 |
| entities | 8,045 条 | 2,853 个角色 faction=未知（91%），4,916 个"概念实体"泛滥 |
| relation types | 80+ 种 | "admire"和"admiration"是两种关系，"leader"和"leadership"也是 |
| concept types | 25+ 种 | 从 "item" 到 "organization_info"，没有边界 |
| 概念碎片化 | 致命 | "源石"被拆成 71 个独立条目，无法合并 |

**根因链：**

```
逐 chunk 提取 (19,456 chunk × LLM)
  → 每个 chunk 独立提取，无上下文共享
    → 同名实体无法合并，同一概念被拆碎
      → Round2 聚合承诺合并碎片，但 LLM 做不到大规模去重
        → 聚合全部失败 (total_nodes=0, appear_node_count=0)
          → 数据存在但完全不可查询、不可验证
```

**教训：**
1. 不要让 LLM 做开放式的、没有 schema 约束的提取 → 类型爆炸
2. 不要逐 chunk 提取 → 章节级上下文才能正确识别实体和事件
3. 不要指望 LLM 做大规模聚合去重 → 聚合用 Python 规则，不用 LLM
4. 提取结果必须自带源引用 → 没有行号引用的数据无法验证
5. 一个 prompt 不要同时做多个维度的事 → LLM 分心，每个维度都做不好

---

## 核心设计

**三遍独立提取，每遍用不同的数据视角，互不依赖：**

```
第一遍：剧情骨架（每章一次）
  输入: 全章对话
  提取: 关键事件（数量随内容浮动）+ 出场人物 + 概念讨论（LLM 自行发现，不用关键词表）
  聚焦: 纵向通读，理清剧情链

第二遍：世界观概念（跨章收集）
  输入: 所有 109 章对话（独立扫描，不依赖第一遍）
  提取: 按概念收集所有相关段落 → 每个概念一次 LLM 合成定义
  聚焦: 横向扫视，发现定义和背景讨论

第三遍：角色档案（双源融合）
  输入: operators.json 档案 + 角色所有出场章节的战斗对话
  提取: 每个角色一次 LLM 生成 Wiki 页面
  聚焦: 定点检索，战斗力和能力评估
```

**三遍之间无依赖关系**，可以并行跑，也可以独立调试。

---

## 第一遍：剧情骨架

### 输入
- 每个章节的完整对话（`[说话者] 文本` 格式）
- 如果章节超大（>80K tokens），按批次拆分，每批 ~25K tokens

### LLM 输出

```json
{
  "chapter": "慈悲灯塔",
  "category": "main",
  "summary": "3-5 段章节摘要...",

  "events": [
    {
      "event": "威灵顿公爵率赤铁近卫队冲破食腐者包围",
      "type": "battle",
      "line_range": [1, 45],
      "participants": ["威灵顿公爵", "爱布拉娜"],
      "location": "加斯特里尔号附近战场",
      "significance": "展示公爵与塔拉领袖的军事协作"
    }
  ],

  "characters": [
    {
      "name": "威灵顿公爵",
      "type": "operator",
      "operator_id": null,
      "role_in_chapter": "指挥赤铁近卫队突破食腐者防线",
      "first_appearance_chapter": false
    }
  ],

  "concepts": [
    {
      "concept": "食腐者",
      "line_range": [23, 156],
      "discussion_summary": "食腐者作为萨卡兹的一支，在王庭军中承担前线作战职能",
      "is_substantive": true
    }
  ]
}
```

### 关键约束

**事件数量**：随内容密度自然浮动。密集战斗章节可能有 20-30 个，对话为主的章节可能只有 3-5 个。不设数量限制，不凑数，不遗漏。

**事件类型枚举**（固定，不允许 LLM 发明新类型）：
`battle | revelation | confrontation | negotiation | rescue | departure | sacrifice | meeting | emotional_breakthrough | other`

**角色提取规则**：
- 如果角色是干员 → name 用规范名（prompt 中注入 operators.json 角色列表），type=operator
- 如果角色是 NPC → name 保持一致拼写，type=npc
- 泛型角色（整合运动成员、罗德岛干员、士兵等）→ 不提取

**概念提取规则**：
- LLM 自行判断"这段对话是否在实质性讨论一个概念"
- 不是关键词匹配，不是提到一个词就算
- 角色说"整合运动占领了切尔诺伯格"不算讨论"整合运动"概念
- 角色说"整合运动的目标是为感染者争取权益"才算讨论
- 每个概念标注涉及的对话行号范围 + 是否实质讨论

**所有提取项必须标注行号范围**（line_range），对应源文件 lines 数组的索引。

### 输出位置
```
data/extractions/v1_events/{category}/{chapter}.json
```

### 成本
109 章 × ~34K tokens 输入 avg × ~4K tokens 输出 ≈ $2-4 (DeepSeek)

---

## 第二遍：世界观概念

### 流程

```
1. 扫描所有 109 章的对话原文（独立扫描，不依赖第一遍结果）
2. LLM 逐章输出概念讨论列表（同第一遍的概念提取，但单独做一遍）
3. Python 按概念名合并：收集概念 X 在所有章节的讨论片段
4. 每个概念一次 LLM 调用：输入所有相关片段 → 合成完整定义页面
```

### 为什么独立扫描而不是复用第一遍

第一遍聚焦剧情事件，概念提取可能被"主线叙事"带偏——LLM 会优先标注对剧情重要的概念，忽略世界观背景概念。第二遍独立扫描，让 LLM 专门关注"这里有没有世界观设定、背景知识、概念定义"。

### 概念页面结构

```json
{
  "concept": "源石",
  "definition": "源石是泰拉世界的基础能源矿物...",
  "origin": "源石的起源与天灾的关系...",
  "properties": ["感染生物体导致矿石病", "可用于施放源石技艺", "..."],
  "role_in_story": "源石在主线剧情中的核心地位...",
  "related_characters": ["阿米娅", "凯尔希", "..."],
  "related_factions": ["罗德岛", "整合运动", "..."],
  "related_concepts": ["矿石病", "源石技艺", "天灾"],
  "source_chapters": [
    {"chapter": "黑暗时代·上", "line_range": [100, 150], "excerpt": "..."}
  ]
}
```

### 成本
~30-50 个概念 × 1 次 LLM ≈ 30-50 次调用

---

## 第三遍：角色 Wiki

### 双数据源

| 源 | 内容 | 用途 |
|----|------|------|
| `data/operators.json` 档案 | 临床诊断、战斗经验、客观履历、档案资料1-4 | 角色基本设定、背景故事、能力描述 |
| 故事对话（全章扫描） | 角色所有出场、战斗场景、关键对话 | 剧情表现、能力展示、人际关系 |

### 流程

```
1. 从 operators.json 提取 381 个干员的档案文本
2. 扫描故事对话，收集每个角色的出场段落和战斗场景
3. 每个角色一次 LLM 调用：档案 + 故事片段 → Wiki 页面
4. 对于重要 NPC（非干员），纯从对话提取
```

### 角色页面结构

```json
{
  "name": "Logos",
  "basic_info": {
    "race": "萨卡兹（女妖）",
    "faction": "罗德岛",
    "occupation": "罗德岛精英干员"
  },
  "background": "Logos 的背景故事...",
  "personality": "性格特点...",
  "abilities": {
    "arts_type": "女妖咒术",
    "notable_techniques": ["骨哨", "血脉燃烧", "..."],
    "combat_level": "精英干员级，单人可拖住食腐者之王孽茨雷",
    "feats": [
      {"description": "以生命为代价压制提卡兹之血祭坛", "chapter": "慈悲灯塔", "source": "故事对话"}
    ]
  },
  "relationships": [
    {"character": "阿米娅", "relation": "精英干员/下属", "description": "..."}
  ],
  "story_appearances": [
    {"chapter": "慈悲灯塔", "role": "单人断后对抗孽茨雷", "key_moments": [...]}
  ],
  "source_refs": [
    {"type": "archive", "section": "档案资料一"},
    {"type": "story", "chapter": "慈悲灯塔", "line_range": [430, 520]}
  ]
}
```

### 战斗力评估

专设一个 section，不凭空编造，只从数据源中提取：
- **档案中的战斗描述**：临床诊断、战斗经验字段
- **故事中的战斗表现**：对战胜负、造成的伤害、承受的伤害、战术角色
- **其他角色评价**：其他角色对其能力的评价

### 成本
~380 干员 + ~50 重要 NPC × 1 次 LLM ≈ 430 次调用

---

## 总成本估算

| 阶段 | LLM 调用 | 每次 ~tokens | 估算成本 |
|------|---------|-------------|---------|
| 第一遍 | 109 | 34K in / 4K out | $2-4 |
| 第二遍 | ~50 概念 | 10K in / 3K out | $1-2 |
| 第三遍 | ~430 角色 | 5K in / 2K out | $3-5 |
| **合计** | **~590** | | **$6-11** |

使用 MiniMax M3 约 $8-15。

---

## 数据存储

简化后的 SQLite 表（在现有基础上砍掉不需要的）：

```sql
-- 实体注册表
CREATE TABLE entities (
    id         TEXT PRIMARY KEY,
    type       TEXT NOT NULL,  -- character, faction, region, concept
    name_zh    TEXT NOT NULL,
    meta_json  TEXT DEFAULT '{}'
);

-- 第一遍提取结果（原始 LLM 输出，含完整 line_range 引用）
CREATE TABLE chapter_extractions (
    chapter    TEXT PRIMARY KEY,
    category   TEXT,
    content_json TEXT NOT NULL
);

-- Wiki 页面（三遍提取的最终产物）
CREATE TABLE wiki_pages (
    entity_id  TEXT NOT NULL,
    page_type  TEXT NOT NULL,  -- character, faction, region, concept, chapter
    content_md TEXT NOT NULL,
    source_refs TEXT DEFAULT '[]',
    version    INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
```

**砍掉的表：**
- `source_index` — 提取结果自带 line_range，不需要独立倒排索引
- `entity_aliases` — 干员别名在 `config/identity_map.json` 维护，聚合时直接用

---

## 执行顺序

```
1. 第一遍试跑 2-3 章 → 验证事件/角色/概念提取质量
2. 第一遍全量 109 章
3. 第二遍概念扫描 → 概念页面生成
4. 第三遍角色页面生成
5. FAISS 索引 → 检索验证
```

---

## 与 mrfz 的关键区别

| | mrfz | 新架构 |
|---|------|--------|
| 提取单元 | 19,456 chunks | 109 chapters |
| 提取遍数 | 一轮，7 维度混在一起 | 三轮，每轮专注一个视角 |
| 事件提取 | 无独立事件提取 | 独立第一遍，数量随密度浮动 |
| 概念提取 | LLM 开放提取，无源链接 | LLM 发现 + 行号标注，跨章合成 |
| 角色数据 | 仅对话 | 档案 + 对话双源 |
| 源引用 | 全部丢失 (total_nodes=0) | 每项自带 line_range |
| 概念聚合 | LLM Round2（全失败） | Python 规则合并 + LLM 合成定义 |
| 可验证性 | 零（无源引用） | 每项可追溯到具体章节行号 |
