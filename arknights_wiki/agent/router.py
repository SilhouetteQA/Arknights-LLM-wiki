"""查询路由器 -- 本地规则判定问题复杂度 + 实体提取"""
import json
import os
import re

from arknights_wiki.config import DATA_DIR
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

    return list(set(entities))


def _infer_question_type(question: str) -> str:
    """从关键词推断问题类型"""
    if any(kw in question for kw in [
        '整体讲了', '讲了什么', '讲了怎样', '整体故事',
        '整体脉络', '大框架', '梳理', '概括', '概述',
        '剧情发展', '剧情梗概', '故事梗概', '主要情节',
        '总结', '讲了一个', '讲了', '脉络',
    ]):
        return 'summary'
    if any(kw in question for kw in [
        '什么是', '是什么', '概念', '设定', '世界观',
        '是怎样的组织', '是怎样的国家', '有什么特点',
        '理念', '宗旨', '格局', '政治', '社会结构',
        '有几个', '有多少',
    ]):
        return 'worldview'
    if any(kw in question for kw in [
        '对比', '比较', '区别', '异同', '孰强孰弱',
        '排名', '排序', '最强',
    ]):
        return 'comparison'
    if any(kw in question for kw in [
        '做了什么', '关系如何', '是什么关系', '有什么互动',
        '性格', '战力', '实力',
    ]):
        return 'character'
    return 'event'


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


def classify_complexity_local(
    question: str, entities: list[str], question_type: str, time_scope: str
) -> dict:
    """纯规则判断问题复杂度"""
    if question_type == "comparison":
        return {
            "complexity": "complex",
            "question_type": question_type,
            "entities": entities,
            "time_scope": time_scope,
            "reason": "对比问题需要多源检索比对",
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

    clean_entities = [e for e in entities if not e.startswith("__")]
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


def _llm_rewrite_query(question: str) -> list[str]:
    """轻量 LLM: 从问题中提取检索关键词（entities=[] 时兜底）"""
    try:
        from arknights_wiki.extraction.llm_client import create_client
        from arknights_wiki.agent.prompts import ROUTER_SYSTEM_PROMPT

        client = create_client()
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        text = response.choices[0].message.content or ""
        text = text.strip().strip("`").removeprefix("json")
        entities = json.loads(text)
        if isinstance(entities, list):
            return [e for e in entities if isinstance(e, str) and len(e) >= 1]
    except Exception:
        pass
    return []


def route_query(question: str, history=None) -> dict:
    """查询路由主函数"""
    entities = _extract_entities_local(question)
    question_type = _infer_question_type(question)

    source = "local"
    clean_entities = [e for e in entities if not e.startswith("__")]
    if len(clean_entities) == 0:
        llm_entities = _llm_rewrite_query(question)
        if llm_entities:
            entities = list(set(entities + llm_entities))
            source = "local+llm"

    time_scope = _infer_time_scope(question, entities)
    result = classify_complexity_local(question, entities, question_type, time_scope)
    result["source"] = source
    return result
