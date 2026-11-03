# Core ↔ physics provider 协议草案

状态：`DRAFT_FOR_DISCUSSION`；本节为 1c 设计交付，已由 Sol 有界审核修正；协议最终接受/冻结仍待维护者。扩展现有 RuntimeSession／admission／adapter owner；不创建平行 ProviderManager、Runtime 或 Recorder。下列版本化值是建议，不代表生产 schema 已实现。

## Owner、现有入口与证据层级

Core 拥有任务／资产语义、执行需求汇总、初始化采样、生命周期调度、Controller、公开状态组合、评价和 Recorder 调用。RuntimeSession 是 Core 的同步 physics 边界；adapter 拥有原生对象翻译、公开 provider 调用、同步和自己创建的资源；provider 项目拥有物理算法、原生对象与 solver。batch worker／process App 是单独的部署 owner。

主要现有 caller 是 `make_env → SelectedReferenceEnv._reset/step/close → materialize 或 materialize_control → RuntimeSession → adapter`。`RuntimeSession` 当前有 reset、snapshot_v1/v2、control feedback、step、close；没有通用 request-specific capability query，也没有统一 build receipt。当前 `provider_manifest()` 返回静态 `provider-capability-v0`，其通用声明不能代表具体资产／依赖／耦合／运行能力。注册或能 import 也不等于准入。Isaac F06 是 Core 生成的精确 source-bound admission，不等于任意 Isaac route。

能力结论用**分开的维度**记录，不压成 provider 名称或一个 bool：

| 维度 | 取值／证据 | 含义 |
| --- | --- | --- |
| 物理／provider API | `supported / unsupported / unknown` | provider 公开能力及版本限制；不能由 adapter 声明替代 |
| Core adapter | `implemented / not_implemented / unknown` | 当前版本是否有受支持的 adapter 路径 |
| 环境依赖 | `available / unavailable / unknown` | 精确版本、设备和运行环境检查；读取包元数据不启动原生 runtime |
| 本项目证据 | `none / bounded_execution / qualified` | 精确 task/source/route 的历史证据等级；新设计不能升格证据 |

建议在现有 admission owner 增加一个小型 `CapabilityAssessmentV1` 行：`capability_id`、上述状态、`assessed_at=declaration|preflight|native_build|runtime`、对象／通道引用、reason、evidence_ref。请求绑定 Artifact／Scene identity、source closure、ExecutionSpec、Controller/StateRequirements、reset 粒度、batch layout 和共享资源需求。缺少 required 行为或 unknown 的最终准入拒绝；可静态判定 unknown、但能由本次 build 判定的项返回“需构建期核对”，不得提前标为 supported。optional 缺项进入 typed availability，不能补零。用户 manifest 只能收紧这些结论。

判定分三段：**静态 query** 检查明确声明、source closure、依赖元数据、route 与需求交集；**native build** 才能核实具体语法、编译后对象映射、传动、solver/coupler 和可读回配置；**reset/runtime** 才能核实实际写入、时间推进、测量可用性和状态时钟。文件可读、schema 可解码、provider 注册或 host 上存在 GPU 都不能越过后两段。

## 双向操作契约

每个失败建议通过现有异常边界携带一个精简的 `PhysicsOperationIssueV1`：`operation`、`phase`、`request_identity`、可选 `materialization_id`、`failed_capabilities/objects`、`completed/attempted`、`partial_effects`、`cleanup_receipt` 和 `recovery_action`。异常类型仍由现有 API 决定；该值补充可审计的结构化事实，不另建异常体系。原生句柄、solver 私有对象和裸指针不越过 adapter。

| 操作 | Core 输入 | Adapter 输出／保证 | 修改资源与 owner | 失败／现有映射及最小扩展 |
| --- | --- | --- | --- | --- |
| 能力 query／准入 | Artifact/Scene/source closure；分层 route；Controller 输入／输出和模型需求；required/optional state、interaction、device、timebase、scalar/batch 与 renderer 共享前置需求 | 按能力逐行报告 provider API、adapter、依赖、证据等级；列检查阶段、缺项、可执行的下一检查和可选 availability；静态 required 全部通过、其余 required 已明确安排本次 native_build 检查且存在 adapter 时，才可进行 provisional build；最终准入必须等所有 required 检查通过 | query 无原生副作用；Core 汇总需求，admission owner 对结果负责 | 现在只有静态 manifest 与精确 profile 特判；为 admission 加受请求 identity 绑定的结果，不由 renderer 自行放宽 physics admission。render 细节留 1d |
| 原生构建／materialize | 已校验的统一 Scene/Asset/ExecutionSpec，source closure receipt，具名 entity/frame/joint/DOF/actuator／representation binding，配置、设备、solver/coupler 与 Controller 依赖 | 成功后公开真实 host/provider/build/dependency/device/timebase、对象语义映射、输入到原生表示的转换／丢失／限制、编译期 readback 和资源 owner | adapter 建立模型和 session；source receipt 保持 task/source owner；环境只发布完整 session | 当前 `materialize()` 返回 session，无 universal receipt；建议给现有 RuntimeSession 扩 `ProviderMaterializationReceiptV1`。复用 NativeRuntimeIOMetadata、ExecutionSourceReceipt、已测指纹；只公开语义名称和摘要，不公开 provider ordinal |
| 初始化／reset | Core 持有 seed/sample/reset-plan；env mask（仅声明支持时）；reset 配置／generation 与 source-bound tolerance | 返回新 episode/reset identity、sample id、请求和 realized named state、写入范围／被清零速度、公开 readback、偏差及 reset receipt；不暗中重采样 | 环境／Core 创建新 episode 与 Controller 初态；adapter 只改授权的 native scene/row | 现有 `reset_plan` 无通用 mask；ReferenceEnv selected reset 会关闭并重建 session。纯静态 preflight 拒绝必须在释放旧 session 前发生且不改变现 episode；第一次释放／写入后失败则保留部分事实并 fault，不能回滚。部分 reset 必须保持未选 row 的 state/clock/controller/episode 不变 |
| 命令接受／施控 | source-bound、step/revision-bound具名物理命令、writer、区间、单位／axis／frame、饱和及限幅策略 | 分别报告 submitted、accepted、native write ack、effective generalized effort（仅在有映射证据时）和 measured/estimated feedback；拒绝 stale／duplicate／无映射命令 | Core Binding/Controller 是唯一 command writer；adapter 写 native channels | 现有 CanonicalControlTarget 仍为位置；MixedActuatorCommand/Applied Ack 只覆盖受限 source profile。Ack 证明目标按映射写入，不证明发生运动、力已实测或跨引擎等效 |
| advance／step | 要求的控制 interval、physics dt × substeps、Controller cadence（interval hold 或每 native substep 重算）、所需同步边界 | 同步路由返回完成 native steps、实际结束时间、final revision/state boundary；可选逐 substep 记录。若准确 adapter 是异步，则返回绑定 session/generation 的 completion ticket，必须 wait/synchronize 后才能读状态 | session/adapter 推进唯一场景；Controller 仅按明确 cadence 计算命令 | 当前 `step()` 同步循环 `control_substeps`；没有通用 async ticket。中途失败报告 attempted/completed native interval、实际时钟及未知部分；不得输出正常 transition。异步只对明确支持的 route 声明 |
| state／feedback publish | `StateRequirements`、Consumer 和需求 sample clock；所需 names/units/frames/reference points、device/layout、copy/lifetime | CanonicalStatePublication/typed availability、StateBoundaryIdentity、sample clock/revision、完成 fence、owned/borrowed lifetime；required 缺项报错，optional 缺项带 reason | adapter 只读其拥有的公开 provider view；Core 发布对外 state；Consumer 管理 retained copy | 复用 StateRequirements、StateSampleClock、StateBoundaryIdentity、CanonicalStatePublicationV1/V2、NativeIntervalEvidence。绝不把旧 revision、未完成 async 写入或借用的 native array当当前状态 |
| close／failure | env/session/app/worker 的 owner 身份及已分配资源 receipt | 每个 owner 返回一次 cleanup attempt/status、关闭资源列表、失败／仍存活持有者；调用重复安全，不能双重释放共享资源 | env 统筹 Recorder、session、source receipt 和 task resources；session 释放自身 model/context；process App/worker 独立 owner | 现有 `close()` 在 RuntimeSession 为 None；部分路线另有 close receipt。增补 typed receipt 并保留全部清理失败。session close 释放自己的 App lease，不直接关闭仍被其他 session 持有的 process App |

建议的 `ProviderMaterializationReceiptV1` 在当前 session/materialize owner 内增补，复用已有 identity。至少绑定 Artifact 与 Scene identity、source closure、完整 route、精确 provider/build/dependency/device、实际 timebase、具名 mapping/layout digest、表示转换、unknown/loss 清单、resource lease id、build phase 和 evidence。它是“构建了什么”的收据，不是物理正确性或 qualification。

## 身份、状态转移与部分执行

跨操作至少绑定：Artifact/Scene identity、source id 与 closure digest、ExecutionSpec identity、provider materialization、Scene instance/env row、topology/config generation、episode/reset sample、Controller/action spec、control step、state revision 和带 domain 的 sample clock。批内一次 template 用显式 env id → worker id → local row mapping，不以 native ordinal 作为跨 API 身份。

- query 或纯 preflight 拒绝：不得取得原生 lease、关旧 session 或改变 episode；现 session 仍可继续。
- 初次 build 失败：adapter 尽力关闭新建资源并返回 cleanup facts；清理成功可回到未物化，清理不完整则 env faulted。reset/rebuild 若已经关闭旧 session 或发生其他 first effect，即使新资源清理成功也仍属 faulted，不能假装旧 episode 仍可继续。
- reset/command 在第一次 native effect 前拒绝：状态不变。开始写入后出错：注明实际写入／partial，环境 faulted，不允许正常 step。
- advance 部分推进：记录已完成和尝试的 interval，不能合成完整 transition 或声称未推进。后续只允许明确 reset/rebuild 或 close；不承诺把 solver state 回滚到 step 前。
- publish 发现 required 字段、revision 或同步 fence 不符：不得交付正常 observation／transition；optional 数据以 UnavailableStateValue 和原因发布。
- 关闭只尝试各自拥有的资源。close 失败记录在 receipt；调用方不能因异常而重复释放已移交给别的 owner 的资源。

## 资产、数值与路线准入

对每种 required physical representation 分开核对 source closure/依赖、长度／质量／时间单位和坐标、刚体质量与完整惯量、joint/axis/limits、actuator/transmission 与有效力域、约束及 required interactions、reset realization 与 public readback。source 声明作为 oracle；可读回量应绑定准确 build/source。只有有限数值或“无 NaN”不是正确性证据；容差按量纲和具体 source oracle/指标给出。Panda/PickCube 的惯量解析值与声明值约 5% 的历史差异保持为待资产 owner 确认，不在本协议自动修正。跨 solver 容差不设万能数值。

| 首批 route | 当前 adapter／host／engine 与实现面 | 可公开核实的边界 | 1c 设计结论／缺口 |
| --- | --- | --- | --- |
| MuJoCo CPU | `_MuJoCoSession` 从已解析 source/MJCF 构建 MjModel/MjData；Core 使用具名 source binding、qpos/qvel、ctrl 和同步 step | 受支持 profile 下固定 timestep 与 control_substeps；source-bound mixed plan 有 named command/ack；读取和 reset 仍限已支持标量/free-body 映射 | query 不能泛化成所有 MJCF／solver option；compiled mapping/actuator transmission 要进入 receipt。native ctrl 不等于广义力；当前有限 effort/position channel profile 不能证明任意 transmission。实际安装版本未在此窗口 import/启动核实 |
| GeoPhys CPU | `_GeoPhysSession` 经 GeoPhysSourceComposer/bootstrap 构建，并通过公开 EpisodePhysicsBoundary reset/read_snapshot/apply_control/step；CPU route | mixed plan 可核对 named joint→unit-gain stateless joint transmission/control-range；存在 compiled layout/readback 与 close receipt 的有界 profile；不把 adapter 内部 ID 作为 Core API | 只支持实际 source/compiler/profile 交集。当前 task_env 声明 mujoco>=3.8.1,<3.9.0，而 GeoPhys pyproject 声明 mujoco>=3.15.0，两者没有同环境版本交集；dependency readiness 仍 unknown，后续由环境／依赖 owner 决定隔离方式，本包不改依赖。另缺通用 request query、统一公开 build receipt、一般 tendon generalized-effort 与跨 profile dynamics oracle；不把单 solver 实现外推至其他场景 |
| Isaac Sim 6.2.0.0 + PhysX CUDA | 精确 F06 PickCube admission 创建 Isaac native IO，再由 UsdCoreRuntimeSession 驱动；独立 IsaacSimAppOwnerV1 是每 worker process 的 headless App owner | exact metadata 绑定 source/scene/artifact/execution/provider build/backend/device/timebase/named scalar DOFs；具名 position write/readback/reset/advance receipt；App lease 可延迟 process close | 当前不是通用 physics query/build；F06 的 native position/mimic drive 不是 direct generalized effort，也未证明 PickCube 同步 camera obs、任意 Isaac batch 或任意 asset。Effort 未实现则拒绝所需 route，不将 PhysX drive Ack 记成实测 effort |

独立 Isaac-hosted Newton 与 standalone Newton 是不同的 host/engine/solver 路线；Isaac Sim 6.2 官方文档确认这类层级可存在，但本仓库没有相应 adapter admission。一个 provider 可在自身内部组合多个 solver/coupler；本版只表示一个整场景 owner，跨 provider 力学耦合不在范围。若 required interaction 明确要求耦合而 adapter/build 无 public coupling receipt，则 query 为 unknown、build 拒绝，不从“同一场景包含两类材质”推断已耦合。

## 复杂路线的表达检查（设计，不是新增接入）

| 具名情况 | 必须能区分的值和拒绝边界 |
| --- | --- |
| 独立 Newton 与 Isaac 内 Newton | provider/adapter 路由、standalone process 与 Isaac host、engine/library build、solver family/algorithm、source importer 和 App/worker owner 分别记录。两种宿主不共享准入结论 |
| Isaac＋PhysX 与 Isaac＋Newton | host 相同不代表资产、drive、solver option、公开反馈或 renderer 绑定兼容；只选准确宿主版本公开的 solver。Newton SDK 中有某 solver，不等于 Isaac 插件暴露该 solver |
| Genesis rigid＋FEM | 同一 scene provider、两个 representation→solver binding、明确 required contact/momentum interaction、coupler/精度/依赖及子步完成边界；只有单项 solver 支持而 coupling 未证实则不准入，具体设计见 P2 |
| SAPIEN | 由现有 adapter 和准确公开 API/依赖/设备声明真实 solver、控制、反馈、batch 与原生 renderer 绑定；不因其同样有 Scene 接口而套用其他 provider 的能力 |

这些例子只检查协议是否能表达不同层级，不引入新的物理 DSL 或运行承诺。后端是否开源不作为 solver 选择轴；可用公开 API/插件及其版本、依赖和实际实现决定准入。原生 API 可获得而 adapter 尚未实现，也必须单独报告。

## Panda effort、反馈与模型依赖的协议边界

建议 physical action 主路径使用 source-bound **七个 Panda arm generalized joint effort**（每个具名 revolute DOF，N·m）与一个**具名 gripper-closure generalized effort coordinate**（N，coordinate 为夹爪开度/闭合距离 m）。Scene/Execution 的建议版本化 extension 要提供轴、符号、joint order、有效范围、native actuator/transmission 映射、约束关系和传动矩阵；compiled receipt 验证 native write 与 `F dx = Σ τᵢ dqᵢ` 的 source-bound 映射关系。平动 DOF effort 为 N。Cube 是被动 free body，不增加 action 维数。

当前 Panda source 具有 7 arm actuators 和 1 tendon gripper route、两个 finger joints。现有 mixed plan 不能通用表达 closure generalized effort；一个 tendon channel也不等价于任意两个 finger torque。无法证明 command 在源定义的约束子空间内可表示时必须拒绝 effort admission。Finger opening/force-limit 位置伺服只列为明确的 compatibility route。R3 当前给出 q_ref＋gripper position、由 native servo 施控；不是 canonical effort。Isaac F06 的 mimic/position ACK 也不是 effort。显式 effort route 禁止同一 DOF 同时由 position/implicit-PD drive 和外部 effort writer 施控；若引擎必须保留 drive，则其 policy/gains/被动力需入 receipt，重复 PD 为拒绝条件。

Controller 的 q/qdot、pose、FK/Jacobian、M/gravity/bias、contact/actuator-force 是按实现声明的需求，不要求所有 route 提供全部字段。建议在现有 ControlBindingPlan/Controller binding 内声明 `ControllerModelRequirementV1`：模型 profile/library 与依赖版本、source/closure identity、输入 DOF names/order/units、输出 quantities/frame/reference point、纯计算/不推进 physics 标记、刷新 cadence、StateBoundaryIdentity/revision 与 max-age、reset/close owner。Model adapter 可以是明确声明的外部模型库，但不读 provider 私有 solver state，不创建第二套 physics step。

当前 R3 用 source MJCF 构造 PandaKinematics 得 q_ref；LIBERO 的 `MujocoSourceGravityBiasV1` 用 source receipt 绑定 MJCF，计算 FK/Jacobian/M/bias 并调用 `mj_forward`，记录 `mj_step_call_count=0`。它说明 source-bound 公共参考动力学可与 GeoPhys live physics 分离，但目前是 benchmark owner 和 MuJoCo 软件依赖，不能称为通用 Core ModelService。必须明确模型来源／profile、对齐的 live q/qdot 与边界、调用频率和数值偏差检查。真实 actuator/contact force sample 缺失时标 unavailable；command ack 不是测量。

## batch 与共享资源

native batch 和 process vectorization 是可组合部署维度。每个 native batch 声明统一 provider/host/engine/solver/coupler/device/timebase/action-observation layout 和 env-row mapping；RemoteBatchVecEnv 一 worker 搭载 GeoPhys merged batch 不等于每 env 一进程。配置切换整批重建；同配置 partial reset 只有对应 adapter 提供 mask-scoped receipt 时开放，未选 env 的 episode、clock、Controller/action spec 和 state identity 必须不变。现存 selected scalar reset 关闭／重建 session，不能当成 native partial reset 证据。Isaac batch 尚无本仓库 adapter。

Renderer 仅向 physics query 声明“需借用哪类公开 scene/state/resource lease”；窗口、RGB、capture、renderer 更新、image layout 与 close 的具体契约属于 1d。physics session 不暴露私有 stage/context/solver handle；App/worker 只共享显式 lease/identity，不把 lease 当 renderer 已接通。

## 参考边界

- [Isaac Sim 6.2 Newton physics backend](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/physics/newton_physics.html)：核实 Isaac host 可切换 PhysX/Newton，Newton 再选择 solver family；只支持分层 route 表达，不证明 Geochora adapter。
- [MuJoCo API functions](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html)：`mj_step` 推进一个时间步，`mj_forward` 仅计算前向动力学；支持 advance 与纯模型计算区分。
- [Isaac Lab actuator concepts](https://isaac-sim.github.io/IsaacLab/main/source/concepts/actuators.html)：隐式 drive 与显式 torque 模型的 owner／限幅不同；参考概念，不作为本仓库 6.2 API 或实现证据。
- 这些官方资料于 2026-11-03 查阅。具体版本、route 与设备仍须在未来实施包按本机元数据核验。
