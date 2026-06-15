# arknights_wiki/pipeline/orchestrate.py
"""增量批次控制管线 —— 编排剧情抓取 + 干员数据提取"""

import asyncio
import copy
import json
import os
from datetime import datetime, timezone

from arknights_wiki._utils import read_json, write_json, compute_hash
from arknights_wiki.config import DATA_DIR
from arknights_wiki.pipeline.fetch_index import fetch_index, index_to_batch_state
from arknights_wiki.pipeline.fetch_stories import fetch_story, fetch_story_async
from arknights_wiki.pipeline.parse_dialogue import parse_story_html, save_story_json
from arknights_wiki.pipeline.gen_markdown import generate_all_markdown
from arknights_wiki.pipeline.fetch_operators import fetch_operators_full
from arknights_wiki.pipeline.gen_operators_md import generate_all_operators_markdown


def init_pipeline() -> dict:
    """初始化管线：抓取剧情索引 + 干员数据，建立批次状态"""
    print("=== Phase 1: 原始内容提取 ===\n")

    # 1. 剧情索引
    print("[剧情] 抓取剧情一览索引页 ...")
    nodes = fetch_index()
    batch_state = index_to_batch_state(nodes)
    batch_path = os.path.join(DATA_DIR, "batch_state.json")
    write_json(batch_path, batch_state)
    print(f"  发现 {len(nodes)} 个剧情节点\n")

    # 2. 干员数据
    print("[干员] 开始抓取干员数据 ...")
    fetch_operators_full()
    generate_all_operators_markdown()
    print()

    # 3. metadata
    metadata = {
        "last_fetch": datetime.now(timezone.utc).isoformat(),
        "index_version": "",
        "stats": {
            "total_nodes": len(nodes),
            "fetched": 0,
            "pending": len(nodes),
        },
        "node_hashes": {},
    }
    write_json(os.path.join(DATA_DIR, "metadata.json"), metadata)

    return batch_state


def _select_batch_nodes(state: dict, count: int,
                        chapter_filter: str | None = None) -> list:
    """从 pending_ordered 中选择待抓取节点，支持章节过滤"""
    node_map = {}
    if chapter_filter is not None:
        index_path = os.path.join(DATA_DIR, "index.json")
        if os.path.exists(index_path):
            index_data = read_json(index_path)
            node_map = {n["id"]: n for n in index_data["nodes"]}

    pending = []
    for nid in state["pending_ordered"]:
        if chapter_filter is None:
            pending.append(nid)
        elif nid in node_map and node_map[nid].get("chapter", "") == chapter_filter:
            pending.append(nid)
        if len(pending) >= count:
            break

    return pending


def _fetch_single(node_id: str, node_map: dict, metadata: dict) -> tuple[str | None, str | None]:
    """抓取单个节点（同步版）"""
    if node_id not in node_map:
        return None, "节点不在索引中"
    node = node_map[node_id]

    try:
        html_text = fetch_story(
            node_id, node["source_url"], node["category"], node["chapter"]
        )
        story = parse_story_html(
            html_text, node_id, node["title"], node["chapter"],
            node["category"], node["source_url"],
        )
        save_story_json(story)
        raw_text = json.dumps(story["lines"], ensure_ascii=False)
        metadata["node_hashes"][node_id] = compute_hash(raw_text)
        return node_id, None
    except Exception as e:
        return node_id, str(e)


async def _fetch_single_async(node_id: str, node_map: dict,
                              metadata: dict) -> tuple[str | None, str | None]:
    """异步抓取单个节点"""
    if node_id not in node_map:
        return None, "节点不在索引中"
    node = node_map[node_id]

    try:
        html_text = await fetch_story_async(
            node_id, node["source_url"], node["category"], node["chapter"]
        )
        story = parse_story_html(
            html_text, node_id, node["title"], node["chapter"],
            node["category"], node["source_url"],
        )
        save_story_json(story)
        raw_text = json.dumps(story["lines"], ensure_ascii=False)
        metadata["node_hashes"][node_id] = compute_hash(raw_text)
        return node_id, None
    except Exception as e:
        return node_id, str(e)


def fetch_next_batch(count: int = 10, chapter_filter: str | None = None,
                     workers: int = 10) -> dict:
    """异步并发抓取下一批剧情节点"""
    batch_path = os.path.join(DATA_DIR, "batch_state.json")
    metadata_path = os.path.join(DATA_DIR, "metadata.json")

    state = read_json(batch_path)
    metadata = read_json(metadata_path)
    index_data = read_json(os.path.join(DATA_DIR, "index.json"))
    node_map = {n["id"]: n for n in index_data["nodes"]}

    batch_nodes = _select_batch_nodes(state, count, chapter_filter)

    if not batch_nodes:
        if chapter_filter:
            print(f"  没有找到章节 [{chapter_filter}] 的待抓取节点")
        else:
            print("  没有待抓取节点")
        return {"fetched": 0, "nodes": []}

    filter_info = f" (章节: {chapter_filter})" if chapter_filter else ""
    actual_workers = min(workers, len(batch_nodes))
    print(f"  异步并发抓取 {len(batch_nodes)} 个节点{filter_info}，{actual_workers} 路并发...")

    meta_copies = {i: copy.deepcopy(metadata) for i in range(len(batch_nodes))}

    async def _run():
        sem = asyncio.Semaphore(actual_workers)

        async def _bounded(nid, i):
            async with sem:
                return await _fetch_single_async(nid, node_map, meta_copies[i])

        tasks = [_bounded(nid, i) for i, nid in enumerate(batch_nodes)]
        return await asyncio.gather(*tasks, return_exceptions=True)

    results = asyncio.run(_run())

    fetched_node_ids = []
    for result in results:
        if isinstance(result, Exception):
            print(f"  抓取异常: {result}")
            continue
        nid, err = result
        if err:
            print(f"  抓取失败: {nid} - {err}")
        elif nid:
            fetched_node_ids.append(nid)
            print(f"  + {nid}")

    for mc in meta_copies.values():
        metadata["node_hashes"].update(mc.get("node_hashes", {}))

    fetched_set = set(fetched_node_ids)
    state["pending_ordered"] = [
        nid for nid in state["pending_ordered"] if nid not in fetched_set
    ]
    state["fetched_nodes"] = state.get("fetched_nodes", 0) + len(fetched_node_ids)
    prev_batch_num = state.get("current_batch", {}).get("number", 0) if state.get("current_batch") else 0
    state["current_batch"] = {
        "number": prev_batch_num + 1,
        "nodes": fetched_node_ids,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    state["next_batch_available"] = len(state["pending_ordered"]) > 0

    write_json(batch_path, state)

    metadata["last_fetch"] = datetime.now(timezone.utc).isoformat()
    metadata["stats"]["fetched"] = state["fetched_nodes"]
    metadata["stats"]["pending"] = len(state["pending_ordered"])
    write_json(metadata_path, metadata)

    generate_all_markdown()

    return {
        "fetched": len(fetched_node_ids),
        "nodes": fetched_node_ids,
    }
