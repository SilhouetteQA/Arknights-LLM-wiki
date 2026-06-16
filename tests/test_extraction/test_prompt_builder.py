# tests/test_extraction/test_prompt_builder.py
from arknights_wiki.extraction.prompt_builder import build_system_prompt, build_user_prompt


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
