"""W0 T5: 评测运行器（双路径）与 LLM-as-judge 六指标评分

用法：
  python -m arknights_wiki.eval.runner --dry-run            # 预估成本（无外部调用）
  python -m arknights_wiki.eval.runner --mode both --limit 5
  python -m arknights_wiki.eval.runner --mode direct --category timeline

双路径：
  direct — route_query → simple_search / LangGraph stream（进程内同步调用）
  http   — POST /chat + SSE 解析（需先启动 agent server，--server 指定）

成本机制（Spec §3.6）：--dry-run 预估 → 用户同意 → 执行；judge 调用精确记录 tokens/cost 到
output/eval/cost_log.jsonl；agent 侧内部 LLM 调用无法取 usage，按响应字符估算并标注 estimate。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import httpx

from arknights_wiki.eval import config as eval_config
from arknights_wiki.eval.judge import judge_answer, rule_metrics
from arknights_wiki.eval.llm import compute_cost
from arknights_wiki.observability import TRACE_ROOT, flush, get_client

COST_LOG = Path(
    os.environ.get(
        "ARKNIGHTS_COST_LOG",
        str(ROOT / "output" / "eval" / "cost_log.jsonl"),
    )
)


def _log_cost(entry: dict) -> None:
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry["timestamp"] = datetime.now().isoformat(timespec="seconds")
    with COST_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _estimate_llm_cost(text: str, model: str | None = None) -> dict:
    """agent 侧内部调用无 usage 暴露，按字符估算 tokens（/1.5）并标注 estimate。

    model 缺省时读统一模型层配置（火山 deepseek-v4-flash-ga-260731 / DeepSeek deepseek-4-flash）。
    """
    if model is None:
        try:
            from arknights_wiki.extraction.llm_client import _get_model_config

            model = _get_model_config()["model"]
        except Exception:  # noqa: BLE001
            model = "deepseek-4-flash"
    tokens = max(1, int(len(text) // 1.5))
    return {
        "model": model,
        "tokens_in": 0,
        "tokens_out": tokens,
        "cost": compute_cost(model, 0, tokens),
        "estimate": True,
    }


def run_direct(question: str) -> dict:
    """direct 路径：与线上同一逻辑（route_query → simple / graph）"""
    from arknights_wiki.agent.router import route_query

    t0 = time.monotonic()
    route = route_query(question)
    tools_called: list[str] = []
    retrieval_context: list[str] = []
    if route["complexity"] == "simple":
        from arknights_wiki.agent.simple_search import simple_search

        result = simple_search(question, route)
        answer = result.get("answer", "")
        # simple 路径 sources 仅元数据（name/file_path），无正文——
        # retrieval_context 留空，打分时回退到出题材料（题目由材料生成，agent 检索同一知识库，近似一致）
    else:
        from arknights_wiki.agent.graph import build_agent_graph, build_planner_graph

        # W4: 支持 ARKNIGHTS_AGENT_MODE=react|planner（默认 react，2026-08-19 用户决策质量优先）
        agent_mode = os.environ.get("ARKNIGHTS_AGENT_MODE", "react")
        graph = build_planner_graph() if agent_mode == "planner" else build_agent_graph()
        initial_state = {
            "messages": [],
            "question": question,
            "collected_docs": [],
            "iteration": 0,
            "route": route,
        }
        final_state: dict = {}
        collected_docs: list[dict] = []
        for event in graph.stream(initial_state):
            for node_name, node_state in event.items():
                final_state = node_state
                # 工具节点产生的检索文档会随 state 传递，跨事件保留（与真实图一致）
                if node_state.get("collected_docs"):
                    collected_docs = node_state["collected_docs"]
        messages = final_state.get("messages", [])
        answer = messages[-1].get("content", "") if messages else ""
        tools_called = [d.get("tool", "") for d in collected_docs]
        for d in collected_docs:
            txt = d.get("result") or d.get("content") or ""
            if txt:
                retrieval_context.append(str(txt)[:1500])
        # 补充非工具节点文档（如对话/时间线检索结果）
        for d in final_state.get("collected_docs", []):
            txt = d.get("result") or d.get("content") or ""
            if txt and str(txt)[:1500] not in retrieval_context:
                retrieval_context.append(str(txt)[:1500])
    latency_ms = round((time.monotonic() - t0) * 1000, 1)
    cost_est = _estimate_llm_cost(answer)
    _log_cost({"step": f"agent_direct:{route['complexity']}", **cost_est})
    return {
        "answer": answer,
        "route": route["complexity"],
        "tools_called": tools_called,
        "retrieval_context": retrieval_context[:8],
        "latency_ms": latency_ms,
        "cost": cost_est["cost"],
    }


def run_http(question: str, server: str) -> dict:
    """http 路径：POST /chat + SSE 解析（覆盖服务层校验/限流/注入防御）"""
    t0 = time.monotonic()
    url = server.rstrip("/") + "/chat"
    answer_parts: list[str] = []
    tools_called: list[str] = []
    route_info: dict = {}
    try:
        with httpx.stream("POST", url, json={"question": question}, timeout=300.0) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    evt = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                evt_type = evt.get("event")
                data = evt.get("data", "")
                if evt_type == "route":
                    try:
                        route_info = json.loads(data)
                    except json.JSONDecodeError:
                        route_info = {"raw": data}
                elif evt_type == "step":
                    try:
                        tools_called.append(json.loads(data).get("tool", ""))
                    except json.JSONDecodeError:
                        pass
                elif evt_type == "token":
                    try:
                        answer_parts.append(json.loads(data).get("text", ""))
                    except json.JSONDecodeError:
                        answer_parts.append(data)
                elif evt_type == "error":
                    answer_parts.append(f"[agent error: {data[:200]}]")
                    break
    except Exception as e:  # noqa: BLE001
        return {
            "answer": f"[http 调用失败: {str(e)[:300]}]",
            "route": "error",
            "tools_called": [],
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "cost": 0.0,
            "error": str(e)[:300],
        }
    latency_ms = round((time.monotonic() - t0) * 1000, 1)
    answer = "".join(answer_parts)
    cost_est = _estimate_llm_cost(answer)
    _log_cost({"step": f"agent_http:{route_info.get('complexity', '?')}", **cost_est})
    return {
        "answer": answer,
        "route": route_info.get("complexity", "?"),
        "tools_called": tools_called,
        "latency_ms": latency_ms,
        "cost": cost_est["cost"],
    }


def _load_questions(bench_path: Path) -> list[dict]:
    items = []
    for line in bench_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(json.loads(line))
    return items


def _existing_ids(results_path: Path) -> set:
    if not results_path.exists():
        return set()
    ids = set()
    for line in results_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            ids.add(f"{r['id']}:{r['mode']}")
        except Exception:
            continue
    return ids


def _write_result(results_path: Path, row: dict) -> None:
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with results_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _run_and_score(item: dict, mode: str, args) -> dict:
    """跑单题单模式并评分（worker 单元，供串行/并行共用）。

    W1 Observability: direct 模式开启 trace 时每题包一个 chat_request 根
    （metadata.benchmark_id / mode 便于 Langfuse 过滤复盘）；http 模式由 server 侧创建根。
    """
    if mode == "direct":
        c = get_client()
        if c is not None:
            with c.start_as_current_observation(
                name=TRACE_ROOT,
                as_type="chain",
                input={"question": item["question"]},
                metadata={"benchmark_id": item["id"], "mode": "direct"},
            ):
                res = run_direct(item["question"])
        else:
            res = run_direct(item["question"])
    else:
        res = run_http(item["question"], args.server)
    row = {
        "id": item["id"],
        "mode": mode,
        "category": item.get("category", ""),
        "question": item["question"],
        "answer": res["answer"],
        "route": res.get("route", ""),
        "tools_called": res.get("tools_called", []),
        "retrieval_context": res.get("retrieval_context", []),
        "latency_ms": res.get("latency_ms", 0),
        "cost": res.get("cost", 0.0),
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    if not args.no_judge:
        judged = judge_answer(
            question=item["question"],
            answer=res["answer"],
            answer_key=item.get("answer_key", {}),
            tools_called=res.get("tools_called", []),
            expected_tools=item.get("requires_tools", []),
            expected_behavior=item.get("expected_behavior", ""),
        )
        row["judge"] = judged
        row["metrics"] = rule_metrics(
            answer=res["answer"],
            tools_called=res.get("tools_called", []),
            expected_tools=item.get("requires_tools", []),
            expected_behavior=item.get("expected_behavior", ""),
        )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="W0 Benchmark 评测运行器")
    parser.add_argument("--bench", default=str(ROOT / "benchmarks" / "arknights_bench" / "questions.jsonl"))
    parser.add_argument("--out", default=str(ROOT / "output" / "eval"))
    parser.add_argument("--mode", choices=["direct", "http", "both"], default="both")
    parser.add_argument("--limit", type=int, default=0, help="0=全部")
    parser.add_argument("--category", default="")
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-judge", action="store_true", help="只跑 agent 不评分（试跑用）")
    parser.add_argument("--workers", type=int, default=1, help="并发 worker 数（>1 时并行跑批加速）")
    args = parser.parse_args()

    bench_path = Path(args.bench)
    if not bench_path.exists():
        print(f"错误：题目集不存在 {bench_path}（先完成题目定稿）", file=sys.stderr)
        return 1
    items = _load_questions(bench_path)
    if args.category:
        items = [i for i in items if i.get("category") == args.category]
    if args.limit:
        items = items[: args.limit]

    modes = ["direct", "http"] if args.mode == "both" else [args.mode]
    agent_calls = len(items) * len(modes)
    judge_calls = 0 if args.no_judge else len(items)
    est_tokens = (agent_calls + judge_calls) * 2000
    est_cost = est_tokens / 1e6 * 0.3

    print("=== W0 评测预估 ===")
    print(f"题目: {len(items)} 条（{args.category or '全类别'}）| 模式: {modes} | judge: {'跳过' if args.no_judge else '六指标'}")
    print(f"外部调用估算: agent {agent_calls} 次（DeepSeek 内部计价）+ judge {judge_calls} 次（{eval_config.get_judge_model()}）")
    print(f"LLM tokens 估算: ~{est_tokens:,} → judge 侧费用 ~¥{est_cost:.3f}（Flash 档估算；agent 侧另按 DeepSeek 计价）")
    print(f"judge 模型: {eval_config.get_judge_model()} | base: {eval_config.get_ark_base()}")
    print(f"输出: {Path(args.out) / 'results_v1.jsonl'} + report_v1.md")
    if args.dry_run:
        print("\n[dry-run] 未执行任何外部调用。确认后去掉 --dry-run 运行。")
        return 0
    if not eval_config.get_opencode_go_key():
        print("错误：未检测到 opencode_go_api（HKCU 注册表，judge 需要）", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    results_path = out_dir / "results_v1.jsonl"
    existing = _existing_ids(results_path)

    tasks = [
        (item, mode)
        for item in items
        for mode in modes
        if f"{item['id']}:{mode}" not in existing
    ]
    print(f"\n开始评测（断点续跑，待跑 {len(tasks)} 条 / workers={args.workers}）...")

    if args.workers > 1:
        import concurrent.futures

        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            future_map = {
                ex.submit(_run_and_score, item, mode, args): (item, mode)
                for item, mode in tasks
            }
            for fut in concurrent.futures.as_completed(future_map):
                item, mode = future_map[fut]
                try:
                    row = fut.result()
                except Exception as e:  # noqa: BLE001
                    print(f"  ! {item['id']}:{mode} 失败: {str(e)[:200]}")
                    _write_result(results_path, {
                        "id": item["id"], "mode": mode, "question": item["question"],
                        "answer": f"[run error: {str(e)[:200]}]", "route": "error",
                        "latency_ms": 0, "cost": 0.0,
                        "ts": datetime.now().isoformat(timespec="seconds"),
                    })
                    done += 1
                    continue
                _write_result(results_path, row)
                done += 1
                print(f"  + {row['id']}:{mode} route={row['route']} len={len(row['answer'])} latency={row['latency_ms']}ms ({done}/{len(tasks)})")
    else:
        done = 0
        for item, mode in tasks:
            row = _run_and_score(item, mode, args)
            _write_result(results_path, row)
            done += 1
            print(f"  + {row['id']}:{mode} route={row['route']} len={len(row['answer'])} latency={row['latency_ms']}ms ({done}/{len(tasks)})")

    print(f"\n完成。明细: {results_path}")
    flush()  # W1 Observability: 冲刷未导出的 trace（CLI 短生命周期进程）
    if not args.no_judge:
        try:
            from arknights_wiki.eval.report import generate_report

            report_path = generate_report(results_path, out_dir)
            print(f"报告: {report_path}")
        except Exception as e:  # noqa: BLE001
            print(f"报告生成失败: {str(e)[:200]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
