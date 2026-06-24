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
    """执行多层检索，合并收集的文档"""
    data_dir = _get_data_dir()
    collected = []
    seen = set()

    def add(doc: dict):
        key = f"{doc.get('entity_type', '')}:{doc.get('name', '')}"
        if key not in seen:
            seen.add(key)
            collected.append(doc)

    # Layer 0: Wiki 精确匹配
    wiki_store = WikiStore(data_dir=data_dir)
    for entity in entities:
        for etype in ["concept", "faction", "location", "character"]:
            page = wiki_store.get_page(entity, etype)
            if page:
                add(page)
                break
        for result in wiki_store.search(entity, limit=3):
            add(result)

    # Layer 1: Events 结构化查询
    event_store = EventStore(data_dir=data_dir)
    if chapter:
        summary = event_store.get_chapter_summary(chapter)
        if summary:
            add(summary)
    for entity in entities:
        for evt in event_store.search(entity=entity, limit=5):
            add(evt)

    # Layer 2: FAISS 语义搜索
    index_dir = os.path.join(data_dir, "index")
    index_path = os.path.join(index_dir, "faiss.index")
    map_path = os.path.join(index_dir, "chunk_map.json")
    if os.path.exists(index_path) and os.path.exists(map_path):
        from arknights_wiki.agent.vector_index import load_index, semantic_search
        try:
            index, chunk_map = load_index(index_path, map_path)
            faiss_results = semantic_search(question, index, chunk_map, top_k=10)
            for r in faiss_results:
                if r["score"] > 0.3:
                    add({
                        "entity_type": r["entity_type"],
                        "name": r["name"],
                        "text": r["text"],
                        "file_path": r.get("file_path", ""),
                    })
        except Exception:
            pass

    # Layer 3: Dialogue 兜底（仅在结果少时触发）
    if len(collected) < 5:
        dialogue_store = DialogueStore(data_dir=data_dir)
        for result in dialogue_store.search(question[:50], chapter=chapter, limit=5):
            add(result)

    # Timeline（时间/因果类问题）
    if question_type in ("event", "comparison") or any(
        kw in question for kw in ["时间线", "先后", "年表", "历史"]
    ):
        timeline_store = TimelineStore(data_dir=data_dir)
        for result in timeline_store.search(question[:30], limit=5):
            add(result)

    return collected[:max_sources]


def build_answer_prompt(question: str, sources: list[dict]) -> str:
    """构建 LLM answer prompt"""
    source_text = ""
    for i, s in enumerate(sources, 1):
        header = f"[{i}] [{s.get('entity_type', 'unknown')}] {s.get('name', '')}"
        source_text += f"{header}\n{s.get('text', '')[:1000]}\n\n"

    return f"""## 用户问题
{question}

## 参考资料
{source_text}

请基于以上参考资料，以连贯的叙述方式回答用户问题。将零散的对话片段组织成有逻辑的、易读的叙事文本，按照时间顺序展开，自然地在文中标注引用来源 [1][2]。"""


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
