"""M1 提取质量测试 — 慈悲灯塔章节，多模型对比"""
import json, os, sys, time

sys.stdout.reconfigure(encoding='utf-8')

from openai import OpenAI

# ─── 模型列表 ───
DS_KEY = os.environ.get("deepseek_api", "")
MM_KEY = os.environ.get("minimax_api", "")

MODELS = [
    {
        "name": "deepseek-v4-flash (非思考)",
        "client": OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com/v1"),
        "model": "deepseek-4-flash",  # deepseek-chat 已下线（2026-08-17）
        "extra_body": {},
    },
    {
        "name": "deepseek-v4-flash (思考)",
        "client": OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com/v1"),
        "model": "deepseek-reasoner",
        "extra_body": {},
    },
    {
        "name": "MiniMax M2.5",
        "client": OpenAI(api_key=MM_KEY, base_url="https://api.minimaxi.com/v1"),
        "model": "MiniMax-M2.5",
        "extra_body": {},
    },
    {
        "name": "MiniMax M2.7",
        "client": OpenAI(api_key=MM_KEY, base_url="https://api.minimaxi.com/v1"),
        "model": "MiniMax-M2.7",
        "extra_body": {},
    },
    {
        "name": "MiniMax M3",
        "client": OpenAI(api_key=MM_KEY, base_url="https://api.minimaxi.com/v1"),
        "model": "MiniMax-M3",
        "extra_body": {},
    },
]

# ─── 加载测试数据 ───
dialogue_path = "output/_test_beacon_dialogue.txt"
if not os.path.exists(dialogue_path):
    print("ERROR: 先运行聚合脚本生成 output/_test_beacon_dialogue.txt")
    sys.exit(1)

with open(dialogue_path, encoding='utf-8') as f:
    full_text = f.read()

# 取前 ~25K tokens (约 37K 汉字) 作为测试批次
# 这个大小让所有模型都能处理
BATCH_CHARS = 37000
test_text = full_text[:BATCH_CHARS]
# 在最后一个完整行处截断
last_newline = test_text.rfind('\n')
test_text = test_text[:last_newline]

line_count = test_text.count('\n') + 1
print(f"测试数据: {len(test_text):,} 字, ~{len(test_text)//1.5:,} tokens, {line_count} 行")
print()

# ─── 简化版 extraction schema (从架构v2来，只关注核心) ───
SYSTEM_PROMPT = """你是一个《明日方舟》剧情深度分析师。你的任务是通读章节对话，提取结构化信息。

严格按 JSON 格式输出，不要包含 markdown 代码块标记。"""

USER_PROMPT_TEMPLATE = """以下是「慈悲灯塔」章节的部分对话。请提取以下结构化信息。

## 对话
{text}

## 输出 JSON 格式
{{
  "summary": "本批次的剧情摘要（200-400字，按时间顺序）",
  "characters": [
    {{
      "name": "角色名（用规范名，不要用别名）",
      "type": "operator/npc",
      "role_in_scene": "在本批次中的角色和行动",
      "first_appearance": true/false
    }}
  ],
  "key_events": [
    {{
      "event": "事件描述",
      "type": "battle/revelation/confrontation/negotiation/rescue/departure/sacrifice/meeting/emotional_breakthrough/other",
      "participants": ["角色名"],
      "location": "地点",
      "significance": "为什么这个事件重要"
    }}
  ],
  "factions_involved": [
    {{
      "faction": "阵营名",
      "role": "在本批次中的作用"
    }}
  ],
  "locations_referenced": [
    {{
      "location": "地点名",
      "context": "在本批次中的上下文"
    }}
  ],
  "concepts_discussed": [
    {{
      "concept": "概念名",
      "context": "在本批次中如何被讨论（仅记录被实质性讨论的概念，不是提到一个词就算）"
    }}
  ]
}}

## 规则
- 必须基于提供的对话内容，不要编造
- 泛型角色（整合运动成员、罗德岛干员、士兵等）不提取为 characters
- concepts_discussed 只记录被实质性讨论的概念（如角色讨论了矿石病的本质），不是关键词匹配
- 只用给定的 event type 枚举值，不要发明新类型
"""

# ─── 执行测试 ───
output_dir = "output/extraction_tests"
os.makedirs(output_dir, exist_ok=True)

results = []

for m in MODELS:
    name = m["name"]
    print(f"=== 测试: {name} ===")

    prompt = USER_PROMPT_TEMPLATE.format(text=test_text)

    t0 = time.time()
    try:
        response = m["client"].chat.completions.create(
            model=m["model"],
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=8192,
            extra_body=m["extra_body"],
        )
        elapsed = time.time() - t0

        raw = response.choices[0].message.content
        usage = response.usage

        # 解析
        json_str = raw.strip()
        if json_str.startswith("```"):
            idx = json_str.find("\n")
            if idx > 0:
                json_str = json_str[idx+1:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        json_str = json_str.strip()

        try:
            parsed = json.loads(json_str)
            parse_ok = True
        except json.JSONDecodeError:
            parsed = {"_raw": raw, "_parse_error": "JSON decode failed"}
            parse_ok = False

        result = {
            "model": name,
            "parse_ok": parse_ok,
            "elapsed_s": elapsed,
            "tokens_in": usage.prompt_tokens if usage else 0,
            "tokens_out": usage.completion_tokens if usage else 0,
            "output": parsed,
        }

        # 统计
        chars_count = sum(len(c["name"]) for c in parsed.get("characters", [])) if isinstance(parsed, dict) and "characters" in parsed else 0
        events_count = len(parsed.get("key_events", [])) if isinstance(parsed, dict) else 0
        concepts_count = len(parsed.get("concepts_discussed", [])) if isinstance(parsed, dict) else 0

        print(f"  Parse: {'OK' if parse_ok else 'FAIL'}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  Tokens: in={result['tokens_in']:,} out={result['tokens_out']:,}")
        print(f"  角色: {len(parsed.get('characters', []))} | 事件: {events_count} | 阵营: {len(parsed.get('factions_involved', []))} | 地点: {len(parsed.get('locations_referenced', []))} | 概念: {concepts_count}")

        if parse_ok and events_count > 0:
            print(f"  事件类型: {[e.get('type','?') for e in parsed['key_events'][:5]]}")

    except Exception as e:
        elapsed = time.time() - t0
        result = {"model": name, "parse_ok": False, "elapsed_s": elapsed, "error": str(e)}
        print(f"  ERROR: {e}")

    results.append(result)

    # 保存原始输出
    safe_name = name.replace(" ", "_").replace("(", "").replace(")", "")
    with open(f"{output_dir}/{safe_name}.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print()

# ─── 汇总 ───
print("=" * 60)
print("汇总:")
print(f"{'模型':<35} {'解析':<6} {'耗时':<8} {'in tok':<10} {'out tok':<10} {'角色':<5} {'事件':<5} {'概念':<5}")
print("-" * 85)
for r in results:
    name = r["model"][:33]
    ok = "OK" if r.get("parse_ok") else "FAIL"
    elapsed = f"{r['elapsed_s']:.1f}s"
    tin = f"{r.get('tokens_in', 0):,}"
    tout = f"{r.get('tokens_out', 0):,}"
    chars = str(len(r.get("output", {}).get("characters", []))) if r.get("parse_ok") else "-"
    events = str(len(r.get("output", {}).get("key_events", []))) if r.get("parse_ok") else "-"
    concepts = str(len(r.get("output", {}).get("concepts_discussed", []))) if r.get("parse_ok") else "-"
    if r.get("error"):
        print(f"{name:<35} {ok:<6} {elapsed:<8} {'N/A':<10} {'N/A':<10} ERROR: {r['error'][:50]}")
    else:
        print(f"{name:<35} {ok:<6} {elapsed:<8} {tin:<10} {tout:<10} {chars:<5} {events:<5} {concepts:<5}")

print(f"\n详细结果: {output_dir}/")
