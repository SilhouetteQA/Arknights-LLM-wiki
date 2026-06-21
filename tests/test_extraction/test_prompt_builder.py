# tests/test_extraction/test_prompt_builder.py
from arknights_wiki.extraction.prompt_builder import (
    build_system_prompt,
    build_user_prompt,
    get_summary_word_limit,
    build_character_system_prompt,
    build_character_user_prompt,
)


def test_build_system_prompt_contains_key_elements():
    prompt = build_system_prompt()
    assert "明日方舟" in prompt
    assert "JSON" in prompt
    assert "markdown" in prompt
    assert "line_range" in prompt
    assert "snake_case" in prompt
    assert "泛型" in prompt
    assert "实质" in prompt


def test_build_user_prompt_includes_chapter_and_dialogue():
    prompt = build_user_prompt(
        chapter="黑暗时代·上",
        dialogue_text="[阿米娅] 博士！\n[博士] 嗯。",
        total_lines=2
    )
    assert "黑暗时代·上" in prompt
    assert "[阿米娅] 博士！" in prompt
    assert "events" in prompt
    assert "concepts" in prompt


class TestGetSummaryWordLimit:
    """get_summary_word_limit 字数限制测试"""

    def test_limits_by_chapter_count(self):
        assert get_summary_word_limit(40) == 500
        assert get_summary_word_limit(20) == 500
        assert get_summary_word_limit(15) == 350
        assert get_summary_word_limit(10) == 350
        assert get_summary_word_limit(7) == 250
        assert get_summary_word_limit(5) == 250
        assert get_summary_word_limit(3) == 150
        assert get_summary_word_limit(2) == 150
        assert get_summary_word_limit(1) == 100


class TestCharacterSystemPrompt:
    """build_character_system_prompt 测试"""

    def test_contains_key_rules(self):
        prompt = build_character_system_prompt()
        assert "角色档案编纂者" in prompt
        assert "summary" in prompt
        assert "power_level" in prompt
        assert "participated_events" in prompt
        assert "JSON" in prompt
        assert "markdown" in prompt
        assert "编造" in prompt
        assert "信息不足" in prompt

    def test_mentions_power_level_system(self):
        prompt = build_character_system_prompt()
        assert "战场中坚" in prompt
        assert "文明之敌" in prompt
        assert "信息不足" in prompt


class TestCharacterUserPrompt:
    """build_character_user_prompt 测试"""

    def test_includes_character_name(self):
        prompt = build_character_user_prompt("阿米娅", 32, [])
        assert "阿米娅" in prompt
        assert "32" in prompt

    def test_includes_operator_archive_when_present(self):
        archive = {
            "name_zh": "阿米娅", "race": "卡特斯", "nation": "罗德岛",
            "team": "行动组A4", "group": "",
            "archives": {"基础档案": "代号阿米娅...", "客观履历": "罗德岛的公开领袖..."}
        }
        prompt = build_character_user_prompt("阿米娅", 32, [], archive)
        assert "卡特斯" in prompt
        assert "罗德岛" in prompt
        assert "基础档案" in prompt

    def test_includes_events_with_context(self):
        events = [{
            "chapter": "黑暗时代·上", "event": "阿米娅救出博士",
            "context_text": "[1] [阿米娅] 博士！\n[2] [博士] 嗯。",
            "line_range": [1, 2], "significance": "关键救援", "is_imaginary": False
        }]
        prompt = build_character_user_prompt("阿米娅", 1, events)
        assert "黑暗时代·上" in prompt
        assert "阿米娅救出博士" in prompt
        assert "[1] [阿米娅] 博士！" in prompt

    def test_marks_imaginary_events(self):
        events = [{
            "chapter": "萨卡兹的无终奇语", "event": "IF事件",
            "context_text": "[1] test", "line_range": [1, 1],
            "significance": "", "is_imaginary": True
        }]
        prompt = build_character_user_prompt("阿米娅", 1, events)
        assert "IS-IF线" in prompt

    def test_includes_summary_limit(self):
        prompt = build_character_user_prompt("阿米娅", 32, [])
        assert "500" in prompt

    def test_skips_archive_for_npc(self):
        prompt = build_character_user_prompt("Guard", 5, [], None)
        assert "非干员角色" in prompt
