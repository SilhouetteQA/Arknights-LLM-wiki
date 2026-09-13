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

关于 deepeval：`arknights_wiki/eval/scoring.py` 顶层 import deepeval，而项目**只在
`deepeval-local` 容器内跑 deepeval**（宿主 pip 装不上，见 `Dockerfile.deepeval` 与
`scripts/docker_setup_deepeval.sh`）。因此这里**不注入假模块顶替**：真实 deepeval 不可用时
该 stage 的用例明确 skip，容器内则真正执行：

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "<wiki worktree>:/work" -w /work \
  --entrypoint sh deepeval-local:latest -c \
  'pip install -q pytest -i https://pypi.tuna.tsinghua.edu.cn/simple; python3 -m pytest tests/contracts -q'
```
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_core.contracts.enums.evidence import ValidationStatus
from agent_core.contracts.enums.modes import ContractMode
from agent_core.contracts.models.evidence import EvidenceRecord

from arknights_wiki import observability
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

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "config" / "contracts" / "producer-registry.json"

COMMIT = "c" * 40
PAYLOAD_HASH = "sha256:" + "f" * 64
RUN_ID = "run-spec07"
MODEL = "deepseek-4-flash"

#: Spec 07 负责的六个 mapping stage 与其应归属的 producer。
WIRED_STAGES = {
    "chat_completion": "wiki.agent.llm_usage",
    "intent_rewrite": "wiki.agent.llm_usage",
    "runner": "wiki.eval.cost_log",
    "judge": "wiki.eval.cost_log",
    "scoring": "wiki.eval.cost_log",
    "cost_log_summary": "wiki.eval.cost_summary",
}


def real_deepeval_available() -> bool:
    """是否存在**真实安装**的 deepeval。

    刻意区分"真实安装"与"测试注入的假模块"：手工构造的 ``types.ModuleType`` 没有
    ``__file__``，而真装的包一定有。项目在宿主上没有 deepeval，打分只在
    ``deepeval-local`` 容器内跑。
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
                "容器内跑打分（见 Dockerfile.deepeval）。容器内命令见本文件模块 docstring。"
            )
        from arknights_wiki.eval import scoring

        return scoring
    raise AssertionError(f"未知 stage：{stage}")


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


def use_runtime(
    mode: ContractMode | str = ContractMode.OBSERVE,
) -> tuple[WikiFoundationRuntime, RecordingSink]:
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


def make_response(
    *,
    content: str = "ok",
    prompt_tokens: int = 7,
    completion_tokens: int = 5,
    with_usage: bool = True,
) -> SimpleNamespace:
    """构造固定 provider 响应；字段名用真实的 prompt_tokens / completion_tokens。"""
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
        lambda: {"model": MODEL, "max_tokens": 4096, "api_key": "k", "base_url": "http://x"},
    )
    # llm_client 在函数内 import is_enabled，因此打在 observability 模块上。
    monkeypatch.setattr(observability, "is_enabled", lambda: False)
    monkeypatch.setattr(router_mod, "is_enabled", lambda: False)
    return client


# --------------------------------------------------------------------------- #
# agent 侧两个 stage
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
    usage = record.foundation_output.usage  # type: ignore[union-attr]
    assert usage.input_tokens == 7
    assert usage.source == "provider_reported"


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


# --------------------------------------------------------------------------- #
# eval 侧四个 stage
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("stage", ["runner", "judge", "scoring"])
def test_log_cost_seams(
    stage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """三个 _log_cost 各自旁路观察，并保持原写入行为。"""
    module = eval_module_for(stage)
    _, sink = use_runtime()
    target = tmp_path / "cost_log.jsonl"
    monkeypatch.setattr(module, "COST_LOG", target)

    module._log_cost(
        {
            "step": stage,
            "model": MODEL,
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


def test_runner_estimate_seam_marks_input_as_not_measured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """runner 的字符估算路径：input 记为未测量（null），output 为估算值。"""
    _, sink = use_runtime()
    monkeypatch.setattr(runner_mod, "COST_LOG", tmp_path / "cost_log.jsonl")

    runner_mod._log_cost(
        {
            "step": "agent_direct:complex",
            "model": MODEL,
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
        f'{{"step": "judge", "model": "{MODEL}", "cost": 0.01}}\n'
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
# off 模式
# --------------------------------------------------------------------------- #


def test_off_mode_runs_no_seam(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """off 模式下五个不依赖 deepeval 的 seam 都不产出证据。"""
    runtime, sink = use_runtime(ContractMode.OFF)
    patch_llm_client(monkeypatch, make_response())
    monkeypatch.setattr(runner_mod, "COST_LOG", tmp_path / "runner.jsonl")
    monkeypatch.setattr(judge_mod, "COST_LOG", tmp_path / "judge.jsonl")

    llm_client.chat_completion([{"role": "user", "content": "hi"}])
    router_mod._llm_intent_rewrite("问题")
    runner_mod._log_cost({"step": "runner", "model": MODEL, "cost": 0.1})
    judge_mod._log_cost({"step": "judge", "model": MODEL, "cost": 0.1})
    metrics_mod.summarize_cost(tmp_path / "missing.jsonl")

    assert sink.records == []
    assert runtime.sink_failure_count == 0
    assert runtime.run_is_valid is True


def test_off_mode_runs_no_seam_for_scoring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """off 模式下 scoring seam 同样不产出证据（需真实 deepeval 才会执行）。"""
    module = eval_module_for("scoring")
    _, sink = use_runtime(ContractMode.OFF)
    monkeypatch.setattr(module, "COST_LOG", tmp_path / "scoring.jsonl")

    module._log_cost({"step": "scoring", "model": MODEL, "cost": 0.1})

    assert sink.records == []
    assert (tmp_path / "scoring.jsonl").exists()  # Legacy 写入照旧


# --------------------------------------------------------------------------- #
# Registry 一致性
# --------------------------------------------------------------------------- #


def test_registry_stages_match_wired_stages() -> None:
    """接线用的 stage 必须与 producer-registry.json 登记的一致。"""
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_producer = {producer["producer_id"]: producer for producer in registry["producers"]}
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
    for path in (REPO_ROOT / "arknights_wiki").rglob("*.py"):
        if "adapters" in path.parts:
            continue
        assert "wiki.trace.summary" not in path.read_text(encoding="utf-8")
