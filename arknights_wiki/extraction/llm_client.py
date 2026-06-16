# arknights_wiki/extraction/llm_client.py
"""MiniMax M3 API 调用 + JSON 解析 + <think> 标签剥离"""
import json
import os
import re

from openai import OpenAI


def strip_think_tags(text: str) -> str:
    """移除 MiniMax M3 输出的 <think>...</think> 标签"""
    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()


def parse_llm_response(raw: str) -> dict | None:
    """从 LLM 原始输出中提取 JSON"""
    text = strip_think_tags(raw).strip()

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 块
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 尝试提取 { ... } 块
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return None


def create_client() -> OpenAI:
    """创建 MiniMax API 客户端"""
    api_key = os.environ.get("minimax_api", "")
    if not api_key:
        raise RuntimeError("环境变量 minimax_api 未设置")
    return OpenAI(api_key=api_key, base_url="https://api.minimaxi.com/v1")


def call_llm(
    client: OpenAI,
    system_prompt: str,
    user_prompt: str,
    model: str = "MiniMax-M3",
    temperature: float = 0.1,
    max_tokens: int = 16384,
    max_retries: int = 3,
) -> dict:
    """调用 LLM，自动重试 JSON 解析失败"""
    last_raw = None
    stats = {}
    for attempt in range(max_retries):
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
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

    return {"_parse_error": True, "_raw": last_raw, "_stats": stats}
