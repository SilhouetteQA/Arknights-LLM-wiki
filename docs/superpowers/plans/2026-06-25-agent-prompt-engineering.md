# Agent 提示词工程 + 实体索引 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 通过三层改造（意图识别+问题改写合并、双向实体索引、CASUAL 合成式提示词）修复 Agent 检索精度和回答质量。

**Architecture:** 关键词规则快速路径 → LLM 意图识别+问题改写兜底 → 实体索引驱动定向检索 → CASUAL 风格合成式总结。索引一次性预构建，原文路径存储按需加载。

**Tech Stack:** Python 3.12, LangGraph, DeepSeek API, JSON 文件索引

**Spec:** `CONTEXT.md` (grill-with-docs 结论)

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `arknights_wiki/agent/prompts.py` | 重写 | INTENT_REWRITE_PROMPT + CASUAL QA/AGENT/SYNTHESIS prompts |
| `arknights_wiki/agent/router.py` | 重写 | 合并意图识别+问题改写，更新复杂度路由规则 |
| `arknights_wiki/agent/retrieval.py` | 修改 | 新增 EntityIndexStore 类 |
| `arknights_wiki/agent/simple_search.py` | 修改 | 集成 CASUAL prompt + 索引驱动过滤 |
| `arknights_wiki/agent/graph.py` | 修改 | CASUAL synthesis prompt + 索引工具注入 Agent |
| `arknights_wiki/agent/tools.py` | 修改 | 新增 lookup_entity_index 工具 |
| `scripts/build_entity_index.py` | 新建 | 一次性索引构建脚本 |
| `tests/agent/test_router.py` | 修改 | 意图识别+改写测试 |
| `tests/agent/test_retrieval.py` | 修改 | EntityIndexStore 测试 |
| `tests/agent/test_tools.py` | 修改 | lookup_entity_index 工具测试 |
| `tests/agent/test_simple_search.py` | 修改 | CASUAL 提示词 + 索引集成测试 |
| `tests/agent/test_graph.py` | 修改 | Agent CASUAL synthesis 测试 |

---

### Task 1: prompts.py — 新增 INTENT_REWRITE_PROMPT + 重写三个 CASUAL prompt

**Files:**
- Modify: `arknights_wiki/agent/prompts.py`

**Design:** 四个 prompt 全部替换。ROUTER_SYSTEM_PROMPT 替换为更详细的意图识别+改写 prompt。QA/AGENT/SYNTHESIS 注入 CASUAL persona 风格约束。

- [ ] **Step 1: 更新 prompts.py 全部内容**

```python
"""Agent 和 Simple Search 的 LLM 提示词模板"""

# === 意图识别 + 问题改写 (合并) ===

INTENT_REWRITE_PROMPT = """你是《明日方舟》玩家社群助手。分析用户问题，输出意图分类和改写后的检索用问题。

## 意图类型
- concept_definition: 询问某个概念/设定/机制的定义或本质（如"X是什么"、"X的设定"）
- chapter_summary: 询问某个活动/章节的剧情概要（如"X讲了什么"、"X的剧情"）
- character_profile: 询问角色性格/战力/背景（如"X是什么样的人"、"X的实力"）
- causal_reasoning: 询问因果/原因/演变（如"为什么X"、"X如何变化"）
- comparison: 实体间对比（如"A和B的区别"、"谁更强"）
- fact_lookup: 简短事实查询（如"X的出生地"、"X属于哪个阵营"）
- list_enumeration: 列举清单（如"有哪些X"、"X的成员"）

## 改写原则
- 将口语俗称替换为规范名（"怪猎"→"落叶逐火"或"泡影苍霆"）
- 将模糊指代具体化（"那个龙门的警官"→"陈"）
- "最新"需要从已知发布时间判断，不确定时列出候选供后处理消歧
- 补全隐含的上下文使问题完整
- 输出 expansion_hints 作为辅助检索扩展词

## 输出格式
输出 JSON:
{
  "intent": "concept_definition",
  "rewritten_question": "源石是什么？它的本质和特性是什么？",
  "canonical_entities": ["源石"],
  "expansion_hints": ["源石技艺", "矿石病", "天灾"],
  "disambiguation_note": ""
}

如果意图无法确定，intent 设为 "unknown"。
如果问题中有无法映射为规范实体的表达，在 disambiguation_note 中说明。"""

# === CASUAL persona 回答指南 (Simple Search) ===

QA_SYSTEM_PROMPT = """你是《明日方舟》的剧情叙述助手。用口语化、像朋友聊天的方式回答玩家关于剧情和设定的问题。

## 回答风格
- 用口语化的方式解释，不要用学术腔或百科腔
- 先给一句核心答案，再展开细节说明
- 避免堆砌专有名词，首次出现的术语用一两句自然解释
- 把事件融入连贯叙述中，不要罗列事件清单
- 用你自己的话重新组织信息，不要直接复制粘贴原文
- 内容完整性优先，说清楚为止，不设字数限制
- 忽略参考资料中与问题无关的内容

## 回答约束
- 禁止输出任何引用标记（如 [1]、[来源1] 等）
- 禁止逐条列举事件（如 "事件1: ... 事件2: ..."）
- 禁止分点列表格式，使用自然段落
- 只能根据参考资料回答，如果资料不足则诚实说明"""

# === CASUAL persona 回答指南 (LangGraph Agent) ===

AGENT_SYSTEM_PROMPT = """你是《明日方舟》剧情知识检索专家。逐步检索信息回答玩家问题。

## 可用工具
1. search_wiki(query, category) — 全文搜索 Wiki 页面（概念/阵营/地点/角色）
2. get_entity_page(name, entity_type) — 获取实体完整 Wiki 页面
3. search_events(entity, event_type, chapter) — 搜索剧情事件
4. search_dialogue(query, chapter) — 搜索原始对话文本
5. search_timeline(query) — 搜索历史时间线
6. get_chapter_summary(chapter) — 获取章节摘要
7. semantic_search(query, top_k) — FAISS 语义搜索（模糊/描述性查询）
8. lookup_entity_index(entity_name) — 查找实体的关联实体和相关章节

## 检索策略
- 概念定义类问题：先 lookup_entity_index 确定实体类型和关联章，再 get_entity_page 获取核心定义
- 剧情总结类问题：先 get_chapter_summary，再 search_events(chapter=具体章) 补细节
- 多实体/跨章/世界观概念 → 先用 lookup_entity_index 获取索引，定向检索
- 因果分析/时间线 → 必需 search_timeline
- 发现关键实体立即用 get_entity_page 深入
- 信息足够后立即 stop，不要过度检索

## 最终回答要求 (CASUAL 风格)
- 口语化叙述，像朋友聊天般自然
- 先给核心答案，再展开
- 禁止输出 [来源N] 等引用标记
- 禁止罗列事件清单
- 用自己话重组，不复制原文
- 只基于检索结果回答，不编造"""

# === CASUAL persona 合成提示词 (LangGraph Agent) ===

SYNTHESIS_PROMPT = """基于以下证据材料，用口语化、轻松自然的方式回答玩家的问题。

## 证据材料
{evidence}

## 玩家问题
{question}

## 回答要求
- 用口语化叙述，像朋友给你讲解剧情一样
- 先给一句话核心答案，再展开细节
- 将零散证据融合成连贯的故事叙述
- 不要逐条罗列事件或来源
- 用你自己的话重组信息
- 忽略与问题无关的证据
- 如果证据不足，诚实告诉玩家"这部分剧情我还不太清楚""""
```

- [ ] **Step 2: 运行现有测试确认 prompt 变更不破坏兼容性**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python -m pytest tests/agent/ -v --tb=short 2>&1
```
Expected: 所有通过（prompt 内容变更不影响现有测试逻辑）

- [ ] **Step 3: Commit**

```bash
git add arknights_wiki/agent/prompts.py
git commit -m "feat(agent): add INTENT_REWRITE_PROMPT, rewrite QA/AGENT/SYNTHESIS with CASUAL persona"
```

---

### Task 2: router.py — 合并意图识别+问题改写 + 更新复杂度路由

**Files:**
- Modify: `arknights_wiki/agent/router.py`
- Modify: `tests/agent/test_router.py`

**Design:** 新增 `recognize_intent_and_rewrite()` 合并函数：先用本地关键词规则，规则不匹配时 LLM 兜底。更新 `route_query()` 使用新函数。更新 `classify_complexity_local()` — 世界观概念/多实体/跨章 强制 complex。

- [ ] **Step 1: 写 router 单元测试**

```python
# 在 tests/agent/test_router.py 末尾追加:

class TestRecognizeIntentAndRewrite:
    """意图识别+问题改写合并测试"""

    def test_concept_definition_local(self, temp_data_dir):
        """关键词规则匹配概念定义"""
        from arknights_wiki.agent.router import recognize_intent_and_rewrite
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            result = recognize_intent_and_rewrite("源石是什么")
            assert result["intent"] == "concept_definition"
            assert "源石" in result["canonical_entities"]

    def test_chapter_summary_local(self, temp_data_dir):
        """关键词规则匹配剧情总结"""
        from arknights_wiki.agent.router import recognize_intent_and_rewrite
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            result = recognize_intent_and_rewrite("落叶逐火讲了什么")
            assert result["intent"] == "chapter_summary"
            assert "落叶逐火" in result["canonical_entities"]

    def test_comparison_local(self, temp_data_dir):
        """关键词规则匹配对比"""
        from arknights_wiki.agent.router import recognize_intent_and_rewrite
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            result = recognize_intent_and_rewrite("阿米娅和凯尔希实力对比")
            assert result["intent"] == "comparison"

    def test_llm_fallback_unknown(self, temp_data_dir, mock_llm_client):
        """本地规则无法匹配时 LLM 兜底"""
        from arknights_wiki.agent.router import recognize_intent_and_rewrite
        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = (
            '{"intent": "concept_definition", "rewritten_question": "巨兽是什么", '
            '"canonical_entities": ["巨兽"], "expansion_hints": ["岁兽", "耶拉冈德"], '
            '"disambiguation_note": ""}'
        )
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            with patch("arknights_wiki.agent.router.create_client", return_value=mock_llm_client):
                result = recognize_intent_and_rewrite("巨兽是啥玩意", use_llm=True)
                assert result["intent"] == "concept_definition"
                assert "巨兽" in result["canonical_entities"]
                assert result["source"] == "llm"

    def test_llm_rewrites_slang(self, temp_data_dir, mock_llm_client):
        """LLM 改写口语俗称"""
        from arknights_wiki.agent.router import recognize_intent_and_rewrite
        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = (
            '{"intent": "chapter_summary", "rewritten_question": "落叶逐火活动的剧情讲了什么", '
            '"canonical_entities": ["落叶逐火"], "expansion_hints": ["怪物猎人联动", "MH联动", "CF活动"], '
            '"disambiguation_note": "怪猎通常指落叶逐火联动活动"}'
        )
        with patch("arknights_wiki.agent.router.DATA_DIR", temp_data_dir):
            with patch("arknights_wiki.agent.router.create_client", return_value=mock_llm_client):
                result = recognize_intent_and_rewrite("怪猎活动讲了什么", use_llm=True)
                assert result["intent"] == "chapter_summary"
                assert "落叶逐火" in result["canonical_entities"]
                assert len(result["expansion_hints"]) > 0


class TestComplexityRouting:
    """更新后的复杂度路由规则"""

    def test_worldview_concept_to_complex(self):
        """世界观概念类问题 -> complex"""
        result = classify_complexity_local(
            "巨兽是什么", ["巨兽"], "concept_definition", "cross_arc"
        )
        assert result["complexity"] == "complex"
        assert "世界观概念" in result["reason"]

    def test_multi_entity_to_complex(self):
        """多实体 -> complex"""
        result = classify_complexity_local(
            "阿米娅和凯尔希对比", ["阿米娅", "凯尔希"], "comparison", "cross_arc"
        )
        assert result["complexity"] == "complex"

    def test_cross_chapter_to_complex(self):
        """跨章节 -> complex"""
        result = classify_complexity_local(
            "矿石病在整个泰拉的演变", ["矿石病"], "concept_definition", "cross_arc"
        )
        assert result["complexity"] == "complex"

    def test_character_profile_cross_arc_to_complex(self):
        """角色跨章 -> complex"""
        result = classify_complexity_local(
            "阿米娅的性格变化", ["阿米娅"], "character_profile", "cross_arc"
        )
        assert result["complexity"] == "complex"

    def test_simple_fact_remains_simple(self):
        """简单事实查询保持 simple"""
        result = classify_complexity_local(
            "阿米娅的出生地", ["阿米娅"], "fact_lookup", "chapter"
        )
        assert result["complexity"] == "simple"
```

- [ ] **Step 2: 运行测试确认新测试失败**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python -m pytest tests/agent/test_router.py -v --tb=short 2>&1
```
Expected: 新测试 FAIL（函数尚未实现）

- [ ] **Step 3: 实现 recognize_intent_and_rewrite() 和更新 classify_complexity_local()**

```python
# 在 router.py 中替换 _infer_question_type 和更新 classify_complexity_local

def recognize_intent_and_rewrite(question: str, use_llm: bool = True) -> dict:
    """合并意图识别和问题改写：本地规则先行，LLM 兜底

    返回:
      {intent, rewritten_question, canonical_entities, expansion_hints,
       disambiguation_note, source: "local"|"llm"}
    """
    # 本地关键词规则
    intent = _infer_intent_local(question)
    entities = _extract_entities_local(question)
    clean_entities = [e for e in entities if not e.startswith("__")]

    # 规则命中且实体非空 → 本地结果
    if intent != "unknown" and len(clean_entities) > 0:
        return {
            "intent": intent,
            "rewritten_question": question,
            "canonical_entities": clean_entities,
            "expansion_hints": [],
            "disambiguation_note": "",
            "source": "local",
        }

    # LLM 兜底
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


def classify_complexity_local(
    question: str, entities: list[str], question_type: str, time_scope: str
) -> dict:
    """纯规则判断问题复杂度

    规则：comparison / concept_definition+世界观 / list_enumeration
    / 多实体 / 深度关键词+cross_arc → complex
    """
    clean_entities = [e for e in entities if not e.startswith("__")]

    # 强制 complex 的意图
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

    # 多实体 → complex
    if len(clean_entities) > 1:
        return {
            "complexity": "complex",
            "question_type": question_type,
            "entities": entities,
            "time_scope": time_scope,
            "reason": "多实体需要分别检索后综合",
        }

    # 深度关键词 + 跨章 → complex
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

    # 跨章但无实体 → complex (Agent 多步检索补充)
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
    """查询路由主函数：意图识别+改写 → 复杂度分类"""
    intent_result = recognize_intent_and_rewrite(question)

    entities = intent_result["canonical_entities"] + intent_result["expansion_hints"]
    entities = list(set(entities))
    question_type = intent_result["intent"]

    time_scope = _infer_time_scope(question, entities)
    result = classify_complexity_local(question, entities, question_type, time_scope)

    # 附加改写信息到路由结果
    result["rewritten_question"] = intent_result["rewritten_question"]
    result["expansion_hints"] = intent_result["expansion_hints"]
    result["disambiguation_note"] = intent_result["disambiguation_note"]
    result["source"] = intent_result.get("source", "local")
    return result
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python -m pytest tests/agent/test_router.py -v --tb=short 2>&1
```
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/agent/router.py tests/agent/test_router.py
git commit -m "feat(agent): merge intent recognition + query rewrite, force complex for worldview/multi-entity"
```

---

### Task 3: scripts/build_entity_index.py + EntityIndexStore — 预构建双向实体索引

**Files:**
- Create: `scripts/build_entity_index.py`
- Modify: `arknights_wiki/agent/retrieval.py` (新增 EntityIndexStore)
- Modify: `tests/agent/test_retrieval.py`

**Design:** 构建脚本遍历 Pass1/2/3/档案/大地巡旅，为每个实体建立 source_files 和 related_* 双向关系。EntityIndexStore 加载 JSON 提供 O(1) 查找。

- [ ] **Step 1: 写 build_entity_index 测试**

```python
# tests/agent/test_retrieval.py 末尾追加:

class TestEntityIndexStore:
    """实体索引存储测试"""

    def test_build_and_load_index(self, temp_data_dir):
        """构建并加载索引"""
        import subprocess, sys, os, json
        # 运行构建脚本
        index_path = os.path.join(temp_data_dir, "entity_source_map.json")
        subprocess.run([
            sys.executable, "scripts/build_entity_index.py",
            "--data-dir", temp_data_dir,
            "--output", index_path,
        ], check=True, capture_output=True)
        assert os.path.exists(index_path)

        # 加载并验证
        store = EntityIndexStore(data_dir=temp_data_dir)
        entry = store.lookup("源石")
        assert entry is not None
        assert entry["type"] == "concept"
        assert "source_files" in entry
        assert "related_entities" in entry

    def test_lookup_missing_entity(self, temp_data_dir):
        """查找不存在的实体"""
        store = EntityIndexStore(data_dir=temp_data_dir)
        assert store.lookup("不存在的实体XYZ") is None

    def test_bidirectional_lookup(self, temp_data_dir):
        """双向索引：从 faction 能找到 member characters"""
        import subprocess, sys, os
        index_path = os.path.join(temp_data_dir, "entity_source_map.json")
        subprocess.run([
            sys.executable, "scripts/build_entity_index.py",
            "--data-dir", temp_data_dir,
            "--output", index_path,
        ], check=True, capture_output=True)

        store = EntityIndexStore(data_dir=temp_data_dir)
        entry = store.lookup("罗德岛")
        assert entry is not None
        assert entry["type"] == "faction"

    def test_search_related(self, temp_data_dir):
        """搜索关联实体"""
        import subprocess, sys, os
        index_path = os.path.join(temp_data_dir, "entity_source_map.json")
        subprocess.run([
            sys.executable, "scripts/build_entity_index.py",
            "--data-dir", temp_data_dir,
            "--output", index_path,
        ], check=True, capture_output=True)

        store = EntityIndexStore(data_dir=temp_data_dir)
        related = store.search_related("源石")
        assert isinstance(related, list)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python -m pytest tests/agent/test_retrieval.py::TestEntityIndexStore -v --tb=short 2>&1
```
Expected: FAIL（EntityIndexStore 未定义）

- [ ] **Step 3: 创建 scripts/build_entity_index.py**

```python
#!/usr/bin/env python3
"""预构建双向实体索引 entity_source_map.json

数据源: Pass1 events + Pass2 characters + Pass3 wiki + operators.json + 大地巡旅
输出: {DATA_DIR}/entity_source_map.json
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict


def build_index(data_dir: str) -> dict:
    """构建双向实体索引"""
    index = {}

    # 1. Pass 1 events → entity → chapters
    events_dir = os.path.join(data_dir, "extractions", "v1_events")
    if os.path.isdir(events_dir):
        for root, dirs, files in os.walk(events_dir):
            for fname in files:
                if not fname.endswith(".json"):
                    continue
                fp = os.path.join(root, fname)
                try:
                    data = json.loads(Path(fp).read_text(encoding="utf-8"))
                except Exception:
                    continue
                chapter = os.path.splitext(fname)[0]

                # 事件中的参与者 → 章节
                for evt in data.get("events", []):
                    for participant in evt.get("participants", []):
                        if not participant:
                            continue
                        _ensure(index, participant, "character")
                        _add_source(index, participant, "pass1_events", fname)
                        _add_source(index, participant, "raw_stories",
                                     _story_path(chapter, data.get("chapter", chapter)))

                # 概念 → 章节
                for concept in data.get("concepts", []):
                    name = concept.get("name", "")
                    if not name:
                        continue
                    _ensure(index, name, "concept")
                    _add_source(index, name, "pass1_events", fname)

                # 阵营 → 章节
                for faction in data.get("factions", []):
                    name = faction.get("name", "")
                    if not name:
                        continue
                    _ensure(index, name, "faction")
                    _add_source(index, name, "pass1_events", fname)

                # 地点 → 章节
                for loc in data.get("locations", []):
                    name = loc.get("name", "")
                    if not name:
                        continue
                    _ensure(index, name, "location")
                    _add_source(index, name, "pass1_events", fname)

    # 2. Pass 2 characters → character entities
    chars_dir = os.path.join(data_dir, "extractions", "v2_characters")
    if os.path.isdir(chars_dir):
        for fname in os.listdir(chars_dir):
            if not fname.endswith(".json"):
                continue
            fp = os.path.join(chars_dir, fname)
            try:
                data = json.loads(Path(fp).read_text(encoding="utf-8"))
            except Exception:
                continue
            name = data.get("display_name") or data.get("name", "")
            if not name:
                continue
            _ensure(index, name, "character")

            # 关联阵营
            faction = data.get("faction", "")
            if faction:
                _ensure(index, faction, "faction")
                _add_relation(index, name, "related_factions", faction)
                _add_relation(index, faction, "related_characters", name)

            # 关联地点
            birthplace = data.get("birthplace", "")
            if birthplace:
                _ensure(index, birthplace, "location")
                _add_relation(index, name, "related_locations", birthplace)

    # 3. Pass 3 wiki pages → concepts/factions/locations
    for entity_type in ["concept", "faction", "location"]:
        wiki_dir = os.path.join(data_dir, "extractions", "v3_wiki", entity_type + "s")
        if not os.path.isdir(wiki_dir):
            continue
        for fname in os.listdir(wiki_dir):
            if not fname.endswith(".md"):
                continue
            name = os.path.splitext(fname)[0]
            fp = os.path.join(wiki_dir, fname)
            _ensure(index, name, entity_type)

            # 提取关联实体
            try:
                content = Path(fp).read_text(encoding="utf-8")
            except Exception:
                continue
            # 从内容提取 [[entity]] 或提到的其他实体
            for other_name, other_entry in index.items():
                if other_name != name and other_name in content:
                    if other_entry["type"] in ("faction", "location") and entity_type == "character":
                        _add_relation(index, name, f"related_{other_entry['type']}s", other_name)
                    elif entity_type in ("concept", "faction", "location"):
                        _add_relation(index, name, "related_entities", other_name)

    # 4. 大地巡旅 → 概念/阵营/地点
    lorebook_dir = os.path.join(data_dir, "lorebook", "terra_a_journey")
    if os.path.isdir(lorebook_dir):
        for fname in os.listdir(lorebook_dir):
            if not fname.startswith("page_") or not fname.endswith(".md"):
                continue
            fp = os.path.join(lorebook_dir, fname)
            try:
                content = Path(fp).read_text(encoding="utf-8")
            except Exception:
                continue
            for entity_name, entry in index.items():
                if len(entity_name) >= 2 and entity_name in content:
                    _add_source(index, entity_name, "terra_journey", fname)

    # 5. 干员档案
    operators_path = os.path.join(data_dir, "operators.json")
    if os.path.exists(operators_path):
        try:
            operators = json.loads(Path(operators_path).read_text(encoding="utf-8"))
        except Exception:
            operators = {}
        for op_name in operators:
            _ensure(index, op_name, "character")
            _add_source(index, op_name, "operator_archives", "operators.json")

    return index


def _ensure(index: dict, name: str, entity_type: str):
    if name not in index:
        index[name] = {
            "type": entity_type,
            "source_files": defaultdict(list),
            "related_entities": [],
            "related_factions": [],
            "related_locations": [],
            "related_characters": [],
        }


def _add_source(index: dict, name: str, source_type: str, filename: str):
    if filename not in index[name]["source_files"][source_type]:
        index[name]["source_files"][source_type].append(filename)


def _add_relation(index: dict, name: str, relation_field: str, target: str):
    if target not in index[name].get(relation_field, []):
        index[name].setdefault(relation_field, []).append(target)


def _story_path(chapter: str, category: str) -> str:
    return f"data/stories/{category}/{chapter}/"


def main():
    parser = argparse.ArgumentParser(description="构建实体双向索引")
    parser.add_argument("--data-dir", required=True, help="数据根目录")
    parser.add_argument("--output", required=True, help="输出 JSON 路径")
    args = parser.parse_args()

    index = build_index(args.data_dir)

    # 转换 defaultdict → 普通 list
    output = {}
    for name, entry in index.items():
        cleaned = {
            "type": entry["type"],
            "source_files": {k: list(v) for k, v in entry["source_files"].items()},
            "related_entities": entry.get("related_entities", []),
            "related_factions": entry.get("related_factions", []),
            "related_locations": entry.get("related_locations", []),
            "related_characters": entry.get("related_characters", []),
        }
        output[name] = cleaned

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"索引构建完成: {len(output)} 实体 → {args.output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 在 retrieval.py 新增 EntityIndexStore**

```python
# 在 retrieval.py 末尾追加:

class EntityIndexStore:
    """实体双向索引 -- 加载 entity_source_map.json 提供 O(1) 查找"""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = data_dir or DATA_DIR
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
        """获取实体的关联实体名列表"""
        entry = self.lookup(name)
        if not entry:
            return []
        related = []
        for field in ["related_entities", "related_factions", "related_locations", "related_characters"]:
            related.extend(entry.get(field, []))
        return related

    def get_source_chapters(self, name: str) -> list[str]:
        """获取实体出现的章节列表（从 pass1_events）"""
        entry = self.lookup(name)
        if not entry:
            return []
        pass1 = entry.get("source_files", {}).get("pass1_events", [])
        return [f.replace(".json", "") for f in pass1]

    def get_type(self, name: str) -> str | None:
        """获取实体类型"""
        entry = self.lookup(name)
        return entry["type"] if entry else None
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python -m pytest tests/agent/test_retrieval.py::TestEntityIndexStore -v --tb=short 2>&1
```
Expected: ALL PASS

- [ ] **Step 6: 在 tools.py 添加 lookup_entity_index 工具**

```python
# 在 tools.py 文件末尾追加:

def lookup_entity_index(entity_name: str) -> str:
    """查找实体在预构建索引中的关联实体和相关章节。用于确定检索范围和发现相关实体。"""
    store = EntityIndexStore(data_dir=_get_data_dir())
    entry = store.lookup(entity_name)
    if entry is None:
        return f"未在索引中找到实体: {entity_name}"

    lines = [f"实体 '{entity_name}' ({entry['type']}):"]

    # 关联实体
    for field, label in [
        ("related_entities", "关联概念"),
        ("related_factions", "关联阵营"),
        ("related_locations", "关联地点"),
        ("related_characters", "关联角色"),
    ]:
        items = entry.get(field, [])
        if items:
            lines.append(f"  {label}: {', '.join(items[:10])}")

    # 出现章节
    chapters = store.get_source_chapters(entity_name)
    if chapters:
        lines.append(f"  出现章节: {', '.join(chapters[:10])}")

    return "\n".join(lines)


# 添加到 TOOL_DEFINITIONS (在现有列表末尾追加):
TOOL_DEFINITIONS.append({
    "type": "function",
    "function": {
        "name": "lookup_entity_index",
        "description": "查找实体在预构建索引中的关联实体、相关章节。用于确定检索方向和发现相关实体。",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_name": {"type": "string", "description": "实体名称"},
            },
            "required": ["entity_name"],
        },
    },
})

# 添加到 TOOL_EXECUTORS:
TOOL_EXECUTORS["lookup_entity_index"] = lookup_entity_index
```

- [ ] **Step 7: 运行 tools 测试确认通过**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python -m pytest tests/agent/test_tools.py -v --tb=short 2>&1
```
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add scripts/build_entity_index.py arknights_wiki/agent/retrieval.py arknights_wiki/agent/tools.py tests/agent/test_retrieval.py
git commit -m "feat(agent): add EntityIndexStore + build_entity_index script, add lookup_entity_index tool"
```

---

### Task 4: simple_search.py — CASUAL prompt 集成 + 索引驱动检索

**Files:**
- Modify: `arknights_wiki/agent/simple_search.py`
- Modify: `tests/agent/test_simple_search.py`

**Design:** `search_and_collect()` 利用 `rewritten_question` + `expansion_hints` 做检索。概念定义类问题优先 `get_entity_page` 而非广撒网。`build_answer_prompt()` 使用新的 CASUAL 格式化。

- [ ] **Step 1: 写 simple_search 更新测试**

```python
# tests/agent/test_simple_search.py 末尾追加:

class TestCASUALSearch:
    """CASUAL 风格搜索测试"""

    def test_concept_definition_prioritizes_page(self, temp_data_dir, mock_llm_client):
        """概念定义类优先 get_entity_page"""
        route = {
            "complexity": "simple",
            "question_type": "concept_definition",
            "entities": ["源石"],
            "rewritten_question": "源石是什么",
            "expansion_hints": [],
        }
        with patch("arknights_wiki.agent.simple_search.DATA_DIR", temp_data_dir):
            with patch("arknights_wiki.agent.simple_search.create_client", return_value=mock_llm_client):
                sources = search_and_collect(
                    entities=["源石"],
                    question="源石是什么",
                    question_type="concept_definition",
                )
                # 精确匹配的页面应该排在前面
                assert len(sources) > 0
                assert sources[0]["match_type"] == "exact"

    def test_chapter_summary_includes_summary(self, temp_data_dir, mock_llm_client):
        """剧情总结类包含章节摘要"""
        route = {
            "complexity": "simple",
            "question_type": "chapter_summary",
            "entities": ["黑暗时代·上"],
            "rewritten_question": "黑暗时代·上讲了什么",
            "expansion_hints": [],
        }
        with patch("arknights_wiki.agent.simple_search.DATA_DIR", temp_data_dir):
            with patch("arknights_wiki.agent.simple_search.create_client", return_value=mock_llm_client):
                sources = search_and_collect(
                    entities=["黑暗时代·上"],
                    question="黑暗时代·上讲了什么",
                    question_type="chapter_summary",
                )
                assert len(sources) > 0


class TestBuildAnswerPrompt:
    """CASUAL answer prompt 构建测试"""

    def test_prompt_includes_casual_instructions(self):
        """prompt 包含 CASUAL 风格指令"""
        sources = [{
            "entity_type": "concept",
            "name": "源石",
            "text": "源石是泰拉世界的核心能源。",
        }]
        prompt = build_answer_prompt("源石是什么", sources)
        assert "用口语化" in prompt or "不要罗列" in prompt
        assert "源石" in prompt

    def test_no_citation_marks_instruction(self):
        """prompt 包含禁止引用标记指令"""
        prompt = build_answer_prompt("测试问题", [])
        assert "禁止" in prompt or "不要罗列" in prompt
```

- [ ] **Step 2: 实现 simple_search.py 更新**

```python
# 更新 build_answer_prompt:

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
    event_store = EventStore(data_dir=data_dir)
    if question_type == "chapter_summary":
        for entity in entities:
            summary = event_store.get_chapter_summary(entity)
            if summary:
                add(summary)
            # 限定章节的事件
            for evt in event_store.search(chapter=entity, limit=10):
                add(evt)

    # 常规事件搜索
    for entity in entities:
        for evt in event_store.search(entity=entity, limit=5):
            add(evt)

    # FAISS 语义搜索 (限制 top_k 减少噪声)
    index_dir = os.path.join(data_dir, "index")
    index_path = os.path.join(index_dir, "faiss.index")
    map_path = os.path.join(index_dir, "chunk_map.json")
    if os.path.exists(index_path) and os.path.exists(map_path):
        from arknights_wiki.agent.vector_index import load_index, semantic_search
        try:
            index, chunk_map = load_index(index_path, map_path)
            faiss_results = semantic_search(question, index, chunk_map, top_k=5)
            for r in faiss_results:
                if r["score"] > 0.4:  # 提高阈值减少噪声
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
```

- [ ] **Step 3: 运行测试确认通过**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python -m pytest tests/agent/test_simple_search.py -v --tb=short 2>&1
```
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add arknights_wiki/agent/simple_search.py tests/agent/test_simple_search.py
git commit -m "feat(agent): CASUAL prompt integration + intent-driven retrieval strategy in simple_search"
```

---

### Task 5: graph.py — CASUAL synthesis + 索引工具注入 Agent

**Files:**
- Modify: `arknights_wiki/agent/graph.py`
- Modify: `tests/agent/test_graph.py`

**Design:** `synthesize_node` 使用新的 `SYNTHESIS_PROMPT`。Agent 引导 prompt (`AGENT_SYSTEM_PROMPT`) 已在 Task 1 更新，包含 lookup_entity_index 工具说明。状态中新增 `intent` 字段供 synthesis 使用。

- [ ] **Step 1: 写 graph 更新测试**

```python
# tests/agent/test_graph.py 末尾追加:

class TestCASUALSynthesis:
    """CASUAL 风格 synthesis 测试"""

    def test_synthesis_uses_casual_prompt(self, mock_llm_client):
        """synthesis 使用 CASUAL 提示词"""
        from arknights_wiki.agent.graph import synthesize_node
        state = {
            "messages": [
                {"role": "system", "content": "test"},
                {"role": "user", "content": "源石是什么"},
            ],
            "question": "源石是什么",
            "collected_docs": [
                {"tool": "get_entity_page", "args": {"name": "源石", "entity_type": "concept"},
                 "result": "源石是泰拉世界的核心能源。"},
            ],
            "iteration": 1,
            "route": {"intent": "concept_definition", "entities": ["源石"]},
        }
        with patch("arknights_wiki.agent.graph.create_client", return_value=mock_llm_client):
            result = synthesize_node(state)
            messages = result.get("messages", [])
            assert len(messages) > 0

    def test_synthesis_no_docs_graceful(self):
        """无证据时优雅处理"""
        from arknights_wiki.agent.graph import synthesize_node
        state = {
            "messages": [
                {"role": "system", "content": "test"},
                {"role": "user", "content": "不存在的实体"},
            ],
            "question": "不存在的实体",
            "collected_docs": [],
            "iteration": 1,
            "route": {"intent": "unknown", "entities": []},
        }
        result = synthesize_node(state)
        messages = result.get("messages", [])
        answer = messages[-1].get("content", "")
        assert len(answer) > 0
        assert "无法" in answer or "不足" in answer or "不确定" in answer

    def test_build_agent_graph_includes_index_tool(self):
        """编译后的图包含 lookup_entity_index 工具"""
        from arknights_wiki.agent.graph import build_agent_graph
        from arknights_wiki.agent.tools import TOOL_DEFINITIONS
        tool_names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        assert "lookup_entity_index" in tool_names
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python -m pytest tests/agent/test_graph.py::TestCASUALSynthesis -v --tb=short 2>&1
```
Expected: FAIL（state 字段变更不兼容）

- [ ] **Step 3: 更新 graph.py**

```python
# 在 synthesize_node 中，将 route 信息注入 prompt:

def synthesize_node(state: AgentState) -> AgentState:
    """综合所有证据，生成 CASUAL 风格最终回答"""
    from arknights_wiki.extraction.llm_client import create_client

    question = state["question"]
    collected_docs = state.get("collected_docs", [])
    route = state.get("route", {})

    evidence_parts = []
    for i, doc in enumerate(collected_docs, 1):
        evidence_parts.append(f"[来源{i}] 工具: {doc['tool']}, 参数: {doc['args']}")
        evidence_parts.append(doc["result"])
        evidence_parts.append("")

    evidence_text = "\n".join(evidence_parts) if evidence_parts else "无证据收集到。"

    if not collected_docs:
        answer = "抱歉，我目前掌握的剧情资料里还没有这部分内容。你可以换个方式问我，或者问点别的。"
    else:
        prompt = SYNTHESIS_PROMPT.format(evidence=evidence_text, question=question)
        try:
            client = create_client()
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=8192,
            )
            answer = response.choices[0].message.content or ""
        except Exception as e:
            answer = f"抱歉，回答生成出了点问题。请稍后再试。"

    state["messages"] = state["messages"] + [
        {"role": "assistant", "content": answer}
    ]
    return state
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python -m pytest tests/agent/test_graph.py -v --tb=short 2>&1
```
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add arknights_wiki/agent/graph.py tests/agent/test_graph.py
git commit -m "feat(agent): CASUAL synthesis prompt + entity index tool integration in LangGraph agent"
```

---

### Task 6: 全量测试 + 索引构建

- [ ] **Step 1: 运行全量 agent 测试**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python -m pytest tests/agent/ -v --tb=short 2>&1
```
Expected: ALL PASS (增量后 > 45 tests)

- [ ] **Step 2: 构建实体索引**

```bash
cd "D:/AI project/Arknights LLM Wiki" && python scripts/build_entity_index.py \
  --data-dir data \
  --output data/entity_source_map.json 2>&1
```
Expected: 输出实体数量和文件路径

- [ ] **Step 3: Commit**

```bash
git add tests/agent/
git commit -m "test(agent): add CASUAL + intent-rewrite + entity-index integration tests"
```
