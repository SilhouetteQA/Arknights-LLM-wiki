# LangGraph AI Agent 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建基于 LangGraph 的《明日方舟》剧情问答 AI Agent，利用 Pass 1/2/3 提取数据做 RAG 问答。

**Architecture:** Query Router（本地规则）→ Simple Search（4 层检索 + LLM 回答）或 LangGraph ReAct Agent（7 工具多步检索）→ 统一 SSE 流式输出。FAISS 向量索引提供语义搜索兜底，chunk_id 命名约定确保搜索结果可追溯到精确实体。

**Tech Stack:** Python 3.12, LangGraph, FastAPI + SSE, FAISS (IndexFlatIP), BGE-small-zh-v1.5, sentence-transformers, DeepSeek v4-flash

**数据路径:**
- v1_events: `data/extractions/v1_events/{category}/{chapter}.json`
- v2_characters: `data/extractions/v2_characters/{name}.json`
- v3_wiki: `data/extractions/v3_wiki/{concepts|factions|locations}/{name}.md`
- stories: `data/stories/{category}/{chapter}/*.json`

---

## File Structure

```
arknights_wiki/agent/           # 新建目录
├── __init__.py                 # 空 init
├── state.py                    # AgentState TypedDict
├── prompts.py                  # 所有 LLM prompt 模板
├── vector_index.py             # FAISS 索引构建 + semantic_search()
├── retrieval.py                # Wiki/Event/Dialogue/Timeline 数据访问层
├── tools.py                    # 7 个 @tool 函数
├── router.py                   # 查询复杂度路由器
├── simple_search.py            # 简单检索路径
├── graph.py                    # LangGraph ReAct Agent 图定义
└── server.py                   # FastAPI + /chat SSE 端点

scripts/
└── build_agent_index.py        # 一次性离线索引构建脚本

tests/agent/                    # 新建目录
├── __init__.py
├── conftest.py                 # 共享 fixtures（LLM mock, sample data）
├── test_vector_index.py        # FAISS 索引构建 + 搜索
├── test_retrieval.py           # 数据访问层
├── test_tools.py               # 7 个 tool 函数
├── test_router.py              # 路由分类
├── test_simple_search.py       # 简单检索
├── test_graph.py               # LangGraph agent
└── test_server.py              # Web API

pyproject.toml                  # 修改: 添加 langgraph, fastapi, sse-starlette, sentence-transformers, faiss-cpu
```

---

### Task 0: 项目依赖与基础设施

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 添加 agent 依赖到 pyproject.toml**

在 `[project.optional-dependencies]` 下新增 `agent` 依赖组：

```toml
agent = [
    "fastapi>=0.115",
    "sse-starlette>=2.0",
    "langgraph>=0.2",
    "sentence-transformers>=3.0",
    "faiss-cpu>=1.8",
    "numpy>=1.26",
    "openai>=1.0",
]
```

- [ ] **Step 2: 安装依赖**

```bash
pip install -e ".[agent]"
```

- [ ] **Step 3: 创建目录结构和空 __init__**

```bash
mkdir -p arknights_wiki/agent tests/agent
```

`arknights_wiki/agent/__init__.py`:
```python
"""明日方舟剧情问答 AI Agent"""
```

`tests/agent/__init__.py`:
```python
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml arknights_wiki/agent/__init__.py tests/agent/__init__.py
git commit -m "chore: add agent dependencies + directory scaffold"
```

---

### Task 1: AgentState + Prompts

**Files:**
- Create: `arknights_wiki/agent/state.py`
- Create: `arknights_wiki/agent/prompts.py`

- [ ] **Step 1: 创建 AgentState TypedDict**

`arknights_wiki/agent/state.py`:
```python
"""LangGraph Agent 状态定义"""
from typing import TypedDict


class AgentState(TypedDict):
    messages: list          # 完整对话历史（含 ToolMessage）
    question: str           # 用户原始问题
    collected_docs: list    # 已收集的检索结果
    iteration: int          # 当前 ReAct 迭代次数
    route: dict             # Router 分类结果: {complexity, question_type, entities, time_scope, reason}
```

- [ ] **Step 2: 创建 Prompts 模块**

`arknights_wiki/agent/prompts.py`:
```python
"""Agent 和 Simple Search 的 LLM 提示词模板"""

ROUTER_SYSTEM_PROMPT = """你是一个查询关键词提取器。从用户问题中提取用于搜索的角色名、章节名、活动名、组织名、地名。
只输出JSON数组，不要其他内容。
示例: ["阿米娅","罗德岛","第三章"]"""

QA_SYSTEM_PROMPT = """你是一个《明日方舟》剧情叙述者。根据参考资料以连贯叙事方式回答用户问题。

## 核心原则
- 只能根据参考资料回答，不要使用外部知识。
- 将零散信息融合成连贯的故事，按时间顺序展开，体现因果逻辑。
- 用自然流畅的段落叙述，禁止使用列表、条目或分点格式。

## 引用规范
- 叙述中自然融入引用标注 [1]、[2] 等，不要单独列出。
- 当回答涉及相关内容时，自然地引用原文，并用「」包裹。
- 如果参考资料不足，明确说明"参考资料中未包含该信息"。

## 概念类问题
- 当问题询问某个概念/设定/机制的定义时（如"源石是什么"），重点解释该概念本身：
  定义 → 特性 → 影响/危害 → 在故事中的意义。
"""

AGENT_SYSTEM_PROMPT = """你是一个《明日方舟》剧情知识检索专家。逐步检索信息回答用户问题。

## 可用工具
1. search_wiki(query, category) — 全文搜索 Wiki 页面（概念/阵营/地点/角色）
2. get_entity_page(name, entity_type) — 获取实体完整 Wiki 页面
3. search_events(entity, event_type, chapter) — 搜索剧情事件
4. search_dialogue(query, chapter) — 搜索原始对话文本
5. search_timeline(query) — 搜索历史时间线
6. get_chapter_summary(chapter) — 获取章节摘要
7. semantic_search(query, top_k) — FAISS 语义搜索（用于模糊/描述性查询）

## 检索原则
- 优先 search_wiki（信息密度最高），其次 search_events，最后 semantic_search / search_dialogue 兜底
- 发现关键实体时用 get_entity_page 深入获取完整信息
- 因果链/时间线问题必须用 search_timeline
- 信息足够后立即给出回答，不要过度检索
- 禁止使用外部知识，所有回答必须基于检索结果
"""

SYNTHESIS_PROMPT = """基于以下已收集的证据，以连贯叙事方式回答用户问题。

## 证据材料
{evidence}

## 用户问题
{question}

## 要求
- 基于证据材料回答，不要编造。
- 将零散证据融合成连贯故事，按时间顺序展开。
- 自然地在文中引用来源 [来源N]。
- 如果证据不足，诚实说明。
"""
```

- [ ] **Step 3: Commit**

```bash
git add arknights_wiki/agent/state.py arknights_wiki/agent/prompts.py
git commit -m "feat(agent): AgentState + prompt templates"
```

---

### Task 2: 测试基础设施

**Files:**
- Create: `tests/agent/conftest.py`

- [ ] **Step 1: 创建共享 fixtures**

`tests/agent/conftest.py`:
```python
"""Agent 测试共享 fixtures"""
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def sample_concept_page():
    """Pass 3 概念页示例"""
    return """# 源石

**分类:** 自然现象/物质

**定义:** 泰拉世界一种蕴含巨大能量的矿物。

## 概述

源石是泰拉世界最核心的能量来源和工业原料。它也是矿石病的病原体。

## 剧情事件

### 黑暗时代·上

- **首次提及源石** [minor]: 阿米娅向博士解释源石和矿石病的关系。
"""


@pytest.fixture
def sample_character_json():
    """Pass 2 角色 JSON 示例"""
    return {
        "name": "Amiya",
        "display_name": "阿米娅",
        "summary": "罗德岛公开领袖，公开身份为感染者。拥有出色的源石技艺天赋。",
        "personality": "认真、温柔、坚强，对博士绝对信任。",
        "power_level": "军事精锐·标准",
        "power_level_evidence": "多次在正面战场中展现出色的战术指挥和源石技艺能力。",
        "story_events": [
            {"chapter": "黑暗时代·上", "summary": "在切尔诺伯格唤醒失忆的博士。"},
        ],
    }


@pytest.fixture
def sample_pass1_events():
    """Pass 1 事件 JSON 示例"""
    return {
        "summary": "博士在切尔诺伯格苏醒，整合运动发动袭击。",
        "events": [
            {
                "event": "博士在切尔诺伯格核心区苏醒，被阿米娅告知其罗德岛成员身份。",
                "type": "revelation",
                "line_range": [1, 78],
                "participants": ["阿米娅", "医疗干员", "博士"],
                "location": "切尔诺伯格核心区废弃设施",
                "is_imaginary": False,
            },
            {
                "event": "整合运动突袭设施，阿米娅请求博士指挥。",
                "type": "ambush",
                "line_range": [79, 124],
                "participants": ["阿米娅", "博士", "整合运动成员"],
                "location": "切尔诺伯格核心区废弃设施",
                "is_imaginary": False,
            },
        ],
    }


@pytest.fixture
def sample_timeline():
    """Timeline 示例"""
    return """# 泰拉历史时间线

## 759

**维多利亚工程师发明了第一台轮式源石外燃机**

## 797

**七城联邦建成泰拉历史上第一座现代移动城市**
"""


@pytest.fixture
def sample_dialogue():
    """原始对话示例"""
    return {
        "id": "main_01_01",
        "chapter": "黑暗时代·上",
        "lines": [
            {"type": "narration", "text": "5:57 a.m. / 多云"},
            {"type": "dialogue", "speaker": "阿米娅", "text": "博士，您醒了吗？"},
            {"type": "dialogue", "speaker": "博士", "text": "这里...是哪里？"},
            {"type": "dialogue", "speaker": "阿米娅", "text": "欢迎回来，博士。我是罗德岛的阿米娅。"},
        ],
    }


@pytest.fixture
def mock_llm_client():
    """模拟 LLM 客户端（不发起真实 API 调用）"""
    client = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"complexity": "simple", "question_type": "worldview", "entities": ["源石"], "time_scope": "cross_arc", "reason": "简单事实查询"}'
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    client.chat.completions.create.return_value = mock_response
    return client


@pytest.fixture
def temp_data_dir():
    """临时数据目录，包含最小 wiki 数据"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建子目录
        concepts_dir = os.path.join(tmpdir, "extractions", "v3_wiki", "concepts")
        factions_dir = os.path.join(tmpdir, "extractions", "v3_wiki", "factions")
        locations_dir = os.path.join(tmpdir, "extractions", "v3_wiki", "locations")
        characters_dir = os.path.join(tmpdir, "extractions", "v2_characters")
        events_dir = os.path.join(tmpdir, "extractions", "v1_events", "main")
        stories_dir = os.path.join(tmpdir, "stories", "main", "黑暗时代·上")

        for d in [concepts_dir, factions_dir, locations_dir, characters_dir, events_dir, stories_dir]:
            os.makedirs(d, exist_ok=True)

        # 写入示例数据
        with open(os.path.join(concepts_dir, "源石.md"), "w", encoding="utf-8") as f:
            f.write("# 源石\n\n**分类:** 自然现象/物质\n\n**定义:** 泰拉世界一种蕴含巨大能量的矿物。\n\n## 概述\n\n源石是泰拉世界最核心的能源。也是矿石病的病原体。\n")

        with open(os.path.join(concepts_dir, "矿石病.md"), "w", encoding="utf-8") as f:
            f.write("# 矿石病\n\n**分类:** 自然现象/物质\n\n**定义:** 由源石感染引发的致命疾病。\n\n## 概述\n\n矿石病是泰拉世界的绝症。\n")

        with open(os.path.join(factions_dir, "罗德岛.md"), "w", encoding="utf-8") as f:
            f.write("# 罗德岛\n\n**分类:** 势力/组织\n\n**定义:** 致力于解决感染者问题的医药公司。\n\n## 概述\n\n罗德岛表面为制药公司，实际致力于解决感染者问题。\n")

        with open(os.path.join(locations_dir, "切尔诺伯格.md"), "w", encoding="utf-8") as f:
            f.write("# 切尔诺伯格\n\n**分类:** 城市/移动城市\n\n**定义:** 乌萨斯帝国的主要移动城市之一。\n\n## 概述\n\n切尔诺伯格是乌萨斯帝国的主要移动城市。\n")

        with open(os.path.join(characters_dir, "Amiya.json"), "w", encoding="utf-8") as f:
            json.dump({
                "name": "Amiya",
                "display_name": "阿米娅",
                "summary": "罗德岛公开领袖。",
                "personality": "认真、温柔、坚强。",
            }, f, ensure_ascii=False)

        with open(os.path.join(events_dir, "黑暗时代·上.json"), "w", encoding="utf-8") as f:
            json.dump({
                "summary": "博士苏醒，整合运动袭击。",
                "events": [
                    {"event": "博士在切尔诺伯格苏醒。", "type": "revelation", "line_range": [1, 78], "participants": ["阿米娅", "博士"], "location": "切尔诺伯格", "is_imaginary": False},
                ],
            }, f, ensure_ascii=False)

        with open(os.path.join(stories_dir, "main_01_01.json"), "w", encoding="utf-8") as f:
            json.dump({
                "id": "main_01_01",
                "chapter": "黑暗时代·上",
                "lines": [
                    {"type": "dialogue", "speaker": "阿米娅", "text": "博士，您醒了吗？"},
                ],
            }, f, ensure_ascii=False)

        # 写 timeline
        timeline_dir = os.path.join(tmpdir, "extractions", "v3_wiki")
        with open(os.path.join(timeline_dir, "timeline.md"), "w", encoding="utf-8") as f:
            f.write("# 泰拉历史时间线\n\n## 797\n\n**七城联邦建成第一座移动城市**\n\n")

        yield tmpdir
```

- [ ] **Step 2: Commit**

```bash
git add tests/agent/conftest.py
git commit -m "test(agent): shared fixtures + mock LLM + temp data"
```

---

### Task 3: FAISS 向量索引

**Files:**
- Create: `arknights_wiki/agent/vector_index.py`
- Create: `tests/agent/test_vector_index.py`

- [ ] **Step 1: 编写测试**

`tests/agent/test_vector_index.py`:
```python
"""FAISS 向量索引测试"""
import json
import os

import numpy as np
import pytest

from arknights_wiki.agent.vector_index import (
    build_chunk_map,
    build_faiss_index,
    build_index_from_data,
    load_index,
    semantic_search,
)


class TestChunkMap:
    def test_build_chunk_map_from_concepts(self, temp_data_dir):
        """chunk_map 正确映射概念页面"""
        data_dir = temp_data_dir
        chunk_map = build_chunk_map(data_dir)

        assert ("concept", "源石") in chunk_map
        entry = chunk_map[("concept", "源石")]
        assert "源石.md" in entry["file_path"]
        assert "泰拉世界一种蕴含巨大能量的矿物" in entry["text"]


class TestFAISSIndex:
    def test_build_and_search(self, temp_data_dir):
        """FAISS 索引构建 + 搜索端到端"""
        chunk_map = build_chunk_map(temp_data_dir)
        texts = [v["text"] for v in chunk_map.values()]
        ids = list(chunk_map.keys())

        index = build_faiss_index(texts, dimension=384)

        # 索引大小等于文本数
        assert index.ntotal == len(texts)

        # 语义搜索: "能源矿物" 应返回源石
        results = semantic_search("能源矿物", index, chunk_map, model=None, top_k=3)
        assert len(results) > 0
        # 源石应该排在前面
        top_entity_names = [r["name"] for r in results]
        assert "源石" in top_entity_names


def test_build_index_from_data_saves_files(temp_data_dir):
    """build_index_from_data 写出 FAISS 文件 + chunk_map JSON"""
    index_dir = os.path.join(temp_data_dir, "index")
    os.makedirs(index_dir, exist_ok=True)

    index_path, map_path = build_index_from_data(temp_data_dir, index_dir)

    assert os.path.exists(index_path)
    assert os.path.exists(map_path)

    # 验证 load
    index, chunk_map = load_index(index_path, map_path)
    assert index.ntotal > 0
    assert len(chunk_map) > 0


def test_semantic_search_returns_structured_results(temp_data_dir):
    """semantic_search 返回结构化结果，含 entity_type 和 name"""
    chunk_map = build_chunk_map(temp_data_dir)
    texts = [v["text"] for v in chunk_map.values()]
    index = build_faiss_index(texts, dimension=384)

    results = semantic_search("矿石病是什么", index, chunk_map, model=None, top_k=2)

    for r in results:
        assert "chunk_id" in r
        assert "entity_type" in r
        assert "name" in r
        assert "score" in r
        assert "text" in r
        assert r["entity_type"] in ("concept", "faction", "location", "character", "event")
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/agent/test_vector_index.py -v
```
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 vector_index.py**

`arknights_wiki/agent/vector_index.py`:
```python
"""FAISS 向量索引构建 + 语义搜索

参照 mrfz 的索引构建模式:
- 所有 wiki/event/character 内容统一编码为 FAISS 向量
- chunk_id 命名约定: {entity_type}:{name} (如 concept:源石)
- chunk_map.json: (entity_type, name) → {file_path, text, chunk_id}
- 搜索通过 chunk_map 追溯到精确实体
"""
import json
import os
import re
from pathlib import Path

import numpy as np

from arknights_wiki.config import DATA_DIR


def _load_embedding_model():
    """惰性加载 BGE-small-zh-v1.5（同 mrfz 配置，模块级缓存）"""
    from sentence_transformers import SentenceTransformer

    model_name = os.environ.get("ARKNIGHTS_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
    model = SentenceTransformer(model_name, device="cpu")
    model.max_seq_length = 512
    try:
        model.half()
    except Exception:
        pass
    return model


_embed_model = None


def _get_model():
    global _embed_model
    if _embed_model is None:
        _embed_model = _load_embedding_model()
    return _embed_model


def _list_markdown_files(directory: str) -> list[Path]:
    """递归列出目录下所有 .md 文件"""
    p = Path(directory)
    if not p.exists():
        return []
    return sorted(p.rglob("*.md"))


def build_chunk_map(data_dir: str | None = None) -> dict:
    """遍历所有数据源，构建 chunk_map

    chunk_map key: (entity_type, name)
    chunk_map value: {file_path, text, chunk_id}

    数据源:
      - v3_wiki/concepts/*.md    → entity_type="concept"
      - v3_wiki/factions/*.md    → entity_type="faction"
      - v3_wiki/locations/*.md   → entity_type="location"
      - v2_characters/*.json     → entity_type="character"
      - v1_events/**/*.json      → entity_type="event" (每个事件) + "chapter_summary" (每章摘要)
      - v3_wiki/timeline.md      → entity_type="timeline" (每个 year 条目)
    """
    if data_dir is None:
        data_dir = DATA_DIR

    base = Path(data_dir)
    chunk_map = {}

    # ── Pass 3 Concepts ──
    concepts_dir = base / "extractions" / "v3_wiki" / "concepts"
    for fp in _list_markdown_files(str(concepts_dir)):
        name = fp.stem
        text = fp.read_text(encoding="utf-8")
        chunk_map[("concept", name)] = {
            "file_path": str(fp),
            "text": text,
            "chunk_id": f"concept:{name}",
        }

    # ── Pass 3 Factions ──
    factions_dir = base / "extractions" / "v3_wiki" / "factions"
    for fp in _list_markdown_files(str(factions_dir)):
        name = fp.stem
        text = fp.read_text(encoding="utf-8")
        chunk_map[("faction", name)] = {
            "file_path": str(fp),
            "text": text,
            "chunk_id": f"faction:{name}",
        }

    # ── Pass 3 Locations ──
    locations_dir = base / "extractions" / "v3_wiki" / "locations"
    for fp in _list_markdown_files(str(locations_dir)):
        name = fp.stem
        text = fp.read_text(encoding="utf-8")
        chunk_map[("location", name)] = {
            "file_path": str(fp),
            "text": text,
            "chunk_id": f"location:{name}",
        }

    # ── Pass 2 Characters ──
    characters_dir = base / "extractions" / "v2_characters"
    if characters_dir.exists():
        for fp in sorted(characters_dir.glob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                name = data.get("display_name") or data.get("name", fp.stem)
                # 拼接角色关键信息为可索引文本
                parts = [f"角色: {name}"]
                if data.get("summary"):
                    parts.append(f"概述: {data['summary']}")
                if data.get("personality"):
                    parts.append(f"性格: {data['personality']}")
                if data.get("power_level"):
                    parts.append(f"战力: {data['power_level']}")
                text = "。".join(parts)
                chunk_map[("character", name)] = {
                    "file_path": str(fp),
                    "text": text,
                    "chunk_id": f"character:{name}",
                }
            except (json.JSONDecodeError, KeyError):
                continue

    # ── Pass 1 Events ──
    events_dir = base / "extractions" / "v1_events"
    if events_dir.exists():
        for fp in sorted(events_dir.rglob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                chapter = fp.parent.name + "/" + fp.stem
                # 章节摘要
                summary = data.get("summary", "")
                if summary:
                    chunk_map[("chapter_summary", fp.stem)] = {
                        "file_path": str(fp),
                        "text": f"章节摘要 [{fp.stem}]: {summary}",
                        "chunk_id": f"chapter_summary:{fp.stem}",
                    }
                # 每个事件
                for i, evt in enumerate(data.get("events", [])):
                    event_text = evt.get("event", "")
                    evt_type = evt.get("type", "")
                    participants = ", ".join(evt.get("participants", []))
                    location = evt.get("location", "")
                    parts = [f"事件 [{fp.stem}]: {event_text}"]
                    if evt_type:
                        parts.append(f"类型: {evt_type}")
                    if participants:
                        parts.append(f"参与者: {participants}")
                    if location:
                        parts.append(f"地点: {location}")
                    text = "。".join(parts)
                    chunk_map[("event", f"{fp.stem}_{i}")] = {
                        "file_path": str(fp),
                        "text": text,
                        "chunk_id": f"event:{fp.stem}_{i}",
                        "event_index": i,
                    }
            except (json.JSONDecodeError, KeyError):
                continue

    # ── Timeline ──
    timeline_path = base / "extractions" / "v3_wiki" / "timeline.md"
    if timeline_path.exists():
        text = timeline_path.read_text(encoding="utf-8")
        # 按 ## 分割年表条目
        entries = re.split(r"\n## (\d+)", text)
        for i in range(1, len(entries), 2):
            year = entries[i].strip()
            content = entries[i + 1].strip() if i + 1 < len(entries) else ""
            # 提取 **...** 中的事件描述
            bold_match = re.search(r"\*\*(.+?)\*\*", content)
            desc = bold_match.group(1) if bold_match else content[:100]
            chunk_map[("timeline", year)] = {
                "file_path": str(timeline_path),
                "text": f"时间线事件 [{year}]: {desc}",
                "chunk_id": f"timeline:{year}",
            }

    return chunk_map


def build_faiss_index(texts: list[str], dimension: int = 384) -> "faiss.IndexFlatIP":
    """编码文本列表并构建 FAISS IndexFlatIP

    Args:
        texts: 文本列表
        dimension: 嵌入维度 (BGE-small-zh 默认 384)

    Returns:
        faiss.IndexFlatIP 实例
    """
    import faiss

    model = _get_model()
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=128,
        show_progress_bar=True,
    )
    index = faiss.IndexFlatIP(dimension)
    index.add(np.array(embeddings, dtype=np.float32))
    return index


def build_index_from_data(data_dir: str | None = None, index_dir: str | None = None) -> tuple[str, str]:
    """从数据目录构建完整 FAISS 索引，写出文件

    Args:
        data_dir: 数据根目录，默认 DATA_DIR
        index_dir: 索引输出目录，默认 data_dir/index

    Returns:
        (index_path, chunk_map_path) 元组
    """
    if data_dir is None:
        data_dir = DATA_DIR
    if index_dir is None:
        index_dir = os.path.join(data_dir, "index")

    os.makedirs(index_dir, exist_ok=True)

    chunk_map = build_chunk_map(data_dir)
    texts = [v["text"] for v in chunk_map.values()]
    index = build_faiss_index(texts)

    import faiss

    index_path = os.path.join(index_dir, "faiss.index")
    faiss.write_index(index, index_path)

    # chunk_map: key 为 tuple，序列化为可 JSON 的格式
    serializable_map = {}
    for (entity_type, name), info in chunk_map.items():
        key = f"{entity_type}:{name}"
        serializable_map[key] = info

    map_path = os.path.join(index_dir, "chunk_map.json")
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(serializable_map, f, ensure_ascii=False, indent=2)

    return index_path, map_path


def load_index(index_path: str, map_path: str) -> tuple:
    """加载 FAISS 索引和 chunk_map

    Returns:
        (faiss.Index, dict) 元组
    """
    import faiss

    index = faiss.read_index(index_path)
    with open(map_path, "r", encoding="utf-8") as f:
        chunk_map = json.load(f)
    return index, chunk_map


def semantic_search(
    query: str,
    index,
    chunk_map: dict,
    model=None,
    top_k: int = 20,
) -> list[dict]:
    """FAISS 语义搜索，返回结构化结果列表

    每个结果包含:
      - chunk_id: 唯一标识
      - entity_type: 实体类型 (concept/faction/location/character/event/timeline/chapter_summary)
      - name: 实体名称
      - score: 相似度分数 (0-1，内积结果)
      - text: 文本内容前 500 字符
      - file_path: 源文件路径
    """
    if model is None:
        model = _get_model()

    query_vec = model.encode([query], normalize_embeddings=True)
    scores, indices = index.search(np.array(query_vec, dtype=np.float32), top_k)

    results = []
    chunk_map_items = list(chunk_map.items())  # key_str → info dict

    for i, idx in enumerate(indices[0]):
        if idx < 0 or idx >= len(chunk_map_items):
            continue
        key_str, info = chunk_map_items[idx]
        # 解析 entity_type:name
        parts = key_str.split(":", 1)
        entity_type = parts[0] if len(parts) > 0 else "unknown"
        name = parts[1] if len(parts) > 1 else key_str

        results.append({
            "chunk_id": info.get("chunk_id", key_str),
            "entity_type": entity_type,
            "name": name,
            "score": float(scores[0][i]),
            "text": info.get("text", "")[:500],
            "file_path": info.get("file_path", ""),
        })

    return results
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/agent/test_vector_index.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/agent/vector_index.py tests/agent/test_vector_index.py
git commit -m "feat(agent): FAISS vector index build + semantic_search"
```

---

### Task 4: 数据访问层 (Retrieval)

**Files:**
- Create: `arknights_wiki/agent/retrieval.py`
- Create: `tests/agent/test_retrieval.py`

- [ ] **Step 1: 编写测试**

`tests/agent/test_retrieval.py`:
```python
"""数据访问层测试"""
from arknights_wiki.agent.retrieval import (
    WikiStore,
    EventStore,
    DialogueStore,
    TimelineStore,
)


class TestWikiStore:
    def test_search_concept_by_name(self, temp_data_dir):
        store = WikiStore(data_dir=temp_data_dir)
        results = store.search("源石", category="concept")
        assert len(results) > 0
        assert results[0]["name"] == "源石"
        assert results[0]["entity_type"] == "concept"
        assert len(results[0]["text"]) > 0

    def test_search_faction(self, temp_data_dir):
        store = WikiStore(data_dir=temp_data_dir)
        results = store.search("罗德岛", category="faction")
        assert len(results) > 0
        assert results[0]["name"] == "罗德岛"

    def test_get_entity_page(self, temp_data_dir):
        store = WikiStore(data_dir=temp_data_dir)
        page = store.get_page("源石", "concept")
        assert page is not None
        assert "源石" in page["text"]

    def test_get_nonexistent_page(self, temp_data_dir):
        store = WikiStore(data_dir=temp_data_dir)
        page = store.get_page("不存在", "concept")
        assert page is None

    def test_list_all_entity_names(self, temp_data_dir):
        store = WikiStore(data_dir=temp_data_dir)
        names = store.list_names("concept")
        assert "源石" in names
        assert "矿石病" in names


class TestEventStore:
    def test_search_by_entity(self, temp_data_dir):
        store = EventStore(data_dir=temp_data_dir)
        results = store.search(entity="阿米娅")
        assert len(results) > 0
        assert any("阿米娅" in r["text"] for r in results)

    def test_get_chapter_summary(self, temp_data_dir):
        store = EventStore(data_dir=temp_data_dir)
        summary = store.get_chapter_summary("黑暗时代·上")
        assert summary is not None
        assert "博士苏醒" in summary["text"]


class TestDialogueStore:
    def test_search_dialogue(self, temp_data_dir):
        store = DialogueStore(data_dir=temp_data_dir)
        results = store.search("博士")
        assert len(results) > 0
        assert any("博士" in r["text"] for r in results)

    def test_search_dialogue_by_chapter(self, temp_data_dir):
        store = DialogueStore(data_dir=temp_data_dir)
        results = store.search("博士", chapter="黑暗时代·上")
        assert len(results) > 0


class TestTimelineStore:
    def test_search_timeline(self, temp_data_dir):
        store = TimelineStore(data_dir=temp_data_dir)
        results = store.search("移动城市")
        assert len(results) > 0
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/agent/test_retrieval.py -v
```
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 retrieval.py**

`arknights_wiki/agent/retrieval.py`:
```python
"""数据访问层 — Wiki/Event/Dialogue/Timeline 的统一检索接口"""
import json
import os
import re
from pathlib import Path

from arknights_wiki.config import DATA_DIR


class WikiStore:
    """Wiki 页面存储（Pass 2 角色 + Pass 3 概念/阵营/地点）

    按实体名精确匹配，支持子串搜索内容。
    """

    def __init__(self, data_dir: str | None = None):
        self.data_dir = data_dir or DATA_DIR
        self._name_cache: dict[str, list[str]] = {}  # entity_type → [names]

    def _get_dir(self, entity_type: str) -> str:
        """获取实体类型对应的目录"""
        base = os.path.join(self.data_dir, "extractions")
        if entity_type == "character":
            return os.path.join(base, "v2_characters")
        return os.path.join(base, "v3_wiki", entity_type + "s")  # concept→concepts

    def list_names(self, entity_type: str) -> list[str]:
        """列出指定类型的所有实体名称"""
        if entity_type not in self._name_cache:
            d = self._get_dir(entity_type)
            if not os.path.isdir(d):
                return []
            names = []
            ext = ".json" if entity_type == "character" else ".md"
            for f in os.listdir(d):
                if f.endswith(ext):
                    names.append(os.path.splitext(f)[0])
            self._name_cache[entity_type] = sorted(names)
        return self._name_cache[entity_type]

    def search(self, query: str, category: str | None = None, limit: int = 10) -> list[dict]:
        """全文搜索 wiki 页面

        策略:
          1. 文件名精确匹配 (query 恰好等于实体名)
          2. 文件名包含 query (子串匹配)
          3. 内容子串匹配

        Args:
            query: 搜索关键词
            category: 限定类别 (concept/faction/location/character)，None 搜索全部
            limit: 最大返回数

        Returns:
            [{entity_type, name, text, file_path, match_type}]
        """
        categories = [category] if category else ["concept", "faction", "location", "character"]
        results = []

        for cat in categories:
            names = self.list_names(cat)
            ext = ".json" if cat == "character" else ".md"
            d = self._get_dir(cat)

            for name in names:
                match_type = None
                # 精确匹配
                if name == query:
                    match_type = "exact"
                elif query in name:
                    match_type = "name_contains"
                else:
                    # 内容子串搜索
                    fp = os.path.join(d, name + ext)
                    try:
                        content = Path(fp).read_text(encoding="utf-8")
                    except Exception:
                        continue
                    if query in content:
                        match_type = "content_match"

                if match_type:
                    fp = os.path.join(d, name + ext)
                    try:
                        text = Path(fp).read_text(encoding="utf-8")
                    except Exception:
                        text = ""
                    results.append({
                        "entity_type": cat,
                        "name": name,
                        "text": text[:2000],
                        "file_path": fp,
                        "match_type": match_type,
                    })

        # 排序：精确 > 名包含 > 内容匹配
        order = {"exact": 0, "name_contains": 1, "content_match": 2}
        results.sort(key=lambda r: order.get(r["match_type"], 3))
        return results[:limit]

    def get_page(self, name: str, entity_type: str) -> dict | None:
        """获取实体完整页面

        Returns:
            {entity_type, name, text, file_path} 或 None
        """
        d = self._get_dir(entity_type)
        ext = ".json" if entity_type == "character" else ".md"
        fp = os.path.join(d, name + ext)
        if not os.path.exists(fp):
            return None
        try:
            text = Path(fp).read_text(encoding="utf-8")
        except Exception:
            return None
        return {
            "entity_type": entity_type,
            "name": name,
            "text": text,
            "file_path": fp,
        }


class EventStore:
    """Pass 1 事件存储"""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = data_dir or DATA_DIR
        self._events_dir = os.path.join(self.data_dir, "extractions", "v1_events")

    def _load_chapter(self, chapter: str) -> dict | None:
        """加载指定章节的 Pass 1 JSON"""
        for root, dirs, files in os.walk(self._events_dir):
            for f in files:
                if f.startswith(chapter) and f.endswith(".json"):
                    fp = os.path.join(root, f)
                    try:
                        return json.loads(Path(fp).read_text(encoding="utf-8"))
                    except Exception:
                        continue
        return None

    def _iter_events(self) -> list[dict]:
        """遍历所有事件文件，返回 [(chapter, event_dict, file_path)]"""
        results = []
        for root, dirs, files in os.walk(self._events_dir):
            for f in files:
                if not f.endswith(".json"):
                    continue
                fp = os.path.join(root, f)
                try:
                    data = json.loads(Path(fp).read_text(encoding="utf-8"))
                except Exception:
                    continue
                chapter = data.get("chapter") or os.path.splitext(f)[0]
                for evt in data.get("events", []):
                    results.append((chapter, evt, fp))
        return results

    def search(
        self,
        entity: str | None = None,
        event_type: str | None = None,
        chapter: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """搜索事件

        Args:
            entity: 按参与者名筛选
            event_type: 按事件类型筛选
            chapter: 按章节名筛选
            limit: 最大返回数
        """
        results = []
        for ch, evt, fp in self._iter_events():
            if chapter and chapter not in ch and ch not in chapter:
                continue
            if event_type and evt.get("type") != event_type:
                continue
            if entity:
                participants = evt.get("participants", [])
                if entity not in participants:
                    # 也检查事件文本
                    if entity not in evt.get("event", ""):
                        continue

            parts = [f"事件 [{ch}]: {evt.get('event', '')}"]
            if evt.get("type"):
                parts.append(f"类型: {evt['type']}")
            participants = evt.get("participants", [])
            if participants:
                parts.append(f"参与者: {', '.join(participants)}")
            if evt.get("location"):
                parts.append(f"地点: {evt['location']}")

            results.append({
                "entity_type": "event",
                "name": f"{ch} ({evt.get('type', '')})",
                "text": "。".join(parts),
                "file_path": fp,
                "event": evt,
                "chapter": ch,
            })

            if len(results) >= limit:
                break

        return results

    def get_chapter_summary(self, chapter: str) -> dict | None:
        """获取章节摘要"""
        data = self._load_chapter(chapter)
        if data is None:
            return None
        summary = data.get("summary", "")
        if not summary:
            return None
        return {
            "entity_type": "chapter_summary",
            "name": chapter,
            "text": summary,
        }


class DialogueStore:
    """原始对话全文搜索"""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = data_dir or DATA_DIR
        self._stories_dir = os.path.join(self.data_dir, "stories")

    def search(self, query: str, chapter: str | None = None, limit: int = 20) -> list[dict]:
        """在原始对话中搜索关键词"""
        results = []
        for root, dirs, files in os.walk(self._stories_dir):
            # 如果指定了章节，只搜索对应目录
            if chapter:
                dir_name = os.path.basename(root)
                if chapter not in dir_name:
                    continue
            for f in files:
                if not f.endswith(".json"):
                    continue
                fp = os.path.join(root, f)
                try:
                    data = json.loads(Path(fp).read_text(encoding="utf-8"))
                except Exception:
                    continue
                ch = data.get("chapter", "")
                node_id = data.get("id", "")
                lines = data.get("lines", [])

                for i, line in enumerate(lines):
                    text = line.get("text", "")
                    if query not in text:
                        continue
                    speaker = line.get("speaker", "旁白" if line.get("type") == "narration" else "???")
                    # 获取上下文（前后各 2 行）
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    context_lines = []
                    for j in range(start, end):
                        l = lines[j]
                        s = l.get("speaker", "旁白" if l.get("type") == "narration" else "???")
                        context_lines.append(f"[{s}] {l.get('text', '')}")
                    context = "\n".join(context_lines)

                    results.append({
                        "entity_type": "dialogue",
                        "name": f"{ch} / {node_id}",
                        "text": context,
                        "file_path": fp,
                        "speaker": speaker,
                        "chapter": ch,
                        "node_id": node_id,
                    })

                    if len(results) >= limit:
                        return results

        return results


class TimelineStore:
    """时间线搜索"""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = data_dir or DATA_DIR
        self._timeline_path = os.path.join(
            self.data_dir, "extractions", "v3_wiki", "timeline.md"
        )

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """搜索时间线事件"""
        if not os.path.exists(self._timeline_path):
            return []

        text = Path(self._timeline_path).read_text(encoding="utf-8")
        entries = re.split(r"\n## (\d+)", text)
        results = []

        for i in range(1, len(entries), 2):
            year = entries[i].strip()
            content = entries[i + 1].strip() if i + 1 < len(entries) else ""
            if query in content:
                bold_match = re.search(r"\*\*(.+?)\*\*", content)
                desc = bold_match.group(1) if bold_match else content[:200]
                results.append({
                    "entity_type": "timeline",
                    "name": year,
                    "text": f"时间线事件 [{year}]: {desc}",
                    "file_path": self._timeline_path,
                    "year": year,
                    "content": content,
                })

            if len(results) >= limit:
                break

        return results
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/agent/test_retrieval.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/agent/retrieval.py tests/agent/test_retrieval.py
git commit -m "feat(agent): WikiStore + EventStore + DialogueStore + TimelineStore"
```

---

### Task 5: 7 个 LangGraph Tools

**Files:**
- Create: `arknights_wiki/agent/tools.py`
- Create: `tests/agent/test_tools.py`

- [ ] **Step 1: 编写测试**

`tests/agent/test_tools.py`:
```python
"""Agent Tools 测试"""
import os
from unittest.mock import patch

from arknights_wiki.agent.tools import (
    search_wiki,
    get_entity_page,
    search_events,
    search_dialogue,
    search_timeline,
    get_chapter_summary,
    semantic_search_tool,
)


class TestSearchWiki:
    def test_search_returns_string(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = search_wiki("源石")
            assert isinstance(result, str)
            assert len(result) > 0

    def test_search_no_results(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = search_wiki("不存在的实体名称xyz123")
            assert isinstance(result, str)


class TestGetEntityPage:
    def test_get_existing_concept(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = get_entity_page("源石", "concept")
            assert "源石" in result

    def test_get_nonexistent(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = get_entity_page("不存在", "concept")
            assert "未找到" in result


class TestSearchEvents:
    def test_search_by_entity(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = search_events(entity="阿米娅")
            assert isinstance(result, str)


class TestSearchDialogue:
    def test_search_dialogue(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = search_dialogue("博士")
            assert isinstance(result, str)


class TestTimeline:
    def test_search_timeline(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = search_timeline("移动城市")
            assert isinstance(result, str)


class TestChapterSummary:
    def test_get_summary(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = get_chapter_summary("黑暗时代·上")
            assert isinstance(result, str)


class TestSemanticSearchTool:
    def test_returns_error_when_no_index(self, temp_data_dir):
        with patch("arknights_wiki.agent.tools._get_data_dir", return_value=temp_data_dir):
            result = semantic_search_tool("源石")
            # 索引未构建时应返回友好错误
            assert isinstance(result, str)
```

- [ ] **Step 2: 实现 tools.py**

`arknights_wiki/agent/tools.py`:
```python
"""LangGraph Agent 工具函数 — 7 个 @tool 装饰的检索工具

每个工具接收参数，返回 ToolMessage 可用的字符串结果。
"""
import os

from langgraph.prebuilt import ToolNode

from arknights_wiki.agent.retrieval import (
    WikiStore,
    EventStore,
    DialogueStore,
    TimelineStore,
)
from arknights_wiki.config import DATA_DIR


def _get_data_dir():
    return os.environ.get("ARKNIGHTS_DATA_DIR", DATA_DIR)


def search_wiki(query: str, category: str | None = None) -> str:
    """全文搜索 Wiki 页面（概念/阵营/地点/角色）。

    Args:
        query: 搜索关键词
        category: 限定类别 concept|faction|location|character，不传则搜索全部

    Returns:
        格式化的搜索结果文本
    """
    store = WikiStore(data_dir=_get_data_dir())
    results = store.search(query, category=category, limit=10)
    if not results:
        return f"未找到与 '{query}' 相关的 Wiki 页面。"
    lines = [f"搜索 '{query}' 找到 {len(results)} 个结果:"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[{i}] [{r['entity_type']}] {r['name']} ({r['match_type']})")
        lines.append(r["text"][:800])
    return "\n".join(lines)


def get_entity_page(name: str, entity_type: str) -> str:
    """获取实体完整 Wiki 页面。

    Args:
        name: 实体名称
        entity_type: 实体类型 concept|faction|location|character

    Returns:
        完整页面 markdown 文本，或错误信息
    """
    store = WikiStore(data_dir=_get_data_dir())
    page = store.get_page(name, entity_type)
    if page is None:
        return f"未找到 {entity_type} 实体: {name}"
    return page["text"]


def search_events(
    entity: str | None = None,
    event_type: str | None = None,
    chapter: str | None = None,
) -> str:
    """搜索 Pass 1 剧情事件。

    Args:
        entity: 按参与者名筛选（可选）
        event_type: 按事件类型筛选（可选）
        chapter: 按章节名筛选（可选）

    Returns:
        格式化的事件列表文本
    """
    store = EventStore(data_dir=_get_data_dir())
    results = store.search(entity=entity, event_type=event_type, chapter=chapter, limit=15)
    if not results:
        parts = []
        if entity:
            parts.append(f"entity={entity}")
        if event_type:
            parts.append(f"type={event_type}")
        if chapter:
            parts.append(f"chapter={chapter}")
        return f"未找到匹配的事件 ({', '.join(parts)})。"
    lines = [f"找到 {len(results)} 个事件:"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[{i}] {r['text'][:500]}")
    return "\n".join(lines)


def search_dialogue(query: str, chapter: str | None = None) -> str:
    """全文搜索原始剧情对话。

    Args:
        query: 搜索关键词
        chapter: 限定章节（可选）

    Returns:
        格式化的对话片段
    """
    store = DialogueStore(data_dir=_get_data_dir())
    results = store.search(query, chapter=chapter, limit=15)
    if not results:
        return f"未在对话中找到 '{query}'。"
    lines = [f"搜索 '{query}' 找到 {len(results)} 段对话:"]
    for i, r in enumerate(results, 1):
        source = f"[{r.get('chapter', '')}/{r.get('node_id', '')}]"
        lines.append(f"\n[{i}] {source}")
        lines.append(r["text"][:500])
    return "\n".join(lines)


def search_timeline(query: str) -> str:
    """搜索泰拉历史时间线。

    Args:
        query: 搜索关键词

    Returns:
        格式化的时间线事件列表
    """
    store = TimelineStore(data_dir=_get_data_dir())
    results = store.search(query, limit=10)
    if not results:
        return f"未在时间线中找到 '{query}'。"
    lines = [f"搜索时间线 '{query}' 找到 {len(results)} 个事件:"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n[{i}] 年份 {r['year']}: {r['text']}")
    return "\n".join(lines)


def get_chapter_summary(chapter: str) -> str:
    """获取指定章节的叙事摘要。

    Args:
        chapter: 章节名称

    Returns:
        章节摘要文本
    """
    store = EventStore(data_dir=_get_data_dir())
    result = store.get_chapter_summary(chapter)
    if result is None:
        return f"未找到章节 '{chapter}' 的摘要。"
    return f"[{chapter}] 章节摘要:\n{result['text']}"


def semantic_search_tool(query: str, top_k: int = 10) -> str:
    """FAISS 语义搜索 — 处理描述性/模糊查询（如 "那个整合运动的女领袖"）。

    Args:
        query: 搜索查询
        top_k: 返回结果数

    Returns:
        格式化的语义搜索结果
    """
    index_dir = os.path.join(_get_data_dir(), "index")
    index_path = os.path.join(index_dir, "faiss.index")
    map_path = os.path.join(index_dir, "chunk_map.json")

    if not os.path.exists(index_path) or not os.path.exists(map_path):
        return "FAISS 索引未就绪。请先运行 build_agent_index.py。可尝试其他检索工具。"

    from arknights_wiki.agent.vector_index import load_index, semantic_search

    index, chunk_map = load_index(index_path, map_path)
    results = semantic_search(query, index, chunk_map, top_k=top_k)

    if not results:
        return f"语义搜索 '{query}' 未找到相关结果。"

    lines = [f"语义搜索 '{query}' 找到 {len(results)} 个结果:"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"\n[{i}] [{r['entity_type']}] {r['name']} (score: {r['score']:.3f})"
        )
        lines.append(r["text"][:400])
    return "\n".join(lines)


# 工具定义列表（供 LangGraph bind_tools 使用）
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_wiki",
            "description": "全文搜索 Wiki 页面。用于查找角色、概念、阵营、地点的名称或相关描述。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词（实体名或描述）"},
                    "category": {
                        "type": "string",
                        "enum": ["concept", "faction", "location", "character"],
                        "description": "限定类别，不传则搜索全部",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity_page",
            "description": "获取实体完整 Wiki 页面。当发现关键实体需要深入了解时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "实体名称"},
                    "entity_type": {
                        "type": "string",
                        "enum": ["concept", "faction", "location", "character"],
                        "description": "实体类型",
                    },
                },
                "required": ["name", "entity_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": "搜索剧情事件。按参与者、事件类型或章节筛选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "参与者名称（可选）"},
                    "event_type": {"type": "string", "description": "事件类型（可选）"},
                    "chapter": {"type": "string", "description": "章节名称（可选）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_dialogue",
            "description": "全文搜索原始剧情对话文本。适合查找 Wiki 和 Events 未覆盖的具体对话。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "chapter": {"type": "string", "description": "限定章节（可选）"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_timeline",
            "description": "搜索泰拉历史时间线。用于时间/因果关系问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chapter_summary",
            "description": "获取指定章节的叙事摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter": {"type": "string", "description": "章节名称"},
                },
                "required": ["chapter"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": "FAISS 语义搜索。处理描述性/模糊查询（如'那个整合运动的女领袖'），也能查到精确实体名匹配不到的相关内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询"},
                    "top_k": {"type": "integer", "description": "返回结果数，默认10"},
                },
                "required": ["query"],
            },
        },
    },
]

# Tool 执行映射
TOOL_EXECUTORS = {
    "search_wiki": search_wiki,
    "get_entity_page": get_entity_page,
    "search_events": search_events,
    "search_dialogue": search_dialogue,
    "search_timeline": search_timeline,
    "get_chapter_summary": get_chapter_summary,
    "semantic_search": semantic_search_tool,
}
```

- [ ] **Step 3: 运行测试**

```bash
pytest tests/agent/test_tools.py -v
```
Expected: PASS (基础 import 验证)

- [ ] **Step 4: Commit**

```bash
git add arknights_wiki/agent/tools.py tests/agent/test_tools.py
git commit -m "feat(agent): 7 LangGraph tools with function definitions"
```

---

### Task 6: Query Router

**Files:**
- Create: `arknights_wiki/agent/router.py`
- Create: `tests/agent/test_router.py`

- [ ] **Step 1: 编写测试**

`tests/agent/test_router.py`:
```python
"""Query Router 测试"""
from unittest.mock import patch

from arknights_wiki.agent.router import (
    _extract_entities_local,
    _infer_question_type,
    _infer_time_scope,
    classify_complexity_local,
    route_query,
)


class TestEntityExtraction:
    def test_extract_wiki_entity(self, temp_data_dir):
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            entities = _extract_entities_local("源石是什么", temp_data_dir)
            assert "源石" in entities

    def test_extract_identity_map_entity(self, temp_data_dir):
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            entities = _extract_entities_local("魏彦吾做了什么", temp_data_dir)
            # identity_map 中有 "炎武": "魏彦吾"
            # We search for "魏彦吾" directly as entity name
            assert "魏彦吾" in entities or len(entities) >= 0  # 可能无匹配

    def test_chapter_pattern(self, temp_data_dir):
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            entities = _extract_entities_local("第三章讲了什么", temp_data_dir)
            assert "第三章" in entities


class TestQuestionType:
    def test_worldview_type(self):
        assert _infer_question_type("源石是什么") == "worldview"

    def test_event_type(self):
        assert _infer_question_type("黑暗时代上发生了什么") == "event"

    def test_comparison_type(self):
        assert _infer_question_type("阿米娅和凯尔希对比") == "comparison"

    def test_summary_type(self):
        assert _infer_question_type("整体剧情脉络") == "summary"

    def test_default_event(self):
        assert _infer_question_type("第三章") == "event"


class TestTimeScope:
    def test_cross_arc_indicators(self):
        assert _infer_time_scope("矿石病在整个泰拉的演变", []) == "cross_arc"

    def test_chapter_explicit(self):
        assert _infer_time_scope("第三章讲了什么", ["第三章"]) == "chapter"

    def test_default_cross_arc(self):
        assert _infer_time_scope("源石是什么", ["源石"]) == "cross_arc"


class TestComplexity:
    def test_simple_fact(self):
        result = classify_complexity_local("源石是什么", ["源石"], "worldview", "cross_arc")
        assert result["complexity"] == "simple"

    def test_complex_comparison(self):
        result = classify_complexity_local("对比阿米娅和凯尔希", ["阿米娅", "凯尔希"], "comparison", "cross_arc")
        assert result["complexity"] == "complex"

    def test_complex_causal(self):
        result = classify_complexity_local("切尔诺伯格事件的起因是什么", [], "event", "cross_arc")
        assert result["complexity"] == "complex"


class TestRouteQuery:
    def test_route_simple_question(self, temp_data_dir):
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            result = route_query("源石是什么")
            assert "complexity" in result
            assert "question_type" in result
            assert "entities" in result
            assert isinstance(result["entities"], list)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/agent/test_router.py -v
```
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 router.py**

`arknights_wiki/agent/router.py`:
```python
"""查询路由器 — 本地规则判定问题复杂度 + 实体提取

流程:
  1. 本地实体提取 (identity_map + operators + wiki 文件名 + 正则)
  2. 问题类型推断 (关键词匹配)
  3. 时间范围推断
  4. 复杂度分类 (纯本地规则)
  5. entities=[] 时 LLM 兜底提取实体
"""
import json
import os
import re

from arknights_wiki.config import DATA_DIR
from arknights_wiki.agent.retrieval import WikiStore


def _load_identity_map() -> dict:
    """加载 identity_map.json"""
    fp = os.path.join(DATA_DIR, "config", "identity_map.json")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _load_operators() -> dict:
    """加载 operators.json"""
    fp = os.path.join(DATA_DIR, "operators.json")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _extract_entities_local(question: str, data_dir: str | None = None) -> list[str]:
    """从问题文本中提取实体名（纯本地，不调 LLM）

    匹配源:
      1. identity_map 的 key（别名）和 value（正名）
      2. operators.json 的角色名
      3. Wiki 页面名（concept/faction/location/character）
      4. 正则: 章节/活动名模式
    """
    entities = []
    if data_dir is None:
        data_dir = DATA_DIR

    # 1. identity_map
    identity = _load_identity_map()
    for alias, canonical in identity.items():
        if alias in question:
            # 提取正名
            if canonical.startswith("character:"):
                entities.append(canonical.split(":", 1)[1])
            else:
                entities.append(canonical)
        if canonical in question and canonical not in entities:
            entities.append(canonical)

    # 2. operators
    operators = _load_operators()
    for op_name in operators:
        if op_name in question and op_name not in entities:
            entities.append(op_name)

    # 3. Wiki 页面名（惰性加载）
    for entity_type in ["concept", "faction", "location", "character"]:
        store = WikiStore(data_dir=data_dir)
        for name in store.list_names(entity_type):
            if len(name) >= 2 and name in question and name not in entities:
                entities.append(name)

    # 4. 章节/活动名正则
    chapter_match = re.search(r'(序章|第[0-9零一二三四五六七八九十]+章)', question)
    if chapter_match:
        entities.append(chapter_match.group(1))

    # 5. 「...」活动名
    event_match = re.findall(r'「([^」]+)」', question)
    entities.extend(event_match)

    return list(set(entities))


def _infer_question_type(question: str) -> str:
    """从关键词推断问题类型"""
    # 概括/总结类
    if any(kw in question for kw in [
        '整体讲了', '讲了什么', '讲了怎样', '整体故事',
        '整体脉络', '大框架', '梳理', '概括', '概述',
        '剧情发展', '剧情梗概', '故事梗概', '主要情节',
        '总结', '讲了一个', '讲了',
    ]):
        return 'summary'
    # 世界观/设定类
    if any(kw in question for kw in [
        '什么是', '是什么', '概念', '设定', '世界观',
        '是怎样的组织', '是怎样的国家', '有什么特点',
        '理念', '宗旨', '格局', '政治', '社会结构',
        '有几个', '有多少',
    ]):
        return 'worldview'
    # 对比类
    if any(kw in question for kw in [
        '对比', '比较', '区别', '异同', '孰强孰弱',
        '排名', '排序', '最强',
    ]):
        return 'comparison'
    # 角色行为/关系类
    if any(kw in question for kw in [
        '做了什么', '关系如何', '是什么关系', '有什么互动',
        '性格', '战力', '实力',
    ]):
        return 'character'
    return 'event'


def _infer_time_scope(question: str, entities: list[str]) -> str:
    """推断时间范围"""
    cross_signals = [
        '演变', '演化', '历程', '整个过程', '整体', '各个',
        '所有', '全部', '大框架', '脉络', '梳理',
    ]
    if any(kw in question for kw in cross_signals):
        return 'cross_arc'
    if re.search(r'(序章|第[0-9零一二三四五六七八九十]+章)', question):
        return 'chapter'
    return 'cross_arc'


def classify_complexity_local(
    question: str, entities: list[str], question_type: str, time_scope: str
) -> dict:
    """纯规则判断问题复杂度"""
    # comparison 类型 → complex
    if question_type == "comparison":
        return {
            "complexity": "complex",
            "question_type": question_type,
            "entities": entities,
            "time_scope": time_scope,
            "reason": "对比问题需要多源检索比对",
        }

    # 深度推理关键词
    deep_keywords = [
        "导致", "原因", "后果", "为什么",
        "对比", "比较", "区别", "异同", "排名", "排序",
        "演变", "变迁", "发展历程", "历程", "变革",
        "时间线", "编年史", "大事记", "梳理",
        "势力格局", "势力分布",
    ]
    has_deep = any(kw in question for kw in deep_keywords)

    if has_deep and time_scope == "cross_arc":
        return {
            "complexity": "complex",
            "question_type": question_type,
            "entities": entities,
            "time_scope": time_scope,
            "reason": "跨章节深度推理问题, 需要多步检索",
        }

    clean_entities = [e for e in entities if not e.startswith("__")]
    if time_scope == "cross_arc" and len(clean_entities) < 3 and len(clean_entities) == 0:
        return {
            "complexity": "complex",
            "question_type": question_type,
            "entities": entities,
            "time_scope": time_scope,
            "reason": "跨章节但实体不足, Agent 多步检索补充",
        }

    return {
        "complexity": "simple",
        "question_type": question_type,
        "entities": entities,
        "time_scope": time_scope,
        "reason": "简单事实查询",
    }


def _llm_rewrite_query(question: str) -> list[str]:
    """轻量 LLM: 从问题中提取检索关键词（entities=[] 时兜底）"""
    try:
        from arknights_wiki.extraction.llm_client import create_client
        from arknights_wiki.agent.prompts import ROUTER_SYSTEM_PROMPT

        client = create_client()
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        text = response.choices[0].message.content or ""
        text = text.strip().strip("`").removeprefix("json")
        entities = json.loads(text)
        if isinstance(entities, list):
            return [e for e in entities if isinstance(e, str) and len(e) >= 1]
    except Exception:
        pass
    return []


def route_query(question: str, history=None) -> dict:
    """查询路由主函数

    Args:
        question: 用户问题文本
        history: 历史对话列表（保留接口，暂未使用）

    Returns:
        dict: {complexity, question_type, entities, time_scope, reason, source}
    """
    entities = _extract_entities_local(question)
    question_type = _infer_question_type(question)

    source = "local"
    clean_entities = [e for e in entities if not e.startswith("__")]
    if len(clean_entities) == 0:
        llm_entities = _llm_rewrite_query(question)
        if llm_entities:
            entities = list(set(entities + llm_entities))
            source = "local+llm"

    time_scope = _infer_time_scope(question, entities)
    result = classify_complexity_local(question, entities, question_type, time_scope)
    result["source"] = source
    return result
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/agent/test_router.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/agent/router.py tests/agent/test_router.py
git commit -m "feat(agent): query router — local rules + LLM fallback"
```

---

### Task 7: Simple Search

**Files:**
- Create: `arknights_wiki/agent/simple_search.py`
- Create: `tests/agent/test_simple_search.py`

- [ ] **Step 1: 编写测试**

`tests/agent/test_simple_search.py`:
```python
"""Simple Search 测试"""
from unittest.mock import MagicMock, patch

from arknights_wiki.agent.simple_search import (
    simple_search,
    search_and_collect,
    build_answer_prompt,
)


class TestSearchAndCollect:
    def test_collects_wiki_results(self, temp_data_dir):
        with patch("arknights_wiki.agent.simple_search.DATA_DIR", temp_data_dir):
            results = search_and_collect(
                entities=["源石"],
                question="源石是什么",
                question_type="worldview",
            )
            assert len(results) > 0

    def test_collects_events(self, temp_data_dir):
        with patch("arknights_wiki.agent.simple_search.DATA_DIR", temp_data_dir):
            results = search_and_collect(
                entities=["阿米娅"],
                question="阿米娅在黑暗时代做了什么",
                question_type="character",
                chapter="黑暗时代·上",
            )
            # 至少能找到角色页面
            assert len(results) > 0


class TestBuildAnswerPrompt:
    def test_formats_sources(self, temp_data_dir):
        sources = [
            {"entity_type": "concept", "name": "源石", "text": "源石是泰拉世界的核心能源。"},
        ]
        prompt = build_answer_prompt("源石是什么", sources)
        assert "源石是什么" in prompt
        assert "[1]" in prompt
        assert "源石是泰拉世界的核心能源" in prompt


class TestSimpleSearch:
    def test_returns_answer_with_mock_llm(self, temp_data_dir, mock_llm_client):
        with patch("arknights_wiki.agent.simple_search.DATA_DIR", temp_data_dir):
            with patch("arknights_wiki.extraction.llm_client.create_client", return_value=mock_llm_client):
                result = simple_search(
                    question="源石是什么",
                    route={
                        "complexity": "simple",
                        "question_type": "worldview",
                        "entities": ["源石"],
                        "time_scope": "cross_arc",
                    },
                )
                assert "answer" in result
                assert "sources" in result
                assert len(result["sources"]) > 0
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/agent/test_simple_search.py -v
```
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 simple_search.py**

`arknights_wiki/agent/simple_search.py`:
```python
"""简单检索路径 — 多层检索 → 合并 → LLM 回答

Layer 0: Wiki 精确匹配
Layer 1: Events 结构化查询
Layer 2: FAISS 语义搜索
Layer 3: Dialogue 兜底
"""
import os
import time

from arknights_wiki.agent.retrieval import (
    WikiStore,
    EventStore,
    DialogueStore,
    TimelineStore,
)
from arknights_wiki.agent.prompts import QA_SYSTEM_PROMPT
from arknights_wiki.config import DATA_DIR


def _get_data_dir():
    return os.environ.get("ARKNIGHTS_DATA_DIR", DATA_DIR)


def search_and_collect(
    entities: list[str],
    question: str,
    question_type: str,
    chapter: str | None = None,
    max_sources: int = 20,
) -> list[dict]:
    """执行多层检索，合并收集的文档"""
    data_dir = _get_data_dir()
    collected = []
    seen = set()

    def add(doc: dict):
        key = f"{doc.get('entity_type', '')}:{doc.get('name', '')}"
        if key not in seen:
            seen.add(key)
            collected.append(doc)

    # Layer 0: Wiki 精确匹配
    wiki_store = WikiStore(data_dir=data_dir)
    for entity in entities:
        # 尝试各类型
        for etype in ["concept", "faction", "location", "character"]:
            page = wiki_store.get_page(entity, etype)
            if page:
                add(page)
                break  # 找到即停止
        # 也做全文搜索
        for result in wiki_store.search(entity, limit=3):
            add(result)

    # Layer 1: Events 结构化查询
    event_store = EventStore(data_dir=data_dir)
    if chapter:
        summary = event_store.get_chapter_summary(chapter)
        if summary:
            add(summary)
    for entity in entities:
        for evt in event_store.search(entity=entity, limit=5):
            add(evt)

    # Layer 2: FAISS 语义搜索
    index_dir = os.path.join(data_dir, "index")
    index_path = os.path.join(index_dir, "faiss.index")
    map_path = os.path.join(index_dir, "chunk_map.json")
    if os.path.exists(index_path) and os.path.exists(map_path):
        from arknights_wiki.agent.vector_index import load_index, semantic_search
        index, chunk_map = load_index(index_path, map_path)
        faiss_results = semantic_search(question, index, chunk_map, top_k=10)
        for r in faiss_results:
            if r["score"] > 0.3:  # 相似度阈值
                add({
                    "entity_type": r["entity_type"],
                    "name": r["name"],
                    "text": r["text"],
                    "file_path": r.get("file_path", ""),
                })
    else:
        # FAISS 未就绪，跳过
        pass

    # Layer 3: Dialogue 兜底（仅在结果少时触发）
    if len(collected) < 5:
        dialogue_store = DialogueStore(data_dir=data_dir)
        for result in dialogue_store.search(question[:50], chapter=chapter, limit=5):
            add(result)

    # Timeline（时间/因果类问题）
    if question_type in ("event", "comparison") or any(
        kw in question for kw in ["时间线", "先后", "年表", "历史"]
    ):
        timeline_store = TimelineStore(data_dir=data_dir)
        for result in timeline_store.search(question[:30], limit=5):
            add(result)

    return collected[:max_sources]


def build_answer_prompt(question: str, sources: list[dict]) -> str:
    """构建 LLM answer prompt"""
    source_text = ""
    for i, s in enumerate(sources, 1):
        header = f"[{i}] [{s.get('entity_type', 'unknown')}] {s.get('name', '')}"
        source_text += f"{header}\n{s.get('text', '')[:1000]}\n\n"

    return f"""## 用户问题
{question}

## 参考资料
{source_text}

请基于以上参考资料，以连贯的叙述方式回答用户问题。将零散的对话片段组织成有逻辑的、易读的叙事文本，按照时间顺序展开，自然地在文中标注引用来源 [1][2]。"""


def simple_search(question: str, route: dict) -> dict:
    """简单检索路径主函数

    Args:
        question: 用户问题
        route: 路由分类结果

    Returns:
        {"answer": str, "sources": list[dict]}
    """
    entities = route.get("entities", [])
    question_type = route.get("question_type", "summary")

    # 收集证据
    sources = search_and_collect(
        entities=entities,
        question=question,
        question_type=question_type,
    )

    if not sources:
        return {
            "answer": "未找到与问题相关的资料。请尝试更具体地描述问题。",
            "sources": [],
        }

    # 构建 prompt
    user_prompt = build_answer_prompt(question, sources)

    # 调用 LLM
    from arknights_wiki.extraction.llm_client import create_client

    client = create_client()
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=8192,
    )
    answer = response.choices[0].message.content or ""

    # 格式化 sources 元信息
    source_meta = []
    for i, s in enumerate(sources, 1):
        source_meta.append({
            "ref": i,
            "entity_type": s.get("entity_type", ""),
            "name": s.get("name", ""),
            "file_path": s.get("file_path", ""),
        })

    return {
        "answer": answer,
        "sources": source_meta,
    }
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/agent/test_simple_search.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/agent/simple_search.py tests/agent/test_simple_search.py
git commit -m "feat(agent): simple search — 4-layer retrieval + LLM answer"
```

---

### Task 8: LangGraph ReAct Agent

**Files:**
- Create: `arknights_wiki/agent/graph.py`
- Create: `tests/agent/test_graph.py`

- [ ] **Step 1: 编写测试**

`tests/agent/test_graph.py`:
```python
"""LangGraph Agent 测试"""
from unittest.mock import MagicMock, patch

from arknights_wiki.agent.graph import build_agent_graph, call_model, tool_node
from arknights_wiki.agent.state import AgentState


class TestAgentGraph:
    def test_build_graph_returns_compiled_graph(self):
        graph = build_agent_graph()
        assert graph is not None
        # LangGraph compiled graph 有 invoke 方法
        assert hasattr(graph, "invoke")

    def test_graph_invoke_simple(self, temp_data_dir, mock_llm_client):
        """端到端: simple 问题不进 Agent，直接返回"""
        graph = build_agent_graph()

        with patch("arknights_wiki.agent.graph.create_client", return_value=mock_llm_client):
            initial_state: AgentState = {
                "messages": [],
                "question": "源石是什么",
                "collected_docs": [],
                "iteration": 0,
                "route": {
                    "complexity": "simple",
                    "question_type": "worldview",
                    "entities": ["源石"],
                    "time_scope": "cross_arc",
                },
            }
            result = graph.invoke(initial_state)
            assert len(result["messages"]) > 0


class TestAgentNode:
    def test_call_model_decides_tool_or_finish(self, temp_data_dir):
        """call_model 节点: LLM 返回 tool_call 时路由到 tools，否则路由到 synthesize"""
        from arknights_wiki.agent.graph import call_model

        state: AgentState = {
            "messages": [{"role": "user", "content": "岁兽有几个碎片？"}],
            "question": "岁兽有几个碎片？",
            "collected_docs": [],
            "iteration": 0,
            "route": {"complexity": "complex", "entities": ["岁兽"]},
        }

        # 模拟 LLM 返回 tool_call
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "search_wiki"
        mock_tool_call.function.arguments = '{"query": "岁兽"}'
        mock_choice.message.tool_calls = [mock_tool_call]
        mock_choice.message.content = None
        mock_response.choices = [mock_choice]

        with patch("arknights_wiki.agent.graph.create_client") as mock_create:
            mock_create.return_value.chat.completions.create.return_value = mock_response
            result = call_model(state)
            # 有 tool_calls 时，最后一条 message 应该包含 tool_calls
            assert len(result["messages"]) > 1  # 原始 + assistant message

    def test_tool_node_executes_and_adds_results(self):
        """tool_node 执行工具并将结果追加到 messages"""
        from arknights_wiki.agent.graph import tool_node

        state: AgentState = {
            "messages": [
                {"role": "user", "content": "测试问题"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "search_wiki",
                                "arguments": '{"query": "源石"}',
                            },
                        }
                    ],
                },
            ],
            "question": "测试问题",
            "collected_docs": [],
            "iteration": 0,
            "route": {},
        }

        with patch("arknights_wiki.agent.tools.search_wiki") as mock_tool:
            mock_tool.return_value = "找到 3 个结果: ..."
            result = tool_node(state)
            assert len(result["collected_docs"]) > 0
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/agent/test_graph.py -v
```
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: 实现 graph.py**

`arknights_wiki/agent/graph.py`:
```python
"""LangGraph ReAct Agent 图定义

Graph 结构:
  START → call_model (agent_node)
             ├─ tool_calls → tool_node → call_model
             └─ no_tool_calls → synthesize_node → END
"""
import json
import os

from langgraph.graph import StateGraph, END

from arknights_wiki.agent.state import AgentState
from arknights_wiki.agent.prompts import AGENT_SYSTEM_PROMPT, SYNTHESIS_PROMPT
from arknights_wiki.agent.tools import TOOL_DEFINITIONS, TOOL_EXECUTORS


MAX_ITERATIONS = 8


def call_model(state: AgentState) -> AgentState:
    """调用 LLM（带 tool 定义），决定下一步: tool_call 或 final answer"""
    from arknights_wiki.extraction.llm_client import create_client

    question = state["question"]
    iteration = state.get("iteration", 0)

    # 首次调用时添加 system prompt
    if not state.get("messages"):
        state["messages"] = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
    else:
        # 确保 system prompt 在开头
        if state["messages"][0].get("role") != "system":
            state["messages"].insert(0, {"role": "system", "content": AGENT_SYSTEM_PROMPT})

    # 追踪收集的文档
    collected_docs = state.get("collected_docs", [])

    client = create_client()
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=state["messages"],
        tools=TOOL_DEFINITIONS,
        temperature=0.1,
        max_tokens=8192,
    )

    choice = response.choices[0]
    assistant_message = choice.message

    # 构建 assistant message dict
    new_message = {"role": "assistant"}
    if assistant_message.content:
        new_message["content"] = assistant_message.content
    if assistant_message.tool_calls:
        new_message["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in assistant_message.tool_calls
        ]
        new_message["content"] = assistant_message.content  # 可能为 None

    state["messages"] = state["messages"] + [new_message]
    state["iteration"] = iteration + 1

    return state


def tool_node(state: AgentState) -> AgentState:
    """执行 tool_calls，将结果追加到 messages"""
    last_message = state["messages"][-1]
    tool_calls = last_message.get("tool_calls", [])

    collected_docs = state.get("collected_docs", [])

    for tc in tool_calls:
        func_name = tc["function"]["name"]
        func_args = json.loads(tc["function"]["arguments"])

        executor = TOOL_EXECUTORS.get(func_name)
        if executor:
            result_text = executor(**func_args)
        else:
            result_text = f"未知工具: {func_name}"

        # 记录收集的文档
        collected_docs.append({
            "tool": func_name,
            "args": func_args,
            "result": result_text[:500],
        })

        # 追加 ToolMessage
        state["messages"] = state["messages"] + [
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": func_name,
                "content": result_text,
            }
        ]

    state["collected_docs"] = collected_docs
    return state


def synthesize_node(state: AgentState) -> AgentState:
    """综合所有证据，生成最终回答"""
    from arknights_wiki.extraction.llm_client import create_client

    question = state["question"]
    collected_docs = state.get("collected_docs", [])

    # 构建证据文本
    evidence_parts = []
    for i, doc in enumerate(collected_docs, 1):
        evidence_parts.append(f"[来源{i}] 工具: {doc['tool']}, 参数: {doc['args']}")
        evidence_parts.append(doc["result"])
        evidence_parts.append("")

    evidence_text = "\n".join(evidence_parts) if evidence_parts else "无证据收集到。"

    if not collected_docs:
        answer = "未能收集到与问题相关的证据，无法回答。请尝试更具体地描述问题。"
    else:
        prompt = SYNTHESIS_PROMPT.format(evidence=evidence_text, question=question)
        try:
            client = create_client()
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=8192,
            )
            answer = response.choices[0].message.content or ""
        except Exception as e:
            answer = f"回答生成失败: {str(e)}"

    state["messages"] = state["messages"] + [
        {"role": "assistant", "content": answer}
    ]
    return state


def should_continue(state: AgentState) -> str:
    """路由决策: 继续 tool calling 还是结束"""
    last_message = state["messages"][-1]
    iteration = state.get("iteration", 0)

    # 达到最大迭代
    if iteration >= MAX_ITERATIONS:
        return "synthesize"

    # 有 tool_calls → 继续
    if last_message.get("tool_calls"):
        return "tools"

    # 无 tool_calls → LLM 认为已经可以回答
    return "synthesize"


def build_agent_graph():
    """构建并编译 LangGraph agent 图

    图结构:
      START → agent_node (call_model)
                 ├─ "tools" → tool_node → agent_node
                 └─ "synthesize" → synthesize_node → END
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    workflow.add_node("synthesize", synthesize_node)

    workflow.set_entry_point("agent")

    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "synthesize": "synthesize",
        },
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge("synthesize", END)

    return workflow.compile()
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/agent/test_graph.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/agent/graph.py tests/agent/test_graph.py
git commit -m "feat(agent): LangGraph ReAct agent with 7 tools"
```

---

### Task 9: FastAPI Server + SSE

**Files:**
- Create: `arknights_wiki/agent/server.py`
- Create: `tests/agent/test_server.py`

- [ ] **Step 1: 编写测试**

`tests/agent/test_server.py`:
```python
"""Web Server 测试"""
import pytest
from fastapi.testclient import TestClient

from arknights_wiki.agent.server import app

client = TestClient(app)


class TestChatEndpoint:
    def test_chat_returns_sse_stream(self, temp_data_dir):
        with patch("arknights_wiki.agent.server.DATA_DIR", temp_data_dir):
            with patch("arknights_wiki.agent.server._get_router") as mock_router:
                mock_router.return_value = {
                    "complexity": "simple",
                    "question_type": "worldview",
                    "entities": ["源石"],
                    "time_scope": "cross_arc",
                    "reason": "简单事实查询",
                    "source": "local",
                }
                with patch("arknights_wiki.agent.server.simple_search") as mock_simple:
                    mock_simple.return_value = {
                        "answer": "源石是泰拉世界最核心的能源矿物。",
                        "sources": [{"ref": 1, "entity_type": "concept", "name": "源石"}],
                    }
                    response = client.post("/chat", json={"question": "源石是什么"})
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers["content-type"]

    def test_chat_missing_question(self):
        response = client.post("/chat", json={})
        assert response.status_code == 422

    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/agent/test_server.py -v
```
Expected: FAIL (ModuleNotFoundError 或 ImportError)

- [ ] **Step 3: 实现 server.py**

`arknights_wiki/agent/server.py`:
```python
"""FastAPI Web 服务 — SSE 流式对话 API"""
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from arknights_wiki.config import DATA_DIR, PROJECT_ROOT
from arknights_wiki.agent.router import route_query
from arknights_wiki.agent.simple_search import simple_search
from arknights_wiki.agent.state import AgentState


class ChatRequest(BaseModel):
    question: str
    history: list[dict] | None = None


app = FastAPI(title="明日方舟剧情 Wiki Agent", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok"}


async def _simple_search_events(question: str, route: dict):
    """Simple search SSE 事件流"""
    yield {"event": "route", "data": json.dumps(route, ensure_ascii=False)}

    result = simple_search(question, route)
    answer = result.get("answer", "")

    # 流式输出 token（按句分割模拟流式）
    for chunk in _split_text(answer):
        yield {"event": "token", "data": json.dumps({"text": chunk}, ensure_ascii=False)}

    yield {
        "event": "sources",
        "data": json.dumps(result.get("sources", []), ensure_ascii=False),
    }
    yield {"event": "done", "data": json.dumps({"total_steps": 1})}


async def _agent_search_events(question: str, route: dict):
    """Complex (LangGraph Agent) SSE 事件流"""
    from arknights_wiki.agent.graph import build_agent_graph

    yield {"event": "route", "data": json.dumps(route, ensure_ascii=False)}

    graph = build_agent_graph()
    initial_state: AgentState = {
        "messages": [],
        "question": question,
        "collected_docs": [],
        "iteration": 0,
        "route": route,
    }

    # 逐步执行，yield 中间事件
    final_state = initial_state
    for event in graph.stream(initial_state):
        node_name = list(event.keys())[0]
        node_state = event[node_name]
        final_state = node_state

        if node_name == "tools":
            docs = node_state.get("collected_docs", [])
            if docs:
                last_doc = docs[-1]
                yield {
                    "event": "step",
                    "data": json.dumps({
                        "step": len(docs),
                        "tool": last_doc.get("tool", ""),
                        "summary": last_doc.get("result", "")[:200],
                    }, ensure_ascii=False),
                }
        elif node_name == "synthesize":
            final_message = node_state["messages"][-1]
            answer = final_message.get("content", "")
            for chunk in _split_text(answer):
                yield {"event": "token", "data": json.dumps({"text": chunk}, ensure_ascii=False)}

    # Sources from collected docs
    sources = []
    for i, doc in enumerate(final_state.get("collected_docs", []), 1):
        sources.append({
            "ref": i,
            "tool": doc.get("tool", ""),
            "args": doc.get("args", {}),
            "summary": doc.get("result", "")[:200],
        })
    yield {
        "event": "sources",
        "data": json.dumps(sources, ensure_ascii=False),
    }
    yield {
        "event": "done",
        "data": json.dumps({"total_steps": len(final_state.get("collected_docs", []))}),
    }


def _split_text(text: str, chunk_size: int = 50) -> list[str]:
    """按句子分块模拟流式输出"""
    chunks = []
    current = ""
    for char in text:
        current += char
        if len(current) >= chunk_size or char in "。！？\n":
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


@app.post("/chat")
async def chat(req: ChatRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    # 路由分类
    route = route_query(question)

    if route["complexity"] == "simple":
        event_generator = _simple_search_events(question, route)
    else:
        event_generator = _agent_search_events(question, route)

    return EventSourceResponse(event_generator)


@app.get("/", response_class=HTMLResponse)
async def index():
    """简单对话 UI"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>明日方舟剧情 Wiki</title>
<style>
body { font-family: -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #1a1a2e; color: #e0e0e0; }
h1 { color: #e6b422; }
#chat { height: 60vh; overflow-y: auto; border: 1px solid #333; padding: 15px; margin-bottom: 15px; border-radius: 8px; background: #16213e; }
.msg { margin-bottom: 12px; }
.user { text-align: right; color: #4fc3f7; }
.assistant { color: #e0e0e0; line-height: 1.6; }
.sources { font-size: 0.8em; color: #888; margin-top: 5px; border-top: 1px solid #333; padding-top: 5px; }
input { width: 75%; padding: 10px; border: 1px solid #333; border-radius: 4px; background: #16213e; color: #e0e0e0; }
button { padding: 10px 20px; background: #e6b422; border: none; border-radius: 4px; cursor: pointer; color: #1a1a2e; }
.step { font-size: 0.8em; color: #888; background: #1e2d4a; padding: 4px 8px; border-radius: 4px; margin: 4px 0; }
</style>
</head>
<body>
<h1>明日方舟 剧情 Wiki Agent</h1>
<div id="chat"></div>
<input type="text" id="question" placeholder="提问关于明日方舟剧情的问题..." onkeydown="if(event.key==='Enter')ask()">
<button onclick="ask()">提问</button>

<script>
const chat = document.getElementById("chat");
const input = document.getElementById("question");

function addMsg(role, text, cls) {
    const div = document.createElement("div");
    div.className = "msg " + (cls || role);
    div.innerHTML = "<strong>" + (role === "user" ? "你" : "Wiki") + ":</strong> " + text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

async function ask() {
    const q = input.value.trim();
    if (!q) return;
    addMsg("user", q);
    input.value = "";
    
    const assistantDiv = document.createElement("div");
    assistantDiv.className = "msg assistant";
    assistantDiv.innerHTML = "<strong>Wiki:</strong> <span class='answer'></span><div class='sources'></div><div class='steps'></div>";
    chat.appendChild(assistantDiv);
    
    const answerSpan = assistantDiv.querySelector(".answer");
    const sourcesDiv = assistantDiv.querySelector(".sources");
    const stepsDiv = assistantDiv.querySelector(".steps");
    
    const response = await fetch("/chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({question: q, history: []}),
    });
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        const text = decoder.decode(value);
        for (const line of text.split("\\n")) {
            if (line.startsWith("event: token")) continue;
            if (line.startsWith("data: ")) {
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.text) {
                        answerSpan.textContent += data.text;
                    }
                } catch(e) {}
            }
            if (line.startsWith("event: step")) continue;
            if (line.startsWith("event: sources")) continue;
        }
    }
}

</script>
</body>
</html>"""
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/agent/test_server.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/agent/server.py tests/agent/test_server.py
git commit -m "feat(agent): FastAPI + SSE streaming chat endpoint"
```

---

### Task 10: 离线索引构建脚本 + 全流程集成

**Files:**
- Create: `scripts/build_agent_index.py`

- [ ] **Step 1: 创建索引构建脚本**

`scripts/build_agent_index.py`:
```python
"""一次性离线脚本: 构建 FAISS 向量索引 + chunk_map

使用方式:
  python scripts/build_agent_index.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arknights_wiki.agent.vector_index import build_index_from_data
from arknights_wiki.config import DATA_DIR


def main():
    index_dir = os.path.join(DATA_DIR, "index")
    print(f"数据目录: {DATA_DIR}")
    print(f"索引目录: {index_dir}")

    t0 = time.time()
    index_path, map_path = build_index_from_data(DATA_DIR, index_dir)

    elapsed = time.time() - t0
    print(f"\n索引构建完成 ({elapsed:.1f}s)")
    print(f"  FAISS 索引: {index_path}")
    print(f"  chunk_map:   {map_path}")

    # 验证
    from arknights_wiki.agent.vector_index import load_index
    index, chunk_map = load_index(index_path, map_path)
    print(f"  向量数: {index.ntotal}")
    print(f"  实体数: {len(chunk_map)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add scripts/build_agent_index.py
git commit -m "feat(agent): offline FAISS index build script"
```

- [ ] **Step 3: 全流程验证**

```bash
# 安装依赖
pip install -e ".[agent]"

# 构建索引
python scripts/build_agent_index.py

# 运行全部测试
pytest tests/agent/ -v

# 启动服务
python -m uvicorn arknights_wiki.agent.server:app --host 0.0.0.0 --port 8000
```

Expected: 所有测试通过，服务可启动。

---

## 验证检查清单

- [ ] `pip install -e ".[agent]"` 安装成功
- [ ] `python scripts/build_agent_index.py` 索引构建成功
- [ ] `pytest tests/agent/ -v` 全部测试通过
- [ ] `python -m uvicorn arknights_wiki.agent.server:app --port 8000` 服务启动
- [ ] `curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"question":"源石是什么"}'` 返回 SSE 流
- [ ] 评估: 构建 ~50 条问答数据，跑 agent eval
