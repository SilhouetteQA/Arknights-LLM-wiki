# 统计系统 — 开发过程追踪

**日期:** 2026-06-16
**状态:** 已完成
**关联:** M0 store/, 后续 M1-M9 模块

---

## 一、背景

M0 store/ 完成后，数据持续增长，后续 M1-M9 涉及大量 LLM 调用。需要一套轻量统计系统追踪：内容规模变化、LLM 成本、操作耗时。核心痛点是批量 LLM 调用时不知道黑箱进度。

## 二、目标

1. 每次操作（seed / pipeline / LLM 生成）自动记录快照到 `output/stats.jsonl`
2. CLI 命令查看最新快照、历史趋势、两次对比
3. 批量 LLM 调用时终端实时显示进度，每 10 分钟自动输出中间快照
4. 原始数据总量一次性统计后缓存

## 三、不在此阶段

- 图形化 dashboard / 趋势图
- Web 服务集成
- 成本账单导出

---

## 四、架构

```
arknights_wiki/
├── stats/
│   ├── __init__.py
│   ├── collector.py       # StatsCollector — 收集 + 写入 JSONL
│   └── reporter.py        # StatsReporter — 读取 + CLI 渲染

output/
└── stats.jsonl            # 每行一个 JSON 快照
```

两个类，一个数据文件。Collector 负责写，Reporter 负责读。

## 五、JSONL 快照结构

每行一个 JSON 对象，字段如下：

```json
{
  "timestamp": "2026-06-16T15:30:00",
  "operation": "seed_m0",
  "duration_ms": 1847,
  "content": {
    "entities": {"character": 381, "faction": 44, "region": 34},
    "entity_aliases": 40,
    "source_index": {"exact": 3615, "alias": 0, "concept_keyword": 0},
    "wiki_pages": {
      "character": {"draft": 0, "published": 0},
      "faction":   {"draft": 0, "published": 0},
      "region":    {"draft": 0, "published": 0},
      "concept":   {"draft": 0, "published": 0},
      "event":     {"draft": 0, "published": 0},
      "storyarc":  {"draft": 0, "published": 0},
      "chapter":   {"draft": 0, "published": 0},
      "timeline":  {"draft": 0, "published": 0},
      "glossary":  {"draft": 0, "published": 0}
    },
    "db_size_mb": 2.3,
    "raw_data": {
      "stories_count": 1663,
      "operators_count": 420,
      "total_chars": 1134547
    }
  },
  "cost": {
    "models": {
      "deepseek-v4-flash":      {"calls": 0, "tokens_in": 0, "tokens_out": 0},
      "deepseek-v4-flash-think":{"calls": 0, "tokens_in": 0, "tokens_out": 0}
    },
    "total_cost_rmb": 0
  },
  "timing": {
    "module_steps": {},
    "llm_calls_count": 0,
    "llm_calls_total_ms": 0
  }
}
```

**字段说明：**

| 字段 | 说明 |
|------|------|
| `content.entities` | 各 type 实体数，按 DB 实际 type 动态列出 |
| `content.entity_aliases` | 别名映射总数 |
| `content.source_index` | 按 match_type 分组计数 |
| `content.wiki_pages` | 按 page_type × status 二维分组，覆盖 9 种 Wiki 页面类型 |
| `content.db_size_mb` | SQLite 文件大小 |
| `content.raw_data` | 原始数据总量，首次快照统计后缓存 |
| `content.raw_data.total_chars` | 全部原始文本（故事 + 档案）总字符数 |
| `cost.models` | 按模型拆分，后续新增模型只需加 key |
| `timing.module_steps` | 按模块步骤键值对，如 `{"seed_entities_ms": 200, ...}` |
| `timing.llm_calls_count` | LLM 调用总次数 |
| `timing.llm_calls_total_ms` | LLM 调用总耗时 |

## 六、StatsCollector API

```python
class StatsCollector:
    def __init__(self, db_path: str,
                 jsonl_path: str = "output/stats.jsonl",
                 auto_snapshot_interval: int = 600)

    # 生命周期
    def start(self, operation: str) -> None
        # 启动后台定时快照线程（每 auto_snapshot_interval 秒）

    # 记录
    def record_llm_call(self, model: str, tokens_in: int,
                        tokens_out: int, duration_ms: int) -> None
        # 实时 stderr 进度 + 内部累计

    def record_step(self, step_name: str, duration_ms: int) -> None

    # 完成
    def finish(self) -> dict
        # 停后台线程，自动采集 content 快照 + 汇总 cost/timing，写 JSONL，返回 dict
```

**content 自动采集逻辑：**
- entities → `SELECT type, COUNT(*) FROM entities GROUP BY type`（动态，不硬编码 type 列表）
- entity_aliases → `SELECT COUNT(*) FROM entity_aliases`
- source_index → 按 match_type 分组计数
- wiki_pages → 按 page_type + status 二维分组，覆盖全部 9 种类型
- db_size → `os.path.getsize(db_path)`
- raw_data → 首次采集时遍历 stories/ + operators.json 计算总字符数，写入模块级缓存，后续快照直接复用

**进度可见性：**
- 每次 `record_llm_call` 输出 `[stats] #N model=deepseek-v4-flash 1.2s | 53/240` 到 stderr
- 后台线程每 10 分钟自动采集中间快照追加到 JSONL

## 七、StatsReporter + CLI

```bash
# 查看最新快照
python -m arknights_wiki.stats

# 查看最近 N 次
python -m arknights_wiki.stats --last 5

# 对比最近两次快照
python -m arknights_wiki.stats --diff
```

`--last N` 输出格式：表格式，每行一次快照的时间戳、操作名、entity 总数、source_index 总数、耗时、成本。

`--diff` 输出格式：最近两次快照的逐字段差值，新增/减少量。

## 八、集成点

| 位置 | 调用方式 |
|------|----------|
| `seed.py:run_seed()` | `collector.start("seed_m0")` → 各 step `record_step` → `collector.finish()` |
| M1+ LLM 管线 | `collector.start("gen_xxx")` → 循环中 `record_llm_call` → `collector.finish()` |

## 九、依赖

仅 Python 标准库（sqlite3 / json / pathlib / threading / time）。零外部依赖。

## 十、风险

| 风险 | 应对 |
|------|------|
| JSONL 文件无限增长 | 每行 ~300B，一万次快照仅 ~3MB，无需分片 |
| 后台线程写入冲突 | JSONL 追加写入，行级原子，无锁冲突 |
| raw_data 首次采集慢 | 仅首次遍历，后续缓存，启动可感知 |
