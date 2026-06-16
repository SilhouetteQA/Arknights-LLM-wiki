"""章节对话加载：遍历 JSON 文件 → 拼接为 [说话者] 文本 + 行号数组"""
import json, os
from dataclasses import dataclass, field


@dataclass
class ChapterDialogue:
    chapter: str
    category: str
    nodes: list[str] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)

    @property
    def text(self) -> str:
        """拼接为 [说话者] 文本 格式"""
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
        return int(len(self.text) / 1.5)


def load_chapter(chapter_dir: str) -> ChapterDialogue:
    """加载章节目录下所有 JSON 文件，按文件名排序拼接"""
    json_files = sorted(f for f in os.listdir(chapter_dir) if f.endswith(".json"))
    if not json_files:
        raise FileNotFoundError(f"章节目录 {chapter_dir} 下无 JSON 文件")

    chapter_name = os.path.basename(chapter_dir.rstrip("/\\"))
    result = ChapterDialogue(chapter=chapter_name, category="", nodes=[], lines=[])

    for jf in json_files:
        with open(os.path.join(chapter_dir, jf), "r", encoding="utf-8") as f:
            node = json.load(f)
        result.nodes.append(jf)
        if not result.category and node.get("category"):
            result.category = node["category"]
        for line in node.get("lines", []):
            result.lines.append({
                "index": len(result.lines) + 1,
                "speaker": line.get("speaker", ""),
                "type": line.get("type", "dialogue"),
                "text": line.get("text", ""),
                "_node_file": jf,
            })

    return result


def split_chapter(cd: ChapterDialogue, max_tokens: int = 128000) -> list[ChapterDialogue]:
    """超大章切成 2 批，在总 token 数一半处最近 node 边界切断"""
    if cd.token_estimate <= max_tokens:
        return [cd]

    # 累计 token 找中点
    half_target = cd.token_estimate // 2
    cumulative = 0
    split_node_idx = 0
    for i, n in enumerate(cd.nodes):
        node_tokens = 0
        for line in cd.lines:
            if line.get("_node_file") == n:
                node_tokens += len(line.get("text", "")) // 1.5
        cumulative += node_tokens
        if cumulative >= half_target:
            split_node_idx = i
            break

    batch1_nodes = cd.nodes[:split_node_idx]
    batch2_nodes = cd.nodes[split_node_idx:]

    def _filter_lines(target_nodes):
        return [dict(l) for l in cd.lines if l.get("_node_file") in target_nodes]

    batch1 = ChapterDialogue(
        chapter=f"{cd.chapter} (批次 1/2)", category=cd.category,
        nodes=batch1_nodes, lines=_filter_lines(batch1_nodes))
    batch2 = ChapterDialogue(
        chapter=f"{cd.chapter} (批次 2/2)", category=cd.category,
        nodes=batch2_nodes, lines=_filter_lines(batch2_nodes))
    return [batch1, batch2]
