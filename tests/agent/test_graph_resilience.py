"""Graph 工具执行接入恢复链的集成测试（W2 Failure Recovery）

验证: _run_tool_with_resilience 的 fallback 命中 / breaker 短路 / 参数适配。
"""
from arknights_wiki.agent.graph import _adapt_fallback_args, _run_tool_with_resilience
from arknights_wiki.agent.resilience import CircuitBreaker
from arknights_wiki.agent.tools import TOOL_FALLBACKS, TOOL_EXECUTORS


class TestToolFallbacks:
    def test_fallback_registry(self):
        """注册表: 4 个工具声明了 fallback"""
        assert TOOL_FALLBACKS["get_entity_page"] == "search_wiki"
        assert TOOL_FALLBACKS["semantic_search"] == "search_wiki"
        assert TOOL_FALLBACKS["get_chapter_summary"] == "search_events"
        assert TOOL_FALLBACKS["lookup_entity_index"] == "search_wiki"

    def test_adapt_entity_page_args(self):
        """get_entity_page(name, entity_type) → search_wiki(query, category)"""
        adapted = _adapt_fallback_args("search_wiki", {"name": "罗德岛", "entity_type": "faction"})
        assert adapted == {"query": "罗德岛", "category": "faction"}

    def test_adapt_lookup_args(self):
        """lookup_entity_index(entity_name) → search_wiki(query)"""
        adapted = _adapt_fallback_args("search_wiki", {"entity_name": "源石"})
        assert adapted == {"query": "源石"}

    def test_adapt_chapter_args(self):
        """get_chapter_summary(chapter) → search_events(chapter)"""
        adapted = _adapt_fallback_args("search_events", {"chapter": "第九章"})
        assert adapted == {"chapter": "第九章"}


class TestRunToolWithResilience:
    def test_success_no_recovery(self):
        """正常执行: 无重试/无 fallback"""
        result, stats = _run_tool_with_resilience(
            "search_wiki",
            {"query": "不存在的实体XYZ"},
            TOOL_EXECUTORS["search_wiki"],
        )
        assert isinstance(result, str)
        assert stats["retries"] == 0
        assert stats["fallback_used"] is None

    def test_fallback_on_primary_failure(self):
        """主工具失败 → fallback 命中，文本带降级前缀"""
        def broken(**kwargs):
            raise ConnectionError("store unavailable")

        result, stats = _run_tool_with_resilience(
            "get_entity_page",
            {"name": "罗德岛", "entity_type": "faction"},
            broken,
        )
        assert stats["fallback_used"] == "search_wiki"
        assert result.startswith("[已降级: search_wiki]")

    def test_breaker_short_circuit(self):
        """breaker open 时返回熔断提示而非执行函数"""
        from arknights_wiki.agent.graph import _get_tool_breaker

        breaker = _get_tool_breaker("_test_breaker_tool")
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()  # 达到阈值 → open
        assert breaker.state == "open"

        def never_called(**kwargs):
            raise AssertionError("breaker open 后不应执行工具")

        result, stats = _run_tool_with_resilience(
            "_test_breaker_tool", {}, never_called,
        )
        assert "熔断" in result
        assert stats["breaker_state"] == "open"
