# tests/test_config.py
import os
from arknights_wiki import config


class TestProjectRoot:
    def test_project_root_exists(self):
        assert os.path.isdir(config.PROJECT_ROOT)

    def test_data_dir_default(self):
        assert config.DATA_DIR.endswith("data")
        assert config.DATA_DIR.startswith(config.PROJECT_ROOT)

    def test_output_dir_default(self):
        assert config.OUTPUT_DIR.endswith("output")


class TestOperatorFields:
    def test_char_fields_count_is_9(self):
        assert len(config.OPERATOR_CHAR_FIELDS) == 9

    def test_char_fields_contains_name_zh(self):
        assert "name_zh" in config.OPERATOR_CHAR_FIELDS

    def test_char_fields_excludes_gameplay_stats(self):
        excluded = ["hp", "atk", "def", "res", "block", "cost",
                    "name_en", "name_ja", "profession", "rarity", "position"]
        for field in excluded:
            assert field not in config.OPERATOR_CHAR_FIELDS


class TestCategoryMapping:
    def test_contains_main_categories(self):
        assert "主线" in config.CATEGORY_LABEL_MAP
        assert config.CATEGORY_LABEL_MAP["主线"] == "main"
        assert config.CATEGORY_LABEL_MAP["活动"] == "side"

    def test_labels_reverse_mapping(self):
        assert config.CATEGORY_LABELS["main"] == "主线"
        assert config.CATEGORY_LABELS["side"] == "支线"


class TestUrls:
    def test_index_url_is_prts_wiki(self):
        assert "prts.wiki" in config.INDEX_URL
        assert "剧情" in config.INDEX_URL or "%" in config.INDEX_URL

    def test_operator_list_url_is_prts_wiki(self):
        assert "prts.wiki" in config.OPERATOR_LIST_URL
