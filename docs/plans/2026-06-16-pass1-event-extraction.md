# Pass 1 剧情骨架提取 — 实施计划

> **状态**: 已完成
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现三遍独立提取的第一遍——逐章拼接对话、调用 MiniMax M3 提取事件/角色/概念位置、后处理对齐、产出 JSON + 审阅 Markdown

**Architecture:** 五个独立模块按管道顺序连接：dialogue_loader → prompt_builder + llm_client → post_processor → orchestrator。每模块独立测试，无循环依赖。

**Tech Stack:** Python 3.12+, openai SDK, MiniMax M3 (128K context, 16384 max_tokens), difflib (标准库)

**Spec:** `docs/specs/2026-06-16-pass1-event-extraction.md`

> **状态**: 已完成

---

## 文件结构

```
arknights_wiki/extraction/
├── __init__.py              # 空，包标记
├── dialogue_loader.py       # 章节对话加载 + 拼接 + 分批
├── prompt_builder.py        # 系统/用户 prompt 组装
├── llm_client.py            # MiniMax M3 调用 + JSON 解析 + <think> 剥离
├── post_processor.py        # 角色名对齐 + 事件去重 + 分批合并 + 合法性校验
└── orchestrator.py          # 编排：章节目录遍历 → 调用链 → 落盘 + 审阅 Markdown

tests/test_extraction/
├── __init__.py
├── test_dialogue_loader.py
├── test_prompt_builder.py
├── test_llm_client.py
├── test_post_processor.py
└── test_orchestrator.py
```

---

### Task 1: dialogue_loader — 章节对话加载与拼接

**Files:**
- Create: `arknights_wiki/extraction/__init__.py`
- Create: `arknights_wiki/extraction/dialogue_loader.py`
- Create: `tests/test_extraction/__init__.py`
- Create: `tests/test_extraction/test_dialogue_loader.py`

- [x] **Step 1: 写失败测试 — 加载单章对话**

```python
# tests/test_extraction/test_dialogue_loader.py
import json, os, tempfile
from arknights_wiki.extraction.dialogue_loader import load_chapter, ChapterDialogue

def test_load_chapter_single_node():
    """加载包含一个 story node 的章节目录"""
    tmp = tempfile.mkdtemp()
    os.makedirs(f"{tmp}/测试章", exist_ok=True)
    node = {
        "id": "1-1_test",
        "title": "测试节点",
        "chapter": "测试章",
        "category": "main",
        "source_url": "https://example.com",
        "lines": [
            {"speaker": "阿米娅", "type": "dialogue", "text": "博士，准备好了吗？"},
            {"speaker": "博士", "type": "dialogue", "text": "走吧。"},
            {"speaker": "旁白", "type": "narration", "text": "罗德岛的走廊空无一人。"}
        ]
    }
    with open(f"{tmp}/测试章/1-1_test.json", "w", encoding="utf-8") as f:
        json.dump(node, f, ensure_ascii=False)

    result = load_chapter(f"{tmp}/测试章")

    assert isinstance(result, ChapterDialogue)
    assert result.chapter == "测试章"
    assert result.category == "main"
    assert len(result.lines) == 3
    assert result.lines[0] == {"index": 1, "speaker": "阿米娅", "type": "dialogue", "text": "博士，准备好了吗？"}
    assert result.lines[2] == {"index": 3, "speaker": "旁白", "type": "narration", "text": "罗德岛的走廊空无一人。"}
    assert "阿米娅" in result.text
    assert "罗德岛的走廊空无一人" in result.text
```

- [x] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_extraction/test_dialogue_loader.py::test_load_chapter_single_node -v
```
Expected: FAIL (ModuleNotFoundError)

- [x] **Step 3: 实现 dialogue_loader.py**

```python
# arknights_wiki/extraction/dialogue_loader.py
"""章节对话加载：遍历 JSON 文件 → 拼接为 [说话者] 文本 + 行号数组"""
import json, os
from dataclasses import dataclass, field


@dataclass
class ChapterDialogue:
    chapter: str
    category: str
    nodes: list[str] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)

    @property
    def text(self) -> str:
        """拼接为 [说话者] 文本\\n 格式"""
        parts = []
        for line in self.lines:
            if line["type"] == "dialogue" and line["speaker"]:
                parts.append(f"[{line['speaker']}] {line['text']}")
            else:
                parts.append(line["text"])
        return "\n".join(parts)

    @property
    def token_estimate(self) -> int:
        """粗略 token 估算：字符数 / 1.5"""
        return len(self.text) // 1.5


def load_chapter(chapter_dir: str) -> ChapterDialogue:
    """加载章节目录下所有 JSON 文件，按文件名排序拼接"""
    json_files = sorted(f for f in os.listdir(chapter_dir) if f.endswith(".json"))
    if not json_files:
        raise FileNotFoundError(f"章节目录 {chapter_dir} 下无 JSON 文件")

    chapter_name = os.path.basename(chapter_dir.rstrip("/\\"))
    result = ChapterDialogue(chapter=chapter_name, category="", nodes=[], lines=[])

    for jf in json_files:
        with open(os.path.join(chapter_dir, jf), "r", encoding="utf-8") as f:
            node = json.load(f)
        result.nodes.append(jf)
        if not result.category and node.get("category"):
            result.category = node["category"]
        for line in node.get("lines", []):
            result.lines.append({
                "index": len(result.lines) + 1,
                "speaker": line.get("speaker", ""),
                "type": line.get("type", "dialogue"),
                "text": line.get("text", ""),
            })

    return result


def split_chapter(cd: ChapterDialogue, max_tokens: int = 128000) -> list[ChapterDialogue]:
    """超大章切成 2 批，在总 token 数一半处最近 node 边界切断"""
    if cd.token_estimate <= max_tokens:
        return [cd]

    # 累计 token 找中点
    half_target = cd.token_estimate // 2
    cumulative = 0
    split_node_idx = 0
    for i, n in enumerate(cd.nodes):
        node_tokens = 0
        for line in cd.lines:
            if line.get("_node_file") == n:
                node_tokens += len(line.get("text", "")) // 1.5
        cumulative += node_tokens
        if cumulative >= half_target:
            split_node_idx = i
            break

    # 构建两个批次
    batch1_nodes = cd.nodes[:split_node_idx]
    batch2_nodes = cd.nodes[split_node_idx:]

    batch1 = ChapterDialogue(
        chapter=f"{cd.chapter} (批次 1/2)", category=cd.category,
        nodes=batch1_nodes, lines=_filter_lines(cd, batch1_nodes))
    batch2 = ChapterDialogue(
        chapter=f"{cd.chapter} (批次 2/2)", category=cd.category,
        nodes=batch2_nodes, lines=_filter_lines(cd, batch2_nodes))
    return [batch1, batch2]


def _filter_lines(cd: ChapterDialogue, target_nodes: list[str]) -> list[dict]:
    """过滤 lines 到指定 node 集合"""
    return [l for l in cd.lines if l.get("_node_file") in target_nodes]
```

注意：上面代码中 `_node_file` 需要在 load_chapter 时标记。修正 load_chapter 中的 lines 构建：

```python
for line in node.get("lines", []):
    result.lines.append({
        "index": len(result.lines) + 1,
        "speaker": line.get("speaker", ""),
        "type": line.get("type", "dialogue"),
        "text": line.get("text", ""),
        "_node_file": jf,
    })
```

- [x] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_extraction/test_dialogue_loader.py::test_load_chapter_single_node -v
```
Expected: PASS

- [x] **Step 5: 写多 node 排序测试**

```python
def test_load_chapter_multi_node_order():
    """多个 node 按文件名排序拼接，行号连续递增"""
    tmp = tempfile.mkdtemp()
    os.makedirs(f"{tmp}/测试章", exist_ok=True)
    for i, name in enumerate(["2_second.json", "1_first.json"]):
        node = {
            "id": f"1-{i}_test", "title": name, "chapter": "测试章",
            "category": "side", "source_url": "",
            "lines": [{"speaker": "测试角色", "type": "dialogue", "text": f"第{i}句"}]
        }
        with open(f"{tmp}/测试章/{name}", "w", encoding="utf-8") as f:
            json.dump(node, f, ensure_ascii=False)

    result = load_chapter(f"{tmp}/测试章")
    assert result.nodes[0] == "1_first.json"  # 按文件名排序
    assert result.nodes[1] == "2_second.json"
    assert result.lines[0]["index"] == 1
    assert result.lines[1]["index"] == 2
    assert result.category == "side"
```

- [x] **Step 6: 运行测试确认通过**

```bash
python -m pytest tests/test_extraction/test_dialogue_loader.py -v
```
Expected: 2 PASS

- [x] **Step 7: 写分批测试**

```python
def test_split_chapter_single_batch():
    """小章不拆分"""
    cd = ChapterDialogue(chapter="小章", category="main", nodes=["a.json"], lines=[
        {"index": 1, "speaker": "A", "type": "dialogue", "text": "短对话", "_node_file": "a.json"}
    ])
    batches = split_chapter(cd)
    assert len(batches) == 1
    assert batches[0] is cd


def test_split_chapter_two_batches():
    """超长章切成 2 批"""
    # 构建一个 token_estimate 超过 128000 的章节
    lines = []
    nodes = []
    # 100 个 node，每个 ~2000 tokens
    for ni in range(100):
        nname = f"{ni:03d}_node.json"
        nodes.append(nname)
        for li in range(200):
            lines.append({
                "index": len(lines) + 1,
                "speaker": f"角色{ni}",
                "type": "dialogue",
                "text": "长文本。" * 20,  # ~80 chars
                "_node_file": nname,
            })

    cd = ChapterDialogue(chapter="超大章", category="main", nodes=nodes, lines=lines)
    assert cd.token_estimate > 128000

    batches = split_chapter(cd)
    assert len(batches) == 2
    assert "批次 1/2" in batches[0].chapter
    assert "批次 2/2" in batches[1].chapter
    assert len(batches[0].lines) + len(batches[1].lines) == len(lines)
```

- [x] **Step 8: 运行测试确认通过**

```bash
python -m pytest tests/test_extraction/test_dialogue_loader.py -v
```
Expected: 4 PASS

- [x] **Step 9: Commit**

```bash
git add arknights_wiki/extraction/__init__.py arknights_wiki/extraction/dialogue_loader.py tests/test_extraction/
git commit -m "feat(extraction): add dialogue_loader — chapter JSON loading, concatenation, splitting"
```

---

### Task 2: prompt_builder — Prompt 组装

**Files:**
- Create: `arknights_wiki/extraction/prompt_builder.py`
- Create: `tests/test_extraction/test_prompt_builder.py`

- [x] **Step 1: 写失败测试 — 基础 prompt 构建**

```python
# tests/test_extraction/test_prompt_builder.py
from arknights_wiki.extraction.prompt_builder import build_system_prompt, build_user_prompt

def test_build_system_prompt_contains_key_elements():
    prompt = build_system_prompt()
    assert "明日方舟" in prompt
    assert "JSON" in prompt
    assert "markdown" in prompt
    assert "line_range" in prompt
    assert "snake_case" in prompt
    assert "泛型" in prompt or "泛型角色" in prompt
    assert "实质" in prompt  # 概念讨论区分


def test_build_user_prompt_includes_chapter_and_dialogue():
    prompt = build_user_prompt(
        chapter="黑暗时代·上",
        dialogue_text="[阿米娅] 博士！\n[博士] 嗯。",
        total_lines=2
    )
    assert "黑暗时代·上" in prompt
    assert "[阿米娅] 博士！" in prompt
    assert "line_range" in prompt
    assert "output_schema" in prompt or "events" in prompt
```

- [x] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_extraction/test_prompt_builder.py -v
```
Expected: FAIL

- [x] **Step 3: 实现 prompt_builder.py**

```python
# arknights_wiki/extraction/prompt_builder.py
"""组装 system prompt 和 user prompt"""

SYSTEM_PROMPT = """你是一个《明日方舟》剧情深度分析师。你的任务是通读完整章节的对话，提取结构化信息。

严格遵守以下规则：

1. **输出格式**：严格输出 JSON，不要包含 ```json``` 等 markdown 代码块标记。
2. **事件提取**：提取本章所有关键事件，数量随内容密度浮动——战斗密集的章节自然事件多，对话为主的章节自然事件少。不凑数不遗漏。每个事件的 type 用 snake_case 英文自由描述，如 battle, political_intrigue, sacrifice, revelation 等。参考类型：battle, ambush, siege, retreat, infiltration, revelation, investigation, negotiation, alliance, betrayal, confrontation, sacrifice, rescue, departure, reunion, ceremony, emotional_breakthrough, flashback, disaster, planning, political_intrigue, assassination, rebellion, training, dream_vision。
3. **角色提取**：提取有名字、有台词、有剧情作用的角色。泛型角色不提取——"整合运动成员"、"罗德岛干员"、"某个士兵"、"路过的居民"等无名群体不列为 characters。operator 类角色使用规范名。
4. **概念标注**：只标注被角色"实质性讨论"的概念——角色在解释、描述、辩论某个世界观要素的本质/机制/历史时才算讨论。仅作为名词标签提及不算。
   - ✅ 标注："食腐者是萨卡兹中最古老的分支之一，他们的身体能吸收源石能量"——在讨论食腐者的本质
   - ❌ 不标注："前方发现食腐者小队！准备迎战。"——只是提到名字作为敌人标识
5. **行号范围**：line_range 对应对话的行号（从 1 开始），必须精确指向相关对话段落。"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


OUTPUT_SCHEMA = """```json
{
  "chapter": "章节名",
  "category": "main|side|special",
  "summary": "3-5段章节摘要，按时间顺序，覆盖主要剧情推进",

  "events": [{
    "event": "事件描述（一句话）",
    "type": "snake_case 事件类型",
    "line_range": [起始行号, 结束行号],
    "participants": ["参与角色名"],
    "location": "发生地点（如能确定）",
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
```"""


def build_user_prompt(chapter: str, dialogue_text: str, total_lines: int) -> str:
    return f"""以下是「{chapter}」章节的完整对话。共 {total_lines} 行。

## 对话
{dialogue_text}

## 输出 JSON 格式
{OUTPUT_SCHEMA}

## 规则
- 必须基于提供的对话内容，不要编造
- 泛型角色（整合运动成员、罗德岛干员、士兵、居民、路人等）不提取为 characters
- concepts 只记录被实质性讨论的概念（解释/描述/辩论其本质），不是关键词匹配
- 事件类型用 snake_case 英文描述，覆盖剧情中各种可能的场景
- line_range 对应上述对话文本的行号（从第 1 行开始计数）"""
```

- [x] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_extraction/test_prompt_builder.py -v
```
Expected: 2 PASS

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/extraction/prompt_builder.py tests/test_extraction/test_prompt_builder.py
git commit -m "feat(extraction): add prompt_builder — system + user prompt assembly"
```

---

### Task 3: llm_client — MiniMax M3 调用与 JSON 解析

**Files:**
- Create: `arknights_wiki/extraction/llm_client.py`
- Create: `tests/test_extraction/test_llm_client.py`

- [x] **Step 1: 写失败测试 — JSON 解析与 think 标签剥离**

```python
# tests/test_extraction/test_llm_client.py
from arknights_wiki.extraction.llm_client import parse_llm_response, strip_think_tags

def test_strip_think_tags_basic():
    text = "<think>这是思考内容</think>\n{\"key\": \"value\"}"
    result = strip_think_tags(text)
    assert "<think>" not in result
    assert "这是思考内容" not in result
    assert '{"key": "value"}' in result


def test_strip_think_tags_no_think():
    text = '{"key": "value"}'
    result = strip_think_tags(text)
    assert result == text


def test_strip_think_tags_multiline_think():
    text = "<think>\n多行\n思考\n</think>\n{\"key\": \"value\"}"
    result = strip_think_tags(text)
    assert "<think>" not in result
    assert '{"key": "value"}' in result


def test_parse_llm_response_valid_json():
    result = parse_llm_response('{"chapter": "测试章", "events": []}')
    assert result["chapter"] == "测试章"
    assert result["events"] == []


def test_parse_llm_response_with_think():
    raw = "<think>思考...</think>\n{\"chapter\": \"测试章\", \"events\": []}"
    result = parse_llm_response(raw)
    assert result["chapter"] == "测试章"


def test_parse_llm_response_markdown_wrapped():
    raw = '```json\n{"chapter": "测试章", "events": []}\n```'
    result = parse_llm_response(raw)
    assert result["chapter"] == "测试章"


def test_parse_llm_response_malformed_returns_none():
    result = parse_llm_response("不是 JSON")
    assert result is None
```

- [x] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_extraction/test_llm_client.py -v
```
Expected: FAIL

- [x] **Step 3: 实现 llm_client.py**

```python
# arknights_wiki/extraction/llm_client.py
"""MiniMax M3 API 调用 + JSON 解析 + <think> 标签剥离"""
import json, os, re
from openai import OpenAI


def strip_think_tags(text: str) -> str:
    """移除 MiniMax M3 输出的 <think>...</think> 标签"""
    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()


def parse_llm_response(raw: str) -> dict | None:
    """从 LLM 原始输出中提取 JSON"""
    text = strip_think_tags(raw).strip()

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 块
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 尝试提取 { ... } 块
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return None


def create_client() -> OpenAI:
    """创建 MiniMax API 客户端"""
    api_key = os.environ.get("minimax_api", "")
    if not api_key:
        raise RuntimeError("环境变量 minimax_api 未设置")
    return OpenAI(api_key=api_key, base_url="https://api.minimaxi.com/v1")


def call_llm(
    client: OpenAI,
    system_prompt: str,
    user_prompt: str,
    model: str = "MiniMax-M3",
    temperature: float = 0.1,
    max_tokens: int = 16384,
    max_retries: int = 3,
) -> dict:
    """调用 LLM，自动重试 JSON 解析失败"""
    last_raw = None
    for attempt in range(max_retries):
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw = response.choices[0].message.content or ""
        usage = response.usage
        stats = {
            "tokens_in": usage.prompt_tokens if usage else 0,
            "tokens_out": usage.completion_tokens if usage else 0,
        }

        parsed = parse_llm_response(raw)
        if parsed is not None:
            parsed["_stats"] = stats
            return parsed

        last_raw = raw

    return {"_parse_error": True, "_raw": last_raw, "_stats": stats}
```

- [x] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_extraction/test_llm_client.py -v
```
Expected: 7 PASS

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/extraction/llm_client.py tests/test_extraction/test_llm_client.py
git commit -m "feat(extraction): add llm_client — MiniMax M3 wrapper with think tag stripping"
```

---

### Task 4: post_processor — 角色名对齐 + 事件去重 + 分批合并

**Files:**
- Create: `arknights_wiki/extraction/post_processor.py`
- Create: `tests/test_extraction/test_post_processor.py`

- [x] **Step 1: 写失败测试**

```python
# tests/test_extraction/test_post_processor.py
from arknights_wiki.extraction.post_processor import (
    align_character_names,
    deduplicate_events,
    merge_batches,
    validate_extraction,
    load_identity_map,
    normalize_character_type,
)

# ─── 角色类型标准化 ───

def test_normalize_character_type_infer_from_identity_map():
    """identity_map 中有的视为 operator，否则保持原样"""
    id_map = {"耀骑士临光": "character:KZ01", "W": "character:B00W"}
    assert normalize_character_type({"name": "耀骑士临光", "type": "npc"}, id_map) == "operator"
    assert normalize_character_type({"name": "塔露拉", "type": "npc"}, id_map) == "npc"
    assert normalize_character_type({"name": "阿米娅", "type": "operator"}, id_map) == "operator"


# ─── 角色名对齐 ───

def test_align_character_names_exact_match():
    """精确匹配 operators.json name_zh"""
    operators = [{"name_zh": "阿米娅"}, {"name_zh": "凯尔希"}]
    chars = [
        {"name": "阿米娅", "type": "operator", "role_in_chapter": "..."},
        {"name": "Amiya", "type": "operator", "role_in_chapter": "..."},
    ]
    result, unmatched = align_character_names(chars, operators, {})
    assert result[0]["name"] == "阿米娅"  # 精确匹配不变
    assert result[1]["name"] == "Amiya"   # 无匹配保持原名
    assert len(unmatched) == 1


def test_align_character_names_identity_map_match():
    """identity_map 别名→规范名"""
    operators = [{"name_zh": "阿米娅"}, {"name_zh": "凯尔希"}]
    id_map = {"Guard": "character:R001"}
    chars = [
        {"name": "Guard", "type": "operator", "role_in_chapter": "..."},
    ]
    result, _ = align_character_names(chars, operators, id_map)
    assert result[0]["name"] == "Guard"  # identity_map 不改变 name，但 type 修正
    assert result[0]["type"] == "operator"


def test_align_character_names_fuzzy_match():
    """模糊匹配：Levenshtein ≤ 2"""
    operators = [{"name_zh": "阿米娅"}, {"name_zh": "陈晖洁"}]
    chars = [
        {"name": "阿米亚", "type": "operator", "role_in_chapter": "..."},
        {"name": "陈辉洁", "type": "operator", "role_in_chapter": "..."},
    ]
    result, _ = align_character_names(chars, operators, {})
    assert result[0]["name"] == "阿米娅"
    assert result[1]["name"] == "陈晖洁"


# ─── 事件去重 ───

def test_deduplicate_events_merge_similar():
    events = [
        {"event": "Logos断后对抗孽茨雷", "type": "battle", "line_range": [1, 5]},
        {"event": "Logos独自断后抵挡孽茨雷", "type": "battle", "line_range": [3, 8]},
        {"event": "阿米娅召集小队", "type": "planning", "line_range": [10, 15]},
    ]
    result = deduplicate_events(events)
    # 前两条相似度高应合并，第三条独立保留
    assert len(result) <= 3
    events_texts = [e["event"] for e in result]
    assert "阿米娅召集小队" in events_texts


# ─── 分批合并 ───

def test_merge_batches():
    batch1 = {
        "chapter": "测试章 (批次 1/2)", "category": "main",
        "summary": "第一部分摘要",
        "events": [
            {"event": "事件A", "type": "battle", "line_range": [1, 10]},
            {"event": "事件B", "type": "meeting", "line_range": [11, 20]},
        ],
        "characters": [
            {"name": "阿米娅", "type": "operator", "role_in_chapter": "...", "first_appearance_chapter": True},
        ],
        "concepts": [
            {"concept": "源石", "line_range": [5, 15], "discussion_summary": "...", "is_substantive": True},
        ],
    }
    batch2 = {
        "chapter": "测试章 (批次 2/2)", "category": "main",
        "summary": "第二部分摘要",
        "events": [
            {"event": "事件C", "type": "battle", "line_range": [21, 30]},
        ],
        "characters": [
            {"name": "阿米娅", "type": "operator", "role_in_chapter": "...", "first_appearance_chapter": False},
            {"name": "凯尔希", "type": "operator", "role_in_chapter": "...", "first_appearance_chapter": True},
        ],
        "concepts": [],
    }
    merged = merge_batches([batch1, batch2], chapter="测试章")
    assert merged["chapter"] == "测试章"
    assert merged["batch_count"] == 2
    assert len(merged["events"]) == 3
    assert len(merged["characters"]) == 2  # 阿米娅 去重
    assert merged["characters"][0]["first_appearance_chapter"] == True  # 保留 True


# ─── 合法性校验 ───

def test_validate_extraction_valid():
    data = {
        "chapter": "测试", "category": "main",
        "events": [{"event": "测试事件", "type": "battle", "line_range": [1, 5]}],
    }
    errors = validate_extraction(data, total_lines=10)
    assert len(errors) == 0


def test_validate_extraction_missing_events():
    errors = validate_extraction({"chapter": "测试", "category": "main", "events": []}, total_lines=10)
    assert any("events" in e for e in errors)


def test_validate_extraction_line_range_out_of_bounds():
    data = {
        "chapter": "测试", "category": "main",
        "events": [{"event": "测试", "type": "battle", "line_range": [1, 999]}],
    }
    errors = validate_extraction(data, total_lines=10)
    assert any("999" in e or "超出" in e for e in errors)
```

- [x] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_extraction/test_post_processor.py -v
```
Expected: FAIL

- [x] **Step 3: 实现 post_processor.py**

```python
# arknights_wiki/extraction/post_processor.py
"""后处理：角色名对齐 + 事件去重 + 分批合并 + 合法性校验"""
import json
from difflib import SequenceMatcher


def load_identity_map(config_path: str = "config/identity_map.json") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mappings", {})


def normalize_character_type(char: dict, id_map: dict) -> str:
    """根据 identity_map 修正角色 type"""
    for alias in id_map:
        if alias == char["name"] or char["name"] == alias:
            return "operator"
    return char["type"]


def align_character_names(
    characters: list[dict],
    operators: list[dict],
    id_map: dict,
) -> tuple[list[dict], list[str]]:
    """角色名对齐到规范名。返回 (对齐后的角色列表, 未匹配列表)"""
    op_names = {op["name_zh"] for op in operators}
    unmatched = []

    for char in characters:
        name = char["name"]
        # 1. 精确匹配
        if name in op_names:
            continue
        # 2. identity_map 匹配
        if name in id_map:
            char["type"] = "operator"
            continue
        # 3. 模糊匹配
        best_ratio = 0
        best_name = name
        for opn in op_names:
            ratio = SequenceMatcher(None, name, opn).ratio()
            if ratio >= 0.85 and ratio > best_ratio:
                best_ratio = ratio
                best_name = opn
        if best_ratio >= 0.85:
            char["name"] = best_name
            char["type"] = "operator"
        else:
            unmatched.append(name)

    return characters, unmatched


def deduplicate_events(events: list[dict], threshold: float = 0.85) -> list[dict]:
    """事件去重：相似度 > threshold 合并"""
    if len(events) <= 1:
        return events

    kept = []
    merged_indices = set()

    for i, e1 in enumerate(events):
        if i in merged_indices:
            continue
        best = e1
        for j, e2 in enumerate(events):
            if j <= i or j in merged_indices:
                continue
            ratio = SequenceMatcher(None, e1["event"], e2["event"]).ratio()
            if ratio >= threshold:
                # 保留更详细的（更长的 event 描述 + 更宽的 line_range）
                if len(e2["event"]) > len(best["event"]):
                    best = e2
                merged_indices.add(j)
        kept.append(best)

    return kept


def merge_batches(batches: list[dict], chapter: str) -> dict:
    """合并多个批次的提取结果"""
    if len(batches) == 1:
        result = dict(batches[0])
        result["chapter"] = chapter
        result["batch_count"] = 1
        return result

    merged = {
        "chapter": chapter,
        "category": batches[0]["category"],
        "batch_count": len(batches),
        "summary": "\n\n".join(b.get("summary", "") for b in batches),
        "events": [],
        "characters": [],
        "concepts": [],
    }

    # events: 按 line_range 排序
    all_events = []
    for b in batches:
        all_events.extend(b.get("events", []))
    all_events.sort(key=lambda e: e.get("line_range", [0, 0])[0])
    merged["events"] = deduplicate_events(all_events)

    # characters: 同名合并
    seen_chars = {}
    for b in batches:
        for c in b.get("characters", []):
            name = c["name"]
            if name in seen_chars:
                # 保留 first_appearance_chapter=True
                if c.get("first_appearance_chapter"):
                    seen_chars[name]["first_appearance_chapter"] = True
            else:
                seen_chars[name] = dict(c)
    merged["characters"] = list(seen_chars.values())

    # concepts: 同名合并 line_range
    seen_concepts = {}
    for b in batches:
        for c in b.get("concepts", []):
            name = c["concept"]
            if name in seen_concepts:
                existing = seen_concepts[name]
                lr = c.get("line_range", [0, 0])
                existing["line_range"] = [
                    min(existing["line_range"][0], lr[0]),
                    max(existing["line_range"][1], lr[1]),
                ]
            else:
                seen_concepts[name] = dict(c)
    merged["concepts"] = list(seen_concepts.values())

    return merged


def validate_extraction(data: dict, total_lines: int) -> list[str]:
    """合法性校验，返回错误信息列表"""
    errors = []
    if not data.get("chapter"):
        errors.append("chapter 字段为空")
    if not data.get("category"):
        errors.append("category 字段为空")
    if not data.get("events"):
        errors.append("events 数组为空")

    for i, event in enumerate(data.get("events", [])):
        if not event.get("event"):
            errors.append(f"events[{i}].event 为空")
        if not event.get("type"):
            errors.append(f"events[{i}].type 为空")
        lr = event.get("line_range", [])
        if not isinstance(lr, list) or len(lr) != 2:
            errors.append(f"events[{i}].line_range 无效: {lr}")
        elif lr[1] > total_lines:
            errors.append(f"events[{i}].line_range {lr} 超出总行数 {total_lines}")

    return errors
```

- [x] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_extraction/test_post_processor.py -v
```
Expected: 10 PASS

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/extraction/post_processor.py tests/test_extraction/test_post_processor.py
git commit -m "feat(extraction): add post_processor — character alignment, event dedup, batch merge"
```

---

### Task 5: orchestrator — 编排器 + 审阅 Markdown 生成

**Files:**
- Create: `arknights_wiki/extraction/orchestrator.py`
- Create: `tests/test_extraction/test_orchestrator.py`

- [x] **Step 1: 写失败测试 — 单章提取流程**

```python
# tests/test_extraction/test_orchestrator.py
import json, os, tempfile
from arknights_wiki.extraction.orchestrator import (
    generate_review_markdown,
    save_extraction,
    discover_chapters,
)

def test_discover_chapters():
    """发现章节目录"""
    tmp = tempfile.mkdtemp()
    for cat in ["main", "side"]:
        os.makedirs(f"{tmp}/{cat}/测试章", exist_ok=True)
        node = {
            "id": "1-1", "title": "测试", "chapter": "测试章",
            "category": cat, "source_url": "",
            "lines": [{"speaker": "阿米娅", "type": "dialogue", "text": "测试"}]
        }
        with open(f"{tmp}/{cat}/测试章/1-1.json", "w", encoding="utf-8") as f:
            json.dump(node, f, ensure_ascii=False)

    chapters = discover_chapters(tmp)
    assert ("main", "测试章") in chapters
    assert ("side", "测试章") in chapters


def test_generate_review_markdown():
    """生成审阅 Markdown"""
    data = {
        "chapter": "慈悲灯塔",
        "category": "main",
        "summary": "测试摘要",
        "events": [
            {"event": "战斗开始", "type": "battle", "line_range": [1, 10],
             "participants": ["阿米娅"], "location": "战场", "significance": "重要"},
        ],
        "characters": [
            {"name": "阿米娅", "type": "operator", "role_in_chapter": "指挥"},
        ],
        "concepts": [
            {"concept": "源石", "line_range": [5, 8],
             "discussion_summary": "讨论源石的本质", "is_substantive": True},
        ],
    }
    lines = ["[阿米娅] 准备作战。", "[旁白] 战场硝烟弥漫。"]

    md = generate_review_markdown(data, lines)
    assert "# 慈悲灯塔" in md
    assert "战斗开始" in md
    assert "battle" in md
    assert "阿米娅" in md
    assert "源石" in md


def test_save_extraction_creates_directory_and_file():
    """保存提取结果自动创建目录"""
    tmp = tempfile.mkdtemp()
    data = {
        "chapter": "测试章", "category": "main", "processed_at": "2026-06-16",
        "model": "MiniMax-M3", "batch_count": 1, "summary": "测试",
        "events": [], "characters": [], "concepts": [],
        "stats": {"tokens_in": 100, "tokens_out": 50, "elapsed_s": 2.0},
    }
    output_dir = f"{tmp}/extractions/v1_events"
    save_extraction(data, output_dir)
    path = f"{output_dir}/main/测试章.json"
    assert os.path.exists(path)
    loaded = json.load(open(path, encoding="utf-8"))
    assert loaded["chapter"] == "测试章"
```

- [x] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_extraction/test_orchestrator.py -v
```
Expected: FAIL

- [x] **Step 3: 实现 orchestrator.py**

```python
# arknights_wiki/extraction/orchestrator.py
"""编排器：章节目录遍历 → 对话加载 → LLM 调用 → 后处理 → 落盘 + 审阅 Markdown"""
import json, os, time
from datetime import datetime, timezone

from .dialogue_loader import load_chapter, split_chapter
from .prompt_builder import build_system_prompt, build_user_prompt
from .llm_client import create_client, call_llm
from .post_processor import (
    align_character_names,
    load_identity_map,
    merge_batches,
    validate_extraction,
)


def discover_chapters(data_dir: str = "data/stories") -> list[tuple[str, str]]:
    """发现所有章节，返回 [(category, chapter_name), ...]"""
    chapters = []
    for category in ["main", "side", "special"]:
        cat_dir = os.path.join(data_dir, category)
        if not os.path.isdir(cat_dir):
            continue
        for ch_name in sorted(os.listdir(cat_dir)):
            ch_dir = os.path.join(cat_dir, ch_name)
            if os.path.isdir(ch_dir) and any(f.endswith(".json") for f in os.listdir(ch_dir)):
                chapters.append((category, ch_name))
    return chapters


def extract_chapter(
    category: str,
    chapter: str,
    data_dir: str = "data/stories",
    identity_map_path: str = "config/identity_map.json",
    operators_path: str = "data/operators.json",
) -> dict:
    """提取单章：加载 → 分批 → LLM → 合并 → 后处理"""
    chapter_dir = os.path.join(data_dir, category, chapter)
    cd = load_chapter(chapter_dir)
    batches = split_chapter(cd)

    # 加载辅助数据
    id_map = load_identity_map(identity_map_path)
    with open(operators_path, "r", encoding="utf-8") as f:
        operators = json.load(f)["operators"]

    client = create_client()
    system_prompt = build_system_prompt()
    all_batches = []
    total_stats = {"tokens_in": 0, "tokens_out": 0, "elapsed_s": 0}

    for batch in batches:
        user_prompt = build_user_prompt(
            chapter=batch.chapter,
            dialogue_text=batch.text,
            total_lines=len(batch.lines),
        )

        t0 = time.time()
        llm_result = call_llm(client, system_prompt, user_prompt)
        elapsed = time.time() - t0

        if llm_result.get("_parse_error"):
            print(f"  WARNING: {chapter} JSON 解析失败，记录原始输出")
            all_batches.append({
                "chapter": batch.chapter, "category": cd.category,
                "summary": "", "events": [], "characters": [], "concepts": [],
                "_parse_error": True, "_raw": llm_result.get("_raw", ""),
            })
        else:
            stats = llm_result.pop("_stats", {})
            total_stats["tokens_in"] += stats.get("tokens_in", 0)
            total_stats["tokens_out"] += stats.get("tokens_out", 0)
            all_batches.append(llm_result)

        total_stats["elapsed_s"] += elapsed

    # 合并批次
    merged = merge_batches(all_batches, chapter)
    merged["processed_at"] = datetime.now(timezone.utc).isoformat()
    merged["model"] = "MiniMax-M3"
    merged["stats"] = total_stats

    # 合法性校验
    errors = validate_extraction(merged, len(cd.lines))
    if errors:
        merged["_validation_errors"] = errors

    # 角色名对齐
    if merged.get("characters"):
        merged["characters"], unmatched = align_character_names(
            merged["characters"], operators, id_map)
        if unmatched:
            merged["_unmatched_names"] = unmatched

    return merged


def save_extraction(data: dict, output_base: str = "data/extractions/v1_events") -> str:
    """保存提取结果 JSON"""
    category = data["category"]
    chapter = data["chapter"]
    out_dir = os.path.join(output_base, category)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{chapter}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out_path


def generate_review_markdown(data: dict, lines: list[str]) -> str:
    """生成人工审阅 Markdown"""
    chapter = data["chapter"]
    md = f"# {chapter}\n\n"
    md += f"**类别:** {data.get('category', '')} | "
    md += f"**模型:** {data.get('model', '')} | "
    md += f"**批次:** {data.get('batch_count', 1)}\n\n"

    # 摘要
    md += "## 章节摘要\n\n"
    md += data.get("summary", "无") + "\n\n"

    # 事件列表
    md += "## 事件列表\n\n"
    for i, ev in enumerate(data.get("events", []), 1):
        md += f"### {i}. {ev.get('type', '?')} — {ev.get('event', '?')}\n\n"
        md += f"- **行号范围:** {ev.get('line_range', [])}\n"
        md += f"- **参与角色:** {', '.join(ev.get('participants', []))}\n"
        md += f"- **地点:** {ev.get('location', '未知')}\n"
        md += f"- **意义:** {ev.get('significance', '')}\n\n"

        # 原文引用
        lr = ev.get("line_range", [0, 0])
        if lr[0] > 0 and lr[0] <= len(lines):
            md += "**原文引用:**\n\n```\n"
            for li in range(lr[0] - 1, min(lr[1], len(lines))):
                if li < len(lines):
                    md += f"[{li + 1}] {lines[li]}\n"
            md += "```\n\n"

    # 角色列表
    md += "## 角色列表\n\n"
    md += "| 名称 | 类型 | 本章角色 | 首次登场 |\n"
    md += "|------|------|----------|----------|\n"
    for c in data.get("characters", []):
        first = "Y" if c.get("first_appearance_chapter") else ""
        md += f"| {c['name']} | {c.get('type', '')} | {c.get('role_in_chapter', '')} | {first} |\n"

    # 概念列表
    md += "\n## 概念列表\n\n"
    for c in data.get("concepts", []):
        md += f"### {c.get('concept', '')}\n\n"
        md += f"- **行号范围:** {c.get('line_range', [])}\n"
        md += f"- **讨论摘要:** {c.get('discussion_summary', '')}\n"
        md += f"- **实质讨论:** {c.get('is_substantive', False)}\n\n"

    return md


def run_trial(
    trial_chapters: list[tuple[str, str]],
    data_dir: str = "data/stories",
) -> dict[str, dict]:
    """试跑：提取指定章节，生成 JSON + 审阅 Markdown"""
    results = {}
    os.makedirs("output/trial_review", exist_ok=True)

    for category, chapter in trial_chapters:
        print(f"\n{'='*50}")
        print(f"提取: [{category}] {chapter}")
        print(f"{'='*50}")

        data = extract_chapter(category, chapter, data_dir)

        # 保存 JSON
        save_extraction(data)

        # 生成审阅 Markdown
        chapter_dir = os.path.join(data_dir, category, chapter)
        try:
            cd = load_chapter(chapter_dir)
            review_texts = [l["text"] for l in cd.lines]
        except Exception:
            review_texts = []
        md = generate_review_markdown(data, review_texts)
        md_path = f"output/trial_review/{chapter}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)

        print(f"  事件: {len(data.get('events', []))}")
        print(f"  角色: {len(data.get('characters', []))}")
        print(f"  概念: {len(data.get('concepts', []))}")
        if data.get("_validation_errors"):
            print(f"  校验错误: {data['_validation_errors']}")
        if data.get("_unmatched_names"):
            print(f"  未匹配角色名: {data['_unmatched_names']}")
        print(f"  JSON → data/extractions/v1_events/{category}/{chapter}.json")
        print(f"  Markdown → {md_path}")

        results[chapter] = data

    return results


def run_all(
    data_dir: str = "data/stories",
    skip_chapters: set = None,
) -> list[dict]:
    """全量 109 章提取"""
    if skip_chapters is None:
        skip_chapters = set()

    chapters = discover_chapters(data_dir)
    results = []

    for category, chapter in chapters:
        if chapter in skip_chapters:
            continue
        print(f"[{category}] {chapter} ...", end=" ", flush=True)
        try:
            data = extract_chapter(category, chapter, data_dir)
            save_extraction(data)
            n_events = len(data.get("events", []))
            n_chars = len(data.get("characters", []))
            toks = data.get("stats", {}).get("tokens_in", 0)
            elapsed = data.get("stats", {}).get("elapsed_s", 0)
            print(f"events={n_events} chars={n_chars} toks_in={toks} {elapsed:.1f}s")
            results.append(data)
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"chapter": chapter, "category": category, "_error": str(e)})

    return results
```

- [x] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_extraction/test_orchestrator.py -v
```
Expected: 3 PASS

- [x] **Step 5: Commit**

```bash
git add arknights_wiki/extraction/orchestrator.py tests/test_extraction/test_orchestrator.py
git commit -m "feat(extraction): add orchestrator — chapter extraction pipeline + review markdown"
```

---

### Task 6: 试跑 6 章

- [x] **Step 1: 运行试跑脚本**

```python
# 在项目根目录交互运行
from arknights_wiki.extraction.orchestrator import run_trial

TRIAL = [
    ("main", "黑暗时代·上"),
    ("main", "怒号光明"),
    ("main", "慈悲灯塔"),
    ("side", "孤星"),
    ("side", "相见欢"),
    ("side", "长夜临光"),
]

results = run_trial(TRIAL)
```

- [x] **Step 2: 检查输出文件**

```bash
ls data/extractions/v1_events/main/
ls data/extractions/v1_events/side/
ls output/trial_review/
```

Expected: 6 个 JSON + 6 个 Markdown 都存在

- [x] **Step 3: 呈现试跑结果给用户审阅**

```
试跑完成。输出位置:
  JSON: data/extractions/v1_events/{category}/{chapter}.json
  Markdown: output/trial_review/{chapter}.md

每章统计:
  ...summary table...
```

- [x] **Step 4: Commit 试跑结果**

```bash
git add data/extractions/v1_events/ output/trial_review/
git commit -m "feat(extraction): add 6-chapter trial run results"
```

---

### Task 7: 全量 109 章运行（试跑审阅通过后）

- [x] **Step 1: 运行全量**

```python
from arknights_wiki.extraction.orchestrator import run_all

results = run_all(skip_chapters={
    "黑暗时代·上", "怒号光明", "慈悲灯塔", "孤星", "相见欢", "长夜临光"
})
print(f"全量完成: {len(results)} 章")
```

- [x] **Step 2: 汇总统计**

```bash
python -c "
import json, os
base = 'data/extractions/v1_events'
total_events = total_chars = total_concepts = 0
total_tokens_in = total_tokens_out = 0
for cat in ['main','side','special']:
    d = os.path.join(base, cat)
    if not os.path.isdir(d): continue
    for f in os.listdir(d):
        if f.endswith('.json'):
            with open(os.path.join(d, f)) as fh:
                data = json.load(fh)
            total_events += len(data.get('events', []))
            total_chars += len(data.get('characters', []))
            total_concepts += len(data.get('concepts', []))
            s = data.get('stats', {})
            total_tokens_in += s.get('tokens_in', 0)
            total_tokens_out += s.get('tokens_out', 0)
print(f'章节: 109')
print(f'事件: {total_events}')
print(f'角色: {total_chars}')
print(f'概念: {total_concepts}')
print(f'Token in: {total_tokens_in:,}')
print(f'Token out: {total_tokens_out:,}')
"
```

- [x] **Step 3: Commit**

```bash
git add data/extractions/v1_events/
git commit -m "feat(extraction): full 109-chapter pass 1 extraction complete"
```

---

## 执行顺序

```
Task 1 (dialogue_loader)  →  Task 2 (prompt_builder)  →  Task 3 (llm_client)
                                    ↓                          ↓
                              Task 4 (post_processor)  ←────────┘
                                    ↓
                              Task 5 (orchestrator)
                                    ↓
                              Task 6 (试跑 6 章)  →  用户审阅
                                    ↓
                              Task 7 (全量 109 章)
```

Task 1-3 可并行，Task 4 依赖 Task 1-3，Task 5 依赖全部。
