"""查询路由器 -- 合并意图识别 + 问题改写 + 复杂度分类

配置 vs 数据加载约定:
  - 配置文件 (identity_map, chapter_timeline, collab_series) → PROJECT_ROOT/config/
  - 数据文件 (operators, characters, events, wiki pages)   → DATA_DIR/
"""
import json
import os
import re
from functools import lru_cache

from arknights_wiki.config import DATA_DIR, PROJECT_ROOT
from arknights_wiki.agent.prompts import VALID_INTENTS

# 2 字实体名前边界检查：前一字符为 CJK/字母数字则拒绝（'多利' 不匹配 '维多利亚'）
_CJK_OR_ALNUM = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf0-9A-Za-z]")


def _load_identity_map(data_dir: str | None = None) -> dict:
    """加载身份映射表（别名 -> 规范名）

    identity_map.json 结构: {_description, _source, _updated, mappings: {alias: canonical, ...}}
    """
    base = data_dir if data_dir is not None else PROJECT_ROOT
    fp = os.path.join(base, "config", "identity_map.json")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("mappings", {})
    return {}


def _load_operators(data_dir: str | None = None) -> dict:
    """加载干员名称列表 {name_zh: True}

    operators.json 结构: {fetched_at, source_list_url, total, operators: [{name_zh, ...}, ...]}
    """
    base = data_dir if data_dir is not None else DATA_DIR
    fp = os.path.join(base, "operators.json")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
            op_list = data.get("operators", [])
            return {op["name_zh"]: True for op in op_list if isinstance(op, dict) and op.get("name_zh")}
    return {}


@lru_cache(maxsize=8)
def _load_character_names(data_dir: str | None = None) -> frozenset[str]:
    """从 v2_characters 文件名提取所有角色名（干员+NPC，~642 个）"""
    base = data_dir if data_dir is not None else DATA_DIR
    char_dir = os.path.join(base, "extractions", "v2_characters")
    names = set()
    if os.path.exists(char_dir):
        for fname in os.listdir(char_dir):
            if fname.endswith(".json"):
                name = fname[:-5]  # 去掉 .json
                if len(name) >= 2:
                    names.add(name)
    return frozenset(names)


@lru_cache(maxsize=8)
def _load_worldbuilding_names(data_dir: str | None = None) -> dict[str, str]:
    """加载世界观实体名（v3_wiki factions/locations/concepts 文件名 → 类别）"""
    base = data_dir if data_dir is not None else DATA_DIR
    wb_dir = os.path.join(base, "extractions", "v3_wiki")
    names = {}
    for cat in ("factions", "locations", "concepts"):
        d = os.path.join(wb_dir, cat)
        if os.path.isdir(d):
            for fname in os.listdir(d):
                if fname.endswith(".md"):
                    name = fname[:-3]
                    if len(name) >= 2:
                        names[name] = cat
    return names


def _match_entities_ordered(
    question: str,
    names: list[str],
    min_len: int = 2,
    two_char_boundary: bool = True,
    used: list[tuple[int, int]] | None = None,
) -> list[str]:
    """统一实体匹配：长度降序 + 区间占用 + （可选）2 字前边界

    W0 路由修复（实体噪声治理，源自 benchmark 100 题诊断）:
    - 长度降序: 长名优先，'源石外燃机' 先于 '源石' 匹配
    - 区间占用: 已匹配文本不可被子串重复匹配，'维多利亚' 占用后 '多利' 失效；
      used 可跨调用共享（角色层与世界观层共用同一区间表）
    - 2 字前边界（仅角色层）: '多利' 不匹配 '维多利亚'、'领袖' 不匹配 '的领袖'
      世界观层不做边界——'使用源石' 中 '源石' 前是动词，概念名常作宾语
    """
    matched = []
    used = used if used is not None else []
    for name in sorted(set(names), key=len, reverse=True):
        if len(name) < min_len:
            continue
        pos = 0
        while True:
            pos = question.find(name, pos)
            if pos == -1:
                break
            if any(s <= pos < e for s, e in used):
                pos += 1
                continue
            if (
                two_char_boundary
                and len(name) == 2
                and pos > 0
                and _CJK_OR_ALNUM.match(question[pos - 1])
            ):
                pos += 1
                continue
            matched.append(name)
            used.append((pos, pos + len(name)))
            break
    return matched


def _extract_entities_local(question: str, data_dir: str | None = None) -> list[str]:
    """从问题文本中提取实体名（纯本地，不调 LLM）

    四层精确提取: identity_map → operators → character_names → chapter_timeline
    不再扫描 WikiStore 做子串匹配（5213 实体噪声太大）。
    """
    entities = []
    if data_dir is None:
        data_dir = DATA_DIR

    # 1. identity_map 别名→规范名（min 2 chars 防单字误匹配）
    identity = _load_identity_map(data_dir)
    for alias, canonical in identity.items():
        if len(alias) >= 2 and alias in question:
            if canonical.startswith("character:"):
                entities.append(canonical.split(":", 1)[1])
            else:
                entities.append(canonical)
        if len(canonical) >= 2 and canonical in question and canonical not in entities:
            entities.append(canonical)

    # 2. operators 干员名（min 2 chars）
    operators = _load_operators(data_dir)
    for op_name in operators:
        if len(op_name) >= 2 and op_name in question and op_name not in entities:
            entities.append(op_name)

    # 3. v2_characters 角色名 + v3_wiki 世界观实体（统一匹配: 长度降序+区间占用）
    #    角色层（干员+NPC ~642，2 字边界）与世界观层（factions/locations/concepts ~1750，无边界）
    #    共享同一占用区间表：'维多利亚'(世界观层) 占用后 '多利'(角色层) 失效。
    #    长名优先保证 '源石外燃机' 而非 '源石'。
    used_ranges: list[tuple[int, int]] = []
    wb_names = _load_worldbuilding_names(data_dir)
    for name in _match_entities_ordered(
        question, list(wb_names), two_char_boundary=False, used=used_ranges
    ):
        if name not in entities:
            entities.append(name)
    char_names = _load_character_names(data_dir)
    for name in _match_entities_ordered(
        question, list(char_names), two_char_boundary=True, used=used_ranges
    ):
        if name not in entities:
            entities.append(name)

    # 4. 章节/活动名（从 chapter_timeline.json，min 3 chars 防短名噪声）
    timeline = _load_chapter_timeline()
    for ch_name in timeline:
        if len(ch_name) >= 3 and ch_name in question and ch_name not in entities:
            entities.append(ch_name)

    # 5. 「...」书名号活动名
    event_match = re.findall(r'「([^」]+)」', question)
    for m in event_match:
        if m not in entities:
            entities.append(m)

    # 6. 联动活动系列别名→目标章节
    collab_series = _load_collab_series()
    for series_name, series_info in collab_series.items():
        for alias in series_info.get("aliases", []):
            if alias in question:
                for ch in series_info.get("chapters", []):
                    if ch not in entities:
                        entities.append(ch)

    return list(set(entities))


def _infer_intent_local(question: str) -> str:
    """本地关键词推断意图（7类），无法匹配返回 'unknown'
    优先级: chapter_summary > character_profile > concept_definition
    因为 '讲了什么' 包含 '什么'，'是什么样的人' 包含 '是什么'，需先精确匹配
    """
    if any(kw in question for kw in [
        '整体讲了', '讲了什么', '讲了怎样', '整体故事',
        '整体脉络', '大框架', '梳理', '概括', '概述',
        '剧情发展', '剧情梗概', '故事梗概', '主要情节',
        '总结', '讲了一个', '发生了什么', '讲了', '剧情', '故事',
        '肉鸽', '集成战略', '结局是什么', '结局',
    ]):
        return 'chapter_summary'
    if any(kw in question for kw in [
        '是谁', '是什么样的人', '是什么角色', '性格',
        '战力', '实力', '背景', '能力',
    ]):
        return 'character_profile'
    if any(kw in question for kw in [
        '什么是', '是什么', '是怎样的', '什么叫', '啥是',
    ]):
        return 'concept_definition'
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


def _llm_intent_rewrite(question: str) -> dict | None:
    """LLM 兜底意图识别+问题改写，失败返回 None。

    同时过滤 LLM 返回的章节名幻觉：
    如果 LLM 返回了不在问题原文中的章节名（如 "界园肉鸽" → "探索者的银凇止境"），
    降级为 expansion_hints 而非 canonical_entities。
    """
    try:
        from arknights_wiki.extraction.llm_client import create_client
        from arknights_wiki.agent.prompts import INTENT_REWRITE_PROMPT
        from arknights_wiki.agent import wrap_user_input

        client = create_client()
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": INTENT_REWRITE_PROMPT},
                {"role": "user", "content": wrap_user_input(question)},
            ],
            temperature=0.1,
            max_tokens=400,
        )
        text = response.choices[0].message.content or ""
        text = text.strip().strip("`").removeprefix("json")
        result = json.loads(text)
    except Exception:
        return None

    llm_entities = result.get("canonical_entities", [])
    timeline = _load_chapter_timeline()
    verified_entities = []
    extra_hints = list(result.get("expansion_hints", []))
    for ent in llm_entities:
        if ent in timeline and ent not in question:
            extra_hints.append(ent)
        else:
            verified_entities.append(ent)

    return {
        "intent": result.get("intent", "unknown"),
        "rewritten_question": result.get("rewritten_question", question),
        "canonical_entities": verified_entities,
        "expansion_hints": extra_hints,
        "disambiguation_note": result.get("disambiguation_note", ""),
        "source": "llm",
    }


def _make_intent_result(
    intent: str,
    question: str,
    entities: list[str],
    expansion_hints: list[str] | None = None,
    disambiguation_note: str = "",
    source: str = "local",
) -> dict:
    """构建意图识别结果的统一工厂函数"""
    return {
        "intent": intent,
        "rewritten_question": question,
        "canonical_entities": entities,
        "expansion_hints": expansion_hints or [],
        "disambiguation_note": disambiguation_note,
        "source": source,
    }


def recognize_intent_and_rewrite(question: str, use_llm: bool = True) -> dict:
    """合并意图识别和问题改写：本地规则先行，LLM 兜底"""
    intent = _infer_intent_local(question)
    entities = _extract_entities_local(question)
    clean_entities = [e for e in entities if not e.startswith("__")]

    # 本地规则命中：意图明确且提取到实体，完全使用本地结果
    if intent != "unknown" and len(clean_entities) > 0:
        return _make_intent_result(intent, question, clean_entities)

    # LLM 兜底（意图未知 或 意图已知但实体为空时，让 LLM 补充实体）
    if use_llm:
        llm_result = _llm_intent_rewrite(question)
        if llm_result is not None:
            # 校验 LLM 返回的 intent 在有效范围内，防止幻觉出无效意图
            if llm_result.get("intent") not in VALID_INTENTS:
                # 本地意图已知时保留本地意图；否则退为 fact_lookup
                llm_result["intent"] = intent if intent != "unknown" else "fact_lookup"
            return llm_result

    # 最终兜底
    fallback_intent = intent if intent != "unknown" else "fact_lookup"
    return _make_intent_result(fallback_intent, question, clean_entities)


def _make_complexity_result(
    complexity: str,
    question_type: str,
    entities: list[str],
    time_scope: str,
    reason: str,
) -> dict:
    """构建复杂度分类结果的统一工厂函数"""
    return {
        "complexity": complexity,
        "question_type": question_type,
        "entities": entities,
        "time_scope": time_scope,
        "reason": reason,
    }


def classify_complexity_local(
    question: str, entities: list[str], question_type: str, time_scope: str
) -> dict:
    """纯规则判断问题复杂度

    三条路径依次判断:
    1. 意图类型本身就是多源检索型 (comparison/list_enumeration/causal_reasoning)
    2. 多实体需要综合 (>3 个实体)
    3. 深度关键词 + 跨章节范围 (cross_arc)
    否则为 simple。
    """
    _result = lambda c, r: _make_complexity_result(c, question_type, entities, time_scope, r)
    clean_entities = [e for e in entities if not e.startswith("__")]

    # 路径 1: 意图类型本身需要多源检索
    complex_intents = {"comparison", "list_enumeration", "causal_reasoning"}
    intent_reasons = {
        "comparison": "对比问题需要多源检索比对",
        "list_enumeration": "列表枚举需要宽搜多源",
        "causal_reasoning": "因果推理需要多步检索",
    }
    if question_type in complex_intents:
        return _result("complex", intent_reasons.get(question_type, "需要多步检索"))

    # 路径 2: 多实体 (>3 个) 需要分别检索后综合
    if len(clean_entities) > 3:
        return _result("complex", "多实体需要分别检索后综合")

    # 路径 2.5: 多主体分别/对比/关系综合（≥2 实体 + 结构信号）
    # W0 路由修复: character_complex 类题多被 chapter_summary/character_profile 抢占意图,
    # 但"双实体 + 分别/各自/对比"结构本身就需要多源检索后综合。
    multi_subject_keywords = [
        '分别', '各自', '两者', '二者', '两人', '两位', '双方',
        '对比', '比较', '异同', '区别', '差异',
        '关系', '关联', '以及',  # 'X与Y的关系/关联'、'A是...，以及B是...' 多问综合
    ]
    if len(clean_entities) >= 2 and any(kw in question for kw in multi_subject_keywords):
        return _result("complex", "多主体分别/对比/关系需要多源检索后综合")

    # 路径 2.5b: 双实体 + 全面综合词（'全部影响'/'所有事件'/'综合阐述'）
    if len(clean_entities) >= 2 and any(kw in question for kw in ['全部', '所有', '综合']):
        return _result("complex", "多实体全面综合需要多源检索")

    # 路径 2.6: 多时间点事件综合（≥2 个不同年份 → 跨时间线检索）
    years = set(re.findall(r'\d{3,4}\s*年', question))
    if len(years) >= 2:
        return _result("complex", "多时间点事件需要跨时间线综合")

    # 路径 2.7: 事件枚举（"哪些...事件/事"）→ 需要宽搜多源
    if re.search(r'哪些.{0,12}(事件|事)', question):
        return _result("complex", "事件枚举需要宽搜多源")

    # 路径 3: 深度关键词 + 跨章节 → 需要 Agent 多步检索
    # 注意: '原因' 不作为深度词——"直接原因是什么" 等单事实查询（benchmark 实证误判）。
    #       因果类推理由 causal_reasoning 意图路径（'为什么'/'导致'）覆盖。
    deep_keywords = [
        '导致', '后果', '为什么',
        '对比', '比较', '区别', '异同', '排名', '排序',
        '演变', '变迁', '发展历程', '历程', '变革',
        '时间线', '编年史', '大事记', '梳理',
        '势力格局', '势力分布',
    ]
    has_deep = any(kw in question for kw in deep_keywords)

    if has_deep and time_scope == "cross_arc":
        return _result("complex", "跨章节深度推理问题, 需要多步检索")

    # 路径 4: 跨章节深度问题但实体不足 → Agent 探索兜底
    # W0 修复: 原条件仅要求 cross_arc + 实体空, 而 time_scope 默认即 cross_arc,
    # 导致所有实体提取为空的简单事实题被误判 complex (24/100)。改为要求深度信号。
    if has_deep and len(clean_entities) == 0:
        return _result("complex", "跨章节深度问题但实体不足, Agent 多步检索补充")

    return _result("simple", "简单事实查询")


def route_query(question: str, history=None) -> dict:
    """查询路由主函数：意图识别+改写 → 时序消歧 → 复杂度分类"""
    intent_result = recognize_intent_and_rewrite(question)

    entities = list(intent_result["canonical_entities"])

    # 时序消歧：处理"最新""最近"等时间词
    resolved_entities, temporal_note = _resolve_temporal_entities(question, entities)

    entities = list(set(resolved_entities))
    question_type = intent_result["intent"]

    time_scope = _infer_time_scope(question, entities)
    result = classify_complexity_local(question, entities, question_type, time_scope)

    result["rewritten_question"] = intent_result["rewritten_question"]
    result["expansion_hints"] = intent_result["expansion_hints"]  # 搜索扩展词，不用于路由
    # 合并消歧备注
    disambig = intent_result.get("disambiguation_note", "")
    if temporal_note:
        disambig = f"{disambig}; {temporal_note}" if disambig else temporal_note
    result["disambiguation_note"] = disambig
    result["source"] = intent_result.get("source", "local")
    return result
