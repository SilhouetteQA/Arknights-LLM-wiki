"""Pass 2 角色聚合：从 Pass 1 提取结果中按参与者收集事件，规范化后合并，过滤目标角色"""

import json
import os
import re
from difflib import SequenceMatcher

from arknights_wiki.extraction.dialogue_loader import ChapterDialogue, load_chapter


def normalize_participant(name: str, op_names: set, id_map: dict) -> str:
    """规范化参与者名称。

    处理步骤：
    1. 去除首尾空白
    2. 去除中英文问号
    3. 去除括号及括号内内容（如 "(幼年)"）
    4. 去除书名号/双引号（「」、『』）
    5. 精确匹配干员名
    6. identity_map 精确映射
    7. 复合名 · 拆分后匹配（id_map + op_names）
    8. 模糊匹配（SequenceMatcher >= 0.6）
    """
    name = name.strip()

    if not name:
        return name

    # 去除中英文问号
    name = name.rstrip("?？")

    # 去除括号及括号内内容（中英文括号）
    name = re.sub(r"[（(][^）)]*[）)]", "", name).strip()

    # 去除书名号、双引号等
    name = name.strip("「」")

    if not name:
        return name

    # 精确匹配干员名
    if name in op_names:
        return name

    # identity_map 精确映射
    if name in id_map:
        canonical = id_map[name]
        if not canonical.startswith("character:"):
            return canonical
        return name

    # 复合名 · 拆分匹配
    if "·" in name:
        segments = name.split("·")
        for part in segments:
            if part in id_map:
                canonical = id_map[part]
                if not canonical.startswith("character:"):
                    return canonical
            if part in op_names:
                return part

    # 模糊匹配
    best_ratio = 0.0
    best_name = name
    for opn in op_names:
        len_diff = abs(len(name) - len(opn))
        if len_diff > 5:
            continue
        ratio = SequenceMatcher(None, name, opn).ratio()
        if ratio >= 0.6 and ratio > best_ratio:
            best_ratio = ratio
            best_name = opn

    if best_ratio >= 0.6:
        return best_name

    # 无匹配，保持原名
    return name


def collect_from_v1(v1_dir: str) -> dict:
    """扫描 v1_events 目录下 main/side/special 子目录，按参与者收集事件。

    返回格式:
    {
        "参与者原始名": {
            "events": [
                {
                    "chapter": str,
                    "category": str,
                    "pass1_index": int,
                    "event": str,
                    "type": str,
                    "line_range": [int, int],
                    "significance": str,
                    "is_imaginary": bool,
                },
                ...
            ],
            "chapters": {"章名1", "章名2", ...},
        },
        ...
    }
    """
    result: dict = {}

    for category in ("main", "side", "special"):
        cat_dir = os.path.join(v1_dir, category)
        if not os.path.isdir(cat_dir):
            continue

        for filename in os.listdir(cat_dir):
            if not filename.endswith(".json"):
                continue

            filepath = os.path.join(cat_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                continue

            chapter = data.get("chapter", filename.replace(".json", ""))
            events = data.get("events", [])

            for i, event in enumerate(events):
                if not isinstance(event, dict):
                    continue
                participants = event.get("participants")
                if not participants or not isinstance(participants, list):
                    continue

                for participant in participants:
                    if not participant or not isinstance(participant, str):
                        continue
                    participant = participant.strip()
                    if not participant:
                        continue

                    if participant not in result:
                        result[participant] = {
                            "events": [],
                            "chapters": set(),
                        }

                    result[participant]["events"].append({
                        "chapter": chapter,
                        "category": data.get("category", ""),
                        "pass1_index": i,
                        "event": event.get("event", ""),
                        "type": event.get("type", ""),
                        "line_range": event.get("line_range", []),
                        "significance": event.get("significance", ""),
                        "is_imaginary": event.get("is_imaginary", False),
                    })
                    result[participant]["chapters"].add(chapter)

    return result


def normalize_and_merge(
    raw_participants: dict,
    operators: list,
    id_map: dict,
) -> dict:
    """规范化参与者名字并合并同名条目。

    返回格式:
    {
        "规范名": {
            "aliases": {"原始名1", "原始名2", ...},
            "chapters": {"章1", "章2", ...},
            "events": [...],
        },
        ...
    }
    """
    op_names = {op["name_zh"] for op in operators}

    # 先规范化所有参与者名
    canonical_map: dict[str, str] = {}
    for raw_name in raw_participants:
        canonical = normalize_participant(raw_name, op_names, id_map)
        canonical_map[raw_name] = canonical

    # 按规范名合并
    merged: dict = {}
    for raw_name, entry in raw_participants.items():
        canonical = canonical_map[raw_name]

        if canonical not in merged:
            merged[canonical] = {
                "aliases": set(),
                "chapters": set(),
                "events": [],
            }

        merged_entry = merged[canonical]
        if raw_name != canonical:
            merged_entry["aliases"].add(raw_name)
        merged_entry["chapters"] |= entry["chapters"]
        merged_entry["events"].extend(entry["events"])

    return merged


def filter_targets(
    merged: dict,
    operators: list,
    keep_set: set,
) -> dict:
    """过滤目标角色：干员 + 多章 NPC + 用户 KEEP 单章 NPC。

    保留条件（满足任一即保留）：
    1. 规范名精确匹配干员列表中的 name_zh
    2. 出场章节 >= 2 的 NPC
    3. 在用户 KEEP 集合中的单章 NPC
    """
    op_names = {op["name_zh"] for op in operators}

    result: dict = {}
    for name, entry in merged.items():
        if name in op_names:
            result[name] = entry
            continue

        num_chapters = len(entry["chapters"])
        if num_chapters >= 2:
            result[name] = entry
            continue

        if num_chapters == 1 and name in keep_set:
            result[name] = entry
            continue

    return result


def parse_keep_list(md_path: str) -> set[str]:
    """解析单次出场 NPC markdown 文件，提取 [KEEP] 标记的角色名。

    文件格式为 markdown 表格，每行格式:
    | # | 角色名 | 事件类型 | 事件描述 | 处理 |
    [KEEP] 或 [KEEP ] 表示保留。
    """
    keep_set: set[str] = set()

    if not os.path.exists(md_path):
        return keep_set

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content:
        return keep_set

    # 按行解析表格，标记 | 分隔
    for line in content.split("\n"):
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue

        # 跳过表头分隔行
        if re.match(r"^\|[-:\s|]+\|", line):
            continue

        cells = [c.strip() for c in line.split("|")[1:-1]]  # 去掉首尾空 cell
        if len(cells) < 5:
            continue

        # cells[0] 是序号 #, cells[1] 是角色名, cells[4] 是处理标记
        # 但表头行 cells[0] 可能是 "#"
        if cells[0] == "#":
            continue

        character_name = cells[1]
        action = cells[4] if len(cells) > 4 else ""

        # 检查是否有 [KEEP] 标记（允许 [KEEP ] 带空格）
        if re.search(r"\[KEEP\s*\]", action, re.IGNORECASE):
            keep_set.add(character_name)

    return keep_set


def _cut_lines(cd: ChapterDialogue, start: int, end: int, buffer: int = 3) -> str:
    """从 ChapterDialogue 中截取指定行范围 + 前后 buffer 行的文本。

    格式: "[global_index] [speaker] text"（旁白无 speaker 时省略）
    """
    total_lines = len(cd.lines)

    # 计算截取范围（1-indexed）
    cut_start = max(1, start - buffer)
    cut_end = min(total_lines, end + buffer)

    parts = []
    for line in cd.lines:
        idx = line.get("global_index", 0)
        if idx < cut_start:
            continue
        if idx > cut_end:
            break

        speaker = line.get("speaker", "")
        text = line.get("text", "")

        if speaker:
            parts.append(f"[{idx}] [{speaker}] {text}")
        else:
            parts.append(f"[{idx}] {text}")

    return "\n".join(parts)


def inject_context(targets: dict, data_dir: str = "data/stories") -> dict:
    """为每个目标角色的每个事件注入原文上下文。

    按 chapter 加载 ChapterDialogue（带缓存），
    根据 event 的 line_range 调用 _cut_lines 截取原文。

    事件新增 context 字段。

    注意：直接修改传入的 targets 字典（原地注入 context_text），同时返回该字典以支持链式调用。
    """
    chapter_cache: dict = {}

    for name, entry in targets.items():
        for event in entry.get("events", []):
            chapter = event.get("chapter", "")
            if not chapter:
                continue

            if chapter not in chapter_cache:
                chapter_dir = os.path.join(data_dir, chapter)
                try:
                    cd = load_chapter(chapter_dir)
                except (FileNotFoundError, json.JSONDecodeError):
                    chapter_cache[chapter] = None
                    continue
                chapter_cache[chapter] = cd

            cd = chapter_cache.get(chapter)
            if cd is None:
                continue

            line_range = event.get("line_range", [])
            if not isinstance(line_range, list) or len(line_range) != 2:
                continue

            event["context_text"] = _cut_lines(cd, line_range[0], line_range[1])

    return targets


def get_operator_archive(name_zh: str, operators: list) -> dict | None:
    """从干员列表中按 name_zh 精确查找档案。

    Returns:
        archives dict if found, None otherwise
    """
    for op in operators:
        if op.get("name_zh") == name_zh:
            return op.get("archives")
    return None
