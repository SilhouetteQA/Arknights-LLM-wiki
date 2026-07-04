# Pass 3 世界观实体提取 — 设计规格

> 状态: 已完成
> 日期: 2026-06-23
> 分支: feature/pass3-entity-extraction

## 一、目标

从《大地巡旅》官方设定集、37 个世界观视频、106 章剧情原文中提取世界观实体（概念/阵营/地点），产出结构化种子库 + 完整 Wiki 页面。

## 二、数据源

| 源 | 规模 | 角色 |
|----|------|------|
| 大地巡旅 | 1.2MB / 12,561 行 / 401 页 OCR | 官方设定集，最权威，地基 |
| 视频字幕 | 37 个 / ~85KB | 主题聚焦，补充和丰富 |
| Pass 1 剧情原文 | 106 章 | 实体链接 + 新实体发现 |

视频元数据包含发布时间，纳入 source_records。

## 三、Pipeline

### Phase 1 — 大地巡旅提取

```
书按 6 章 + 附录切分:
  Ch1: 源石/天灾/矿石病
  Ch2: 泰拉科技
  Ch3: 泰拉生物
  Ch4: 泰拉种族
  Ch5: 国家与地区 (19+国)
  Ch6: 组织 (20+组织)
  附录: 泰拉纪年

  每章 → LLM 提取实体 → 跨章聚合去重 → Seed DB v1
```

### Phase 2 — 视频补充

```
37 视频全量合并 → LLM 提取
  ← 注入 Seed DB v1 作已知实体
  → 丰富已有实体 + 发现新实体
  → Seed DB v2 + 初版 Wiki 页面
```

### Phase 3 — 剧情原文（后续）

```
7 个验证章试跑: 孤星、相见欢、慈悲灯塔、怒号光明、长夜临光、愚人号、火山旅梦
  ← 注入 Seed DB v2 作实体锚点
  → 实体链接 + 新实体发现 + story_events 填充

验证通过后全量 106 章 → 最终 Wiki 页面
```

## 四、概念实体 Schema

### 通用字段

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 主名称 |
| aliases | string[] | 别名/异称 |
| category | enum | 六子类之一 |
| definition | string | 一句话定义，≤80 字 |
| summary | string | 完整描述，≤500 字 |
| story_events | object[] | [{event_name, chapter, role, description}] — Phase 1/2 留空，Phase 3 填充 |
| source_records | object[] | [{source, source_detail, location, publish_date?, confidence}] |

source 枚举: terra_book / video / story_text
confidence 枚举: confirmed / inferred / conflicting

### 六子类分类体系

| 子类 | 说明 | 示例 |
|------|------|------|
| 自然现象/物质 | 泰拉世界的物理/自然基础 | 源石、天灾、活性源石、矿石病 |
| 种族/血脈 | 智慧种族的生物学/文化定义 | 萨卡兹、阿戈尔、库兰塔、提卡兹 |
| 超自然存在 | 超越常态的存在个体或集体 | 巨兽、兽主、海嗣、邪魔、岁兽 |
| 技术/技艺体系 | 系统化的知识和技术体系 | 源石技艺七学派、移动城市技术、炼金术 |
| 社会制度/文化 | 人类社会层面的制度和文化现象 | 拉特兰律法、骑士竞技、天灾信使制度 |
| 特殊地域/异域 | 非常态地理空间或异空间 | 焚风热土、黑流树海、荒域、星荚 |

纳入标准: 属于六子类之一的客观世界实体
排除标准: 情感/品德/角色观点/模糊隐喻（通过分类体系自动拦截）
不设频率门槛: 单次出现的关键信息保留，标注 coverage: single

### 各子类独有字段

**自然现象/物质**

| 字段 | 说明 |
|------|------|
| manifestation | 表现形态/物理特性 |
| origin_hypothesis | 起源假说 |
| related_arts | 关联的源石技艺类型 |

**种族/血脈**

| 字段 | 说明 |
|------|------|
| origin_region | 起源地/主要分布区域 |
| physical_traits | 体貌特征 |
| related_races | 亲缘/衍生种族 |
| oripathy_susceptibility | 矿石病易感性 |
| lifespan | 寿命特征 |

**超自然存在**

| 字段 | 说明 |
|------|------|
| nature | 本质（自然现象/人造/外来/未知） |
| scale | 位阶/规模描述 |
| known_instances | 已知个体或化身列表 |
| relation_to_humanity | 与人类文明的关系 |

**技术/技艺体系**

| 字段 | 说明 |
|------|------|
| underlying_principle | 底层原理 |
| practitioners | 使用群体 |
| spread | 传播范围/普及度 |
| key_applications | 关键技术应用 |

**社会制度/文化**

| 字段 | 说明 |
|------|------|
| origin_nation | 起源国家/地区 |
| characteristics | 制度/文化特点 |
| key_institutions | 核心制度/机构 |
| social_impact | 社会影响 |

**特殊地域/异域**

| 字段 | 说明 |
|------|------|
| location_type | 类型（异空间/极端地貌/边界地带） |
| accessibility | 进入方式/可抵达性 |
| hazards | 危险要素 |
| phenomena | 独特现象 |

### 关系字段

| 字段 | 说明 |
|------|------|
| related_concepts | [{name, relation, desc}] — 不设关系枚举，自由描述 |
| related_factions | [{name, relation, desc}] |
| related_locations | [{name, relation, desc}] |

## 五、阵营实体 Schema

### 通用字段

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 主名称 |
| aliases | string[] | 别名 |
| category | enum | nation / organization |
| definition | string | 一句话定义，≤80 字 |
| summary | string | 完整描述，≤400 字 |
| story_events | object[] | [{event_name, chapter, role, description}] |
| source_records | object[] | [{source, source_detail, location, publish_date?, confidence}] |

### 国家/政权

| 字段 | 说明 |
|------|------|
| government_type | 政体类型 |
| ruler | 当前统治者/领导层 |
| key_figures | [{name, role, description}] — 核心政治人物索引 |
| capital | 首都/核心城市 |
| territory | 疆域简述，含已知移动城市及势力范围 |
| major_races | 主要种族构成 |
| historical_events | [{name, timeframe, description}] — 已知历史进程索引 |
| foreign_relations | [{target_nation, attitude, description}] — 对其他国家/地区态度 |

### 势力/组织

| 字段 | 说明 |
|------|------|
| type | 类型（军事/科研/宗教/商业/佣兵/地下...） |
| parent_nation | 所属国家（可空） |
| leader | 首领/核心人物 |
| headquarters | 总部地点 |
| member_composition | [{name, role, description}] — 人员构成，name 可索引到角色实体 |
| goal | 宗旨/目标 |
| external_relations | [{target, relation_type, description}] — 对外关系 |

### 关系字段

| 字段 | 说明 |
|------|------|
| related_concepts | [{name, relation, desc}] |

## 六、地点实体 Schema

### 通用字段

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 主名称 |
| aliases | string[] | 别名 |
| category | enum | city / facility |
| definition | string | 一句话定义，≤80 字 |
| summary | string | 完整描述，≤300 字 |
| story_events | object[] | [{event_name, chapter, role, description}] |
| source_records | object[] | [{source, source_detail, location, publish_date?, confidence}] |

### 城市/移动城市

| 字段 | 说明 |
|------|------|
| parent_nation | 所属国家/地区（指向国家实体 name，可双向索引） |
| city_type | 类型（移动城市/固定城市/聚落） |
| scale | 规模简述 |
| known_districts | [{name, description}] — 已知分区/区域 |
| key_events | [{name, description}] — 发生于此地的重大事件索引 |

### 设施/建筑

| 字段 | 说明 |
|------|------|
| located_in | 所在城市/地区 |
| facility_type | 类型（军事基地/研究所/医院/监狱/工厂...） |
| owner | 所属阵营/组织 |
| purpose | 用途 |
| key_events | [{name, chapter?, description}] — 在此发生的关键事件索引 |

### 关系字段

| 字段 | 说明 |
|------|------|
| related_factions | [{name, relation, desc}] |
| related_concepts | [{name, relation, desc}] |

## 七、跨实体索引规则

- 国家 territory 中的移动城市 → 指向地点实体（city category）
- 国家 key_figures[].name → 指向 Pass 2 角色实体
- 组织 member_composition[].name → 指向 Pass 2 角色实体
- 组织 parent_nation → 指向国家实体 name
- 城市 parent_nation → 指向国家实体 name
- 设施 owner → 指向阵营实体 name
- 设施 located_in → 指向城市实体 name

## 八、Prompt 设计要点

### Phase 1 (书章节提取)

- 按六子类/两子类/两子类分类提取
- 同一实体在不同章节出现时标记为补充而非重复创建
- 章节内出现的人名/地名/事件名做显式标注
- 附录"泰拉纪年"单独提取时间线事件

### Phase 2 (视频补充)

- 注入 Seed DB v1 已知实体列表
- 指令: 优先丰富已有实体的 summary/独有字段/关系
- 只有确认是新实体时才创建
- 视频发布时间纳入 source_records.publish_date
- **发布时间的上下文意义**: 当视频内容涉及主线剧情演进（如罗德岛的使用与废弃、某个国家的政权更迭、角色的生死状态等），发布时间是判断"视频描述的是转变前还是转变后"的关键依据。常规世界观信息（源石原理、种族特征等）跳过此判断

### Phase 3 (原文提取，后续)

- 注入 Seed DB v2 作实体锚点
- 逐章做实体链接 + 新实体发现
- 填充 story_events 字段

## 九、验证标准

### 7 章试跑 checklist

- [ ] 实体辨析准确: 同名概念被正确区分（如不同语境下的"萨卡兹"）
- [ ] 新实体发现: 原文中出现但书/视频未覆盖的实体被识别
- [ ] 分类合理: 每个实体被归入正确的子类
- [ ] 证据链完整: source_records 准确追溯到原文段落
- [ ] story_events 填充: 超自然存在/地点的事件出场被正确记录

### 全量验收

- [ ] 三层实体（概念/阵营/地点）全覆盖
- [ ] 交叉索引完整性（国家↔城市、组织↔人物、概念↔阵营）
