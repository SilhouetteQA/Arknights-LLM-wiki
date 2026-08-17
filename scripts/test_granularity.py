"""事件提取颗粒度对比测试：不限制 vs 限制20 vs 自定"""
import json, os, sys, time
sys.stdout.reconfigure(encoding='utf-8')

from openai import OpenAI

DS_KEY = os.environ.get("deepseek_api", "")
client = OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com/v1")

# 加载同一批测试数据
with open("output/_test_beacon_dialogue.txt", encoding='utf-8') as f:
    full_text = f.read()
BATCH_CHARS = 37000
test_text = full_text[:BATCH_CHARS]
last_newline = test_text.rfind('\n')
test_text = test_text[:last_newline]

SYSTEM = "你是一个《明日方舟》剧情深度分析师。通读对话后提取结构化信息。严格按 JSON 输出，不需要 markdown 代码块。"

# 三个版本的 prompt —— 只改事件提取指令
PROMPTS = {
    "自由提取": """
以下是「慈悲灯塔」章节的部分对话。提取所有你能识别到的关键事件，数量不限，只提取真正存在的事件。

## 事件提取标准
一个"事件"的定义：
- 一次具体的行动或决策（战斗、撤退、结盟、背叛、牺牲、揭示等）
- 涉及明确的角色和后果
- 不是对白的简单转述，而是"发生了什么"

格式：{{"key_events": [{{"event": "...", "type": "battle/revelation/confrontation/negotiation/rescue/departure/sacrifice/meeting/emotional_breakthrough/other", "participants": [...], "location": "...", "significance": "..."}}]}}

## 对话
{text}

只输出 JSON 对象，key_events 数量不限。
""",

    "限制20个": """
以下是「慈悲灯塔」章节的部分对话。提取 20 个关键事件，严格 20 个，不多不少。

## 事件提取标准
一个"事件"的定义：
- 一次具体的行动或决策（战斗、撤退、结盟、背叛、牺牲、揭示等）
- 涉及明确的角色和后果

格式：{{"key_events": [{{"event": "...", "type": "...", "participants": [...], "location": "...", "significance": "..."}}]}}

## 对话
{text}

只输出 JSON 对象，key_events 必须恰好 20 个。
""",

    "尽量多提取": """
以下是「慈悲灯塔」章节的部分对话。尽可能多地提取事件，目标至少 30 个。

## 事件提取标准
把剧情拆细：每一条独立的战斗行动、战术决策、人物对峙、情感转折、信息揭示、牺牲行为都算一个事件。不要合并。

格式：{{"key_events": [{{"event": "...", "type": "...", "participants": [...], "location": "...", "significance": "..."}}]}}

## 对话
{text}

只输出 JSON 对象，尽可能多的事件。
""",
}

os.makedirs("output/extraction_tests", exist_ok=True)

for label, template in PROMPTS.items():
    print(f"=== {label} ===")
    prompt = template.format(text=test_text)

    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model="deepseek-4-flash",  # deepseek-chat 已下线（2026-08-17）
            messages=[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],
            temperature=0.1, max_tokens=8192
        )
        elapsed = time.time() - t0
        raw = resp.choices[0].message.content.strip()

        # Clean
        if raw.startswith("```"):
            idx = raw.find("\n")
            if idx > 0: raw = raw[idx+1:]
        if raw.endswith("```"): raw = raw[:-3]
        raw = raw.strip()

        parsed = json.loads(raw)
        events = parsed.get('key_events', [])
        print(f"  耗时: {elapsed:.1f}s | 提取事件数: {len(events)}")
        print(f"  Tokens: in={resp.usage.prompt_tokens:,} out={resp.usage.completion_tokens:,}")

        for i, e in enumerate(events[:5]):
            print(f"  {i+1}. [{e.get('type','?')}] {e.get('event','')[:80]}")
        if len(events) > 5:
            print(f"  ... 还有 {len(events)-5} 个")
        print()

        # Save
        safe = label.replace(" ", "_")
        with open(f"output/extraction_tests/granularity_{safe}.json", 'w', encoding='utf-8') as f:
            json.dump({"label": label, "events_count": len(events), "events": events,
                       "elapsed_s": elapsed, "tokens_in": resp.usage.prompt_tokens,
                       "tokens_out": resp.usage.completion_tokens}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  ERROR: {e}\n")
