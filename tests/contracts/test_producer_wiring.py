"""Wiki producer seam 接线测试（Spec 07）。

每个 `(producer_id, mapping_stage)` 至少一次 **fixed-response** 接线测试：

```text
wiki.agent.llm_usage / chat_completion
wiki.agent.llm_usage / intent_rewrite
wiki.eval.cost_log  / runner | judge | scoring
wiki.eval.cost_summary / cost_log_summary
```

测试只 monkeypatch **模块边界**（`create_client` / `_get_model_config` / `COST_LOG`），
不 monkeypatch 业务内部私有函数。`wiki.trace.summary` 必须仍为 DEFERRED 且无虚构事件。
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

# ---- 注入 fake deepeval：宿主未安装 deepeval 时 scoring.py 仍可导入 ----
# 与 tests/eval/test_scoring.py 同一手法，只保留 scoring 顶层 import 需要的符号。
if "deepeval" not in sys.modules:
    _fake_metrics = types.ModuleType("deepeval.metrics")

    class _FakeMetric:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.score = 0.7
            self.reason = "fake reason"

        def measure(self, tc):
            pass

    _fake_metrics.FaithfulnessMetric = _FakeMetric
    _fake_metrics.GEval = _FakeMetric
    _fake_metrics.HallucinationMetric = _FakeMetric

    _fake_g_eval = types.ModuleType("deepeval.metrics.g_eval.utils")
    _fake_g_eval.SingleTurnParams = SimpleNamespace(
        ACTUAL_OUTPUT="actual_output",
        EXPECTED_OUTPUT="expected_output",
        RETRIEVAL_CONTEXT="retrieval_context",
    )
    _fake_models = types.ModuleType("deepeval.models")
    _fake_models.DeepEvalBaseLLM = object
    _fake_test_case = types.ModuleType("deepeval.test_case")

    class _FakeLLMTestCase:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    _fake_test_case.LLMTestCase = _FakeLLMTestCase
    _fake_telemetry = types.ModuleType("deepeval.telemetry")
    _fake_telemetry.telemetry_opt_out = True

    _fake_deepeval = types.ModuleType("deepeval")
    _fake_deepeval.metrics = _fake_metrics
    _fake_deepeval.models = _fake_models
    _fake_deepeval.test_case = _fake_test_case

    sys.modules.setdefault("deepeval", _fake_deepeval)
    sys.modules.setdefault("deepeval.metrics", _fake_metrics)
    sys.modules.setdefault("deepeval.metrics.g_eval.utils", _fake_g_eval)
    sys.modules.setdefault("deepeval.models", _fake_models)
    sys.modules.setdefault("deepeval.test_case", _fake_test_case)
    sys.modules.setdefault("deepeval.telemetry", _fake_telemetry)

from agent_core.contracts.enums.evidence import ValidationStatus  # noqa: E402
from agent_core.contracts.enums.modes import ContractMode  # noqa: E402
from agent_core.contracts.models.evidence import EvidenceRecord  # noqa: E402

from arknights_wiki.adapters.foundation.runtime import (  # noqa: E402
    WikiFoundationRuntime,
    reset_foundation_runtime,
    set_foundation_runtime,
)
from arknights_wiki.extraction import llm_client  # noqa: E402

from arknights_wiki import observability  # noqa: E402
from arknights_wiki.eval import judge as judge_mod  # noqa: E402
from arknights_wiki.eval import metrics as metrics_mod  # noqa: E402
from arknights_wiki.eval import runner as runner_mod  # noqa: E402
from arknights_wiki.eval import scoring as scoring_mod  # noqa: E402
from arknights_wiki.agent import router as router_mod  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "config" / "contracts" / "producer-registry.json"

COMMIT = "c" * 40
PAYLOAD_HASH = "sha256:" + "f" * 64
RUN_ID = "run-spec07"

#: Spec 07 负责的六个 mapping stage 与其应归属的 producer。
WIRED_STAGES = {
    "chat_completion": "wiki.agent.llm_usage",
    "intent_rewrite": "wiki.agent.llm_usage",
    "runner": "wiki.eval.cost_log",
    "judge": "wiki.eval.cost_log",
    "scoring": "wiki.eval.cost_log",
    "cost_log_summary": "wiki.eval.cost_summary",
}


class RecordingSink:
    """口袋 sink：只收集记录，不落盘。"""

    def __init__(self) -> None:
        self.records: list[EvidenceRecord] = []

    def emit(self, record: EvidenceRecord) -> None:
        self.records.append(record)


@pytest.fixture(autouse=True)
def _clean_runtime():
    """每个测试用注入的 runtime，结束后清空进程级缓存。"""
    reset_foundation_runtime()
    yield
    reset_foundation_runtime()


def use_runtime(mode: ContractMode | str = ContractMode.OBSERVE) -> tuple[WikiFoundationRuntime, RecordingSink]:
    """注入一个指向口袋 sink 的 runtime，并返回它。"""
    sink = RecordingSink()
    runtime = WikiFoundationRuntime(
        sink=sink,
        mode=mode,
        run_id=RUN_ID,
        repository_commit=COMMIT,
        payload_hash=PAYLOAD_HASH,
    )
    set_foundation_runtime(runtime)
    return runtime, sink


# --------------------------------------------------------------------------- #
# 固定响应与假 client
# --------------------------------------------------------------------------- #


def make_response(
    *, content: str = "ok", prompt_tokens: int = 7, completion_tokens: int = 5,
    with_usage: bool = True,
) -> SimpleNamespace:
    usage = (
        SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        if with_usage
        else None
    )
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


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


def patch_llm_client(monkeypatch: pytest.MonkeyPatch, response: SimpleNamespace) -> _FakeClient:
    """只替换模块边界：client 工厂、模型配置与 Langfuse 开关。"""
    client = _FakeClient(response)
    monkeypatch.setattr(llm_client, "create_client", lambda: client)
    monkeypatch.setattr(
        llm_client,
        "_get_model_config",
        lambda: {"model": "deepseek-4-flash", "max_tokens": 4096, "api_key": "k", "base_url": "http://x"},
    )
    # llm_client 在函数内 import is_enabled，因此打在 observability 模块上。
    monkeypatch.setattr(observability, "is_enabled", lambda: False)
    monkeypatch.setattr(router_mod, "is_enabled", lambda: False)
    return client


# --------------------------------------------------------------------------- #
# 六个 stage 的接线
# --------------------------------------------------------------------------- #


def test_chat_completion_seam(monkeypatch: pytest.MonkeyPatch) -> None:
    """chat_completion 成功响应后旁路观察，stage=chat_completion。"""
    _, sink = use_runtime()
    patch_llm_client(monkeypatch, make_response(content="hello"))

    content, _message = llm_client.chat_completion([{"role": "user", "content": "hi"}])

    assert content == "hello"
    assert len(sink.records) == 1
    record = sink.records[0]
    assert record.producer_id == "wiki.agent.llm_usage"
    assert record.mapping_stage == "chat_completion"
    assert record.validation_status is ValidationStatus.PASS
    assert record.foundation_output.usage.input_tokens == 7  # type: ignore[union-attr]
    assert record.foundation_output.usage.source == "provider_reported"  # type: ignore[union-attr]


def test_chat_completion_seam_without_usage_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """provider 未报告 usage：仍产出证据，但不是"零"。"""
    _, sink = use_runtime()
    patch_llm_client(monkeypatch, make_response(with_usage=False))

    llm_client.chat_completion([{"role": "user", "content": "hi"}])

    record = sink.records[0]
    usage = record.foundation_output.usage  # type: ignore[union-attr]
    assert usage.input_tokens is None
    assert usage.source == "unknown"
    cost = record.foundation_output.cost  # type: ignore[union-attr]
    assert cost.amount is None and cost.source == "unknown"


def test_intent_rewrite_seam(monkeypatch: pytest.MonkeyPatch) -> None:
    """_llm_intent_rewrite 成功响应后旁路观察，stage=intent_rewrite。"""
    _, sink = use_runtime()
    patch_llm_client(monkeypatch, make_response(content="不是 JSON，触发本地兜底"))

    result = router_mod._llm_intent_rewrite("某角色是谁")

    assert result is None  # 旧 fallback 控制流不变
    assert len(sink.records) == 1
    record = sink.records[0]
    assert record.producer_id == "wiki.agent.llm_usage"
    assert record.mapping_stage == "intent_rewrite"


@pytest.mark.parametrize(
    "module,stage",
    [(runner_mod, "runner"), (judge_mod, "judge"), (scoring_mod, "scoring")],
)
def test_log_cost_seams(
    module: object, stage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """三个 _log_cost 各自旁路观察，并保持原写入行为。"""
    _, sink = use_runtime()
    target = tmp_path / "cost_log.jsonl"
    monkeypatch.setattr(module, "COST_LOG", target)  # type: ignore[attr-defined]

    module._log_cost(  # type: ignore[attr-defined]
        {
            "step": stage,
            "model": "deepseek-4-flash",
            "tokens_in": 11,
            "tokens_out": 22,
            "cost": 0.003,
        }
    )

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["step"] == stage
    assert len(sink.records) == 1
    record = sink.records[0]
    assert record.producer_id == "wiki.eval.cost_log"
    assert record.mapping_stage == stage
    assert record.foundation_output.cost.source == "estimated"  # type: ignore[union-attr]


def test_runner_estimate_seam_marks_input_as_not_measured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """runner 的字符估算路径：input 记为未测量（null），output 为估算值。"""
    _, sink = use_runtime()
    monkeypatch.setattr(runner_mod, "COST_LOG", tmp_path / "cost_log.jsonl")

    runner_mod._log_cost(
        {
            "step": "agent_direct:complex",
            "model": "deepseek-4-flash",
            "tokens_in": 0,  # 调用点硬编码的占位
            "tokens_out": 600,
            "cost": 0.0012,
            "estimate": True,
        }
    )

    usage = sink.records[0].foundation_output.usage  # type: ignore[union-attr]
    assert usage.input_tokens is None
    assert usage.output_tokens == 600
    assert usage.total_tokens is None
    assert usage.source == "estimated"


def test_summary_seam(tmp_path: Path) -> None:
    """summarize_cost 在同一次读取后旁路产出 CostSummary 证据。"""
    _, sink = use_runtime()
    log = tmp_path / "cost_log.jsonl"
    log.write_text(
        '{"step": "judge", "model": "deepseek-4-flash", "cost": 0.01}\n'
        '{"step": "judge", "model": "no-such-model", "cost": 0.0}\n',
        encoding="utf-8",
    )

    result = metrics_mod.summarize_cost(log)

    assert result["total"] == 0.01
    assert result["steps"]["judge"]["count"] == 2
    assert len(sink.records) == 1
    record = sink.records[0]
    assert record.producer_id == "wiki.eval.cost_summary"
    assert record.mapping_stage == "cost_log_summary"
    summary = record.foundation_output.cost_summary  # type: ignore[union-attr]
    assert summary.component_count == 2
    assert summary.known_component_count == 1
    assert summary.unknown_component_count == 1
    assert summary.complete is False


def test_summary_seam_flags_malformed_lines(tmp_path: Path) -> None:
    """malformed 行对 Legacy 继续跳过，但证据侧必须是 FAIL。"""
    _, sink = use_runtime()
    log = tmp_path / "cost_log.jsonl"
    log.write_text('{"step": "judge", "cost": 0.01}\n{ 坏行\n', encoding="utf-8")

    result = metrics_mod.summarize_cost(log)

    assert result["total"] == 0.01  # Legacy 结果不变
    record = sink.records[0]
    assert record.validation_status is ValidationStatus.FAIL
    assert record.error_envelope is not None
    assert record.error_envelope.code == "foundation.invalid_cost_summary"
    assert record.sanitized_input_facts["wiki.legacy.malformed_record_count"] == 1


def test_summary_seam_on_missing_file(tmp_path: Path) -> None:
    """缺文件：Legacy 返回空摘要，证据侧也照实记录（0 组成项）。"""
    _, sink = use_runtime()

    result = metrics_mod.summarize_cost(tmp_path / "missing.jsonl")

    assert result == {"total": 0.0, "steps": {}}
    assert len(sink.records) == 1
    summary = sink.records[0].foundation_output.cost_summary  # type: ignore[union-attr]
    assert summary.component_count == 0
    assert summary.complete is True


# --------------------------------------------------------------------------- #
# off 模式与 Registry 一致性
# --------------------------------------------------------------------------- #


def test_off_mode_runs_no_seam(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """off 模式下六个 seam 全部不产出证据、不写 staging。"""
    _, sink = use_runtime(ContractMode.OFF)
    patch_llm_client(monkeypatch, make_response())
    for module in (runner_mod, judge_mod, scoring_mod):
        monkeypatch.setattr(module, "COST_LOG", tmp_path / f"{module.__name__}.jsonl")

    llm_client.chat_completion([{"role": "user", "content": "hi"}])
    router_mod._llm_intent_rewrite("问题")
    runner_mod._log_cost({"step": "runner", "model": "m", "cost": 0.1})
    judge_mod._log_cost({"step": "judge", "model": "m", "cost": 0.1})
    scoring_mod._log_cost({"step": "scoring", "model": "m", "cost": 0.1})
    metrics_mod.summarize_cost(tmp_path / "missing.jsonl")

    assert sink.records == []


def test_registry_stages_match_wired_stages() -> None:
    """接线用的 stage 必须与 producer-registry.json 登记的一致。"""
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_producer = {
        producer["producer_id"]: producer for producer in registry["producers"]
    }
    for stage, producer_id in WIRED_STAGES.items():
        assert producer_id in by_producer, f"未登记的 producer：{producer_id}"
        producer = by_producer[producer_id]
        assert producer["status"] == "IN_SCOPE"
        assert stage in producer["mapping_stages"], f"{stage} 不在 {producer_id} 的 stage 列表"


def test_trace_summary_stays_deferred_and_unwired() -> None:
    """wiki.trace.summary 仍为 DEFERRED，且没有被本步骤接线。"""
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_producer = {p["producer_id"]: p for p in registry["producers"]}
    trace = by_producer["wiki.trace.summary"]
    assert trace["status"] == "DEFERRED"

    for stage in trace["mapping_stages"]:
        assert stage not in WIRED_STAGES
    source = (REPO_ROOT / "arknights_wiki").rglob("*.py")
    assert not any(
        "wiki.trace.summary" in path.read_text(encoding="utf-8")
        for path in source
        if "adapters" not in path.parts
    )
