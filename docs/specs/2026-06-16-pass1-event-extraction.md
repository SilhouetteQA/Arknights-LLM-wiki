# Pass 1 — 剧情骨架提取 (事件 + 角色 + 概念位置标注)

**日期:** 2026-06-16
**状态:** 已完成
**关联:** 架构 v3 三遍独立提取，第一遍
**分支:** feature/pass1-event-extraction

---

## 一、背景

架构 v3 将知识提取拆为三遍独立扫描。第一遍聚焦剧情骨架：每章通读全量对话，提取关键事件、出场人物、概念讨论位置。

核心原则：
- **单章完整处理**：109 章除相变临界和长夜临光外，全部单次喂入 128K 上下文
- **数量随密度浮动**：事件不设上下限，战斗章自然多，对话章自然少
- **必须标注行号**：每个提取项附带 line_range，可追溯到源文件具体行

---

## 二、目标

1. 对 109 章逐章提取事件、角色、概念位置
2. 试跑 6 章人工验证质量后全量执行
3. 产出 `data/extractions/v1_events/` 供第二遍概念合成和第三遍角色 Wiki 使用
4. 角色名后处理对齐到规范名（identity_map + 模糊匹配）

---

## 三、不在此阶段的范围

- 概念跨章合成 → Pass 2
- 角色 Wiki 页面生成 → Pass 3
- FAISS 索引 → Pass 3 之后
- 关系提取、时间线、故事弧 → 后续阶段

---

## 四、输入层

### 4.1 数据源

```
data/stories/{category}/{chapter}/*.json
```

每个 JSON 包含一条 story node 的对话行数组：`[{speaker, type, text}, ...]`。

### 4.2 对话拼接

遍历章节目录下按 node 排序的全部 JSON，逐行拼接为：

```
[说话者] 文本
[说话者] 文本
...
```

每行对应一个行号索引（从 1 开始），存入 `lines` 数组供 LLM 输出的 line_range 引用。

非对话类型行（type != 'dialogue'，如旁白/描述）也保留在 lines 中，但不标注 speaker。

### 4.3 分批策略

| 条件 | 策略 | 涉及章节 |
|------|------|----------|
| ≤128K tokens | 单次全量喂入 | 107 章 |
| >128K tokens | 按自然 node 边界切成 2 批，在总 token 数一半处最近 node 边界切断 | 相变临界、长夜临光 |

两批各自独立调用 LLM，Python 合并去重。

---

## 五、LLM 层

### 5.1 模型

- 模型: MiniMax-M3
- API: OpenAI SDK, base_url=https://api.minimaxi.com/v1
- temperature: 0.1
- max_tokens: 16384 (mrfz 经验：65536 导致 M3 think 过长，16384 最优)
- 环境变量: `minimax_api`

### 5.2 Prompt 设计

**系统提示**要点：
- 角色设定：明日方舟剧情深度分析师
- 严格要求 JSON 输出，不含 markdown 代码块标记
- 事件类型由 LLM 用 snake_case 英文自由描述（如 `battle`, `political_intrigue`, `sacrifice`），不设枚举
- 泛型角色过滤规则
- 概念"实质讨论"vs"提及"区分标准

**用户提示**结构：
```
以下是「{chapter}」章节的完整对话。请提取结构化信息。

## 对话
{拼接后的全章对话文本}

## 输出 JSON 格式
{...schema...}

## 规则
- 必须基于对话内容，不要编造
- 泛型角色不提取为 characters
- concepts_discussed 只记录被实质性讨论的概念
- 事件类型用 snake_case 英文描述，覆盖剧情中各种可能的场景
```

### 5.3 LLM 输出 Schema

```json
{
  "chapter": "章节名",
  "category": "main|side|special",
  "summary": "3-5段章节摘要，按时间顺序，覆盖主要剧情推进",

  "events": [{
    "event": "事件描述（一句话）",
    "type": "snake_case 事件类型，如 battle, political_intrigue, sacrifice",
    "line_range": [起始行号, 结束行号],
    "participants": ["角色名"],
    "location": "发生地点",
    "significance": "剧情意义（一句话）"
  }],

  "characters": [{
    "name": "角色名（尽可能用规范名）",
    "type": "operator|npc",
    "role_in_chapter": "本章中的角色和行动",
    "first_appearance_chapter": true
  }],

  "concepts": [{
    "concept": "概念名",
    "line_range": [起始行号, 结束行号],
    "discussion_summary": "本章中如何被讨论（仅记录被实质性讨论的概念）",
    "is_substantive": true
  }]
}
```

### 5.4 事件类型

不设枚举，LLM 自行用 snake_case 英文描述事件性质。prompt 中给出 8-10 个常见类型作为参考示例，但不限制 LLM 创造新类型。

常见参考类型: `battle`, `ambush`, `siege`, `retreat`, `infiltration`, `revelation`, `investigation`, `negotiation`, `alliance`, `betrayal`, `confrontation`, `sacrifice`, `rescue`, `departure`, `reunion`, `ceremony`, `emotional_breakthrough`, `flashback`, `disaster`, `planning`, `political_intrigue`, `assassination`, `rebellion`, `training`, `dream_vision`

### 5.5 角色提取规则

- operator 角色 → 使用规范名（由后处理对齐）
- NPC 角色 → 保持一致的拼写
- 泛型角色过滤：整合运动成员、罗德岛干员、士兵、居民、路人等无名群体不提取
- first_appearance_chapter: 该角色在本章是否首次登场（基于 LLM 对剧情的理解判断）

### 5.6 概念标注规则

LLM 需区分"讨论"和"提及"：
- 角色在**解释、描述、辩论某个世界观的本质/机制/历史** → 标注为概念讨论
- 角色仅将名词作为标签使用（如"食腐者来了！准备战斗"） → 不标注

prompt 中给出 2-3 组正反例帮助 LLM 建立判断标准。

---

## 六、后处理层

### 6.1 角色名对齐

```
LLM 输出角色名
  → 精确匹配 operators.json 中 name_zh
  → 匹配 identity_map.json 中 key
  → 模糊匹配 (Levenshtein distance ≤ 2 或 包含关系)
  → 未能对齐的保留原名，记录日志供人工审阅
```

### 6.2 事件去重

同一章节内，两个 event 的 event 字段文本相似度 >0.85 时合并为一条，保留更详细的版本。

### 6.3 分批合并

被拆分的章节（相变临界、长夜临光）：
- events 按 line_range 排序，相邻事件去重
- characters 同名合并，保留首次出现的 first_appearance_chapter 值
- concepts 同 concept 名合并 line_range 范围
- summary 按批次顺序拼接

### 6.4 合法性校验

- chapter/category 字段非空
- events 数组至少 1 条
- 每个 event 的 event/type 字段非空
- line_range 为有效整数对且不超出输入行数

---

## 七、输出层

### 7.1 文件路径

```
data/extractions/v1_events/{category}/{chapter}.json
```

### 7.2 最终文件结构

```json
{
  "chapter": "慈悲灯塔",
  "category": "main",
  "processed_at": "2026-06-16T...",
  "model": "MiniMax-M3",
  "batch_count": 1,
  "summary": "...",
  "events": [...],
  "characters": [...],
  "concepts": [...],
  "stats": {
    "tokens_in": 0,
    "tokens_out": 0,
    "elapsed_s": 0
  }
}
```

含 `processed_at`、`model`、`batch_count` 等元信息用于追溯。

---

## 八、试跑验证

### 8.1 试跑章节

| 章节 | 类别 | 估算 tokens | 目的 |
|------|------|-------------|------|
| 黑暗时代·上 | main | ~35K | 对话为主，事件密度低 |
| 怒号光明 | main | ~110K | 终章高潮，战斗+情感密集 |
| 慈悲灯塔 | main | ~127K | 已测试过，验证正式 prompt 效果 |
| 孤星 | side | ~116K | 高密度 lore，概念讨论丰富 |
| 相见欢 | side | ~70K | 角色互动为主的 side story |
| 长夜临光 | side | ~129K | 超大章，测试分批合并逻辑 |

### 8.2 检查项

每个试跑章生成一个审阅用 Markdown 文件（`output/trial_review/{chapter}.md`），包含：
- 章节摘要
- 事件列表（序号 + 类型 + 描述 + 参与角色 + 行号范围）
- 角色列表（名称 + 类型 + 本章角色）
- 概念列表（名称 + 讨论摘要 + 行号范围）
- 原文行号引用（关键事件对应的原文对话片段，方便核对）

人工逐章审阅：
- [ ] 事件是否遗漏重要剧情节点
- [ ] 事件类型描述是否准确
- [ ] 角色名是否规范（尤其 operator 角色）
- [ ] NPC 是否正确识别（未被过滤的真正角色 vs 应过滤的泛型角色）
- [ ] 概念标注是否准确区分"讨论"和"提及"
- [ ] 长夜临光分批合并后事件链是否连贯
- [ ] line_range 指回原文是否能定位到对应对话

### 8.3 通过标准

用户逐章确认后，进入全量 109 章执行。

### 8.4 通过方式

人工审阅试跑 Markdown，逐项核对事件/角色/概念质量，6 章全部确认后进入全量 109 章执行。

---

## 九、全量执行

试跑通过后，脚本顺序执行 109 章：

1. 遍历 `data/stories/{main,side,special}/` 下所有章节目录
2. 每章：拼接对话 → 判断是否需分批 → 调用 LLM → 后处理 → 落盘
3. 记录每章耗时和 token 用量
4. 预计总成本：109 次调用 × ~0.02-0.04 USD/次 ≈ $2-4

---

## 十、代码组织

```
arknights_wiki/
├── extraction/
│   ├── __init__.py
│   ├── dialogue_loader.py    # 对话拼接 + lines 数组构建
│   ├── llm_client.py          # MiniMax M3 调用封装
│   ├── prompt_builder.py      # prompt 模板 + 组装
│   ├── post_processor.py      # 角色名对齐 + 事件去重 + 分批合并
│   └── orchestrator.py        # 编排：遍历章节 → 调用 → 后处理 → 落盘
```

不涉及 store/ 层（数据库），第一遍产出为纯 JSON 文件。

---

## 十一、依赖

- Python 3.12+
- openai SDK（已有，test_extraction.py 已在用）
- json, pathlib, difflib（标准库）
- 不使用 langchain 或其他 LLM 框架

---

## 十二、风险与取舍

| 风险 | 应对 |
|------|------|
| LLM 输出 JSON 解析失败 | 提取 `{...}` 段落后重试；连续 3 次失败则记录原始输出并跳过 |
| MiniMax M3 输出含 `<think>` 标签 | 解析前 strip 掉 `<think>...</think>` 段 |
| 泛型角色误提取 | prompt 明确过滤规则 + 后处理正则二次过滤 |
| 概念标记遗漏 | Pass 2 独立扫描兜底，第一遍过了的不影响第二遍 |
| 超大章分批合并导致事件断裂 | 每批在 node 边界切断 + 合并时相邻事件相似度检测 |
| 角色名对齐失败 | 记录 unmatched_names 日志，试跑阶段人工补充到 identity_map |
