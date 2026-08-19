"""LLM API 调用 + JSON 解析 + 多模型支持"""
import json
import os
import re
import time as time_mod

from openai import OpenAI
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from arknights_wiki.observability import GENERATION_LLM, traced


def strip_think_tags(text: str) -> str:
    """移除 <think>...</think> 标签（MiniMax M3 / DeepSeek R1 等推理模型）"""
    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()


def _repair_json(text: str) -> str:
    """修复 LLM 常见 JSON 错误"""
    try:
        from json_repair import repair_json
        return repair_json(text)
    except ImportError:
        pass
    return text


def parse_llm_response(raw: str) -> dict | None:
    """从 LLM 原始输出中提取 JSON，含修复步骤"""
    text = strip_think_tags(raw).strip()

    candidates = []

    # 直接文本
    candidates.append(text)

    # ```json ... ``` 块
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        candidates.append(m.group(1).strip())

    # { ... } 块
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        candidates.append(m.group(0))

    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass
        try:
            repaired = _repair_json(cand)
            return json.loads(repaired)
        except json.JSONDecodeError:
            continue

    return None


def _volc_config() -> dict:
    """火山引擎 Ark（coding 端点，2026-08-15 实测 deepseek-v4-flash-ga-260731 可用）"""
    key = os.environ.get("arkcode_api", "")
    if not key:
        raise RuntimeError("未设置 arkcode_api 环境变量")
    return {
        "api_key": key,
        "base_url": os.environ.get(
            "ark_api_base", "https://ark.cn-beijing.volces.com/api/coding/v3"
        ),
        "model": os.environ.get("ark_agent_model", "deepseek-v4-flash-ga-260731"),
        "max_tokens": 8192,
    }


def _deepseek_config() -> dict:
    """DeepSeek 官方 API（deepseek-chat 已下线，非思考模式 = deepseek-4-flash）"""
    key = os.environ.get("deepseek_api", "")
    if not key:
        raise RuntimeError("未设置 deepseek_api 环境变量")
    return {
        "api_key": key,
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-4-flash",
        "max_tokens": 8192,  # DeepSeek v4-flash 硬上限
    }


def _minimax_config() -> dict:
    key = os.environ.get("minimax_api", "")
    if not key:
        raise RuntimeError("未设置 minimax_api 环境变量")
    return {
        "api_key": key,
        "base_url": "https://api.minimaxi.com/v1",
        "model": "MiniMax-M3",
        "max_tokens": 32768,
    }


def _get_model_config() -> dict:
    """从环境变量读取模型配置，返回 {api_key, base_url, model, max_tokens}

    2026-08-17 统一模型层（agent 回答 + 意图改写 + 提取共用）:
      - 显式指定: arknights_llm_provider = volcengine | deepseek | minimax
      - 默认优先级: 火山引擎(arkcode_api) > DeepSeek官方(deepseek_api) > MiniMax(minimax_api)
    模型名:
      - 火山: deepseek-v4-flash-ga-260731（ark_agent_model 可覆盖; ark_api_base 可覆盖端点）
      - DeepSeek 官方: deepseek-4-flash（非思考模式; deepseek-chat 已下线）
    """
    provider = os.environ.get("arknights_llm_provider", "").strip().lower()
    if provider in ("volcengine", "volc", "ark"):
        return _volc_config()
    if provider == "deepseek":
        return _deepseek_config()
    if provider == "minimax":
        return _minimax_config()

    if os.environ.get("arkcode_api"):
        return _volc_config()
    if os.environ.get("deepseek_api"):
        return _deepseek_config()
    if os.environ.get("minimax_api"):
        return _minimax_config()
    raise RuntimeError("未设置 arkcode_api / deepseek_api / minimax_api 环境变量")


def create_client() -> OpenAI:
    """创建 LLM API 客户端（自动检测 DeepSeek / MiniMax）

    网络策略（2026-08-18 W4 修复）: 默认直连（trust_env=False）——本机系统代理
    HTTPS_PROXY 常指向未运行的代理端口导致全部请求 10061 失败；
    需要代理时设置 ARKNIGHTS_HTTP_PROXY=http://host:port 显式启用。
    """
    config = _get_model_config()
    import httpx

    proxy = os.environ.get("ARKNIGHTS_HTTP_PROXY", "").strip()
    if proxy:
        http_client = httpx.Client(proxy=proxy, timeout=300.0)
    else:
        http_client = httpx.Client(trust_env=False, timeout=300.0)
    return OpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
        timeout=300.0,
        http_client=http_client,
    )


@traced(name=GENERATION_LLM, as_type="generation")
def chat_completion(
    messages: list[dict],
    temperature: float = 0.1,
    max_tokens: int | None = None,
    tools: list[dict] | None = None,
) -> tuple[str, object]:
    """统一的 LLM 聊天补全封装

    自动创建客户端、读取模型配置，返回 (content, message) 元组。
    调用方根据需求使用 content（纯文本回答）或 message（含 tool_calls 等元信息）。

    W1 Observability: 启用 trace 时每次调用产生一个 `llm_call` generation，
    在内部通过 record_llm_usage 记录 model/tokens/cost/latency。
    W2 Failure Recovery: 对网络/限流/5xx 异常指数退避重试（默认 2 次），
    retries 写入 llm_call generation metadata；4xx 业务错误不重试。
    """
    from arknights_wiki.agent.resilience import ResilienceConfig, retry_call

    config = _get_model_config()
    retry_config = ResilienceConfig(
        timeout_seconds=float(os.environ.get("ARKNIGHTS_LLM_TIMEOUT", "60")),
        max_retries=int(os.environ.get("ARKNIGHTS_LLM_MAX_RETRIES", "2")),
        backoff_base=1.0,
        backoff_max=8.0,
        retryable_exceptions=(APIConnectionError, APITimeoutError, RateLimitError, InternalServerError),
        breaker_threshold=0,  # LLM 调用暂不开熔断（避免误伤全局）
    )

    def _do_create():
        client = create_client()
        return client.chat.completions.create(
            model=config["model"],
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens or config["max_tokens"],
            tools=tools,
        )

    from arknights_wiki.observability import is_enabled, record_llm_usage

    _t0 = time_mod.time()
    response, rstats = retry_call(_do_create, (), {}, retry_config)
    latency_ms = round((time_mod.time() - _t0) * 1000, 1)

    message = response.choices[0].message
    if is_enabled():
        usage = getattr(response, "usage", None)
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0
        from arknights_wiki.observability import compute_cost_rmb

        extra = {"latency_ms": latency_ms, "n_tools": len(tools) if tools else 0}
        if rstats.get("retries"):
            extra["retries"] = rstats["retries"]  # W2: 重试次数入 trace
        record_llm_usage(
            config["model"],
            tokens_in,
            tokens_out,
            compute_cost_rmb(config["model"], tokens_in, tokens_out),
            extra=extra,
        )
    return message.content or "", message


def call_llm(
    client: OpenAI,
    system_prompt: str,
    user_prompt: str,
    max_retries: int = 3,
) -> dict:
    """调用 LLM，自动检测模型配置，超时和 JSON 解析失败自动重试"""
    import time as time_mod
    config = _get_model_config()
    model = config["model"]
    max_tokens = config["max_tokens"]

    last_raw = None
    stats = {}
    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=max_tokens,
                timeout=300.0,
            )
        except Exception as e:
            last_error = str(e)
            wait = 2 ** attempt
            print(f"    [API异常 尝试{attempt+1}/{max_retries}] {last_error[:120]}... {wait}s后重试")
            time_mod.sleep(wait)
            continue

        raw = response.choices[0].message.content or ""
        usage = response.usage
        stats = {
            "tokens_in": usage.prompt_tokens if usage else 0,
            "tokens_out": usage.completion_tokens if usage else 0,
        }

        parsed = parse_llm_response(raw)
        if parsed is not None:
            parsed["_stats"] = stats
            return parsed

        last_raw = raw

    if last_error and not last_raw:
        return {"_parse_error": True, "_error": last_error, "_stats": stats}
    return {"_parse_error": True, "_raw": last_raw, "_stats": stats}
