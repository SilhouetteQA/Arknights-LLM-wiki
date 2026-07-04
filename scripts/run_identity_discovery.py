"""Pass 2 身份映射发现：LLM 识别真名/别名→干员映射，全量批处理"""
import json, sys, os, time
sys.path.insert(0, ".")

from arknights_wiki.extraction.character_aggregator import collect_from_v1, normalize_and_merge
from arknights_wiki.extraction.post_processor import load_identity_map
from arknights_wiki.extraction.llm_client import create_client, call_llm


def load_data():
    with open("data/operators.json", encoding="utf-8") as f:
        operators = json.load(f)["operators"]
    id_map = load_identity_map()
    raw = collect_from_v1("data/extractions/v1_events")
    merged = normalize_and_merge(raw, operators, id_map)

    op_names = {op["name_zh"] for op in operators}
    id_map_values = set(id_map.values())
    id_map_keys = set(id_map.keys())

    unmapped = []
    for name, data in merged.items():
        if name in op_names:  # already an operator name
            continue
        if name in id_map_keys:  # already mapped via identity_map
            continue
        if name in id_map_values:  # this IS an operator codename mapped from elsewhere
            continue
        n_ev = len(data["events"])
        if n_ev >= 3:  # lower threshold for broader discovery
            chapters = list(data["chapters"])
            unmapped.append({
                "name": name,
                "events": n_ev,
                "chapters": len(chapters),
                "sample_chapters": chapters[:3],
                "aliases": list(data.get("aliases", set())),
            })

    unmapped.sort(key=lambda x: -x["events"])
    return unmapped, operators


def build_discovery_prompt(batch: list[dict], operators: list[dict]) -> str:
    # Compact operator list: just names, since LLM knows Arknights
    op_names = [op["name_zh"] for op in operators]
    op_list_str = "、".join(op_names)

    name_lines = []
    for u in batch:
        alias_str = f" [aka {', '.join(u['aliases'])}]" if u['aliases'] else ""
        ch_str = "、".join(u["sample_chapters"][:2])
        name_lines.append(f"{u['name']}（{u['events']}ev/{u['chapters']}ch/{ch_str}）{alias_str}")

    return f"""你是明日方舟角色数据库专家。识别以下「未映射角色名」中，哪些是已有干员的真名、别名、代号变体。

## 当前干员列表

{op_list_str}

## 未映射角色名（{len(batch)}个）

{chr(10).join(name_lines)}

## 规则

判断每个未映射角色名与干员的关系：
1. real_name: 某干员的本名/真名
2. alias: 某干员的别名/外号/绰号
3. variant: 曾用名/异格名/代号变体
4. none: 独立NPC，与现有干员无关

只输出 JSON，不含 markdown。字符串内禁用英文双引号，用「」代替。

```json
{{"mappings": [{{"unmapped_name": "名", "operator_name": "干员或空", "relation": "real_name|alias|variant|none", "reason": "简短理由"}}]}}
```

注意：
- 不要编造不存在的干员名。operator_name 必须在上述干员列表中。
- 英文名区分大小写（如 Logos、Ace、Scout 如果是干员则映射，否则为 none）。
- 泛称/无名角色（带「的」「者」「士兵」「矿工」等词）通常是 none。
- 置信度低的不要输出，只输出你能确定的映射。"""


def main():
    unmapped, operators = load_data()
    print(f"未映射角色（>=3事件）: {len(unmapped)}")

    # Check for existing results to resume
    output_path = "output/identity_discovery_all.json"
    existing = {}
    if os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as f:
            existing = json.load(f)
        print(f"已有 {len(existing)} 条结果，跳过已处理的")

    batch_size = 50
    total_cost = 0.0
    all_found = dict(existing)

    for i in range(0, len(unmapped), batch_size):
        batch = unmapped[i : i + batch_size]

        # Skip already-processed names
        new_batch = [u for u in batch if u["name"] not in existing]
        if not new_batch:
            continue

        batch_num = i // batch_size + 1
        total_batches = (len(unmapped) + batch_size - 1) // batch_size
        print(f"\n批次 {batch_num}/{total_batches}: {len(new_batch)} 个新名...", flush=True)

        prompt = build_discovery_prompt(new_batch, operators)
        client = create_client()

        try:
            result = call_llm(client, "你是明日方舟角色数据库专家。只输出 JSON。", prompt)
        except Exception as e:
            print(f"  API 错误: {e}")
            continue

        stats = result.get("_stats", {})
        ti = stats.get("tokens_in", 0)
        to = stats.get("tokens_out", 0)
        cost = ti / 1_000_000 * 0.27 + to / 1_000_000 * 1.10
        total_cost += cost
        print(f"  tokens: in={ti:,} out={to:,} cost=${cost:.4f}", flush=True)

        if result.get("_parse_error"):
            print(f"  JSON 解析失败")
            raw = result.get("_raw", "")
            print(f"  raw: {raw[:200]}")
            continue

        mappings = result.get("mappings", [])
        batch_found = 0
        for m in mappings:
            name = m.get("unmapped_name", "")
            rel = m.get("relation", "none")
            if name and rel != "none":
                all_found[name] = {
                    "operator_name": m.get("operator_name", ""),
                    "relation": rel,
                    "reason": m.get("reason", ""),
                }
                batch_found += 1
                print(f"  {name} -> {m['operator_name']} ({rel})", flush=True)

        if batch_found == 0:
            print(f"  (无新映射)")

        # Save after each batch
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_found, f, ensure_ascii=False, indent=2)

        time.sleep(0.5)  # rate limit

    # Final summary
    print(f"\n=== 全量发现完成 ===")
    print(f"总候选映射: {len(all_found)}")
    print(f"估算成本: ${total_cost:.4f}")
    print(f"结果: {output_path}")

    # Print candidate identity_map entries
    print("\n=== 候选 identity_map 条目 ===")
    for name, info in sorted(all_found.items()):
        print(f'    "{name}": "{info["operator_name"]}",  # {info["relation"]}: {info["reason"]}')


if __name__ == "__main__":
    main()
