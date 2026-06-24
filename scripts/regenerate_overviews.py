"""
Phase 3.5: 用剧情事件 + 原文片段重写实体概述
对每个 faction/concept/location，将其 story_events 和对应章节原文
喂给 LLM，生成一份有剧情深度的新概述替换纯大地巡旅版 summary。
"""

import json
import os
import sys
import re
import time as time_mod
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))
from arknights_wiki.extraction.llm_client import create_client, call_llm

PROJECT_ROOT = Path(__file__).parent.parent

SYSTEM_PROMPT = """你是泰拉世界的设定编纂者。你的任务是基于已有的剧情事件列表和原文摘录，
为一个世界观实体（国家/势力/概念/地点）撰写一份 **概述（Overview）**。

要求:
1. 概述需涵盖该实体在剧情中的**核心定位**、**关键事件脉络**、**内部矛盾或演变趋势**
2. 不要罗列事件——要**合成**成连贯的叙述段落
3. 保留大地巡旅中关于该实体的**基本定义**（地理位置、制度特征等）
4. 篇幅控制在 300-800 字（中文），视该实体复杂度而定

输出格式: 严格输出如下 JSON 结构:
{"overview": "合成的概述全文（纯文本，用 \\n 表示段落分隔）"}"""

USER_PROMPT_TEMPLATE = """请为泰拉世界的实体「{entity_name}」（类别: {category}）撰写概述。

当前定义: {definition}

当前概述（来自大地巡旅等设定集，缺乏剧情综合）:
{current_summary}

以下是从剧情章节中提取的相关事件（已结构化）:
{events_text}

以下是与部分事件相关的原文摘录（从原始章节提取）:
{source_excerpts}

请基于以上信息，撰写一份新的概述，综合设定集信息和剧情事件脉络。
输出 JSON: {{"overview": "..."}}"""


def load_story_text(chapter_path: Path) -> str:
    """加载章节原文，提取所有对话文本"""
    if not chapter_path.exists():
        return ""
    try:
        data = json.loads(chapter_path.read_text(encoding='utf-8'))
        lines = data.get("lines", [])
        texts = []
        for line in lines:
            speaker = line.get("speaker", "")
            text = line.get("text", "")
            if text.strip():
                texts.append(f"[{speaker}]: {text}")
        return "\n".join(texts)
    except Exception:
        return ""


def find_chapter_dir(chapter_name: str) -> Path | None:
    """根据章节名查找章节目录"""
    stories_root = PROJECT_ROOT / "data" / "stories"
    for category in ["main", "side", "special", "is"]:
        cat_dir = stories_root / category
        if not cat_dir.exists():
            continue
        for subdir in cat_dir.iterdir():
            if subdir.is_dir() and subdir.name == chapter_name:
                return subdir
    return None


def extract_source_excerpts(entity: dict, max_chars: int = 8000) -> str:
    """从实体的事件中提取原文摘录"""
    events = entity.get("story_events", [])
    chapters_seen = set()
    excerpts = []
    total_chars = 0

    for ev in events:
        ch = ev.get("source_chapter", "")
        if not ch or ch in chapters_seen:
            continue
        chapters_seen.add(ch)

        ch_dir = find_chapter_dir(ch)
        if not ch_dir:
            continue

        # 读取该章节的关键ST节点（通常包含核心剧情）
        st_files = sorted([f for f in ch_dir.iterdir() if f.suffix == '.json' and 'ST' in f.stem])
        if not st_files:
            # 取前2个和后2个节点
            json_files = sorted([f for f in ch_dir.iterdir() if f.suffix == '.json'])
            st_files = json_files[:2] + json_files[-2:]

        for st_file in st_files[:4]:  # 每章最多取4个节点
            text = load_story_text(st_file)
            if text:
                excerpt = f"\n--- {ch} / {st_file.stem} ---\n{text[:2000]}"
                if total_chars + len(excerpt) <= max_chars:
                    excerpts.append(excerpt)
                    total_chars += len(excerpt)

    return "\n".join(excerpts)


def format_events(entity: dict) -> str:
    """格式化事件列表为文本"""
    events = entity.get("story_events", [])
    if not events:
        return "（无剧情事件）"

    lines = []
    for ev in events:
        name = ev.get("name", "")
        desc = ev.get("description", "")
        sig = ev.get("significance", "minor")
        ch = ev.get("source_chapter", "")
        sig_label = {"revelation": "[核心揭示]", "major": "[重要]", "minor": ""}.get(sig, "")
        lines.append(f"- {sig_label} [{ch}] {name}: {desc}")
    return "\n".join(lines)


def regenerate_summary(
    entity: dict,
    client,
    dry_run: bool = True,
) -> str | None:
    """为单个实体重新生成概述"""
    name = entity.get("name", "")
    category = entity.get("category", "")
    definition = entity.get("definition", "")
    current_summary = entity.get("summary", "")
    events = entity.get("story_events", [])

    if not events:
        print(f"  跳过 {name} — 无剧情事件")
        return None

    events_text = format_events(entity)
    source_excerpts = extract_source_excerpts(entity)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        entity_name=name,
        category=category,
        definition=definition,
        current_summary=current_summary[:500] + ("..." if len(current_summary) > 500 else ""),
        events_text=events_text[:8000] + ("..." if len(events_text) > 8000 else ""),
        source_excerpts=source_excerpts[:8000],
    )

    print(f"  [{name}] events={len(events)}, excerpts={len(source_excerpts)} chars, prompt={len(user_prompt)} chars")

    if dry_run:
        print(f"  [DRY RUN] 跳过 LLM 调用")
        return None

    result = call_llm(client, SYSTEM_PROMPT, user_prompt, max_retries=2)

    if "_parse_error" in result or "_error" in result:
        print(f"  [{name}] LLM 调用失败: {result.get('_error', result.get('_raw', 'unknown'))[:200]}")
        return None

    stats = result.get("_stats", {})
    print(f"  [{name}] tokens: {stats.get('tokens_in',0)} in / {stats.get('tokens_out',0)} out")

    # 提取 overview 字段
    overview = result.get("overview", "")
    if not overview:
        # 尝试从 _raw 中提取
        raw = result.get("_raw", "")
        if raw:
            import re as re_m
            m = re_m.search(r'"overview"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
            if m:
                overview = m.group(1)
    if not overview:
        print(f"  [{name}] 无法提取 overview 字段")
        return None

    # 处理转义
    overview = overview.replace("\\n", "\n")
    return overview


def main():
    dry_run = "--apply" not in sys.argv

    print("=" * 80)
    print(f"Phase 3.5: 概述重写 {'(DRY RUN)' if dry_run else '(APPLY)'}")
    print("=" * 80)

    # 加载种子库
    seed_path = PROJECT_ROOT / "data" / "extractions" / "v3_seed_db_v3_final.json"
    seed_db = json.loads(seed_path.read_text(encoding='utf-8'))
    print(f"加载种子库: {len(seed_db.get('factions',[]))} 阵营, {len(seed_db.get('concepts',[]))} 概念, {len(seed_db.get('locations',[]))} 地点")

    if not dry_run:
        client = create_client()
        print("LLM 客户端已初始化")

    # 目标实体列表（优先处理核心国家和主要势力）
    target_factions = [
        "乌萨斯", "乌萨斯帝国",
        "维多利亚", "维多利亚帝国",
        "炎国",
        "伊比利亚",
        "莱塔尼亚", "莱塔尼亚帝国",
        "卡西米尔",
        "叙拉古",
        "拉特兰",
        "阿戈尔",
        "卡兹戴尔",
        "整合运动",
        "深池",
        "巴别塔",
        "深海猎人",
        "喀兰贸易",
    ]

    # 去重（乌萨斯和乌萨斯帝国可能都匹配同一个实体）
    all_factions = seed_db.get("factions", [])
    processed = set()
    modified = 0

    for target in target_factions:
        if target in processed:
            continue

        # 查找匹配实体
        matches = [f for f in all_factions if f.get("name") == target]
        if not matches:
            print(f"\n  未找到: {target}")
            continue

        entity = matches[0]
        if not entity.get("story_events"):
            print(f"\n  [{target}] 无事件，跳过")
            continue

        print(f"\n{'─'*60}")
        new_summary = regenerate_summary(entity, client if not dry_run else None, dry_run)

        if new_summary and not dry_run:
            entity["summary"] = new_summary
            modified += 1
            print(f"  [{target}] 概述已更新 ({len(new_summary)} chars)")

        processed.add(target)
        # 同时标记同名实体
        for m in matches:
            processed.add(m.get("name"))

        if not dry_run:
            time_mod.sleep(1)  # 速率限制

    # 保存
    if not dry_run and modified > 0:
        seed_path.write_text(json.dumps(seed_db, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\n{'='*80}")
        print(f"已保存: {modified} 个实体概述已更新 → {seed_path}")
        print(f"{'='*80}")
    elif dry_run:
        print(f"\n{'='*80}")
        print("DRY RUN 完成。加 --apply 执行 LLM 调用。")
        print(f"{'='*80}")


if __name__ == "__main__":
    main()
