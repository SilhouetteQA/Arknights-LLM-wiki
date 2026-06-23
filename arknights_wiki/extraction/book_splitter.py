"""大地巡旅 OCR 全文按章节切分"""
import re
from dataclasses import dataclass


@dataclass
class ChapterSegment:
    title: str
    text: str
    start_page: int
    end_page: int


# 章节边界定义: (OCR 页号, "章节标题")
# 页号对应 OCR 文件中的 "## 第 N 页" 编号
_CHAPTER_BOUNDARIES = [
    (1,   "目录与前言"),
    (3,   "第一章：源石，天灾，矿石病"),
    (33,  "第二章：泰拉科技"),
    (59,  "第三章：泰拉生物"),
    (79,  "第四章：泰拉种族"),
    (107, "第五章：国家与地区"),
    (347, "第六章：组织"),
    (389, "附录：组织名录"),
]


def _find_page_offset(lines: list[str], page_num: int) -> int:
    """在行列表中找到指定页号的行索引"""
    marker = f"## 第 {page_num} 页"
    for i, line in enumerate(lines):
        if line.strip() == marker:
            return i
    # 如果精确页号不存在（如被审查拦截的页），找最近的下一个存在的页
    for offset in range(1, 10):
        marker = f"## 第 {page_num + offset} 页"
        for i, line in enumerate(lines):
            if line.strip() == marker:
                return i
    return -1


def split_book(filepath: str) -> list[ChapterSegment]:
    """将大地巡旅全文按 6 个章节 + 附录切分

    返回 ChapterSegment 列表。目录段跳过，附录合并入第六章。
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")

    # 找各章起始行
    chapter_starts = []
    for page_num, title in _CHAPTER_BOUNDARIES:
        offset = _find_page_offset(lines, page_num)
        if offset >= 0:
            chapter_starts.append((offset, page_num, title))

    # 切分
    segments = []
    for i, (start_offset, page, title) in enumerate(chapter_starts):
        if i + 1 < len(chapter_starts):
            end_offset = chapter_starts[i + 1][0]
        else:
            end_offset = len(lines)

        text = "\n".join(lines[start_offset:end_offset]).strip()
        seg = ChapterSegment(
            title=title,
            text=text,
            start_page=page,
            end_page=chapter_starts[i+1][1] if i+1 < len(chapter_starts) else 999,
        )
        segments.append(seg)

    # 跳过目录，合并附录到 Ch6
    result = []
    for seg in segments:
        if "目录" in seg.title:
            continue
        if "附录" in seg.title:
            if result:
                result[-1].text += "\n\n" + seg.text
                result[-1].end_page = seg.end_page
            continue
        result.append(seg)

    return result
