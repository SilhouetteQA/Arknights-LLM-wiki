# tests/test_gen_operators_md.py
from arknights_wiki.pipeline.gen_operators_md import operator_to_markdown


class TestOperatorToMarkdown:
    def test_basic_with_archives(self):
        op = {
            "name_zh": "阿米娅",
            "race": "卡特斯/奇美拉",
            "nation": "雷姆必拓",
            "birth_place": "雷姆必拓",
            "sex": "女",
            "team": "",
            "group": "罗德岛",
            "logo": "罗德岛",
            "archives": {
                "基础档案": "【代号】阿米娅\n【性别】女",
                "客观履历": "罗德岛的公开领袖。",
                "档案资料一": "档案内容一。",
            },
        }
        md = operator_to_markdown(op)
        assert "# 阿米娅" in md
        assert "种族：卡特斯/奇美拉" in md
        assert "阵营：雷姆必拓" in md
        assert "组织：罗德岛" in md
        assert "## 基础档案" in md
        assert "【代号】阿米娅" in md
        assert "## 客观履历" in md
        assert "罗德岛的公开领袖。" in md
        assert "## 档案资料一" in md

    def test_no_archives(self):
        op = {
            "name_zh": "测试",
            "race": "未知", "nation": "", "birth_place": "",
            "sex": "", "team": "", "group": "", "logo": "",
            "archives": {},
        }
        md = operator_to_markdown(op)
        assert "# 测试" in md
        assert "无档案数据" in md

    def test_archive_order(self):
        """档案按固定顺序输出"""
        op = {
            "name_zh": "测试",
            "race": "", "nation": "", "birth_place": "", "sex": "",
            "team": "", "group": "", "logo": "",
            "archives": {
                "档案资料二": "second",
                "基础档案": "first",
                "档案资料一": "third",
            },
        }
        md = operator_to_markdown(op)
        pos_first = md.find("## 基础档案")
        pos_third = md.find("## 档案资料一")
        pos_second = md.find("## 档案资料二")
        assert pos_first < pos_third < pos_second

    def test_optional_fields_handled(self):
        """空的可选字段不产生多余输出"""
        op = {
            "name_zh": "测试",
            "race": "", "nation": "", "birth_place": "", "sex": "",
            "team": "", "group": "", "logo": "",
            "archives": {"基础档案": "hello"},
        }
        md = operator_to_markdown(op)
        # team 为空不应出现 "小队："
        assert "小队：" not in md
        # group 为空不应出现 "组织："
        assert "组织：" not in md
