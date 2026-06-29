"""Query Router 测试"""
from unittest.mock import patch

from arknights_wiki.agent.router import (
    _extract_entities_local,
    _infer_intent_local,
    _infer_time_scope,
    classify_complexity_local,
    recognize_intent_and_rewrite,
    route_query,
    _resolve_temporal_entities,
)


class TestIntentLocal:
    """本地意图推断测试（7类）"""
    def test_concept_definition(self):
        assert _infer_intent_local("源石是什么") == "concept_definition"
        assert _infer_intent_local("巨兽是怎样的") == "concept_definition"

    def test_chapter_summary(self):
        assert _infer_intent_local("落叶逐火讲了什么") == "chapter_summary"
        assert _infer_intent_local("孤星的剧情") == "chapter_summary"
        assert _infer_intent_local("整体脉络") == "chapter_summary"

    def test_character_profile(self):
        assert _infer_intent_local("阿米娅的性格") == "character_profile"
        assert _infer_intent_local("凯尔希战力") == "character_profile"

    def test_comparison(self):
        assert _infer_intent_local("阿米娅和凯尔希对比") == "comparison"
        assert _infer_intent_local("谁更强") == "comparison"

    def test_causal_reasoning(self):
        assert _infer_intent_local("为什么整合运动会袭击切尔诺伯格") == "causal_reasoning"
        assert _infer_intent_local("矿石病的演变") == "causal_reasoning"

    def test_list_enumeration(self):
        assert _infer_intent_local("有哪些兽主") == "list_enumeration"
        assert _infer_intent_local("罗德岛成员有谁") == "list_enumeration"

    def test_fact_lookup(self):
        assert _infer_intent_local("阿米娅的出生地") == "fact_lookup"
        assert _infer_intent_local("凯尔希的种族") == "fact_lookup"

    def test_unknown(self):
        assert _infer_intent_local("你好") == "unknown"
        assert _infer_intent_local("今天天气") == "unknown"


class TestTimeScope:
    def test_cross_arc_indicators(self):
        assert _infer_time_scope("矿石病在整个泰拉的演变", []) == "cross_arc"

    def test_chapter_explicit(self):
        assert _infer_time_scope("第三章讲了什么", ["第三章"]) == "chapter"

    def test_default_cross_arc(self):
        assert _infer_time_scope("源石是什么", ["源石"]) == "cross_arc"


class TestComplexity:
    def test_simple_fact(self):
        result = classify_complexity_local("阿米娅的出生地", ["阿米娅"], "fact_lookup", "chapter")
        assert result["complexity"] == "simple"

    def test_complex_comparison(self):
        result = classify_complexity_local(
            "对比阿米娅和凯尔希", ["阿米娅", "凯尔希"], "comparison", "cross_arc"
        )
        assert result["complexity"] == "complex"

    def test_complex_concept_definition(self):
        """concept_definition 不再强制 complex，单实体走 simple"""
        result = classify_complexity_local(
            "巨兽是什么", ["巨兽"], "concept_definition", "cross_arc"
        )
        assert result["complexity"] == "simple"

    def test_complex_list_enumeration(self):
        result = classify_complexity_local(
            "有哪些兽主", [], "list_enumeration", "cross_arc"
        )
        assert result["complexity"] == "complex"

    def test_complex_causal(self):
        result = classify_complexity_local(
            "为什么切尔诺伯格被摧毁", [], "causal_reasoning", "cross_arc"
        )
        assert result["complexity"] == "complex"

    def test_complex_multi_entity(self):
        """>3 个实体才触发 multi-entity complex"""
        result = classify_complexity_local(
            "整合运动、罗德岛、龙门、乌萨斯的关系", ["整合运动", "罗德岛", "龙门", "乌萨斯"], "chapter_summary", "cross_arc"
        )
        assert result["complexity"] == "complex"

    def test_complex_deep_cross_arc(self):
        result = classify_complexity_local(
            "整合运动的势力演变", ["整合运动"], "chapter_summary", "cross_arc"
        )
        assert result["complexity"] == "complex"


class TestRecognizeIntentAndRewrite:
    """意图识别+问题改写合并测试"""
    def test_concept_definition_local(self, temp_data_dir):
        """角色档案类问题走本地路径（干员名可通过 operators 匹配）"""
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            result = recognize_intent_and_rewrite("阿米娅是什么样的人", use_llm=False)
            assert result["intent"] == "character_profile"
            assert "阿米娅" in result["canonical_entities"]
            assert result["source"] == "local"

    def test_chapter_summary_local(self, temp_data_dir):
        """意图已知但实体为空时，关闭 LLM 走本地路径"""
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            result = recognize_intent_and_rewrite("黑暗时代讲了什么", use_llm=False)
            assert result["intent"] == "chapter_summary"
            assert result["source"] == "local"

    def test_llm_fallback_unknown(self, temp_data_dir, mock_llm_client):
        """意图未知时走 LLM 兜底，需 patch extraction.llm_client 而非 router"""
        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = (
            '{"intent": "concept_definition", "rewritten_question": "巨兽是什么", '
            '"canonical_entities": ["巨兽"], "expansion_hints": ["岁兽", "耶拉冈德"], '
            '"disambiguation_note": ""}'
        )
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            with patch(
                "arknights_wiki.extraction.llm_client.create_client",
                return_value=mock_llm_client,
            ):
                result = recognize_intent_and_rewrite("巨兽是啥玩意", use_llm=True)
                assert result["intent"] == "concept_definition"
                assert "巨兽" in result["canonical_entities"]
                assert result["source"] == "llm"

    def test_local_when_entities_empty_but_intent_known(self, temp_data_dir):
        """意图明确但实体为空 → 走 LLM 兜底"""
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            result = recognize_intent_and_rewrite("有哪些兽主", use_llm=False)
            # 意图明确但实体为空 → should try LLM if allowed, otherwise fallback
            assert result["intent"] in ("list_enumeration", "unknown", "fact_lookup")


class TestRouteQuery:
    def test_route_simple_question(self, temp_data_dir):
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            result = route_query("阿米娅的出生地")
            assert "complexity" in result
            assert "question_type" in result
            assert "entities" in result
            assert "rewritten_question" in result
            assert "expansion_hints" in result

    def test_route_returns_rewritten_fields(self, temp_data_dir):
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            result = route_query("源石是什么")
            assert "rewritten_question" in result
            assert "expansion_hints" in result
            assert "disambiguation_note" in result
            assert result["question_type"] == "concept_definition"


class TestTemporalResolution:
    """时序消歧测试"""
    def test_resolve_newest_replaces_earlier(self):
        from arknights_wiki.agent.router import _resolve_temporal_entities
        entities, note = _resolve_temporal_entities(
            "最新怪猎活动", ["落叶逐火", "泡影苍霆"]
        )
        assert "泡影苍霆" in entities
        assert "落叶逐火" not in entities
        assert "落叶逐火" in note

    def test_resolve_first_picks_earliest(self):
        from arknights_wiki.agent.router import _resolve_temporal_entities
        entities, note = _resolve_temporal_entities(
            "第一个怪猎联动", ["落叶逐火", "泡影苍霆"]
        )
        assert "落叶逐火" in entities
        assert "泡影苍霆" not in entities

    def test_no_temporal_keyword_no_change(self):
        from arknights_wiki.agent.router import _resolve_temporal_entities
        entities, note = _resolve_temporal_entities(
            "怪猎联动讲了什么", ["落叶逐火", "泡影苍霆"]
        )
        # 没有时间关键词，保持原样（两个都在，让 LLM 自行判断）
        assert len(entities) == 2

    def test_single_chapter_series_no_change(self):
        from arknights_wiki.agent.router import _resolve_temporal_entities
        entities, note = _resolve_temporal_entities(
            "最新孤星活动", ["孤星"]
        )
        assert "孤星" in entities

    def test_route_query_resolves_mh_newest(self, temp_data_dir):
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            result = route_query("最新怪猎联动讲了什么")
            entities = result["entities"]
            # 属于联动系列且有"最新" → 应替换为泡影苍霆
            assert "泡影苍霆" in entities
            # 消歧备注应包含信息
            assert len(result.get("disambiguation_note", "")) > 0
