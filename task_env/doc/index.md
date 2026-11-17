# TaskEnv 文档入口

当前（2026-11-17）：v2.1.1已发布，tag固定于`15f85f35`；[发布记录](../../docs/releases/v2.1.1/README.md)和[遗留清单](../../docs/releases/v2.1.1/remaining-work.md)区分已完成范围与后续候选。G01～G06 及 G07 7a/7b 已按各自范围有界接收；7c002 的 GeoPhys Nut 渲染修复与文档补正已通过独立主审的有界接收。5c 和 E00～E16 的旧结案不重开。先读[当前摘要](../../docs/module/task_env/v2.1.1/maintenance/current-state.md)和[优化安排](../../docs/module/task_env/v2.1.1/planning/post-5c-optimization-execution.md)。旧 attempt 的失败／待审文字保留所属历史时点。

## v2.1.1 新手入口与当前范围

从 [v2.1.1 学习指南](../../docs/module/task_env/v2.1.1/guides/README.md) 开始，按“安装 → 无渲染 → 相机/窗口 → device batch → 环境/资产/Robot/Controller → API”学习；[安装与启动](../../docs/module/task_env/v2.1.1/guides/installation-and-start.md) 仍是唯一安装教程。该指南区分未验证的新安装、本轮普通 Nut 有界运行、7b 已接收边界和独立主审状态，不把静态核对写成 native 成功。

Empty、Pendulum、TwoWheel、PickCube 和 NutAssembly 已使用统一 `SelectedReferenceEnv` 及共同 episode owner，`BaseTaskEnv` 是同对象兼容导出。G06 canonical CUDA batch（Pendulum/PickCube × MuJoCo Warp/GeoPhys/Isaac）已有界接收；device `step()`、same-step autoreset、部分 reset、具名相机和 Isaac↔MJWarp 整批切换见 [device 教程](../../docs/module/task_env/v2.1.1/guides/quickstart-device-batch.md)。旧 SB3/RSL/parallel-render 入口是另一套合同，登记或历史运行不证明其已适配。

TaskEnv 现有文档按使用场景导航：

| 读者 | 文档 | 适合解决的问题 |
| --- | --- | --- |
| 新用户 | [学习指南](../../docs/module/task_env/v2.1.1/guides/README.md) | 六部分学习顺序和能力边界 |
| 安装/部署 | [安装与启动](../../docs/module/task_env/v2.1.1/guides/installation-and-start.md) | 新克隆/已有安装、后端隔离、Isaac pip/app、路径优先级 |
| 单环境使用者 | [无渲染 Quickstart](../../docs/module/task_env/v2.1.1/guides/quickstart-state-only.md) | Pendulum/PickCube/Nut 的 reset/step/close、Solution、Nut 随机限制 |
| 训练/采集使用者 | [训练与采集](新手使用训练与采集.md)、[API 用法](../../docs/module/task_env/v2.1.1/guides/api-usage.md) | 单环境、Solution、轨迹与 H5；learner/vector 边界 |
| 渲染使用者 | [相机与窗口](../../docs/module/task_env/v2.1.1/guides/quickstart-rendering.md) | CameraSpec、human/rgb_array、task sensor、device 相机 |
| device batch | [device 并行](../../docs/module/task_env/v2.1.1/guides/quickstart-device-batch.md) | 两任务×三 provider、动作树、same-step/partial reset、切换 |
| 任务/资产开发者 | [环境、资产、Robot](../../docs/module/task_env/v2.1.1/guides/authoring-scenes-assets-robots.md) | 声明、实例、编译、绑定、canonical action |
| Controller 开发者 | [自定义 Controller](../../docs/module/task_env/v2.1.1/guides/custom-controllers.md) | Protocol vs typed compute、默认绑定、PD/OSC/验证 |
| 资产开发者 | [资产导入与二次开发指南](资产导入与二次开发指南.md) | 注册 world、robot、object 并接入 assembly |
| API 使用者 | [API Reference](api/index.md) | 查找公开、扩展、兼容和内部接口的适用范围 |
| 排查／维护开发者 | [诊断与代码边界规范](../../docs/global/diagnostics-and-code-boundaries.md)、[诊断目录](../diagnostics/README.md) | 外部驱动、包装／继承、局部注入与核心职责 |

## 推荐阅读顺序

1. 先查看 [安装](../../docs/module/task_env/v2.1.1/guides/installation-and-start.md) 的支持范围；已准备依赖时从单环境开始，不把旧并行示例当成统一路线能力。
2. 需要训练或录制数据时阅读 [训练与采集](新手使用训练与采集.md) 与 [API 用法](../../docs/module/task_env/v2.1.1/guides/api-usage.md)。
3. 需要创建新任务时阅读 [环境、资产、Robot](../../docs/module/task_env/v2.1.1/guides/authoring-scenes-assets-robots.md) 和 [自定义 Controller](../../docs/module/task_env/v2.1.1/guides/custom-controllers.md)。
4. 需要导入新资产时阅读 [资产导入与二次开发指南](资产导入与二次开发指南.md)。
5. 需要确认函数签名、返回值或生命周期时查阅 [API Reference](api/index.md) 与 [v2.1.1 API](../../docs/module/task_env/v2.1.1/api/README.md)。

## 公开入口

~~~
task_env.make_env(...)          # 单环境
task_env.make_parallel_env(...) # 同构并行环境
task_env.ENV_REGISTRY           # 单环境注册表
task_env.PARALLEL_ENV_REGISTRY  # 并行能力注册表
~~~

TaskEnv 使用者只通过 reset、step、action_space、observation_space、info 和记录器访问环境。solver、Taichi field、runtime private state 和 stage/diagnostic 文件不属于 Quickstart 使用面。

## Diagnostics、文档与 Skill 的边界

[`task_env/diagnostics`](../diagnostics) 保存针对真实入口的验证与证据采集，输入是各脚本声明的配置、已固定 source 与运行预算；输出是对应运行的结果和失败，不能由一次导入或 mock 推导物理成功。native 验证使用既有共享锁和监督器，临时原始数据写 ignored `workspace/` 并保留失败与关闭结果；诊断代码不接管生产 Runtime。`task_env/doc` 解释当前接口，历史日志保留其时点；[TaskEnv Skill](../../.agents/skills/geochora-task-env/SKILL.md) 为维护者指向已有 owner 和验证入口，并非运行时 API。

从仓库根目录执行文档治理检查：

```bash
python .agents/skills/geochora-doc-governance/scripts/validate_docs.py --mode current
```

该命令只检查文档治理，不运行文档中的物理示例；目前已知本地保护日志基准差异见当前状态，新增错误仍须单独处理。
