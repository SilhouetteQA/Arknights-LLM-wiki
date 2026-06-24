"""
用 faction_roster_index.json + identity_map.json 修复 v3_wiki 阵营成员:
1. 成员名规范化（异格→基体、真名→代号）
2. 按规范名去重（保留描述最丰富的条目）
3. 补全 operators.json 中有但 wiki 中缺失的干员
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent

# ── 索引名 → wiki 文件名 映射 ──
INDEX_TO_WIKI = {
    "莱茵生命": "莱茵生命.md",
    "彩虹小队": "彩虹小队.md",
    "乌萨斯学生自治团": "乌萨斯学生自治团.md",
    "黑钢国际": "黑钢国际.md",
    "深海猎人": "深海猎人.md",
    "企鹅物流": "企鹅物流.md",
    "罗德岛-精英干员": "罗德岛.md",
    "红松骑士团": "红松骑士团.md",
    "喀兰贸易": "喀兰贸易.md",
    "巴别塔": "巴别塔.md",
    "鲤氏侦探事务所": "鲤氏侦探事务所.md",
    "塔拉": "塔拉王国.md",
    "格拉斯哥帮": "格拉斯哥帮.md",
    "龙门近卫局": "龙门近卫局.md",
    "汐斯塔": "汐斯塔.md",
    "行动预备组A1": "罗德岛.md",
    "行动预备组A4": "罗德岛.md",
    "行动预备组A6": "罗德岛.md",
    "行动组A4": "罗德岛.md",
    "使徒": "罗德岛.md",
    "S.W.E.E.P.": "罗德岛.md",
    "炎-岁": None,
    "Ave Mujica": None,
    "贾维团伙": None,
    "莱欧斯小队": None,
}


def load_name_normalizer() -> Dict[str, str]:
    """构建名字规范化器: 任意名字 → 规范干员名"""
    norm: Dict[str, str] = {}

    # 从 identity_map 加载
    id_map_path = PROJECT_ROOT / "config" / "identity_map.json"
    id_map = json.loads(id_map_path.read_text(encoding='utf-8'))
    for key, value in id_map["mappings"].items():
        if isinstance(value, str) and value.startswith("character:"):
            continue
        norm[key] = value

    # 从 faction_roster_index 补充: 每个 member 的正规名就是它自己
    idx_path = PROJECT_ROOT / "data" / "faction_roster_index.json"
    idx = json.loads(idx_path.read_text(encoding='utf-8'))
    for faction_data in idx.values():
        for member in faction_data["members"]:
            if member not in norm:
                norm[member] = member

    # 添加额外规范化规则
    extras = {
        "恩希欧迪斯·希瓦艾什": "银灰",
        "恩希欧迪斯": "银灰",
        "诺希斯·埃德怀斯": "灵知",
        "诺希斯": "灵知",
        "桥夹克里夫": "克里夫",
        "克里夫": "克里夫",
        "克丽斯腾·莱特": "克丽斯腾",
        "克丽斯腾": "克丽斯腾",
        "奥利维亚·赫默": "赫默",
        "赫默": "赫默",
        "娜斯提·鲁诺瑞伊": "娜斯提",
        "娜斯提": "娜斯提",
        "贾斯汀·菲茨罗伊": "小贾斯汀",
        "小贾斯汀·菲茨罗伊": "小贾斯汀",
        "多萝西·弗兰克斯": "多萝西",
        "缪尔赛思": "缪尔赛思",
        "Doctor": "博士",
        "博士": "博士",
        "可露希尔": "可露希尔",
        "Mechanist": "Mechanist",
        "Misery": "Misery",
        "Sharp": "Sharp",
        "Stormeye": "Stormeye",
        "Pith": "Pith",
        "Touch": "Touch",
        "Scout": "Scout",
        "Ace": "Ace",
        "Guard": "Guard",
        "Outcast": "Outcast",
        "Logos": "逻各斯",
        "Mon3tr": "Mon3tr",
        "Raidian": "电弧",
        "Friston-3": "Friston-3",
        "Lancet-2": "Lancet-2",
    }
    norm.update(extras)
    return norm


def normalize_name(name: str, normalizer: Dict[str, str]) -> str:
    """规范化单个成员名"""
    n = name.strip()
    # 规范化弯引号
    n = n.replace('“', '"').replace('”', '"')
    n = n.replace('‘', ''').replace('’', ''')
    n = n.replace('「', '').replace('」', '')
    n = n.replace('『', '').replace('』', '')
    # 先精确匹配
    if n in normalizer:
        return normalizer[n]
    # 去掉括号内容再试
    cleaned = re.sub(r'[（(].*?[）)]', '', n).strip()
    if cleaned in normalizer:
        return normalizer[cleaned]
    # 去掉书名号
    cleaned2 = cleaned.replace('《', '').replace('》', '')
    if cleaned2 in normalizer:
        return normalizer[cleaned2]
    return n


def parse_member_section(content: str):
    """解析 wiki 文件中 ## 已知成员 段落，返回 (prefix, members, suffix)"""
    parts = content.split("## 已知成员")
    if len(parts) < 2:
        return content, []

    prefix = parts[0]
    member_text = parts[1]

    member_lines = member_text.split("\n")
    members: List[Dict] = []
    in_members = True
    suffix_lines: List[str] = []

    for line in member_lines:
        line = line.rstrip()
        if in_members:
            if line.startswith("## "):
                in_members = False
                suffix_lines.append(line)
                continue
            m = re.match(r'- \*\*(.+?)\*\*\s*(?:—|--)?\s*(.*)', line)
            if m and not m.group(2):
                # 无分隔符的情况: group(1) 可能包含了多余空白
                name_part = m.group(1).strip()
                desc_part = ""
            elif m:
                name_part = m.group(1).strip()
                desc_part = m.group(2).strip()
            if m:
                members.append({"name": name_part, "description": desc_part, "role": ""})
                continue
            if line.strip():
                suffix_lines.append(line)
            else:
                suffix_lines.append(line)
        else:
            suffix_lines.append(line)

    suffix = "\n".join(suffix_lines)
    return prefix, members, suffix


def rebuild_member_section(prefix: str, members: List[Dict], suffix: str) -> str:
    """用规范化后的成员列表重建 wiki 内容"""
    lines = [prefix.rstrip(), "", "## 已知成员", ""]
    for m in members:
        name = m["name"]
        desc = m.get("description", "").strip()
        if desc:
            lines.append("- **{}** — {}".format(name, desc))
        else:
            lines.append("- **{}**".format(name))
    lines.append("")
    if suffix:
        lines.append(suffix.rstrip())
    return "\n".join(lines) + "\n"


def fix_faction_wiki(
    wiki_path: Path,
    faction_index_name: str,
    faction_data: Dict,
    normalizer: Dict[str, str],
    dry_run: bool = True,
) -> Dict:
    """修复单个阵营 wiki 文件"""
    result = {
        "wiki_file": wiki_path.name,
        "index_faction": faction_index_name,
        "existing_members": 0,
        "after_dedup": 0,
        "added_operators": 0,
        "duplicates_removed": 0,
        "errors": [],
    }

    if not wiki_path.exists():
        result["errors"].append("Wiki file not found")
        return result

    content = wiki_path.read_text(encoding='utf-8')

    # 解析现有成员
    parsed = parse_member_section(content)
    if len(parsed) == 2:
        existing_members = []
        if "## 来源" in content:
            parts = content.split("## 来源", 1)
            prefix = parts[0].rstrip()
            suffix = "## 来源" + parts[1]
        else:
            prefix = content.rstrip()
            suffix = ""
    else:
        prefix, existing_members, suffix = parsed

    result["existing_members"] = len(existing_members)

    # Step 1: 规范化所有成员名并去重
    canonical_seen: Dict[str, Dict] = {}
    duplicates_removed = 0

    for m in existing_members:
        raw_name = m["name"]
        canonical = normalize_name(raw_name, normalizer)

        if canonical in canonical_seen:
            existing = canonical_seen[canonical]
            # 保留更丰富的描述
            if len(m.get("description", "")) > len(existing.get("description", "")):
                existing["description"] = m["description"]
                existing["name"] = raw_name
            elif m.get("role") and not existing.get("role"):
                existing["role"] = m["role"]
            duplicates_removed += 1
        else:
            canonical_seen[canonical] = {
                "name": raw_name if len(raw_name) >= len(canonical) else canonical,
                "description": m.get("description", ""),
                "role": m.get("role", ""),
                "canonical": canonical,
            }

    # Step 2: 添加 faction_roster_index 中有但 wiki 缺失的干员
    index_members = set(faction_data.get("members", []))
    added = 0
    for op_name in sorted(index_members):
        canonical = normalize_name(op_name, normalizer)
        if canonical not in canonical_seen:
            canonical_seen[canonical] = {
                "name": op_name,
                "description": "",
                "role": "",
                "canonical": canonical,
            }
            added += 1

    # Step 3: 对 罗德岛 特殊处理 —— 添加所有子阵营的成员
    if wiki_path.name == "罗德岛.md":
        faction_index = json.loads(
            (PROJECT_ROOT / "data" / "faction_roster_index.json").read_text(encoding='utf-8')
        )
        for sub_name, sub_data in faction_index.items():
            if INDEX_TO_WIKI.get(sub_name) == "罗德岛.md":
                for op_name in sub_data.get("members", []):
                    canonical = normalize_name(op_name, normalizer)
                    if canonical not in canonical_seen:
                        canonical_seen[canonical] = {
                            "name": op_name,
                            "description": "",
                            "role": "",
                            "canonical": canonical,
                        }
                        added += 1

    # 重建成员列表
    new_members: List[Dict] = []
    for canonical, data in sorted(canonical_seen.items()):
        entry = {"name": data["name"], "description": data.get("description", "")}
        if data.get("role"):
            entry["role"] = data["role"]
        new_members.append(entry)

    result["after_dedup"] = len(new_members)
    result["added_operators"] = added
    result["duplicates_removed"] = duplicates_removed

    # 重建文件内容
    new_content = rebuild_member_section(prefix, new_members, suffix)

    if not dry_run:
        wiki_path.write_text(new_content, encoding='utf-8')

    return result


def main():
    dry_run = "--apply" not in sys.argv

    print("=" * 80)
    print("V3 Wiki 阵营成员修复 {}".format("(DRY RUN)" if dry_run else "(APPLY)"))
    print("=" * 80)

    normalizer = load_name_normalizer()
    print("\n名字规范化器: {} 条映射".format(len(normalizer)))

    faction_index = json.loads(
        (PROJECT_ROOT / "data" / "faction_roster_index.json").read_text(encoding='utf-8')
    )
    print("阵营索引: {} 个阵营".format(len(faction_index)))

    wiki_dir = PROJECT_ROOT / "data" / "extractions" / "v3_wiki" / "factions"

    total_removed = 0
    total_added = 0

    for idx_name, idx_data in sorted(faction_index.items()):
        wiki_file = INDEX_TO_WIKI.get(idx_name)
        if wiki_file is None:
            print("\n  跳过 {} — 无对应 wiki 文件".format(idx_name))
            continue

        wiki_path = wiki_dir / wiki_file
        result = fix_faction_wiki(
            wiki_path, idx_name, idx_data, normalizer, dry_run=dry_run
        )

        if result["errors"]:
            print("\n  [{}] 错误: {}".format(idx_name, result["errors"]))
            continue

        dupes = result["duplicates_removed"]
        added = result["added_operators"]
        existing = result["existing_members"]
        final = result["after_dedup"]

        status_parts = []
        if dupes > 0:
            status_parts.append("去重-{}".format(dupes))
        if added > 0:
            status_parts.append("补全+{}".format(added))
        if not status_parts:
            status_parts.append("无需修改")

        print("  [{}] -> {}: {}->{}成员 ({})".format(
            idx_name, wiki_file, existing, final, ", ".join(status_parts)))

        total_removed += dupes
        total_added += added

    print("\n" + "=" * 80)
    print("总计: -{} 重复项, +{} 补全项".format(total_removed, total_added))
    if dry_run:
        print("DRY RUN 模式 — 未修改任何文件。加 --apply 参数执行实际操作。")
    else:
        print("已应用所有修改。")
    print("=" * 80)


if __name__ == "__main__":
    main()
