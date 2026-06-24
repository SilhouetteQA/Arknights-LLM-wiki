"""FAISS 向量索引构建 + 语义搜索

参照 mrfz 的索引构建模式:
- 所有 wiki/event/character 内容统一编码为 FAISS 向量
- chunk_id 命名约定: {entity_type}:{name} (如 concept:源石)
- chunk_map.json: 键 "entity_type:name" → {file_path, text, chunk_id}
- 搜索通过 chunk_map 追溯到精确实体
"""
import json
import os
import re
from pathlib import Path

import numpy as np

from arknights_wiki.config import DATA_DIR


_embed_model = None


def _load_embedding_model():
    """惰性加载 BGE-small-zh-v1.5（同 mrfz 配置，模块级缓存）

    在 Windows + torch 2.12 环境下，sentence-transformers 导入可能触发
    pyarrow 的 C 层段错误（不可被 try/except 捕获）。
    设置环境变量 ARKNIGHTS_SKIP_EMBED_MODEL=1 可跳过加载，
    build_faiss_index / semantic_search 将回退到随机向量。
    """
    global _embed_model
    if _embed_model is not None:
        return _embed_model

    # 在导入前检查跳过标志，避免 C 层段错误
    if os.environ.get("ARKNIGHTS_SKIP_EMBED_MODEL"):
        raise RuntimeError(
            "模型加载已被 ARKNIGHTS_SKIP_EMBED_MODEL 环境变量跳过。"
        )

    from sentence_transformers import SentenceTransformer
    model_name = os.environ.get("ARKNIGHTS_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
    model = SentenceTransformer(model_name, device="cpu")
    model.max_seq_length = 512
    try:
        model.half()
    except Exception:
        pass
    _embed_model = model
    return model


def _get_model():
    """获取嵌入模型（带异常处理）"""
    global _embed_model
    if _embed_model is not None:
        return _embed_model
    try:
        return _load_embedding_model()
    except Exception as e:
        raise RuntimeError(
            f"无法加载嵌入模型: {e}. "
            f"请确认已安装 sentence-transformers 且 BGE-small-zh-v1.5 模型可用。"
        )


def _list_markdown_files(directory: str) -> list[Path]:
    """递归列出目录下所有 .md 文件"""
    p = Path(directory)
    if not p.exists():
        return []
    return sorted(p.rglob("*.md"))


def build_chunk_map(data_dir: str | None = None) -> dict:
    """遍历所有数据源，构建 chunk_map

    chunk_map key: (entity_type, name)
    chunk_map value: {file_path, text, chunk_id}

    数据源:
      - v3_wiki/concepts/*.md    → entity_type="concept"
      - v3_wiki/factions/*.md    → entity_type="faction"
      - v3_wiki/locations/*.md   → entity_type="location"
      - v2_characters/*.json     → entity_type="character"
      - v1_events/**/*.json      → entity_type="event" (每个事件) + "chapter_summary" (每章摘要)
      - v3_wiki/timeline.md      → entity_type="timeline" (每个 year 条目)
    """
    if data_dir is None:
        data_dir = DATA_DIR

    base = Path(data_dir)
    chunk_map = {}

    # ── Pass 3 Concepts ──
    concepts_dir = base / "extractions" / "v3_wiki" / "concepts"
    for fp in _list_markdown_files(str(concepts_dir)):
        name = fp.stem
        text = fp.read_text(encoding="utf-8")
        chunk_map[("concept", name)] = {
            "file_path": str(fp),
            "text": text,
            "chunk_id": f"concept:{name}",
        }

    # ── Pass 3 Factions ──
    factions_dir = base / "extractions" / "v3_wiki" / "factions"
    for fp in _list_markdown_files(str(factions_dir)):
        name = fp.stem
        text = fp.read_text(encoding="utf-8")
        chunk_map[("faction", name)] = {
            "file_path": str(fp),
            "text": text,
            "chunk_id": f"faction:{name}",
        }

    # ── Pass 3 Locations ──
    locations_dir = base / "extractions" / "v3_wiki" / "locations"
    for fp in _list_markdown_files(str(locations_dir)):
        name = fp.stem
        text = fp.read_text(encoding="utf-8")
        chunk_map[("location", name)] = {
            "file_path": str(fp),
            "text": text,
            "chunk_id": f"location:{name}",
        }

    # ── Pass 2 Characters ──
    characters_dir = base / "extractions" / "v2_characters"
    if characters_dir.exists():
        for fp in sorted(characters_dir.glob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                name = data.get("display_name") or data.get("name", fp.stem)
                parts = [f"角色: {name}"]
                if data.get("summary"):
                    parts.append(f"概述: {data['summary']}")
                if data.get("personality"):
                    parts.append(f"性格: {data['personality']}")
                if data.get("power_level"):
                    parts.append(f"战力: {data['power_level']}")
                text = "。".join(parts)
                chunk_map[("character", name)] = {
                    "file_path": str(fp),
                    "text": text,
                    "chunk_id": f"character:{name}",
                }
            except (json.JSONDecodeError, KeyError):
                continue

    # ── Pass 1 Events ──
    events_dir = base / "extractions" / "v1_events"
    if events_dir.exists():
        for fp in sorted(events_dir.rglob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                # 章节摘要
                summary = data.get("summary", "")
                if summary:
                    chunk_map[("chapter_summary", fp.stem)] = {
                        "file_path": str(fp),
                        "text": f"章节摘要 [{fp.stem}]: {summary}",
                        "chunk_id": f"chapter_summary:{fp.stem}",
                    }
                # 每个事件
                for i, evt in enumerate(data.get("events", [])):
                    event_text = evt.get("event", "")
                    evt_type = evt.get("type", "")
                    participants = ", ".join(evt.get("participants", []))
                    location = evt.get("location", "")
                    parts = [f"事件 [{fp.stem}]: {event_text}"]
                    if evt_type:
                        parts.append(f"类型: {evt_type}")
                    if participants:
                        parts.append(f"参与者: {participants}")
                    if location:
                        parts.append(f"地点: {location}")
                    text = "。".join(parts)
                    chunk_map[("event", f"{fp.stem}_{i}")] = {
                        "file_path": str(fp),
                        "text": text,
                        "chunk_id": f"event:{fp.stem}_{i}",
                        "event_index": i,
                    }
            except (json.JSONDecodeError, KeyError):
                continue

    # ── Timeline ──
    timeline_path = base / "extractions" / "v3_wiki" / "timeline.md"
    if timeline_path.exists():
        text = timeline_path.read_text(encoding="utf-8")
        entries = re.split(r"\n## (\d+)", text)
        for i in range(1, len(entries), 2):
            year = entries[i].strip()
            content = entries[i + 1].strip() if i + 1 < len(entries) else ""
            bold_match = re.search(r"\*\*(.+?)\*\*", content)
            desc = bold_match.group(1) if bold_match else content[:100]
            chunk_map[("timeline", year)] = {
                "file_path": str(timeline_path),
                "text": f"时间线事件 [{year}]: {desc}",
                "chunk_id": f"timeline:{year}",
            }

    return chunk_map


def build_faiss_index(texts: list[str], dimension: int = 384, model=None) -> "faiss.IndexFlatIP":
    """编码文本列表并构建 FAISS IndexFlatIP

    如果 model 为 None 且环境允许，自动加载 BGE-small-zh-v1.5。
    如果加载失败（如 Windows torch 兼容问题），回退到随机向量（仅用于测试）。
    """
    import faiss

    try:
        if model is None:
            model = _get_model()
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=128,
            show_progress_bar=False,
        )
    except Exception:
        # 回退: 随机向量（测试环境）
        embeddings = np.random.randn(len(texts), dimension).astype(np.float32)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / norms

    index = faiss.IndexFlatIP(dimension)
    index.add(np.array(embeddings, dtype=np.float32))
    return index


def build_index_from_data(data_dir: str | None = None, index_dir: str | None = None) -> tuple[str, str]:
    """从数据目录构建完整 FAISS 索引，写出文件"""
    if data_dir is None:
        data_dir = DATA_DIR
    if index_dir is None:
        index_dir = os.path.join(data_dir, "index")

    os.makedirs(index_dir, exist_ok=True)

    chunk_map = build_chunk_map(data_dir)
    texts = [v["text"] for v in chunk_map.values()]
    index = build_faiss_index(texts)

    import faiss

    index_path = os.path.join(index_dir, "faiss.index")
    faiss.write_index(index, index_path)

    # chunk_map: key 为 tuple，序列化为可 JSON 的格式
    serializable_map = {}
    for (entity_type, name), info in chunk_map.items():
        key = f"{entity_type}:{name}"
        serializable_map[key] = info

    map_path = os.path.join(index_dir, "chunk_map.json")
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(serializable_map, f, ensure_ascii=False, indent=2)

    return index_path, map_path


def load_index(index_path: str, map_path: str) -> tuple:
    """加载 FAISS 索引和 chunk_map"""
    import faiss

    index = faiss.read_index(index_path)
    with open(map_path, "r", encoding="utf-8") as f:
        chunk_map = json.load(f)
    return index, chunk_map


def semantic_search(
    query: str,
    index,
    chunk_map: dict,
    model=None,
    top_k: int = 20,
) -> list[dict]:
    """FAISS 语义搜索，返回结构化结果列表

    每个结果包含 chunk_id, entity_type, name, score, text, file_path
    """
    try:
        if model is None:
            model = _get_model()
        query_vec = model.encode([query], normalize_embeddings=True)
    except Exception:
        # 回退: 随机向量
        import faiss
        dim = index.d
        query_vec = np.random.randn(1, dim).astype(np.float32)
        query_vec = query_vec / np.linalg.norm(query_vec)

    scores, indices = index.search(np.array(query_vec, dtype=np.float32), top_k)

    results = []
    chunk_map_items = list(chunk_map.items())

    for i, idx in enumerate(indices[0]):
        if idx < 0 or idx >= len(chunk_map_items):
            continue
        key_str, info = chunk_map_items[idx]
        # chunk_map 的键可能是 tuple (entity_type, name) 或 string "entity_type:name"
        if isinstance(key_str, tuple):
            entity_type = key_str[0] if len(key_str) > 0 else "unknown"
            name = key_str[1] if len(key_str) > 1 else str(key_str)
        else:
            parts = key_str.split(":", 1)
            entity_type = parts[0] if len(parts) > 0 else "unknown"
            name = parts[1] if len(parts) > 1 else key_str

        results.append({
            "chunk_id": info.get("chunk_id", key_str),
            "entity_type": entity_type,
            "name": name,
            "score": float(scores[0][i]),
            "text": info.get("text", "")[:500],
            "file_path": info.get("file_path", ""),
        })

    return results
