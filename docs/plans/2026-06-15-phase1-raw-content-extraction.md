# Phase 1: 原始内容提取 — 实施计划

> **关联 Spec:** `docs/specs/2026-06-15-phase1-raw-content-extraction.md`
> **状态:** 草稿

**目标:** 从 mrfz 迁移 scraper 管线到 `arknights_wiki/pipeline/`，新增干员数据提取能力

**验证标准:** 每个模块都可独立导入；`init_pipeline()` 能完成剧情索引+干员数据抓取；生成 Markdown 输出

---

### Task 1: 项目骨架

**Files:**
- Create: `pyproject.toml`
- Create: `arknights_wiki/__init__.py`
- Create: `arknights_wiki/config.py`
- Create: `tests/test_config.py`
- Create: `arknights_wiki/pipeline/__init__.py`

- [ ] **Step 1: 写 config 测试**

```python
# tests/test_config.py
import os
from arknights_wiki import config


def test_project_root_exists():
    """项目根目录应存在"""
    assert os.path.isdir(config.PROJECT_ROOT)


def test_data_dir_default():
    """默认 DATA_DIR 应在项目根下"""
    assert config.DATA_DIR.endswith("data")
    assert config.DATA_DIR.startswith(config.PROJECT_ROOT)


def test_data_dir_env_override(monkeypatch):
    """环境变量可覆盖 DATA_DIR"""
    monkeypatch.setenv("ARKNIGHTS_DATA_DIR", "/tmp/test_data")
    import importlib
    importlib.reload(config)
    assert config.DATA_DIR == "/tmp/test_data"
    # 恢复
    monkeypatch.delenv("ARKNIGHTS_DATA_DIR")
    importlib.reload(config)


def test_operator_char_fields_only_9():
    """干员字段白名单应为 9 个"""
    assert len(config.OPERATOR_CHAR_FIELDS) == 9
    assert "name_zh" in config.OPERATOR_CHAR_FIELDS
    assert "hp" not in config.OPERATOR_CHAR_FIELDS


def test_category_label_map_keys():
    """分类映射应包含主线、活动等"""
    assert "主线" in config.CATEGORY_LABEL_MAP
    assert config.CATEGORY_LABEL_MAP["主线"] == "main"
```

- [ ] **Step 2: 运行测试确认失败（config.py 尚未创建）**

```bash
python -m pytest tests/test_config.py -v
```

- [ ] **Step 3: 创建 pyproject.toml + __init__.py + config.py + pipeline/__init__.py**

```toml
# pyproject.toml
[project]
name = "arknights-wiki"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.28",
    "beautifulsoup4>=4.12",
    "lxml>=5.3",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.25"]
```

```python
# arknights_wiki/__init__.py
# arknights_wiki — 明日方舟剧情 LLM Wiki
```

```python
# arknights_wiki/config.py
"""集中配置 —— 路径常量、URL、分类映射"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("ARKNIGHTS_DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
OUTPUT_DIR = os.environ.get("ARKNIGHTS_OUTPUT_DIR", os.path.join(PROJECT_ROOT, "output"))

PRTS_BASE = "https://prts.wiki"
INDEX_URL = f"{PRTS_BASE}/w/%E5%89%A7%E6%83%85%E4%B8%80%E8%A7%88"
OPERATOR_LIST_URL = f"{PRTS_BASE}/w/%E5%B9%B2%E5%91%98%E4%B8%80%E8%A7%88"

CATEGORY_LABEL_MAP = {
    "主线": "main",
    "插曲": "intermezzi",
    "干员密录": "operator_records",
    "活动": "side",
    "剧情": "special",
}

CATEGORY_LABELS = {
    "main": "主线",
    "side": "支线",
    "intermezzi": "插曲",
    "operator_records": "干员密录",
    "special": "特殊",
}

OPERATOR_CHAR_FIELDS = [
    "id", "name_zh", "race", "nation", "birth_place",
    "team", "group", "sex", "logo",
]

OPERATOR_DATA_ATTR_MAP = {
    "data-id": "id",
    "data-zh": "name_zh",
    "data-race": "race",
    "data-nation": "nation",
    "data-birth_place": "birth_place",
    "data-team": "team",
    "data-group": "group",
    "data-sex": "sex",
    "data-logo": "logo",
}
```

```python
# arknights_wiki/pipeline/__init__.py
# pipeline — 原始内容提取管线
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_config.py -v
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml arknights_wiki/ tests/ docs/plans/
git commit -m "feat: add project skeleton with config and initial tests"
```

---

### Task 2: 工具函数模块

**Files:**
- Create: `arknights_wiki/_utils.py`
- Create: `tests/test_utils.py`

- [ ] **Step 1: 写 _utils 测试**

```python
# tests/test_utils.py
import json
import os
import tempfile
from arknights_wiki._utils import (
    sanitize_filename, ensure_dir, read_json, write_json,
    compute_hash, normalize_url,
)


def test_sanitize_filename_removes_illegal_chars():
    assert sanitize_filename('test:file<name>') == 'test_file_name_'


def test_sanitize_filename_spaces_to_underscores():
    assert sanitize_filename('hello world') == 'hello_world'


def test_ensure_dir_creates_directory():
    with tempfile.TemporaryDirectory() as tmp:
        new_dir = os.path.join(tmp, "a", "b", "c")
        ensure_dir(new_dir)
        assert os.path.isdir(new_dir)


def test_read_write_json_roundtrip():
    data = {"key": "值", "nested": [1, 2, 3]}
    with tempfile.TemporaryDirectory() as tmp:
        filepath = os.path.join(tmp, "test.json")
        write_json(filepath, data)
        result = read_json(filepath)
        assert result == data


def test_write_json_creates_parent_dir():
    with tempfile.TemporaryDirectory() as tmp:
        filepath = os.path.join(tmp, "sub", "deep", "test.json")
        write_json(filepath, {"a": 1})
        assert os.path.exists(filepath)


def test_write_json_ensure_ascii_false():
    """中文应保持原样，不被转义为 \\uXXXX"""
    with tempfile.TemporaryDirectory() as tmp:
        filepath = os.path.join(tmp, "test.json")
        write_json(filepath, {"name": "阿米娅"})
        with open(filepath, 'r', encoding='utf-8') as f:
            raw = f.read()
        assert "阿米娅" in raw
        assert "\\u" not in raw


def test_compute_hash_deterministic():
    h1 = compute_hash("hello")
    h2 = compute_hash("hello")
    assert h1 == h2
    assert len(h1) == 64  # SHA256


def test_compute_hash_different_inputs():
    assert compute_hash("a") != compute_hash("b")


def test_normalize_url_already_full():
    assert normalize_url("https://prts.wiki/w/test") == "https://prts.wiki/w/test"


def test_normalize_url_protocol_relative():
    assert normalize_url("//prts.wiki/w/test") == "https://prts.wiki/w/test"


def test_normalize_url_path_only():
    assert normalize_url("/w/test") == "https://prts.wiki/w/test"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_utils.py -v
```

- [ ] **Step 3: 创建 _utils.py 使测试通过**

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_utils.py -v
```

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/_utils.py tests/test_utils.py
git commit -m "feat: add utility functions with tests"
```

---

### Task 3: 剧情索引抓取

**Files:**
- Create: `arknights_wiki/pipeline/fetch_index.py`
- Create: `tests/test_fetch_index.py`

- [ ] **Step 1: 写测试（用本地 HTML fixture）**

```python
# tests/test_fetch_index.py
import json
import os
import tempfile
from arknights_wiki.pipeline.fetch_index import (
    parse_index_html, index_to_batch_state,
)

# 最小 HTML fixture：模拟剧情一览页表格结构
SAMPLE_INDEX_HTML = """
<div class="mw-parser-output">
<table>
<tr><th>主线剧情</th><th></th></tr>
<tr><td>黑暗时代·上</td><td>主线</td><td><a href="/w/TR-1/BEG">TR-1 行动前</a></td></tr>
<tr><td>黑暗时代·上</td><td>主线</td><td><a href="/w/TR-2/BEG">TR-2 行动后</a></td></tr>
</table>
<table>
<tr><th>活动剧情</th><th></th></tr>
<tr><td>骑兵与猎人</td><td>活动</td><td><a href="/w/GT-1/BEG">GT-1 日暮寻路</a></td></tr>
</table>
</div>
"""


def test_parse_index_html_extracts_nodes():
    nodes = parse_index_html(SAMPLE_INDEX_HTML)
    assert len(nodes) == 3

    # 主线节点
    main_nodes = [n for n in nodes if n["category"] == "main"]
    assert len(main_nodes) == 2
    assert main_nodes[0]["chapter"] == "黑暗时代·上"

    # 活动节点
    side_nodes = [n for n in nodes if n["category"] == "side"]
    assert len(side_nodes) == 1
    assert side_nodes[0]["chapter"] == "骑兵与猎人"


def test_parse_index_html_node_structure():
    nodes = parse_index_html(SAMPLE_INDEX_HTML)
    node = nodes[0]
    assert "id" in node
    assert "title" in node
    assert "chapter" in node
    assert "category" in node
    assert "source_url" in node
    assert node["source_url"].startswith("https://prts.wiki")


def test_parse_index_html_empty():
    assert parse_index_html("") == []
    assert parse_index_html("<div></div>") == []


def test_index_to_batch_state():
    nodes = [
        {"id": "A", "title": "A", "chapter": "X", "category": "main", "source_url": "http://x"},
        {"id": "B", "title": "B", "chapter": "Y", "category": "side", "source_url": "http://y"},
    ]
    state = index_to_batch_state(nodes)
    assert state["total_nodes"] == 2
    assert state["fetched_nodes"] == 0
    assert state["pending_ordered"] == ["A", "B"]
    assert state["next_batch_available"] is True
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_fetch_index.py -v
```

- [ ] **Step 3: 创建 fetch_index.py 使测试通过**

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_fetch_index.py -v
```

- [ ] **Step 5: Commit**

---

### Task 4: 剧情页面抓取

**Files:**
- Create: `arknights_wiki/pipeline/fetch_stories.py`
- Create: `tests/test_fetch_stories.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_fetch_stories.py
import os
import tempfile
from arknights_wiki._utils import ensure_dir
from arknights_wiki.pipeline.fetch_stories import (
    get_cache_path, story_url_from_id,
)


def test_get_cache_path_with_chapter(monkeypatch):
    monkeypatch.setenv("ARKNIGHTS_DATA_DIR", "/tmp/fake_data")
    import importlib
    from arknights_wiki import config
    importlib.reload(config)
    path = get_cache_path("TR-1", "main", "黑暗时代·上")
    assert "stories" in path
    assert "main" in path
    assert "黑暗时代_上" in path
    assert path.endswith("TR-1.html")


def test_get_cache_path_without_chapter(monkeypatch):
    monkeypatch.setenv("ARKNIGHTS_DATA_DIR", "/tmp/fake_data")
    import importlib
    from arknights_wiki import config
    importlib.reload(config)
    path = get_cache_path("TR-1", "special")
    assert "stories" in path
    assert "special" in path
    assert path.endswith("TR-1.html")


def test_story_url_from_id_full_url():
    url = story_url_from_id("test", "https://prts.wiki/w/test/BEG")
    assert url == "https://prts.wiki/w/test/BEG"


def test_story_url_from_id_relative():
    url = story_url_from_id("test", "/w/test/BEG")
    assert url == "https://prts.wiki/w/test/BEG"


def test_story_url_from_id_no_url():
    url = story_url_from_id("test")
    assert "prts.wiki" in url
    assert "test" in url
```

- [ ] **Step 2-4: 标准 TDD 循环**

- [ ] **Step 5: Commit**

---

### Task 5: 对话解析

**Files:**
- Create: `arknights_wiki/pipeline/parse_dialogue.py`
- Create: `tests/test_parse_dialogue.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_parse_dialogue.py
from arknights_wiki.pipeline.parse_dialogue import (
    parse_datas_txt, parse_story_html, extract_datas_txt,
)


def test_parse_datas_txt_dialogue():
    raw = '[name="阿米娅"] 博士，您醒了。'
    result = parse_datas_txt(raw)
    assert len(result) == 1
    assert result[0]["type"] == "dialogue"
    assert result[0]["speaker"] == "阿米娅"
    assert "博士" in result[0]["text"]


def test_parse_datas_txt_narration():
    raw = '[name=""] 天黑了。'
    result = parse_datas_txt(raw)
    assert len(result) == 1
    assert result[0]["type"] == "narration"
    assert "speaker" not in result[0]


def test_parse_datas_txt_nickname_placeholder():
    raw = '[name="阿米娅"] {@nickname}，您好。'
    result = parse_datas_txt(raw)
    assert "博士" in result[0]["text"]
    assert "{@nickname}" not in result[0]["text"]


def test_parse_datas_txt_skips_directives():
    raw = '[name="阿米娅"] 你好。\n[bgm="battle"]'
    result = parse_datas_txt(raw)
    assert len(result) == 1  # 指令行被跳过


def test_parse_datas_txt_empty():
    assert parse_datas_txt("") == []
    assert parse_datas_txt(None) == []


def test_parse_datas_txt_mixed():
    raw = (
        '[name=""] 罗德岛的早晨开始了。\n'
        '[name="阿米娅"] 博士，早。\n'
        '[name="杜宾"] 训练场见。\n'
        '[name=""] 三人走向训练场。'
    )
    result = parse_datas_txt(raw)
    assert len(result) == 4
    assert result[0]["type"] == "narration"
    assert result[1]["type"] == "dialogue"
    assert result[1]["speaker"] == "阿米娅"


# parse_story_html 用最小 HTML fixture
MINIMAL_STORY_HTML = """<html><body>
<pre id="datas_txt">[name="阿米娅"] 博士。\n[name=""] 天黑了。</pre>
</body></html>"""


def test_extract_datas_txt():
    text = extract_datas_txt(MINIMAL_STORY_HTML)
    assert text is not None
    assert "博士" in text


def test_parse_story_html():
    story = parse_story_html(
        MINIMAL_STORY_HTML, "TEST-1", "测试", "测试章", "main",
        "https://prts.wiki/w/TEST-1"
    )
    assert story["id"] == "TEST-1"
    assert story["title"] == "测试"
    assert story["chapter"] == "测试章"
    assert story["category"] == "main"
    assert len(story["lines"]) == 2
```

- [ ] **Step 2-4: TDD 循环**

- [ ] **Step 5: Commit**

---

### Task 6: Story Markdown 生成

**Files:**
- Files: `arknights_wiki/pipeline/gen_markdown.py`
- Create: `tests/test_gen_markdown.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_gen_markdown.py
from arknights_wiki.pipeline.gen_markdown import story_to_markdown


def test_story_to_markdown_basic():
    story = {
        "id": "TEST-1",
        "title": "测试",
        "chapter": "测试章",
        "category": "main",
        "source_url": "https://prts.wiki/w/TEST-1",
        "lines": [
            {"type": "dialogue", "speaker": "阿米娅", "text": "博士。"},
            {"type": "narration", "text": "天黑了。"},
        ],
    }
    md = story_to_markdown(story)
    assert "# TEST-1 测试" in md
    assert "**阿米娅**：博士。" in md
    assert "*天黑了。*" in md
    assert "章节：测试章" in md
    assert "主线" in md
```

- [ ] **Step 2-4: TDD 循环**

- [ ] **Step 5: Commit**

---

### Task 7: 干员数据抓取

**Files:**
- Create: `arknights_wiki/pipeline/fetch_operators.py`
- Create: `tests/test_fetch_operators.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_fetch_operators.py
import json
from arknights_wiki.pipeline.fetch_operators import (
    _extract_data_attrs, parse_operator_page,
)

# 模拟干员一览页中的 data-* div
SAMPLE_OPERATOR_HTML = """
<div class="xxx" data-id="R001" data-zh="阿米娅" data-race="卡特斯/奇美拉"
data-nation="雷姆必拓" data-birth_place="雷姆必拓" data-team=""
data-group="罗德岛" data-sex="女" data-logo="罗德岛"
data-hp="1480" data-atk="612" data-def="120" data-name_en="Amiya"
data-name_ja="アーミヤ"></div>
<div class="xxx" data-id="R002" data-zh="杜宾" data-race="佩洛"
data-nation="玻利瓦尔" data-birth_place="玻利瓦尔" data-team="行动组A4"
data-group="罗德岛" data-sex="女" data-logo="罗德岛"
data-hp="1200" data-atk="450"></div>
"""


def test_extract_data_attrs_only_char_fields():
    ops = _extract_data_attrs(SAMPLE_OPERATOR_HTML)
    assert len(ops) == 2

    # 阿米娅
    assert ops[0]["id"] == "R001"
    assert ops[0]["name_zh"] == "阿米娅"
    assert ops[0]["race"] == "卡特斯/奇美拉"
    assert ops[0]["nation"] == "雷姆必拓"
    assert ops[0]["logo"] == "罗德岛"

    # 不应包含游戏数值
    assert "hp" not in ops[0]
    assert "atk" not in ops[0]
    assert "def" not in ops[0]
    assert "name_en" not in ops[0]
    assert "name_ja" not in ops[0]


def test_extract_data_attrs_empty():
    assert _extract_data_attrs("") == []
    assert _extract_data_attrs("<div>no data-id</div>") == []


# 模拟干员个人页档案 HTML
ARCHIVE_HTML = """<html><body>
<h2><span class="mw-headline" id="干员信息">干员信息</span></h2>
<p>一些内容</p>
<h2><span class="mw-headline" id="干员档案">干员档案</span></h2>
<h3><span class="mw-headline" id="基础档案">基础档案</span></h3>
<p>【代号】测试干员</p>
<p>【性别】女</p>
<p>【出身地】罗德岛</p>
<h3><span class="mw-headline" id="客观履历">客观履历</span></h3>
<p>一位测试干员，背景不详。</p>
<h3><span class="mw-headline" id="档案资料一">档案资料一</span></h3>
<p>这是档案内容。</p>
<h2><span class="mw-headline" id="语音记录">语音记录</span></h2>
<p>语音内容</p>
</body></html>"""


def test_parse_operator_page_extracts_archives():
    archives = parse_operator_page(ARCHIVE_HTML)
    assert "基础档案" in archives
    assert "测试干员" in archives["基础档案"]
    assert "客观履历" in archives
    assert "背景不详" in archives["客观履历"]
    assert "档案资料一" in archives
    assert "这是档案内容" in archives["档案资料一"]


def test_parse_operator_page_stops_at_next_h2():
    archives = parse_operator_page(ARCHIVE_HTML)
    # 语音记录 不在干员档案 h2 内
    assert "语音记录" not in archives


def test_parse_operator_page_empty():
    assert parse_operator_page("") == {}
    assert parse_operator_page("<div></div>") == {}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_fetch_operators.py -v
```

- [ ] **Step 3: 创建 fetch_operators.py 使测试通过**

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_fetch_operators.py -v
```

- [ ] **Step 5: Commit**

---

### Task 8: 干员档案 Markdown

**Files:**
- Create: `arknights_wiki/pipeline/gen_operators_md.py`
- Create: `tests/test_gen_operators_md.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_gen_operators_md.py
from arknights_wiki.pipeline.gen_operators_md import operator_to_markdown


def test_operator_to_markdown_basic():
    op = {
        "name_zh": "阿米娅",
        "race": "卡特斯/奇美拉",
        "nation": "雷姆必拓",
        "birth_place": "雷姆必拓",
        "sex": "女",
        "team": "",
        "group": "罗德岛",
        "logo": "罗德岛",
        "archives": {
            "基础档案": "【代号】阿米娅\n【性别】女",
            "客观履历": "罗德岛的公开领袖。",
            "档案资料一": "档案内容一。",
        },
    }
    md = operator_to_markdown(op)
    assert "# 阿米娅" in md
    assert "种族：卡特斯/奇美拉" in md
    assert "阵营：雷姆必拓" in md
    assert "组织：罗德岛" in md
    assert "## 基础档案" in md
    assert "【代号】阿米娅" in md
    assert "## 客观履历" in md
    assert "罗德岛的公开领袖。" in md
    assert "## 档案资料一" in md


def test_operator_to_markdown_no_archives():
    op = {
        "name_zh": "测试",
        "race": "未知",
        "nation": "",
        "birth_place": "",
        "sex": "",
        "team": "",
        "group": "",
        "logo": "",
        "archives": {},
    }
    md = operator_to_markdown(op)
    assert "# 测试" in md
    assert "无档案数据" in md


def test_operator_to_markdown_archive_order():
    """档案应按 基础档案→客观履历→临床诊断→档案资料一~四→晋升记录 的顺序输出"""
    op = {
        "name_zh": "测试",
        "race": "", "nation": "", "birth_place": "", "sex": "",
        "team": "", "group": "", "logo": "",
        "archives": {
            "档案资料二": "second",
            "基础档案": "first",
            "档案资料一": "third",
        },
    }
    md = operator_to_markdown(op)
    pos_first = md.find("## 基础档案")
    pos_third = md.find("## 档案资料一")
    pos_second = md.find("## 档案资料二")
    assert pos_first < pos_third < pos_second
```

- [ ] **Step 2-4: TDD 循环**

- [ ] **Step 5: Commit**

---

### Task 9: 编排器

**Files:**
- Create: `arknights_wiki/pipeline/orchestrate.py`
- Create: `tests/test_orchestrate.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_orchestrate.py
import json
import os
import tempfile
from arknights_wiki.pipeline.orchestrate import _select_batch_nodes


def test_select_batch_nodes_no_filter():
    state = {"pending_ordered": ["A", "B", "C", "D", "E"]}
    result = _select_batch_nodes(state, 3)
    assert result == ["A", "B", "C"]


def test_select_batch_nodes_count_limit():
    state = {"pending_ordered": ["A", "B"]}
    result = _select_batch_nodes(state, 10)
    assert len(result) == 2


def test_select_batch_nodes_empty():
    state = {"pending_ordered": []}
    result = _select_batch_nodes(state, 5)
    assert result == []
```

- [ ] **Step 2-4: TDD 循环**

- [ ] **Step 5: Commit**

---

### Task 10: 集成测试 + 全模块导入验证

- [ ] **Step 1: 写集成测试**

```python
# tests/test_integration.py
def test_all_modules_importable():
    """所有模块应可成功导入"""
    from arknights_wiki import config
    from arknights_wiki import _utils
    from arknights_wiki.pipeline import fetch_index
    from arknights_wiki.pipeline import fetch_stories
    from arknights_wiki.pipeline import parse_dialogue
    from arknights_wiki.pipeline import gen_markdown
    from arknights_wiki.pipeline import fetch_operators
    from arknights_wiki.pipeline import gen_operators_md
    from arknights_wiki.pipeline import orchestrate
```

- [ ] **Step 2: 运行全部测试**

```bash
python -m pytest tests/ -v
```

- [ ] **Step 3: Commit 最终版本**

