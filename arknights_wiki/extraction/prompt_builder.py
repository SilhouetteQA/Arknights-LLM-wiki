"""组装 system prompt 和 user prompt"""

SYSTEM_PROMPT = """你是一个《明日方舟》剧情深度分析师。你的任务是通读完整章节的对话，提取结构化信息。

严格遵守以下规则：

1. **输出格式**：严格输出 JSON，不要包含 `json` 等 markdown 代码块标记。<EXTREMELY_IMPORTANT>JSON 字符串值内禁止使用英文双引号 \"，需要引用或强调时用「」书名号代替。例如 "他说「走吧」" 而不是 "他说\"走吧\""。</EXTREMELY_IMPORTANT>
2. **事件提取**：提取本章所有关键事件，数量随内容密度浮动——战斗密集的章节自然事件多，对话为主的章节自然事件少。不凑数不遗漏。每个事件的 type 用 snake_case 英文自由描述，如 battle, political_intrigue, sacrifice, revelation 等。参考类型：battle, ambush, siege, retreat, infiltration, revelation, investigation, negotiation, alliance, betrayal, confrontation, sacrifice, rescue, departure, reunion, ceremony, emotional_breakthrough, flashback, disaster, planning, political_intrigue, assassination, rebellion, training, dream_vision。
3. **角色提取**：提取有名字、有台词、有剧情作用的角色。泛型角色不提取——"整合运动成员"、"罗德岛干员"、"某个士兵"、"路过的居民"等无名群体不列为 characters。operator 类角色使用规范名。
4. **概念标注**：只标注被角色"实质性讨论"的概念——角色在解释、描述、辩论某个世界观要素的本质/机制/历史时才算讨论。仅作为名词标签提及不算。
   - 标注示例："食腐者是萨卡兹中最古老的分支之一，他们的身体能吸收源石能量"——在讨论食腐者的本质
   - 不标注示例："前方发现食腐者小队！准备迎战。"——只是提到名字作为敌人标识
5. **行号范围**：line_range 对应对话的行号（从 1 开始），必须精确指向相关对话段落。"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT


OUTPUT_SCHEMA = """```json
{
  "chapter": "章节名",
  "category": "main|side|special",
  "summary": "3-5段章节摘要，按时间顺序，覆盖主要剧情推进",

  "events": [{
    "event": "事件描述（一句话）",
    "type": "snake_case 事件类型",
    "line_range": [起始行号, 结束行号],
    "participants": ["参与角色名"],
    "location": "发生地点（如能确定）",
    "significance": "剧情意义（一句话）"
  }],

  "characters": [{
    "name": "角色名（尽可能用规范名）",
    "type": "operator|npc",
    "role_in_chapter": "本章中的角色和行动",
    "first_appearance_chapter": true
  }],

  "concepts": [{
    "concept": "概念名",
    "line_range": [起始行号, 结束行号],
    "discussion_summary": "本章中如何被讨论（仅记录被实质性讨论的概念）",
    "is_substantive": true
  }]
}
```"""


def build_user_prompt(chapter: str, dialogue_text: str, total_lines: int) -> str:
    return f"""以下是「{chapter}」章节的完整对话。共 {total_lines} 行。

## 对话
{dialogue_text}

## 输出 JSON 格式
{OUTPUT_SCHEMA}

## 规则
- 必须基于提供的对话内容，不要编造
- 泛型角色（整合运动成员、罗德岛干员、士兵、居民、路人等）不提取为 characters
- concepts 只记录被实质性讨论的概念（解释/描述/辩论其本质），不是关键词匹配
- 事件类型用 snake_case 英文描述，覆盖剧情中各种可能的场景
- line_range 对应上述对话文本的行号（从第 1 行开始计数）"""
