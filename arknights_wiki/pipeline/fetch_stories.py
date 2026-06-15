# arknights_wiki/pipeline/fetch_stories.py
"""抓取单个剧情页面 HTML，支持本地缓存"""

import os
import urllib.parse
from typing import Optional

import httpx

from arknights_wiki._utils import ensure_dir, sanitize_filename
from arknights_wiki.config import DATA_DIR


def get_cache_path(story_id: str, category: str, chapter: str = "") -> str:
    """获取故事页面的本地缓存路径 (stories/{category}/{chapter}/{id}.html)"""
    safe_id = sanitize_filename(story_id)
    cat_dir = sanitize_filename(category)
    if chapter:
        chap_dir = sanitize_filename(chapter)
        return os.path.join(DATA_DIR, "stories", cat_dir, chap_dir, f"{safe_id}.html")
    return os.path.join(DATA_DIR, "stories", cat_dir, f"{safe_id}.html")


def story_url_from_id(story_id: str, url: Optional[str] = None) -> str:
    """从节点 ID 和已知 URL 构造完整 URL"""
    if url:
        if url.startswith("https://"):
            return url
        if url.startswith("/"):
            return f"https://prts.wiki{url}"
        encoded = urllib.parse.quote(story_id)
        return f"https://prts.wiki/w/{encoded}/{url}"

    encoded = urllib.parse.quote(story_id)
    return f"https://prts.wiki/w/{encoded}/BEG"


def fetch_story(story_id: str, source_url: str, category: str,
                chapter: str = "", use_cache: bool = True) -> str:
    """抓取单个剧情页面，返回 HTML 文本。若 use_cache=True 且本地缓存存在，直接读取缓存。"""
    cache_path = get_cache_path(story_id, category, chapter)

    if use_cache and os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            return f.read()

    url = story_url_from_id(story_id, source_url)
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    html = resp.text

    ensure_dir(os.path.dirname(cache_path))
    with open(cache_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return html


async def fetch_story_async(story_id: str, source_url: str, category: str,
                            chapter: str = "", use_cache: bool = True) -> str:
    """异步版 fetch_story，用于并发抓取管线"""
    cache_path = get_cache_path(story_id, category, chapter)

    if use_cache and os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            return f.read()

    url = story_url_from_id(story_id, source_url)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        resp.encoding = 'utf-8'
        html = resp.text

    ensure_dir(os.path.dirname(cache_path))
    with open(cache_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return html
