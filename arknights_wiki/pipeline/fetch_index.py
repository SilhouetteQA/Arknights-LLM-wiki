# arknights_wiki/pipeline/fetch_index.py
"""抓取"剧情一览"索引页面，解析为结构化 index.json"""

import re

import httpx
from bs4 import BeautifulSoup

from arknights_wiki._utils import normalize_url, write_json
from arknights_wiki.config import DATA_DIR, INDEX_URL

CATEGORY_LABEL_MAP = {
    "主线": "main",
    "插曲": "intermezzi",
    "干员密录": "operator_records",
    "活动": "side",
    "剧情": "special",
}

EXCLUDE_URL_PATTERNS = [
    "/%E5%88%86%E7%B1%BB:",  # 分类页
    "/PRTS:",                # 项目页
    "/%E7%89%B9%E6%AE%8A:",  # 特殊页
]


def _is_story_link(href: str) -> bool:
    """判断是否为剧情页面链接（排除分类页、项目页等）"""
    if '/w/' not in href:
        return False
    for pattern in EXCLUDE_URL_PATTERNS:
        if pattern in href:
            return False
    return True


def parse_index_html(html: str) -> list[dict]:
    """解析索引页 HTML（表格结构），返回去重后的剧情节点列表"""
    soup = BeautifulSoup(html, 'lxml')
    nodes = []
    seen_urls = set()

    content = soup.find('div', class_='mw-parser-output')
    if not content:
        return nodes

    current_section_category = "main"

    for table in content.find_all('table'):
        rows = table.find_all('tr')
        if not rows:
            continue

        first_row_text = rows[0].get_text(strip=True)

        # 只处理有明确剧情分类标题的表格
        if "主线剧情" in first_row_text:
            current_section_category = "main"
            start_row = 1
        elif "活动剧情" in first_row_text or "支线故事" in first_row_text:
            current_section_category = "side"
            start_row = 1
        elif "插曲剧情" in first_row_text:
            current_section_category = "intermezzi"
            start_row = 1
        elif "干员密录" in first_row_text:
            current_section_category = "operator_records"
            start_row = 1
        else:
            continue

        for row in rows[start_row:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 2:
                continue

            chapter = cells[0].get_text(strip=True)
            if not chapter:
                continue

            category_label = cells[1].get_text(strip=True)
            category = CATEGORY_LABEL_MAP.get(category_label, current_section_category)

            for link in row.find_all('a'):
                href = link.get('href', '')
                if not _is_story_link(href):
                    continue

                text = link.get_text(strip=True)
                if not text:
                    continue

                full_url = normalize_url(href)
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                nodes.append({
                    "id": text,
                    "title": text,
                    "chapter": chapter,
                    "category": category,
                    "source_url": full_url,
                })

    return nodes


def fetch_index(output_path: str = None) -> list[dict]:
    """从网络抓取索引页并解析"""
    resp = httpx.get(INDEX_URL, timeout=30, follow_redirects=True)
    resp.encoding = 'utf-8'
    html = resp.text

    version_match = re.search(r'最近一次刷新时间：([\d-]+\s[\d:]+)', html)
    version = version_match.group(1) if version_match else ""

    nodes = parse_index_html(html)

    if output_path is None:
        output_path = f"{DATA_DIR}/index.json"

    write_json(output_path, {
        "source_url": INDEX_URL,
        "version": version,
        "fetched_at": "",
        "total": len(nodes),
        "nodes": nodes,
    })

    return nodes


def index_to_batch_state(nodes: list[dict]) -> dict:
    """从节点列表生成初始 batch_state"""
    pending = [n["id"] for n in nodes]
    return {
        "total_nodes": len(nodes),
        "fetched_nodes": 0,
        "pending_ordered": pending,
        "current_batch": None,
        "next_batch_available": len(pending) > 0,
    }
