"""Pass 3 世界观实体提取提示词"""


_BOOK_SYSTEM_PROMPT = """你是一位《明日方舟》世界观设定档案编纂者。你的任务是从设定集《大地巡旅》的章节中提取结构化世界观实体。

## 提取三类实体（按输出顺序: 先阵营和地点，再概念）

### 1. 阵营 (factions) — 优先提取
有组织的行动者，分为两类:
- nation (国家/政权): 维多利亚、乌萨斯、炎、拉特兰、卡兹戴尔...
- organization (势力/组织): 莱茵生命、整合运动、罗德岛、黑钢国际...
**重要: 每个国家/政权必须提取为一个独立的 faction 条目**

### 2. 地点 (locations) — 优先提取
具体物理场所，分为两类:
- city (城市/移动城市): 龙门、汐斯塔、切尔诺伯格...
- facility (设施/建筑): 罗德岛本舰、莱茵生命总部、移动城市核心城...
注意: 特殊地貌/异域归入概念层的"特殊地域/异域"子类，不在地点层

### 3. 概念 (concepts)
世界观层面的客观实体，分为六子类:
- 自然现象/物质: 源石、天灾、活性源石、矿石病
- 种族/血脈: 萨卡兹、阿戈尔、库兰塔、提卡兹
- 超自然存在: 巨兽、兽主、海嗣、邪魔、岁兽
- 技术/技艺体系: 源石技艺七学派、移动城市技术、炼金术
- 社会制度/文化: 拉特兰律法、骑士竞技、天灾信使制度
- 特殊地域/异域: 焚风热土、黑流树海、荒域、星荚

纳入标准: 属于六子类之一的客观世界实体
排除标准: 情感/品德/角色观点/模糊隐喻
不设频率门槛: 即使只在文中出现一次，只要是关键设定信息就提取
**概念数量较多时，summary 尽量精简（100-300字），优先保证 factions 和 locations 不被截断**

## 提取规则

1. **同名实体合并**: 如果同一实体在本章多处出现，合并为一个条目，在 summary 中综合所有信息
2. **不做跨章猜测**: 只基于本章提供的内容提取，不要引入你在其他资料中知道的信息
3. **人名/地名/事件名显式标注**: 在 summary 和独有字段中，使用【】标注关键实体名
4. **source_records**: 标注 source="terra_book"，source_detail="大地巡旅 <章节名>"
5. **关系字段**: 如果文中提到实体间的关联，填写 related_concepts / related_factions / related_locations
6. **注意实体辨析**: 同一个词在不同语境下可能对应不同实体，例如"萨卡兹"作为种族(概念层)和"萨卡兹王庭"作为政治组织(阵营层)
7. **捕捉时间线事件**: 留意文本中出现的具体年份（如797、1086-1094）及对应的历史事件描述，提取到 timeline_events。即使文中仅提及年份无详细描述也要记录，标注 year_note 补充相对时序（如"乌萨斯-卡西米尔战争期间"）。年份可能稀疏，但出现时往往描述重大事件

## 输出格式

严格输出 JSON，不要包含 markdown 代码块标记。
JSON 字符串值内禁止使用英文双引号 "，用「」代替。"""


_BOOK_USER_PROMPT_TEMPLATE = """## 设定集章节: {chapter_title}

以下是《大地巡旅》中"{chapter_title}"的完整文本:

{chapter_text}

## 输出要求

请提取本章中所有三层实体，输出 JSON:

{output_schema}

## 规则
- 必须基于提供的文本内容，不编造
- 同一实体在多处出现时合并为一个条目
- definition 一句话定义不超过 80 字
- 阵营 summary 不超过 400 字，地点不超过 300 字，概念 summary 精炼至 100-300 字（概念数量多时优先精简以留出 factions/locations 空间）
- 各类独有字段有信息就填，没有可省略
- 输出顺序: 先写 factions 和 locations，最后写 concepts，确保核心实体不被截断"""


_VIDEO_SYSTEM_PROMPT = """你是一位《明日方舟》世界观设定档案编纂者。你的任务是从官方世界观视频中提取结构化实体，并丰富已有的设定集实体库。

## 已有实体库

下方提供了从《大地巡旅》官方设定集提取的已知实体列表。你的首要任务是:

1. **丰富已有实体**: 如果视频内容对已知实体提供了新信息（细节、案例、不同角度），更新该实体的 summary 和独有字段
2. **发现新实体**: 只有确认是现有实体库中没有的全新实体时，才创建新条目
3. **不重复创建**: 视频中出现但实体库已有的实体，不要作为新实体输出

## 视频发布时间说明

视频的发布时间已标注在每个视频的头部。当视频内容涉及主线剧情演进（如组织的成立/解散、城市的建立/废弃、角色的状态变化等），注意结合发布时间判断视频描述的是转变前还是转变后的状态。常规世界观信息（如源石原理、种族特征）不受发布时间影响。

## 提取三类实体

与设定集提取相同: concepts(六子类) / factions(两类) / locations(两类)

## 时间线事件

同样留意视频中出现的具体年份和对应的历史事件描述，提取到 timeline_events。视频发布时间可作为时间参考锚点。

## 输出格式

严格输出 JSON，不要包含 markdown 代码块标记。
JSON 字符串值内禁止使用英文双引号 "，用「」代替。"""


_VIDEO_USER_PROMPT_TEMPLATE = """## 视频字幕合集

{video_text}

{seed_context}

## 输出要求

请基于视频内容，对已知实体库进行补充和丰富，如发现新实体则创建。

输出 JSON:

{output_schema}

## 规则
- 优先丰富已有实体，只有确认是全新实体时才创建
- source_records 中 source="video"，source_detail 标注视频标题和发布时间
- 新实体和丰富后的实体都输出，已有实体无新增信息则不输出
- 视频中的信息可能与设定集一致（跳过），也可能提供新角度（补充），也可能冲突（标注 confidence="conflicting"）
- 注意发布时间与主线剧情演进的关系"""


_OUTPUT_SCHEMA = """{
  "factions": [
    {
      "name": "实体名称",
      "category": "nation或organization",
      "definition": "一句话定义(≤80字)",
      "summary": "综合描述(≤400字)",
      "aliases": ["别名"],
      "government_type": "政体(仅nation)",
      "ruler": "统治者(仅nation)",
      "key_figures": [{"name": "...", "role": "...", "description": "..."}],
      "capital": "首都(仅nation)",
      "territory": "疆域(仅nation)",
      "major_races": ["主要种族(仅nation)"],
      "historical_events": [{"name": "...", "timeframe": "...", "description": "..."}],
      "foreign_relations": [{"target_nation": "...", "attitude": "...", "description": "..."}],
      "type": "类型(仅organization)",
      "parent_nation": "所属国家(仅organization)",
      "leader": "首领(仅organization)",
      "headquarters": "总部(仅organization)",
      "member_composition": [{"name": "...", "role": "...", "description": "..."}],
      "goal": "宗旨(仅organization)",
      "external_relations": [{"target": "...", "relation_type": "...", "description": "..."}],
      "source_records": [{"source": "terra_book或video", "source_detail": "...", "location": "...", "publish_date": "...(仅video)", "confidence": "confirmed或inferred或conflicting"}],
      "story_events": [],
      "related_concepts": [{"name": "...", "relation": "...", "desc": "..."}]
    }
  ],
  "locations": [
    {
      "name": "实体名称",
      "category": "city或facility",
      "definition": "一句话定义(≤80字)",
      "summary": "综合描述(≤300字)",
      "aliases": ["别名"],
      "parent_nation": "所属国家(仅city)",
      "city_type": "类型(仅city)",
      "scale": "规模(仅city)",
      "known_districts": [{"name": "...", "description": "..."}],
      "key_events": [{"name": "...", "description": "..."}],
      "located_in": "所在城市(仅facility)",
      "facility_type": "设施类型(仅facility)",
      "owner": "所属阵营(仅facility)",
      "purpose": "用途(仅facility)",
      "source_records": [{"source": "terra_book或video", "source_detail": "...", "location": "...", "publish_date": "...(仅video)", "confidence": "confirmed或inferred或conflicting"}],
      "story_events": [],
      "related_factions": [{"name": "...", "relation": "...", "desc": "..."}],
      "related_concepts": [{"name": "...", "relation": "...", "desc": "..."}]
    }
  ],
  "concepts": [
    {
      "name": "实体名称",
      "category": "六子类之一",
      "definition": "一句话定义(≤80字)",
      "summary": "简练描述(100-300字，不要超过500字)",
      "aliases": ["别名1"],
      "manifestation": "表现形态(自然现象/物质)",
      "origin_hypothesis": "起源假说(自然现象/物质)",
      "related_arts": "关联源石技艺(自然现象/物质)",
      "origin_region": "起源地(种族)",
      "physical_traits": "体貌特征(种族)",
      "related_races": ["亲缘种族(种族)"],
      "oripathy_susceptibility": "矿石病易感性(种族)",
      "lifespan": "寿命特征(种族)",
      "nature": "本质(超自然存在)",
      "scale": "位阶/规模(超自然存在)",
      "known_instances": ["已知个体(超自然存在)"],
      "relation_to_humanity": "与人类关系(超自然存在)",
      "underlying_principle": "底层原理(技术)",
      "practitioners": "使用群体(技术)",
      "spread": "传播范围(技术)",
      "key_applications": ["关键应用(技术)"],
      "origin_nation": "起源国家(社会制度)",
      "characteristics": "制度特点(社会制度)",
      "key_institutions": ["核心机构(社会制度)"],
      "social_impact": "社会影响(社会制度)",
      "location_type": "地域类型(特殊地域)",
      "accessibility": "进入方式(特殊地域)",
      "hazards": ["危险要素(特殊地域)"],
      "phenomena": ["独特现象(特殊地域)"],
      "source_records": [{"source": "terra_book或video", "source_detail": "...", "location": "...", "publish_date": "...(仅video)", "confidence": "confirmed或inferred或conflicting"}],
      "story_events": [],
      "related_concepts": [{"name": "...", "relation": "...", "desc": "..."}],
      "related_factions": [{"name": "...", "relation": "...", "desc": "..."}],
      "related_locations": [{"name": "...", "relation": "...", "desc": "..."}]
    }
  ],
  "timeline_events": [
    {
      "year": "具体年份或年份范围，如 797 或 1086-1094，或 null（无具体年份）",
      "year_note": "相对时序描述，如「乌萨斯-卡西米尔战争期间」(无具体年份时必填)",
      "event": "事件简述",
      "involved_nations": ["涉及的国家/阵营"],
      "involved_locations": ["涉及的地点"],
      "significance": "历史意义（一句话）",
      "source": "来源标记: timeline_appendix / terra_book / video"
    }
  ]
}"""


def build_book_system_prompt() -> str:
    return _BOOK_SYSTEM_PROMPT


def build_book_user_prompt(chapter_title: str, chapter_text: str) -> str:
    return _BOOK_USER_PROMPT_TEMPLATE.format(
        chapter_title=chapter_title,
        chapter_text=chapter_text,
        output_schema=_OUTPUT_SCHEMA,
    )


def build_video_system_prompt() -> str:
    return _VIDEO_SYSTEM_PROMPT


def build_video_user_prompt(video_text: str, seed_context: str = "") -> str:
    return _VIDEO_USER_PROMPT_TEMPLATE.format(
        video_text=video_text,
        seed_context=seed_context,
        output_schema=_OUTPUT_SCHEMA,
    )


_TIMELINE_SYSTEM_PROMPT = """你是一位《明日方舟》历史编年学者。你的任务是从《大地巡旅》附录的"泰拉纪年"年表中提取结构化的历史事件。

## 年表格式

年表以「**年份** + 事件描述」的格式排列，覆盖泰拉世界从远古到当代的历史进程。

## 提取规则

1. **每个事件条目提取为一条记录**: 每条 timeline_event 包含:
   - year: 具体年份或年份范围（如 797、1086-1094）
   - year_note: 如年份非精确（如"约900年代"），在 year 标注大致年份，year_note 补充说明
   - event: 事件简述
   - involved_nations: 涉及的国家/阵营名称列表
   - involved_locations: 涉及的地点名称列表
   - significance: 历史意义（一句话）
   - source: 固定为 "timeline_appendix"
2. **同一年多条事件**: 分别提取为独立条目
3. **关联已有实体**: 事件中提到的国家/阵营/地点名称，使用游戏内常用中文名
4. **不做推测**: 只提取年表中明确记载的事件，不补充不在年表中的历史

## 输出格式

严格输出 JSON，不要包含 markdown 代码块标记。
JSON 字符串值内禁止使用英文双引号 "，用「」代替。"""

_TIMELINE_USER_PROMPT_TEMPLATE = """## 泰拉纪年年表

以下是《大地巡旅》附录中的泰拉纪年全文:

{timeline_text}

## 输出要求

请提取年表中所有历史事件，输出 JSON:

{output_schema}

## 规则
- 必须基于提供的年表内容，不编造
- 每条事件独立提取，同一年多条事件分开记录
- 国家/阵营/地点名称使用游戏内常用中文名
- source 统一标记为 "timeline_appendix\""""


def build_timeline_system_prompt() -> str:
    return _TIMELINE_SYSTEM_PROMPT


def build_timeline_user_prompt(timeline_text: str) -> str:
    return _TIMELINE_USER_PROMPT_TEMPLATE.format(
        timeline_text=timeline_text,
        output_schema=_OUTPUT_SCHEMA,
    )


def build_seed_context(seed_db: dict) -> str:
    """将种子库转为视频 prompt 中的已知实体列表"""
    concepts = seed_db.get("concepts", [])
    factions = seed_db.get("factions", [])
    locations = seed_db.get("locations", [])

    parts = ["## 已知实体库 (来自《大地巡旅》设定集)"]
    parts.append("请优先丰富以下已有实体，只有确认是新实体时才创建新条目。\n")

    if concepts:
        parts.append(f"### 概念 ({len(concepts)} 个)")
        for c in concepts:
            parts.append(f"- {c['name']} [{c.get('category', '')}]: {c.get('definition', '')}")
        parts.append("")

    if factions:
        parts.append(f"### 阵营 ({len(factions)} 个)")
        for f in factions:
            parts.append(f"- {f['name']} [{f.get('category', '')}]: {f.get('definition', '')}")
        parts.append("")

    if locations:
        parts.append(f"### 地点 ({len(locations)} 个)")
        for l in locations:
            parts.append(f"- {l['name']} [{l.get('category', '')}]: {l.get('definition', '')}")
        parts.append("")

    return "\n".join(parts)


# ====================================================================
# Pass 3b: 概念专用提取 (不做 factions/locations, 专注概念完整性)
# ====================================================================

_CONCEPT_ONLY_SYSTEM_PROMPT = """你是一位《明日方舟》世界观设定档案编纂者。你的任务是从文本中提取世界观概念实体。

## 本次只提取概念 (concepts)

你已经不需要提取阵营和地点——它们已在之前的步骤中完成。本次只聚焦概念层。

### 概念六子类

- 自然现象/物质: 源石、天灾、活性源石、矿石病
- 种族/血脈: 萨卡兹、阿戈尔、库兰塔、提卡兹、黎博利、斐迪亚、瓦伊凡、鲁珀、菲林、佩洛...（注意捕捞出文中出现的所有具名种族，不要遗漏）
- 超自然存在: 巨兽、兽主、海嗣、邪魔、岁兽
- 技术/技艺体系: 源石技艺七学派、移动城市技术、炼金术
- 社会制度/文化: 拉特兰律法、骑士竞技、天灾信使制度
- 特殊地域/异域: 焚风热土、黑流树海、荒域、星荚

纳入标准: 属于六子类之一的客观世界实体。因为本次只有概念层，输出空间充足，请尽量全面的提取，不要因为篇幅限制而省略。
排除标准: 情感/品德/角色观点/模糊隐喻
不设频率门槛: 即使只在文中出现一次也要提取

## 输出格式

严格输出 JSON，不要包含 markdown 代码块标记。
JSON 字符串值内禁止使用英文双引号 "，用「」代替。"""

_CONCEPT_ONLY_OUTPUT_SCHEMA = """{
  "concepts": [
    {
      "name": "实体名称",
      "category": "六子类之一",
      "definition": "一句话定义(≤80字)",
      "summary": "精简概述(100-300字)",
      "aliases": ["别名"],
      "manifestation": "表现形态(仅自然现象/物质)",
      "origin_hypothesis": "起源假说(仅自然现象/物质)",
      "related_arts": "关联源石技艺(仅自然现象/物质)",
      "origin_region": "起源地(仅种族)",
      "physical_traits": "体貌特征(仅种族)",
      "related_races": ["亲缘种族(仅种族)"],
      "oripathy_susceptibility": "矿石病易感性(仅种族)",
      "lifespan": "寿命特征(仅种族)",
      "nature": "本质(仅超自然存在)",
      "scale": "位阶/规模(仅超自然存在)",
      "known_instances": ["已知个体(仅超自然存在)"],
      "relation_to_humanity": "与人类关系(仅超自然存在)",
      "underlying_principle": "底层原理(仅技术)",
      "practitioners": "使用群体(仅技术)",
      "spread": "传播范围(仅技术)",
      "key_applications": ["关键应用(仅技术)"],
      "origin_nation": "起源国家(仅社会制度)",
      "characteristics": "制度特点(仅社会制度)",
      "key_institutions": ["核心机构(仅社会制度)"],
      "social_impact": "社会影响(仅社会制度)",
      "location_type": "地域类型(仅特殊地域)",
      "accessibility": "进入方式(仅特殊地域)",
      "hazards": ["危险要素(仅特殊地域)"],
      "phenomena": ["独特现象(仅特殊地域)"],
      "source_records": [{"source": "terra_book或video", "source_detail": "...", "location": "...", "confidence": "confirmed或inferred"}],
      "story_events": [],
      "related_concepts": [{"name": "...", "relation": "...", "desc": "..."}]
    }
  ]
}"""

_CONCEPT_ONLY_USER_PROMPT_TEMPLATE = """## 设定集章节: {chapter_title}

以下是《大地巡旅》中"{chapter_title}"的完整文本:

{chapter_text}

## 输出要求

本次只提取概念 (concepts)，不提取 factions 和 locations。请完整提取本章中所有符合六子类标准的概念实体。

{output_schema}

## 规则
- 只输出 concepts 数组，不输出 factions 和 locations
- definition 一句话定义不超过 80 字
- summary 精简至 100-300 字
- 各类独有字段有信息就填，不要输出空字符串或空列表——没有就省略字段
- **不要输出空字符串 "" 或空列表 []，无信息直接省略该字段**
- 特别是对于仅适用特定子类的字段（如 manifestation 仅适用于自然现象/物质），不属于该子类的实体不要输出这些字段"""


def build_concept_only_system_prompt() -> str:
    return _CONCEPT_ONLY_SYSTEM_PROMPT


def build_concept_only_user_prompt(chapter_title: str, chapter_text: str) -> str:
    return _CONCEPT_ONLY_USER_PROMPT_TEMPLATE.format(
        chapter_title=chapter_title,
        chapter_text=chapter_text,
        output_schema=_CONCEPT_ONLY_OUTPUT_SCHEMA,
    )


# ============================================================
# Phase 3: 剧情实体链接 — 用故事文本丰富已有实体库
# ============================================================

_PHASE3_SYSTEM_PROMPT = """你是一位《明日方舟》世界观档案编纂者。你的任务是将剧情章节中的事件与已知世界观实体关联起来，并发现新实体。

## 任务

给定一个已知实体清单和一段剧情文本，你需要:

### 1. 实体-事件链接
对于清单中在剧情里出现的实体，记录其参与的剧情事件。
事件按重要程度分为三级:

**revelation (核心揭示)** — 对该实体的本质、起源、运作机制或历史真相进行了颠覆性或深层揭示:
- 判定标准: 包含「不是/其实是/本质是/原来是/真相是/假的/伪造的/从来就」等揭示性表述，或角色首次获知某个世界观秘密
- 描述要求: 80-150字，必须包含:
  (a) 谁在什么情境下揭示/发现了什么
  (b) 直接引用原文关键句（用「」标注，注明说话者）
  (c) 这个揭示对理解该实体意味着什么（改变了什么认知）
- 格式示例: 「克里斯滕在万星园突破星荚后对塞雷娅说:『外面不是星空，是假的』，揭示星荚之外并非真实宇宙。这意味着泰拉天空的阻隔层不是物理屏障，而是一种伪装——天空本身就是被制造出来的。」

**major (重要事件)** — 实体是事件核心参与者或主题，但非揭示性:
- 描述: 30-80字，说明发生了什么+实体如何参与

**minor (背景提及)** — 实体作为背景、类比或间接提及:
- 描述: 20-50字，简洁记录

### 2. 新实体发现
如果剧情中出现了清单中没有的重要世界观实体，创建新条目。
新实体的 category 必须是以下合法值，不能自创分类:
- 概念: 自然现象/物质 | 种族/血脉 | 超自然存在 | 技术/技艺体系 | 社会制度/文化 | 特殊地域/异域
- 阵营: nation | organization
- 地点: city | facility

### 3. 角色型世界观实体的识别（重要）

以下三类"角色"本身就是世界观实体，必须提取，不可当作普通角色忽略:

**A. 超自然存在的个体化身**
- 判别: 巨兽化身、岁兽碎片、兽主个体、海神/海嗣核心个体
- 处理: 创建 concept (超自然存在)，标注其所属的超自然实体，记录其独立意志和能力
- 示例: 颉(岁兽第三碎片)、重岳(岁兽碎片/巨兽化身)、多利(兽主)、Ishar-mla(海神)
- 关键信号: 对话中讨论其"本质""化身""碎片""觉醒"等，说明它不仅是角色也是世界规则的一部分

**B. 制度性职位的代表人物**
- 判别: 天师、太傅/太师/太尉、宗师、司岁官、秉烛人、禁军统领 等
- 处理: 为所述制度/机构创建或更新 concept (社会制度/文化)，记录该角色的言行揭示的制度信息
- 关键信号: 其言行不是在推进个人剧情，而是在揭示制度运作规则、历史决策、内部矛盾

**C. 历史关键人物**
- 判别: 已故或不在场，但其过往行动构成了当前世界观的关键背景
- 处理: 创建 concept (社会制度/文化)，记录其历史定位和影响
- 示例: 魏彦武(太师案核心人物)、老天师(炎国天师制度的代表人物)
- 关键信号: 多个角色反复提及该人物的过往行动，且该行动与当前世界局势直接相关

## 重要规则
- 普通故事角色（如阿米娅、凯尔希、博士、普通干员）不是世界观实体，不要提取
- 但如果一个"角色"符合上述 A/B/C 任一条，它就是世界观实体，必须提取
- 制度性职位（如「天师」「太傅」「宗师」「司岁官」）本身作为概念提取，其代表人物**必须同时记录到对应的 faction member_composition**。例如: 文中出现"老天师""麟青砚""白定山"等天师个体时，天机阁/天师府的 members 字段必须包含他们
- 只记录与世界观设定相关的事件。以下情况**不单独记录**:
  * 常规战斗中实体作为武器/工具被使用（如"XX用源石技艺攻击"）——Pass 1 已覆盖
  * 纯角色互动不涉及世界观信息
  * 仅在对话中作为口头禅或类比出现，没有实质信息
- 但战斗过程中如果**揭示了实体的新能力/新限制/新本质**，仍需记录
- 先仔细检查已知实体清单，确认实体不在清单中才创建新条目
- 如果剧情没有提及某个实体，不要输出空记录或占位事件
- 不要创建与已知实体清单中已有实体同名的重复条目
- 揭示型事件 (revelation) 是最高优先级——宁可多记一个 revelation，不可遗漏

### 4. 关键对话场景的识别与深层提取（重要）

常规战斗/行动场景中实体作为背景或工具出现，已有 Pass 1 覆盖。你的独特价值是识别**关键对话场景**——两个以上有名有姓的角色在特定场所长时间对话，通过回忆、对质、和解等方式揭示世界观深层信息。

**判别标准**（满足 2 条以上即视为关键对话场景）:
- 对话超过 10 轮交替发言，且发言者均为有名有姓的角色
- 对话发生在有明确名称的非战斗场所（如天镜阁、驿馆、大殿、密室）
- 对话内容涉及: 历史事件的真相还原 / 身份揭示 / 制度内幕 / 已故人物追忆 / 兄弟/姐妹/师徒等深层关系的和解或清算
- 对话中出现「放下」「原谅」「恨」「太重」「太迟」「已经XX年了」等情感回溯信号词

**处理要求**（此类场景的事件享有最高输出优先级）:
- 为该场景创建至少 1 条 revelation 事件，描述覆盖:
  (a) 对话发生的场所和情境（谁来找谁、为什么此时见面）
  (b) 对话中揭示的核心历史真相（不是"回顾了恩怨"，而是具体回顾了什么）
  (c) 至少引用 3 处原文关键句，标注说话者
  (d) 对话达成的结果或留下的未解问题
- 对场景中揭示的人物身份关联（如"他是他弟弟""她改名换姓""他替他赴死"），同时为涉及的实体补充 identity 类 revelation
- 描述字数: 120-200字（关键对话场景不受常规字数限制）

**示例**: 辞岁行末尾炎武与真龙炎礼在天镜阁的重逢对话。不应压缩为「炎武与真龙回顾四十年恩怨」，而应记录: 天镜阁藏四千三百万卷书、真龙曾想在此终老、胞妹炎景公主在去龙门路上拦截炎武、炎武说「唯独是你......不曾于大炎有愧」、炎礼是弟弟等具体信息。

## 输出格式
严格输出 JSON，不要包含 ```json 等 markdown 标记。JSON 字符串值内禁止使用英文双引号 "，用「」代替。"""


_PHASE3_USER_PROMPT_TEMPLATE = """## 已知实体清单

以下是已从设定集和视频中提取的世界观实体。请检查哪些实体在本章剧情中出现。

{entity_checklist}

## 剧情章节: {chapter_name}

{chapter_text}

## 输出要求

请输出此段剧情中出现的已知实体的事件记录，以及发现的新实体:

{output_schema}

## 规则
- 只输出在剧情中出现的实体，不输出未出现的
- story_events 按 significance 分三级: revelation > major > minor，描述要求见 system prompt
- 对 faction 实体，输出 members 字段记录本章出场的组织成员
- 新实体使用完整格式（含 category/definition/summary 及子类字段）
- 重要角色名(阿米娅/凯尔希/博士等)不是世界观实体，但巨兽/兽主/海嗣等超自然存在是世界观实体
- definition 一句话定义不超过 80 字"""


_PHASE3_OUTPUT_SCHEMA = """{
  "entity_mentions": [
    {
      "entity_name": "已知实体名",
      "entity_type": "concept/faction/location",
      "story_events": [
        {
          "name": "事件名",
          "description": "描述（revelation: 80-150字含原文引用+意义解读; major: 30-80字; minor: 20-50字）",
          "significance": "revelation/major/minor",
          "quote": "原文关键句（仅 revelation 必填，用「」标注，注明说话者，如: 克里斯滕:『外面不是星空』）",
          "implication": "这个揭示意味着什么（仅 revelation 必填，20-50字）",
          "line_range": [起始行号, 结束行号]
        }
      ],
      "members": [
        {
          "name": "角色名",
          "role": "在组织中的职位/身份",
          "chapter_role": "本章中的关键表现（1-2句话）"
        }
      ]
    }
  ],
  "new_entities": {
    "concepts": [
      {
        "name": "新概念名",
        "category": "六子类之一",
        "definition": "一句话定义(≤80字)",
        "summary": "描述(≤200字)",
        "source_records": [{"source": "story_text", "source_detail": "章节名", "confidence": "confirmed"}],
        "story_events": []
      }
    ],
    "factions": [
      {
        "name": "新阵营名",
        "category": "nation/organization",
        "definition": "一句话定义(≤80字)",
        "summary": "描述(≤200字)",
        "source_records": [{"source": "story_text", "source_detail": "章节名", "confidence": "confirmed"}],
        "story_events": [],
        "members": []
      }
    ],
    "locations": [
      {
        "name": "新地点名",
        "category": "city/facility",
        "definition": "一句话定义(≤80字)",
        "summary": "描述(≤200字)",
        "source_records": [{"source": "story_text", "source_detail": "章节名", "confidence": "confirmed"}],
        "story_events": []
      }
    ]
  }
}"""


def _entity_in_text(entity: dict, text: str) -> bool:
    """检查实体名或其任何别名是否在文本中出现"""
    names = [entity.get("name", "")]
    names.extend(entity.get("aliases", []))
    for name in names:
        if name and len(name) >= 2 and name in text:
            return True
    return False


def build_entity_checklist(seed_db: dict, filter_text: str = None) -> str:
    """将种子库编译为实体清单文本，供 LLM 做实体链接用

    Args:
        seed_db: 种子库 dict
        filter_text: 如果提供，只包含在文本中出现的实体（缩减 token 预算）
    """
    parts = []

    all_concepts = seed_db.get("concepts", [])
    all_factions = seed_db.get("factions", [])
    all_locations = seed_db.get("locations", [])

    if filter_text:
        concepts = [c for c in all_concepts if _entity_in_text(c, filter_text)]
        factions = [f for f in all_factions if _entity_in_text(f, filter_text)]
        locations = [l for l in all_locations if _entity_in_text(l, filter_text)]
        # 确保至少保留 10 个概念/5 个阵营作锚点，避免空清单
        if len(concepts) < 10:
            concepts = all_concepts[:10]
        if len(factions) < 5:
            factions = all_factions[:5]
        if len(locations) < 2:
            locations = all_locations[:2]
    else:
        concepts = all_concepts
        factions = all_factions
        locations = all_locations

    if concepts:
        parts.append(f"### 概念 ({len(concepts)} 个)")
        for c in concepts:
            cat = c.get("category", "")
            definition = c.get("definition", "")
            line = f"- 【{c['name']}】[{cat}] {definition}"
            ki = c.get("known_instances", [])
            if ki:
                line += f" | 已知实例: {', '.join(ki[:4])}"
            aliases = c.get("aliases", [])
            if aliases:
                line += f" | 又名: {', '.join(aliases[:5])}"
            parts.append(line)
        parts.append("")

    if factions:
        parts.append(f"### 阵营 ({len(factions)} 个)")
        for f in factions:
            cat = f.get("category", "")
            definition = f.get("definition", "")
            line = f"- 【{f['name']}】[{cat}] {definition}"
            aliases = f.get("aliases", [])
            if aliases:
                line += f" | 又名: {', '.join(aliases[:5])}"
            parts.append(line)
        parts.append("")

    if locations:
        parts.append(f"### 地点 ({len(locations)} 个)")
        for loc in locations:
            cat = loc.get("category", "")
            definition = loc.get("definition", "")
            line = f"- 【{loc['name']}】[{cat}] {definition}"
            aliases = loc.get("aliases", [])
            if aliases:
                line += f" | 又名: {', '.join(aliases[:5])}"
            parts.append(line)
        parts.append("")

    return "\n".join(parts)


def build_phase3_system_prompt() -> str:
    return _PHASE3_SYSTEM_PROMPT


def build_phase3_user_prompt(
    chapter_name: str,
    chapter_text: str,
    seed_db: dict,
) -> str:
    entity_checklist = build_entity_checklist(seed_db, filter_text=chapter_text)
    return _PHASE3_USER_PROMPT_TEMPLATE.format(
        entity_checklist=entity_checklist,
        chapter_name=chapter_name,
        chapter_text=chapter_text,
        output_schema=_PHASE3_OUTPUT_SCHEMA,
    )
