"""LangGraph checkpoint 工厂（W2 Failure Recovery）

server complex 路径的 checkpointer：
  - 默认 SqliteSaver 持久化到 output/checkpoints/agent.sqlite（跨请求断点续跑）
  - ARKNIGHTS_CHECKPOINT=0 或 sqlite 不可用时降级 MemorySaver（进程内语义）
每请求新建连接（executor 线程内使用，避免跨线程共享 sqlite 连接）。
"""
from __future__ import annotations

import os
from pathlib import Path

from arknights_wiki.config import PROJECT_ROOT


def _checkpoint_db() -> Path:
    env = os.environ.get("ARKNIGHTS_CHECKPOINT_DB", "")
    if env:
        return Path(env)
    return Path(PROJECT_ROOT) / "output" / "checkpoints" / "agent.sqlite"


def make_checkpointer():
    """创建 checkpoint 实例（线程内使用，勿跨线程共享同一实例）"""
    if os.environ.get("ARKNIGHTS_CHECKPOINT", "1") == "0":
        return _memory_saver()

    db = _checkpoint_db()
    try:
        db.parent.mkdir(parents=True, exist_ok=True)
        from langgraph.checkpoint.sqlite import SqliteSaver

        return SqliteSaver.from_conn_string(str(db))
    except Exception:  # noqa: BLE001 — 降级内存 checkpoint，不阻断服务
        return _memory_saver()


def _memory_saver():
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()
