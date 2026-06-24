"""OpenAI Evals 入口 — 设置环境变量后调用 oaieval"""
import os
import sys

# 桥接 deepseek_api 到 OPENAI_API_KEY（evals 包 import 时需要）
deepseek_key = os.environ.get("deepseek_api", "")
if deepseek_key and not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = deepseek_key

# 将项目根目录加入 PYTHONPATH
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 修复 add_token_usage_to_result 兼容新版 OpenAI SDK
# 新版 SDK 的 usage 包含 prompt_tokens_details (对象) 等非 int 字段
from typing import Any
from evals.record import RecorderBase


def _patched_add_token_usage_to_result(result: dict[str, Any], recorder: RecorderBase) -> None:
    import logging
    logger = logging.getLogger(__name__)
    usage_events = []
    sampling_events = recorder.get_events("sampling")
    for event in sampling_events:
        if "usage" in event.data:
            usage_events.append(dict(event.data["usage"]))
    logger.info(f"Found {len(usage_events)}/{len(sampling_events)} sampling events with usage data")
    if usage_events:
        total_usage = {
            key: sum(u[key] if isinstance(u[key], (int, float)) else 0 for u in usage_events)
            for key in usage_events[0]
        }
        total_usage_str = "\n".join(
            f"{key}: {value:,}" for key, value in total_usage.items() if value
        )
        logger.info(f"Token usage from {len(usage_events)} sampling events:\n{total_usage_str}")
        for key, value in total_usage.items():
            keyname = f"usage_{key}"
            if keyname not in result:
                result[keyname] = value


import evals.cli.oaieval as oaieval_mod
oaieval_mod.add_token_usage_to_result = _patched_add_token_usage_to_result

from evals.cli.oaieval import main

if __name__ == "__main__":
    main()
