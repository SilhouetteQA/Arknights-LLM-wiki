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
import subprocess
import uuid
from collections.abc import Callable, Mapping, Sequence
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


def _repo_root() -> Path:
    """返回 Wiki 仓库根（`arknights_wiki` 的父目录）。"""
    import arknights_wiki

    return Path(arknights_wiki.__file__).resolve().parent.parent


_commit_probed: bool = False
_detected_commit: str | None = None


def detect_repository_commit() -> str | None:
    """**只读**地探测当前工作区的 HEAD 提交号；失败返回 ``None``。

    只在显式参数与 ``AGENT_CONTRACT_COMMIT`` 都不可用时才作为兜底调用；
    结果在进程内缓存，因此最多执行一次。绝不写仓库、绝不抛错 ——
    探测失败只会让该 run 无法产出证据（observe 记日志，strict 失败）。
    """
    global _commit_probed, _detected_commit
    if _commit_probed:
        return _detected_commit
    _commit_probed = True

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("无法探测 repository commit：%s", type(exc).__name__)
        return None

    candidate = completed.stdout.strip()
    if completed.returncode == 0 and REPOSITORY_COMMIT_PATTERN.match(candidate):
        _detected_commit = candidate
    else:
        logger.warning(
            "git rev-parse HEAD 未返回合法提交号（rc=%s）", completed.returncode
        )
    return _detected_commit


def reset_repository_commit_probe() -> None:
    """清空提交号探测缓存；仅供测试使用。"""
    global _commit_probed, _detected_commit
    _commit_probed = False
    _detected_commit = None


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
    def accepts_observation(self) -> bool:
        """是否处于会真正观察的模式（非 ``off``）。

        producer seam 用它做**最外层**短路：``off`` 下连 facts 提取都不发生
        （包括不去触发 pricing 加载这类惰性副作用）。
        """
        return self._mode is not ContractMode.OFF

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
        """观察一次 Legacy cost 汇总（自行读取 cost log）。

        便捷入口；接线路径应优先使用 :meth:`observe_summary_entries`，
        以便与 Legacy 共用**同一次**逐行读取（Master §8.5）。
        """
        entries, malformed, _ = facts_mod.parse_cost_log(cost_log_path)
        self.observe_summary_entries(entries, malformed, producer_id=producer_id)

    def observe_summary_entries(
        self,
        entries: Sequence[Mapping[str, object]],
        malformed_records: Sequence[str] = (),
        *,
        stage: str = "cost_log_summary",
        legacy_total: float | None = None,
        producer_id: str | None = None,
    ) -> None:
        """用**已解析**的 cost-log 条目观察一次 Legacy 汇总。

        Legacy 继续按旧逻辑跳过 malformed 行；本方法在存在 malformed 记录时产出
        **FAIL** 证据（母 Spec §6.3 / Spec 05 step 8），且绝不改变 Legacy 返回值。
        ``legacy_total`` 只被记录，**不参与**组成项推导（FND-CSUM-011）。
        """
        if not self._guard():
            return

        malformed_count = len(tuple(malformed_records))
        resolved_producer = producer_id or producer_for_stage(stage)

        if malformed_count:
            # 先判 malformed：Legacy 继续跳过，证据侧必须是 FAIL，且**不改** Legacy 返回值。
            failure = mapping_mod.map_malformed_summary()
            self._emit_failure(
                producer_id=resolved_producer,
                stage=stage,
                envelope=failure.envelope,
                fact_payload={
                    "wiki.legacy.component_count": len(tuple(entries)),
                    "wiki.legacy.malformed_record_count": malformed_count,
                    "wiki.currency.context": facts_mod.CURRENCY_CONTEXT,
                },
            )
            return

        def produce() -> tuple[FoundationObservation, Mapping[str, JsonValue]]:
            # 提取放在 produce 内：任何失败都会变成 FAIL 证据，绝不冒出到业务函数。
            summary_facts = facts_mod.extract_summary_facts(
                entries,
                self.pricing_snapshot,
                malformed_records=malformed_records,
                legacy_total=legacy_total,
            )
            payload: dict[str, JsonValue] = {
                "wiki.legacy.component_count": len(summary_facts.components),
                "wiki.legacy.malformed_record_count": summary_facts.malformed_count,
                "wiki.currency.context": facts_mod.CURRENCY_CONTEXT,
            }
            return mapping_mod.map_observation(summary_facts=summary_facts), payload

        self._run(producer_id=resolved_producer, stage=stage, produce=produce)

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

        self._emit(
            producer_id=producer_id,
            stage=stage,
            status=ValidationStatus.PASS,
            observation=observation,
            envelope=None,
            fact_payload=fact_payload,
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
        self._emit(
            producer_id=producer_id,
            stage=stage,
            status=ValidationStatus.FAIL,
            observation=None,
            envelope=envelope,
            fact_payload=fact_payload,
        )
        if self._mode is ContractMode.STRICT:
            raise ContractValidationError(f"{envelope.code}: {envelope.message}")

    def _emit(
        self,
        *,
        producer_id: str,
        stage: str,
        status: ValidationStatus,
        observation: FoundationObservation | None,
        envelope: ErrorEnvelope | None,
        fact_payload: Mapping[str, JsonValue],
    ) -> None:
        """构造并投递一条记录。

        证据**构造**本身也可能失败（容量、字段形状等），而 seam 位于业务函数内部 ——
        因此这里必须兜住，让 observe 的承诺（业务返回不变）成立：
        构造失败只令该 run 失效（strict 下仍会明确失败）。
        """
        try:
            record = self._build_record(
                producer_id=producer_id,
                stage=stage,
                status=status,
                observation=observation,
                envelope=envelope,
                fact_payload=dict(fact_payload),
            )
        except Exception as exc:  # noqa: BLE001 - 构造失败不得冒出到业务
            self._invalidate_run(f"无法构造证据记录：{type(exc).__name__}")
            return
        self._deliver(record)

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


# --------------------------------------------------------------------------- #
# 进程级 runtime 访问器（producer seam 的唯一入口）
# --------------------------------------------------------------------------- #

#: run_id 的环境变量（受控 smoke / replay / strict 必须显式提供）。
CONTRACT_RUN_ID_ENV: Final[str] = "AGENT_CONTRACT_RUN_ID"

_active_runtime: WikiFoundationRuntime | None = None


def _build_runtime_from_env() -> WikiFoundationRuntime:
    """按环境构造进程级 runtime。

    任何环境配置问题都**不得**影响业务：非法 commit / run_id 只降级为"该 run 不可用"
    （observe 记日志并继续，strict 由 runtime 自身明确失败）。
    """
    from arknights_wiki.adapters.foundation.evidence_sink import FileEvidenceSink

    mode = resolve_contract_mode()
    if mode is ContractMode.OFF:
        # off：不构造 sink、不读 payload/pricing，六个 producer 的调用都会立即返回。
        return WikiFoundationRuntime(mode=ContractMode.OFF)

    try:
        commit = resolve_repository_commit(None, env=os.environ)
    except ContractConfigurationError as exc:
        logger.error(
            "忽略非法的 %s：%s", CONTRACT_COMMIT_ENV, exc,
            extra={"evidence_code": EVIDENCE_ARTIFACT_UNAVAILABLE},
        )
        commit = None
    if commit is None:
        commit = detect_repository_commit()

    raw_run_id = os.environ.get(CONTRACT_RUN_ID_ENV, "").strip()
    run_id = raw_run_id if raw_run_id and is_safe_run_id(raw_run_id) else None
    if raw_run_id and run_id is None:
        logger.error(
            "忽略不安全的 %s：%r", CONTRACT_RUN_ID_ENV, raw_run_id,
            extra={"evidence_code": "evidence.invalid_run_id"},
        )

    return WikiFoundationRuntime(
        sink=FileEvidenceSink(),
        mode=mode,
        run_id=run_id,
        repository_commit=commit,
    )


def get_foundation_runtime() -> WikiFoundationRuntime:
    """返回进程级 runtime（首次调用时按环境构造并缓存）。

    这是六个 producer seam 的唯一入口。``off`` 下只构造一个无 sink 的轻量对象，
    之后每次调用都只是一次属性访问。
    """
    global _active_runtime
    if _active_runtime is None:
        _active_runtime = _build_runtime_from_env()
    return _active_runtime


def observe_eval_cost_entry(entry: Mapping[str, object], *, stage: str) -> None:
    """producer seam 的窄 helper：观察一次 Eval cost-log 写入（Master §8.4）。

    runner / judge / scoring 三个 `_log_cost` 共用它。只做
    「白名单 entry → facts → mapping → emit」，不写文件、不改 entry。
    """
    get_foundation_runtime().observe_eval_cost_entry(entry, stage=stage)


def observe_summary_entries(
    entries: Sequence[Mapping[str, object]],
    malformed_records: Sequence[str] = (),
    *,
    stage: str = "cost_log_summary",
    legacy_total: float | None = None,
) -> None:
    """producer seam 的窄 helper：用**已解析**条目观察一次 Legacy 汇总（Master §8.5）。

    与 Legacy 共用同一次逐行读取；只读取入参，不重新读文件。
    """
    get_foundation_runtime().observe_summary_entries(
        entries, malformed_records, stage=stage, legacy_total=legacy_total
    )


def set_foundation_runtime(runtime: WikiFoundationRuntime) -> None:
    """注入自定义 runtime；供测试与受控运行（如 Spec 13 的 smoke harness）使用。"""
    global _active_runtime
    _active_runtime = runtime


def reset_foundation_runtime() -> None:
    """清空进程级 runtime 缓存；仅供测试使用。"""
    global _active_runtime
    _active_runtime = None


__all__ = [
    "CONTRACT_COMMIT_ENV",
    "CONTRACT_RUN_ID_ENV",
    "STAGE_PRODUCER",
    "ContractConfigurationError",
    "ContractValidationError",
    "WikiFoundationRuntime",
    "detect_repository_commit",
    "get_foundation_runtime",
    "observe_eval_cost_entry",
    "observe_summary_entries",
    "producer_for_stage",
    "reset_foundation_runtime",
    "reset_repository_commit_probe",
    "resolve_payload_hash",
    "resolve_repository_commit",
    "set_foundation_runtime",
]
