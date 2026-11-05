# TaskEnv 文档入口

## v2.1.1 新手入口与当前范围

从[安装与启动指南](../../docs/module/task_env/v2.1.1/guides/installation-and-start.md)选择新克隆或已有安装路径，并查看解释器、simulator／renderer、资产与启动脚本的要求。该指南标明尚未验证的新安装和native路线；[实施记录](../../docs/module/task_env/v2.1.1/planning/pre-stage3-environment-refactor.md)中的单环境生命周期与限定核心收尾已有限接收，更广整理仍有边界。

Empty、Pendulum和TwoWheel已使用统一`SelectedReferenceEnv`及共同episode owner，`BaseTaskEnv`是同对象兼容导出；组件RuntimeBoundary与selected RuntimeSession仍有各自接线。Pendulum范围为单环境；旧并行API、注册和脚本保留，不代表统一路线已适配。并行适配和真实多环境验证留待阶段6，不以单slot或静默降级代替。

TaskEnv现有文档按使用场景导航：

| 读者 | 文档 | 适合解决的问题 |
| --- | --- | --- |
| 使用者 | [安装与启动](../../docs/module/task_env/v2.1.1/guides/installation-and-start.md) | 单环境、已有路径和未验证的安装缺口 |
| 训练/采集使用者 | [训练与采集](新手使用训练与采集.md) | 单环境、Solution、轨迹与 H5 数据；训练限制 |
| 任务开发者 | [自定义任务构建指南](自定义任务构建指南.md) | 从声明式示例理解任务、reset、评价与 Solution |
| 资产开发者 | [资产导入与二次开发指南](资产导入与二次开发指南.md) | 注册 world、robot、object 并接入 assembly |
| API 使用者 | [API Reference](api/index.md) | 查找公开、扩展、兼容和内部接口的适用范围 |
| 排查／维护开发者 | [诊断与代码边界规范](../../docs/global/diagnostics-and-code-boundaries.md)、[诊断目录](../diagnostics/README.md) | 外部驱动、包装／继承、局部注入与核心职责；诊断代码如何动工和归位 |

## 推荐阅读顺序

1. 先查看[安装与启动](../../docs/module/task_env/v2.1.1/guides/installation-and-start.md)的支持范围；已准备依赖时从单环境开始，不把旧并行示例当成统一路线能力。
2. 需要训练或录制数据时阅读 [训练与采集](新手使用训练与采集.md)。
3. 需要创建新任务时阅读 [自定义任务构建指南](自定义任务构建指南.md)。
4. 需要导入新资产时阅读 [资产导入与二次开发指南](资产导入与二次开发指南.md)。
5. 需要确认函数签名、返回值或生命周期时查阅 [API Reference](api/index.md)。

## 公开入口

~~~
task_env.make_env(...)          # 单环境
task_env.make_parallel_env(...) # 同构并行环境
task_env.ENV_REGISTRY           # 单环境注册表
task_env.PARALLEL_ENV_REGISTRY  # 并行能力注册表
~~~

TaskEnv 使用者只通过 reset、step、action_space、observation_space、info 和记录器访问环境。solver、Taichi field、runtime private state 和 stage/diagnostic 文件不属于 Quickstart 使用面。
