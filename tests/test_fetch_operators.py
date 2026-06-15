# tests/test_fetch_operators.py
from arknights_wiki.pipeline.fetch_operators import (
    _extract_data_attrs, parse_operator_page,
)


SAMPLE_OPERATOR_HTML = """<html><body><div>
<div data-id="R001" data-zh="阿米娅" data-race="卡特斯/奇美拉"
data-nation="雷姆必拓" data-birth_place="雷姆必拓" data-team=""
data-group="罗德岛" data-sex="女" data-logo="罗德岛"
data-hp="1480" data-atk="612" data-def="120" data-name_en="Amiya"
data-name_ja="アーミヤ" data-profession="术师"></div>
<div data-id="R002" data-zh="杜宾" data-race="佩洛"
data-nation="玻利瓦尔" data-birth_place="玻利瓦尔" data-team="行动组A4"
data-group="罗德岛" data-sex="女" data-logo="罗德岛"
data-hp="1200" data-atk="450"></div>
</div></body></html>"""

# 模拟干员个人页档案 HTML（table 格式，与 PRTS Wiki 实际结构一致）
ARCHIVE_HTML = """<html><body>
<h2><span class="mw-headline" id="干员信息">干员信息</span></h2>
<p>一些内容</p>
<h2><span class="mw-headline" id="干员档案">干员档案</span></h2>
<table class="wikitable">
<tr><th>————人员档案</th></tr>
<tr><th style="background:#424242">基础档案</th></tr>
<tr><th>初始开放</th></tr>
<tr><td>【代号】测试干员<br/>【性别】女<br/>【出身地】罗德岛</td></tr>
<tr><th style="background:#424242">客观履历</th></tr>
<tr><th>初始开放</th></tr>
<tr><td>一位测试干员，背景不详。</td></tr>
<tr><th style="background:#424242">档案资料一</th></tr>
<tr><th>初始开放</th></tr>
<tr><td>这是档案内容。</td></tr>
<tr><th style="background:#424242">档案资料二</th></tr>
<tr><th>提升信赖至50%以查看更多信息</th></tr>
<tr><td></td></tr>
</table>
<h2><span class="mw-headline" id="语音记录">语音记录</span></h2>
<p>语音内容</p>
</body></html>"""


class TestExtractDataAttrs:
    def test_extracts_only_char_fields(self):
        ops = _extract_data_attrs(SAMPLE_OPERATOR_HTML)
        assert len(ops) == 2

        amiya = ops[0]
        assert amiya["id"] == "R001"
        assert amiya["name_zh"] == "阿米娅"
        assert amiya["race"] == "卡特斯/奇美拉"
        assert amiya["nation"] == "雷姆必拓"
        assert amiya["logo"] == "罗德岛"

    def test_excludes_gameplay_stats(self):
        ops = _extract_data_attrs(SAMPLE_OPERATOR_HTML)
        for op in ops:
            assert "hp" not in op
            assert "atk" not in op
            assert "def" not in op

    def test_excludes_extra_names(self):
        ops = _extract_data_attrs(SAMPLE_OPERATOR_HTML)
        for op in ops:
            assert "name_en" not in op
            assert "name_ja" not in op

    def test_empty_input(self):
        assert _extract_data_attrs("") == []

    def test_no_operator_divs(self):
        assert _extract_data_attrs("<div>no data-id here</div>") == []


class TestParseOperatorPage:
    def test_extracts_archives(self):
        archives = parse_operator_page(ARCHIVE_HTML)
        assert "基础档案" in archives
        assert "测试干员" in archives["基础档案"]

    def test_extracts_objective_resume(self):
        archives = parse_operator_page(ARCHIVE_HTML)
        assert "客观履历" in archives
        assert "背景不详" in archives["客观履历"]

    def test_extracts_archive_files(self):
        archives = parse_operator_page(ARCHIVE_HTML)
        assert "档案资料一" in archives
        assert "这是档案内容" in archives["档案资料一"]

    def test_stops_at_next_h2(self):
        archives = parse_operator_page(ARCHIVE_HTML)
        assert "语音记录" not in archives

    def test_empty_html(self):
        assert parse_operator_page("") == {}
        assert parse_operator_page("<div></div>") == {}
