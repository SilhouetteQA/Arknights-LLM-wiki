"""Simple Search 测试"""
from unittest.mock import MagicMock, patch

from arknights_wiki.agent.simple_search import (
    simple_search,
    search_and_collect,
    build_answer_prompt,
)


class TestSearchAndCollect:
    def test_collects_wiki_results(self, temp_data_dir):
        with patch("arknights_wiki.agent.simple_search._get_data_dir", return_value=temp_data_dir):
            results = search_and_collect(
                entities=["源石"],
                question="源石是什么",
                question_type="worldview",
            )
            assert len(results) > 0

    def test_collects_events(self, temp_data_dir):
        with patch("arknights_wiki.agent.simple_search._get_data_dir", return_value=temp_data_dir):
            results = search_and_collect(
                entities=["阿米娅"],
                question="阿米娅在黑暗时代做了什么",
                question_type="character",
                chapter="黑暗时代·上",
            )
            assert len(results) > 0


class TestBuildAnswerPrompt:
    def test_formats_sources(self, temp_data_dir):
        sources = [
            {"entity_type": "concept", "name": "源石", "text": "源石是泰拉世界的核心能源。"},
        ]
        prompt = build_answer_prompt("源石是什么", sources)
        assert "源石是什么" in prompt
        assert "[参考1]" in prompt
        assert "源石是泰拉世界的核心能源" in prompt


class TestSimpleSearch:
    def test_returns_answer_with_mock_llm(self, temp_data_dir, mock_llm_client):
        with patch("arknights_wiki.agent.simple_search._get_data_dir", return_value=temp_data_dir):
            with patch("arknights_wiki.agent.simple_search.create_client", return_value=mock_llm_client):
                result = simple_search(
                    question="源石是什么",
                    route={
                        "complexity": "simple",
                        "question_type": "worldview",
                        "entities": ["源石"],
                        "time_scope": "cross_arc",
                    },
                )
                assert "answer" in result
                assert "sources" in result
                assert len(result["sources"]) > 0


class TestCASUALSearch:
    """CASUAL 风格搜索测试"""
    def test_build_answer_prompt_casual_style(self):
        sources = [{"entity_type": "concept", "name": "源石", "text": "源石是泰拉世界的核心能源。"}]
        prompt = build_answer_prompt("源石是什么", sources)
        assert "口语化" in prompt
        assert "禁止" in prompt
        assert "源石" in prompt

    def test_search_concept_prioritizes_page(self, temp_data_dir):
        with patch("arknights_wiki.agent.simple_search.DATA_DIR", temp_data_dir):
            sources = search_and_collect(
                entities=["源石"], question="源石是什么",
                question_type="concept_definition",
            )
            assert len(sources) > 0
            # First result should be exact match
            exact_matches = [s for s in sources if s.get("entity_type") == "concept" and s.get("name") == "源石"]
            assert len(exact_matches) > 0
