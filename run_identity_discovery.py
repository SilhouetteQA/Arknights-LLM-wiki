"""Pass 2 身份映射发现：用 LLM 知识识别真名/别名→干员的映射"""
import json
import sys
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
    id_map_keys = set(id_map.keys())

    # Find unmapped names with >=5 events
    unmapped = []
    for name, data in merged.items():
        if name in op_names:
            continue
        if name in id_map_keys:
            continue
        n_ev = len(data["events"])
        if n_ev >= 5:
            chapters = list(data["chapters"])
            unmapped.append({
                "name": name,
                "events": n_ev,
                "chapters": len(chapters),
                "sample_chapter": chapters[0],
                "aliases": list(data.get("aliases", set())),
            })

    unmapped.sort(key=lambda x: -x["events"])
    return unmapped, operators


def build_discovery_prompt(unmapped_batch: list[dict], operators: list[dict]) -> str:
    """构建身份映射发现提示词"""
    op_summary = []
    for op in operators:
        op_summary.append(f"- {op['name_zh']}（{op.get('race','?')}/{op.get('nation','?')}）")

    name_list = []
    for u in unmapped_batch:
        alias_str = f" [别名: {', '.join(u['aliases'])}]" if u['aliases'] else ""
        name_list.append(
            f"- {u['name']}（{u['events']}次出场, {u['chapters']}章, 如{u['sample_chapter']}）{alias_str}"
        )

    prompt = f"""你是明日方舟角色数据库专家。你的任务是识别以下「未映射角色名」中，哪些是已有干员的真名、别名、或代号变体。

## 干员列表（共{len(operators)}人）

{chr(10).join(op_summary[:200])}

（仅展示前200名干员，完整列表过长省略）

## 未映射角色名（{len(unmapped_batch)}个）

{chr(10).join(name_list)}

## 要求

判断每个未映射角色名是否与某个干员存在以下关系：
1. **真名/本名**：该角色名是某干员的本名（如「蕾缪乐」是「能天使」的本名）
2. **别名/外号**：该角色名是某干员的别名或外号（如「苦难陈述者」是「菲亚梅塔」的外号）
3. **曾用名/代号变体**：该角色名是某干员曾用或变体的代号
4. **无关联**：该角色名是独立NPC，与现有干员无关

只输出 JSON，不含 markdown 标记。JSON 字符串内禁止英文双引号，用「」代替。

```json
{{
  "mappings": [
    {{"unmapped_name": "未映射角色名", "operator_name": "对应干员名", "relation": "real_name|alias|variant|none", "confidence": "high|medium|low", "reason": "一句话说明"}}
  ]
}}
```

对于 relation=none 的条目，operator_name 留空字符串。
"""
    return prompt


def main():
    unmapped, operators = load_data()
    print(f"未映射角色（>=5事件）: {len(unmapped)}")
    print(f"干员总数: {len(operators)}")

    # 分批处理，每批40个未映射名
    batch_size = 40
    all_mappings = []

    for i in range(0, min(len(unmapped), 120), batch_size):
        batch = unmapped[i : i + batch_size]
        print(f"\n处理批次 {i//batch_size + 1}: {len(batch)} 个未映射名...")

        prompt = build_discovery_prompt(batch, operators)
        client = create_client()
        result = call_llm(client, "你是明日方舟角色数据库专家。只输出 JSON，不含 markdown。", prompt)

        if result.get("_parse_error"):
            print(f"  解析失败: {result.get('_raw', '')[:200]}")
            continue

        mappings = result.get("mappings", [])
        stats = result.get("_stats", {})
        print(f"  tokens: in={stats.get('tokens_in',0):,} out={stats.get('tokens_out',0):,}")

        for m in mappings:
            if m.get("relation") != "none" and m.get("confidence") in ("high", "medium"):
                all_mappings.append(m)
                print(f"  {m['unmapped_name']} → {m['operator_name']} ({m['relation']}, {m['confidence']})")

    # 输出候选映射
    print(f"\n=== 候选映射 ({len(all_mappings)} 条) ===")
    for m in all_mappings:
        print(f"  \"{m['unmapped_name']}\": \"{m['operator_name']}\",  # {m['relation']}, {m['confidence']}: {m['reason']}")

    # 输出可直接添加到 identity_map 的格式
    print("\n=== identity_map 格式 ===")
    for m in all_mappings:
        print(f'    "{m["unmapped_name"]}": "{m["operator_name"]}",')


if __name__ == "__main__":
    main()
