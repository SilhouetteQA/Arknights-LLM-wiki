#!/usr/bin/env python
"""Spec 10 — Cycle 协调器：`coordinate_cycle.py`（仅 Wiki）。

规范来源
--------
- Master §15.3（Level 2 Cross-repository Cycle Gate、状态闭集）
- Master §16.1–§16.5（身份模型、Candidate A / Evidence B、Cycle Plan、Coordination Report）
- Master §12.5（`contract-manifest.json` 字段）、§12.6（same version + different hash）
- Master §17 Stage 9–10、Appendix C.5 / D.2 / D.3 / I.4
- Spec 15:41-51（9 项 Coordination Checks）、Spec 10:110（fixture 命令）
- `FND-REL-001`–`FND-REL-006`、`FND-VER-005`、`GOV-STAT-004`

行为边界（**硬约束**）
----------------------
- 只做**只读** git 操作：``cat-file -e`` / ``merge-base --is-ancestor`` / ``diff`` / ``show`` /
  ``archive``。**不** ``fetch``、**不** ``checkout``、**不** 移动 main、**不** 推断"最新成功 commit"。
- 输入 plan 闭合后不得自动寻找替代 SHA：plan 中所有 commit 必须是完整 40/64 位十六进制，
  branch / tag / ``HEAD`` 等 ref 形式一律拒绝（``UsageError``，退出 2）。
- 不调用真实模型、不产生新 L3 Evidence、不 dump 环境变量、不把 token / 凭据写进 artifact 或日志。
- 只写 ``--output`` 目录下的 ``coordination.json`` / ``coordination.md``；写入前拒绝任何
  落在本仓 ``docs/contracts/**`` 的路径（``AGENT_CONTRACT_ALLOW_REAL_COORDINATION=1`` 可解锁）。
- 状态只能 ``PASS``/``READY_FOR_FINALIZATION``、``FAILED``、``DIVERGED``；
  **绝不**输出 `Cycle COMPLETE`（Master §16.5:1713、Spec 10:84）。

规范缺口与 provisional 决策（编号沿用 `output/spec10-normative-extraction-report.md`）
----------------------------------------------------------------------------------
- **G-17**（fixture / 仓根位置未定义）：规范 CLI 只有 ``--plan`` / ``--output``，但 plan
  按 §16.4 不含任何仓路径。本实现新增**可选** ``--wiki-repo`` / ``--coding-repo``：
  默认 wiki = 本脚本所在仓根，coding = 环境变量 ``AGENT_CONTRACT_CODING_REPO``，
  再退化为同级目录 ``../coding``。**不 clone、不 fetch**；解析不到即退出 2。
- **G-18**（退出码全文未定义）：``0`` = PASS；``1`` = 校验失败或 ``FAILED``/``DIVERGED``；
  ``2`` = 用法 / 配置错误（与 Spec 10 既有 ``validate_local.py`` 约定一致）。
- **G-15 / G-16**（expected hash 来源未定义）：只使用 plan 中显式声明的
  ``expected_contract_payload_hash``；不读另一仓、不推断。
- **§16.5 字段数**：Master §16.5 枚举 16 个字段（任务书称 17）。Spec 15:50 第 8 项额外要求
  记录 workflow version，故本实现输出 **17** 个字段 = §16.5 的 16 个 + ``workflow_version``
  （§16.5 原文为"至少包含"）。另附允许的扩展字段 ``checks`` / ``divergence_reason`` /
  ``cycle_plan_hash``，均可由 §16.5 的"至少包含"覆盖。
- **G-03 / G-18（reducer 接口）**：Spec 15:49 要求"可由 A 中 reducer 合法归约"，而
  ``scripts/contracts/status_ledger.py`` 的 Python API 未定义、其规范 CLI 为
  ``validate --ledger <path>``（Spec 10:109）。本实现只通过**该规范 CLI** 调用 A 树中的
  reducer（``cwd`` = A 树，并以 ``--spec-dir``/``--index`` 指向 A 树的子 Spec 与执行索引，
  使 genesis / DAG / Authority 全部来自 A），退出 0 记为可归约，非 0 记为
  ``SPEC_STATUS_CONFLICT``。A 中不存在 reducer 时**记为无法校验并失败**
  （``STATUS_REDUCER_UNAVAILABLE``），不自行实现 reducer、不静默通过。
- **check 6 扩展（§12.5）**：除两份 Evidence Manifest 外同时校验 B 中
  ``contract-manifest.json`` 的 ``canonical_payload_repository=wiki`` 与
  ``canonical_payload_commit=A_wiki``（"同一 Payload identity"）。
- **check 7 结果承载键名（SPEC_INCOMPLETE）**：L1/L2/L3 与 full regression 取自
  ``validation/<repo>/evidence-manifest.json``（D.2 最小 Schema 已定义）；``producer_coverage``
  同文件；``reproducibility`` / ``publication_scan`` 的**键名规范未定义**，本实现接受
  ``RUN_MANIFEST_RESULT_ALIASES`` 中的别名并**缺失即失败**（无法验证 ≠ 通过）。
- **G-08**：evidence publication allowlist 显式包含 ``changelog.md``。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

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
    read_text,
    sha256_hex,
)

def _configure_stdio() -> None:
    """Windows 控制台默认 GBK 会让中文/数学符号打印崩溃；强制 UTF-8 输出。

    artifact 本身始终以 UTF-8 落盘；这里只影响进度输出，绝不改变任何校验结果。
    """
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

#: 本工具身份版本（写入 coordination_tool_version）。工具自身改动即 bump。
COORDINATION_TOOL_VERSION = "1"

RELEASE_ROOT = Path("docs") / "contracts" / "releases"
LEDGER_RELATIVE = Path("docs") / "specs" / "foundation-contract" / "execution-status-events.jsonl"
STATUS_REDUCER_RELATIVE = Path("scripts") / "contracts" / "status_ledger.py"
#: 子 Spec 目录（genesis / DAG / index 的规范来源，即 reducer 的 ``--spec-dir``）。
SPEC_DIR_RELATIVE = LEDGER_RELATIVE.parent
EXECUTION_INDEX_NAME = "00-execution-index.md"
PAYLOAD_DIR = "agent_core"

#: §16.4 闭合 plan 的全部字段（缺失或多余一律视为 plan 不闭合）。
REQUIRED_PLAN_FIELDS: tuple[str, ...] = (
    "cycle_id",
    "target_contract_version",
    "expected_contract_payload_hash",
    "wiki_candidate_commit",
    "coding_candidate_commit",
    "wiki_evidence_commit",
    "coding_evidence_commit",
    "created_at",
)

SHA_FIELDS: tuple[str, ...] = (
    "wiki_candidate_commit",
    "coding_candidate_commit",
    "wiki_evidence_commit",
    "coding_evidence_commit",
)

#: D.2 要求的 validation artifact 清单（缺失即失败）。
EVIDENCE_ARTIFACTS: tuple[str, ...] = (
    "run-manifest.json",
    "evidence-manifest.json",
    "validation-report.md",
    "rule-traceability.json",
    "sanitized-replay-corpus.jsonl",
)

#: D.2 Evidence Manifest 最小 Schema 的必需字段。
EVIDENCE_MANIFEST_REQUIRED: tuple[str, ...] = (
    "contract_version",
    "contract_payload_hash",
    "verified_repository_commit",
    "repository",
    "environment",
    "evidence",
    "producer_coverage",
    "benchmark_reference_status",
)

#: §16.3：Evidence Manifest 不得包含自身身份。
EVIDENCE_MANIFEST_FORBIDDEN: tuple[str, ...] = ("evidence_manifest_hash", "evidence_commit")

#: L1 / L2 / L3 的 Evidence Manifest 键。
LAYER_KEYS: tuple[tuple[str, str], ...] = (
    ("contract_tests", "L1"),
    ("historical_replay", "L2"),
    ("fresh_smoke", "L3"),
)

#: 视为"通过"的取值（大小写不敏感）。
PASS_VALUES: frozenset[str] = frozenset({"PASS", "PASSED", "OK", "SATISFIED"})

#: 各仓 full regression 的允许取值（D.2:2503）。
REGRESSION_VALUES: dict[str, frozenset[str]] = {
    "wiki": frozenset({"PASS", "PASS_WITH_KNOWN_BASELINE_FAILURES"}),
    "coding": frozenset({"PASS"}),
}

#: check 7 的 reproducibility / publication scan 结果键别名（SPEC_INCOMPLETE，见模块 docstring）。
RUN_MANIFEST_RESULT_ALIASES: dict[str, tuple[str, ...]] = {
    "reproducibility": ("reproducibility", "reproducibility_status", "reproducibility_result"),
    "publication_scan": ("publication_scan", "publication_scan_status", "publication_scan_result"),
}

#: §12.5 contract-manifest.json 的必需字段。
CONTRACT_MANIFEST_REQUIRED: tuple[str, ...] = (
    "contract_version",
    "contract_payload_hash",
    "payload_descriptor_hash",
    "schema_set_hash",
    "canonical_payload_repository",
    "canonical_payload_commit",
)

_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_PAYLOAD_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")

#: 环境变量白名单（**只**读取这些；不做环境 dump）。
ENV_COORDINATOR_REPOSITORY = "AGENT_CONTRACT_COORDINATOR_REPOSITORY"
ENV_WORKFLOW_VERSION = "AGENT_CONTRACT_WORKFLOW_VERSION"
ENV_RUN_ID = "AGENT_CONTRACT_RUN_ID"
ENV_GITHUB_RUN_ID = "GITHUB_RUN_ID"
ENV_CODING_REPO = "AGENT_CONTRACT_CODING_REPO"
ENV_ALLOW_REAL_OUTPUT = "AGENT_CONTRACT_ALLOW_REAL_COORDINATION"

UNKNOWN = "unknown"


class UsageError(RuntimeError):
    """用法 / 配置错误（退出码 2）。"""


class CoordinationAbort(RuntimeError):
    """致命校验失败：无法继续，但仍产出 FAILED artifact（退出码 1）。"""


@dataclass
class Check:
    """单条 Coordination Check 的结果。"""

    index: int
    name: str
    status: str  # "PASS" / "FAIL" / "SKIP"
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"check": self.index, "name": self.name, "status": self.status, "detail": self.detail}


@dataclass
class Facts:
    """跨检查共享的中间事实。"""

    wiki_payload_hash: str | None = None
    coding_payload_hash: str | None = None
    wiki_contract_version: str | None = None
    coding_contract_version: str | None = None
    wiki_evidence_manifest_hash: str | None = None
    coding_evidence_manifest_hash: str | None = None
    diverged: bool = False
    divergence_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def payload_hash(self) -> str | None:
        return self.wiki_payload_hash or self.coding_payload_hash


# --------------------------------------------------------------------------- #
# 纯函数层（不触 git、不触文件系统之外的状态；可独立单测）
# --------------------------------------------------------------------------- #


def parse_sha(value: Any, field_name: str) -> str:
    """把 plan 字段解析为完整 commit SHA；ref 形式（HEAD/branch/tag/短 SHA）一律拒绝。"""
    if not isinstance(value, str) or not value.strip():
        raise UsageError(f"plan 字段 {field_name!r} 必须是非空字符串")
    candidate = value.strip()
    if not _SHA_RE.match(candidate):
        raise UsageError(
            f"plan 字段 {field_name!r} 不是完整 commit SHA（40 或 64 位小写十六进制）：{candidate!r}；"
            "输入闭合后不得接受 ref / 短 SHA（Master §16.4:1688）"
        )
    return candidate


def validate_plan(data: Any) -> dict[str, Any]:
    """校验 §16.4 闭合 plan；返回规范化后的字段字典。"""
    if not isinstance(data, dict):
        raise UsageError("cycle plan 必须是 JSON object")

    missing = [name for name in REQUIRED_PLAN_FIELDS if name not in data]
    if missing:
        raise UsageError(f"cycle plan 缺少字段：{missing}（Master §16.4）")
    extra = sorted(set(data) - set(REQUIRED_PLAN_FIELDS))
    if extra:
        raise UsageError(f"cycle plan 含未定义字段：{extra}（§16.4 要求输入闭合，不得自行扩展）")

    plan: dict[str, Any] = {}
    for name in SHA_FIELDS:
        plan[name] = parse_sha(data[name], name)

    for name in ("cycle_id", "target_contract_version"):
        value = data[name]
        if not isinstance(value, str) or not value.strip():
            raise UsageError(f"plan 字段 {name!r} 必须是非空字符串")
        plan[name] = value.strip()

    if not _SEMVER_RE.match(plan["target_contract_version"]):
        raise UsageError(
            f"plan 字段 'target_contract_version' 形状非法：{plan['target_contract_version']!r}"
        )

    expected = data["expected_contract_payload_hash"]
    if not isinstance(expected, str) or not _PAYLOAD_HASH_RE.match(expected):
        raise UsageError(
            "plan 字段 'expected_contract_payload_hash' 必须是 sha256:<64 hex>："
            f"{expected!r}"
        )
    plan["expected_contract_payload_hash"] = expected

    created_at = data["created_at"]
    if not isinstance(created_at, str) or not _RFC3339_RE.match(created_at):
        raise UsageError(f"plan 字段 'created_at' 必须是 RFC3339 时间戳：{created_at!r}")
    plan["created_at"] = created_at
    return plan


def evidence_publication_allowlist(version: str, repository: str) -> tuple[str, ...]:
    """§16.3 / Spec 14:25-39 的 A→B 允许变更集合（G-08：显式含 changelog.md）。"""
    if repository not in {"wiki", "coding"}:
        raise UsageError(f"未知 repository：{repository!r}")
    release = f"docs/contracts/releases/{version}"
    validation = f"{release}/validation/{repository}"
    allowed = [
        f"{release}/contract-manifest.json",
        f"{release}/changelog.md",
        f"{validation}/run-manifest.json",
        f"{validation}/evidence-manifest.json",
        f"{validation}/validation-report.md",
        f"{validation}/rule-traceability.json",
        f"{validation}/sanitized-replay-corpus.jsonl",
    ]
    if repository == "wiki":
        allowed.append(LEDGER_RELATIVE.as_posix())
    return tuple(allowed)


def check_diff_allowlist(
    changes: Iterable[tuple[str, str]], *, version: str, repository: str
) -> list[str]:
    """纯函数：A→B diff 必须 ⊆ evidence publication allowlist，且不得删除 / 改名。

    :param changes: ``(status, path)`` 序列，来自 ``git diff --name-status``。
    """
    allowlist = set(evidence_publication_allowlist(version, repository))
    errors: list[str] = []
    for status, path in changes:
        code = status[:1].upper()
        if code in {"D", "R", "C", "T", "U", "X"}:
            errors.append(f"A→B 出现非追加变更 {status} {path}（B tree 必须 = A tree + allowlist 新增）")
            continue
        if path not in allowlist:
            errors.append(f"A→B diff 越界：{status} {path} 不在 {repository} publication allowlist 内")
    return errors


def check_ledger_append_only(previous: bytes, current: bytes) -> list[str]:
    """纯函数：Wiki Ledger 在 B 中必须是 A 字节的**严格前缀 + 非空追加**。

    依据 §16.3:1671 / I.4:2840-2852 / GOV-STAT-004：旧字节不得修改、删除或重排。
    """
    errors: list[str] = []
    if not current:
        errors.append("Wiki Ledger 在 B 中缺失或为空（Spec 14 必须追加 Spec 11–14 事件）")
        return errors
    if not current.startswith(previous):
        errors.append(
            "Wiki Ledger 非纯追加：B 的前 "
            f"{min(len(previous), len(current))} 字节不是 A 的逐字节前缀（GOV-STAT-004）"
        )
        return errors
    appended = current[len(previous) :]
    if not appended:
        errors.append("Wiki Ledger 未追加任何字节（B 必须包含 Spec 11–14 的 append-only 事件）")
        return errors
    if not current.endswith(b"\n"):
        errors.append("Wiki Ledger 追加部分未以换行结束（JSONL 每行必须是完整 event）")
    for offset, raw_line in enumerate(appended.split(b"\n")):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"Wiki Ledger 追加行不是合法 UTF-8 JSON（第 {offset + 1} 行）：{exc}")
            continue
        if not isinstance(record, dict):
            errors.append(f"Wiki Ledger 追加行不是 JSON object（第 {offset + 1} 行）")
            continue
        if canonical_json_dumps(record).encode("utf-8") != line:
            errors.append(
                f"Wiki Ledger 追加行不是 canonical JSON（第 {offset + 1} 行）："
                "event 必须按键名排序的单行 canonical JSON"
            )
    return errors


# --------------------------------------------------------------------------- #
# git 只读交互层
# --------------------------------------------------------------------------- #


def _git(repo: Path, args: Sequence[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:  # pragma: no cover - 环境无 git
        raise UsageError("找不到 git 可执行文件；Coordination 需要只读 git 访问") from exc
    except subprocess.TimeoutExpired as exc:  # pragma: no cover
        raise CoordinationAbort(f"git {' '.join(args)} 超时") from exc


def require_repo(repo: Path, label: str) -> None:
    if not repo.is_dir():
        raise UsageError(f"{label} 仓路径不存在：{repo}")
    proc = _git(repo, ["rev-parse", "--git-dir"])
    if proc.returncode != 0:
        raise UsageError(f"{label} 不是 git 仓库：{repo}（{proc.stderr.strip()}）")


def commit_exists(repo: Path, sha: str) -> bool:
    """``git cat-file -e <sha>^{commit}`` 级别校验（不 fetch、不 checkout）。"""
    return _git(repo, ["cat-file", "-e", f"{sha}^{{commit}}"]).returncode == 0


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    return _git(repo, ["merge-base", "--is-ancestor", ancestor, descendant]).returncode == 0


def changed_paths(repo: Path, base: str, head: str) -> list[tuple[str, str]]:
    proc = _git(repo, ["diff", "--name-status", "--no-renames", "--no-ext-diff", base, head])
    if proc.returncode != 0:
        raise CoordinationAbort(f"git diff {base}..{head} 失败：{proc.stderr.strip()}")
    changes: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            changes.append((parts[0].strip(), parts[1].strip()))
    return changes


def read_blob(repo: Path, sha: str, relative: Path | str) -> bytes | None:
    """读取某 commit 中的文件字节；不存在返回 None（不落盘、不 checkout）。"""
    proc = subprocess.run(
        ["git", "show", f"{sha}:{Path(relative).as_posix()}"],
        cwd=str(repo),
        capture_output=True,
        timeout=300,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def extract_paths(repo: Path, sha: str, paths: Sequence[str], dest: Path) -> Path:
    """把某 commit 的给定子树导出到 ``dest``（``git archive`` + tar 解包，工作区不动）。"""
    proc = subprocess.run(
        ["git", "archive", "--format=tar", sha, *paths],
        cwd=str(repo),
        capture_output=True,
        timeout=600,
    )
    if proc.returncode != 0:
        raise CoordinationAbort(
            f"git archive {sha} {' '.join(paths)} 失败：{proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as archive:
        try:
            archive.extractall(dest, filter="data")
        except TypeError:  # pragma: no cover - Python < 3.12
            archive.extractall(dest)
    return dest


# --------------------------------------------------------------------------- #
# check 1–3
# --------------------------------------------------------------------------- #


def check_fixed_commits(
    index: int, repo: Path, label: str, plan: dict[str, Any]
) -> Check:
    """check 1：两仓各自的固定 A 与 B 存在且可解析为 commit。"""
    pairs = {
        f"{label}_candidate_commit": plan[f"{label}_candidate_commit"],
        f"{label}_evidence_commit": plan[f"{label}_evidence_commit"],
    }
    missing = [name for name, sha in pairs.items() if not commit_exists(repo, sha)]
    if missing:
        detail = "；".join(f"{name}={pairs[name]} 不存在或不是 commit" for name in missing)
        return Check(index, f"checkout 固定 A/B（{label}）", "FAIL", detail)
    values = "，".join(f"{name.replace('_commit', '')}={sha[:12]}" for name, sha in pairs.items())
    return Check(index, f"checkout 固定 A/B（{label}）", "PASS", values)


def check_ancestry(index: int, repo: Path, label: str, plan: dict[str, Any]) -> Check:
    """check 2：每仓 ``A is ancestor of B``。"""
    candidate = plan[f"{label}_candidate_commit"]
    evidence = plan[f"{label}_evidence_commit"]
    if not is_ancestor(repo, candidate, evidence):
        return Check(
            index,
            f"A is ancestor of B（{label}）",
            "FAIL",
            f"merge-base --is-ancestor {candidate[:12]} {evidence[:12]} 返回非 0",
        )
    return Check(index, f"A is ancestor of B（{label}）", "PASS", f"{candidate[:12]} → {evidence[:12]}")


def check_diff(index: int, repo: Path, label: str, plan: dict[str, Any], version: str) -> Check:
    """check 3：``diff(A, B) ⊆ evidence publication allowlist``。"""
    candidate = plan[f"{label}_candidate_commit"]
    evidence = plan[f"{label}_evidence_commit"]
    changes = changed_paths(repo, candidate, evidence)
    errors = check_diff_allowlist(changes, version=version, repository=label)
    if errors:
        return Check(index, f"A→B diff allowlist（{label}）", "FAIL", "；".join(errors))
    listing = "，".join(f"{status}:{path}" for status, path in changes) or "(空 diff)"
    return Check(
        index, f"A→B diff allowlist（{label}）", "PASS", f"{len(changes)} 个文件全部在 allowlist 内：{listing}"
    )


# --------------------------------------------------------------------------- #
# check 4：重算 version 与 Payload Hash
# --------------------------------------------------------------------------- #


def _payload_identity(repo: Path, sha: str, workdir: Path) -> tuple[str | None, str | None, list[str]]:
    """导出 A 的 payload 子树并用共享 ``verify_tree`` 重算 version / payload hash。"""
    tree_root = extract_paths(repo, sha, [PAYLOAD_DIR], workdir)
    from agent_core.contracts.tooling import verify_payload as vp

    try:
        report = vp.verify_tree(tree_root)
    except Exception as exc:  # payload 结构不可解析
        return None, None, [f"verify_tree 异常：{exc}"]

    descriptor_path = tree_root / PAYLOAD_DIR / "contracts" / "payload-descriptor.json"
    version: str | None = None
    if descriptor_path.is_file():
        try:
            version = json.loads(read_text(descriptor_path)).get("contract_version")
        except (json.JSONDecodeError, ValueError) as exc:
            return None, None, [f"payload-descriptor.json 不可解析：{exc}"]

    errors = list(report.errors)
    if version != vp.CONTRACT_VERSION:
        errors.append(
            f"A 中 descriptor.contract_version={version!r} 与本工具 CONTRACT_VERSION="
            f"{vp.CONTRACT_VERSION!r} 不一致"
        )
    return report.payload_hash, version, errors


def check_payload_identity(index: int, plan: dict[str, Any], facts: Facts, workdir: Path, repos: dict[str, Path]) -> Check:
    """check 4：重算两仓 contract version 与 Payload Hash；同版本不同 hash → DIVERGED。"""
    details: list[str] = []
    for label, repo in repos.items():
        payload_hash, version, errors = _payload_identity(
            repo, plan[f"{label}_candidate_commit"], workdir / label
        )
        setattr(facts, f"{label}_payload_hash", payload_hash)
        setattr(facts, f"{label}_contract_version", version)
        details.append(f"{label}: version={version} payload={payload_hash}")
        if errors:
            facts.errors.extend(f"[{label}] {error}" for error in errors)

    target = plan["target_contract_version"]
    expected = plan["expected_contract_payload_hash"]
    wiki_hash, coding_hash = facts.wiki_payload_hash, facts.coding_payload_hash
    wiki_version, coding_version = facts.wiki_contract_version, facts.coding_contract_version

    if facts.errors:
        return Check(index, "重算 contract version / Payload Hash", "FAIL", "；".join(details + facts.errors))

    if wiki_version != coding_version:
        facts.errors.append(
            f"两仓 contract version 不同（wiki={wiki_version}, coding={coding_version}）→ FAILED"
        )
    elif wiki_hash != coding_hash:
        facts.diverged = True
        facts.divergence_reason = (
            f"相同 contract version {wiki_version} 但 Payload Hash 不同："
            f"wiki={wiki_hash}, coding={coding_hash}（Master §15.3 / §12.6）"
        )
    elif wiki_hash != expected:
        facts.errors.append(
            f"实际 Payload Hash {wiki_hash} 与 plan.expected_contract_payload_hash {expected} 不一致"
            "（§15.3 FAILED：plan 与实测身份不匹配）"
        )
    if wiki_version != target or coding_version != target:
        facts.errors.append(
            f"contract version 与 plan.target_contract_version={target} 不一致"
            f"（wiki={wiki_version}, coding={coding_version}）"
        )

    if facts.diverged:
        return Check(
            index, "重算 contract version / Payload Hash", "FAIL", "DIVERGED：" + str(facts.divergence_reason)
        )
    if facts.errors:
        return Check(index, "重算 contract version / Payload Hash", "FAIL", "；".join(details + facts.errors))
    return Check(index, "重算 contract version / Payload Hash", "PASS", "；".join(details))


# --------------------------------------------------------------------------- #
# check 5 / 6：Evidence Manifest 与独立 hash
# --------------------------------------------------------------------------- #


def _validation_dir(version: str, label: str) -> str:
    return f"{RELEASE_ROOT.as_posix()}/{version}/validation/{label}"


def _load_manifest(
    repo: Path, sha: str, relative: str, label: str
) -> tuple[dict[str, Any] | None, list[str]]:
    blob = read_blob(repo, sha, relative)
    if blob is None:
        return None, [f"[{label}] B 中缺少 {relative}"]
    try:
        manifest = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, [f"[{label}] {relative} 不是合法 JSON：{exc}"]
    if not isinstance(manifest, dict):
        return None, [f"[{label}] {relative} 不是 JSON object"]
    return manifest, []


def check_evidence_manifests(index: int, plan: dict[str, Any], facts: Facts, repos: dict[str, Path]) -> Check:
    """check 5 + 6：Manifest 引用各自 A 与同一 Payload、Evidence commit 为 B；计算独立 hash。"""
    version = plan["target_contract_version"]
    problems: list[str] = []
    details: list[str] = []

    for label, repo in repos.items():
        candidate = plan[f"{label}_candidate_commit"]
        evidence_commit = plan[f"{label}_evidence_commit"]
        relative = f"{_validation_dir(version, label)}/evidence-manifest.json"
        manifest, errors = _load_manifest(repo, evidence_commit, relative, label)
        problems.extend(errors)
        if manifest is None:
            continue

        missing = sorted(set(EVIDENCE_MANIFEST_REQUIRED) - set(manifest))
        if missing:
            problems.append(f"[{label}] Evidence Manifest 缺少字段：{missing}")
        forbidden = sorted(set(EVIDENCE_MANIFEST_FORBIDDEN) & set(manifest))
        if forbidden:
            problems.append(f"[{label}] Evidence Manifest 不得包含自身身份字段：{forbidden}（§16.3）")

        if manifest.get("contract_version") != version:
            problems.append(
                f"[{label}] Evidence Manifest contract_version={manifest.get('contract_version')!r} ≠ {version!r}"
            )
        if manifest.get("contract_payload_hash") != facts.payload_hash:
            problems.append(
                f"[{label}] Evidence Manifest contract_payload_hash={manifest.get('contract_payload_hash')!r} "
                f"≠ 实测 {facts.payload_hash!r}"
            )
        if manifest.get("verified_repository_commit") != candidate:
            problems.append(
                f"[{label}] verified_repository_commit={manifest.get('verified_repository_commit')!r} "
                f"≠ 对应 Candidate A {candidate!r}"
            )
        if manifest.get("repository") != label:
            problems.append(f"[{label}] Evidence Manifest repository={manifest.get('repository')!r} ≠ {label!r}")

        manifest_hash = sha256_hex(canonical_json_bytes(manifest))
        setattr(facts, f"{label}_evidence_manifest_hash", manifest_hash)
        details.append(f"{label} manifest_hash={manifest_hash}")

    # §12.5：contract-manifest 必须存在且 canonical payload provenance 固定指向 A_wiki。
    manifest_rel = f"{RELEASE_ROOT.as_posix()}/{version}/contract-manifest.json"
    contract_manifest: dict[str, Any] | None = None
    for label, repo in repos.items():
        loaded, errors = _load_manifest(repo, plan[f"{label}_evidence_commit"], manifest_rel, label)
        problems.extend(errors)
        if loaded is None:
            continue
        if contract_manifest is None:
            contract_manifest = loaded
            missing = sorted(set(CONTRACT_MANIFEST_REQUIRED) - set(loaded))
            if missing:
                problems.append(f"contract-manifest.json 缺少字段：{missing}（§12.5）")
            if loaded.get("canonical_payload_repository") != "wiki":
                problems.append(
                    "contract-manifest.json canonical_payload_repository 必须是 'wiki'（§12.5）"
                )
            if loaded.get("canonical_payload_commit") != plan["wiki_candidate_commit"]:
                problems.append(
                    "contract-manifest.json canonical_payload_commit 必须指向 A_wiki（§12.5）"
                )
            if loaded.get("contract_payload_hash") != facts.payload_hash:
                problems.append("contract-manifest.json contract_payload_hash 与实测 Payload Hash 不一致")
        elif loaded != contract_manifest:
            problems.append(f"[{label}] contract-manifest.json 与另一仓内容不同（§12.5 要求同步后内容不变）")

    if facts.wiki_evidence_manifest_hash and facts.coding_evidence_manifest_hash:
        if facts.wiki_evidence_manifest_hash == facts.coding_evidence_manifest_hash:
            details.append("两仓 Evidence Manifest Hash 相同（合法，但非规范期望：两仓证据内容通常不同）")
        else:
            details.append("两项目 Evidence Manifest Hash 不同（正常事实，§16.3:1660）")

    if problems:
        return Check(index, "Evidence Manifest 引用与独立 hash（check 5+6）", "FAIL", "；".join(problems))
    return Check(index, "Evidence Manifest 引用与独立 hash（check 5+6）", "PASS", "；".join(details))


# --------------------------------------------------------------------------- #
# check 7：L1/L2/L3、full regression、producer coverage、reproducibility、publication scan
# --------------------------------------------------------------------------- #


def _coverage_ok(coverage: Any) -> list[str]:
    """producer coverage 判定（SPEC_INCOMPLETE：结构未定义，取最小可行语义）。"""
    errors: list[str] = []
    if not isinstance(coverage, list) or not coverage:
        return ["producer_coverage 缺失或为空（§14 / Spec 13 要求 required stages satisfied）"]
    for item in coverage:
        if isinstance(item, str):
            if item.upper() not in PASS_VALUES:
                errors.append(f"producer_coverage 条目取值非通过：{item!r}")
        elif isinstance(item, dict):
            values = [str(value).upper() for value in item.values() if isinstance(value, str)]
            if not values or not any(value in PASS_VALUES for value in values):
                errors.append(f"producer_coverage 条目无通过状态：{item!r}")
        else:
            errors.append(f"producer_coverage 条目类型非法：{item!r}")
    return errors


def _run_manifest_results(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for concept, aliases in RUN_MANIFEST_RESULT_ALIASES.items():
        found = next((manifest[key] for key in aliases if key in manifest), None)
        if found is None:
            errors.append(
                f"run-manifest.json 缺少 {concept} 结果（接受键名 {list(aliases)}；"
                "SPEC_INCOMPLETE：结果承载键名未定义，缺失即失败）"
            )
        elif str(found).upper() not in PASS_VALUES:
            errors.append(f"run-manifest.json {concept}={found!r} 非 PASS")
    return errors


def check_validation_results(index: int, plan: dict[str, Any], repos: dict[str, Path]) -> Check:
    """check 7：L1/L2/L3、full regression、producer coverage、reproducibility、publication scan。"""
    version = plan["target_contract_version"]
    problems: list[str] = []
    details: list[str] = []

    for label, repo in repos.items():
        evidence_commit = plan[f"{label}_evidence_commit"]
        validation_dir = _validation_dir(version, label)
        for artifact in EVIDENCE_ARTIFACTS:
            if read_blob(repo, evidence_commit, f"{validation_dir}/{artifact}") is None:
                problems.append(f"[{label}] B 中缺少 validation artifact：{validation_dir}/{artifact}")
        evidence_manifest, errors = _load_manifest(
            repo, evidence_commit, f"{validation_dir}/evidence-manifest.json", label
        )
        problems.extend(errors)
        run_manifest, errors = _load_manifest(
            repo, evidence_commit, f"{validation_dir}/run-manifest.json", label
        )
        problems.extend(errors)
        if evidence_manifest is None or run_manifest is None:
            continue

        evidence = evidence_manifest.get("evidence")
        if not isinstance(evidence, dict):
            problems.append(f"[{label}] Evidence Manifest evidence 必须是 object")
            continue
        for key, layer in LAYER_KEYS:
            value = evidence.get(key)
            if value is None:
                problems.append(f"[{label}] {layer} 结果缺失（evidence.{key}）")
            elif str(value).upper() not in PASS_VALUES:
                problems.append(f"[{label}] {layer} 结果非 PASS：evidence.{key}={value!r}")
        regression = evidence.get("full_regression")
        if regression is None:
            problems.append(f"[{label}] full regression 结果缺失（evidence.full_regression）")
        elif str(regression).upper() not in REGRESSION_VALUES[label]:
            problems.append(
                f"[{label}] full regression 状态 {regression!r} 不在允许集合 "
                f"{sorted(REGRESSION_VALUES[label])}（D.2:2503）"
            )

        problems.extend(f"[{label}] {error}" for error in _coverage_ok(evidence_manifest.get("producer_coverage")))
        problems.extend(f"[{label}] {error}" for error in _run_manifest_results(run_manifest))
        details.append(
            f"{label}: L1/L2/L3={[evidence.get(key) for key, _ in LAYER_KEYS]} "
            f"regression={regression} coverage={len(evidence_manifest.get('producer_coverage') or [])}"
        )

    if problems:
        return Check(index, "L1/L2/L3 + regression + coverage + reproducibility + scan", "FAIL", "；".join(problems))
    return Check(index, "L1/L2/L3 + regression + coverage + reproducibility + scan", "PASS", "；".join(details))


# --------------------------------------------------------------------------- #
# check 8：Wiki Ledger 纯追加 + A 中 reducer 合法归约
# --------------------------------------------------------------------------- #


def check_wiki_ledger(
    index: int, plan: dict[str, Any], wiki_repo: Path, workdir: Path
) -> Check:
    candidate = plan["wiki_candidate_commit"]
    evidence_commit = plan["wiki_evidence_commit"]

    previous = read_blob(wiki_repo, candidate, LEDGER_RELATIVE) or b""
    current = read_blob(wiki_repo, evidence_commit, LEDGER_RELATIVE)
    if current is None:
        return Check(
            index,
            "Wiki Ledger 纯追加 + A reducer 归约",
            "FAIL",
            f"B 中缺少 {LEDGER_RELATIVE.as_posix()}",
        )

    errors = check_ledger_append_only(previous, current)
    if errors:
        return Check(index, "Wiki Ledger 纯追加 + A reducer 归约", "FAIL", "；".join(errors))

    appended = current[len(previous) :]
    appended_lines = len([line for line in appended.split(b"\n") if line.strip()])

    reducer_blob = read_blob(wiki_repo, candidate, STATUS_REDUCER_RELATIVE)
    if reducer_blob is None:
        return Check(
            index,
            "Wiki Ledger 纯追加 + A reducer 归约",
            "FAIL",
            f"纯追加 OK（追加 {len(appended)} 字节 / {appended_lines} 行），但 "
            f"STATUS_REDUCER_UNAVAILABLE：A({candidate[:12]}) 中不存在 "
            f"{STATUS_REDUCER_RELATIVE.as_posix()}，无法依 Spec 15:49 校验归约；"
            "本工具不自行实现 reducer（Spec 10:78 要求该 reducer 属于 A）",
        )

    tree_root = extract_paths(
        wiki_repo,
        candidate,
        [PAYLOAD_DIR, STATUS_REDUCER_RELATIVE.as_posix(), SPEC_DIR_RELATIVE.as_posix()],
        workdir / "reducer",
    )
    reducer_path = tree_root / STATUS_REDUCER_RELATIVE
    spec_dir = tree_root / SPEC_DIR_RELATIVE
    ledger_file = workdir / "ledger-under-test.jsonl"
    ledger_file.write_bytes(current)

    # Spec 10:109 冻结的 reducer CLI：`status_ledger.py validate --ledger <path>`。
    command = [
        sys.executable,
        str(reducer_path),
        "validate",
        "--ledger",
        str(ledger_file),
        "--spec-dir",
        str(spec_dir),
    ]
    index_path = spec_dir / EXECUTION_INDEX_NAME
    if index_path.is_file():
        command += ["--index", str(index_path)]
    try:
        proc = subprocess.run(
            command,
            cwd=str(tree_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:  # pragma: no cover - 环境异常
        return Check(
            index,
            "Wiki Ledger 纯追加 + A reducer 归约",
            "FAIL",
            f"呼出 A 中 reducer 失败：{exc}",
        )

    output = (proc.stdout or "").strip()
    err_output = (proc.stderr or "").strip()
    tail = " | ".join(part for part in (output, err_output) if part)
    if proc.returncode != 0:
        conflict = "SPEC_STATUS_CONFLICT" in f"{output}\n{err_output}"
        return Check(
            index,
            "Wiki Ledger 纯追加 + A reducer 归约",
            "FAIL",
            f"纯追加 OK，但 A 中 reducer 判定非法"
            f"（exit {proc.returncode}{'，SPEC_STATUS_CONFLICT' if conflict else ''}）：{tail[-600:]}",
        )
    return Check(
        index,
        "Wiki Ledger 纯追加 + A reducer 归约",
        "PASS",
        f"追加 {len(appended)} 字节 / {appended_lines} 行；A 中 reducer（{STATUS_REDUCER_RELATIVE.as_posix()}）"
        f"归约通过：{tail[-200:] or '(无输出)'}",
    )


# --------------------------------------------------------------------------- #
# check 9：协调身份记录
# --------------------------------------------------------------------------- #


def collect_provenance(plan: dict[str, Any]) -> dict[str, Any]:
    """check 9：records coordinator repository / commit / tool version / workflow version / run id。"""
    repository = os.environ.get(ENV_COORDINATOR_REPOSITORY, "").strip() or "wiki"
    workflow_version = os.environ.get(ENV_WORKFLOW_VERSION, "").strip() or UNKNOWN
    run_id = (
        os.environ.get(ENV_RUN_ID, "").strip()
        or os.environ.get(ENV_GITHUB_RUN_ID, "").strip()
        or UNKNOWN
    )
    return {
        "coordinator_repository": repository,
        # provisional：协调身份 = A 中冻结的 coordinator 工具身份（Spec 15 Retry/Rollback）。
        "coordinator_commit": plan["wiki_candidate_commit"],
        "coordination_tool_version": COORDINATION_TOOL_VERSION,
        "workflow_version": workflow_version,
        "coordination_run_id": run_id,
    }


def check_provenance(index: int, provenance: dict[str, Any]) -> Check:
    unknown = [
        name
        for name in ("workflow_version", "coordination_run_id")
        if provenance[name] == UNKNOWN
    ]
    detail = "；".join(f"{key}={value}" for key, value in provenance.items())
    if unknown:
        detail += f"；{unknown} 未由环境提供，按规范记为 {UNKNOWN!r}（如实标注，未推断）"
    return Check(index, "记录协调身份（repository/commit/tool/workflow/run）", "PASS", detail)


# --------------------------------------------------------------------------- #
# 编排
# --------------------------------------------------------------------------- #


def resolve_repos(args: argparse.Namespace) -> dict[str, Path]:
    wiki_repo = Path(args.wiki_repo).resolve() if args.wiki_repo else REPO_ROOT
    if args.coding_repo:
        coding_repo = Path(args.coding_repo).resolve()
    else:
        env_repo = os.environ.get(ENV_CODING_REPO, "").strip()
        if env_repo:
            coding_repo = Path(env_repo).resolve()
        else:
            candidate = (REPO_ROOT.parent / "coding").resolve()
            coding_repo = candidate
    repos = {"wiki": wiki_repo, "coding": coding_repo}
    for label, repo in repos.items():
        require_repo(repo, label)
    return repos


def guard_output(output: Path) -> Path:
    """拒绝把 artifact 写进本仓 docs/contracts/**（Spec 10 fixture-only 约束）。"""
    resolved = output.resolve()
    guarded = (REPO_ROOT / "docs" / "contracts").resolve()
    if guarded in resolved.parents or resolved == guarded:
        if os.environ.get(ENV_ALLOW_REAL_OUTPUT, "").strip() != "1":
            raise UsageError(
                f"--output 指向本仓真实发布树 {resolved}；Spec 10 只做 fixture 验证，"
                f"如需写入请显式设置 {ENV_ALLOW_REAL_OUTPUT}=1"
            )
    if resolved.exists() and resolved.is_file():
        raise UsageError(f"--output 必须是目录，实际是文件：{resolved}")
    return resolved


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Cycle Coordination Report — {report['cycle_id']}",
        "",
        f"- coordination_result: `{report['coordination_result']}`",
        f"- cycle_state: `{report['cycle_state']}`",
        f"- contract_version: `{report['contract_version']}`",
        f"- contract_payload_hash: `{report['contract_payload_hash']}`",
        f"- completed_at: `{report['completed_at']}`",
        "",
        "> Coordination PASS 不等于 `Cycle COMPLETE`：COMPLETE 只能由 C_wiki 合并后的验证产生"
        "（Master §15.3:1594、§16.5:1713）。",
        "",
        "## 固定 A/B",
        "",
        "| 仓库 | Candidate A | Evidence B | Evidence Manifest Hash |",
        "|---|---|---|---|",
    ]
    for label in ("wiki", "coding"):
        lines.append(
            f"| {label} | `{report[f'{label}_candidate_commit']}` | "
            f"`{report[f'{label}_evidence_commit']}` | "
            f"`{report[f'{label}_evidence_manifest_hash'] or '(未计算)'}` |"
        )
    lines += [
        "",
        "## 协调身份",
        "",
        f"- coordinator_repository: `{report['coordinator_repository']}`",
        f"- coordinator_commit: `{report['coordinator_commit']}`",
        f"- coordination_tool_version: `{report['coordination_tool_version']}`",
        f"- workflow_version: `{report['workflow_version']}`",
        f"- coordination_run_id: `{report['coordination_run_id']}`",
        "",
        "## Checks",
        "",
        "| # | 检查 | 状态 | 详情 |",
        "|---|---|---|---|",
    ]
    for check in report["checks"]:
        detail = str(check["detail"]).replace("|", "\\|")
        lines.append(f"| {check['check']} | {check['name']} | {check['status']} | {detail} |")
    if report.get("divergence_reason"):
        lines += ["", f"## DIVERGED 原因", "", report["divergence_reason"]]
    lines.append("")
    return "\n".join(lines)


def build_report(
    plan: dict[str, Any],
    checks: list[Check],
    facts: Facts,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    failed = [check for check in checks if check.status == "FAIL"]
    if facts.diverged:
        coordination_result, cycle_state = "DIVERGED", "DIVERGED"
    elif failed:
        coordination_result, cycle_state = "FAILED", "FAILED"
    else:
        coordination_result, cycle_state = "PASS", "READY_FOR_FINALIZATION"

    report: dict[str, Any] = {
        "cycle_id": plan["cycle_id"],
        "contract_version": plan["target_contract_version"],
        "contract_payload_hash": facts.payload_hash or plan["expected_contract_payload_hash"],
        "wiki_candidate_commit": plan["wiki_candidate_commit"],
        "coding_candidate_commit": plan["coding_candidate_commit"],
        "wiki_evidence_commit": plan["wiki_evidence_commit"],
        "coding_evidence_commit": plan["coding_evidence_commit"],
        "wiki_evidence_manifest_hash": facts.wiki_evidence_manifest_hash,
        "coding_evidence_manifest_hash": facts.coding_evidence_manifest_hash,
        "coordination_result": coordination_result,
        "cycle_state": cycle_state,
        "coordinator_repository": provenance["coordinator_repository"],
        "coordinator_commit": provenance["coordinator_commit"],
        "coordination_tool_version": provenance["coordination_tool_version"],
        "coordination_run_id": provenance["coordination_run_id"],
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # §16.5 之外但 Spec 15:50 第 8 项要求记录的 workflow version。
        "workflow_version": provenance["workflow_version"],
        # 扩展诊断字段（§16.5 "至少包含"）。
        "cycle_plan_hash": sha256_hex(canonical_json_bytes(plan)),
        "checks": [check.as_dict() for check in checks],
    }
    if facts.divergence_reason:
        report["divergence_reason"] = facts.divergence_reason
    return report


def write_artifacts(output_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "coordination.json"
    md_path = output_dir / "coordination.md"
    text = canonical_json_dumps(report) + "\n"
    json_path.write_text(text, encoding="utf-8", newline="\n")
    md_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return json_path, md_path


def load_plan_file(plan_path: Path) -> dict[str, Any]:
    target = plan_path / "cycle-plan.json" if plan_path.is_dir() else plan_path
    if not target.is_file():
        raise UsageError(f"cycle plan 不存在：{target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UsageError(f"cycle plan 不是合法 UTF-8 JSON：{exc}") from exc
    return validate_plan(data)


def coordinate(args: argparse.Namespace) -> int:
    plan = load_plan_file(Path(args.plan))
    output_dir = guard_output(Path(args.output))
    repos = resolve_repos(args)
    version = plan["target_contract_version"]
    facts = Facts()
    checks: list[Check] = []

    with tempfile.TemporaryDirectory(prefix="coordination-") as tmp:
        workdir = Path(tmp)

        # check 1：固定 A/B 存在且可解析（两仓）
        repo_pairs = list(repos.items())
        for label, repo in repo_pairs:
            check = check_fixed_commits(1, repo, label, plan)
            checks.append(check)
        checks = _merge(checks, 1, "checkout 固定 A/B（两仓）")

        if any(check.status == "FAIL" for check in checks if check.index == 1):
            return _finalize(args, output_dir, plan, checks, facts, provenance_only=True)

        # check 2：ancestry
        for label, repo in repo_pairs:
            checks.append(check_ancestry(2, repo, label, plan))
        checks = _merge(checks, 2, "A is ancestor of B（两仓）")
        if any(check.status == "FAIL" for check in checks if check.index == 2):
            return _finalize(args, output_dir, plan, checks, facts, provenance_only=True)

        # check 3：diff allowlist
        for label, repo in repo_pairs:
            checks.append(check_diff(3, repo, label, plan, version))
        checks = _merge(checks, 3, "A→B diff 必须是 evidence publication allowlist 的子集（两仓）")
        if any(check.status == "FAIL" for check in checks if check.index == 3):
            return _finalize(args, output_dir, plan, checks, facts, provenance_only=True)

        # check 4：version + payload hash（DIVERGED 判定）
        checks.append(check_payload_identity(4, plan, facts, workdir, repos))
        if facts.diverged or facts.errors:
            checks.extend(_skipped(5, 8, "上游 check 4 未通过：证据与账本校验不再具备意义"))
            checks.append(check_provenance(9, collect_provenance(plan)))
            return _finalize(args, output_dir, plan, checks, facts)

        # check 5+6：Evidence Manifest
        checks.append(check_evidence_manifests(5, plan, facts, repos))
        # check 7：validation results
        checks.append(check_validation_results(7, plan, repos))
        # check 8：wiki ledger
        checks.append(check_wiki_ledger(8, plan, repos["wiki"], workdir))
        # check 9：provenance
        checks.append(check_provenance(9, collect_provenance(plan)))

    return _finalize(args, output_dir, plan, checks, facts)


def _merge(checks: list[Check], index: int, name: str) -> list[Check]:
    """把同 index 的多仓检查（1–3）合并为单条以保持 Spec 15 的 9 项语义。"""
    grouped = [check for check in checks if check.index == index]
    others = [check for check in checks if check.index != index]
    failed = [check for check in grouped if check.status == "FAIL"]
    status = "FAIL" if failed else "PASS"
    detail = "；".join(f"{check.name} → {check.detail}" for check in grouped)
    return sorted([*others, Check(index, name, status, detail)], key=lambda item: item.index)


def _skipped(first: int, last: int, detail: str) -> list[Check]:
    names = {
        5: "Evidence Manifest 引用与独立 hash（check 5+6）",
        6: "Evidence Manifest 独立 hash（并入 check 5）",
        7: "L1/L2/L3 + regression + coverage + reproducibility + scan",
        8: "Wiki Ledger 纯追加 + A reducer 归约",
    }
    return [Check(index, names[index], "SKIP", detail) for index in range(first, last + 1) if index in names]


def _finalize(
    args: argparse.Namespace,
    output_dir: Path,
    plan: dict[str, Any],
    checks: list[Check],
    facts: Facts,
    *,
    provenance_only: bool = False,
) -> int:
    if provenance_only:
        checks = [*checks, check_provenance(9, collect_provenance(plan))]
    checks = sorted(checks, key=lambda item: item.index)
    report = build_report(plan, checks, facts, collect_provenance(plan))
    json_path, md_path = write_artifacts(output_dir, report)

    result = report["coordination_result"]
    print(f"coordination_result = {result}")
    print(f"cycle_state         = {report['cycle_state']}")
    print(f"contract_payload_hash = {report['contract_payload_hash']}")
    for check in checks:
        print(f"  [{check.index}] {check.status:4} {check.name} — {check.detail}")
    print(f"artifacts: {json_path}")
    print(f"           {md_path}")
    if result == "PASS":
        return EXIT_OK
    print(
        "Coordination 未通过；artifact 已按规范落盘（不修改任何仓、不产生新的 L3 Evidence）",
        file=sys.stderr,
    )
    return EXIT_FAILED


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Foundation Contract Cycle 协调器（Spec 10 / Spec 15，仅 Wiki）"
    )
    parser.add_argument("--plan", required=True, type=Path, help="闭合 cycle plan JSON（或含它的目录）")
    parser.add_argument("--output", required=True, type=Path, help="coordination artifact 输出目录")
    parser.add_argument("--wiki-repo", type=Path, default=None, help="Wiki 仓路径（默认本脚本所在仓）")
    parser.add_argument(
        "--coding-repo",
        type=Path,
        default=None,
        help=f"Coding 仓路径（默认环境变量 {ENV_CODING_REPO}，再退化为同级 ../coding）",
    )
    args = parser.parse_args(argv)
    _configure_stdio()
    try:
        return coordinate(args)
    except UsageError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except CoordinationAbort as exc:
        print(f"coordination aborted: {exc}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
