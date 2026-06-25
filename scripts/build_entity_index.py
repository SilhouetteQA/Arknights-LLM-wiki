"""构建双向实体索引 — 遍历所有数据源，生成 entity_source_map.json

用法:
    python scripts/build_entity_index.py --data-dir data --output data/entity_source_map.json

数据源:
    - data/extractions/v1_events/  (main/side/special, .json 文件)
    - data/extractions/v2_characters/  (.json 文件)
    - data/extractions/v3_wiki/concepts/  (.md 文件)
    - data/extractions/v3_wiki/factions/  (.md 文件)
    - data/extractions/v3_wiki/locations/  (.md 文件)
    - data/lorebook/terra_a_journey/  (page_XXX.md 文件)

输出格式 example:
{
  "巨兽": {
    "type": "concept",
    "source_files": {
      "pass1_events": ["画中人.json"],
      "operator_archives": [],
      "terra_journey": ["page_042.md"]
    },
    "related_entities": ["岁兽", "耶拉冈德"],
    "related_factions": [],
    "related_locations": ["萨米"],
    "related_characters": ["重岳", "夕"]
  }
}
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path


# ── 第一阶段: 收集所有实体 ─────────────────────────────────────────────

def build_index(data_dir: str) -> dict:
    """构建完整双向实体索引"""

    index: dict[str, dict] = {}

    def _ensure(entity_name: str, entity_type: str) -> dict:
        """确保实体存在于索引中，返回其条目"""
        if entity_name not in index:
            index[entity_name] = {
                "type": entity_type,
                "source_files": {
                    "pass1_events": [],
                    "characters": [],
                    "operator_archives": [],
                    "terra_journey": [],
                },
                "related_entities": [],
                "related_factions": [],
                "related_locations": [],
                "related_characters": [],
            }
        return index[entity_name]

    def _add_source(entity_name: str, source_key: str, filename: str):
        """记录实体出现在某个源文件中"""
        entry = _ensure(entity_name, "")  # type 在发现时推断
        if filename not in entry["source_files"][source_key]:
            entry["source_files"][source_key].append(filename)

    # ── 1a. 扫描 v1_events ──
    events_dir = os.path.join(data_dir, "extractions", "v1_events")
    if os.path.isdir(events_dir):
        for root, _dirs, files in os.walk(events_dir):
            for fname in files:
                if not fname.endswith(".json"):
                    continue
                fp = os.path.join(root, fname)
                try:
                    data = json.loads(Path(fp).read_text(encoding="utf-8"))
                except Exception:
                    continue
                for evt in data.get("events", []):
                    # 参与者 → character
                    for p in evt.get("participants", []):
                        if p and p.strip():
                            entry = _ensure(p, "character")
                            if fname not in entry["source_files"]["pass1_events"]:
                                entry["source_files"]["pass1_events"].append(fname)
                    # 地点 → location
                    loc = evt.get("location", "")
                    if loc and loc.strip():
                        entry = _ensure(loc, "location")
                        if fname not in entry["source_files"]["pass1_events"]:
                            entry["source_files"]["pass1_events"].append(fname)

    # ── 1b. 扫描 v2_characters ──
    chars_dir = os.path.join(data_dir, "extractions", "v2_characters")
    if os.path.isdir(chars_dir):
        for fname in os.listdir(chars_dir):
            if not fname.endswith(".json"):
                continue
            fp = os.path.join(chars_dir, fname)
            try:
                data = json.loads(Path(fp).read_text(encoding="utf-8"))
            except Exception:
                continue
            display_name = data.get("name_zh") or os.path.splitext(fname)[0]
            entry = _ensure(display_name, "character")
            _add_source(display_name, "characters", fname)
            # 阵营关联
            for aff in data.get("affiliations", []):
                if aff and aff.strip():
                    _add_source(display_name, "characters", fname)
                    faction_entry = _ensure(aff, "faction")
            # 章节关联
            for ch in data.get("source_pass1_chapters", []):
                if ch and ch.strip():
                    chapter_entry = _ensure(ch, "chapter")

    # ── 1c. 扫描 v3_wiki/concepts ──
    concepts_dir = os.path.join(data_dir, "extractions", "v3_wiki", "concepts")
    _scan_md_dir(concepts_dir, "concept", index, "terra_journey")  # concepts 不用 terra_journey key，但后续 cross-ref 需要

    # ── 1d. 扫描 v3_wiki/factions ──
    factions_dir = os.path.join(data_dir, "extractions", "v3_wiki", "factions")
    _scan_md_dir(factions_dir, "faction", index, None)

    # ── 1e. 扫描 v3_wiki/locations ──
    locations_dir = os.path.join(data_dir, "extractions", "v3_wiki", "locations")
    _scan_md_dir(locations_dir, "location", index, None)

    # ── 1f. 扫描 lorebook/terra_a_journey ──
    terra_dir = os.path.join(data_dir, "lorebook", "terra_a_journey")
    if os.path.isdir(terra_dir):
        for fname in sorted(os.listdir(terra_dir)):
            if not fname.endswith(".md") or not fname.startswith("page_"):
                continue
            fp = os.path.join(terra_dir, fname)
            try:
                content = Path(fp).read_text(encoding="utf-8")
            except Exception:
                continue
            # 提取 TERRA A ORIGINUM 章节标题
            chapter_match = re.search(r"CHAPTER\s+\d+\s+([A-Z\s/]+)", content)
            if chapter_match:
                chapter_title = chapter_match.group(1).strip()
                entry = _ensure(chapter_title, "chapter")

    # ── 第二阶段: 交叉引用 (wiki 页面内容中出现的实体名) ──
    # 收集所有已知实体名用于匹配，过滤掉过短或无效的名称
    all_entity_names = {name for name in index.keys() if len(name) >= 2 and name.strip()}
    # 对每个概念/阵营/地点 wiki 页面，扫描内容中是否提到了其他实体
    wiki_dirs = [
        (os.path.join(data_dir, "extractions", "v3_wiki", "concepts"), "concept"),
        (os.path.join(data_dir, "extractions", "v3_wiki", "factions"), "faction"),
        (os.path.join(data_dir, "extractions", "v3_wiki", "locations"), "location"),
    ]
    for wiki_dir, ent_type in wiki_dirs:
        if not os.path.isdir(wiki_dir):
            continue
        for fname in os.listdir(wiki_dir):
            if not fname.endswith(".md"):
                continue
            fp = os.path.join(wiki_dir, fname)
            try:
                content = Path(fp).read_text(encoding="utf-8")
            except Exception:
                continue
            page_name = os.path.splitext(fname)[0]
            # 在内容中查找所有已知实体名
            for other_name in all_entity_names:
                if other_name == page_name:
                    continue
                if other_name not in content:
                    continue
                # 确保是词边界匹配（避免 "龙门" 匹配到 "龙门币"）
                if _is_word_boundary_match(content, other_name):
                    _add_cross_reference(index, page_name, other_name)

    # ── 第三阶段: 合并/去重 related 字段 ──
    valid_names = all_entity_names  # already filtered to len >= 2
    for entry in index.values():
        for rel_field in ["related_entities", "related_factions", "related_locations", "related_characters"]:
            entry[rel_field] = sorted(
                {item for item in set(entry[rel_field]) if item in valid_names}
            )
        # 去重 source_files
        for src_key in entry["source_files"]:
            entry["source_files"][src_key] = sorted(set(entry["source_files"][src_key]))

    # 移除过短或无效名称的实体 (通过 participant 等途径可能引入)
    for name in list(index.keys()):
        if len(name) < 2 or not name.strip():
            del index[name]

    return index


def _scan_md_dir(dir_path: str, entity_type: str, index: dict, _unused: str | None):
    """扫描 markdown 目录，收集实体名"""
    if not os.path.isdir(dir_path):
        return
    for fname in os.listdir(dir_path):
        if not fname.endswith(".md"):
            continue
        entity_name = os.path.splitext(fname)[0]
        if entity_name not in index:
            index[entity_name] = {
                "type": entity_type,
                "source_files": {
                    "pass1_events": [],
                    "characters": [],
                    "operator_archives": [],
                    "terra_journey": [],
                },
                "related_entities": [],
                "related_factions": [],
                "related_locations": [],
                "related_characters": [],
            }
        else:
            # 已存在则更新类型（参与者可能被标记为 character，这里可能是 concept）
            # 保留首次发现的类型
            pass


def _add_cross_reference(index: dict, source_name: str, target_name: str):
    """双向添加交叉引用关系"""
    if source_name not in index or target_name not in index:
        return

    source_type = index[source_name]["type"]
    target_type = index[target_name]["type"]

    # 根据 target 类型，添加到 source 的对应 related_* 字段
    rel_map = {
        "concept": "related_entities",
        "faction": "related_factions",
        "location": "related_locations",
        "character": "related_characters",
        "chapter": "related_entities",  # chapter 也归入概念关联
    }

    src_rel_field = rel_map.get(target_type, "related_entities")
    tgt_rel_field = rel_map.get(source_type, "related_entities")

    if target_name not in index[source_name][src_rel_field]:
        index[source_name][src_rel_field].append(target_name)
    if source_name not in index[target_name][tgt_rel_field]:
        index[target_name][tgt_rel_field].append(source_name)


def _is_word_boundary_match(content: str, name: str) -> bool:
    """检查 name 是否作为独立词/短语出现在 content 中

    最小长度 2 个字以上的实体才做词边界检查；单字直接包含匹配即可。
    """
    if len(name) <= 2:
        return True
    # 对于中文实体，使用 lookahead/lookbehind 检查不被中文字符包围
    # 中文字符范围: 一-鿿
    pattern = re.compile(r"(?<![一-鿿])" + re.escape(name) + r"(?![一-鿿])")
    return bool(pattern.search(content))


# ── CLI ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="构建双向实体索引 entity_source_map.json")
    parser.add_argument("--data-dir", default="data", help="数据目录路径 (默认: data)")
    parser.add_argument("--output", default="data/entity_source_map.json", help="输出 JSON 文件路径")
    args = parser.parse_args()

    if not os.path.isdir(args.data_dir):
        print(f"错误: 数据目录不存在: {args.data_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"正在构建实体索引，数据目录: {args.data_dir}")
    index = build_index(args.data_dir)
    print(f"共发现 {len(index)} 个实体")

    # 统计各类型数量
    type_counts = defaultdict(int)
    for entry in index.values():
        type_counts[entry["type"]] += 1
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")

    # 确保输出目录存在
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"索引已写入: {args.output}")


if __name__ == "__main__":
    main()
