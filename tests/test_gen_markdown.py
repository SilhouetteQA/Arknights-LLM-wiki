# tests/test_gen_markdown.py
from arknights_wiki.pipeline.gen_markdown import story_to_markdown


class TestStoryToMarkdown:
    def test_basic_structure(self):
        story = {
            "id": "TEST-1",
            "title": "测试",
            "chapter": "测试章",
            "category": "main",
            "source_url": "https://prts.wiki/w/TEST-1",
            "lines": [
                {"type": "dialogue", "speaker": "阿米娅", "text": "博士。"},
                {"type": "narration", "text": "天黑了。"},
            ],
        }
        md = story_to_markdown(story)
        assert "# TEST-1 测试" in md
        assert "**阿米娅**：博士。" in md
        assert "*天黑了。*" in md

    def test_chapter_and_category_in_header(self):
        story = {
            "id": "X", "title": "X", "chapter": "第一章", "category": "side",
            "source_url": "http://x",
            "lines": [],
        }
        md = story_to_markdown(story)
        assert "章节：第一章" in md
        assert "支线" in md

    def test_source_link(self):
        story = {
            "id": "X", "title": "X", "chapter": "X", "category": "main",
            "source_url": "https://prts.wiki/w/X",
            "lines": [],
        }
        md = story_to_markdown(story)
        assert "PRTS Wiki" in md
        assert "https://prts.wiki/w/X" in md

    def test_empty_lines(self):
        story = {
            "id": "X", "title": "X", "chapter": "X", "category": "main",
            "source_url": "http://x",
            "lines": [],
        }
        md = story_to_markdown(story)
        assert md  # 不是空字符串
