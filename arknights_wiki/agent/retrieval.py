"""数据访问层 — Wiki/Event/Dialogue/Timeline 的统一检索接口"""
import json
import os
import re
from pathlib import Path
from typing import TypedDict

from arknights_wiki.config import DATA_DIR


class SearchResult(TypedDict, total=False):
    """所有 Store.search() 返回 dict 的统一字段约定。

    必含字段: entity_type, name, text, file_path
    可选字段: match_type, event, chapter, speaker, node_id, year, content
    """
    entity_type: str
    name: str
    text: str
    file_path: str


class _BaseStore:
    """Store 基类——统一 data_dir 初始化模式，减少子类样板代码。"""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = data_dir or DATA_DIR


class WikiStore(_BaseStore):
    """Wiki 页面存储（Pass 2 角色 + Pass 3 概念/阵营/地点）

    按实体名精确匹配，支持子串搜索内容。
    """

    def __init__(self, data_dir: str | None = None):
        super().__init__(data_dir)
        self._name_cache: dict[str, list[str]] = {}

    def _get_dir(self, entity_type: str) -> str:
        base = os.path.join(self.data_dir, "extractions")
        if entity_type == "character":
            return os.path.join(base, "v2_characters")
        return os.path.join(base, "v3_wiki", entity_type + "s")

    def list_names(self, entity_type: str) -> list[str]:
        if entity_type not in self._name_cache:
            d = self._get_dir(entity_type)
            if not os.path.isdir(d):
                return []
            names = []
            ext = ".json" if entity_type == "character" else ".md"
            for f in os.listdir(d):
                if f.endswith(ext):
                    names.append(os.path.splitext(f)[0])
            self._name_cache[entity_type] = sorted(names)
        return self._name_cache[entity_type]

    def search(self, query: str, category: str | None = None, limit: int = 10) -> list[dict]:
        """全文搜索 wiki 页面

        策略:
          1. 文件名精确匹配
          2. 文件名包含 query
          3. 内容子串匹配
        """
        categories = [category] if category else ["concept", "faction", "location", "character"]
        results = []

        for cat in categories:
            names = self.list_names(cat)
            ext = ".json" if cat == "character" else ".md"
            d = self._get_dir(cat)

            for name in names:
                match_type = None
                if name == query:
                    match_type = "exact"
                elif query in name:
                    match_type = "name_contains"
                else:
                    fp = os.path.join(d, name + ext)
                    try:
                        content = Path(fp).read_text(encoding="utf-8")
                    except Exception:
                        continue
                    if query in content:
                        match_type = "content_match"

                if match_type:
                    fp = os.path.join(d, name + ext)
                    try:
                        text = Path(fp).read_text(encoding="utf-8")
                    except Exception:
                        text = ""
                    results.append({
                        "entity_type": cat,
                        "name": name,
                        "text": text[:2000],
                        "file_path": fp,
                        "match_type": match_type,
                    })

        order = {"exact": 0, "name_contains": 1, "content_match": 2}
        results.sort(key=lambda r: order.get(r["match_type"], 3))
        return results[:limit]

    def get_page(self, name: str, entity_type: str) -> dict | None:
        d = self._get_dir(entity_type)
        ext = ".json" if entity_type == "character" else ".md"
        fp = os.path.join(d, name + ext)
        if not os.path.exists(fp):
            return None
        try:
            text = Path(fp).read_text(encoding="utf-8")
        except Exception:
            return None
        return {
            "entity_type": entity_type,
            "name": name,
            "text": text,
            "file_path": fp,
        }


class EventStore(_BaseStore):
    """Pass 1 事件存储 -- 首次访问时全量加载到内存缓存"""

    def __init__(self, data_dir: str | None = None):
        super().__init__(data_dir)
        self._events_dir = os.path.join(self.data_dir, "extractions", "v1_events")
        self._cache: list[tuple] | None = None
        self._chapter_data: dict[str, dict] = {}

    def _ensure_loaded(self):
        """惰性加载: 首次调用时遍历全部 JSON 文件并缓存"""
        if self._cache is not None:
            return
        self._cache = []
        for root, dirs, files in os.walk(self._events_dir):
            for f in files:
                if not f.endswith(".json"):
                    continue
                fp = os.path.join(root, f)
                try:
                    data = json.loads(Path(fp).read_text(encoding="utf-8"))
                except Exception:
                    continue
                chapter = os.path.splitext(f)[0]
                self._chapter_data[chapter] = data
                for evt in data.get("events", []):
                    self._cache.append((chapter, evt, fp))

    def search(
        self, entity: str | None = None, event_type: str | None = None,
        chapter: str | None = None, limit: int = 20,
    ) -> list[dict]:
        self._ensure_loaded()
        results = []
        for ch, evt, fp in self._cache:
            if chapter and ch != chapter:
                continue
            if event_type and evt.get("type") != event_type:
                continue
            if entity:
                participants = evt.get("participants", [])
                if entity not in participants and entity not in evt.get("event", ""):
                    continue

            parts = [f"事件 [{ch}]: {evt.get('event', '')}"]
            if evt.get("type"):
                parts.append(f"类型: {evt['type']}")
            participants = evt.get("participants", [])
            if participants:
                parts.append(f"参与者: {', '.join(participants)}")
            if evt.get("location"):
                parts.append(f"地点: {evt['location']}")

            results.append({
                "entity_type": "event",
                "name": f"{ch} ({evt.get('type', '')})",
                "text": "。".join(parts),
                "file_path": fp,
                "event": evt,
                "chapter": ch,
            })
            if len(results) >= limit:
                return results
        return results

    def get_chapter_summary(self, chapter: str) -> dict | None:
        self._ensure_loaded()
        data = self._chapter_data.get(chapter)
        if data is None:
            return None
        summary = data.get("summary", "")
        if not summary:
            return None
        return {"entity_type": "chapter_summary", "name": chapter, "text": summary}


class DialogueStore(_BaseStore):
    """原始对话全文搜索 -- 首次访问时全量加载到内存缓存"""

    def __init__(self, data_dir: str | None = None):
        super().__init__(data_dir)
        self._stories_dir = os.path.join(self.data_dir, "stories")
        self._cache: list[tuple] | None = None

    def _ensure_loaded(self):
        """惰性加载: 首次调用时遍历全部对话 JSON 并缓存 (fp, data, chapter, node_id, lines)"""
        if self._cache is not None:
            return
        self._cache = []
        for root, dirs, files in os.walk(self._stories_dir):
            for f in files:
                if not f.endswith(".json"):
                    continue
                fp = os.path.join(root, f)
                try:
                    data = json.loads(Path(fp).read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                ch = data.get("chapter", "")
                node_id = data.get("id", "")
                lines = data.get("lines", [])
                self._cache.append((fp, data, ch, node_id, lines))

    def search(self, query: str, chapter: str | None = None, limit: int = 20) -> list[dict]:
        self._ensure_loaded()
        results = []
        for fp, data, ch, node_id, lines in self._cache:
            if chapter and chapter not in ch:
                continue
            for i, line in enumerate(lines):
                text = line.get("text", "")
                if query not in text:
                    continue
                speaker = line.get("speaker", "旁白" if line.get("type") == "narration" else "???")
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                context_lines = []
                for j in range(start, end):
                    l = lines[j]
                    s = l.get("speaker", "旁白" if l.get("type") == "narration" else "???")
                    context_lines.append(f"[{s}] {l.get('text', '')}")
                context = "\n".join(context_lines)

                results.append({
                    "entity_type": "dialogue",
                    "name": f"{ch} / {node_id}",
                    "text": context,
                    "file_path": fp,
                    "speaker": speaker,
                    "chapter": ch,
                    "node_id": node_id,
                })
                if len(results) >= limit:
                    return results
        return results


class TimelineStore(_BaseStore):
    """时间线搜索"""

    def __init__(self, data_dir: str | None = None):
        super().__init__(data_dir)
        self._timeline_path = os.path.join(self.data_dir, "extractions", "v3_wiki", "timeline.md")

    def search(self, query: str, limit: int = 20) -> list[dict]:
        if not os.path.exists(self._timeline_path):
            return []
        text = Path(self._timeline_path).read_text(encoding="utf-8")
        entries = re.split(r"\n## (\d+)", text)
        results = []
        for i in range(1, len(entries), 2):
            year = entries[i].strip()
            content = entries[i + 1].strip() if i + 1 < len(entries) else ""
            if query in content:
                bold_match = re.search(r"\*\*(.+?)\*\*", content)
                desc = bold_match.group(1) if bold_match else content[:200]
                results.append({
                    "entity_type": "timeline",
                    "name": year,
                    "text": f"时间线事件 [{year}]: {desc}",
                    "file_path": self._timeline_path,
                    "year": year,
                    "content": content,
                })
            if len(results) >= limit:
                break
        return results


class EntityIndexStore(_BaseStore):
    """实体双向索引 -- 加载 entity_source_map.json 提供 O(1) 查找"""

    def __init__(self, data_dir: str | None = None):
        super().__init__(data_dir)
        self._index_path = os.path.join(self.data_dir, "entity_source_map.json")
        self._index: dict | None = None

    def _load(self) -> dict:
        if self._index is None:
            if os.path.exists(self._index_path):
                self._index = json.loads(Path(self._index_path).read_text(encoding="utf-8"))
            else:
                self._index = {}
        return self._index

    def lookup(self, name: str) -> dict | None:
        """查找实体索引条目"""
        return self._load().get(name)

    def search_related(self, name: str) -> list[str]:
        """获取实体的所有关联实体名"""
        entry = self.lookup(name)
        if not entry:
            return []
        related = []
        for field in ["related_entities", "related_factions", "related_locations", "related_characters"]:
            related.extend(entry.get(field, []))
        return related

    def get_source_chapters(self, name: str) -> list[str]:
        """获取实体出现的章节列表（从 pass1_events 提取章节名）"""
        entry = self.lookup(name)
        if not entry:
            return []
        pass1 = entry.get("source_files", {}).get("pass1_events", [])
        return [f.replace(".json", "") for f in pass1]

    def get_type(self, name: str) -> str | None:
        """获取实体类型"""
        entry = self.lookup(name)
        return entry["type"] if entry else None
