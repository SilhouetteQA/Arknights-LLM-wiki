# LangGraph AI Agent 设计规格

> **状态**: 已完成

## 目标

构建基于 LangGraph 的《明日方舟》剧情问答 AI Agent，利用三遍提取（Pass 1 事件/Pass 2 角色/Pass 3 世界观）的结构化数据做 RAG 问答。

## 架构总览

```
用户问题
    │
    ▼
┌──────────────┐
│ query_router │  本地规则: simple / complex
└──┬───────┬──┘
   │       │
   ▼       ▼
┌──────┐ ┌──────────────────┐
│simple │ │ complex          │
│search │ │ LangGraph Agent  │
│      │ │ (ReAct 多步检索)  │
└──┬───┘ └────────┬─────────┘
   │              │
   ▼              ▼
   统一 SSE 流式输出 (FastAPI)
```

## 模块划分

| 模块 | 路径 | 职责 |
|------|------|------|
| `router` | `arknights_wiki/agent/router.py` | 复杂度判断，实体提取，问题类型分类 |
| `simple_search` | `arknights_wiki/agent/simple_search.py` | 多层检索+合并+LLM直接回答 |
| `graph` | `arknights_wiki/agent/graph.py` | LangGraph 图定义，ReAct 循环 |
| `tools` | `arknights_wiki/agent/tools.py` | 6 个 Tool 实现，@tool 装饰器 |
| `retrieval` | `arknights_wiki/agent/retrieval.py` | Wiki/Event/Dialogue 数据访问层 |
| `vector_index` | `arknights_wiki/agent/vector_index.py` | FAISS 索引构建 + 语义搜索 |
| `server` | `arknights_wiki/agent/server.py` | FastAPI + /chat SSE 端点 |
| `state` | `arknights_wiki/agent/state.py` | AgentState TypedDict 定义 |
| `eval` | `arknights_wiki/agent/eval.py` | 质量评估（复用 eval/ 框架） |

## 数据资产

| 数据源 | 格式 | 数量 | 内容 |
|--------|------|------|------|
| Pass 1 Events | JSON/章 | 106 章 | 事件列表 + concepts/factions/locations |
| Pass 2 Characters | JSON/角色 | 642 个 | 性格、战力、剧情事件、人际关系 |
| Pass 3 Concepts | Markdown | 1251 个 | 定义、概述（多源融合）、剧情事件+原文 |
| Pass 3 Factions | Markdown | 247 个 | 定义、概述、成员、剧情事件 |
| Pass 3 Locations | Markdown | 257 个 | 定义、概述、剧情事件 |
| Timeline | Markdown | 1 个 | 49 个历史事件 |
| Raw Stories | JSON/章 | 106 章 | 原始对话，scene/line 结构 |

## FAISS 向量检索

### 设计原则

参照 mrfz 的向量检索模式：所有可检索内容统一编码为嵌入向量存入 FAISS，通过 chunk_id 命名约定精确追溯到源实体。

### Chunk ID 约定（溯源关键）

```
concept:源石          → data/extractions/v3_wiki/concepts/源石.md
faction:罗德岛         → data/extractions/v3_wiki/factions/罗德岛.md
location:切尔诺伯格    → data/extractions/v3_wiki/locations/切尔诺伯格.md
character:阿米娅       → data/extractions/v2_characters/Amiya.json
event:黑暗时代·上_0    → data/extractions/v1_events/main/黑暗时代·上.json (event index 0)
summary:黑暗时代·上     → data/extractions/v1_events/main/黑暗时代·上.json (chapter summary)
timeline:759           → data/extractions/v3_wiki/timeline.md (year 759)
dialogue:node_id_0     → data/stories/{category}/{chapter}.json (scene 0)
```

### 索引构建

```
build_index.py (一次性离线脚本)

输入:
  - v3_wiki/concepts/*.md     → 1251 chunks (每页=1 chunk)
  - v3_wiki/factions/*.md     →  247 chunks
  - v3_wiki/locations/*.md    →  257 chunks
  - v2_characters/*.json      →  642 chunks (name+personality+power+story_events)
  - v1_events/**/*.json       → ~4000 chunks (events) + ~106 chunks (summaries)
  - v3_wiki/timeline.md       →   49 chunks (年表事件)
  - stories/**/*.json         → raw dialogue chunks (可选, 按需)

流程:
  1. 遍历数据源 → 每实体/事件生成 chunk (chunk_id + text)
  2. BGE-small-zh-v1.5 编码 (normalize=True, max_seq_length=512)
  3. FAISS IndexFlatIP 写入 data/index/faiss.index
  4. chunk_id→元信息映射写入 data/index/chunk_map.json
输出: data/index/faiss.index + chunk_map.json
```

### 语义搜索

```python
def semantic_search(query: str, top_k: int = 20) -> list[dict]:
    """编码 query → FAISS 内积搜索 → 返回 top_k chunks + 元信息"""
    vec = model.encode(query, normalize_embeddings=True)
    scores, indices = index.search(vec, top_k)
    # 通过 chunk_map 解析 chunk_id → entity_type, name, file_path
    return [{"chunk_id": ..., "score": ..., "entity_type": ..., "name": ..., "text": ...}]
```

### 为何能精确识别实体

- 向量检索返回的是 chunk_id，chunk_id 编码了实体类型+实体名
- 例如搜"整合运动女领袖"，FAISS 返回 `character:塔露拉`（score 0.87），chunk_map 解析为 entity_type=character, name=塔露拉, file=v2_characters/塔露拉.json
- 后续可直接调用 get_entity_page("塔露拉", "character") 获取完整信息
- 精确+FTS 仍然是 Layer 0/1 的主力，FAISS 是 Layer 2 语义兜底

## Tool 层（7 个工具）

### 1. search_wiki
全文搜索 wiki 页面（概念/阵营/地点/角色）。
```
参数: query (str), category (concept|faction|location|character, 可选)
返回: 匹配页面名 + 匹配段落摘录
实现: 文件名精确匹配 + 内容子串搜索
```

### 2. get_entity_page
按名称获取完整 wiki 页面。
```
参数: name (str), entity_type (concept|faction|location|character)
返回: 完整 markdown 内容
实现: 直接文件读取
```

### 3. search_events
搜索 Pass 1 事件。
```
参数: entity (str), event_type (str, 可选), chapter (str, 可选), limit (int=20)
返回: 事件列表，含标题、描述、参与者、地点、行号
实现: 加载 Pass 1 JSON，按字段过滤
```

### 4. search_dialogue
全文搜索原始对话。
```
参数: query (str), chapter (str, 可选), limit (int=20)
返回: 对话片段，含说话人、文本、场景上下文
实现: 加载 story JSON，子串搜索对话行
```

### 5. search_timeline
搜索历史时间线。
```
参数: query (str), limit (int=20)
返回: 时间线事件，含年份、描述、涉及实体
实现: 解析 timeline.md，关键词匹配
```

### 6. get_chapter_summary
获取章节摘要。
```
参数: chapter (str)
返回: 章级叙事摘要 + 事件列表
实现: 加载 Pass 1 JSON 文件的 summary 字段
```

### 7. semantic_search
FAISS 语义搜索（BGE 嵌入向量内积相似度）。
```
参数: query (str), top_k (int=20)
返回: 语义相关 chunks，含 chunk_id → entity_type + name + text + score
实现: 编码 query → FAISS.search → chunk_map 解析实体
用途: 处理描述性/模糊问题 ("那个整合运动的女领袖" → 塔露拉)
```

## Query Router

### 流程

1. 本地实体提取：identity_map.json + operators.json + wiki 文件名 + 正则（章节/活动名）
2. 问题类型推断：关键词匹配 → event/character/worldview/comparison/summary
3. 时间范围推断：cross_arc（默认，无明确章节限定时）/ arc / chapter
4. 复杂度分类（纯本地规则）：

| 条件 | 判定 |
|------|------|
| comparison 类型 | complex |
| cross_arc + 因果/演变/时间线/排名关键词 | complex |
| cross_arc + clean_entities < 3 | complex |
| 其余所有情况 | simple |

5. entities=[] 时 LLM 兜底：轻量 LLM 提取实体关键词

### 输出

```python
RouteResult(complexity, question_type, entities, time_scope, reason, source)
```

## Simple Search（简单路径）

不经过 LangGraph，直接多层检索 → 合并 → LLM 回答。

```
Layer 0: Wiki 精确匹配 (get_entity_page × N)     ← 最高权重
Layer 1: Events 结构化查询 (search_events)        ← 按实体+章节
Layer 2: FAISS 语义搜索 (semantic_search)         ← BGE-M3 编码 → 内积搜索 → chunk_map 解析实体
Layer 3: Dialogue 兜底 (search_dialogue)          ← 仅结果不足时触发
    ↓
Merge & Rank: wiki > event > faiss > dialogue
    token 预算: 默认 8K，概括题 12K
    ↓
LLM Answer: 1 次 chat_complete(system_prompt + sources + question)
    输出: answer + source_refs
```

System prompt 要求：连贯叙事、按时间顺序、文中自然引用 [1][2]、用「」引用原文。

## Complex Agent（LangGraph ReAct 路径）

### State

```python
class AgentState(TypedDict):
    messages: list          # 完整对话历史（含 tool_call/tool_result）
    question: str           # 原始问题
    collected_docs: list    # 已收集的文档片段
    iteration: int          # 当前迭代次数
    route: dict             # 路由分类结果
```

### Graph 结构

```
START → call_model (agent_node)
           ├─ tool_call → tool_node → call_model
           └─ final_answer → synthesize_node → END
```

### 节点

- **call_model**: LLM + 6 tool 定义 → 决策下一步（tool_call 或 final_answer）
- **tool_node**: 执行 retrieval 函数，ToolMessage 追加回 messages
- **synthesize_node**: 综合所有 collected_docs + messages，生成最终回答

### 停止条件

- LLM 输出 final_answer 信号
- iteration >= 8
- 连续 2 轮无新文档

### Agent System Prompt 要点

- 可用工具及使用场景（7 tools: search_wiki, get_entity_page, search_events, search_dialogue, search_timeline, get_chapter_summary, semantic_search）
- 检索优先级：Wiki → Events → FAISS 语义 → Dialogue
- 精确实体用 search_wiki / get_entity_page，模糊描述用 semantic_search
- 发现关键实体时用 get_entity_page 深入
- 因果链/时间线问题必须用 search_timeline
- 信息足够后停止检索

## Web API

```
POST /chat
  body: { "question": "...", "history": [...] }
  → SSE stream:
    route → plan (complex) → step (complex) → token → sources → done
```

前端: 原生 HTML+CSS+JS，由 FastAPI 静态托管。

## 评估集成

复用 `arknights_wiki/eval/` 框架（OpenAI Evals + modelgraded YAML）。

| 维度 | 方法 | 目标 |
|------|------|------|
| 路由准确率 | 人工标注 50 条，对比 router 输出 | >95% |
| 回答完整性 | LLM judge 评分 1-5 | >=4.0 |
| 来源可追溯 | 规则检查引用是否对应真实数据源 | 100% |
| 幻觉检测 | LLM judge 判断有无无证据内容 | <5% |

评估数据: `data/eval/agent_questions.jsonl`（手工构建，~50 条）
门禁: 完整度 < 4.0 或幻觉率 > 5% → 不通过

## 实施约束

- 模型: DeepSeek v4-flash（与现有提取 pipeline 一致）
- 嵌入模型: BGE-small-zh-v1.5（与 mrfz 一致，本地缓存，FP16，max_seq_length=512）
- FAISS 索引: IndexFlatIP（内积相似度，写入 data/index/faiss.index）
- 不引入 langchain，仅用 langgraph + sentence_transformers + faiss-cpu
- 简单路径 1 次 LLM 调用，复杂路径 3-10 次
- 开发流程: TDD → Subagent 并行 → Codex Review

## 阶段预估

| 阶段 | 内容 | 预估 |
|------|------|------|
| 1 | vector_index: 索引构建 + chunk_map + semantic_search | TDD, ~10 tests |
| 2 | retrieval: 数据访问层 + 7 tools | TDD, ~10 tests |
| 3 | query_router | TDD, ~10 tests |
| 4 | simple_search | TDD, ~10 tests |
| 5 | LangGraph agent (graph + state + synthesize) | TDD, ~10 tests |
| 6 | FastAPI server + SSE | ~5 tests |
| 7 | 评估数据 + 跑评估 | 50 条标注 |
| 8 | 前端 UI | 单页 HTML |
