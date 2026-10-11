#!/usr/bin/env python
"""Spec 13 — L3 fresh smoke 的受控驱动器（A2 交付物）。

冻结的 ``python scripts/contracts/validate_local.py --gate smoke`` 按 G-13 provisional
**只校验已完成的 run**，不驱动业务路径；L3 的"真跑一遍"因此缺一个受控入口。
本工具就是这个入口：它跑**真实业务路径**（observe 模式），产出运行后汇总
``run-summary.json``（G-04），最后调用**同一个冻结 gate** 证明该 run 闭合。

CLI（A2；``--run-manifest`` 唯一必需参数）::

    python scripts/contracts/run_l3_smoke.py --run-manifest config/contracts/smoke-v0.1.json
    python scripts/contracts/run_l3_smoke.py --run-manifest <manifest> --case-source <bench.jsonl>
    python scripts/contracts/run_l3_smoke.py --run-manifest <manifest> --json

前置（与 ``gate_smoke`` 完全同款，缺一即配置错误 exit 2）::

    AGENT_CONTRACT_MODE    == "observe"
    AGENT_CONTRACT_RUN_ID  == manifest["run_id"]
    AGENT_CONTRACT_COMMIT  40 位小写 hex（manifest.repository_commit 为 null 时）
    AGENT_CONTRACT_EVIDENCE_DIR 会被本工具**覆盖**为 <repo>/<manifest.evidence_root>，
                          以保证业务子进程写证据的位置与 gate 读取的位置一致

业务命令（本仓）::

    <sys.executable> -m arknights_wiki.eval.runner \
        --bench <staging>/<run_id>/driver/bench-selected.jsonl \
        --out   <staging>/<run_id>/driver/out --mode direct --workers 1

staging 布局（``evidence_root`` 来自 manifest，默认 ``output/contract-validation/staging``）::

    <evidence_root>/<run_id>/events/<event_id>.json      影子运行时落盘的事件
    <evidence_root>/<run_id>/sink-failures.jsonl         sink 失败标记（A2；缺省 = 零失败）
    <evidence_root>/<run_id>/run-summary.json            A2 产出的运行后汇总（G-04，8 键）
    <evidence_root>/<run_id>/driver/bench-selected.jsonl 投影出的一 case 一条 bench
    <evidence_root>/<run_id>/driver/out/                 runner 的 results_v1.jsonl / report_v1.md

本工具**不写任何 tracked 文件**：投影 bench 与 ``--out`` 全在 gitignore 覆盖的
staging 之下。它会清空**同一个 run_id** 上一次尝试留下的 ``events/`` / ``driver/`` /
``run-summary.json`` / ``sink-failures.jsonl`` —— 否则残留的旧事件会让一次失败的重跑
看起来像"闭合"，而"无法验证不等于通过"是本契约的首要原则。

case 选择（A2 修 B3）
--------------------
manifest 预登记的 ``case_ids`` 必须**逐条**出现在 ``--case-source`` 中，否则 exit 2
并打 ``SPEC_INCOMPLETE``（绝不静默换一道题）。缺省 case source 是
``benchmarks/arknights_bench/questions_draft.jsonl``：runner 的缺省
``benchmarks/arknights_bench/questions.jsonl`` 在本仓**不存在**，而 draft 是唯一逐条
含 id 字段、且**完整包含**预登记 ``character_complex_002`` 的仓库内 bench（它是第 2 条，
所以不能靠 ``--limit 1`` 选它）。runner 没有 ``--case-id``，投影 bench 是本仓唯一的
非侵入选择机制。

run-summary 的 8 个键（``validate_local.RUN_SUMMARY_KEYS``，名字冻结）全部由**本次 run 的
durable artifact 现场推导**，不是硬编码::

    sink_failure_count      <run_id>/sink-failures.jsonl 的行数（缺文件 = 0）
    rejected_records       该文件里的 event_id 列表（非 canonical 的记 null）
    actual_calls           带 usage 观测的已发布事件条数
    actual_tokens          usage 的 input_tokens + output_tokens presence-aware 求和
                           （provider 报告的 total_tokens 冗余，不重复计入）
    duration_seconds       业务子进程的墙钟时长（round 3 位）
    producer_coverage      已观测的 {producer_id, mapping_stage} 集合（与 gate 算出的
                           元组集合一一对应；同一条记录只算一次）
    known_cost_components  foundation_output.cost 中 amount 非 null 的组成项数
    unknown_cost_components foundation_output.cost 中 amount 为 null 的组成项数

退出码（G-18 provisional，与 validate_local 同约定）::

    0  gate 通过（业务路径跑完 + run-summary 闭合 + --gate smoke 8 步全过）
    1  gate / 验证失败；stderr 含 SPEC_STATUS_CONFLICT
    2  用法或配置错误（manifest 缺键、mode/run_id/commit 不符、case_id 不在 source、
       超时以外的前置问题）；stderr 含 SPEC_INCOMPLETE

绝不打印 traceback。

provisional 决策与已知缺口
--------------------------
- **G-13**：``--gate smoke`` 冻结为 validate-only，本工具补上缺失的"业务运行"半边；
  它不修改、不放宽 gate 的任何检查（最后一步直接复用 ``validate_local.gate_smoke``）。
- **G-04**：``sink_failure_count`` / 被拒绝记录原先只在进程内存里（业务跑在子进程，
  父进程读不到）。A2 在项目 sink 上加了**最小**的 durable 标记
  （``evidence_sink.SINK_FAILURES_FILENAME``），本工具据此重算，而不是让 gate 猜。
- **G-01**：``repository_commit`` 为 null 时由 ``AGENT_CONTRACT_COMMIT`` 解析；不自动
  推断 HEAD（与 gate 同一 ``_resolve_manifest_commit`` 实现）。
- **用户授权偏离（B，依 N-04）**：``--gate smoke`` 的顶层 ``coverage_policy`` 是
  ``ALL_STAGES``，但 ``wiki.eval.cost_log/scoring`` 已按逐对 ``evidence_requirement =
  NOT_OBSERVED_ALLOWED`` 登记（母 Spec §7.3:896「错误 stage 可 ``NOT_OBSERVED``」的逐对
  形态）。该 stage 只由 ``scripts/score_runner.py`` 触发，而
  ``arknights_wiki/eval/scoring.py`` 顶层 ``import deepeval``，宿主环境**未声明也未安装**
  该包（项目只在 ``deepeval-local`` 容器里跑打分），故本机**无法**观测它。用户已授权该
  偏离，记录在 ``docs/plans/2026-09-16-foundation-contract-spec11-stage0-calibration.md``
  §10 (B1)；恢复条件：在 ``pyproject.toml`` 声明并安装 ``deepeval``。
  **"未观测 ≠ 通过"**：gate 第 7 步会把 ``wiki.eval.cost_log/scoring`` **逐对具名**报为
  未观测（豁免登记，不计入覆盖），本工具不做任何伪造、降级或"当作已覆盖"的表述。
  本工具驱动的 runner 路径覆盖其余 5 对；``scoring`` 之外的 ALL_STAGES 对一旦缺失仍判失败。
- ``side_effect_policy: read_only`` 与业务现实存在偏差：runner / judge 会把 cost 条目
  append 到**已 tracked** 的 ``output/eval/cost_log.jsonl``。这是业务路径的既有行为
  （本工具不改业务代码），因此 L3 之后需要人工 revert 该文件的 diff。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

# --------------------------------------------------------------------------- #
# sys.path 自举
# --------------------------------------------------------------------------- #
# 以 `python scripts/contracts/run_l3_smoke.py` 直跑时 sys.path[0] 是脚本目录，
# 仓库根不在其中；因此既插入仓库根（agent_core / arknights_wiki），也插入同目录
# （validate_local —— scripts/contracts 不是包，只能按同目录模块导入，
# 与 publish_evidence.py → replay_history 的既有做法一致）。

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HERE = Path(__file__).resolve().parent
for _entry in (str(_REPO_ROOT), str(_HERE)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import validate_local as vl  # noqa: E402  (同目录冻结 gate：复用其校验与错误语义)

from agent_core.contracts.models.base import canonical_json_dumps  # noqa: E402
from agent_core.contracts.models.evidence import is_safe_run_id  # noqa: E402

REPO_ROOT: Final[Path] = _REPO_ROOT

# --------------------------------------------------------------------------- #
# 退出码 / 标记 / 常量
# --------------------------------------------------------------------------- #

EXIT_OK: Final[int] = 0
EXIT_GATE_FAILED: Final[int] = 1
EXIT_USAGE: Final[int] = 2

#: 退出码 1 的可 grep 标记（本工具的 stderr 契约）。
MARKER_STATUS_CONFLICT: Final[str] = "SPEC_STATUS_CONFLICT"

#: 退出码 2 的可 grep 标记（与 validate_local 的用法错误标记同名）。
MARKER_SPEC_INCOMPLETE: Final[str] = "SPEC_INCOMPLETE"

#: 与 ``gate_smoke`` 逐字相同的必需键集合（键名冻结，不得改名）。
#: 与 gate 的一致性由 ``tests/contracts/test_run_l3_smoke.py`` 从
#: ``gate_smoke.__code__.co_consts`` 取出字面量表逐项比对。
MANIFEST_REQUIRED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "manifest_version",
        "run_id",
        "contract_mode",
        "contract_version",
        "payload_hash",
        "repository_commit",
        "evidence_root",
        "coverage_policy",
        "required_producer_stages",
        "expected_calls",
        "max_calls",
        "estimated_cost_cap",
        "network_requirement",
        "side_effect_policy",
        "timeout_seconds",
        "duration_cap_seconds",
        "model",
        "provider",
        "case_ids",
    }
)

#: 缺省 case source：本仓唯一逐条含 id、且完整包含预登记 case_ids 的 bench 文件。
#: （runner 的缺省 ``questions.jsonl`` 在本仓不存在；draft 的第 2 条才是
#: ``character_complex_002``，故不能用 ``--limit`` 代替逐 id 选择。）
DEFAULT_CASE_SOURCE: Final[Path] = (
    Path("benchmarks") / "arknights_bench" / "questions_draft.jsonl"
)

#: driver 自己的 staging 子目录名（与 events/ 同级）。
DRIVER_DIRNAME: Final[str] = "driver"
BUSINESS_OUT_DIRNAME: Final[str] = "out"
PROJECTED_BENCH_FILENAME: Final[str] = "bench-selected.jsonl"
RUN_SUMMARY_FILENAME: Final[str] = "run-summary.json"
EVENTS_DIRNAME: Final[str] = "events"

#: 业务运行输出的回显行数上限（只回显、不落盘，避免把绝对路径/业务正文写进 staging）。
BUSINESS_OUTPUT_TAIL_LINES: Final[int] = 40


class _MarkerParser(argparse.ArgumentParser):
    """用法错误也必须带可 grep 标记（G-18），且不打印 traceback。"""

    def error(self, message: str) -> None:  # noqa: D401 - argparse 契约
        self.print_usage(sys.stderr)
        print(f"{MARKER_SPEC_INCOMPLETE} / USAGE: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


@dataclass
class L3Outcome:
    """一次受控 L3 驱动的结果（成功路径）。"""

    run_id: str
    case_ids: list[str]
    case_source: str
    projected_bench: str
    out_dir: str
    business_command: list[str]
    duration_seconds: float
    run_summary: dict[str, Any]
    steps: list[vl.Step] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #


def _force_utf8_streams() -> None:
    """把 stdout/stderr 强制为 UTF-8（与 freeze gate 同因：Windows cp1252 会炸中文）。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - 非文本流或已关闭的流
            pass


def _sink_api() -> tuple[str, Callable[[Path], bool], Callable[[Path], Any]]:
    """惰性返回项目 sink 的 ``(SINK_FAILURES_FILENAME, has_residual_temp_files,
    iter_published_events)``。

    惰性导入让本模块在 ``agent_core`` 不可用时能给出干净的用法错误，而不是 import 期
    traceback。读取端一律复用 sink 的既有入口（只认 ``.json``），不另写一套目录遍历。
    """
    from arknights_wiki.adapters.foundation.evidence_sink import (  # noqa: PLC0415
        SINK_FAILURES_FILENAME,
        has_residual_temp_files,
        iter_published_events,
    )

    return SINK_FAILURES_FILENAME, has_residual_temp_files, iter_published_events


def _default_command_factory(projected_bench: Path, out_dir: Path) -> list[str]:
    """本仓的冻结业务命令：真实 runner，direct 模式，单 worker。"""
    repo_root = Path(vl.REPO_ROOT).resolve()
    return [
        sys.executable,
        "-m",
        "arknights_wiki.eval.runner",
        "--bench",
        _repo_relative(projected_bench, repo_root),
        "--out",
        _repo_relative(out_dir, repo_root),
        "--mode",
        "direct",
        "--workers",
        "1",
    ]


def _repo_relative(path: Path, repo_root: Path) -> str:
    """把 staging 路径转成仓库相对 posix 路径。

    刻意用相对路径：runner 会把 ``--out`` 原样打印到 stdout，绝对 Windows 路径命中
    发布安全扫描的"绝对路径"模式（§11.4），会污染后续 ``--gate pr`` 的 staging 扫描。
    """
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise vl.UsageError(
            f"staging 路径必须位于仓库内（否则无法给出相对路径）：{path}"
        ) from exc


# --------------------------------------------------------------------------- #
# 前置校验
# --------------------------------------------------------------------------- #


def resolve_evidence_root(repo_root: Path, manifest: Mapping[str, Any]) -> Path:
    """解析 ``manifest.evidence_root``：必须是仓库内、无上跳的相对目录。"""
    raw = manifest["evidence_root"]
    if not isinstance(raw, str) or not raw:
        raise vl.UsageError(f"manifest.evidence_root 必须是非空字符串：{raw!r}")
    candidate = Path(raw)
    if candidate.is_absolute():
        raise vl.UsageError(
            f"manifest.evidence_root 必须是仓库相对路径（EVD-PUB 位置约定）：{raw!r}"
        )
    if ".." in candidate.parts:
        raise vl.UsageError(f"manifest.evidence_root 不得包含上跳：{raw!r}")
    return (repo_root / candidate).resolve()


def preflight(manifest: Mapping[str, Any]) -> tuple[str, str]:
    """校验 manifest 必需键 + 三个环境前置；返回 ``(run_id, repository_commit)``。

    与 ``gate_smoke`` 逐条对齐（FND-MODE-001 / EVD-RUN-001 / G-01），但错误类别是
    "配置错误"（exit 2）：这些条件不满足时 run 根本不该开始。
    """
    missing = sorted(MANIFEST_REQUIRED_KEYS - set(manifest))
    if missing:
        raise vl.UsageError(
            f"run manifest 缺少字段 {missing}；"
            "SPEC_INCOMPLETE（G-01）：smoke-v0.1.json 的键名是 Spec 10 provisional 收敛"
        )

    run_id = manifest["run_id"]
    if not is_safe_run_id(run_id):
        raise vl.UsageError(f"manifest.run_id 不是 safe run id（EVD-RUN-001）：{run_id!r}")
    if manifest["contract_mode"] != "observe":
        raise vl.UsageError(
            f"FND-MODE-001：manifest.contract_mode 必须是 observe，"
            f"实际 {manifest['contract_mode']!r}"
        )

    env_mode = os.environ.get("AGENT_CONTRACT_MODE")
    env_run_id = os.environ.get("AGENT_CONTRACT_RUN_ID")
    if env_mode != "observe":
        raise vl.UsageError(
            f"FND-MODE-001：L3 要求 AGENT_CONTRACT_MODE=observe，实际 {env_mode!r}"
        )
    if env_run_id != run_id:
        raise vl.UsageError(
            f"EVD-RUN-001：显式 run_id 与 manifest 不一致"
            f"（env={env_run_id!r}, manifest={run_id!r}）"
        )

    try:
        commit = vl._resolve_manifest_commit(dict(manifest))
    except vl.GateFailure as exc:
        # gate 把"commit 不可用"归为 gate 失败；驱动器里它是**运行前**的配置错误，
        # 消息逐字保留，只改类别（不自动推断 HEAD 的约定不变）。
        raise vl.UsageError(str(exc)) from exc
    return str(run_id), str(commit)


# --------------------------------------------------------------------------- #
# case 选择（B3）
# --------------------------------------------------------------------------- #


def load_case_index(case_source: Path) -> dict[str, dict[str, Any]]:
    """把一个 bench JSONL 读成 ``id → 记录``；形状非法即用法错误。"""
    if not case_source.is_file():
        raise vl.UsageError(f"case source 不存在：{case_source}")
    index: dict[str, dict[str, Any]] = {}
    for line_no, line in enumerate(case_source.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise vl.UsageError(f"case source 第 {line_no} 行不是合法 JSON：{exc}") from exc
        if not isinstance(record, dict):
            raise vl.UsageError(f"case source 第 {line_no} 行不是 JSON object")
        case_id = record.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise vl.UsageError(f"case source 第 {line_no} 行缺少非空字符串 id")
        if case_id in index:
            raise vl.UsageError(f"case source 含重复 id：{case_id!r}（选择结果会不确定）")
        index[case_id] = record
    if not index:
        raise vl.UsageError(f"case source 不含任何记录：{case_source}")
    return index


def select_cases(
    manifest: Mapping[str, Any], repo_root: Path, case_source: Path | None
) -> tuple[list[dict[str, Any]], Path]:
    """按 manifest 预登记的 ``case_ids`` 从 case source 逐条取出（顺序保持）。

    **硬要求**：任一预登记 id 不在 source 里 → ``SPEC_INCOMPLETE``（exit 2）。
    绝不静默换题、绝不用 ``--limit`` 近似。
    """
    declared = manifest["case_ids"]
    if not isinstance(declared, list) or not declared:
        raise vl.UsageError("manifest.case_ids 必须是至少含一项的列表")
    if not all(isinstance(item, str) and item for item in declared):
        raise vl.UsageError("manifest.case_ids 的每一项都必须是非空字符串")
    if len(set(declared)) != len(declared):
        raise vl.UsageError(f"manifest.case_ids 含重复项：{declared!r}")

    source = Path(case_source) if case_source is not None else repo_root / DEFAULT_CASE_SOURCE
    index = load_case_index(source)
    missing = [item for item in declared if item not in index]
    if missing:
        raise vl.UsageError(
            f"SPEC_INCOMPLETE（B3）：预登记 case_ids {missing} 不在 case source "
            f"{source}（该文件有 {len(index)} 条记录）；拒绝改用其他题目"
        )
    return [index[item] for item in declared], source


def project_bench(run_root: Path, records: Sequence[Mapping[str, Any]]) -> Path:
    """把选中的 case 投影成临时 bench（一 case 一条），只写 staging。"""
    driver_dir = run_root / DRIVER_DIRNAME
    driver_dir.mkdir(parents=True, exist_ok=True)
    target = driver_dir / PROJECTED_BENCH_FILENAME
    text = "".join(canonical_json_dumps(dict(record)) + "\n" for record in records)
    target.write_text(text, encoding="utf-8")
    return target


# --------------------------------------------------------------------------- #
# 运行 / 汇总
# --------------------------------------------------------------------------- #


def clear_previous_run(run_root: Path) -> list[str]:
    """清掉同一个 run_id 的上一次尝试（fresh smoke 的"fresh"必须是真的）。"""
    removed: list[str] = []
    for relative in (
        EVENTS_DIRNAME,
        DRIVER_DIRNAME,
        RUN_SUMMARY_FILENAME,
        _sink_api()[0],
    ):
        target = run_root / relative
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            removed.append(f"{relative}/")
        elif target.exists():
            target.unlink()
            removed.append(relative)
    return removed


def run_business(
    command: Sequence[str],
    *,
    repo_root: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
) -> tuple[float, int, str, str]:
    """跑业务子进程并测量墙钟时长；超时按 gate 失败处理（exit 1）。"""
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(repo_root),
            env=dict(env),
            capture_output=True,
            text=True,
            # Windows 下 text=True 默认用本地编码（gbk/cp936）解码，业务路径的 UTF-8 中文
            # 输出会让读取线程抛 UnicodeDecodeError 并丢掉全部业务输出（已实测）。
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = round(time.monotonic() - started, 3)
        raise vl.GateFailure(
            f"业务路径超时：timeout_seconds={timeout_seconds} 用尽"
            f"（已运行 {elapsed}s）：{' '.join(command)}"
        ) from exc
    elapsed = round(time.monotonic() - started, 3)
    return elapsed, completed.returncode, completed.stdout or "", completed.stderr or ""


def read_sink_failures(run_root: Path) -> tuple[int, list[str]]:
    """读 run 级 sink 失败标记；**缺文件 = 零失败**（G-04 / A2）。"""
    filename, _has_temp, _iter_events = _sink_api()
    path = run_root / filename
    if not path.is_file():
        return 0, []
    rejected: list[str] = []
    count = 0
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        count += 1
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            rejected.append(f"<unparsable:{line_no}>")
            continue
        event_id = entry.get("event_id") if isinstance(entry, dict) else None
        rejected.append(str(event_id) if event_id is not None else "<unknown>")
    return count, rejected


def load_published_events(run_root: Path) -> list[dict[str, Any]]:
    """读取本次 run 已发布的事件（只认 ``.json``，与 gate 同一入口）。"""
    _filename, _has_temp, iter_events = _sink_api()
    events_dir = run_root / EVENTS_DIRNAME
    return [json.loads(path.read_text(encoding="utf-8")) for path in iter_events(events_dir)]


def derive_run_summary(
    *,
    events: Sequence[Mapping[str, Any]],
    duration_seconds: float,
    sink_failure_count: int,
    rejected_records: Sequence[str],
) -> dict[str, Any]:
    """从 durable artifact 现场推导 8 键 run-summary（键名取自冻结 gate 常量）。

    presence 原则：缺字段记为"未观测"，不用 0 冒充；``total_tokens`` 不参与求和，
    因为 provider 同时报告 in/out 时它是同一批 token 的第二次计数。
    """
    observed: set[tuple[str, str]] = set()
    actual_calls = 0
    actual_tokens = 0
    known_cost_components = 0
    unknown_cost_components = 0

    for event in events:
        observed.add((str(event.get("producer_id")), str(event.get("mapping_stage"))))
        output = event.get("foundation_output")
        if not isinstance(output, Mapping):
            continue
        usage = output.get("usage")
        if isinstance(usage, Mapping):
            actual_calls += 1
            for field_name in ("input_tokens", "output_tokens"):
                value = usage.get(field_name)
                if isinstance(value, int) and not isinstance(value, bool):
                    actual_tokens += value
        cost = output.get("cost")
        if isinstance(cost, Mapping):
            if cost.get("amount") is None:
                unknown_cost_components += 1
            else:
                known_cost_components += 1

    summary = {
        "sink_failure_count": int(sink_failure_count),
        "rejected_records": [str(item) for item in rejected_records],
        "actual_calls": actual_calls,
        "actual_tokens": actual_tokens,
        "duration_seconds": duration_seconds,
        "producer_coverage": [
            {"producer_id": producer_id, "mapping_stage": stage}
            for producer_id, stage in sorted(observed)
        ],
        "known_cost_components": known_cost_components,
        "unknown_cost_components": unknown_cost_components,
    }
    missing = sorted(set(vl.RUN_SUMMARY_KEYS) - set(summary))
    extra = sorted(set(summary) - set(vl.RUN_SUMMARY_KEYS))
    if missing or extra:  # pragma: no cover - 结构性防御（键集冻结）
        raise vl.UsageError(
            f"内部错误：run-summary 键集与冻结常量不一致（缺 {missing} / 多 {extra}）"
        )
    return summary


def write_run_summary(path: Path, summary: Mapping[str, Any]) -> None:
    """原子写 run-summary.json（canonical JSON，与项目其它 artifact 同格式）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(canonical_json_dumps(dict(summary)) + "\n", encoding="utf-8")
    os.replace(temp, path)


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #


def run_l3(
    *,
    manifest_path: Path,
    case_source: Path | None = None,
    command_factory: Callable[[Path, Path], Sequence[str]] | None = None,
) -> L3Outcome:
    """执行一次受控 L3；成功返回 :class:`L3Outcome`，失败抛 ``UsageError``/``GateFailure``。

    ``command_factory`` 是**测试缝**（默认 = 冻结的 runner 命令）：测试可以注入一个
    合成 fixture 命令，从而在不联网、不调用真实模型的前提下驱动完整流程。
    """
    manifest_file = Path(manifest_path)
    manifest = vl._load_manifest(manifest_file)
    run_id, commit = preflight(manifest)

    repo_root = Path(vl.REPO_ROOT)
    evidence_root = resolve_evidence_root(repo_root, manifest)
    run_root = evidence_root / run_id
    messages: list[str] = []

    removed = clear_previous_run(run_root)
    if removed:
        messages.append(
            f"清空同一 run_id 的既有产物（fresh smoke 必须 fresh）：{', '.join(removed)}"
        )

    selected, source = select_cases(manifest, repo_root, case_source)
    projected = project_bench(run_root, selected)
    out_dir = run_root / DRIVER_DIRNAME / BUSINESS_OUT_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)

    factory = command_factory or _default_command_factory
    command = [str(item) for item in factory(projected, out_dir)]

    timeout_seconds = manifest["timeout_seconds"]
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool):
        raise vl.UsageError(f"manifest.timeout_seconds 必须是整数：{timeout_seconds!r}")
    if timeout_seconds <= 0:
        raise vl.UsageError(f"manifest.timeout_seconds 必须为正：{timeout_seconds!r}")

    env = os.environ.copy()
    env["AGENT_CONTRACT_MODE"] = "observe"
    env["AGENT_CONTRACT_RUN_ID"] = run_id
    env["AGENT_CONTRACT_COMMIT"] = commit
    # 覆盖 sink 根：保证业务子进程写证据的位置与 gate 读取的位置一致
    # （sink 只看 AGENT_CONTRACT_EVIDENCE_DIR，gate 只看 REPO_ROOT/manifest.evidence_root）。
    env["AGENT_CONTRACT_EVIDENCE_DIR"] = str(evidence_root)

    duration, returncode, stdout_text, stderr_text = run_business(
        command, repo_root=repo_root, env=env, timeout_seconds=timeout_seconds
    )

    stdout_lines = stdout_text.strip().splitlines()
    stderr_lines = stderr_text.strip().splitlines()
    if stdout_lines:
        print("--- business stdout (tail) ---")
        print("\n".join(stdout_lines[-BUSINESS_OUTPUT_TAIL_LINES:]))
    if stderr_lines:
        print("--- business stderr (tail) ---", file=sys.stderr)
        print("\n".join(stderr_lines[-BUSINESS_OUTPUT_TAIL_LINES:]), file=sys.stderr)

    if returncode != 0:
        raise vl.GateFailure(
            f"业务路径退出码 {returncode} != 0（command: {' '.join(command)}）；"
            "拒绝为一次未跑完的 run 写 run-summary"
        )

    _filename, has_temp_files, _iter_events = _sink_api()
    if has_temp_files(run_root / EVENTS_DIRNAME):
        raise vl.GateFailure("§11.1：事件目录存在残留 .tmp，本次 run 的证据不完整")

    sink_failure_count, rejected_records = read_sink_failures(run_root)
    events = load_published_events(run_root)
    if not events:
        raise vl.GateFailure(
            "本次 run 没有发布任何事件（observe 模式下必然产出证据；"
            "0 条 = wiring/身份绑定失效，不构成 Smoke 证据）"
        )

    summary = derive_run_summary(
        events=events,
        duration_seconds=duration,
        sink_failure_count=sink_failure_count,
        rejected_records=rejected_records,
    )
    write_run_summary(run_root / RUN_SUMMARY_FILENAME, summary)
    messages.append(
        f"run-summary 已写入 <run_id>/{RUN_SUMMARY_FILENAME}"
        f"（{len(events)} 事件 / {len(summary['producer_coverage'])} producer-stage）"
    )
    if summary["sink_failure_count"]:
        messages.append(
            f"警告：本次 run 记录了 {summary['sink_failure_count']} 次 sink 失败；"
            "gate 会因此失败（EVD-SINK-003）"
        )

    steps = vl.gate_smoke(manifest_file)

    return L3Outcome(
        run_id=run_id,
        case_ids=[str(item) for item in manifest["case_ids"]],
        case_source=str(source),
        projected_bench=str(projected),
        out_dir=str(out_dir),
        business_command=command,
        duration_seconds=duration,
        run_summary=summary,
        steps=steps,
        messages=messages,
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = _MarkerParser(
        prog="run_l3_smoke.py",
        description="L3 fresh smoke 的受控驱动器（Spec 13 / A2）",
    )
    parser.add_argument(
        "--run-manifest", type=Path, required=True, help="预登记的 smoke run manifest"
    )
    parser.add_argument(
        "--case-source",
        type=Path,
        default=None,
        help=(
            "逐条含 id 的 bench JSONL；缺省 "
            f"{DEFAULT_CASE_SOURCE.as_posix()}（必须完整包含 manifest.case_ids）"
        ),
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    return parser


def _render(outcome: L3Outcome) -> None:
    print(f"=== L3 fresh smoke / run_id={outcome.run_id} ===")
    print(f"case source : {outcome.case_source}")
    print(f"case ids    : {', '.join(outcome.case_ids)}")
    print(f"business    : {' '.join(outcome.business_command)}")
    print(f"duration    : {outcome.duration_seconds}s")
    print(f"events      : {len(outcome.run_summary['producer_coverage'])} producer-stage")
    for message in outcome.messages:
        print(f"note: {message}")
    for step in outcome.steps:
        print(step.render())
    print("L3 fresh smoke PASSED（业务路径跑完 + run-summary 闭合 + --gate smoke 8 步全过）")


def main(argv: Sequence[str] | None = None) -> int:
    _force_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        outcome = run_l3(
            manifest_path=args.run_manifest,
            case_source=args.case_source,
        )
    except vl.UsageError as exc:
        print(f"{MARKER_SPEC_INCOMPLETE} / USAGE: {exc}", file=sys.stderr)
        if args.json:
            print(
                json.dumps(
                    {"status": "FAIL", "marker": MARKER_SPEC_INCOMPLETE, "detail": str(exc)},
                    ensure_ascii=False,
                )
            )
        return EXIT_USAGE
    except vl.GateFailure as exc:
        print(f"{MARKER_STATUS_CONFLICT} / GATE FAILED: {exc}", file=sys.stderr)
        if args.json:
            print(
                json.dumps(
                    {"status": "FAIL", "marker": MARKER_STATUS_CONFLICT, "detail": str(exc)},
                    ensure_ascii=False,
                )
            )
        return EXIT_GATE_FAILED
    except KeyboardInterrupt:  # pragma: no cover - 人工中断
        print(f"{MARKER_STATUS_CONFLICT} / 中断", file=sys.stderr)
        return EXIT_GATE_FAILED
    except Exception as exc:  # noqa: BLE001 - 绝不向用户抛 traceback（G-18）
        print(
            f"{MARKER_SPEC_INCOMPLETE} / unexpected {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    if args.json:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "run_id": outcome.run_id,
                    "case_ids": outcome.case_ids,
                    "case_source": outcome.case_source,
                    "business_command": outcome.business_command,
                    "projected_bench": outcome.projected_bench,
                    "out_dir": outcome.out_dir,
                    "duration_seconds": outcome.duration_seconds,
                    "run_summary": outcome.run_summary,
                    "gate": {
                        "gate": "smoke",
                        "steps": [
                            {"index": s.index, "name": s.name, "detail": s.detail}
                            for s in outcome.steps
                        ],
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _render(outcome)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
