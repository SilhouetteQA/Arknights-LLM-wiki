# CONTEXT.md — 明日方舟剧情 LLM Wiki

## 领域术语

| 术语 | 定义 |
|------|------|
| **Pass 1** | 剧情骨架提取 — 从原始对话中提取事件/概念/阵营/地点，产出 v1_events/ |
| **Pass 2** | 角色 Wiki 页面生成 — 跨章聚合角色出场→LLM 生成角色百科，产出 v2_characters/ |
| **Pass 3** | 世界观实体提取 — 概念/阵营/地点 Wiki 页面，产出 v3_wiki/ |
| **v3_wiki** | 当前数据基线：1251 概念 + 247 阵营 + 257 地点 + 642 角色，FAISS 6666 向量 |
| **LangGraph Agent** | Phase 4 核心：Query Router → SimpleSearch / ReAct Agent → 7 tools → 流式 SSE 回答 |
| **PRTS 终端** | 前端 UI：双栏 SSE 聊天界面，赛博朋克终端风格 |
| **CASUAL persona** | 固定回答风格：口语化补课，像朋友聊天，避免术语堆砌和事件罗列 |
| **大地巡旅** | 官方设定集《Terra: A Journey》，426 页 OCR 文本，存放于 data/lorebook/ |

## Persona

系统固定使用 **CASUAL** persona：
- 用口语化方式解释，像朋友聊天
- 先给一句话核心答案，再展开细节
- 避免堆砌专有名词，首次出现的术语用一两句解释
- 不要罗列事件清单，把事件融入连贯叙述
- 内容完整性优先，不设字数限制

## 意图分类（7 类）

| 意图 | 典型问法 | 检索策略 |
|------|---------|---------|
| `concept_definition` | "X是什么" | get_entity_page 优先，避免广撒网 |
| `chapter_summary` | "X活动讲了什么" | get_chapter_summary + 对应章节 events |
| `character_profile` | "X的性格/战力" | get_entity_page + search_events(entity=X) |
| `causal_reasoning` | "为什么X会Y" | search_timeline + semantic_search |
| `comparison` | "A和B的区别" | 分别 get_page 两个实体 |
| `fact_lookup` | "X的出生地" | 精确 get_page，简短回答 |
| `list_enumeration` | "有哪些兽主" | search_wiki 宽搜 + 结构化列表输出 |

## 路由规则

- 多实体 / 跨章节 / 世界观概念 → 强制 `complex`（LangGraph Agent 多步检索）
- 包含深度关键词（导致/原因/对比/演变/势力格局）+ cross_arc → `complex`
- 简单事实查询 → `simple`（直接检索 + LLM 回答）

## 实体索引

预构建双向索引 `entity_source_map.json`，数据源：
- Pass 1 事件 (v1_events/)
- 原始故事文本 (data/stories/，仅存储路径，按需读取)
- 干员档案 (operators.json)
- 大地巡旅 (data/lorebook/terra_a_journey/)
- 实体间双向关联（entity↔faction↔location↔character）

## 回答格式约束

- 禁止输出 "[来源N]" 引用标记
- 禁止逐条列举事件（如 "事件1: ... 事件2: ..."）
- 用自己话重新组织，不复制粘贴原文
- 忽略与问题无关的参考资料
