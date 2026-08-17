#!/usr/bin/env python
"""事件类题目重构生成器：按游戏内题材（主线三大篇章 / 地区变革 / 世界观大事件）生成

背景：现有 event 类 18 题 100% 来自书籍编年史时间线（event.json），用户要求改为
游戏内剧情题材——主线（切尔诺伯格0-8/维多利亚9-14/乌萨斯15-17）、地区变革
（炎国岁兽/卡西米尔骑士/叙拉古家族）、世界观大事件。

复用 generate_benchmark_questions.py 的材料加载/校验/元评估，题材约束 + 跨章综合引导。

用法：
  python scripts/generate_event_questions.py --dry-run
  python scripts/generate_event_questions.py --topic all --workers 4
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 复用 generate_benchmark_questions 的核心函数（材料加载/章节校验/kb校验/元评估/成本）
_spec = importlib.util.spec_from_file_location("gbq", ROOT / "scripts" / "generate_benchmark_questions.py")
gbq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gbq)

MATERIALS = ROOT / "benchmarks" / "arknights_bench" / "materials" / "event_chapters.json"
OUT_PATH = ROOT / "benchmarks" / "arknights_bench" / "questions_draft_event_new.jsonl"

# 题材 → 活动清单（event_chapters.json 的 meta['章节或活动']）
TOPICS = {
    "主线-切尔诺伯格0-8": ["黑暗时代·上", "黑暗时代·下", "异卵同生", "二次呼吸", "急性衰竭", "靶向药物", "局部坏死", "苦难摇篮", "怒号光明"],
    "主线-维多利亚9-14": ["风暴瞭望", "破碎日冕", "淬火尘霾", "惊霆无声", "恶兆湍流", "慈悲灯塔", "离解复合"],
    "主线-乌萨斯15-17": ["反常光谱", "相变临界"],
    "地区-炎国岁兽": ["画中人", "将进酒", "登临意", "怀黍离", "相见欢"],
    "地区-卡西米尔骑士": ["玛莉娅·临光", "长夜临光", "日暮寻路"],
    "地区-叙拉古家族": ["叙拉古人", "崔林特尔梅之金"],
    "世界观大事件": ["孤星", "愚人号", "巴别塔", "空想花庭", "尘影余音", "风雪过境", "生于黑夜"],
}

# 题量（用户：主线为主）：主10 + 地区6 + 世界观4 = 20
TARGET = {
    "主线-切尔诺伯格0-8": 4, "主线-维多利亚9-14": 4, "主线-乌萨斯15-17": 2,
    "地区-炎国岁兽": 2, "地区-卡西米尔骑士": 2, "地区-叙拉古家族": 2,
    "世界观大事件": 4,
}

# 每个题材默认 complex 占比（主线大事记/地区演变 → 多 complex 跨章综合；simple 给单点事实）
COMPLEX_RATIO = 0.55


def load_topic_materials(topic: str) -> list[dict]:
    """从 event_chapters.json 选出该题材的活动材料"""
    data = json.loads(MATERIALS.read_text(encoding="utf-8"))
    acts = TOPICS[topic]
    selected = []
    for it in data["items"]:
        act = it["meta"].get("章节或活动", "")
        for a in acts:
            if a in act:
                selected.append(it)
                break
    # 去重（同一活动可能多条）
    seen = set()
    uniq = []
    for it in selected:
        src = it.get("source_file", "")
        if src not in seen:
            seen.add(src)
            uniq.append(it)
    return uniq


def topic_desc(topic: str) -> str:
    desc = {
        "主线-切尔诺伯格0-8": "明日方舟主线第一章程「切尔诺伯格事件」（游戏 0-8 章）：博士苏醒、整合运动、龙门合作、塔露拉与核心城危机、怒号光明终局",
        "主线-维多利亚9-14": "明日方舟主线第二篇章「维多利亚事件」（游戏 9-14 章）：维多利亚内乱、萨卡兹占领、伦蒂尼姆、特蕾西娅与魔王、慈悲灯塔与离解复合",
        "主线-乌萨斯15-17": "明日方舟主线最新篇章「乌萨斯事件」（游戏 15-17 章）：乌萨斯内部、第一集团军阴谋、凯尔希复生、相变临界",
        "地区-炎国岁兽": "炎国岁兽相关大事件：画中人、将进酒、登临意、怀黍离、相见欢——岁兽碎片的恩怨与炎国政局",
        "地区-卡西米尔骑士": "卡西米尔骑士竞技制度：玛莉娅·临光、长夜临光、日暮寻路——骑士制度的商业化与耀骑士的回归",
        "地区-叙拉古家族": "叙拉古与家族变革：叙拉古人、崔林特尔梅之金——西西里夫人与家族斗争、德克萨斯返乡",
        "世界观大事件": "与明日方舟世界观高度相关的重大事件：孤星、愚人号、巴别塔、空想花庭、尘影余音、风雪过境、生于黑夜",
    }
    return desc.get(topic, topic)


def build_topic_prompt(topic: str, route: str, materials: list[dict]) -> str:
    parts = []
    for i, m in enumerate(materials, 1):
        parts.append(f"[材料{i}] {m['name']}（来源: {m.get('source_file', '?')}）\n{m.get('excerpt', '')[:900]}")
    if route == "simple":
        route_desc = (
            "简单路由：用【单个活动材料】内的单点事实出题——问某事件/计划/角色的具体事实，"
            "答案须有信息量（事实 + 一句意义/依据/背景），基于材料可答，禁止单字词或干瘪列表"
        )
    else:
        route_desc = (
            "复杂路由：**跨活动/跨章节综合题**——围绕该题材的完整脉络出题（如：梳理事件进程、"
            "关键转折、多方势力演变、因果链、主题对比）。答案要点分别标注材料编号，"
            "总结要串起因果与前后关联（用户强调：跨章节总结必须到位，不能只罗列孤立事件）"
        )
    return (
        f"题材：{topic}\n题材背景：{topic_desc(topic)}\n"
        f"路由：{route_desc}\n"
        f"预期工具：['search_events', 'get_chapter_summary', 'search_timeline']\n"
        f"预期行为：complex\n\n"
        f"材料片段：\n" + "\n\n".join(parts) +
        f"\n\n请基于上述材料生成 1 道{topic} 的{route}题（含答案要点 summary 与 evidence，evidence 标注材料编号）。"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="事件类题材题生成器")
    parser.add_argument("--topic", default="all", help="题材名或 all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-meta-eval", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    topics = list(TARGET) if args.topic == "all" else [args.topic]
    for t in topics:
        if t not in TARGET:
            print(f"未知题材: {t}", file=sys.stderr)
            return 2

    plan = {t: {"simple": 0, "complex": 0, "topic_materials": len(load_topic_materials(t))} for t in topics}
    total = 0
    for t in topics:
        n = TARGET[t]
        plan[t]["complex"] = round(n * COMPLEX_RATIO)
        plan[t]["simple"] = n - plan[t]["complex"]
        total += n

    print("=== 事件类题材题生成预估 ===")
    for t, p in plan.items():
        print(f"  {t}: 简 {p['simple']} + 复 {p['complex']} = {p['simple'] + p['complex']} 题（题材材料 {p['topic_materials']} 条）")
    print(f"外部调用: 生成 {total} 次 + 元评估 {0 if args.no_meta_eval else total} 次（{gbq.eval_config.get_search_model()}）")
    if args.dry_run:
        print("\n[dry-run] 未执行。")
        return 0
    if not gbq.eval_config.get_opencode_go_key():
        print("错误：未检测到 opencode_go_api", file=sys.stderr)
        return 1

    existing_ids = set()
    if OUT_PATH.exists():
        for line in OUT_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    existing_ids.add(json.loads(line)["id"])
                except Exception:
                    pass
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_lock = threading.Lock()
    counter = {"n": 0, "ok": 0, "reject": 0}

    def generate_one(t: str, route: str, k: int):
        mats = load_topic_materials(t)
        if not mats:
            return f"  ! {t}: 无材料"
        prompt = build_topic_prompt(t, route, mats)
        try:
            out = gbq.chat_json(gbq.eval_config.get_search_model(), "你是《明日方舟》剧情出题专家。", prompt, max_retries=2)
            stats = out.pop("_stats", {})
            gbq._log_cost({"step": f"generate:event:{route}", "model": gbq.eval_config.get_search_model(), **{k2: v2 for k2, v2 in stats.items()}})
            items = out.get("items", [])
            if not items:
                return f"  ! {t} 生成空 items"
            for it in items:
                it["id"] = it.get("id") or f"event_{route}_{k:03d}"
                it["category"] = "event"
                it["route"] = "complex" if route == "complex" else "simple"
                it["topic"] = t
                it["source"] = "gamedrama_topic"
                it["requires_tools"] = ["search_events", "get_chapter_summary", "search_timeline"] if route == "complex" else []
                it["expected_behavior"] = "complex" if route == "complex" else "simple"
                # 校验：章节名 + kb
                cc = gbq.chapter_name_check(it["question"], it.get("answer_key", {}).get("summary", ""))
                it["chapter_check"] = cc
                kb = gbq.kb_check(it.get("answer_key", {}))
                it["kb_check"] = kb
                # 元评估
                if args.no_meta_eval:
                    it["meta_eval"] = {"quality": 1.0, "issues": [], "verdict": "pass"}
                else:
                    me = gbq.meta_eval(it, mats)
                    it["meta_eval"] = me
                with write_lock:
                    with OUT_PATH.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(it, ensure_ascii=False) + "\n")
                with write_lock:
                    counter["n"] += 1
                    if me.get("verdict") == "pass":
                        counter["ok"] += 1
                    else:
                        counter["reject"] += 1
                return f"  + [{it['id']}] {t} {route} | 元评估={me.get('verdict')} q={me.get('quality')}"
        except Exception as e:  # noqa: BLE001
            return f"  ! {t} {route} 失败: {str(e)[:150]}"

    jobs = []
    for t in topics:
        for route, n in (("complex", plan[t]["complex"]), ("simple", plan[t]["simple"])):
            for k in range(n):
                jobs.append((t, route, k))

    print(f"\n开始生成（{len(jobs)} 题, workers={args.workers}）...")
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(generate_one, *j): j for j in jobs}
        for fut in as_completed(futs):
            print(fut.result())
    print(f"\n完成。写入 {OUT_PATH} | 总 {counter['n']} | pass {counter['ok']} | review/reject {counter['reject']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
