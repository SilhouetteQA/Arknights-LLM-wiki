"""组装 system prompt 和 user prompt"""

SYSTEM_PROMPT_BASE = """你是一个《明日方舟》剧情深度分析师。你的任务是通读章节对话，提取结构化信息。

对话按 **Scene（场景/节点）** 组织，每个 Scene 内的行号独立编号（从 [1] 开始）。Scene 之间是自然剧情断点。

严格遵守以下规则：

1. **输出格式**：严格输出 JSON，不要包含 ```json 等 markdown 标记。<EXTREMELY_IMPORTANT>JSON 字符串值内禁止使用英文双引号 \"，用「」代替。</EXTREMELY_IMPORTANT>

2. **事件提取**：以 Scene 为单位提取事件。一个 Scene 内可能有多个事件，也可能跨 Scene。line_range 使用 Scene 内行号，格式为 {"scene": N, "lines": [start, end]}。事件数量由内容密度决定，不凑数不遗漏。必须覆盖所有并行剧情线。

3. **角色提取**：提取有名字、有台词、有剧情作用的角色。无名泛型角色不提取。

4. **概念标注**：仅标注被角色**实质性讨论**的概念——必须在具体对话中解释/描述/辩论其本质/机制/历史。lines 范围精确到讨论该概念的具体对话行（通常 10-40 行），而不是整个 Scene。仅作为名词标签提及的不算概念。如同一概念在多处讨论，每个实质性讨论段落单独列一条。

5. **阵营/组织标注**：提取本章中出现的阵营、组织、势力（国家政权、政治实体、武装组织、骑士团/门派等）。每个 faction 标注本章中**实质性涉及**该阵营的对话段落——即角色讨论、描述、或与该阵营互动的具体对话。line_range 应覆盖该段讨论/互动的起止行（类似概念标注），不应只有一行。如同一阵营在多处被涉及，每个实质性段落单独列一条。仅作为名词标签一带而过的不要标注。

6. **地区/地点标注**：提取本章中出现的具名地区、城市、关键地点。每个 location 标注本章中**实质性描述或讨论**该地点的对话段落。line_range 应覆盖角色讨论/描述该地点的对话跨度。如同一地点在多处被讨论，每个实质性段落单独列一条。仅作为名词标签一带而过的不要标注。

7. **事件类型**：用 snake_case 英文自由描述。参考类型：battle, ambush, siege, retreat, infiltration, revelation, investigation, negotiation, alliance, betrayal, confrontation, sacrifice, rescue, departure, reunion, ceremony, emotional_breakthrough, flashback, disaster, planning, political_intrigue, assassination, rebellion, training, dream_vision, character_development, family_moment, ideological_clash, farewell, reflection。"""

IS_PROMPT_APPENDIX = """

================================================================
## 重要：本章内容来源说明
================================================================

本章来自《集成战略》（Integrated Strategies）模式。其核心内容是**特定条件下产生的想象未来/IF线剧情**，不是明日方舟正史中实际发生的事件。

理解 IS 结局的性质：
- **第一结局（Ending 1）**：在合理条件下可能性最大的发展，可视为"最接近正史的可能性"
- **后续结局（Ending 2-5）**：基于越来越极端的假设条件产生的发散想象
- 所有结局都是"what-if"——它们展示的**不是**已经发生的事实，而是角色/世界在某些条件下的可能走向

================================================================
## 总结格式要求（IS 专用——严格遵守）
================================================================

**summary 必须按 Scene 和 PART 边界组织，不得将不同结局/不同PART的内容混在一起概述。**

格式：
```
本章为集成战略IF线剧情，非正史事件。

## 序章/框架对话
Scene N: [节点名] — [该场景的核心内容，1-2句]

## Ending 01：[结局标题]（一结局，可能性最大的发展）
Scene M: [结局名_ending] PART 1 — [该PART的核心事件和叙事要点，2-3句]
Scene M: [结局名_ending] PART 2 — [同上]
Scene M: [结局名_ending] PART 3 — [同上]
Scene M: [结局名_ending] PART 4 — [同上（如存在）]

## Ending 02：[结局标题]（后续结局，基于更极端假设）
...（每个结局一个独立章节，每个PART一段）
```

**关键约束：**
- 每个结局独立成节，不跨结局合并叙述
- 每个 PART 必须单独概述，不能跳过或用"后来/之后"等连词夹断
- 序章/框架对话（不含_ending 的 story node）作为第一个独立场景概述
- PART 标题从原文中的 `PART N ...` 标记读取
- 即使某个 PART 内容较长，也必须完整概述其核心叙事，不能中途截断

提取要求：
1. **世界观设定**：源石技艺机制、种族特性、地理环境、历史文化背景等——这些是有效的世界观补充信息，正常提取到 concepts / factions / locations
2. **高层战斗力描述**：角色在极端条件下的战力表现、能力边界、特殊形态——提取到 events 中，这是评估角色能力上限的重要参考
3. **角色关系与性格**：IF线中的角色互动可以反映角色性格的不同侧面，正常提取

**关键规则——绝对不能违反：**
- 所有 IS 章节中的 events（含序章框架对话和结局文本），必须标记 `"is_imaginary": true`
- 在 summary 中开篇即说明"本章为集成战略IF线剧情，非正史事件"
- 提取 concepts / factions / locations 时，如果内容仅存在于IF线设定中（非主线已有的世界观），需在 discussion_summary / description 中注明"IS-IF设定"
- **决不能将IS事件与主线/支线的实际发生事件混淆**——这些事件没有在明日方舟主时间线中发生"""


def build_system_prompt(chapter_type: str = "full") -> str:
    if chapter_type == "is":
        return SYSTEM_PROMPT_BASE + IS_PROMPT_APPENDIX
    return SYSTEM_PROMPT_BASE


OUTPUT_SCHEMA = """```json
{
  "summary": "按 Scene 顺序概述本章剧情，3-5段，覆盖所有主要剧情线",

  "events": [{
    "event": "事件描述（一句话）",
    "type": "snake_case 事件类型",
    "line_range": {"scene": 场景编号, "lines": [起始行号, 结束行号]},
    "participants": ["参与角色名"],
    "location": "发生地点（如能确定）",
    "significance": "剧情意义（一句话）",
    "is_imaginary": false
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
                     scene_count: int = 0, context: str = "",
                     chapter_type: str = "full") -> str:
    """构建 user prompt。chapter_type 为 full/is/ra/light/skip"""
    parts = [f"以下是「{chapter}」的对话文本。"]

    if chapter_type == "is":
        parts.append("")
        parts.append("**来源类型：集成战略（IS）IF线剧情**")
        parts.append("本章结构：前几个 Scene 是序章/框架对话（story node），后续 Scene 是各结局的完整叙事文本（_ending.json）。")
        parts.append("每个 _ending 文件内按 `PART 1/2/3/4` 分节，每节是一个完整的叙事片段。")
        parts.append("每个结局是**独立的平行IF线**，彼此不连续——不要将一个结局的事件当作另一个结局的前置剧情。")
        parts.append("提取世界观设定、战力描述、角色关系，所有事件（含序章框架对话）标记 is_imaginary=true。")
        parts.append("summary 必须按「序章 → Ending 01 PART 1~4 → Ending 02 PART 1~4 → ...」的层级结构组织，每个 PART 单独概述。")

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
    if chapter_type == "is":
        parts.append("- IS 章节：summary 按「序章 Scene → 每个结局的 Scene（含 PART 1~4 分节）」的层级结构组织，每个结局独立成节、每个 PART 单独概述、不得跨结局合并叙述、不得中途夹断PART的叙事")

    return "\n".join(parts)
