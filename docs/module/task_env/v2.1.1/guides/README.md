# v2.1.1 学习指南

本目录是 v2.1.1 的**教程入口**；每页只负责教学解释、完整例子、预期结果和失败路径。公共字段/默认值/能力仍以 [API](../api/README.md) 和 `task_env/doc/api/` 为权威。

## 学习顺序

| 顺序 | 页面 | 你会得到什么 | 前置 |
| --- | --- | --- | --- |
| 1 | [安装、后端隔离与路径配置](installation-and-start.md) | 选路线、Core/GeoPhys/MJWarp/Isaac 两条安装路径、解释器优先级与排错 | Linux 基础、Python 3.12 |
| 2 | [单环境无渲染 Quickstart](quickstart-state-only.md) | Pendulum、PickCube、Nut 的原 Solution；Nut 普通随机的**预期拒绝**与 `T-NUT-RANDOM` 缺口 | 第 1 页的 Core 环境 |
| 3 | [有头窗口、相机参数与图像](quickstart-rendering.md) | CameraSpec 全字段、GeoPhys Rasterizer 优先的 human/rgb_array、task sensor 与 device 相机区别 | 第 2 页的任一任务 |
| 4 | [device 并行与三后端](quickstart-device-batch.md) | Pendulum/PickCube × MJWarp/GeoPhys/Isaac 六条命令、动作树、same-step/partial reset、整批切换 | CUDA 与对应 worker 环境 |
| 5 | [环境、资产、Robot 与 canonical action](authoring-scenes-assets-robots.md) | 声明→source→binding→Env→Runtime 链、AssetDefinition/EntityInstance、Robot/source recipe/TCP | 第 2 页 |
| 5b | [实现自己的 Controller](custom-controllers.md) | Protocol vs typed compute、默认恒等绑定、命名关节 PD、OSC/模型/reset/验收 | 第 5 页 |
| 6 | [API 详细用法、迁移与排错](api-usage.md) | 签名/类型/单位/返回/异常、记录与独立 reader、Solution、learner 边界、迁移表 | 全部 |

旧 [Panda 本体重力补偿](panda-gravity-compensation.md) 保留为有界实现说明；它只支持 MuJoCo CPU 进程内的 selected PickCube/Nut 位置驱动，其他 provider/worker/固定附件路线拒绝，不替代上面的通用教程。

## 能力与证据语言

- 本教程的代码块按源码/现有 caller 静态核对；**没有在本轮运行 native**。示例能 import 不等于 reset/step 成功。
- 复用历史证据时必须同时给出 task、provider、backend、source/pin、seed/horizon、renderer/Controller 交集；不要用单格成功外推整矩阵。
- `T-NUT-RANDOM` 是**未满足的真实需求**：当前 Nut 只准入 source-bound `ExpertAction`，普通随机数组被拒绝。教程保留预期拒绝例子，不以负例替代正向能力。
- `WAIT_7B_ACCEPTANCE`：7b 正在变化的 BodyWrench 新 producer/transport/API 和最终接收矩阵由 attempt002 回填；正文其余部分已在本轮完成。
- G06 canonical device 能力有界接收；G07 最终九格/版本收口仍待 7b 接收与 attempt002。R3 batch 仍为独立后续项。

## 旧页面归并与导航

本目录原“交付要求”页已转为当前学习导航。历史要求仍可通过原提交和 [v2.1.0 文档](../../v2.1.0/README.md) 恢复；不把旧页删成一条 `current-state` 链接。

| 旧位置/内容 | 当前处置 |
| --- | --- |
| 本页旧“阶段3前必须补齐的新手路线”清单 | 由上面的 6 部分教程取代；历史要求保留在 git 历史，不再作为当前教程正文 |
| [安装与启动](installation-and-start.md) 旧“已有安装/三条路线摘要” | 扩写为唯一安装教程；保留已有多环境事实与未验证边界 |
| 旧 `examples/README.md` 中“四个正式任务无 batch adapter/旧 Pendulum batch 不可用” | 已按 G06 受测 device 路线更正；旧 SB3/RSL/parallel-render 边界继续保留 |
| `task_env/doc/api` 中“统一 Env 并行未适配” | 当前入口/导航已改；历史 accepted 证据仍按版本保留 |
| 旧 PickCube/Nut candidate 与 `BaseTaskEnv` 教程 | 不删除旧兼容/历史记录；当前主线明确为 `make_env` + `SelectedReferenceEnv` + typed Controller |
| 旧 UI `float32`/CUDA 返回说法 | 按当前 render 合同更正为 CPU HWC `uint8`；sensor 自身 dtype/device 单列 |
| [Panda 重力补偿](panda-gravity-compensation.md) | 保留原页；从学习顺序中作为受限专题链接 |

## 生态入口

- 符号级 API：[`task_env/doc/api/index.md`](../../../../../task_env/doc/api/index.md)
- 当前跨边界合同：[v2.1.1 API](../api/README.md)
- 任务/资产/机器人开发：[`declared_marker.py`](../../../../../examples/tasks/declared_marker.py) 与第 5 页
- 记录与读回：[`examples/recording`](../../../../../examples/recording) 与第 6 页
- 资产服务/Agent 设置：[agent setup](../../../../global/agent-setup.md)（不会自动下载模型或安装 SDK）
- 当前状态与证据：[current state](../maintenance/current-state.md)、[能力矩阵](../capabilities/README.md)、[G06 实施总结](../maintenance/g06/implementation-summary.md)
- 诊断/代码边界：[diagnostics and code boundaries](../../../../global/diagnostics-and-code-boundaries.md)
