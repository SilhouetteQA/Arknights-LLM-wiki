# CONTEXT.md — 明日方舟剧情 LLM Wiki

## 领域术语

| 术语 | 定义 |
|------|------|
| **Pass 1** | 剧情骨架提取 — 从原始对话中提取事件/概念/阵营/地点，产出 v1_events/ |
| **Pass 2** | 角色 Wiki 页面生成 — 跨章聚合角色出场→LLM 生成角色百科，产出 v2_characters/ |
| **Pass 3** | 世界观实体提取 — 概念/阵营/地点 Wiki 页面，产出 v3_wiki/ |
| **v3_wiki** | 当前数据基线：1251 概念 + 247 阵营 + 257 地点 + 642 角色，FAISS 6666 向量 |
| **LangGraph Agent** | Phase 4 核心：Query Router → SimpleSearch / ReAct Agent → 7 tools → 流式 SSE 回答 |
| **PRTS 终端** | 前端 UI：双栏 SSE 聊天界面，赛博朋克终端风格 |
| **CASUAL persona** | 固定回答风格：口语化补课，像朋友聊天，避免术语堆砌和事件罗列 |
| **大地巡旅** | 官方设定集《Terra: A Journey》，426 页 OCR 文本，存放于 data/lorebook/ |

## Persona

系统固定使用 **CASUAL** persona：
- 用口语化方式解释，像朋友聊天
- 先给一句话核心答案，再展开细节
- 避免堆砌专有名词，首次出现的术语用一两句解释
- 不要罗列事件清单，把事件融入连贯叙述
- 内容完整性优先，不设字数限制

## 意图分类（7 类）

| 意图 | 典型问法 | 检索策略 |
|------|---------|---------|
| `concept_definition` | "X是什么" | get_entity_page 优先，避免广撒网 |
| `chapter_summary` | "X活动讲了什么" | get_chapter_summary + 对应章节 events |
| `character_profile` | "X的性格/战力" | get_entity_page + search_events(entity=X) |
| `causal_reasoning` | "为什么X会Y" | search_timeline + semantic_search |
| `comparison` | "A和B的区别" | 分别 get_page 两个实体 |
| `fact_lookup` | "X的出生地" | 精确 get_page，简短回答 |
| `list_enumeration` | "有哪些兽主" | search_wiki 宽搜 + 结构化列表输出 |

## 路由规则

- 多实体 / 跨章节 / 世界观概念 → 强制 `complex`（LangGraph Agent 多步检索）
- 包含深度关键词（导致/原因/对比/演变/势力格局）+ cross_arc → `complex`
- 简单事实查询 → `simple`（直接检索 + LLM 回答）

## 实体索引

预构建双向索引 `entity_source_map.json`，数据源：
- Pass 1 事件 (v1_events/)
- 原始故事文本 (data/stories/，仅存储路径，按需读取)
- 干员档案 (operators.json)
- 大地巡旅 (data/lorebook/terra_a_journey/)
- 实体间双向关联（entity↔faction↔location↔character）

## 回答格式约束

- 禁止输出 "[来源N]" 引用标记
- 禁止逐条列举事件（如 "事件1: ... 事件2: ..."）
- 用自己话重新组织，不复制粘贴原文
- 忽略与问题无关的参考资料

## 双旗舰工程化协作语言

**统一契约（Unified Contract）**:
两个旗舰项目共同遵守的数据语义与交互边界；它统一接口含义和元数据格式，但不要求两个项目共用底层实现或状态机。
_Avoid_: 公共实现、万能抽象

**仓库内适配器（In-repository Adapter）**:
位于各自仓库内、负责在统一契约与现有项目实现之间进行转换的边界层；第一阶段通过它保护既有行为。
_Avoid_: 临时胶水、兼容补丁

**共享工程层（Shared Agent Engineering Layer）**:
由统一契约、契约测试以及未来满足门禁后抽取的公共包组成的跨项目工程能力层。
_Avoid_: 统一 Agent、共享领域层

**项目领域层（Project Domain Layer）**:
只属于单个旗舰项目且保留其独立语义的能力集合；Wiki 领域层包含检索、记忆和知识图谱，Coding 领域层包含沙箱、审批和 GitHub 工作流。
_Avoid_: 项目特例、非共享代码

**抽包门禁（Extraction Gate）**:
决定统一契约是否已经稳定到可以抽取为版本化 `agent_core` 公共包的一组量化条件。
_Avoid_: 感觉稳定、目录统一完成

**迭代周期（Contract Iteration Cycle）**:
围绕一个明确契约版本，完成“双仓适配、共享契约测试、原有测试与 Benchmark 验证、问题记录、双仓主分支合并”的完整闭环；用于抽包门禁的第二个周期必须包含由真实接入反馈触发、会影响适配实现的非纯文档型契约变更。
_Avoid_: 自然周、重复运行同一版本

**跨边界数据（Boundary Data）**:
在模型、工具、观测、评测或持久化边界之间传递，并需要被两个项目共同理解和验证的数据；Agent 内部状态不属于跨边界数据。
_Avoid_: 全部运行时状态、领域状态

**扩展边界（Extension Boundary）**:
统一契约中供项目领域层携带命名空间化附加信息的显式出口；公共层不解释其内部语义，连续两个迭代周期被双仓共同使用的扩展字段必须接受公共字段晋升评估。
_Avoid_: 任意额外字段、业务数据垃圾桶

**规范化 Schema（Canonical Schema）**:
由共享数据契约导出并经过确定性规范化的 JSON Schema 表示，用于生成独立于排版和键顺序的内容哈希。
_Avoid_: 原始 JSON 文件字节、人工维护的重复 Schema

**行为契约测试（Behavioral Contract Test）**:
由所有协议实现共同执行、用于验证超时、取消、异常、序列化和版本兼容等运行语义的共享测试；它与 Protocol 的静态接口约束共同定义行为边界。
_Avoid_: 只检查方法签名、项目单元测试替代品

**契约族（Contract Family）**:
围绕同一类跨边界语义组织、可以独立经历迭代周期并接受抽包门禁评估的一组契约；契约集合使用统一版本，契约族不维护独立发布版本号。
_Avoid_: 单个类型、独立发布包

**基础契约（Foundation Contract）**:
为其他契约族提供版本、错误、扩展和兼容性约定的公共基础；其他契约族进入共享包前，其依赖的基础边界必须稳定。
_Avoid_: 全部公共工具、默认基类

**领域保留（LOCAL_BY_DESIGN）**:
某个契约族经过实际共享评估后，确认其语义差异不应由公共层抹平，因而有意保留在项目领域层的成熟结论。
_Avoid_: 尚未完成、抽取失败

**用量（Usage）**:
描述一次边界活动已知的 token 消耗及其整体可信来源；零值表示已知未消耗，空值表示未知，混合来源采用其中最低可信等级。
_Avoid_: 成本、强制补齐的 token 总数

**原始成本（Cost）**:
以原始币种和可追溯计价来源表达的不可变金额；真实零值、未知值和估算值具有不同语义，契约层不执行隐式汇率换算。
_Avoid_: 归一化成本、未知时使用零值

**成本汇总（Cost Summary）**:
表达同一聚合范围内的已知成本小计、统计是否完整以及未知组成项数量；存在未知组成项时，已知小计不得被宣称为完整总成本。
_Avoid_: Cost、忽略未知项的总成本

**旁路契约验证（Shadow Contract Validation）**:
在不改变既有业务决策源的前提下，由仓库内适配器把真实旧路径数据转换为统一契约对象，并仅用于契约校验和证据产出。
_Avoid_: 双主路径、统一对象回写旧路径

**错误信封（Error Envelope）**:
错误跨序列化、API、IPC、MCP、跨仓适配或评测产物边界时使用的稳定数据表示；机器逻辑依据 `code`，它不是异常类型，也不替代任何仓库的内部错误控制流。
_Avoid_: 公共异常基类、内部 Result 返回模式、根据 message 分支

**证据门禁（Evidence Gate）**:
一个契约迭代周期完成前必须同时具备确定性契约测试、历史生产产物回放和当前真实路径运行三层证据；未观察到某种合法语义不等于验证失败，但必须如实标记。
_Avoid_: 只有 fixture、只有一次真实运行、用未观察状态冒充通过

**契约模式（Contract Mode）**:
Phase 1 旁路契约验证的统一运行策略：`off` 完全跳过，`observe` 记录验证结果但不影响业务，`strict` 使用相同适配和校验逻辑并在失败时令验证命令失败。
_Avoid_: 生产严格模式、Foundation 优先的降级开关

**业务不变性（Business Invariant）**:
同一固定输入在 `observe` 与 `off` 模式下应保持一致的既有输出、决策、副作用和旧观测结果；Foundation 新增的验证证据不属于比较对象。
_Avoid_: 只比较最终文本、忽略副作用

**锁步契约集版本（Lockstep Contract Set Versioning）**:
Phase 1 两个仓库共同使用一个契约集版本并在周期结束时对齐；历史证据不可变，但 `0.x` 不承诺跨 minor 版本的运行时兼容。
_Avoid_: 每个契约族独立版本、无迁移说明的不兼容

**契约载荷哈希（Contract Payload Hash）**:
对规范性契约文件束进行跨平台规范化后计算的完整性标识，用于判断两个仓库是否持有同一份契约。
_Avoid_: 证据哈希、直接哈希目录字节

**证据清单哈希（Evidence Manifest Hash）**:
对单个仓库验证某一契约载荷所使用的代码版本、环境和三层证据清单计算的项目独立完整性标识。
_Avoid_: 契约相同性标识、要求双仓相同

**契约分歧（DIVERGED）**:
两个仓库面向相同目标契约版本却产生不同契约载荷哈希的周期状态；项目证据清单哈希不同不构成契约分歧。
_Avoid_: 正常迁移中的版本错位、项目验证结果不同

**规范规则标识（Contract Rule ID）**:
采用“契约族、子域、不可复用序号”组成的稳定标识，用于关联规范文档、共享一致性测试和双仓证据。
_Avoid_: 测试函数名、可重新编号的章节号

**契约冲突（CONTRACT_CONFLICT）**:
同一契约载荷内部的 Pydantic、Enum、Protocol、规范文档、共享一致性测试或生成 Schema 表达出互相矛盾的语义，导致该发布快照无效。
_Avoid_: 双仓载荷不同、普通适配失败

**仓库契约门禁（Repository Contract Gate）**:
单个仓库独立执行的一级门禁，用于证明本仓契约载荷、共享一致性测试和项目适配器自洽，不读取另一个仓库。
_Avoid_: 普通 PR 跨仓拉取、项目完整发布门禁

**跨仓周期门禁（Cross-repository Cycle Gate）**:
Wiki 协调端针对两个固定提交执行的二级门禁，用于核验锁步契约载荷、提交绑定证据和周期完成条件。
_Avoid_: 比较移动主分支、产生新的真实运行证据

**命名空间预留（Namespace Reservation）**:
Phase 1 由两个仓库分别携带相同的 `agent_core.contracts` 本地载荷，以提前稳定未来公共包的导入路径，但不代表已经存在独立 distribution 或共享运行时实现。
_Avoid_: 已完成抽包、namespace package、双份 agent_core 来源

**证据发布边界（Evidence Publication Boundary）**:
契约周期只向 Git 发布由白名单字段重新构造的最小可复现结构化事实；原始 Prompt、模型响应、代码内容、完整 Trace、凭据和私人环境信息保留在受控临时证据范围内。
_Avoid_: 原始日志脱敏副本、全量环境导出、公开原始内容哈希

**生产者注册表（Producer Registry）**:
记录所有已发现 Usage/Cost 生产边界及其稳定标识、范围状态、旧字段、目标契约对象和实际接线证据的范围控制清单。
_Avoid_: 只有文件名的散列表、新发现即自动纳入范围

**已知回归基线（Known Regression Baseline）**:
在契约改造开始前，以唯一权威命令记录的测试通过、跳过与已知失败集合；后续门禁要求不得新增失败，并要求已知失败的测试标识与根因保持可追踪，但不把范围外旧故障伪装成新改造的成功或失败。
_Avoid_: 要求脱离现状的全绿、只比较失败数量、顺手修复范围外旧故障

**失败指纹（Failure Fingerprint）**:
由测试 nodeid、异常类型与规范化错误关键信息构成的稳定基线标识；它用于确认既有失败的身份和根因未漂移，不包含完整堆栈、临时路径或易变行号。
_Avoid_: 完整 traceback 哈希、只比较失败数量

**周期非侵入门禁（Cycle Non-intrusion Gate）**:
在固定输入和固定模型响应下，精确比较 `off` 与 `observe` 的既有输出、决策、副作用和旧观测结果，用于证明旁路契约接入没有改变业务行为。
_Avoid_: 随机 LLM 分数精确相等、历史 Benchmark 冒充当前基线

**契约族抽取质量门禁（Family Extraction Quality Gate）**:
在抽取代码前冻结可复现 BenchmarkSpec 与不可变基线，再以相同配置验证候选公共包；质量指标使用预先登记容差，安全与副作用不变量零容忍。
_Avoid_: 抽包后补基线、事后调整容差、以质量提升抵消安全违规

**暂存契约证据（Staging Contract Evidence）**:
由项目内 EvidenceSink 原子写入、尚未经过发布聚合的逐事件契约证据；它仍受白名单、容量和敏感内容禁入约束，不包含原始业务载荷。
_Avoid_: 原始 Prompt 或 Trace、可直接发布的 release artifact

**行为保持型边界重构（Behavior-preserving Boundary Refactor）**:
仅为形成稳定观察接缝、提取 Usage/Cost 事实、改善依赖注入或复用窄旁路 helper 而调整既有结构，并以业务不变性证明外部语义未改变。
_Avoid_: 零代码改动、全仓成本服务重写、Foundation 接管业务计算

**存在性感知事实提取（Presence-aware Facts Extraction）**:
从原始 provider 或旧运行时状态中分别保留字段是否出现、实际值、来源和计价证据，再交给 Adapter 构造 Foundation 对象；旧系统为方便计算填入的默认值不自动成为事实。
_Avoid_: `getattr(..., 0)`、从 legacy total 反推组成项、把存储位置当作可信来源

**载荷描述符（Payload Descriptor）**:
位于 `agent_core.contracts` 规范载荷内部、在载荷总哈希计算前即可完整生成的机器目录，记录契约版本、工具版本、Schema 哈希和规范规则集合，但不记录载荷自身哈希或治理成熟度。
_Avoid_: 外部发布清单、自引用哈希、契约族生命周期状态

**候选提交（Candidate Commit）**:
包含契约载荷、项目适配、接线代码、测试和配置并作为验证对象的固定提交；最终证据不得声称验证包含自身的提交。
_Avoid_: Evidence Publication Commit、移动 main、验证后继续修改代码

**证据发布提交（Evidence Publication Commit）**:
在候选提交之后仅按发布白名单增加净化证据与清单的提交；Evidence Manifest 的 `verified_repository_commit` 指向候选提交，不保存自身提交或自身哈希。
_Avoid_: 被验证代码提交、夹带业务代码变化、覆盖失败证据

**最终化提交（Finalization Commit）**:
Phase 1 仅由 Wiki canonical 仓在跨仓协调通过后，以严格白名单持久化 cycle report 与当前发布指针的提交；协调通过本身不等于周期完成。
_Avoid_: Coding 重复最终化、修改既有证据、记录自身提交哈希

**规格深度（Specification Depth）**:
按照证据成熟度限定文档的执行含义：`IMPLEMENTATION-READY` 可直接实施，`FEEDBACK-BOUND` 只规定真实反馈驱动的演进流程，`GATE-DEFINED` 只规定未来进入条件而不授权实现。
_Avoid_: 把路线愿景当作当前任务、预写未经证据支持的未来接口

**最终化就绪（READY_FOR_FINALIZATION）**:
两个固定 Candidate/Evidence 提交已通过跨仓协调，但 canonical Cycle Report 尚未由 Wiki Finalization Commit 持久化的中间状态。
_Avoid_: Cycle COMPLETE、协调失败、可继续修改 Candidate

**周期完成（Cycle COMPLETE）**:
跨仓协调已经通过，且一致的 Cycle Report 与当前发布指针已由合法 Wiki Finalization Commit 合并；只有该状态才能宣称该 Contract Iteration Cycle 完成。
_Avoid_: Local CI 通过、Fresh Smoke 通过、READY_FOR_FINALIZATION

**子规格执行投影（Child Spec / Execution Projection）**:
从 Master Spec 投影出的单个可验收工作单元；它在操作上自包含，但只引用而不重新定义规范语义。
_Avoid_: 独立规范真相源、强制对应一个 Git commit

**规格冲突（SPEC_CONFLICT）**:
子规格执行投影与 Master Spec 对同一规则给出矛盾要求，导致执行必须停止并进行规范协调的状态。
_Avoid_: 以更具体文档优先、执行者自行选择语义、普通实现故障

**规格不完整（SPEC_INCOMPLETE）**:
完成当前工作所需的契约语义在子规格与 Master Spec 中均未定义，因而不能由执行者凭经验补全的状态。
_Avoid_: Master 已有明确引用、一般代码细节、擅自新增公共字段

**执行状态事件（Execution Status Event）**:
描述某个子规格真实状态转换及其原因和证据引用的结构化事实；事件只引用已经存在的对象，不记录包含自身的提交身份。
_Avoid_: 自由进度日志、Markdown Current Status、包含自身 commit 的事件

**执行状态账本（Execution Status Ledger）**:
仅由 Wiki canonical 仓维护的 append-only 状态事件集合，是子规格动态执行状态的唯一真相源。
_Avoid_: Coding shadow copy、实时数据库、可重写状态文件

**状态归约器（Status Reducer）**:
从子规格 Initial Status 和按顺序追加的合法状态事件确定性计算当前状态的 Candidate-bound 工具；它不采用“最后一行赢”掩盖非法转换。
_Avoid_: 人工选择当前状态、B/C 阶段临时修改规则

**候选冻结（Candidate Freeze）**:
Spec 11 将 Contract、实现、测试、验证工具、配置与 workflow 固定为 Candidate A 的边界；冻结后只允许执行既有能力和发布允许的 Evidence/协调产物。
_Avoid_: 代码完成但仍可修改、只冻结业务代码、不冻结验证工具

**规格状态冲突（SPEC_STATUS_CONFLICT）**:
执行状态账本无法依据规定状态机、DAG、执行权限和 Evidence 要求唯一合法归约时的治理失败。
_Avoid_: 普通 BLOCKED、00 与子文件文本差异、最后事件自动覆盖

**候选已取代（Candidate Superseded）**:
冻结后的 Candidate 因代码、契约、测试或验证工具缺陷不再具备继续取证资格，必须回到所属前置子规格形成新的 Candidate。
_Avoid_: 在原 Candidate 上热修、Evidence publication defect、Coordinator defect
