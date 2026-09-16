"""Spec 10 交付物测试 —— Cycle 协调器与 Wiki Finalizer（Spec 15 / Master §16.4–16.6）。

覆盖范围
--------
1. **纯函数层**（不触 git）：plan 闭合校验、publication / finalization allowlist、
   Ledger 纯追加判定、`current.json` 四字段、账本事件序列、自身 SHA 禁用、状态归约。
   —— 这些函数即使 git 交互层未实跑也可独立验证。
2. **真实本地 git fixture**（`tmp_path` + `git init` 两次提交造 A→B→C）：
   ancestry、diff allowlist、Payload Hash 重算、DIVERGED、Evidence Manifest 绑定、
   L1/L2/L3 结果、Ledger 纯追加 + A 中 reducer 归约、provisional 退出码。
3. **端到端 CLI**：用 `sys.executable` **直接**运行
   `scripts/contracts/coordinate_cycle.py` / `finalize_cycle.py`（而不是 import 调用），
   因为直接运行时 `sys.path[0]` 是脚本目录 —— 只有真跑才能证明仓根自举有效。
4. **安全边界**：真实 `docs/specs/foundation-contract/execution-status-events.jsonl`
   与真实 `docs/contracts/**` 在整个测试模块内必须逐字节不变（autouse guard）。

fixture 说明
------------
- 账本是**合法账本**：按真实 `00-execution-index.md` 的 DAG 走
  `01..10 COMPLETE + 11 IN_PROGRESS`（Candidate A 边界），B 追加 `11 VALIDATED..COMPLETE`
  与 `12/13/14 COMPLETE`（Evidence B 边界）。因此可直接交给真实
  `scripts/contracts/status_ledger.py` 归约（见 ``test_finalizer_events_are_reducer_legal``）。
- 事件里的 `candidate_commit` 用固定 40-hex 占位（`candidate_commit` 只校验形状；
  真实 Cycle 中它等于 A）。fixture 只写 `tmp_path`，不写仓库。
- Payload 来自本仓 `agent_core/**` 的**只读拷贝**，因此 Payload Hash 是真实重算结果，
  不是硬编码常量。
"""
from __future__ import annotations

import importlib.util
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "contracts"
COORDINATOR = SCRIPTS_DIR / "coordinate_cycle.py"
FINALIZER = SCRIPTS_DIR / "finalize_cycle.py"
REAL_REDUCER = SCRIPTS_DIR / "status_ledger.py"

SPEC_DIR_REL = Path("docs") / "specs" / "foundation-contract"
LEDGER_REL = SPEC_DIR_REL / "execution-status-events.jsonl"
REAL_LEDGER = REPO_ROOT / LEDGER_REL
REAL_CONTRACTS = REPO_ROOT / "docs" / "contracts"

VERSION = "0.1.0"
RELEASE_REL = f"docs/contracts/releases/{VERSION}"
CYCLE_ID = "foundation-0.1.0-cycle-1"

#: fixture 账本里 post-freeze 事件的 candidate_commit 占位（40-hex 形状）。
FIXTURE_CANDIDATE = "c" * 40

if str(REPO_ROOT) not in sys.path:  # pytest 下 CWD 通常在 sys.path 里，这里显式兜底
    sys.path.insert(0, str(REPO_ROOT))

from agent_core.contracts.tooling.canonical_json import (  # noqa: E402
    canonical_file_bundle_digest,
    canonical_json_dumps,
)


def _load_script(name: str, path: Path):
    """按文件路径加载被测脚本（``scripts/contracts`` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


coord = _load_script("coordinate_cycle_under_test", COORDINATOR)
final = _load_script("finalize_cycle_under_test", FINALIZER)


# --------------------------------------------------------------------------- #
# autouse 安全护栏：真实账本与真实发布树必须逐字节不变
# --------------------------------------------------------------------------- #


def _real_contracts_artifacts() -> set[str]:
    if not REAL_CONTRACTS.is_dir():
        return set()
    return {
        path.relative_to(REAL_CONTRACTS).as_posix()
        for path in REAL_CONTRACTS.rglob("*")
        if path.is_file() and path.name in {"current.json", "cycle-report.json", "cycle-report.md"}
    }


@pytest.fixture(scope="module", autouse=True)
def _guard_real_artifacts():
    ledger_before = REAL_LEDGER.read_bytes()
    contracts_before = _real_contracts_artifacts()
    yield
    assert REAL_LEDGER.read_bytes() == ledger_before, "测试修改了真实账本（绝对禁止）"
    assert _real_contracts_artifacts() == contracts_before, (
        "测试在真实 docs/contracts 下产生了 C 产物（绝对禁止）"
    )


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #


def run_cli(script: Path, *args: object, env: dict[str, str] | None = None):
    """直接运行脚本（非 import），验证仓根自举与 provisional 退出码。"""
    merged = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(script), *[str(arg) for arg in args]],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=merged,
        timeout=900,
    )


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert proc.returncode == 0, f"git {' '.join(args)} 失败：{proc.stderr}"
    return proc.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "user.name=Cycle Fixture",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        message,
    )
    return _git(repo, "rev-parse", "HEAD")


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    # 关键：禁止 autocrlf 改写 blob 字节，否则账本与 payload 的字节级校验全部失真。
    _git(path, "config", "core.autocrlf", "false")
    _git(path, "config", "user.email", "fixture@example.invalid")
    _git(path, "config", "user.name", "Cycle Fixture")
    _git(path, "config", "commit.gpgsign", "false")


def _copy_payload(dest_repo: Path) -> None:
    shutil.copytree(
        REPO_ROOT / "agent_core",
        dest_repo / "agent_core",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


# --------------------------------------------------------------------------- #
# fixture 账本：按真实 DAG 生成合法事件链
# --------------------------------------------------------------------------- #

_TIMESTAMPS = itertools.count(1)


def _event(
    spec_id: str,
    from_status: str,
    to_status: str,
    reason_code: str,
    *,
    candidate: str | None,
    evidence_refs: tuple[str, ...] = (),
) -> dict[str, object]:
    index = next(_TIMESTAMPS)
    return {
        "event_id": str(uuid.uuid4()),
        "spec_id": spec_id,
        "from_status": from_status,
        "to_status": to_status,
        "candidate_commit": candidate,
        "evidence_refs": list(evidence_refs),
        "timestamp": f"2026-09-16T10:{index // 60:02d}:{index % 60:02d}Z",
        "reason_code": reason_code,
        "reason": f"fixture {spec_id} {from_status}->{to_status}",
        "references": [],
    }


def _chain(
    spec_id: str, *, genesis: str = "NOT_STARTED", candidate: str | None, upto: str = "COMPLETE"
) -> list[dict[str, object]]:
    """从 genesis 走主路径到 ``upto``（reason_code 全部落在 reducer 的合法集合内）。"""
    steps = [
        ("READY", "PREREQUISITES_SATISFIED"),
        ("IN_PROGRESS", "EXECUTION_STARTED"),
        ("VALIDATED", "VALIDATION_PASSED"),
        ("COMPLETE", "ACCEPTANCE_COMPLETE"),
    ]
    events: list[dict[str, object]] = []
    status = genesis
    for to_status, reason in steps:
        if to_status == genesis:
            continue
        # rule 5：进入 VALIDATED 必须有非空 validation result / Evidence reference。
        refs = ("contract-tests:fixture-validation",) if to_status == "VALIDATED" else ()
        events.append(_event(spec_id, status, to_status, reason, candidate=candidate, evidence_refs=refs))
        status = to_status
        if status == upto:
            break
    assert status == upto, f"无法从 {genesis} 走到 {upto}"
    return events


def _a_ledger_bytes() -> bytes:
    """Candidate A 边界：01–10 COMPLETE + 11 走到 IN_PROGRESS（§16.2）。"""
    events: list[dict[str, object]] = []
    for index in range(1, 11):
        spec_id = f"{index:02d}"
        genesis = "READY" if spec_id == "01" else "NOT_STARTED"
        events.extend(_chain(spec_id, genesis=genesis, candidate=None))
    events.extend(_chain("11", candidate=None, upto="IN_PROGRESS"))
    return _lines(events)


def _b_appended_ledger_bytes() -> bytes:
    """Evidence B 边界追加：11 收尾 + 12/13/14 COMPLETE。"""
    events: list[dict[str, object]] = [
        _event(
            "11",
            "IN_PROGRESS",
            "VALIDATED",
            "FREEZE_BOUNDARY_REACHED",
            candidate=FIXTURE_CANDIDATE,
            evidence_refs=("contract-tests:freeze-boundary",),
        ),
        _event("11", "VALIDATED", "COMPLETE", "CANDIDATE_FROZEN", candidate=FIXTURE_CANDIDATE),
    ]
    for spec_id in ("12", "13", "14"):
        events.extend(_chain(spec_id, candidate=FIXTURE_CANDIDATE))
    return _lines(events)


def _lines(events: list[dict[str, object]]) -> bytes:
    return b"".join((canonical_json_dumps(event) + "\n").encode("utf-8") for event in events)


STUB_REDUCER = '''#!/usr/bin/env python
"""fixture reducer stub：只实现 Spec 10:109 冻结的 CLI 形状 `validate --ledger <path>`。"""
import argparse
import json
import sys

FIELDS = (
    "event_id", "spec_id", "from_status", "to_status", "candidate_commit",
    "evidence_refs", "timestamp", "reason_code", "reason", "references",
)


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--ledger", required=True)
    validate.add_argument("--spec-dir", default=None)
    validate.add_argument("--index", default=None)
    args = parser.parse_args(argv)

    try:
        text = open(args.ledger, encoding="utf-8").read()
    except OSError as exc:
        print("ledger unreadable: %s" % exc, file=sys.stderr)
        return 2

    seen = set()
    count = 0
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            print("SPEC_STATUS_CONFLICT: line %d not JSON (%s)" % (line_no, exc.msg), file=sys.stderr)
            return 1
        missing = [name for name in FIELDS if name not in record]
        if missing:
            print("SPEC_STATUS_CONFLICT: line %d missing %s" % (line_no, missing), file=sys.stderr)
            return 1
        if record["event_id"] in seen:
            print("SPEC_STATUS_CONFLICT: duplicate event_id at line %d" % line_no, file=sys.stderr)
            return 1
        seen.add(record["event_id"])
        count += 1
    print("fixture reducer OK: %d events" % count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

REJECTING_REDUCER = '''#!/usr/bin/env python
"""fixture reducer stub：永远返回 SPEC_STATUS_CONFLICT（用于校验失败分支）。"""
import sys

print("SPEC_STATUS_CONFLICT: fixture reducer rejects every ledger", file=sys.stderr)
raise SystemExit(1)
'''


# --------------------------------------------------------------------------- #
# Evidence 产物
# --------------------------------------------------------------------------- #


def _evidence_manifest(repository: str, payload_hash: str, candidate: str) -> dict[str, object]:
    return {
        "contract_version": VERSION,
        "contract_payload_hash": payload_hash,
        "verified_repository_commit": candidate,
        "repository": repository,
        "environment": {"python": "3.12.10", "pydantic": "2.13.4", "os": "windows"},
        "evidence": {
            "contract_tests": "PASS",
            "historical_replay": "PASS",
            "fresh_smoke": "PASS",
            "full_regression": (
                "PASS_WITH_KNOWN_BASELINE_FAILURES" if repository == "wiki" else "PASS"
            ),
        },
        "producer_coverage": [
            {"producer_id": "chat_completion", "mapping_stage": "llm_call", "status": "PASS"},
            {"producer_id": "cost_log", "mapping_stage": "cost", "status": "PASS"},
        ],
        "benchmark_reference_status": (
            "BENCHMARK_BASELINE_NOT_REPRODUCIBLE"
            if repository == "wiki"
            else "BENCHMARK_REPRODUCTION_RESTRICTED"
        ),
    }


def _run_manifest() -> dict[str, object]:
    return {
        "manifest_version": 1,
        "run_id": "cycle-fixture-run",
        "contract_version": VERSION,
        "reproducibility": "PASS",
        "publication_scan": "PASS",
    }


def _write_evidence(
    repo: Path,
    repository: str,
    payload_hash: str,
    candidate: str,
    canonical_payload_commit: str,
) -> None:
    validation = repo / RELEASE_REL / "validation" / repository
    validation.mkdir(parents=True, exist_ok=True)
    (repo / RELEASE_REL).mkdir(parents=True, exist_ok=True)
    manifest = _evidence_manifest(repository, payload_hash, candidate)
    (validation / "evidence-manifest.json").write_text(
        canonical_json_dumps(manifest) + "\n", encoding="utf-8", newline="\n"
    )
    (validation / "run-manifest.json").write_text(
        canonical_json_dumps(_run_manifest()) + "\n", encoding="utf-8", newline="\n"
    )
    (validation / "validation-report.md").write_text(
        f"# Validation report ({repository})\n\nL1/L2/L3 all PASS.\n", encoding="utf-8", newline="\n"
    )
    (validation / "rule-traceability.json").write_text(
        canonical_json_dumps({"contract_version": VERSION, "rules": [
            {"rule_id": "FND-COST-001", "shared_tests": ["test_cost"], "evidence_ids": ["wiki-1"]}
        ]})
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (validation / "sanitized-replay-corpus.jsonl").write_text(
        canonical_json_dumps({"record_id": "r1", "source_class": "cost_log"}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (repo / RELEASE_REL / "changelog.md").write_text(
        "# Changelog\n\n- cycle fixture\n", encoding="utf-8", newline="\n"
    )
    (repo / RELEASE_REL / "contract-manifest.json").write_text(
        canonical_json_dumps(
            {
                "contract_version": VERSION,
                "contract_payload_hash": payload_hash,
                "payload_descriptor_hash": "sha256:" + "1" * 64,
                "schema_set_hash": "sha256:" + "2" * 64,
                "canonical_payload_repository": "wiki",
                "canonical_payload_commit": canonical_payload_commit,
            }
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


# --------------------------------------------------------------------------- #
# Cycle fixture
# --------------------------------------------------------------------------- #


@dataclass
class CycleFixture:
    root: Path
    wiki: Path
    coding: Path
    wiki_a: str
    wiki_b: str
    coding_a: str
    coding_b: str
    payload_hash: str
    plan_path: Path
    output_dir: Path
    ledger_path: Path
    release_dir: Path
    notes: dict[str, object] = field(default_factory=dict)

    def run_coordinator(self, *extra: object, env: dict[str, str] | None = None):
        return run_cli(
            COORDINATOR,
            "--plan",
            self.plan_path,
            "--output",
            self.output_dir,
            "--wiki-repo",
            self.wiki,
            "--coding-repo",
            self.coding,
            *extra,
            env=env,
        )

    def coordination(self) -> dict[str, object]:
        return json.loads((self.output_dir / "coordination.json").read_text(encoding="utf-8"))


def build_cycle(
    root: Path,
    *,
    diverged: bool = False,
    manifest_payload_hash: str | None = None,
    ledger_mode: str = "append",
    reducer: str = "stub",
    extra_out_of_allowlist: str | None = None,
    missing_coding_commit: bool = False,
) -> CycleFixture:
    """构造 wiki + coding 两个本地 git 仓（A→B），并写出闭合 plan。"""
    wiki = root / "wiki"
    coding = root / "coding"
    _init_repo(wiki)
    _init_repo(coding)

    # ---- Candidate A ----
    _copy_payload(wiki)
    if reducer == "stub":
        path = wiki / "scripts" / "contracts" / "status_ledger.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(STUB_REDUCER, encoding="utf-8", newline="\n")
    elif reducer == "rejecting":
        path = wiki / "scripts" / "contracts" / "status_ledger.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(REJECTING_REDUCER, encoding="utf-8", newline="\n")
    elif reducer == "real":
        path = wiki / "scripts" / "contracts" / "status_ledger.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_REDUCER, path)
        shutil.copytree(REPO_ROOT / SPEC_DIR_REL, wiki / SPEC_DIR_REL)
    elif reducer is None:
        pass
    else:  # pragma: no cover - 防御
        raise AssertionError(f"unknown reducer mode {reducer!r}")

    ledger_path = wiki / LEDGER_REL
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_bytes(_a_ledger_bytes())
    wiki_a = _commit(wiki, "A: candidate fixture")

    _copy_payload(coding)
    if diverged:
        target = coding / "agent_core" / "contracts" / "version.py"
        target.write_text(target.read_text(encoding="utf-8") + "# diverged fixture\n", encoding="utf-8", newline="\n")
    coding_a = _commit(coding, "A: candidate fixture")

    payload_hash = canonical_file_bundle_digest(wiki)[0]
    manifest_hash = manifest_payload_hash or payload_hash

    # ---- Evidence B ----
    if ledger_mode == "append":
        ledger_path.write_bytes(ledger_path.read_bytes() + _b_appended_ledger_bytes())
    elif ledger_mode == "rewrite":  # 非纯追加：改写 A 的首行字节
        text = ledger_path.read_text(encoding="utf-8")
        first, rest = text.split("\n", 1)
        ledger_path.write_text('{"event_id": "tampered"}\n' + rest, encoding="utf-8", newline="\n")
    elif ledger_mode == "empty":  # 不做任何追加
        pass
    else:  # pragma: no cover - 防御
        raise AssertionError(f"unknown ledger mode {ledger_mode!r}")

    _write_evidence(wiki, "wiki", manifest_hash, wiki_a, wiki_a)
    if extra_out_of_allowlist:
        extra = wiki / extra_out_of_allowlist
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text("out of allowlist\n", encoding="utf-8", newline="\n")
    wiki_b = _commit(wiki, "B: evidence fixture")

    # §12.5：contract-manifest.json 同步到 Coding 后内容不变，provenance 始终指向 A_wiki。
    _write_evidence(coding, "coding", payload_hash, coding_a, wiki_a)
    coding_b = _commit(coding, "B: evidence fixture")

    plan = {
        "cycle_id": CYCLE_ID,
        "target_contract_version": VERSION,
        "expected_contract_payload_hash": payload_hash,
        "wiki_candidate_commit": wiki_a,
        "coding_candidate_commit": coding_a,
        "wiki_evidence_commit": wiki_b,
        "coding_evidence_commit": coding_b if not missing_coding_commit else wiki_b,
        "created_at": "2026-09-16T12:00:00Z",
    }
    plan_path = root / "cycle-plan.json"
    plan_path.write_text(canonical_json_dumps(plan) + "\n", encoding="utf-8", newline="\n")

    return CycleFixture(
        root=root,
        wiki=wiki,
        coding=coding,
        wiki_a=wiki_a,
        wiki_b=wiki_b,
        coding_a=coding_a,
        coding_b=coding_b,
        payload_hash=payload_hash,
        plan_path=plan_path,
        output_dir=root / "coordination",
        ledger_path=ledger_path,
        release_dir=wiki / RELEASE_REL,
        notes={"diverged": diverged, "reducer": reducer},
    )


# 模块级共享 fixture（构建成本：copytree + git 提交，故复用）
@pytest.fixture(scope="module")
def good_cycle(tmp_path_factory) -> CycleFixture:
    return build_cycle(tmp_path_factory.mktemp("cycle-pass"), reducer="stub")


@pytest.fixture(scope="module")
def good_cycle_with_real_reducer(tmp_path_factory) -> CycleFixture:
    if not REAL_REDUCER.is_file():
        pytest.skip("scripts/contracts/status_ledger.py 尚未实现（由其他执行者并行交付）")
    return build_cycle(tmp_path_factory.mktemp("cycle-real-reducer"), reducer="real")


@pytest.fixture(scope="module")
def diverged_cycle(tmp_path_factory) -> CycleFixture:
    return build_cycle(tmp_path_factory.mktemp("cycle-diverged"), diverged=True, reducer="stub")


@pytest.fixture(scope="module")
def failed_cycle(tmp_path_factory) -> CycleFixture:
    return build_cycle(tmp_path_factory.mktemp("cycle-failed"), reducer="stub", missing_coding_commit=True)


# =========================================================================== #
# 1. 纯函数层 —— plan 闭合
# =========================================================================== #


def _valid_plan() -> dict[str, str]:
    return {
        "cycle_id": CYCLE_ID,
        "target_contract_version": VERSION,
        "expected_contract_payload_hash": "sha256:" + "a" * 64,
        "wiki_candidate_commit": "1" * 40,
        "coding_candidate_commit": "2" * 40,
        "wiki_evidence_commit": "3" * 40,
        "coding_evidence_commit": "4" * 40,
        "created_at": "2026-09-16T12:00:00Z",
    }


@pytest.mark.parametrize("missing", sorted(coord.REQUIRED_PLAN_FIELDS))
def test_plan_missing_field_is_usage_error(missing: str) -> None:
    plan = _valid_plan()
    plan.pop(missing)
    with pytest.raises(coord.UsageError) as excinfo:
        coord.validate_plan(plan)
    assert missing in str(excinfo.value)


@pytest.mark.parametrize(
    "bad_sha",
    ["HEAD", "main", "abc123", "1" * 39, "1" * 41, "Z" * 40, "", "  ", "refs/heads/main"],
)
def test_plan_rejects_ref_like_or_malformed_sha(bad_sha: str) -> None:
    plan = _valid_plan()
    plan["wiki_candidate_commit"] = bad_sha
    with pytest.raises(coord.UsageError) as excinfo:
        coord.validate_plan(plan)
    assert "wiki_candidate_commit" in str(excinfo.value)


def test_plan_rejects_extra_fields_and_bad_metadata() -> None:
    plan = _valid_plan()
    plan["latest_successful_commit"] = "5" * 40
    with pytest.raises(coord.UsageError):
        coord.validate_plan(plan)

    plan = _valid_plan()
    plan["created_at"] = "yesterday"
    with pytest.raises(coord.UsageError):
        coord.validate_plan(plan)

    plan = _valid_plan()
    plan["target_contract_version"] = "0.1"
    with pytest.raises(coord.UsageError):
        coord.validate_plan(plan)

    plan = _valid_plan()
    plan["expected_contract_payload_hash"] = "sha256:short"
    with pytest.raises(coord.UsageError):
        coord.validate_plan(plan)


def test_plan_accepts_sixty_four_hex_commit() -> None:
    plan = _valid_plan()
    plan["wiki_candidate_commit"] = "a" * 64
    assert coord.validate_plan(plan)["wiki_candidate_commit"] == "a" * 64


# =========================================================================== #
# 2. 纯函数层 —— allowlist / ledger / current.json / 事件 / 自引用
# =========================================================================== #


def test_publication_allowlist_matches_spec14_and_g08() -> None:
    wiki = set(coord.evidence_publication_allowlist(VERSION, "wiki"))
    coding = set(coord.evidence_publication_allowlist(VERSION, "coding"))
    assert f"{RELEASE_REL}/changelog.md" in wiki, "G-08：allowlist 必须显式包含 changelog.md"
    assert f"{RELEASE_REL}/contract-manifest.json" in wiki
    assert f"{RELEASE_REL}/validation/wiki/sanitized-replay-corpus.jsonl" in wiki
    assert LEDGER_REL.as_posix() in wiki
    # Coding 不保存账本（Spec 14:41）
    assert LEDGER_REL.as_posix() not in coding
    assert not any("validation/wiki" in path for path in coding)


def test_check_diff_allowlist_rejects_scope_escape_and_deletion() -> None:
    ok = [
        ("A", f"{RELEASE_REL}/changelog.md"),
        ("A", f"{RELEASE_REL}/validation/wiki/run-manifest.json"),
        ("M", LEDGER_REL.as_posix()),
    ]
    assert coord.check_diff_allowlist(ok, version=VERSION, repository="wiki") == []

    outside = coord.check_diff_allowlist(
        [("M", "agent_core/contracts/version.py")], version=VERSION, repository="wiki"
    )
    assert outside and "越界" in outside[0]

    deleted = coord.check_diff_allowlist(
        [("D", f"{RELEASE_REL}/changelog.md")], version=VERSION, repository="wiki"
    )
    assert deleted and "非追加变更" in deleted[0]

    wrong_repo = coord.check_diff_allowlist(
        [("A", f"{RELEASE_REL}/validation/coding/run-manifest.json")],
        version=VERSION,
        repository="wiki",
    )
    assert wrong_repo and "越界" in wrong_repo[0]


def test_check_ledger_append_only_rules() -> None:
    base = _a_ledger_bytes()
    appended = base + _b_appended_ledger_bytes()
    assert coord.check_ledger_append_only(base, appended) == []

    # 空账本 → 视为 genesis，纯追加仍成立
    assert coord.check_ledger_append_only(b"", appended) == []

    # 非前缀（第一行被改写）
    tampered = b'{"event_id": "x"}\n' + appended.split(b"\n", 1)[1]
    errors = coord.check_ledger_append_only(base, tampered)
    assert errors and "非纯追加" in errors[0]

    # 未追加任何字节
    errors = coord.check_ledger_append_only(base, base)
    assert errors and "未追加任何字节" in errors[0]

    # 追加行不是 canonical JSON
    errors = coord.check_ledger_append_only(base, base + b'{"b": 1, "a": 2}\n')
    assert errors and "canonical JSON" in errors[0]

    # 追加部分未以换行结束
    errors = coord.check_ledger_append_only(base, base + b'{"a": 1}')
    assert errors and "换行" in errors[0]

    # B 中账本缺失
    errors = coord.check_ledger_append_only(base, b"")
    assert errors and "缺失" in errors[0]


def test_current_pointer_is_exactly_four_fields() -> None:
    pointer = {
        "contract_version": VERSION,
        "contract_payload_hash": "sha256:" + "a" * 64,
        "cycle_id": CYCLE_ID,
        "release_path": RELEASE_REL,
    }
    assert final.check_current_pointer(pointer) == []
    assert final.check_current_pointer({**pointer, "cycle_report_hash": "x"})
    assert final.check_current_pointer({k: v for k, v in pointer.items() if k != "cycle_id"})


def test_plan_ledger_events_is_legal_main_path() -> None:
    events = final.plan_ledger_events(
        "NOT_STARTED",
        cycle_id=CYCLE_ID,
        candidate_commit="a" * 40,
        coordination_hash="sha256:" + "b" * 64,
        timestamp="2026-09-16T12:00:00Z",
    )
    assert [event["from_status"] for event in events] == [
        "NOT_STARTED",
        "READY",
        "IN_PROGRESS",
        "VALIDATED",
    ]
    assert [event["to_status"] for event in events] == [
        "READY",
        "IN_PROGRESS",
        "VALIDATED",
        "COMPLETE",
    ]
    assert [event["reason_code"] for event in events] == [
        "PREREQUISITES_SATISFIED",
        "EXECUTION_STARTED",
        "COORDINATION_PASSED",
        "FINALIZATION_COMPLETE",
    ]
    assert "COORDINATION_PASSED" in [event["reason_code"] for event in events]
    assert "FINALIZATION_COMPLETE" in [event["reason_code"] for event in events]
    for event in events:
        assert set(event) == set(final.EVENT_KEYS), "事件字段必须与 I.2 Event Schema 完全一致"
        assert event["spec_id"] == "15"
        assert event["candidate_commit"] == "a" * 40
        assert event["evidence_refs"], "VALIDATED 必须有 Evidence reference"


def test_plan_ledger_events_respects_current_status() -> None:
    kwargs = dict(
        cycle_id=CYCLE_ID,
        candidate_commit="a" * 40,
        coordination_hash="sha256:" + "b" * 64,
        timestamp="2026-09-16T12:00:00Z",
    )
    assert [e["reason_code"] for e in final.plan_ledger_events("IN_PROGRESS", **kwargs)] == [
        "COORDINATION_PASSED",
        "FINALIZATION_COMPLETE",
    ]
    assert [e["reason_code"] for e in final.plan_ledger_events("VALIDATED", **kwargs)] == [
        "FINALIZATION_COMPLETE"
    ]
    assert final.plan_ledger_events("COMPLETE", **kwargs) == []
    assert final.plan_ledger_events("SUPERSEDED", **kwargs) == []
    with pytest.raises(final.UsageError):
        final.plan_ledger_events("BLOCKED", **kwargs)
    with pytest.raises(final.UsageError):
        final.plan_ledger_events("WAT", **kwargs)


def test_reduce_spec_status_follows_file_order() -> None:
    assert final.reduce_spec_status("", "15") == "NOT_STARTED"
    assert final.reduce_spec_status(_a_ledger_bytes().decode("utf-8"), "11") == "IN_PROGRESS"
    text = _a_ledger_bytes().decode("utf-8") + _b_appended_ledger_bytes().decode("utf-8")
    assert final.reduce_spec_status(text, "14") == "COMPLETE"
    assert final.reduce_spec_status(text, "15") == "NOT_STARTED"


def test_no_self_sha_detection() -> None:
    c_sha = "d" * 40
    assert final.check_no_self_sha({"a.json": '{"cycle_id": "x"}'}, c_sha) == []
    hit = final.check_no_self_sha({"a.json": json.dumps({"finalization_commit": c_sha})}, c_sha)
    assert len(hit) == 2, "既命中禁用字段名，也命中 C SHA 字面值"
    assert final.check_no_self_sha({"a.json": c_sha}, c_sha)
    assert final.check_no_self_sha({"a.json": c_sha.upper()}, c_sha)


def test_c_allowlist_pure_function() -> None:
    allowed = {
        f"{RELEASE_REL}/cycle-report.json",
        f"{RELEASE_REL}/cycle-report.md",
        "docs/contracts/current.json",
        LEDGER_REL.as_posix(),
    }
    ok = [
        ("A", f"{RELEASE_REL}/cycle-report.json"),
        ("A", f"{RELEASE_REL}/cycle-report.md"),
        ("A", "docs/contracts/current.json"),
        ("M", LEDGER_REL.as_posix()),
    ]
    assert final.check_c_allowlist(ok, allowed) == []
    assert final.check_c_allowlist([("M", f"{RELEASE_REL}/changelog.md")], allowed)
    assert final.check_c_allowlist([("D", LEDGER_REL.as_posix())], allowed)


# =========================================================================== #
# 3. coordinator CLI —— 用法错误（退出 2）
# =========================================================================== #


def test_coordinator_missing_plan_exits_2(tmp_path: Path) -> None:
    proc = run_cli(COORDINATOR, "--plan", tmp_path / "nope.json", "--output", tmp_path / "out")
    assert proc.returncode == 2, proc.stderr
    assert "cycle plan" in proc.stderr


def test_coordinator_rejects_ref_plan_exits_2(tmp_path: Path) -> None:
    plan = _valid_plan()
    plan["wiki_candidate_commit"] = "HEAD"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    proc = run_cli(COORDINATOR, "--plan", plan_path, "--output", tmp_path / "out")
    assert proc.returncode == 2, proc.stderr
    assert "wiki_candidate_commit" in proc.stderr
    assert not (tmp_path / "out").exists(), "用法错误不得产生 artifact"


def test_coordinator_rejects_output_inside_real_docs_contracts(tmp_path: Path) -> None:
    plan = _valid_plan()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    proc = run_cli(
        COORDINATOR,
        "--plan",
        plan_path,
        "--output",
        REPO_ROOT / "docs" / "contracts" / "releases",
    )
    assert proc.returncode == 2, proc.stdout
    assert "fixture" in proc.stderr


# =========================================================================== #
# 4. coordinator CLI —— 正向 / 反向（真实 git fixture）
# =========================================================================== #


def test_coordinator_pass_is_ready_for_finalization(good_cycle: CycleFixture) -> None:
    proc = good_cycle.run_coordinator()
    assert proc.returncode == 0, proc.stdout + proc.stderr

    artifact = good_cycle.coordination()
    assert artifact["coordination_result"] == "PASS"
    assert artifact["cycle_state"] == "READY_FOR_FINALIZATION"
    assert artifact["cycle_id"] == CYCLE_ID
    assert artifact["contract_version"] == VERSION
    assert artifact["contract_payload_hash"] == good_cycle.payload_hash
    assert artifact["wiki_candidate_commit"] == good_cycle.wiki_a
    assert artifact["coding_candidate_commit"] == good_cycle.coding_a
    assert artifact["wiki_evidence_commit"] == good_cycle.wiki_b
    assert artifact["coding_evidence_commit"] == good_cycle.coding_b
    # check 6：两项目独立 Evidence Manifest Hash —— 不同是正常事实，不得要求相等
    assert artifact["wiki_evidence_manifest_hash"].startswith("sha256:")
    assert artifact["coding_evidence_manifest_hash"].startswith("sha256:")
    assert artifact["wiki_evidence_manifest_hash"] != artifact["coding_evidence_manifest_hash"]
    # check 9：协调身份
    assert artifact["coordinator_repository"] == "wiki"
    assert artifact["coordinator_commit"] == good_cycle.wiki_a
    assert artifact["coordination_tool_version"]
    assert artifact["coordination_run_id"], "run ID 缺失时也应记为 'unknown' 而非空"
    assert artifact["workflow_version"]
    # 17 字段（§16.5 的 16 + Spec 15:50 要求的 workflow_version）
    for name in (
        "cycle_id",
        "contract_version",
        "contract_payload_hash",
        "wiki_candidate_commit",
        "coding_candidate_commit",
        "wiki_evidence_commit",
        "coding_evidence_commit",
        "wiki_evidence_manifest_hash",
        "coding_evidence_manifest_hash",
        "coordination_result",
        "cycle_state",
        "coordinator_repository",
        "coordinator_commit",
        "coordination_tool_version",
        "coordination_run_id",
        "completed_at",
        "workflow_version",
    ):
        assert name in artifact, f"缺少 §16.5 字段 {name}"


def test_coordinator_checks_are_all_pass_and_cover_nine_items(good_cycle: CycleFixture) -> None:
    assert good_cycle.run_coordinator().returncode == 0
    artifact = good_cycle.coordination()
    checks = {check["check"]: check for check in artifact["checks"]}
    assert set(checks) == {1, 2, 3, 4, 5, 7, 8, 9}, "Spec 15:42-51 的 9 项检查（5+6 合并为一条）"
    for index, check in checks.items():
        assert check["status"] == "PASS", f"check {index} 未通过：{check}"
    assert "A is ancestor of B" in checks[2]["name"]
    assert "allowlist" in checks[3]["name"]
    assert "Evidence Manifest" in checks[5]["name"]
    assert "Ledger" in checks[8]["name"]


def test_coordinator_artifacts_never_claim_complete(good_cycle: CycleFixture) -> None:
    report = good_cycle.coordination()
    json_text = (good_cycle.output_dir / "coordination.json").read_text(encoding="utf-8")
    md_text = (good_cycle.output_dir / "coordination.md").read_text(encoding="utf-8")

    def walk(value: object) -> list[str]:
        if isinstance(value, dict):
            return [item for child in value.values() for item in walk(child)]
        if isinstance(value, list):
            return [item for child in value for item in walk(child)]
        return [value] if isinstance(value, str) else []

    assert "COMPLETE" not in walk(report), "协调 artifact 不得把 COMPLETE 作为任何字段值"
    assert "| `COMPLETE`" not in md_text
    assert report["cycle_state"] == "READY_FOR_FINALIZATION"
    assert "cycle-report" not in json_text, "coordinator 不产出 cycle report / current pointer"
    assert not (good_cycle.output_dir / "current.json").exists()
    assert not (good_cycle.wiki / "docs" / "contracts" / "current.json").exists()


@pytest.mark.parametrize(
    ("fixture_name", "expected_result", "expected_state"),
    [
        ("good_cycle", "PASS", "READY_FOR_FINALIZATION"),
        ("diverged_cycle", "DIVERGED", "DIVERGED"),
        ("failed_cycle", "FAILED", "FAILED"),
    ],
)
def test_coordinator_result_and_state_are_closed_set(
    request, fixture_name: str, expected_result: str, expected_state: str
) -> None:
    fixture = request.getfixturevalue(fixture_name)
    proc = fixture.run_coordinator()
    if expected_result == "PASS":
        assert proc.returncode == 0, proc.stdout + proc.stderr
    else:
        assert proc.returncode == 1, proc.stdout + proc.stderr
    artifact = fixture.coordination()
    assert artifact["coordination_result"] == expected_result
    assert artifact["cycle_state"] == expected_state
    assert artifact["coordination_result"] != "COMPLETE"
    assert artifact["cycle_state"] != "COMPLETE"


def test_coordinator_diverged_when_same_version_different_payload(
    diverged_cycle: CycleFixture,
) -> None:
    proc = diverged_cycle.run_coordinator()
    assert proc.returncode == 1
    artifact = diverged_cycle.coordination()
    assert artifact["coordination_result"] == "DIVERGED"
    assert artifact["cycle_state"] == "DIVERGED"
    assert "不同" in artifact["divergence_reason"]
    # DIVERGED 时后续证据校验被跳过而非伪装通过
    statuses = {check["check"]: check["status"] for check in artifact["checks"]}
    assert statuses[4] == "FAIL"
    assert statuses[5] == "SKIP"
    assert statuses[7] == "SKIP"


def test_coordinator_fails_when_commit_missing(failed_cycle: CycleFixture) -> None:
    proc = failed_cycle.run_coordinator()
    assert proc.returncode == 1
    artifact = failed_cycle.coordination()
    assert artifact["coordination_result"] == "FAILED"
    check1 = next(check for check in artifact["checks"] if check["check"] == 1)
    assert check1["status"] == "FAIL"
    assert "coding_evidence_commit" in check1["detail"]


def test_coordinator_fails_on_out_of_allowlist_diff(tmp_path: Path) -> None:
    fixture = build_cycle(tmp_path, reducer="stub", extra_out_of_allowlist="docs/notes/cycle.md")
    proc = fixture.run_coordinator()
    assert proc.returncode == 1
    artifact = fixture.coordination()
    assert artifact["coordination_result"] == "FAILED"
    check3 = next(check for check in artifact["checks"] if check["check"] == 3)
    assert check3["status"] == "FAIL"
    assert "越界" in check3["detail"] and "docs/notes/cycle.md" in check3["detail"]


def test_coordinator_fails_when_ledger_is_not_append_only(tmp_path: Path) -> None:
    fixture = build_cycle(tmp_path, reducer="stub", ledger_mode="rewrite")
    proc = fixture.run_coordinator()
    assert proc.returncode == 1
    artifact = fixture.coordination()
    check8 = next(check for check in artifact["checks"] if check["check"] == 8)
    assert check8["status"] == "FAIL"
    assert "非纯追加" in check8["detail"]


def test_coordinator_fails_when_ledger_has_no_appended_bytes(tmp_path: Path) -> None:
    fixture = build_cycle(tmp_path, reducer="stub", ledger_mode="empty")
    proc = fixture.run_coordinator()
    assert proc.returncode == 1
    check8 = next(check for check in fixture.coordination()["checks"] if check["check"] == 8)
    assert check8["status"] == "FAIL"
    assert "未追加任何字节" in check8["detail"]


def test_coordinator_fails_when_evidence_manifest_payload_differs(tmp_path: Path) -> None:
    fixture = build_cycle(tmp_path, reducer="stub", manifest_payload_hash="sha256:" + "9" * 64)
    proc = fixture.run_coordinator()
    assert proc.returncode == 1
    artifact = fixture.coordination()
    check5 = next(check for check in artifact["checks"] if check["check"] == 5)
    assert check5["status"] == "FAIL"
    assert "contract_payload_hash" in check5["detail"]


def test_coordinator_fails_when_reducer_absent_in_a(tmp_path: Path) -> None:
    fixture = build_cycle(tmp_path, reducer=None)
    proc = fixture.run_coordinator()
    assert proc.returncode == 1
    check8 = next(check for check in fixture.coordination()["checks"] if check["check"] == 8)
    assert check8["status"] == "FAIL"
    assert "STATUS_REDUCER_UNAVAILABLE" in check8["detail"], "缺失 reducer 必须显式失败，不得静默通过"


def test_coordinator_fails_when_reducer_rejects_ledger(tmp_path: Path) -> None:
    fixture = build_cycle(tmp_path, reducer="rejecting")
    proc = fixture.run_coordinator()
    assert proc.returncode == 1
    check8 = next(check for check in fixture.coordination()["checks"] if check["check"] == 8)
    assert check8["status"] == "FAIL"
    assert "SPEC_STATUS_CONFLICT" in check8["detail"]


def test_coordinator_uses_a_tree_reducer_cli(good_cycle_with_real_reducer: CycleFixture) -> None:
    """A 中的真实 reducer（`status_ledger.py validate --ledger ... --spec-dir ...`）归约通过。"""
    proc = good_cycle_with_real_reducer.run_coordinator()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    artifact = good_cycle_with_real_reducer.coordination()
    assert artifact["coordination_result"] == "PASS"
    check8 = next(check for check in artifact["checks"] if check["check"] == 8)
    assert check8["status"] == "PASS"
    assert "reducer" in check8["detail"]


def test_coordinator_reads_only_named_env_vars(good_cycle: CycleFixture, tmp_path: Path) -> None:
    output = tmp_path / "coordination-env"
    proc = run_cli(
        COORDINATOR,
        "--plan",
        good_cycle.plan_path,
        "--output",
        output,
        "--wiki-repo",
        good_cycle.wiki,
        "--coding-repo",
        good_cycle.coding,
        env={
            "AGENT_CONTRACT_RUN_ID": "run-42",
            "AGENT_CONTRACT_WORKFLOW_VERSION": "workflow-7",
            "AGENT_CONTRACT_COORDINATOR_REPOSITORY": "wiki",
            "COORDINATOR_SECRET_TOKEN": "should-never-appear",
        },
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = (output / "coordination.json").read_text(encoding="utf-8")
    artifact = json.loads(text)
    assert artifact["coordination_run_id"] == "run-42"
    assert artifact["workflow_version"] == "workflow-7"
    assert "should-never-appear" not in text
    assert "COORDINATOR_SECRET_TOKEN" not in text, "不得 dump 环境变量名/值"


# =========================================================================== #
# 5. finalizer —— 正向：C allowlist / current.json / 账本事件
# =========================================================================== #


def test_finalize_prepares_c_files_then_validates_ancestry(tmp_path: Path) -> None:
    fixture = build_cycle(tmp_path, reducer="stub")
    assert fixture.run_coordinator().returncode == 0

    # 阶段 1：缺少 B/C SHA → 如实标注未校验并失败（exit 1），但 C allowlist 文件已准备
    phase1 = run_cli(
        FINALIZER,
        "--coordination",
        fixture.output_dir,
        "--release",
        fixture.release_dir,
        "--ledger",
        fixture.ledger_path,
        "--wiki-repo",
        fixture.wiki,
    )
    assert phase1.returncode == 1, phase1.stdout + phase1.stderr

    report_path = fixture.release_dir / "cycle-report.json"
    report_md = fixture.release_dir / "cycle-report.md"
    pointer_path = fixture.wiki / "docs" / "contracts" / "current.json"
    assert report_path.is_file() and report_md.is_file() and pointer_path.is_file()

    coordination_text = (fixture.output_dir / "coordination.json").read_text(encoding="utf-8")
    assert report_path.read_text(encoding="utf-8") == coordination_text, "cycle-report 必须字节一致"
    expected_hash = final.canonical_hash(json.loads(coordination_text))
    assert final.canonical_hash(json.loads(report_path.read_text(encoding="utf-8"))) == expected_hash
    assert (
        final.normalize_markdown_bytes(report_md.read_bytes())
        == final.normalize_markdown_bytes((fixture.output_dir / "coordination.md").read_bytes())
    )

    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert sorted(pointer) == ["contract_payload_hash", "contract_version", "cycle_id", "release_path"]
    assert pointer == {
        "contract_version": VERSION,
        "contract_payload_hash": fixture.payload_hash,
        "cycle_id": CYCLE_ID,
        "release_path": RELEASE_REL,
    }

    # 账本：只追加 reducer 可识别事件
    appended = _read_ledger(fixture.ledger_path)
    assert appended[-4:] == [
        "PREREQUISITES_SATISFIED",
        "EXECUTION_STARTED",
        "COORDINATION_PASSED",
        "FINALIZATION_COMPLETE",
    ]

    # 阶段 2：形成 C_wiki → ancestry / diff allowlist 通过
    c_sha = _commit(fixture.wiki, "C: finalization fixture")
    phase2 = run_cli(
        FINALIZER,
        "--coordination",
        fixture.output_dir,
        "--release",
        fixture.release_dir,
        "--ledger",
        fixture.ledger_path,
        "--wiki-repo",
        fixture.wiki,
        "--b-wiki",
        fixture.wiki_b,
        "--c-wiki",
        c_sha,
        "--json",
    )
    assert phase2.returncode == 0, phase2.stdout + phase2.stderr
    summary = json.loads([line for line in phase2.stdout.splitlines() if line.startswith("{")][0])
    assert summary["finalization_result"] == "PASS"
    assert summary["ledger_already_finalized"] is True, "重跑必须幂等，不重复追加事件"
    assert summary["ledger_events_appended"] == []
    assert summary["c_wiki"] == c_sha

    statuses = {check["check"]: check["status"] for check in summary["checks"]}
    assert statuses == {1: "PASS", 2: "PASS", 3: "PASS", 4: "PASS", 5: "PASS", 6: "PASS", 7: "PASS", 8: "PASS"}
    diff = _git(fixture.wiki, "diff", "--name-status", fixture.wiki_b, c_sha)
    for line in diff.splitlines():
        path = line.split("\t")[1]
        assert path in {
            f"{RELEASE_REL}/cycle-report.json",
            f"{RELEASE_REL}/cycle-report.md",
            "docs/contracts/current.json",
            LEDGER_REL.as_posix(),
        }, f"C 混入 allowlist 外文件：{path}"


def _read_ledger(path: Path) -> list[str]:
    """读取账本中 Spec 15 事件的 reason_code 序列。"""
    reason_codes: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("spec_id") == "15":
            reason_codes.append(record["reason_code"])
    return reason_codes


def test_finalizer_events_are_reducer_legal(tmp_path: Path) -> None:
    """把 finalizer 追加的事件交给**真实** status_ledger.py 归约，Spec 15 应到 COMPLETE。"""
    if not REAL_REDUCER.is_file():
        pytest.skip("scripts/contracts/status_ledger.py 尚未实现（由其他执行者并行交付）")
    fixture = build_cycle(tmp_path, reducer="real")
    assert fixture.run_coordinator().returncode == 0
    proc = run_cli(
        FINALIZER,
        "--coordination",
        fixture.output_dir,
        "--release",
        tmp_path / "release",
        "--ledger",
        fixture.ledger_path,
        "--wiki-repo",
        fixture.wiki,
    )
    assert proc.returncode == 1, "缺少 B/C SHA 时必须 fail closed"
    assert _read_ledger(fixture.ledger_path)[-2:] == [
        "COORDINATION_PASSED",
        "FINALIZATION_COMPLETE",
    ]

    reduction = subprocess.run(
        [
            sys.executable,
            str(REAL_REDUCER),
            "validate",
            "--ledger",
            str(fixture.ledger_path),
            "--spec-dir",
            str(REPO_ROOT / SPEC_DIR_REL),
            "--index",
            str(REPO_ROOT / SPEC_DIR_REL / "00-execution-index.md"),
            "--json",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    assert reduction.returncode == 0, reduction.stdout + reduction.stderr
    payload = json.loads(reduction.stdout)
    statuses = {row["spec_id"]: row["status"] for row in payload["effective_status"]}
    assert statuses["15"] == "COMPLETE"
    assert statuses["14"] == "COMPLETE"


# =========================================================================== #
# 6. finalizer —— 反向与安全边界
# =========================================================================== #


def test_finalize_hash_mismatch_exits_1_without_writing(good_cycle: CycleFixture, tmp_path: Path) -> None:
    release = tmp_path / "release-mismatch"
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(good_cycle.ledger_path.read_bytes())
    proc = run_cli(
        FINALIZER,
        "--coordination",
        good_cycle.output_dir,
        "--release",
        release,
        "--ledger",
        ledger,
        "--expected-coordination-hash",
        "sha256:" + "0" * 64,
    )
    assert proc.returncode == 1, proc.stdout
    assert "canonical hash 不匹配" in proc.stderr
    assert not release.exists(), "hash 不匹配时不得写入任何 C 文件"
    assert ledger.read_bytes() == good_cycle.ledger_path.read_bytes()


def test_finalize_rejects_non_pass_coordination(tmp_path: Path) -> None:
    coordination = tmp_path / "coordination"
    coordination.mkdir()
    artifact = {
        "cycle_id": CYCLE_ID,
        "contract_version": VERSION,
        "cycle_state": "FAILED",
        "coordination_result": "FAILED",
    }
    (coordination / "coordination.json").write_text(
        canonical_json_dumps(artifact) + "\n", encoding="utf-8", newline="\n"
    )
    (coordination / "coordination.md").write_text("# failed\n", encoding="utf-8", newline="\n")
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(b"")
    proc = run_cli(
        FINALIZER,
        "--coordination",
        coordination,
        "--release",
        tmp_path / "release",
        "--ledger",
        ledger,
    )
    assert proc.returncode == 1
    assert not (tmp_path / "release").exists()


def test_finalize_missing_ledger_exits_2(good_cycle: CycleFixture, tmp_path: Path) -> None:
    proc = run_cli(
        FINALIZER,
        "--coordination",
        good_cycle.output_dir,
        "--release",
        tmp_path / "release",
        "--ledger",
        tmp_path / "missing-ledger.jsonl",
    )
    assert proc.returncode == 2, proc.stdout
    assert "目标账本不存在" in proc.stderr


def test_finalize_default_temp_ledger_missing_exits_2(good_cycle: CycleFixture, tmp_path: Path) -> None:
    default = Path(tempfile.gettempdir()) / "foundation-contract-cycle" / f"{CYCLE_ID}.jsonl"
    if default.exists():
        pytest.skip(f"默认临时账本已存在，无法验证缺失分支：{default}")
    proc = run_cli(
        FINALIZER,
        "--coordination",
        good_cycle.output_dir,
        "--release",
        tmp_path / "release",
    )
    assert proc.returncode == 2, proc.stdout
    assert "--ledger" in proc.stderr


def test_finalize_refuses_real_ledger(good_cycle: CycleFixture, tmp_path: Path) -> None:
    proc = run_cli(
        FINALIZER,
        "--coordination",
        good_cycle.output_dir,
        "--release",
        tmp_path / "release",
        "--ledger",
        REAL_LEDGER,
    )
    assert proc.returncode == 2, proc.stdout
    assert "拒绝写入本仓真实账本" in proc.stderr


def test_finalize_refuses_real_release_tree(good_cycle: CycleFixture, tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(good_cycle.ledger_path.read_bytes())
    proc = run_cli(
        FINALIZER,
        "--coordination",
        good_cycle.output_dir,
        "--release",
        REPO_ROOT / RELEASE_REL,
        "--ledger",
        ledger,
    )
    assert proc.returncode == 2, proc.stdout
    assert "真实发布树" in proc.stderr


def test_finalize_never_records_self_sha(tmp_path: Path) -> None:
    fixture = build_cycle(tmp_path, reducer="stub")
    assert fixture.run_coordinator().returncode == 0
    phase1 = run_cli(
        FINALIZER,
        "--coordination",
        fixture.output_dir,
        "--release",
        fixture.release_dir,
        "--ledger",
        fixture.ledger_path,
        "--wiki-repo",
        fixture.wiki,
    )
    assert phase1.returncode == 1
    c_sha = _commit(fixture.wiki, "C: self-sha fixture")
    phase2 = run_cli(
        FINALIZER,
        "--coordination",
        fixture.output_dir,
        "--release",
        fixture.release_dir,
        "--ledger",
        fixture.ledger_path,
        "--wiki-repo",
        fixture.wiki,
        "--b-wiki",
        fixture.wiki_b,
        "--c-wiki",
        c_sha,
    )
    assert phase2.returncode == 0, phase2.stdout + phase2.stderr

    artifacts = [
        fixture.release_dir / "cycle-report.json",
        fixture.release_dir / "cycle-report.md",
        fixture.wiki / "docs" / "contracts" / "current.json",
        fixture.ledger_path,
    ]
    for path in artifacts:
        content = path.read_text(encoding="utf-8")
        assert c_sha not in content, f"{path.name} 记录了 C 自身 SHA"
        assert c_sha.upper() not in content
        for key in ("c_wiki", "finalization_commit", "self_hash", "current_commit"):
            assert f'"{key}"' not in content, f"{path.name} 出现自身身份字段名 {key}"

    # 账本事件不得引用 C；candidate_commit 必须是 A_wiki
    spec15 = [
        json.loads(line)
        for line in fixture.ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("spec_id") == "15"
    ]
    assert spec15, "finalizer 必须追加 Spec 15 事件"
    for event in spec15:
        assert event["candidate_commit"] == fixture.wiki_a
        assert c_sha not in json.dumps(event)


def test_finalize_leaves_preexisting_b_evidence_untouched(tmp_path: Path) -> None:
    fixture = build_cycle(tmp_path, reducer="stub")
    assert fixture.run_coordinator().returncode == 0
    before_wiki = {
        path.relative_to(fixture.wiki).as_posix(): path.read_bytes()
        for path in fixture.release_dir.rglob("*")
        if path.is_file()
    }
    before_release = {
        path.relative_to(fixture.release_dir).as_posix()
        for path in fixture.release_dir.rglob("*")
        if path.is_file()
    }
    proc = run_cli(
        FINALIZER,
        "--coordination",
        fixture.output_dir,
        "--release",
        fixture.release_dir,
        "--ledger",
        fixture.ledger_path,
        "--wiki-repo",
        fixture.wiki,
    )
    assert proc.returncode == 1
    for relative, content in before_wiki.items():
        assert (fixture.wiki / relative).read_bytes() == content, f"finalizer 触碰了 B 证据文件 {relative}"
    after_release = {
        path.relative_to(fixture.release_dir).as_posix()
        for path in fixture.release_dir.rglob("*")
        if path.is_file()
    }
    assert after_release - before_release == {"cycle-report.json", "cycle-report.md"}
