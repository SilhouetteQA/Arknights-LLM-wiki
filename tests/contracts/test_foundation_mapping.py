"""Wiki presence-aware facts / mapping / runtime 的契约测试（Spec 05）。

覆盖 Spec 05 要求的 fixture：

```text
usage absent / provider zero / provider total mismatch / runner estimate
unknown price / estimate price / confirmed-free price / CNY context
malformed summary component / mode invalid value
```

以及验收项：

```text
extractor 不出现 get(..., 0) / or 0 / total reconstruction
estimate=true → source=estimated
price missing/tbd → amount null + source unknown，且保留 CNY 上下文
mapping failure 在 observe 中形成 FAIL Evidence，业务返回不变
project facts 未进入 agent_core.contracts 或 JSON Schema
```

本文件不接任何 producer，也不触碰 Legacy 业务文件。
"""
from __future__ import annotations

import io
import re
import tokenize
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from agent_core.contracts.enums.evidence import ValidationStatus
from agent_core.contracts.enums.modes import ContractMode, ContractModeConfigError
from agent_core.contracts.enums.sources import CostSource, UsageSource
from agent_core.contracts.models.evidence import EvidenceRecord
from agent_core.contracts.protocols.evidence_sink import SinkFailure

from arknights_wiki.adapters.foundation import facts as facts_mod
from arknights_wiki.adapters.foundation import mapping as mapping_mod
from arknights_wiki.adapters.foundation.runtime import (
    ContractConfigurationError,
    ContractValidationError,
    WikiFoundationRuntime,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_DIR = REPO_ROOT / "arknights_wiki" / "adapters" / "foundation"
PAYLOAD_DIR = REPO_ROOT / "agent_core"


def code_only(path: Path) -> str:
    """返回剥掉注释与字符串字面量后的代码文本。

    源码扫描必须跳过 docstring 与注释：规范性文件里会**引用**被禁止的写法
    （例如"禁止 get(..., 0)"），那属于说明而不是违规。只检查真实代码。
    """
    source = path.read_text(encoding="utf-8")
    pieces: list[str] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        if token.type == tokenize.ENDMARKER:
            break
        pieces.append(token.string)
    return " ".join(pieces)


COMMIT = "a" * 40
PAYLOAD_HASH = "sha256:" + "d" * 64
RUN_ID = "run-spec05"

#: 合成价格表：覆盖 estimate / confirmed / free / tbd / per-call / absent 六种状态。
SYNTHETIC_PRICING: Mapping[str, object] = {
    "_note": "测试用价格表；_note 参与快照身份",
    "model-estimate": {"in": 1.0, "out": 2.0, "estimate": True},
    "model-confirmed": {"in": 3.0, "out": 4.0, "estimate": False},
    "model-free": {"in": 0.0, "out": 0.0, "estimate": False},
    "model-tbd": {"in": None, "out": "tbd"},
    "model-per-call": {"in": None, "out": None, "per_call": "tbd"},
}
SNAPSHOT = facts_mod.WikiPricingSnapshot.from_payload(SYNTHETIC_PRICING)


class RecordingSink:
    """口袋 sink：只收集记录。"""

    def __init__(self) -> None:
        self.records: list[EvidenceRecord] = []

    def emit(self, record: EvidenceRecord) -> None:
        self.records.append(record)


class ExplodingSink:
    """总是失败的 sink，用于验证 observe 不受影响。"""

    def __init__(self) -> None:
        self.calls = 0

    def emit(self, record: EvidenceRecord) -> None:
        self.calls += 1
        raise SinkFailure("evidence.sink_write_failed", "injected sink failure")


class _Usage:
    """伪 provider usage 对象（只带被显式设置的字段）。"""

    def __init__(self, **fields: object) -> None:
        for key, value in fields.items():
            setattr(self, key, value)


class _Response:
    def __init__(self, usage: object | None) -> None:
        if usage is not None:
            self.usage = usage


class _ExplodingResponse:
    """读取 ``usage`` 即抛错的响应对象，用于验证提取失败的降级路径。"""

    @property
    def usage(self) -> object:
        raise RuntimeError("injected extraction failure")


def make_runtime(
    sink: object | None = None,
    *,
    mode: ContractMode | str = ContractMode.OBSERVE,
    run_id: str | None = RUN_ID,
    snapshot: facts_mod.WikiPricingSnapshot | None = SNAPSHOT,
    repository_commit: str | None = COMMIT,
    **kwargs: object,
) -> WikiFoundationRuntime:
    return WikiFoundationRuntime(
        sink=sink,  # type: ignore[arg-type]
        mode=mode,
        run_id=run_id,
        repository_commit=repository_commit,
        pricing_snapshot=snapshot,
        payload_hash=PAYLOAD_HASH,
        **kwargs,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- #
# usage facts 与映射
# --------------------------------------------------------------------------- #


def test_usage_absent_maps_to_all_null_unknown() -> None:
    """usage object absent → 全部 null、source=unknown。"""
    usage_facts = facts_mod.extract_usage_from_response(None)
    assert usage_facts.call_observed is False
    assert usage_facts.usage_object_present is False

    usage = mapping_mod.map_usage(usage_facts)
    assert usage.source is UsageSource.UNKNOWN
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens is None


def test_response_without_usage_attribute_is_unknown_not_zero() -> None:
    """调用发生但 provider 未报告 usage：unknown，不是零。"""
    usage_facts = facts_mod.extract_usage_from_response(_Response(None))
    assert usage_facts.call_observed is True
    assert usage_facts.usage_object_present is False

    usage = mapping_mod.map_usage(usage_facts)
    assert usage.source is UsageSource.UNKNOWN
    assert usage.input_tokens is None


def test_explicit_zero_is_preserved_and_distinct_from_unknown() -> None:
    """provider 明确报告 0 与「未知」必须可区分。"""
    facts = facts_mod.extract_usage_from_response(
        _Response(_Usage(input_tokens=0, output_tokens=0, total_tokens=0)),
        model="model-confirmed",
    )
    usage = mapping_mod.map_usage(facts)
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.total_tokens == 0
    assert usage.source is UsageSource.PROVIDER_REPORTED

    unknown = mapping_mod.map_usage(facts_mod.extract_usage_from_response(None))
    assert unknown.total_tokens is None


def test_missing_field_stays_null_while_present_zero_stays_zero() -> None:
    """同一 usage 对象里，缺失字段为 null，显式零为 0。"""
    facts = facts_mod.extract_usage_from_response(
        _Response(_Usage(input_tokens=7, total_tokens=0)), model="model-confirmed"
    )
    assert facts.field_presence == {
        "input_tokens": True,
        "output_tokens": False,
        "total_tokens": True,
        "cache_read_tokens": False,
        "cache_write_tokens": False,
    }
    usage = mapping_mod.map_usage(facts)
    assert usage.input_tokens == 7
    assert usage.output_tokens is None
    assert usage.total_tokens == 0


def test_provider_total_is_preserved_even_when_mismatched() -> None:
    """provider total 与 input+output 不符时原样保留，绝不重算。"""
    facts = facts_mod.extract_usage_from_response(
        _Response(_Usage(prompt_tokens=10, completion_tokens=20, total_tokens=999))
    )
    usage = mapping_mod.map_usage(facts)
    assert usage.total_tokens == 999
    assert usage.total_tokens != 10 + 20


def test_runner_character_estimate_maps_input_to_null() -> None:
    """runner 字符估算：input 记为未测量（null），output 为估算值，total null。"""
    stats = {
        "model": "model-estimate",
        "tokens_in": 0,  # 调用点硬编码的占位，不是测量值
        "tokens_out": 600,
        "cost": 0.0012,
        "estimate": True,
    }
    facts = facts_mod.extract_usage_from_eval_stats(stats, model="model-estimate", is_character_estimate=True)
    assert facts.input_tokens is None
    assert facts.output_tokens == 600
    assert facts.total_tokens is None
    assert facts.field_presence["input_tokens"] is False

    usage = mapping_mod.map_usage(facts)
    assert usage.input_tokens is None
    assert usage.output_tokens == 600
    assert usage.total_tokens is None
    assert usage.source is UsageSource.ESTIMATED


# --------------------------------------------------------------------------- #
# cost 映射
# --------------------------------------------------------------------------- #


def test_estimate_price_maps_to_estimated_source() -> None:
    """estimate=true 的价格项 → source=estimated，并记录快照身份。"""
    facts = facts_mod.extract_cost_facts(
        {"model": "model-estimate", "cost": 0.0012}, SNAPSHOT
    )
    assert facts.price_entry_present is True
    assert facts.pricing_value_present is True
    assert facts.pricing_is_estimate is True

    cost = mapping_mod.map_cost(facts)
    assert cost.source is CostSource.ESTIMATED
    assert str(cost.amount) == "0.0012"
    assert cost.pricing_version == SNAPSHOT.snapshot_hash


def test_confirmed_price_maps_to_price_table() -> None:
    """确认价 → source=price_table，pricing_version 必填。"""
    facts = facts_mod.extract_cost_facts({"model": "model-confirmed", "cost": 0.05}, SNAPSHOT)
    cost = mapping_mod.map_cost(facts)
    assert cost.source is CostSource.PRICE_TABLE
    assert cost.pricing_version == SNAPSHOT.snapshot_hash


def test_confirmed_free_price_is_a_true_zero() -> None:
    """价格项明确写 0 是"真实零"的明确证据（与 missing price 区别对待）。"""
    facts = facts_mod.extract_cost_facts({"model": "model-free", "cost": 0.0}, SNAPSHOT)
    assert facts.pricing_value_present is True
    cost = mapping_mod.map_cost(facts)
    assert cost.source is CostSource.PRICE_TABLE
    assert cost.amount is not None
    assert cost.amount == 0


@pytest.mark.parametrize("model", ["model-tbd", "model-per-call", "model-absent"])
def test_missing_or_tbd_price_maps_to_unknown_and_keeps_currency(model: str) -> None:
    """价格缺失/tbd → amount null、source unknown，并保留 CNY 上下文。"""
    facts = facts_mod.extract_cost_facts({"model": model, "cost": 0.0}, SNAPSHOT)
    assert facts.pricing_value_present is False

    cost = mapping_mod.map_cost(facts)
    assert cost.source is CostSource.UNKNOWN
    assert cost.amount is None
    assert cost.currency == "CNY"


def test_legacy_zero_alone_is_not_evidence_of_true_zero() -> None:
    """只有 legacy amount 0.0（无可用价格项）不足以证明真实零。"""
    facts = facts_mod.extract_cost_facts({"model": "model-absent", "cost": 0.0}, SNAPSHOT)
    assert facts.legacy_amount == 0.0
    cost = mapping_mod.map_cost(facts)
    assert cost.source is CostSource.UNKNOWN
    assert cost.amount is None

    # 对照：同样 0.0，但价格项明确为 0 时才是真实零
    free = mapping_mod.map_cost(
        facts_mod.extract_cost_facts({"model": "model-free", "cost": 0.0}, SNAPSHOT)
    )
    assert free.amount == 0


def test_provider_reported_cost_is_preferred() -> None:
    """provider 明确报告的货币成本 → source=provider_reported。"""
    facts = facts_mod.extract_cost_facts(
        {"model": "model-absent", "cost": 0.25},
        SNAPSHOT,
        provider_reported_cost=True,
        provider_reported_currency="USD",
    )
    cost = mapping_mod.map_cost(facts)
    assert cost.source is CostSource.PROVIDER_REPORTED
    assert cost.currency == "USD"


def test_pricing_snapshot_identity_is_deterministic_and_content_addressed() -> None:
    """快照身份 = 整个 pricing.json 的 canonical JSON SHA256；改内容即改身份。"""
    first = facts_mod.WikiPricingSnapshot.from_payload(SYNTHETIC_PRICING)
    second = facts_mod.WikiPricingSnapshot.from_payload(dict(SYNTHETIC_PRICING))
    assert first.snapshot_hash == second.snapshot_hash
    assert first.snapshot_hash.startswith("sha256:")

    changed = dict(SYNTHETIC_PRICING)
    changed["_note"] = "改了文档键"
    assert facts_mod.WikiPricingSnapshot.from_payload(changed).snapshot_hash != first.snapshot_hash

    reordered = dict(reversed(list(SYNTHETIC_PRICING.items())))
    assert facts_mod.WikiPricingSnapshot.from_payload(reordered).snapshot_hash == first.snapshot_hash


# --------------------------------------------------------------------------- #
# summary 映射
# --------------------------------------------------------------------------- #


def test_summary_is_built_only_from_observed_components() -> None:
    """CostSummary 只由被观察到的组成项构建，legacy total 不参与。"""
    summary_facts = facts_mod.extract_summary_facts(
        [
            {"model": "model-confirmed", "cost": 0.05, "step": "judge"},
            {"model": "model-tbd", "cost": 0.0, "step": "judge"},
        ],
        SNAPSHOT,
        legacy_total=0.05,
    )
    summary = mapping_mod.map_summary(summary_facts)
    assert summary.component_count == 2
    assert summary.known_component_count == 1
    assert summary.unknown_component_count == 1
    assert summary.complete is False


def test_summary_of_all_unknown_has_no_known_amount() -> None:
    """全未知组成项 → known_amount null、complete=false。"""
    summary_facts = facts_mod.extract_summary_facts(
        [{"model": "model-absent", "cost": 0.0}], SNAPSHOT
    )
    summary = mapping_mod.map_summary(summary_facts)
    assert summary.known_component_count == 0
    assert summary.known_amount is None
    assert summary.complete is False


def test_malformed_cost_log_records_are_flagged_not_parsed(tmp_path: Path) -> None:
    """malformed 行被 Legacy 语义跳过，但标识被记录（不含内容）。"""
    log = tmp_path / "cost_log.jsonl"
    log.write_text(
        '{"model": "model-confirmed", "cost": 0.05, "step": "judge"}\n'
        "{ 这行不是 JSON\n"
        "\n"
        '["不是对象"]\n',
        encoding="utf-8",
    )
    entries, malformed, total_lines = facts_mod.parse_cost_log(log)
    assert len(entries) == 1
    assert malformed == ["line:2", "line:4"]
    assert total_lines == 4
    assert all("{" not in item for item in malformed[:-1])


def test_missing_cost_log_yields_empty_summary() -> None:
    """cost log 不存在时与 Legacy 一致：空条目、无 malformed。"""
    entries, malformed, total = facts_mod.parse_cost_log(Path("does-not-exist.jsonl"))
    assert entries == [] and malformed == [] and total == 0


# --------------------------------------------------------------------------- #
# runtime：mode policy
# --------------------------------------------------------------------------- #


def test_off_mode_does_nothing_at_all() -> None:
    """off 模式不提取、不映射、不发射；与未安装 Adapter 等价。"""
    sink = RecordingSink()
    runtime = make_runtime(sink, mode=ContractMode.OFF)
    assert runtime.mode is ContractMode.OFF

    runtime.observe_chat_completion(_Response(_Usage(input_tokens=10)))
    runtime.observe_eval_cost_entry({"model": "model-confirmed", "cost": 0.05}, stage="judge")
    runtime.observe_summary(Path("does-not-exist.jsonl"))

    assert sink.records == []
    assert runtime.sink_failure_count == 0
    assert runtime.run_is_valid is True


def test_invalid_mode_value_fails_configuration() -> None:
    """非法 AGENT_CONTRACT_MODE 必须明确失败，不得静默降级为 off。"""
    with pytest.raises(ContractModeConfigError):
        make_runtime(RecordingSink(), mode="verbose")
    with pytest.raises(ContractModeConfigError):
        make_runtime(RecordingSink(), mode=None, env={"AGENT_CONTRACT_MODE": "on"})
    with pytest.raises(ContractModeConfigError):
        make_runtime(RecordingSink(), mode=None, env={"AGENT_CONTRACT_MODE": "observ"})


def test_mode_defaults_to_off_when_env_absent() -> None:
    """未配置时默认 off（不介入业务）。"""
    runtime = make_runtime(RecordingSink(), mode=None, env={})
    assert runtime.mode is ContractMode.OFF


def test_strict_requires_explicit_run_id() -> None:
    """strict 必须显式提供 run_id（EVD-RUN-001）。"""
    with pytest.raises(ContractConfigurationError):
        make_runtime(RecordingSink(), mode=ContractMode.STRICT, run_id=None)


def test_observe_generates_process_run_id_when_absent() -> None:
    """observe 未提供 run_id 时生成进程级 UUID。"""
    runtime = make_runtime(RecordingSink(), run_id=None)
    assert re.fullmatch(r"[0-9a-f-]{36}", runtime.run_id)


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a:b", "a b", ""])
def test_unsafe_run_id_is_rejected(bad: str) -> None:
    """不安全的 run_id 必须被拒绝。"""
    with pytest.raises(ContractConfigurationError):
        make_runtime(RecordingSink(), run_id=bad)


def test_invalid_repository_commit_is_rejected() -> None:
    """提交号形状非法时明确失败。"""
    with pytest.raises(ContractConfigurationError):
        make_runtime(RecordingSink(), repository_commit="not-a-commit")
    with pytest.raises(ContractConfigurationError):
        make_runtime(RecordingSink(), repository_commit=None, env={"AGENT_CONTRACT_COMMIT": "xyz"})


# --------------------------------------------------------------------------- #
# runtime：证据产出
# --------------------------------------------------------------------------- #


def test_observe_chat_completion_emits_pass_evidence() -> None:
    """一次成功观察产出 PASS 证据，且绑定正确的 producer / stage。"""
    sink = RecordingSink()
    runtime = make_runtime(sink)
    runtime.observe_chat_completion(
        _Response(_Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)),
        model="model-estimate",
        cost_amount=0.02,
    )

    assert len(sink.records) == 1
    record = sink.records[0]
    assert record.validation_status is ValidationStatus.PASS
    assert record.producer_id == "wiki.agent.llm_usage"
    assert record.mapping_stage == "chat_completion"
    assert record.repository == "wiki"
    assert record.repository_commit == COMMIT
    assert record.contract_payload_hash == PAYLOAD_HASH
    assert record.foundation_output is not None
    assert record.foundation_output.usage is not None
    assert record.error_envelope is None
    assert all(key.startswith("wiki.") for key in record.sanitized_input_facts)


def test_observe_eval_cost_entry_stages_map_to_registered_producers() -> None:
    """runner / judge / scoring 三个 stage 都映射到 wiki.eval.cost_log。"""
    sink = RecordingSink()
    runtime = make_runtime(sink)
    for stage in ("runner", "judge", "scoring"):
        runtime.observe_eval_cost_entry(
            {"model": "model-confirmed", "tokens_in": 1, "tokens_out": 2, "cost": 0.01},
            stage=stage,
        )
    assert [record.producer_id for record in sink.records] == ["wiki.eval.cost_log"] * 3
    assert [record.mapping_stage for record in sink.records] == ["runner", "judge", "scoring"]


def test_unknown_stage_is_rejected() -> None:
    """未登记的 stage 明确失败（不静默产出未登记 producer 的证据）。"""
    runtime = make_runtime(RecordingSink())
    with pytest.raises(ContractConfigurationError):
        runtime.observe_eval_cost_entry({"model": "x"}, stage="not-registered")


def test_malformed_summary_emits_fail_evidence(tmp_path: Path) -> None:
    """malformed legacy record → observe 产出 FAIL 证据。"""
    log = tmp_path / "cost_log.jsonl"
    log.write_text('{"model": "model-confirmed", "cost": 0.05}\n{ bad json\n', encoding="utf-8")

    sink = RecordingSink()
    runtime = make_runtime(sink)
    runtime.observe_summary(log)

    assert len(sink.records) == 1
    record = sink.records[0]
    assert record.validation_status is ValidationStatus.FAIL
    assert record.error_envelope is not None
    assert record.error_envelope.code == "foundation.invalid_cost_summary"
    assert record.sanitized_input_facts["wiki.legacy.malformed_record_count"] == 1


def test_clean_summary_emits_pass_with_components(tmp_path: Path) -> None:
    """无 malformed 时产出 PASS 证据，组成项来自被观察到的条目。"""
    log = tmp_path / "cost_log.jsonl"
    log.write_text(
        '{"model": "model-confirmed", "cost": 0.05}\n{"model": "model-absent", "cost": 0.0}\n',
        encoding="utf-8",
    )
    sink = RecordingSink()
    runtime = make_runtime(sink)
    runtime.observe_summary(log)

    assert len(sink.records) == 1
    record = sink.records[0]
    assert record.validation_status is ValidationStatus.PASS
    assert record.producer_id == "wiki.eval.cost_summary"
    assert record.mapping_stage == "cost_log_summary"
    summary = record.foundation_output.cost_summary  # type: ignore[union-attr]
    assert summary.component_count == 2
    assert summary.known_component_count == 1
    assert summary.unknown_component_count == 1


def test_mapping_failure_in_observe_emits_fail_and_leaves_business_result_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mapping 失败在 observe 中形成 FAIL Evidence，模拟业务返回不变。"""
    sink = RecordingSink()
    runtime = make_runtime(sink)

    def boom(*args: object, **kwargs: object) -> None:
        raise mapping_mod.MappingFailure(
            mapping_mod.make_envelope("foundation.invalid_usage", "injected mapping failure")
        )

    monkeypatch.setattr(mapping_mod, "map_observation", boom)

    def simulate_business_call() -> dict[str, str]:
        result = {"answer": "业务返回值"}
        runtime.observe_eval_cost_entry({"model": "model-confirmed", "cost": 0.01}, stage="judge")
        return result

    assert simulate_business_call() == {"answer": "业务返回值"}
    assert len(sink.records) == 1
    assert sink.records[0].validation_status is ValidationStatus.FAIL
    assert sink.records[0].error_envelope is not None


def test_object_without_usage_attribute_is_observed_as_unknown() -> None:
    """响应对象没有 usage 属性 → 观测为「调用发生、usage 缺失」，而不是崩溃或补零。"""
    sink = RecordingSink()
    runtime = make_runtime(sink)
    runtime.observe_chat_completion(object(), model="model-confirmed")

    assert len(sink.records) == 1
    record = sink.records[0]
    assert record.validation_status is ValidationStatus.PASS
    assert record.sanitized_input_facts["wiki.legacy.call_observed"] is True
    assert record.sanitized_input_facts["wiki.legacy.usage_object_present"] is False
    usage = record.foundation_output.usage  # type: ignore[union-attr]
    assert usage.source is UsageSource.UNKNOWN
    assert usage.input_tokens is None


def test_unexpected_extraction_error_becomes_fail_evidence() -> None:
    """提取阶段的意外异常变成 FAIL 证据，不冒出到业务，也不静默丢弃。"""
    sink = RecordingSink()
    runtime = make_runtime(sink)
    runtime.observe_chat_completion(_ExplodingResponse(), model="model-confirmed")

    assert len(sink.records) == 1
    record = sink.records[0]
    assert record.validation_status is ValidationStatus.FAIL
    assert record.error_envelope is not None
    assert record.error_envelope.code == "foundation.invalid_usage"
    assert "injected" not in (record.error_envelope.message or "")  # 不含原始异常文本


# --------------------------------------------------------------------------- #
# runtime：sink 失败语义
# --------------------------------------------------------------------------- #


def test_observe_sink_failure_does_not_change_business_result() -> None:
    """observe 下 sink 失败不改变业务返回；该 run 明确失效。"""
    sink = ExplodingSink()
    runtime = make_runtime(sink)

    def simulate_business_call() -> str:
        runtime.observe_eval_cost_entry({"model": "model-confirmed", "cost": 0.01}, stage="judge")
        return "unchanged"

    assert simulate_business_call() == "unchanged"
    assert sink.calls == 1
    assert runtime.sink_failure_count == 1
    assert runtime.run_is_valid is False


def test_strict_sink_failure_raises() -> None:
    """strict 下 sink 失败必须令验证失败，且不递归重试。"""
    sink = ExplodingSink()
    runtime = make_runtime(sink, mode=ContractMode.STRICT, run_id=RUN_ID)
    with pytest.raises(ContractValidationError):
        runtime.observe_eval_cost_entry({"model": "model-confirmed", "cost": 0.01}, stage="judge")
    assert sink.calls == 1


def test_missing_sink_marks_run_invalid_without_raising_in_observe() -> None:
    """没有注入 sink 时证据无接收方：observe 标记 run 失效，业务不受影响。"""
    runtime = make_runtime(None)
    runtime.observe_eval_cost_entry({"model": "model-confirmed", "cost": 0.01}, stage="judge")
    assert runtime.sink_failure_count == 1
    assert runtime.run_is_valid is False


def test_missing_repository_commit_degrades_in_observe_and_fails_in_strict() -> None:
    """commit 不可用时无法构造合法记录：observe 标记失效，strict 直接失败。"""
    sink = RecordingSink()
    runtime = make_runtime(sink, repository_commit=None, env={})
    runtime.observe_eval_cost_entry({"model": "model-confirmed", "cost": 0.01}, stage="judge")
    assert sink.records == []
    assert runtime.run_is_valid is False
    assert runtime.sink_failure_count == 1

    strict = make_runtime(
        RecordingSink(), mode=ContractMode.STRICT, run_id=RUN_ID, repository_commit=None, env={}
    )
    with pytest.raises(ContractValidationError):
        strict.observe_eval_cost_entry({"model": "model-confirmed", "cost": 0.01}, stage="judge")


# --------------------------------------------------------------------------- #
# 静态与边界验收
# --------------------------------------------------------------------------- #

#: 抹去 presence 的写法；Extractor 内一律禁止。
FORBIDDEN_PRESENCE_PATTERNS: Sequence[tuple[str, str]] = (
    (r"getattr\([^)]*,\s*0\s*\)", "getattr(..., 0)"),
    (r"\.get\([^)]*,\s*0\s*\)", "dict.get(..., 0)"),
    (r"\bor\s+0\b", "or 0"),
)

FORBIDDEN_TOTAL_RECONSTRUCTION: Sequence[tuple[str, str]] = (
    (r"input_tokens\s*\+\s*\w*output_tokens", "input+output 求和"),
    (r"prompt_tokens\s*\+\s*\w*completion_tokens", "prompt+completion 求和"),
)


@pytest.mark.parametrize("pattern,label", FORBIDDEN_PRESENCE_PATTERNS)
def test_facts_extractor_never_erases_presence(pattern: str, label: str) -> None:
    """facts.py 不出现 get(..., 0) / or 0 这类抹去 presence 的写法。"""
    matches = re.findall(pattern, code_only(ADAPTER_DIR / "facts.py"))
    assert not matches, f"facts.py 出现 {label}：{matches}"


@pytest.mark.parametrize("pattern,label", FORBIDDEN_TOTAL_RECONSTRUCTION)
def test_facts_extractor_never_reconstructs_total(pattern: str, label: str) -> None:
    """facts.py 与 mapping.py 不做 input+output 的 total 重建。"""
    for name in ("facts.py", "mapping.py"):
        assert not re.search(pattern, code_only(ADAPTER_DIR / name)), f"{name} 出现 {label}"


def test_project_facts_do_not_enter_shared_payload() -> None:
    """项目 facts 未进入 agent_core 的代码与生成的 Schema/descriptor。

    ``contract.md`` 是规范散文，会**描述**项目 Adapter 应该放在哪里
    （例如 "Wiki：`arknights_wiki/adapters/foundation/`"），这属于说明而非渗漏；
    因此对散文只检查项目内部的 facts 类型名，不检查路径。
    """
    code_needles = ("WikiLegacy", "CodingLegacy", "arknights_wiki", "adapters.foundation")
    prose_needles = ("WikiLegacy", "CodingLegacy")

    for path in sorted(PAYLOAD_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix in {".py", ".json"}:
            text = code_only(path) if path.suffix == ".py" else path.read_text(encoding="utf-8")
            needles = code_needles
        elif path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
            needles = prose_needles
        else:
            continue
        for needle in needles:
            assert needle not in text, f"{path.relative_to(REPO_ROOT)} 出现项目符号 {needle}"


def _declared_property_names(schema: object) -> set[str]:
    """递归收集一份 JSON Schema 里声明的全部属性名。"""
    names: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, Mapping):
            properties = node.get("properties")
            if isinstance(properties, Mapping):
                names.update(str(key) for key in properties)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return names


def test_generated_schemas_carry_no_project_fields() -> None:
    """生成的六类 Schema 属性集合里没有任何项目专有或敏感字段。

    按**解析后的属性名**断言，而不是扫原始文本：共享契约的描述文字里出现
    "legacy" 之类的通用词是正常的，真正的渗漏会表现为项目字段名。
    """
    import json

    schemas_dir = PAYLOAD_DIR / "contracts" / "schemas"
    names = sorted(item.name for item in schemas_dir.glob("*.schema.json"))
    assert names == [
        "cost-summary.schema.json",
        "cost.schema.json",
        "error-envelope.schema.json",
        "evidence-record.schema.json",
        "foundation-observation.schema.json",
        "usage.schema.json",
    ]

    sensitive = {
        "prompt",
        "raw_prompt",
        "response",
        "response_body",
        "reasoning",
        "traceback",
        "api_key",
        "authorization",
    }
    for item in schemas_dir.glob("*.schema.json"):
        declared = _declared_property_names(json.loads(item.read_text(encoding="utf-8")))
        assert declared, f"{item.name} 未声明任何属性"
        offending = {
            name
            for name in declared
            if name.startswith(("wiki.", "coding.")) or name.lower() in sensitive
        }
        assert not offending, f"{item.name} 出现项目/敏感字段 {sorted(offending)}"


def test_evidence_records_satisfy_shared_contract() -> None:
    """产出的记录必须能被共享契约重新校验（防止运行时绕过模型约束）。"""
    sink = RecordingSink()
    runtime = make_runtime(sink)
    runtime.observe_eval_cost_entry(
        {"model": "model-estimate", "tokens_in": 3, "tokens_out": 4, "cost": 0.001},
        stage="judge",
    )
    record = sink.records[0]
    assert EvidenceRecord(**record.model_dump(mode="json")).event_id == record.event_id
