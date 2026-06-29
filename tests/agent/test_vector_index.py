"""FAISS 向量索引测试"""
import json
import os

import numpy as np
import pytest

from arknights_wiki.agent.vector_index import (
    build_chunk_map,
    build_faiss_index,
    build_index_from_data,
    load_index,
    semantic_search,
)


class TestChunkMap:
    def test_build_chunk_map_from_concepts(self, temp_data_dir):
        """chunk_map 正确映射概念页面"""
        chunk_map = build_chunk_map(temp_data_dir)

        assert ("concept", "源石") in chunk_map
        entry = chunk_map[("concept", "源石")]
        assert "源石.md" in entry["file_path"]
        assert "泰拉世界一种蕴含巨大能量的矿物" in entry["text"]


class TestFAISSIndex:
    def test_build_and_search(self, temp_data_dir, monkeypatch):
        """FAISS 索引构建 + 搜索端到端（mock 嵌入模型避免加载真实模型）"""
        chunk_map = build_chunk_map(temp_data_dir)
        texts = [v["text"] for v in chunk_map.values()]

        dim = 384
        # mock _encode_texts 返回 L2 归一化的随机向量
        def _mock_encode(t, batch_size=128):
            vecs = np.random.randn(len(t), dim).astype(np.float32)
            return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        monkeypatch.setattr(
            "arknights_wiki.agent.vector_index._encode_texts", _mock_encode
        )
        index = build_faiss_index(texts, dimension=dim)

        # 索引大小等于文本数
        assert index.ntotal == len(texts)

        # 模拟语义搜索
        query_vec = np.random.random(dim).astype(np.float32)
        query_vec = query_vec / np.linalg.norm(query_vec)
        scores, indices = index.search(query_vec.reshape(1, -1), 3)
        assert len(indices[0]) <= 3


def test_build_index_from_data_saves_files(temp_data_dir, monkeypatch):
    """build_index_from_data 写出 FAISS 文件 + chunk_map JSON"""
    index_dir = os.path.join(temp_data_dir, "index")
    os.makedirs(index_dir, exist_ok=True)

    def _mock_encode(t, batch_size=128):
        vecs = np.random.randn(len(t), 384).astype(np.float32)
        return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    monkeypatch.setattr(
        "arknights_wiki.agent.vector_index._encode_texts", _mock_encode
    )

    index_path, map_path = build_index_from_data(temp_data_dir, index_dir)

    assert os.path.exists(index_path)
    assert os.path.exists(map_path)

    # 验证 load
    index, chunk_map = load_index(index_path, map_path)
    assert index.ntotal > 0
    assert len(chunk_map) > 0


def test_semantic_search_returns_structured_results(temp_data_dir, monkeypatch):
    """semantic_search 返回结构化结果，含 entity_type 和 name"""
    chunk_map = build_chunk_map(temp_data_dir)
    texts = [v["text"] for v in chunk_map.values()]

    dim = 384
    def _mock_encode(t, batch_size=128):
        vecs = np.random.randn(len(t), dim).astype(np.float32)
        return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    monkeypatch.setattr(
        "arknights_wiki.agent.vector_index._encode_texts", _mock_encode
    )

    index = build_faiss_index(texts, dimension=dim)

    results = semantic_search("矿石病是什么", index, chunk_map, top_k=2)

    for r in results:
        assert "chunk_id" in r
        assert "entity_type" in r
        assert "name" in r
        assert "score" in r
        assert "text" in r
        assert r["entity_type"] in ("concept", "faction", "location", "character", "event", "chapter_summary", "timeline")
