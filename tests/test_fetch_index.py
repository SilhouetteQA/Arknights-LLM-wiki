# tests/test_fetch_index.py
from arknights_wiki.pipeline.fetch_index import (
    parse_index_html, index_to_batch_state, _is_story_link,
)

SAMPLE_INDEX_HTML = """<html><body><div class="mw-parser-output">
<table>
<tr><th>主线剧情</th><th></th></tr>
<tr><td>黑暗时代·上</td><td>主线</td><td><a href="/w/TR-1/BEG">TR-1 行动前</a></td></tr>
<tr><td>黑暗时代·上</td><td>主线</td><td><a href="/w/TR-2/BEG">TR-2 行动后</a></td></tr>
</table>
<table>
<tr><th>活动剧情</th><th></th></tr>
<tr><td>骑兵与猎人</td><td>活动</td><td><a href="/w/GT-1/BEG">GT-1 日暮寻路</a></td></tr>
</table>
</div></body></html>"""


class TestIsStoryLink:
    def test_valid_story_link(self):
        assert _is_story_link("/w/TR-1/BEG") is True

    def test_category_page_excluded(self):
        assert _is_story_link("/w/%E5%88%86%E7%B1%BB:test") is False

    def test_prts_page_excluded(self):
        assert _is_story_link("/w/PRTS:test") is False

    def test_no_w_prefix(self):
        assert _is_story_link("/other/page") is False


class TestParseIndexHtml:
    def test_extracts_nodes(self):
        nodes = parse_index_html(SAMPLE_INDEX_HTML)
        assert len(nodes) == 3

    def test_main_category_nodes(self):
        nodes = parse_index_html(SAMPLE_INDEX_HTML)
        main_nodes = [n for n in nodes if n["category"] == "main"]
        assert len(main_nodes) == 2
        assert main_nodes[0]["chapter"] == "黑暗时代·上"

    def test_side_category_nodes(self):
        nodes = parse_index_html(SAMPLE_INDEX_HTML)
        side_nodes = [n for n in nodes if n["category"] == "side"]
        assert len(side_nodes) == 1
        assert side_nodes[0]["chapter"] == "骑兵与猎人"

    def test_node_has_all_required_fields(self):
        nodes = parse_index_html(SAMPLE_INDEX_HTML)
        node = nodes[0]
        assert "id" in node
        assert "title" in node
        assert "chapter" in node
        assert "category" in node
        assert "source_url" in node

    def test_source_url_is_absolute(self):
        nodes = parse_index_html(SAMPLE_INDEX_HTML)
        for node in nodes:
            assert node["source_url"].startswith("https://prts.wiki")

    def test_empty_html(self):
        assert parse_index_html("") == []

    def test_no_parser_output(self):
        assert parse_index_html("<div></div>") == []


class TestIndexToBatchState:
    def test_basic_state(self):
        nodes = [
            {"id": "A", "title": "A", "chapter": "X", "category": "main",
             "source_url": "http://x"},
            {"id": "B", "title": "B", "chapter": "Y", "category": "side",
             "source_url": "http://y"},
        ]
        state = index_to_batch_state(nodes)
        assert state["total_nodes"] == 2
        assert state["fetched_nodes"] == 0
        assert state["pending_ordered"] == ["A", "B"]
        assert state["next_batch_available"] is True

    def test_empty_nodes(self):
        state = index_to_batch_state([])
        assert state["total_nodes"] == 0
        assert state["pending_ordered"] == []
