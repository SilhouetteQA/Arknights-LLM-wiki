"""Wiki 业务不变性测试（Spec 07）。

证明 `off` 与 `observe` 在**固定输入**下产生完全相同的业务输出与副作用：

```text
chat_completion        → (content, message)、provider 请求参数
_llm_intent_rewrite    → 返回值（含 None 兜底）
runner/judge/scoring   → 写出的 JSONL 行（除 timestamp）
summarize_cost         → 返回 dict（含缺文件路径）
Langfuse 遥测          → record_llm_usage 的调用参数（除 latency_ms）
```

以及"失败也不变"：observe 下注入 mapping failure / sink failure 时，
以上输出与副作用仍然不变，且不会冒出异常。

deepeval 处理方式与 `test_producer_wiring.py` 一致：scoring.py 顶层 import deepeval，
而项目只在 `deepeval-local` 容器内跑 deepeval，因此**不注入假模块**；
真实 deepeval 不可用时该 stage 明确 skip，容器内则真正执行。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_core.contracts.enums.modes import ContractMode
from agent_core.contracts.models.evidence import EvidenceRecord
from agent_core.contracts.protocols.evidence_sink import SinkFailure

from arknights_wiki import observability
from arknights_wiki.adapters.foundation import mapping as mapping_mod
from arknights_wiki.adapters.foundation.runtime import (
    WikiFoundationRuntime,
    reset_foundation_runtime,
    set_foundation_runtime,
)
from arknights_wiki.agent import router as router_mod
from arknights_wiki.eval import judge as judge_mod
from arknights_wiki.eval import metrics as metrics_mod
from arknights_wiki.eval import runner as runner_mod
from arknights_wiki.extraction import llm_client

COMMIT = "d" * 40
PAYLOAD_HASH = "sha256:" + "a" * 64
RUN_ID = "run-spec07-invariance"
MODEL = "deepseek-4-flash"
MESSAGES = [{"role": "user", "content": "hi"}]


def real_deepeval_available() -> bool:
    """是否存在**真实安装**的 deepeval（假模块没有 ``__file__``）。

    与 `test_producer_wiring.py` 的同名helper 保持一致的语义：项目在宿主上没有
    deepeval，打分只在 `deepeval-local` 容器内跑（见 `Dockerfile.deepeval`）。
    """
    module = sys.modules.get("deepeval")
    if module is not None:
        return getattr(module, "__file__", None) is not None
    try:
        return importlib.util.find_spec("deepeval") is not None
    except (ImportError, ValueError):  # pragma: no cover - 极端 sys.modules 状态
        return False


def eval_module_for(stage: str):
    """返回 stage 对应的 eval 模块；scoring 需要真实 deepeval，否则 skip。"""
    if stage == "runner":
        return runner_mod
    if stage == "judge":
        return judge_mod
    if stage == "scoring":
        if not real_deepeval_available():
            pytest.skip(
                "scoring.py 顶层 import deepeval，宿主未安装该包；项目只在 deepeval-local "
                "容器内跑打分（见 Dockerfile.deepeval）。"
            )
        from arknights_wiki.eval import scoring

        return scoring
    raise AssertionError(f"未知 stage：{stage}")


class RecordingSink:
    def __init__(self) -> None:
        self.records: list[EvidenceRecord] = []

    def emit(self, record: EvidenceRecord) -> None:
        self.records.append(record)


class ExplodingSink:
    def __init__(self) -> None:
        self.calls = 0

    def emit(self, record: EvidenceRecord) -> None:
        self.calls += 1
        raise SinkFailure("evidence.sink_write_failed", "injected sink failure")


@pytest.fixture(autouse=True)
def _clean_runtime():
    reset_foundation_runtime()
    yield
    reset_foundation_runtime()


def use_runtime(mode: ContractMode, sink: object | None = None) -> WikiFoundationRuntime:
    runtime = WikiFoundationRuntime(
        sink=sink or RecordingSink(),  # type: ignore[arg-type]
        mode=mode,
        run_id=RUN_ID,
        repository_commit=COMMIT,
        payload_hash=PAYLOAD_HASH,
    )
    set_foundation_runtime(runtime)
    return runtime


def make_response(*, content: str = "hello", with_usage: bool = True) -> SimpleNamespace:
    usage = SimpleNamespace(prompt_tokens=7, completion_tokens=5) if with_usage else None
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))],
        usage=usage,
    )


class _FakeClient:
    def __init__(self, response: SimpleNamespace) -> None:
        self.calls: list[dict] = []
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                return response

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def patch_llm_client(
    monkeypatch: pytest.MonkeyPatch, response: SimpleNamespace, *, langfuse: bool = False
) -> _FakeClient:
    """只替换模块边界；`langfuse=True` 时打开旧遥测分支以便对比其调用参数。"""
    client = _FakeClient(response)
    monkeypatch.setattr(llm_client, "create_client", lambda: client)
    monkeypatch.setattr(
        llm_client,
        "_get_model_config",
        lambda: {"model": MODEL, "max_tokens": 4096, "api_key": "k", "base_url": "http://x"},
    )
    monkeypatch.setattr(observability, "is_enabled", lambda: langfuse)
    monkeypatch.setattr(router_mod, "is_enabled", lambda: langfuse)
    return client


def _strip_latency(recorded: list[tuple[tuple, dict]]) -> list[tuple[tuple, dict]]:
    """去掉每次运行都会变化的 latency_ms，便于逐字段比较。"""
    normalized = []
    for args, kwargs in recorded:
        extra = dict(kwargs.get("extra") or {})
        extra.pop("latency_ms", None)
        normalized.append((args, {**kwargs, "extra": extra}))
    return normalized


def _log_lines(path: Path) -> list[dict]:
    """读取 JSONL 并去掉每次运行都会变化的 timestamp。"""
    entries = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
    ]
    for entry in entries:
        entry.pop("timestamp", None)
    return entries


def _injected_mapping_failure(code: str = "foundation.invalid_usage"):
    """构造一个会抛 MappingFailure 的替身，用于"失败也不变"的用例。"""

    def boom(*args: object, **kwargs: object) -> None:
        raise mapping_mod.MappingFailure(mapping_mod.make_envelope(code, "injected"))

    return boom


# --------------------------------------------------------------------------- #
# chat_completion
# --------------------------------------------------------------------------- #


def test_chat_completion_output_and_request_invariant(monkeypatch: pytest.MonkeyPatch) -> None:
    """off / observe 下 (content, message) 与 provider 请求参数完全一致。"""
    monkeypatch.setattr(observability, "is_enabled", lambda: False)

    use_runtime(ContractMode.OFF)
    client_off = patch_llm_client(monkeypatch, make_response(content="答案"))
    off_content, off_message = llm_client.chat_completion(list(MESSAGES))

    use_runtime(ContractMode.OBSERVE)
    client_obs = patch_llm_client(monkeypatch, make_response(content="答案"))
    obs_content, obs_message = llm_client.chat_completion(list(MESSAGES))

    assert off_content == obs_content == "答案"
    assert off_message.content == obs_message.content
    assert client_off.calls == client_obs.calls  # provider 请求参数一字不差


def test_chat_completion_langfuse_telemetry_invariant(monkeypatch: pytest.MonkeyPatch) -> None:
    """旧 Langfuse 遥测的调用参数在 off / observe 下完全相同（除 latency_ms）。"""
    recorded: list[tuple[tuple, dict]] = []
    patch_llm_client(monkeypatch, make_response(), langfuse=True)
    monkeypatch.setattr(
        observability, "record_llm_usage", lambda *a, **k: recorded.append((a, k))
    )

    use_runtime(ContractMode.OFF)
    llm_client.chat_completion(list(MESSAGES))
    off_calls = _strip_latency(list(recorded))

    recorded.clear()
    use_runtime(ContractMode.OBSERVE)
    llm_client.chat_completion(list(MESSAGES))

    assert off_calls and _strip_latency(recorded) == off_calls


def test_chat_completion_mapping_failure_keeps_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """observe 下 mapping 失败：输出与请求参数仍然不变，且不抛异常。"""
    monkeypatch.setattr(observability, "is_enabled", lambda: False)
    use_runtime(ContractMode.OFF)
    patch_llm_client(monkeypatch, make_response(content="答案"))
    off_content, _ = llm_client.chat_completion(list(MESSAGES))

    use_runtime(ContractMode.OBSERVE)
    monkeypatch.setattr(mapping_mod, "map_observation", _injected_mapping_failure())
    client = patch_llm_client(monkeypatch, make_response(content="答案"))
    obs_content, _ = llm_client.chat_completion(list(MESSAGES))

    assert obs_content == off_content == "答案"
    assert len(client.calls) == 1


def test_chat_completion_sink_failure_keeps_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """observe 下 sink 失败：输出不变、不抛异常、该 run 失效。"""
    monkeypatch.setattr(observability, "is_enabled", lambda: False)
    sink = ExplodingSink()
    runtime = use_runtime(ContractMode.OBSERVE, sink)
    patch_llm_client(monkeypatch, make_response(content="答案"))

    content, _ = llm_client.chat_completion(list(MESSAGES))

    assert content == "答案"
    assert sink.calls == 1
    assert runtime.sink_failure_count == 1
    assert runtime.run_is_valid is False


# --------------------------------------------------------------------------- #
# _llm_intent_rewrite
# --------------------------------------------------------------------------- #


def test_intent_rewrite_return_invariant(monkeypatch: pytest.MonkeyPatch) -> None:
    """off / observe 下返回值（含 None 兜底）与请求参数一致。"""
    use_runtime(ContractMode.OFF)
    client_off = patch_llm_client(monkeypatch, make_response(content="不是 JSON"))
    off_result = router_mod._llm_intent_rewrite("某角色是谁")

    use_runtime(ContractMode.OBSERVE)
    client_obs = patch_llm_client(monkeypatch, make_response(content="不是 JSON"))
    obs_result = router_mod._llm_intent_rewrite("某角色是谁")

    assert off_result == obs_result
    assert client_off.calls == client_obs.calls


def test_intent_rewrite_mapping_failure_keeps_return(monkeypatch: pytest.MonkeyPatch) -> None:
    """observe 下 mapping 失败：返回值仍然不变。"""
    use_runtime(ContractMode.OFF)
    patch_llm_client(monkeypatch, make_response(content="不是 JSON"))
    off_result = router_mod._llm_intent_rewrite("问题")

    use_runtime(ContractMode.OBSERVE)
    monkeypatch.setattr(mapping_mod, "map_observation", _injected_mapping_failure())
    patch_llm_client(monkeypatch, make_response(content="不是 JSON"))
    assert router_mod._llm_intent_rewrite("问题") == off_result


# --------------------------------------------------------------------------- #
# 三个 _log_cost
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("stage", ["runner", "judge", "scoring"])
def test_log_cost_written_bytes_invariant(
    stage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """off / observe 写出的 cost-log 行除 timestamp 外逐字段相同。"""
    module = eval_module_for(stage)
    entry = {"step": stage, "model": MODEL, "tokens_in": 11, "tokens_out": 22, "cost": 0.003}

    use_runtime(ContractMode.OFF)
    off_path = tmp_path / "off.jsonl"
    monkeypatch.setattr(module, "COST_LOG", off_path)
    module._log_cost(dict(entry))

    use_runtime(ContractMode.OBSERVE)
    obs_path = tmp_path / "obs.jsonl"
    monkeypatch.setattr(module, "COST_LOG", obs_path)
    module._log_cost(dict(entry))

    assert _log_lines(off_path) == _log_lines(obs_path)
    assert len(_log_lines(obs_path)) == 1  # append 次数不变


def test_log_cost_mapping_failure_still_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """observe 下 mapping 失败：Legacy 仍然照常写盘。"""
    use_runtime(ContractMode.OBSERVE)
    monkeypatch.setattr(mapping_mod, "map_observation", _injected_mapping_failure())
    target = tmp_path / "cost_log.jsonl"
    monkeypatch.setattr(runner_mod, "COST_LOG", target)

    runner_mod._log_cost({"step": "runner", "model": MODEL, "cost": 0.01})

    assert len(_log_lines(target)) == 1


def test_log_cost_sink_failure_still_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """observe 下 sink 失败：Legacy 仍然照常写盘，不抛异常。"""
    sink = ExplodingSink()
    use_runtime(ContractMode.OBSERVE, sink)
    target = tmp_path / "cost_log.jsonl"
    monkeypatch.setattr(judge_mod, "COST_LOG", target)

    judge_mod._log_cost({"step": "judge", "model": MODEL, "cost": 0.01})

    assert len(_log_lines(target)) == 1
    assert sink.calls == 1


# --------------------------------------------------------------------------- #
# summarize_cost
# --------------------------------------------------------------------------- #


def test_summarize_cost_return_invariant(tmp_path: Path) -> None:
    """off / observe 返回 dict 完全相等（含 malformed 与未知模型路径）。"""
    log = tmp_path / "cost_log.jsonl"
    log.write_text(
        f'{{"step": "judge", "model": "{MODEL}", "cost": 0.01}}\n'
        '{"step": "runner", "model": "no-such-model", "cost": 0.0}\n'
        "{ 坏行\n"
        "\n"
        f'{{"step": "judge", "model": "{MODEL}", "cost": 0.02}}\n',
        encoding="utf-8",
    )

    use_runtime(ContractMode.OFF)
    off_result = metrics_mod.summarize_cost(log)

    use_runtime(ContractMode.OBSERVE)
    obs_result = metrics_mod.summarize_cost(log)

    assert off_result == obs_result
    assert off_result["steps"]["judge"]["count"] == 2


def test_summarize_cost_missing_file_invariant(tmp_path: Path) -> None:
    """缺文件路径的返回值不变。"""
    missing = tmp_path / "nope.jsonl"

    use_runtime(ContractMode.OFF)
    off_result = metrics_mod.summarize_cost(missing)

    use_runtime(ContractMode.OBSERVE)
    obs_result = metrics_mod.summarize_cost(missing)

    assert off_result == obs_result == {"total": 0.0, "steps": {}}


def test_summarize_cost_mapping_failure_keeps_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """observe 下 mapping 失败：返回 dict 仍然不变。"""
    log = tmp_path / "cost_log.jsonl"
    log.write_text('{"step": "judge", "cost": 0.01}\n', encoding="utf-8")

    use_runtime(ContractMode.OFF)
    off_result = metrics_mod.summarize_cost(log)

    use_runtime(ContractMode.OBSERVE)
    monkeypatch.setattr(
        mapping_mod, "map_observation", _injected_mapping_failure("foundation.invalid_cost_summary")
    )
    assert metrics_mod.summarize_cost(log) == off_result
