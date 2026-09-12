# Task Composition

**Import path**：`task_env.worlds`、`task_env.objects`、`task_env.robots`、`task_env.controllers`、`task_env.assembly`  
**任务域**：Task Composition  
**稳定性**：Public API / Extension API  
**职责**：将纯描述组件编译为场景及稳定 `TaskReferences`。  
**调用者/消费者**：`BaseTaskEnv`、scene compiler。  
**源码**：`task_env/{worlds,objects,robots,controllers,assembly}/`

world、passive object、active agent 的组件 API 只声明资产和稳定名称；controller 是 active agent 的控制接口。编译后的 `TaskReferences` 把名称解析为只读 ID，供 action、observation 和 task definition 消费。

- [Worlds](worlds.md)
- [Passive objects](passive_objects.md)
- [Active agents and control](active_agents_and_control.md)
- [Assembly and references](assembly_and_references.md)
