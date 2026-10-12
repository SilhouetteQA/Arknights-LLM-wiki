"""W11-D1/D2/D3 缺陷回归钉子（2026-10-12）。

背景：W11-α 首次基线跑批 122 题时 13/13 全部返回回退文案，根因是三条缺陷叠加：

- **D1（阻塞）**：`chat_completion` 在 `tools=None` 时把 `"tools": null` 发给 command_goat 网关，
  网关返回 400 `Invalid input: expected array, received null`；400 不可重试 ⇒ 一次即失败
  ⇒ **Wiki Agent 全线不可用**（2026-09-16 provider 整合后一直如此，因未重跑评测而未被发现）。
- **D2**：`judge.py` / `scoring.py` 硬编码全局 cost log 路径、无视 `ARKNIGHTS_COST_LOG`，
  导致 `--out <dir>` 跑批的成本账分裂（judge 记到别处），冻结基线的成本章节会漏掉 judge 成本。
- **D3**：`synthesize_node` 静默吞掉所有异常，使 D1 这种"每次都失败"的故障完全不可见。

本文件把三者都钉住，避免回归。
"""
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from arknights_wiki.agent import graph as agent_graph
from arknights_wiki.eval import judge
from arknights_wiki.extraction import llm_client

TMP_ROOT = Path(__file__).resolve().parents[2] / "output" / "_w11_probe" / "tmp"


def _scoring_module():
    """取 scoring 模块；宿主没有 deepeval（打分层在容器里跑）时跳过。

    刻意**不做全局 fake 注入** —— 那会污染同一会话里的 test_scoring.py（实测 4 例失败）。
    """
    pytest.importorskip("deepeval", reason="宿主无 deepeval：打分层在 Docker 容器内运行")
    from arknights_wiki.eval import scoring

    return scoring


@pytest.fixture()
def workdir():
    """仓库内自管理临时目录（本机沙箱下 pytest 的 tmp_path 建目录会被拒；见 test_freeze_metadata.py）。"""
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    d = TMP_ROOT / f"defect_{uuid.uuid4().hex[:10]}"
    d.mkdir(parents=True, exist_ok=True)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


class _Sentinel(Exception):
    """用于在记录到请求参数后中断调用，避免构造假的 OpenAI 响应对象。"""


class _Recorder:
    def __init__(self) -> None:
        self.kwargs: dict | None = None

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.kwargs = kwargs
        raise _Sentinel()


class TestD1ToolsNull:
    """D1：tools 为 None 时绝不能出现在请求里。"""

    def _call(self, tools):
        rec = _Recorder()
        orig = llm_client.create_client
        llm_client.create_client = lambda: rec
        try:
            with pytest.raises(_Sentinel):
                llm_client.chat_completion(
                    messages=[{"role": "user", "content": "hi"}], tools=tools
                )
        finally:
            llm_client.create_client = orig
        return rec.kwargs

    def test_none_tools_is_omitted(self):
        """回归：此前发的是 `"tools": null` → 网关 400 → agent 每个问题都回退。"""
        kwargs = self._call(None)
        assert "tools" not in kwargs, "tools=None 时不得放入请求（网关会对 null 返回 400）"

    def test_empty_tools_is_omitted(self):
        kwargs = self._call([])
        assert "tools" not in kwargs

    def test_real_tools_are_passed(self):
        tools = [{"type": "function", "function": {"name": "search_wiki", "parameters": {}}}]
        kwargs = self._call(tools)
        assert kwargs["tools"] == tools, "真实工具定义必须照常传递，否则 tool calling 失效"

    def test_other_params_unchanged(self):
        kwargs = self._call(None)
        assert set(kwargs) >= {"model", "messages", "temperature", "max_tokens"}


class TestD2CostLogPath:
    """D2：judge / scoring 必须与 runner 同口径尊重 ARKNIGHTS_COST_LOG。"""

    def test_judge_honors_env(self, monkeypatch, workdir):
        target = workdir / "baseline" / "cost_log.jsonl"
        monkeypatch.setenv("ARKNIGHTS_COST_LOG", str(target))
        assert judge.cost_log_path() == target

    def test_judge_default_is_global_path(self, monkeypatch):
        monkeypatch.delenv("ARKNIGHTS_COST_LOG", raising=False)
        assert judge.cost_log_path().as_posix().endswith("output/eval/cost_log.jsonl")

    def test_scoring_honors_env(self, monkeypatch, workdir):
        scoring = _scoring_module()
        target = workdir / "baseline" / "cost_log.jsonl"
        monkeypatch.setenv("ARKNIGHTS_COST_LOG", str(target))
        assert scoring.cost_log_path() == target

    def test_scoring_default_is_global_path(self, monkeypatch):
        scoring = _scoring_module()
        monkeypatch.delenv("ARKNIGHTS_COST_LOG", raising=False)
        assert scoring.cost_log_path().as_posix().endswith("output/eval/cost_log.jsonl")

    def test_log_cost_writes_to_override(self, monkeypatch, workdir):
        """端到端：写出的成本条目必须落在 --out 指定的目录里（否则基线成本账分裂）。"""
        target = workdir / "cost_log.jsonl"
        monkeypatch.setenv("ARKNIGHTS_COST_LOG", str(target))
        judge._log_cost({"step": "judge", "model": "m", "tokens_in": 1, "tokens_out": 1, "cost": 0.0})
        assert target.is_file()
        text = target.read_text(encoding="utf-8")
        assert '"step": "judge"' in text
        assert len([ln for ln in text.splitlines() if ln.strip()]) == 1


class TestD4JudgeSeesRetrievalContext:
    """D4：judge 必须看到 agent 实际检索到的资料（否则 faithfulness/hallucination 名不副实）。"""

    def test_prompt_includes_context(self):
        from arknights_wiki.eval import judge as j

        prompt = j._build_prompt(
            "问题", "答案", {"summary": "s", "evidence": ["e"]},
            ["资料甲：罗德岛是制药公司", "资料乙：凯尔希是医疗主管"],
        )
        assert "Agent 实际检索到的资料" in prompt
        assert "资料甲" in prompt and "资料乙" in prompt

    def test_prompt_without_context_is_explicit(self):
        from arknights_wiki.eval import judge as j

        prompt = j._build_prompt("问题", "答案", {"summary": "s"}, None)
        assert "未记录到检索资料" in prompt

    def test_context_budget_is_capped_and_declared(self):
        from arknights_wiki.eval import judge as j

        docs = ["x" * 1200 for _ in range(20)]
        prompt = j._build_prompt("q", "a", {}, docs)
        assert "后续资料因上下文预算省略" in prompt
        assert len(prompt) < j._MAX_CONTEXT_CHARS + 2000, "上下文必须有预算上限，不能无限膨胀"

    def test_judge_answer_forwards_context(self, monkeypatch):
        from arknights_wiki.eval import judge as j

        captured: dict = {}

        def fake_chat_json(model, system_prompt, prompt, **kw):
            captured["prompt"] = prompt
            captured["system"] = system_prompt
            return {
                "answer_correctness": 0.8, "faithfulness": 0.8,
                "citation_accuracy": None, "hallucination": 0, "reason": "ok",
                "_stats": {"tokens_in": 1, "tokens_out": 1, "cost": 0.0},
            }

        monkeypatch.setattr(j, "chat_json", fake_chat_json)
        out = j.judge_answer(
            "q", "a", {"summary": "s"}, [], [], "complex",
            retrieval_context=["检索到的资料：凯尔希是医疗主管"],
        )
        assert out["faithfulness"] == 0.8
        assert "凯尔希是医疗主管" in captured["prompt"]
        assert "实际检索" in captured["system"], "系统提示词也要说明判据含实际检索资料"


class TestD3FailureVisibility:
    """D3：回退文案不变，但失败必须留下告警（否则故障不可见）。"""

    def _state(self):
        return {
            "question": "罗德岛是什么？",
            "messages": [],
            "collected_docs": [
                {"tool": "search_wiki", "args": {"q": "罗德岛"}, "result": "资料内容"},
            ],
        }

    def test_failure_is_logged_and_fallback_preserved(self, monkeypatch, caplog):
        def boom(**kwargs):
            raise RuntimeError("Invalid input: expected array, received null")

        monkeypatch.setattr(llm_client, "chat_completion", boom)
        with caplog.at_level(logging.WARNING, logger="arknights_wiki.agent.graph"):
            state = agent_graph.synthesize_node(self._state())

        last = state["messages"][-1]
        assert last["role"] == "assistant"
        assert last["content"] == "抱歉，回答生成出了点问题。请稍后再试。"
        assert any("synthesize_node LLM 调用失败" in r.message for r in caplog.records), \
            "失败必须留下告警，静默吞异常正是 D1 三周未被发现的原因"

    def test_success_path_unaffected(self, monkeypatch, caplog):
        monkeypatch.setattr(
            llm_client, "chat_completion",
            lambda **kwargs: ("正常回答内容", SimpleNamespace(content="正常回答内容")),
        )
        with caplog.at_level(logging.WARNING, logger="arknights_wiki.agent.graph"):
            state = agent_graph.synthesize_node(self._state())
        assert state["messages"][-1]["content"] == "正常回答内容"
        assert not [r for r in caplog.records if "失败" in r.message]

    def test_no_docs_keeps_existing_behaviour(self):
        state = {"question": "q", "messages": [], "collected_docs": []}
        out = agent_graph.synthesize_node(state)
        assert "未找到相关内容" in out["messages"][-1]["content"]
