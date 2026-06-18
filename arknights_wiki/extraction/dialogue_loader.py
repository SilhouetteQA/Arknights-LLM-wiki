"""章节对话加载：遍历 JSON 文件 → 场景结构 → 场景内行号

文件顺序来自 _order.json（从 data/index.json 的 PRTS Wiki 抓取顺序生成，= 游戏内实际顺序）
"""
import json, os, re
from dataclasses import dataclass, field


@dataclass
class ChapterDialogue:
    chapter: str
    category: str
    nodes: list[str] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)

    def scene_count(self) -> int:
        """场景数 = node 文件数"""
        return len(self.nodes)

    @property
    def text(self) -> str:
        """以场景为单位的格式化对话文本，场景内行号独立编号。

        格式:
        ## Scene 1: NL-ST-1_欣欣向荣 (267 行)
        [1] [佐菲娅] ——好！到此为止！
        [2] [佐菲娅] 还有疼痛感吗？
        """
        parts = []
        scene_num = 0
        for nf in self.nodes:
            scene_lines = [l for l in self.lines if l.get("_node_file") == nf]
            if not scene_lines:
                continue
            scene_num += 1
            scene_label = nf.replace(".json", "")
            # 对 ending PART 场景，附加结局标题
            if "_ending_PART" in nf:
                first_line = scene_lines[0]
                ending_title = first_line.get("_ending_title", "")
                if ending_title:
                    scene_label = f"{ending_title} {scene_label}"
                # 标记为想象事件来源
                parts.append(f"\n## Scene {scene_num}: {scene_label} ({len(scene_lines)} 行) [IS-IF线结局叙事]")
            else:
                parts.append(f"\n## Scene {scene_num}: {scene_label} ({len(scene_lines)} 行)")

            for li, line in enumerate(scene_lines, 1):
                if line["type"] == "dialogue" and line["speaker"]:
                    parts.append(f"[{li}] [{line['speaker']}] {line['text']}")
                else:
                    parts.append(f"[{li}] {line['text']}")

        return "\n".join(parts)

    @property
    def text_no_markers(self) -> str:
        """无场景标记的纯文本，用于 token 估算"""
        parts = []
        for line in self.lines:
            if line["type"] == "dialogue" and line["speaker"]:
                parts.append(f"[{line['speaker']}] {line['text']}")
            else:
                parts.append(line["text"])
        return "\n".join(parts)

    @property
    def token_estimate(self) -> int:
        """粗略 token 估算：字符数 / 1.5"""
        return int(len(self.text_no_markers) / 1.5)


def _split_by_parts(text: str) -> list[tuple[str, str]]:
    """将结局文本按 PART N 标记拆分为多个 (part_label, part_text) 块。

    PART 格式: 行首的 `PART N ...`（N = 1-9）
    返回的 part_label 如 "PART1", "PART2" 等。
    第一个 PART 标记之前的文本（标题行等）合并到 PART1 块开头。
    """
    lines = text.split("\n")
    part_pattern = re.compile(r"^PART (\d+)\b")
    blocks = []
    current_label = None
    current_lines = []
    pre_part_lines = []  # 第一个 PART 之前的文本，合并到 PART1

    for line in lines:
        m = part_pattern.match(line.strip())
        if m:
            part_num = int(m.group(1))
            if current_label is not None and current_lines:
                blocks.append((current_label, "\n".join(current_lines)))
            elif part_num == 1 and pre_part_lines:
                # 第一个 PART 之前的文本合并到 PART1
                pass
            current_label = f"PART{part_num}"
            current_lines = pre_part_lines + [line] if part_num == 1 and pre_part_lines else [line]
            pre_part_lines = []
        else:
            if current_label is None:
                pre_part_lines.append(line)
            else:
                current_lines.append(line)

    if current_label is not None and current_lines:
        blocks.append((current_label, "\n".join(current_lines)))

    return blocks


def load_chapter(chapter_dir: str) -> ChapterDialogue:
    """加载章节目录下所有 JSON 文件。

    优先读取 _order.json（PRTS Wiki 游戏顺序）。
    """
    order_path = os.path.join(chapter_dir, "_order.json")
    if os.path.exists(order_path):
        with open(order_path, "r", encoding="utf-8") as f:
            ordered = json.load(f)
        existing = set(os.listdir(chapter_dir))
        # 仅保留实际存在且非 _ending 的 story node
        json_files = [f for f in ordered if f in existing and f.endswith(".json") and "_ending" not in f]
        # 追加 _order.json 中未列出的 story node（排除 _ending、_order、_ 前缀）
        for f in sorted(os.listdir(chapter_dir)):
            if f.endswith(".json") and f not in json_files and not f.startswith("_") and "_ending" not in f:
                json_files.append(f)
    else:
        json_files = sorted(f for f in os.listdir(chapter_dir)
                          if f.endswith(".json") and not f.startswith("_") and "_ending" not in f)

    # 为每个 story node 注入对应的 _ending.json（集成战略结局文本）
    enhanced_files = []
    for jf in json_files:
        enhanced_files.append(jf)
        base = jf.replace(".json", "")
        ending_file = f"{base}_ending.json"
        if os.path.exists(os.path.join(chapter_dir, ending_file)):
            enhanced_files.append(ending_file)
    json_files = enhanced_files

    if not json_files:
        raise FileNotFoundError(f"章节目录 {chapter_dir} 下无 JSON 文件")

    chapter_name = os.path.basename(chapter_dir.rstrip("/\\"))
    result = ChapterDialogue(chapter=chapter_name, category="", nodes=[], lines=[])

    for jf in json_files:
        file_path = os.path.join(chapter_dir, jf)
        with open(file_path, "r", encoding="utf-8") as f:
            node = json.load(f)

        if jf.endswith("_ending.json"):
            # 按 PART 标记拆分为独立场景，每个 PART 一个虚拟 node
            ending_title = node.get("ending_title", "")
            ending_source = node.get("source", "")
            ending_text = node.get("text", "")
            part_blocks = _split_by_parts(ending_text)
            for part_label, part_lines_text in part_blocks:
                part_node_name = jf.replace(".json", f"_{part_label}")
                result.nodes.append(part_node_name)
                for line_text in part_lines_text.split("\n"):
                    line_text = line_text.strip()
                    if line_text:
                        result.lines.append({
                            "global_index": len(result.lines) + 1,
                            "speaker": "",
                            "type": "narration",
                            "text": line_text,
                            "_node_file": part_node_name,
                            "_ending_title": ending_title,
                            "_ending_source": ending_source,
                        })
        else:
            result.nodes.append(jf)
            if not result.category and node.get("category"):
                result.category = node["category"]
            for line in node.get("lines", []):
                result.lines.append({
                    "global_index": len(result.lines) + 1,
                    "speaker": line.get("speaker", ""),
                    "type": line.get("type", "dialogue"),
                    "text": line.get("text", ""),
                    "_node_file": jf,
                })

    return result


def scene_line_to_global(cd: ChapterDialogue, scene_num: int, local_line: int) -> int:
    """将场景内行号转换为全局行号"""
    if scene_num < 1 or scene_num > len(cd.nodes):
        return 0

    target_nf = cd.nodes[scene_num - 1]
    count = 0
    for nf in cd.nodes:
        if nf == target_nf:
            break
        count += sum(1 for l in cd.lines if l.get("_node_file") == nf)

    return count + local_line


def split_chapter(
    cd: ChapterDialogue,
) -> list[ChapterDialogue]:
    """按 node 自然边界切分章节。

    - 总行 <= 1500: 不分段
    - 1500 < 总行 <= 3000: 2 段，在最近中点的 node 边界切断
    - 总行 > 3000: 3 段，在 1/3 和 2/3 处的 node 边界切断
    """
    total = len(cd.lines)
    if total <= 1500:
        return [cd]

    if total <= 3000:
        num_batches = 2
    else:
        num_batches = 3

    target_per_batch = total / num_batches

    node_line_counts = []
    for n in cd.nodes:
        node_line_counts.append(sum(1 for l in cd.lines if l.get("_node_file") == n))

    split_points = []
    for target_i in range(1, num_batches):
        target = target_per_batch * target_i
        best_idx = 0
        best_dist = float('inf')
        cum = 0
        for i, nlc in enumerate(node_line_counts):
            cum += nlc
            dist = abs(cum - target)
            if dist < best_dist and i < len(node_line_counts) - 1:
                best_dist = dist
                best_idx = i + 1
        if best_idx > 0 and best_idx not in split_points:
            split_points.append(best_idx)

    split_points.sort()

    batches = []
    start = 0
    for sp in split_points:
        batch_nodes = cd.nodes[start:sp]
        batches.append(_make_batch(cd, batch_nodes, len(batches) + 1))
        start = sp
    if start < len(cd.nodes):
        batches.append(_make_batch(cd, cd.nodes[start:], len(batches) + 1))

    if len(batches) == 1:
        return [cd]

    for i, b in enumerate(batches):
        print(f"  段{i+1}: {b.nodes[0] if b.nodes else '?'} ... {b.nodes[-1] if b.nodes else '?'} ({len(b.lines)} 行, {len(b.nodes)} 场景)")

    return batches


def _make_batch(cd: ChapterDialogue, nodes: list[str], batch_num: int) -> ChapterDialogue:
    """创建批次 ChapterDialogue，重新计算 global_index"""
    batch_lines = [dict(l) for l in cd.lines if l.get("_node_file") in nodes]
    for i, l in enumerate(batch_lines):
        l["global_index"] = i + 1
    return ChapterDialogue(
        chapter=f"{cd.chapter} (批次 {batch_num})",
        category=cd.category,
        nodes=nodes,
        lines=batch_lines,
    )


def build_context_prompt(previous_batches: list[dict]) -> str:
    """将前几批的摘要和事件作为上下文传给下一批"""
    valid = [b for b in previous_batches if not b.get("_parse_error")]
    if not valid:
        return ""

    parts = ["## 前置剧情上下文（已提取的事件和摘要，供参考以保持连贯性）\n"]
    for i, batch in enumerate(valid):
        summary = batch.get("summary", "")
        events = batch.get("events", [])
        if summary:
            parts.append(f"### 前段 {i+1} 摘要\n{summary}\n")
        if events:
            parts.append(f"### 前段 {i+1} 事件")
            for ev in events:
                parts.append(
                    f"- [{ev.get('type', '?')}] {ev.get('event', '?')} "
                    f"(参与: {', '.join(ev.get('participants', []))})"
                )
            parts.append("")

    parts.append("---\n")
    parts.append("请基于以上前置剧情和下方对话，提取本段的事件。")
    parts.append("确保新提取的事件与前置事件连贯，不重复已提取的事件。\n")
    return "\n".join(parts)
