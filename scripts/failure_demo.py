"""W2 Failure Recovery 验收脚本

演示恢复链四个核心场景（离线，无需 LLM API）:
  1. 超时 → 重试 → fallback
  2. 报错 → 重试 → fallback 命中（文本带降级标注）
  3. 连续失败 → circuit breaker 打开 → 短路
  4. LLM 调用（chat_completion）网络异常 → 指数退避重试成功

可选 --trace: 在 Langfuse trace 下跑场景 1/2，生成真实 trace
（需 Langfuse 容器运行 + docker/langfuse/.env 密钥）。

用法:
  python scripts/failure_demo.py          # 离线四场景
  python scripts/failure_demo.py --trace  # 追加 trace 演示（验证 retries/fallback 可见）
"""
from __future__ import annotations

import os
import sys
import time as time_mod
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

PASS = 0
FAIL = 0


def _check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    mark = "PASS" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{mark}] {name}" + (f"  ({detail})" if detail else ""))


def demo_timeout_retry_fallback():
    """场景1: 超时 → 重试（仍超时）→ fallback 命中"""
    print("\n场景1: timeout → retry → fallback")
    from arknights_wiki.agent.resilience import (
        OperationTimeoutError,
        ResilienceConfig,
        execute_with_resilience,
    )

    def slow(**kwargs):
        time_mod.sleep(0.5)
        return "slow-result"

    def fallback(**kwargs):
        return "fallback-result"

    config = ResilienceConfig(
        timeout_seconds=0.05, max_retries=2,
        backoff_base=0.0, breaker_threshold=0,
    )
    t0 = time_mod.time()
    result, stats = execute_with_resilience(
        slow, (), {"q": "x"}, config, fallbacks=[(fallback, "fb_fn")]
    )
    elapsed = time_mod.time() - t0
    _check("fallback 结果返回", result == "fallback-result", f"got={result}")
    _check("timeout_hit=True", stats["timeout_hit"] is True, f"stats={stats}")
    _check("retries=2", stats["retries"] == 2, f"retries={stats['retries']}")
    _check("fallback_used=fb_fn", stats["fallback_used"] == "fb_fn")
    _check("总耗时受控(≈0.1s 而非 1.5s)", elapsed < 0.4, f"{elapsed:.2f}s")


def demo_error_fallback():
    """场景2: 工具抛异常 → 重试 → fallback 命中（经 graph 恢复链入口）"""
    print("\n场景2: error → retry → fallback（graph._run_tool_with_resilience）")
    from arknights_wiki.agent.graph import _run_tool_with_resilience

    def broken(**kwargs):
        raise ConnectionError("store unavailable")

    # 用 graph 入口: get_entity_page 失败 → fallback search_wiki（真实执行本地检索）
    result, stats = _run_tool_with_resilience(
        "get_entity_page", {"name": "罗德岛", "entity_type": "faction"}, broken
    )
    _check("fallback 命中", stats["fallback_used"] == "search_wiki", f"fb={stats['fallback_used']}")
    _check("文本带降级标注", result.startswith("[已降级: search_wiki]"), result[:40])
    _check("retries=2", stats["retries"] == 2, f"retries={stats['retries']}")


def demo_breaker():
    """场景3: 连续失败 → breaker open → 短路（不执行函数）"""
    print("\n场景3: circuit breaker 短路")
    from arknights_wiki.agent.resilience import BreakerOpenError, CircuitBreaker, retry_call
    from arknights_wiki.agent.resilience import ResilienceConfig

    calls = {"n": 0}

    def failing(**kwargs):
        calls["n"] += 1
        raise ConnectionError("down")

    breaker = CircuitBreaker(threshold=3, reset_seconds=60.0)
    config = ResilienceConfig(max_retries=0, timeout_seconds=5.0,
                              backoff_base=0.0, breaker_threshold=3,
                              breaker_reset_seconds=60.0)
    for i in range(3):
        try:
            retry_call(failing, (), {}, config, breaker)
        except Exception:
            pass
    _check("breaker open", breaker.state == "open", f"state={breaker.state}")
    before = calls["n"]
    try:
        retry_call(failing, (), {}, config, breaker)
        _check("open 后应短路", False, "未短路！")
    except BreakerOpenError:
        _check("open 后抛 BreakerOpenError", True)
    _check("短路未执行函数", calls["n"] == before, f"calls={calls['n']}")


def demo_llm_retry():
    """场景4: LLM 调用网络异常 → 指数退避重试成功"""
    print("\n场景4: chat_completion 网络异常重试")
    from unittest.mock import MagicMock, patch

    from openai import APIConnectionError

    from arknights_wiki.extraction.llm_client import chat_completion

    client = MagicMock()
    calls = {"n": 0}

    def _flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise APIConnectionError(message="conn", request=MagicMock())
        r = MagicMock()
        r.choices[0].message.content = "ok"
        r.choices[0].message.tool_calls = None
        r.usage.prompt_tokens = 10
        r.usage.completion_tokens = 5
        return r

    client.chat.completions.create.side_effect = _flaky
    with patch("arknights_wiki.extraction.llm_client.create_client", return_value=client):
        with patch("arknights_wiki.extraction.llm_client._get_model_config",
                   return_value={"model": "test-model", "max_tokens": 100}):
            content, _ = chat_completion(messages=[{"role": "user", "content": "hi"}])
    _check("重试后成功", content == "ok", f"content={content}")
    _check("调用 3 次(1+2 重试)", calls["n"] == 3, f"calls={calls['n']}")


def demo_trace():
    """场景5: Langfuse trace 下验证 retries/fallback 字段可见（需容器 + .env 密钥）"""
    print("\n场景5: trace 可见性（Langfuse）")
    env_file = PROJECT_ROOT / "docker" / "langfuse" / ".env"
    if not env_file.exists():
        _check("跳过: docker/langfuse/.env 不存在", False)
        return
    # 从 .env 读取（compose 用 LANGFUSE_INIT_PROJECT_* 前缀；SDK 需要 LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASE_URL）
    env = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"')
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", env.get("LANGFUSE_INIT_PROJECT_PUBLIC_KEY", ""))
    os.environ.setdefault("LANGFUSE_SECRET_KEY", env.get("LANGFUSE_INIT_PROJECT_SECRET_KEY", ""))
    os.environ.setdefault("LANGFUSE_BASE_URL", env.get("LANGFUSE_BASE_URL", "http://localhost:3000"))

    from arknights_wiki.observability import TRACE_ROOT, get_client
    from arknights_wiki.observability.client import flush

    if get_client() is None:
        _check("跳过: trace 未启用（LANGFUSE 三键缺失）", False)
        return

    from arknights_wiki.agent.graph import _execute_tool_traced

    def broken(**kwargs):
        raise ConnectionError("store unavailable")

    with get_client().start_as_current_observation(
        name=TRACE_ROOT, as_type="chain",
        input={"question": "验收: 注入工具失败 → fallback"},
        metadata={"complexity": "complex", "question_type": "failure_demo",
                  "benchmark_id": "w2-acceptance"},
    ):
        result = _execute_tool_traced(
            "get_entity_page", {"name": "罗德岛", "entity_type": "faction"}, broken
        )
    flush()
    _check("文本标注降级", result.startswith("[已降级: search_wiki]"), result[:30])
    print(f"  → Langfuse UI 查看 trace: http://localhost:3000 (benchmark_id=w2-acceptance)")


def main():
    demo_timeout_retry_fallback()
    demo_error_fallback()
    demo_breaker()
    demo_llm_retry()
    if "--trace" in sys.argv:
        demo_trace()
    print(f"\n===== 结果: {PASS} PASS / {FAIL} FAIL =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
