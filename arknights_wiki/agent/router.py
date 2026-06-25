"""查询路由器 -- 合并意图识别 + 问题改写 + 复杂度分类"""
import json
import os
import re

from arknights_wiki.config import DATA_DIR, PROJECT_ROOT
from arknights_wiki.agent.retrieval import WikiStore


def _load_identity_map(data_dir: str | None = None) -> dict:
    """加载身份映射表（别名 -> 规范名）"""
    base = data_dir if data_dir is not None else DATA_DIR
    fp = os.path.join(base, "config", "identity_map.json")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _load_operators(data_dir: str | None = None) -> dict:
    """加载干员列表"""
    base = data_dir if data_dir is not None else DATA_DIR
    fp = os.path.join(base, "operators.json")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _extract_entities_local(question: str, data_dir: str | None = None) -> list[str]:
    """从问题文本中提取实体名（纯本地，不调 LLM）"""
    entities = []
    if data_dir is None:
        data_dir = DATA_DIR

    # 1. identity_map
    identity = _load_identity_map(data_dir)
    for alias, canonical in identity.items():
        if alias in question:
            if canonical.startswith("character:"):
                entities.append(canonical.split(":", 1)[1])
            else:
                entities.append(canonical)
        if canonical in question and canonical not in entities:
            entities.append(canonical)

    # 2. operators
    operators = _load_operators(data_dir)
    for op_name in operators:
        if op_name in question and op_name not in entities:
            entities.append(op_name)

    # 3. Wiki 页面名
    for entity_type in ["concept", "faction", "location", "character"]:
        try:
            store = WikiStore(data_dir=data_dir)
            for name in store.list_names(entity_type):
                if len(name) >= 2 and name in question and name not in entities:
                    entities.append(name)
        except Exception:
            pass

    # 4. 章节/活动名正则
    chapter_match = re.search(r'(序章|第[0-9零一二三四五六七八九十]+章)', question)
    if chapter_match:
        entities.append(chapter_match.group(1))

    # 5. 「...」活动名
    event_match = re.findall(r'「([^」]+)」', question)
    entities.extend(event_match)

    # 6. 联动活动系列别名映射
    collab_series = _load_collab_series()
    for series_name, series_info in collab_series.items():
        for alias in series_info.get("aliases", []):
            if alias in question:
                entities.extend(series_info.get("chapters", []))

    return list(set(entities))


def _infer_intent_local(question: str) -> str:
    """本地关键词推断意图（7类），无法匹配返回 'unknown'"""
    if any(kw in question for kw in [
        '什么是', '是什么', '是怎样的', '什么叫', '啥是',
    ]):
        return 'concept_definition'
    if any(kw in question for kw in [
        '整体讲了', '讲了什么', '讲了怎样', '整体故事',
        '整体脉络', '大框架', '梳理', '概括', '概述',
        '剧情发展', '剧情梗概', '故事梗概', '主要情节',
        '总结', '讲了一个', '发生了什么', '剧情',
    ]):
        return 'chapter_summary'
    if any(kw in question for kw in [
        '是谁', '性格', '战力', '实力', '背景',
        '是什么样的人', '是什么角色', '能力',
    ]):
        return 'character_profile'
    if any(kw in question for kw in [
        '对比', '比较', '区别', '异同', '孰强孰弱',
        '排名', '排序', '最强', '谁更强', '哪个更',
    ]):
        return 'comparison'
    if any(kw in question for kw in [
        '为什么', '原因', '导致', '结果', '引起',
        '演变', '发展历程', '怎么变成', '如何形成',
        '变迁', '演化',
    ]):
        return 'causal_reasoning'
    if any(kw in question for kw in [
        '有哪些', '有几个', '多少个', '所有', '列举',
        '列出', '成员', '包括什么', '都有谁',
    ]):
        return 'list_enumeration'
    if any(kw in question for kw in [
        '出生地', '属于哪个', '什么时候', '在哪里',
        '多少岁', '年龄', '种族', '身高',
    ]):
        return 'fact_lookup'
    return 'unknown'


def _infer_time_scope(question: str, entities: list[str]) -> str:
    """推断时间范围"""
    cross_signals = [
        '演变', '演化', '历程', '整个过程', '整体', '各个',
        '所有', '全部', '大框架', '脉络', '梳理',
    ]
    if any(kw in question for kw in cross_signals):
        return 'cross_arc'
    if re.search(r'(序章|第[0-9零一二三四五六七八九十]+章)', question):
        return 'chapter'
    return 'cross_arc'


def _load_chapter_timeline() -> dict:
    """加载章节发布时间线 {章节名: 序号, ...}"""
    fp = os.path.join(PROJECT_ROOT, "config", "chapter_timeline.json")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
            chapters = data.get("chapters", [])
            return {ch: i for i, ch in enumerate(chapters)}
    return {}


def _load_collab_series() -> dict:
    """加载联动活动系列映射 {别名: series_info, ...}"""
    fp = os.path.join(PROJECT_ROOT, "config", "collab_series.json")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("series", {})
    return {}


def _resolve_temporal_entities(question: str, entities: list[str]) -> tuple[list[str], str]:
    """时序消歧：处理'最新''最近'等时间词，替换联动系列的实体"""
    temporal_newest = any(kw in question for kw in ['最新', '最近', '最后的', '最后一次'])
    temporal_first = any(kw in question for kw in ['第一', '首个', '最初', '最早的', '第一次'])

    if not (temporal_newest or temporal_first):
        return entities, ""

    collab_series = _load_collab_series()
    if not collab_series:
        return entities, ""

    timeline = _load_chapter_timeline()
    resolved = list(entities)
    notes = []

    for series_name, series_info in collab_series.items():
        series_chapters = series_info.get("chapters", [])
        if len(series_chapters) < 2:
            continue

        # 按发布时间排序章节
        ordered = sorted(series_chapters, key=lambda ch: timeline.get(ch, 999))
        target = ordered[-1] if temporal_newest else ordered[0]

        for i, entity in enumerate(resolved):
            if entity in series_chapters and entity != target:
                resolved[i] = target
                if temporal_newest:
                    notes.append(f"'{entity}'为较早的{series_info['label']}，'最新'应指'{target}'")
                else:
                    notes.append(f"'{entity}'为较晚的{series_info['label']}，'首个'应指'{target}'")

    return resolved, "; ".join(notes) if notes else ""


def recognize_intent_and_rewrite(question: str, use_llm: bool = True) -> dict:
    """合并意图识别和问题改写：本地规则先行，LLM 兜底"""
    intent = _infer_intent_local(question)
    entities = _extract_entities_local(question)
    clean_entities = [e for e in entities if not e.startswith("__")]

    if intent != "unknown" and len(clean_entities) > 0:
        return {
            "intent": intent,
            "rewritten_question": question,
            "canonical_entities": clean_entities,
            "expansion_hints": [],
            "disambiguation_note": "",
            "source": "local",
        }

    if use_llm:
        try:
            from arknights_wiki.extraction.llm_client import create_client
            from arknights_wiki.agent.prompts import INTENT_REWRITE_PROMPT

            client = create_client()
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": INTENT_REWRITE_PROMPT},
                    {"role": "user", "content": question},
                ],
                temperature=0.1,
                max_tokens=400,
            )
            text = response.choices[0].message.content or ""
            text = text.strip().strip("`").removeprefix("json")
            result = json.loads(text)
            return {
                "intent": result.get("intent", "unknown"),
                "rewritten_question": result.get("rewritten_question", question),
                "canonical_entities": result.get("canonical_entities", clean_entities),
                "expansion_hints": result.get("expansion_hints", []),
                "disambiguation_note": result.get("disambiguation_note", ""),
                "source": "llm",
            }
        except Exception:
            pass

    return {
        "intent": intent if intent != "unknown" else "fact_lookup",
        "rewritten_question": question,
        "canonical_entities": clean_entities,
        "expansion_hints": [],
        "disambiguation_note": "",
        "source": "local",
    }


def classify_complexity_local(
    question: str, entities: list[str], question_type: str, time_scope: str
) -> dict:
    """纯规则判断问题复杂度"""
    clean_entities = [e for e in entities if not e.startswith("__")]

    complex_intents = {"comparison", "concept_definition", "list_enumeration", "causal_reasoning"}
    if question_type in complex_intents:
        reasons = {
            "comparison": "对比问题需要多源检索比对",
            "concept_definition": "世界观概念需要跨章检索",
            "list_enumeration": "列表枚举需要宽搜多源",
            "causal_reasoning": "因果推理需要多步检索",
        }
        return {
            "complexity": "complex",
            "question_type": question_type,
            "entities": entities,
            "time_scope": time_scope,
            "reason": reasons.get(question_type, "需要多步检索"),
        }

    if len(clean_entities) > 1:
        return {
            "complexity": "complex",
            "question_type": question_type,
            "entities": entities,
            "time_scope": time_scope,
            "reason": "多实体需要分别检索后综合",
        }

    deep_keywords = [
        '导致', '原因', '后果', '为什么',
        '对比', '比较', '区别', '异同', '排名', '排序',
        '演变', '变迁', '发展历程', '历程', '变革',
        '时间线', '编年史', '大事记', '梳理',
        '势力格局', '势力分布',
    ]
    has_deep = any(kw in question for kw in deep_keywords)

    if has_deep and time_scope == "cross_arc":
        return {
            "complexity": "complex",
            "question_type": question_type,
            "entities": entities,
            "time_scope": time_scope,
            "reason": "跨章节深度推理问题, 需要多步检索",
        }

    if time_scope == "cross_arc" and len(clean_entities) == 0:
        return {
            "complexity": "complex",
            "question_type": question_type,
            "entities": entities,
            "time_scope": time_scope,
            "reason": "跨章节但实体不足, Agent 多步检索补充",
        }

    return {
        "complexity": "simple",
        "question_type": question_type,
        "entities": entities,
        "time_scope": time_scope,
        "reason": "简单事实查询",
    }


def route_query(question: str, history=None) -> dict:
    """查询路由主函数：意图识别+改写 → 时序消歧 → 复杂度分类"""
    intent_result = recognize_intent_and_rewrite(question)

    entities = intent_result["canonical_entities"] + intent_result["expansion_hints"]

    # 时序消歧：处理"最新""最近"等时间词
    resolved_entities, temporal_note = _resolve_temporal_entities(question, entities)

    entities = list(set(resolved_entities))
    question_type = intent_result["intent"]

    time_scope = _infer_time_scope(question, entities)
    result = classify_complexity_local(question, entities, question_type, time_scope)

    result["rewritten_question"] = intent_result["rewritten_question"]
    result["expansion_hints"] = intent_result["expansion_hints"]
    # 合并消歧备注
    disambig = intent_result.get("disambiguation_note", "")
    if temporal_note:
        disambig = f"{disambig}; {temporal_note}" if disambig else temporal_note
    result["disambiguation_note"] = disambig
    result["source"] = intent_result.get("source", "local")
    return result
