"""T1: eval 配置层测试（进程环境 → HKCU 注册表回退）"""
import sys
from unittest.mock import patch

from arknights_wiki.eval import config


class TestEnvRead:
    def test_process_env_wins(self, monkeypatch):
        monkeypatch.setenv("arkcode_api", "sk-process")
        assert config.get_ark_api_key() == "sk-process"

    def test_empty_env_falls_back_to_registry(self, monkeypatch):
        monkeypatch.delenv("arkcode_api", raising=False)
        import winreg

        with patch.object(winreg, "OpenKey") as mock_open, patch.object(
            winreg, "QueryValueEx"
        ) as mock_q:
            mock_q.return_value = ("sk-registry", 1)
            assert config.get_ark_api_key() == "sk-registry"
            mock_open.assert_called_once()

    def test_registry_exception_returns_empty(self, monkeypatch):
        monkeypatch.delenv("arkcode_api", raising=False)
        import winreg

        with patch.object(winreg, "OpenKey", side_effect=OSError):
            assert config.get_ark_api_key() == ""

    def test_defaults(self):
        assert config.get_ark_base().startswith("https://")
        assert config.get_judge_model()  # 非空默认
        assert config.get_search_model()  # 非空默认

    def test_override_via_env(self, monkeypatch):
        monkeypatch.setenv("ark_judge_model", "custom-model")
        assert config.get_judge_model() == "custom-model"
