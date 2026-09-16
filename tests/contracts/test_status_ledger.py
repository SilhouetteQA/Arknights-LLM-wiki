"""Spec 10 交付物测试 —— 状态账本 reducer（Appendix I / Spec10:78-79）。

覆盖 Spec 10 §79 要求的 8 类用例，每类至少一个测试：
duplicate ID / missing prerequisite / ``READY→COMPLETE`` 跳跃 /
mutually exclusive successors / correction / self-reference /
pending suffix hash 与 append 一致性 / Candidate 隔离。

另外覆盖：空账本 genesis（GOV-STAT-002，01 READY、02–18 NOT_STARTED，可复现）、
真实账本端到端归约、以及 DAG/Authority 常量与 ``00-execution-index.md`` §3 表格
的逐项一致性。

治理规则 ID 只写在 docstring 里：``GOV-STAT-*`` / ``GOV-FRZ-*`` 不属于
``agent_core.contracts`` Payload，不在 ``RULE_REGISTRY`` 中，因此**不**使用
``@contract_rule`` 装饰器（避免制造"已登记 payload 规则"的假象）。

所有账本 fixture 都建在 ``tmp_path`` 下；真实账本只读。
"""
from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "contracts" / "status_ledger.py"
SPEC_DIR = REPO_ROOT / "docs" / "specs" / "foundation-contract"
INDEX_PATH = SPEC_DIR / "00-execution-index.md"
REAL_LEDGER = SPEC_DIR / "execution-status-events.jsonl"

if str(REPO_ROOT) not in sys.path:  # pytest 下 CWD 通常在 sys.path 里，这里显式兜底
    sys.path.insert(0, str(REPO_ROOT))


def _load_status_ledger() -> Any:
    """按文件路径加载被测脚本（``scripts/`` 不是包，不能按包路径 import）。"""
    spec = importlib.util.spec_from_file_location("status_ledger_under_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass 需要 ``cls.__module__`` 能在 sys.modules 里解析，故先注册再执行。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sl = _load_status_ledger()

COMMIT_A = "a" * 40
COMMIT_B = "b" * 40
EVIDENCE = ("contract-tests:fixture-validation",)

#: 与 18 个子 Spec 头部一致的 genesis（Spec 01 的 genesis 是 READY，不是 NOT_STARTED）。
DEFAULT_GENESIS: Mapping[str, str] = {
    spec_id: ("READY" if spec_id == "01" else "NOT_STARTED") for spec_id in sl.SPEC_IDS
}

_TIMESTAMPS = itertools.count(1)


def _next_timestamp() -> str:
    index = next(_TIMESTAMPS)
    return f"2026-09-14T14:{index // 60:02d}:{index % 60:02d}Z"


# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #


def _event(
    spec_id: str,
    from_status: str,
    to_status: str,
    reason_code: str,
    *,
    candidate_commit: str | None = None,
    evidence_refs: Iterable[str] = (),
    references: Iterable[str] = (),
    event_id: str | None = None,
    reason: str = "fixture event",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """构造一条合法的 10 字段事件（调用方可覆盖任意字段）。"""
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "spec_id": spec_id,
        "from_status": from_status,
        "to_status": to_status,
        "candidate_commit": candidate_commit,
        "evidence_refs": list(evidence_refs),
        "timestamp": timestamp or _next_timestamp(),
        "reason_code": reason_code,
        "reason": reason,
        "references": list(references),
    }


def _chain(
    spec_id: str,
    *,
    candidate: str | None = None,
    complete_reason: str = "ACCEPTANCE_COMPLETE",
) -> list[dict[str, Any]]:
    """从该 spec 的 genesis 走完主路径 ``READY → IN_PROGRESS → VALIDATED → COMPLETE``。

    Spec 01 的 genesis 是 ``READY``（GOV-STAT-002），因此它只有 3 条事件；
    其余 spec 从 ``NOT_STARTED`` 起步，有 4 条。
    """
    events: list[dict[str, Any]] = []
    if DEFAULT_GENESIS[spec_id] == "NOT_STARTED":
        events.append(_event(spec_id, "NOT_STARTED", "READY", "PREREQUISITES_SATISFIED"))
    events.extend(
        [
            _event(spec_id, "READY", "IN_PROGRESS", "EXECUTION_STARTED"),
            _event(
                spec_id,
                "IN_PROGRESS",
                "VALIDATED",
                "VALIDATION_PASSED",
                evidence_refs=EVIDENCE,
            ),
            _event(
                spec_id,
                "VALIDATED",
                "COMPLETE",
                complete_reason,
                evidence_refs=EVIDENCE,
                candidate_commit=candidate,
            ),
        ]
    )
    return events


def _jsonl(events: Sequence[Mapping[str, Any]]) -> bytes:
    """事件列表 → canonical JSONL 字节（按键名排序，LF 结尾）。"""
    return b"".join(
        sl.canonical_json_dumps(dict(event)).encode("utf-8") + b"\n" for event in events
    )


def _topo_order(spec_ids: Iterable[str]) -> list[str]:
    """按脚本内 DAG 常量给出一个合法的完成顺序（fixture 用）。"""
    order: list[str] = []
    remaining = list(spec_ids)
    while remaining:
        for spec_id in sorted(remaining):
            if all(prereq in order for prereq in sl.DAG[spec_id].prerequisites):
                order.append(spec_id)
                remaining.remove(spec_id)
                break
        else:  # pragma: no cover - fixture 自身错误
            raise AssertionError(f"DAG fixture has a cycle: {remaining}")
    return order


def _completed_ledger(
    spec_ids: Iterable[str],
    *,
    freeze_spec: str | None = None,
    freeze_candidate: str = COMMIT_B,
) -> bytes:
    """给定 spec 全部走完主路径的 canonical ledger。"""
    events: list[dict[str, Any]] = []
    for spec_id in _topo_order(spec_ids):
        if spec_id == freeze_spec:
            events.extend(
                _chain(spec_id, candidate=freeze_candidate, complete_reason="CANDIDATE_FROZEN")
            )
        else:
            events.extend(_chain(spec_id))
    return _jsonl(events)


def _write_genesis(directory: Path, statuses: Mapping[str, str] | None = None) -> Path:
    """写 18 个子 Spec fixture（头部含 ``> Initial Status：`X```）。"""
    overrides = dict(statuses or {})
    directory.mkdir(parents=True, exist_ok=True)
    for spec_id in sl.SPEC_IDS:
        status = overrides.get(spec_id, DEFAULT_GENESIS[spec_id])
        (directory / f"{spec_id}-fixture.md").write_text(
            f"# Spec {spec_id} fixture\n\n"
            f"> Spec ID：`{spec_id}`  \n"
            f"> Initial Status：`{status}`  \n",
            encoding="utf-8",
        )
    return directory


@pytest.fixture()
def spec_dir(tmp_path: Path) -> Path:
    return _write_genesis(tmp_path / "specs")


def _pending_files(
    suffix_events: Sequence[Mapping[str, Any]],
    *,
    candidate: str = COMMIT_A,
    boundary: str = "candidate_a",
    suffix_hash: str | None = None,
    event_count: int | None = None,
    envelope_overrides: Mapping[str, Any] | None = None,
) -> tuple[bytes, bytes]:
    """构造 (pending.jsonl 字节, pending.json envelope 字节)。"""
    pending_bytes = _jsonl(suffix_events)
    envelope: dict[str, Any] = {
        "pending_version": "1",
        "target_boundary": boundary,
        "candidate_commit": candidate,
        "event_count": (
            event_count
            if event_count is not None
            else sl.count_nonempty_lines(pending_bytes, "pending-jsonl")
        ),
        "suffix_hash": suffix_hash or sl.compute_suffix_hash(pending_bytes),
    }
    envelope.update(dict(envelope_overrides or {}))
    return pending_bytes, sl.canonical_json_dumps(envelope).encode("utf-8")


def _reduce(
    ledger_bytes: bytes,
    spec_dir: Path,
    *,
    pending: tuple[bytes, bytes] | None = None,
    self_commit: str | None = None,
    index_path: Path | None = None,
) -> Any:
    return sl.reduce_ledger_bytes(
        ledger_bytes,
        spec_dir=spec_dir,
        index_path=index_path,
        pending_jsonl_bytes=pending[0] if pending else None,
        pending_envelope_bytes=pending[1] if pending else None,
        self_commit=self_commit,
    )


def _conflict_rule(excinfo: pytest.ExceptionInfo[Any]) -> str:
    error = excinfo.value
    assert isinstance(error, sl.LedgerConflict)
    return error.rule


# --------------------------------------------------------------------------- #
# 1. Event Schema（rule 1）
# --------------------------------------------------------------------------- #


class TestEventSchema:
    """rule 1：严格 UTF-8 + 每行独立 canonical JSON object + 10 字段 schema。"""

    def test_unknown_field_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-001：Event Schema 之外的字段 → SPEC_STATUS_CONFLICT。"""
        event = _event("01", "READY", "IN_PROGRESS", "EXECUTION_STARTED")
        event["persistence_boundary"] = "candidate_a"
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl([event]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_1_EVENT_SCHEMA
        assert "unknown field" in str(excinfo.value)

    def test_missing_field_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-001：缺字段 → SPEC_STATUS_CONFLICT。"""
        event = _event("01", "READY", "IN_PROGRESS", "EXECUTION_STARTED")
        del event["references"]
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl([event]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_1_EVENT_SCHEMA
        assert "missing required field" in str(excinfo.value)

    def test_non_canonical_json_line_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-001：键未排序 / 含多余空格的 JSON 行 → SPEC_STATUS_CONFLICT。"""
        event = _event("01", "READY", "IN_PROGRESS", "EXECUTION_STARTED")
        line = json.dumps(event).encode("utf-8")  # 插入序 + 默认分隔符 = 非 canonical
        assert line.decode("utf-8") != sl.canonical_json_dumps(event)
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(line + b"\n", spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_1_EVENT_SCHEMA
        assert "canonical JSON" in str(excinfo.value)

    def test_bad_reason_code_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-001：reason_code 必须是 14 值闭集之一。"""
        event = _event("01", "READY", "IN_PROGRESS", "NOT_A_REASON")
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl([event]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_1_EVENT_SCHEMA

    def test_error_carries_line_number_event_id_and_rule(self, spec_dir: Path) -> None:
        """rule 8：错误信息必须给出 行号 + event_id + 违规规则（禁止静默忽略）。"""
        good = _event("01", "READY", "IN_PROGRESS", "EXECUTION_STARTED")
        bad = _event("01", "IN_PROGRESS", "VALIDATED", "VALIDATION_PASSED")
        bad["reason_code"] = "NOPE"
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl([good, bad]), spec_dir)
        message = str(excinfo.value)
        assert "execution-status-events.jsonl:2" in message
        assert bad["event_id"] in message
        assert sl.RULE_1_EVENT_SCHEMA in message


# --------------------------------------------------------------------------- #
# 2. duplicate ID（rule 2）
# --------------------------------------------------------------------------- #


class TestDuplicateEventId:
    """rule 2：event_id 全局唯一（含大小写归一），事件按文件顺序归约。"""

    def test_duplicate_event_id_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-001：重复 event_id → SPEC_STATUS_CONFLICT。"""
        first = _event("01", "READY", "IN_PROGRESS", "EXECUTION_STARTED")
        second = _event(
            "01",
            "IN_PROGRESS",
            "VALIDATED",
            "VALIDATION_PASSED",
            evidence_refs=EVIDENCE,
            event_id=first["event_id"],
        )
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl([first, second]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_2_DUPLICATE_EVENT_ID

    def test_duplicate_event_id_is_case_insensitive(self, spec_dir: Path) -> None:
        """GOV-STAT-001：UUID 的两种大小写拼写是同一个 event_id。"""
        identifier = "cbc001a0-a9c3-4fff-b7cb-b36db677555f"
        first = _event(
            "01", "READY", "IN_PROGRESS", "EXECUTION_STARTED", event_id=identifier
        )
        second = _event(
            "01",
            "IN_PROGRESS",
            "VALIDATED",
            "VALIDATION_PASSED",
            evidence_refs=EVIDENCE,
            event_id=identifier.upper(),
        )
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl([first, second]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_2_DUPLICATE_EVENT_ID


# --------------------------------------------------------------------------- #
# 3. missing prerequisite（rule 6）
# --------------------------------------------------------------------------- #


class TestMissingPrerequisite:
    """rule 6：进入 READY 时 DAG 前置必须已 COMPLETE；支持 ``02–08`` 区间展开。"""

    def test_ready_without_completed_prerequisite_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-003：Spec 02 在 Spec 01 未 COMPLETE 时进入 READY → 冲突。"""
        event = _event("02", "NOT_STARTED", "READY", "PREREQUISITES_SATISFIED")
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl([event]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_6_MISSING_PREREQUISITE
        assert "01=READY" in str(excinfo.value)

    def test_ready_after_prerequisites_complete_is_accepted(self, spec_dir: Path) -> None:
        """GOV-STAT-003：Spec 01 COMPLETE 后 Spec 02 可进入 READY（正例）。"""
        ledger = _jsonl(_chain("01") + [_event("02", "NOT_STARTED", "READY", "PREREQUISITES_SATISFIED")])
        report = _reduce(ledger, spec_dir)
        assert report.statuses["02"] == "READY"

    def test_en_dash_range_prerequisite_is_expanded(self, spec_dir: Path) -> None:
        """GOV-STAT-003：``02–08 COMPLETE`` 展开为 02..08，缺 08 时 Spec 09 不得 READY。"""
        complete_01_07 = _completed_ledger([f"{index:02d}" for index in range(1, 8)])
        blocked = _jsonl([_event("09", "NOT_STARTED", "READY", "PREREQUISITES_SATISFIED")])
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(complete_01_07 + blocked, spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_6_MISSING_PREREQUISITE
        assert "08=" in str(excinfo.value)

        complete_01_08 = _completed_ledger([f"{index:02d}" for index in range(1, 9)])
        report = _reduce(complete_01_08 + blocked, spec_dir)
        assert report.statuses["09"] == "READY"

    def test_validated_unlock_allowlist_is_declared_empty(self) -> None:
        """GOV-STAT-003：Index §4/§6 未声明 VALIDATED 解锁例外 → 常量必须为空集。"""
        assert sl.VALIDATED_UNLOCK_ALLOWED == frozenset()


# --------------------------------------------------------------------------- #
# 4. READY → COMPLETE 跳跃（rule 4）
# --------------------------------------------------------------------------- #


class TestSkippedMandatoryStage:
    """rule 4 / rule 8：跳过主路径强制阶段（且不得 last-line-wins）。"""

    def test_ready_to_complete_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-003：``READY → COMPLETE`` 跳跃 → SPEC_STATUS_CONFLICT。"""
        event = _event("01", "READY", "COMPLETE", "ACCEPTANCE_COMPLETE", evidence_refs=EVIDENCE)
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl([event]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_4_SKIPPED_MANDATORY_STAGE

    def test_not_started_to_in_progress_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-003：``NOT_STARTED → IN_PROGRESS`` 同样跳过强制阶段。"""
        ledger = _jsonl(_chain("01") + [_event("02", "NOT_STARTED", "IN_PROGRESS", "EXECUTION_STARTED")])
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(ledger, spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_4_SKIPPED_MANDATORY_STAGE

    def test_validated_requires_evidence(self, spec_dir: Path) -> None:
        """rule 5：``VALIDATED`` 必须有非空 evidence_refs。"""
        ledger = _jsonl(
            [
                _event("01", "READY", "IN_PROGRESS", "EXECUTION_STARTED"),
                _event("01", "IN_PROGRESS", "VALIDATED", "VALIDATION_PASSED"),
            ]
        )
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(ledger, spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_5_VALIDATED_WITHOUT_EVIDENCE


# --------------------------------------------------------------------------- #
# 5. mutually exclusive successors（rule 4 / rule 8）
# --------------------------------------------------------------------------- #


class TestMutuallyExclusiveSuccessors:
    """rule 8：同一起点的互斥后继必须由匹配的 reason_code 支撑；BLOCKED 回到原阶段。"""

    def test_wrong_reason_for_successor_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-003：``IN_PROGRESS → BLOCKED`` 用 VALIDATION_PASSED 支撑 → 冲突。"""
        event = _event("01", "IN_PROGRESS", "BLOCKED", "VALIDATION_PASSED")
        ledger = _jsonl([_event("01", "READY", "IN_PROGRESS", "EXECUTION_STARTED"), event])
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(ledger, spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_4_MUTUALLY_EXCLUSIVE_SUCCESSOR

    def test_execution_started_cannot_reach_validated(self, spec_dir: Path) -> None:
        """GOV-STAT-003：``READY → IN_PROGRESS`` 用 VALIDATION_PASSED 支撑 → 冲突。"""
        event = _event("01", "READY", "IN_PROGRESS", "VALIDATION_PASSED", evidence_refs=EVIDENCE)
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl([event]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_4_MUTUALLY_EXCLUSIVE_SUCCESSOR

    def test_same_status_transition_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-003：``READY → READY`` 不是状态事件（no-op）→ 冲突。"""
        event = _event("01", "READY", "READY", "PREREQUISITES_SATISFIED")
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl([event]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_4_ILLEGAL_TRANSITION

    def test_blocked_returns_to_original_stage(self, spec_dir: Path) -> None:
        """GOV-STAT-003：``READY → BLOCKED → READY`` 合法；回到 IN_PROGRESS 则冲突。"""
        ok_ledger = _jsonl(
            [
                _event("01", "READY", "BLOCKED", "BLOCKED"),
                _event("01", "BLOCKED", "READY", "PREREQUISITES_SATISFIED"),
            ]
        )
        assert _reduce(ok_ledger, spec_dir).statuses["01"] == "READY"

        wrong_stage = _jsonl(
            [
                _event("01", "READY", "BLOCKED", "BLOCKED"),
                _event("01", "BLOCKED", "IN_PROGRESS", "EXECUTION_STARTED"),
            ]
        )
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(wrong_stage, spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_4_ILLEGAL_TRANSITION

    def test_blocked_cannot_be_entered_from_validated(self, spec_dir: Path) -> None:
        """GOV-STAT-003：``BLOCKED`` 只能从 READY / IN_PROGRESS 进入。"""
        ledger = _jsonl(
            [
                _event("01", "READY", "IN_PROGRESS", "EXECUTION_STARTED"),
                _event("01", "IN_PROGRESS", "VALIDATED", "VALIDATION_PASSED", evidence_refs=EVIDENCE),
                _event("01", "VALIDATED", "BLOCKED", "BLOCKED"),
            ]
        )
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(ledger, spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_4_ILLEGAL_TRANSITION

    def test_from_status_mismatch_is_conflict(self, spec_dir: Path) -> None:
        """rule 3：``from_status`` 必须等于该 spec 的前一归约状态。"""
        ledger = _jsonl([_event("01", "NOT_STARTED", "IN_PROGRESS", "EXECUTION_STARTED")])
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(ledger, spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_3_FROM_STATUS_MISMATCH


# --------------------------------------------------------------------------- #
# 6. correction（rule 4）
# --------------------------------------------------------------------------- #


class TestCorrection:
    """rule 4：``COMPLETE → IN_PROGRESS`` 仅允许 STATUS_CORRECTION 且必须引用错误事件。"""

    def test_status_correction_with_reference_is_accepted(self, spec_dir: Path) -> None:
        """GOV-STAT-004：合法 correction（引用错误事件）→ 状态回到 IN_PROGRESS。"""
        chain = _chain("01")
        erroneous = chain[-1]
        correction = _event(
            "01",
            "COMPLETE",
            "IN_PROGRESS",
            "STATUS_CORRECTION",
            references=[erroneous["event_id"]],
        )
        report = _reduce(_jsonl(chain + [correction]), spec_dir)
        assert report.statuses["01"] == "IN_PROGRESS"
        assert report.canonical_event_count == len(chain) + 1

    def test_status_correction_without_reference_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-004：correction 缺 references → SPEC_STATUS_CONFLICT。"""
        correction = _event("01", "COMPLETE", "IN_PROGRESS", "STATUS_CORRECTION")
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl(_chain("01") + [correction]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_4_CORRECTION_WITHOUT_REFERENCE

    def test_status_correction_with_unknown_reference_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-004：correction 引用不存在的 event_id → 悬空引用冲突。"""
        correction = _event(
            "01",
            "COMPLETE",
            "IN_PROGRESS",
            "STATUS_CORRECTION",
            references=[str(uuid.uuid4())],
        )
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl(_chain("01") + [correction]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_4_CORRECTION_DANGLING_REFERENCE

    def test_complete_to_in_progress_requires_status_correction(self, spec_dir: Path) -> None:
        """GOV-STAT-004：``COMPLETE → IN_PROGRESS`` 用别的理由码 → 冲突。"""
        event = _event("01", "COMPLETE", "IN_PROGRESS", "EXECUTION_STARTED")
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl(_chain("01") + [event]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_4_MUTUALLY_EXCLUSIVE_SUCCESSOR

    def test_candidate_defect_uses_candidate_superseded(self, spec_dir: Path) -> None:
        """GOV-STAT-004：候选缺陷走 CANDIDATE_SUPERSEDED，不修改既有 A 身份。"""
        ledger = _jsonl(
            _chain("01", candidate=COMMIT_A, complete_reason="CANDIDATE_FROZEN")
            + [
                _event(
                    "01",
                    "COMPLETE",
                    "SUPERSEDED",
                    "CANDIDATE_SUPERSEDED",
                    candidate_commit=COMMIT_A,
                )
            ]
        )
        assert _reduce(ledger, spec_dir).statuses["01"] == "SUPERSEDED"


# --------------------------------------------------------------------------- #
# 7. self-reference（rule 7）
# --------------------------------------------------------------------------- #


class TestSelfReference:
    """rule 7：事件不得保存包含自己的 commit SHA；envelope 不得自 hash。"""

    def test_event_candidate_commit_equal_to_self_commit_is_conflict(self, spec_dir: Path) -> None:
        """I.2:2776：``candidate_commit`` 指向封装该账本的提交 → 自引用冲突。"""
        event = _event(
            "01", "READY", "IN_PROGRESS", "EXECUTION_STARTED", candidate_commit=COMMIT_A
        )
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl([event]), spec_dir, self_commit=COMMIT_A)
        assert _conflict_rule(excinfo) == sl.RULE_7_SELF_COMMIT_REFERENCE

        # 未声明 self-commit 时同一账本合法（无法推断当前提交）。
        assert _reduce(_jsonl([event]), spec_dir).statuses["01"] == "IN_PROGRESS"

    def test_event_referencing_own_event_id_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-004：``references`` 含自身 event_id → 自引用冲突。"""
        identifier = str(uuid.uuid4())
        event = _event(
            "01",
            "READY",
            "IN_PROGRESS",
            "EXECUTION_STARTED",
            event_id=identifier,
            references=[identifier],
        )
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(_jsonl([event]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_7_SELF_EVENT_REFERENCE

    def test_envelope_cannot_hash_itself(self, spec_dir: Path) -> None:
        """G-03：``suffix_hash`` 若把 envelope 自身算进去 → hash 不一致冲突。"""
        suffix = [_event("11", "NOT_STARTED", "READY", "PREREQUISITES_SATISFIED", candidate_commit=COMMIT_A)]
        pending_bytes, _ = _pending_files(suffix)
        # 先造 envelope，再把 "jsonl + envelope" 当 hash 输入（典型的自引用错误）。
        envelope_placeholder = sl.canonical_json_dumps(
            {
                "pending_version": "1",
                "target_boundary": "candidate_a",
                "candidate_commit": COMMIT_A,
                "event_count": 1,
                "suffix_hash": "sha256:" + "0" * 64,
            }
        ).encode("utf-8")
        self_hashed = sl.compute_suffix_hash(pending_bytes + envelope_placeholder)
        pending_bytes, envelope_bytes = _pending_files(suffix, suffix_hash=self_hashed)
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(
                _completed_ledger([f"{index:02d}" for index in range(1, 11)]),
                spec_dir,
                pending=(pending_bytes, envelope_bytes),
            )
        assert _conflict_rule(excinfo) == sl.RULE_PENDING_HASH_MISMATCH

    def test_null_candidate_commit_is_rejected_post_freeze(self, spec_dir: Path) -> None:
        """GOV-FRZ-001：Spec 12–18 事件必须绑定已存在的候选 A（不得 null）。"""
        prefix = _completed_ledger(
            [f"{index:02d}" for index in range(1, 12)],
            freeze_spec="11",
            freeze_candidate=COMMIT_B,
        )
        event = _event("12", "NOT_STARTED", "READY", "PREREQUISITES_SATISFIED")
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(prefix + _jsonl([event]), spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_7_CANDIDATE_COMMIT_REQUIRED

    def test_boundary_reason_requires_candidate_commit(self, spec_dir: Path) -> None:
        """GOV-FRZ-001：``CANDIDATE_FROZEN`` 等边界事件必须带非空 candidate_commit。"""
        ledger = _jsonl(
            [
                _event("01", "READY", "IN_PROGRESS", "EXECUTION_STARTED"),
                _event("01", "IN_PROGRESS", "VALIDATED", "VALIDATION_PASSED", evidence_refs=EVIDENCE),
                _event("01", "VALIDATED", "COMPLETE", "CANDIDATE_FROZEN", evidence_refs=EVIDENCE),
            ]
        )
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(ledger, spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_7_CANDIDATE_COMMIT_REQUIRED


# --------------------------------------------------------------------------- #
# 8. pending suffix hash 与 append 一致性（G-03）
# --------------------------------------------------------------------------- #


class TestPendingSuffix:
    """G-03 provisional：canonical prefix + pending suffix → effective status（标 pending）。"""

    @staticmethod
    def _prefix() -> bytes:
        return _completed_ledger([f"{index:02d}" for index in range(1, 11)])

    @staticmethod
    def _suffix() -> list[dict[str, Any]]:
        return [
            _event("11", "NOT_STARTED", "READY", "PREREQUISITES_SATISFIED", candidate_commit=COMMIT_A),
            _event("11", "READY", "IN_PROGRESS", "EXECUTION_STARTED", candidate_commit=COMMIT_A),
        ]

    def test_valid_suffix_unlocks_and_is_marked_pending(self, spec_dir: Path) -> None:
        """I.3:2822-2830：suffix 可解锁 Spec 11，但必须标 ``pending=True``。"""
        pending = _pending_files(self._suffix())
        report = _reduce(self._prefix(), spec_dir, pending=pending)
        assert report.statuses["11"] == "IN_PROGRESS"
        assert report.pending["11"] is True
        assert report.pending["10"] is False
        assert report.used_pending_suffix is True
        assert report.suffix_event_count == 2
        # 01 有 3 条（genesis 已是 READY），02–10 各 4 条。
        assert report.canonical_event_count == 3 + 9 * 4
        assert report.candidate_commit == COMMIT_A
        assert report.target_boundary == "candidate_a"
        assert report.suffix_hash == sl.compute_suffix_hash(pending[0])
        assert report.pending_specs == ("11",)
        assert "11: IN_PROGRESS (pending)" in report.render_text()
        assert report.to_json()["pending_suffix"]["pending_specs"] == ["11"]

    def test_suffix_hash_mismatch_is_conflict(self, spec_dir: Path) -> None:
        """G-03：``suffix_hash`` 与实际 ``.jsonl`` 字节不一致 → 冲突。"""
        pending = _pending_files(self._suffix(), suffix_hash="sha256:" + "0" * 64)
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(self._prefix(), spec_dir, pending=pending)
        assert _conflict_rule(excinfo) == sl.RULE_PENDING_HASH_MISMATCH

    def test_suffix_event_count_mismatch_is_conflict(self, spec_dir: Path) -> None:
        """G-03：envelope ``event_count`` 必须等于 ``.jsonl`` 非空行数。"""
        pending = _pending_files(self._suffix(), event_count=3)
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(self._prefix(), spec_dir, pending=pending)
        assert _conflict_rule(excinfo) == sl.RULE_PENDING_COUNT_MISMATCH

    def test_suffix_candidate_binding_mismatch_is_conflict(self, spec_dir: Path) -> None:
        """G-03：suffix 内事件引用的候选必须与 envelope ``candidate_commit`` 一致。"""
        suffix = [
            _event("11", "NOT_STARTED", "READY", "PREREQUISITES_SATISFIED", candidate_commit=COMMIT_B),
            _event("11", "READY", "IN_PROGRESS", "EXECUTION_STARTED", candidate_commit=COMMIT_A),
        ]
        pending = _pending_files(suffix)
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(self._prefix(), spec_dir, pending=pending)
        assert _conflict_rule(excinfo) == sl.RULE_PENDING_CANDIDATE_MISMATCH

    def test_envelope_schema_drift_is_conflict(self, spec_dir: Path) -> None:
        """G-03：envelope 缺字段 / 多字段 / 非 canonical → 冲突。"""
        pending = _pending_files(self._suffix(), envelope_overrides={"sequence_no": 1})
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(self._prefix(), spec_dir, pending=pending)
        assert _conflict_rule(excinfo) == sl.RULE_PENDING_ENVELOPE_SCHEMA

        envelope = sl.canonical_json_dumps(
            {
                "pending_version": "1",
                "target_boundary": "candidate_a",
                "candidate_commit": COMMIT_A,
                "event_count": 2,
            }
        ).encode("utf-8")
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(self._prefix(), spec_dir, pending=(pending[0], envelope))
        assert _conflict_rule(excinfo) == sl.RULE_PENDING_ENVELOPE_SCHEMA

    def test_duplicate_event_id_across_prefix_and_suffix_is_conflict(self, spec_dir: Path) -> None:
        """rule 2：canonical prefix 与 suffix 之间 event_id 也不得重复。"""
        reused = _event("11", "NOT_STARTED", "READY", "PREREQUISITES_SATISFIED", candidate_commit=COMMIT_A)
        prefix = self._prefix()
        pending = _pending_files([reused, reused])
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(prefix, spec_dir, pending=pending)
        assert _conflict_rule(excinfo) == sl.RULE_2_DUPLICATE_EVENT_ID

    def test_append_is_byte_exact(self, spec_dir: Path) -> None:
        """I.3/I.4：``assert_suffix_appended`` 通过当且仅当逐字节前缀 + 逐字节相等。"""
        original = self._prefix()
        pending = _pending_files(self._suffix())[0]
        appended = original + pending
        assert sl.assert_suffix_appended(original, appended, pending) is None

    def test_append_with_extra_byte_is_conflict(self, spec_dir: Path) -> None:
        """I.3/I.4 反例 ①：多一个字节 → 冲突。"""
        original = self._prefix()
        pending = _pending_files(self._suffix())[0]
        with pytest.raises(sl.LedgerConflict) as excinfo:
            sl.assert_suffix_appended(original, original + pending + b"\n", pending)
        assert _conflict_rule(excinfo) == sl.RULE_PENDING_APPEND_MISMATCH

    def test_append_with_missing_byte_is_conflict(self, spec_dir: Path) -> None:
        """I.3/I.4 反例 ②：少一个字节（suffix 被截断）→ 冲突。"""
        original = self._prefix()
        pending = _pending_files(self._suffix())[0]
        with pytest.raises(sl.LedgerConflict) as excinfo:
            sl.assert_suffix_appended(original, original + pending[:-1], pending)
        assert _conflict_rule(excinfo) == sl.RULE_PENDING_APPEND_MISMATCH

    def test_append_with_reordered_bytes_is_conflict(self, spec_dir: Path) -> None:
        """I.3/I.4 反例 ③：顺序改变（重排后长度相同）→ 冲突。"""
        original = self._prefix()
        pending = _pending_files(self._suffix())[0]
        reordered = b"\n".join(reversed(pending.splitlines())) + b"\n"
        assert len(reordered) == len(pending)
        with pytest.raises(sl.LedgerConflict) as excinfo:
            sl.assert_suffix_appended(original, original + reordered, pending)
        assert _conflict_rule(excinfo) == sl.RULE_PENDING_APPEND_MISMATCH

    def test_append_without_original_prefix_is_conflict(self, spec_dir: Path) -> None:
        """I.3/I.4：新账本不是旧账本的纯追加（旧内容被改写）→ 冲突。"""
        original = self._prefix()
        pending = _pending_files(self._suffix())[0]
        rewritten = b"x" + original[1:] + pending
        with pytest.raises(sl.LedgerConflict) as excinfo:
            sl.assert_suffix_appended(original, rewritten, pending)
        assert _conflict_rule(excinfo) == sl.RULE_PENDING_APPEND_MISMATCH

    def test_cli_requires_both_pending_files(self, tmp_path: Path, spec_dir: Path, capsys: Any) -> None:
        """CLI：只给一半的 pending 参数 → 退出 2 且 stderr 带 SPEC_INCOMPLETE。"""
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_bytes(self._prefix())
        pending_bytes, _envelope_bytes = _pending_files(self._suffix())
        pending_jsonl = tmp_path / "suffix.pending.jsonl"
        pending_jsonl.write_bytes(pending_bytes)

        code = sl.main(
            [
                "validate",
                "--ledger",
                str(ledger),
                "--spec-dir",
                str(spec_dir),
                "--pending-jsonl",
                str(pending_jsonl),
            ]
        )
        captured = capsys.readouterr()
        assert code == 2
        assert "SPEC_INCOMPLETE" in captured.err

        code = sl.main(
            [
                "validate",
                "--ledger",
                str(ledger),
                "--spec-dir",
                str(spec_dir),
                "--pending-jsonl",
                str(pending_jsonl),
                "--pending-envelope",
                str(tmp_path / "missing.pending.json"),
            ]
        )
        captured = capsys.readouterr()
        assert code == 2
        assert "SPEC_INCOMPLETE" in captured.err

    def test_cli_accepts_valid_suffix_and_marks_pending(
        self, tmp_path: Path, spec_dir: Path, capsys: Any
    ) -> None:
        """CLI：合法 suffix → 退出 0，stdout 标注 ``(pending)`` 与 suffix hash。"""
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_bytes(self._prefix())
        pending_bytes, envelope_bytes = _pending_files(self._suffix())
        pending_jsonl = tmp_path / "suffix.pending.jsonl"
        pending_jsonl.write_bytes(pending_bytes)
        pending_envelope = tmp_path / "suffix.pending.json"
        pending_envelope.write_bytes(envelope_bytes)

        code = sl.main(
            [
                "validate",
                "--ledger",
                str(ledger),
                "--spec-dir",
                str(spec_dir),
                "--pending-jsonl",
                str(pending_jsonl),
                "--pending-envelope",
                str(pending_envelope),
            ]
        )
        captured = capsys.readouterr()
        assert code == 0
        assert "11: IN_PROGRESS (pending)" in captured.out
        assert "pending_suffix: used" in captured.out
        assert sl.compute_suffix_hash(pending_bytes) in captured.out


# --------------------------------------------------------------------------- #
# 9. Candidate 隔离
# --------------------------------------------------------------------------- #


class TestCandidateIsolation:
    """I.3 规则 7 / C.7：suffix 由同一 Candidate A 的 reducer 生成，不得跨候选复用。"""

    @staticmethod
    def _frozen_b_prefix() -> bytes:
        return _completed_ledger(
            [f"{index:02d}" for index in range(1, 12)],
            freeze_spec="11",
            freeze_candidate=COMMIT_B,
        )

    @staticmethod
    def _spec12_suffix(candidate: str) -> list[dict[str, Any]]:
        return [
            _event("12", "NOT_STARTED", "READY", "PREREQUISITES_SATISFIED", candidate_commit=candidate)
        ]

    def test_suffix_bound_to_other_candidate_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-003：A 已冻结为 B，suffix 却绑定 A → 冲突（不跨候选复用）。"""
        pending = _pending_files(self._spec12_suffix(COMMIT_A), candidate=COMMIT_A)
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(self._frozen_b_prefix(), spec_dir, pending=pending)
        assert _conflict_rule(excinfo) == sl.RULE_PENDING_CANDIDATE_MISMATCH

    def test_suffix_bound_to_current_candidate_is_accepted(self, spec_dir: Path) -> None:
        """GOV-STAT-003 正例：suffix 绑定当前冻结候选 B → 合法解锁 Spec 12。"""
        pending = _pending_files(self._spec12_suffix(COMMIT_B), candidate=COMMIT_B)
        report = _reduce(self._frozen_b_prefix(), spec_dir, pending=pending)
        assert report.statuses["12"] == "READY"
        assert report.pending["12"] is True

    def test_suffix_bound_to_superseded_candidate_is_conflict(self, spec_dir: Path) -> None:
        """GOV-STAT-004：候选 A 已被 CANDIDATE_SUPERSEDED，旧 suffix 失效 → 冲突。"""
        prefix = self._frozen_b_prefix() + _jsonl(
            [
                _event(
                    "11",
                    "COMPLETE",
                    "SUPERSEDED",
                    "CANDIDATE_SUPERSEDED",
                    candidate_commit=COMMIT_B,
                )
            ]
        )
        pending = _pending_files(self._spec12_suffix(COMMIT_B), candidate=COMMIT_B)
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(prefix, spec_dir, pending=pending)
        assert _conflict_rule(excinfo) == sl.RULE_PENDING_CANDIDATE_SUPERSEDED


# --------------------------------------------------------------------------- #
# 10. genesis（GOV-STAT-002）
# --------------------------------------------------------------------------- #


class TestGenesis:
    """GOV-STAT-002：空账本 + 子 Spec Initial Status = genesis（不硬编码）。"""

    def test_empty_ledger_resolves_to_child_spec_initial_status(self, spec_dir: Path) -> None:
        """GOV-STAT-002：空账本 → 01 READY、02–18 NOT_STARTED。"""
        report = _reduce(b"", spec_dir)
        assert report.statuses["01"] == "READY"
        for spec_id in sl.SPEC_IDS[1:]:
            assert report.statuses[spec_id] == "NOT_STARTED", spec_id
        assert report.canonical_event_count == 0
        assert report.used_pending_suffix is False
        assert report.pending_specs == ()

    def test_whitespace_only_ledger_is_still_genesis(self, spec_dir: Path) -> None:
        """GOV-STAT-002：0 字节 / 0 行都归约到 genesis。"""
        report = _reduce(b"\n  \n\n", spec_dir)
        assert report.statuses["01"] == "READY"
        assert report.canonical_event_count == 0

    def test_genesis_is_reproducible_and_read_from_real_child_specs(self, spec_dir: Path) -> None:
        """GOV-STAT-002：真实子 Spec 的 Initial Status 必须复现同一 genesis。"""
        first = _reduce(b"", spec_dir).to_json()
        second = _reduce(b"", spec_dir).to_json()
        assert first == second

        real = _reduce(b"", SPEC_DIR)
        assert real.statuses["01"] == "READY"
        assert {spec_id: real.statuses[spec_id] for spec_id in sl.SPEC_IDS} == {
            spec_id: ("READY" if spec_id == "01" else "NOT_STARTED") for spec_id in sl.SPEC_IDS
        }

    def test_initial_status_parser_handles_fullwidth_colon_and_backticks(self) -> None:
        """GOV-STAT-002：全角冒号 / 反引号 / 多空格 / 全角空格都能解析。"""
        assert sl.parse_initial_status("> Initial Status：`NOT_STARTED`  ") == "NOT_STARTED"
        assert sl.parse_initial_status("> Initial Status: READY") == "READY"
        assert sl.parse_initial_status(">  Initial   Status  ：\u3000`VALIDATED`") == "VALIDATED"
        assert sl.parse_initial_status("> Initial Status：不适用") is None
        assert sl.parse_initial_status("# no header here") is None

    def test_unparsable_genesis_exits_2(self, tmp_path: Path, capsys: Any) -> None:
        """GOV-STAT-002：Initial Status 解析失败必须退出 2，不得静默兜底。"""
        directory = _write_genesis(tmp_path / "specs")
        broken = directory / "05-fixture.md"
        broken.write_text("# Spec 05 fixture\n\nno header\n", encoding="utf-8")
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_bytes(b"")

        with pytest.raises(sl.LedgerConfigError) as excinfo:
            _reduce(b"", directory)
        assert "SPEC_INCOMPLETE" in str(excinfo.value)

        code = sl.main(["validate", "--ledger", str(ledger), "--spec-dir", str(directory)])
        captured = capsys.readouterr()
        assert code == 2
        assert "SPEC_INCOMPLETE" in captured.err

    def test_missing_ledger_file_exits_2(self, tmp_path: Path, capsys: Any) -> None:
        """CLI：账本文件缺失 → 退出 2 且 stderr 带 SPEC_INCOMPLETE。"""
        code = sl.main(["validate", "--ledger", str(tmp_path / "nope.jsonl")])
        captured = capsys.readouterr()
        assert code == 2
        assert "SPEC_INCOMPLETE" in captured.err

    def test_conflict_exit_code_is_1(self, tmp_path: Path, spec_dir: Path, capsys: Any) -> None:
        """CLI：非法事件 → 退出 1 且 stderr 带 SPEC_STATUS_CONFLICT。"""
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_bytes(_jsonl([_event("01", "READY", "COMPLETE", "ACCEPTANCE_COMPLETE")]))
        code = sl.main(["validate", "--ledger", str(ledger), "--spec-dir", str(spec_dir)])
        captured = capsys.readouterr()
        assert code == 1
        assert "SPEC_STATUS_CONFLICT" in captured.err
        assert sl.RULE_4_SKIPPED_MANDATORY_STAGE in captured.err


# --------------------------------------------------------------------------- #
# 11. 真实账本端到端
# --------------------------------------------------------------------------- #


class TestRealLedger:
    """真实账本 ``docs/specs/foundation-contract/execution-status-events.jsonl`` 必须通过。"""

    def test_real_ledger_reduces_cleanly(self) -> None:
        """GOV-STAT-001：真实账本必须合法归约，且状态只取合法闭集。

        期望以**文件实际内容**为准，**不硬编码"当前进度"**：账本会随每个 Spec 推进而增长，
        任何写死的中间状态都会在下一个 Spec 完成时变成假失败（本测试确实在 Spec 10 完成、
        事件追加进账本时于 CI 上挂掉过）。真正要断言的是：
          - 归约本身不抛 ``SPEC_STATUS_CONFLICT``；
          - 每个 spec 的状态都在 ``STATUSES`` 闭集内；
          - 早期已完成的 Spec 不会被静默回退（回退只能经 ``STATUS_CORRECTION`` 事件，而那种
            事件会被归约校验捕获）；
          - canonical 事件数与文件行数自洽。
        """
        raw = REAL_LEDGER.read_bytes()
        report = sl.reduce_ledger_files(
            ledger_path=REAL_LEDGER, spec_dir=SPEC_DIR, index_path=INDEX_PATH
        )
        assert set(report.statuses) == set(sl.SPEC_IDS)
        illegal = {
            spec_id: status
            for spec_id, status in report.statuses.items()
            if status not in set(sl.STATUSES)
        }
        assert not illegal, f"非法状态取值：{illegal}"
        for spec_id in [f"{index:02d}" for index in range(1, 10)]:
            assert report.statuses[spec_id] == "COMPLETE", spec_id
        assert report.used_pending_suffix is False
        assert report.suffix_hash is None
        assert report.canonical_event_count == sl.count_nonempty_lines(raw, "ledger")
        assert len(raw.splitlines()) == report.canonical_event_count

    def test_real_ledger_cli_exit_code_0(self, capsys: Any) -> None:
        """CLI：Spec 10 fixture 命令 #7 的完整形态 → 退出 0。"""
        expected_events = sl.count_nonempty_lines(REAL_LEDGER.read_bytes(), "ledger")
        code = sl.main(["validate", "--ledger", str(REAL_LEDGER)])
        captured = capsys.readouterr()
        assert code == 0
        assert "01: COMPLETE" in captured.out
        assert f"canonical_events: {expected_events}" in captured.out
        assert "pending_suffix: none" in captured.out

    def test_script_runs_as_plain_script_without_module_bootstrap(self) -> None:
        """以脚本方式直跑（非 ``python -m``）：sys.path 自举必须生效。

        使用 Spec 10 §F.2 命令 #7 的原样相对路径，``cwd`` = 仓库根。
        """
        expected_events = sl.count_nonempty_lines(REAL_LEDGER.read_bytes(), "ledger")
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/contracts/status_ledger.py",
                "validate",
                "--ledger",
                "docs/specs/foundation-contract/execution-status-events.jsonl",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "01: COMPLETE" in completed.stdout
        assert f"canonical_events: {expected_events}" in completed.stdout


# --------------------------------------------------------------------------- #
# 12. Index 一致性（DAG / Authority / Initial Status）
# --------------------------------------------------------------------------- #


class TestIndexConsistency:
    """脚本内常量必须与 ``00-execution-index.md`` §3 表格逐项一致。"""

    def test_index_table_parses_all_18_specs(self) -> None:
        """Index §3：表格必须覆盖 01–18。"""
        rows = sl.parse_index_table(INDEX_PATH.read_text(encoding="utf-8"))
        assert set(rows) == set(sl.SPEC_IDS)

    def test_authority_constants_match_index(self) -> None:
        """Index §2/§3：Authority 常量与表格逐项一致。"""
        rows = sl.parse_index_table(INDEX_PATH.read_text(encoding="utf-8"))
        for spec_id in sl.SPEC_IDS:
            assert rows[spec_id].authority == sl.SPEC_AUTHORITY[spec_id], spec_id

    def test_dag_constants_match_index(self) -> None:
        """Index §3/§4：Depends On 原文与解析结果都必须与常量逐项一致。"""
        rows = sl.parse_index_table(INDEX_PATH.read_text(encoding="utf-8"))
        for spec_id in sl.SPEC_IDS:
            row = rows[spec_id]
            assert row.depends_on_raw == sl.DAG[spec_id].raw, spec_id
            assert sl.parse_dependencies(row.depends_on_raw) == sl.DAG[spec_id], spec_id

    def test_initial_status_column_matches_child_specs(self) -> None:
        """GOV-STAT-002：Index §3 的 Initial Status 列必须等于子 Spec 头部声明。"""
        rows = sl.parse_index_table(INDEX_PATH.read_text(encoding="utf-8"))
        genesis = sl.read_genesis(SPEC_DIR)
        for spec_id in sl.SPEC_IDS:
            assert rows[spec_id].initial_status == genesis[spec_id], spec_id

    def test_index_verification_accepts_real_index(self) -> None:
        """常量与真实 Index 一致时 ``verify_index`` 不报错。"""
        rows = sl.verify_index(INDEX_PATH, sl.read_genesis(SPEC_DIR))
        assert set(rows) == set(sl.SPEC_IDS)

    def test_index_verification_detects_authority_drift(self, tmp_path: Path) -> None:
        """GOV-SPEC-002：Index 表格漂移 → 冲突（常量是规范投影，不得静默漂移）。"""
        text = INDEX_PATH.read_text(encoding="utf-8")
        drifted = text.replace(
            "| IMPLEMENTATION-READY | READY | — |",
            "| FEEDBACK-BOUND / PROCESS-ONLY | READY | — |",
        )
        assert drifted != text
        index_copy = tmp_path / "00-execution-index.md"
        index_copy.write_text(drifted, encoding="utf-8")
        with pytest.raises(sl.LedgerConflict) as excinfo:
            sl.verify_index(index_copy)
        assert _conflict_rule(excinfo) == sl.RULE_GOV_INDEX_MISMATCH

    def test_dependency_parser_handles_all_index_forms(self) -> None:
        """Index §3：``—`` / ``+`` / en dash 区间 / 附加条件文本都要能解析。"""
        assert sl.parse_dependencies("—") == sl.Dependency("—")
        assert sl.parse_dependencies("01 COMPLETE").prerequisites == ("01",)
        assert sl.parse_dependencies("02 + 03 COMPLETE").prerequisites == ("02", "03")
        assert sl.parse_dependencies("02\u201308 COMPLETE").prerequisites == (
            "02",
            "03",
            "04",
            "05",
            "06",
            "07",
            "08",
        )
        assert sl.parse_dependencies("02-08 COMPLETE").prerequisites == sl.parse_dependencies(
            "02\u201308 COMPLETE"
        ).prerequisites
        extra = sl.parse_dependencies("Cycle 1 COMPLETE + real L2/L3 issue")
        assert extra.prerequisites == ()
        assert extra.extra_conditions == ("Cycle 1 COMPLETE + real L2/L3 issue",)
        assert sl.parse_dependencies("Foundation boundary sufficiently stable").prerequisites == ()

    def test_non_executable_authorities_cannot_enter_execution(self, spec_dir: Path) -> None:
        """rule 6：``FEEDBACK-BOUND`` / ``GATE-DEFINED`` 不得进入 IN_PROGRESS/VALIDATED/COMPLETE。"""
        assert sl.SPEC_AUTHORITY["16"] in sl.NON_EXECUTABLE_AUTHORITIES
        assert sl.SPEC_AUTHORITY["17"] in sl.NON_EXECUTABLE_AUTHORITIES
        assert sl.SPEC_AUTHORITY["18"] in sl.NON_EXECUTABLE_AUTHORITIES

        ledger = _jsonl(
            [
                _event(
                    "16",
                    "NOT_STARTED",
                    "READY",
                    "PREREQUISITES_SATISFIED",
                    candidate_commit=COMMIT_B,
                ),
                _event(
                    "16",
                    "READY",
                    "IN_PROGRESS",
                    "EXECUTION_STARTED",
                    candidate_commit=COMMIT_B,
                ),
            ]
        )
        with pytest.raises(sl.LedgerConflict) as excinfo:
            _reduce(ledger, spec_dir)
        assert _conflict_rule(excinfo) == sl.RULE_6_AUTHORITY_NOT_EXECUTABLE

        # READY 本身是允许的（只允许 NOT_STARTED / READY / BLOCKED）。
        ready_only = _jsonl(
            [
                _event(
                    "16",
                    "NOT_STARTED",
                    "READY",
                    "PREREQUISITES_SATISFIED",
                    candidate_commit=COMMIT_B,
                )
            ]
        )
        assert _reduce(ready_only, spec_dir).statuses["16"] == "READY"


# --------------------------------------------------------------------------- #
# 12. 冻结表面（Spec 11 Stage 0 校准）
# --------------------------------------------------------------------------- #


class TestFrozenSurface:
    """把 Spec 10 的 provisional 发明物钉成**显式冻结面**（G-22 / G-26 / G-03）。

    这三个语义在母 Spec 中**完全没有定义**，是 Spec 10 的发明；它们会随 Candidate A 一起冻结，
    之后任何改动都必须把 A 标 ``SUPERSEDED`` 并形成 A2（``GOV-FRZ-002``）。因此这里用**字面量
    表**把耦合表、CLI 表面与 pending suffix 载体固定下来：改动会让测试**显式失败**，
    而不是悄悄漂移。

    校准记录：``docs/plans/2026-09-16-foundation-contract-spec11-stage0-calibration.md``
    """

    EXPECTED_REASON_CODES = (
        "PREREQUISITES_SATISFIED",
        "EXECUTION_STARTED",
        "VALIDATION_PASSED",
        "ACCEPTANCE_COMPLETE",
        "BLOCKED",
        "SPEC_CONFLICT",
        "SPEC_INCOMPLETE",
        "FREEZE_BOUNDARY_REACHED",
        "CANDIDATE_FROZEN",
        "CANDIDATE_SUPERSEDED",
        "EVIDENCE_PUBLISHED",
        "COORDINATION_PASSED",
        "FINALIZATION_COMPLETE",
        "STATUS_CORRECTION",
    )

    #: G-22 冻结：静态转换 → 允许理由码（``BLOCKED`` 相关转换在运行时另行判定）。
    EXPECTED_REASON_BY_TRANSITION = {
        ("NOT_STARTED", "READY"): frozenset({"PREREQUISITES_SATISFIED"}),
        ("READY", "IN_PROGRESS"): frozenset({"EXECUTION_STARTED"}),
        ("IN_PROGRESS", "VALIDATED"): frozenset(
            {
                "VALIDATION_PASSED",
                "FREEZE_BOUNDARY_REACHED",
                "CANDIDATE_FROZEN",
                "EVIDENCE_PUBLISHED",
                "COORDINATION_PASSED",
            }
        ),
        ("VALIDATED", "COMPLETE"): frozenset(
            {
                "ACCEPTANCE_COMPLETE",
                "FREEZE_BOUNDARY_REACHED",
                "CANDIDATE_FROZEN",
                "EVIDENCE_PUBLISHED",
                "COORDINATION_PASSED",
                "FINALIZATION_COMPLETE",
            }
        ),
        ("COMPLETE", "IN_PROGRESS"): frozenset({"STATUS_CORRECTION"}),
    }

    #: G-26 冻结：``status_ledger.py validate`` 的 CLI 表面。
    EXPECTED_VALIDATE_FLAGS = frozenset(
        {
            "--ledger",
            "--pending-jsonl",
            "--pending-envelope",
            "--spec-dir",
            "--index",
            "--self-commit",
            "--json",
        }
    )

    def test_reason_codes_closed_set_is_frozen(self) -> None:
        assert sl.REASON_CODES == self.EXPECTED_REASON_CODES
        assert len(set(sl.REASON_CODES)) == len(sl.REASON_CODES) == 14

    def test_reason_by_transition_table_is_frozen(self) -> None:
        assert dict(sl.REASON_BY_TRANSITION) == self.EXPECTED_REASON_BY_TRANSITION
        used = {code for codes in sl.REASON_BY_TRANSITION.values() for code in codes}
        assert used <= set(sl.REASON_CODES), sorted(used - set(sl.REASON_CODES))

    def test_every_reason_code_is_usable_somewhere(self) -> None:
        """14 个理由码必须都能在某个转换（含 BLOCK/UNBLOCK/SUPERSEDE 分支）里被接受。"""
        usable = (
            {code for codes in sl.REASON_BY_TRANSITION.values() for code in codes}
            | set(sl.BLOCK_REASON_CODES)
            | set(sl.UNBLOCK_REASON_CODES)
            | set(sl.SUPERSEDE_REASON_CODES)
        )
        assert usable == set(sl.REASON_CODES), sorted(set(sl.REASON_CODES) - usable)

    def test_block_unblock_supersede_sets_are_frozen(self) -> None:
        assert sl.BLOCK_REASON_CODES == frozenset({"BLOCKED", "SPEC_CONFLICT", "SPEC_INCOMPLETE"})
        assert sl.UNBLOCK_REASON_CODES == frozenset(
            {"PREREQUISITES_SATISFIED", "EXECUTION_STARTED"}
        )
        assert sl.SUPERSEDE_FROM_STATUSES == frozenset(
            {"READY", "IN_PROGRESS", "BLOCKED", "VALIDATED", "COMPLETE"}
        )
        assert sl.SUPERSEDE_REASON_CODES == frozenset({"CANDIDATE_SUPERSEDED"})

    def test_non_executable_authority_statuses_are_frozen(self) -> None:
        assert sl.NON_EXECUTABLE_STATUSES == frozenset({"NOT_STARTED", "READY", "BLOCKED"})
        assert sl.VALIDATED_UNLOCK_ALLOWED == frozenset()

    def test_validate_cli_surface_is_frozen(self) -> None:
        """G-26：coordinator 的 check 8 依赖这些参数，它们必须随 A 一起冻结。"""
        parser = sl.build_parser()
        subparsers = next(
            action
            for action in parser._actions  # noqa: SLF001 - argparse 无公开的自省 API
            if isinstance(action, argparse._SubParsersAction)  # noqa: SLF001
        )
        validate = subparsers.choices["validate"]
        flags = {
            option
            for action in validate._actions  # noqa: SLF001
            for option in action.option_strings
            # argparse 会自动加入 -h/--help，不属于本工具的自定义表面
            if option not in {"-h", "--help"}
        }
        assert flags == self.EXPECTED_VALIDATE_FLAGS

    def test_pending_suffix_paths_are_canonical(self, tmp_path: Path) -> None:
        """G-03 冻结：suffix 载体文件名与 ledger 同目录。"""
        ledger = tmp_path / "execution-status-events.jsonl"
        jsonl, envelope = sl.canonical_pending_paths(ledger)
        assert jsonl == tmp_path / "execution-status-events.pending.jsonl"
        assert envelope == tmp_path / "execution-status-events.pending.json"
        assert sl.PENDING_JSONL_FILENAME == "execution-status-events.pending.jsonl"
        assert sl.PENDING_ENVELOPE_FILENAME == "execution-status-events.pending.json"
        assert sl.PENDING_ENVELOPE_FIELDS == (
            "pending_version",
            "target_boundary",
            "candidate_commit",
            "event_count",
            "suffix_hash",
        )
        assert sl.TARGET_BOUNDARIES == frozenset(
            {"candidate_a", "evidence_b_wiki", "finalization_c_wiki"}
        )
        # 真实账本必须能用同一套命名定位 suffix
        real_jsonl, real_envelope = sl.canonical_pending_paths(REAL_LEDGER)
        assert real_jsonl.parent == REAL_LEDGER.parent == SPEC_DIR
        assert real_envelope.name == sl.PENDING_ENVELOPE_FILENAME

    def test_manifest_key_sets_are_frozen(self) -> None:
        """G-01 / G-02 冻结：两个 run manifest 的键集与嵌套结构。

        Spec 13/14 禁止修改 ``config/``，所以键名必须在 A 冻结前定死；这里用字面量钉住。

        逐对 ``evidence_requirement`` 的值同样钉住，但**性质必须逐条分清**（不得混同）：

        * **§7.3 规范硬要求**（L3 列逐字）→ ``ALL_STAGES``。
        * **(A) 规范回归**：母 Spec §7.3:896 写明"错误 stage 可 ``NOT_OBSERVED``"。
          Coding ``case_cost`` 的冻结 manifest 曾把 ``environment_error`` / ``error``
          错标 ``ALL_STAGES``，本轮回归为 ``NOT_OBSERVED_ALLOWED`` —— 这是**修缺陷**，
          不是偏离。
        * **(B) 用户授权偏离**（依 N-04）：Wiki ``wiki.eval.cost_log`` / ``scoring``
          被 §7.3:892 硬要求，但 ``arknights_wiki/eval/scoring.py`` 顶层 ``import deepeval``
          而宿主**未声明也未安装**该包（只能由 ``scripts/score_runner.py`` 触发），
          因此记 ``NOT_OBSERVED_ALLOWED``。记录见
          ``docs/plans/2026-09-16-foundation-contract-spec11-stage0-calibration.md`` §10 (B1)。
        """
        expected_smoke_keys = {
            "manifest_version",
            "run_id",
            "contract_mode",
            "contract_version",
            "payload_hash",
            "candidate_commit",
            "repository_commit",
            "evidence_root",
            "coverage_policy",
            "required_producer_stages",
            "model",
            "provider",
            "case_ids",
            "expected_calls",
            "max_calls",
            "estimated_cost_cap",
            "network_requirement",
            "side_effect_policy",
            "timeout_seconds",
            "duration_cap_seconds",
        }
        expected_replay_keys = {
            "manifest_version",
            "run_id",
            "contract_mode",
            "contract_version",
            "payload_hash",
            "repository_commit",
            "output_dir",
            "sources",
            "max_records",
            "reproduction_restriction",
        }
        expected_stage_keys = {"producer_id", "mapping_stage", "evidence_requirement"}
        #: 冻结的逐对覆盖要求（键名/嵌套不变；值 = §7.3 硬要求 + (B) 授权偏离）。
        expected_stage_requirements = {
            ("wiki.agent.llm_usage", "chat_completion"): "ALL_STAGES",
            ("wiki.agent.llm_usage", "intent_rewrite"): "ALL_STAGES",
            ("wiki.eval.cost_log", "runner"): "ALL_STAGES",
            ("wiki.eval.cost_log", "judge"): "ALL_STAGES",
            # (B) N-04 授权偏离：deepeval 未声明未安装，宿主无法观测 scoring
            ("wiki.eval.cost_log", "scoring"): "NOT_OBSERVED_ALLOWED",
            ("wiki.eval.cost_summary", "cost_log_summary"): "ALL_STAGES",
        }
        #: registry 的 producer 级值是**授权下限**（manifest 逐对可更严，不可更松）。
        expected_registry_requirements = {
            "wiki.agent.llm_usage": "ALL_STAGES",
            "wiki.eval.cost_log": "NOT_OBSERVED_ALLOWED",  # (B) 授权下限
            "wiki.eval.cost_summary": "ALL_STAGES",
        }
        expected_source_keys = {
            "source_id",
            "source_class",
            "path",
            "producer_id",
            "mapping_stage",
            "runtime_adapter_status",
            "evidence_role",
        }
        config_dir = REPO_ROOT / "config" / "contracts"
        smoke = json.loads((config_dir / "smoke-v0.1.json").read_text(encoding="utf-8"))
        replay = json.loads((config_dir / "replay-v0.1.json").read_text(encoding="utf-8"))
        registry = json.loads((config_dir / "producer-registry.json").read_text(encoding="utf-8"))
        assert set(smoke) == expected_smoke_keys, sorted(set(smoke) ^ expected_smoke_keys)
        assert set(replay) == expected_replay_keys, sorted(set(replay) ^ expected_replay_keys)
        actual_stage_requirements = {}
        for item in smoke["required_producer_stages"]:
            assert set(item) == expected_stage_keys
            actual_stage_requirements[(item["producer_id"], item["mapping_stage"])] = item[
                "evidence_requirement"
            ]
        assert actual_stage_requirements == expected_stage_requirements
        actual_registry_requirements = {
            producer["producer_id"]: producer["evidence_requirement"]
            for producer in registry["producers"]
            if producer["status"] == "IN_SCOPE"
        }
        assert actual_registry_requirements == expected_registry_requirements
        for source in replay["sources"]:
            assert set(source) == expected_source_keys
