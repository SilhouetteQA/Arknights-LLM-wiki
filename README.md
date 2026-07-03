# 明日方舟剧情 LLM Wiki（重构版）

基于 PRTS Wiki 抓取的《明日方舟》全量剧情知识库。结构化对话存储 + 知识图谱 + FAISS 向量检索 + LLM RAG 问答。

> **来源项目**: `D:\AI project\mrfz`（保持不动，逐步迁移）
> **重构目标**: 清理技术债务、收敛代码组织、完善工程质量

---

## 项目状态

| 维度 | 值 | 说明 |
|------|-----|------|
| Phase | 4 - LangGraph Agent | v2 优化完成：实体噪声/路由过拟合/检索漏配/叙事逻辑已修复 |
| 分支 | feature/langgraph-agent | Agent pipeline 系统性优化 |
| 数据 | v3_wiki + 实体索引 | 6666 FAISS 向量, 5213 实体索引, 25300 双向引用 |
| 测试 | 76/76 passed | agent 测试全通过 |
| 前端 | PRTS 终端风格 | 双栏 SSE 聊天 UI + QA 日志机制 |

---

## 快速启动

### 1. 启动 Agent 服务

```bash
cd "D:\AI project\Arknights LLM Wiki"
python -m arknights_wiki.agent.server
```

服务启动后访问 **http://localhost:8000** 进入 PRTS 终端对话界面。

### 2. 运行评估

```bash
python scripts/run_agent_eval.py
```

评估报告输出到 `output/agent_eval_*.json` 和 `output/agent_eval_report.md`。

### 3. 构建/更新索引

```bash
# FAISS 向量索引
python scripts/build_agent_index.py

# 实体双向索引
python scripts/build_entity_index.py
```

---

## 技术栈

| 层级 | 方案 | 说明 |
|------|------|------|
| 语言 | Python 3.12+ | 保持 |
| 数据存储 | SQLite | 精简单表职责，JSON 仅归档 |
| 向量检索 | FAISS + BGE-small-zh-v1.5 | 抽象为独立模块 |
| LLM API | OpenAI SDK (MiniMax M2.5 + DeepSeek) | 剥离 tokenizer，结构化成本日志 |
| Web 框架 | FastAPI + SSE | 保持 |
| 前端 | 原生 HTML+CSS+JS | CSS/JS 从单文件拆分为独立文件 |
| 代码组织 | arknights_wiki/ Python 包 | 拆分 God Object，每表一个 repository |
| Agent 框架 | LangGraph | ReAct Agent + 8 tools |
| 依赖管理 | pyproject.toml (PEP 621) | 从 requirements.txt 升级 |
| 测试 | pytest | 逐模块补测试 |

---

## 目录结构

```
Arknights LLM Wiki/
├── README.md
├── pyproject.toml
├── CONTEXT.md                    # 领域术语
├── docs/
│   ├── specs/                    # 设计规格
│   ├── plans/                    # 实施计划
│   └── adr/                      # 架构决策记录
├── arknights_wiki/               # 主代码包
│   ├── config.py
│   ├── extraction/               # Pass 1/2/3 提取模块
│   ├── agent/                    # LangGraph Agent
│   │   ├── server.py             # FastAPI + SSE 服务
│   │   ├── static/               # 前端 (index.html + CSS + JS)
│   │   ├── router.py             # 查询路由（意图识别+实体提取+复杂度）
│   │   ├── simple_search.py      # Simple 检索路径
│   │   ├── graph.py              # Complex LangGraph ReAct Agent
│   │   ├── tools.py              # 8 个检索工具
│   │   ├── retrieval.py          # Wiki/Event/Dialogue/Timeline 数据层
│   │   └── prompts.py            # LLM 提示词模板
│   ├── eval/                     # 评估器
│   ├── store/                    # SQLite 数据层
│   └── web/                      # Web 工具
├── config/
│   ├── chapter_timeline.json     # 109 章发布时间线
│   ├── collab_series.json        # 联动活动系列映射
│   ├── identity_map.json         # 角色身份映射(~150 条)
│   └── hooks/                    # 会话管理 Hook 脚本
├── data/
│   ├── stories/                  # 原始剧情对话 (2160 JSON)
│   ├── extractions/
│   │   ├── v1_events/            # Pass 1 剧情事件 (106 章)
│   │   ├── v2_characters/        # Pass 2 角色 Wiki (641 角色)
│   │   └── v3_wiki/              # Pass 3 世界观 Wiki (概念/阵营/地点)
│   ├── lorebook/                 # 大地巡旅 OCR
│   ├── operators.json            # 干员列表
│   ├── entity_source_map.json    # 实体双向索引 (5213 实体, 2.3MB)
│   └── index/                    # FAISS 向量索引
├── output/
│   ├── devlog.md
│   ├── qa_log.jsonl
│   └── sessions/
├── scripts/                      # 构建和评估脚本
└── tests/
    └── agent/                    # Agent 测试 (76 tests)
```

---

## Agent Pipeline 架构

```
用户问题
  │
  ▼
[router.py] route_query()
  ├── _infer_intent_local()     → 7 类意图（关键词规则）
  ├── _extract_entities_local() → identity_map + operators + chapter_timeline
  ├── recognize_intent_and_rewrite() → LLM 兜底（无本地结果时）
  └── classify_complexity_local() → simple / complex
  │
  ├── simple (实体<=3, 非comparison/list_enumeration/causal_reasoning)
  │     │
  │     ▼
  │   [simple_search.py] search_and_collect()
  │     ├── Chapter 识别 → get_chapter_summary + 章节事件
  │     ├── Entity get_page → WikiStore 精确页面
  │     ├── Events(chapter=章节名, entity=实体名) → 章节感知事件
  │     ├── Wiki 搜索 + expansion_hints 补充
  │     ├── FAISS 语义搜索
  │     └── Dialogue / Timeline 兜底
  │     │
  │     ▼
  │   build_answer_prompt() → DeepSeek LLM → 百科编纂者回答
  │
  └── complex (comparison/list_enumeration/causal_reasoning/实体>3)
        │
        ▼
      [graph.py] LangGraph ReAct Agent
        ├── call_model (DeepSeek + 8 tool definitions)
        ├── tool_node → 执行检索工具
        ├── 循环最多 8 轮
        └── synthesize_node → 综合证据生成回答
```

### 8 个检索工具

| 工具 | 用途 |
|------|------|
| `search_wiki` | 全文搜索 Wiki 页面 |
| `get_entity_page` | 获取实体完整页面 |
| `search_events` | 搜索剧情事件（按参与者/类型/章节） |
| `search_dialogue` | 搜索原始对话文本 |
| `search_timeline` | 搜索泰拉历史时间线 |
| `get_chapter_summary` | 获取章节叙事摘要 |
| `semantic_search` | FAISS 语义搜索 |
| `lookup_entity_index` | 查找实体关联和相关章节 |

---

## Phase 进度

### Phase 1: 原始内容提取 — 完成 (2026-06-15)

| 维度 | 值 |
|------|-----|
| 故事节点 | 1,663/1,669 |
| 干员档案 | 420/420 |
| 测试 | 87 passed |

### Phase 2: 知识提取 — 完成 (2026-06-21)

Pass 1 剧情骨架: 106 章 / 4129 事件 / 957 概念  
Pass 2 角色 Wiki: 641 角色 / $4.63 / 210 tests  
Pass 3 世界观 Wiki: 概念/阵营/地点 三层独立 / $0.18 / 271 tests

### Phase 3: 数据质量 — 完成 (2026-06-24)

OpenAI Evals 评估框架集成 / 4 维数据质量评估 / 大地巡旅 OCR 401 页

### Phase 4: LangGraph Agent — 当前 (2026-06-27)

| 维度 | 值 |
|------|-----|
| 模块 | 10 源文件 |
| 工具 | 8 LangGraph tools |
| 测试 | 76 passed |
| FAISS 索引 | 6,666 实体 (512-dim BGE) |
| 实体索引 | 5,213 实体 / 25,300 双向引用 |
| 前端 | PRTS 终端风格双栏 SSE 聊天 UI |

#### Phase 4 关键优化 (2026-06-27)

- 实体提取从 5213 WikiStore 全量扫描改为三层精确提取
- 章节感知事件检索（自动识别章节名→事件按章过滤）
- expansion_hints 与 canonical_entities 分离（噪声-83%）
- 叙事弧线 prompt 工程（起因→经过→转折→高潮→结局）
- LLM 章节名幻觉过滤
- search_dialogue 崩溃修复

---

## 下一步

1. 用户手动测试前端
2. 评估器重新跑基线（路由/检索变化影响较大）
3. 根据评估结果继续调优 prompt 和检索策略
