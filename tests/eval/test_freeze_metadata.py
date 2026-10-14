"""W11-α：BenchmarkSpec 冻结件与显式覆盖率口径的测试（母 Spec §24）。

覆盖三件事：
1. corpus 哈希语义 —— 对格式免疫、对内容与顺序敏感；
2. BenchmarkSpec 的 §24 字段齐全且可复算（`verify_manifest`），漂移必须被发现；
3. 覆盖率口径 —— judge 失败与 null 指标必须可见，分母不得静默漂移。

注：本文件**不使用 pytest 的 `tmp_path`**：在受限文件沙箱下 pytest 无法在系统临时目录建目录
（WinError 5）。改用自管理的仓库内临时目录 `output/_w11_probe/tmp/`。
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from arknights_wiki.eval import freeze
from arknights_wiki.eval.metrics import aggregate
from arknights_wiki.eval.report import generate_report

TMP_ROOT = Path(__file__).resolve().parents[2] / "output" / "_w11_probe" / "tmp"


@pytest.fixture()
def workdir():
    """仓库内自管理临时目录（避开沙箱对系统 temp 的限制）。

    注意：**不能用 `tempfile.mkdtemp`** —— 本机受限文件沙箱下，mkdtemp 创建出来的目录
    不可写（Errno 13），而 `Path.mkdir` 创建的目录可写。因此这里用 mkdir + 唯一目录名。
    """
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    d = TMP_ROOT / f"case_{uuid.uuid4().hex[:10]}"
    d.mkdir(parents=True, exist_ok=True)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _write_jsonl(path, items):
    path.write_text(
        "\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n",
        encoding="utf-8",
    )
    return path


SAMPLE = [
    {"id": "q1", "question": "问题一", "category": "character"},
    {"id": "q2", "question": "问题二", "category": "event"},
    {"id": "q3", "question": "问题三", "category": "event"},
]


class TestCorpusHash:
    def test_format_insensitive_but_content_sensitive(self, workdir):
        a = _write_jsonl(workdir / "a.jsonl", SAMPLE)
        # 同样的内容、不同的键序/缩进 → 同一哈希
        b = workdir / "b.jsonl"
        b.write_text(
            "\n".join(json.dumps(i, ensure_ascii=False, sort_keys=True) for i in SAMPLE) + "\n",
            encoding="utf-8",
        )
        assert freeze.canonical_jsonl_sha256(a) == freeze.canonical_jsonl_sha256(b)

        # 内容变化 → 哈希变化
        changed = [dict(SAMPLE[0], question="问题一（改）")] + SAMPLE[1:]
        c = _write_jsonl(workdir / "c.jsonl", changed)
        assert freeze.canonical_jsonl_sha256(a) != freeze.canonical_jsonl_sha256(c)

    def test_order_sensitive(self, workdir):
        a = _write_jsonl(workdir / "a.jsonl", SAMPLE)
        b = _write_jsonl(workdir / "b.jsonl", list(reversed(SAMPLE)))
        assert freeze.canonical_jsonl_sha256(a) != freeze.canonical_jsonl_sha256(b)

    def test_manifest_case_ids_ordered_and_counted(self, workdir):
        bench = _write_jsonl(workdir / "questions.jsonl", SAMPLE)
        manifest = freeze.corpus_manifest(bench)
        assert manifest["case_ids"] == ["q1", "q2", "q3"]
        assert manifest["case_count"] == 3
        assert manifest["category_counts"] == {"character": 1, "event": 2}


class TestBenchmarkSpec:
    def _root_with_prompt(self, workdir):
        rel = freeze.PROMPT_SOURCES[0]
        p = workdir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# prompt v1\n", encoding="utf-8")
        return workdir

    def test_section24_fields_present(self, workdir):
        root = self._root_with_prompt(workdir)
        bench = _write_jsonl(workdir / "questions.jsonl", SAMPLE)
        spec = freeze.build_benchmark_spec(bench, workdir / "materials", root)

        # 母 Spec §24 的 Wiki 十项字段一一对应
        assert spec["corpus"]["corpus_sha256"]
        assert spec["corpus"]["case_ids"]
        assert spec["harness"]["commit"]
        assert spec["models"]["judge_model"]
        assert spec["temperature_policy"]
        assert spec["prompt_hashes"]
        assert spec["aggregation_rules_version"]
        assert spec["preregistered_tolerances"]["safety_violations_max"] == 0
        assert spec["historical_baseline"]["comparable"] is False

    def test_verify_manifest_ok_then_detects_drift(self, workdir):
        root = self._root_with_prompt(workdir)
        bench = _write_jsonl(workdir / "questions.jsonl", SAMPLE)
        spec_path = workdir / "benchmark-spec.json"
        freeze.write_benchmark_spec(
            spec_path, freeze.build_benchmark_spec(bench, workdir / "materials", root)
        )

        ok, problems = freeze.verify_manifest(spec_path, root=root)
        assert ok, problems

        # 语料漂移 → 必须被发现
        _write_jsonl(bench, SAMPLE[:-1])
        ok, problems = freeze.verify_manifest(spec_path, root=root)
        assert not ok
        assert any("corpus_sha256" in p or "case_ids" in p for p in problems)

    def test_verify_manifest_detects_prompt_drift(self, workdir):
        root = self._root_with_prompt(workdir)
        bench = _write_jsonl(workdir / "questions.jsonl", SAMPLE)
        spec_path = workdir / "benchmark-spec.json"
        freeze.write_benchmark_spec(
            spec_path, freeze.build_benchmark_spec(bench, workdir / "materials", root)
        )

        (root / freeze.PROMPT_SOURCES[0]).write_text("# prompt v2\n", encoding="utf-8")
        ok, problems = freeze.verify_manifest(spec_path, root=root)
        assert not ok
        assert any("提示词/评分语义已变更" in p for p in problems)

    def test_verify_manifest_resolves_materials_from_recorded_dir(self, workdir):
        """回归：冻结副本旁边没有 materials/，校验必须按记录的 materials_dir 去找。

        首次真实冻结时此校验报了 7 个「materials/*.json 哈希不一致」——因为校验端
        默认在冻结文件旁边找 materials/。自校验没有空转，正是它挡住了这次冻结。
        """
        root = self._root_with_prompt(workdir)
        mats = workdir / "materials"
        mats.mkdir(parents=True, exist_ok=True)
        (mats / "character.json").write_text('[{"name": "测试"}]', encoding="utf-8")
        bench = _write_jsonl(workdir / "questions.jsonl", SAMPLE)

        frozen_dir = workdir / "frozen" / "v1"
        frozen_dir.mkdir(parents=True, exist_ok=True)
        frozen_bench = _write_jsonl(frozen_dir / "questions.jsonl", SAMPLE)
        spec_path = frozen_dir / "MANIFEST.json"
        freeze.write_benchmark_spec(
            spec_path, freeze.build_benchmark_spec(frozen_bench, mats, root)
        )

        # 冻结副本旁边确实没有 materials/
        assert not (frozen_dir / "materials").exists()
        ok, problems = freeze.verify_manifest(spec_path, root=root)
        assert ok, problems

        # 内容漂移仍必须被发现
        (mats / "character.json").write_text('[{"name": "改了"}]', encoding="utf-8")
        ok, problems = freeze.verify_manifest(spec_path, root=root)
        assert not ok
        assert any("materials/character.json" in p for p in problems)

    def test_default_root_resolves_repo_root(self, workdir):
        """回归（W11-α 评审）：不传 root 时也必须推断出仓库根。

        此前默认 `parents[2]` 会把 `benchmarks/arknights_bench/frozen/<ver>/MANIFEST.json`
        算成 `benchmarks/arknights_bench` ⇒ 全部 prompt_hashes 解析失败、自校验**假失败**；
        只有显式传 root 才通过。Plan 里那条验证命令正是默认调用 —— 也就是说当时它是坏的。
        """
        repo_root = Path(__file__).resolve().parents[2]
        bench = _write_jsonl(workdir / "questions.jsonl", SAMPLE)
        frozen = workdir / "frozen" / "v1"
        frozen.mkdir(parents=True, exist_ok=True)
        spec_path = frozen / "MANIFEST.json"
        freeze.write_benchmark_spec(
            spec_path, freeze.build_benchmark_spec(bench, workdir / "materials", repo_root)
        )

        ok, problems = freeze.verify_manifest(spec_path)  # 不传 root
        assert ok, problems

    def test_missing_corpus_is_not_pass(self, workdir):
        root = self._root_with_prompt(workdir)
        bench = _write_jsonl(workdir / "questions.jsonl", SAMPLE)
        spec_path = workdir / "benchmark-spec.json"
        freeze.write_benchmark_spec(
            spec_path, freeze.build_benchmark_spec(bench, workdir / "materials", root)
        )
        bench.unlink()
        ok, problems = freeze.verify_manifest(spec_path, root=root)
        assert not ok, "文件缺失不得被判为可复算"
        assert any("缺失" in p for p in problems)


def _row(rid, mode, category, judge=None, metrics=None):
    return {
        "id": rid,
        "mode": mode,
        "category": category,
        "judge": judge or {},
        "metrics": metrics or {},
    }


class TestCoverageDenominator:
    def test_judge_failure_counted_and_excluded(self):
        rows = [
            _row("a", "direct", "character", judge={"answer_correctness": 0.8, "hallucination": 0}),
            _row("b", "direct", "character", judge={"judge_error": True, "reason": "judge 调用失败"}),
        ]
        agg = aggregate(rows)
        cov = agg["coverage"]
        assert cov["rows"] == 2
        assert cov["judge_failure_count"] == 1
        # 失败行不进入均值：只有 a 的值参与（0.8），而不是被拉成 0.4
        assert agg["by_mode"]["direct"]["metrics"]["answer_correctness"] == 0.8
        assert cov["metric_null_count"]["answer_correctness"] == 1

    def test_deepeval_error_field_counted(self):
        rows = [_row("a", "direct", "event", judge={"error": "LLM 调用失败（3 次尝试）"})]
        agg = aggregate(rows)
        assert agg["coverage"]["judge_failure_count"] == 1

    def test_per_mode_coverage_present(self):
        rows = [_row("a", "direct", "character"), _row("b", "http", "character")]
        agg = aggregate(rows)
        assert agg["by_mode"]["direct"]["coverage"]["rows"] == 1
        assert agg["by_mode"]["http"]["coverage"]["rows"] == 1


class TestReportMetadata:
    def test_metadata_block_and_coverage_rendered(self, workdir):
        results = _write_jsonl(
            workdir / "results_v1.jsonl",
            [
                {
                    "id": "q1",
                    "mode": "direct",
                    "category": "character",
                    "question": "问题",
                    "answer": "答案" * 20,
                    "judge": {"answer_correctness": 0.9, "hallucination": 0},
                    "metrics": {"tool_selection_accuracy": 1.0, "task_completion": 1.0},
                }
            ],
        )
        spec = {
            "spec_version": "w11a-test",
            "aggregation_rules_version": freeze.AGGREGATION_RULES_VERSION,
            "harness": {"commit": "deadbeef", "branch": "test"},
            "corpus": {"case_count": 1, "corpus_sha256": "f" * 64},
            "models": {
                "agent_model": "deepseek/deepseek-v4.1-flash",
                "agent_provider": "command_goat",
                "judge_model": "deepseek/deepseek-v4.1-flash",
                "judge_provider": "command_goat",
                "judge_is_same_as_agent": True,
            },
            "temperature_policy": freeze.TEMPERATURE_POLICY,
            "max_tokens_policy": freeze.MAX_TOKENS_POLICY,
            "preregistered_tolerances": freeze.PREREGISTERED_TOLERANCES,
            "historical_baseline": freeze.HISTORICAL_BASELINE,
        }
        path = generate_report(results, workdir, spec=spec)
        text = path.read_text(encoding="utf-8")

        assert "冻结元数据" in text
        assert "deadbeef" in text
        assert "自评" in text
        assert "与历史基线不可比" in text
        assert "覆盖率与失败" in text
        header = text.split("## 一、")[0]
        # 硬编码的"当前 judge"说明必须消失（旧常量无条件写着 opencode zen/go 网关 mimo-v2.5）
        assert "opencode zen/go 网关 mimo-v2.5" not in header
        # 而"与历史基线不可比"的声明是数据驱动的，必须保留
        assert "mimo-v2.5" in header

    def test_report_without_spec_is_marked_unusable(self, workdir):
        results = _write_jsonl(
            workdir / "results_v1.jsonl",
            [{"id": "q1", "mode": "direct", "category": "character", "answer": "a", "judge": {}, "metrics": {}}],
        )
        text = generate_report(results, workdir).read_text(encoding="utf-8")
        assert "不可作为 Baseline 证据" in text


def test_preregistered_tolerances_are_declared():
    """容差必须在源码中固化（母 Spec §24：不得事后决定）。"""
    tol = freeze.PREREGISTERED_TOLERANCES
    assert tol["stochastic_metric_mean_delta_max"] == pytest.approx(0.03)
    assert tol["stochastic_per_case_agreement_min"] == pytest.approx(0.90)
    assert tol["judge_failure_rate_max"] == pytest.approx(0.05)
    assert tol["safety_violations_max"] == 0
    assert tol["declared_at"]
