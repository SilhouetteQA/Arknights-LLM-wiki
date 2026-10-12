"""W11-alpha step 1.1 — provider availability probe, WIKI side.

Read-only: makes three tiny LLM calls (max_tokens=16) and writes one JSON report.
Never prints API keys — only presence booleans.

Run from the wiki repo root with the authoritative interpreter:
    D:\\CodexPython312\\python.exe output/_w11_probe/probe_wiki_providers.py
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

OUT = Path("output/_w11_probe")
OUT.mkdir(parents=True, exist_ok=True)
res: dict = {"side": "wiki", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def host_of(url: str | None) -> str | None:
    try:
        return (url or "").split("/")[2]
    except Exception:
        return None


def safe(fn, label):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        res[label + "_error"] = f"{type(e).__name__}: {e}"[:300]
        return None


from arknights_wiki.eval import config as cfg  # noqa: E402
from arknights_wiki.eval import llm as evalllm  # noqa: E402


def agent_cfg():
    from arknights_wiki.extraction.llm_client import _get_model_config

    return _get_model_config()


acfg = safe(agent_cfg, "agent_config")
if acfg:
    res["agent"] = {
        "model": acfg.get("model"),
        "base_url_host": host_of(acfg.get("base_url")),
        "api_key_present": bool(acfg.get("api_key")),
    }

res["judge_model"] = safe(cfg.get_judge_model, "judge_model")
res["judge_base_host"] = safe(lambda: host_of(cfg.get_opencode_go_base()), "judge_base")
res["judge_key_present"] = safe(lambda: bool(cfg.get_opencode_go_key()), "judge_key")


def timed_chat(model: str, label: str, **kw):
    t0 = time.monotonic()
    r = evalllm.chat(
        model,
        [{"role": "user", "content": "Reply with the single word: pong"}],
        max_tokens=16,
        max_retries=0,
        **kw,
    )
    res[label] = {
        "model": r["model"],
        "latency_ms": r["latency_ms"],
        "wall_ms": round((time.monotonic() - t0) * 1000, 1),
        "tokens_in": r["tokens_in"],
        "tokens_out": r["tokens_out"],
        "cost_cny": r["cost"],
        "content_head": (r["content"] or "")[:40],
    }
    return r


# --- consolidated provider (current default for both agent and judge) ---
if res.get("judge_model"):
    safe(lambda: timed_chat(res["judge_model"], "consolidated_judge_call"), "consolidated_judge_call")
if acfg and acfg.get("model") and acfg.get("model") != res.get("judge_model"):
    safe(lambda: timed_chat(acfg["model"], "agent_model_call"), "agent_model_call")

# --- legacy opencode zen/go gateway (judge of the historical 0.857 baseline) ---
os.environ["arknights_judge_use_opencode"] = "1"
res["legacy_gateway"] = {
    "base_host": safe(lambda: host_of(cfg.get_opencode_go_base()), "legacy_base"),
    "key_present": safe(lambda: bool(cfg.get_opencode_go_key()), "legacy_key"),
}
safe(lambda: timed_chat("mimo-v2.5", "legacy_mimo_call"), "legacy_mimo_call")

(OUT / "probe_wiki.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=2))
