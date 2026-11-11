# G05 5c 人工诊断与统一中间层重构路线

初版日期：2026-11-08；2026-11-10 按单元 4 已执行的统一主体/场景命令设计、单元 5 有界主审与维护者新指示修订。状态：`MAINTAINER_DIRECTED_DIAGNOSIS_IN_PROGRESS`；本页是路线，不单独构成执行资源授权或自动派包。单元 6 的重心是主体与 Controller 解耦、匹配与实际调用，重力补偿作为现有能力兼容和可选能力检查，不把通用补偿推广作为其主目标。

维护者要求以多个必要的人工诊断窗口解决受控主体、Controller、Runtime、renderer 和公共诊断耦合的实质问题，最终完成 5c，并为 G06 并行提供统一的标量契约。原 5c 三个普通 attempt 的结果与失败保留；本次是维护者明确指定的 post-limit 人工诊断，不新造普通 attempt 004 或清零原计数。诊断 attempt 没有固定次数上限；**下面是依赖顺序中的工作单元，不机械对应 attempt 数量**。一般情况下，一个已授权窗口可以完成多个紧邻单元；但维护者已为工作单元 4 → 5 设定强制停门：单元 4 完成交付后必须结束该窗口，等待 Sol 对精确提交和证据独立主审，再由维护者人工接收并转发单元 5；不得在单元 4 的窗口内预先实施单元 5。其他相邻单元仍按具体包界定是否可合并。每个窗口冻结实际 HEAD、写入/操作范围、资源、完整交付和释放，由维护者指定实施者并手动转发，Sol 独立主审。反复无进展时重新评估，不把 ACK、fake、图或文档当作真实闭环。

## 计划基准与当前事实

- 基准 checkout `/home/lly/.codex/worktrees/v210-integration/Geochora`，branch `codex/v211-stage5`，本计划起草时 HEAD `7f83200f`，GeoPhys `c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7`，Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`；准备实际工作包时必须重新绑定真实 HEAD、pins、writer、双锁及保护输入，不以本值覆盖后续结果。
- 权威为 [统一任务表示](../contracts/unified-task-representation.md)、[控制协议](../contracts/control-and-feedback.md)、[physics](../contracts/physics-provider.md)、[render](../contracts/render-provider.md)、[生命周期和数据](../contracts/lifecycle-and-data.md)、[G03](../goals/03-backends.md)、[G04](../goals/04-control.md)、[修订后 G05](../goals/05-rendering.md)、[G06](../goals/06-parallel.md)、[G07](../goals/07-integration.md)。1–4、5a、5b 按各自记录有界接收，不重写历史；受本轮修改的共享能力需要定向回归。G06 尚未启动。
- 起草时 Pendulum/双轮车的 component bootstrap 使用 `GeoPhysRuntimeBoundary`；该表述是历史起点，不代表当前全部生产路由。单元 2/3 和 5 已为两者接通 selected 共同主体/Controller/Runtime 链，受测的 MuJoCo CPU、GeoPhys CPU 和 Isaac 6.2 PhysX CUDA 短程路线已有各自有界证据。原 component/批量调用者及其兼容语义仍需保留，不据别名推断其已迁移。Isaac F06 身份门仍是独立受限交集。
- 5c attempt001 四条 PickCube 同步 RGB 真机证据、003 的 MuJoCo／GeoPhys／GeoPhys→MuJoCo 与 Pendulum 组件结果按各自 source/代码/时钟身份有界保存；003 的通用 reset 强制调用只接受 `RuntimeSource` 的 MuJoCo renderer-only 绑定，阻断 Isaac `UsdRuntimeSourceV1` task RGB。参见 [003 主审](../maintenance/reviews/20261108_5c_attempt003_sol_review.md)。5b 已接收，不重开。
- Panda 现有重力补偿不是空白：默认关闭，仅已证的 MuJoCo CPU 一体 Panda selected PickCube/Nut 限定交集可启用，依真实 source、固定基座与 position-drive 特性计算并记录贡献；通用装配树/跨实体、其他 provider 未完成。参考 [指南](../guides/panda-gravity-compensation.md)及[装配树提案](gravity-compensation-assembly-tree.md)。保留默认关闭及已支持配置，不能把位置目标偏移重命名成通用 effort 或声称其他 provider 通过。
- 一体 Panda、Panda 裸臂＋独立夹爪、Pendulum、双轮车的**统一主体构建与 Controller 接入**现由维护者明确提前作为 5c 诊断目标；这不等于将原附加用例的两任务 × 两机器人完整 Solution 成功从 7a 改到 5c。原 [装配 Panda 7a 用例](stage4-assembled-panda.md)的完整成功/跟踪/独立记录门继续保留；若当前不能构建或驱动装配主体，5c 的新主体统一目标不能宣称完成。
- 原 G07/7a 安排诊断耦合集中收口。维护者随后明确：**大批量兼容代码与历史分支清理放在整个 5c 有界接收之后**；本轮只处理实施目标必需的局部越权或阻塞，维护清理清单，不能批量删除调用者或历史接口。

## 2026-11-10 接收与优先级更新

- 单元 1–3 和单元 4 按各自主审/维护者决定有界接收。单元 4 的最终实现方向是现有主体/嵌套 Assembly、Controller binding、scene interval 和一个 RuntimeSession 物理推进 owner；其中默认恒等 Controller 仅覆盖实际声明的 canonical 通道，不自动覆盖所有传动，Task 原选 R1/R3 不被静默替换。单元 4 审查及执行授权文本用于解释本路线，实施结果以真实提交和证据为准。
- 单元 5 在 Core `8965eec5` 的两简单主体 × 三 provider 短程路线经 Sol 有界审阅；Isaac 的实际交集为固定 delivery-014、6.2 PhysX CUDA、headless。旧失败、source 身份、启动物理 unknown 和预约偏差继续保留；这一结论不证明所有 USD/source、renderer 或 5c 已通过。后续共享代码改动按影响决定定向复验，不以本页状态替代独立证据。
- 单元 6 在 Core `4c8a0be0` 的四主体受测配置有界接收：简单主体的直接/阻尼 effort 选择和两条 Panda Position 生产路径各有真实短程证据。当前 selected effort 匹配器对显式 profile 限制每主体一个 writer；这一限制不等于已有一体/装配 Panda Position 双 writer 失效，也不证明一般多 writer 匹配已完成。不要为了本轮图像工作重新设计 Controller；后续需求应按实际调用和共同资源合同处理。
- 维护者指定单元 7 与单元 8 在同一个执行 goal 内完成，最终一起停门由 Sol 主审；本轮只做满足验收的最小真实纵切及受影响回归，不重跑历史矩阵。单元 8 的大规模兼容清理仍在 5c 接收之后。
- 当初先后次序、技术建议与 2026-11-09 单元 4 侧边方案主审、维护者授权及后续明确决定冲突时，按后者和当前生产代码处理。以下单元 0–5 保留目标与背景，不要求重做已接收纵切；单元 6 以下采用本次修订的边界。

## 2026-11-11：单元 7／8 按重构后的生产架构收敛

- 单元 4 的统一主体、Controller binding、scene interval 和单一 RuntimeSession 物理 owner 是后续生产路线的基准；保留 Panda 的具体位置 Controller 不等于让公共 Env 依赖其 profile。以公共调用链和职责为准，旧诊断 driver、profile 测试及历史路线只提供适用范围内的参考，不能替代重构后的生产验收。
- 单元 7／8 合并为一个有边界的执行窗口：renderer 从真实已发布状态取得同步图像；单元 8 同时迁移本次直接阻碍该流程的公共越权，兼容路径的大批清理仍在 5c 接收后。已有证据按最终代码、source、配置和具体 claim 决定复用或补测。
- 只执行能建立原 5c 出口与本次共享架构所需的最少合同和真实检查；不要求历史矩阵的数值、测试模块或像素逐项复刻。真实 Isaac 同步 RGB 和至少一个真实跨组合仍需证明，不以 fake、单纯 shape 或旧代码结果冒称最终代码通过。
- 中断前的 Isaac 资源键错误和输出限额停止是独立事实，旧证据、预算与未知项保留；后续窗口按维护者授权单独记账，不修改原记录。新方案优先于本页此前对 7／8 的过时操作安排，且不重新开启已接收的单元 1–6。

## 2026-11-11：单元 7／8 独立有界接收

Core `a53bf19d` 的单元 7／8 已按[Sol 主审](../maintenance/reviews/20261111_unit007_008_sol_review_a53bf19d.md)有界接收：独立 renderer 状态投影、真实 Isaac reset／非零 step／二次 reset 的同步 RGB 与关闭，以及 GeoPhys CPU → MuJoCo renderer-only 均有适用证据。本轮局部职责迁移接收不等于所有入口、registry 和兼容路径已整理完成。下一步为单元 9 综合对账；5c 接收后按[优化台账](post-5c-code-project-optimization-diagnostic-ledger.md)完成代码与项目优化及人工接收，再进入 G06。台账不是倒灌到本轮的额外验收门；不重加复杂像素阈值、跨 provider 数值一致、启动 unknown 归零或整张历史矩阵。

## 2026-11-11：单元 9 综合交付，待独立主审

单元 9 已完成离线 G1～G6 综合对账，执行者建议 `READY_FOR_SOL_5C_BOUNDED_REVIEW`；**单元 9 已交付、待独立主审、待维护者接收**，不等于本页已签署整个 5c。生产实现仍为 `a53bf19d`，没有新 native 或矩阵复验；旧证据按受测身份及共同 reset／RGB 的实际变更逐项解释。见[执行者综合交付索引](../maintenance/reviews/20261111_unit009_executor_5c_closeout.md)。5c 接收后仍须完成维护者指定的代码／入口／项目优化并人工接收，之后才决定 G06；本轮未进入优化施工。

## 2026-11-11 后续决定：Sol 有界接收 5c 功能

[单元 9 独立综合主审](../maintenance/reviews/20261111_unit009_sol_5c_bounded_acceptance_b23fb3cc.md)已完成，结论为 `SOL_ACCEPTED_BOUNDED_5C`，取代上一段的待主审状态，维护者最终接收仍待确认。四主体、三 provider 的受测标量路由、同步任务 RGB、固定 renderer 及真实跨组合按明确身份和影响有界接收；没有新增 native、全矩阵或像素评分门。后续代码优化与项目优化仍未接收，不因本次功能接收而跳过；按[优化台账](post-5c-code-project-optimization-diagnostic-ledger.md)经安排、实施及人工接收后才决定 G06。

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
- **主要影响：**为 Pendulum/双轮车逐项核对 GeoPhys、MuJoCo、Isaac 的受支持 source、joint、actuator、控制模式和可用依赖；当前三个 provider 的具体受测交集已有短程证据，Isaac 的 F06 冻结 USD 仍不是通用输入。遇缺 USD/source closure、native API 或资源时保留具体失败证据与可实施修复，不伪造 provenance、不静默 fallback，也不把 provider 实现差异抹成假通过。
- **退出：**每个任务在已准入路线得到真实 reset/有界动作/状态与 clock，至少覆盖修改后的代表 MuJoCo、GeoPhys 和受影响 Isaac 真实路径；原用户希望两简单主体也能接入 MuJoCo/Isaac，需逐格给出落实状态和剩余阻碍，不能仅测 PickCube 声称已做到。对确因缺少真实资产/provider能力未闭合的交集标 BLOCKED，交维护者决定，不能自动宣称通用支持。保留 G03 的 seed、preflight、切换与 4c Controller reset 能力，受影响时补回归；不执行 G06 batch。

## 工作单元 6：主体与 Controller 解耦、能力匹配和调用

- **代码范围：**`environment/protocols.py`／配置及 `reference_binding.py`、`robots/` 四主体及真实生产 builder、`controllers/contracts.py`／`controllers/canonical/` 已有 Controller 与 model、`runtime/sessions/physical_control.py`／`control.py`／selected materialization 和现有诊断测试。模型来源及 provider native 映射仍由相应 runtime/provider 负责，不把 SDK 对象传进通用 Controller。视实际生产链选用已有 owner，避免另建未消费的平行 registry、batch 或 Runtime。
- **核心目的：**主体声明可控制通道、类型/单位/边界、嵌套关系、root 及状态/模型能力和可选配置；Controller 独立声明 action 输入、具名 state/model 需求、输出类型、资源、cadence 与能力；在真正构建/绑定前由公共绑定 owner 对照声明进行匹配并明确拒绝不兼容。由主体/任务的公开配置选择并调用匹配的 Controller，再复用已有 scene interval 和 Runtime 提交。一个主体不应在公共 Env 中依靠任务名、Panda profile 或动作维数猜测；Controller 算法不依赖某个 Robot Python 实例或 live provider SDK。Robot 提供配置和描述不等于 Controller 必须放在 Robot 文件中。
- **生产出口：**明确以既有 `ControlledSubjectV1`、`compile_declared_subject_binding`、`PhysicalControlExecutionV1`、`DefaultCanonicalController` 和 selected Position binding 为基线；区分 `supported_controller_kinds` 的旧 component 含义与 `selected_controller_profiles`，不得因同名返回值为空把既有 selected 能力判为不存在。迁移 Pendulum/双轮声明所需的通用直接力矩选择，验证同一 Controller 实现在不同主体/不同通道下复用；一体/装配 Panda 的 R1/R3、双 Controller、耦合手指仍以各自实际声明和可准入交集匹配，不能按 7+2 个数字或身份猜能力。无有效匹配、冲突、缺失 state/model、单位或 source 不同应在可能的最早无副作用边界拒绝。
- **兼容与延后：**现有默认恒等输出保持显式 canonical joint effort 通道、单位/范围/传动及 provider admission；它不承诺任意独立手指力矩，零力矩不保证静止；显式选用的 Task Controller 不静默替换。保留旧 Controller identity/receipt、R3 时序、Solution 入口和故障/资源保护，兼容接口需要时提供可追溯桥接。G06 的 batch、通用闭环、多 provider 完整矩阵和全库清理不提前实施。
- **重力边界：**保留已受测的 MuJoCo CPU 一体 Panda Position 补偿、默认关闭和不支持交集拒绝；是否支持由主体、Controller/model 需求和 provider 能力共同准入，不能由主体或 Controller 直接依赖某个 live SDK。已受测 Position 偏移不重命名为通用 direct effort；装配树/多 provider 重力补偿另依已有提案与后续授权推进，除非为保持既有行为所必需，不将其当单元 6 的新终验。
- **退出：**生产调用链能够展示实际的主体声明→Controller 选择和能力匹配→状态/动作→scene 提交；至少一条相同通用 Controller 跨 Pendulum 与双轮主体的公开真实短程、一个 Panda 实际选用既有 Controller 的公开短程及装配多 Controller 绑定/资源边界依具体修改影响复用或定向复验；正反合同覆盖形状、单位、通道、source、模型、资源冲突和状态身份。不能仅交 schema、class 名或 fake 检查，也不因此把四主体×三 provider 全矩阵重新变成门。记录可复用的 unit4/5 与 gravity 开闭态证据及未覆盖交集。

## 工作单元 7：新公共状态到同步任务 RGB

- **代码范围：**`environment/reference_env.py` 的状态/observation 调度、`observations/capture.py`、`render/camera/` 已有 source/session 与各 provider adapter。必要时修共同 binding 的真实缺陷，不重新实现统一 Controller 或重做单元 1–6。
- **架构：**公开任务配置 → 共同主体、Controller binding、scene interval 与 RuntimeSession → 已发布 state/boundary/clock → 所选 renderer adapter → reset/step 自动返回 task RGB。共享 native scene 与独立 visual model 由各 adapter 处理；公共 Env 不因为某个 Panda profile 或 renderer 格式改变状态与控制语义。Panda R1/R3/Position 保留为合法 Controller；同一 Env renderer 创建时固定至 close。
- **影响：**不推进第二套 physics、不放松真实 source、场景、身份、时钟与旧帧检查。当前 `prepare_task_rgb_render_source` 的名称分派和旧路径只是现状，不能因代码搬动或单测通过而声称全部解耦。现有 renderer session 构造可归位既有 adapter，避免新增平行 Runtime/RenderManager。
- **退出：**在最终代码上，真实 Isaac 公开 reset、非零 step、同步状态/时钟/RGB 及 close；至少一个真实跨组合（首选 GeoPhys CPU × MuJoCo renderer-only）确认公开状态映射与视觉更新且 renderer 不另做 physics step。保留 reset 首帧、同 boundary 与可用图像、采集不推进、旧帧所有权、固定 renderer 和失败清理等原合同。先复用仍适用的三原生路线证据；依据实际受影响范围补最短真实回归，不将四路线机械重跑、复杂像素评分或历史数值对齐设为独立目标。真实证据和合同测试分别陈述，不扩大未受测配置。

## 工作单元 8：公共职责归位与有界兼容

- **代码范围：**优先本次涉及的 `environment/reference_env.py`、`runtime/sessions/control.py`／`selected_materialization.py`、renderer/capture 与相关生产 caller，按实际调用而非文件名判断是否为诊断代码。
- **核心目的：**清除当前流程中为 RGB/状态选择而依赖特定 Panda `position_profile` 或通过诊断入口绕开共同 binding 的实质耦合；让状态需求由已声明的能力与相机决定，原 Controller、source 和 provider 专属实现留在其 owner。先核对行为和兼容，再迁移受影响部分；不靠改名或搬移同等条件冒充统一。
- **验证与清理：**对本次改动做少量针对生产调用、两种状态/源类型及错误身份的合同检查，并复用已有受测主体与控制证据；受影响的正常路径按必要性补测。不删除安全、source、clock、fault/close、Recorder 检查和仍有调用者的兼容接口。大规模历史清理在 5c 接收后，未处理项记录 owner、caller 与后续条件。

## 工作单元 9：5c 综合主审与 G06 前检查

- **代码/证据：**四主体的实际公共构建与 Controller/通道与 canonical command 证据；源/representation/版本/route/capability 矩阵；三原生及真实跨组合在最终代码身份下的 source/state/time/RGB、fault/close 与独立读回；旧有 3c/4c 的 reset/controller 原能力及重力可用交集；诊断耦合 disposition；文档/API/示例与兼容 caller。
- **核心目的：**完成修订后的 5c 同步 RGB、固定 renderer、真实跨组合和本次明确的四主体统一真实链，而非以多个独立 profile 各跑通冒充共享机制。对实际影响决定补测；保留原 5b 人工接收、3b 原 N08 FAIL、未实现的 7a Solution 全用例和旧过程偏差。
- **主要影响：**G06 前验证标量合同能表达 env/row、episode、boundary、controller/renderer generation、RNG、终止首帧、buffer ownership 与不同嵌套主体；这些是设计/合同准备，不提前实施 6a/6b/6c、不以 `num_env=1` 冒充 batch，不强制两个后端的真实并行提前成为 5c 门。跨 provider 并发能力、mask reset 和 GPU 批量仍按 G06。
- **退出：**由 Sol 根据每个真实受测交集和稳定代码身份独立决定是否有界接收 5c；任何实际必达项阻断仍保持未接收，并报告可执行决策。各实施窗口保留报告、inputs/output SHA、完整命令、source/worker/physics/GPU 资源账、双锁、失败与可复用 evidence、独立验证方法和 release，具体预算和实际修改权限按窗口经维护者授权。

## 开源参考与责任边界

[ManiSkill BaseAgent](https://maniskill.readthedocs.io/en/latest/_modules/mani_skill/agents/base_agent.html) 将 agent、可选 controller config/模式和加载后的 articulation 组织在一起，[Panda 示例](https://github.com/mani-skill/ManiSkill/blob/main/mani_skill/agents/robots/panda/panda.py) 与 [CartPoleRobot](https://maniskill.readthedocs.io/en/latest/api/mani_skill/envs/tasks/control/cartpole/) 提供主体与控制配置的参考。它们是上游开发版示例，不是当前 GeoChora 已运行证据；不引入 ManiSkill/SAPIEN 新依赖、不复制其 provider-owned articulation 到公共控制接口，GeoChora 仍遵循既有 provider-neutral 状态/命令和真实 source-bound admission。

## 明确不做的隐式扩展

此路线不启动阶段 6、merge/push/tag/发布；不恢复同一 Env 的 renderer A→B→A，不要求任意 provider×renderer×controller 全矩阵，不为每一步设置多 seed/全 GUI/完整任务成功。仅当具体新源、provider API、依赖安装、资源增额或新的修改窗口已由维护者明确授权时执行；遇真实不可用保持 PARTIAL/BLOCKED 并说明最早边界，不自动删掉原目标。准备与文档审阅不是 attempt；真实执行才按已冻结诊断窗口单独计数。
