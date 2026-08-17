#!/usr/bin/env python
"""W0 T4: Benchmark 题目生成管线 v3（Grounded Generation）

流程：读材料清单 → 按角度×路由抽样 → 材料注入出题 → 校验（章节比对/kb_check/元评估）→ 输出候选

用法：
  python scripts/generate_benchmark_questions.py --dry-run            # 预估（零外部调用）
  python scripts/generate_benchmark_questions.py --angle all          # 生成全部角度
  python scripts/generate_benchmark_questions.py --angle character --limit 2 --no-meta-eval

外部调用：生成 + 元评估（doubao-seed-1-6-flash，经 arkcode_api）；成本记录 cost_log.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from arknights_wiki.eval import config as eval_config
from arknights_wiki.eval.llm import chat_json

MATERIALS_DIR = ROOT / "benchmarks" / "arknights_bench" / "materials"
DRAFT_PATH = ROOT / "benchmarks" / "arknights_bench" / "questions_draft.jsonl"
COST_LOG = ROOT / "output" / "eval" / "cost_log.jsonl"
CHAPTER_LIST = ROOT / "config" / "chapter_timeline.json"
TAXONOMY = ROOT / "config" / "story_taxonomy.json"

# 角度配置：题量（简/复）、工具、行为
ANGLE_CONFIG = {
    "character": {"total": 18, "simple": 7, "complex": 11, "tools": ["get_entity_page", "search_events"], "behavior": "complex"},
    "event": {"total": 18, "simple": 7, "complex": 11, "tools": ["search_events", "search_timeline"], "behavior": "complex"},
    "region": {"total": 16, "simple": 6, "complex": 10, "tools": ["get_entity_page", "search_wiki"], "behavior": "complex"},
    "organization": {"total": 16, "simple": 6, "complex": 10, "tools": ["get_entity_page", "search_events"], "behavior": "complex"},
    "combat_power": {"total": 16, "simple": 6, "complex": 10, "tools": ["get_entity_page"], "behavior": "complex"},
    "worldview": {"total": 16, "simple": 6, "complex": 10, "tools": ["get_entity_page", "search_timeline", "semantic_search"], "behavior": "complex"},
}

ANGLE_ZH = {
    "character": "人物", "event": "事件", "region": "国家地区",
    "organization": "组织", "combat_power": "战斗力", "worldview": "世界观",
}

SYSTEM_PROMPT = """你是《明日方舟》剧情知识库出题专家。你只依据【材料片段】出题，禁止使用材料之外的任何信息。

规则：
1. 题目必须能由材料片段直接回答；答案要点必须完全来自材料
2. 章节名/活动名/人物名/事件名一律取自材料原文，禁止联想或替换
3. 简单路由题：单条材料即可作答的单点事实题，但答案必须【有信息量】——包含事实本身 + 一句依据/上下文解释（如战斗力题：评级 + 依据/能力体现），禁止单字词或干瘪列表式回答
4. 复杂路由题：需要综合多条材料（对比/因果/聚合），答案要点分别标注材料编号
5. 【答案质量要求（所有题）】：summary 为 2-4 句连贯的可读段落——第一句给出核心事实，后续句给出依据/背景/影响（从材料提取），确保只读答案也能理解来龙去脉，不要罗列碎片
6. 输出严格 JSON 对象：{"items": [{"id": "...", "question": "...", "answer_key": {"summary": "2-4 句连贯可读答案", "evidence": ["材料编号+要点"]}, "difficulty": 1-3, "material_refs": ["材料名1", "材料名2"]}]}
7. id 格式：{angle}_{simple|complex}_{三位序号}"""


def _log_cost(entry: dict) -> None:
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry["timestamp"] = datetime.now().isoformat(timespec="seconds")
    with COST_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_materials(angle: str) -> list[dict]:
    """读取角度材料清单（支持多文件：{angle}.json + {angle}_chapters.json）"""
    items: list[dict] = []
    for path in MATERIALS_DIR.glob(f"{angle}*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items.extend(data.get("items", []))
        except Exception as e:  # noqa: BLE001
            print(f"  警告: 材料文件 {path.name} 解析失败: {str(e)[:100]}")
    return items


def chapter_name_check(question: str, answer: str) -> dict:
    """校验①：问题/答案中出现的《章节》名是否在知识库清单中"""
    names = re.findall(r"[《【]([^》】]+)[》】]", question + answer)
    if not names:
        return {"checked": 0, "unknown": []}
    known = set()
    try:
        tl = json.loads(CHAPTER_LIST.read_text(encoding="utf-8"))
        known.update(tl.get("chapters", []))
    except Exception:
        pass
    try:
        tax = json.loads(TAXONOMY.read_text(encoding="utf-8"))
        known.update(tax.keys())
    except Exception:
        pass
    unknown = [n for n in names if n not in known and len(n) >= 2]
    return {"checked": len(names), "unknown": unknown}


def kb_check(answer_key: dict) -> dict:
    """校验②：evidence 中的实体能否在知识库定位（零成本）"""
    checks = []
    try:
        from arknights_wiki.agent.retrieval import EntityIndexStore, WikiStore

        idx = EntityIndexStore()
        wiki = WikiStore()
        for ev in (answer_key or {}).get("evidence", []):
            found = False
            candidates = [ev] + re.findall(r"[《【]([^》】]+)[》】]", ev)
            for cand in candidates:
                cand = cand.strip()
                if not cand:
                    continue
                if idx.lookup(cand) is not None:
                    found = True
                    break
                for etype in ("concepts", "factions", "locations"):
                    if wiki.get_page(cand, etype) is not None:
                        found = True
                        break
            checks.append({"evidence": ev, "in_kb": bool(found)})
    except Exception as e:  # noqa: BLE001
        checks.append({"error": str(e)[:200]})
    return {"kb_checks": checks, "kb_all_found": all(c.get("in_kb") for c in checks) if checks else None}


META_EVAL_PROMPT = """你是题目质量评审。判断这道题是否适合作为评测题：
标准：① 有明确唯一答案（基于材料可作答）② 无歧义 ③ 不要求材料之外的知识 ④ 难度适中
输出严格 JSON：{"quality": 0.0-1.0, "issues": ["问题1", ...], "verdict": "pass|review|reject"}"""


def meta_eval(item: dict, materials: list[dict] | None = None) -> dict:
    """校验③：题目质量元评估（judge 打分），低分标记；必须传入实际材料内容供评审"""
    material_text = "（未提供）"
    if materials:
        material_text = "\n---\n".join(
            f"[材料{i + 1}] {m.get('name', '?')}: {m.get('excerpt', '')[:500]}" for i, m in enumerate(materials)
        )
    prompt = (
        f"题目：{item['question']}\n"
        f"答案要点：{item['answer_key']['summary']}\n"
        f"材料内容：\n{material_text}\n\n" + META_EVAL_PROMPT
    )
    try:
        out = chat_json(eval_config.get_search_model(), "你是评测题目质量评审。", prompt)
        stats = out.pop("_stats", {})
        _log_cost({"step": "meta_eval", "model": eval_config.get_search_model(), **{k: v for k, v in stats.items()}})
        return out
    except Exception as e:  # noqa: BLE001
        return {"quality": 0.0, "issues": [str(e)[:100]], "verdict": "review"}


def build_prompt(angle: str, route: str, materials: list[dict]) -> str:
    cfg = ANGLE_CONFIG[angle]
    parts = []
    for i, m in enumerate(materials, 1):
        parts.append(f"[材料{i}] {m['name']}（来源: {m.get('source_file', '?')}）\n{m.get('excerpt', '')[:800]}")
    route_desc = (
        "简单路由：单条材料即可作答的单点事实题；答案须含事实 + 依据/上下文解释（有信息量，禁单字词回答）"
        if route == "simple"
        else "复杂路由：需综合多条材料（对比/因果/聚合/多章节），答案要点分别标注材料编号"
    )
    return (
        f"角度：{ANGLE_ZH[angle]}（{angle}）\n"
        f"路由：{route_desc}\n"
        f"预期工具：{cfg['tools']}\n"
        f"预期行为：{cfg['behavior']}\n\n"
        f"材料片段：\n" + "\n\n".join(parts) +
        f"\n\n请基于上述材料生成 1 道{ANGLE_ZH[angle]}{route}题（含答案要点与材料引用）。"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="W0 题目生成管线 v3")
    parser.add_argument("--angle", default="all", help="character|event|region|organization|combat_power|worldview|all")
    parser.add_argument("--limit", type=int, default=0, help="每角度每路由最多生成数（0=按配置）")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-meta-eval", action="store_true", help="跳过题目质量元评估")
    args = parser.parse_args()

    angles = list(ANGLE_CONFIG) if args.angle == "all" else [args.angle]
    for a in angles:
        if a not in ANGLE_CONFIG:
            print(f"未知角度: {a}", file=sys.stderr)
            return 2

    # 预估
    plan = {}
    total = 0
    for a in angles:
        mats = load_materials(a)
        cfg = ANGLE_CONFIG[a]
        if not mats:
            print(f"警告: 角度 {a} 无材料清单，跳过")
            continue
        s = min(cfg["simple"], args.limit or cfg["simple"])
        c = min(cfg["complex"], args.limit or cfg["complex"])
        plan[a] = {"simple": s, "complex": c, "materials": len(mats)}
        total += s + c
    est_cost = total * 3 * 1500 / 1e6 * 0.3 + (0 if args.no_meta_eval else total * 1.5 * 1000 / 1e6 * 0.3)

    print("=== W0 题目生成预估 (v3 grounded) ===")
    for a, p in plan.items():
        print(f"  {ANGLE_ZH[a]}: 简 {p['simple']} + 复 {p['complex']} = {p['simple'] + p['complex']} 题（材料 {p['materials']} 条）")
    print(f"外部调用: 生成 {total} 次 + 元评估 {0 if args.no_meta_eval else total} 次（{eval_config.get_search_model()}）")
    print(f"LLM 费用估算: ~¥{est_cost:.3f}")
    if args.dry_run:
        print("\n[dry-run] 未执行外部调用。确认后去掉 --dry-run 运行。")
        return 0
    if not eval_config.get_ark_api_key():
        print("错误：未检测到 arkcode_api", file=sys.stderr)
        return 1

    # 生成（并发 4 路提速；id 按 k 规范化保证唯一且与断点兼容）
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    existing_ids = set()
    if DRAFT_PATH.exists():
        for line in DRAFT_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    existing_ids.add(json.loads(line)["id"])
                except Exception:
                    pass
    DRAFT_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_lock = threading.Lock()

    def generate_one(a: str, route: str, k: int, mats: list[dict]):
        """单题生成（线程安全）：抽样 → 生成 → 校验 → 元评估"""
        if route == "simple":
            sample = [mats[k % len(mats)]]
        else:
            i1 = (k * 2) % len(mats)
            i2 = (k * 2 + 1) % len(mats)
            sample = [mats[i1]]
            if i2 != i1:
                sample.append(mats[i2])
        out = chat_json(eval_config.get_search_model(), SYSTEM_PROMPT, build_prompt(a, route, sample))
        stats = out.pop("_stats", {})
        _log_cost({"step": f"generate:{a}:{route}", "model": eval_config.get_search_model(), **{k2: v for k2, v in stats.items()}})
        items = out.get("items") or []
        if isinstance(out, list):
            items = out
        results = []
        for it in items:
            if not isinstance(it, dict) or not it.get("question"):
                continue
            qid = f"{a}_{route}_{k + 1:03d}"
            it["id"] = qid
            it["category"] = a
            it["route"] = route
            it["expected_behavior"] = route
            it["requires_tools"] = ANGLE_CONFIG[a]["tools"]
            it["source"] = "grounded_llm"
            it["material_refs"] = [m["name"] for m in sample]
            it["chapter_check"] = chapter_name_check(it.get("question", ""), it.get("answer_key", {}).get("summary", ""))
            it["answer_key"]["kb_check"] = kb_check(it.get("answer_key", {}))
            it["meta_eval"] = meta_eval(it, sample) if not args.no_meta_eval else {"verdict": "skipped"}
            results.append(it)
        return results

    futures = []
    for a, p in plan.items():
        mats = load_materials(a)
        for route, count in (("simple", p["simple"]), ("complex", p["complex"])):
            if count == 0:
                continue
            for k in range(count):
                qid = f"{a}_{route}_{k + 1:03d}"
                if qid in existing_ids:
                    continue
                futures.append((qid, a, route, k, mats))

    written = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        fmap = {ex.submit(generate_one, a, route, k, mats): qid for qid, a, route, k, mats in futures}
        for fut in as_completed(fmap):
            qid = fmap[fut]
            try:
                for it in fut.result():
                    with write_lock:
                        with DRAFT_PATH.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(it, ensure_ascii=False) + "\n")
                    existing_ids.add(it["id"])
                    written += 1
                    print(f"  + {it['id']}: {it['question'][:50]}... meta={it['meta_eval'].get('verdict', '?')}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  [失败 {qid}] {str(e)[:150]}", file=sys.stderr)
    print(f"\n完成。新写入 {written} 条（失败 {failed}）→ {DRAFT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
