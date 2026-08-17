"""eval 包配置：环境变量读取（进程环境 → HKCU 注册表回退）

接入的密钥全部通过环境变量引用（不硬编码、不落盘）：
- opencode_go_api : opencode zen/go 网关 API key（**只读注册表**，2026-08-17 用户指定；
                    进程环境同名变量为另一 key，弃用）
- arkcode_api     : 火山引擎 Ark API key（旧 judge 端点，保留兼容）
- firecrawl_api   : Firecrawl 搜索 key
- opencode_go_base: opencode 网关 base URL（默认 https://opencode.ai/zen/go/v1）
- ark_judge_model / ark_search_model : 可选覆盖模型
"""
from __future__ import annotations

import os

# opencode zen/go 网关（2026-08-17 起 judge 默认端点，mimo-v2.5 实测可用）
OPENCODE_GO_BASE_DEFAULT = "https://opencode.ai/zen/go/v1"
ARK_API_BASE_DEFAULT = "https://ark.cn-beijing.volces.com/api/coding/v3"
# 2026-08-15 实测：coding 端点仅部分模型可用（flash 系 404 UnsupportedModel）
# 2026-08-17: judge 默认切 mimo-v2.5（opencode 网关，JSON 判分/长上下文实测可用，延迟 8-15s）
ARK_JUDGE_MODEL_DEFAULT = "mimo-v2.5"
# 搜索/生成用模型（opencode 网关；qwen 系列 503 不可用，minimax-m3 实测可用且与 judge 分离避免自评估偏差）
ARK_SEARCH_MODEL_DEFAULT = "minimax-m3"
FIRE_CRAWL_API_DEFAULT = "https://api.firecrawl.dev/v2"


def _get_env(name: str) -> str:
    """读取环境变量：进程环境优先，Windows 回退 HKCU 用户级注册表。

    场景：DSH/服务进程启动早于用户设置变量时，进程环境可能缺失，
    但注册表（HKCU:\\Environment）是权威的用户环境来源。
    """
    value = os.environ.get(name, "")
    if value:
        return value
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        try:
            value, _ = winreg.QueryValueEx(key, name)
            return value if isinstance(value, str) else ""
        finally:
            key.Close()
    except Exception:
        return ""
    return ""


def get_opencode_go_key() -> str:
    """读 opencode zen/go 网关 key。

    2026-08-17 用户指定：宿主用 **HKCU 注册表**值（进程环境同名 OPENCODE_GO_API
    是另一 key，弃用）。Linux Docker 容器内无注册表 → 回退进程环境
    （docker run -e opencode_go_api=<注册表值> 显式传入同一 key）。
    """
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        try:
            value, _ = winreg.QueryValueEx(key, "opencode_go_api")
            if isinstance(value, str) and value:
                return value
        finally:
            key.Close()
    except Exception:
        pass
    return os.environ.get("opencode_go_api", "")


def get_opencode_go_base() -> str:
    return os.environ.get("opencode_go_base", OPENCODE_GO_BASE_DEFAULT)


def get_ark_api_key() -> str:
    return _get_env("arkcode_api")


def get_firecrawl_key() -> str:
    return _get_env("firecrawl_api")


def get_ark_base() -> str:
    return os.environ.get("ark_api_base", ARK_API_BASE_DEFAULT)


def get_judge_model() -> str:
    return os.environ.get("ark_judge_model", ARK_JUDGE_MODEL_DEFAULT)


def get_search_model() -> str:
    return os.environ.get("ark_search_model", ARK_SEARCH_MODEL_DEFAULT)


def get_firecrawl_base() -> str:
    return os.environ.get("firecrawl_base", FIRE_CRAWL_API_DEFAULT)
