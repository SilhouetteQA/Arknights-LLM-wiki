"""数据访问层测试"""
from arknights_wiki.agent.retrieval import (
    WikiStore,
    EventStore,
    DialogueStore,
    TimelineStore,
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
