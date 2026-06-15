# tests/test_orchestrate.py
from arknights_wiki.pipeline.orchestrate import _select_batch_nodes


class TestSelectBatchNodes:
    def test_basic_selection(self):
        state = {"pending_ordered": ["A", "B", "C", "D", "E"]}
        result = _select_batch_nodes(state, 3)
        assert result == ["A", "B", "C"]

    def test_count_exceeds_pending(self):
        state = {"pending_ordered": ["A", "B"]}
        result = _select_batch_nodes(state, 10)
        assert len(result) == 2

    def test_empty_pending(self):
        state = {"pending_ordered": []}
        result = _select_batch_nodes(state, 5)
        assert result == []
