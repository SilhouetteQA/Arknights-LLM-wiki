"""Resilience 恢复链模块（W2 Failure Recovery）

恢复链: timeout → retry(指数退避) → circuit breaker → fallback → escalation
与 observability 解耦（不依赖 trace 开关），stats 供调用方埋点。

设计要点:
  - with_timeout: 线程池执行 + future.result(timeout)（Windows 无 SIGALRM，跨平台方案）。
    超时后线程继续运行但结果丢弃（检索类只读函数无副作用，可接受）。
  - CircuitBreaker: closed → open → half_open → closed 状态机，线程安全。
  - retry_call: 指数退避重试，仅对 retryable_exceptions 重试，每次失败喂给 breaker。
  - execute_with_resilience: 统一入口，主函数 + fallbacks 依次尝试，全失败抛 ResilienceError。
"""
from __future__ import annotations

import concurrent.futures
import dataclasses
import threading
import time as time_mod
from typing import Callable, Iterable, Sequence

# ---- 异常 ----

class OperationTimeoutError(TimeoutError):
    """单次执行超时（继承内置 TimeoutError，`except TimeoutError` 也能捕获）"""


class BreakerOpenError(RuntimeError):
    """熔断器打开，请求被短路（不执行目标函数）"""


class ResilienceError(RuntimeError):
    """恢复链全部耗尽（重试 + fallback），携带统计信息供上层降级"""

    def __init__(self, message: str, stats: dict):
        super().__init__(message)
        self.stats = stats


# ---- 配置 ----

@dataclasses.dataclass
class ResilienceConfig:
    """恢复链配置（按调用场景覆盖）"""

    timeout_seconds: float = 30.0      # 单次执行超时（0 = 不启用）
    max_retries: int = 2               # 重试次数（不含首次；0 = 不重试）
    backoff_base: float = 1.0          # 退避基数：wait = min(base * 2**attempt, backoff_max)
    backoff_max: float = 8.0           # 退避上限（秒）
    retryable_exceptions: tuple = (Exception,)  # 可重试异常类型
    breaker_threshold: int = 5         # 熔断打开阈值（连续失败次数；0 = 不启用熔断）
    breaker_reset_seconds: float = 60.0  # 熔断打开后进入 half_open 的等待
    fallback_enabled: bool = True

    def __post_init__(self):
        if self.retryable_exceptions is None:
            self.retryable_exceptions = (Exception,)


# ---- 线程池（timeout 用）----

_executor: concurrent.futures.ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=8, thread_name_prefix="ark-resilience"
                )
    return _executor


def with_timeout(fn: Callable, args: Sequence = (), kwargs: dict | None = None,
                 seconds: float = 30.0):
    """在线程中执行 fn，超过 seconds 抛 OperationTimeoutError（0 = 不启用）"""
    if seconds <= 0:
        return fn(*args, **(kwargs or {}))
    future = _get_executor().submit(fn, *args, **(kwargs or {}))
    try:
        return future.result(timeout=seconds)
    except concurrent.futures.TimeoutError as e:
        future.cancel()
        raise OperationTimeoutError(
            f"执行超时（>{seconds}s）: {getattr(fn, '__name__', fn)}"
        ) from e


# ---- 熔断器 ----

class CircuitBreaker:
    """线程安全熔断器：closed → open → half_open → closed"""

    def __init__(self, threshold: int = 5, reset_seconds: float = 60.0):
        self.threshold = max(threshold, 1)
        self.reset_seconds = reset_seconds
        self._lock = threading.Lock()
        self._failures = 0
        self._state = "closed"
        self._opened_at: float | None = None

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "open" and self._opened_at is not None:
                if time_mod.time() - self._opened_at >= self.reset_seconds:
                    self._state = "half_open"
            return self._state

    def is_open(self) -> bool:
        return self.state == "open"

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            if self._state != "closed":
                self._state = "closed"
                self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._state == "half_open" or self._failures >= self.threshold:
                self._state = "open"
                self._opened_at = time_mod.time()


# ---- 重试 ----

def _is_retryable(exc: BaseException, config: ResilienceConfig) -> bool:
    return isinstance(exc, config.retryable_exceptions)


def retry_call(fn: Callable, args: Sequence = (), kwargs: dict | None = None,
               config: ResilienceConfig | None = None,
               breaker: CircuitBreaker | None = None,
               stats_out: dict | None = None) -> tuple:
    """指数退避重试调用。

    Returns:
        (result, stats) — stats: attempts / retries / breaker_state / error
    Raises:
        重试耗尽后抛最后一次异常；breaker open 时抛 BreakerOpenError。
        stats_out 传入时失败路径也会被填充（供上层恢复链统计）。
    """
    config = config or ResilienceConfig()
    kwargs = kwargs or {}
    stats = stats_out if stats_out is not None else {}
    stats.update({"attempts": 0, "retries": 0, "breaker_state": "closed",
                  "error": None})

    if breaker is not None and breaker.is_open():
        stats["breaker_state"] = "open"
        raise BreakerOpenError("熔断器打开，请求被短路")

    attempt = 0
    last_error: BaseException | None = None
    while True:
        stats["attempts"] = attempt + 1
        try:
            result = with_timeout(fn, args, kwargs, config.timeout_seconds)
            if breaker is not None:
                breaker.record_success()
            stats["breaker_state"] = breaker.state if breaker else "closed"
            stats["retries"] = stats["attempts"] - 1
            return result, stats
        except OperationTimeoutError as e:
            last_error = e
        except Exception as e:  # noqa: BLE001 — 按配置过滤可重试性
            if not _is_retryable(e, config):
                raise
            last_error = e

        if breaker is not None:
            breaker.record_failure()
            stats["breaker_state"] = breaker.state
        if breaker is not None and breaker.is_open():
            raise BreakerOpenError("熔断器打开，请求被短路") from last_error

        if attempt >= config.max_retries:
            break
        wait = min(config.backoff_base * (2 ** attempt), config.backoff_max)
        if wait > 0:
            time_mod.sleep(wait)
        attempt += 1

    stats["retries"] = stats["attempts"] - 1
    stats["error"] = str(last_error) if last_error else None
    if last_error is not None:
        raise last_error
    raise RuntimeError("retry_call 未产生结果")


# ---- 统一入口 ----

def execute_with_resilience(
    fn: Callable,
    args: Sequence = (),
    kwargs: dict | None = None,
    config: ResilienceConfig | None = None,
    fallbacks: Iterable[tuple[Callable, str]] | None = None,
    breaker: CircuitBreaker | None = None,
) -> tuple:
    """统一恢复链入口：主函数重试 → 依次 fallback → 全失败抛 ResilienceError。

    Args:
        fn: 主执行函数
        fallbacks: [(fn, 描述), ...]，主函数失败后依次尝试
        breaker: 共享熔断器（同一源的工具共用）

    Returns:
        (result, stats) — stats: attempts/retries/timeout_hit/breaker_state/fallback_used/error
    Raises:
        ResilienceError（全链耗尽，含 stats）；breaker open 时 BreakerOpenError
    """
    config = config or ResilienceConfig()
    fallbacks = list(fallbacks) if fallbacks else []
    if breaker is None and config.breaker_threshold > 0:
        breaker = CircuitBreaker(
            threshold=config.breaker_threshold,
            reset_seconds=config.breaker_reset_seconds,
        )

    stats = {"attempts": 0, "retries": 0, "timeout_hit": False,
             "breaker_state": "closed", "fallback_used": None, "error": None}

    # 主函数（stats_out 共享，失败时 stats 也填充 attempts/retries/error）
    try:
        result, rstats = retry_call(fn, args, kwargs, config, breaker, stats_out=stats)
        stats.update(rstats)
        return result, stats
    except OperationTimeoutError as e:
        stats["timeout_hit"] = True
        last_error = e
    except Exception as e:  # noqa: BLE001 — 进入 fallback 链
        last_error = e
        if isinstance(e, BreakerOpenError):
            stats["breaker_state"] = "open"
            raise

    stats["error"] = str(last_error)

    # fallback 链（独立 stats_out，不覆盖主函数统计）
    if config.fallback_enabled:
        for fb_fn, fb_name in fallbacks:
            fb_stats: dict = {}
            try:
                result, _ = retry_call(fb_fn, (), {}, config, breaker, stats_out=fb_stats)
                stats["fallback_used"] = fb_name
                stats["breaker_state"] = breaker.state if breaker else "closed"
                return result, stats
            except OperationTimeoutError:
                stats["timeout_hit"] = True
            except BreakerOpenError:
                stats["breaker_state"] = "open"
                raise
            except Exception:  # noqa: BLE001 — 尝试下一个 fallback
                continue

    raise ResilienceError(
        f"恢复链全部耗尽: {getattr(fn, '__name__', fn)} -> {stats['error']}",
        stats,
    )
