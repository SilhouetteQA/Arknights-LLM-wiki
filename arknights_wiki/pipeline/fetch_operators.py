# arknights_wiki/pipeline/fetch_operators.py
"""从 PRTS Wiki 提取干员人物信息 + 个人页档案文本"""

import asyncio
import html as _html_mod
import os
import re
from datetime import datetime, timezone

import httpx

from arknights_wiki._utils import ensure_dir, sanitize_filename, write_json
from arknights_wiki.config import DATA_DIR, OPERATOR_LIST_URL, OPERATOR_DATA_ATTR_MAP

_RE_OPERATOR_DIV = re.compile(r'<div\s+([^>]*data-id="[^"]+"[^>]*)>')


def _extract_data_attrs(html_text: str) -> list[dict]:
    """从 HTML 中提取所有干员的 data-* 属性，仅保留白名单字段"""
    operators = []
    for match in _RE_OPERATOR_DIV.finditer(html_text):
        attr_str = match.group(1)
        attrs = dict(re.findall(r'data-(\w+)="([^"]*)"', attr_str))
        op = {}
        for data_key, field_name in OPERATOR_DATA_ATTR_MAP.items():
            attr_name = data_key.replace("data-", "")
            if attr_name in attrs:
                op[field_name] = _html_mod.unescape(attrs[attr_name])
        if "id" in op and "name_zh" in op:
            operators.append(op)
    return operators


def fetch_operator_list() -> list[dict]:
    """从干员一览页提取所有干员人物信息"""
    resp = httpx.get(OPERATOR_LIST_URL, timeout=30, follow_redirects=True)
    resp.encoding = 'utf-8'
    return _extract_data_attrs(resp.text)


def parse_operator_page(html_text: str) -> dict[str, str]:
    """从干员个人页 HTML 解析「干员档案」节，返回 {档案项标题: 纯文本内容}"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_text, 'lxml')
    archives = {}

    # 定位「干员档案」h2：mw-headline 的 id 可能是中文或 URL 编码两种形式
    archive_h2 = None
    for span in soup.find_all('span', class_='mw-headline'):
        span_id = span.get('id', '')
        if '干员档案' in span_id or '档案' in span_id:
            archive_h2 = span.find_parent('h2')
            if archive_h2:
                break
    if not archive_h2:
        return archives

    current = archive_h2.next_sibling
    current_title = None
    current_lines = []

    while current:
        if current.name == 'h2':
            if current_title and current_lines:
                archives[current_title] = "\n".join(current_lines).strip()
            break

        if current.name == 'h3':
            if current_title and current_lines:
                archives[current_title] = "\n".join(current_lines).strip()
            span = current.find('span', class_='mw-headline')
            current_title = span.get_text(strip=True) if span else current.get_text(strip=True)
            current_lines = []
        elif current.name in ('p', 'div', 'table', 'ul', 'ol'):
            text = current.get_text().strip()
            if text:
                current_lines.append(text)
            for child in current.find_all(['p', 'li'], recursive=False):
                child_text = child.get_text().strip()
                if child_text:
                    current_lines.append(child_text)

        current = current.next_sibling

    if current_title and current_lines:
        archives[current_title] = "\n".join(current_lines).strip()

    return archives


def _operator_page_url(name_zh: str) -> str:
    """构造干员个人页 URL"""
    import urllib.parse
    encoded = urllib.parse.quote(name_zh)
    return f"https://prts.wiki/w/{encoded}"


def get_operator_cache_path(name_zh: str) -> str:
    """获取干员个人页本地缓存路径"""
    safe_name = sanitize_filename(name_zh)
    return os.path.join(DATA_DIR, "operators", "pages", f"{safe_name}.html")


async def fetch_operator_page_async(name_zh: str, use_cache: bool = True) -> str | None:
    """异步抓取单个干员个人页 HTML"""
    cache_path = get_operator_cache_path(name_zh)

    if use_cache and os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            return f.read()

    url = _operator_page_url(name_zh)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            resp.encoding = 'utf-8'
            html_text = resp.text
    except Exception:
        return None

    ensure_dir(os.path.dirname(cache_path))
    with open(cache_path, 'w', encoding='utf-8') as f:
        f.write(html_text)

    return html_text


async def fetch_all_archives(operators: list[dict],
                             max_concurrent: int = 10) -> list[dict]:
    """并发抓取所有干员的个人页档案文本"""
    sem = asyncio.Semaphore(max_concurrent)

    async def _fetch_one(op: dict):
        async with sem:
            name_zh = op.get("name_zh", "")
            if not name_zh:
                return op
            html_text = await fetch_operator_page_async(name_zh)
            if html_text:
                op["archives"] = parse_operator_page(html_text)
            else:
                op["archives"] = {}
            return op

    tasks = [_fetch_one(op) for op in operators]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    final = []
    for r in results:
        if isinstance(r, Exception):
            continue
        final.append(r)

    return final


def save_operators_json(operators: list[dict], output_path: str = None) -> str:
    """保存干员数据到 data/operators.json"""
    if output_path is None:
        output_path = os.path.join(DATA_DIR, "operators.json")

    data = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_list_url": OPERATOR_LIST_URL,
        "total": len(operators),
        "operators": operators,
    }
    write_json(output_path, data)
    return output_path


def fetch_operators_full() -> list[dict]:
    """同步入口：抓取一览页 + 异步抓取全部个人页档案"""
    print("  抓取干员一览页 ...")
    operators = fetch_operator_list()
    print(f"  发现 {len(operators)} 个干员")

    print("  抓取干员个人页档案 (异步并发) ...")
    operators = asyncio.run(fetch_all_archives(operators))

    has_archives = sum(1 for op in operators if op.get("archives"))
    print(f"  档案获取: {has_archives}/{len(operators)} 个干员")

    path = save_operators_json(operators)
    print(f"  保存: {path}")
    return operators
