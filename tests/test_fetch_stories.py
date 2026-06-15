# tests/test_fetch_stories.py
import os
import importlib
from arknights_wiki import config
from arknights_wiki.pipeline.fetch_stories import (
    get_cache_path, story_url_from_id,
)


class TestGetCachePath:
    def test_with_chapter(self, monkeypatch):
        monkeypatch.setenv("ARKNIGHTS_DATA_DIR", "/tmp/fake_data")
        importlib.reload(config)
        try:
            path = get_cache_path("TR-1", "main", "黑暗时代·上")
            assert "stories" in path
            assert "main" in path
            assert "TR-1.html" in path
        finally:
            monkeypatch.delenv("ARKNIGHTS_DATA_DIR", raising=False)
            importlib.reload(config)

    def test_without_chapter(self, monkeypatch):
        monkeypatch.setenv("ARKNIGHTS_DATA_DIR", "/tmp/fake_data")
        importlib.reload(config)
        try:
            path = get_cache_path("TEST", "special")
            assert "special" in path
            assert "TEST.html" in path
        finally:
            monkeypatch.delenv("ARKNIGHTS_DATA_DIR", raising=False)
            importlib.reload(config)

    def test_uses_data_dir(self):
        path = get_cache_path("NODE", "main")
        assert "data" in path
        assert "stories" in path
        assert path.endswith("NODE.html")


class TestStoryUrlFromId:
    def test_full_url_passthrough(self):
        url = story_url_from_id("test", "https://prts.wiki/w/test/BEG")
        assert url == "https://prts.wiki/w/test/BEG"

    def test_relative_path(self):
        url = story_url_from_id("test", "/w/test/BEG")
        assert url == "https://prts.wiki/w/test/BEG"

    def test_no_url_default(self):
        url = story_url_from_id("test")
        assert "prts.wiki" in url
        assert "test" in url
