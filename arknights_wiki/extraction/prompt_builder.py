"""组装 system prompt 和 user prompt"""

SYSTEM_PROMPT = """你是一个《明日方舟》剧情深度分析师。你的任务是通读章节对话，提取结构化信息。

对话按 **Scene（场景/节点）** 组织，每个 Scene 内的行号独立编号（从 [1] 开始）。Scene 之间是自然剧情断点。

严格遵守以下规则：

1. **输出格式**：严格输出 JSON，不要包含 ```json 等 markdown 标记。<EXTREMELY_IMPORTANT>JSON 字符串值内禁止使用英文双引号 \"，用「」代替。</EXTREMELY_IMPORTANT>

2. **事件提取**：以 Scene 为单位提取事件。一个 Scene 内可能有多个事件，也可能跨 Scene。line_range 使用 Scene 内行号，格式为 {"scene": N, "lines": [start, end]}。事件数量由内容密度决定，不凑数不遗漏。必须覆盖所有并行剧情线。

3. **角色提取**：提取有名字、有台词、有剧情作用的角色。无名泛型角色不提取。

4. **概念标注**：仅标注被角色**实质性讨论**的概念——必须在具体对话中解释/描述/辩论其本质/机制/历史。lines 范围精确到讨论该概念的具体对话行（通常 10-40 行），而不是整个 Scene。仅作为名词标签提及的不算概念。如同一概念在多处讨论，每个实质性讨论段落单独列一条。

5. **阵营/组织标注**：提取本章中出现的阵营、组织、势力（国家政权、政治实体、武装组织、骑士团/门派等）。每个 faction 标注本章中**实质性涉及**该阵营的对话段落——即角色讨论、描述、或与该阵营互动的具体对话。line_range 应覆盖该段讨论/互动的起止行（类似概念标注），不应只有一行。如同一阵营在多处被涉及，每个实质性段落单独列一条。仅作为名词标签一带而过的不要标注。

6. **地区/地点标注**：提取本章中出现的具名地区、城市、关键地点。每个 location 标注本章中**实质性描述或讨论**该地点的对话段落。line_range 应覆盖角色讨论/描述该地点的对话跨度。如同一地点在多处被讨论，每个实质性段落单独列一条。仅作为名词标签一带而过的不要标注。

7. **事件类型**：用 snake_case 英文自由描述。参考类型：battle, ambush, siege, retreat, infiltration, revelation, investigation, negotiation, alliance, betrayal, confrontation, sacrifice, rescue, departure, reunion, ceremony, emotional_breakthrough, flashback, disaster, planning, political_intrigue, assassination, rebellion, training, dream_vision, character_development, family_moment, ideological_clash, farewell, reflection。"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


OUTPUT_SCHEMA = """```json
{
  "summary": "按 Scene 顺序概述本章剧情，3-5段，覆盖所有主要剧情线",

  "events": [{
    "event": "事件描述（一句话）",
    "type": "snake_case 事件类型",
    "line_range": {"scene": 场景编号, "lines": [起始行号, 结束行号]},
    "participants": ["参与角色名"],
    "location": "发生地点（如能确定）",
    "significance": "剧情意义（一句话）"
  }],

  "characters": [{
    "name": "角色名（对话中的称呼）",
    "type": "operator|npc",
    "role_in_chapter": "本章中的角色和行动",
    "first_appearance_chapter": true
  }],

  "concepts": [{
    "concept": "概念名",
    "line_range": {"scene": 场景编号, "lines": [起始行号, 结束行号]},
    "discussion_summary": "该段对话中如何讨论此概念",
    "is_substantive": true
  }],

  "factions": [{
    "faction": "阵营/组织名",
    "line_range": {"scene": 场景编号, "lines": [起始行号, 结束行号]},
    "description": "该段对话中如何涉及此阵营"
  }],

  "locations": [{
    "location": "地区/地点名",
    "line_range": {"scene": 场景编号, "lines": [起始行号, 结束行号]},
    "description": "该段对话中如何涉及此地点"
  }]
}
```"""


def build_user_prompt(chapter: str, dialogue_text: str, total_lines: int,
                     scene_count: int = 0, context: str = "") -> str:
    """构建 user prompt。"""
    parts = [f"以下是「{chapter}」的对话文本。"]

    if scene_count > 0:
        parts.append(f"共 {scene_count} 个 Scene，{total_lines} 行对话。")
    else:
        parts.append(f"共 {total_lines} 行。")

    parts.append("每个 Scene 以 ## Scene N: name 开头，Scene 内行号独立编号 [1] [2] ...")
    parts.append("line_range 中的 scene 对应 Scene 编号 N。")
    parts.append("")

    if context:
        parts.append(context)

    parts.append("## 对话")
    parts.append(dialogue_text)
    parts.append("")
    parts.append("## 输出 JSON 格式")
    parts.append(OUTPUT_SCHEMA)
    parts.append("")
    parts.append("## 规则")
    parts.append("- 必须基于提供的对话内容，不编造")
    parts.append("- 泛型角色不提取为 characters")
    parts.append("- concepts / factions / locations 的 lines 范围精确到实质性讨论/涉及的具体对话行，不是整个 Scene 的范围，也不应只有一行")
    parts.append("- 同一实体在多处被讨论时，每个实质性段落单独列一条")
    parts.append("- 覆盖所有并行剧情线")
    parts.append("- Scene 编号从 Scene 标题中读取，如 ## Scene 1: xxx -> scene=1")

    return "\n".join(parts)
