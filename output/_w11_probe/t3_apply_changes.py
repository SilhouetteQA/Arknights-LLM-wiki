#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T3 变更脚本：为「基准可比性元信息」补齐最小测量仪表（幂等 + 原子）。

目标仓库（CODING，默认硬编码，可用 --repo 覆盖）：
    D:\\AI project\\Knowledge-Augmented Autonomous Coding Agent

改动范围（5 个文件，全部为「锚点精确匹配」式替换；不动执行语义）：
    benchmark/report.py        T3 元信息字段 + 渲染容忍 None 成本
    benchmark/runner.py        cost_usd 不再静默 0.0（None + cost_source）+ 真实执行器
    benchmark/loader.py        可选 repository_commit + 可选锁定文件
    tools/docker_sandbox.py    真实执行器记录/getter + 有效沙箱策略 dict
    main.py                    CLI 成本提示文案与 None 语义对齐
    tests/test_benchmark_metadata.py   （新建）

用法：
    python t3_apply_changes.py --check [--repo <path>]
    python t3_apply_changes.py --apply [--repo <path>]

实现约定：
  * 纯标准库；每个编辑是一个 (old, new) 精确锚点对，要求 old 在文件中恰好出现 1 次。
  * 先在内存里构建全部新内容（并对 Python 文件做 compile 预检），**全部成功才落盘**，
    任一失败则一个文件都不写（不会留下半改文件）。
  * 幂等：若某个编辑的 new 文本已在位 → 报「already applied」并跳过；重复 --apply
    不会重复追加、不会破坏文件。
  * 只新建文件，从不删除文件（新建文件已存在且内容不同时拒绝覆盖并报错）。
  * 任一锚点失败 → 退出码非 0。
"""
import argparse
import os
import sys

DEFAULT_REPO = r"D:\AI project\Knowledge-Augmented Autonomous Coding Agent"

#: 新建文件（相对路径 -> 内容），内容用原始字符串书写，保证逐字节精确
TEST_FILE_REL = "tests/test_benchmark_metadata.py"


def L(*lines):
    """把逐行书写的原文拼成精确文本（行内空格/中文原样保留，不 trim）。"""
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 1) benchmark/report.py
# ---------------------------------------------------------------------------

REPORT_EDITS = [
    # 1. 顶部导入 + T3 常量
    (
        L('"""评测报告：run metadata、JSON/Markdown 报告与多轮对比。"""',
          'import json',
          'import subprocess',
          'from dataclasses import asdict, dataclass, field',
          'from datetime import datetime'),
        L('"""评测报告：run metadata、JSON/Markdown 报告与多轮对比。"""',
          'import hashlib',
          'import json',
          'import os',
          'import subprocess',
          'from dataclasses import asdict, dataclass, field',
          'from datetime import datetime',
          '',
          '# T3：resolution 判定口径版本——判定语义/实现变化时必须递增，供跨轮报告比对。',
          'RESOLUTION_DEFINITION_VERSION = "t3-1"',
          '',
          '# T3：基准运行的副作用策略。核对依据（读码结论）：benchmark/runner.py 调用',
          '# run_issue_agent 时不传 approval_dir（默认 None）→ agent/issue.py 不生成审批单、',
          '# pr_url 恒为 None；远端写（push / 建 PR）的唯一入口是 main.py --approve →',
          '# tools.approval.approve_request → tools.github_tools.push_branch/',
          '# create_pull_request。该入口不在 benchmark 调用链上，故基准运行对被测仓库只读',
          '# （clone/sync/checkout 均为读操作）。',
          'SIDE_EFFECT_POLICY_READ_ONLY = "read_only"',
          '',
          '# T3：judge 提示词文本缓存（judge_prompt_sha256() 惰性取自 benchmark.judge）',
          '_JUDGE_PROMPT_CACHE = None'),
        "imports + T3 常量",
    ),
    # 2. RunMetadata 追加 T3 字段
    (
        L('    run_id: str',
          '    git_commit: str',
          '    branch: str',
          '    model: str',
          '    timestamp: str',
          '    executor: str',
          '    params: dict'),
        L('    run_id: str',
          '    git_commit: str',
          '    branch: str',
          '    model: str',
          '    timestamp: str',
          '    executor: str',
          '    params: dict',
          '    # T3（可比性元信息）：以下字段全部带默认值，保证旧 report.json 仍可',
          '    # RunMetadata(**data["metadata"]) 反序列化（main.py --compare 路径）。',
          '    provider: str = ""                  # 供应商名（agent.llm 解析结果）',
          '    base_url: str = ""                  # 实际端点（llm.base_url）',
          '    temperature: float | None = None    # 采样温度；未配置记 None（当前 chat 不传该参数）',
          '    max_tokens: int | None = None       # 输出上限；未配置记 None',
          '    executor_actual: str = ""           # 真实创建的执行器（tools.docker_sandbox 记录）',
          '    sandbox_policy: dict = field(default_factory=dict)   # image/cpus/memory/pids/network',
          '    iteration_limits: dict = field(default_factory=dict) # 逐 case 迭代上限 + run 级兜底',
          '    timeouts: dict = field(default_factory=dict)         # 生效的 KA_* 超时/重试 env',
          '    resolution_definition_version: str = RESOLUTION_DEFINITION_VERSION',
          '    side_effect_policy: str = SIDE_EFFECT_POLICY_READ_ONLY',
          '    judge_prompt_sha256: str = ""       # judge 提示词 sha256（判定可比性）'),
        "RunMetadata 追加 T3 字段",
    ),
    # 3. CaseResult.cost_usd 允许 None
    (
        L('    tokens_prompt: int',
          '    tokens_completion: int',
          '    cost_usd: float',
          '    diff: str'),
        L('    tokens_prompt: int',
          '    tokens_completion: int',
          '    # T3：单价未知时为 None（此前静默填 0.0，会被下游误读为“真实零成本”）',
          '    cost_usd: float | None',
          '    diff: str'),
        "CaseResult.cost_usd 允许 None",
    ),
    # 4. CaseResult 增加 cost_source
    (
        L('    errors: list[str] = field(default_factory=list)',
          '    test_error_summary: str = ""   # must_pass 失败摘要（判定阶段；无失败为空）'),
        L('    errors: list[str] = field(default_factory=list)',
          '    # T3：成本来源标记——computed（单价表命中并计算）/ unknown（无单价，cost_usd=None）',
          '    cost_source: str = "unknown"',
          '    test_error_summary: str = ""   # must_pass 失败摘要（判定阶段；无失败为空）'),
        "CaseResult 增加 cost_source",
    ),
    # 5. 渲染辅助：None 成本 -> unknown
    (
        L('def _truncate(text: str, limit: int) -> str:',
          '    """明细表格文本截断：超长保留前 limit 字符并追加省略号。"""',
          '    return text if len(text) <= limit else text[:limit] + "..."'),
        L('def _truncate(text: str, limit: int) -> str:',
          '    """明细表格文本截断：超长保留前 limit 字符并追加省略号。"""',
          '    return text if len(text) <= limit else text[:limit] + "..."',
          '',
          '',
          'def _fmt_cost(cost: float | None) -> str:',
          '    """成本渲染（T3）：None（单价未知）→ unknown，绝不做假零渲染。"""',
          '    return "unknown" if cost is None else f"{cost:.4f}"',
          '',
          '',
          'def _total_cost(report: "BenchmarkReport") -> str:',
          '    """总成本（T3）：任一 case 成本未知即标注 unknown，绝不把 None 当 0 求和。"""',
          '    known = [x.cost_usd for x in report.results if x.cost_usd is not None]',
          '    if not known:',
          '        return "unknown"',
          '    total = sum(known)',
          '    if len(known) < len(report.results):',
          '        return f"{total:.4f} (部分 unknown)"',
          '    return f"{total:.4f}"'),
        "新增 _fmt_cost / _total_cost 渲染辅助",
    ),
    # 6. T3 元信息采集函数（插在 current_metadata 之前）
    (
        L('def current_metadata(model: str, executor: str, **params) -> RunMetadata:'),
        L('def judge_prompt_sha256(judge_prompt: str | None = None) -> str:',
          '    """judge 提示词 sha256（T3）：默认取 benchmark.judge.JUDGE_PROMPT 真实文本。',
          '',
          '    惰性导入避免 report ↔ judge 的模块级耦合；导入失败（缺依赖）返回空串而非崩溃。',
          '    """',
          '    global _JUDGE_PROMPT_CACHE',
          '    text = judge_prompt',
          '    if text is None:',
          '        if _JUDGE_PROMPT_CACHE is None:',
          '            try:',
          '                from benchmark.judge import JUDGE_PROMPT',
          '                _JUDGE_PROMPT_CACHE = JUDGE_PROMPT',
          '            except Exception:  # noqa: BLE001 — 指纹缺失不阻塞报告',
          '                _JUDGE_PROMPT_CACHE = ""',
          '        text = _JUDGE_PROMPT_CACHE',
          '    return hashlib.sha256(text.encode("utf-8")).hexdigest()',
          '',
          '',
          'def _env_int(name: str, default: int) -> int:',
          '    """env 整数解析：未设/非法 → default。"""',
          '    raw = (os.environ.get(name) or "").strip()',
          '    try:',
          '        return int(raw) if raw else default',
          '    except ValueError:',
          '        return default',
          '',
          '',
          'def _env_float(name: str) -> float | None:',
          '    """env 浮点解析：未设/非法 → None。"""',
          '    raw = (os.environ.get(name) or "").strip()',
          '    if not raw:',
          '        return None',
          '    try:',
          '        return float(raw)',
          '    except ValueError:',
          '        return None',
          '',
          '',
          'def setup_timeout_s() -> int:',
          '    """setup_commands 生效超时秒数：KA_SETUP_TIMEOUT_S，缺省 60（与 runner 同源）。"""',
          '    return _env_int("KA_SETUP_TIMEOUT_S", 60)',
          '',
          '',
          'def llm_timeout_s() -> float | None:',
          '    """LLM 生效超时：KA_LLM_TIMEOUT_S（未设 → None = SDK 默认；非法 → 120.0）。"""',
          '    try:',
          '        from agent.llm import _env_timeout',
          '        return _env_timeout()',
          '    except Exception:  # noqa: BLE001 — 依赖缺失时退回原始 env 解析',
          '        return _env_float("KA_LLM_TIMEOUT_S")',
          '',
          '',
          'def llm_max_retries() -> int | None:',
          '    """LLM 生效重试：KA_LLM_MAX_RETRIES（未设 → None = SDK 默认；非法 → 2）。"""',
          '    try:',
          '        from agent.llm import _env_max_retries',
          '        return _env_max_retries()',
          '    except Exception:  # noqa: BLE001',
          '        raw = (os.environ.get("KA_LLM_MAX_RETRIES") or "").strip()',
          '        return _env_int("KA_LLM_MAX_RETRIES", 2) if raw else None',
          '',
          '',
          'def effective_timeouts() -> dict:',
          '    """生效超时/重试 env（T3）：值即运行期真实取值（含缺省规则）。"""',
          '    return {',
          '        "KA_SETUP_TIMEOUT_S": setup_timeout_s(),',
          '        "KA_LLM_TIMEOUT_S": llm_timeout_s(),',
          '        "KA_LLM_MAX_RETRIES": llm_max_retries(),',
          '    }',
          '',
          '',
          'def effective_iteration_limits(cases: list | None = None,',
          '                               run_level: int | None = None) -> dict:',
          '    """迭代上限（T3）：逐 case 的 max_iterations 优先，缺失时退回 run 级上限。"""',
          '    per_case: dict = {}',
          '    fallback: list = []',
          '    for c in cases or []:',
          '        cid = getattr(c, "id", "") or "?"',
          '        v = getattr(c, "max_iterations", None)',
          '        if isinstance(v, int) and not isinstance(v, bool) and v > 0:',
          '            per_case[cid] = v',
          '        else:',
          '            fallback.append(cid)',
          '            if isinstance(run_level, int) and not isinstance(run_level, bool):',
          '                per_case[cid] = run_level',
          '    return {"run_level": run_level, "per_case": per_case,',
          '            "fallback_to_run_level": sorted(fallback)}',
          '',
          '',
          'def actual_executor() -> str:',
          '    """真实创建的执行器名（T3）：tools.docker_sandbox 模块级记录；未创建 → ""。"""',
          '    try:',
          '        from tools.docker_sandbox import get_actual_executor',
          '        return get_actual_executor()',
          '    except Exception:  # noqa: BLE001 — 记录缺失不阻塞报告',
          '        return ""',
          '',
          '',
          'def effective_sandbox_policy() -> dict:',
          '    """有效沙箱策略 dict（T3）：image/cpus/memory/pids/network（docker_sandbox 提供）。"""',
          '    try:',
          '        from tools.docker_sandbox import get_effective_sandbox_policy',
          '        return get_effective_sandbox_policy()',
          '    except Exception:  # noqa: BLE001',
          '        return {}',
          '',
          '',
          'def llm_provider(llm: object | None = None) -> str:',
          '    """供应商名（T3）：llm.provider → agent.llm 解析 → KA_LLM_PROVIDER 原值。"""',
          '    prov = getattr(llm, "provider", None)',
          '    if prov:',
          '        return str(prov)',
          '    try:',
          '        from agent.llm import _resolve_provider_name',
          '        return _resolve_provider_name(os.environ)',
          '    except Exception:  # noqa: BLE001',
          '        return os.environ.get("KA_LLM_PROVIDER", "") or ""',
          '',
          '',
          'def enrich_run_metadata(meta: RunMetadata, llm: object | None = None,',
          '                        cases: list | None = None,',
          '                        run_max_iterations: int | None = None) -> RunMetadata:',
          '    """就地补齐 T3 可比性字段（只写新键，不改既有键与语义）。"""',
          '    meta.provider = llm_provider(llm)',
          '    meta.base_url = str(getattr(llm, "base_url", "") or "")',
          '    temp = getattr(llm, "temperature", None)',
          '    if isinstance(temp, (int, float)) and not isinstance(temp, bool):',
          '        meta.temperature = float(temp)',
          '    else:',
          '        meta.temperature = _env_float("KA_LLM_TEMPERATURE")',
          '    mt = getattr(llm, "max_tokens", None)',
          '    if isinstance(mt, int) and not isinstance(mt, bool):',
          '        meta.max_tokens = mt',
          '    else:',
          '        meta.max_tokens = _env_int("KA_LLM_MAX_TOKENS", 0) or None',
          '    meta.executor_actual = actual_executor() or meta.executor',
          '    meta.sandbox_policy = effective_sandbox_policy()',
          '    meta.iteration_limits = effective_iteration_limits(cases, run_max_iterations)',
          '    meta.timeouts = effective_timeouts()',
          '    meta.resolution_definition_version = RESOLUTION_DEFINITION_VERSION',
          '    meta.side_effect_policy = SIDE_EFFECT_POLICY_READ_ONLY',
          '    meta.judge_prompt_sha256 = judge_prompt_sha256()',
          '    return meta',
          '',
          '',
          'def current_metadata(model: str, executor: str, **params) -> RunMetadata:'),
        "新增 T3 元信息采集函数 + 保留 current_metadata",
    ),
    # 7. Markdown 头部输出 T3 元信息
    (
        L('        f"- timestamp: {m.timestamp}",',
          '        f"- params: {json.dumps(m.params, ensure_ascii=False)}",',
          '        "",'),
        L('        f"- timestamp: {m.timestamp}",',
          '        f"- params: {json.dumps(m.params, ensure_ascii=False)}",',
          '        f"- provider: `{m.provider}` | base_url: `{m.base_url}`",',
          '        f"- temperature: {m.temperature} | max_tokens: {m.max_tokens}",',
          '        f"- executor: 声明 `{m.executor}` / 实际 `{m.executor_actual}`",',
          '        f"- sandbox_policy: {json.dumps(m.sandbox_policy, ensure_ascii=False)}",',
          '        f"- iteration_limits: {json.dumps(m.iteration_limits, ensure_ascii=False)}",',
          '        f"- timeouts: {json.dumps(m.timeouts, ensure_ascii=False)}",',
          '        f"- resolution_definition_version: `{m.resolution_definition_version}`",',
          '        f"- side_effect_policy: `{m.side_effect_policy}`",',
          '        f"- judge_prompt_sha256: `{m.judge_prompt_sha256}`",',
          '        "",'),
        "report.md 输出 T3 元信息",
    ),
    # 8. 明细表成本列
    (
        L('            f"{r.cost_usd:.4f} | {summary} | "'),
        L('            f"{_fmt_cost(r.cost_usd)} | {summary} | "'),
        "明细表成本列容忍 None",
    ),
    # 9. compare 总成本行
    (
        L('        ("总成本($)",',
          '         lambda r: f"{sum(x.cost_usd for x in r.results):.4f}"),'),
        L('        ("总成本($)",',
          '         _total_cost),'),
        "compare 总成本容忍 None",
    ),
]

# ---------------------------------------------------------------------------
# 2) benchmark/runner.py
# ---------------------------------------------------------------------------

RUNNER_EDITS = [
    (
        L('# 模型单价表（每 1K token 的美元成本）；未知模型或空单价表 → cost_usd=0；CLI 摘要提示单价未知',
          'MODEL_PRICE_USD_PER_1K = {',
          '    # "mimo-v2.5": 0.004,   # 示例：每 1K token 美元（待用户提供实际单价）',
          '}'),
        L('# 模型单价表（每 1K token 的美元成本）；命中 → 计算值 + cost_source="computed"；',
          '# 未命中/空表 → cost_usd=None + cost_source="unknown"（T3：不再静默填 0.0——假零会被',
          '# 下游误读为“真实零成本”，使跨轮成本不可比）。',
          'MODEL_PRICE_USD_PER_1K = {',
          '    # "mimo-v2.5": 0.004,   # 示例：每 1K token 美元（待用户提供实际单价）',
          '}',
          '',
          '# T3：成本来源标记',
          'COST_SOURCE_COMPUTED = "computed"',
          'COST_SOURCE_UNKNOWN = "unknown"'),
        "单价表注释 + cost_source 常量",
    ),
    (
        L('def _cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:',
          '    """按单价表估算成本；未知模型返回 0.0。"""',
          '    price = MODEL_PRICE_USD_PER_1K.get(model)',
          '    if price is None:',
          '        return 0.0',
          '    return (prompt_tokens + completion_tokens) / 1000.0 * price'),
        L('def cost_for(model: str, prompt_tokens: int, completion_tokens: int',
          '             ) -> tuple[float | None, str]:',
          '    """按单价表估算成本（T3）：→ (cost_usd, cost_source)。',
          '',
          '    单价表未命中/空表 → (None, "unknown")；命中 → (计算值, "computed")。',
          '    未知成本必须显式为 None：0.0 会被下游当作“真实零成本”参与汇总与跨轮比较。',
          '    """',
          '    price = MODEL_PRICE_USD_PER_1K.get(model)',
          '    if price is None:',
          '        return None, COST_SOURCE_UNKNOWN',
          '    return (prompt_tokens + completion_tokens) / 1000.0 * price, COST_SOURCE_COMPUTED',
          '',
          '',
          'def _cost_usd(model: str, prompt_tokens: int, completion_tokens: int',
          '              ) -> float | None:',
          '    """历史薄包装（T3）：等价 cost_for(...)[0]；未知模型 → None（不再是 0.0）。"""',
          '    return cost_for(model, prompt_tokens, completion_tokens)[0]'),
        "cost_for + _cost_usd(None-safe)",
    ),
    (
        L('from benchmark.report import (BenchmarkReport, CaseResult, RunMetadata,',
          '                              current_metadata, save_json, save_markdown)'),
        L('from benchmark.report import (BenchmarkReport, CaseResult, RunMetadata,',
          '                              current_metadata, enrich_run_metadata, save_json,',
          '                              save_markdown, setup_timeout_s)'),
        "import 调整",
    ),
    (
        L('    with sandbox_executor(repo_dir):',
          '        setup_timeout = int(os.environ.get("KA_SETUP_TIMEOUT_S", "60"))'),
        L('    with sandbox_executor(repo_dir):',
          '        # T3：生效超时与报告 metadata.timeouts 同源（report.setup_timeout_s）',
          '        setup_timeout = setup_timeout_s()'),
        "setup 超时同源",
    ),
    (
        L('    return CaseResult(',
          '        case_id=case.id, category=case.category, status="environment_error",',
          '        resolution=False, test_pass=False, patch_acceptance=False,',
          '        judge_verdict="SKIP",',
          '        judge_reason="SKIP 基线测试失败（环境缺口，未运行 Agent）",',
          '        tool_success_rate=0.0, iteration_count=0,',
          '        latency_s=end - start,',
          '        tokens_prompt=llm.tokens_total["prompt"] - prompt_before,',
          '        tokens_completion=llm.tokens_total["completion"] - completion_before,',
          '        cost_usd=0.0, diff="",',
          '        errors=[f"基线测试失败: {summary}"])'),
        L('    # T3：成本与正常路径同口径（单价未知 → None/unknown，不填假零）',
          '    prompt = llm.tokens_total["prompt"] - prompt_before',
          '    completion = llm.tokens_total["completion"] - completion_before',
          '    cost, cost_source = cost_for(getattr(llm, "model", "unknown"), prompt, completion)',
          '    return CaseResult(',
          '        case_id=case.id, category=case.category, status="environment_error",',
          '        resolution=False, test_pass=False, patch_acceptance=False,',
          '        judge_verdict="SKIP",',
          '        judge_reason="SKIP 基线测试失败（环境缺口，未运行 Agent）",',
          '        tool_success_rate=0.0, iteration_count=0,',
          '        latency_s=end - start,',
          '        tokens_prompt=prompt,',
          '        tokens_completion=completion,',
          '        cost_usd=cost, cost_source=cost_source, diff="",',
          '        errors=[f"基线测试失败: {summary}"])'),
        "environment_error 成本",
    ),
    (
        L('    model = getattr(llm, "model", "unknown")',
          '    tool_success = _tool_success_rate(getattr(run, "steps", None) or [])'),
        L('    model = getattr(llm, "model", "unknown")',
          '    cost, cost_source = cost_for(model, prompt, completion)',
          '    tool_success = _tool_success_rate(getattr(run, "steps", None) or [])'),
        "正常路径成本计算",
    ),
    (
        L('        tokens_prompt=prompt, tokens_completion=completion,',
          '        cost_usd=_cost_usd(model, prompt, completion),',
          '        diff=diff, errors=errors,'),
        L('        tokens_prompt=prompt, tokens_completion=completion,',
          '        cost_usd=cost, cost_source=cost_source,',
          '        diff=diff, errors=errors,'),
        "CaseResult 成本 + 来源",
    ),
    (
        L('        result = CaseResult(',
          '            case_id=case.id, category=case.category, status="error",',
          '            resolution=False, test_pass=False, patch_acceptance=False,',
          '            judge_verdict="SKIP", judge_reason="SKIP 执行异常",',
          '            tool_success_rate=0.0, iteration_count=0,',
          '            latency_s=time.monotonic() - start,',
          '            tokens_prompt=llm.tokens_total["prompt"] - prompt_before,',
          '            tokens_completion=llm.tokens_total["completion"] - completion_before,',
          '            cost_usd=0.0, diff="", errors=[str(e)])'),
        L('        prompt = llm.tokens_total["prompt"] - prompt_before',
          '        completion = llm.tokens_total["completion"] - completion_before',
          '        cost, cost_source = cost_for(getattr(llm, "model", "unknown"),',
          '                                     prompt, completion)',
          '        result = CaseResult(',
          '            case_id=case.id, category=case.category, status="error",',
          '            resolution=False, test_pass=False, patch_acceptance=False,',
          '            judge_verdict="SKIP", judge_reason="SKIP 执行异常",',
          '            tool_success_rate=0.0, iteration_count=0,',
          '            latency_s=time.monotonic() - start,',
          '            tokens_prompt=prompt,',
          '            tokens_completion=completion,',
          '            cost_usd=cost, cost_source=cost_source, diff="", errors=[str(e)])'),
        "error 路径成本",
    ),
    (
        L('    metadata = current_metadata(getattr(llm, "model", "unknown"), executor)'),
        L('    # T3：除 git/时间戳外补齐可比性元信息（真实执行器 / 沙箱策略 / 超时 / 迭代上限 /',
          '    # judge 指纹等）。run_max_iterations=None：基准逐 case 自带 max_iterations',
          '    # （loader 保证），run 级上限仅在 case 给不出时作兜底。',
          '    metadata = enrich_run_metadata(',
          '        current_metadata(getattr(llm, "model", "unknown"), executor),',
          '        llm=llm, cases=cases, run_max_iterations=None)'),
        "runner 汇总时补齐 T3 元信息",
    ),
]

# ---------------------------------------------------------------------------
# 3) benchmark/loader.py
# ---------------------------------------------------------------------------

LOADER_EDITS = [
    (
        L('"""基准案例加载与 schema 校验。',
          '',
          '案例目录结构：',
          '    cases/<category>/<id>.json   （category ∈ bug/feature/test/refactor/domain）',
          '    cases/gold/<id>.diff         （社区已合并 PR 的 diff，gold patch）',
          '"""',
          'import json',
          'from dataclasses import dataclass, field',
          'from pathlib import Path'),
        L('"""基准案例加载与 schema 校验。',
          '',
          '案例目录结构：',
          '    cases/<category>/<id>.json   （category ∈ bug/feature/test/refactor/domain）',
          '    cases/gold/<id>.diff         （社区已合并 PR 的 diff，gold patch）',
          '',
          'T3 可选锁定：frozen/<version>/cases.lock.json（或 KA_BENCHMARK_CASES_LOCK 指定的',
          '路径）以 {case_id: repository_commit} 钉住被测仓库提交。文件不存在即视为未锁定',
          '（完全向后兼容）；存在时锁定值优先于 case 内联的 repository_commit。',
          '"""',
          'import json',
          'import os',
          'from dataclasses import dataclass, field',
          'from pathlib import Path'),
        "docstring + import os",
    ),
    (
        L('CATEGORIES = ("bug", "feature", "test", "refactor", "domain")'),
        L('CATEGORIES = ("bug", "feature", "test", "refactor", "domain")',
          '',
          '# T3：可选锁定文件（不要求存在）。路径优先级：load_cases 显式参数 >',
          '# KA_BENCHMARK_CASES_LOCK > <cases_dir 同级>/frozen/<version>/cases.lock.json',
          'LOCK_ENV_VAR = "KA_BENCHMARK_CASES_LOCK"',
          'FROZEN_VERSION_ENV_VAR = "KA_BENCHMARK_FROZEN_VERSION"',
          'FROZEN_VERSION_DEFAULT = "v1"'),
        "锁定文件常量",
    ),
    (
        L('    setup_commands: list[str] = field(default_factory=list)',
          '    # E10：交付一致性核查配置——期望动作（如 {"deletions": 5}），缺省空 dict 不核查',
          '    expected_actions: dict = field(default_factory=dict)'),
        L('    setup_commands: list[str] = field(default_factory=list)',
          '    # E10：交付一致性核查配置——期望动作（如 {"deletions": 5}），缺省空 dict 不核查',
          '    expected_actions: dict = field(default_factory=dict)',
          '    # T3：被测仓库钉住的提交（case 内联 repository_commit 或锁定文件给出）；',
          '    # 缺省空串 = 未钉住（沿用仓库默认分支 HEAD，与既有行为一致）',
          '    repository_commit: str = ""'),
        "BenchmarkCase.repository_commit 字段",
    ),
    (
        L('def _validate(data: dict, path: Path) -> BenchmarkCase:'),
        L('def _validate(data: dict, path: Path,',
          '              lock: dict[str, str] | None = None) -> BenchmarkCase:'),
        "_validate 接受 lock",
    ),
    (
        L('    return BenchmarkCase(',
          '        id=case_id, category=category, repository=repo,'),
        L('    # T3：repository_commit 可选——锁定文件优先（冻结基线不被 case 内联值覆盖），',
          '    # 其次 case 内联字段；两者皆无 → 空串（不钉住）。非字符串（null 除外）报错。',
          '    inline_commit = data.get("repository_commit", "")',
          '    if inline_commit is None:',
          '        inline_commit = ""',
          '    if not isinstance(inline_commit, str):',
          '        raise CaseError(f"{path.name}: repository_commit 须为字符串"',
          '                        f"（got {inline_commit!r}）")',
          '    pinned_commit = (lock or {}).get(case_id, "") or inline_commit',
          '    return BenchmarkCase(',
          '        id=case_id, category=category, repository=repo,'),
        "解析并钉住 repository_commit",
    ),
    (
        L('        setup_commands=list(setup),',
          '        expected_actions=dict(expected_actions),',
          '    )'),
        L('        setup_commands=list(setup),',
          '        expected_actions=dict(expected_actions),',
          '        repository_commit=pinned_commit,',
          '    )'),
        "回填 repository_commit",
    ),
    (
        L('def load_cases(cases_dir: str) -> list[BenchmarkCase]:',
          '    """加载全部案例（五类目录递归扫描）；任一非法 → CaseError。"""',
          '    root = Path(cases_dir)',
          '    if not root.is_dir():',
          '        raise CaseError(f"案例目录不存在: {cases_dir}")',
          '    cases: list[BenchmarkCase] = []'),
        L('def default_lock_path(cases_dir: str, version: str | None = None) -> str:',
          '    """默认锁定文件路径（T3）：<cases_dir 同级>/frozen/<version>/cases.lock.json。"""',
          '    ver = (version or os.environ.get(FROZEN_VERSION_ENV_VAR, "")',
          '           or FROZEN_VERSION_DEFAULT)',
          '    return str(Path(cases_dir).parent / "frozen" / ver / "cases.lock.json")',
          '',
          '',
          'def resolve_lock_path(cases_dir: str, lock_path: str | None = None) -> str:',
          '    """锁定文件路径解析（T3）：显式参数 > KA_BENCHMARK_CASES_LOCK > 默认路径。"""',
          '    if lock_path:',
          '        return lock_path',
          '    env_path = (os.environ.get(LOCK_ENV_VAR) or "").strip()',
          '    return env_path or default_lock_path(cases_dir)',
          '',
          '',
          'def load_lock_file(lock_path: str) -> dict[str, str]:',
          '    """读取锁定文件 → {case_id: repository_commit}；文件不存在 → {}（可选）。',
          '',
          '    存在但非法（JSON 无法解析 / 顶层非对象 / 值非非空字符串）→ CaseError：',
          '    锁定文件损坏必须显式失败，不能静默降级为“未锁定”。',
          '    兼容 {"cases": {...}} 包裹形态与裸映射 {"id": "commit"} 两种写法。',
          '    """',
          '    p = Path(lock_path)',
          '    if not p.is_file():',
          '        return {}',
          '    try:',
          '        data = json.loads(p.read_text(encoding="utf-8"))',
          '    except json.JSONDecodeError as e:',
          '        raise CaseError(f"锁定文件 {lock_path}: JSON 解析失败: {e}") from e',
          '    if isinstance(data, dict) and isinstance(data.get("cases"), dict):',
          '        data = data["cases"]',
          '    if not isinstance(data, dict):',
          '        raise CaseError(f"锁定文件 {lock_path}: 顶层须为对象（case_id -> commit）")',
          '    lock: dict[str, str] = {}',
          '    for key, value in data.items():',
          '        if not isinstance(value, str) or not value:',
          '            raise CaseError(',
          '                f"锁定文件 {lock_path}: {key} 的 repository_commit 须为非空字符串"',
          '                f"（got {value!r}）")',
          '        lock[str(key)] = value',
          '    return lock',
          '',
          '',
          'def load_cases(cases_dir: str, lock_path: str | None = None) -> list[BenchmarkCase]:',
          '    """加载全部案例（五类目录递归扫描）；任一非法 → CaseError。',
          '',
          '    lock_path 可选（T3，见模块 docstring）：缺省由 resolve_lock_path 解析；',
          '    锁定文件不存在即未锁定，行为与历史完全一致。',
          '    """',
          '    root = Path(cases_dir)',
          '    if not root.is_dir():',
          '        raise CaseError(f"案例目录不存在: {cases_dir}")',
          '    # T3：可选锁定文件（不存在 → {}，与未锁定行为一致）',
          '    lock = load_lock_file(resolve_lock_path(cases_dir, lock_path))',
          '    cases: list[BenchmarkCase] = []'),
        "锁定文件加载 + load_cases 签名",
    ),
    (
        L('            c = _validate(data, json_file)'),
        L('            c = _validate(data, json_file, lock)'),
        "把 lock 传给 _validate",
    ),
]

# ---------------------------------------------------------------------------
# 4) tools/docker_sandbox.py
# ---------------------------------------------------------------------------

SANDBOX_EDITS = [
    (
        L('DEFAULT_IMAGE = "ka-sandbox:py312-v1"',
          '',
          '# docker CLI 单次调用超时（创建/销毁/exec 都可能长耗时）',
          'DOCKER_CLI_TIMEOUT = 300'),
        L('DEFAULT_IMAGE = "ka-sandbox:py312-v1"',
          '',
          '# docker CLI 单次调用超时（创建/销毁/exec 都可能长耗时）',
          'DOCKER_CLI_TIMEOUT = 300',
          '',
          '# T3：真实执行器旁路记录——sandbox_executor 真正返回/创建执行器时写入，供',
          '# benchmark/report.py 读取“实际跑过的执行器”（此前报告只能记声明值，声明 docker',
          '# 而实际 local 无法暴露）。纯观测记录，不改变任何执行语义。',
          '_ACTUAL_EXECUTOR: dict = {"name": "", "workspace_root": ""}',
          '',
          '',
          'def _record_actual_executor(name: str, workspace_root: str = "") -> None:',
          '    """记录真实创建的执行器（T3，仅供报告观测）。"""',
          '    _ACTUAL_EXECUTOR["name"] = name',
          '    _ACTUAL_EXECUTOR["workspace_root"] = workspace_root',
          '',
          '',
          'def get_actual_executor() -> str:',
          '    """真实创建过的执行器名（T3）："local" / "docker"；从未创建 → ""。"""',
          '    return _ACTUAL_EXECUTOR.get("name", "")',
          '',
          '',
          'def reset_actual_executor() -> None:',
          '    """清空真实执行器记录（T3；测试用，避免用例间残留）。"""',
          '    _record_actual_executor("", "")'),
        "真实执行器记录 + getter",
    ),
    (
        L('        repo_url=os.environ.get("KA_SANDBOX_REPO_URL") or None,',
          '    )'),
        L('        repo_url=os.environ.get("KA_SANDBOX_REPO_URL") or None,',
          '    )',
          '',
          '',
          'def get_effective_sandbox_policy() -> dict:',
          '    """当前环境生效的沙箱策略 dict（T3）：image/cpus/memory/pids/network。',
          '',
          '    取自 get_sandbox_config()（与创建容器同源）；executor 为 KA_EXECUTOR 声明值。',
          '    有意不含 repo_url（可能携带凭据）。',
          '    """',
          '    cfg = get_sandbox_config()',
          '    return {',
          '        "executor": os.environ.get("KA_EXECUTOR", "local"),',
          '        "image": cfg.image,',
          '        "cpus": cfg.cpus,',
          '        "memory": cfg.memory,',
          '        "pids_limit": cfg.pids_limit,',
          '        "network": cfg.network,',
          '    }'),
        "有效沙箱策略 dict",
    ),
    (
        L('    if os.environ.get("KA_EXECUTOR", "local") != "docker":',
          '        yield LocalExecutor()',
          '        return'),
        L('    if os.environ.get("KA_EXECUTOR", "local") != "docker":',
          '        # T3：旁路记录真实执行器（声明值仍来自 KA_EXECUTOR / --executor）',
          '        _record_actual_executor("local", os.path.abspath(workspace_root))',
          '        yield LocalExecutor()',
          '        return'),
        "local 路径记录",
    ),
    (
        L('        manager.create()          # 创建失败（含部分失败）也会走到 finally 的 destroy',
          '        executor = DockerExecutor(manager)',
          '        token = _CURRENT_EXECUTOR.set(executor)'),
        L('        manager.create()          # 创建失败（含部分失败）也会走到 finally 的 destroy',
          '        executor = DockerExecutor(manager)',
          '        # T3：容器真正创建成功后才记 docker（创建失败不得被记为“跑过 docker”）',
          '        _record_actual_executor("docker", manager.workspace_root)',
          '        token = _CURRENT_EXECUTOR.set(executor)'),
        "docker 路径记录",
    ),
]

# ---------------------------------------------------------------------------
# 5) main.py（成本提示文案：0 → unknown）
# ---------------------------------------------------------------------------

MAIN_EDITS = [
    (
        L('    if report.results and not MODEL_PRICE_USD_PER_1K:',
          '        print("提示: 模型单价表为空，成本列全部为 0（待提供实际单价后填入 benchmark/runner.py 的 MODEL_PRICE_USD_PER_1K）")'),
        L('    if report.results and not MODEL_PRICE_USD_PER_1K:',
          '        print("提示: 模型单价表为空，成本列为 unknown（cost_usd=null / cost_source="',
          '              "unknown，不是 0；待提供实际单价后填入 benchmark/runner.py 的 "',
          '              "MODEL_PRICE_USD_PER_1K）")'),
        "成本提示文案与 None 语义对齐",
    ),
]

TARGETS = [
    ("benchmark/report.py", REPORT_EDITS),
    ("benchmark/runner.py", RUNNER_EDITS),
    ("benchmark/loader.py", LOADER_EDITS),
    ("tools/docker_sandbox.py", SANDBOX_EDITS),
    ("main.py", MAIN_EDITS),
]

# ---------------------------------------------------------------------------
# 新建测试文件
# ---------------------------------------------------------------------------

TEST_FILE_CONTENT = r'''"""T3 元信息测试：成本来源、报告渲染、锁定文件、真实执行器记录。"""
import hashlib
import json
from pathlib import Path

import pytest

import benchmark.runner as runner_mod
import tools.docker_sandbox as sandbox_mod
from benchmark.loader import BenchmarkCase, CaseError, load_cases
from benchmark.report import (BenchmarkReport, CaseResult, RunMetadata,
                              compare_reports, current_metadata,
                              enrich_run_metadata, judge_prompt_sha256,
                              save_json, save_markdown)
from tools.shell_tools import LocalExecutor


# --- 1) 成本：单价表为空 → cost_usd=None + cost_source="unknown" ---


def test_default_price_table_is_empty():
    """现状：仓库单价表为空 → 任何模型成本都是 unknown（而不是 0.0）。"""
    assert runner_mod.MODEL_PRICE_USD_PER_1K == {}
    assert runner_mod.cost_for("whatever", 10, 10) == (None, "unknown")


def test_cost_unknown_when_price_table_empty(monkeypatch):
    monkeypatch.setattr(runner_mod, "MODEL_PRICE_USD_PER_1K", {})
    assert runner_mod.cost_for("mimo-v2.5", 1000, 500) == (None, "unknown")
    assert runner_mod._cost_usd("mimo-v2.5", 1000, 500) is None


def test_cost_computed_when_price_known(monkeypatch):
    monkeypatch.setattr(runner_mod, "MODEL_PRICE_USD_PER_1K", {"mimo-v2.5": 0.004})
    cost, source = runner_mod.cost_for("mimo-v2.5", 1000, 0)
    assert source == "computed"
    assert cost == pytest.approx(0.004)


def test_case_result_defaults_to_unknown_source():
    """CaseResult 缺省 cost_source=unknown（旧 report.json 反序列化不会假装已知）。"""
    r = _case_result("c1", None)
    assert r.cost_source == "unknown"


# --- 2) 报告渲染容忍 None 成本 ---


def _meta(run_id="t3-run"):
    return RunMetadata(run_id=run_id, git_commit="abc", branch="b",
                       model="m", timestamp="2026-01-01T00:00:00",
                       executor="docker", params={})


def _case_result(case_id, cost, source="unknown"):
    return CaseResult(
        case_id=case_id, category="bug", status="not_resolved",
        resolution=False, test_pass=False, patch_acceptance=False,
        judge_verdict="SKIP", judge_reason="SKIP", tool_success_rate=0.0,
        iteration_count=0, latency_s=1.0, tokens_prompt=0, tokens_completion=0,
        cost_usd=cost, cost_source=source, diff="", errors=[])


def test_report_renders_unknown_cost(tmp_path):
    report = BenchmarkReport(metadata=_meta(), total=1, resolved=0,
                             resolution_rate=0.0,
                             results=[_case_result("c1", None)])
    text = Path(save_markdown(report, str(tmp_path))).read_text(encoding="utf-8")
    assert "unknown" in text
    data = json.loads(Path(save_json(report, str(tmp_path))).read_text(encoding="utf-8"))
    assert data["results"][0]["cost_usd"] is None
    assert data["results"][0]["cost_source"] == "unknown"


def test_report_total_cost_handles_none(tmp_path):
    """混合成本：已知值照常求和并标注部分 unknown；全 None → unknown；均不崩。"""
    mixed = BenchmarkReport(metadata=_meta(), total=2, resolved=0,
                            resolution_rate=0.0,
                            results=[_case_result("c1", 0.5, "computed"),
                                     _case_result("c2", None)])
    text = Path(save_markdown(mixed, str(tmp_path))).read_text(encoding="utf-8")
    assert "0.5000" in text and "unknown" in text
    out = compare_reports([mixed])
    assert "0.5000" in out and "unknown" in out
    assert "unknown" in compare_reports([
        BenchmarkReport(metadata=_meta(), total=1, resolved=0,
                        resolution_rate=0.0, results=[_case_result("c1", None)])])


def test_unknown_cost_survives_json_roundtrip(tmp_path):
    """--compare 路径（RunMetadata/CaseResult 反序列化）容忍 None 成本与缺失新键。"""
    report = BenchmarkReport(metadata=_meta(), total=1, resolved=0,
                             resolution_rate=0.0,
                             results=[_case_result("c1", None)])
    data = json.loads(Path(save_json(report, str(tmp_path))).read_text(encoding="utf-8"))
    meta = RunMetadata(**data["metadata"])
    assert meta.resolution_definition_version == "t3-1"
    assert meta.side_effect_policy == "read_only"
    r = CaseResult(**data["results"][0])
    assert r.cost_usd is None and r.cost_source == "unknown"
    # 旧报告缺新键 → 默认值兜底（向后兼容）
    legacy = {"run_id": "old", "git_commit": "c", "branch": "b", "model": "m",
              "timestamp": "t", "executor": "local", "params": {}}
    old = RunMetadata(**legacy)
    assert old.executor_actual == "" and old.sandbox_policy == {}
    assert old.iteration_limits == {} and old.timeouts == {}
    assert old.judge_prompt_sha256 == ""


# --- 3) T3 元信息采集 ---


def test_enrich_run_metadata_records_t3_fields():
    llm = type("L", (), {"base_url": "http://x", "model": "m"})()
    cases = [type("C", (), {"id": "c1", "max_iterations": 30})()]
    meta = enrich_run_metadata(current_metadata("m", "docker"), llm=llm, cases=cases)
    assert meta.base_url == "http://x"
    assert meta.resolution_definition_version == "t3-1"
    assert meta.side_effect_policy == "read_only"
    assert meta.iteration_limits["per_case"] == {"c1": 30}
    assert meta.iteration_limits["fallback_to_run_level"] == []
    assert set(meta.timeouts) == {"KA_SETUP_TIMEOUT_S", "KA_LLM_TIMEOUT_S",
                                  "KA_LLM_MAX_RETRIES"}
    assert meta.judge_prompt_sha256 == judge_prompt_sha256()
    assert len(meta.judge_prompt_sha256) == 64


def test_iteration_limits_fallback_to_run_level():
    from benchmark.report import effective_iteration_limits
    out = effective_iteration_limits([type("C", (), {"id": "c1"})()], run_level=7)
    assert out["per_case"] == {"c1": 7}
    assert out["fallback_to_run_level"] == ["c1"]


def test_timeouts_reflect_env(monkeypatch):
    from benchmark.report import effective_timeouts
    monkeypatch.setenv("KA_SETUP_TIMEOUT_S", "45")
    monkeypatch.setenv("KA_LLM_TIMEOUT_S", "33.5")
    monkeypatch.setenv("KA_LLM_MAX_RETRIES", "5")
    assert effective_timeouts() == {"KA_SETUP_TIMEOUT_S": 45,
                                    "KA_LLM_TIMEOUT_S": 33.5,
                                    "KA_LLM_MAX_RETRIES": 5}


def test_judge_prompt_sha256_matches_judge_module():
    from benchmark.judge import JUDGE_PROMPT
    assert judge_prompt_sha256() == hashlib.sha256(
        JUDGE_PROMPT.encode("utf-8")).hexdigest()


# --- 4) 锁定文件：可选 + 存在时钉住提交 ---


def _write_case(cases_dir, category, case_id, **overrides):
    data = {
        "id": case_id, "category": category, "repository": "dbader/schedule",
        "issue": {"number": 646, "title": "t", "body": "b", "labels": [],
                  "state": "open"},
        "gold_patch": "gold/%s.diff" % case_id, "must_pass": ["test_schedule.py"],
        "max_iterations": 30,
    }
    data.update(overrides)
    p = cases_dir / category / (case_id + ".json")
    p.parent.mkdir(parents=True, exist_ok=True)
    (p.parent.parent / "gold").mkdir(parents=True, exist_ok=True)
    (p.parent.parent / "gold" / ("%s.diff" % case_id)).write_text(
        "+guard", encoding="utf-8")
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _cases_dir(tmp_path):
    """cases_dir = <tmp>/benchmark/cases → 默认锁定路径落在 <tmp>/benchmark 内。"""
    return tmp_path / "benchmark" / "cases"


def _no_lock_env(monkeypatch):
    monkeypatch.delenv("KA_BENCHMARK_CASES_LOCK", raising=False)
    monkeypatch.delenv("KA_BENCHMARK_FROZEN_VERSION", raising=False)


def test_lock_file_is_optional(tmp_path, monkeypatch):
    """无锁定文件：加载成功且不钉提交（向后兼容）。"""
    _no_lock_env(monkeypatch)
    cases_dir = _cases_dir(tmp_path)
    _write_case(cases_dir, "bug", "schedule-646")
    cases = load_cases(str(cases_dir))
    assert len(cases) == 1
    assert cases[0].repository_commit == ""


def test_default_lock_file_pins_commit(tmp_path, monkeypatch):
    """默认路径 frozen/<version>/cases.lock.json 存在 → 钉住锁定值。"""
    _no_lock_env(monkeypatch)
    cases_dir = _cases_dir(tmp_path)
    _write_case(cases_dir, "bug", "schedule-646")
    lock_dir = tmp_path / "benchmark" / "frozen" / "v1"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "cases.lock.json").write_text(
        json.dumps({"schedule-646": "deadbeef" * 5}), encoding="utf-8")
    assert load_cases(str(cases_dir))[0].repository_commit == "deadbeef" * 5
    # 版本切换：KA_BENCHMARK_FROZEN_VERSION 指向另一版本目录
    other = tmp_path / "benchmark" / "frozen" / "v2"
    other.mkdir(parents=True, exist_ok=True)
    (other / "cases.lock.json").write_text(
        json.dumps({"schedule-646": "v2commit"}), encoding="utf-8")
    monkeypatch.setenv("KA_BENCHMARK_FROZEN_VERSION", "v2")
    assert load_cases(str(cases_dir))[0].repository_commit == "v2commit"


def test_inline_repository_commit_exposed(tmp_path, monkeypatch):
    _no_lock_env(monkeypatch)
    cases_dir = _cases_dir(tmp_path)
    _write_case(cases_dir, "bug", "schedule-646", repository_commit="cafe1234")
    assert load_cases(str(cases_dir))[0].repository_commit == "cafe1234"


def test_lock_env_path_overrides_inline(tmp_path, monkeypatch):
    """KA_BENCHMARK_CASES_LOCK 指定路径；锁定值优先于 case 内联值。"""
    cases_dir = _cases_dir(tmp_path)
    _write_case(cases_dir, "bug", "schedule-646", repository_commit="inline")
    lock = tmp_path / "custom.lock.json"
    lock.write_text(json.dumps({"cases": {"schedule-646": "pinned"}}),
                    encoding="utf-8")
    monkeypatch.setenv("KA_BENCHMARK_CASES_LOCK", str(lock))
    assert load_cases(str(cases_dir))[0].repository_commit == "pinned"


def test_explicit_lock_path_argument(tmp_path, monkeypatch):
    _no_lock_env(monkeypatch)
    cases_dir = _cases_dir(tmp_path)
    _write_case(cases_dir, "bug", "schedule-646")
    lock = tmp_path / "l.json"
    lock.write_text(json.dumps({"schedule-646": "abc123"}), encoding="utf-8")
    assert load_cases(str(cases_dir), lock_path=str(lock))[0].repository_commit \
        == "abc123"


def test_broken_lock_file_raises(tmp_path, monkeypatch):
    _no_lock_env(monkeypatch)
    cases_dir = _cases_dir(tmp_path)
    _write_case(cases_dir, "bug", "schedule-646")
    lock_dir = tmp_path / "benchmark" / "frozen" / "v1"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "cases.lock.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(CaseError, match="锁定文件"):
        load_cases(str(cases_dir))


def test_invalid_repository_commit_type_raises(tmp_path, monkeypatch):
    _no_lock_env(monkeypatch)
    cases_dir = _cases_dir(tmp_path)
    _write_case(cases_dir, "bug", "schedule-646", repository_commit=123)
    with pytest.raises(CaseError, match="repository_commit"):
        load_cases(str(cases_dir))


# --- 5) 真实执行器记录 / 沙箱策略 ---


def test_actual_executor_local_recorded(tmp_path, monkeypatch):
    monkeypatch.delenv("KA_EXECUTOR", raising=False)
    sandbox_mod.reset_actual_executor()
    try:
        assert sandbox_mod.get_actual_executor() == ""
        with sandbox_mod.sandbox_executor(str(tmp_path)) as ex:
            assert isinstance(ex, LocalExecutor)
        assert sandbox_mod.get_actual_executor() == "local"
    finally:
        sandbox_mod.reset_actual_executor()


def test_report_executor_actual_reflects_local(tmp_path, monkeypatch):
    """声明 docker 但真实跑的是 local → executor_actual 记 local（T3 核心诉求）。"""
    monkeypatch.delenv("KA_EXECUTOR", raising=False)
    sandbox_mod.reset_actual_executor()
    try:
        with sandbox_mod.sandbox_executor(str(tmp_path)):
            meta = enrich_run_metadata(current_metadata("m", "docker"))
        assert meta.executor_actual == "local"
    finally:
        sandbox_mod.reset_actual_executor()


def test_effective_sandbox_policy_exposes_limits(monkeypatch):
    monkeypatch.delenv("KA_EXECUTOR", raising=False)
    monkeypatch.setenv("KA_SANDBOX_CPUS", "4")
    monkeypatch.setenv("KA_SANDBOX_MEMORY", "2g")
    monkeypatch.setenv("KA_SANDBOX_PIDS", "256")
    policy = sandbox_mod.get_effective_sandbox_policy()
    assert policy == {"executor": "local", "image": sandbox_mod.DEFAULT_IMAGE,
                      "cpus": 4.0, "memory": "2g", "pids_limit": 256,
                      "network": False}


def test_report_carries_sandbox_policy():
    meta = enrich_run_metadata(current_metadata("m", "local"))
    assert meta.sandbox_policy.get("image") == sandbox_mod.DEFAULT_IMAGE
    assert meta.sandbox_policy.get("network") is False


# --- 6) 端到端：runner 产出的 CaseResult 携带 unknown 成本来源 ---


def test_runner_emits_unknown_cost_source(tmp_path, monkeypatch):
    from agent.llm import LLMMessage, MockLLMClient
    from tools.github_tools import GitHubIssue
    from tools.shell_tools import TestResult

    (tmp_path / "gold").mkdir(parents=True, exist_ok=True)
    (tmp_path / "gold" / "c.diff").write_text("+g", encoding="utf-8")
    case = BenchmarkCase(
        id="c", category="bug", repository="dbader/schedule",
        issue=GitHubIssue(number=1, title="t", body="b", labels=[], state="open"),
        gold_patch="gold/c.diff", must_pass=["t.py"], max_iterations=30)
    monkeypatch.setattr(runner_mod, "_ensure_repository", lambda *a, **k: None)
    monkeypatch.setattr(runner_mod, "run_issue_agent",
                        lambda task, llm, **kw: type("R", (), {
                            "diff": "+x", "iteration_count": 1, "steps": []})())
    monkeypatch.setattr(runner_mod, "run_tests",
                        lambda path, workspace_root: TestResult(1, 0, 0, 1, 0.1, []))
    monkeypatch.setattr(runner_mod, "MODEL_PRICE_USD_PER_1K", {})
    llm = MockLLMClient([LLMMessage(role="assistant", content="PASS 一致。")])
    report = runner_mod.run_benchmark_cases(
        llm, [case], str(tmp_path), "", "local", tmp_path)
    r = report.results[0]
    assert r.cost_usd is None
    assert r.cost_source == "unknown"
    assert report.metadata.executor_actual == "local"
    assert report.metadata.resolution_definition_version == "t3-1"
'''


# ---------------------------------------------------------------------------
# 计划 / 执行
# ---------------------------------------------------------------------------

class Row:
    """单条编辑的执行/检查结果。"""

    def __init__(self, idx, label, anchor_hits, status, note="", anchor_head=""):
        self.idx = idx
        self.label = label
        self.anchor_hits = anchor_hits
        self.status = status          # OK / ALREADY / FAILED
        self.note = note
        self.anchor_head = anchor_head

    def render(self):
        flag = {"OK": "OK     ", "ALREADY": "ALREADY", "FAILED": "FAILED "}[self.status]
        return (f"  {flag} edit#{self.idx:<2} hits={self.anchor_hits}  {self.label}\n"
                f"           anchor: {self.anchor_head}  ({self.note})")


def _plan_edits(text, edits):
    """按编辑顺序在内存中做锚点替换。

    返回 (ok, new_text, rows)。规则（保证幂等）：
      * 若 new 文本已在位 → ALREADY（跳过；追加型编辑的 old 会同时仍在文件中，
        因此必须先判 new 再判 old，否则重复 --apply 会重复追加）。
      * 否则 old 必须恰好出现 1 次 → OK，替换（在内存工作副本上顺序推进）。
      * 其余（0 次或 >1 次）→ FAILED，整组作废。
    """
    working = text
    rows = []
    ok = True
    for idx, (old, new, label) in enumerate(edits, 1):
        hits = working.count(old)
        head = old.split("\n")[0].strip()
        if len(head) > 66:
            head = head[:66] + "..."
        if working.count(new) >= 1:
            rows.append(Row(idx, label, hits, "ALREADY",
                            "新文本已在位（幂等跳过）", head))
            continue
        if hits == 1:
            working = working.replace(old, new, 1)
            rows.append(Row(idx, label, hits, "OK", "锚点唯一，已替换", head))
            continue
        ok = False
        rows.append(Row(idx, label, hits, "FAILED",
                        f"锚点匹配 {hits} 次（需恰好 1 次）", head))
    return ok, working, rows


def _compile_check(rel, new_text):
    """Python 目标新内容语法预检：返回错误信息或 None。"""
    if not rel.endswith(".py"):
        return None
    try:
        compile(new_text, rel.replace("/", os.sep), "exec")
        return None
    except SyntaxError as e:
        return f"语法预检失败: {e}"


def _load(path):
    """读文件 → (LF 归一化文本, 原换行风格, 是否有 BOM)。

    CODING 仓库源码是 CRLF；锚点以 LF 书写，故读入时统一归一为 LF，
    写回时再按原风格还原（二进制写，避免平台换行翻译改变整文件）。
    """
    with open(path, "rb") as f:
        raw = f.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    if bom:
        raw = raw[3:]
    nl = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return text, nl, bom


def _dump(path, text, nl="\n", bom=False):
    """按指定换行风格/BOM 原子写回（临时文件 + os.replace）。"""
    data = text.replace("\n", nl).encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".t3tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _repo_newline(repo):
    """新建文件使用的换行风格：随仓库现有源码（main.py），缺省 LF。"""
    probe = os.path.join(repo, "main.py")
    if os.path.isfile(probe):
        try:
            return _load(probe)[1]
        except OSError:
            pass
    return "\n"


def build_plans(repo, check_only):
    """构建全部文件的改动计划（不落盘）。返回 (plans, failed)。

    plans 元素：{"rel","path","ok","text","rows","nl","bom"}
    """
    plans = []
    failed = False
    for rel, edits in TARGETS:
        path = os.path.join(repo, rel.replace("/", os.sep))
        print(f"[{'CHECK' if check_only else 'PLAN '}] {rel}")
        if not os.path.isfile(path):
            print(f"  ! 目标文件不存在: {path}")
            plans.append({"rel": rel, "path": path, "ok": False, "text": None,
                          "rows": [], "nl": "\n", "bom": False})
            failed = True
            continue
        text, nl, bom = _load(path)
        ok, new_text, rows = _plan_edits(text, edits)
        for r in rows:
            print(r.render())
        err = _compile_check(rel, new_text) if ok else None
        if err:
            ok = False
            print(f"  ! {err}")
        changed = ok and new_text != text
        if not ok:
            failed = True
        plans.append({"rel": rel, "path": path, "ok": ok,
                      "text": new_text if changed else None, "rows": rows,
                      "nl": nl, "bom": bom})
        if ok:
            note = "将写入（内容有变化）" if changed else "无需写入（已是目标状态）"
            print(f"  => {note}")
    # 新建测试文件
    rel = TEST_FILE_REL
    path = os.path.join(repo, rel.replace("/", os.sep))
    nl = _repo_newline(repo)
    print(f"[{'CHECK' if check_only else 'PLAN '}] {rel}")
    if os.path.isfile(path):
        existing = _load(path)[0]
        if existing == TEST_FILE_CONTENT:
            print("  ALREADY 文件已存在且内容一致（幂等跳过）")
            plans.append({"rel": rel, "path": path, "ok": True, "text": None,
                          "rows": [], "nl": nl, "bom": False})
        else:
            print("  FAILED  文件已存在但内容不同（拒绝覆盖，请人工处理）")
            plans.append({"rel": rel, "path": path, "ok": False, "text": None,
                          "rows": [], "nl": nl, "bom": False})
            failed = True
    else:
        err = _compile_check(rel, TEST_FILE_CONTENT)
        if err:
            print(f"  ! {err}")
            plans.append({"rel": rel, "path": path, "ok": False, "text": None,
                          "rows": [], "nl": nl, "bom": False})
            failed = True
        else:
            print(f"  OK      将新建文件（内容已通过语法预检；换行风格 {'CRLF' if nl == chr(13) + chr(10) else 'LF'}）")
            plans.append({"rel": rel, "path": path, "ok": True,
                          "text": TEST_FILE_CONTENT, "rows": [], "nl": nl,
                          "bom": False})
    return plans, failed


def write_plans(plans):
    """全部计划成功才落盘（逐文件原子替换；调用前已确认无失败）。"""
    written = []
    for p in plans:
        if not p["ok"] or p["text"] is None:
            continue
        _dump(p["path"], p["text"], p["nl"], p["bom"])
        written.append((p["rel"], len(p["text"].encode("utf-8"))))
    return written


def main(argv=None):
    # Windows 控制台默认 GBK，中文摘要会乱码；统一 UTF-8 输出（同 CODING main.py 的做法）
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    ap = argparse.ArgumentParser(
        description="T3 基准元信息变更脚本（幂等 + 原子；默认 --repo 指向 CODING 仓库）")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true",
                      help="只检查：对每条计划编辑报告文件/锚点/匹配次数，不写文件")
    mode.add_argument("--apply", action="store_true", help="执行全部编辑")
    ap.add_argument("--repo", default=DEFAULT_REPO,
                    help=f"目标仓库根目录（默认 {DEFAULT_REPO}）")
    args = ap.parse_args(argv)

    repo = os.path.abspath(args.repo)
    print(f"repo = {repo}")
    print(f"mode = {'check' if args.check else 'apply'}")
    print("-" * 78)
    if not os.path.isdir(repo):
        print(f"! 仓库目录不存在: {repo}")
        return 2

    plans, failed = build_plans(repo, args.check)
    print("-" * 78)
    if failed:
        print("结果: FAILED —— 存在锚点失败/文件冲突，未写入任何文件")
        return 1

    if args.check:
        total = sum(len(p["rows"]) for p in plans)
        already = sum(1 for p in plans for x in p["rows"] if x.status == "ALREADY")
        print(f"结果: CHECK OK —— {len(plans)} 个文件 / {total} 条编辑，"
              f"其中 {already} 条为 already-applied")
        return 0

    written = write_plans(plans)
    print("已写入:")
    for rel, size in written:
        print(f"  {rel}  ({size} bytes)")
    if not written:
        print("  （无变化：全部编辑此前已应用）")
    print("结果: APPLY OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
