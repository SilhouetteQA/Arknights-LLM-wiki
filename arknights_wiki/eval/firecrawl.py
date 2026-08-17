"""Firecrawl 搜索封装：自动搜索验证答案（免费模型驱动，不走人工逐条搜索）"""
from __future__ import annotations

import time

import httpx

from . import config


def search(query: str, limit: int = 5, timeout: float = 60.0) -> list[dict]:
    """Firecrawl v2 /search。返回 [{title, url, content}]，content 截断 2000 字符。"""
    api_key = config.get_firecrawl_key()
    if not api_key:
        raise RuntimeError("未设置 firecrawl_api 环境变量")
    url = config.get_firecrawl_base().rstrip("/") + "/search"
    payload = {"query": query, "limit": limit, "lang": "zh"}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    t0 = time.monotonic()
    resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    results: list[dict] = []
    for item in data.get("data", []):
        content = item.get("markdown") or item.get("content") or ""
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": content[:2000],
            }
        )
    return results


def search_cost_info() -> dict:
    """返回搜索计费信息（供 cost_log 记录）。"""
    return {"step": "firecrawl_search", "per_call": "tbd", "latency_ms": None}
