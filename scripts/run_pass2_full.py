"""Pass 2 全量角色 Wiki 页面提取 — 641 角色"""
import json, os, time
from datetime import datetime, timezone

from arknights_wiki.extraction.orchestrator import (
    build_character_pipeline,
    run_character_extraction,
    save_character_output,
    _get_model_label,
)
from arknights_wiki.extraction.post_processor import validate_character_output
from arknights_wiki.extraction.character_aggregator import get_operator_archive


def _load_result(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def run_all_characters(
    output_dir: str = "data/extractions/v2_characters",
    resume: bool = True,
):
    print("=" * 60)
    print("Pass 2 全量角色 Wiki 页面提取")
    print("=" * 60)

    # 构建流水线
    print("\n[1/3] 构建流水线...")
    t0 = time.time()
    targets, operators = build_character_pipeline(
        v1_dir="data/extractions/v1_events",
        data_dir="data/stories",
        operators_path="data/operators.json",
        identity_map_path="config/identity_map.json",
        keep_list_path="config/npc_single_keep.md",
    )
    elapsed = time.time() - t0
    total_events = sum(len(e["events"]) for e in targets.values())
    print(f"  目标角色: {len(targets)}")
    print(f"  总关联事件: {total_events}")
    print(f"  耗时: {elapsed:.1f}s")

    # 排序：按事件数降序（高频角色先跑，尽早发现问题）
    sorted_targets = sorted(
        targets.items(),
        key=lambda x: len(x[1]["chapters"]),
        reverse=True,
    )

    os.makedirs(output_dir, exist_ok=True)

    # 统计
    total_tokens_in = 0
    total_tokens_out = 0
    total_elapsed = 0.0
    success_count = 0
    skip_count = 0
    fail_count = 0
    t_start_all = time.time()

    print(f"\n[2/3] 开始提取 ({len(sorted_targets)} 角色)")
    print(f"  resume={'ON' if resume else 'OFF'}")
    print()

    for i, (name, char_data) in enumerate(sorted_targets):
        idx = f"{i+1}/{len(sorted_targets)}"

        safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_")
        out_path = os.path.join(output_dir, f"{safe_name}.json")

        # Resume: 检查已存在的有效输出
        if resume:
            existing = _load_result(out_path)
            if existing and not existing.get("_parse_error") and existing.get("summary"):
                skip_count += 1
                print(f"[{idx}] {name} SKIP (resume)")
                continue

        chapter_count = len(char_data.get("chapters", []))
        event_count = len(char_data.get("events", []))
        print(f"[{idx}] {name} (ch={chapter_count} ev={event_count}) ...", end=" ", flush=True)

        try:
            op_archive = get_operator_archive(name, operators)
            result = run_character_extraction(name, char_data, operator_archive=op_archive)
        except Exception as e:
            print(f"ERROR: {e}")
            fail_count += 1
            continue

        stats = result.get("_stats", {})
        tok_in = stats.get("tokens_in", 0)
        tok_out = stats.get("tokens_out", 0)
        elapsed_s = stats.get("elapsed_s", 0)
        total_tokens_in += tok_in
        total_tokens_out += tok_out
        total_elapsed += elapsed_s

        if result.get("_parse_error"):
            print(f"PARSE ERROR")
            fail_count += 1
        else:
            # 校验
            errors = validate_character_output(result, name)
            if errors:
                result["_validation_errors"] = errors

            # 后处理字段
            result["aliases"] = list(char_data.get("aliases", []))
            result["source_pass1_chapters"] = sorted(char_data.get("chapters", []))
            result["model"] = _get_model_label()
            result["generated_at"] = datetime.now(timezone.utc).isoformat()

            if op_archive:
                result["race"] = op_archive.get("race", "")
                affiliations = []
                for field in ["nation", "team", "group"]:
                    val = op_archive.get(field, "")
                    if val:
                        affiliations.append(val)
                result["affiliations"] = affiliations

            path = save_character_output(result, output_dir=output_dir)
            print(f"OK tok={tok_in:,}/{tok_out:,} {elapsed_s:.1f}s")
            success_count += 1

    elapsed_all = time.time() - t_start_all

    # 成本估算
    cost_in = total_tokens_in / 1_000_000 * 0.27
    cost_out = total_tokens_out / 1_000_000 * 1.10
    cost = cost_in + cost_out

    print(f"\n[3/3] 全量提取完成")
    print(f"{'='*60}")
    print(f"  成功: {success_count}")
    print(f"  跳过 (resume): {skip_count}")
    print(f"  失败: {fail_count}")
    print(f"  tokens: in={total_tokens_in:,} out={total_tokens_out:,}")
    print(f"  估算成本: ${cost:.3f} USD")
    print(f"  总耗时: {elapsed_all:.0f}s ({elapsed_all/60:.1f}m)")
    print(f"  输出目录: {output_dir}/")


if __name__ == "__main__":
    run_all_characters()
