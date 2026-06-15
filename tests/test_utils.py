# tests/test_utils.py
import os
import tempfile
from arknights_wiki._utils import (
    sanitize_filename, ensure_dir, read_json, write_json,
    compute_hash, normalize_url,
)


class TestSanitizeFilename:
    def test_removes_illegal_chars(self):
        assert sanitize_filename('test:file<name>') == 'test_file_name_'

    def test_spaces_to_underscores(self):
        assert sanitize_filename('hello world') == 'hello_world'

    def test_chinese_characters_preserved(self):
        assert sanitize_filename('阿米娅') == '阿米娅'

    def test_strips_whitespace(self):
        assert sanitize_filename('  hello  ') == 'hello'


class TestEnsureDir:
    def test_creates_nested_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            new_dir = os.path.join(tmp, "a", "b", "c")
            ensure_dir(new_dir)
            assert os.path.isdir(new_dir)

    def test_existing_dir_no_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            ensure_dir(tmp)  # 不应报错


class TestJsonIO:
    def test_read_write_roundtrip(self):
        data = {"key": "值", "nested": [1, 2, 3]}
        with tempfile.TemporaryDirectory() as tmp:
            filepath = os.path.join(tmp, "test.json")
            write_json(filepath, data)
            result = read_json(filepath)
            assert result == data

    def test_write_json_creates_parent_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            filepath = os.path.join(tmp, "sub", "deep", "test.json")
            write_json(filepath, {"a": 1})
            assert os.path.exists(filepath)

    def test_write_json_chinese_not_escaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            filepath = os.path.join(tmp, "test.json")
            write_json(filepath, {"name": "阿米娅"})
            with open(filepath, 'r', encoding='utf-8') as f:
                raw = f.read()
            assert "阿米娅" in raw
            assert "\\u" not in raw


class TestComputeHash:
    def test_deterministic(self):
        h1 = compute_hash("hello")
        h2 = compute_hash("hello")
        assert h1 == h2

    def test_sha256_length(self):
        assert len(compute_hash("test")) == 64

    def test_different_inputs(self):
        assert compute_hash("a") != compute_hash("b")


class TestNormalizeUrl:
    def test_already_full_url(self):
        assert normalize_url("https://prts.wiki/w/test") == "https://prts.wiki/w/test"

    def test_protocol_relative(self):
        assert normalize_url("//prts.wiki/w/test") == "https://prts.wiki/w/test"

    def test_path_only(self):
        assert normalize_url("/w/test") == "https://prts.wiki/w/test"

    def test_bare_string(self):
        result = normalize_url("bare")
        assert result == "bare"  # 无法判断，原样返回
