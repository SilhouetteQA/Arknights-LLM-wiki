"""Resilience 恢复链模块测试（W2 Failure Recovery）

覆盖: timeout / retry(指数退避) / circuit breaker / fallback / 组合降级。
"""
from unittest.mock import patch

import pytest

from arknights_wiki.agent.resilience import (
    BreakerOpenError,
    CircuitBreaker,
    OperationTimeoutError,
    ResilienceConfig,
    ResilienceError,
    execute_with_resilience,
    retry_call,
    with_timeout,
)


def _flaky(fail_times: int, result: str = "ok", exc: type = ConnectionError):
    """前 fail_times 次抛 exc，之后返回 result 的函数"""
    state = {"n": 0}

    def fn(*args, **kwargs):
        if state["n"] < fail_times:
            state["n"] += 1
            raise exc("boom")
        return result

    return fn, state


def _base_config(**overrides) -> ResilienceConfig:
    defaults = dict(
        timeout_seconds=5.0,
        max_retries=2,
        backoff_base=0.0,  # 测试默认零退避，避免真实 sleep
        breaker_threshold=3,
        breaker_reset_seconds=60.0,
    )
    defaults.update(overrides)
    return ResilienceConfig(**defaults)


class TestWithTimeout:
    def test_fast_fn_returns_result(self):
        assert with_timeout(lambda: "r", seconds=1.0) == "r"

    def test_slow_fn_raises_timeout(self):
        with pytest.raises(OperationTimeoutError):
            with_timeout(lambda: __import__("time").sleep(0.5), seconds=0.05)

    def test_args_passed_through(self):
        assert with_timeout(lambda a, b: a + b, (1, 2), {}, seconds=1.0) == 3


class TestRetryCall:
    def test_success_first_try_no_retry(self):
        fn, _ = _flaky(0)
        result, stats = retry_call(fn, (), {}, _base_config(), None)
        assert result == "ok"
        assert stats["attempts"] == 1
        assert stats["retries"] == 0

    def test_retry_succeeds_after_failures(self):
        fn, _ = _flaky(2)
        result, stats = retry_call(fn, (), {}, _base_config(max_retries=3), None)
        assert result == "ok"
        assert stats["attempts"] == 3
        assert stats["retries"] == 2

    def test_retry_exhausted_raises_last_error(self):
        fn, _ = _flaky(99)
        with pytest.raises(ConnectionError):
            retry_call(fn, (), {}, _base_config(max_retries=2), None)

    def test_backoff_exponential(self):
        fn, _ = _flaky(3)
        config = _base_config(max_retries=3, backoff_base=1.0, backoff_max=8.0)
        with patch("arknights_wiki.agent.resilience.time_mod.sleep") as mock_sleep:
            retry_call(fn, (), {}, config, None)
        assert mock_sleep.call_count == 3
        waits = [c.args[0] for c in mock_sleep.call_args_list]
        assert waits == [1.0, 2.0, 4.0]  # 2^0, 2^1, 2^2

    def test_backoff_capped(self):
        fn, _ = _flaky(10)
        config = _base_config(max_retries=5, backoff_base=1.0, backoff_max=3.0)
        with patch("arknights_wiki.agent.resilience.time_mod.sleep") as mock_sleep:
            with pytest.raises(ConnectionError):
                retry_call(fn, (), {}, config, None)
        waits = [c.args[0] for c in mock_sleep.call_args_list]
        assert waits == [1.0, 2.0, 3.0, 3.0, 3.0]

    def test_non_retryable_error_not_retried(self):
        fn, _ = _flaky(99, exc=ValueError)
        config = _base_config(retryable_exceptions=(ConnectionError,))
        with pytest.raises(ValueError):
            retry_call(fn, (), {}, config, None)


class TestCircuitBreaker:
    def test_open_after_threshold(self):
        breaker = CircuitBreaker(threshold=3, reset_seconds=60.0)
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == "open"

    def test_open_short_circuits_without_executing(self):
        breaker = CircuitBreaker(threshold=2, reset_seconds=60.0)
        breaker.record_failure()
        breaker.record_failure()
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            raise ConnectionError("x")

        with pytest.raises(BreakerOpenError):
            retry_call(fn, (), {}, _base_config(), breaker)
        assert calls["n"] == 0  # 短路：函数未被调用

    def test_half_open_success_closes(self):
        breaker = CircuitBreaker(threshold=2, reset_seconds=0.05)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == "open"
        import time as time_mod

        time_mod.sleep(0.08)
        assert breaker.state == "half_open"
        breaker.record_success()
        assert breaker.state == "closed"

    def test_half_open_failure_reopens(self):
        breaker = CircuitBreaker(threshold=2, reset_seconds=0.05)
        breaker.record_failure()
        breaker.record_failure()
        import time as time_mod

        time_mod.sleep(0.08)
        assert breaker.state == "half_open"
        breaker.record_failure()
        assert breaker.state == "open"

    def test_success_resets_counter(self):
        breaker = CircuitBreaker(threshold=3, reset_seconds=60.0)
        breaker.record_failure()
        breaker.record_success()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == "closed"  # 成功清零后需再连续 3 次才打开


class TestExecuteWithResilience:
    # 以下场景禁用熔断（breaker_threshold=0），熔断行为单独在 test_breaker_open_* 验证

    def test_fallback_used(self):
        fn, _ = _flaky(99)
        fallback, _ = _flaky(0, result="fb")
        result, stats = execute_with_resilience(
            fn, (), {}, _base_config(breaker_threshold=0),
            fallbacks=[(fallback, "fallback_fn")]
        )
        assert result == "fb"
        assert stats["fallback_used"] == "fallback_fn"
        assert stats["retries"] == 2

    def test_multiple_fallbacks_sequentially(self):
        fn, _ = _flaky(99)
        fb1, _ = _flaky(99)
        fb2, _ = _flaky(0, result="fb2")
        result, stats = execute_with_resilience(
            fn, (), {}, _base_config(breaker_threshold=0),
            fallbacks=[(fb1, "fb1"), (fb2, "fb2")]
        )
        assert result == "fb2"
        assert stats["fallback_used"] == "fb2"

    def test_all_failed_raises_resilience_error(self):
        fn, _ = _flaky(99)
        fb1, _ = _flaky(99)
        with pytest.raises(ResilienceError) as ei:
            execute_with_resilience(
                fn, (), {}, _base_config(breaker_threshold=0),
                fallbacks=[(fb1, "fb1")]
            )
        assert ei.value.stats["fallback_used"] is None
        assert "error" in ei.value.stats

    def test_timeout_then_fallback(self):
        def slow():
            __import__("time").sleep(0.5)
            return "late"

        fallback, _ = _flaky(0, result="fb")
        result, stats = execute_with_resilience(
            slow, (), {}, _base_config(timeout_seconds=0.05, breaker_threshold=0),
            fallbacks=[(fallback, "fb")],
        )
        assert result == "fb"
        assert stats["timeout_hit"] is True

    def test_breaker_open_short_circuits_everything(self):
        fn, _ = _flaky(99)
        fallback, _ = _flaky(0, result="fb")
        config = _base_config(breaker_threshold=2)
        breaker = CircuitBreaker(threshold=2, reset_seconds=60.0)
        with pytest.raises(BreakerOpenError):
            execute_with_resilience(
                fn, (), {}, config, fallbacks=[(fallback, "fb")],
                breaker=breaker,
            )

    def test_stats_shape(self):
        fn, _ = _flaky(1)
        result, stats = execute_with_resilience(fn, (), {}, _base_config())
        assert result == "ok"
        assert set(stats) >= {
            "attempts", "retries", "timeout_hit", "breaker_state", "fallback_used", "error",
        }
        assert stats["attempts"] == 2
        assert stats["breaker_state"] in ("closed", "open", "half_open")
