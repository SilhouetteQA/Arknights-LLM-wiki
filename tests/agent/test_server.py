"""Web Server 测试"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from arknights_wiki.agent.server import app

client = TestClient(app)


class TestChatEndpoint:
    def test_chat_returns_sse_stream(self, temp_data_dir):
        with patch("arknights_wiki.agent.server.DATA_DIR", temp_data_dir):
            with patch("arknights_wiki.agent.server.route_query") as mock_router:
                mock_router.return_value = {
                    "complexity": "simple",
                    "question_type": "worldview",
                    "entities": ["源石"],
                    "time_scope": "cross_arc",
                    "reason": "简单事实查询",
                    "source": "local",
                }
                with patch("arknights_wiki.agent.server.simple_search") as mock_simple:
                    mock_simple.return_value = {
                        "answer": "源石是泰拉世界最核心的能源矿物。",
                        "sources": [{"ref": 1, "entity_type": "concept", "name": "源石"}],
                    }
                    response = client.post("/chat", json={"question": "源石是什么"})
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers["content-type"]

    def test_chat_missing_question(self):
        response = client.post("/chat", json={})
        assert response.status_code == 422

    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
