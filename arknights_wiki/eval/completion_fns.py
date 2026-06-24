"""DeepSeek 适配 — OpenAI Evals 通过 OpenAI 兼容 API 调用 DeepSeek"""
import os

# evals 包在 import 时会创建全局 OpenAI client，需要 OPENAI_API_KEY 环境变量
# 项目使用 deepseek_api，这里做一个桥接
if not os.environ.get("OPENAI_API_KEY"):
    deepseek_key = os.environ.get("deepseek_api", "")
    if deepseek_key:
        os.environ["OPENAI_API_KEY"] = deepseek_key

from evals.completion_fns.openai import OpenAIChatCompletionFn


class DeepSeekCompletionFn(OpenAIChatCompletionFn):
    """使用项目已有的 deepseek_api 环境变量配置"""

    def __init__(self, registry=None, **kwargs):
        api_key = os.environ.get("deepseek_api", "")
        if not api_key:
            raise RuntimeError("未设置 deepseek_api 环境变量")

        # 默认值，允许调用方通过 kwargs 覆盖
        defaults = {
            "model": "deepseek-chat",
            "api_base": "https://api.deepseek.com/v1",
            "api_key": api_key,
        }
        # 过滤掉 OpenAIChatCompletionFn 不接受的参数
        accepted = {"model", "api_base", "api_key", "n_ctx", "extra_options"}
        defaults.update({k: v for k, v in kwargs.items() if k in accepted})
        super().__init__(**defaults)
