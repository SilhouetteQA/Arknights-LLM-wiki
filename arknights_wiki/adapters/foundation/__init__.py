"""Wiki 项目本地的 Foundation Adapter 层。

本子包是**项目本地**代码，与 Coding 仓的同名子包各自独立实现，不共享源码；
共享的只有 :mod:`agent_core.contracts` 定义的 DTO / Protocol / Schema。

约定：这里只做"把项目事实搬进契约形状"的事。业务代码不得反向依赖本子包，
也不得把 Foundation DTO 当作业务返回类型。
"""
