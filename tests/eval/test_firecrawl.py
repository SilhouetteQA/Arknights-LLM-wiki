"""T2: Firecrawl 搜索封装测试（mock httpx）"""
from unittest.mock import MagicMock, patch

import pytest

from arknights_wiki.eval import firecrawl


class TestFirecrawl:
    @patch("arknights_wiki.eval.config.get_firecrawl_key", return_value="fc-x")
    @patch("arknights_wiki.eval.firecrawl.httpx.post")
    def test_search_success(self, mock_post, _key):
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = {
            "data": [
                {"title": "条目A", "url": "https://example.com/a", "markdown": "内容" * 1000},
                {"title": "条目B", "url": "https://example.com/b", "content": "短内容"},
            ]
        }
        mock_post.return_value = fake
        results = firecrawl.search("德克萨斯 企鹅物流")
        assert len(results) == 2
        assert results[0]["title"] == "条目A"
        assert len(results[0]["content"]) <= 2000

    @patch("arknights_wiki.eval.config.get_firecrawl_key", return_value="")
    def test_missing_key_raises(self, _):
        with pytest.raises(RuntimeError, match="firecrawl_api"):
            firecrawl.search("q")
