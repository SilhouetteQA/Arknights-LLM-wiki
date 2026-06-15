# tests/test_parse_dialogue.py
from arknights_wiki.pipeline.parse_dialogue import (
    parse_datas_txt, parse_story_html, extract_datas_txt,
)

MINIMAL_STORY_HTML = """<html><body>
<pre id="datas_txt">[name="阿米娅"] 博士。
[name=""] 天黑了。</pre>
</body></html>"""


class TestExtractDatasTxt:
    def test_extracts_pre_content(self):
        text = extract_datas_txt(MINIMAL_STORY_HTML)
        assert text is not None
        assert "博士" in text

    def test_no_datas_txt_tag(self):
        text = extract_datas_txt("<div>no pre</div>")
        assert text is None

    def test_empty_html(self):
        assert extract_datas_txt("") is None


class TestParseDatasTxt:
    def test_dialogue(self):
        result = parse_datas_txt('[name="阿米娅"] 博士，您醒了。')
        assert len(result) == 1
        assert result[0]["type"] == "dialogue"
        assert result[0]["speaker"] == "阿米娅"

    def test_narration(self):
        result = parse_datas_txt('[name=""] 天黑了。')
        assert len(result) == 1
        assert result[0]["type"] == "narration"
        assert "speaker" not in result[0]

    def test_nickname_placeholder_replaced(self):
        result = parse_datas_txt('[name="阿米娅"] {@nickname}，您好。')
        assert "博士" in result[0]["text"]
        assert "{@nickname}" not in result[0]["text"]

    def test_directives_skipped(self):
        result = parse_datas_txt(
            '[name="阿米娅"] 你好。\n[bgm="battle"]'
        )
        assert len(result) == 1

    def test_empty_input(self):
        assert parse_datas_txt("") == []
        assert parse_datas_txt(None) == []

    def test_mixed_dialogue_and_narration(self):
        raw = (
            '[name=""] 罗德岛的早晨。\n'
            '[name="阿米娅"] 早。\n'
            '[name="杜宾"] 训练场见。\n'
            '[name=""] 三人走向训练场。'
        )
        result = parse_datas_txt(raw)
        assert len(result) == 4
        assert result[0]["type"] == "narration"
        assert result[1]["speaker"] == "阿米娅"
        assert result[2]["speaker"] == "杜宾"
        assert result[3]["type"] == "narration"

    def test_whitespace_only_lines_skipped(self):
        result = parse_datas_txt(
            '[name="阿米娅"] 你好。\n\n   \n[name="杜宾"] 嗯。'
        )
        assert len(result) == 2


class TestParseStoryHtml:
    def test_full_parsing(self):
        story = parse_story_html(
            MINIMAL_STORY_HTML, "TEST-1", "测试", "测试章", "main",
            "https://prts.wiki/w/TEST-1"
        )
        assert story["id"] == "TEST-1"
        assert story["title"] == "测试"
        assert story["chapter"] == "测试章"
        assert story["category"] == "main"
        assert story["source_url"] == "https://prts.wiki/w/TEST-1"
        assert len(story["lines"]) == 2

    def test_no_datas_txt_returns_empty_lines(self):
        story = parse_story_html(
            "<div>no data</div>", "T", "T", "T", "main", "http://x"
        )
        assert story["lines"] == []
