"""一次性离线脚本: 构建 FAISS 向量索引 + chunk_map

使用方式:
  python scripts/build_agent_index.py

环境变量:
  ARKNIGHTS_SKIP_EMBED_MODEL=1  跳过模型加载（使用随机向量，仅测试）
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arknights_wiki.agent.vector_index import build_index_from_data
from arknights_wiki.config import DATA_DIR


def main():
    index_dir = os.path.join(DATA_DIR, "index")
    print(f"数据目录: {DATA_DIR}")
    print(f"索引目录: {index_dir}")

    t0 = time.time()
    index_path, map_path = build_index_from_data(DATA_DIR, index_dir)

    elapsed = time.time() - t0
    print(f"\n索引构建完成 ({elapsed:.1f}s)")
    print(f"  FAISS 索引: {index_path}")
    print(f"  chunk_map:   {map_path}")

    from arknights_wiki.agent.vector_index import load_index
    index, chunk_map = load_index(index_path, map_path)
    print(f"  向量数: {index.ntotal}")
    print(f"  实体数: {len(chunk_map)}")

    # 统计各类型实体数
    type_counts = {}
    for key in chunk_map:
        etype = key.split(":", 1)[0]
        type_counts[etype] = type_counts.get(etype, 0) + 1
    print(f"\n实体类型分布:")
    for etype, count in sorted(type_counts.items()):
        print(f"  {etype}: {count}")


if __name__ == "__main__":
    main()
