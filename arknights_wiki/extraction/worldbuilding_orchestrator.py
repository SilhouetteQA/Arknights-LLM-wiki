"""Pass 3 世界观实体提取编排器: Phase 1 图书 + Phase 2 视频"""
import os, time, json
from datetime import datetime, timezone

from .llm_client import create_client, call_llm, _get_model_config
from .book_splitter import split_book
from .video_merger import merge_videos
from .worldbuilding_prompts import (
    build_book_system_prompt, build_book_user_prompt,
    build_video_system_prompt, build_video_user_prompt,
    build_timeline_system_prompt, build_timeline_user_prompt,
    build_seed_context,
)
from .worldbuilding_processor import (
    parse_worldbuilding_output, aggregate_chapters,
    merge_timelines,
    save_seed_db, load_seed_db, generate_wiki_pages,
)


def _estimate_cost(tokens_in: int, tokens_out: int) -> float:
    """估算 DeepSeek API 成本 (USD)"""
    return tokens_in / 1_000_000 * 0.27 + tokens_out / 1_000_000 * 1.10


def run_phase1_book(
    book_path: str = "data/lorebook/terra_a_journey_full.md",
    seed_db_path: str = "data/extractions/v3_seed_db_v1.json",
) -> dict:
    """Phase 1: 提取大地巡旅设定集 (6章正文 + 泰拉纪年)

    Returns:
        种子库 v1 dict (含 concepts/factions/locations + timeline_events)
    """
    segments = split_book(book_path)

    # 分离泰拉纪年段和正文章节
    timeline_seg = None
    chapter_segments = []
    for seg in segments:
        if "泰拉纪年" in seg.title:
            timeline_seg = seg
        else:
            chapter_segments.append(seg)

    print(f"大地巡旅切分为 {len(chapter_segments)} 个正文章节 + {'泰拉纪年' if timeline_seg else '无纪年'}")

    client = create_client()
    system_prompt = build_book_system_prompt()
    chapter_results = []
    total_tokens_in = 0
    total_tokens_out = 0
    t_start = time.time()

    for i, seg in enumerate(chapter_segments, 1):
        print(f"\n[Phase 1] 章节 {i}/{len(chapter_segments)}: {seg.title}")
        print(f"  页数: {seg.start_page}-{seg.end_page}, 字符数: {len(seg.text):,}")

        user_prompt = build_book_user_prompt(seg.title, seg.text)

        t0 = time.time()
        result = call_llm(client, system_prompt, user_prompt)
        elapsed = time.time() - t0

        if result.get("_parse_error"):
            print(f"  ERROR: JSON 解析失败")
            continue

        stats = result.pop("_stats", {})
        ti = stats.get("tokens_in", 0)
        to = stats.get("tokens_out", 0)
        total_tokens_in += ti
        total_tokens_out += to

        n_c = len(result.get("concepts", []))
        n_f = len(result.get("factions", []))
        n_l = len(result.get("locations", []))
        print(f"  concepts={n_c} factions={n_f} locations={n_l}")
        print(f"  tokens: in={ti:,} out={to:,} {elapsed:.1f}s")

        chapter_results.append(result)

    # 跨章聚合 (timeline_events 来自各章正文中的年份事件)
    seed_db = aggregate_chapters(chapter_results)

    # 提取泰拉纪年，与正文中的 timeline_events 合并
    if timeline_seg:
        print(f"\n[Phase 1] 泰拉纪年: {len(timeline_seg.text):,} 字符")
        timeline_prompt = build_timeline_user_prompt(timeline_seg.text)
        timeline_sys = build_timeline_system_prompt()

        t0 = time.time()
        timeline_result = call_llm(client, timeline_sys, timeline_prompt)
        timeline_elapsed = time.time() - t0

        if timeline_result.get("_parse_error"):
            print(f"  ERROR: 泰拉纪年 JSON 解析失败")
        else:
            t_stats = timeline_result.pop("_stats", {})
            ti_t = t_stats.get("tokens_in", 0)
            to_t = t_stats.get("tokens_out", 0)
            total_tokens_in += ti_t
            total_tokens_out += to_t
            seed_db["timeline_events"] = merge_timelines(seed_db, timeline_result)
            print(f"  历史事件 (合并后): {len(seed_db['timeline_events'])}")
            print(f"  tokens: in={ti_t:,} out={to_t:,} {timeline_elapsed:.1f}s")

    seed_db["_meta"] = {
        "phase": 1,
        "model": _get_model_config()["model"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "大地巡旅",
        "chapters_processed": len(chapter_results),
        "has_timeline": timeline_seg is not None,
        "stats": {
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
            "elapsed_s": time.time() - t_start,
            "cost_usd": _estimate_cost(total_tokens_in, total_tokens_out),
        },
    }

    save_seed_db(seed_db, seed_db_path)
    print(f"\nPhase 1 完成:")
    print(f"  概念: {len(seed_db['concepts'])}")
    print(f"  阵营: {len(seed_db['factions'])}")
    print(f"  地点: {len(seed_db['locations'])}")
    print(f"  时间线事件: {len(seed_db.get('timeline_events', []))}")
    print(f"  tokens: in={total_tokens_in:,} out={total_tokens_out:,}")
    print(f"  成本: ${seed_db['_meta']['stats']['cost_usd']:.3f}")
    print(f"  种子库: {seed_db_path}")

    return seed_db


def run_phase2_video(
    seed_db: dict = None,
    video_dir: str = "data/videos",
    output_dir: str = "data/extractions/v3_wiki",
) -> dict:
    """Phase 2: 视频补充提取

    Args:
        seed_db: Phase 1 种子库（如为 None，从默认路径加载）
        video_dir: 视频字幕目录
        output_dir: Wiki 页面输出目录

    Returns:
        丰富后的种子库 v2
    """
    if seed_db is None:
        seed_db = load_seed_db("data/extractions/v3_seed_db_v1.json")

    # 合并视频
    video_text = merge_videos(video_dir)
    print(f"视频合并完成: {len(video_text):,} 字符")

    # 构建种子上下文
    seed_context = build_seed_context(seed_db)

    client = create_client()
    system_prompt = build_video_system_prompt()
    user_prompt = build_video_user_prompt(video_text, seed_context=seed_context)

    print(f"\n[Phase 2] 视频提取开始...")
    t0 = time.time()
    result = call_llm(client, system_prompt, user_prompt)
    elapsed = time.time() - t0

    if result.get("_parse_error"):
        print(f"  ERROR: JSON 解析失败")
        return seed_db

    stats = result.pop("_stats", {})
    ti = stats.get("tokens_in", 0)
    to = stats.get("tokens_out", 0)

    n_c = len(result.get("concepts", []))
    n_f = len(result.get("factions", []))
    n_l = len(result.get("locations", []))
    print(f"  新/丰富: concepts={n_c} factions={n_f} locations={n_l}")
    print(f"  tokens: in={ti:,} out={to:,} {elapsed:.1f}s")

    # 合并到种子库
    enriched = aggregate_chapters([seed_db, result])
    enriched["_meta"] = {
        "phase": 2,
        "model": _get_model_config()["model"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "大地巡旅 + 视频",
        "stats": {
            "tokens_in": ti + seed_db.get("_meta", {}).get("stats", {}).get("tokens_in", 0),
            "tokens_out": to + seed_db.get("_meta", {}).get("stats", {}).get("tokens_out", 0),
            "elapsed_s": elapsed,
            "cost_usd": _estimate_cost(ti, to),
        },
    }

    # 保存种子库 v2
    seed_db_v2_path = "data/extractions/v3_seed_db_v2.json"
    save_seed_db(enriched, seed_db_v2_path)

    # 生成 Wiki 页面
    wiki_paths = generate_wiki_pages(enriched, output_dir)
    print(f"\nPhase 2 完成:")
    print(f"  概念: {len(enriched['concepts'])}")
    print(f"  阵营: {len(enriched['factions'])}")
    print(f"  地点: {len(enriched['locations'])}")
    print(f"  Wiki 页面: {len(wiki_paths)} 个")
    print(f"  种子库 v2: {seed_db_v2_path}")

    return enriched


def run_pass3(
    book_path: str = "data/lorebook/terra_a_journey_full.md",
    video_dir: str = "data/videos",
    output_dir: str = "data/extractions/v3_wiki",
) -> dict:
    """运行完整 Pass 3: Phase 1 + Phase 2"""
    print("=" * 60)
    print("Pass 3: 世界观实体提取")
    print(f"模型: {_get_model_config()['model']}")
    print("=" * 60)

    # Phase 1
    seed_db_v1 = run_phase1_book(book_path)

    # Phase 2
    seed_db_v2 = run_phase2_video(
        seed_db=seed_db_v1,
        video_dir=video_dir,
        output_dir=output_dir,
    )

    return seed_db_v2
