"""37 个世界观视频字幕合并测试"""
import os
from arknights_wiki.extraction.video_merger import merge_videos, parse_video_meta, VideoMeta


class TestVideoMerger:
    def test_merge_returns_string(self):
        """合并返回非空字符串"""
        result = merge_videos("data/videos")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_merge_includes_video_titles(self):
        """合并结果包含视频标题"""
        result = merge_videos("data/videos")
        # 至少包含几个已知视频内容
        assert "圣灵" in result or "拉特兰" in result or "源石技艺" in result

    def test_merge_includes_publish_dates(self):
        """合并结果包含发布时间"""
        result = merge_videos("data/videos")
        assert "发布时间" in result

    def test_parse_video_meta(self):
        """解析单个视频文件的元数据"""
        files = sorted(os.listdir("data/videos"))
        md_files = [f for f in files if f.endswith(".md") and f != "input.md"]
        if md_files:
            meta = parse_video_meta(os.path.join("data/videos", md_files[0]))
            assert isinstance(meta, VideoMeta)
            assert meta.title
            assert meta.publish_date is not None

    def test_merge_result_has_structure(self):
        """合并结果有清晰的节结构"""
        result = merge_videos("data/videos")
        assert "===" in result

    def test_merge_correct_video_count(self):
        """合并的视频数量正确（排除了 input.md）"""
        result = merge_videos("data/videos")
        # 共 36 个视频（37 个 .md 减去 input.md）
        assert "共 36 个视频" in result

    def test_input_md_is_excluded(self):
        """input.md 被排除在合并之外"""
        result = merge_videos("data/videos")
        assert "input.md" not in result
