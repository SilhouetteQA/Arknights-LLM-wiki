"""Wiki 项目本地 Adapter 层。

本子包是**项目本地**代码，与 Coding 仓的同名子包各自独立实现，不共享源码；
共享的只有 `agent_core.contracts` 定义的 DTO / Protocol / Schema。

子包构成：

```text
facts.py              presence-aware facts 提取（不 import 业务模块，无副作用）
mapping.py            facts → Foundation DTO，边界处映射 ErrorEnvelope
runtime.py            Contract Mode 策略、EvidenceRecord 组装、sink 注入
evidence_sink.py      项目本地 FileEvidenceSink（原子写）
```

约定：这里只做"把项目事实搬进契约形状"的事。业务代码不得反向依赖本子包，
也不得把 Foundation DTO 当作业务返回类型。
"""
