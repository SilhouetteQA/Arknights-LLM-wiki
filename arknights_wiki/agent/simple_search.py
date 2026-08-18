"""简单检索路径 — 多层检索 → 合并 → LLM 回答

Layer 0: Wiki 精确匹配
Layer 1: Events 结构化查询
Layer 2: FAISS 语义搜索
Layer 3: Dialogue 兜底
"""
import json
import os
import time as time_mod

from arknights_wiki.agent import wrap_user_input
from arknights_wiki.agent.retrieval import (
    WikiStore,
    EventStore,
    DialogueStore,
    TimelineStore,
)
from arknights_wiki.agent.prompts import QA_SYSTEM_PROMPT, _SOURCE_FIDELITY_RULES, _LOGICAL_ORGANIZATION_SYNTHESIS
from arknights_wiki.config import DATA_DIR, PROJECT_ROOT
from arknights_wiki.extraction.llm_client import _get_model_config, create_client
from arknights_wiki.observability import (
    GENERATION_ANSWER,
    SPAN_RETRIEVAL,
    SPAN_SIMPLE_SEARCH,
    compute_cost_rmb,
    get_client,
    is_enabled,
    record_llm_usage,
    traced,
)


def _get_data_dir():
    """获取数据目录路径"""
    return os.environ.get("ARKNIGHTS_DATA_DIR", DATA_DIR)


def _load_chapter_timeline_order() -> dict[str, int]:
    """加载章节时间线排序 {章节名: 序号}"""
    fp = os.path.join(PROJECT_ROOT, "config", "chapter_timeline.json")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
            chapters = data.get("chapters", [])
            return {ch: i for i, ch in enumerate(chapters)}
    return {}


def _get_character_chapters(entity: str, data_dir: str) -> list[str]:
    """从实体索引获取角色所有出场章节，按时间线排序"""
    entity_map_path = os.path.join(data_dir, "entity_source_map.json")
    if not os.path.exists(entity_map_path):
        return []
    try:
        with open(entity_map_path, "r", encoding="utf-8") as f:
            entity_map = json.load(f)
    except Exception:
        return []

    if entity not in entity_map:
        return []

    pass1_files = entity_map[entity].get("source_files", {}).get("pass1_events", [])
    chapters = [f[:-5] for f in pass1_files if f.endswith(".json")]  # 去 .json

    # 按时间线排序
    timeline = _load_chapter_timeline_order()
    return sorted(chapters, key=lambda ch: timeline.get(ch, 999))


def _sample_events_across_arc(
    entity: str,
    event_store: EventStore,
    add,
    data_dir: str,
    chapter_entities: list[str],
    question_type: str,
):
    """对角色查询，从实体索引获取所有出场章节，跨时间线均匀采样事件。

    解决 limit=3 硬编码导致的角色剧情覆盖不全：
    - 阿米娅 32 章只取 3 个事件 → 漏掉维多利亚、乌萨斯等关键时期
    - 改为从角色全出场章节中均匀选 5 个代表性章节，每章取 2-3 个事件
    """
    if question_type != "character_profile":
        return

    chapters = _get_character_chapters(entity, data_dir)
    if len(chapters) <= 3:
        # 出场章节少，全取
        for ch in chapters:
            if ch not in chapter_entities:
                for evt in event_store.search(entity=entity, chapter=ch, limit=2):
                    add(evt)
        return

    # 均匀选取 5 个代表性章节：最早 → 1/4 → 中点 → 3/4 → 最新
    n = len(chapters)
    sample_indices = [0, max(1, n // 4), n // 2, min(n - 2, 3 * n // 4), n - 1]
    sample_indices = sorted(set(sample_indices))  # 去重

    for idx in sample_indices:
        ch = chapters[idx]
        if ch not in chapter_entities:
            for evt in event_store.search(entity=entity, chapter=ch, limit=3):
                add(evt)


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
    question_type: str = "",
    data_dir: str = "",
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

        # 无章节上下文
        if not chapter_entities:
            if question_type == "character_profile":
                # 角色查询：跨章均匀采样，覆盖完整角色弧线
                _sample_events_across_arc(
                    entity, event_store, add, data_dir, chapter_entities, question_type,
                )
            else:
                # 概念/事实类查询：全局搜索但适度提高上限
                for evt in event_store.search(entity=entity, limit=6):
                    add(evt)

    # Layer 3: wiki 搜索（精确实体优先，少量条数）
    for entity in entities:
        wiki_limit = 2 if chapter_entities else 4
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


def _retrieval_metadata(args, kwargs, result: list[dict]) -> dict:
    """search_and_collect 结果的 trace metadata（来源数）"""
    return {"n_sources": len(result) if isinstance(result, list) else 0}


@traced(name=SPAN_RETRIEVAL, metadata_fn=_retrieval_metadata)
def search_and_collect(
    entities: list[str],
    question: str,
    question_type: str,
    expansion_hints: list[str] | None = None,
    chapter: str | None = None,
    max_sources: int = 20,
    progress_callback=None,
) -> list[dict]:
    """多层检索，根据意图类型调整检索策略。

    核心改进：
    1. 识别实体中的章节名，章节事件始终按 chapter 过滤
    2. expansion_hints 仅作 wiki 补充搜索，不影响事件/页面定位
    3. 角色+章节组合时，优先搜索该章内的事件
    4. progress_callback(tool, summary) 用于向前端实时推送检索进度
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
    if progress_callback:
        progress_callback("实体解析", f"正在解析 {len(entities)} 个实体...")
    chapter_entities, non_chapter_entities = _resolve_chapter_context(
        entities, event_store, add
    )
    if progress_callback:
        parts = []
        if chapter_entities:
            parts.append(f"章节: {', '.join(chapter_entities)}")
        if non_chapter_entities:
            parts.append(f"实体: {', '.join(non_chapter_entities)}")
        progress_callback("解析结果", " | ".join(parts) if parts else "未识别到章节或实体")

    # 步骤 2: 结构化检索（事件 + 页面 + wiki）
    _collect_structured_sources(
        entities=entities,
        chapter_entities=chapter_entities,
        non_chapter_entities=non_chapter_entities,
        expansion_hints=expansion_hints,
        wiki_store=wiki_store,
        event_store=event_store,
        add=add,
        question_type=question_type,
        data_dir=data_dir,
    )
    if progress_callback:
        progress_callback("结构化检索完成", f"已收集 {len(collected)} 条来源")

    # 步骤 3: 语义搜索兜底（FAISS + 对话 + 时间线）
    if progress_callback:
        progress_callback("语义搜索", "FAISS 向量检索中...")
    _collect_semantic_fallback(
        question=question,
        question_type=question_type,
        chapter_entities=chapter_entities,
        chapter=chapter,
        data_dir=data_dir,
        collected=collected,
        add=add,
    )

    if progress_callback:
        progress_callback("检索完成", f"共收集 {min(len(collected), max_sources)} 条来源，开始生成回答...")

    return collected[:max_sources]


def build_answer_prompt(question: str, sources: list[dict]) -> str:
    """构建百科风格 LLM answer prompt"""
    source_text = ""
    for i, s in enumerate(sources, 1):
        header = f"[参考{i}] [{s.get('entity_type', 'unknown')}] {s.get('name', '')}"
        source_text += f"{header}\n{s.get('text', '')[:2000]}\n\n"

    return f"""## 玩家问题
{wrap_user_input(question)}

## 参考资料
{source_text}

## 回答要求
{_SOURCE_FIDELITY_RULES}

{_LOGICAL_ORGANIZATION_SYNTHESIS}
- 禁止输出 [参考N] 这类引用标记
- 说清楚为止，不限制字数"""


def _search_metadata(args, kwargs, result: dict) -> dict:
    """simple_search 结果的 trace metadata（来源数/回答长度）"""
    if not isinstance(result, dict):
        return {}
    return {"n_sources": len(result.get("sources", [])), "answer_len": len(result.get("answer", ""))}


@traced(name=SPAN_SIMPLE_SEARCH, metadata_fn=_search_metadata)
def simple_search(question: str, route: dict, progress_callback=None) -> dict:
    """简单检索路径主函数"""
    entities = route.get("entities", [])
    expansion_hints = route.get("expansion_hints", [])
    question_type = route.get("question_type", "summary")

    sources = search_and_collect(
        entities=entities,
        question=question,
        question_type=question_type,
        expansion_hints=expansion_hints,
        progress_callback=progress_callback,
    )

    if not sources:
        return {
            "answer": "未找到与问题相关的资料。请尝试更具体地描述问题。",
            "sources": [],
        }

    if progress_callback:
        progress_callback("生成回答", "LLM 正在整理答案...")

    user_prompt = build_answer_prompt(question, sources)

    client = create_client()
    model = _get_model_config()["model"]  # 统一模型层（火山/DeepSeek，勿硬编码）

    def _do_generate():
        return client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": QA_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=8192,
        )

    # W1 Observability: 回答生成包一个 generation span（record_llm_usage 需要处于 generation 内）
    from arknights_wiki.observability import GENERATION_ANSWER, get_client

    _obs_client = get_client()
    if _obs_client is not None:
        with _obs_client.start_as_current_observation(
            name=GENERATION_ANSWER, as_type="generation", model=model
        ):
            _t0 = time_mod.time()
            response = _do_generate()
            latency_ms = round((time_mod.time() - _t0) * 1000, 1)
            answer = response.choices[0].message.content or ""
            if is_enabled():
                usage = getattr(response, "usage", None)
                tokens_in = usage.prompt_tokens if usage else 0
                tokens_out = usage.completion_tokens if usage else 0
                record_llm_usage(
                    model,
                    tokens_in,
                    tokens_out,
                    compute_cost_rmb(model, tokens_in, tokens_out),
                    extra={"latency_ms": latency_ms, "stage": "answer_generation"},
                )
    else:
        _t0 = time_mod.time()
        response = _do_generate()
        latency_ms = round((time_mod.time() - _t0) * 1000, 1)
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
