# G05 5c 人工诊断与统一中间层重构路线

日期：2026-11-08。状态：`MAINTAINER_DIRECTED_DIAGNOSIS_PLANNED`；这是 Sol 基于维护者最新要求、原 7 阶段计划与当前源码所作的实施次序和范围规划，不是已启动的实施 Goal、native/source/SDK/GPU/GUI 授权或自动派包。

维护者要求以多个必要的人工诊断窗口解决受控主体、Controller、Runtime、renderer 和公共诊断耦合的实质问题，最终完成 5c，并为 G06 并行提供统一的标量契约。原 5c 三个普通 attempt 的结果与失败保留；本次是维护者明确指定的 post-limit 人工诊断，不新造普通 attempt 004 或清零原计数。诊断 attempt 没有固定次数上限；**下面是依赖顺序中的工作单元，不机械对应 attempt 数量**。一个已授权窗口可以完成多个紧邻单元；有新发现可调整次序，同一窗口内解决正常错误与受影响检查；每个窗口冻结实际 HEAD、写入/操作范围、资源、完整交付和释放，由维护者指定实施者并手动转发，Sol 独立主审。反复无进展时重新评估，不把 ACK、fake、图或文档当作真实闭环。

## 计划基准与当前事实

- 基准 checkout `/home/lly/.codex/worktrees/v210-integration/Geochora`，branch `codex/v211-stage5`，本计划起草时 HEAD `7f83200f`，GeoPhys `c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7`，Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`；准备实际工作包时必须重新绑定真实 HEAD、pins、writer、双锁及保护输入，不以本值覆盖后续结果。
- 权威为 [统一任务表示](../contracts/unified-task-representation.md)、[控制协议](../contracts/control-and-feedback.md)、[physics](../contracts/physics-provider.md)、[render](../contracts/render-provider.md)、[生命周期和数据](../contracts/lifecycle-and-data.md)、[G03](../goals/03-backends.md)、[G04](../goals/04-control.md)、[修订后 G05](../goals/05-rendering.md)、[G06](../goals/06-parallel.md)、[G07](../goals/07-integration.md)。1–4、5a、5b 按各自记录有界接收，不重写历史；受本轮修改的共享能力需要定向回归。G06 尚未启动。
- `BaseTaskEnv` 现为 `SelectedReferenceEnv` 别名，但 Pendulum/双轮车走 component bootstrap + `GeoPhysRuntimeBoundary`，并没有自动走 selected 的 `RuntimeSession` 路由；当前不能声称这两任务已支持 MuJoCo 或 Isaac。Isaac F06 exact source/representation/admission 本来就有严格限定，不能靠改注册或删 guard 扩大能力。source 与 SDK 的可用性交集须逐项核实。
- 5c attempt001 四条 PickCube 同步 RGB 真机证据、003 的 MuJoCo／GeoPhys／GeoPhys→MuJoCo 与 Pendulum 组件结果按各自 source/代码/时钟身份有界保存；003 的通用 reset 强制调用只接受 `RuntimeSource` 的 MuJoCo renderer-only 绑定，阻断 Isaac `UsdRuntimeSourceV1` task RGB。参见 [003 主审](../maintenance/reviews/20261108_5c_attempt003_sol_review.md)。5b 已接收，不重开。
- Panda 现有重力补偿不是空白：默认关闭，仅已证的 MuJoCo CPU 一体 Panda selected PickCube/Nut 限定交集可启用，依真实 source、固定基座与 position-drive 特性计算并记录贡献；通用装配树/跨实体、其他 provider 未完成。参考 [指南](../guides/panda-gravity-compensation.md)及[装配树提案](gravity-compensation-assembly-tree.md)。保留默认关闭及已支持配置，不能把位置目标偏移重命名成通用 effort 或声称其他 provider 通过。
- 一体 Panda、Panda 裸臂＋独立夹爪、Pendulum、双轮车的**统一主体构建与 Controller 接入**现由维护者明确提前作为 5c 诊断目标；这不等于将原附加用例的两任务 × 两机器人完整 Solution 成功从 7a 改到 5c。原 [装配 Panda 7a 用例](stage4-assembled-panda.md)的完整成功/跟踪/独立记录门继续保留；若当前不能构建或驱动装配主体，5c 的新主体统一目标不能宣称完成。
- 原 G07/7a 安排诊断耦合集中收口。维护者现要求在进入并行化前，先处理**本轮所触及且阻碍统一公共链的**实验探针、代码越权和冗余判断；其他未涉及项仍登记供 7a，不扩大成无界全库清理。

## 共同目标和调用链

```text
任务配置 / TaskDefinition / Solution
    → Scene 与资产声明 + 一个或多个受控主体 + 可选被动物体
    → 同一主体／嵌套 Assembly 与具名关节、Frame、Actuator 绑定
    → 主体声明可匹配 Controller → Controller 接受 robot action
    → 具名、带单位/时钟/来源的 canonical 控制命令
    → 同一 Runtime 契约 / provider adapter / 单一物理提交
    → 当前 published state + boundary + clock
    → task 语义和 observation；renderer adapter 独立消费状态并同步 RGB
```

一个逻辑控制边界不意味着只有一个 Controller；多个 Controller 可以作用不同通道或按明确规则组合，必须防冲突/重复施力。一个公共 Runtime **契约和明确的物理 owner**不意味着所有 Env 共享一个进程或各 provider 共用一个 native 类；batch 可复用底层批处理资源。renderer-only visual model 不得成为第二 physics stepper。USD/MJCF 等保留各自版本化 representation/closure 与 adapter，不强制转换为同一个文件格式；公共生命周期/任务/state 不根据具体 renderer/source Python 类型泄漏专有语义。

`robot action` 是选定 Controller 接受的外部输入；`canonical action` 是与具体语义、目标和单位相符的通用中间命令，不等同于一个固定维度数组，也不预设所有 Controller 都产出 torque。复用已确认的 `JointEffortV1`、`BodyWrenchV1`、position compatibility 与贡献组合；如需补 typed 通道，明确输入/输出层次和版本，不把原生无量纲 actuator ctrl、position target、measured force 互相改名。机器人声明自身结构、初始状态、可供选择的 Controller 和本体 state 描述；Controller 声明输入、需要的 state/model 和输出；任务拥有目标、奖励、成功/终止和任务 observation；Env 组合对应的 action/state/observation spaces 并维护固定规则。不能让 Controller 单方面定义所有任务/相机 observation，也不能让 Panda 的空间默认值溢出到别的主体。

## 工作单元 0：冻结真实基线与差异清单

- **代码/材料：**现有 `goals/01–07`、五份 contracts、`planning/stage4-assembled-panda.md`、`planning/gravity-compensation-assembly-tree.md`、三份 5c Sol 主审及 output release；`task_env/registry.py`、`environment/reference_env.py`、`runtime/sessions/*`、`robots/*`、`controllers/*`、`assembly/*`、`render/*` 生产调用链。
- **目的：**明确已接收的实际交集、当前使用者、真实调用和版本 identity；建立一体/装配 Panda、Pendulum、双轮车各自构建→state→action→physics→observation→render→close 的 owner 与差异表，区分正式能力/兼容行为/诊断探针/未知。不是重复历史全部 matrix 或静态审计无限期拖延。
- **影响：**不修改旧证据、任务语义或资格结论；确定 `BaseTaskEnv` aliases、recorder、fixed-space wrapper、API/配置身份的兼容线。**退出：**每一条路径定位实际文件、分叉、可复用 owner 和最早缺口；列 4 主体 × 3 physics 的当前能力（PASS/BLOCKED/NOT_RUN）及实际资产前提，不能因为共享类名宣称全支持。

## 工作单元 1：冻结可运行的主体、动作、状态和 Runtime 合同

- **代码范围：**`task_env/environment/protocols.py`、`types.py`、`config.py`、`configuration.py`、`reference_binding.py`，`task_env/artifacts/logical_assembly*.py`、`artifacts/state.py`，`controllers/contracts.py`、`controllers/canonical/physical_commands.py`、`runtime/sessions/physical_control.py`、现有 capability/representation owners 及其相关测试/文档。
- **核心目的：**在既有 owner 上确定同一主体/嵌套组件、source owner 或引用既有实体、固定/自由/约束 root、控制通道、Controller capabilities、robot action→typed canonical command、state requirements、source/episode/clock 和固定 space 的可执行契约。保持原已确认的 contribution/冲突规则和不同类型命令，不新增平行 TaskIR、Controller manager 或仿真 Runtime。
- **主要影响：**Panda 7+2、Pendulum 一关节与双轮两关节由声明表达；源控制器和 provider 依旧验证能力交集。保持既有 codec/hash 与 default 配置；若新字段改变 identity，使用新版本及兼容映射，不覆盖历史 receipts。设计联合代码用一个最小真实生产纵切验证，不能只交空 schema/设计图。
- **退出：**单层与现有多层真实 resolver 同套路径、引用/缺失/冲突拒绝、多 Controller 单次聚合及 state/clock 定向测试；冻结四主体的动作/状态/ownership 和首个可执行纵切输入，保留 G04 已接收的 profile 安全边界。

## 工作单元 2：建立通用构建、Runtime 和 Pendulum 首个真实纵切

- **代码范围：**`task_env/registry.py`、`environment/reference_env.py`／`lifecycle.py`／`reference_binding.py`、`assembly/compiler.py`／`references.py`、`runtime/bootstrap.py`／`boundary.py` 与 `runtime/sessions/api.py`／`common.py`／各受影响 adapter，`robots/pendulum.py`、`tasks/pendulum.py`、`controllers/` 的直接 torque Controller、诊断及 tests。
- **核心目的：**一个 `make_env` 生产调用链把 Pendulum 已存在的主体绑定到通用 Assembly/Controller/runtime，而不是仅让 component Env 多一个标志。将本轮涉及的 component 与 selected 在统一发布、reset/step/fault/close owner 上接通；provider 仍可有不同 native 实现。控制器接收 1 维 ±2 N·m 直接 torque 输入并产生对应具名命令，原 public action tree、单位/轴和 provider transmission 必须以真实映射验证，不双重提交。
- **主要影响：**来源已含主体的路径只引用既有实体，不重复导入；保留 Pendulum reset/seed、25×0.002 s 节奏、reward/termination/horizon、space、记录以及有/无 RGB 行为。早期优先比较 GeoPhys CPU 旧/新同初态同动作及 MuJoCo CPU 现有能力；不是通过新 solver 偷换相同语义。
- **退出：**公开工厂真实 construct→reset→至少一个非零合法动作 step→state/clock→close，确认同一主体/Controller 和一次提交，受影响旧/新行为逐项对照；missing/conflicting names、非法动作、fault/close 的适当合同检查。共享运行链必须有真实调用，不用 fake 构造或只改测试名冒充；若 provider/source capability 缺失在最早边界报告并在授权内修复。

## 工作单元 3：双轮车及多通道 Controller，证明主体不是特例

- **代码范围：**`robots/two_wheel_balance.py`、`tasks/two_wheel_balance.py`、`controllers/` 通用或参数化 direct-effort Controller、共同主体/assembly/runtime 代码与测试。
- **核心目的：**让双轮车经与 Pendulum 相同的主体构建、Controller binding、canonical 命令和 Runtime 路径运行；左右轮顺序和每路 ±1.5 N·m 通道由声明决定，允许单个 Controller 管理多个通道，不写 task UID if 或复制一套 Env/runtime。
- **主要影响：**保持现有 torque tree/schema、单位、左右轴/传动、25-substep cadence、任务奖励/终止与 state spaces；非零不对称输入应能揭示左右互换或重复施力。默认使用直通 Controller；滤波若使用必须显式选择、记录内部状态并在 reset 清理，不能默默改变原任务。
- **退出：**真实 public construct/reset/step/close、两轮命令和状态来自同一边界、与旧路径的适用同动作对照，外加错误/冲突、reset、无 RGB 兼容；真实不同主体消费同一生产 owner 的证据，不把一次成功泛化为全部 backend。

## 工作单元 4：一体 Panda 与多层装配 Panda 的同一主体流程

- **代码范围：**`robots/panda.py`／`robots/base.py`／`robots/runtime.py`、Panda 裸臂/夹爪新主体类及既有 `assembly/fixed_attachment.py`、`artifacts/logical_assembly*`、`tasks/position_candidate/*`、PickCube/Nut 正式任务 binding、`controllers/canonical/leaf_*`／`position_profile.py`／`physical_*` 及相关 tests。
- **核心目的：**一体 Panda 与裸臂＋独立夹爪实际从正常配置进入与单层任务同一个主体/嵌套绑定和命令提交机制；Robot 类声明自身 source、关节、TCP、默认/候选 Controller、state requirements，不要求无夹爪主体拥有 Panda 字段。嵌套路径映射到既有 Scene/实体，保证 parent/child、单位、唯一物理实体、source/identity/约束和 writer 正确。
- **主要影响：**位置、R3、7+2 effort、夹爪/传动与独立附着模式保留原能力边界；Panda 的 8 维输入到 7 臂力矩＋2 指力是 Controller 专属映射，不写入通用 Env；task/solution 不按 Robot 名称改变策略。现有固定附件候选可能只支持特定 source，先认清并在允许范围扩展，不宣称任意夹爪已准入。
- **退出：**四种主体实际声明/装配/选择 Controller 的公开链可复核；一体 Panda 受影响短程及既有 4c 控制器 reset 行为回归；装配 Panda 至少完成真实构建、所选控制及状态边界代表验证，验证单层/多层一致机制和不重复绑定。其余精度、重力、两任务完整 Solution/成功仍按原 7a 用例单独收口，旧 N08 不改写。

## 工作单元 5：三 provider 的同一 Runtime 路由及任务语义

- **代码范围：**`runtime/sessions/api.py`、`source.py`／`representation.py`／`common.py`、`mujoco.py`、`geophys.py`、`native_io.py`／`isaac_native_io.py`、`environment/lifecycle.py`、`task_definition.py`、`observations/*`、`registry.py` 及各真实 task binding；必要 provider 公共 API 变更另在具体包列出。
- **核心目的：**同一 public Env/Runtime contract 从相同任务主体语义出发执行所支持 provider，不以装载特定任务选择另一套控制/状态语义；Source 是被编译绑定的表示，provider/SDK type 在 adapter 处理，公共 state 与 clock 由同一合同发布。任务的 observation/reward/成功判据留 `TaskDefinition`，机器人本体 state、Controller action space、任务 observation/RGB 在 Env 中按声明组合。
- **主要影响：**为 Pendulum/双轮车逐项核对 GeoPhys、MuJoCo、Isaac 的受支持 source、joint、actuator、控制模式和可用依赖；现有 MuJoCo/Isaac 并未证明这两任务可运行，尤其 Isaac 的 F06 冻结 USD 不是通用输入。目标是实际走统一入口接通有能力的路线；遇缺 USD/source closure、native API 或资源时形成具体失败证据与可实施修复，不伪造 provenance、不静默 fallback，也不把 provider 实现差异抹成假通过。
- **退出：**每个任务在已准入路线得到真实 reset/有界动作/状态与 clock，至少覆盖修改后的代表 MuJoCo、GeoPhys 和受影响 Isaac 真实路径；原用户希望两简单主体也能接入 MuJoCo/Isaac，需逐格给出落实状态和剩余阻碍，不能仅测 PickCube 声称已做到。对确因缺少真实资产/provider能力未闭合的交集标 BLOCKED，交维护者决定，不能自动宣称通用支持。保留 G03 的 seed、preflight、切换与 4c Controller reset 能力，受影响时补回归；不执行 G06 batch。

## 工作单元 6：重力补偿与控制贡献兼容

- **代码范围：**`controllers/canonical/model.py`／`physical_controller.py`、`position_profile.py`／`physical_commands.py`、`runtime/sessions/mujoco.py`／`mujoco_dynamics.py`、configuration/metadata、`assembly/fixed_attachment.py`、现有 gravity guides/树提案及测试。
- **核心目的：**把“是否启用”和计算所需的本体/Source/model/Controller 能力表达清楚，保留当前默认关闭和限定的一体 Panda MuJoCo 实现；保证统一控制链不会重复补偿、漏算或静默改变 4c 默认成功路径。机器人内部提供模型/配置，通用命令合成管理 source-bound 贡献和一次提交。
- **主要影响：**当前实现通过经约束审核的 position-drive 目标偏移实现，不能称为一般 direct effort。装配树内哪些实体的自重可选择、手指耦合/限幅、fixed vs mobile base 和 source completeness 必须按现有提案处理；不把外物/接触自动当作本体，也不宣称其他 provider 已有补偿。通用装配重力作为原计划的待实现能力，除非必要且本包明确授权，不以空开关假装完成或强行扩成所有组合。
- **退出：**关闭态动作/状态/记录兼容和已支持开启态的受影响定向回归；启用不支持交集明确拒绝；装配树选择/贡献计算如本轮实现，需独立数学与真实受测范围证据，未实现标待办并维持 7a 既定完整用例。

## 工作单元 7：renderer 边界、Isaac 回归与 5c 图像

- **代码范围：**`environment/reference_env.py::_prepare_task_rgb_state_binding`／`_new_task_rgb_consumer`、`observations/capture.py`、`render/camera/source.py`／`api.py`／各 adapter、`runtime/sessions/isaac_native_io.py`／`geophys.py`／MuJoCo renderer-only；必要的 GeoPhys public camera API/gitlink 另明确。
- **核心目的：**公共 Runtime 发布真实 state、boundary、clock；renderer adapter 按自身能力消费，分离 USD native shared-scene 与 MuJoCo MJCF renderer-only 的 source 前置。先在 1–2 的纯合同中加入能暴露 USD 被误送到 MJCF source 的反例，实际修复位置依统一接口冻结；在相关公共 owner 稳定后做当前代码 Isaac 真正 reset/step/RGB/close 回归，避免先热修后又让大规模迁移失效。
- **主要影响：**保留窗口与任务相机分离、固定 renderer 至 close、旧帧/故障、旧 owned 图像、相机 optics/source/capture identity；任意 renderer 的声明不能改变任务、Controller 或 physics 语义。窗口显示、离屏 RGB 和自动同步 RGB 分别依据受影响记录证明；不重开已人工认可的 5b 可辨性，不设新的通用像素分数门。
- **退出：**Isaac `UsdRuntimeSourceV1` 不再经过不属于它的 MJCF renderer-only admission，同时身份和同步不被放松；真实 Isaac reset/step 的 frame+state+clock、capture 无额外物理推进及释放；按影响复测 MuJoCo、GeoPhys、GeoPhys CPU×MuJoCo renderer-only 和 Pendulum RGB。PickCube 仍是原真实代表；跨组合至少一条真实，其他非 Panda 图像不假称全路线已验证。

## 工作单元 8：诊断、条件分支和兼容债务归位

- **代码范围：**先从实际改动涉及的 `environment/reference_env.py`、`runtime/sessions/api.py`／`control.py`、`assembly/compiler.py`、`observations/selected_reference.py`、renderer 与历史 `task_env/diagnostics/` callers 做精确 inventory；参考 [全局诊断代码规范](../../../../global/diagnostics-and-code-boundaries.md)与[原遗留清单](pre-stage3-environment-refactor.md#diagnostic-policy-and-final-cleanup)。
- **核心目的：**为每项记录位置、真实用途/caller、分类、目标 owner、保留或迁移理由、证据和兼容方案。仅实验/测试探针转诊断驱动/fixture/包装；任务策略移 task/Robot、provider 约束由 adapter/capability owner 管；在相关改造单元内清除重复或越权判断，不以换名/搬到新大类冒充解耦。
- **主要影响：**`_diagnostic_profile`、`_diagnostic_manifest`、leaf-record 私有桥、`position_profile` 跨职责判断以及 task UID/fixture 特判逐项调查；不是所有 if 或 `diagnostics` 字段都该删除。正式 source/资产 pin、能力 admission、安全/单位/clock/stale、fault/close、feedback、Recorder/兼容 API 必须保留；旧认证不变更或绕过。先保证正常 caller 后再删除；移除后的受影响测试应验证原生产 owner。
- **退出：**触及项均有 disposition 和明确回归，未能处理者带原因/owner/7a 计划；不得把尚有诊断入口的实验 profile 写成正式通用支持。不可跨包清理 ignored workspace/temp_outputs 或改写受保护输入/历史记录。

## 工作单元 9：5c 综合主审与 G06 前检查

- **代码/证据：**四主体的实际公共构建与 Controller/通道与 canonical command 证据；源/representation/版本/route/capability 矩阵；三原生及真实跨组合在最终代码身份下的 source/state/time/RGB、fault/close 与独立读回；旧有 3c/4c 的 reset/controller 原能力及重力可用交集；诊断耦合 disposition；文档/API/示例与兼容 caller。
- **核心目的：**完成修订后的 5c 同步 RGB、固定 renderer、真实跨组合和本次明确的四主体统一真实链，而非以多个独立 profile 各跑通冒充共享机制。对实际影响决定补测；保留原 5b 人工接收、3b 原 N08 FAIL、未实现的 7a Solution 全用例和旧过程偏差。
- **主要影响：**G06 前验证标量合同能表达 env/row、episode、boundary、controller/renderer generation、RNG、终止首帧、buffer ownership 与不同嵌套主体；这些是设计/合同准备，不提前实施 6a/6b/6c、不以 `num_env=1` 冒充 batch，不强制两个后端的真实并行提前成为 5c 门。跨 provider 并发能力、mask reset 和 GPU 批量仍按 G06。
- **退出：**由 Sol 根据每个真实受测交集和稳定代码身份独立决定是否有界接收 5c；任何实际必达项阻断仍保持未接收，并报告可执行决策。各实施窗口保留报告、inputs/output SHA、完整命令、source/worker/physics/GPU 资源账、双锁、失败与可复用 evidence、独立验证方法和 release，具体预算和实际修改权限按窗口经维护者授权。

## 开源参考与责任边界

[ManiSkill BaseAgent](https://maniskill.readthedocs.io/en/latest/_modules/mani_skill/agents/base_agent.html) 将 agent、可选 controller config/模式和加载后的 articulation 组织在一起，[Panda 示例](https://github.com/mani-skill/ManiSkill/blob/main/mani_skill/agents/robots/panda/panda.py) 与 [CartPoleRobot](https://maniskill.readthedocs.io/en/latest/api/mani_skill/envs/tasks/control/cartpole/) 提供主体与控制配置的参考。它们是上游开发版示例，不是当前 GeoChora 已运行证据；不引入 ManiSkill/SAPIEN 新依赖、不复制其 provider-owned articulation 到公共控制接口，GeoChora 仍遵循既有 provider-neutral 状态/命令和真实 source-bound admission。

## 明确不做的隐式扩展

此路线不启动阶段 6、merge/push/tag/发布；不恢复同一 Env 的 renderer A→B→A，不要求任意 provider×renderer×controller 全矩阵，不为每一步设置多 seed/全 GUI/完整任务成功。仅当具体新源、provider API、依赖安装、资源增额或新的修改窗口已由维护者明确授权时执行；遇真实不可用保持 PARTIAL/BLOCKED 并说明最早边界，不自动删掉原目标。准备与文档审阅不是 attempt；真实执行才按已冻结诊断窗口单独计数。
