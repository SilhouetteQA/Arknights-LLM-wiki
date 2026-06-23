import os
from arknights_wiki.extraction.book_splitter import split_book, ChapterSegment


class TestBookSplitter:
    def test_split_returns_chapter_segments(self):
        """切分返回 ChapterSegment 列表，至少 9 段 (3+4+1+1)"""
        segments = split_book("data/lorebook/terra_a_journey_full.md")
        assert len(segments) >= 9
        for seg in segments:
            assert isinstance(seg, ChapterSegment)
            assert seg.title
            assert len(seg.text) > 0

    def test_chapter_titles_match_expected(self):
        """章节标题覆盖六章 + 泰拉纪年"""
        segments = split_book("data/lorebook/terra_a_journey_full.md")
        titles = [s.title for s in segments]
        assert any("源石" in t for t in titles)
        assert any("科技" in t for t in titles)
        assert any("生物" in t for t in titles)
        assert any("种族" in t for t in titles)
        assert any("国家" in t for t in titles)
        assert any("组织" in t for t in titles)
        assert any("泰拉纪年" in t for t in titles)

    def test_each_chapter_starts_with_page_marker(self):
        """每章以 ## 第 X 页 开头"""
        segments = split_book("data/lorebook/terra_a_journey_full.md")
        for seg in segments:
            assert seg.text.strip().startswith("## 第"), \
                f"章节 '{seg.title}' 不以页面标记开头: {seg.text[:50]}..."

    def test_no_overlap_between_chapters(self):
        """相邻章节无内容重叠"""
        segments = split_book("data/lorebook/terra_a_journey_full.md")
        for i in range(len(segments) - 1):
            # 第二章的开头不应在第一章的内容中
            assert segments[i+1].text[:200] not in segments[i].text
