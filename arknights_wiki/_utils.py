# arknights_wiki/_utils.py
"""纯函数工具 —— JSON 读写、哈希、文件名清理、URL 规范化"""

import hashlib
import json
import os
import re


def sanitize_filename(name: str) -> str:
    """将字符串转换为安全的文件名"""
    result = name.strip()
    result = re.sub(r'[<>:"/\\|?*]', '_', result)
    result = re.sub(r'\s+', '_', result)
    return result


def ensure_dir(path: str) -> None:
    """确保目录存在，不存在则创建"""
    os.makedirs(path, exist_ok=True)


def read_json(filepath: str) -> dict:
    """读取 JSON 文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json(filepath: str, data: object) -> None:
    """写入 JSON 文件，保持中文字符可读"""
    dirname = os.path.dirname(filepath)
    if dirname:
        ensure_dir(dirname)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compute_hash(text: str) -> str:
    """计算文本的 SHA256 hash（十六进制）"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def normalize_url(url: str) -> str:
    """将相对 URL 或域名缺省的 URL 补全为完整 prts.wiki URL"""
    if url.startswith('https://'):
        return url
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('/'):
        return 'https://prts.wiki' + url
    return url
