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


def _consolidated_endpoint() -> dict:
    """judge / search 的统一 provider 解析（**订阅优先**）。

    2026-09-16 实测：原默认端点全部不可用于推理 ——
      - opencode_go（旧 judge/search 默认）: 鉴权通过但推理返回 **429 Too Many Requests**
      - volcengine(arkcode_api): 订阅过期 InvalidSubscription
      - minimax(minimax_api): 配额用尽 429
    因此统一委托 `llm_client._get_model_config()`（command_goat 优先 → DeepSeek 官方），
    不再回退到上述任何网关；两者都不可用时该函数会明确抛错，而不是静默换模型。
    """
    from arknights_wiki.extraction.llm_client import _get_model_config

    cfg = _get_model_config()
    return {"api_key": cfg["api_key"], "base_url": cfg["base_url"], "model": cfg["model"]}


def _use_legacy_opencode() -> bool:
    """是否强制使用旧 opencode 网关。

    **不能**仅凭 ``opencode_go_api`` 存在就判定 —— 该变量在本机环境里始终存在，
    若以它为准会把 opencode 的 key 发给新端点并得到 401（已实测）。必须显式要求：
    设置 ``opencode_go_base``，或 ``arknights_judge_use_opencode=1``。
    """
    if os.environ.get("opencode_go_base", "").strip():
        return True
    return os.environ.get("arknights_judge_use_opencode", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def get_opencode_go_key() -> str:
    """judge/search 的 API key。

    2026-09-16 收敛：默认返回**统一 provider** 的 key（订阅优先）。仅当显式要求旧网关
    （见 :func:`_use_legacy_opencode`）时才回到 HKCU 注册表 / ``opencode_go_api``。
    """
    if _use_legacy_opencode():
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
    return _consolidated_endpoint()["api_key"]


def get_opencode_go_base() -> str:
    """judge/search 的 base URL。仅当显式 ``opencode_go_base`` 时才用旧网关。"""
    if _use_legacy_opencode():
        return os.environ.get("opencode_go_base", OPENCODE_GO_BASE_DEFAULT)
    return _consolidated_endpoint()["base_url"]


def get_ark_api_key() -> str:
    return _get_env("arkcode_api")


def get_firecrawl_key() -> str:
    return _get_env("firecrawl_api")


def get_ark_base() -> str:
    return os.environ.get("ark_api_base", ARK_API_BASE_DEFAULT)


def get_judge_model() -> str:
    """judge 模型。

    2026-09-16 收敛：默认取**统一 provider** 的模型（`deepseek/deepseek-v4.1-flash`），
    因为旧默认 `mimo-v2.5` 只存在于已限流的 opencode 网关上。显式 ``ark_judge_model``
    可覆盖（例如该网关恢复后要重新启用 agent/judge 模型分离以缓解自评偏差）。
    """
    explicit = os.environ.get("ark_judge_model", "")
    if explicit:
        return explicit
    return _consolidated_endpoint()["model"]


def get_search_model() -> str:
    """search/生成模型。同样收敛到统一 provider；显式 ``ark_search_model`` 可覆盖。"""
    explicit = os.environ.get("ark_search_model", "")
    if explicit:
        return explicit
    return _consolidated_endpoint()["model"]


def get_firecrawl_base() -> str:
    return os.environ.get("firecrawl_base", FIRE_CRAWL_API_DEFAULT)
