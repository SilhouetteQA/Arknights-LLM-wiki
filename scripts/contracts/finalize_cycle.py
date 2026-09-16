#!/usr/bin/env python
"""Spec 10 — Wiki Finalization：`finalize_cycle.py`（仅 Wiki）。

规范来源
--------
- Master §16.6（Wiki Finalization C 的 allowlist、report hash、`current.json` 四字段、账本不写 C SHA）
- Master §15.3（`COMPLETE` 只能在 C_wiki 合并后成立）、§17 Stage 10
- Master Appendix C.5 / D.3 / I.2–I.4（Event Schema、reason_code 闭集、append-only）
- Spec 15:53-64（Finalization C 步骤）、Spec 10:111（fixture 命令）
- `FND-REL-003`–`FND-REL-006`、`GOV-STAT-004`

行为边界（**硬约束**）
----------------------
- 本工具只**准备** C 的 allowlist 文件（`cycle-report.json` / `cycle-report.md` / `current.json`）
  并**只追加**账本事件；**不做** ``git commit``、**不做** ``git push``。
- **不** 记录 C 自身 SHA：任何写入的 artifact 字段与账本事件都不得包含 C SHA。
- **绝不** 写真实的 ``docs/specs/foundation-contract/execution-status-events.jsonl``：
  目标账本必须由 ``--ledger`` 或临时默认路径指定，**缺失即退出 2**；
  仅当显式设置 ``AGENT_CONTRACT_ALLOW_REAL_LEDGER=1`` 时才允许指向本仓真实账本。
- **绝不** 写本仓真实 ``docs/contracts/releases/**``：默认拒绝，需显式设置
  ``AGENT_CONTRACT_ALLOW_REAL_RELEASE=1``（Spec 10 只做 fixture 验证）。
- 本工具**不** 声明 `Cycle COMPLETE`：COMPLETE 只能由 C_wiki 合并后的 canonical 验证产生。

规范缺口与 provisional 决策（编号沿用 `output/spec10-normative-extraction-report.md`）
----------------------------------------------------------------------------------
- **G-18**（退出码未定义）：``0`` = 成功；``1`` = 校验失败；``2`` = 用法 / 配置错误。
- **G-17**（fixture 路径未定义）：新增可选 ``--ledger`` / ``--wiki-repo`` / ``--b-wiki`` /
  ``--c-wiki`` / ``--expected-coordination-hash`` / ``--release-relative``；规范 CLI
  ``--coordination`` + ``--release`` 保持不变。
- **§16.6 current.json 位置**：规范最终路径是 ``docs/contracts/current.json``。当 ``--release``
  形如 ``<root>/.../releases/<version>`` 时写到 ``<release>/../..``（即 release 的上两级）；
  ``releases`` 目录名不匹配（如临时 release 目录）时退化为 ``<release>/current.json``。
- **§16.6 / Spec 15:59 账本事件的 from_status 推导**：规范未定义 Python API。本实现按
  文件顺序归约 Spec 15 的当前状态（纯函数 ``reduce_spec_status``），只在必要时补齐
  合法前驱事件（``PREREQUISITES_SATISFIED`` → READY、``EXECUTION_STARTED`` → IN_PROGRESS），
  随后追加 ``COORDINATION_PASSED``（→ VALIDATED）与 ``FINALIZATION_COMPLETE``（→ COMPLETE）。
  所有事件都只使用 I.2:2790 的 reason_code 闭集；事件本身不写 C SHA。
- **幂等**：账本中已存在同一 ``cycle_id`` 的 ``FINALIZATION_COMPLETE`` 时不再重复追加
  （避免 C2 重试产生互斥后继 / 重复 ID）。
- **"hash 精确一致"的判定**：对 ``coordination.json`` 重算 canonical SHA256；若传入
  ``--expected-coordination-hash``（或环境变量 ``AGENT_CONTRACT_COORDINATION_HASH``）则必须相等；
  写出的 ``cycle-report.json`` 再读回后必须与源 artifact 字节与 canonical hash 都一致。
  Markdown 按 §16.6 先做 UTF-8 / LF 规范化再比较。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

# --------------------------------------------------------------------------- #
# 自举：直接以 `python scripts/contracts/xxx.py` 运行时 sys.path[0] 是脚本目录，
# 仓库根不在其中；先注入仓根，再做任何项目 import。
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
REPO_ROOT = _REPO_ROOT

from agent_core.contracts.tooling.canonical_json import (  # noqa: E402
    canonical_json_bytes,
    canonical_json_dumps,
    normalize_text,
    sha256_hex,
)

def _configure_stdio() -> None:
    """Windows 控制台默认 GBK 会让中文/数学符号打印崩溃；强制 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:  # pragma: no cover - 依控制台而异
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

RELEASE_ROOT = Path("docs") / "contracts" / "releases"
CURRENT_POINTER = Path("docs") / "contracts" / "current.json"
LEDGER_RELATIVE = Path("docs") / "specs" / "foundation-contract" / "execution-status-events.jsonl"

#: §16.6：C 允许的 4 类变更。
C_ALLOWED_BASENAMES: tuple[str, ...] = ("cycle-report.json", "cycle-report.md", "current.json")

#: §16.6：`current.json` 只允许 4 字段（它是指针，不是第三份 manifest）。
CURRENT_POINTER_KEYS: tuple[str, ...] = (
    "contract_version",
    "contract_payload_hash",
    "cycle_id",
    "release_path",
)

#: I.2 Event Schema 的字段闭集（事件不得含自身 SHA）。
EVENT_KEYS: tuple[str, ...] = (
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

#: 事件名称 / reason_code（I.2:2790-2807 闭集）。
REASON_PREREQUISITES_SATISFIED = "PREREQUISITES_SATISFIED"
REASON_EXECUTION_STARTED = "EXECUTION_STARTED"
REASON_COORDINATION_PASSED = "COORDINATION_PASSED"
REASON_FINALIZATION_COMPLETE = "FINALIZATION_COMPLETE"

SPEC_ID = "15"

#: 合法状态闭集（I.2:2778）。
STATUSES: tuple[str, ...] = (
    "NOT_STARTED",
    "READY",
    "IN_PROGRESS",
    "BLOCKED",
    "VALIDATED",
    "COMPLETE",
    "SUPERSEDED",
)

#: 禁止出现在任何 C artifact 字段名中的自身身份键。
FORBIDDEN_SELF_KEYS: tuple[str, ...] = (
    "c_wiki",
    "c_wiki_commit",
    "finalization_commit",
    "finalization_c_commit",
    "self_hash",
    "self_sha",
    "current_commit",
    "own_sha",
)

_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

ENV_EXPECTED_HASH = "AGENT_CONTRACT_COORDINATION_HASH"
ENV_B_WIKI = "AGENT_CONTRACT_B_WIKI"
ENV_C_WIKI = "AGENT_CONTRACT_C_WIKI"
ENV_ALLOW_REAL_LEDGER = "AGENT_CONTRACT_ALLOW_REAL_LEDGER"
ENV_ALLOW_REAL_RELEASE = "AGENT_CONTRACT_ALLOW_REAL_RELEASE"

UNVERIFIED = "unverified"


class UsageError(RuntimeError):
    """用法 / 配置错误（退出码 2）。"""


class FinalizationFailure(RuntimeError):
    """校验失败（退出码 1）。"""


@dataclass
class Check:
    index: int
    name: str
    status: str  # "PASS" / "FAIL" / "SKIP"
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"check": self.index, "name": self.name, "status": self.status, "detail": self.detail}


@dataclass
class FinalizationState:
    coordination_hash: str = ""
    cycle_id: str = ""
    contract_version: str = ""
    contract_payload_hash: str = ""
    wiki_candidate_commit: str = ""
    release_dir: Path = Path(".")
    release_relative: str = ""
    current_pointer: Path = Path(".")
    ledger_path: Path = Path(".")
    appended_events: list[dict[str, Any]] = field(default_factory=list)
    already_finalized: bool = False
    b_wiki: str | None = None
    c_wiki: str | None = None
    problems: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# 纯函数层
# --------------------------------------------------------------------------- #


def canonical_hash(value: Any) -> str:
    """canonical JSON 的 SHA256（与协调端计算 Evidence Manifest / artifact hash 同口径）。"""
    return sha256_hex(canonical_json_bytes(value))


def raw_hash(data: bytes) -> str:
    return sha256_hex(data)


def normalize_markdown_bytes(data: bytes) -> bytes:
    """§16.6：Markdown 在 UTF-8 / LF 规范化后比较。"""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return normalize_text(data.decode("utf-8")).encode("utf-8")


def check_current_pointer(pointer: Any) -> list[str]:
    """纯函数：`current.json` 必须恰好是 4 个允许字段。"""
    if not isinstance(pointer, dict):
        return ["current.json 必须是 JSON object"]
    errors: list[str] = []
    missing = [key for key in CURRENT_POINTER_KEYS if key not in pointer]
    extra = sorted(set(pointer) - set(CURRENT_POINTER_KEYS))
    if missing:
        errors.append(f"current.json 缺少字段：{missing}（§16.6 只允许 4 字段）")
    if extra:
        errors.append(f"current.json 出现规范外字段：{extra}（§16.6 只允许 4 字段）")
    return errors


def check_no_self_sha(texts: dict[str, str], c_sha: str | None) -> list[str]:
    """纯函数：任何 C artifact / 账本事件都不得记录 C 自身 SHA 或自身身份键。"""
    errors: list[str] = []
    for name, text in texts.items():
        lowered = text.lower()
        for key in FORBIDDEN_SELF_KEYS:
            if f'"{key}"' in lowered:
                errors.append(f"{name} 出现禁止的自身身份字段名 {key!r}（Spec 15:59 / Spec 10:85）")
        if c_sha:
            if c_sha.lower() in lowered:
                errors.append(f"{name} 记录了 C_wiki 自身 SHA（{c_sha[:12]}…），规范禁止")
            if c_sha.upper() in text:
                errors.append(f"{name} 记录了 C_wiki 自身 SHA（大写形式），规范禁止")
    return errors


def check_c_allowlist(changes: list[tuple[str, str]], allowed_paths: set[str]) -> list[str]:
    """纯函数：``diff(B_wiki, C_wiki)`` 必须 ⊆ 严格 finalization allowlist。"""
    errors: list[str] = []
    for status, path in changes:
        code = status[:1].upper()
        if code in {"D", "R", "C", "T", "U", "X"}:
            errors.append(f"B→C 出现非追加变更 {status} {path}")
            continue
        if path not in allowed_paths:
            errors.append(f"B→C diff 越界：{status} {path} 不在 finalization allowlist 内（§16.6）")
    return errors


def reduce_spec_status(ledger_text: str, spec_id: str = SPEC_ID) -> str:
    """纯函数：按文件顺序归约单个 spec 的当前状态（不重排、不采用 last-line-wins 之外的语义）。"""
    status = "NOT_STARTED"
    for line in ledger_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or str(record.get("spec_id")) != spec_id:
            continue
        to_status = record.get("to_status")
        if isinstance(to_status, str) and to_status in STATUSES:
            status = to_status
    return status


def _event(
    *,
    from_status: str,
    to_status: str,
    reason_code: str,
    reason: str,
    candidate_commit: str,
    evidence_ref: str,
    cycle_id: str,
    timestamp: str,
) -> dict[str, Any]:
    event = {
        "event_id": str(uuid.uuid4()),
        "spec_id": SPEC_ID,
        "from_status": from_status,
        "to_status": to_status,
        "candidate_commit": candidate_commit,
        "evidence_refs": [f"contract-tests:{evidence_ref}"],
        "timestamp": timestamp,
        "reason_code": reason_code,
        "reason": reason,
        "references": [cycle_id],
    }
    assert set(event) == set(EVENT_KEYS), "event 字段必须与 I.2 Event Schema 完全一致"
    return event


def plan_ledger_events(
    current_status: str,
    *,
    cycle_id: str,
    candidate_commit: str,
    coordination_hash: str,
    timestamp: str,
) -> list[dict[str, Any]]:
    """纯函数：推导把 Spec 15 推到 COMPLETE 所需的最小合法事件序列。

    只在必要时补齐合法前驱（I.2:2778-2788 的 NOT_STARTED → READY → IN_PROGRESS），
    然后追加 Spec 15 的两个 finalization 事件（Spec 15:59）。
    """
    if current_status not in STATUSES:
        raise UsageError(f"账本中的 Spec {SPEC_ID} 状态非法：{current_status!r}")
    if current_status in {"COMPLETE", "SUPERSEDED"}:
        return []

    events: list[dict[str, Any]] = []
    status = current_status

    def emit(to_status: str, reason_code: str, reason: str, evidence_ref: str) -> None:
        nonlocal status
        events.append(
            _event(
                from_status=status,
                to_status=to_status,
                reason_code=reason_code,
                reason=reason,
                candidate_commit=candidate_commit,
                evidence_ref=evidence_ref,
                cycle_id=cycle_id,
                timestamp=timestamp,
            )
        )
        status = to_status

    if status == "NOT_STARTED":
        emit(
            "READY",
            REASON_PREREQUISITES_SATISFIED,
            f"Spec 15 依赖（Spec 14 COMPLETE）满足，cycle {cycle_id} 进入协调/最终化边界",
            "coordination.json",
        )
    if status == "READY":
        emit(
            "IN_PROGRESS",
            REASON_EXECUTION_STARTED,
            f"Spec 15 coordination/finalization 执行开始（cycle {cycle_id}）",
            "coordination.json",
        )
    if status == "BLOCKED":
        raise UsageError(
            "账本中 Spec 15 当前为 BLOCKED；阻塞未解除前不得追加 finalization 事件（I.2:2778-2788）"
        )
    if status == "VALIDATED":
        pass
    elif status != "IN_PROGRESS":
        raise UsageError(f"无法从状态 {status!r} 推导合法 finalization 事件序列")

    if status == "IN_PROGRESS":
        emit(
            "VALIDATED",
            REASON_COORDINATION_PASSED,
            f"Coordination PASS（cycle {cycle_id}），artifact canonical hash={coordination_hash}",
            "coordination.json",
        )
    emit(
        "COMPLETE",
        REASON_FINALIZATION_COMPLETE,
        f"Wiki finalization 文件已按 §16.6 allowlist 准备（cycle {cycle_id}）",
        "cycle-report.json",
    )
    return events


def load_ledger_bytes(path: Path) -> bytes:
    if not path.is_file():
        raise UsageError(
            f"目标账本不存在：{path}；本工具不做 fixture 之外的账本创建（缺失即退出 2）。"
            "真实账本必须以 --ledger 显式指向，且默认被拒绝写入"
        )
    return path.read_bytes()


# --------------------------------------------------------------------------- #
# 文件快照（用于"只允许 4 类文件"自检）
# --------------------------------------------------------------------------- #


def snapshot(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = raw_hash(path.read_bytes())
    return result


def diff_snapshots(before: dict[str, str], after: dict[str, str]) -> list[str]:
    changed: list[str] = []
    for path, digest in after.items():
        if path not in before:
            changed.append(f"A:{path}")
        elif before[path] != digest:
            changed.append(f"M:{path}")
    for path in before:
        if path not in after:
            changed.append(f"D:{path}")
    return changed


# --------------------------------------------------------------------------- #
# git 只读交互层
# --------------------------------------------------------------------------- #


def _git(wiki_repo: Path, args: Sequence[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(wiki_repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:  # pragma: no cover
        raise UsageError("找不到 git 可执行文件；ancestry/diff 校验需要只读 git 访问") from exc
    except subprocess.TimeoutExpired as exc:  # pragma: no cover
        raise FinalizationFailure(f"git {' '.join(args)} 超时") from exc


def is_ancestor(wiki_repo: Path, ancestor: str, descendant: str) -> bool:
    return _git(wiki_repo, ["merge-base", "--is-ancestor", ancestor, descendant]).returncode == 0


def changed_paths(wiki_repo: Path, base: str, head: str) -> list[tuple[str, str]]:
    proc = _git(wiki_repo, ["diff", "--name-status", "--no-renames", "--no-ext-diff", base, head])
    if proc.returncode != 0:
        raise FinalizationFailure(f"git diff {base}..{head} 失败：{proc.stderr.strip()}")
    changes: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            changes.append((parts[0].strip(), parts[1].strip()))
    return changes


# --------------------------------------------------------------------------- #
# 路径解析与守卫
# --------------------------------------------------------------------------- #


def _relative_to(root: Path, path: Path, fallback: str) -> str:
    """返回 ``path`` 相对 ``root`` 的 POSIX 路径；不在其下时使用规范 fallback。"""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return fallback


def resolve_coordination_path(value: Path) -> Path:
    target = value / "coordination.json" if value.is_dir() else value
    if not target.is_file():
        raise UsageError(f"coordination artifact 不存在：{target}")
    return target


def resolve_release(
    value: Path, contract_version: str, explicit_relative: str | None, wiki_repo: Path
) -> tuple[Path, str]:
    release = value.resolve()
    guarded = (REPO_ROOT / RELEASE_ROOT).resolve()
    if (guarded in release.parents or release == guarded) and os.environ.get(
        ENV_ALLOW_REAL_RELEASE, ""
    ).strip() != "1":
        raise UsageError(
            f"--release 指向本仓真实发布树 {release}；Spec 10 只做 fixture 验证，"
            f"如需写入请显式设置 {ENV_ALLOW_REAL_RELEASE}=1"
        )
    if release.exists() and release.is_file():
        raise UsageError(f"--release 必须是目录，实际是文件：{release}")
    relative = explicit_relative or _relative_to(
        wiki_repo, release, f"{RELEASE_ROOT.as_posix()}/{contract_version}"
    )
    return release, relative.replace("\\", "/").strip("/")


def resolve_current_pointer(
    release: Path, release_relative: str, wiki_repo: Path
) -> tuple[Path, str]:
    """§16.6：规范路径是 ``docs/contracts/current.json``。"""
    if release.parent.name == "releases":
        pointer = release.parent.parent / "current.json"
        fallback = CURRENT_POINTER.as_posix()
    else:
        # 临时 release 目录（Spec 10 fixture）：指针落在 release 目录内。
        pointer = release / "current.json"
        fallback = f"{release_relative}/current.json"
    return pointer, _relative_to(wiki_repo, pointer, fallback)


def resolve_ledger(value: Path | None, cycle_id: str) -> Path:
    """目标账本：显式参数优先，否则临时路径；两者都必须已存在（缺失 → 退出 2）。"""
    if value is None:
        default = Path(tempfile.gettempdir()) / "foundation-contract-cycle" / f"{cycle_id}.jsonl"
        if not default.is_file():
            raise UsageError(
                f"未提供 --ledger，默认账本 {default} 不存在；Spec 10 只允许 fixture 账本，"
                "真实账本必须显式传入且受守卫限制（缺失即退出 2）"
            )
        ledger = default
    else:
        ledger = value.resolve()

    real_ledger = (REPO_ROOT / LEDGER_RELATIVE).resolve()
    if ledger == real_ledger and os.environ.get(ENV_ALLOW_REAL_LEDGER, "").strip() != "1":
        raise UsageError(
            "拒绝写入本仓真实账本 docs/specs/foundation-contract/execution-status-events.jsonl；"
            f"Spec 10 只做 fixture 验证（如确为 Spec 15 正式运行，请显式设置 {ENV_ALLOW_REAL_LEDGER}=1）"
        )
    if not ledger.is_file():
        raise UsageError(f"目标账本不存在：{ledger}（缺失即退出 2）")
    return ledger


# --------------------------------------------------------------------------- #
# 账本
# --------------------------------------------------------------------------- #


def load_sibling(module_name: str) -> Any:
    """按文件路径加载同目录脚本（`scripts/contracts` 不是包）。"""
    path = Path(__file__).resolve().parent / f"{module_name}.py"
    if not path.is_file():
        raise UsageError(f"缺少同目录工具模块：{path}")
    spec = importlib.util.spec_from_file_location(f"_contract_sibling_{module_name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def finalization_already_recorded(ledger_text: str, cycle_id: str) -> bool:
    for line in ledger_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if (
            str(record.get("spec_id")) == SPEC_ID
            and record.get("reason_code") == REASON_FINALIZATION_COMPLETE
            and cycle_id in (record.get("references") or [])
        ):
            return True
    return False


def append_ledger_events(ledger_path: Path, events: list[dict[str, Any]]) -> None:
    """只追加：旧字节保持为严格前缀，事件为单行 canonical JSON。"""
    previous = ledger_path.read_bytes()
    appended = b"".join((canonical_json_dumps(event) + "\n").encode("utf-8") for event in events)
    tmp = ledger_path.with_name(ledger_path.name + ".tmp")
    tmp.write_bytes(previous + appended)
    os.replace(tmp, ledger_path)


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #


def finalize(args: argparse.Namespace) -> int:
    coordination_path = resolve_coordination_path(Path(args.coordination))
    source_bytes = coordination_path.read_bytes()
    try:
        report = json.loads(source_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UsageError(f"coordination artifact 不是合法 UTF-8 JSON：{exc}") from exc
    if not isinstance(report, dict):
        raise UsageError("coordination artifact 必须是 JSON object")

    state = FinalizationState()
    state.coordination_hash = canonical_hash(report)
    state.cycle_id = str(report.get("cycle_id") or "")
    state.contract_version = str(report.get("contract_version") or "")
    state.contract_payload_hash = str(report.get("contract_payload_hash") or "")
    state.wiki_candidate_commit = str(report.get("wiki_candidate_commit") or "")
    checks: list[Check] = []

    # check 1：coordination artifact canonical hash 校验（此阶段失败不写任何文件）
    expected = args.expected_coordination_hash or os.environ.get(ENV_EXPECTED_HASH)
    hash_problems: list[str] = []
    if not state.cycle_id:
        hash_problems.append("coordination artifact 缺少 cycle_id")
    if report.get("coordination_result") != "PASS" or report.get("cycle_state") != "READY_FOR_FINALIZATION":
        hash_problems.append(
            f"coordination_result={report.get('coordination_result')!r} / "
            f"cycle_state={report.get('cycle_state')!r} 不是 PASS / READY_FOR_FINALIZATION"
        )
    if expected:
        if not _HASH_RE.match(expected):
            raise UsageError(f"--expected-coordination-hash 形状非法：{expected!r}")
        if expected != state.coordination_hash:
            hash_problems.append(
                f"coordination artifact canonical hash 不匹配：期望 {expected}，实测 {state.coordination_hash}"
            )
    else:
        # 无外部期望值时，至少要求 artifact 落盘字节已是 canonical JSON（hash 才有唯一定义）。
        if source_bytes.decode("utf-8").strip() != canonical_json_dumps(report):
            hash_problems.append(
                "coordination artifact 落盘字节不是 canonical JSON；无法给出稳定的 canonical hash"
            )
    if hash_problems:
        checks.append(Check(1, "coordination artifact canonical hash", "FAIL", "；".join(hash_problems)))
        return _report(
            args,
            state,
            checks,
            write=False,
            abort="coordination artifact 校验失败，未写入任何文件：" + "；".join(hash_problems),
        )
    checks.append(
        Check(
            1,
            "coordination artifact canonical hash",
            "PASS",
            f"canonical hash={state.coordination_hash}"
            + ("（与外部期望值一致）" if expected else "（无外部期望值：仅校验落盘字节 canonical）"),
        )
    )

    # 路径与守卫（失败即退出 2，不写文件）
    wiki_repo = Path(args.wiki_repo).resolve() if args.wiki_repo else REPO_ROOT
    if not wiki_repo.is_dir():
        raise UsageError(f"--wiki-repo 不存在：{wiki_repo}")
    release_dir, release_relative = resolve_release(
        Path(args.release), state.contract_version, args.release_relative, wiki_repo
    )
    current_pointer, current_relative = resolve_current_pointer(release_dir, release_relative, wiki_repo)
    ledger_path = resolve_ledger(Path(args.ledger) if args.ledger else None, state.cycle_id)
    state.release_dir = release_dir
    state.release_relative = release_relative
    state.current_pointer = current_pointer
    state.ledger_path = ledger_path

    state.b_wiki = (args.b_wiki or os.environ.get(ENV_B_WIKI) or "").strip() or None
    state.c_wiki = (args.c_wiki or os.environ.get(ENV_C_WIKI) or "").strip() or None
    for name, sha in (("--b-wiki", state.b_wiki), ("--c-wiki", state.c_wiki)):
        if sha is not None and not _SHA_RE.match(sha):
            raise UsageError(f"{name} 必须是完整 commit SHA：{sha!r}")

    before_release = snapshot(release_dir)
    before_pointer_parent = snapshot(current_pointer.parent)
    before_ledger = ledger_path.read_bytes()

    # check 2：复制 hash 精确一致的 cycle-report.json / cycle-report.md
    release_dir.mkdir(parents=True, exist_ok=True)
    json_target = release_dir / "cycle-report.json"
    md_target = release_dir / "cycle-report.md"

    md_source = coordination_path.with_suffix(".md")
    if not md_source.is_file():
        raise UsageError(f"缺少 coordination Markdown：{md_source}")
    md_bytes = normalize_markdown_bytes(md_source.read_bytes())

    copy_problems: list[str] = []
    existing_json = json_target.read_bytes() if json_target.is_file() else None
    existing_md = md_target.read_bytes() if md_target.is_file() else None
    if existing_json is not None and existing_json != source_bytes:
        copy_problems.append(
            "release 中已存在内容不同的 cycle-report.json；不得覆盖既有失败 C（Master §16.7）"
        )
    else:
        json_target.write_bytes(source_bytes)
    if existing_md is not None and normalize_markdown_bytes(existing_md) != md_bytes:
        copy_problems.append(
            "release 中已存在内容不同的 cycle-report.md；不得覆盖既有失败 C（Master §16.7）"
        )
    else:
        md_target.write_bytes(md_bytes)

    copied = json_target.read_bytes()
    if copied != source_bytes:
        copy_problems.append("cycle-report.json 与 coordination artifact 字节不一致")
    if canonical_hash(json.loads(copied.decode("utf-8"))) != state.coordination_hash:
        copy_problems.append("cycle-report.json 读回后的 canonical hash 与源 artifact 不一致")
    if normalize_markdown_bytes(md_target.read_bytes()) != md_bytes:
        copy_problems.append("cycle-report.md 规范化后 hash 与源 Markdown 不一致")
    checks.append(
        Check(
            2,
            "cycle-report.json/.md hash 精确一致",
            "FAIL" if copy_problems else "PASS",
            "；".join(copy_problems)
            or f"json={state.coordination_hash}（{len(copied)} 字节）；md normalized sha256:{raw_hash(md_bytes)[7:19]}…",
        )
    )

    # check 3：current.json 恰好 4 字段
    pointer = {
        "contract_version": state.contract_version,
        "contract_payload_hash": state.contract_payload_hash,
        "cycle_id": state.cycle_id,
        "release_path": release_relative,
    }
    pointer_errors = check_current_pointer(pointer)
    current_pointer.parent.mkdir(parents=True, exist_ok=True)
    current_pointer.write_text(canonical_json_dumps(pointer) + "\n", encoding="utf-8", newline="\n")
    checks.append(
        Check(
            3,
            "current.json 只含 4 字段",
            "FAIL" if pointer_errors else "PASS",
            "；".join(pointer_errors) or f"{sorted(pointer)} @ {current_relative}",
        )
    )

    # check 4：账本只追加 reducer 可识别事件
    ledger_text = before_ledger.decode("utf-8")
    ledger_problems: list[str] = []
    if finalization_already_recorded(ledger_text, state.cycle_id):
        state.already_finalized = True
        ledger_detail = f"账本已存在 cycle {state.cycle_id} 的 FINALIZATION_COMPLETE，幂等跳过追加"
    else:
        current_status = reduce_spec_status(ledger_text)
        try:
            events = plan_ledger_events(
                current_status,
                cycle_id=state.cycle_id,
                candidate_commit=state.wiki_candidate_commit,
                coordination_hash=state.coordination_hash,
                timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        except UsageError as exc:
            events = []
            ledger_problems.append(str(exc))
        if events:
            append_ledger_events(ledger_path, events)
            state.appended_events = events
        else:
            ledger_problems.append(
                f"账本中 Spec {SPEC_ID} 已为 {current_status}，但不存在本 cycle {state.cycle_id} 的 "
                "FINALIZATION_COMPLETE 事件；拒绝在无合法事件的情况下宣告 finalization"
            )
        after = ledger_path.read_bytes()
        if not after.startswith(before_ledger):
            ledger_problems.append("账本写入破坏了 append-only：旧字节不再是前缀（GOV-STAT-004）")
        sibling = load_sibling("coordinate_cycle")
        ledger_problems.extend(sibling.check_ledger_append_only(before_ledger, after))
        reasons = [event["reason_code"] for event in events]
        ledger_detail = (
            f"from_status={current_status} → 追加 {len(events)} 条事件 {reasons} @ {ledger_path}"
        )
    checks.append(
        Check(
            4,
            "账本只追加 COORDINATION_PASSED / FINALIZATION_COMPLETE",
            "FAIL" if ledger_problems else "PASS",
            "；".join(ledger_problems) or ledger_detail,
        )
    )

    # check 5：不得记录 C 自身 SHA
    self_texts = {
        "cycle-report.json": json_target.read_text(encoding="utf-8"),
        "cycle-report.md": md_target.read_text(encoding="utf-8"),
        "current.json": current_pointer.read_text(encoding="utf-8"),
    }
    # 账本中本 spec 的全部事件（含既有事件）也一并扫描：重跑（幂等跳过）时同样不得出现 C SHA。
    spec_events = [
        line
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("spec_id") == SPEC_ID
    ]
    if spec_events:
        self_texts[f"ledger-spec{SPEC_ID}"] = "".join(spec_events)
    if state.appended_events:
        self_texts["ledger-appended"] = "".join(canonical_json_dumps(event) for event in state.appended_events)
    self_problems = check_no_self_sha(self_texts, state.c_wiki)
    checks.append(
        Check(
            5,
            "C artifact 不记录自身 SHA",
            "FAIL" if self_problems else "PASS",
            "；".join(self_problems)
            or (
                f"已确认 {state.c_wiki[:12]}… 未出现在任何 C artifact / 事件中"
                if state.c_wiki
                else "未提供 --c-wiki：仅校验禁止的自身身份字段名（未校验具体 SHA）"
            ),
        )
    )

    # check 6：B_wiki is ancestor of C_wiki
    if state.b_wiki and state.c_wiki:
        if not wiki_repo.is_dir():
            raise UsageError(f"--wiki-repo 不存在：{wiki_repo}")
        if is_ancestor(wiki_repo, state.b_wiki, state.c_wiki):
            checks.append(
                Check(
                    6,
                    "B_wiki is ancestor of C_wiki",
                    "PASS",
                    f"{state.b_wiki[:12]} → {state.c_wiki[:12]}（{wiki_repo}）",
                )
            )
        else:
            checks.append(
                Check(
                    6,
                    "B_wiki is ancestor of C_wiki",
                    "FAIL",
                    f"merge-base --is-ancestor {state.b_wiki[:12]} {state.c_wiki[:12]} 返回非 0",
                )
            )
    else:
        checks.append(
            Check(
                6,
                "B_wiki is ancestor of C_wiki",
                "FAIL",
                f"{UNVERIFIED}：未提供 --b-wiki / --c-wiki（或环境变量 "
                f"{ENV_B_WIKI}/{ENV_C_WIKI}）；无法验证不等于通过（Spec 15:60）",
            )
        )

    # check 7：严格 C allowlist
    allowed = {f"{release_relative}/{name}" for name in C_ALLOWED_BASENAMES}
    allowed.add(current_relative)
    allowed.add(LEDGER_RELATIVE.as_posix())
    allow_problems: list[str] = []
    roots: list[tuple[Path, dict[str, str], str]] = [(release_dir, before_release, release_relative)]
    if current_pointer.parent != release_dir:
        roots.append(
            (
                current_pointer.parent,
                before_pointer_parent,
                current_relative.rsplit("/", 1)[0] if "/" in current_relative else "",
            )
        )
    for root, before, prefix in roots:
        for change in diff_snapshots(before, snapshot(root)):
            status, _, path = change.partition(":")
            full = f"{prefix}/{path}" if prefix else path
            if full not in allowed:
                allow_problems.append(f"C 中出现 allowlist 外变更：{status} {full}")
    if state.b_wiki and state.c_wiki:
        allow_problems.extend(
            check_c_allowlist(changed_paths(wiki_repo, state.b_wiki, state.c_wiki), allowed)
        )
    checks.append(
        Check(
            7,
            "严格 C allowlist（4 类文件）",
            "FAIL" if allow_problems else "PASS",
            "；".join(allow_problems)
            or f"仅写 {sorted(allowed)}（已比对写前快照"
            + ("，并校验 B→C diff" if state.b_wiki and state.c_wiki else "；B→C diff 因缺少 SHA 未校验")
            + "）",
        )
    )

    # check 8：不做 git commit / push
    checks.append(
        Check(
            8,
            "不做 git commit / push",
            "PASS",
            "本工具只执行 git merge-base / git diff 只读命令；工作区变更留给人工或 CI 提交（§16.6 步骤 5）",
        )
    )

    return _report(args, state, checks, write=True)


def _report(
    args: argparse.Namespace,
    state: FinalizationState,
    checks: list[Check],
    *,
    write: bool,
    abort: str | None = None,
) -> int:
    failed = [check for check in checks if check.status == "FAIL"]
    summary: dict[str, Any] = {
        "finalization_result": "FAILED" if failed or abort else "PASS",
        "cycle_id": state.cycle_id,
        "contract_version": state.contract_version,
        "coordination_canonical_hash": state.coordination_hash,
        "release_path": state.release_relative,
        "current_pointer": state.current_pointer.as_posix() if write else None,
        "ledger_path": state.ledger_path.as_posix() if write else None,
        "ledger_events_appended": [event["reason_code"] for event in state.appended_events],
        "ledger_already_finalized": state.already_finalized,
        "b_wiki": state.b_wiki,
        "c_wiki": state.c_wiki,
        "wrote_c_files": write and not abort,
        "checks": [check.as_dict() for check in checks],
    }
    if abort:
        summary["abort"] = abort
        print(f"finalization aborted: {abort}", file=sys.stderr)
    for check in checks:
        print(f"  [{check.index}] {check.status:4} {check.name} — {check.detail}")
    print(f"finalization_result = {summary['finalization_result']}")
    if args.json:
        print(canonical_json_dumps(summary))
    if summary["finalization_result"] == "PASS":
        print(
            "C allowlist 文件已准备完成；Cycle COMPLETE 仍需 C 合并 canonical branch 后重新验证"
            "（Master §16.6 / Spec 15:62）"
        )
        return EXIT_OK
    return EXIT_FAILED


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Foundation Contract Wiki finalization（Spec 10 / Spec 15，仅 Wiki）"
    )
    parser.add_argument("--coordination", required=True, type=Path, help="coordination 输出目录或 coordination.json")
    parser.add_argument("--release", required=True, type=Path, help="release 目录（Spec 10 为临时目录）")
    parser.add_argument("--ledger", type=Path, default=None, help=f"目标账本（默认临时路径；缺失退出 2）")
    parser.add_argument("--expected-coordination-hash", default=None, help="期望的 coordination canonical hash")
    parser.add_argument("--wiki-repo", type=Path, default=None, help="Wiki 仓路径（ancestry / diff 校验）")
    parser.add_argument("--b-wiki", default=None, help=f"B_wiki SHA（或环境变量 {ENV_B_WIKI}）")
    parser.add_argument("--c-wiki", default=None, help=f"C_wiki SHA（或环境变量 {ENV_C_WIKI}）")
    parser.add_argument("--release-relative", default=None, help="release 目录的仓内相对 POSIX 路径")
    parser.add_argument("--json", action="store_true", help="额外输出一行 canonical JSON 摘要")
    args = parser.parse_args(argv)
    _configure_stdio()
    try:
        return finalize(args)
    except UsageError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except FinalizationFailure as exc:
        print(f"finalization failed: {exc}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
