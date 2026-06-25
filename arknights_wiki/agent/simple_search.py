"""简单检索路径 — 多层检索 → 合并 → LLM 回答

Layer 0: Wiki 精确匹配
Layer 1: Events 结构化查询
Layer 2: FAISS 语义搜索
Layer 3: Dialogue 兜底
"""
import os

from arknights_wiki.agent.retrieval import (
    WikiStore,
    EventStore,
    DialogueStore,
    TimelineStore,
)
from arknights_wiki.agent.prompts import QA_SYSTEM_PROMPT
from arknights_wiki.config import DATA_DIR
from arknights_wiki.extraction.llm_client import create_client


def _get_data_dir():
    return os.environ.get("ARKNIGHTS_DATA_DIR", DATA_DIR)


def search_and_collect(
    entities: list[str],
    question: str,
    question_type: str,
    chapter: str | None = None,
    max_sources: int = 20,
) -> list[dict]:
    """多层检索，根据意图类型调整检索策略"""
    data_dir = _get_data_dir()
    collected = []
    seen = set()

    def add(doc: dict):
        key = f"{doc.get('entity_type', '')}:{doc.get('name', '')}"
        if key not in seen:
            seen.add(key)
            collected.append(doc)

    wiki_store = WikiStore(data_dir=data_dir)
    event_store = EventStore(data_dir=data_dir)

    # 概念定义/角色资料/事实查询：精确 get_page 优先
    if question_type in ("concept_definition", "character_profile", "fact_lookup"):
        for entity in entities:
            for etype in ["concept", "faction", "location", "character"]:
                page = wiki_store.get_page(entity, etype)
                if page:
                    add(page)
                    break

    # 常规 wiki 搜索
    for entity in entities:
        for result in wiki_store.search(entity, limit=3):
            add(result)

    # 章节总结：精确 get_chapter_summary + 该章 events
    if question_type == "chapter_summary":
        for entity in entities:
            summary = event_store.get_chapter_summary(entity)
            if summary:
                add(summary)
            for evt in event_store.search(chapter=entity, limit=10):
                add(evt)

    # 常规事件搜索
    if question_type != "chapter_summary":
        for entity in entities:
            for evt in event_store.search(entity=entity, limit=5):
                add(evt)

    # FAISS 语义搜索 (提高阈值减少噪声)
    index_dir = os.path.join(data_dir, "index")
    index_path = os.path.join(index_dir, "faiss.index")
    map_path = os.path.join(index_dir, "chunk_map.json")
    if os.path.exists(index_path) and os.path.exists(map_path):
        from arknights_wiki.agent.vector_index import load_index, semantic_search
        try:
            index, chunk_map = load_index(index_path, map_path)
            faiss_results = semantic_search(question, index, chunk_map, top_k=5)
            for r in faiss_results:
                if r["score"] > 0.4:
                    add({
                        "entity_type": r["entity_type"],
                        "name": r["name"],
                        "text": r["text"],
                        "file_path": r.get("file_path", ""),
                    })
        except Exception:
            pass

    # Dialogue 兜底
    if len(collected) < 5:
        dialogue_store = DialogueStore(data_dir=data_dir)
        for result in dialogue_store.search(question[:50], chapter=chapter, limit=5):
            add(result)

    # Timeline
    if question_type in ("causal_reasoning", "comparison") or any(
        kw in question for kw in ["时间线", "先后", "年表", "历史"]
    ):
        timeline_store = TimelineStore(data_dir=data_dir)
        for result in timeline_store.search(question[:30], limit=5):
            add(result)

    return collected[:max_sources]


def build_answer_prompt(question: str, sources: list[dict]) -> str:
    """构建 CASUAL 风格 LLM answer prompt"""
    source_text = ""
    for i, s in enumerate(sources, 1):
        header = f"[参考{i}] [{s.get('entity_type', 'unknown')}] {s.get('name', '')}"
        source_text += f"{header}\n{s.get('text', '')[:800]}\n\n"

    return f"""## 玩家问题
{question}

## 参考资料
{source_text}

## 回答要求
- 用口语化、朋友聊天的语气回答
- 先给一句核心答案，再展开细节
- 将资料融合成连贯叙述，不要逐条罗列事件
- 禁止输出 [参考N] 这类引用标记
- 用你自己的话重组信息
- 忽略与问题无关的资料
- 说清楚为止，不限制字数"""


def simple_search(question: str, route: dict) -> dict:
    """简单检索路径主函数"""
    entities = route.get("entities", [])
    question_type = route.get("question_type", "summary")

    sources = search_and_collect(
        entities=entities,
        question=question,
        question_type=question_type,
    )

    if not sources:
        return {
            "answer": "未找到与问题相关的资料。请尝试更具体地描述问题。",
            "sources": [],
        }

    user_prompt = build_answer_prompt(question, sources)

    client = create_client()
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=8192,
    )
    answer = response.choices[0].message.content or ""

    source_meta = []
    for i, s in enumerate(sources, 1):
        source_meta.append({
            "ref": i,
            "entity_type": s.get("entity_type", ""),
            "name": s.get("name", ""),
            "file_path": s.get("file_path", ""),
        })

    return {"answer": answer, "sources": source_meta}
