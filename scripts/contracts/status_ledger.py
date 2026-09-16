#!/usr/bin/env python
"""Spec 10 — Foundation Contract 状态账本 reducer（Appendix I 状态治理）。

规范来源
--------
- Master Appendix I.1（静态 genesis）、I.2（Event Schema 与状态/理由闭集）
- Master Appendix I.3（8 条 reducer 校验规则、canonical prefix + pending suffix）
- Master Appendix I.4（A/B/C 持久化边界与 append-only）、I.5（GOV-STAT-* / GOV-FRZ-*）
- `docs/specs/foundation-contract/00-execution-index.md` §2/§3/§4/§5/§6/§7
- Spec 10 §A/§C（交付物 A.4、8 类必测用例）

CLI
---
```text
python scripts/contracts/status_ledger.py validate --ledger <ledger.jsonl>
python scripts/contracts/status_ledger.py validate --ledger <ledger.jsonl> \
    --pending-jsonl <suffix.pending.jsonl> --pending-envelope <suffix.pending.json>
```

退出码（provisional，与 Spec 10 其它脚本统一；规范未定义数字，见 G-18）
--------------------------------------------------------------------
```text
0  合法：归约成功
1  归约/校验失败（非法事件、非法 envelope、非法 append）
2  用法或配置错误（文件缺失、参数非法、genesis 规范缺失）
```

失败时 **stderr 必须**出现可 grep 的符号：退出 1 → ``SPEC_STATUS_CONFLICT``；
退出 2 → ``SPEC_INCOMPLETE``。绝不忽略非法行、绝不重排、绝不 last-line-wins。

PROVISIONAL 决策（规范缺口 → 本实现的选择；全部待 Spec 11 Stage 0 校准）
------------------------------------------------------------------------
- **G-03（pending suffix 的载体与 schema 未定义）→ 本实现自定载体**：
  * ``*.pending.jsonl``（append-only，仅事件行，格式与 canonical ledger 完全一致）
  * ``*.pending.json``（envelope：``pending_version`` / ``target_boundary`` /
    ``candidate_commit`` / ``event_count`` / ``suffix_hash``）
  * ``suffix_hash`` = 对该 ``.jsonl`` 文件**原始字节**的 ``sha256:<hex>``；
    envelope 自身**不参与**该 hash（避免自引用）。
  * 归约形式：``canonical ledger prefix`` + ``pending suffix`` → effective status；
    suffix 归约出的状态一律标 ``pending=True``，因为 suffix **不是** Git canonical
    history，不能单独证明 Cycle COMPLETE（I.3:2822-2830）。
- **G-18（退出码未定义）→ 0/1/2**，见上。
- **rule 7 的 pre-freeze 范围**：Spec 01–11 事件允许 ``candidate_commit = null``；
  Spec 12–18 事件必须绑定已存在的候选 A（非空）。5 个边界/发布类 reason_code
  （``FREEZE_BOUNDARY_REACHED`` / ``CANDIDATE_FROZEN`` / ``EVIDENCE_PUBLISHED`` /
  ``COORDINATION_PASSED`` / ``FINALIZATION_COMPLETE``）无论 spec 为何都必须非空。
- **rule 4 中 BLOCKED 解除的 reason_code**：I.2/I.3 只说"回到原执行阶段"，未规定理由码。
  本实现只接受 ``PREREQUISITES_SATISFIED`` / ``EXECUTION_STARTED``；解除阻塞时**不**重新
  检查 DAG 前置（规范只要求回到原阶段，未要求重新解锁）。
- **rule 4 中 ``SUPERSEDED``**：进入需 ``CANDIDATE_SUPERSEDED``；Index §5 要求工具缺陷
  时"回到所属 01–10 子 Spec 形成 A2"，因此额外允许
  ``SUPERSEDED → IN_PROGRESS``（理由码同样为 ``CANDIDATE_SUPERSEDED``）作为 A2 重启。
- **rule 4 的理由码 ↔ 转换耦合（"互斥后继"）**：同一起点可有多个合法后继
  （如 ``IN_PROGRESS → VALIDATED | BLOCKED``），因此把 I.3 规则 8 的"互斥后继"
  实现为：**转换必须由该转换对应的理由码集合中的理由码支撑**；用错误的理由码
  走到某一后继 → ``RULE_4_MUTUALLY_EXCLUSIVE_SUCCESSOR``。理由码集合中，绑定后
  阶段（post-freeze）的辅助码（``FREEZE_BOUNDARY_REACHED`` / ``CANDIDATE_FROZEN`` /
  ``EVIDENCE_PUBLISHED`` / ``COORDINATION_PASSED`` / ``FINALIZATION_COMPLETE``）被允许
  落在"验证/完成"两个转换上——规范未指定它们各自对应哪个状态转换，本实现按最小
  可行语义放宽，待 Spec 11 校准。
- **rule 6 的 VALIDATED 解锁**：Index §4/§6 声明"依赖默认要求 upstream ``COMPLETE``"，
  没有任何子 Spec 显式允许 ``VALIDATED`` 解锁 → ``VALIDATED_UNLOCK_ALLOWED = frozenset()``。
  该常量即规范声明位，测试可直接断言。
- **rule 6 的 Authority 限制**：``FEEDBACK-BOUND / PROCESS-ONLY``、
  ``GATE-DEFINED / NOT EXECUTABLE YET`` 的 spec 只允许
  ``NOT_STARTED`` / ``READY`` / ``BLOCKED``；出现 ``IN_PROGRESS`` / ``VALIDATED`` /
  ``COMPLETE`` / ``SUPERSEDED`` → ``SPEC_STATUS_CONFLICT``（不能仅因状态变化获得实施权限）。
- **Self-reference 的实现**：单凭账本无法知道"当前提交"，因此额外提供可选参数
  ``--self-commit``（封装账本的那次提交）；给出时任何事件
  ``candidate_commit == self_commit`` → 冲突（I.2:2776 "事件不得保存包含自己的
  Git commit SHA"）。未给出时该检查跳过，其余自引用检查（``references`` 含自身
  ``event_id``、envelope 自 hash、correction 悬空引用）始终生效。
- **DAG/Authority 的双轨实现**：脚本内以显式常量 ``DAG`` / ``SPEC_AUTHORITY`` 声明
  （reducer 只用常量）；同时提供 ``parse_index_table`` / ``parse_dependencies``
  解析 ``00-execution-index.md`` §3 表格，``verify_index`` 逐项比对并在漂移时报冲突。
  解析器处理 ``02–08``（en dash 区间）、``+``、``—``、以及非纯前置的附加条件文本。
- **``Cycle 1 COMPLETE + real L2/L3 issue`` 一类单元格**：不以枚举特判；只有整格
  形如 ``NN[–NN] [+ NN[–NN] ...] COMPLETE`` 才展开为前置集合，否则整格作为
  "附加条件文本"（``extra_conditions``），前置集合为空——不发明不存在的 spec 依赖。
- **新行处理**：解析时 CRLF/CR 归一为 LF（复用 Spec 03 共享规范化约定）；
  append-only 的逐字节一致性检查**用原始字节**，不受归一影响。
- **BOM**：拒绝（"文件严格 UTF-8" + canonical JSON；BOM 使首行不合法）。
- **空行**：``strip() == ""`` 的行跳过（"每个非空行"），不计入事件数。

本脚本只读账本与子 Spec，不写任何文件、不调用真实模型、不访问另一仓。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

#: 直接以脚本方式运行时 ``sys.path[0]`` 是脚本所在目录，仓库根不在其中
#: （只有 ``python -m`` 才把 CWD 放进 sys.path）。Spec 10 的权威命令形如
#: ``python scripts/contracts/status_ledger.py ...``，因此必须自行自举，
#: 否则 ``import agent_core`` 会 ModuleNotFoundError。不得依赖 editable install
#: 的副作用（两仓都提供顶层 ``agent_core``，同一解释器里无法同时可编辑安装）。
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
REPO_ROOT = _REPO_ROOT


def _force_utf8_streams() -> None:
    """把 stdout/stderr 强制为 UTF-8。

    GitHub Actions 的 Windows runner 默认 stdout 编码是 cp1252；本 reducer 的冲突信息与
    状态表含中文，直接 ``print`` 会 ``UnicodeEncodeError`` 并掩盖真正的 ``SPEC_STATUS_CONFLICT``
    判定。coordinate workflow 会在 Windows runner 上调用本脚本，故入口处统一处理。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


from agent_core.contracts.models.evidence import (  # noqa: E402  (自举之后才能 import)
    REPOSITORY_COMMIT_PATTERN,
    TIMESTAMP_PATTERN,
    is_canonical_event_id,
    normalize_event_id,
)
from agent_core.contracts.tooling.canonical_json import (  # noqa: E402
    canonical_json_dumps,
    normalize_text,
    sha256_hex,
)

__all__ = [
    "AUTHORITY_FEEDBACK_BOUND",
    "AUTHORITY_GATE_DEFINED",
    "AUTHORITY_IMPLEMENTATION_READY",
    "DAG",
    "EVENT_FIELDS",
    "EXECUTABLE_AUTHORITIES",
    "INDEX_FILENAME",
    "LEDGER_FILENAME",
    "NON_EXECUTABLE_AUTHORITIES",
    "PENDING_ENVELOPE_FIELDS",
    "PENDING_ENVELOPE_FILENAME",
    "PENDING_ENVELOPE_VERSION",
    "PENDING_JSONL_FILENAME",
    "REASON_CODES",
    "SPEC_AUTHORITY",
    "SPEC_IDS",
    "STATUSES",
    "TARGET_BOUNDARIES",
    "VALIDATED_UNLOCK_ALLOWED",
    "Dependency",
    "IndexRow",
    "LedgerConfigError",
    "LedgerConflict",
    "LedgerReport",
    "StatusEvent",
    "assert_suffix_appended",
    "canonical_pending_paths",
    "compute_suffix_hash",
    "count_nonempty_lines",
    "main",
    "parse_dependencies",
    "parse_event_line",
    "parse_event_lines",
    "parse_index_table",
    "parse_initial_status",
    "parse_pending_envelope",
    "read_genesis",
    "reduce_events",
    "reduce_ledger_bytes",
    "reduce_ledger_files",
    "verify_index",
]

# --------------------------------------------------------------------------- #
# 0. 路径与闭集
# --------------------------------------------------------------------------- #

#: 权威账本路径（Index 顶部 + I.1）。
LEDGER_FILENAME: Final[str] = "execution-status-events.jsonl"

#: 执行索引文件名（DAG/Authority/Initial Status 的规范来源）。
INDEX_FILENAME: Final[str] = "00-execution-index.md"

#: 子 Spec 编号闭集（01–18）。
SPEC_IDS: Final[tuple[str, ...]] = tuple(f"{index:02d}" for index in range(1, 19))

#: 状态闭集（I.2:2778-2788）。
STATUSES: Final[tuple[str, ...]] = (
    "NOT_STARTED",
    "READY",
    "IN_PROGRESS",
    "BLOCKED",
    "VALIDATED",
    "COMPLETE",
    "SUPERSEDED",
)

#: 主路径（跳过强制阶段检测用）。
MAIN_PATH: Final[tuple[str, ...]] = (
    "NOT_STARTED",
    "READY",
    "IN_PROGRESS",
    "VALIDATED",
    "COMPLETE",
)

#: 14 个 reason_code 闭集（I.2:2790-2807）。
REASON_CODES: Final[tuple[str, ...]] = (
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

#: Event Schema 的 10 个字段（I.2:2757-2776）；未知字段与缺字段都是冲突。
EVENT_FIELDS: Final[tuple[str, ...]] = (
    "event_id",
    "spec_id",
    "from_status",
    "to_status",
    "candidate_commit",
    "evidence_refs",
    "timestamp",
    "reason_code",
    "reason",
    "references",
)

#: rule 7：这些理由码无论属于哪个 spec 都必须绑定非空 ``candidate_commit``。
COMMIT_BOUND_REASON_CODES: Final[frozenset[str]] = frozenset(
    {
        "FREEZE_BOUNDARY_REACHED",
        "CANDIDATE_FROZEN",
        "EVIDENCE_PUBLISHED",
        "COORDINATION_PASSED",
        "FINALIZATION_COMPLETE",
    }
)

#: rule 7：Spec 01–11 的 pre-freeze 事件允许 ``candidate_commit = null``；
#: Spec 12–18 属于 post-freeze，必须绑定已存在的候选 A。
CANDIDATE_COMMIT_NULL_ALLOWED_SPECS: Final[frozenset[str]] = frozenset(SPEC_IDS[:11])

#: rule 6：显式允许 "upstream VALIDATED 即解锁" 的 spec。Index §4/§6 声明依赖默认
#: 只由 upstream ``COMPLETE`` 解锁，且没有任何子 Spec 声明例外 → 空集。
VALIDATED_UNLOCK_ALLOWED: Final[frozenset[str]] = frozenset()

#: Index §3 Authority 列的三个闭集取值（原样字符串，不做归一）。
AUTHORITY_IMPLEMENTATION_READY: Final[str] = "IMPLEMENTATION-READY"
AUTHORITY_FEEDBACK_BOUND: Final[str] = "FEEDBACK-BOUND / PROCESS-ONLY"
AUTHORITY_GATE_DEFINED: Final[str] = "GATE-DEFINED / NOT EXECUTABLE YET"

#: 可执行 authority（Index §2：Executable = YES）。
EXECUTABLE_AUTHORITIES: Final[frozenset[str]] = frozenset({AUTHORITY_IMPLEMENTATION_READY})

#: 非可执行 authority（rule 6：不能仅因状态变化获得实施权限）。
NON_EXECUTABLE_AUTHORITIES: Final[frozenset[str]] = frozenset(
    {AUTHORITY_FEEDBACK_BOUND, AUTHORITY_GATE_DEFINED}
)

#: 非可执行 authority 允许出现的状态（rule 6 的收紧实现）。
NON_EXECUTABLE_STATUSES: Final[frozenset[str]] = frozenset(
    {"NOT_STARTED", "READY", "BLOCKED"}
)

#: pending envelope 的字段闭集与版本（G-03 provisional）。
PENDING_ENVELOPE_FIELDS: Final[tuple[str, ...]] = (
    "pending_version",
    "target_boundary",
    "candidate_commit",
    "event_count",
    "suffix_hash",
)
PENDING_ENVELOPE_VERSION: Final[str] = "1"

#: suffix 目标持久化边界（I.4 边界表）。
TARGET_BOUNDARIES: Final[frozenset[str]] = frozenset(
    {"candidate_a", "evidence_b_wiki", "finalization_c_wiki"}
)

#: **G-03 冻结**：pending suffix 的规范化文件名，与 canonical ledger **同目录**。
#:
#: 母 Spec 只规定 suffix 必须"由同一 Candidate A 的 reducer 生成/验证、记录目标持久化边界、
#: 具备自身 canonical hash"，未规定载体路径。Spec 11 Stage 0 把下面的命名冻结为规范载体：
#: Spec 11（freeze boundary 条目）、Spec 12/13（12/13 完成事件）都必须写这两个文件，
#: coordinator 与审计者据此无歧义定位 suffix。
#: CLI 的 ``--pending-jsonl`` / ``--pending-envelope`` 仍可指向任意路径（synthetic fixture 与
#: 受控 staging 需要），但**持久化边界只接受上面这两个名字**。
PENDING_JSONL_FILENAME: Final[str] = "execution-status-events.pending.jsonl"
PENDING_ENVELOPE_FILENAME: Final[str] = "execution-status-events.pending.json"


def canonical_pending_paths(ledger_path: Path | str) -> tuple[Path, Path]:
    """返回该账本对应的规范化 pending suffix 路径 ``(jsonl, envelope)``。

    与 ``--ledger`` 同目录；两个文件名已冻结（见 ``PENDING_JSONL_FILENAME``）。
    """
    directory = Path(ledger_path).parent
    return directory / PENDING_JSONL_FILENAME, directory / PENDING_ENVELOPE_FILENAME

# --------------------------------------------------------------------------- #
# 1. 违规规则标识（错误信息必须携带：行号 + event_id + 规则）
# --------------------------------------------------------------------------- #

RULE_1_EVENT_SCHEMA: Final[str] = "RULE_1_EVENT_SCHEMA"
RULE_2_DUPLICATE_EVENT_ID: Final[str] = "RULE_2_DUPLICATE_EVENT_ID"
RULE_3_FROM_STATUS_MISMATCH: Final[str] = "RULE_3_FROM_STATUS_MISMATCH"
RULE_4_ILLEGAL_TRANSITION: Final[str] = "RULE_4_ILLEGAL_TRANSITION"
RULE_4_SKIPPED_MANDATORY_STAGE: Final[str] = "RULE_4_SKIPPED_MANDATORY_STAGE"
RULE_4_MUTUALLY_EXCLUSIVE_SUCCESSOR: Final[str] = "RULE_4_MUTUALLY_EXCLUSIVE_SUCCESSOR"
RULE_4_CORRECTION_WITHOUT_REFERENCE: Final[str] = "RULE_4_CORRECTION_WITHOUT_REFERENCE"
RULE_4_CORRECTION_DANGLING_REFERENCE: Final[str] = (
    "RULE_4_CORRECTION_DANGLING_REFERENCE"
)
RULE_5_VALIDATED_WITHOUT_EVIDENCE: Final[str] = "RULE_5_VALIDATED_WITHOUT_EVIDENCE"
RULE_6_MISSING_PREREQUISITE: Final[str] = "RULE_6_MISSING_PREREQUISITE"
RULE_6_AUTHORITY_NOT_EXECUTABLE: Final[str] = "RULE_6_AUTHORITY_NOT_EXECUTABLE"
RULE_7_CANDIDATE_COMMIT_REQUIRED: Final[str] = "RULE_7_CANDIDATE_COMMIT_REQUIRED"
RULE_7_SELF_COMMIT_REFERENCE: Final[str] = "RULE_7_SELF_COMMIT_REFERENCE"
RULE_7_SELF_EVENT_REFERENCE: Final[str] = "RULE_7_SELF_EVENT_REFERENCE"
RULE_GOV_INDEX_MISMATCH: Final[str] = "GOV_INDEX_MISMATCH"
RULE_GOV_INDEX_GENESIS_MISMATCH: Final[str] = "GOV_INDEX_GENESIS_MISMATCH"
RULE_PENDING_ENVELOPE_SCHEMA: Final[str] = "PENDING_1_ENVELOPE_SCHEMA"
RULE_PENDING_HASH_MISMATCH: Final[str] = "PENDING_2_SUFFIX_HASH_MISMATCH"
RULE_PENDING_COUNT_MISMATCH: Final[str] = "PENDING_2_EVENT_COUNT_MISMATCH"
RULE_PENDING_CANDIDATE_MISMATCH: Final[str] = "PENDING_3_CANDIDATE_MISMATCH"
RULE_PENDING_CANDIDATE_SUPERSEDED: Final[str] = "PENDING_3_CANDIDATE_SUPERSEDED"
RULE_PENDING_APPEND_MISMATCH: Final[str] = "PENDING_4_APPEND_MISMATCH"

#: 8 条 reducer 规则 ↔ 治理规则 ID（I.5，仅作文档/错误信息标注，不进 Payload）。
RULE_GOVERNANCE_SOURCE: Final[Mapping[str, str]] = {
    RULE_1_EVENT_SCHEMA: "GOV-STAT-001",
    RULE_2_DUPLICATE_EVENT_ID: "GOV-STAT-001",
    RULE_3_FROM_STATUS_MISMATCH: "GOV-STAT-001/GOV-STAT-003",
    RULE_4_ILLEGAL_TRANSITION: "GOV-STAT-003",
    RULE_4_SKIPPED_MANDATORY_STAGE: "GOV-STAT-003",
    RULE_4_MUTUALLY_EXCLUSIVE_SUCCESSOR: "GOV-STAT-003",
    RULE_4_CORRECTION_WITHOUT_REFERENCE: "GOV-STAT-004",
    RULE_4_CORRECTION_DANGLING_REFERENCE: "GOV-STAT-004",
    RULE_5_VALIDATED_WITHOUT_EVIDENCE: "GOV-STAT-003",
    RULE_6_MISSING_PREREQUISITE: "GOV-STAT-003",
    RULE_6_AUTHORITY_NOT_EXECUTABLE: "GOV-STAT-003",
    RULE_7_CANDIDATE_COMMIT_REQUIRED: "GOV-FRZ-001",
    RULE_7_SELF_COMMIT_REFERENCE: "GOV-STAT-004",
    RULE_7_SELF_EVENT_REFERENCE: "GOV-STAT-004",
    RULE_GOV_INDEX_MISMATCH: "GOV-SPEC-002",
    RULE_GOV_INDEX_GENESIS_MISMATCH: "GOV-STAT-002",
    RULE_PENDING_ENVELOPE_SCHEMA: "GOV-STAT-004",
    RULE_PENDING_HASH_MISMATCH: "GOV-STAT-004",
    RULE_PENDING_COUNT_MISMATCH: "GOV-STAT-004",
    RULE_PENDING_CANDIDATE_MISMATCH: "GOV-STAT-003",
    RULE_PENDING_CANDIDATE_SUPERSEDED: "GOV-STAT-003",
    RULE_PENDING_APPEND_MISMATCH: "GOV-STAT-004",
}

# --------------------------------------------------------------------------- #
# 2. 异常
# --------------------------------------------------------------------------- #


class LedgerError(Exception):
    """账本工具的错误基类。"""


class LedgerConflict(LedgerError):
    """非法事件 / 非法 envelope / 非法 append → ``SPEC_STATUS_CONFLICT``（退出 1）。"""

    symbol: Final[str] = "SPEC_STATUS_CONFLICT"

    def __init__(self, rule: str, detail: str, *, origin: str = "", line_no: int | None = None,
                 event_id: str | None = None) -> None:
        self.rule = rule
        self.detail = detail
        self.origin = origin
        self.line_no = line_no
        self.event_id = event_id
        governance = RULE_GOVERNANCE_SOURCE.get(rule, "GOV-STAT-003")
        location = f"{origin or '<memory>'}:{line_no if line_no is not None else '-'}"
        message = (
            f"{self.symbol}: {location} rule={rule} ({governance}) "
            f"event_id={event_id if event_id else '<n/a>'} :: {detail}"
        )
        super().__init__(message)


class LedgerConfigError(LedgerError):
    """用法 / 配置 / genesis 规范缺失 → ``SPEC_INCOMPLETE``（退出 2）。"""

    symbol: Final[str] = "SPEC_INCOMPLETE"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"{self.symbol}: {detail}")


def _conflict(
    origin: str,
    line_no: int | None,
    rule: str,
    event_id: str | None,
    detail: str,
) -> LedgerConflict:
    return LedgerConflict(rule, detail, origin=origin, line_no=line_no, event_id=event_id)


# --------------------------------------------------------------------------- #
# 3. DAG 与 Authority 的显式常量（规范来源：00-execution-index.md §3）
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Dependency:
    """``Depends On`` 单元格的解析结果。

    ``raw`` 保留单元格原文（供逐字比对 Index 表格）；
    ``prerequisites`` 是可由 DAG 状态机械检验的 spec 前置集合；
    ``extra_conditions`` 是**非纯前置**的附加条件文本（如 "Cycle 1 COMPLETE +
    real L2/L3 issue"）——它不可由账本机械判定，故只记录不归约。
    """

    raw: str
    prerequisites: tuple[str, ...] = ()
    extra_conditions: tuple[str, ...] = ()


#: 显式 DAG 常量：键为 spec_id，值为 ``Dependency``。
#: 与 Index §3 的 ``Depends On`` 列逐项一致（测试 ``test_index_constants_match_execution_index``）。
DAG: Final[Mapping[str, Dependency]] = {
    "01": Dependency("—"),
    "02": Dependency("01 COMPLETE", ("01",)),
    "03": Dependency("02 COMPLETE", ("02",)),
    "04": Dependency("02 + 03 COMPLETE", ("02", "03")),
    "05": Dependency("04 COMPLETE", ("04",)),
    "06": Dependency("04 COMPLETE", ("04",)),
    "07": Dependency("05 COMPLETE", ("05",)),
    "08": Dependency("06 COMPLETE", ("06",)),
    "09": Dependency(
        "02–08 COMPLETE",
        ("02", "03", "04", "05", "06", "07", "08"),
    ),
    "10": Dependency("09 COMPLETE", ("09",)),
    "11": Dependency("10 COMPLETE", ("10",)),
    "12": Dependency("11 COMPLETE", ("11",)),
    "13": Dependency("11 COMPLETE", ("11",)),
    "14": Dependency("11 + 12 + 13 COMPLETE", ("11", "12", "13")),
    "15": Dependency("14 COMPLETE", ("14",)),
    "16": Dependency(
        "Cycle 1 COMPLETE + real L2/L3 issue",
        (),
        ("Cycle 1 COMPLETE + real L2/L3 issue",),
    ),
    "17": Dependency(
        "Foundation C1 + C2 COMPLETE",
        (),
        ("Foundation C1 + C2 COMPLETE",),
    ),
    "18": Dependency(
        "Foundation boundary sufficiently stable",
        (),
        ("Foundation boundary sufficiently stable",),
    ),
}

#: 显式 Authority 常量：与 Index §3 的 ``Authority`` 列逐项一致。
SPEC_AUTHORITY: Final[Mapping[str, str]] = {
    "01": AUTHORITY_IMPLEMENTATION_READY,
    "02": AUTHORITY_IMPLEMENTATION_READY,
    "03": AUTHORITY_IMPLEMENTATION_READY,
    "04": AUTHORITY_IMPLEMENTATION_READY,
    "05": AUTHORITY_IMPLEMENTATION_READY,
    "06": AUTHORITY_IMPLEMENTATION_READY,
    "07": AUTHORITY_IMPLEMENTATION_READY,
    "08": AUTHORITY_IMPLEMENTATION_READY,
    "09": AUTHORITY_IMPLEMENTATION_READY,
    "10": AUTHORITY_IMPLEMENTATION_READY,
    "11": AUTHORITY_IMPLEMENTATION_READY,
    "12": AUTHORITY_IMPLEMENTATION_READY,
    "13": AUTHORITY_IMPLEMENTATION_READY,
    "14": AUTHORITY_IMPLEMENTATION_READY,
    "15": AUTHORITY_IMPLEMENTATION_READY,
    "16": AUTHORITY_FEEDBACK_BOUND,
    "17": AUTHORITY_GATE_DEFINED,
    "18": AUTHORITY_GATE_DEFINED,
}

# --------------------------------------------------------------------------- #
# 4. 状态转换与理由码耦合（I.3 规则 4/8）
# --------------------------------------------------------------------------- #

#: 静态合法转换 → 允许的理由码集合。``BLOCKED`` 相关的转换在运行时另行判定
#: （解除阻塞必须回到**该 spec 进入 BLOCKED 之前**的状态）。
#:
#: **G-22 冻结**：母 Spec 的 rule 4/8 要求判定"互斥后继"，却从未把 14 个 reason_code 映射到
#: 状态转换；本表是 Spec 10 的发明，已在 Spec 11 Stage 0 校准中冻结（见
#: ``docs/plans/2026-09-16-foundation-contract-spec11-stage0-calibration.md``）。
#: ``tests/contracts/test_status_ledger.py::TestFrozenSurface`` 用字面量表把它钉住 ——
#: 任何改动都会显式让测试失败，而不是悄悄漂移。
REASON_BY_TRANSITION: Final[Mapping[tuple[str, str], frozenset[str]]] = {
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

#: 进入 ``BLOCKED`` 允许的理由码。
BLOCK_REASON_CODES: Final[frozenset[str]] = frozenset(
    {"BLOCKED", "SPEC_CONFLICT", "SPEC_INCOMPLETE"}
)

#: 解除 ``BLOCKED`` 允许的理由码（provisional，见模块 docstring）。
UNBLOCK_REASON_CODES: Final[frozenset[str]] = frozenset(
    {"PREREQUISITES_SATISFIED", "EXECUTION_STARTED"}
)

#: 进入 ``SUPERSEDED`` 的合法起点。
SUPERSEDE_FROM_STATUSES: Final[frozenset[str]] = frozenset(
    {"READY", "IN_PROGRESS", "BLOCKED", "VALIDATED", "COMPLETE"}
)

#: 进入 ``SUPERSEDED`` 与 A2 重启允许的理由码。
SUPERSEDE_REASON_CODES: Final[frozenset[str]] = frozenset({"CANDIDATE_SUPERSEDED"})

# --------------------------------------------------------------------------- #
# 5. 索引表格解析（Index §3）
# --------------------------------------------------------------------------- #

#: ``NN`` 或 ``NN–NN``（en dash / em dash / hyphen 都接受）。
_DEP_ITEM_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<start>\d{2})(?:\s*[\u2013\u2014-]\s*(?P<end>\d{2}))?$"
)

#: 单元格以 ``COMPLETE`` 收尾（前置纯表达式的必要条件）。
_COMPLETE_SUFFIX: Final[str] = "COMPLETE"

#: ``> Initial Status：`NOT_STARTED```（全角/半角冒号、反引号、多空格都接受）。
_INITIAL_STATUS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^Initial\s+Status\s*[:：]\s*[`\"']?\s*(?P<status>[A-Z][A-Z_]*)\s*[`\"']?$"
)

#: ``Depends On`` 单元格中表示"无前置"的占位符。
_NO_DEPENDENCY_TOKENS: Final[frozenset[str]] = frozenset({"", "—", "–", "-"})


@dataclass(frozen=True)
class IndexRow:
    """``00-execution-index.md`` §3 表格的一行。"""

    spec_id: str
    authority: str
    initial_status: str
    depends_on_raw: str
    line_no: int

    @property
    def dependency(self) -> Dependency:
        return parse_dependencies(self.depends_on_raw)


def parse_dependencies(raw: str) -> Dependency:
    """解析 ``Depends On`` 单元格 → :class:`Dependency`。

    只有整格形如 ``NN[–NN] [+ NN[–NN] ...] COMPLETE`` 时才展开为前置集合；
    其余（含 ``Cycle 1 COMPLETE + real L2/L3 issue``、``Foundation C1 + C2
    COMPLETE``、``Foundation boundary sufficiently stable``）整格作为附加条件文本，
    前置集合为空——规范未把这些文本映射到 spec 编号，本实现不自行发明依赖。
    """
    text = raw.replace("\u3000", " ").strip()
    if text in _NO_DEPENDENCY_TOKENS:
        return Dependency(raw=raw)

    if text.upper().endswith(_COMPLETE_SUFFIX):
        prefix = text[: -len(_COMPLETE_SUFFIX)].strip()
        items = [item.strip() for item in prefix.split("+")] if prefix else []
        expanded: set[str] = set()
        for item in items:
            match = _DEP_ITEM_PATTERN.match(item)
            if match is None:
                expanded = set()
                break
            start = int(match.group("start"))
            end = int(match.group("end")) if match.group("end") else start
            if not (1 <= start <= end <= 18):
                expanded = set()
                break
            expanded.update(f"{number:02d}" for number in range(start, end + 1))
        if expanded:
            return Dependency(raw=raw, prerequisites=tuple(sorted(expanded)))

    return Dependency(raw=raw, prerequisites=(), extra_conditions=(text,))


def parse_initial_status(text: str) -> str | None:
    """从子 Spec 头部解析 ``> Initial Status：`XXX``` 行；解析不到返回 ``None``。

    接受全角冒号、反引号/引号包裹、多空格与全角空格。
    """
    for line in normalize_text(text).split("\n"):
        stripped = line.replace("\u3000", " ").strip()
        if not stripped.startswith(">"):
            continue
        match = _INITIAL_STATUS_PATTERN.match(stripped[1:].strip())
        if match is not None:
            return match.group("status")
    return None


def parse_index_table(text: str) -> dict[str, IndexRow]:
    """解析 ``00-execution-index.md`` §3 的子 Spec 表格 → ``{spec_id: IndexRow}``。"""
    rows: dict[str, IndexRow] = {}
    for line_no, line in enumerate(normalize_text(text).split("\n"), start=1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 5:
            continue
        spec_id = cells[0]
        if spec_id not in SPEC_IDS:
            continue
        rows[spec_id] = IndexRow(
            spec_id=spec_id,
            authority=cells[2],
            initial_status=cells[3],
            depends_on_raw=cells[4],
            line_no=line_no,
        )
    return rows


# --------------------------------------------------------------------------- #
# 6. 文件读取与 genesis
# --------------------------------------------------------------------------- #


def _decode_strict(raw: bytes, origin: str) -> str:
    """严格 UTF-8 解码；BOM 与非法字节都是冲突（rule 1）。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        raise _conflict(origin, 1, RULE_1_EVENT_SCHEMA, None, "UTF-8 BOM is not allowed")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _conflict(
            origin,
            1,
            RULE_1_EVENT_SCHEMA,
            None,
            f"file is not strict UTF-8: {exc}",
        ) from exc


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except FileNotFoundError as exc:
        raise LedgerConfigError(f"{label} not found: {path}") from exc
    except OSError as exc:  # pragma: no cover - 权限/设备错误
        raise LedgerConfigError(f"{label} unreadable: {path} ({exc})") from exc


def _split_lines(raw: bytes, origin: str) -> list[tuple[int, str]]:
    """按 LF 归一后切行，返回 ``(行号, 行文本)``（行号从 1 开始）。"""
    text = normalize_text(_decode_strict(raw, origin))
    return list(enumerate(text.split("\n"), start=1))


def count_nonempty_lines(raw: bytes, origin: str = "<memory>") -> int:
    """统计非空行数（``strip() == ""`` 视为空行）。"""
    return sum(1 for _, line in _split_lines(raw, origin) if line.strip())


def read_genesis(spec_dir: Path) -> dict[str, str]:
    """GOV-STAT-002：从 18 个子 Spec 文件的 ``Initial Status`` 行解析 genesis。

    解析失败/文件缺失 → :class:`LedgerConfigError`（退出 2），**不静默兜底**。
    ``00-execution-index.md`` 的 Initial Status 是"不适用"，不参与。
    """
    directory = Path(spec_dir)
    if not directory.is_dir():
        raise LedgerConfigError(f"child spec directory not found: {directory}")

    statuses: dict[str, str] = {}
    for spec_id in SPEC_IDS:
        matches = sorted(directory.glob(f"{spec_id}-*.md"))
        if len(matches) != 1:
            raise LedgerConfigError(
                f"exactly one child spec file required for Spec {spec_id} in "
                f"{directory} (found {len(matches)})"
            )
        path = matches[0]
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LedgerConfigError(f"child spec is not strict UTF-8: {path} ({exc})") from exc
        except OSError as exc:  # pragma: no cover
            raise LedgerConfigError(f"child spec unreadable: {path} ({exc})") from exc
        status = parse_initial_status(text)
        if status is None:
            raise LedgerConfigError(
                f"cannot parse '> Initial Status' header in {path}"
            )
        if status not in STATUSES:
            raise LedgerConfigError(
                f"unknown Initial Status {status!r} in {path} "
                f"(closed set: {', '.join(STATUSES)})"
            )
        statuses[spec_id] = status
    return statuses


def verify_index(index_path: Path, genesis: Mapping[str, str] | None = None) -> dict[str, IndexRow]:
    """把显式常量与 ``00-execution-index.md`` §3 表格逐项比对；漂移即冲突。"""
    path = Path(index_path)
    raw = _read_bytes(path, "execution index")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LedgerConfigError(f"execution index is not strict UTF-8: {path} ({exc})") from exc

    origin = str(path)
    rows = parse_index_table(text)
    if set(rows) != set(SPEC_IDS):
        missing = sorted(set(SPEC_IDS) - set(rows))
        extra = sorted(set(rows) - set(SPEC_IDS))
        raise _conflict(
            origin,
            None,
            RULE_GOV_INDEX_MISMATCH,
            None,
            f"spec table rows do not cover 01–18 (missing={missing}, extra={extra})",
        )

    for spec_id in SPEC_IDS:
        row = rows[spec_id]
        if row.authority != SPEC_AUTHORITY[spec_id]:
            raise _conflict(
                origin,
                row.line_no,
                RULE_GOV_INDEX_MISMATCH,
                None,
                f"Spec {spec_id} Authority drift: index={row.authority!r} "
                f"constant={SPEC_AUTHORITY[spec_id]!r}",
            )
        if row.depends_on_raw != DAG[spec_id].raw:
            raise _conflict(
                origin,
                row.line_no,
                RULE_GOV_INDEX_MISMATCH,
                None,
                f"Spec {spec_id} Depends On drift: index={row.depends_on_raw!r} "
                f"constant={DAG[spec_id].raw!r}",
            )
        parsed = row.dependency
        if parsed != DAG[spec_id]:
            raise _conflict(
                origin,
                row.line_no,
                RULE_GOV_INDEX_MISMATCH,
                None,
                f"Spec {spec_id} dependency parse drift: index={parsed!r} "
                f"constant={DAG[spec_id]!r}",
            )
        if genesis is not None and row.initial_status != genesis[spec_id]:
            raise _conflict(
                origin,
                row.line_no,
                RULE_GOV_INDEX_GENESIS_MISMATCH,
                None,
                f"Spec {spec_id} Initial Status drift: index={row.initial_status!r} "
                f"child-spec genesis={genesis[spec_id]!r}",
            )
    return rows


# --------------------------------------------------------------------------- #
# 7. Event Schema
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StatusEvent:
    """一条已通过 rule 1 校验的状态事件（外加来源行号）。"""

    event_id: str
    spec_id: str
    from_status: str
    to_status: str
    candidate_commit: str | None
    evidence_refs: tuple[str, ...]
    timestamp: str
    reason_code: str
    reason: str
    references: tuple[str, ...]
    origin: str
    line_no: int

    def identity(self) -> str:
        return normalize_event_id(self.event_id)


def _require_string_list(
    value: Any, field: str, origin: str, line_no: int, event_id: str | None
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _conflict(
            origin, line_no, RULE_1_EVENT_SCHEMA, event_id, f"{field} must be a JSON array"
        )
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise _conflict(
                origin,
                line_no,
                RULE_1_EVENT_SCHEMA,
                event_id,
                f"{field} entries must be non-empty strings",
            )
        items.append(item.strip())
    return tuple(items)


def parse_event_line(line: str, *, origin: str, line_no: int) -> StatusEvent:
    """rule 1：单行 → :class:`StatusEvent`；任何 schema 违规都是冲突。"""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise _conflict(
            origin, line_no, RULE_1_EVENT_SCHEMA, None, f"line is not valid JSON: {exc.msg}"
        ) from exc

    if not isinstance(payload, dict):
        raise _conflict(
            origin, line_no, RULE_1_EVENT_SCHEMA, None, "line is not a JSON object"
        )

    keys = set(payload)
    expected = set(EVENT_FIELDS)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing:
        raise _conflict(
            origin,
            line_no,
            RULE_1_EVENT_SCHEMA,
            payload.get("event_id") if isinstance(payload.get("event_id"), str) else None,
            f"missing required field(s): {', '.join(missing)}",
        )
    if unknown:
        raise _conflict(
            origin,
            line_no,
            RULE_1_EVENT_SCHEMA,
            payload.get("event_id") if isinstance(payload.get("event_id"), str) else None,
            f"unknown field(s) not in Event Schema: {', '.join(unknown)}",
        )
    if canonical_json_dumps(payload) != line.strip():
        raise _conflict(
            origin,
            line_no,
            RULE_1_EVENT_SCHEMA,
            payload.get("event_id") if isinstance(payload.get("event_id"), str) else None,
            "line is not canonical JSON (keys must be sorted, compact separators, no extra spacing)",
        )

    event_id = payload["event_id"]
    if not is_canonical_event_id(event_id):
        raise _conflict(
            origin,
            line_no,
            RULE_1_EVENT_SCHEMA,
            None,
            f"event_id must be a canonical UUID or a 26-char Crockford ULID (got {event_id!r})",
        )

    spec_id = payload["spec_id"]
    if spec_id not in SPEC_IDS:
        raise _conflict(
            origin,
            line_no,
            RULE_1_EVENT_SCHEMA,
            event_id,
            f"spec_id must be '01'..'18' (got {spec_id!r})",
        )

    from_status = payload["from_status"]
    to_status = payload["to_status"]
    for field, value in (("from_status", from_status), ("to_status", to_status)):
        if value not in STATUSES:
            raise _conflict(
                origin,
                line_no,
                RULE_1_EVENT_SCHEMA,
                event_id,
                f"{field} must be one of {', '.join(STATUSES)} (got {value!r})",
            )

    candidate_commit = payload["candidate_commit"]
    if candidate_commit is not None and (
        not isinstance(candidate_commit, str)
        or REPOSITORY_COMMIT_PATTERN.match(candidate_commit) is None
    ):
        raise _conflict(
            origin,
            line_no,
            RULE_1_EVENT_SCHEMA,
            event_id,
            "candidate_commit must be null or a 40-char lowercase hex commit",
        )

    evidence_refs = _require_string_list(
        payload["evidence_refs"], "evidence_refs", origin, line_no, event_id
    )
    references = _require_string_list(
        payload["references"], "references", origin, line_no, event_id
    )

    timestamp = payload["timestamp"]
    if not isinstance(timestamp, str) or TIMESTAMP_PATTERN.match(timestamp) is None:
        raise _conflict(
            origin,
            line_no,
            RULE_1_EVENT_SCHEMA,
            event_id,
            f"timestamp must be RFC3339 with timezone (got {timestamp!r})",
        )
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _conflict(
            origin, line_no, RULE_1_EVENT_SCHEMA, event_id, f"timestamp is not a real date: {exc}"
        ) from exc

    reason_code = payload["reason_code"]
    if reason_code not in REASON_CODES:
        raise _conflict(
            origin,
            line_no,
            RULE_1_EVENT_SCHEMA,
            event_id,
            f"reason_code must be one of the 14-value closed set (got {reason_code!r})",
        )

    reason = payload["reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise _conflict(
            origin, line_no, RULE_1_EVENT_SCHEMA, event_id, "reason must be a non-empty string"
        )

    return StatusEvent(
        event_id=event_id,
        spec_id=spec_id,
        from_status=from_status,
        to_status=to_status,
        candidate_commit=candidate_commit,
        evidence_refs=evidence_refs,
        timestamp=timestamp,
        reason_code=reason_code,
        reason=reason,
        references=references,
        origin=origin,
        line_no=line_no,
    )


def parse_event_lines(raw: bytes, *, origin: str) -> list[StatusEvent]:
    """rule 1 + rule 2 的解析入口：空行跳过，其余每行必须是合法事件。"""
    events: list[StatusEvent] = []
    seen: dict[str, StatusEvent] = {}
    for line_no, line in _split_lines(raw, origin):
        if not line.strip():
            continue
        event = parse_event_line(line, origin=origin, line_no=line_no)
        identity = event.identity()
        if identity in seen:
            previous = seen[identity]
            raise _conflict(
                origin,
                line_no,
                RULE_2_DUPLICATE_EVENT_ID,
                event.event_id,
                f"event_id already used at {previous.origin}:{previous.line_no} "
                "(event_id must be globally unique)",
            )
        seen[identity] = event
        events.append(event)
    return events


# --------------------------------------------------------------------------- #
# 8. pending suffix（G-03 provisional 载体）
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PendingEnvelope:
    """``*.pending.json`` envelope（provisional，见模块 docstring）。"""

    pending_version: str
    target_boundary: str
    candidate_commit: str
    event_count: int
    suffix_hash: str


def compute_suffix_hash(pending_bytes: bytes) -> str:
    """suffix hash = 对 ``.jsonl`` **原始字节**的 ``sha256:<hex>``（envelope 不参与）。"""
    return sha256_hex(pending_bytes)


def parse_pending_envelope(raw: bytes) -> PendingEnvelope:
    """解析并校验 envelope（字段闭集、canonical JSON、取值闭集）。"""
    origin = "pending-envelope"
    text = _decode_strict(raw, origin)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _conflict(
            origin, None, RULE_PENDING_ENVELOPE_SCHEMA, None, f"not valid JSON: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise _conflict(
            origin, None, RULE_PENDING_ENVELOPE_SCHEMA, None, "envelope is not a JSON object"
        )
    keys = set(payload)
    expected = set(PENDING_ENVELOPE_FIELDS)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing or unknown:
        raise _conflict(
            origin,
            None,
            RULE_PENDING_ENVELOPE_SCHEMA,
            None,
            f"envelope fields drift (missing={missing}, unknown={unknown}); "
            f"required={list(PENDING_ENVELOPE_FIELDS)}",
        )
    if canonical_json_dumps(payload) != text.strip():
        raise _conflict(
            origin,
            None,
            RULE_PENDING_ENVELOPE_SCHEMA,
            None,
            "envelope is not canonical JSON (keys must be sorted, compact separators)",
        )

    version = payload["pending_version"]
    if str(version) != PENDING_ENVELOPE_VERSION:
        raise _conflict(
            origin,
            None,
            RULE_PENDING_ENVELOPE_SCHEMA,
            None,
            f"pending_version must be {PENDING_ENVELOPE_VERSION!r} (got {version!r})",
        )

    boundary = payload["target_boundary"]
    if boundary not in TARGET_BOUNDARIES:
        raise _conflict(
            origin,
            None,
            RULE_PENDING_ENVELOPE_SCHEMA,
            None,
            f"target_boundary must be one of {sorted(TARGET_BOUNDARIES)} (got {boundary!r})",
        )

    candidate = payload["candidate_commit"]
    if not isinstance(candidate, str) or REPOSITORY_COMMIT_PATTERN.match(candidate) is None:
        raise _conflict(
            origin,
            None,
            RULE_PENDING_ENVELOPE_SCHEMA,
            None,
            "candidate_commit must be a 40-char lowercase hex commit (suffix is Candidate-bound)",
        )

    count = payload["event_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise _conflict(
            origin, None, RULE_PENDING_ENVELOPE_SCHEMA, None, "event_count must be a non-negative int"
        )

    suffix_hash = payload["suffix_hash"]
    if not isinstance(suffix_hash, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", suffix_hash) is None:
        raise _conflict(
            origin,
            None,
            RULE_PENDING_ENVELOPE_SCHEMA,
            None,
            "suffix_hash must be 'sha256:<64 lowercase hex>'",
        )

    return PendingEnvelope(
        pending_version=str(version),
        target_boundary=boundary,
        candidate_commit=candidate,
        event_count=count,
        suffix_hash=suffix_hash,
    )


def _candidate_markers(events: Sequence[StatusEvent]) -> tuple[list[str], set[str]]:
    """收集 prefix 中的候选冻结顺序与被取代的候选集合。"""
    frozen: list[str] = []
    superseded: set[str] = set()
    for event in events:
        if not event.candidate_commit:
            continue
        if event.reason_code == "CANDIDATE_FROZEN":
            frozen.append(event.candidate_commit)
        elif event.reason_code == "CANDIDATE_SUPERSEDED":
            superseded.add(event.candidate_commit)
    return frozen, superseded


def check_suffix_candidate_binding(
    prefix_events: Sequence[StatusEvent],
    suffix_events: Sequence[StatusEvent],
    envelope: PendingEnvelope,
) -> None:
    """Candidate 隔离：suffix 只能绑定当前（未被取代的）候选 A，且事件引用一致。"""
    origin = "pending-envelope"
    for event in suffix_events:
        if event.candidate_commit is not None and event.candidate_commit != envelope.candidate_commit:
            raise _conflict(
                event.origin,
                event.line_no,
                RULE_PENDING_CANDIDATE_MISMATCH,
                event.event_id,
                f"event candidate_commit={event.candidate_commit} does not match "
                f"envelope candidate_commit={envelope.candidate_commit}",
            )

    frozen, superseded = _candidate_markers(prefix_events)
    if envelope.candidate_commit in superseded:
        raise _conflict(
            origin,
            None,
            RULE_PENDING_CANDIDATE_SUPERSEDED,
            None,
            f"candidate {envelope.candidate_commit} was superseded in the canonical ledger; "
            "a pending suffix cannot be reused across candidates",
        )
    if frozen and envelope.candidate_commit != frozen[-1]:
        raise _conflict(
            origin,
            None,
            RULE_PENDING_CANDIDATE_MISMATCH,
            None,
            f"envelope candidate_commit={envelope.candidate_commit} is not the current frozen "
            f"candidate {frozen[-1]}",
        )


def assert_suffix_appended(
    ledger_original_bytes: bytes, ledger_new_bytes: bytes, pending_bytes: bytes
) -> None:
    """I.3/I.4：新账本必须 = 旧账本**逐字节前缀** + pending 内容**逐字节相等**。

    多一个字节、少一个字节、顺序改变、内容修改都 → ``SPEC_STATUS_CONFLICT``。
    """
    expected = ledger_original_bytes + pending_bytes
    if ledger_new_bytes == expected:
        return

    origin = "pending-append"
    if len(ledger_new_bytes) > len(expected):
        detail = (
            f"append contains {len(ledger_new_bytes) - len(expected)} unexpected byte(s) "
            f"beyond prefix+suffix (expected {len(expected)} bytes, got {len(ledger_new_bytes)})"
        )
    elif len(ledger_new_bytes) < len(expected):
        detail = (
            f"append is {len(expected) - len(ledger_new_bytes)} byte(s) short of "
            f"prefix+suffix (expected {len(expected)} bytes, got {len(ledger_new_bytes)})"
        )
    else:
        common = 0
        for left, right in zip(ledger_new_bytes, expected):
            if left != right:
                break
            common += 1
        detail = (
            "append bytes differ from prefix+suffix at offset "
            f"{common} (content modified or reordered); suffix must be appended verbatim"
        )

    if not ledger_new_bytes.startswith(ledger_original_bytes):
        detail = "new ledger does not start with the original ledger bytes (not a pure append)"
    raise _conflict(origin, None, RULE_PENDING_APPEND_MISMATCH, None, detail)


# --------------------------------------------------------------------------- #
# 9. reducer
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LedgerReport:
    """归约结果（effective status + pending 标记）。"""

    statuses: Mapping[str, str]
    pending: Mapping[str, bool]
    canonical_event_count: int
    suffix_event_count: int
    used_pending_suffix: bool
    suffix_hash: str | None
    candidate_commit: str | None
    target_boundary: str | None
    authority: Mapping[str, str]

    @property
    def pending_specs(self) -> tuple[str, ...]:
        return tuple(spec_id for spec_id in SPEC_IDS if self.pending.get(spec_id))

    def to_json(self) -> dict[str, Any]:
        return {
            "canonical_event_count": self.canonical_event_count,
            "effective_status": [
                {
                    "spec_id": spec_id,
                    "status": self.statuses[spec_id],
                    "authority": self.authority[spec_id],
                    "pending": bool(self.pending.get(spec_id)),
                }
                for spec_id in SPEC_IDS
            ],
            "pending_suffix": None
            if not self.used_pending_suffix
            else {
                "candidate_commit": self.candidate_commit,
                "event_count": self.suffix_event_count,
                "pending_specs": list(self.pending_specs),
                "suffix_hash": self.suffix_hash,
                "target_boundary": self.target_boundary,
            },
            "spec_count": len(SPEC_IDS),
        }

    def render_text(self) -> str:
        lines = [
            f"{spec_id}: {self.statuses[spec_id]}"
            + (" (pending)" if self.pending.get(spec_id) else "")
            for spec_id in SPEC_IDS
        ]
        lines.append(f"canonical_events: {self.canonical_event_count}")
        if not self.used_pending_suffix:
            lines.append("pending_suffix: none")
        else:
            lines.append(
                "pending_suffix: used "
                f"(target_boundary={self.target_boundary}, "
                f"candidate_commit={self.candidate_commit}, "
                f"events={self.suffix_event_count})"
            )
            lines.append(f"pending_suffix_hash: {self.suffix_hash}")
            lines.append(
                "pending_specs: " + (", ".join(self.pending_specs) or "none")
            )
        return "\n".join(lines)


def _skipped_mandatory_stage(from_status: str, to_status: str) -> bool:
    if from_status not in MAIN_PATH or to_status not in MAIN_PATH:
        return False
    return MAIN_PATH.index(to_status) > MAIN_PATH.index(from_status) + 1


def _check_transition(
    event: StatusEvent,
    current: str,
    block_return: Mapping[str, str],
    known_event_ids: frozenset[str],
) -> None:
    """I.3 规则 4 + 规则 8：转换合法性、理由码耦合、correction 引用。"""
    origin, line_no, event_id = event.origin, event.line_no, event.event_id
    from_status, to_status = event.from_status, event.to_status

    if from_status == to_status:
        raise _conflict(
            origin,
            line_no,
            RULE_4_ILLEGAL_TRANSITION,
            event_id,
            f"no-op transition {from_status} → {to_status} is not a legal status event",
        )

    if to_status == "SUPERSEDED":
        if from_status not in SUPERSEDE_FROM_STATUSES:
            raise _conflict(
                origin,
                line_no,
                RULE_4_ILLEGAL_TRANSITION,
                event_id,
                f"{from_status} → SUPERSEDED is not a legal transition",
            )
        if event.reason_code not in SUPERSEDE_REASON_CODES:
            raise _conflict(
                origin,
                line_no,
                RULE_4_MUTUALLY_EXCLUSIVE_SUCCESSOR,
                event_id,
                f"{from_status} → SUPERSEDED requires reason_code CANDIDATE_SUPERSEDED "
                f"(got {event.reason_code})",
            )
        return

    if from_status == "SUPERSEDED":
        if to_status == "IN_PROGRESS" and event.reason_code in SUPERSEDE_REASON_CODES:
            return
        raise _conflict(
            origin,
            line_no,
            RULE_4_ILLEGAL_TRANSITION,
            event_id,
            f"SUPERSEDED → {to_status} is not a legal transition "
            "(only SUPERSEDED → IN_PROGRESS with CANDIDATE_SUPERSEDED restarts as A2)",
        )

    if from_status == "BLOCKED":
        target = block_return.get(event.spec_id)
        if target is None:
            raise _conflict(
                origin,
                line_no,
                RULE_4_ILLEGAL_TRANSITION,
                event_id,
                "unblock event without a recorded BLOCKED entry for this spec",
            )
        if to_status != target:
            raise _conflict(
                origin,
                line_no,
                RULE_4_ILLEGAL_TRANSITION,
                event_id,
                f"unblock must return to the original execution stage {target} (got {to_status})",
            )
        if event.reason_code not in UNBLOCK_REASON_CODES:
            raise _conflict(
                origin,
                line_no,
                RULE_4_MUTUALLY_EXCLUSIVE_SUCCESSOR,
                event_id,
                f"unblock requires reason_code in {sorted(UNBLOCK_REASON_CODES)} "
                f"(got {event.reason_code})",
            )
        return

    if to_status == "BLOCKED":
        if from_status not in {"READY", "IN_PROGRESS"}:
            raise _conflict(
                origin,
                line_no,
                RULE_4_ILLEGAL_TRANSITION,
                event_id,
                f"BLOCKED can only be entered from READY or IN_PROGRESS (got {from_status})",
            )
        if event.reason_code not in BLOCK_REASON_CODES:
            raise _conflict(
                origin,
                line_no,
                RULE_4_MUTUALLY_EXCLUSIVE_SUCCESSOR,
                event_id,
                f"{from_status} → BLOCKED requires reason_code in {sorted(BLOCK_REASON_CODES)} "
                f"(got {event.reason_code})",
            )
        return

    allowed = REASON_BY_TRANSITION.get((from_status, to_status))
    if allowed is None:
        if _skipped_mandatory_stage(from_status, to_status):
            raise _conflict(
                origin,
                line_no,
                RULE_4_SKIPPED_MANDATORY_STAGE,
                event_id,
                f"{from_status} → {to_status} skips mandatory stages of the main path "
                f"{' → '.join(MAIN_PATH)}",
            )
        raise _conflict(
            origin,
            line_no,
            RULE_4_ILLEGAL_TRANSITION,
            event_id,
            f"{from_status} → {to_status} is not a legal transition "
            f"(current reduced status: {current})",
        )

    if event.reason_code not in allowed:
        raise _conflict(
            origin,
            line_no,
            RULE_4_MUTUALLY_EXCLUSIVE_SUCCESSOR,
            event_id,
            f"{from_status} → {to_status} is not justified by reason_code {event.reason_code} "
            f"(mutually exclusive successors require one of {sorted(allowed)})",
        )

    if from_status == "COMPLETE" and to_status == "IN_PROGRESS":
        if not event.references:
            raise _conflict(
                origin,
                line_no,
                RULE_4_CORRECTION_WITHOUT_REFERENCE,
                event_id,
                "COMPLETE → IN_PROGRESS (STATUS_CORRECTION) must reference the erroneous event_id",
            )
        for reference in event.references:
            if normalize_event_id(reference) not in known_event_ids:
                raise _conflict(
                    origin,
                    line_no,
                    RULE_4_CORRECTION_DANGLING_REFERENCE,
                    event_id,
                    f"correction reference {reference!r} does not resolve to an earlier event_id",
                )


def reduce_events(
    genesis: Mapping[str, str],
    canonical_events: Sequence[StatusEvent],
    suffix_events: Sequence[StatusEvent] = (),
    *,
    self_commit: str | None = None,
) -> LedgerReport:
    """按**文件顺序**归约 canonical prefix + pending suffix（禁止排序后重新解释）。

    每一步都做 rule 3–7 的校验；首个违规即抛 :class:`LedgerConflict`
    （rule 8：不 last-line-wins、不忽略非法行、不重排）。
    """
    statuses: dict[str, str] = {spec_id: genesis[spec_id] for spec_id in SPEC_IDS}
    pending_flags: dict[str, bool] = {spec_id: False for spec_id in SPEC_IDS}
    block_return: dict[str, str] = {}
    known_event_ids: set[str] = set()
    seen_ids: dict[str, StatusEvent] = {}
    suffix_identities = {event.identity() for event in suffix_events}

    for event in list(canonical_events) + list(suffix_events):
        origin, line_no, event_id = event.origin, event.line_no, event.event_id
        spec_id = event.spec_id
        current = statuses[spec_id]

        identity = event.identity()
        if identity in seen_ids:
            previous = seen_ids[identity]
            raise _conflict(
                origin,
                line_no,
                RULE_2_DUPLICATE_EVENT_ID,
                event_id,
                f"event_id already used at {previous.origin}:{previous.line_no}",
            )

        # rule 6（Authority）：非可执行 authority 不能仅因状态变化获得实施权限。
        authority = SPEC_AUTHORITY[spec_id]
        if authority in NON_EXECUTABLE_AUTHORITIES and event.to_status not in NON_EXECUTABLE_STATUSES:
            raise _conflict(
                origin,
                line_no,
                RULE_6_AUTHORITY_NOT_EXECUTABLE,
                event_id,
                f"Spec {spec_id} authority {authority!r} is not executable: "
                f"only {sorted(NON_EXECUTABLE_STATUSES)} are allowed "
                f"(got {event.to_status})",
            )

        # rule 3：from_status 必须等于前一归约状态。
        if event.from_status != current:
            raise _conflict(
                origin,
                line_no,
                RULE_3_FROM_STATUS_MISMATCH,
                event_id,
                f"from_status={event.from_status} does not equal the reduced status "
                f"{current} for Spec {spec_id}",
            )

        # rule 4 / 8：转换合法性与理由码耦合、correction 引用。
        _check_transition(
            event, current, block_return, frozenset(known_event_ids)
        )

        # rule 5：VALIDATED 必须有非空 evidence_refs。
        if event.to_status == "VALIDATED" and not event.evidence_refs:
            raise _conflict(
                origin,
                line_no,
                RULE_5_VALIDATED_WITHOUT_EVIDENCE,
                event_id,
                "VALIDATED requires a non-empty validation result / Evidence reference",
            )

        # rule 6（依赖解锁）：进入 READY 时 DAG 前置必须已 COMPLETE。
        if event.to_status == "READY":
            dependency = DAG[spec_id]
            accepted = {"COMPLETE"}
            if spec_id in VALIDATED_UNLOCK_ALLOWED:
                accepted.add("VALIDATED")
            unmet = [
                prerequisite
                for prerequisite in dependency.prerequisites
                if statuses[prerequisite] not in accepted
            ]
            if unmet:
                raise _conflict(
                    origin,
                    line_no,
                    RULE_6_MISSING_PREREQUISITE,
                    event_id,
                    f"Spec {spec_id} cannot become READY: prerequisite(s) "
                    + ", ".join(
                        f"{prerequisite}={statuses[prerequisite]}" for prerequisite in unmet
                    )
                    + f" are not COMPLETE (Depends On: {dependency.raw!r})",
                )

        # rule 7：candidate_commit 绑定与自引用。
        if event.candidate_commit is None:
            if event.reason_code in COMMIT_BOUND_REASON_CODES:
                raise _conflict(
                    origin,
                    line_no,
                    RULE_7_CANDIDATE_COMMIT_REQUIRED,
                    event_id,
                    f"reason_code {event.reason_code} must bind a non-null candidate_commit",
                )
            if spec_id not in CANDIDATE_COMMIT_NULL_ALLOWED_SPECS:
                raise _conflict(
                    origin,
                    line_no,
                    RULE_7_CANDIDATE_COMMIT_REQUIRED,
                    event_id,
                    f"Spec {spec_id} is post-freeze: candidate_commit must reference the "
                    "existing candidate A (null is only allowed for Specs 01–11 pre-freeze)",
                )
        elif self_commit is not None and event.candidate_commit == self_commit:
            raise _conflict(
                origin,
                line_no,
                RULE_7_SELF_COMMIT_REFERENCE,
                event_id,
                f"event stores its own commit SHA {self_commit} (candidate_commit must point "
                "at an existing earlier A, never at the commit that contains the ledger)",
            )

        if any(normalize_event_id(reference) == identity for reference in event.references):
            raise _conflict(
                origin,
                line_no,
                RULE_7_SELF_EVENT_REFERENCE,
                event_id,
                "references must not contain the event's own event_id",
            )

        # 应用事件
        if event.from_status == "BLOCKED":
            block_return.pop(spec_id, None)
        if event.to_status == "BLOCKED":
            block_return[spec_id] = event.from_status
        statuses[spec_id] = event.to_status
        if identity in suffix_identities:
            pending_flags[spec_id] = True
        known_event_ids.add(identity)
        seen_ids[identity] = event

    return LedgerReport(
        statuses={spec_id: statuses[spec_id] for spec_id in SPEC_IDS},
        pending={spec_id: pending_flags[spec_id] for spec_id in SPEC_IDS},
        canonical_event_count=len(canonical_events),
        suffix_event_count=len(suffix_events),
        used_pending_suffix=bool(suffix_events),
        suffix_hash=None,
        candidate_commit=None,
        target_boundary=None,
        authority={spec_id: SPEC_AUTHORITY[spec_id] for spec_id in SPEC_IDS},
    )


def _with_pending_metadata(report: LedgerReport, envelope: PendingEnvelope | None) -> LedgerReport:
    if envelope is None:
        return report
    return LedgerReport(
        statuses=report.statuses,
        pending=report.pending,
        canonical_event_count=report.canonical_event_count,
        suffix_event_count=report.suffix_event_count,
        used_pending_suffix=True,
        suffix_hash=envelope.suffix_hash,
        candidate_commit=envelope.candidate_commit,
        target_boundary=envelope.target_boundary,
        authority=report.authority,
    )


def reduce_ledger_bytes(
    ledger_bytes: bytes,
    *,
    spec_dir: Path,
    index_path: Path | None = None,
    pending_jsonl_bytes: bytes | None = None,
    pending_envelope_bytes: bytes | None = None,
    self_commit: str | None = None,
) -> LedgerReport:
    """完整归约：genesis（子 Spec） → canonical prefix → pending suffix。"""
    genesis = read_genesis(Path(spec_dir))
    if index_path is not None:
        verify_index(Path(index_path), genesis)

    canonical_events = parse_event_lines(ledger_bytes, origin=LEDGER_FILENAME)

    envelope: PendingEnvelope | None = None
    suffix_events: list[StatusEvent] = []
    if (pending_jsonl_bytes is None) != (pending_envelope_bytes is None):
        raise LedgerConfigError(
            "pending suffix requires both --pending-jsonl and --pending-envelope"
        )
    if pending_jsonl_bytes is not None and pending_envelope_bytes is not None:
        envelope = parse_pending_envelope(pending_envelope_bytes)
        if envelope.suffix_hash != compute_suffix_hash(pending_jsonl_bytes):
            raise _conflict(
                "pending-envelope",
                None,
                RULE_PENDING_HASH_MISMATCH,
                None,
                f"suffix_hash={envelope.suffix_hash} does not match the sha256 of the "
                f"pending .jsonl raw bytes ({compute_suffix_hash(pending_jsonl_bytes)}); "
                "the envelope must not participate in its own hash",
            )
        nonempty = count_nonempty_lines(pending_jsonl_bytes, "pending-jsonl")
        if envelope.event_count != nonempty:
            raise _conflict(
                "pending-envelope",
                None,
                RULE_PENDING_COUNT_MISMATCH,
                None,
                f"event_count={envelope.event_count} does not match the "
                f"{nonempty} non-empty line(s) in the pending .jsonl",
            )
        suffix_events = parse_event_lines(pending_jsonl_bytes, origin="pending-jsonl")
        check_suffix_candidate_binding(canonical_events, suffix_events, envelope)

    report = reduce_events(
        genesis, canonical_events, suffix_events, self_commit=self_commit
    )
    return _with_pending_metadata(report, envelope)


def reduce_ledger_files(
    *,
    ledger_path: Path,
    spec_dir: Path | None = None,
    index_path: Path | None = None,
    pending_jsonl_path: Path | None = None,
    pending_envelope_path: Path | None = None,
    self_commit: str | None = None,
) -> LedgerReport:
    """文件入口：缺失文件 → :class:`LedgerConfigError`（退出 2）。"""
    ledger = Path(ledger_path)
    resolved_spec_dir = Path(spec_dir) if spec_dir is not None else ledger.parent

    ledger_bytes = _read_bytes(ledger, "ledger")
    pending_bytes = (
        _read_bytes(Path(pending_jsonl_path), "pending jsonl")
        if pending_jsonl_path is not None
        else None
    )
    envelope_bytes = (
        _read_bytes(Path(pending_envelope_path), "pending envelope")
        if pending_envelope_path is not None
        else None
    )
    return reduce_ledger_bytes(
        ledger_bytes,
        spec_dir=resolved_spec_dir,
        index_path=Path(index_path) if index_path is not None else None,
        pending_jsonl_bytes=pending_bytes,
        pending_envelope_bytes=envelope_bytes,
        self_commit=self_commit,
    )


# --------------------------------------------------------------------------- #
# 10. CLI
# --------------------------------------------------------------------------- #


class _ArgumentParser(argparse.ArgumentParser):
    """退出码 2 的错误输出必须带可 grep 的 ``SPEC_INCOMPLETE`` 符号。"""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(2, f"SPEC_INCOMPLETE: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="status_ledger.py",
        description=(
            "Foundation Contract 状态账本 reducer（Appendix I）。"
            "只读；不写账本、不调用模型。"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser(
        "validate",
        help="归约并校验 canonical ledger（可选叠加 pending suffix）",
        description="validate --ledger <ledger.jsonl> [--pending-jsonl ... --pending-envelope ...]",
    )
    validate.add_argument("--ledger", required=True, help="canonical ledger 路径（*.jsonl）")
    validate.add_argument("--pending-jsonl", default=None, help="pending suffix 事件文件（provisional）")
    validate.add_argument(
        "--pending-envelope", default=None, help="pending suffix envelope（provisional）"
    )
    validate.add_argument(
        "--spec-dir",
        default=None,
        help="子 Spec 目录（genesis 的 Initial Status 来源）；默认 = ledger 所在目录",
    )
    validate.add_argument(
        "--index",
        default=None,
        help=f"执行索引路径；默认 = <spec-dir>/{INDEX_FILENAME}（存在时校验常量漂移）",
    )
    validate.add_argument(
        "--self-commit",
        default=None,
        help="封装该账本的提交 SHA；给出时任何事件引用它即判 self-reference 冲突",
    )
    validate.add_argument("--json", action="store_true", help="以 JSON 输出归约结果")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _force_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "validate":  # pragma: no cover - argparse 已限制
        parser.error(f"unknown command {args.command!r}")

    if args.self_commit is not None and (
        not isinstance(args.self_commit, str)
        or REPOSITORY_COMMIT_PATTERN.match(args.self_commit) is None
    ):
        parser.error("--self-commit must be a 40-char lowercase hex commit")

    try:
        ledger_path = Path(args.ledger)
        if not ledger_path.is_file():
            raise LedgerConfigError(f"ledger not found: {ledger_path}")

        spec_dir = Path(args.spec_dir) if args.spec_dir else ledger_path.parent
        if args.index:
            index_path: Path | None = Path(args.index)
            if not index_path.is_file():
                raise LedgerConfigError(f"execution index not found: {index_path}")
        else:
            candidate_index = spec_dir / INDEX_FILENAME
            index_path = candidate_index if candidate_index.is_file() else None

        report = reduce_ledger_files(
            ledger_path=ledger_path,
            spec_dir=spec_dir,
            index_path=index_path,
            pending_jsonl_path=Path(args.pending_jsonl) if args.pending_jsonl else None,
            pending_envelope_path=(
                Path(args.pending_envelope) if args.pending_envelope else None
            ),
            self_commit=args.self_commit,
        )
    except LedgerConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except LedgerConflict as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report.to_json(), ensure_ascii=False, indent=2))
    else:
        print(report.render_text())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
