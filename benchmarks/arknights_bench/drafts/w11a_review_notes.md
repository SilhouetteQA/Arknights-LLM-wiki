# W11-α T4 — 新增两类题目（`no_answer` / `hallucination_bait`）人工抽验单

> 交付物：`benchmarks/arknights_bench/drafts/w11a_new_categories.jsonl`（22 条，**草稿，未入冻结集**）
> 关联：`docs/specs/2026-10-12-pre-extraction-benchmark-freeze.md` §3.2 · `docs/plans/2026-10-12-pre-extraction-benchmark-freeze-plan.md` T4 · CLAUDE.md U-14 / N-01
> 全部题目**人工构造**（`source=manual`），无 LLM 生成，故不写 `source=grounded_llm`。

## 0. 字段口径（对齐既有 100 题，先看这里）

| 字段 | 本批取值 | 依据 |
|---|---|---|
| `id` | `{category}_reject_{NNN}`（如 `no_answer_reject_001`） | 沿用既有 100 题的 `{category}_{route}_{NNN}` 约定（`character_complex_001`）。既有同类草稿 `manual_draft.jsonl` 用的是 `no_answer_001` 形式，与之**会撞 id**，故显式带上 route 段 |
| `category` | `no_answer` / `hallucination_bait` | `arknights_wiki/eval/metrics.py:9-18` 的 `CATEGORY_ZH` 已注册这两类 |
| `route` / `expected_behavior` | 全部 `"reject"` | `metrics.py:99` 是唯一判定分支：`if expected_behavior == "reject"` 要求答案含拒绝词。既有 100 题满足 `route == expected_behavior` 不变式，本批继续满足。`route` 字段在 eval 侧只被结果行透传，不参与 agent 路由 |
| `source` | `"manual"` | 与 `manual_draft.jsonl` 的人工题目口径一致，明确区别于 `grounded_llm` |
| `answer_key` | `{summary, evidence, kb_check}` | 与既有 100 题同键。`no_answer` 的 `evidence=[]`（弃答题没有正证据）；`hallucination_bait` 的 `evidence` 写「材料文件 + 条目名 + 源文件路径 + 原文」，即反驳前提的真实事实 |
| `kb_check` | `{"kb_checks": [], "kb_all_found": null}` | `kb_all_found=null` 正是 `scripts/generate_benchmark_questions.py:130` 在无 checks 时的产出（`... if checks else None`）。本窗口**未调用**实体索引/LLM，故不伪造 `true` |
| `chapter_check` | `{"checked": 0, "unknown": []}` | 与既有 100 题逐字一致（本批不含章节名断言，`checked=0` 属实） |
| `meta_eval` | `{"quality": null, "issues": ["人工构造题，未运行 LLM 元评估（W11-α T4，待用户抽验）"], "verdict": "skipped"}` | **未运行**元评估，故不写 `verdict: "pass"`。`"skipped"` 是 `generate_benchmark_questions.py:265` 已有的取值。⚠️ 若冻结脚本按 `verdict=="pass"` 过滤，需先对本批跑一次元评估或放行 `skipped` |
| `material_refs` | 只取 `materials/**` 中真实存在的条目名（33 个不同条目） | Spec §3.1 规定 `material_refs` 用 materials 哈希做校验，故不允许自造条目名；已程序化校验 100% 可解析 |
| `difficulty` | 1（6 条）/ 2（15 条）/ 3（1 条） | 与既有 100 题的 1-3 整数口径一致 |
| `requires_tools` | `[]`（8 条）或既有工具名子集 | 弃答题多数无需调工具；实体核查类给 `get_entity_page`，时间线类给 `search_events` / `search_timeline` |

自检命令与结果（可复算）：

```powershell
D:\CodexPython312\python.exe -c "import json,collections;o=[json.loads(l) for l in open('benchmarks/arknights_bench/drafts/w11a_new_categories.jsonl',encoding='utf-8') if l.strip()];print(len(o),collections.Counter(x['category'] for x in o),len({x['id'] for x in o}))"
# → 22 Counter({'no_answer': 11, 'hallucination_bait': 11}) 22

D:\CodexPython312\python.exe -m arknights_wiki.eval.runner --bench benchmarks/arknights_bench/drafts/w11a_new_categories.jsonl --dry-run
# → 题目: 22 条（全类别）· corpus sha256 48d9315465302da51f8639bc · [dry-run] 未写出任何文件
```

---

## 1. 逐题抽验表

| id | 类别 | 问题摘要 | 判定依据（真实事实 or 缺失证据） | 我实际运行的校验 | 置信度 |
|---|---|---|---|---|---|
| no_answer_reject_001 | no_answer | 「罗德岛」号陆行舰最大航速多少节 | 缺失：材料只记罗德岛号的功能与来历，全语料无任何性能参数 | 三源子串计数 `航速/续航里程/时速/排水量/吨位/公里每小时/km/h` 全 = 0；阳性对照 `陆行舰` = 50 | 高 |
| no_answer_reject_002 | no_answer | 源石技艺的能量转化效率是多少 | 缺失：材料只给定性描述（体系/分类/适应性），无效率数值 | `转化效率/能量转换效率/转换效率/转化率/能效` 全 = 0；对照 `源石技艺` = 1810 | 高 |
| no_answer_reject_003 | no_answer | 矿石病从感染到发病的潜伏期多长 | 缺失：材料有早/中/晚三期病程与崩解，但无潜伏期时长 | `潜伏期/潜伏天数/潜伏时间` = 0；另对 `潜伏` 的 50 处命中**逐条打印上下文**，全部是特工/身形隐蔽，无一是疾病潜伏期 | 中 |
| no_answer_reject_004 | no_answer | 切尔诺伯格事件前的常住人口 | 缺失：材料给了炎国约三亿、龙门约四百万，恰未给切尔诺伯格 | `常住人口/人口普查/居民人数/常驻人口` = 0；再以 `切尔诺伯格`/`切城` 为中心 ±60 字窗口匹配数量词，仅 10 段且均为行号区间/事件名，无人口数 | 高 |
| no_answer_reject_005 | no_answer | 罗德岛在编干员总数 | 缺失：材料只记部门设置（外勤/医疗/工程/人事/后勤）与工牌凭证，无编制人数 | `干员总数/在编干员/干员人数/员工人数/在册干员` 全 = 0；对照 `干员` = 1789 | 高 |
| no_answer_reject_006 | no_answer | 泰拉各国货币之间的官方汇率 | 缺失：参考材料无任何货币/比价设定 | `汇率/货币汇率/兑换比例` 全 = 0；另查 `货币`（31 处）全部为泛称或个别币种，无两两比价 | 中 |
| no_answer_reject_007 | no_answer | 天灾信使对天灾的预警准确率 | 缺失：材料说天灾信使负责预警并首创危机合约、明说预报有误差，但无准确率 | `准确率/正确率/预警准确/命中率` 全 = 0；对照 `天灾信使` = 411 | 高 |
| no_answer_reject_008 | no_answer | 「乌萨斯国家科学院」设在哪座城市 | 缺失：该机构在全语料中不存在 | `乌萨斯国家科学院/乌萨斯科学院/国家科学院` 全 = 0；阳性对照 `皇家科学院` = 55，逐条看全部指**维多利亚**皇家科学院（伦蒂尼姆） | 中 |
| no_answer_reject_009 | no_answer | 「石棺」最初由谁制造 | 缺失：材料只说石棺是切城研究所研究对象、源自切城的古代能源装置、事故后转移且去向不明 | `石棺的制造者/石棺的建造者/制造了石棺/建造了石棺/石棺由谁` 全 = 0；`石棺` 855 处命中逐条看均不含制造者 | 高 |
| no_answer_reject_010 | no_answer | 源石的化学式是什么 | 缺失：材料只从能量/工业/医学角度描述源石，无化学式 | `化学式/分子式/元素周期表/原子序数` 全 = 0；对照 `源石` = 7814 | 高 |
| no_answer_reject_011 | no_answer | 「第一届泰拉万国博览会」在哪座城市举办 | 缺失：该活动不存在；真事件是 `materials/event.json` 的「第一届拉特兰万国峰会」（1099 年，阵营拉特兰） | `万国博览会/泰拉万国/世界博览会` 全 = 0；`博览会` 7 处命中逐条看全部是**汐斯塔商品博览会**（火山旅梦），非万国峰会 | 中 |
| hallucination_bait_reject_001 | hallucination_bait | 企鹅物流总部设在叙拉古？ | 假。真事实：总部在**炎国龙门**（`materials/organization.json#企鹅物流`，源 `v3_wiki/factions/企鹅物流.md`）；meta「国家/地区」=「龙门（叙拉古/汐斯塔多城活动）」，叙拉古只是活动地 | 三源检索材料原文命中「总部位于炎国龙门」；meta 字段直读 | 高 |
| hallucination_bait_reject_002 | hallucination_bait | 莱茵生命总辖是生态科主任缪尔赛思？ | 假。真事实：总辖是**克丽斯腾**（`character.json#克丽斯腾`）；缪尔赛思是**生态科主任**（`character.json#缪尔赛思`）；`organization.json#莱茵生命` 记公司「由总辖构件科领导」 | 三份材料条目原文对读，两个职务互斥 | 高 |
| hallucination_bait_reject_003 | hallucination_bait | 特雷西斯是特蕾西娅的弟弟？ | 假。真事实：**特雷西斯是特蕾西娅的兄长**（`character.json#特雷西斯` 原句：「军事委员会的建立者，特蕾西娅的兄长」）；`#魔王` 亦写特蕾西娅「与兄长特雷西斯……分歧」 | 材料原句逐字比对，两处独立互证 | 高 |
| hallucination_bait_reject_004 | hallucination_bait | 大静谧发生在维多利亚？ | 假。真事实：大静谧 = 1038 年**伊比利亚**灾难（`event.json#大静谧爆发，伊比利亚王国崩溃`；`worldview.json#大静谧`：「1038年降临伊比利亚的海洋灾难」） | 两处材料互证；同材料 meta 涉及国家/阵营 = 伊比利亚，无维多利亚 | 高 |
| hallucination_bait_reject_005 | hallucination_bait | 巫王赫尔昏佐伦在四国战争期间被推翻？ | 假。真事实：巫王**1077 年**被推翻（`event.json#巫王被推翻，双子女皇时代开始`）；四国战争 = **1029-1031 年**（`event.json#高卢-莱塔尼亚战争与四国战争`），相差约半个世纪 | 两条时间线条目 meta 年份直接对读 | 高 |
| hallucination_bait_reject_006 | hallucination_bait | 伊比利亚审判庭建于大静谧之前？ | 假。真事实：审判庭**大静谧之后**建立（`event.json#伊比利亚审判庭建立（大静谧后）`：「成为实际统治机构，将海洋视为诅咒」）；`worldview.json#大静谧`：「促使国教会改组为审判庭」 | 条目名 + 正文因果句双证 | 高 |
| hallucination_bait_reject_007 | hallucination_bait | 石棺事件发生在龙门？ | 假。真事实：发生在**切尔诺伯格（切城）研究所**（`worldview.json#石棺事件`，meta 章节=切城，正文「切尔诺伯格研究所发生的一场……屠杀」；`#石棺`：「源自切尔诺伯格的古代能源装置」） | meta 章节字段 + 正文地点双证；`龙门` 未出现在这两条 | 高 |
| hallucination_bait_reject_008 | hallucination_bait | 龙门近卫局是魏彦吾的秘密武装？ | 假。真事实：近卫局是**公开政府执法机构**（`organization.json#龙门近卫局`，meta 类型「organization（政府执法机构）」）；魏彦吾的秘密武装是**黑蓑**（`#龙门特殊部队（黑蓑）`：「独立于近卫局的秘密武装力量」） | 两条目类型字段 + 黑蓑原句「独立于近卫局」直接反驳 | 高 |
| hallucination_bait_reject_009 | hallucination_bait | 深海猎人是罗德岛下属小队？ | 假。真事实：深海猎人 = **阿戈尔精英战斗组织**（`organization.json#深海猎人`，meta 类型「organization（阿戈尔精英战斗组织）」、国家/地区「阿戈尔、伊比利亚」；成员为阿戈尔技术执政官与精英战士），与罗德岛是**合作**关系 | meta 类型/国家字段 + 正文「阿戈尔的技术执政官和精英战士」+ 凯尔希促成合作段 | 高 |
| hallucination_bait_reject_010 | hallucination_bait | 卡兹戴尔军事委员会是维多利亚的机构？ | 假。真事实：是**萨卡兹/卡兹戴尔的最高军事政治机构**，1031 年由战争议会改组、特雷西斯任最高领袖（`organization.json#卡兹戴尔军事委员会`，meta 类型「organization（萨卡兹最高军事政治机构）」）；它后来赴维多利亚作战才与维多利亚同列 | meta 类型字段 + 正文「卡兹戴尔军事委员会，特雷西斯成为最高领袖」 | 中 |
| hallucination_bait_reject_011 | hallucination_bait | 切尔诺伯格—龙门事件发生在 1090 年？ | 假。真事实：**1096-1097 年**（`event.json#切尔诺伯格—龙门事件`，meta「泰拉历史时间线 · 1096-1097年」，对应主线黑暗时代·上/下）；1090 年是**博士初次苏醒 / 阿米娅与博士共同启程**之年（同文件两条 1090 年条目） | 三条时间线条目 meta 年份对读，1090 被真实事件占用 | 高 |

**汇总**：22 条 = `no_answer` 11 + `hallucination_bait` 11。高置信 17 条、中置信 5 条（`no_answer_reject_003/006/008/011`、`hallucination_bait_reject_010`）、低置信 0 条。

---

## 2. (a) 缺失证据校验：实际运行的命令

### a-1 全语料子串命中计数（主校验）

三个数据源一次性读入内存后做 `str.count`，`0` 即判缺失：

```powershell
$env:PYTHONIOENCODING='utf-8'
$code = @'
import os
MAT='\n'.join(open('benchmarks/arknights_bench/materials/'+f,encoding='utf-8').read() for f in os.listdir('benchmarks/arknights_bench/materials'))
ext=[]
for root,dirs,fs in os.walk('data/extractions'):
    for fn in fs: ext.append(open(os.path.join(root,fn),encoding='utf-8').read())
EXT='\n'.join(ext)
em=open('data/entity_source_map.json',encoding='utf-8').read()
print('lens MAT',len(MAT),'EXT',len(EXT),'EM',len(em),'files',sum(len(f) for _,_,f in os.walk('data/extractions')))
for t in ['航速','续航里程','排水量','吨位','时速','公里每小时','转化效率','能量转换效率','转换效率','转化率','能效',
          '潜伏期','潜伏天数','潜伏时间','常住人口','人口普查','居民人数','常驻人口','干员总数','在编干员','干员人数',
          '员工人数','在册干员','汇率','货币汇率','兑换比例','准确率','正确率','预警准确','命中率',
          '乌萨斯国家科学院','乌萨斯科学院','国家科学院','皇家科学院','石棺的制造者','石棺的建造者','制造了石棺',
          '建造了石棺','石棺由谁','化学式','分子式','元素周期表','原子序数','万国博览会','泰拉万国','世界博览会',
          '博览会','陆行舰','源石技艺','矿石病','切尔诺伯格','天灾信使','石棺','源石','干员','货币']:
    print(f'{t:22s} MAT={MAT.count(t):5d} EXT={EXT.count(t):6d} EM={em.count(t):6d}')
'@
$code | python -
```

实测规模：`materials/**` 146,517 字符 / `data/extractions/**` 8,300,359 字符（2,505 个文件）/ `data/entity_source_map.json` 2,040,174 字符（5,213 个实体）。所有 claimed-absent 词组三源命中数均为 **0**；所有阳性对照（`陆行舰` 50、`源石技艺` 1810、`矿石病` 1641、`切尔诺伯格` 873、`天灾信使` 411、`石棺` 855、`源石` 7814、`干员` 1789）均 > 0，证明检索链路本身有效（不是「搜不到=缺失」的假阴性）。

### a-2 近义/相邻词的上下文逐条打印（判「缺的是那件事，不是那个词」）

```powershell
$env:PYTHONIOENCODING='utf-8'
$code = @'
import os,re
def ctx(term,width=60,limit=100):
    n=0
    for root,dirs,fs in os.walk('data/extractions'):
        for fn in fs:
            p=os.path.join(root,fn); t=open(p,encoding='utf-8').read()
            for m in re.finditer(re.escape(term),t):
                n+=1
                if n<=limit: print('  ',os.path.relpath(p,'data/extractions'),'|',t[max(0,m.start()-width):m.end()+width].replace('\n',' / '))
    print('### total',term,n)
for term in ['潜伏','货币','博览会','平方公里','国土面积','总面积','尺寸','皇家科学院']:
    ctx(term)
'@
$code | python -
```

结论：`潜伏` 50 处全是「特工/化身潜伏」（弗莱蒙特潜伏路德维格大学、宁辞秋潜伏尚蜀、变形者潜伏自救军…），**无一处**是疾病潜伏期 → 支持 003 的缺口语义；`货币` 31 处是龙门币/源石锭/卡列提/哥伦比亚金镑/里弗尔等币种罗列，**无任何两两比价** → 支持 006；`博览会` 7 处全是汐斯塔商品博览会 → 支持 011。另核 `万国峰会`（materials 4 处、`data/extractions` 106 处）——该概念本身被定义为「拉特兰教宗伊万杰利斯塔十一世倡议建立的国际协议实体」、首届会议在拉特兰召开，因此它确实是拉特兰的活动，与 `万国博览会` 不是同一个词，011 的干扰项成立。

### a-3 数值型断言的空间邻域检索（针对 004 人口）

```powershell
$env:PYTHONIOENCODING='utf-8'
$code = @'
import os,re
pat=re.compile('(切尔诺伯格|切城)'); num=re.compile('[0-9０-９一二三四五六七八九十百千万亿]+(万|亿|人|名|平方公里|千米)'); n=0
for root,dirs,fs in os.walk('data/extractions'):
    for fn in fs:
        p=os.path.join(root,fn); t=open(p,encoding='utf-8').read()
        for m in pat.finditer(t):
            seg=t[max(0,m.start()-60):m.end()+60]
            if num.search(seg):
                n+=1; print('  ',os.path.relpath(p,'data/extractions'),'|',seg.replace('\n',' / '))
print('segments with numbers near 切尔诺伯格:',n)
'@
$code | python -
```

结论：命中 10 段，逐条看分别是 `line_range` 里的数字、章节名（「切尔诺伯格事件」）、「一名白头发少年」等，**没有任何人口数**；同时阳性对照 `龙门`「城市人口约四百万」（materials/region.json）、`炎国`「约三亿人口」说明「有人口设定」这件事本身是可检索的，缺的正是切尔诺伯格那一格。

### a-4 关系型候选的尝试与**弃用**（诚实记录）

曾试「两位从未见面的人物」这一类模式，改为「同一文件内是否同时出现两个名字」：

```powershell
$env:PYTHONIOENCODING='utf-8'
$code = @'
import os
files={}
for root,dirs,fs in os.walk('data/extractions'):
    for fn in fs:
        p=os.path.join(root,fn); files[os.path.relpath(p,'data/extractions')]=open(p,encoding='utf-8').read()
files['<entity_source_map.json>']=open('data/entity_source_map.json',encoding='utf-8').read()
for a,b in [('银灰','魏彦吾'),('歌蕾蒂娅','爱国者'),('嵯峨','爱国者'),('黑键','霜星')]:
    hit=[k for k,v in files.items() if a in v and b in v]
    print(f'{a} & {b}: {len(hit)} :: {hit[:6]}')
'@
$code | python -
```

结论：粒度过粗（`v3_seed_db_v3_final.json` 与 `entity_source_map.json` 是全局聚合文件，几乎命中一切组合），**无法证伪「两人从未见过」**。按「无法验证的候选一律丢弃」的规则，这一类候选**全部弃用**，未写进 22 条。

### a-5 materials 内二次确认（保证「不依赖材料外知识」）

```powershell
D:\CodexPython312\python.exe -c "import json,os;d='benchmarks/arknights_bench/materials';M='\n'.join(open(os.path.join(d,f),encoding='utf-8').read() for f in os.listdir(d));[print(t,M.count(t)) for t in ['皇家科学院','万国峰会','第一届拉特兰万国峰会','货币','龙门币','博览会','三亿','四百万','人口']]"
```

实测：`皇家科学院` 2（维多利亚，见 region.json 维多利亚条目）、`第一届拉特兰万国峰会` 2、`三亿` 1（炎国）、`四百万` 2（龙门）、`货币` 0、`龙门币` 0、`博览会` 0。据此把 006/011 的答案要点限定为「材料未给出」的纯否定表述，避免让答案要点依赖 materials 之外的事实；`龙门币` 等币种信息只作为**语料层**旁证写在本评审单里，不写进题目与答案要点。

### a-6 结构自检

```powershell
D:\CodexPython312\python.exe -c "import json,collections;o=[json.loads(l) for l in open('benchmarks/arknights_bench/drafts/w11a_new_categories.jsonl',encoding='utf-8') if l.strip()];old={json.loads(l)['id'] for l in open('benchmarks/arknights_bench/questions_draft.jsonl',encoding='utf-8') if l.strip()};man={json.loads(l)['id'] for l in open('benchmarks/arknights_bench/manual_draft.jsonl',encoding='utf-8') if l.strip()};print(len(o),collections.Counter(x['category'] for x in o));print('dup',len({x['id'] for x in o})!=len(o));print('collide100',{x['id'] for x in o}&old);print('collidemanual',{x['id'] for x in o}&man)"
```

实测：22 条 / `Counter({'no_answer': 11, 'hallucination_bait': 11})` / 无重复 id / 与既有 100 题及 `manual_draft.jsonl` **均无 id 碰撞**；UTF-8 无 BOM、每行一个 JSON 对象、末行有换行；`answer_key` 键集、`material_refs` 条目名解析率 100%（33 个不同 materials 条目）。

---

## 3. (b) 我认为最弱的 3 条

| 排名 | id | 弱在哪 |
|---|---|---|
| 1 | `no_answer_reject_006`（泰拉各国货币官方汇率） | 问句里的核心概念「货币/汇率」在 `materials/**` 中命中为 **0**——也就是说这条题只能靠「材料根本没写过货币」来弃答，而不是靠「材料写了货币但没有汇率」。语料层（`data/extractions/v3_wiki/concepts/龙门币.md` 等）其实有龙门币、源石锭、卡列提、哥伦比亚金镑、里弗尔、卡西米尔币，却确实没有任何比价。风险：评审可能认为这条题超出了「只用 materials 作答」的范围；也可能被 Agent 用「龙门币在泰拉多国被承认但非万能」这类语料层句子答出半个答案。若要更硬，可换成「科罗萨主矿脉已探明总储量是多少」之类有材料锚点的数值缺口。 |
| 2 | `no_answer_reject_008`（乌萨斯国家科学院设在哪座城市） | 「该机构不存在」已被证到 0 命中，但**同类真实机构就在旁边**：`皇家科学院` 55 处命中（维多利亚，材料见 region.json）。边界可争：这既是「无答案」（索引里没有这个实体），也可以被读成「前提错误的易幻觉题」，因此它与 `hallucination_bait` 的归类可能被评审挑战。另外「国家科学院」是现实机构名，泰拉可能只是换了叫法（如「巫妖王庭知识圣殿」「天师府」），"不存在"的强度略低于纯数值缺口。 |
| 3 | `hallucination_bait_reject_010`（卡兹戴尔军事委员会是维多利亚的机构吗） | 反驳链最弱的一条：该条目 meta 的「国家/地区」写的是「**卡兹戴尔、维多利亚**」，字面上半支撑了假前提；真正的反驳只来自「类型 = organization（萨卡兹最高军事政治机构）」这一字段与正文「卡兹戴尔军事委员会，特雷西斯成为最高领袖」。也就是说，材料里确实存在一个能被断章取义的字段——对 Agent 而言这可能是**好**的干扰，但对「前提被权威材料明确否定」的判定标准而言，它不如其余 10 条那样有一句逐字打脸的原句。 |

（另一个次弱项：`no_answer_reject_003` 的缺口是「潜伏期」，但材料确实写了病程分期，所以严格说这题**部分可答**——正确行为是「只答病程 + 明说没有潜伏期」，判分时需要 judge 接受这种半答半弃，规则指标 `metrics.py:100` 的拒绝词白名单（无法/未找到/没有/不存在/知识库/资料/无法回答）足以覆盖本批措辞，但该白名单是**关键词**匹配，措辞一变就可能误判。）

---

## 4. (c) 请人工评审重点复核的点

1. **`meta_eval` 的 `verdict: "skipped"` 是否被下游接受**。本批**没有**跑 LLM 元评估（未调用任何外部 API），我拒绝填 `verdict: "pass"` 以免伪造未执行的检查。请确认冻结脚本（T5）不会按 `verdict=="pass"` 过滤；若会，需要先补跑一次元评估或显式放行 `skipped`。
2. **`route: "reject"` 是否为冻结口径所接受**。`metrics.py:99` 按 `expected_behavior` 分支，`route` 只是透传字段；但 Spec §3.1 写的 `expected_behavior(simple|complex)` 把取值域写成了两个。请确认「以 `metrics.py` 实际分支为准、`expected_behavior=reject` 合法」。
3. **`no_answer` 与 `hallucination_bait` 的归类边界**。本批的切分标准是：*索引里根本没有该实体/该事实 → no_answer*（001-011）；*材料有一句权威原句正面否定该前提 → hallucination_bait*（001-011）。请重点看 `no_answer_reject_008`（不存在机构，但旁边有真机构）与 `hallucination_bait_reject_010`（meta 字段半支撑假前提）这两条是否要换边或改写。
4. **`no_answer_reject_006` 要不要换掉**。见 (b)-1：它的缺口在 materials 层是「整个货币体系都不存在」。若评审要求「no_answer 必须有材料锚点」（即『材料提到该对象的一部分，但缺关键数值』），请把它替换为「科罗萨主矿脉已探明总储量」或「布列斯克矿区之外远北矿区的年产矿石量」一类有锚点的条目（替换前需先跑 a-1/a-2 的缺失校验）。
5. **拒绝措辞与规则指标是否匹配**。`metrics.py:100` 的通过条件是答案含 `无法 / 未找到 / 没有 / 不存在 / 知识库 / 资料 / 无法回答` 之一。本批 22 条的 `answer_key.summary` 都写了「资料/材料中没有…」「不在知识库中」等表述，理论上能被该白名单命中；但若 Agent 改用「暂无记载」「未见相关记录」等**同义但不在白名单**的说法，会被误判为未完成。请决定是否扩建白名单（并注意这是确定性指标，改白名单会改变历史可比性）。
6. **11+11 是否够入冻结集**。Spec §3.2 与 W0 验收标准要求「每类 ≥10 条」，本批 11+11 达标（100 + 22 = 122 ≥ 120）；但它**少于**既有 `manual_draft.jsonl` 的 13+13。请决定冻结时是「只用本批 22 条」还是「与本文件去重后合并」（两者 id 空间已刻意错开，合并不会撞 id：本批为 `{category}_reject_{NNN}`，sibling 为 `{category}_{NNN}`）。
7. **逐条复核材料原句**。每条 `hallucination_bait` 的 `answer_key.evidence` 都写了「materials 文件 + 条目名 + `data/extractions/...` 源文件 + 原文摘录」，评审时可只读 `materials/**` 对应条目即可核对，**无需**打开 2.3 MB 的 `entity_source_map.json`。
