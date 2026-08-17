"""火山引擎 Ark（OpenAI 兼容）LLM 客户端：调用 + 成本记录 + JSON 解析

复用 extraction/llm_client.py 的成熟解析模式（剥 think 标签 → json 块 → json_repair）。
每次调用返回结构化结果：content / tokens_in / tokens_out / cost / latency_ms。
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import httpx

from . import config

_PRICING_CACHE: dict | None = None


def _load_pricing() -> dict:
    global _PRICING_CACHE
    if _PRICING_CACHE is None:
        path = Path(__file__).parent / "pricing.json"
        _PRICING_CACHE = json.loads(path.read_text(encoding="utf-8"))
    return _PRICING_CACHE


def compute_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """按单价表计算成本（人民币）。未知单价记 0（报告会标注 tbd）。"""
    price = _load_pricing().get(model)
    if not price:
        return 0.0
    p_in, p_out = price.get("in"), price.get("out")
    if p_in in (None, "tbd") or p_out in (None, "tbd"):
        return 0.0
    return tokens_in / 1e6 * p_in + tokens_out / 1e6 * p_out


def strip_think_tags(text: str) -> str:
    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()


def _repair_json(text: str) -> str:
    try:
        from json_repair import repair_json

        return repair_json(text)
    except ImportError:
        pass
    return text


def parse_llm_json(raw: str) -> dict | None:
    """从 LLM 原始输出提取 JSON（复用 llm_client 候选解析模式）"""
    text = strip_think_tags(raw).strip()
    candidates = [text]
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        candidates.append(m.group(1).strip())
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        candidates.append(m.group(0))
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(_repair_json(cand))
        except json.JSONDecodeError:
            continue
    return None


def chat(
    model: str,
    messages: list[dict],
    temperature: float = 0.1,
    max_tokens: int = 4096,
    max_retries: int = 2,
    json_mode: bool = False,
    timeout: float = 300.0,
) -> dict:
    """调用火山引擎 chat.completions，返回结果字典。

    Raises RuntimeError：连续 max_retries+1 次失败。
    """
    api_key = config.get_opencode_go_key()
    if not api_key:
        raise RuntimeError("未设置 opencode_go_api（HKCU 注册表，2026-08-17 起 judge 走 opencode zen/go 网关）")
    url = config.get_opencode_go_base().rstrip("/") + "/chat/completions"
    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    last_error = None
    for attempt in range(max_retries + 1):
        t0 = time.monotonic()
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            usage = data.get("usage", {})
            tokens_in = int(usage.get("prompt_tokens", 0) or 0)
            tokens_out = int(usage.get("completion_tokens", 0) or 0)
            return {
                "content": content,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost": compute_cost(model, tokens_in, tokens_out),
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                "model": model,
            }
        except Exception as e:  # noqa: BLE001
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"LLM 调用失败（{max_retries + 1} 次尝试）: {last_error}")


def chat_json(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    max_retries: int = 2,
) -> dict:
    """调用 LLM 并要求 JSON 输出，返回 {parsed, **stats}；解析失败重试，最终解析失败抛 RuntimeError。"""
    last_raw = None
    stats: dict = {}
    for attempt in range(max_retries + 1):
        result = chat(
            model,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            json_mode=True,
        )
        stats = {
            "tokens_in": result["tokens_in"],
            "tokens_out": result["tokens_out"],
            "cost": result["cost"],
            "latency_ms": result["latency_ms"],
            "model": result["model"],
        }
        parsed = parse_llm_json(result["content"])
        if parsed is not None:
            parsed["_stats"] = stats
            return parsed
        last_raw = result["content"]
    raise RuntimeError(f"LLM JSON 解析失败（{max_retries + 1} 次）: raw={last_raw[:200]!r}")


def env_or(key: str, default: str) -> str:
    """读取进程环境变量（无注册表回退），供测试覆盖。"""
    return os.environ.get(key, default)
