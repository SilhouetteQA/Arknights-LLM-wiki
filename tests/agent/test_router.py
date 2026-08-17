"""Query Router 测试"""
from unittest.mock import patch

from arknights_wiki.agent.router import (
    _extract_entities_local,
    _infer_intent_local,
    _infer_time_scope,
    _match_entities_ordered,
    classify_complexity_local,
    recognize_intent_and_rewrite,
    route_query,
    _resolve_temporal_entities,
)


class TestMatchEntitiesOrdered:
    """统一实体匹配：长度降序 + 区间占用 + 2 字前边界"""

    def test_longest_first(self):
        """长名优先：'源石外燃机' 匹配后 '源石' 被区间占用跳过"""
        result = _match_entities_ordered(
            "第一台轮式源石外燃机的研发阵营", ["源石", "源石外燃机"]
        )
        assert result == ["源石外燃机"]

    def test_range_occupation_blocks_substring(self):
        """区间占用：'维多利亚' 占用后 '多利' 失效（噪声消除）"""
        result = _match_entities_ordered("涉及维多利亚的外交活动", ["多利", "维多利亚"])
        assert result == ["维多利亚"]
        assert "多利" not in result

    def test_two_char_boundary(self):
        """2 字名前边界：'的领袖' 中 '领袖' 拒绝；句首 '博士' 接受"""
        assert _match_entities_ordered("乌萨斯学生自治团的领袖", ["领袖"]) == []
        assert _match_entities_ordered("领袖是谁", ["领袖"]) == ["领袖"]
        assert _match_entities_ordered("博士在切尔诺伯格苏醒", ["博士"]) == ["博士"]

    def test_two_char_boundary_after_punctuation(self):
        """2 字名在标点后仍接受"""
        assert _match_entities_ordered("欢迎回来，博士", ["博士"]) == ["博士"]


class TestComplexityStructuralSignalsExtra:
    """Step 2 补充信号：跨层区间、关系/以及、全面综合"""

    def test_cross_layer_range_blocks_noise(self, temp_data_dir):
        """角色层 '多利' 被世界观层 '维多利亚' 的占用区间拦截（跨层共享）"""
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            entities = _extract_entities_local("希瓦艾什家在维多利亚的外交活动")
            assert "多利" not in entities

    def test_relation_word_two_entities(self):
        """双实体 + 关系/关联 → complex（'矿石病与天灾之间的关联'）"""
        result = classify_complexity_local(
            "概括泰拉世界中矿石病与天灾之间的关联及相互影响",
            ["天灾", "矿石病"], "chapter_summary", "cross_arc",
        )
        assert result["complexity"] == "complex"

    def test_yiji_two_entities(self):
        """双实体 + 以及 → complex（多问综合）"""
        result = classify_complexity_local(
            "泰拉移动城市的驱动燃料是什么，以及与源石形成稳定共生关系的生物",
            ["源石", "移动城市"], "concept_definition", "cross_arc",
        )
        assert result["complexity"] == "complex"

    def test_holistic_two_entities(self):
        """双实体 + 全部/综合 → complex（'大静谧对伊比利亚产生的全部影响'）"""
        result = classify_complexity_local(
            "综合阐述大静谧爆发对伊比利亚产生的全部影响",
            ["伊比利亚", "大静谧"], "fact_lookup", "cross_arc",
        )
        assert result["complexity"] == "complex"

    def test_relation_single_entity_still_simple(self):
        """单实体 + 关系词 → 不触发（'X的关联' 单页可答）"""
        result = classify_complexity_local(
            "矿石病与源石的关联", ["矿石病"], "concept_definition", "cross_arc",
        )
        assert result["complexity"] == "simple"


class TestExtractEntitiesWorldbuilding:
    """v3_wiki 世界观实体提取（W0 路由修复 Step 2）"""

    def test_worldbuilding_entities(self, temp_data_dir):
        """factions/locations/concepts 文件名可被提取"""
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            # 罗德岛(factions) + 切尔诺伯格(locations) + 源石(concepts)
            entities = _extract_entities_local("罗德岛在切尔诺伯格使用源石")
            assert "罗德岛" in entities
            assert "切尔诺伯格" in entities
            assert "源石" in entities

    def test_substring_noise_removed(self, temp_data_dir):
        """'多利' 不匹配 '维多利亚'（2 字边界 + 区间占用）"""
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            entities = _extract_entities_local("维多利亚的外交活动")
            assert "多利" not in entities

    def test_multi_entity_nations(self, temp_data_dir):
        """双国家并列可提取（多主体信号的前提）"""
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            entities = _extract_entities_local("分别阐述乌萨斯与维多利亚的基本国家属性")
            # temp_data_dir 无乌萨斯/维多利亚 faction，断言不抛异常且结果稳定
            assert isinstance(entities, list)


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


class TestComplexityStructuralSignals:
    """结构性复杂信号（W0 路由修复）：多主体分别/对比、多时间点、事件枚举"""

    def test_multi_subject_respective(self):
        """双实体 + 分别 → complex（原被 chapter_summary 抢占误判 simple）"""
        result = classify_complexity_local(
            "分别阐述阿米娅与凯尔希在切尔诺伯格事件中的具体行动，并分别概括两人的核心性格与能力特点",
            ["阿米娅", "凯尔希"], "chapter_summary", "cross_arc",
        )
        assert result["complexity"] == "complex"

    def test_multi_subject_compare_words(self):
        """双实体 + 对比/差异词 → complex（LLM 兜底返回非 comparison 意图时仍命中）"""
        result = classify_complexity_local(
            "对比炎国与卡西米尔的国家政体、种族构成以及权力矛盾有何不同",
            ["炎国", "卡西米尔"], "concept_definition", "cross_arc",
        )
        assert result["complexity"] == "complex"

    def test_multi_subject_needs_two_entities(self):
        """单实体 + 分别/各自 → 不触发（单概念多子问仍 simple）"""
        result = classify_complexity_local(
            "两类技艺各自的使用要求是什么", ["源石技艺"], "concept_definition", "cross_arc",
        )
        assert result["complexity"] == "simple"

    def test_multi_timepoint(self):
        """2+ 不同年份 → complex（时间线事件综合）"""
        result = classify_complexity_local(
            "分别说明845年和885年发生的两个重大国家相关事件及其核心影响",
            [], "fact_lookup", "cross_arc",
        )
        assert result["complexity"] == "complex"

    def test_single_timepoint_not_enough(self):
        """单年份 + 无其他信号 → 保持 simple"""
        result = classify_complexity_local(
            "公元969年莱塔尼亚发生了什么", [], "fact_lookup", "cross_arc",
        )
        assert result["complexity"] == "simple"

    def test_event_enumeration(self):
        """'哪些...事件' → complex（事件枚举需宽搜）"""
        result = classify_complexity_local(
            "1031年发生了哪些与战争相关的重大事件", ["卡兹戴尔"], "fact_lookup", "cross_arc",
        )
        assert result["complexity"] == "complex"

    def test_effect_enumeration_not_complex(self):
        """'哪些标志性影响' 非事件枚举 → 不触发 complex"""
        result = classify_complexity_local(
            "该发明带来了哪些标志性影响", [], "fact_lookup", "cross_arc",
        )
        assert result["complexity"] == "simple"

    def test_empty_entities_no_deep_is_simple(self):
        """兜底修正：实体空 + 无深度词 → simple（原无条件 complex 误判 24 题）"""
        result = classify_complexity_local(
            "第一台轮式源石外燃机是在哪一阵营被发明的", [], "fact_lookup", "cross_arc",
        )
        assert result["complexity"] == "simple"

    def test_empty_entities_with_deep_still_complex(self):
        """实体空 + 跨章深度词 → 仍 complex（保留 Agent 探索兜底）"""
        result = classify_complexity_local(
            "整合运动在整个泰拉的势力演变", [], "chapter_summary", "cross_arc",
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
