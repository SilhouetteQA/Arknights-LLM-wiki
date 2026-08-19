"""W4 用户自测：5 问 × ReAct/Planner 双模式对比 + 质量评估 + 报告

用法: python scripts/w4_user_test.py
输出: output/eval/w4_user_test_report.md
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from arknights_wiki.eval import config as eval_config
from arknights_wiki.eval.llm import chat_json

QUESTIONS = [
    ("Q1", "主线三个大篇章分别讲了什么故事？"),
    ("Q2", "分别介绍一下当前世界观下各个国家都是什么政权，如何统治国家的？"),
    ("Q3", "萨卡兹肉鸽中的阿米娅有多厉害？"),
    ("Q4", "莱茵十杰分别是谁，都负责什么工作，有哪些成就？"),
    ("Q5", "世界观下三大源石矿脉是哪三个，乌萨斯矿脉为什么枯竭了，岁兽和炎国的矿脉又是什么关系？"),
]

QUALITY_SYSTEM_PROMPT = """你是《明日方舟》剧情专家评审。对用户答案做**无参考答案**的质量评估，输出 0-1 小数：
1. coverage：回答覆盖问题的完整程度（要点是否齐全）
2. accuracy：回答的事实准确性（以你的明日方舟剧情知识判断，明显错误/张冠李戴扣分）
3. faithfulness：回答是否忠实于剧情设定（是否存在明显编造/夸大/无依据的断言；越忠实越高分）
4. structure：回答的结构组织清晰度（层次、条理）
输出严格 JSON：{"coverage": 0.0-1.0, "accuracy": 0.0-1.0, "faithfulness": 0.0-1.0, "structure": 0.0-1.0, "reason": "一两句中文理由"}"""


MODES = ["react", "planner", "planner_task_react"]  # 三种路由方式

# 模式 → 环境变量（graph 构建时读取）
MODE_ENV = {
    "react": {"ARKNIGHTS_AGENT_MODE": "react", "ARKNIGHTS_PLANNER_TASK_REACT": "0"},
    "planner": {"ARKNIGHTS_AGENT_MODE": "planner", "ARKNIGHTS_PLANNER_TASK_REACT": "0"},
    "planner_task_react": {"ARKNIGHTS_AGENT_MODE": "planner", "ARKNIGHTS_PLANNER_TASK_REACT": "1"},
}


def run_question(question: str, mode: str) -> dict:
    """跑一次问答（mode: react | planner | planner_task_react），返回答案与元数据"""
    from arknights_wiki.agent.graph import build_agent_graph, build_planner_graph
    from arknights_wiki.agent.router import route_query

    # 应用模式对应环境变量（串行设置，进程内生效）
    for k, v in MODE_ENV[mode].items():
        os.environ[k] = v

    t0 = time.monotonic()
    route = route_query(question)
    planner_source = ""
    if route["complexity"] == "simple":
        from arknights_wiki.agent.simple_search import simple_search

        result = simple_search(question, route)
        answer = result.get("answer", "")
        tools = []
    else:
        if mode == "react":
            graph = build_agent_graph()
        else:
            graph = build_planner_graph()
        state = {
            "messages": [], "question": question, "collected_docs": [],
            "iteration": 0, "route": route,
        }
        final = graph.invoke(state)
        messages = final.get("messages", [])
        answer = messages[-1].get("content", "") if messages else ""
        tools = [d.get("tool", "") for d in final.get("collected_docs", [])]
        planner_source = final.get("planner_source", "")

    return {
        "question": question,
        "mode": mode,
        "route": route["complexity"],
        "answer": answer,
        "tools": tools,
        "n_tools": len(tools),
        "latency_s": round(time.monotonic() - t0, 1),
        "planner_source": planner_source,
    }


def judge_quality(question: str, answer: str) -> dict:
    """无参考答案质量评估"""
    prompt = (
        f"问题：{question}\n\n"
        f"用户答案（待评分）：{answer[:4000]}\n\n"
        "请按系统要求输出四维质量评估 JSON。"
    )
    for _ in range(2):
        try:
            out = chat_json(eval_config.get_judge_model(), QUALITY_SYSTEM_PROMPT, prompt)
            out.pop("_stats", None)
            required = {"coverage", "accuracy", "faithfulness", "structure", "reason"}
            if required.issubset(out.keys()):
                return out
        except Exception:
            continue
    return {"coverage": 0.0, "accuracy": 0.0, "faithfulness": 0.0,
            "structure": 0.0, "reason": "评估调用失败"}


def main():
    results: list[dict] = []
    # 每模式并行 5 问（同模式 env 一致，线程安全）；模式间串行
    for mode in MODES:
        print(f"[{mode}] 开始跑 {len(QUESTIONS)} 问...")
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = [ex.submit(run_question, q, mode) for _, q in QUESTIONS]
            for f in futures:
                r = f.result()
                r["mode"] = mode
                results.append(r)
                print(f"  {r['question'][:24]}... ({mode}) {r['n_tools']} 工具 {r['latency_s']}s")

    # 评估（并行）
    print(f"评估 {len(results)} 份答案...")
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(judge_quality, r["question"], r["answer"]): r for r in results}
        for f, r in futures.items():
            r["eval"] = f.result()

    # 写报告
    report = _build_report(results)
    out_path = PROJECT_ROOT / "output" / "eval" / "w4_three_mode_report.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"\n报告已生成: {out_path}")
    # 汇总打印
    for qid, q in QUESTIONS:
        for mode in MODES:
            r = next(x for x in results if x["question"] == q and x["mode"] == mode)
            e = r["eval"]
            print(f"{qid} {mode}: cov={e['coverage']} acc={e['accuracy']} fth={e['faithfulness']} str={e['structure']} tools={r['n_tools']} {r['latency_s']}s")


def _build_report(results: list[dict]) -> str:
    lines = []
    lines.append("# W4 三路由方式对比报告：ReAct / Planner / Planner+任务级ReAct")
    lines.append("")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 评估模型：{eval_config.get_judge_model()}（无参考答案质量评估：coverage/accuracy/faithfulness/structure）")
    lines.append("")

    # 汇总表
    lines.append("## 一、汇总对比")
    lines.append("")
    lines.append("| 问题 | 模式 | coverage | accuracy | faithfulness | structure | 工具调用 | 延迟(s) | 路由 |")
    lines.append("|------|------|----------|----------|--------------|-----------|----------|---------|------|")
    for qid, q in QUESTIONS:
        for mode in MODES:
            r = next(x for x in results if x["question"] == q and x["mode"] == mode)
            e = r["eval"]
            lines.append(
                f"| {qid} | {mode} | {e['coverage']} | {e['accuracy']} | {e['faithfulness']} "
                f"| {e['structure']} | {r['n_tools']} | {r['latency_s']} | {r['route']} |"
            )
    lines.append("")

    # 每题详情
    for qid, q in QUESTIONS:
        lines.append(f"## {qid}：{q}")
        lines.append("")
        for mode in MODES:
            r = next(x for x in results if x["question"] == q and x["mode"] == mode)
            e = r["eval"]
            lines.append(f"### {mode} 模式（工具 {r['n_tools']} 次 · 延迟 {r['latency_s']}s"
                         + (f" · 规划来源 {r['planner_source']}" if mode == "planner" else "") + "）")
            lines.append("")
            lines.append(f"**评估**：coverage {e['coverage']} / accuracy {e['accuracy']} / "
                         f"faithfulness {e['faithfulness']} / structure {e['structure']}")
            lines.append(f"理由：{e['reason']}")
            lines.append("")
            lines.append("**答案**：")
            lines.append("")
            lines.append(r["answer"].strip())
            lines.append("")
            lines.append("---")
            lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
