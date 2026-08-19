"""W4 三路由方式总对比：benchmark 10 题（六指标）+ 用户自测 5 问（质量评估）

三种路由:
  1. react             — ReAct 循环（ARKNIGHTS_AGENT_MODE=react）
  2. planner           — Plan→Execute→Synthesize（默认单工具执行 + 崩溃兜底）
  3. planner_task_react— Planner + 任务级 ReAct 混合（ARKNIGHTS_PLANNER_TASK_REACT=1）

输出:
  output/eval/w4_cmp_{mode}/report_v1.md  — benchmark 六指标
  output/eval/w4_three_mode_report.md     — 用户自测质量评估
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

PY = r"D:\CodexPython312\python.exe"
BENCH = "benchmarks/arknights_bench/questions_draft.jsonl"

MODES = {
    "react": {"ARKNIGHTS_AGENT_MODE": "react", "ARKNIGHTS_PLANNER_TASK_REACT": "0"},
    "planner": {"ARKNIGHTS_AGENT_MODE": "planner", "ARKNIGHTS_PLANNER_TASK_REACT": "0"},
    "planner_task_react": {"ARKNIGHTS_AGENT_MODE": "planner", "ARKNIGHTS_PLANNER_TASK_REACT": "1"},
}


def run_benchmark_mode(mode: str, env: dict):
    """benchmark 10 题 × 单模式（eval runner，六指标 judge）"""
    print(f"\n===== benchmark [{mode}] =====", flush=True)
    run_env = {**os.environ, **env}
    out_dir = f"output/eval/w4_cmp_{mode}"
    cmd = [PY, "-m", "arknights_wiki.eval.runner",
           "--bench", BENCH, "--mode", "direct", "--limit", "10",
           "--out", out_dir, "--workers", "2"]
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=run_env, check=True)


def run_user_test():
    """用户自测 5 问 × 三模式（质量评估）"""
    print("\n===== 用户自测 5 问 × 三模式 =====", flush=True)
    subprocess.run([PY, "scripts/w4_user_test.py"], cwd=str(PROJECT_ROOT), check=True)


def main():
    for mode, env in MODES.items():
        run_benchmark_mode(mode, env)
    run_user_test()
    print("\n===== 全部完成 =====")
    print("benchmark 报告: output/eval/w4_cmp_{mode}/report_v1.md")
    print("自测报告: output/eval/w4_three_mode_report.md")


if __name__ == "__main__":
    main()
