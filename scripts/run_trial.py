"""试跑脚本 — 6 章剧情骨架提取"""
import sys, io, json, os, time

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from arknights_wiki.extraction.dialogue_loader import load_chapter
from arknights_wiki.extraction.prompt_builder import build_system_prompt, build_user_prompt
from arknights_wiki.extraction.llm_client import create_client, call_llm
from arknights_wiki.extraction.post_processor import (
    align_character_names, load_identity_map, merge_batches, validate_extraction
)
from arknights_wiki.extraction.orchestrator import save_extraction, generate_review_markdown

def extract_chapter_raw(category, chapter):
    """直接提取单章，最小依赖"""
    data_dir = "data/stories"
    chapter_dir = os.path.join(data_dir, category, chapter)
    cd = load_chapter(chapter_dir)

    # 判断是否需要分批
    from arknights_wiki.extraction.dialogue_loader import split_chapter
    batches = split_chapter(cd)

    id_map = load_identity_map("config/identity_map.json")
    with open("data/operators.json", "r", encoding="utf-8") as f:
        operators = json.load(f)["operators"]

    client = create_client()
    system_prompt = build_system_prompt()
    all_batches = []
    total_stats = {"tokens_in": 0, "tokens_out": 0, "elapsed_s": 0}

    for bi, batch in enumerate(batches):
        print(f"  批次 {bi+1}/{len(batches)}: {len(batch.lines)} 行, ~{batch.token_estimate:,} tokens")
        user_prompt = build_user_prompt(
            chapter=batch.chapter,
            dialogue_text=batch.text,
            total_lines=len(batch.lines),
        )

        t0 = time.time()
        try:
            llm_result = call_llm(client, system_prompt, user_prompt)
        except Exception as e:
            print(f"  API ERROR: {e}")
            all_batches.append({"chapter": batch.chapter, "category": cd.category,
                "summary": "", "events": [], "characters": [], "concepts": [],
                "_parse_error": True, "_raw": str(e)})
            continue
        elapsed = time.time() - t0

        if llm_result.get("_parse_error"):
            print(f"  JSON 解析失败")
            all_batches.append({"chapter": batch.chapter, "category": cd.category,
                "summary": "", "events": [], "characters": [], "concepts": [],
                "_parse_error": True, "_raw": llm_result.get("_raw", "")})
        else:
            stats = llm_result.pop("_stats", {})
            total_stats["tokens_in"] += stats.get("tokens_in", 0)
            total_stats["tokens_out"] += stats.get("tokens_out", 0)
            all_batches.append(llm_result)
            print(f"  tokens: in={stats.get('tokens_in',0):,} out={stats.get('tokens_out',0):,} {elapsed:.1f}s")

        total_stats["elapsed_s"] += elapsed

    merged = merge_batches(all_batches, chapter)
    merged["processed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    merged["model"] = "MiniMax-M3"
    merged["stats"] = total_stats

    errors = validate_extraction(merged, len(cd.lines))
    if errors:
        merged["_validation_errors"] = errors

    if merged.get("characters"):
        merged["characters"], unmatched = align_character_names(
            merged["characters"], operators, id_map)
        if unmatched:
            merged["_unmatched_names"] = unmatched

    return merged, cd


# 试跑
TRIAL = [
    ("main", "黑暗时代·上"),
    ("main", "怒号光明"),
    ("main", "慈悲灯塔"),
    ("side", "孤星"),
    ("side", "相见欢"),
    ("side", "长夜临光"),
]

results = {}
os.makedirs("output/trial_review", exist_ok=True)

for category, chapter in TRIAL:
    print(f"\n{'='*50}")
    print(f"[{category}] {chapter}")
    print('='*50)

    data, cd = extract_chapter_raw(category, chapter)
    save_extraction(data)

    review_texts = [l["text"] for l in cd.lines]
    md = generate_review_markdown(data, review_texts)
    md_path = f"output/trial_review/{chapter}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    s = data.get("stats", {})
    events_n = len(data.get("events", []))
    chars_n = len(data.get("characters", []))
    concepts_n = len(data.get("concepts", []))
    cost = s.get("tokens_in", 0) * 0.5/1e6 + s.get("tokens_out", 0) * 2.0/1e6
    print(f"  events={events_n} chars={chars_n} concepts={concepts_n}")
    print(f"  toks: in={s.get('tokens_in',0):,} out={s.get('tokens_out',0):,}")
    print(f"  cost: ${cost:.4f}")
    if data.get("_validation_errors"):
        print(f"  VALIDATION: {data['_validation_errors']}")
    if data.get("_unmatched_names"):
        print(f"  unmatched: {data['_unmatched_names']}")
    print(f"  JSON -> data/extractions/v1_events/{category}/{chapter}.json")
    print(f"  MD   -> {md_path}")

    results[chapter] = data

# 汇总
print("\n" + "="*60)
print("试跑汇总:")
print("="*60)
total_cost = 0
for ch, data in results.items():
    s = data.get("stats", {})
    toks_in = s.get("tokens_in", 0)
    toks_out = s.get("tokens_out", 0)
    cost = toks_in * 0.5/1e6 + toks_out * 2.0/1e6
    total_cost += cost
    events_n = len(data.get("events", []))
    chars_n = len(data.get("characters", []))
    concepts_n = len(data.get("concepts", []))
    print(f"{ch:16s} | events={events_n:>2d} chars={chars_n:>2d} concepts={concepts_n:>2d} | in={toks_in:>6,} out={toks_out:>5,} | ${cost:.4f}")
print(f"Total cost: ${total_cost:.3f}")
