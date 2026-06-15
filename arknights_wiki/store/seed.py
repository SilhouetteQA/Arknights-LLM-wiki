"""M0 种子编排：按序调用三个 Repository 完成初始填充"""
import os
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
    """执行完整种子流程，返回统计信息"""
    if db_path is None:
        db_path = os.path.join(resolve_data_path(''), 'arknights_wiki.db')

    print(f'[M0 Seed] 数据库: {db_path}')

    # 初始化数据库
    init_db(db_path)

    er = EntityRepository(db_path)
    sr = SourceIndexRepository(db_path)

    result = {}

    # 1. 从 operators.json 提取实体
    print('[M0 Seed] Step 1/5: 干员实体...')
    ops_path = resolve_data_path('operators.json')
    n_entities = er.seed_from_operators(ops_path)
    result['entities'] = n_entities
    print(f'  -> {n_entities} 实体 (character + faction + region)')

    # 2. 加载 identity_map -> entity_aliases
    print('[M0 Seed] Step 2/5: 加载异格/别名映射...')
    idmap_path = resolve_config_path('identity_map.json')
    n_aliases = er.seed_identity_map(idmap_path)
    result['aliases'] = n_aliases
    print(f'  -> {n_aliases} 别名')

    # 3. 从 stories 对话提取 NPC
    print('[M0 Seed] Step 3/5: 故事NPC...')
    index_path = resolve_data_path('index.json')
    stories_path = resolve_data_path('stories')
    n_npc = er.seed_from_story_dialogue(index_path, stories_path)
    result['npc_added'] = n_npc
    print(f'  -> {n_npc} 新 NPC')

    # 4. 建立 source_index
    print('[M0 Seed] Step 4/5: 源文档索引...')
    n_archive = sr.seed_operator_archives(ops_path)
    n_story = sr.seed_story_dialogue(index_path, stories_path)
    n_concept = sr.seed_concept_keywords(resolve_config_path('concept_keywords.json'))
    result['source_index_entries'] = n_archive + n_story + n_concept
    print(f'  -> 档案索引: {n_archive}, 故事索引: {n_story}, 概念索引: {n_concept}')

    # 5. 统计
    result['characters'] = er.count('character')
    result['factions'] = er.count('faction')
    result['regions'] = er.count('region')
    result['concepts'] = er.count('concept')
    result['chapters'] = er.count('chapter')

    print(f'[M0 Seed] 完成!')
    print(f'  character: {result["characters"]}  faction: {result["factions"]}')
    print(f'  region: {result["regions"]}  concept: {result["concepts"]}')
    print(f'  source_index: {result["source_index_entries"]}')

    return result


if __name__ == '__main__':
    run_seed()
