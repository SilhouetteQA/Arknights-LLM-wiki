# 明日方舟 LLM Wiki -- 架构图

> 生成日期: 2026-07-04 | 工具: Mermaid

---

## 1. C4 Context -- 系统上下文图

```mermaid
graph TB
    subgraph "用户"
        Player[玩家 / 剧情爱好者<br/>提问明日方舟世界观问题]
    end

    subgraph "明日方舟 LLM Wiki 系统"
        Agent[Wiki Agent<br/>RAG 问答 + 百科编纂风格<br/>端口 8000]
    end

    subgraph "外部系统"
        DeepSeek[DeepSeek API<br/>LLM 推理<br/>模型: deepseek-chat]
        PRTS[PRTS Wiki<br/>原始数据源<br/>抓取后离线使用]
        ModelScope[ModelScope<br/>BGE-small-zh-v1.5<br/>Embedding 模型下载]
    end

    Player -->|"提问 (SSE 流式)"| Agent
    Agent -->|"LLM 调用<br/>(OpenAI SDK 兼容)"| DeepSeek
    Agent -->|"离线数据<br/>(剧情/干员/Wiki)"| PRTS
    Agent -->|"向量化检索<br/>(FAISS + BGE)"| ModelScope

    style Agent fill:#1168bd,color:#fff
    style Player fill:#08427b,color:#fff
    style DeepSeek fill:#6c757d,color:#fff
    style PRTS fill:#6c757d,color:#fff
    style ModelScope fill:#6c757d,color:#fff
```

**系统边界**: Wiki Agent 是一个独立的 RAG 问答系统，数据离线预处理，对外仅依赖 DeepSeek API 做推理。

---

## 2. System Architecture -- 系统架构图

```mermaid
graph TB
    subgraph "前端层"
        HTML[index.html<br/>PRTS 终端风格 UI]
        CSS[style.css<br/>配色/动画/响应式]
        JS[app.js<br/>SSE ReadableStream<br/>tokenCount 实时计数]
    end

    subgraph "API 层 (FastAPI + SSE)"
        Server[server.py<br/>POST /chat → SSE 流]
        RateLimiter[速率限制器<br/>30 req/min per IP]
        LogQA[QA 日志<br/>qa_log.jsonl 自动记录]
    end

    subgraph "Agent Pipeline"
        Router[router.py<br/>意图识别 + 实体提取 + 复杂度分类]
        Simple[simple_search.py<br/>4 层检索 → LLM 直接回答]
        Complex[graph.py<br/>LangGraph ReAct Agent<br/>多步检索 max 8 轮<br/>或 Planner 显式规划<br/>ARKNIGHTS_AGENT_MODE]
        Prompts[prompts.py<br/>百科编纂者风格<br/>来源忠实度约束]
        State[state.py<br/>AgentState TypedDict]
    end

    subgraph "检索层 (Data Access)"
        Wiki[WikiStore<br/>v3_wiki 精确页面]
        Event[EventStore<br/>v1_events 结构化查询]
        Dialogue[DialogueStore<br/>原始剧情对话]
        Timeline[TimelineStore<br/>泰拉历史时间线]
        FAISS[FAISS 语义搜索<br/>6666 向量 512-dim BGE]
        EntityIndex[entity_source_map.json<br/>5213 实体 25300 双向引用]
    end

    subgraph "数据层"
        Stories[data/stories/<br/>2160 剧情 JSON]
        Extractions[data/extractions/<br/>v1_events + v2_characters + v3_wiki]
        Operators[operators.json<br/>340 干员档案]
        Lorebook[data/lorebook/<br/>大地巡旅 401 页 OCR]
        Index[data/index/<br/>FAISS 索引 + chunk_map]
    end

    subgraph "LLM 层"
        LLMClient[llm_client.py<br/>OpenAI SDK 统一接口]
        DeepSeekAPI[DeepSeek API<br/>deepseek-chat]
    end

    HTML --> Server
    CSS --> HTML
    JS --> Server

    Server --> Router
    Router -->|"simple (实体≤3)"| Simple
    Router -->|"complex (对比/列举/因果/实体>3)"| Complex

    Simple --> Wiki
    Simple --> Event
    Simple --> FAISS
    Simple --> Dialogue
    Simple --> Timeline
    Simple --> Prompts
    Simple --> LLMClient

    Complex --> Wiki
    Complex --> Event
    Complex --> FAISS
    Complex --> Dialogue
    Complex --> EntityIndex
    Complex --> Prompts
    Complex --> State
    Complex --> LLMClient

    Wiki --> Extractions
    Wiki --> Lorebook
    Event --> Extractions
    Dialogue --> Stories
    Timeline --> Extractions
    FAISS --> Index
    EntityIndex --> Extractions

    LLMClient --> DeepSeekAPI

    style Server fill:#ff6b6b,color:#fff
    style Router fill:#f39c12,color:#fff
    style Simple fill:#2ecc71,color:#fff
    style Complex fill:#2ecc71,color:#fff
    style LLMClient fill:#9b59b6,color:#fff
    style DeepSeekAPI fill:#9b59b6,color:#fff
```

**分层说明**:
- **前端层**: 纯 HTML/CSS/JS，PRTS 终端风格，双栏布局 (聊天 + 检索追踪)
- **API 层**: FastAPI + SSE 流式输出，内建速率限制和 QA 日志
- **Agent Pipeline**: 查询路由 + 双路径检索 (simple/complex)
- **检索层**: 6 种检索策略统一接口，惰性加载缓存
- **数据层**: 全离线数据 (剧情/提取/干员/设定集/向量索引)
- **LLM 层**: OpenAI SDK 统一接口，当前使用 DeepSeek

---

## 3. Agent Pipeline -- 数据流图

```mermaid
graph TD
    Q[用户问题] --> Wrap[wrap_user_input<br/>注入防护包裹]
    Wrap --> Router

    subgraph "router.py -- route_query()"
        Router{识别结果} --> IntentLocal[_infer_intent_local<br/>7 类意图关键词规则]
        IntentLocal -->|"命中"| Intent
        IntentLocal -->|"未命中"| IntentLLM[recognize_intent_and_rewrite<br/>LLM 兜底]
        IntentLLM --> Intent[意图 + 改写后问题]

        Intent --> EntityLocal[_extract_entities_local<br/>identity_map + operators + chapter_timeline]
        EntityLocal --> FilterHallucination[章节名幻觉过滤<br/>不在问题文本中的章节名降为 hints]
        FilterHallucination --> Classify[classify_complexity_local]

        Classify -->|"simple"| SimplePath
        Classify -->|"complex"| ComplexPath
    end

    subgraph "simple_search.py"
        SimplePath[search_and_collect] --> ChId[章节识别
        get_chapter_summary 试探]
        ChId --> L0[Layer 0: Wiki 精确匹配<br/>get_entity_page]
        L0 --> L1[Layer 1: Events 章节感知<br/>search_events 按章过滤]
        L1 --> L2[Layer 2: FAISS 语义搜索<br/>cosine similarity ≥0.4]
        L2 --> L3[Layer 3: Dialogue 兜底<br/>原始文本搜索]
        L3 --> Collect[去重合并<br/>expansion_hints 仅补充 Wiki]
        Collect --> BuildSimple[build_answer_prompt<br/>百科编纂者风格]
        BuildSimple --> CallLLM1[DeepSeek LLM]
    end

    subgraph "graph.py -- LangGraph ReAct Agent"
        ComplexPath --> InitState[初始化 AgentState<br/>question + messages]
        InitState --> CallModel[call_model<br/>LLM + 8 tool definitions]
        CallModel -->|"tool_calls"| ToolNode[tool_node<br/>执行检索工具<br/>结果追加到 messages]
        ToolNode -->|"继续 (≤8轮)"| CallModel
        CallModel -->|"no tool_calls"| Synthesize[synthesize_node<br/>SYNTHESIS_PROMPT<br/>综合证据生成回答]
    end

    CallLLM1 --> SSE1[SSE 流式输出]
    Synthesize --> SSE2[SSE 流式输出]

    SSE1 --> UI[前端 PRTS 终端]
    SSE2 --> UI

    style Router fill:#f39c12,color:#fff
    style SimplePath fill:#2ecc71,color:#fff
    style ComplexPath fill:#3498db,color:#fff
    style CallLLM1 fill:#9b59b6,color:#fff
    style CallModel fill:#9b59b6,color:#fff
    style UI fill:#1168bd,color:#fff
```

**关键设计决策**:
- **意图识别**: 本地规则优先 (7 类意图)，LLM 兜底 (无匹配时)
- **实体提取**: 3 层精确提取替代全量扫描 (噪声从 5-9 降至 1-2)
- **章节感知**: 自动识别章节名 → 事件搜索按章过滤
- **expansion_hints 分离**: 不参与路由决策和事件检索
- **LangGraph Agent**: ReAct 模式，最多 8 轮 tool 调用，无外部搜索依赖

---

## 4. Component Diagram -- 代码模块依赖图

```mermaid
graph LR
    subgraph "arknights_wiki/"
        subgraph "agent/"
            Server[server.py<br/>FastAPI + SSE]
            Router2[router.py<br/>查询路由]
            Simple2[simple_search.py<br/>简单检索]
            Graph2[graph.py<br/>LangGraph Agent]
            Tools[tools.py<br/>8 个检索工具]
            Prompts2[prompts.py<br/>提示词模板]
            Retrieval2[retrieval.py<br/>数据访问层]
            State2[state.py<br/>AgentState]
            Init[__init__.py<br/>wrap_user_input]
        end

        subgraph "extraction/"
            LLMClient2[llm_client.py<br/>OpenAI SDK 封装]
            DialogueLoader[dialogue_loader.py]
            Orchestrator[orchestrator.py<br/>Pass 1 编排]
            CharacterAggregator[character_aggregator.py]
            PromptBuilder[prompt_builder.py]
            PostProcessor[post_processor.py]
            WorldbuildingOrch[worldbuilding_orchestrator.py]
            WorldbuildingProc[worldbuilding_processor.py]
            WorldbuildingPrompts[worldbuilding_prompts.py]
            WorldbuildingSchema[worldbuilding_schema.py]
            BookSplitter[book_splitter.py]
            VideoMerger[video_merger.py]
        end

        subgraph "pipeline/"
            FetchStories[fetch_stories.py]
            FetchIndex[fetch_index.py]
            FetchOperators[fetch_operators.py]
            ParseDialogue[parse_dialogue.py]
            GenMarkdown[gen_markdown.py]
            GenOpMD[gen_operators_md.py]
            Orchestrate[orchestrate.py]
        end

        subgraph "store/"
            Seed[seed.py]
            EntityRepo[entity_repository.py]
            PageRepo[page_repository.py]
            SourceRepo[source_repository.py]
            Schema[ _schema.py]
            Report[ _report.py]
        end

        subgraph "stats/"
            Collector[collector.py]
            Reporter[reporter.py]
        end

        Config[config.py<br/>DATA_DIR / PROJECT_ROOT]
        Utils[ _utils.py]
    end

    subgraph "config/"
        IdentityMap[identity_map.json]
        ChapterTimeline[chapter_timeline.json]
        CollabSeries[collab_series.json]
    end

    subgraph "外部依赖"
        LangGraph[LangGraph]
        FastAPI2[FastAPI]
        FAISS2[faiss-cpu]
        OpenAISDK[openai]
        SentenceTF[sentence-transformers]
    end

    Server --> Router2
    Server --> Simple2
    Server --> Graph2
    Router2 --> Prompts2
    Router2 --> Config
    Simple2 --> Retrieval2
    Simple2 --> Prompts2
    Simple2 --> LLMClient2
    Graph2 --> Tools
    Graph2 --> Prompts2
    Graph2 --> State2
    Graph2 --> LLMClient2
    Graph2 --> Init
    Tools --> Retrieval2
    Retrieval2 --> Config

    Simple2 --> Init
    Prompts2 --> Tools

    Router2 --> IdentityMap
    Router2 --> ChapterTimeline

    Orchestrator --> LLMClient2
    Orchestrator --> DialogueLoader
    CharacterAggregator --> LLMClient2
    WorldbuildingOrch --> LLMClient2
    WorldbuildingOrch --> WorldbuildingPrompts
    WorldbuildingOrch --> WorldbuildingProc
    WorldbuildingProc --> WorldbuildingSchema

    Seed --> EntityRepo
    Seed --> PageRepo
    Seed --> SourceRepo
    Seed --> Schema

    Graph2 --> LangGraph
    Server --> FastAPI2
    Retrieval2 --> FAISS2
    LLMClient2 --> OpenAISDK
    Tools --> SentenceTF

    style Server fill:#ff6b6b,color:#fff
    style Router2 fill:#f39c12,color:#fff
    style Simple2 fill:#2ecc71,color:#fff
    style Graph2 fill:#3498db,color:#fff
    style LLMClient2 fill:#9b59b6,color:#fff
    style Config fill:#95a5a6,color:#fff
```

**模块职责**:
| 模块 | 职责 | 核心依赖 |
|------|------|----------|
| `agent/` | RAG 问答服务 (API + 路由 + 检索 + LLM) | extraction/llm_client, LangGraph, FastAPI |
| `extraction/` | Pass 1/2/3 数据提取管线 | llm_client, OpenAI SDK |
| `pipeline/` | 原始数据抓取 + 解析 + Markdown 生成 | 无外部 |
| `store/` | SQLite 种子数据库 (实体/索引/页面) | sqlite3 |
| `stats/` | 提取过程统计 (耗时/token/费用) | sqlite3 |
| `config/` | 静态配置文件 | 无 |

---

## 5. 升级阶段架构（W1–W4，2026-08）

> 生成日期: 2026-08-19 | 工具: Mermaid | 规则: architecture-diagrams skill

### 5.1 运行链路与工程化能力

```mermaid
graph TB
    subgraph "运行链路（complex 路径）"
        SRV[server.py<br/>SSE + checkpoint 工厂] --> SEL{选择图<br/>ARKNIGHTS_AGENT_MODE}
        SEL -->|"react（默认）"| REACT[build_agent_graph<br/>call_model ⇄ tool_node ≤8 轮]
        SEL -->|"planner（可选）"| PLAN[build_planner_graph<br/>plan → execute → synthesize<br/>崩溃检测 → 自动切 ReAct]
    end

    subgraph "W2 恢复链（工具/LLM 执行层）"
        EX[execute_with_resilience<br/>timeout → retry → breaker → fallback]
        LLMR[chat_completion 重试<br/>网络/限流/5xx，4xx 不重试]
        CK[SqliteSaver checkpoint<br/>thread_id=sha1(问题)，断点续跑]
    end

    subgraph "W3 MCP Server（工具双轨）"
        MCP[server.py<br/>5 只读工具<br/>search_entities/events/relationship/timeline/story]
        MC[client.py 同步桥<br/>ARKNIGHTS_USE_MCP=1<br/>失败回退内部函数]
    end

    subgraph "W1 Observability"
        LF[Langfuse trace<br/>@observe 全链路埋点]
        DASH[ECharts Dashboard :8001<br/>ClickHouse 直查]
    end

    REACT --> EX
    PLAN --> EX
    EX --> LLMR
    EX --> CK
    EX --> MC --> MCP
    REACT --> LF
    PLAN --> LF
    LF --> DASH

    style SEL fill:#f39c12,color:#fff
    style REACT fill:#3498db,color:#fff
    style PLAN fill:#3498db,color:#fff
    style EX fill:#e74c3c,color:#fff
    style MCP fill:#8e44ad,color:#fff
    style LF fill:#16a085,color:#fff
```

### 5.2 关键开关与环境变量

| 开关 | 默认 | 说明 |
|------|------|------|
| `ARKNIGHTS_AGENT_MODE` | `react` | `planner` 启用显式规划（2026-08-19 用户决策质量优先） |
| `ARKNIGHTS_USE_MCP` | 关 | 工具切换 MCP 后端（LLM 无感知） |
| `ARKNIGHTS_PLANNER_FALLBACK` | 开 | Planner 证据不足自动切 ReAct 兜底 |
| `ARKNIGHTS_PLANNER_TASK_REACT` | 关 | 任务级 ReAct 混合（实验，工具选择精度低） |
| `ARKNIGHTS_TOOL_TIMEOUT/MAX_RETRIES/BREAKER_*` | 30s/2/5×60s | 工具恢复链参数 |
| `ARKNIGHTS_LLM_TIMEOUT/MAX_RETRIES` | 60s/2 | LLM 重试参数 |
| `ARKNIGHTS_HTTP_PROXY` | 空（直连） | 显式代理（失效系统代理会致 10061） |

### 5.3 评测基线（output/eval/）

| 报告 | 内容 |
|------|------|
| `report_v1_mimo.md` | W0 基线：100 题 overall **0.857** |
| `w4_cmp_react / w4_cmp_planner / w4_cmp_planner_task_react` | 三路由同环境对比：**0.942 / 0.903 / 0.758**（工具选择 0.2 弃用任务级 ReAct） |
| `w4_three_mode_report.md` | 用户 5 问质量评估（coverage/accuracy/faithfulness/structure） |
