"""Pass 3 世界观实体提取提示词"""


_BOOK_SYSTEM_PROMPT = """你是一位《明日方舟》世界观设定档案编纂者。你的任务是从设定集《大地巡旅》的章节中提取结构化世界观实体。

## 提取三类实体

### 1. 概念 (concepts)
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

### 2. 阵营 (factions)
有组织的行动者，分为两类:
- nation (国家/政权): 维多利亚、乌萨斯、炎、拉特兰、卡兹戴尔...
- organization (势力/组织): 莱茵生命、整合运动、罗德岛、黑钢国际...

### 3. 地点 (locations)
具体物理场所，分为两类:
- city (城市/移动城市): 龙门、汐斯塔、切尔诺伯格...
- facility (设施/建筑): 罗德岛本舰、莱茵生命总部、移动城市核心城...

注意: 特殊地貌/异域归入概念层的"特殊地域/异域"子类，不在地点层。

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
- 概念 summary 不超过 500 字，阵营不超过 400 字，地点不超过 300 字
- 各类独有字段有信息就填，没有可省略"""


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
  "concepts": [
    {
      "name": "实体名称",
      "category": "六子类之一",
      "definition": "一句话定义(≤80字)",
      "summary": "综合描述(≤500字)",
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
