# 明日方舟剧情 LLM Wiki

基于《明日方舟》全量剧情构建的结构化知识库与 AI 问答系统。覆盖主线第 1-15 章、67 个支线/插曲活动、21 个故事集、6 个集成战略主题，共 109 章剧情经三遍 LLM 提取管线转化为可检索知识图谱，由 LangGraph ReAct Agent 提供自然语言问答。

> 最新收录剧情：泡影苍霆（怪物猎人二期联动）。

> 启动服务后访问 `http://localhost:8000`，PRTS 终端风格双栏 SSE 聊天界面。

---

## 功能特性

- **三遍知识提取**：事件骨架 (Pass 1) -> 角色 Wiki (Pass 2) -> 世界观实体 (Pass 3)，每遍独立 LLM 扫描
- **混合检索**：精确 Wiki 检索 + FAISS 语义搜索 + 原始对话全文搜索 + 章节感知过滤
- **LangGraph ReAct Agent**：多步推理 + 8 工具调用 + 证据综合，支持对比/枚举/因果推理
- **实体双向索引**：5,213 实体的 25,300 条引用，支持精确匹配和别名解析
- **PRTS 终端前端**：SSE 流式聊天、检索步骤可视化、来源引用展开

---

## 快速开始

**环境要求**：Python 3.12+, 8GB+ 内存

```bash
git clone <repo-url>
cd "Arknights LLM Wiki"
pip install -e .

# 启动 Agent 服务
python -m arknights_wiki.agent.server
# 浏览器打开 http://localhost:8000

# 构建索引（首次运行前）
python scripts/build_agent_index.py      # FAISS 向量索引
python scripts/build_entity_index.py     # 实体双向索引
```

---

## 架构概览

```
用户问题 → [router.py] 意图识别 + 实体提取 + 复杂度分类
              ├── simple → 多层检索管线 → LLM 合成
              └── complex → LangGraph ReAct Agent (8 tools, ≤8 轮) → LLM 合成
```

架构图详见 **[docs/diagrams/architecture.md](docs/diagrams/architecture.md)**，或用浏览器打开 **[docs/diagrams/architecture.html](docs/diagrams/architecture.html)** 查看交互式预览。

### Agent 工具

`search_wiki` / `get_entity_page` / `search_events` / `search_dialogue` / `search_timeline` / `get_chapter_summary` / `semantic_search` / `lookup_entity_index`

---

## 技术栈

| 层级 | 方案 |
|------|------|
| 语言 | Python 3.12+ |
| 数据存储 | SQLite（实体注册表 + 源索引 + Wiki 页面） |
| 向量检索 | FAISS (IndexFlatIP) + BGE-small-zh-v1.5 (512-dim) |
| LLM API | DeepSeek（OpenAI SDK 兼容） |
| Agent | LangGraph ReAct Agent |
| Web | FastAPI + SSE 流式 |
| 前端 | 原生 HTML/CSS/JS（PRTS 终端风格） |
| 测试 | pytest（76 agent tests） |

---

## 目录结构

```
Arknights LLM Wiki/
├── docs/
│   ├── specs/                    # 设计规格
│   ├── plans/                    # 实施计划
│   ├── diagrams/                 # 架构图 (Mermaid + HTML)
│   └── adr/                      # 架构决策记录
├── arknights_wiki/
│   ├── extraction/               # Pass 1/2/3 提取模块
│   ├── agent/                    # LangGraph Agent
│   │   ├── server.py             # FastAPI + SSE 服务
│   │   ├── static/               # 前端 (HTML + CSS + JS)
│   │   ├── router.py             # 意图识别 + 实体提取 + 复杂度分类
│   │   ├── simple_search.py      # 多层检索管线
│   │   ├── graph.py              # LangGraph ReAct Agent
│   │   ├── tools.py              # 8 个检索工具
│   │   ├── retrieval.py          # Wiki/Event/Dialogue/Timeline 数据层
│   │   └── prompts.py            # LLM 提示词模板
│   └── store/                    # SQLite 数据层
├── config/
│   ├── chapter_timeline.json     # 章节时间线
│   ├── collab_series.json        # 联动活动映射
│   └── identity_map.json         # 角色身份映射
├── data/
│   ├── stories/                  # 原始剧情对话 (2,160 JSON)
│   ├── extractions/
│   │   ├── v1_events/            # Pass 1 事件 (106 章)
│   │   ├── v2_characters/        # Pass 2 角色 Wiki (641 角色)
│   │   └── v3_wiki/              # Pass 3 世界观 Wiki
│   ├── lorebook/                 # 大地巡旅描述 (原始数据在仓库外)
│   ├── entity_source_map.json    # 实体双向索引 (2.3MB)
│   └── index/                    # FAISS 向量索引
├── scripts/                      # 构建与运行脚本
└── tests/                        # 测试套件
```

---

## 数据规模

| 数据层 | 文件数 | 字符数 | 约合 Tokens | 数据来源 |
|--------|--------|--------|-------------|----------|
| 原始剧情对话 | 2,160 | 3,710 万 | 1,237 万 | PRTS Wiki (prts.wiki) 抓取 |
| 干员档案 | 1 | 133 万 | 44 万 | PRTS Wiki 干员页面抓取 |
| Pass 1 事件标注 | 106 章 | 243 万 | 81 万 | LLM 提取 (DeepSeek) |
| Pass 2 角色 Wiki | 642 角色 | 128 万 | 43 万 | LLM 提取 (DeepSeek) |
| Pass 3 世界观 Wiki | 1,757 页面 | 121 万 | 40 万 | LLM 提取 (DeepSeek) |
| 视频字幕 | 37 个 | 5 万 | 2 万 | 官方视频 (手动转录) |
| **合计** | — | **4,337 万** | **1,447 万** | |

| 索引层 | 规模 |
|--------|------|
| 实体双向索引 (entity_source_map.json) | 5,213 实体 / 25,300 引用 / 2.0 MB |
| FAISS 向量索引 (BGE-small-zh-v1.5, 512-dim) | 6,666 向量 / 13.7 MB |
| chunk_map 分块映射 | 6.2 MB |

---

## 许可证

本项目仅用于学习和研究目的。明日方舟及其相关内容版权归 Hypergryph / Studio Montagne 所有。
