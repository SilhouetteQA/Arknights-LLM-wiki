"""37 个世界观视频字幕合并为一个文本块"""
import os
import re
from dataclasses import dataclass


@dataclass
class VideoMeta:
    title: str
    publish_date: str  # "未知" 或 ISO 格式
    bv_id: str
    url: str


def parse_video_meta(filepath: str) -> VideoMeta:
    """从视频 md 文件中提取元数据"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取标题（第一个 # 标题）
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else os.path.basename(filepath)

    # 提取发布时间
    date_match = re.search(r"\*\*发布时间\*\*:\s*(.+)", content)
    publish_date = date_match.group(1).strip() if date_match else "未知"

    # 提取 BV 号
    bv_match = re.search(r"\*\*BV号\*\*:\s*(\S+)", content)
    bv_id = bv_match.group(1).strip() if bv_match else ""

    # 提取视频链接
    url_match = re.search(r"\*\*视频链接\*\*:\s*(\S+)", content)
    url = url_match.group(1).strip() if url_match else ""

    return VideoMeta(title=title, publish_date=publish_date, bv_id=bv_id, url=url)


def merge_videos(video_dir: str = "data/videos") -> str:
    """合并所有视频字幕为一个文本块

    格式：
    ============================================================
    视频 1: 标题 (发布时间: date)
    ============================================================
    台词内容
    """
    files = sorted([
        f for f in os.listdir(video_dir)
        if f.endswith(".md") and f != "input.md"
    ])

    parts = []
    parts.append("# 明日方舟世界观视频字幕合集\n")
    parts.append(f"共 {len(files)} 个视频\n")

    for i, filename in enumerate(files, 1):
        filepath = os.path.join(video_dir, filename)
        meta = parse_video_meta(filepath)

        # 提取台词部分（## 台词 之后的内容）
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        dialogue_match = re.search(r"##\s*台词\s*\n(.+)", content, re.DOTALL)
        dialogue = dialogue_match.group(1).strip() if dialogue_match else content

        parts.append(f"\n{'='*60}")
        parts.append(f"视频 {i}: {meta.title}")
        parts.append(f"发布时间: {meta.publish_date}")
        parts.append(f"{'='*60}\n")
        parts.append(dialogue)

    return "\n".join(parts)
