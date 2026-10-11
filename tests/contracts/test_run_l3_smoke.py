"""A2 — ``scripts/contracts/run_l3_smoke.py``（L3 fresh smoke 驱动器）自测。

只测**合成证据**：不联网、不调用真实模型、不使用仓库 fixtures 目录。端到端的
"业务路径"由 ``tmp_path`` 里的 fixture 子进程扮演，它用**真实**的项目 sink 写**真实**的
``EvidenceRecord``（含真实 Payload Hash），因此被验证的解析/推导/gate 闭合都是真的。

``scripts/contracts/`` 不是包，驱动器按文件路径加载（与 Spec 09/10 的既有模式一致）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER_PATH = REPO_ROOT / "scripts" / "contracts" / "run_l3_smoke.py"
SMOKE_MANIFEST = REPO_ROOT / "config" / "contracts" / "smoke-v0.1.json"
DEFAULT_CASE_SOURCE = REPO_ROOT / "benchmarks" / "arknights_bench" / "questions_draft.jsonl"
REGISTERED_CASE_ID = "character_complex_002"
COMMIT = "a" * 40

#: 冻结的退出码/标记（G-18 provisional）。
EXIT_OK, EXIT_GATE_FAILED, EXIT_USAGE = 0, 1, 2


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def drv():
    """驱动器模块（它自己会导入同目录的 ``validate_local``）。"""
    return _load(DRIVER_PATH, "_fc_run_l3_smoke")


@pytest.fixture(scope="module")
def vl(drv):
    return drv.vl


# --------------------------------------------------------------------------- #
# 合成业务子进程（扮演 ``python -m arknights_wiki.eval.runner``）
# --------------------------------------------------------------------------- #

FIXTURE_BUSINESS = '''
import json
import os
import sys
import uuid
from pathlib import Path

repo_root = Path(sys.argv[1])
bench = Path(sys.argv[2])
out_dir = Path(sys.argv[3])
sys.path.insert(0, str(repo_root))

from agent_core.contracts.enums.evidence import EvidenceRepository, ValidationStatus
from agent_core.contracts.enums.modes import ContractMode
from agent_core.contracts.enums.sources import CostSource, UsageSource
from agent_core.contracts.models.cost import Cost, CostSummary
from agent_core.contracts.models.evidence import EvidenceRecord, FoundationObservation
from agent_core.contracts.models.usage import Usage

from arknights_wiki.adapters.foundation.evidence_sink import FileEvidenceSink
from arknights_wiki.adapters.foundation.runtime import resolve_payload_hash

run_id = os.environ["AGENT_CONTRACT_RUN_ID"]
commit = os.environ["AGENT_CONTRACT_COMMIT"]
assert os.environ["AGENT_CONTRACT_MODE"] == "observe", "fixture 必须在 observe 下运行"

payload_hash = resolve_payload_hash()
sink = FileEvidenceSink()


def emit(producer_id, stage, observation):
    sink.emit(
        EvidenceRecord(
            event_id=str(uuid.uuid4()),
            run_id=run_id,
            repository=EvidenceRepository.WIKI,
            repository_commit=commit,
            producer_id=producer_id,
            mapping_stage=stage,
            contract_mode=ContractMode.OBSERVE,
            contract_version="0.1.0",
            contract_payload_hash=payload_hash,
            timestamp="2026-01-01T00:00:00Z",
            validation_status=ValidationStatus.PASS,
            sanitized_input_facts={"wiki.model.name": "fixture"},
            foundation_output=observation,
        )
    )


# 6 个 (producer_id, mapping_stage)：5 个带 usage+cost，另加 1 条 unknown cost。
for producer_id, stage in (
    ("wiki.agent.llm_usage", "chat_completion"),
    ("wiki.agent.llm_usage", "intent_rewrite"),
    ("wiki.eval.cost_log", "runner"),
    ("wiki.eval.cost_log", "judge"),
    ("wiki.eval.cost_log", "scoring"),
):
    emit(
        producer_id,
        stage,
        FoundationObservation(
            usage=Usage(input_tokens=11, output_tokens=7, source=UsageSource.PROVIDER_REPORTED),
            cost=Cost(amount="0.001", currency="CNY", source=CostSource.ESTIMATED),
        ),
    )

emit(
    "wiki.eval.cost_log",
    "runner",
    FoundationObservation(
        usage=Usage(input_tokens=3, output_tokens=None, source=UsageSource.UNKNOWN),
        cost=Cost(amount=None, currency=None, source=CostSource.UNKNOWN),
    ),
)
emit(
    "wiki.eval.cost_summary",
    "cost_log_summary",
    FoundationObservation(
        cost_summary=CostSummary(
            complete=True,
            component_count=1,
            known_component_count=1,
            unknown_component_count=0,
            known_amount="0.001",
            currency="CNY",
        )
    ),
)

records = [json.loads(line) for line in bench.read_text(encoding="utf-8").splitlines() if line.strip()]
assert len(records) == 1, f"投影 bench 应当只有 1 条，实际 {len(records)}"
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "results_v1.jsonl").write_text(
    json.dumps({"id": records[0]["id"], "mode": "direct", "answer": "fixture"}, ensure_ascii=False) + "\\n",
    encoding="utf-8",
)
(out_dir / "report_v1.md").write_text("# fixture report\\n", encoding="utf-8")
print("fixture business run OK:", records[0]["id"])
'''


@pytest.fixture
def fixture_business(tmp_path_factory) -> Path:
    home = tmp_path_factory.mktemp("l3-business")
    script = home / "fixture_business.py"
    script.write_text(FIXTURE_BUSINESS, encoding="utf-8")
    return script


# --------------------------------------------------------------------------- #
# 隔离的仓库根 + 测试 manifest
# --------------------------------------------------------------------------- #


@pytest.fixture
def isolated_repo(drv, vl, tmp_path, monkeypatch):
    """把 gate 解析的 ``REPO_ROOT`` 指向 tmp：staging 写入完全不碰真仓。

    ``arknights_wiki/`` 目录必须存在，否则 ``validate_local.repository_name()``
    会判定为 coding 仓并去 import 另一个仓的 sink；bench 目录同样镜像过去，
    让**缺省** case source 在隔离仓里也能解析。
    """
    import shutil

    repo = tmp_path / "repo"
    (repo / "arknights_wiki").mkdir(parents=True)
    bench_dir = repo / "benchmarks" / "arknights_bench"
    bench_dir.mkdir(parents=True)
    shutil.copyfile(DEFAULT_CASE_SOURCE, bench_dir / DEFAULT_CASE_SOURCE.name)
    monkeypatch.setattr(vl, "REPO_ROOT", repo)
    monkeypatch.setenv("AGENT_CONTRACT_MODE", "observe")
    monkeypatch.setenv("AGENT_CONTRACT_COMMIT", COMMIT)
    return repo


def _test_manifest(run_id: str, **overrides) -> dict:
    """冻结的 smoke 预登记 + 仅覆盖 run_id/commit 之类运行期取值。"""
    manifest = json.loads(SMOKE_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["payload_hash"] == _payload_hash(), (
        "Payload Hash 漂移：合成证据必须绑定当前 checkout（PR gate step 3 的同一对象）"
    )
    assert manifest["case_ids"] == [REGISTERED_CASE_ID]
    manifest["run_id"] = run_id
    manifest["repository_commit"] = COMMIT
    manifest.update(overrides)
    return manifest


def _payload_hash() -> str:
    from arknights_wiki.adapters.foundation.runtime import resolve_payload_hash

    return resolve_payload_hash()


def _write_manifest(tmp_path: Path, manifest: dict) -> Path:
    path = tmp_path / "smoke-test.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return path


def _new_run_id() -> str:
    return f"pytest-l3-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def synthetic_run(drv, vl, isolated_repo, tmp_path, monkeypatch, fixture_business):
    """完整合成 L3：真 sink 写事件 + 驱动器推导 run-summary + 真 gate 校验。"""
    run_id = _new_run_id()
    manifest = _test_manifest(run_id)
    manifest_path = _write_manifest(tmp_path, manifest)
    monkeypatch.setenv("AGENT_CONTRACT_RUN_ID", run_id)
    monkeypatch.setattr(
        drv,
        "_default_command_factory",
        lambda bench, out: [
            sys.executable,
            str(fixture_business),
            str(REPO_ROOT),
            str(bench),
            str(out),
        ],
    )
    outcome = drv.run_l3(manifest_path=manifest_path)
    run_root = isolated_repo / manifest["evidence_root"] / run_id
    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "run_id": run_id,
        "run_root": run_root,
        "outcome": outcome,
    }


# --------------------------------------------------------------------------- #
# 1. 冻结面：必需键集合与 RUN_SUMMARY_KEYS 必须与 gate 逐字一致
# --------------------------------------------------------------------------- #


def _gate_required_keys(vl) -> frozenset:
    """从 ``gate_smoke`` 的字面量表取出必需键集合（CPython 把集合字面量折成 frozenset）。"""
    constants = [
        item
        for item in vl.gate_smoke.__code__.co_consts
        if isinstance(item, frozenset) and "manifest_version" in item
    ]
    assert len(constants) == 1, f"未能在 gate_smoke 常量表中唯一定位必需键集合：{constants}"
    return constants[0]


def test_manifest_required_keys_match_gate_smoke(drv, vl) -> None:
    assert drv.MANIFEST_REQUIRED_KEYS == _gate_required_keys(vl)
    assert len(drv.MANIFEST_REQUIRED_KEYS) == 19


def test_run_summary_keys_are_the_frozen_eight(drv, vl) -> None:
    assert tuple(vl.RUN_SUMMARY_KEYS) == (
        "sink_failure_count",
        "rejected_records",
        "actual_calls",
        "actual_tokens",
        "duration_seconds",
        "producer_coverage",
        "known_cost_components",
        "unknown_cost_components",
    )
    assert len(vl.RUN_SUMMARY_KEYS) == 8


# --------------------------------------------------------------------------- #
# 2. manifest / 环境前置（exit 2 + SPEC_INCOMPLETE）
# --------------------------------------------------------------------------- #


def test_missing_manifest_key_is_usage_error(drv, isolated_repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_CONTRACT_RUN_ID", "pytest-l3-missing-key")
    manifest = _test_manifest("pytest-l3-missing-key")
    del manifest["model"]
    with pytest.raises(drv.vl.UsageError) as excinfo:
        drv.run_l3(manifest_path=_write_manifest(tmp_path, manifest))
    assert "model" in str(excinfo.value)


def test_missing_manifest_key_cli_is_exit_2_with_marker(
    drv, isolated_repo, tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("AGENT_CONTRACT_RUN_ID", "pytest-l3-missing-key-cli")
    manifest = _test_manifest("pytest-l3-missing-key-cli")
    del manifest["provider"]
    path = _write_manifest(tmp_path, manifest)
    assert drv.main(["--run-manifest", str(path)]) == EXIT_USAGE
    captured = capsys.readouterr()
    assert "SPEC_INCOMPLETE" in captured.err
    assert "Traceback" not in captured.err


def test_run_id_mismatch_is_rejected(drv, isolated_repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_CONTRACT_RUN_ID", "another-run")
    manifest = _test_manifest("pytest-l3-mismatch")
    with pytest.raises(drv.vl.UsageError) as excinfo:
        drv.run_l3(manifest_path=_write_manifest(tmp_path, manifest))
    assert "EVD-RUN-001" in str(excinfo.value)


def test_run_id_mismatch_cli_is_exit_2_with_marker(
    drv, isolated_repo, tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("AGENT_CONTRACT_RUN_ID", "another-run")
    path = _write_manifest(tmp_path, _test_manifest("pytest-l3-mismatch-cli"))
    assert drv.main(["--run-manifest", str(path)]) == EXIT_USAGE
    captured = capsys.readouterr()
    assert "SPEC_INCOMPLETE" in captured.err
    assert "EVD-RUN-001" in captured.err


def test_non_observe_mode_is_rejected(drv, isolated_repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_CONTRACT_RUN_ID", "pytest-l3-mode")
    monkeypatch.setenv("AGENT_CONTRACT_MODE", "off")
    with pytest.raises(drv.vl.UsageError) as excinfo:
        drv.run_l3(manifest_path=_write_manifest(tmp_path, _test_manifest("pytest-l3-mode")))
    assert "FND-MODE-001" in str(excinfo.value)


def test_null_commit_requires_commit_env(drv, isolated_repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_CONTRACT_RUN_ID", "pytest-l3-commit")
    monkeypatch.delenv("AGENT_CONTRACT_COMMIT", raising=False)
    manifest = _test_manifest("pytest-l3-commit", repository_commit=None)
    with pytest.raises(drv.vl.UsageError) as excinfo:
        drv.run_l3(manifest_path=_write_manifest(tmp_path, manifest))
    assert "AGENT_CONTRACT_COMMIT" in str(excinfo.value)


def test_declared_commit_is_used_verbatim(drv, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_CONTRACT_MODE", "observe")
    monkeypatch.setenv("AGENT_CONTRACT_RUN_ID", "pytest-l3-commit2")
    assert drv.preflight(_test_manifest("pytest-l3-commit2")) == (
        "pytest-l3-commit2",
        COMMIT,
    )


# --------------------------------------------------------------------------- #
# 3. case 选择（B3）
# --------------------------------------------------------------------------- #


def test_missing_case_id_exits_2_with_spec_incomplete(
    drv, isolated_repo, tmp_path, monkeypatch, capsys
) -> None:
    run_id = "pytest-l3-case-missing"
    monkeypatch.setenv("AGENT_CONTRACT_RUN_ID", run_id)
    manifest_path = _write_manifest(tmp_path, _test_manifest(run_id))
    source = tmp_path / "other-bench.jsonl"
    source.write_text(
        json.dumps({"id": "character_complex_001", "question": "别的题"}) + "\n",
        encoding="utf-8",
    )
    exit_code = drv.main(
        ["--run-manifest", str(manifest_path), "--case-source", str(source)]
    )
    assert exit_code == EXIT_USAGE
    captured = capsys.readouterr()
    assert "SPEC_INCOMPLETE" in captured.err
    assert REGISTERED_CASE_ID in captured.err
    # 绝不静默换题：staging 里不能留下任何投影 bench。
    assert not list((isolated_repo / "output").rglob("bench-selected.jsonl"))


def test_default_case_source_is_a_repo_bench_containing_the_registered_id(drv) -> None:
    """缺省 case source 必须是仓库内真实存在、且完整包含预登记 id 的文件。"""
    assert DEFAULT_CASE_SOURCE.is_file(), f"缺省 case source 不存在：{DEFAULT_CASE_SOURCE}"
    assert not (REPO_ROOT / "benchmarks" / "arknights_bench" / "questions.jsonl").exists(), (
        "runner 的缺省 bench 在本仓不存在，这正是需要 --case-source / 投影 bench 的原因"
    )
    assert REGISTERED_CASE_ID in drv.load_case_index(DEFAULT_CASE_SOURCE)


def test_case_selection_is_exactly_one_record_per_registered_id(
    drv, isolated_repo, tmp_path
) -> None:
    manifest = _test_manifest("pytest-l3-select", case_ids=[REGISTERED_CASE_ID])
    selected, source = drv.select_cases(manifest, isolated_repo, DEFAULT_CASE_SOURCE)
    assert [item["id"] for item in selected] == [REGISTERED_CASE_ID]
    assert source == DEFAULT_CASE_SOURCE

    run_root = isolated_repo / "output" / "contract-validation" / "staging" / "x"
    projected = drv.project_bench(run_root, selected)
    assert projected == run_root / "driver" / "bench-selected.jsonl"
    rows = [json.loads(line) for line in projected.read_text(encoding="utf-8").splitlines()]
    assert [row["id"] for row in rows] == [REGISTERED_CASE_ID]
    # 逐字段保留（judge 需要 answer_key / requires_tools）。
    assert rows[0] == drv.load_case_index(DEFAULT_CASE_SOURCE)[REGISTERED_CASE_ID]


def test_duplicate_registered_case_ids_are_rejected(drv, isolated_repo) -> None:
    manifest = _test_manifest("pytest-l3-dup", case_ids=[REGISTERED_CASE_ID, REGISTERED_CASE_ID])
    with pytest.raises(drv.vl.UsageError):
        drv.select_cases(manifest, isolated_repo, DEFAULT_CASE_SOURCE)


# --------------------------------------------------------------------------- #
# 4. 端到端：真 sink 写证据 → 驱动器写 run-summary → 真 gate 通过
# --------------------------------------------------------------------------- #


def test_synthetic_run_writes_valid_summary_and_gate_passes(drv, vl, synthetic_run, capsys) -> None:
    summary_path = synthetic_run["run_root"] / "run-summary.json"
    assert summary_path.is_file()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    # 8 个键，不多不少。
    assert set(summary) == set(vl.RUN_SUMMARY_KEYS)
    # 全部现场推导（不是硬编码）。
    assert summary["sink_failure_count"] == 0
    assert summary["rejected_records"] == []
    assert summary["actual_calls"] == 6
    assert summary["actual_tokens"] == 5 * (11 + 7) + 3
    assert summary["known_cost_components"] == 5
    assert summary["unknown_cost_components"] == 1
    assert isinstance(summary["duration_seconds"], float)
    assert summary["duration_seconds"] >= 0
    assert summary["producer_coverage"] == [
        {"producer_id": "wiki.agent.llm_usage", "mapping_stage": "chat_completion"},
        {"producer_id": "wiki.agent.llm_usage", "mapping_stage": "intent_rewrite"},
        {"producer_id": "wiki.eval.cost_log", "mapping_stage": "judge"},
        {"producer_id": "wiki.eval.cost_log", "mapping_stage": "runner"},
        {"producer_id": "wiki.eval.cost_log", "mapping_stage": "scoring"},
        {"producer_id": "wiki.eval.cost_summary", "mapping_stage": "cost_log_summary"},
    ]
    # producer_coverage 与 gate 算出的 (producer_id, mapping_stage) 集合一一对应。
    events = drv.load_published_events(synthetic_run["run_root"])
    assert {
        (item["producer_id"], item["mapping_stage"]) for item in summary["producer_coverage"]
    } == {(str(event["producer_id"]), str(event["mapping_stage"])) for event in events}

    # 驱动器自带的闭合校验（就是冻结的 gate）。
    assert [step.index for step in synthetic_run["outcome"].steps] == list(range(1, 9))

    # 再独立跑一次冻结的 gate CLI：必须 exit 0。
    assert (
        vl.main(["--gate", "smoke", "--run-manifest", str(synthetic_run["manifest_path"])])
        == EXIT_OK
    )
    captured = capsys.readouterr()
    assert "gate smoke PASSED" in captured.out

    # 业务输出落在 staging 内，且没有写任何 tracked 文件。
    out_dir = synthetic_run["run_root"] / "driver" / "out"
    assert (out_dir / "results_v1.jsonl").is_file()
    assert out_dir.is_relative_to(synthetic_run["run_root"])


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        ({"sink_failure_count": 1}, "EVD-SINK-003"),
        ({"rejected_records": ["11111111-2222-3333-4444-555555555555"]}, "被拒绝"),
        ({"duration_seconds": 99999}, "duration"),
    ],
)
def test_perturbed_summary_fails_gate(drv, vl, synthetic_run, patch, expected) -> None:
    summary_path = synthetic_run["run_root"] / "run-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update(patch)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(vl.GateFailure) as excinfo:
        vl.gate_smoke(synthetic_run["manifest_path"])
    assert expected in str(excinfo.value)

    exit_code = vl.main(
        ["--gate", "smoke", "--run-manifest", str(synthetic_run["manifest_path"])]
    )
    assert exit_code == EXIT_GATE_FAILED


def test_perturbed_summary_missing_key_fails_gate(drv, vl, synthetic_run) -> None:
    summary_path = synthetic_run["run_root"] / "run-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    del summary["actual_tokens"]
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(vl.GateFailure) as excinfo:
        vl.gate_smoke(synthetic_run["manifest_path"])
    assert "actual_tokens" in str(excinfo.value)


def test_previous_run_artifacts_are_cleared(drv, vl, synthetic_run, monkeypatch, fixture_business) -> None:
    """同一 run_id 重跑必须清掉旧证据，否则失败的重跑会看起来"闭合"。"""
    run_root = synthetic_run["run_root"]
    stale_event = run_root / "events" / "11111111-2222-3333-4444-555555555555.json"
    stale_event.write_text("{}", encoding="utf-8")
    (run_root / "run-summary.json").write_text('{"sink_failure_count": 0}', encoding="utf-8")

    drv.run_l3(manifest_path=synthetic_run["manifest_path"])
    assert not stale_event.exists()
    summary = json.loads((run_root / "run-summary.json").read_text(encoding="utf-8"))
    assert set(summary) == set(vl.RUN_SUMMARY_KEYS)


# --------------------------------------------------------------------------- #
# 5. 业务路径失败 / 未预期错误（exit 1 / exit 2，均带标记且无 traceback）
# --------------------------------------------------------------------------- #


def test_business_failure_exits_1_with_marker_and_no_summary(
    drv, isolated_repo, tmp_path, monkeypatch, capsys
) -> None:
    run_id = "pytest-l3-business-fail"
    monkeypatch.setenv("AGENT_CONTRACT_RUN_ID", run_id)
    manifest_path = _write_manifest(tmp_path, _test_manifest(run_id))
    monkeypatch.setattr(
        drv, "_default_command_factory", lambda bench, out: [sys.executable, "-c", "raise SystemExit(3)"]
    )
    assert drv.main(["--run-manifest", str(manifest_path)]) == EXIT_GATE_FAILED
    captured = capsys.readouterr()
    assert "SPEC_STATUS_CONFLICT" in captured.err
    assert "Traceback" not in captured.err
    assert not (isolated_repo / "output" / "contract-validation" / "staging" / run_id / "run-summary.json").exists()


def test_business_timeout_exits_1(drv, isolated_repo, tmp_path, monkeypatch, capsys) -> None:
    run_id = "pytest-l3-timeout"
    monkeypatch.setenv("AGENT_CONTRACT_RUN_ID", run_id)
    manifest = _test_manifest(run_id, timeout_seconds=1)
    manifest_path = _write_manifest(tmp_path, manifest)
    monkeypatch.setattr(
        drv,
        "_default_command_factory",
        lambda bench, out: [
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        ],
    )
    assert drv.main(["--run-manifest", str(manifest_path)]) == EXIT_GATE_FAILED
    captured = capsys.readouterr()
    assert "SPEC_STATUS_CONFLICT" in captured.err
    assert "超时" in captured.err


def test_no_events_is_gate_failure(drv, isolated_repo, tmp_path, monkeypatch, capsys) -> None:
    """observe 下 0 条事件 = wiring/身份绑定失效，绝不能算通过。"""
    run_id = "pytest-l3-no-events"
    monkeypatch.setenv("AGENT_CONTRACT_RUN_ID", run_id)
    manifest_path = _write_manifest(tmp_path, _test_manifest(run_id))
    monkeypatch.setattr(
        drv, "_default_command_factory", lambda bench, out: [sys.executable, "-c", "pass"]
    )
    assert drv.main(["--run-manifest", str(manifest_path)]) == EXIT_GATE_FAILED
    assert "SPEC_STATUS_CONFLICT" in capsys.readouterr().err


def test_unexpected_error_is_exit_2_without_traceback(drv, isolated_repo, tmp_path, monkeypatch, capsys) -> None:
    run_id = "pytest-l3-unexpected"
    monkeypatch.setenv("AGENT_CONTRACT_RUN_ID", run_id)
    manifest_path = _write_manifest(tmp_path, _test_manifest(run_id))

    def _boom(*args, **kwargs):
        raise RuntimeError("injected internal failure")

    monkeypatch.setattr(drv, "run_l3", _boom)
    assert drv.main(["--run-manifest", str(manifest_path)]) == EXIT_USAGE
    captured = capsys.readouterr()
    assert "SPEC_INCOMPLETE" in captured.err
    assert "Traceback" not in captured.err
    assert "injected internal failure" in captured.err


def test_usage_error_has_marker_without_run_manifest(drv, capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        drv.main([])
    assert excinfo.value.code == EXIT_USAGE
    assert "SPEC_INCOMPLETE" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# 6. 业务命令形状（冻结：runner / direct / 单 worker / 仓库相对路径）
# --------------------------------------------------------------------------- #


def test_default_business_command_shape(drv) -> None:
    command = drv._default_command_factory(Path("out/bench.jsonl"), Path("out/out"))
    assert command[1:3] == ["-m", "arknights_wiki.eval.runner"]
    assert command[command.index("--mode") + 1] == "direct"
    assert command[command.index("--workers") + 1] == "1"
    assert command[command.index("--bench") + 1] == "out/bench.jsonl"
    assert command[command.index("--out") + 1] == "out/out"


# --------------------------------------------------------------------------- #
# 7. sink 失败标记（A2 / G-04）
# --------------------------------------------------------------------------- #


def test_sink_failure_marker_written_on_failing_emit(tmp_path) -> None:
    from agent_core.contracts.protocols.evidence_sink import SinkFailure

    from arknights_wiki.adapters.foundation.evidence_sink import (
        SINK_FAILURES_FILENAME,
        FileEvidenceSink,
    )

    sink = FileEvidenceSink(tmp_path)
    marker = tmp_path / "run-1" / SINK_FAILURES_FILENAME
    assert not marker.exists(), "零失败时不得出现标记文件"

    with pytest.raises(SinkFailure):
        sink.emit(type("Rogue", (), {"run_id": "run-1", "event_id": "not-a-uuid"})())

    assert sink.sink_failure_count == 1
    assert marker.is_file()
    lines = [json.loads(line) for line in marker.read_text(encoding="utf-8").splitlines()]
    assert lines == [
        {"code": "evidence.invalid_run_id", "event_id": None, "run_id": "run-1"}
    ]


def test_sink_failure_marker_absent_when_nothing_fails(drv, synthetic_run) -> None:
    from arknights_wiki.adapters.foundation.evidence_sink import SINK_FAILURES_FILENAME

    assert not (synthetic_run["run_root"] / SINK_FAILURES_FILENAME).exists()
    assert synthetic_run["outcome"].run_summary["sink_failure_count"] == 0


def test_sink_failure_marker_makes_the_gate_fail(drv, vl, synthetic_run, tmp_path) -> None:
    """端到端把 sink 失败标记与 run-summary 串起来：标记 → gate 失败。"""
    from arknights_wiki.adapters.foundation.evidence_sink import SINK_FAILURES_FILENAME

    event_id = "11111111-2222-3333-4444-555555555555"
    (synthetic_run["run_root"] / SINK_FAILURES_FILENAME).write_text(
        json.dumps({"code": "evidence.sink_write_failed", "event_id": event_id, "run_id": synthetic_run["run_id"]})
        + "\n",
        encoding="utf-8",
    )
    count, rejected = drv.read_sink_failures(synthetic_run["run_root"])
    assert count == 1 and rejected == [event_id]

    summary_path = synthetic_run["run_root"] / "run-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["sink_failure_count"], summary["rejected_records"] = count, rejected
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    assert vl.main(["--gate", "smoke", "--run-manifest", str(synthetic_run["manifest_path"])]) == (
        EXIT_GATE_FAILED
    )


def test_sink_failure_marker_stays_inside_run_dir_on_unsafe_run_id(tmp_path) -> None:
    from agent_core.contracts.protocols.evidence_sink import SinkFailure

    from arknights_wiki.adapters.foundation.evidence_sink import (
        SINK_FAILURES_FILENAME,
        FileEvidenceSink,
    )

    sink = FileEvidenceSink(tmp_path)
    with pytest.raises(SinkFailure):
        sink.emit(type("Rogue", (), {"run_id": "../escape", "event_id": "x"})())
    assert sink.sink_failure_count == 1
    assert not (tmp_path.parent / "escape").exists()
    assert not list(tmp_path.rglob(SINK_FAILURES_FILENAME))
