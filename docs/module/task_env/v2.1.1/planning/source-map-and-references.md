# 当前 owner、缺口与参考

只读定位日期：2026-11-03，Core `fd03817c`、GeoPhys `67da1165`。本页是派包前的定位入口，具体方法和生产 caller 须随实际 HEAD 重核。CodeGraph 用于定位；源码、调用者与原始证据优先于索引摘要和旧计划。

## 优先复用的 owner

| Concern | 源码入口 | 当前基础／待补齐 |
| --- | --- | --- |
| 公共构造／配置 | [registry](../../../../../task_env/registry.py)、[configuration](../../../../../task_env/environment/configuration.py)、[声明](../../../../../task_env/environment/task_definition.py)、[source](../../../../../task_env/environment/task_source.py)、[assembly compiler](../../../../../task_env/assembly/compiler.py) | 已有 make_env 和配置优先级；公共 TaskDefinition 仍有兼容路径，需沿真实 caller 迁移 |
| 唯一 selected 生命周期 | [reference_env](../../../../../task_env/tasks/reference_env.py) | 当前 selected reset／step／record／close；非任意 reset 配置切换 |
| physics admission／session | [api](../../../../../task_env/runtime/sessions/api.py)、[control](../../../../../task_env/runtime/sessions/control.py)、[contracts](../../../../../task_env/runtime/contracts.py) | RuntimeSession、manifest、受限准入；阶段 profile 特判不能直接删除 |
| 三后端原生翻译 | [MuJoCo](../../../../../task_env/runtime/sessions/mujoco.py)、[GeoPhys](../../../../../task_env/runtime/sessions/geophys.py)、[native session](../../../../../task_env/runtime/sessions/native_io.py)、[Isaac IO](../../../../../task_env/runtime/sessions/isaac_native_io.py) | CPU 两路线及精确 Isaac CUDA／PhysX 路线；不能外推任意资产 |
| 当前控制器 | [canonical contracts](../../../../../task_env/controllers/canonical/contracts.py)、[R3](../../../../../task_env/controllers/canonical/production_r3.py)、[位置 profile](../../../../../task_env/controllers/canonical/position_profile.py) | R3 输出 q_ref，native servo 仍施控；具名 mixed 通道已有基础，非普遍 effort |
| benchmark 控制与模型 | [LIBERO OSC](../../../../../bench_deploy/libero/controllers/osc.py)、[参考动力学](../../../../../bench_deploy/libero/controllers/source_gravity.py) | 有 arm torque＋finger position；参考模型依赖 MuJoCo，未推进第二套物理；不整体搬入 Core |
| render／camera | [backend registry](../../../../../task_env/render/tools/backend_registry.py)、[single provider](../../../../../task_env/render/providers/single.py)、[camera API](../../../../../task_env/render/camera/api.py)、[camera source](../../../../../task_env/render/camera/source.py) | 已有窗口、camera 和多种 backend 入口；selected 仍 state-only，不能只加配置字段 |
| batch | [scene batch](../../../../../task_env/runtime/scene_batch.py)、[GeoPhys batch](../../../../../task_env/runtime/providers/geophys/rigid_batch.py)、[parallel render](../../../../../task_env/render/providers/parallel.py) | 有既有原生／通用批量基础，接入 selected 的真实范围在 1a 核实 |
| 记录与读回 | [recorders](../../../../../task_env/recorders/contracts.py)、[canonical H5](../../../../../task_env/trajectory/canonical/h5.py) | 保持已有 schema、单一 Recorder；episode 配置与新数据身份要接通 |
| 任务和 Solution | [PickCube](../../../../../task_env/tasks/pick_cube/solution.py)、[PickCube specialization](../../../../../task_env/tasks/pick_cube/specialization.py)、[NutAssembly](../../../../../task_env/tasks/nut_assembly/solution.py) | 任务策略留在原 owner；成功参考未证明，不以控制器命名推断根因 |

provider 实现公开能力的 owner 仍在其项目内。Core 不访问 solver／renderer 私有 field；不为统一接口另外维护第二套状态或循环。

## 当前事实和待决定项

历史结果查 [v2.1.0 matrix](../../v2.1.0/capabilities/capability-matrix.json)。有界接收、原生驱动例外、0/9 task-success、A123 限定偏差与未测量项全部保持。版本文档含原候选状态文字；本轮只纠正当前导航和可核实来源，不重写历史记录。

| 编号 | 待冻结问题 | 负责子阶段 | 当前建议／约束 |
| --- | --- | --- | --- |
| D01 | 首批三个物理路线的精确 renderer、资产和版本 | 1a、1d | 原生优先，GeoPhys×MuJoCo 为首跨组合候选；失败须提出有依据的替代 |
| D02 | 统一表示映射到哪些现有 schema，保留哪些兼容输入 | 1b | 优先扩展现有 owner，不凭讨论新建完整物理语言 |
| D03 | 夹爪 effort、传动、mimic／tendon 和现有 native 兼容路由 | 1c、4a | 逐通道声明；不能把 arm torque＋finger position 称为全 effort，不重开 F05 严格等价研究 |
| D04 | 模型服务的库依赖、反馈频率和缺失能力 | 1c、4a | Controller 不依赖 live provider 私有状态；可替换参考模型依赖需显式记录 |
| D05 | batch 的具体两个以上后端、auto-reset 及图像布局 | 1a、1d、6a | 至少两后端、至少一条 native batch；选择一种明确支持的 auto-reset 语义即可 |
| D06 | 数值准入和跨后端容差 | 1a、1c | 本版首批刚体资产逐项约定质量／惯性／约束／reset／稳定性；未测量不填 PASS |
| D07 | 具体 API 签名、action-space 变更和旧 wrapper 兼容 | 1c、1d、4c | obs 固定；动作规格变化显式报告，不承诺旧 Agent／learner 无缝继续 |

这些是协议／执行准备工作，不要求维护者提前指定类名、库实现或全部数值。需要产品语义判断时在该项讨论中集中提出，不能静默替维护者改变范围。

## 官方参考与采用边界

以下页面于 2026-11-03 查阅。`main`／`latest` 为可变来源，派实施包时必须核对本机版本、具体 API、依赖与许可证；参考项目能力不是 GeoChora 验收证据。

| 项目／来源 | 借鉴点 | 本版采用边界 |
| --- | --- | --- |
| [Newton ModelBuilder](https://newton-physics.github.io/newton/latest/api/_generated/newton.ModelBuilder.html) | 构建、Model、State、Control 和 world 布局的分离 | 支持路由和状态协议设计；不承诺接通 Newton |
| [Genesis Engine](https://genesis-world.readthedocs.io/en/latest/api_reference/engine/index.html) | 场景内 solver、材料和 coupler 的归属 | 能力需表达相互作用；不由两种材料存在推断耦合可用 |
| [Isaac Lab Scene Data Provider](https://docs.nvidia.com/isaaclab/concepts/scene-data-provider) | 公开几何／变换、重排、数据格式与消费者需求 | 复用现有公开数据 owner，避免 task／renderer 读取 physics 私有存储 |
| [Isaac Lab Actuators](https://isaac-sim.github.io/IsaacLab/main/source/concepts/actuators.html) | 显式／隐式 PD、effort 计算和限幅区别 | 迁移需重新验证，增益相同不保证响应相同 |
| [Gymnasium Env](https://gymnasium.farama.org/api/env/) | render_mode、metadata、human／rgb_array 与 close | 保持熟悉调用习惯；本项目 reset 换配置属于显式扩展，不能冒称完全兼容所有 wrapper |
| [Farama Vector Autoreset](https://farama.org/Vector-Autoreset-Mode) | 终止观测与 reset 首帧的语义区别 | 选择并公布支持方式，保护 Recorder 和 learner 边界 |
| [SOFA Mapping](https://sofa-framework.github.io/doc/simulation-principles/multi-model-representation/mapping/) | 机械、碰撞和视觉表示之间的映射 | 只准备资产表示边界，不实施 SOFA 后端或非刚体自动适配 |

实施记录须保存实际采用／拒绝方案与理由；不能把外部通用架构直接复制成重复 Runtime、manager 或大型抽象层。
