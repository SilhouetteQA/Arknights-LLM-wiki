"""DeepSeek 适配 — OpenAI Evals 通过 OpenAI 兼容 API 调用 DeepSeek"""
import os


def _ensure_evals_api_key():
    """确保 OPENAI_API_KEY 已设置（供 evals 框架使用）。

    从 deepseek_api 环境变量桥接到 OPENAI_API_KEY。
    仅在显式调用时执行，避免模块导入时的副作用。
    """
    if not os.environ.get("OPENAI_API_KEY"):
        deepseek_key = os.environ.get("deepseek_api", "")
        if deepseek_key:
            os.environ["OPENAI_API_KEY"] = deepseek_key


from evals.completion_fns.openai import OpenAIChatCompletionFn


class DeepSeekCompletionFn(OpenAIChatCompletionFn):
    """使用项目已有的 deepseek_api 环境变量配置"""

    def __init__(self, registry=None, **kwargs):
        _ensure_evals_api_key()
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
