# Task Composition

**Import path**：`task_env.tasks.worlds`、`task_env.objects`、`task_env.robots`、`task_env.controllers`、`task_env.assembly`
**任务域**：Task Composition  
**稳定性**：组件扩展接口；具体接口的适用范围见各页
**职责**：将纯描述组件编译为场景及稳定 `TaskReferences`。  
**调用者/消费者**：classic `BaseTaskEnv`、scene compiler；selected 的任务声明和装配也使用相关组件。
**源码**：`task_env/{worlds,objects,robots,controllers,assembly}/`

world、passive object、active agent 的组件 API 只声明资产和稳定名称；controller 是 active agent 的控制接口。编译后的 `TaskReferences` 把名称解析为只读 ID，供 action、observation 和 task definition 消费。

- [Worlds](worlds.md)
- [Passive objects](passive_objects.md)
- [Active agents and control](active_agents_and_control.md)
- [Assembly and references](assembly_and_references.md)

## 构建顺序与阅读路线

从 [Worlds](worlds.md) 和 [Passive objects](passive_objects.md) 的资产定义与实例开始：定义提供可复用几何/物性和来源，Task 实例赋予语义 ID 与初态；静态桌面、可动对象和 Robot 的资源不因同属 Scene 就具有相同控制权限。接着阅读 [Active agents](active_agents_and_control.md)：Robot 声明具名组件、TCP、传动和支持的 Controller，默认 Controller 还须与实际 source 绑定。最后 [Assembly](assembly_and_references.md) 将 Task 请求、source snapshot/closure、Robot composition、Controller 匹配合成运行输入。

构建和解析只产生声明、资源和绑定，不推进物理，也不证明 provider 或任务成功。reset 由环境和 session 物化，step 由 Controller 与 runtime 提交，close 释放来源和 session；渲染选择与 task success 分属其各自 owner。仅按名称注册、或仅检查一个 assembly plan，不能证明实时 writer/native 映射成功。
