"""Pass 3 世界观实体提取编排器: Phase 1 图书 + Phase 2 视频 + Phase 3 剧情实体链接"""
import os, time, json
from datetime import datetime, timezone
from typing import Optional

from .llm_client import create_client, call_llm, _get_model_config
from .book_splitter import split_book
from .video_merger import merge_videos
from .dialogue_loader import load_chapter, split_chapter
from .worldbuilding_prompts import (
    build_book_system_prompt, build_book_user_prompt,
    build_video_system_prompt, build_video_user_prompt,
    build_timeline_system_prompt, build_timeline_user_prompt,
    build_concept_only_system_prompt, build_concept_only_user_prompt,
    build_seed_context,
    build_phase3_system_prompt, build_phase3_user_prompt,
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

    大地巡旅原文不包含在本仓库中。如需运行此函数，请将 terra_a_journey_full.md 放回 data/lorebook/。
    参考 data/lorebook/README.md 了解详情。

    Returns:
        种子库 v1 dict (含 concepts/factions/locations + timeline_events)
    """
    if not os.path.exists(book_path):
        raise FileNotFoundError(
            f"大地巡旅原文不存在: {book_path}\n"
            "原始文件已移至 D:\\AI project\\Terra A Journey\\\n"
            "详见 data/lorebook/README.md"
        )

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


def run_phase1b_concepts_only(
    book_path: str = "data/lorebook/terra_a_journey_full.md",
) -> list[dict]:
    """Phase 1b: 概念专用提取（不做 factions/locations）

    对每章使用概念专用 prompt，聚焦概念完整性。
    返回 concept-only 提取结果列表，供 merge_concepts 合并到种子库。
    """
    from .book_splitter import split_book

    segments = split_book(book_path)
    # 只取正文章节（跳过泰拉纪年）
    chapter_segments = [s for s in segments if "泰拉纪年" not in s.title]

    print(f"\n[Phase 1b] 概念专用提取: {len(chapter_segments)} 个章节段")

    client = create_client()
    system_prompt = build_concept_only_system_prompt()
    concept_results = []
    total_tokens_in = 0
    total_tokens_out = 0
    t_start = time.time()

    for i, seg in enumerate(chapter_segments, 1):
        print(f"\n[Phase 1b] {i}/{len(chapter_segments)}: {seg.title} ({len(seg.text):,} 字符)")

        user_prompt = build_concept_only_user_prompt(seg.title, seg.text)

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
        print(f"  concepts={n_c}  tokens: in={ti:,} out={to:,} {elapsed:.1f}s")
        concept_results.append(result)

    print(f"\nPhase 1b 完成:")
    print(f"  tokens: in={total_tokens_in:,} out={total_tokens_out:,}")
    print(f"  成本: ${_estimate_cost(total_tokens_in, total_tokens_out):.3f}")

    return concept_results


def merge_concepts_into_seed_db(seed_db: dict, concept_results: list[dict]) -> dict:
    """将概念专用提取结果合并入种子库（只合并 concepts 层）"""
    import copy
    merged = copy.deepcopy(seed_db)

    # 构建现有概念索引
    concept_index = {}
    for c in merged.get("concepts", []):
        name = c.get("name", "").strip()
        if name:
            concept_index[name] = c

    # 合并新概念
    from .worldbuilding_processor import _merge_entity, _strip_empty
    for result in concept_results:
        for concept in result.get("concepts", []):
            concept = _strip_empty(concept)
            name = concept.get("name", "").strip()
            if not name:
                continue
            if name in concept_index:
                concept_index[name] = _merge_entity(concept_index[name], concept)
            else:
                concept_index[name] = concept

    merged["concepts"] = list(concept_index.values())
    return merged


def run_pass3(
    book_path: str = "data/lorebook/terra_a_journey_full.md",
    video_dir: str = "data/videos",
    output_dir: str = "data/extractions/v3_wiki",
) -> dict:
    """运行完整 Pass 3: Phase 1a (factions+locations) + 1b (concepts) + 2 (video)"""
    print("=" * 60)
    print("Pass 3: 世界观实体提取")
    print(f"模型: {_get_model_config()['model']}")
    print("=" * 60)

    # Phase 1a: factions + locations + timeline
    seed_db = run_phase1_book(book_path)

    # Phase 1b: concepts only
    concept_results = run_phase1b_concepts_only(book_path)
    seed_db = merge_concepts_into_seed_db(seed_db, concept_results)
    print(f"\n合并后 概念: {len(seed_db['concepts'])}")

    # Phase 2: video enrichment
    seed_db = run_phase2_video(
        seed_db=seed_db,
        video_dir=video_dir,
        output_dir=output_dir,
    )

    return seed_db


# ============================================================
# Phase 3: 剧情实体链接 — 用故事文本丰富已有实体库
# ============================================================

def _merge_phase3_result(seed_db: dict, result: dict, chapter_name: str) -> dict:
    """将单章 Phase 3 结果合并入种子库"""
    import copy
    merged = copy.deepcopy(seed_db)

    entity_index = {}
    for etype in ("concepts", "factions", "locations"):
        entity_index[etype] = {}
        for i, entity in enumerate(merged.get(etype, [])):
            name = entity.get("name", "").strip()
            if name:
                entity_index[etype][name] = i
            # 同步索引 aliases，解决 LLM 输出简名（如"炎武"）无法匹配
            # 完整名（如"炎武（皇子）"）的问题
            for alias in entity.get("aliases", []):
                alias = alias.strip()
                if alias and alias not in entity_index[etype]:
                    entity_index[etype][alias] = i

    def _resolve_entity(etype_plural: str, ename: str):
        """解析实体名：精确匹配 → alias 匹配 → 去括号匹配"""
        idx_map = entity_index.get(etype_plural, {})
        if ename in idx_map:
            return idx_map[ename]
        # 尝试去掉 LLM 可能添加的括号后缀
        if "（" in ename:
            base = ename.split("（")[0].strip()
            if base in idx_map:
                return idx_map[base]
        # 尝试在种子库中找包含该名称的实体（LLM 简名 vs seed 全名）
        for key, idx in idx_map.items():
            if "（" in key and key.startswith(ename):
                return idx
        return None

    def _is_placeholder(ev: dict) -> bool:
        """检测空占位事件"""
        desc = ev.get("description", "")
        name = ev.get("name", "")
        return any(kw in name or kw in desc for kw in ("未直接出现", "未直接提及", "未直接涉及"))

    for mention in result.get("entity_mentions", []):
        if not isinstance(mention, dict):
            continue
        ename = mention.get("entity_name", "").strip()
        etype = mention.get("entity_type", "")
        if not ename or etype not in ("concept", "faction", "location"):
            continue
        etype_plural = etype + "s"
        idx = _resolve_entity(etype_plural, ename)
        if idx is None:
            continue
        target = merged[etype_plural][idx]

        # 过滤已有占位事件
        existing_events = [ev for ev in target.get("story_events", []) if not _is_placeholder(ev)]
        new_events = [ev for ev in mention.get("story_events", []) if not _is_placeholder(ev)]
        for ev in new_events:
            ev["source_chapter"] = chapter_name
        target["story_events"] = existing_events + new_events

        # 添加 source_record（story_text 来源）
        existing_sources = target.get("source_records", [])
        source_key = f"story_text:{chapter_name}"
        if not any(isinstance(s, dict) and s.get("source") == "story_text"
                   and s.get("source_detail") == chapter_name
                   for s in existing_sources):
            existing_sources.append({
                "source": "story_text",
                "source_detail": chapter_name,
                "location": "",
                "publish_date": "",
                "confidence": "confirmed",
            })
        target["source_records"] = existing_sources

        # 合并 members（仅 faction，按 name 去重）
        if etype == "faction":
            existing_members = target.get("member_composition", [])
            existing_members = [
                m if isinstance(m, dict) else {"name": str(m), "role": "", "chapter_role": ""}
                for m in existing_members
            ]
            existing_names = {m.get("name", "") for m in existing_members if isinstance(m, dict)}
            for m in mention.get("members", []):
                if not isinstance(m, dict):
                    continue
                mname = m.get("name", "").strip()
                if not mname:
                    continue
                if mname in existing_names:
                    # 更新已存在成员的信息（保留更丰富的 role/chapter_role）
                    for em in existing_members:
                        if isinstance(em, dict) and em.get("name") == mname:
                            if len(m.get("role", "")) > len(em.get("role", "")):
                                em["role"] = m["role"]
                            if m.get("chapter_role"):
                                cr = em.get("chapter_role", "")
                                em["chapter_role"] = cr + "; " + m["chapter_role"] if cr else m["chapter_role"]
                            break
                else:
                    existing_members.append(m)
                    existing_names.add(mname)
            target["member_composition"] = existing_members

    new_entities = result.get("new_entities", {})
    for etype in ("concepts", "factions", "locations"):
        for entity in new_entities.get(etype, []):
            if not isinstance(entity, dict):
                continue
            name = entity.get("name", "").strip()
            if not name:
                continue
            se_list = [ev for ev in entity.get("story_events", []) if not _is_placeholder(ev)]
            if not se_list:
                se_list = [{
                    "name": f"{name}首次出现",
                    "description": f"在{chapter_name}剧情中首次出现",
                    "significance": "major",
                }]
            for ev in se_list:
                ev["source_chapter"] = chapter_name
            entity["story_events"] = se_list

            # 新实体也添加 source_record
            entity["source_records"] = entity.get("source_records", [])
            if not any(s.get("source") == "story_text" and s.get("source_detail") == chapter_name
                       for s in entity["source_records"]):
                entity["source_records"].append({
                    "source": "story_text",
                    "source_detail": chapter_name,
                    "location": "",
                    "publish_date": "",
                    "confidence": "confirmed",
                })

            idx = _resolve_entity(etype, name)
            if idx is not None:
                target = merged[etype][idx]
                existing_events = [ev for ev in target.get("story_events", []) if not _is_placeholder(ev)]
                target["story_events"] = existing_events + se_list
            else:
                merged[etype].append(entity)
                entity_index.setdefault(etype, {})[name] = len(merged[etype]) - 1

    # 跨层去重 + 层内同名去重
    faction_names = {f["name"] for f in merged.get("factions", [])}
    removed = [c["name"] for c in merged.get("concepts", []) if c["name"] in faction_names]
    if removed:
        merged["concepts"] = [c for c in merged["concepts"] if c["name"] not in faction_names]
        print(f"  跨层去重: {removed}")

    for etype in ("concepts", "factions", "locations"):
        seen = {}
        deduped = []
        for entity in merged[etype]:
            name = entity.get("name", "").strip()
            if not name:
                continue
            if name in seen:
                # 合并 story_events 和 member_composition
                existing = seen[name]
                for ev in entity.get("story_events", []):
                    if not _is_placeholder(ev):
                        existing["story_events"].append(ev)
                if etype == "factions":
                    existing_mc = existing.get("member_composition", [])
                    existing_names = {m.get("name", "") if isinstance(m, dict) else str(m) for m in existing_mc}
                    for m in entity.get("member_composition", []):
                        mname = m.get("name", "") if isinstance(m, dict) else str(m)
                        if mname and mname not in existing_names:
                            existing_mc.append(m)
                            existing_names.add(mname)
                    existing["member_composition"] = existing_mc
            else:
                seen[name] = entity
                deduped.append(entity)
        merged[etype] = deduped

    return merged


def run_phase3_chapter(
    category: str,
    chapter: str,
    seed_db: dict,
    data_dir: str = "data/stories",
):
    """Phase 3: 对单章剧情进行实体链接

    Returns:
        {"entity_mentions": [...], "new_entities": {...}} 或 None
    """
    chapter_dir = os.path.join(data_dir, category, chapter)
    cd = load_chapter(chapter_dir)
    batches = split_chapter(cd)

    client = create_client()
    system_prompt = build_phase3_system_prompt()
    all_mentions = []
    all_new = {"concepts": [], "factions": [], "locations": []}
    total_tokens_in = 0
    total_tokens_out = 0
    t_start = time.time()

    for i, batch in enumerate(batches, 1):
        batch_text = batch.text
        user_prompt = build_phase3_user_prompt(
            chapter_name=f"{chapter} (段{i}/{len(batches)})",
            chapter_text=batch_text,
            seed_db=seed_db,
        )

        print(f"  [段{i}/{len(batches)}] {len(batch_text):,} chars ...", end=" ", flush=True)
        t0 = time.time()
        result = call_llm(client, system_prompt, user_prompt)
        elapsed = time.time() - t0

        if result.get("_parse_error"):
            print(f"JSON 解析失败")
            continue

        stats = result.pop("_stats", {})
        ti = stats.get("tokens_in", 0)
        to = stats.get("tokens_out", 0)
        total_tokens_in += ti
        total_tokens_out += to

        n_m = len(result.get("entity_mentions", []))
        ne = result.get("new_entities", {})
        nc = len(ne.get("concepts", []))
        nf = len(ne.get("factions", []))
        nl = len(ne.get("locations", []))
        print(f"mentions={n_m} new(c={nc} f={nf} l={nl}) {elapsed:.1f}s")

        all_mentions.extend(result.get("entity_mentions", []))
        for etype in ("concepts", "factions", "locations"):
            all_new[etype].extend(ne.get(etype, []))

    elapsed_total = time.time() - t_start
    cost = _estimate_cost(total_tokens_in, total_tokens_out)
    print(f"  完成: {len(all_mentions)} mentions, "
          f"new(c={len(all_new['concepts'])} "
          f"f={len(all_new['factions'])} "
          f"l={len(all_new['locations'])}), "
          f"${cost:.4f} / {elapsed_total:.1f}s")

    return {
        "entity_mentions": all_mentions,
        "new_entities": all_new,
        "_stats": {
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
            "elapsed_s": elapsed_total,
            "cost_usd": cost,
        },
    }


def run_phase3_trial(
    seed_db_path: str = "data/extractions/v3_seed_db_v2.json",
    data_dir: str = "data/stories",
    output_dir: str = "data/extractions/v3_wiki",
) -> dict:
    """Phase 3 试跑: 对 7 个测试章节进行实体链接"""
    test_chapters = [
        ("side", "孤星"),
        ("side", "相见欢"),
        ("main", "慈悲灯塔"),
        ("main", "怒号光明"),
        ("side", "长夜临光"),
        ("side", "愚人号"),
        ("side", "火山旅梦"),
    ]

    print("=" * 60)
    print("Pass 3 Phase 3: 剧情实体链接 (试跑)")
    print(f"模型: {_get_model_config()['model']}")
    print(f"测试章节: {len(test_chapters)}")
    print("=" * 60)

    seed_db = load_seed_db(seed_db_path)
    print(f"种子库: {len(seed_db.get('concepts',[]))}c / "
          f"{len(seed_db.get('factions',[]))}f / "
          f"{len(seed_db.get('locations',[]))}l")

    total_cost = 0.0
    total_tokens_in = 0
    total_tokens_out = 0
    t_start = time.time()

    for category, chapter in test_chapters:
        chapter_dir = os.path.join(data_dir, category, chapter)
        if not os.path.isdir(chapter_dir):
            print(f"\n跳过 [{category}] {chapter}: 目录不存在")
            continue

        print(f"\n--- [{category}] {chapter} ---")
        result = run_phase3_chapter(category, chapter, seed_db, data_dir)

        if result is None:
            continue

        stats = result.pop("_stats", {})
        total_cost += stats.get("cost_usd", 0)
        total_tokens_in += stats.get("tokens_in", 0)
        total_tokens_out += stats.get("tokens_out", 0)

        seed_db = _merge_phase3_result(seed_db, result, chapter)

    elapsed_total = time.time() - t_start

    # 统计 story_events 数量
    entities_with_events = 0
    total_events = 0
    for etype in ("concepts", "factions", "locations"):
        for e in seed_db.get(etype, []):
            n = len(e.get("story_events", []))
            if n > 0:
                entities_with_events += 1
                total_events += n

    # 保存种子库 v3
    seed_db_v3_path = "data/extractions/v3_seed_db_v3.json"
    seed_db["_meta"] = {
        "phase": 3,
        "model": _get_model_config()["model"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "大地巡旅 + 视频 + 剧情(试跑7章)",
        "chapters_processed": 7,
        "stats": {
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
            "elapsed_s": elapsed_total,
            "cost_usd": total_cost,
        },
    }
    save_seed_db(seed_db, seed_db_v3_path)

    # 重新生成 Wiki 页面
    wiki_paths = generate_wiki_pages(seed_db, output_dir)

    print(f"\n{'='*60}")
    print(f"Phase 3 试跑完成:")
    print(f"  概念: {len(seed_db['concepts'])}")
    print(f"  阵营: {len(seed_db['factions'])}")
    print(f"  地点: {len(seed_db['locations'])}")
    print(f"  有 story_events 的实体: {entities_with_events}")
    print(f"  总 story_events: {total_events}")
    print(f"  Wiki 页面: {len(wiki_paths)} 个 (已更新)")
    print(f"  tokens: in={total_tokens_in:,} out={total_tokens_out:,}")
    print(f"  成本: ${total_cost:.4f}")
    print(f"  种子库 v3: {seed_db_v3_path}")

    return seed_db


# ============================================================
# Phase 3 全量批量提取
# ============================================================

def _strip_phase3_data(seed_db: dict) -> dict:
    """从种子库中剥离 Phase 3 数据，得到干净的 Phase 1+2 基线

    移除: story_events, story_text 类型的 source_records,
          仅含 Phase 3 数据的 member_composition
    """
    import copy
    clean = copy.deepcopy(seed_db)

    for etype in ("concepts", "factions", "locations"):
        for entity in clean.get(etype, []):
            # 移除 story_events
            entity.pop("story_events", None)
            entity.pop("revelations", None)
            # 移除 story_text 类型的 source_records
            if "source_records" in entity:
                entity["source_records"] = [
                    sr for sr in entity["source_records"]
                    if sr.get("source") != "story_text"
                ]

    # 移除 _meta 中 Phase 3 相关字段
    if "_meta" in clean:
        clean["_meta"].pop("chapters_processed", None)
        clean["_meta"]["phase"] = 2

    return clean


def _get_story_chapters(stories_dir: str = "data/stories") -> list[tuple[str, str]]:
    """枚举所有故事章节 (category, chapter_name)"""
    chapters = []
    for cat in ["main", "side", "special"]:
        cat_path = os.path.join(stories_dir, cat)
        if not os.path.isdir(cat_path):
            continue
        for ch in sorted(os.listdir(cat_path)):
            ch_path = os.path.join(cat_path, ch)
            if os.path.isdir(ch_path) and any(f.endswith(".json") for f in os.listdir(ch_path)):
                chapters.append((cat, ch))
    return chapters


def run_phase3_full(
    seed_db_path: str = "data/extractions/v3_seed_db_v3.json",
    baseline_output_path: str = "data/extractions/v3_seed_db_v2_clean.json",
    data_dir: str = "data/stories",
    output_dir: str = "data/extractions/v3_wiki",
    checkpoint_path: str = "data/extractions/v3_seed_db_v3_checkpoint.json",
    skip_chapters: list[str] | None = None,
) -> dict:
    """Phase 3 全量: 对所有故事章节进行实体链接

    每次处理完一章自动保存检查点，支持断点续跑。
    """
    if skip_chapters is None:
        # 7 个炎国章节已用修正后 prompt 跑过，跳过
        skip_chapters = ["画中人", "将进酒", "登临意", "怀黍离", "相见欢", "辞岁行", "洪炉示岁"]

    print("=" * 60)
    print("Pass 3 Phase 3: 全量剧情实体链接")
    print(f"模型: {_get_model_config()['model']}")
    print(f"跳过已正确处理的章节: {skip_chapters}")
    print("=" * 60)

    # 尝试从检查点恢复
    if os.path.exists(checkpoint_path):
        print(f"\n从检查点恢复: {checkpoint_path}")
        seed_db = load_seed_db(checkpoint_path)
        # 从 source_records 提取已处理的章节名
        for etype in ("concepts", "factions", "locations"):
            for e in seed_db.get(etype, []):
                for sr in e.get("source_records", []):
                    if sr.get("source") == "story_text" and sr.get("source_detail"):
                        ch_name = sr["source_detail"]
                        if ch_name not in skip_chapters:
                            skip_chapters.append(ch_name)
        print(f"已处理章节(含恢复): {len(skip_chapters)}")
    else:
        # 从 v3 剥离 Phase 3 数据获取干净基线
        print(f"\n加载种子库: {seed_db_path}")
        original = load_seed_db(seed_db_path)
        seed_db = _strip_phase3_data(original)
        save_seed_db(seed_db, baseline_output_path)
        print(f"干净基线已保存: {baseline_output_path}")
        print(f"  概念: {len(seed_db['concepts'])} 阵营: {len(seed_db['factions'])} 地点: {len(seed_db['locations'])}")

    # 枚举所有章节
    all_chapters = _get_story_chapters(data_dir)
    chapters_to_run = [(c, ch) for c, ch in all_chapters if ch not in skip_chapters]

    print(f"\n总章节: {len(all_chapters)}, 跳过: {len(skip_chapters)}, 待处理: {len(chapters_to_run)}")

    # 恢复累计统计
    prev_meta = seed_db.get("_meta", {})
    prev_stats = prev_meta.get("stats", {})
    grand_cost = prev_stats.get("cost_usd", 0.0)
    grand_tokens_in = prev_stats.get("tokens_in", 0)
    grand_tokens_out = prev_stats.get("tokens_out", 0)
    t_grand_start = time.time()
    success_count = 0
    fail_list = []

    for idx, (cat, ch) in enumerate(chapters_to_run, 1):
        chapter_dir = os.path.join(data_dir, cat, ch)
        if not os.path.isdir(chapter_dir):
            print(f"\n[{idx}/{len(chapters_to_run)}] 跳过 [{cat}] {ch}: 目录不存在")
            continue

        print(f"\n{'─'*50}")
        print(f"[{idx}/{len(chapters_to_run)}] [{cat}] {ch}")
        print(f"{'─'*50}")

        try:
            result = run_phase3_chapter(cat, ch, seed_db, data_dir)
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            fail_list.append((cat, ch, str(e)))
            continue

        if result is None:
            fail_list.append((cat, ch, "返回 None"))
            continue

        stats = result.pop("_stats", {})
        grand_cost += stats.get("cost_usd", 0)
        grand_tokens_in += stats.get("tokens_in", 0)
        grand_tokens_out += stats.get("tokens_out", 0)

        seed_db = _merge_phase3_result(seed_db, result, ch)
        success_count += 1

        # 每章处理完保存检查点
        elapsed = time.time() - t_grand_start
        seed_db["_meta"] = {
            "phase": 3,
            "model": _get_model_config()["model"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "大地巡旅 + 视频 + 剧情(全量进行中)",
            "chapters_processed": success_count,
            "progress": f"{idx}/{len(chapters_to_run)}",
            "last_chapter": f"[{cat}] {ch}",
            "stats": {
                "tokens_in": grand_tokens_in,
                "tokens_out": grand_tokens_out,
                "elapsed_s": elapsed,
                "cost_usd": grand_cost,
            },
        }
        save_seed_db(seed_db, checkpoint_path)

        # 累计统计
        entities_with_events = 0
        total_events = 0
        for etype in ("concepts", "factions", "locations"):
            for e in seed_db.get(etype, []):
                n = len(e.get("story_events", []))
                if n > 0:
                    entities_with_events += 1
                    total_events += n

        print(f"  [累计] {success_count}章成功, {len(fail_list)}失败, "
              f"${grand_cost:.4f}, {entities_with_events}实体有事件, {total_events}事件")

    # 最终保存
    elapsed_total = time.time() - t_grand_start

    entities_with_events = 0
    total_events = 0
    for etype in ("concepts", "factions", "locations"):
        for e in seed_db.get(etype, []):
            n = len(e.get("story_events", []))
            if n > 0:
                entities_with_events += 1
                total_events += n

    final_path = "data/extractions/v3_seed_db_v3_final.json"
    seed_db["_meta"] = {
        "phase": 3,
        "model": _get_model_config()["model"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "大地巡旅 + 视频 + 剧情(全量)",
        "chapters_processed": success_count,
        "chapters_failed": len(fail_list),
        "stats": {
            "tokens_in": grand_tokens_in,
            "tokens_out": grand_tokens_out,
            "elapsed_s": elapsed_total,
            "cost_usd": grand_cost,
        },
    }
    save_seed_db(seed_db, final_path)

    # 生成 Wiki 页面
    wiki_paths = generate_wiki_pages(seed_db, output_dir)

    print(f"\n{'='*60}")
    print(f"Phase 3 全量完成:")
    print(f"  成功: {success_count} 章, 失败: {len(fail_list)} 章")
    print(f"  概念: {len(seed_db['concepts'])}")
    print(f"  阵营: {len(seed_db['factions'])}")
    print(f"  地点: {len(seed_db['locations'])}")
    print(f"  有 story_events 的实体: {entities_with_events}")
    print(f"  总 story_events: {total_events}")
    print(f"  Wiki 页面: {len(wiki_paths)} 个")
    print(f"  tokens: in={grand_tokens_in:,} out={grand_tokens_out:,}")
    print(f"  成本: ${grand_cost:.4f} / {elapsed_total/60:.1f}min")
    print(f"  最终种子库: {final_path}")

    if fail_list:
        print(f"\n失败章节列表:")
        for cat, ch, err in fail_list:
            print(f"  [{cat}] {ch}: {err}")

    return seed_db
