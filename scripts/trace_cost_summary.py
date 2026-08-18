"""W1 Observability: 从 Langfuse ClickHouse 聚合 trace 成本 → output/observability/cost_summary.md

用法：
  python scripts/trace_cost_summary.py [--hours 24]

前置条件：
  - 本地 Langfuse Docker 部署运行中（docker/langfuse/docker-compose.yml）
  - docker CLI 可用（ClickHouse 容器名 langfuse-clickhouse-1）

说明：Langfuse v4 的 v2 observations 列表 API 为 lightweight view（不含 usage/cost），
成本从 ClickHouse `events_full` 表聚合（provided_cost_details），与 UI 一致。
输出供 devlog 1.4 节监控表引用。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "output" / "observability"

CLICKHOUSE_CONTAINER = "langfuse-clickhouse-1"


def _clickhouse(query: str, container: str = CLICKHOUSE_CONTAINER) -> str:
    """执行 ClickHouse 查询（docker exec）"""
    result = subprocess.run(
        ["docker", "exec", container, "clickhouse-client", "-q", query],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ClickHouse 查询失败: {result.stderr.strip()[:300]}")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Langfuse trace 成本摘要（ClickHouse）")
    parser.add_argument("--hours", type=int, default=24, help="回溯小时数")
    parser.add_argument("--out", default=str(OUT_DIR / "cost_summary.md"))
    parser.add_argument("--container", default=CLICKHOUSE_CONTAINER)
    args = parser.parse_args()

    container = args.container

    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    # 按 trace 聚合 cost（events_full 中 GENERATION 的 provided_cost_details.total）
    query = f"""
    SELECT
        trace_name AS name,
        count() AS n_events,
        countDistinct(trace_id) AS n_traces,
        sum(toFloat64(provided_cost_details['total'])) AS total_cost_rmb
    FROM events_full
    WHERE start_time >= toDateTime('{since_str}')
      AND type = 'GENERATION'
      AND has(provided_cost_details, 'total')
    GROUP BY trace_name
    ORDER BY total_cost_rmb DESC
    FORMAT JSONEachRow
    """
    try:
        out = _clickhouse(query, container)
    except RuntimeError as e:
        print(f"错误：{e}")
        print("提示：确认 Langfuse Docker 栈运行中（docker compose -f docker/langfuse/docker-compose.yml ps）")
        return 1

    rows = []
    for line in out.strip().splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))

    total_cost = sum(r["total_cost_rmb"] for r in rows)
    n_traces = sum(r["n_traces"] for r in rows)

    lines = [
        "# Trace 成本摘要（Langfuse ClickHouse）",
        "",
        f"- 生成时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- 回溯范围：最近 {args.hours} 小时（UTC）",
        f"- 涉及 trace 数：{n_traces}",
        f"- 总成本（RMB，provided_cost_details 聚合）：¥{total_cost:.6f}",
        "",
        "## 按 trace 名称分布",
        "",
        "| 名称 | trace 数 | 事件数 | 成本(RMB) |",
        "|------|---------|--------|-----------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['name'] or '(unnamed)'} | {r['n_traces']} | {r['n_events']} | ¥{r['total_cost_rmb']:.6f} |"
        )
    lines.append("")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"已输出：{out_path}")
    print(f"  traces={n_traces} total=¥{total_cost:.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
