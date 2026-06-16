"""M0 种子编排：按序调用三个 Repository 完成初始填充"""
import os
import time
from arknights_wiki.store._schema import init_db
from arknights_wiki.store.entity_repository import EntityRepository
from arknights_wiki.store.source_repository import SourceIndexRepository


def resolve_project_path(relative_path: str) -> str:
    """将项目相对路径解析为绝对路径"""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, relative_path)


def resolve_data_path(relative_path: str) -> str:
    """解析数据文件路径（尊重 ARKNIGHTS_DATA_DIR 环境变量）"""
    data_dir = os.environ.get('ARKNIGHTS_DATA_DIR') or resolve_project_path('data')
    if relative_path.startswith('data/'):
        relative_path = relative_path[5:]
    return os.path.join(data_dir, relative_path)


def resolve_config_path(relative_path: str) -> str:
    """解析配置文件路径"""
    if relative_path.startswith('config/'):
        return resolve_project_path(relative_path)
    return resolve_project_path(f'config/{relative_path}')


def run_seed(db_path: str | None = None) -> dict:
    """执行 M0 种子流程，仅确定性数据。

    M0 职责:
      1. 干员/faction/region 实体 (operators.json)
      2. 异格别名映射 (identity_map.json)
      3. 干员档案索引 (确定性, 无需 LLM)

    NPC 实体和故事对话索引移出 M0 —— 在 M1 chapter 生成和 M3 LLM 提取中按需创建。
    """
    if db_path is None:
        db_path = os.path.join(resolve_data_path(''), 'arknights_wiki.db')

    print(f'[M0 Seed] 数据库: {db_path}')

    init_db(db_path)

    from arknights_wiki.stats import StatsCollector
    collector = StatsCollector(db_path)
    collector.start('seed_m0')

    er = EntityRepository(db_path)
    sr = SourceIndexRepository(db_path)

    result = {}

    # 1. 从 operators.json 提取干员/faction/region 实体 (异格不建独立 entity)
    print('[M0 Seed] Step 1/3: 干员实体...')
    t0 = time.time()
    ops_path = resolve_data_path('operators.json')
    idmap_path = resolve_config_path('identity_map.json')
    n_entities = er.seed_from_operators(ops_path, idmap_path)
    result['entities'] = n_entities
    collector.record_step('seed_entities', int((time.time() - t0) * 1000))
    print(f'  -> {n_entities} 实体 (character + faction + region)')

    # 2. 加载 identity_map -> entity_aliases
    print('[M0 Seed] Step 2/3: 异格/别名映射...')
    t0 = time.time()
    n_aliases = er.seed_identity_map(idmap_path)
    result['aliases'] = n_aliases
    collector.record_step('seed_aliases', int((time.time() - t0) * 1000))
    print(f'  -> {n_aliases} 别名')

    # 3. 干员档案 -> source_index (异格档案挂在基体 entity 上)
    print('[M0 Seed] Step 3/3: 干员档案索引...')
    t0 = time.time()
    n_archive = sr.seed_operator_archives(ops_path, idmap_path)
    result['source_index_entries'] = n_archive
    collector.record_step('seed_archives', int((time.time() - t0) * 1000))
    print(f'  -> {n_archive} 档案索引条目')

    result['characters'] = er.count('character')
    result['factions'] = er.count('faction')
    result['regions'] = er.count('region')

    print(f'[M0 Seed] 完成!')
    print(f'  character: {result["characters"]}  faction: {result["factions"]}')
    print(f'  region: {result["regions"]}  source_index: {result["source_index_entries"]}')

    stats = collector.finish()
    print(f'  统计已写入: {collector._jsonl_path}')
    print(f'  总耗时: {stats["duration_ms"]}ms')

    return result


if __name__ == '__main__':
    run_seed()
