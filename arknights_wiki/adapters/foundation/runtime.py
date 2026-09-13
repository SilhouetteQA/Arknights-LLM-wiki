"""Wiki Foundation runtime：Contract Mode 策略、证据组装与 sink 注入。

三个模式必须共用**同一** extractor 与 mapping，只有失败策略不同（FND-MODE-002）：

```text
off     解析后立即返回；不提取、不映射、不建 sink（零分配）
observe 提取 → 映射 → 组装 EvidenceRecord → 交给注入的 sink
        任何失败只产出 FAIL 证据；**不改变业务返回值**
strict  完全相同的路径；任何失败先 emit FAIL 证据，再抛 ContractValidationError
```

红线（Spec 05 / 母 Spec §10）：

- sink 失败只计数 + 记日志，**绝不**递归再调同一个 sink
- `evidence.*` 基础设施失败不得被包装成 `ErrorEnvelope`（两者互不继承）
- 不读取项目 extensions 改变语义
- 本模块不含 producer 的 Legacy 计算，也不写任何业务文件

身份绑定（EVD-RUN-002）：

```text
contract_payload_hash  由本模块从已安装的 agent_core 现场复算（Spec 03 的唯一实现）
repository_commit      由调用方注入（构造参数优先，否则 AGENT_CONTRACT_COMMIT）
```

`repository_commit` 是 EvidenceRecord 的**必填**字段，因此它不可用时连 FAIL 证据都无法构造：
此时 observe 把该 run 标记为 invalid（计数 + 结构化日志，业务不受影响），strict 直接失败。
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

from agent_core.contracts.enums.errors import FOUNDATION_INVALID_USAGE
from agent_core.contracts.enums.evidence import (
    EVIDENCE_ARTIFACT_UNAVAILABLE,
    EVIDENCE_SINK_WRITE_FAILED,
    EvidenceRepository,
    ValidationStatus,
)
from agent_core.contracts.enums.modes import (
    ContractMode,
    parse_contract_mode,
    resolve_contract_mode,
)
from agent_core.contracts.models.base import JsonValue
from agent_core.contracts.models.evidence import (
    EvidenceRecord,
    FoundationObservation,
    is_safe_run_id,
    REPOSITORY_COMMIT_PATTERN,
)
from agent_core.contracts.models.error import ErrorEnvelope
from agent_core.contracts.protocols.evidence_sink import EvidenceSink, SinkFailure
from agent_core.contracts.tooling.canonical_json import canonical_file_bundle_digest
from agent_core.contracts.version import CONTRACT_VERSION

from arknights_wiki.adapters.foundation import facts as facts_mod
from arknights_wiki.adapters.foundation import mapping as mapping_mod
from arknights_wiki.adapters.foundation.facts import (
    WikiLegacyCostFacts,
    WikiLegacySummaryFacts,
    WikiLegacyUsageFacts,
)
from arknights_wiki.adapters.foundation.mapping import MappingFailure

#: 注入 repository commit 的环境变量。
CONTRACT_COMMIT_ENV: Final[str] = "AGENT_CONTRACT_COMMIT"

#: mapping stage → producer_id（与 Spec 01 的 producer registry 一致）。
STAGE_PRODUCER: Final[Mapping[str, str]] = {
    "chat_completion": "wiki.agent.llm_usage",
    "intent_rewrite": "wiki.agent.llm_usage",
    "runner": "wiki.eval.cost_log",
    "judge": "wiki.eval.cost_log",
    "scoring": "wiki.eval.cost_log",
    "cost_log_summary": "wiki.eval.cost_summary",
}

logger = logging.getLogger(__name__)


class ContractConfigurationError(ValueError):
    """运行前的配置问题：缺失或非法的 run_id / repository commit。"""


class ContractValidationError(RuntimeError):
    """strict 模式下的契约验证失败。调用方必须令验证命令失败。"""


def producer_for_stage(stage: str) -> str:
    """把 mapping stage 映射为已登记的 producer_id。"""
    try:
        return STAGE_PRODUCER[stage]
    except KeyError as exc:
        raise ContractConfigurationError(
            f"未登记的 mapping stage {stage!r}；已知: {sorted(STAGE_PRODUCER)}"
        ) from exc


def resolve_payload_hash() -> str:
    """从**已安装的** `agent_core` 现场复算 Contract Payload Hash。

    使用 Spec 03 的 canonical file bundle 唯一实现，因此这里的值是可以独立验证的，
    不是调用方声明出来的。
    """
    import agent_core

    package_dir = Path(agent_core.__file__).resolve().parent
    repo_root = package_dir.parent
    payload_hash, _ = canonical_file_bundle_digest(repo_root)
    return payload_hash


def resolve_repository_commit(
    explicit: str | None = None, *, env: Mapping[str, str] | None = None
) -> str | None:
    """解析 repository commit：显式参数优先，否则读环境变量。

    :returns: 40 位小写 hex，或 ``None``（不可用）。
    :raises ContractConfigurationError: 提供了值但不是合法提交号。
    """
    source = os.environ if env is None else env
    raw = explicit if explicit is not None else source.get(CONTRACT_COMMIT_ENV)
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if not REPOSITORY_COMMIT_PATTERN.match(text):
        origin = "构造参数" if explicit is not None else CONTRACT_COMMIT_ENV
        raise ContractConfigurationError(
            f"{origin} 不是 40 位小写 hex 提交号：{text!r}"
        )
    return text


class WikiFoundationRuntime:
    """Wiki 侧的统一旁路入口。

    :param sink: 注入的 :class:`EvidenceSink`；``None`` 表示无人接收证据。
    :param mode: 显式模式；``None`` 时读 ``AGENT_CONTRACT_MODE``。
    :param run_id: 显式 run_id；observe 下缺省生成进程级 UUID，strict 下缺省即失败。
    :param repository_commit: 40 位提交号；``None`` 时读环境变量。
    :param pricing_snapshot: 可注入的 pricing 快照（便于测试）；``None`` 时按需加载。
    """

    def __init__(
        self,
        *,
        sink: EvidenceSink | None = None,
        mode: ContractMode | str | None = None,
        run_id: str | None = None,
        repository_commit: str | None = None,
        repository: EvidenceRepository | str = EvidenceRepository.WIKI,
        contract_version: str = CONTRACT_VERSION,
        pricing_snapshot: facts_mod.WikiPricingSnapshot | None = None,
        payload_hash: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._mode = self._resolve_mode(mode, env)
        self._sink = sink
        self._repository = EvidenceRepository(repository)
        self._contract_version = contract_version
        self._pricing_snapshot = pricing_snapshot
        self._payload_hash = payload_hash
        self._repository_commit = resolve_repository_commit(repository_commit, env=env)
        self._sink_failure_count = 0
        self._run_valid = True
        self._generated_run_id = str(uuid.uuid4())
        self._run_id = self._resolve_run_id(run_id)

    # -- 只读属性 --------------------------------------------------------- #

    @property
    def mode(self) -> ContractMode:
        return self._mode

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def repository_commit(self) -> str | None:
        return self._repository_commit

    @property
    def sink_failure_count(self) -> int:
        """sink 失败与 run 级失效的累计次数。Smoke Gate 要求它为 0。"""
        return self._sink_failure_count

    @property
    def run_is_valid(self) -> bool:
        """该 run 是否仍可作为 Cycle Evidence。"""
        return self._run_valid

    @property
    def payload_hash(self) -> str:
        """Payload Hash；首次访问时现场复算并缓存于实例。"""
        if self._payload_hash is None:
            self._payload_hash = resolve_payload_hash()
        return self._payload_hash

    @property
    def pricing_snapshot(self) -> facts_mod.WikiPricingSnapshot:
        """pricing 快照；首次访问时加载并缓存于**实例**（不跨实例共享）。"""
        if self._pricing_snapshot is None:
            self._pricing_snapshot = facts_mod.WikiPricingSnapshot.load()
        return self._pricing_snapshot

    # -- 窄 helper API（供 Spec 07 的 seam 调用）--------------------------- #

    def observe_chat_completion(
        self,
        response: object | None,
        *,
        stage: str = "chat_completion",
        model: str | None = None,
        cost_amount: float | None = None,
        producer_id: str | None = None,
    ) -> None:
        """观察一次 OpenAI 兼容调用。

        :param response: 原始响应对象（可为 ``None`` 表示调用未发生）。
        :param cost_amount: 调用点已经算出的 Legacy 成本（没有则传 ``None``）。
        """
        if not self._guard():
            return

        def produce() -> tuple[FoundationObservation, Mapping[str, JsonValue]]:
            usage_facts = facts_mod.extract_usage_from_response(response, model=model)
            cost_facts = facts_mod.extract_cost_facts(
                {"cost": cost_amount} if cost_amount is not None else None,
                self.pricing_snapshot,
                model=model,
                call_observed=usage_facts.call_observed,
            )
            observation = mapping_mod.map_observation(
                usage_facts=usage_facts, cost_facts=cost_facts
            )
            return observation, {**_usage_payload(usage_facts), **_cost_payload(cost_facts)}

        self._run(
            producer_id=producer_id or producer_for_stage(stage),
            stage=stage,
            produce=produce,
        )

    def observe_eval_cost_entry(
        self,
        entry: Mapping[str, object],
        *,
        stage: str,
        producer_id: str | None = None,
    ) -> None:
        """观察一次 Eval cost-log 写入（runner / judge / scoring 共用）。"""
        if not self._guard():
            return

        def produce() -> tuple[FoundationObservation, Mapping[str, JsonValue]]:
            is_estimate = bool(entry.get("estimate"))
            usage_facts = facts_mod.extract_usage_from_eval_stats(
                entry, model=_model_of(entry), is_character_estimate=is_estimate
            )
            cost_facts = facts_mod.extract_cost_facts(
                entry, self.pricing_snapshot, call_observed=True
            )
            observation = mapping_mod.map_observation(
                usage_facts=usage_facts, cost_facts=cost_facts
            )
            return observation, {**_usage_payload(usage_facts), **_cost_payload(cost_facts)}

        self._run(
            producer_id=producer_id or producer_for_stage(stage),
            stage=stage,
            produce=produce,
        )

    def observe_summary(
        self, cost_log_path: Path, *, producer_id: str | None = None
    ) -> None:
        """观察一次 Legacy cost 汇总。

        Legacy 继续按旧逻辑跳过 malformed 行；本方法在存在 malformed 记录时产出
        **FAIL** 证据（母 Spec §6.3 / Spec 05 step 8）。
        """
        stage = "cost_log_summary"
        if not self._guard():
            return

        entries, malformed, _ = facts_mod.parse_cost_log(cost_log_path)
        summary_facts = facts_mod.extract_summary_facts(entries, self.pricing_snapshot, malformed_records=malformed)
        payload: dict[str, JsonValue] = {
            "wiki.legacy.component_count": len(summary_facts.components),
            "wiki.legacy.malformed_record_count": summary_facts.malformed_count,
            "wiki.currency.context": facts_mod.CURRENCY_CONTEXT,
        }

        if summary_facts.malformed_count:
            failure = mapping_mod.map_malformed_summary()
            self._emit_failure(
                producer_id=producer_id or producer_for_stage(stage),
                stage=stage,
                envelope=failure.envelope,
                fact_payload=payload,
            )
            return

        def produce() -> tuple[FoundationObservation, Mapping[str, JsonValue]]:
            observation = mapping_mod.map_observation(summary_facts=summary_facts)
            return observation, payload

        self._run(
            producer_id=producer_id or producer_for_stage(stage),
            stage=stage,
            produce=produce,
        )

    # -- 内部 ------------------------------------------------------------- #

    @staticmethod
    def _resolve_mode(
        mode: ContractMode | str | None, env: Mapping[str, str] | None
    ) -> ContractMode:
        if mode is None:
            return resolve_contract_mode(env)
        if isinstance(mode, ContractMode):
            return mode
        return parse_contract_mode(str(mode))

    def _resolve_run_id(self, run_id: str | None) -> str:
        if run_id is None:
            if self._mode is ContractMode.STRICT:
                raise ContractConfigurationError(
                    "strict 模式必须显式提供 run_id（EVD-RUN-001）；"
                    "本地 observe 才会生成进程级 UUID"
                )
            return self._generated_run_id
        if not is_safe_run_id(run_id):
            raise ContractConfigurationError(
                f"run_id 不安全或不合法：{run_id!r}（只允许 [A-Za-z0-9_-]+）"
            )
        return run_id

    def _guard(self) -> bool:
        """模式与身份前置检查；返回 ``False`` 表示本次观察不应继续。"""
        if self._mode is ContractMode.OFF:
            return False
        if self._repository_commit is None:
            self._invalidate_run(
                f"repository commit 不可用（需要构造参数或 {CONTRACT_COMMIT_ENV}）；"
                "EvidenceRecord 的该字段必填，因此本次观察无法产出证据"
            )
            return False
        return True

    def _invalidate_run(self, detail: str) -> None:
        self._sink_failure_count += 1
        self._run_valid = False
        logger.error(
            "foundation run invalidated: %s", detail,
            extra={
                "evidence_code": EVIDENCE_ARTIFACT_UNAVAILABLE,
                "evidence_run_id": self._run_id,
                "evidence_detail": detail,
            },
        )
        if self._mode is ContractMode.STRICT:
            raise ContractValidationError(detail)

    def _run(
        self,
        *,
        producer_id: str,
        stage: str,
        produce: Callable[[], tuple[FoundationObservation, Mapping[str, JsonValue]]],
    ) -> None:
        """执行一次「提取 → 映射 → 发射」；失败按 mode 处理。"""
        try:
            observation, fact_payload = produce()
        except MappingFailure as failure:
            self._emit_failure(
                producer_id=producer_id,
                stage=stage,
                envelope=failure.envelope,
                fact_payload={},
            )
            return
        except Exception as exc:  # noqa: BLE001 - 任何提取失败都要变成 FAIL 证据
            self._emit_failure(
                producer_id=producer_id,
                stage=stage,
                envelope=mapping_mod.make_envelope(
                    FOUNDATION_INVALID_USAGE,
                    f"facts 提取失败：{type(exc).__name__}",
                ),
                fact_payload={},
            )
            return

        self._deliver(
            self._build_record(
                producer_id=producer_id,
                stage=stage,
                status=ValidationStatus.PASS,
                observation=observation,
                envelope=None,
                fact_payload=dict(fact_payload),
            )
        )

    def _emit_failure(
        self,
        *,
        producer_id: str,
        stage: str,
        envelope: ErrorEnvelope,
        fact_payload: Mapping[str, JsonValue],
    ) -> None:
        """产出 FAIL 证据；observe 下静默（业务返回不变），strict 下再抛。"""
        self._deliver(
            self._build_record(
                producer_id=producer_id,
                stage=stage,
                status=ValidationStatus.FAIL,
                observation=None,
                envelope=envelope,
                fact_payload=dict(fact_payload),
            )
        )
        if self._mode is ContractMode.STRICT:
            raise ContractValidationError(f"{envelope.code}: {envelope.message}")

    def _deliver(self, record: EvidenceRecord) -> None:
        """交给 sink。失败只计数，绝不递归、绝不再调 sink。"""
        if self._sink is None:
            self._invalidate_run("未注入 EvidenceSink，证据无接收方")
            return
        try:
            self._sink.emit(record)
        except SinkFailure as exc:
            self._sink_failure_count += 1
            self._run_valid = False
            logger.error(
                "evidence sink rejected a record",
                extra={
                    "evidence_code": exc.code,
                    "evidence_event_id": record.event_id,
                    "evidence_run_id": record.run_id,
                    "evidence_sink_failure_count": self._sink_failure_count,
                },
            )
            if self._mode is ContractMode.STRICT:
                raise ContractValidationError(f"{exc.code}: {exc.message}") from exc
        except Exception as exc:  # noqa: BLE001 - 实现缺陷也不得改变业务返回
            self._sink_failure_count += 1
            self._run_valid = False
            logger.error(
                "evidence sink raised an unexpected error: %s", type(exc).__name__,
                extra={
                    "evidence_code": EVIDENCE_SINK_WRITE_FAILED,
                    "evidence_event_id": record.event_id,
                    "evidence_run_id": record.run_id,
                    "evidence_sink_failure_count": self._sink_failure_count,
                },
            )
            if self._mode is ContractMode.STRICT:
                raise ContractValidationError(
                    f"{EVIDENCE_SINK_WRITE_FAILED}: {type(exc).__name__}"
                ) from exc

    def _build_record(
        self,
        *,
        producer_id: str,
        stage: str,
        status: ValidationStatus,
        observation: FoundationObservation | None,
        envelope: ErrorEnvelope | None,
        fact_payload: Mapping[str, JsonValue],
    ) -> EvidenceRecord:
        return EvidenceRecord(
            event_id=str(uuid.uuid4()),
            run_id=self._run_id,
            repository=self._repository,
            repository_commit=self._repository_commit,
            producer_id=producer_id,
            mapping_stage=stage,
            contract_mode=self._mode,
            contract_version=self._contract_version,
            contract_payload_hash=self.payload_hash,
            timestamp=_utc_now(),
            validation_status=status,
            sanitized_input_facts=dict(fact_payload),
            foundation_output=observation,
            error_envelope=envelope,
        )


def _model_of(entry: Mapping[str, object]) -> str | None:
    raw = entry.get("model")
    return raw if isinstance(raw, str) and raw else None


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _usage_payload(facts: WikiLegacyUsageFacts) -> dict[str, JsonValue]:
    return {
        "wiki.legacy.call_observed": facts.call_observed,
        "wiki.legacy.usage_object_present": facts.usage_object_present,
        "wiki.legacy.field_presence": dict(facts.field_presence),
        "wiki.legacy.is_character_estimate": facts.is_character_estimate,
        "wiki.model.name": facts.model or "unknown",
    }


def _cost_payload(facts: WikiLegacyCostFacts) -> dict[str, JsonValue]:
    return {
        "wiki.pricing.entry_present": facts.price_entry_present,
        "wiki.pricing.value_present": facts.pricing_value_present,
        "wiki.pricing.is_estimate": facts.pricing_is_estimate,
        "wiki.pricing.marker": facts.price_entry_marker,
        "wiki.currency.context": facts.currency_context or facts_mod.CURRENCY_CONTEXT,
        "wiki.legacy.amount_present": facts.legacy_amount is not None,
        "wiki.model.name": facts.model or "unknown",
    }


__all__ = [
    "CONTRACT_COMMIT_ENV",
    "STAGE_PRODUCER",
    "ContractConfigurationError",
    "ContractValidationError",
    "WikiFoundationRuntime",
    "producer_for_stage",
    "resolve_payload_hash",
    "resolve_repository_commit",
]
