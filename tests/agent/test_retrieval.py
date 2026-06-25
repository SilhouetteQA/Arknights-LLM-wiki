"""数据访问层测试"""
import os
from arknights_wiki.agent.retrieval import (
    WikiStore,
    EventStore,
    DialogueStore,
    TimelineStore,
    EntityIndexStore,
)


class TestWikiStore:
    def test_search_concept_by_name(self, temp_data_dir):
        store = WikiStore(data_dir=temp_data_dir)
        results = store.search("源石", category="concept")
        assert len(results) > 0
        assert results[0]["name"] == "源石"
        assert results[0]["entity_type"] == "concept"
        assert len(results[0]["text"]) > 0

    def test_search_faction(self, temp_data_dir):
        store = WikiStore(data_dir=temp_data_dir)
        results = store.search("罗德岛", category="faction")
        assert len(results) > 0
        assert results[0]["name"] == "罗德岛"

    def test_get_entity_page(self, temp_data_dir):
        store = WikiStore(data_dir=temp_data_dir)
        page = store.get_page("源石", "concept")
        assert page is not None
        assert "源石" in page["text"]

    def test_get_nonexistent_page(self, temp_data_dir):
        store = WikiStore(data_dir=temp_data_dir)
        page = store.get_page("不存在", "concept")
        assert page is None

    def test_list_all_entity_names(self, temp_data_dir):
        store = WikiStore(data_dir=temp_data_dir)
        names = store.list_names("concept")
        assert "源石" in names
        assert "矿石病" in names


class TestEventStore:
    def test_search_by_entity(self, temp_data_dir):
        store = EventStore(data_dir=temp_data_dir)
        results = store.search(entity="阿米娅")
        assert len(results) > 0
        assert any("阿米娅" in r["text"] for r in results)

    def test_get_chapter_summary(self, temp_data_dir):
        store = EventStore(data_dir=temp_data_dir)
        summary = store.get_chapter_summary("黑暗时代·上")
        assert summary is not None
        assert "博士苏醒" in summary["text"]


class TestDialogueStore:
    def test_search_dialogue(self, temp_data_dir):
        store = DialogueStore(data_dir=temp_data_dir)
        results = store.search("博士")
        assert len(results) > 0
        assert any("博士" in r["text"] for r in results)

    def test_search_dialogue_by_chapter(self, temp_data_dir):
        store = DialogueStore(data_dir=temp_data_dir)
        results = store.search("博士", chapter="黑暗时代·上")
        assert len(results) > 0


class TestTimelineStore:
    def test_search_timeline(self, temp_data_dir):
        store = TimelineStore(data_dir=temp_data_dir)
        results = store.search("移动城市")
        assert len(results) > 0


class TestEntityIndexStore:
    """实体索引存储测试"""

    def test_lookup_missing_entity(self, temp_data_dir):
        store = EntityIndexStore(data_dir=temp_data_dir)
        assert store.lookup("不存在的实体XYZ") is None

    def test_lookup_without_index_file(self, temp_data_dir):
        store = EntityIndexStore(data_dir=temp_data_dir)
        assert store.lookup("源石") is None  # 尚未构建索引文件

    def test_lookup_with_index_file(self, temp_data_dir):
        import json
        # 写入一个最小的实体索引文件
        index_path = os.path.join(temp_data_dir, "entity_source_map.json")
        sample_index = {
            "源石": {
                "type": "concept",
                "source_files": {
                    "pass1_events": ["黑暗时代·上.json"],
                    "characters": [],
                    "operator_archives": [],
                    "terra_journey": [],
                },
                "related_entities": ["矿石病"],
                "related_factions": [],
                "related_locations": [],
                "related_characters": [],
            }
        }
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(sample_index, f, ensure_ascii=False)

        store = EntityIndexStore(data_dir=temp_data_dir)
        entry = store.lookup("源石")
        assert entry is not None
        assert entry["type"] == "concept"
        assert "矿石病" in entry["related_entities"]

    def test_search_related(self, temp_data_dir):
        import json
        index_path = os.path.join(temp_data_dir, "entity_source_map.json")
        sample_index = {
            "源石": {
                "type": "concept",
                "source_files": {"pass1_events": [], "characters": [], "operator_archives": [], "terra_journey": []},
                "related_entities": ["矿石病"],
                "related_factions": ["罗德岛"],
                "related_locations": [],
                "related_characters": ["阿米娅"],
            }
        }
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(sample_index, f, ensure_ascii=False)

        store = EntityIndexStore(data_dir=temp_data_dir)
        related = store.search_related("源石")
        assert "矿石病" in related
        assert "罗德岛" in related
        assert "阿米娅" in related

    def test_get_source_chapters(self, temp_data_dir):
        import json
        index_path = os.path.join(temp_data_dir, "entity_source_map.json")
        sample_index = {
            "源石": {
                "type": "concept",
                "source_files": {
                    "pass1_events": ["黑暗时代·上.json", "局部坏死.json"],
                    "characters": [],
                    "operator_archives": [],
                    "terra_journey": [],
                },
                "related_entities": [],
                "related_factions": [],
                "related_locations": [],
                "related_characters": [],
            }
        }
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(sample_index, f, ensure_ascii=False)

        store = EntityIndexStore(data_dir=temp_data_dir)
        chapters = store.get_source_chapters("源石")
        assert "黑暗时代·上" in chapters
        assert "局部坏死" in chapters

    def test_get_type(self, temp_data_dir):
        import json
        index_path = os.path.join(temp_data_dir, "entity_source_map.json")
        sample_index = {
            "源石": {
                "type": "concept",
                "source_files": {"pass1_events": [], "characters": [], "operator_archives": [], "terra_journey": []},
                "related_entities": [],
                "related_factions": [],
                "related_locations": [],
                "related_characters": [],
            }
        }
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(sample_index, f, ensure_ascii=False)

        store = EntityIndexStore(data_dir=temp_data_dir)
        assert store.get_type("源石") == "concept"
        assert store.get_type("不存在") is None
