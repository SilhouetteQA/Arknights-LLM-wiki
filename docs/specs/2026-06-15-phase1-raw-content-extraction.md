# Phase 1: 原始内容提取 — 设计规格

**日期:** 2026-06-15
**状态:** 实施中
**关联:** mrfz `scripts/scraper/` + 新增干员数据

---

## 一、背景

从 PRTS Wiki 抓取原始数据是知识图谱构建的基础。mrfz 项目已有完整的剧情抓取管线（`scripts/scraper/`），本次重构将其迁移到新的 `arknights_wiki/` 包结构，并新增干员档案抓取能力。

---

## 二、目标

1. 将 mrfz `scripts/scraper/` 的剧情抓取管线迁移到 `arknights_wiki/pipeline/`
2. 新增干员人物信息提取（从干员一览页 + 干员个人页档案文本）
3. 工具函数拆分为独立模块，数据路径改为可配置
4. 产出 `pyproject.toml` 管理依赖

---

## 三、不在此阶段的范围

- `gen_visualization.py` — 依赖 IndexStore（SQLite），留到检索阶段迁移
- 知识图谱提取（events/relations/concepts）— Phase 2
- LLM 调用 — Phase 2+
- Web 服务 — Phase 4
- 游戏数值（HP/ATK/DEF 等战斗面板）— 明确排除

---

## 四、目标文件结构

```
arknights_wiki/
├── __init__.py
├── config.py                 # 集中配置
├── _utils.py                 # 纯函数工具
└── pipeline/
    ├── __init__.py
    ├── fetch_index.py        # 剧情索引页抓取（迁入）
    ├── fetch_operators.py    # ★ 新增：干员人物信息提取
    ├── fetch_stories.py      # 单页HTML抓取+缓存（迁入）
    ├── parse_dialogue.py     # datas_txt解析（迁入）
    ├── gen_markdown.py       # Markdown生成（迁入）
    ├── gen_operators_md.py   # ★ 新增：干员档案Markdown生成
    └── orchestrate.py        # 批量编排器（迁入+适配）
```

### 各文件职责

| 文件 | 职责 | 来源 | 变更程度 |
|------|------|------|----------|
| `config.py` | 路径常量、URL常量、分类映射、干员字段白名单 | 新建 | — |
| `_utils.py` | json读写、hash、文件名清理、URL规范化、目录创建 | 从 mrfz `utils.py` 拆分 | 只迁通用工具，LLM工具留后 |
| `fetch_index.py` | 抓取"剧情一览"→ `index.json` | 迁入 | 改 import 路径 |
| `fetch_operators.py` | 从干员一览页提取 420 干员人物信息；可选抓取个人页档案文本 | 新建 | — |
| `fetch_stories.py` | 抓取单页 HTML + 本地缓存（同步/异步） | 迁入 | 改 import 路径 |
| `parse_dialogue.py` | 解析 `datas_txt` 格式 → story JSON | 迁入 | 改 import 路径 |
| `gen_markdown.py` | story JSON → 人类可读 Markdown | 迁入 | 改 import 路径 |
| `gen_operators_md.py` | operators.json → 按干员分类的可读 Markdown | 新建 | — |
| `orchestrate.py` | 编排批量抓取流程（`init_pipeline`, `fetch_next_batch`） | 迁入自 `pipeline.py` | 改名避免与包名冲突 |

---

## 五、干员数据设计

### 5.1 数据来源

**来源一：干员一览页** (`https://prts.wiki/w/干员一览`)

页面 HTML 中每个干员以 `<div>` 标签嵌入，包含丰富的 `data-*` 属性。当前共约 420 个干员。纯 HTML 解析，无需 JS 渲染。

**来源二：干员个人页** (`https://prts.wiki/w/{干员名}`)

个人页的「干员档案」节包含结构化档案文本（基础档案、客观履历、临床诊断、档案资料一~四）。此部分为**可选深度抓取**，首批可按需抓取。

### 5.2 提取字段（仅人物/剧情相关）

从干员一览页 `data-*` 属性中，**仅提取以下人物信息字段**：

| 字段 | data属性 | 说明 |
|------|----------|------|
| `id` | `data-id` | 干员编号（唯一标识） |
| `name_zh` | `data-zh` | 中文名 |
| `race` | `data-race` | 种族 |
| `nation` | `data-nation` | 所属国家/阵营 |
| `birth_place` | `data-birth_place` | 出身地 |
| `team` | `data-team` | 所属小队 |
| `group` | `data-group` | 所属组织/团体 |
| `sex` | `data-sex` | 性别 |
| `logo` | `data-logo` | 阵营标识（如 罗德岛、龙门近卫局） |

### 5.3 明确排除

`data-*` 中除上述 9 个字段外的所有属性均不提取，包括但不限于：游戏数值（hp/atk/def）、职业定位（profession/subprofession/rarity/position/tag）、日英文名、获取方式等。

### 5.4 个人页档案文本（全量抓取）

每个干员个人页（`https://prts.wiki/w/{干员名}`）「干员档案」节的全部文本块均抓取：

| 档案项 | 说明 |
|--------|------|
| 基础档案 | 代号/性别/出身地/种族/身高/感染情况 |
| 客观履历 | 人物背景叙述 |
| 临床诊断分析 | 矿石病感染情况描述 |
| 档案资料一~四 | 深度角色故事/过去经历 |
| 晋升记录 | 晋升后解锁的额外背景文本 |

**抓取策略**：先抓取一览页获得 420 干员列表，再对每个干员抓取个人页档案文本（异步并发，控制 QPS）。

### 5.5 输出格式

```json
{
  "fetched_at": "2026-06-15T...",
  "source_list_url": "https://prts.wiki/w/干员一览",
  "total": 420,
  "operators": [
    {
      "id": "R001",
      "name_zh": "阿米娅",
      "race": "卡特斯/奇美拉",
      "nation": "雷姆必拓",
      "birth_place": "雷姆必拓",
      "team": "",
      "group": "罗德岛",
      "sex": "女",
      "logo": "罗德岛",
      "archives": {
        "基础档案": "【代号】阿米娅\n【性别】女\n【战斗经验】三年\n【出身地】雷姆必拓\n【生日】12月23日\n【种族】卡特斯/奇美拉\n【身高】142cm\n【矿石病感染情况】体表有源石结晶分布，参照医学检测报告，确认为感染者。",
        "客观履历": "罗德岛的公开领袖，在内部拥有最高执行权。虽然，从外表上看起来仅仅是个不成熟的少女，实际上，她却是深受大家信任的合格的领袖。现在，阿米娅正带领着罗德岛，为了感染者的未来，为了让这片大地挣脱矿石病的阴霾而不懈努力。",
        "临床诊断分析": "造影检测结果显示，该干员体内脏器轮廓模糊，可见异常阴影，循环系统内源石颗粒检测异常，有矿石病感染迹象，现阶段可确认为矿石病感染者。\n\n【体细胞与源石融合率】19%\n【血液源石结晶密度】0.27u/L",
        "档案资料一": "...",
        "档案资料二": "...",
        "档案资料三": "...",
        "档案资料四": "...",
        "晋升记录": "..."
      }
    }
  ]
}
```

> `archives` 中的 key 为档案节标题（中文），value 为该节的纯文本内容。不同干员档案结构可能略有差异（如升变干员有升变档案），解析时以实际 HTML 中的 `h3`/`h2` 标题为准。

### 5.6 干员档案 Markdown 输出

每个干员生成一个独立 Markdown 文件，按阵营分类存放：

```
output/markdown/operators/{logo}/{name_zh}.md
```

文件格式：

```markdown
# {name_zh}

> 种族：{race} | 阵营：{nation} | 出身地：{birth_place} | 性别：{sex}
> 小队：{team} | 组织：{group}

---

## 基础档案

（基础档案内容）

## 客观履历

（客观履历内容）

## 临床诊断分析

（临床诊断分析内容）

## 档案资料一

...

## 晋升记录

...
```

`gen_operators_md.py` 仅做格式转换，数据来源是 `data/operators.json`。

---

## 六、配置设计 (`config.py`)

```python
# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据目录（可通过环境变量覆盖）
DATA_DIR = os.environ.get("ARKNIGHTS_DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
OUTPUT_DIR = os.environ.get("ARKNIGHTS_OUTPUT_DIR", os.path.join(PROJECT_ROOT, "output"))

# PRTS Wiki URL
PRTS_BASE = "https://prts.wiki"
INDEX_URL = f"{PRTS_BASE}/w/剧情一览"
OPERATOR_URL = f"{PRTS_BASE}/w/干员一览"

# 剧情分类映射
CATEGORY_LABEL_MAP = {
    "主线": "main",
    "插曲": "intermezzi",
    "干员密录": "operator_records",
    "活动": "side",
    "剧情": "special",
}

# 分类中文标签
CATEGORY_LABELS = {
    "main": "主线",
    "side": "支线",
    "intermezzi": "插曲",
    "operator_records": "干员密录",
    "special": "特殊",
}

# 干员人物字段白名单（从 data-* 属性中提取）
OPERATOR_CHAR_FIELDS = [
    "id", "name_zh", "race", "nation", "birth_place",
    "team", "group", "sex", "logo",
]
```

---

## 七、依赖 (`pyproject.toml`)

```toml
[project]
name = "arknights-wiki"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.28",
    "beautifulsoup4>=4.12",
    "lxml>=5.3",
    "jinja2>=3.1",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.25"]
```

此阶段不需 `openai`, `numpy`, `faiss`, `sentence-transformers` 等（Phase 2+ 再加）。

---

## 八、迁入文件变更摘要

| 文件 | 变更 |
|------|------|
| `fetch_index.py` | `from scripts.utils import ...` → `from arknights_wiki._utils import ...`；`from arknights_wiki.config import ...` |
| `fetch_stories.py` | 同上，import 路径替换 |
| `parse_dialogue.py` | 同上 |
| `gen_markdown.py` | 同上 + `CATEGORY_LABELS` 从 config 导入 |
| `pipeline.py → orchestrate.py` | 改名，所有 import 路径替换，`generate_all_markdown()` 调用保留 |

---

## 九、风险与取舍

| 风险 | 应对 |
|------|------|
| PRTS Wiki 改版导致解析失败 | 每个解析函数独立，影响面可控；URL 集中在 config 管理 |
| 420 个干员页全量抓取耗时长 | 异步并发 + 本地缓存，控制并发数避免被限流 |
| gen_visualization 依赖 IndexStore 未就绪 | 跳过，Phase 4 后再迁入 |
| 中文字符编码乱码 | utils 层统一 `encoding='utf-8'`，Windows 终端设 `PYTHONIOENCODING=utf-8` |
