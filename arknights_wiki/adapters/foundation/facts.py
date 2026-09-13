"""Wiki presence-aware facts 提取。

母 Spec §6 的总原则：

```text
Foundation mapping = value + presence + provenance + pricing evidence
Legacy normalized value ≠ Foundation fact
```

本模块只做**提取与保留**，不做映射（映射在 :mod:`.mapping`）、不构造公共 Pydantic 对象、
不写文件、不调用 Langfuse。Extractor 的输入是"已经解包好的原始对象"——OpenAI 兼容响应对象、
Eval 结果 dict、cost-log entry dict、pricing 快照——因此本模块**不 import 任何业务模块**，
也没有任何副作用。

硬约束（母 Spec §6 / Spec 05 验收项）：

```text
禁止 getattr(obj, name, 0) / dict.get(name, 0) / ... or 0 抹去 presence
禁止把 provider total 与 input+output 求和
禁止从 legacy total 反推组成项
```

`pricing.json` 的快照身份：对整个文件做 canonical JSON（sorted keys、compact、UTF-8、无 BOM）
后取 SHA256。不使用 mtime、`repr(dict)` 或 Git 时间戳。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from agent_core.contracts.models.base import canonical_json_dumps

#: Wiki 的成本记账货币（Eval cost log、report、Dashboard 均为人民币）。
CURRENCY_CONTEXT: Final[str] = "CNY"

#: 价格表文件名与位置（相对 `arknights_wiki/`）。
PRICING_FILENAME: Final[str] = "pricing.json"

#: 价格表中的文档键；按 Master §6.2 的口径它**参与**快照身份。
PRICING_NOTE_KEY: Final[str] = "_note"

#: 价格表里表示"未知单价"的字面量。
PRICING_UNKNOWN_VALUES: Final[frozenset[object]] = frozenset({"tbd"})

#: 参与占位统计的 provider usage 字段。
USAGE_FIELDS: Final[tuple[str, ...]] = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
)

#: 价格表条目中的结构化键。
_PRICE_IN: Final[str] = "in"
_PRICE_OUT: Final[str] = "out"
_PRICE_ESTIMATE: Final[str] = "estimate"
_PRICE_PER_CALL: Final[str] = "per_call"


def default_pricing_path() -> Path:
    """返回 `arknights_wiki/eval/pricing.json` 的路径。"""
    return Path(__file__).resolve().parents[2] / "eval" / PRICING_FILENAME


def _sha256_hex(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _as_int(value: object) -> int | None:
    """把 provider 报的计数转成 int；无法转就返回 ``None``（未知），**不补零**。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _price_value_usable(value: object) -> bool:
    """价格表里的一个单价是否可用（存在、非 None、非 tbd）。"""
    if value is None:
        return False
    if isinstance(value, str) and value.strip().lower() in PRICING_UNKNOWN_VALUES:
        return False
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# --------------------------------------------------------------------------- #
# pricing 快照
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WikiPricingSnapshot:
    """`pricing.json` 的不可变快照与稳定身份。

    快照身份 = 整个文件 canonical JSON 的 SHA256，用作 Foundation ``pricing_version``。
    """

    entries: Mapping[str, Mapping[str, object]]
    snapshot_hash: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> WikiPricingSnapshot:
        """从已解析的 JSON 载荷构造快照。"""
        entries = {
            key: value for key, value in payload.items() if isinstance(value, Mapping)
        }
        return cls(entries=entries, snapshot_hash=_sha256_hex(canonical_json_dumps(payload).encode("utf-8")))

    @classmethod
    def load(cls, path: Path | None = None) -> WikiPricingSnapshot:
        """从磁盘加载并计算快照身份。"""
        target = path if path is not None else default_pricing_path()
        payload = json.loads(Path(target).read_text(encoding="utf-8"))
        return cls.from_payload(payload)

    # -- 存在性查询（全部返回 bool / None，不返回补零后的值）-------------- #

    def entry(self, model: str | None) -> Mapping[str, object] | None:
        """返回价格表条目；不存在返回 ``None``。"""
        if not model:
            return None
        value = self.entries.get(model)
        return value if isinstance(value, Mapping) else None

    def entry_present(self, model: str | None) -> bool:
        """价格表中是否存在该模型的条目。"""
        return self.entry(model) is not None

    def has_usable_value(self, model: str | None) -> bool:
        """条目是否存在**且** in/out 单价均可用（非 None / 非 tbd）。"""
        entry = self.entry(model)
        if entry is None:
            return False
        return _price_value_usable(entry.get(_PRICE_IN)) and _price_value_usable(
            entry.get(_PRICE_OUT)
        )

    def is_estimate(self, model: str | None) -> bool:
        """条目是否被标记为估算价。"""
        entry = self.entry(model)
        return bool(entry.get(_PRICE_ESTIMATE)) if entry is not None else False

    def is_per_call(self, model: str | None) -> bool:
        """条目是否为按次计价（如 Firecrawl），此类没有 token 单价。"""
        entry = self.entry(model)
        return entry is not None and entry.get(_PRICE_PER_CALL) is not None

    def entry_marker(self, model: str | None) -> str:
        """人类可读的条目状态，用于 facts 诊断（不含任何敏感内容）。"""
        if not self.entry_present(model):
            return "absent"
        if self.is_per_call(model):
            return "per_call"
        if not self.has_usable_value(model):
            return "tbd"
        return "estimate" if self.is_estimate(model) else "confirmed"


# --------------------------------------------------------------------------- #
# usage facts
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WikiLegacyUsageFacts:
    """一次调用可观察到的 usage 事实（含 presence 与 provenance）。"""

    call_observed: bool
    usage_object_present: bool
    field_presence: Mapping[str, bool] = field(default_factory=dict)
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    is_character_estimate: bool = False
    model: str | None = None

    @property
    def any_value_present(self) -> bool:
        """是否存在任一被 provider 明确报告的计数。"""
        return any(
            value is not None
            for value in (
                self.input_tokens,
                self.output_tokens,
                self.total_tokens,
                self.cache_read_tokens,
                self.cache_write_tokens,
            )
        )


def extract_usage_from_response(
    response: object | None, *, model: str | None = None
) -> WikiLegacyUsageFacts:
    """从 OpenAI 兼容响应对象提取 usage facts。

    ``response`` 为 ``None`` 表示调用未发生（或未拿到响应）。
    ``usage`` 属性缺失/为 ``None`` 表示 provider 未报告 usage —— 这是"未知"，
    不是"零"。
    """
    if response is None:
        return WikiLegacyUsageFacts(
            call_observed=False,
            usage_object_present=False,
            field_presence={},
            model=model,
        )

    usage = getattr(response, "usage", None)
    if usage is None:
        return WikiLegacyUsageFacts(
            call_observed=True,
            usage_object_present=False,
            field_presence={},
            model=model,
        )

    presence: dict[str, bool] = {}
    values: dict[str, int | None] = {}
    for field_name in USAGE_FIELDS:
        raw = getattr(usage, field_name, None)
        values[field_name] = _as_int(raw)
        presence[field_name] = raw is not None

    return WikiLegacyUsageFacts(
        call_observed=True,
        usage_object_present=True,
        field_presence=presence,
        input_tokens=values["input_tokens"],
        output_tokens=values["output_tokens"],
        total_tokens=values["total_tokens"],
        cache_read_tokens=values["cache_read_tokens"],
        cache_write_tokens=values["cache_write_tokens"],
        model=model,
    )


def extract_usage_from_eval_stats(
    stats: Mapping[str, object] | None,
    *,
    model: str | None = None,
    is_character_estimate: bool = False,
) -> WikiLegacyUsageFacts:
    """从 Eval（runner / judge / scoring）的 stats dict 提取 usage facts。

    ``stats`` 的键形如 ``tokens_in`` / ``tokens_out``；缺键即"未测量"。

    ``is_character_estimate=True`` 时（runner 的按字符估算路径），``tokens_in`` 的
    数值是调用点硬编码的占位 ``0`` 而非测量结果 —— 按母 Spec §6.1
    "input null，output 为估算 N"，它被记作**未测量**。
    """
    if stats is None:
        return WikiLegacyUsageFacts(
            call_observed=False,
            usage_object_present=False,
            is_character_estimate=is_character_estimate,
            model=model,
        )

    def present(key: str) -> bool:
        if is_character_estimate and key == "tokens_in":
            return False
        return key in stats and stats[key] is not None

    input_value = _as_int(stats.get("tokens_in")) if present("tokens_in") else None
    output_value = _as_int(stats.get("tokens_out")) if present("tokens_out") else None

    return WikiLegacyUsageFacts(
        call_observed=True,
        usage_object_present=True,
        field_presence={
            "input_tokens": input_value is not None,
            "output_tokens": output_value is not None,
            "total_tokens": False,
        },
        input_tokens=input_value,
        output_tokens=output_value,
        total_tokens=None,
        is_character_estimate=is_character_estimate,
        model=model,
    )


# --------------------------------------------------------------------------- #
# cost facts
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WikiLegacyCostFacts:
    """一条 cost 事实（含价格项存在性、估算标记与币种上下文）。"""

    call_observed: bool
    model: str | None = None
    price_entry_present: bool = False
    pricing_value_present: bool = False
    price_entry_complete: bool = False
    pricing_is_estimate: bool = False
    per_call_pricing: bool = False
    price_entry_marker: str = "absent"
    legacy_amount: float | None = None
    legacy_amount_is_estimate: bool = False
    currency_context: str | None = CURRENCY_CONTEXT
    pricing_snapshot_hash: str | None = None
    provider_reported_cost: bool = False
    provider_reported_currency: str | None = None


def extract_cost_facts(
    entry: Mapping[str, object] | None,
    snapshot: WikiPricingSnapshot | None,
    *,
    model: str | None = None,
    call_observed: bool = True,
    provider_reported_cost: bool = False,
    provider_reported_currency: str | None = None,
) -> WikiLegacyCostFacts:
    """从一条 Legacy cost entry 提取 presence-aware cost facts。

    ``entry`` 的 ``cost`` 键是 **Legacy 计算后的数值**（未知单价时为 `0.0`）——
    它只作为 ``legacy_amount`` 保留，**不足以**证明真实零成本。
    """
    resolved_model = model
    if resolved_model is None and entry is not None:
        raw_model = entry.get("model")
        resolved_model = raw_model if isinstance(raw_model, str) and raw_model else None

    legacy_amount: float | None = None
    legacy_amount_is_estimate = False
    if entry is not None:
        raw_amount = entry.get("cost")
        if isinstance(raw_amount, (int, float)) and not isinstance(raw_amount, bool):
            legacy_amount = float(raw_amount)
        legacy_amount_is_estimate = bool(entry.get("estimate"))

    entry_present = snapshot.entry_present(resolved_model) if snapshot else False
    value_present = snapshot.has_usable_value(resolved_model) if snapshot else False

    return WikiLegacyCostFacts(
        call_observed=call_observed,
        model=resolved_model,
        price_entry_present=entry_present,
        pricing_value_present=value_present,
        price_entry_complete=value_present,
        pricing_is_estimate=snapshot.is_estimate(resolved_model) if snapshot else False,
        per_call_pricing=snapshot.is_per_call(resolved_model) if snapshot else False,
        price_entry_marker=snapshot.entry_marker(resolved_model) if snapshot else "unknown",
        legacy_amount=legacy_amount,
        legacy_amount_is_estimate=legacy_amount_is_estimate,
        pricing_snapshot_hash=snapshot.snapshot_hash if snapshot else None,
        provider_reported_cost=provider_reported_cost,
        provider_reported_currency=provider_reported_currency,
    )


# --------------------------------------------------------------------------- #
# summary facts
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WikiLegacySummaryFacts:
    """Legacy `summarize_cost` 的组成项与 malformed 记录。"""

    components: Sequence[WikiLegacyCostFacts] = ()
    malformed_records: Sequence[str] = ()
    legacy_total: float | None = None
    currency_context: str | None = CURRENCY_CONTEXT

    @property
    def malformed_count(self) -> int:
        return len(self.malformed_records)


def extract_summary_facts(
    entries: Sequence[Mapping[str, object]],
    snapshot: WikiPricingSnapshot | None,
    *,
    malformed_records: Sequence[str] = (),
    legacy_total: float | None = None,
) -> WikiLegacySummaryFacts:
    """从 cost-log 条目序列构造 summary facts。

    ``legacy_total`` 只被**记录**，绝不参与组成项推导（FND-CSUM-011）。
    """
    components = tuple(
        extract_cost_facts(entry, snapshot) for entry in entries
    )
    return WikiLegacySummaryFacts(
        components=components,
        malformed_records=tuple(malformed_records),
        legacy_total=legacy_total,
    )


def parse_cost_log(cost_log_path: Path) -> tuple[list[Mapping[str, object]], list[str], int]:
    """按 Legacy 语义解析 cost-log，但**分开保留**坏行标识。

    Legacy `summarize_cost` 会静默跳过 JSON 解析失败的行；这里继续跳过以免
    改变既有汇总结果，但把坏行标识（`line:<n>`，不含任何内容）交还调用方，
    使 observe 能产出 FAIL 证据。

    :returns: ``(条目列表, malformed 标识列表, 总行数)``
    """
    target = Path(cost_log_path)
    if not target.exists():
        return [], [], 0

    entries: list[Mapping[str, object]] = []
    malformed: list[str] = []
    lines = target.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            malformed.append(f"line:{index}")
            continue
        if not isinstance(parsed, Mapping):
            malformed.append(f"line:{index}")
            continue
        entries.append(parsed)
    return entries, malformed, len(lines)


__all__ = [
    "CURRENCY_CONTEXT",
    "PRICING_FILENAME",
    "PRICING_NOTE_KEY",
    "PRICING_UNKNOWN_VALUES",
    "USAGE_FIELDS",
    "WikiPricingSnapshot",
    "WikiLegacyUsageFacts",
    "WikiLegacyCostFacts",
    "WikiLegacySummaryFacts",
    "default_pricing_path",
    "extract_usage_from_response",
    "extract_usage_from_eval_stats",
    "extract_cost_facts",
    "extract_summary_facts",
    "parse_cost_log",
]
