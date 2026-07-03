"""LLM API 调用 + JSON 解析 + 多模型支持"""
import json
import os
import re

from openai import OpenAI


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


def _get_model_config() -> dict:
    """从环境变量读取模型配置，返回 {api_key, base_url, model, max_tokens}"""
    # 优先 DeepSeek
    deepseek_key = os.environ.get("deepseek_api", "")
    if deepseek_key:
        return {
            "api_key": deepseek_key,
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "max_tokens": 8192,  # DeepSeek v4-flash 硬上限
        }
    # 回退 MiniMax
    minimax_key = os.environ.get("minimax_api", "")
    if minimax_key:
        return {
            "api_key": minimax_key,
            "base_url": "https://api.minimaxi.com/v1",
            "model": "MiniMax-M3",
            "max_tokens": 32768,
        }
    raise RuntimeError("未设置 deepseek_api 或 minimax_api 环境变量")


def create_client() -> OpenAI:
    """创建 LLM API 客户端（自动检测 DeepSeek / MiniMax）"""
    config = _get_model_config()
    return OpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
        timeout=300.0,
    )


def chat_completion(
    messages: list[dict],
    temperature: float = 0.1,
    max_tokens: int | None = None,
    tools: list[dict] | None = None,
) -> tuple[str, object]:
    """统一的 LLM 聊天补全封装

    自动创建客户端、读取模型配置，返回 (content, message) 元组。
    调用方根据需求使用 content（纯文本回答）或 message（含 tool_calls 等元信息）。
    """
    client = create_client()
    config = _get_model_config()
    response = client.chat.completions.create(
        model=config["model"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens or config["max_tokens"],
        tools=tools,
    )
    message = response.choices[0].message
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
