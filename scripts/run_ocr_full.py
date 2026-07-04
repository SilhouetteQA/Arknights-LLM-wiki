"""大地巡旅 403页扫描图 → MiniMax M3 OCR → 合并 Markdown

用法: python run_ocr_full.py
- 自动续跑：已处理页面跳过
- 进度文件：data/Terra A Journey/ocr_state.json
- 输出：data/lorebook/terra_a_journey/page_XXX.md + terra_a_journey_full.md
"""
import base64
import io
import json
import os
import re
import sys
import time

from openai import OpenAI

# Windows 控制台 GBK 编码安全
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

IMAGE_DIR = "data/Terra A Journey/扫描全能王 2026-06-22 14.34"
STATE_FILE = "data/Terra A Journey/ocr_state.json"
OUT_DIR = "data/lorebook/terra_a_journey"
FULL_OUTPUT = "data/lorebook/terra_a_journey_full.md"

OCR_PROMPT = (
    "请逐字提取这张扫描书页中的所有文字。要求：\n"
    "1. 保留原文格式（段落、标题、列表、引用块）\n"
    "2. 图片描述文字、图注、边栏标注也需提取，用[图：...]或[注：...]标记\n"
    "3. 手写批注用【手写批注：...】标记\n"
    "4. 模糊不清晰的字根据上下文推断，用[推测：X]标注不确定的单字\n"
    "5. 输出纯 Markdown，不要任何开头说明或结尾总结"
)


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed": {}, "failed": {}, "total_pages": 0, "total_cost_rmb": 0.0}


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def ocr_page(client: OpenAI, image_path: str, page_num: int, max_retries: int = 3) -> tuple[str | None, dict]:
    """单页 OCR，含重试逻辑，返回 (markdown_text, stats)"""
    image_b64 = encode_image(image_path)
    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="MiniMax-M3",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                        {"type": "text", "text": OCR_PROMPT},
                    ],
                }],
                temperature=0.1,
                max_tokens=8192,
                extra_body={"thinking": {"type": "disabled"}},
            )
            content = response.choices[0].message.content or ""
            usage = response.usage
            stats = {
                "page": page_num,
                "tokens_in": usage.prompt_tokens if usage else 0,
                "tokens_out": usage.completion_tokens if usage else 0,
                "chars": len(content),
                "success": True,
                "attempts": attempt + 1,
            }
            # 清理残存的 think 标签
            content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
            return content, stats
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                time.sleep(wait)
    return None, {"page": page_num, "error": last_error, "success": False}


def compute_cost(tokens_in: int, tokens_out: int) -> float:
    """MiniMax M3 标准版价格（元人民币）"""
    cost_in = tokens_in / 1_000_000 * 2.1
    cost_out = tokens_out / 1_000_000 * 8.4
    return cost_in + cost_out


def main():
    # 初始化
    client = OpenAI(
        api_key=os.environ["minimax_api"],
        base_url="https://api.minimaxi.com/v1",
        timeout=180.0,
    )
    os.makedirs(OUT_DIR, exist_ok=True)

    # 获取排序后的图片列表
    all_images = sorted(
        [f for f in os.listdir(IMAGE_DIR) if f.endswith(".jpg")],
        key=lambda x: int(x.rsplit("_", 1)[1].replace(".jpg", "")),
    )
    total = len(all_images)
    print(f"图片总数: {total}")

    state = load_state()
    state["total_pages"] = total

    # 统计已完成
    already_done = len(state["completed"])
    if already_done > 0:
        print(f"已完成: {already_done} 页，跳过继续")

    total_cost = state.get("total_cost_rmb", 0.0)

    for idx, fname in enumerate(all_images):
        page_num = idx + 1
        page_key = str(page_num)

        # 跳过已完成
        if page_key in state["completed"]:
            continue
        # 跳过已知失败（除非要重试）
        if page_key in state["failed"] and state["failed"][page_key].get("retries", 0) >= 3:
            continue

        fpath = os.path.join(IMAGE_DIR, fname)
        file_size_kb = os.path.getsize(fpath) / 1024
        print(f"[{page_num}/{total}] {fname} ({file_size_kb:.0f}KB) ... ", end="", flush=True)

        content, stats = ocr_page(client, fpath, page_num)

        if content is not None:
            # 保存单页 md
            os.makedirs(OUT_DIR, exist_ok=True)
            out_path = os.path.join(OUT_DIR, f"page_{page_num:03d}.md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)

            page_cost = compute_cost(stats["tokens_in"], stats["tokens_out"])
            total_cost += page_cost
            stats["cost_rmb"] = round(page_cost, 4)
            state["completed"][page_key] = stats
            print(f"OK ({stats['tokens_in']}in/{stats['tokens_out']}out, RMB{page_cost:.4f})")
        else:
            # 失败处理
            if page_key not in state["failed"]:
                state["failed"][page_key] = {"retries": 0, "errors": []}
            state["failed"][page_key]["retries"] += 1
            state["failed"][page_key]["errors"].append(stats.get("error", "unknown"))
            print(f"FAIL ({stats.get('error', 'unknown')[:80]})")

        state["total_cost_rmb"] = round(total_cost, 2)
        save_state(state)
        time.sleep(2.0)  # 节流，避免 API 限流

    # 汇总
    completed = len(state["completed"])
    failed = len(state["failed"])
    print(f"\n===== 完成 =====")
    print(f"成功: {completed}/{total}")
    print(f"失败: {failed}/{total}")
    print(f"总费用: RMB{total_cost:.2f}")

    # 合并全文
    if completed > 0:
        print(f"\n合并全文至 {FULL_OUTPUT} ...")
        with open(FULL_OUTPUT, "w", encoding="utf-8") as out:
            out.write("# 《大地巡旅》OCR 全文\n\n")
            out.write(f"> 共 {completed} 页，MiniMax M3 视觉模型提取\n\n")
            out.write("---\n\n")
            for page_num in sorted(int(k) for k in state["completed"]):
                page_file = os.path.join(OUT_DIR, f"page_{page_num:03d}.md")
                if os.path.exists(page_file):
                    with open(page_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    out.write(f"## 第 {page_num} 页\n\n")
                    out.write(content)
                    out.write("\n\n---\n\n")
        print(f"全文合并完成: {FULL_OUTPUT}")


if __name__ == "__main__":
    main()
