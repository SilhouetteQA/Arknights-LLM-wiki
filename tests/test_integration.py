# tests/test_integration.py
"""集成测试：验证所有模块可导入"""


class TestAllModulesImportable:
    def test_config(self):
        from arknights_wiki import config
        assert config.PRTS_BASE == "https://prts.wiki"

    def test_utils(self):
        from arknights_wiki import _utils
        assert callable(_utils.read_json)

    def test_fetch_index(self):
        from arknights_wiki.pipeline import fetch_index
        assert callable(fetch_index.parse_index_html)

    def test_fetch_stories(self):
        from arknights_wiki.pipeline import fetch_stories
        assert callable(fetch_stories.get_cache_path)

    def test_parse_dialogue(self):
        from arknights_wiki.pipeline import parse_dialogue
        assert callable(parse_dialogue.parse_datas_txt)

    def test_gen_markdown(self):
        from arknights_wiki.pipeline import gen_markdown
        assert callable(gen_markdown.story_to_markdown)

    def test_fetch_operators(self):
        from arknights_wiki.pipeline import fetch_operators
        assert callable(fetch_operators._extract_data_attrs)

    def test_gen_operators_md(self):
        from arknights_wiki.pipeline import gen_operators_md
        assert callable(gen_operators_md.operator_to_markdown)

    def test_orchestrate(self):
        from arknights_wiki.pipeline import orchestrate
        assert callable(orchestrate._select_batch_nodes)
