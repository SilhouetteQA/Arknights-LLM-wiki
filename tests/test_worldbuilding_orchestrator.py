import os, tempfile
from unittest.mock import patch, MagicMock
from arknights_wiki.extraction.worldbuilding_orchestrator import (
    run_phase1_book,
    run_phase2_video,
    run_pass3,
)


class TestPhase1Book:
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.call_llm")
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.create_client")
    def test_phase1_returns_seed_db(self, mock_create, mock_call):
        """Phase 1 返回种子库，含三层实体"""
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mock_call.return_value = {
            "concepts": [
                {"name": "源石", "category": "自然现象/物质",
                 "definition": "...", "summary": "..."},
            ],
            "factions": [],
            "locations": [],
            "timeline_events": [],
            "_stats": {"tokens_in": 1000, "tokens_out": 200},
        }

        with tempfile.TemporaryDirectory() as tmp:
            seed_db_path = os.path.join(tmp, "seed_db.json")
            result = run_phase1_book(
                book_path="data/lorebook/terra_a_journey_full.md",
                seed_db_path=seed_db_path,
            )
            assert "concepts" in result
            assert "factions" in result
            assert "locations" in result
            assert os.path.exists(seed_db_path)

    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.call_llm")
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.create_client")
    def test_phase1_calls_llm_per_chapter(self, mock_create, mock_call):
        """Phase 1 对每章调用一次 LLM (6 章 + 1 泰拉纪年 = 7)"""
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mock_call.return_value = {
            "concepts": [], "factions": [], "locations": [],
            "timeline_events": [],
            "_stats": {"tokens_in": 100, "tokens_out": 50},
        }

        with tempfile.TemporaryDirectory() as tmp:
            seed_db_path = os.path.join(tmp, "seed_db.json")
            run_phase1_book(
                book_path="data/lorebook/terra_a_journey_full.md",
                seed_db_path=seed_db_path,
            )
            assert mock_call.call_count == 7


class TestPhase2Video:
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.call_llm")
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.create_client")
    def test_phase2_returns_enriched_seed_db(self, mock_create, mock_call):
        """Phase 2 在种子库基础上返回丰富后的实体"""
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        mock_call.return_value = {
            "concepts": [
                {"name": "源石", "category": "自然现象/物质",
                 "definition": "...", "summary": "补充：视频展示了新的角度。"},
            ],
            "factions": [],
            "locations": [],
            "_stats": {"tokens_in": 5000, "tokens_out": 300},
        }

        seed_db_v1 = {
            "concepts": [
                {"name": "源石", "category": "自然现象/物质",
                 "definition": "...", "summary": "基础设定。"},
            ],
            "factions": [],
            "locations": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            result = run_phase2_video(
                seed_db=seed_db_v1,
                video_dir="data/videos",
                output_dir=tmp,
            )
            assert "concepts" in result
            # 源石应被丰富
            assert "补充" in result["concepts"][0]["summary"]


class TestRunPass3:
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.run_phase1_book")
    @patch("arknights_wiki.extraction.worldbuilding_orchestrator.run_phase2_video")
    def test_run_pass3_calls_both_phases(self, mock_p2, mock_p1):
        """完整 Pass 3 依次调用 Phase 1 和 Phase 2"""
        mock_p1.return_value = {"concepts": [], "factions": [], "locations": []}
        mock_p2.return_value = {"concepts": [], "factions": [], "locations": []}

        with tempfile.TemporaryDirectory() as tmp:
            result = run_pass3(
                book_path="data/lorebook/terra_a_journey_full.md",
                video_dir="data/videos",
                output_dir=tmp,
            )
            mock_p1.assert_called_once()
            mock_p2.assert_called_once()
