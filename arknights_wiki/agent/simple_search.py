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
from arknights_wiki.agent.prompts import QA_SYSTEM_PROMPT, _SOURCE_FIDELITY_RULES, _LOGICAL_ORGANIZATION_SYNTHESIS
from arknights_wiki.config import DATA_DIR
from arknights_wiki.extraction.llm_client import create_client


def _get_data_dir():
    """获取数据目录路径"""
    return os.environ.get("ARKNIGHTS_DATA_DIR", DATA_DIR)


def _resolve_chapter_context(
    entities: list[str],
    event_store: EventStore,
    add,
) -> tuple[list[str], list[str]]:
    """分离章节实体和非章节实体，同时添加章节摘要。

    能通过 event_store 查到 chapter_summary 的实体即为章节名。
    返回 (chapter_entities, non_chapter_entities)。
    """
    chapter_entities = []
    non_chapter_entities = []
    for entity in entities:
        summary = event_store.get_chapter_summary(entity)
        if summary:
            chapter_entities.append(entity)
            add(summary)
        else:
            non_chapter_entities.append(entity)
    return chapter_entities, non_chapter_entities


def _collect_structured_sources(
    entities: list[str],
    chapter_entities: list[str],
    non_chapter_entities: list[str],
    expansion_hints: list[str],
    wiki_store: WikiStore,
    event_store: EventStore,
    add,
):
    """Layer 1-4: 结构化检索——章节事件、实体页面、wiki 搜索、扩展提示词。

    Layer 1: 章节事件（始终优先，按章节过滤）
    Layer 2: 非章节实体的精确页面 + 章节内/全局事件
    Layer 3: wiki 精确搜索
    Layer 4: expansion_hints wiki 补充搜索
    """
    # Layer 1: 章节事件（始终优先，按章节过滤）
    for ch in chapter_entities:
        for evt in event_store.search(chapter=ch, limit=10):
            add(evt)

    # Layer 2: 非章节实体的精确页面 + 章节内事件
    for entity in non_chapter_entities:
        for etype in ["concept", "faction", "location", "character"]:
            page = wiki_store.get_page(entity, etype)
            if page:
                add(page)
                break

        # 如有章节上下文，优先搜索该章内与实体相关的事件
        for ch in chapter_entities:
            for evt in event_store.search(entity=entity, chapter=ch, limit=5):
                add(evt)

        # 无章节上下文时才做全局事件搜索（且限制条数，留空间给章节事件）
        if not chapter_entities:
            for evt in event_store.search(entity=entity, limit=3):
                add(evt)

    # Layer 3: wiki 搜索（精确实体优先，少量条数）
    for entity in entities:
        wiki_limit = 2 if chapter_entities else 3
        for result in wiki_store.search(entity, limit=wiki_limit):
            add(result)

    # Layer 4: expansion_hints 仅用于 wiki 补充搜索，不影响事件定位
    for hint in expansion_hints:
        for result in wiki_store.search(hint, limit=1):
            add(result)


def _collect_semantic_fallback(
    question: str,
    question_type: str,
    chapter_entities: list[str],
    chapter: str | None,
    data_dir: str,
    collected: list[dict],
    add,
):
    """Layer 5-7: 语义搜索兜底——FAISS、对话、时间线。

    Layer 5: FAISS 语义搜索
    Layer 6: Dialogue 兜底（结果不足时）
    Layer 7: Timeline（因果/历史类问题）
    """
    # Layer 5: FAISS 语义搜索
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

    # Layer 6: Dialogue 兜底
    if len(collected) < 5:
        dialogue_store = DialogueStore(data_dir=data_dir)
        for ch in chapter_entities:
            for result in dialogue_store.search(question[:50], chapter=ch, limit=3):
                add(result)
        for result in dialogue_store.search(question[:50], chapter=chapter, limit=3):
            add(result)

    # Layer 7: Timeline
    if question_type in ("causal_reasoning", "comparison") or any(
        kw in question for kw in ["时间线", "先后", "年表", "历史"]
    ):
        timeline_store = TimelineStore(data_dir=data_dir)
        for result in timeline_store.search(question[:30], limit=5):
            add(result)


def search_and_collect(
    entities: list[str],
    question: str,
    question_type: str,
    expansion_hints: list[str] | None = None,
    chapter: str | None = None,
    max_sources: int = 20,
) -> list[dict]:
    """多层检索，根据意图类型调整检索策略。

    核心改进：
    1. 识别实体中的章节名，章节事件始终按 chapter 过滤
    2. expansion_hints 仅作 wiki 补充搜索，不影响事件/页面定位
    3. 角色+章节组合时，优先搜索该章内的事件
    """
    data_dir = _get_data_dir()
    collected = []
    seen = set()
    if expansion_hints is None:
        expansion_hints = []

    def add(doc: dict):
        key = f"{doc.get('entity_type', '')}:{doc.get('name', '')}"
        if key not in seen:
            seen.add(key)
            collected.append(doc)

    wiki_store = WikiStore(data_dir=data_dir)
    event_store = EventStore(data_dir=data_dir)

    # 步骤 1: 分离章节/非章节实体
    chapter_entities, non_chapter_entities = _resolve_chapter_context(
        entities, event_store, add
    )

    # 步骤 2: 结构化检索（事件 + 页面 + wiki）
    _collect_structured_sources(
        entities=entities,
        chapter_entities=chapter_entities,
        non_chapter_entities=non_chapter_entities,
        expansion_hints=expansion_hints,
        wiki_store=wiki_store,
        event_store=event_store,
        add=add,
    )

    # 步骤 3: 语义搜索兜底（FAISS + 对话 + 时间线）
    _collect_semantic_fallback(
        question=question,
        question_type=question_type,
        chapter_entities=chapter_entities,
        chapter=chapter,
        data_dir=data_dir,
        collected=collected,
        add=add,
    )

    return collected[:max_sources]


def build_answer_prompt(question: str, sources: list[dict]) -> str:
    """构建 CASUAL 风格 LLM answer prompt"""
    source_text = ""
    for i, s in enumerate(sources, 1):
        header = f"[参考{i}] [{s.get('entity_type', 'unknown')}] {s.get('name', '')}"
        source_text += f"{header}\n{s.get('text', '')[:2000]}\n\n"

    return f"""## 玩家问题
{question}

## 参考资料
{source_text}

## 回答要求
{_SOURCE_FIDELITY_RULES}

{_LOGICAL_ORGANIZATION_SYNTHESIS}
- 禁止输出 [参考N] 这类引用标记
- 说清楚为止，不限制字数"""


def simple_search(question: str, route: dict) -> dict:
    """简单检索路径主函数"""
    entities = route.get("entities", [])
    expansion_hints = route.get("expansion_hints", [])
    question_type = route.get("question_type", "summary")

    sources = search_and_collect(
        entities=entities,
        question=question,
        question_type=question_type,
        expansion_hints=expansion_hints,
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
