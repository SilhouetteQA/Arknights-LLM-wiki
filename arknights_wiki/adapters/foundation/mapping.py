"""Wiki facts → Foundation Usage / Cost / CostSummary 映射。

母 Spec §8.1 的职责边界：

```text
本模块负责 facts → Foundation DTO，以及把 Pydantic / 聚合失败映射为稳定 ErrorEnvelope
本模块不接管 Legacy compute_cost、summarize_cost 或报告生成
```

映射表逐行对应母 Spec §6.1–§6.3：

```text
usage object absent            → token 全 null，source=unknown
usage 字段明确为 0             → 该字段 0，source=provider_reported
usage 字段缺失                 → 该字段 null
字符估算路径                   → input null、output 估算 N、total null、source=estimated
provider total present/absent  → 精确保留 / null（禁止相加）

price entry absent / tbd       → amount null、source=unknown、保留 CNY 上下文
有效且 estimate=true           → Decimal amount、source=estimated、pricing_version=快照 hash
有效且确认价                   → Decimal amount、source=price_table、pricing_version=快照 hash
provider 明确报告货币成本      → source=provider_reported
只有 legacy amount 0.0         → 不足以证明真实零 → unknown
```

「真实零」只在**存在明确免费证据**时才映射；v0.1 的 Wiki 数据里没有这种证据，
因此所有 ambiguous legacy zero 一律判为 unknown。
"""
from __future__ import annotations

from decimal import Decimal
from typing import Final

from pydantic import ValidationError

from agent_core.contracts.enums.errors import (
    ERROR_CODE_CATEGORY,
    FOUNDATION_CURRENCY_MISMATCH,
    FOUNDATION_INVALID_COST,
    FOUNDATION_INVALID_COST_SUMMARY,
    FOUNDATION_INVALID_USAGE,
)
from agent_core.contracts.enums.sources import CostSource, UsageSource
from agent_core.contracts.models.cost import Cost, CostSummary, CurrencyMismatchError
from agent_core.contracts.models.error import ErrorEnvelope
from agent_core.contracts.models.evidence import FoundationObservation
from agent_core.contracts.models.usage import Usage

from arknights_wiki.adapters.foundation.facts import (
    CURRENCY_CONTEXT,
    WikiLegacyCostFacts,
    WikiLegacySummaryFacts,
    WikiLegacyUsageFacts,
)

#: 仅在存在明确免费证据时使用的真实零来源。
TRUE_ZERO_SOURCE: Final[CostSource] = CostSource.PRICE_TABLE


class MappingFailure(RuntimeError):
    """facts → Foundation 映射失败；携带稳定的 :class:`ErrorEnvelope`。

    Failure 只在**边界**转成 Envelope，内部不建立 `Result[T, ErrorEnvelope]`
    通用返回模式（FND-ERR-001）。
    """

    def __init__(self, envelope: ErrorEnvelope) -> None:
        super().__init__(f"{envelope.code}: {envelope.message}")
        self.envelope = envelope


def make_envelope(code: str, message: str) -> ErrorEnvelope:
    """按错误码的登记分类构造 Envelope。"""
    category = ERROR_CODE_CATEGORY.get(code)
    if category is None:  # pragma: no cover - 仅未登记错误码时触发
        raise ValueError(f"未登记的错误码：{code}")
    return ErrorEnvelope(category=category, code=code, message=message)


# --------------------------------------------------------------------------- #
# Usage
# --------------------------------------------------------------------------- #


def map_usage(facts: WikiLegacyUsageFacts) -> Usage:
    """把 usage facts 映射为 :class:`Usage`。

    ``unknown`` 与「显式零」必须可区分：前者是 ``null``，后者是 ``0``。
    """
    if not facts.call_observed or not facts.usage_object_present:
        return Usage(source=UsageSource.UNKNOWN)

    if facts.is_character_estimate:
        # 按响应字符估算：只有 output 是估算值，input/total 保持未知。
        output = facts.output_tokens
        if output is None:
            return Usage(source=UsageSource.UNKNOWN)
        return Usage(output_tokens=output, source=UsageSource.ESTIMATED)

    if not facts.any_value_present:
        return Usage(source=UsageSource.UNKNOWN)

    try:
        return Usage(
            input_tokens=facts.input_tokens,
            output_tokens=facts.output_tokens,
            total_tokens=facts.total_tokens,
            cache_read_tokens=facts.cache_read_tokens,
            cache_write_tokens=facts.cache_write_tokens,
            source=UsageSource.PROVIDER_REPORTED,
        )
    except ValidationError as exc:
        raise MappingFailure(
            make_envelope(FOUNDATION_INVALID_USAGE, f"usage facts 不满足契约：{_short(exc)}")
        ) from exc


# --------------------------------------------------------------------------- #
# Cost
# --------------------------------------------------------------------------- #


def map_cost(facts: WikiLegacyCostFacts) -> Cost:
    """把 cost facts 映射为 :class:`Cost`。

    ``legacy_amount`` 只有在价格项**存在且可用**时才被采信为金额；
    否则一律 ``amount=null`` + ``source=unknown``，并保留币种上下文。
    """
    currency = facts.provider_reported_currency or facts.currency_context or CURRENCY_CONTEXT

    if facts.provider_reported_cost and facts.legacy_amount is not None:
        return _build_cost(
            facts,
            amount=_decimal(facts.legacy_amount),
            currency=currency,
            source=CostSource.PROVIDER_REPORTED,
            require_pricing_version=False,
        )

    if not facts.price_entry_present or not facts.pricing_value_present:
        # 条目缺失或单价为 null/tbd：未知，不是零。
        return _build_cost(
            facts,
            amount=None,
            currency=currency,
            source=CostSource.UNKNOWN,
            require_pricing_version=False,
        )

    if facts.legacy_amount is None:
        # 价格可用但 Legacy 没有留下金额（例如条目缺 cost 键）：不臆造数值。
        return _build_cost(
            facts,
            amount=None,
            currency=currency,
            source=CostSource.UNKNOWN,
            require_pricing_version=False,
        )

    source = CostSource.ESTIMATED if facts.pricing_is_estimate else CostSource.PRICE_TABLE
    return _build_cost(
        facts,
        amount=_decimal(facts.legacy_amount),
        currency=currency,
        source=source,
        require_pricing_version=True,
    )


def _decimal(value: float) -> Decimal:
    """Legacy float → Decimal：先经 ``str`` 过一遍，禁止二进制误差扩散。"""
    return Decimal(str(value))


def _build_cost(
    facts: WikiLegacyCostFacts,
    *,
    amount: Decimal | None,
    currency: str | None,
    source: CostSource,
    require_pricing_version: bool,
) -> Cost:
    # 币种上下文在 amount 为 null 时同样保留（Master §6.2 "保留币种上下文"）。
    pricing_version = (
        facts.pricing_snapshot_hash if (require_pricing_version or amount is not None) else None
    )
    try:
        return Cost(
            amount=amount,
            currency=currency,
            source=source,
            pricing_version=pricing_version,
        )
    except ValidationError as exc:
        raise MappingFailure(
            make_envelope(FOUNDATION_INVALID_COST, f"cost facts 不满足契约：{_short(exc)}")
        ) from exc


# --------------------------------------------------------------------------- #
# CostSummary
# --------------------------------------------------------------------------- #


def map_summary(facts: WikiLegacySummaryFacts) -> CostSummary:
    """由被观察到的组成项构建 :class:`CostSummary`。

    绝不接受 legacy total 作为参数 —— 从结构上堵死「从 legacy total 反推组成项」
    （FND-CSUM-011）。
    """
    costs: list[Cost] = []
    for component in facts.components:
        costs.append(map_cost(component))

    try:
        summary = CostSummary.from_costs(costs)
    except CurrencyMismatchError as exc:
        raise MappingFailure(
            make_envelope(FOUNDATION_CURRENCY_MISMATCH, f"聚合范围内币种不一致：{exc}")
        ) from exc
    except ValidationError as exc:
        raise MappingFailure(
            make_envelope(
                FOUNDATION_INVALID_COST_SUMMARY, f"summary 不满足契约：{_short(exc)}"
            )
        ) from exc
    return summary


def map_malformed_summary() -> MappingFailure:
    """malformed legacy record 对应的失败：Legacy 可继续跳过，但证据必须是 FAIL。"""
    return MappingFailure(
        make_envelope(
            FOUNDATION_INVALID_COST_SUMMARY,
            "cost log 存在无法按 Legacy 语义解析的记录；Legacy 汇总继续跳过，"
            "但该观察记录判为 FAIL",
        )
    )


# --------------------------------------------------------------------------- #
# Observation
# --------------------------------------------------------------------------- #


def map_observation(
    usage_facts: WikiLegacyUsageFacts | None = None,
    cost_facts: WikiLegacyCostFacts | None = None,
    summary_facts: WikiLegacySummaryFacts | None = None,
) -> FoundationObservation:
    """把可用的 facts 组合成 :class:`FoundationObservation`（至少一项）。"""
    usage = map_usage(usage_facts) if usage_facts is not None else None
    cost = map_cost(cost_facts) if cost_facts is not None else None
    summary = map_summary(summary_facts) if summary_facts is not None else None

    try:
        return FoundationObservation(usage=usage, cost=cost, cost_summary=summary)
    except ValidationError as exc:
        raise MappingFailure(
            make_envelope(FOUNDATION_INVALID_USAGE, f"observation 为空：{_short(exc)}")
        ) from exc


def _short(exc: Exception, limit: int = 240) -> str:
    """把校验错误压成有界字符串（ErrorEnvelope 要求细节有界且已净化）。"""
    text = " ".join(str(exc).split())
    return text[:limit]


__all__ = [
    "TRUE_ZERO_SOURCE",
    "MappingFailure",
    "make_envelope",
    "map_usage",
    "map_cost",
    "map_summary",
    "map_malformed_summary",
    "map_observation",
]
