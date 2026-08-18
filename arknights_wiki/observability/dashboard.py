"""W1 Observability Dashboard — 独立可视化服务（区别于 agent server 8000）

- 端口：8001（`python -m arknights_wiki.observability.dashboard` 或 uvicorn）
- 数据源：Langfuse 本地 Docker 的 ClickHouse（events_full 事件表，直连 127.0.0.1:8123）
- API：
    GET /                       → dashboard.html（ECharts 可视化页面）
    GET /api/overview?hours=24  → 汇总指标 + 时间序列 + 节点类型分布
    GET /api/traces?hours=24    → trace 列表（含成本/延迟/token）
    GET /api/trace/{trace_id}   → 单个 trace 树（层级结构）
- 前置：Langfuse Docker 栈运行中（docker/langfuse/docker-compose.yml）
- 环境变量覆盖：ARKNIGHTS_CH_HOST/PORT/USER/PASSWORD
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import clickhouse_connect
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_langfuse_env() -> dict:
    """读取 docker/langfuse/.env（ClickHouse 凭据）"""
    env_path = Path(__file__).resolve().parents[2] / "docker" / "langfuse" / ".env"
    env = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


_env = _load_langfuse_env()
CH_HOST = os.environ.get("ARKNIGHTS_CH_HOST", "127.0.0.1")
CH_PORT = int(os.environ.get("ARKNIGHTS_CH_PORT", "8123"))
CH_USER = os.environ.get("ARKNIGHTS_CH_USER", _env.get("CLICKHOUSE_USER", "clickhouse"))
CH_PASS = os.environ.get("ARKNIGHTS_CH_PASSWORD", _env.get("CLICKHOUSE_PASSWORD", "clickhouse"))

_client = None


def get_client():
    global _client
    if _client is None:
        _client = clickhouse_connect.get_client(
            host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASS
        )
    return _client


app = FastAPI(title="Arknights Wiki Observability", version="0.1.0")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _since(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


def _rows(client, query: str) -> list[tuple]:
    return client.query(query).result_rows


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")


@app.get("/api/overview")
async def overview(hours: int = Query(24, ge=1, le=168)):
    """汇总指标 + 按小时时间序列 + 节点类型分布"""
    client = get_client()
    since = _since(hours)

    # 1) 根节点（chat_request 等 is_app_root）汇总：trace 数 / 平均延迟 / P95 延迟
    roots = _rows(client, f"""
        SELECT count(),
               ifNull(avgOrNull(toInt64(dateDiff('millisecond', start_time, end_time))), 0),
               ifNull(quantile(0.95)(toInt64(dateDiff('millisecond', start_time, end_time))), 0)
        FROM events_full
        WHERE start_time >= toDateTime('{since}') AND is_app_root = 1
    """)[0]
    n_traces = int(roots[0] or 0)

    # 1b) 总成本（GENERATION 的 provided_cost_details 聚合）
    cost_total = _rows(client, f"""
        SELECT sum(toFloat64(provided_cost_details['total']))
        FROM events_full
        WHERE start_time >= toDateTime('{since}') AND type = 'GENERATION'
    """)[0][0]

    # 2) LLM 调用数 / 工具调用数
    gen = _rows(client, f"""
        SELECT countIf(type='GENERATION'), countIf(type='TOOL')
        FROM events_full WHERE start_time >= toDateTime('{since}')
    """)[0]
    n_llm, n_tools = int(gen[0] or 0), int(gen[1] or 0)

    # 3) 根节点按小时：请求数 + 平均延迟
    ts_traces = _rows(client, f"""
        SELECT toStartOfHour(start_time) AS h, count() AS n,
               ifNull(avgOrNull(toInt64(dateDiff('millisecond', start_time, end_time))), 0)
        FROM events_full
        WHERE start_time >= toDateTime('{since}') AND is_app_root = 1
        GROUP BY h ORDER BY h
    """)

    # 4) GENERATION 按小时：成本 + token
    ts_cost = _rows(client, f"""
        SELECT toStartOfHour(start_time) AS h,
               sum(toFloat64(provided_cost_details['total'])) AS cost,
               sum(toUInt64(provided_usage_details['input'])) AS tin,
               sum(toUInt64(provided_usage_details['output'])) AS tout
        FROM events_full
        WHERE start_time >= toDateTime('{since}') AND type = 'GENERATION'
        GROUP BY h ORDER BY h
    """)

    # 5) 节点类型分布（数量 + 成本）
    by_type = _rows(client, f"""
        SELECT name, type, count() AS n, sum(toFloat64(provided_cost_details['total'])) AS cost
        FROM events_full
        WHERE start_time >= toDateTime('{since}')
        GROUP BY name, type ORDER BY n DESC
    """)

    # 6) 根节点延迟直方图（桶 0-0.5s ... 30s+）
    hist = _rows(client, f"""
        SELECT
            multiIf(
                d < 1000, 0,
                d < 5000, 1,
                d < 10000, 2,
                d < 20000, 3,
                d < 60000, 4,
                5) AS bucket,
            count()
        FROM (SELECT toInt64(dateDiff('millisecond', start_time, end_time)) AS d
              FROM events_full
              WHERE start_time >= toDateTime('{since}') AND is_app_root = 1)
        GROUP BY bucket ORDER BY bucket
    """)
    buckets = ["<1s", "1-5s", "5-10s", "10-20s", "20-60s", ">60s"]
    hist_data = [0] * 6
    for b, c in hist:
        if 0 <= int(b) <= 5:
            hist_data[int(b)] = int(c)

    return {
        "totals": {
            "traces": n_traces,
            "llm_calls": n_llm,
            "tool_calls": n_tools,
            "cost": round(float(cost_total or 0), 6),
            "latency_avg_ms": round(float(roots[1] or 0), 1),
            "latency_p95_ms": round(float(roots[2] or 0), 1),
        },
        "timeseries": [
            {
                "hour": h.strftime("%m-%d %H:00"),
                "traces": n,
                "latency_avg_ms": round(float(avg_ms or 0), 1),
            }
            for h, n, avg_ms in ts_traces
        ],
        "cost_series": [
            {
                "hour": h.strftime("%m-%d %H:00"),
                "cost": round(float(cost or 0), 6),
                "tokens_in": int(tin or 0),
                "tokens_out": int(tout or 0),
            }
            for h, cost, tin, tout in ts_cost
        ],
        "by_type": [
            {"name": name, "type": type_, "count": int(n), "cost": round(float(cost or 0), 6)}
            for name, type_, n, cost in by_type
        ],
        "latency_hist": {"buckets": buckets, "counts": hist_data},
    }


@app.get("/api/traces")
async def traces(hours: int = Query(24, ge=1, le=168), limit: int = Query(50, ge=1, le=200)):
    """trace 列表（按开始时间倒序）"""
    client = get_client()
    since = _since(hours)
    rows = _rows(client, f"""
        SELECT trace_id, trace_name,
               min(start_time) AS st, max(end_time) AS et,
               count() AS n_events,
               sum(toFloat64(provided_cost_details['total'])) AS cost,
               sum(toUInt64(provided_usage_details['input'])) AS tin,
               sum(toUInt64(provided_usage_details['output'])) AS tout
        FROM events_full
        WHERE start_time >= toDateTime('{since}')
        GROUP BY trace_id, trace_name
        ORDER BY st DESC
        LIMIT {limit}
    """)
    out = []
    for tid, tname, st, et, n_ev, cost, tin, tout in rows:
        lat = None
        if st and et:
            lat = round((et - st).total_seconds() * 1000, 1)
        out.append({
            "trace_id": tid,
            "name": tname or "(unnamed)",
            "start_time": st.strftime("%Y-%m-%d %H:%M:%S") if st else "",
            "latency_ms": lat,
            "events": int(n_ev),
            "cost": round(float(cost or 0), 6),
            "tokens_in": int(tin or 0),
            "tokens_out": int(tout or 0),
        })
    return {"traces": out}


@app.get("/api/trace/{trace_id}")
async def trace_detail(trace_id: str):
    """单个 trace 树（events_full 的 span_id/parent_span_id 建树）"""
    client = get_client()
    rows = _rows(client, f"""
        SELECT span_id, parent_span_id, name, type, start_time, end_time,
               provided_model_name, provided_usage_details, provided_cost_details,
               status_message, trace_name,
               mapFromArrays(metadata_names, metadata_values)['tool'] AS tool,
               mapFromArrays(metadata_names, metadata_values) AS meta,
               input AS input_text
        FROM events_full
        WHERE trace_id = '{trace_id}'
    """)
    if not rows:
        raise HTTPException(status_code=404, detail=f"trace {trace_id} 不存在")

    nodes: dict[str, dict] = {}
    children: dict[str, list] = {}
    root_ids: list[str] = []
    trace_name = rows[0][10] or "(unnamed)"

    for span_id, parent_id, name, type_, st, et, model, usage, cost, status, _, tool, meta, input_text in rows:
        lat = None
        if st and et:
            lat = round((et - st).total_seconds() * 1000, 1)
        usage = dict(usage) if usage else {}
        cost = dict(cost) if cost else {}
        # root 节点的 input 可能是 {"question": "..."} JSON，解析出问题文本
        question_text = ""
        if input_text:
            if isinstance(input_text, str) and input_text.lstrip().startswith("{"):
                try:
                    question_text = json.loads(input_text).get("question", "") or ""
                except Exception:  # noqa: BLE001
                    question_text = input_text
            else:
                question_text = input_text
        nodes[span_id] = {
            "span_id": span_id,
            "name": name,
            "type": type_,
            "start_time": st.strftime("%H:%M:%S") if st else "",
            "latency_ms": lat,
            "model": model or None,
            "tool": tool or None,  # tool_call 节点的具体工具名（metadata.tool）
            "metadata": dict(meta) if meta else {},  # 路由信息等（complexity/question_type/entities）
            "input": question_text[:500],  # 根节点的问题文本
            "tokens_in": int(usage.get("input", 0) or 0),
            "tokens_out": int(usage.get("output", 0) or 0),
            "cost": round(float(cost.get("total", 0) or 0), 6),
            "status": status or None,
            "children": [],
        }
        if parent_id and parent_id in nodes or parent_id in {r[0] for r in rows}:
            children.setdefault(parent_id, []).append(span_id)
        else:
            root_ids.append(span_id)

    # 组装树
    for parent_id, kids in children.items():
        if parent_id in nodes:
            nodes[parent_id]["children"] = [nodes[k] for k in kids]

    roots = [nodes[r] for r in root_ids if r in nodes]
    if not roots and rows:
        # 兜底：拿无 parent 或第一个节点为根
        roots = [next(iter(nodes.values()))]

    return {"trace_id": trace_id, "name": trace_name, "roots": roots}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
