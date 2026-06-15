# arknights_wiki/config.py
"""集中配置 —— 路径常量、URL、分类映射"""

import os

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据目录（可通过环境变量覆盖）
DATA_DIR = os.environ.get("ARKNIGHTS_DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
OUTPUT_DIR = os.environ.get("ARKNIGHTS_OUTPUT_DIR", os.path.join(PROJECT_ROOT, "output"))

# PRTS Wiki URL
PRTS_BASE = "https://prts.wiki"
INDEX_URL = f"{PRTS_BASE}/w/%E5%89%A7%E6%83%85%E4%B8%80%E8%A7%88"
OPERATOR_LIST_URL = f"{PRTS_BASE}/w/%E5%B9%B2%E5%91%98%E4%B8%80%E8%A7%88"

# 剧情分类映射（PRTS 页面标签 → 内部 key）
CATEGORY_LABEL_MAP = {
    "主线": "main",
    "插曲": "intermezzi",
    "干员密录": "operator_records",
    "活动": "side",
    "剧情": "special",
}

# 分类中文标签（内部 key → 中文名）
CATEGORY_LABELS = {
    "main": "主线",
    "side": "支线",
    "intermezzi": "插曲",
    "operator_records": "干员密录",
    "special": "特殊",
}

# 干员人物字段白名单（从 data-* 属性中提取）
OPERATOR_CHAR_FIELDS = [
    "id", "name_zh", "race", "nation", "birth_place",
    "team", "group", "sex", "logo",
]

# data-* 属性名 → 输出字段名映射
OPERATOR_DATA_ATTR_MAP = {
    "data-id": "id",
    "data-zh": "name_zh",
    "data-race": "race",
    "data-nation": "nation",
    "data-birth_place": "birth_place",
    "data-team": "team",
    "data-group": "group",
    "data-sex": "sex",
    "data-logo": "logo",
}
