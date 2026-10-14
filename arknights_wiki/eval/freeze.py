"""W11-α: BenchmarkSpec 冻结件（母 Spec §24 Benchmark Freeze and Quality Gate）。

职责单一（N-02）：计算并写出一次评测运行所需的**冻结元数据** —— corpus 哈希、有序 case IDs、
参考数据哈希、runner / judge / 模型 / 温度 / 提示词 / 聚合规则版本、预登记容差；并提供清单可复算校验。

本模块不参与任何评测逻辑，不改写结果文件，不发起任何外部调用。

设计约束：
- 预登记容差（`PREREGISTERED_TOLERANCES`）**必须在跑批前固化**；母 Spec §24 明文禁止事后决定容差。
  修改本表等于使既有基线失效，必须形成新的 `w11a-*` 版本目录并登记原因。
- 温度不是配置项而是代码常量，因此不读运行时配置，而是把已知常量显式登记，
  并对承载它们的文件做哈希 —— 二者任一变化都会被冻结校验捕获。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

#: 预登记容差（母 Spec §24）。任何修改都必须伴随新的 spec_version。
PREREGISTERED_TOLERANCES: dict = {
    "deterministic_metrics": "exact_match",
    "deterministic_metrics_list": ["tool_selection_accuracy", "task_completion"],
    "stochastic_metric_mean_delta_max": 0.03,
    "stochastic_per_case_agreement_min": 0.90,
    "judge_failure_rate_max": 0.05,
    "safety_violations_max": 0,
    "declared_at": "2026-10-12",
    "declared_by": "W11-α Spec §3.5（用户批准 2026-10-12）",
}

#: 聚合规则版本。口径变更（例如分母显式化）必须提升此版本。
AGGREGATION_RULES_VERSION = "w11a-1"

#: 温度是代码常量，不是配置项。
TEMPERATURE_POLICY: dict = {
    "agent_graph_default": 0.1,
    "agent_graph_extended": 0.3,
    "router": 0.1,
    "planner": 0.1,
    "simple_search": 0.3,
    "judge": 0.1,
}

MAX_TOKENS_POLICY: dict = {
    "agent_nodes": 4096,
    "judge": 4096,
}

#: 承载提示词/评分语义的文件 —— 其内容哈希是 "prompt/template version" 与 "judge/scoring version" 的落地形式。
PROMPT_SOURCES: tuple[str, ...] = (
    "arknights_wiki/agent/prompts.py",
    "arknights_wiki/agent/graph.py",
    "arknights_wiki/agent/router.py",
    "arknights_wiki/agent/planner.py",
    "arknights_wiki/agent/simple_search.py",
    "arknights_wiki/eval/judge.py",
    "arknights_wiki/eval/scoring.py",
    "arknights_wiki/eval/metrics.py",
)

#: 历史基线（不可与之直接比较）—— judge 身份已漂移。
HISTORICAL_BASELINE = {
    "artifact": "output/eval/report_v1_mimo.md",
    "judge_model": "mimo-v2.5",
    "overall": 0.857,
    "comparable": False,
    "reason": "judge 身份漂移：历史基线用 mimo-v2.5（旧 opencode 网关，当前返回 HTTP 400），"
              "现默认 judge 已收敛到与 agent 相同的统一 provider 模型；两者不同源。",
}

_PROVIDER_BY_HOST = {
    "api.commandcode.ai": "command_goat",
    "api.deepseek.com": "deepseek",
    "opencode.ai": "opencode_go",
    "ark.cn-beijing.volces.com": "volcengine_ark",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return sha256_bytes(p.read_bytes())


def canonical_jsonl_sha256(path: Path | str) -> str:
    """逐行解析 JSON 后按 canonical 形式重算哈希。

    这样哈希对缩进/键序/行尾差异免疫，但对**内容与顺序**敏感 —— 正是 "corpus hash" 需要的语义。
    """
    p = Path(path)
    if not p.exists():
        return ""
    canon_lines: list[str] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        canon_lines.append(
            json.dumps(json.loads(raw), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        )
    return sha256_bytes("\n".join(canon_lines).encode("utf-8"))


def corpus_manifest(bench_path: Path | str) -> dict:
    """语料清单：canonical 哈希 + 有序 case IDs + 类别计数。"""
    p = Path(bench_path)
    items = [
        json.loads(line)
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    counts: dict[str, int] = {}
    for it in items:
        cat = it.get("category", "")
        counts[cat] = counts.get(cat, 0) + 1
    return {
        "path": str(p),
        "corpus_sha256": canonical_jsonl_sha256(p),
        "case_ids": [it.get("id", "") for it in items],
        "case_count": len(items),
        "category_counts": counts,
    }


def materials_hashes(materials_dir: Path | str) -> dict:
    """参考数据（题目的 material_refs 依据）逐文件哈希。"""
    d = Path(materials_dir)
    if not d.exists():
        return {}
    return {
        f.name: sha256_file(f)
        for f in sorted(d.glob("*.json"))
    }


def prompt_hashes(root: Path | str) -> dict:
    root = Path(root)
    out: dict[str, str] = {}
    for rel in PROMPT_SOURCES:
        p = root / rel
        if p.exists():
            out[rel] = sha256_file(p)
    return out


def _git(root: Path | str, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return (proc.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def harness_commit(root: Path | str) -> str:
    return _git(root, "rev-parse", "HEAD") or "unknown"


def harness_branch(root: Path | str) -> str:
    return _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "unknown"


def provider_label(base_url: str | None) -> str:
    host = (base_url or "").split("/")[2] if base_url and "//" in base_url else ""
    return _PROVIDER_BY_HOST.get(host, host or "unknown")


def model_identity() -> dict:
    """agent 与 judge 的模型/provider 身份（绝不返回 API key）。

    judge 与 agent 同模型是**已知限制**：会引入自评偏差，必须在报告中显式声明。
    """
    from arknights_wiki.eval import config as eval_config

    agent_model = agent_base = ""
    try:
        from arknights_wiki.extraction.llm_client import _get_model_config

        cfg = _get_model_config()
        agent_model = cfg.get("model", "")
        agent_base = cfg.get("base_url", "")
    except Exception:  # noqa: BLE001
        pass

    judge_model = eval_config.get_judge_model()
    try:
        judge_base = eval_config.get_opencode_go_base()
    except Exception:  # noqa: BLE001
        judge_base = ""

    return {
        "agent_model": agent_model,
        "agent_provider": provider_label(agent_base),
        "agent_base_host": (agent_base.split("/")[2] if agent_base else ""),
        "judge_model": judge_model,
        "judge_provider": provider_label(judge_base),
        "judge_base_host": (judge_base.split("/")[2] if judge_base else ""),
        "judge_is_same_as_agent": bool(judge_model and judge_model == agent_model),
    }


def build_benchmark_spec(
    bench_path: Path | str,
    materials_dir: Path | str,
    root: Path | str,
) -> dict:
    """构造完整 BenchmarkSpec（母 Spec §24 的 Wiki 10 项字段一一对应）。"""
    corpus = corpus_manifest(bench_path)
    return {
        "spec_version": "w11a-1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "harness": {
            "commit": harness_commit(root),
            "branch": harness_branch(root),
            #: runner version = harness commit（写入每个结果行与报告头）
        },
        "corpus": corpus,
        "materials": materials_hashes(materials_dir),
        #: 参考数据所在目录：冻结副本旁边**没有** materials/，校验必须回到这里
        "materials_dir": str(Path(materials_dir)),
        "prompt_hashes": prompt_hashes(root),
        "models": model_identity(),
        "temperature_policy": dict(TEMPERATURE_POLICY),
        "max_tokens_policy": dict(MAX_TOKENS_POLICY),
        "aggregation_rules_version": AGGREGATION_RULES_VERSION,
        "preregistered_tolerances": dict(PREREGISTERED_TOLERANCES),
        "historical_baseline": dict(HISTORICAL_BASELINE),
    }


def write_benchmark_spec(path: Path | str, spec: dict) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def load_benchmark_spec(path: Path | str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _default_repo_root(spec_path: Path | str) -> Path:
    """推断仓库根（W11-α 评审修复）。

    此前默认取 `spec_path.resolve().parents[2]`；对真实冻结件
    `benchmarks/arknights_bench/frozen/<ver>/MANIFEST.json` 会算成 `benchmarks/arknights_bench`
    ⇒ 全部 prompt_hashes 解析到不存在的路径、**自校验假失败**；只有显式传 `root=`.` 才通过。
    这类「默认参数下静默失败、加个隐藏参数就通过」正是本窗口反复踩的坑，故改为向上寻找仓库根。
    """
    start = Path(spec_path).resolve()
    for candidate in (start.parent, *start.parents):
        if (candidate / "arknights_wiki").is_dir() or (candidate / ".git").exists():
            return candidate
    return Path.cwd()


def verify_manifest(spec_path: Path | str, root: Path | str | None = None) -> tuple[bool, list[str]]:
    """校验冻结清单可复算：corpus 哈希、参考数据哈希、提示词哈希。

    返回 (是否全部一致, 差异说明列表)。文件缺失**不算**通过 —— 缺失即不可复算。
    """
    spec = load_benchmark_spec(spec_path)
    if spec is None:
        return False, [f"spec 不存在或不可解析: {spec_path}"]
    root = Path(root) if root else _default_repo_root(spec_path)
    problems: list[str] = []

    corpus = spec.get("corpus") or {}
    bench = Path(corpus.get("path", ""))
    if not bench.exists():
        problems.append(f"corpus 文件缺失: {bench}")
    else:
        got = canonical_jsonl_sha256(bench)
        if got != corpus.get("corpus_sha256"):
            problems.append(f"corpus_sha256 不一致: 期望 {corpus.get('corpus_sha256')} 实际 {got}")
        ids = [
            json.loads(line).get("id", "")
            for line in bench.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if ids != corpus.get("case_ids"):
            problems.append("case_ids 顺序或内容与冻结清单不一致")

    mat_hashes = spec.get("materials") or {}
    mat_dir = Path(spec.get("materials_dir") or (Path(bench).parent / "materials"))
    if mat_hashes and not mat_dir.is_dir():
        problems.append(f"materials 目录缺失: {mat_dir}")
    else:
        for name, want in mat_hashes.items():
            got = sha256_file(mat_dir / name)
            if got != want:
                problems.append(f"materials/{name} 哈希不一致")

    for rel, want in (spec.get("prompt_hashes") or {}).items():
        got = sha256_file(Path(root) / rel)
        if got != want:
            problems.append(f"{rel} 哈希不一致（提示词/评分语义已变更，基线需重建）")

    return (not problems), problems
