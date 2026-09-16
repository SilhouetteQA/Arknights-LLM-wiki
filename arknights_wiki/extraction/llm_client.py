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


def _command_goat_config() -> dict:
    """commandcode 网关（订阅制，**默认首选**）。

    2026-09-16 实测：``POST /chat/completions`` 成功。模型 ID **必须**带 ``deepseek/``
    命名空间前缀 —— 裸名 ``deepseek-v4.1-flash`` 会被该端点以 ``unsupported_model`` 拒绝。
    """
    key = os.environ.get("command_goat_api", "")
    if not key:
        raise RuntimeError("未设置 command_goat_api 环境变量")
    return {
        "api_key": key,
        "base_url": os.environ.get(
            "command_goat_base", "https://api.commandcode.ai/provider/v1"
        ),
        "model": os.environ.get("command_goat_model", "deepseek/deepseek-v4.1-flash"),
        "max_tokens": 8192,
    }


def _volc_config() -> dict:
    """火山引擎 Ark —— **已退役，不在默认回退链内**。

    2026-09-16 实测该账号订阅过期（``InvalidSubscription``）。保留此函数仅供显式
    ``arknights_llm_provider=volcengine`` 的调用方使用；**不得**再作为静默 fallback，
    否则过期凭据会被自动选中并掩盖真实故障。
    """
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
    """DeepSeek 官方 API（回退档）。

    2026-09-16 实测 ``GET /models`` 只返回 ``['deepseek-flash', 'deepseek-v4-pro']``：
    旧名 ``deepseek-4-flash`` 已不被接受，且该 API **没有** ``v4.1-flash``。因此本档使用
    ``deepseek-flash`` —— 这是**替代**（command_goat 才是 ``deepseek-v4.1-flash``），
    两者 ID 不等价，不得混用。
    """
    key = os.environ.get("deepseek_api", "")
    if not key:
        raise RuntimeError("未设置 deepseek_api 环境变量")
    return {
        "api_key": key,
        "base_url": os.environ.get("deepseek_base", "https://api.deepseek.com/v1"),
        "model": os.environ.get("deepseek_model", "deepseek-flash"),
        "max_tokens": 8192,  # DeepSeek flash 档硬上限
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

    2026-09-16 统一模型层（agent 回答 + 意图改写 + 提取共用）:
      - 显式指定: arknights_llm_provider = command_goat | deepseek
      - 默认优先级（**订阅优先**）: command_goat_api > deepseek_api
      - **已退役**（不再进入回退链）: volcengine(arkcode_api) 订阅过期、minimax(minimax_api) 配额用尽
    模型名:
      - command_goat: deepseek/deepseek-v4.1-flash（command_goat_model 可覆盖; command_goat_base 可覆盖端点）
      - DeepSeek 官方: deepseek-flash（deepseek_model 可覆盖; deepseek_base 可覆盖端点）
        —— 该 API 没有 v4.1-flash，故为**替代**，与 command_goat 的 ID 不等价

    两者都不可用时**必须**明确报错，不得回退到已退役 provider 或静默换模型。
    """
    provider = os.environ.get("arknights_llm_provider", "").strip().lower()
    if provider in ("command_goat", "commandgoat", "command_code", "commandcode"):
        return _command_goat_config()
    if provider == "deepseek":
        return _deepseek_config()
    # 退役 provider 仅允许显式指定，避免过期/无配额凭据被静默选中
    if provider in ("volcengine", "volc", "ark"):
        return _volc_config()
    if provider == "minimax":
        return _minimax_config()

    if os.environ.get("command_goat_api"):
        return _command_goat_config()
    if os.environ.get("deepseek_api"):
        return _deepseek_config()
    raise RuntimeError(
        "未设置 command_goat_api / deepseek_api 环境变量；"
        "已退役的 arkcode_api(volcengine 订阅过期) 与 minimax_api(配额用尽) 不再作为回退"
    )


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


def _observe_chat_completion(response: object, model: str) -> None:
    """把一次成功的模型响应旁路交给 Foundation runtime（Spec 07 seam）。

    行为保持：不返回值、不改业务状态、不改下面的 Langfuse 分支。

    - ``off``：最外层短路，连 facts 提取都不发生（也不触发 pricing 加载）
    - ``observe``：映射/落盘失败都被 runtime 吞掉，业务返回不变
    - ``strict``：契约失败按设计冒泡，令验证命令失败

    cost 只在 provider **明确报告 usage** 时按既有 ``compute_cost_rmb`` 取同一个数值；
    usage 缺失时传 ``None``（unknown），而不是沿用 ``usage else 0`` 产生的 ambiguous zero。
    """
    from arknights_wiki.adapters.foundation.runtime import get_foundation_runtime

    runtime = get_foundation_runtime()
    if not runtime.accepts_observation:
        return

    cost_amount: float | None = None
    usage = getattr(response, "usage", None)
    if usage is not None:
        from arknights_wiki.observability import compute_cost_rmb

        cost_amount = compute_cost_rmb(
            model,
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
        )

    runtime.observe_chat_completion(
        response, model=model, stage="chat_completion", cost_amount=cost_amount
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

    # Spec 07 旁路观察：成功响应后、Legacy coercion / Trace 之前提取 presence facts。
    # 刻意放在 is_enabled() 之前 —— Foundation 观察不以 Langfuse 开启为前提。
    _observe_chat_completion(response, config["model"])

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
