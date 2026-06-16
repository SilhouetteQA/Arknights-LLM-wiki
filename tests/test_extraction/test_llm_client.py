# tests/test_extraction/test_llm_client.py
"""llm_client 模块测试 — strip_think_tags + parse_llm_response"""
from arknights_wiki.extraction.llm_client import parse_llm_response, strip_think_tags


def test_strip_think_tags_basic():
    text = "<think>这是思考内容</think>\n{\"key\": \"value\"}"
    result = strip_think_tags(text)
    assert "<think>" not in result
    assert "这是思考内容" not in result
    assert '{"key": "value"}' in result


def test_strip_think_tags_no_think():
    text = '{"key": "value"}'
    result = strip_think_tags(text)
    assert result == text


def test_strip_think_tags_multiline_think():
    text = "<think>\n多行\n思考\n</think>\n{\"key\": \"value\"}"
    result = strip_think_tags(text)
    assert "<think>" not in result
    assert '{"key": "value"}' in result


def test_parse_llm_response_valid_json():
    result = parse_llm_response('{"chapter": "测试章", "events": []}')
    assert result["chapter"] == "测试章"
    assert result["events"] == []


def test_parse_llm_response_with_think():
    raw = "<think>思考...</think>\n{\"chapter\": \"测试章\", \"events\": []}"
    result = parse_llm_response(raw)
    assert result["chapter"] == "测试章"


def test_parse_llm_response_markdown_wrapped():
    raw = '```json\n{"chapter": "测试章", "events": []}\n```'
    result = parse_llm_response(raw)
    assert result["chapter"] == "测试章"


def test_parse_llm_response_malformed_returns_none():
    result = parse_llm_response("不是 JSON")
    assert result is None
