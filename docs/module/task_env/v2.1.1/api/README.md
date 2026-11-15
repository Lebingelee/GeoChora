# v2.1.1 API 与迁移入口

Recorder 旧叶节点格式的只读入口为 `task_env.recorders.load_legacy_leaf_control_h5`；它校验结构并解码历史记录，不声称实验通过。此前的 `load_leaf_control_records_h5` 已退休；需要原 R02c/R03c 固定条件和运动判据时，单独运行 `python task_env/diagnostics/tasks/v2.1.1/legacy_leaf_judge.py <历史H5路径>`。普通 v3 控制记录使用 `load_structured_control_records_h5`。`task_env.trajectory.reference_replay.inspect_selected_replay` 只检查外层格式、不会构造 Env；格式受支持不代表源码身份已核对或重执行成功。`reexecute_selected` 仍严格检查源码身份并拒绝不支持的格式。

带物理状态边界的 v3 记录可用 `task_env.recorders.load_physical_recording_h5` 读取观测、结构化动作、clock、episode outcome 和可选 task RGB；它校验 source、控制提交和相机捕获的边界身份。RGB 字节本身尚无独立内容摘要，旧的 `load_camera_observations_h5` 是另一套多模态 Position 实验格式，不能将二者等同。当前非 Panda 物理记录只准入一个声明的 Controller 与一个 action group；详细受测范围见 U6 实施记录。

v3 记录要求运行环境能够导入 `h5py`，缺少依赖时启动记录会立即失败。当前 Isaac SDK 默认解释器路径没有公开该依赖；验证使用其 episode-recorder 扩展自带的 `h5py`，实际部署须将兼容的 H5 依赖配置到运行解释器。

当前（2026-11-15）：G01～G05 已各自有界接收，5c 单元 1～9 收口；E00～E16 代码与项目优化已获[维护者有界接收](../maintenance/reviews/20261114_e11_e16_maintainer_project_acceptance.md)。G06a attempt001 经[独立复核](../maintenance/reviews/20261115_g06a_attempt001_review.md)为 PARTIAL；attempt002 的合同、设备渲染和记录增量已获[G06a 有界接收](../maintenance/reviews/20261115_g06a_attempt002_acceptance.md)；以下能力仅限所述实测交集。G06／G07 及版本整体尚未完成。受测能力、正式入口及限制以[当前摘要](../maintenance/current-state.md)、实际源码和对应证据为准；下面的历史设计／实现记录不把未实现目标升级为 API。

<a id="pendulum-device-batch"></a>

## Pendulum device batch（G06a 有界接收）

主解释器安装兼容的 Torch 和 CUDA Python bindings，另以 Python 3.12 创建 [MJWarp worker 依赖环境](../../../../../task_env/dependencies/README.md)。普通调用示例见 [pendulum_device.py](../../../../../examples/parallel/pendulum_device.py)：通过 `task_env.make_parallel_env('pendulum-v1', ..., num_env=3, backend='cuda', execution='device')` 显式选择，`env_config['execution']` 指定 `physics_provider='mujoco_warp'` 和 worker `interpreter`（也可使用 `GEOCHORA_MJWARP_PYTHON`）。目前验证的是 Linux、CUDA 设备 `cuda:0`、MuJoCo／MJWarp 4.0.1、Warp 1.18.0、GeoPhys 的 taichi-forge 0.7.0、B=3，其他任务、设备与版本不因此获得资格；GeoPhys component AOT 仍有缺失接口，不属于所测 JIT 相机交集。

相同 device 配置也可通过 `task_env.make_env(uid, config=config, execution="device")` 显式构造单行版本；它复用相同的 batch 生命周期并去除公开返回值的 B 轴：动作叶为 CUDA float32 单行形状，camera RGB 为 CUDA uint8 `[H,W,3]`，reward、done 和有效 mask 为零维 CUDA tensor。结束时同样返回新 episode 首帧，旧帧在 `final_observation` 中。不指定该选项时，原 scalar host 入口保持原有合同。`VectorTransitionRecorder` 只接受有 B 轴的 device 环境，需要向量记录时应使用 batch 入口。

`reset(seed=...)` 返回任务树与 info；`step({'torque': action})` 的 action 是 CUDA float32 `[B, 1]`，返回任务树、CUDA float32 reward `[B]`、CUDA bool terminated／truncated `[B]` 和 info。`single_action_space`／`single_observation_space` 描述单行，`action_space`／`observation_space` 描述批量。结束行在同一 step 自动 reset：reward 与 done 属于旧 episode，返回 observation 属于新 episode。`final_observation` 始终保留固定 B 轴和与 observation 相同的树结构；只消费 bool `[B]` 的 `_final_observation` 为 true 的行。`final_mask` 是同一 mask 的兼容别名。`final_info` 提供旧 transition 的 episode、step、boundary 和 Task info；`reset_info` 提供新身份，分别受其 mask 约束。`episode_id` 和 `episode_step` 是返回状态的逐行时钟，Task metrics 与 reward terms 保留在 info 中。`reset(mask=...)` 接受 CUDA bool `[B]`，只重置选中行；native 全局 step／time 不因逐行 reset 倒退。`read_device_state` 返回带 source／generation／revision／native clock 身份的 owned snapshot，可以跨 step 保留。每行独立维护 seed 和随机流，采样范围与既有 Pendulum 相同，但 device 随机算法不保证与 NumPy 产生逐值相同的样本。

`render_mode='rgb_array'` 显式创建共享 GeoPhys Rasterizer，`env.render()` 返回 owned CUDA uint8 `[480, 640, 3]`；`render_mode='human'` 使用窗口，`close_render()` 关闭窗口／renderer，物理仍可继续。默认不创建可选 renderer 或相机传感器。B=3、非默认 CUDA stream、重复 capture 和真实 Xorg 窗口已作短程验证。device batch 可在 `render` 配置中声明 RGB-only、HWC、uint8 的 `CameraSpec`，返回 `obs["cameras"][name]["rgb"]`，形状为 CUDA `[B,H,W,3]`；有限 near/far 使用 compute mesh／analytic 路径，粒子、native graphics、TAA 和 overlay 的有限裁剪仍不准入。一次 B=3 Pendulum 诊断用显式测试相机核对了 reset／step 采集；默认 Pendulum 不创建传感器。启用相机时 `close_render()` 只关闭窗口，保留相机共享 renderer。代表性诊断将真实 Isaac scalar session 的公开设备 body pose 接入同一 Rasterizer，验证了真实 PickCube base／hand 相机与 Xorg 窗口的开关组合；三格仅复制一个 scalar 物理状态供渲染，不表示 Isaac parallel Task 获得资格。

MJWarp session 还按 source 声明发布环境局部坐标的具名 frame pose；合成 Scene 的具名 site 已在 B=3、seed 73 和共享 Rasterizer 路径中核对运动学、masked reset 与保留快照。该 fixture 不代表注册任务已配置传感器。

现有 `VectorTransitionRecorder` 可显式包装 device 五元组并选行、选 observation 字段，开启记录时导出 owned 数据至既有 H5，关闭记录时不执行记录数据复制。设备记录在 transition 已发生后失败时会锁存原异常，拒绝继续 reset／step；`end_record()` 或 `close()` 会尝试结束各行，失败行保留供重试。已用 B=3 Pendulum 的显式测试相机记录两个环境的错开 episode，并独立逐像素核对 H5 中的终止帧、新首帧及状态；Pendulum 默认仍无传感器。Isaac PickCube 的双挂载图像来自真实 scalar 设备位姿；其中 hand 帧还通过受控 episode fixture 做了 H5 独立像素与时钟读回，不能当作 PickCube 并行任务或真实终止／reset 全链的接收证据。这些结果只支持上述 G06a 有界接收，不代表 G06 整体或其他任务／provider 的接收。

PickCube 环境通过 `task_env.make_env` 和正式配置构造；调用方需要独立 Solution 时可使用 `task_env.tasks.pick_cube.build_readiness_solution`。旧的 PickCube `build_reference`、`build_isaac_reference` 和 `build_runtime_source` 直接构造入口已退休，历史诊断中的这些调用需迁到正式构建入口。NutAssembly 的独立 `build_runtime_source` 同样已退休；使用正式 `make_env` 和配置构建，独立 Solution 入口保持可用。

历史记录：3b attempt001 已通过公开 factory 在三条指定路线完成 seed31 的10步与独立读回，整体仍为 PARTIAL、待 Sol 复审：三路线短窗正向位移均未过冻结门。PickCube F06 的 `env.step` 接受既有8维绝对世界位姿与开口动作，并复用已绑定 Controller 的结构化投影；其 Recorder 保存该运行的请求、模型和原生确认。其他 Position 路线仍按各自声明要求 typed action。详见[3b attempt001执行摘要](../maintenance/reviews/20261105_3b_attempt001_execution.md)。

阶段3历史实现：阶段3前限定核心收尾及G03的3a–3c均已按各自范围接收，详见[3c独立主审及阶段收尾](../maintenance/reviews/20261106_3c_attempt001_sol_review.md)；生命周期R1已获[Sol有限接收](../maintenance/reviews/20261105_lifecycle_unification_sol_review.md)。当前可调用入口以 [TaskEnv 当前 API](../../../../../task_env/doc/api/index.md)和源码为准；selected 环境实现已迁至 `task_env.environment.reference_env`，旧导入保留兼容。`BaseTaskEnv` 已是 `SelectedReferenceEnv` 同对象兼容出口，三个组件任务使用共同 episode owner；源码与无引擎契约已复核，后续的[CPU 代表回归](../maintenance/reviews/20261105_pre_stage3_resumed_physical_checks.md)按实际源码提交和路线记录，不扩展到其他组合。本页下表是阶段3–6的设计目标，并非当前能力；已有行为及证据不因本页或导入成功而扩展。

Phase C 的标准方向是外部 Solution 读取 observation 并产生 action，由调用方交给 `env.step(action)`；现存 `step_expert()` 是受限兼容，不是新标准 Env API。部分 `step_with_solution()` 路线由 Env 调用调用方持有的 Solution，属于受限过渡；NutAssembly 现支持调用方直接传入含来源边界和控制请求的 `ExpertAction`，并在 `observe` 校验五个 native 样本；裸数组仍拒绝。PickCube seed31 与 NutAssembly seed19 已在 MuJoCo CPU 上完成有界物理回归和独立读回，证据及源码身份见[验证记录](../maintenance/reviews/20261105_pre_stage3_resumed_physical_checks.md)。详见[当前 Solution 说明](../../../../../task_env/doc/api/planning/task_owned_solutions.md)。

## 5c 后优化：当前正式构造增量

正式 PickCube、NutAssembly、Pendulum 和双轮车经 `make_env` 使用同一正式配置解析与 `SelectedReferenceEnv.from_resolved_config` 构建链。正式入口不接受旧 component resolved 配置；其他保留的 component caller 有其独立范围。E00～E04 的共同构建、生命周期和控制链已获维护者有界接收；完整 source/adapter 整理仍属后续事件，实际状态见[当前摘要](../maintenance/current-state.md)。

四个正式任务均使用 `config={"controller": {"profile_id": ...}}` 选择受支持的 Controller，例如 PickCube 的 `r3_continuous_v1`，或 Pendulum／双轮车的 `direct_joint_effort_v1` 和限定路线的 `velocity_damped_joint_effort_v1`。`control.profile_id` 与 `task.controller_profile` 不是正式输入；Mapping 与 YAML 使用同一解析。各任务和所选 Robot 的能力范围仍分别检查。

四主体的 MuJoCo CPU 正式构造提供同一 `env.robot` 视图：`subjects`、`controllers` 和 `root_frames` 引用实际准入的声明与 owner，`controller` 与 Env 当前 Controller 是同一对象；reset 重绑后返回当前视图。装配 Panda 保留 arm／hand 两个 subject 及两个 Controller，不把它们压成一个控制器。视图不创建 Runtime、第二个推进者或状态副本。旧组件 Panda 的 `references`／`gripper`／`ee` 便利投影继续保留；当前 selected 视图未声明这些投影时相应字段为 None，使用共同 subject／Frame 声明，不为 Pendulum／双轮车制造 Panda 属性。

两个简单任务的 TaskDefinition 通过既有 TaskLifecycleAdapter 消费公开 Runtime 具名状态，Env 负责随机流、reset transaction 和资源生命周期；任务模块保留自己的采样范围、奖励、成功语义及状态投影。这四个正式类不接受 `build_runtime=False` 的旧组件构造；范围外的组件 caller 有各自兼容合同，不代表 native batch。最新短程及历史 Isaac RGB、GeoPhys／MuJoCo worker 证据按[实施记录](../planning/post-5c-optimization-execution.md#6-e00e04-实施记录)的输入身份区分，不据此宣称完整 Solution 或任意组合。

### 正式 PickCube 的 MJCF 物理配置

以下配置进入相同的正式 factory／Runtime owner；本批已在 MuJoCo 3.8.1 CPU 各完成非零 action、reset 重建和 close。它们仍限原 source／模型范围，未取得完整任务成功或任意 provider 组合的接收。physical profile 当前要求 `execution.deployment="in_process"`；GeoPhys 的具体交集仍由 adapter 判断，未在本批新增实测。

| `controller.profile_id` | 输入与模型 | native drive 默认选择 |
| --- | --- | --- |
| `panda-direct-effort-v1` | 8 路直接输入：7 臂力矩与 paired tendon 力；零偏置不代表 Panda 动力学 | `position`，保留原 coexist 语义 |
| `panda-joint-effort-reference-v1` | 7 关节参考与 paired opening，经过原 joint-reference servo 产生 effort | `disabled` |
| `panda-r3-effort-reference-v1` | 原 R3 pose action 经过参考计算与 effort servo | `disabled` |
| `panda-joint-mass-effort-v1` | 原受限 nominal mass model 的 joint reference | `disabled` |
| `panda-r3-mass-effort-v1` | 原受限 nominal mass model 的 R3 pose reference | `disabled` |

普通构造不再要求 source workspace 或内部 Artifact hash，例如：

```python
import numpy as np
import sys
from task_env import make_env

env = make_env("pick-cube-p16-reference-v1", config={
    "execution": {"physics_provider": "mujoco", "deployment": "in_process",
                  "interpreter": sys.executable},
    "controller": {"profile_id": "panda-direct-effort-v1"},
    "episode": {"seed": 31, "horizon": 8},
})
try:
    observation, info = env.reset()
    result = env.step(np.asarray([.2, 0., 0., 0., 0., 0., 0., 0.], dtype=np.float32))
finally:
    env.close()
```

`robot.native_drive` 可显式选择 `position`／`disabled`，但 reference effort 仍要求隔离 drive，未支持的组合会拒绝。`controller.parameters={"reset_selection": True}` 仅适用于已有限定的 MuJoCo joint／R3 reference 路线，`action_space_policy` 保留 `dynamic`／`fixed_semantic`。这种路线沿用 `physical_action_spec()`／`bind_physical_action()` 的 generation 合同：切换通过 `reset(options={"controller": "r3-pose"})`；stale action 会拒绝并故障锁存，须显式 reset 后继续。未完成该 legacy 路线的 Robot convenience 视图迁移，使用其明确的 physical spec 查询当前 Controller。普通五 profile 的 subject／Controller 视图已验证；未新增完整 Solution 接收。

相机可用世界 CameraSpec 声明，在编译后生成绑定几何；底层 advanced CameraGeometry 仍校验 Artifact。observer／task camera 身份必须不同，输出限原 HWC float32 RGB，renderer／physics pairing 和历史观察路线限制继续拒绝。本批只验证声明与生命周期合同，未新增真实 RGB 结论。

2026-11-13 腕部相机增量：Isaac PhysX CUDA × Isaac RTX 的 `task_rgb_camera` 还可使用 `CameraSpec(frame='body', parent='panda-v1/ee', ...)`。parent 是已发布 Frame 的 `entity_id/frame_id`；缺失或不唯一时拒绝。相机解析器组合当前父 Frame 与局部安装位姿，Isaac renderer 更新自己拥有的相机并核验原生几何，沿原捕获路径检查物理时钟。MuJoCo／GeoPhys 的 frame-mounted task RGB 尚未实现，构建时拒绝；observer 的原 world 限制保留。具体 seed31、256×192 腕部图像、动作和 H5 边界见[夹爪返工记录](../maintenance/reviews/20261113_isaac_gripper_rework_ef10e348.md)。这不扩展成任意挂载、renderer 或资产组合的资格。

PickCube 当前公开 info 中的 Position 就绪读回为 `pickcube_position_execution_info_v2`：完整零开口请求、实测开口小于全开 80 mm、关节速度绝对值之和不超过 5 mm/s，表示该边界的关闭已稳定。Solution 要求连续 50 ms 后才尝试抬升；空载和夹物都可能满足，它不是接触或抓取成功检测。原 100 mm 方块抬升成功判据、控制律、本次 Isaac 5 N 原生限幅及 `grasped_cube` 历史奖励代理均未改变。显式 v1 输入仍按原 45 mm 合同验证；新 Task 不再输出 v1，旧记录不被重新解释为 v2。

旧 PickCube physical candidate、Isaac physical candidate 和 Position candidate UID 已退休，不再接收旧输入或 `source_workspace`。请使用本页正式 UID 和 `controller.profile_id`；历史候选的证据与身份按原记录保留。Isaac 路线可自动查找已安装的 Robot USD 资产，普通 `make_env` 配置不必填写内部 manifest；显式 `execution.source_delivery_manifest` 仍可用于选择已验证的高级输入。当前资产包仍需预先安装，项目尚未提供自动生成或发行包安装；不会从历史 workspace 隐式查找。

维护者可以使用 `python -m task_env.assembly.usd_cache --provider isaacsim --robot <robot-uid> --manifest <已验证交付清单>` 预装本地 delivery。安装复制并重新验证完整闭包，不覆盖同位置的不同资产；默认位置为用户缓存，也可通过 `GEOCHORA_USD_ASSET_ROOT` 选择位置。此维护命令当前仍需要清单路径，不代表资产分发已经完成。

正式 PickCube（含物理配置）、NutAssembly、Pendulum、双轮车现在共用 TaskDefinition 构造与语义 lifecycle；reset 会绑定本次重建 Artifact。`CanonicalTaskStateView` 引用原具名 canonical state；组件数组格式保留，不制造 native 索引。公共 Gym info 仍包含 typed ObservationSchema／只读评价 mapping；框架在 Solution reset／act／observe 的输入边界生成值 payload，原数值、身份和时钟检查不变。普通已准入 native 路线使用现有 live source／Controller scene interval binding。本轮有五条 MuJoCo CPU 短程证据，其中 Nut 仅一个 Solution interval；不是完整 Solution、任务成功或新 GeoPhys／Isaac 能力结论。详见[TaskDefinition API](../../../../../task_env/doc/api/semantics/task_definition.md)与[实施记录](../planning/post-5c-optimization-execution.md#6-e00e04-实施记录)。

## 5c 共同主体与场景控制接口（按实际交集有界接收）

公开 PickCube 配置可显式选择 `robot.uid="panda-arm-hand-v1"` 与 `controller.profile_id="r1_split"`：同一装配的 arm 和 hand 使用不同的 Controller/writer，沿既有 R1 动作语义产生目标并在一个 interval 提交。已有 MuJoCo CPU 单步和调用方 Solution 单步证据；不据此声明完整任务成功或其他 provider 的资格。原 `r1`、`r3` 配置仍保持各自行为。

受控主体提供一个初始未绑定的 `default_controller`，目前仅针对显式声明的具名关节广义力通道。须以 `ControlledSubjectV1`、已编译的 physical binding、writer 和每个通道的 SI 单位调用 `bind`；成功后由现有直接 effort Controller 在当前 episode/boundary 生成命令，动作空间沿用其 float32 精度及声明的限幅。嵌套主体可用 `bind_many` 返回多个 Controller，交给现有 `PhysicalControlExecutionV1` 在一个 interval 组合；不兼容的 source、writer、单位、范围及不可由实际耦合传动表达的力向量继续拒绝。它不是自动为所有 provider 开启 effort 物理能力，也不是原生 motor 力读回。Pendulum 和双轮车 selected CPU 路线以该默认 Controller 构建；Panda 已有的 R1/R3 和装配 R1 双 Controller 为显式任务配置，不会被静默替换。Panda 默认 effort 的实际能力仅在各自 source/provider 准入及有界测试范围内成立。

`task_env.ExternalComWrenchV1` 可描述单 interval 的世界力和关于当前质心的世界力矩；`task_env.ExternalComWrenchSegmentV1` 额外声明 writer 和整数半开子步范围。`task_env.ExternalComWrenchSumSegmentV1` 显式声明可求和的片段：同一 native body 的重叠贡献必须全部使用该类型且 effect 不同；旧类型仍独占，不重叠片段可复用同一 writer/effect。可通过 `env.step(action, external_com_wrenches=(wrench, ...))` 在选定 grouped Position interval 中提交。当前准入限 MuJoCo 3.8.1 CPU、implicitfast、source 明确绑定的有质量可动 body；每个相关子步重新读取当前 COM。PickCube R1 可通过 Task 配置 `cube_force_z_N`（−30 至 30 N）声明每个区间的 cube 世界 Z 向 COM 力；Task 与 caller 的贡献分别标记，同体重叠时均须显式求和且 effect 不同。Task 贡献可经普通 action 和 Solution 入口执行；该受限交集不支持与 physical port、mixed control、native-feedback、活动 Recorder 同时使用。Task 计算后失败时要求 reset。旧 `step(action)` 保持原调用方式。动态 COM 原冻结自由体 oracle 的严格线速度判据仍为 FAIL；维护者对受限偏差的有界认可与原判据分别保留，具体范围按单元 9 引用的最终主审，不继续把原失败等同于整个单元未接收，也不外推 GeoPhys／Isaac。

有界 joint-effort 实验路线提供 `env.physical_sequence_spec()`，在 reset 后查询当前 boundary、子步数及每个已绑定 Controller 的 identity、generation、输入名称与映射、输出单位和范围。`task_env.PhysicalActionSequenceV1` 接收由 `PhysicalActionSliceV1` 组成的不可变 tuple；每段以 Controller identity 对应数值 tuple，整数半开范围必须相邻、覆盖整个 interval，每段都需覆盖全部已绑定 Controller。同一 Controller 可在不重叠范围重复出现，所有输出在同一初始状态计算并保留原 physical batch hash，由一个提交和一个 RuntimeSession interval 执行。native ACK 表示序列已暂存，不是逐子步已施力或力测量的证明；后续推进失败会故障锁存。此 advanced 输入不是原 action space 的替代；当前只准入 MuJoCo CPU、明确绑定的 `LinearEffortControllerV1`／`AffineJointBiasModelV1` 与指定 typed observation，不支持 body wrench、Solution、RGB／observer、活动 Recorder、reset-scoped Controller 切换或 caller COM 同时使用。运行中无通用闭环更新；native position drive 可能仍有内部反馈。此有界 candidate 不代表任意 Position／physical 批次已可混合调度，受测接收范围按单元 9 引用的单元 4 最终复审；不据此扩展到其他组合。

## PickCube state-only reset 切换（有界接收）

显式选择 `execution.reset_profile="pickcube-state-only-switch-v1"` 后，同一个 PickCube Env 支持在 `reset(options={"execution": target})` 中切换 MuJoCo CPU 与 GeoPhys CPU，或 MuJoCo CPU 与 Isaac 6.2 CUDA；目标配置从该 provider 的默认路由重新解析。此 profile 固定 state／cube 观测，`hand_pose` 是 `panda-v1/ee` 的兼容别名；九关节速度在 info 与记录中保留。每 episode 的 Recorder 必须在切换前 finish。显式 seed 重置 Core 随机流，None 继续已初始化的流，首次 None 初始化新流。预检失败保留旧 episode；开始替换后失败会 fault 并报告已知关闭及未知写入结果。

本包只验证了指定四条边、state-only、单环境、R3 且重力补偿关闭；GeoPhys↔Isaac、其他任务及通用 controller／renderer 切换不在本次范围。已获[Sol独立有界接收](../maintenance/reviews/20261106_3c_attempt001_sol_review.md)，不需attempt002；实际用法及故障边界按本节，不外推全任务能力。

## 需形成的公共体验

4a 开发中的 Position candidate 提供 `panda-direct-effort-v1`、`panda-split-direct-effort-v1`、`panda-direct-effort-wrench-v1` 与 `panda-direct-effort-object-wrench-v1` 物理控制声明；前两项分别由单个或两个 Controller 以 8 个具名输入产生 7 个臂力矩与 tendon 声明分配的两路 finger 力，后两项分别另声明 hand 或静态 peg 的外力输入。模型的零偏置只定义直接力输入，并非 Panda 动力学；静态 peg 的声明不证明自由物体的受力运动。versioned candidate 也可显式携带 `physical_execution`；预检核对 Scene、Artifact、source closure 和状态名称。

未接收的 002 recovery 增加了该候选的 MuJoCo 3.8.1 CPU physical profile 路线；物化前检查依赖版本与 source 身份。相同 session 在 native build 后核对名称、轴、actuator 力限／gear、tendon 和 equality，将已准入关节贡献与 hand wrench 合并写入广义力缓冲；position drive 保留，显式完整 PD 与未协调 position drive 仍拒绝。source actuator 力域用于约束声明的 direct contribution；保留的 position drive 可叠加，二者总和不受该 direct contribution 界限保证。2026-11-06 在 source closure `aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47` 完成单 Controller effort、双 Controller effort 和 effort 加 hand wrench 的各一次 5 子步短运行，确认提交与写入回执；ACK 不是力测量，该次 4a 运行当时尚未完成 4b 物理效果验证。该 002 历史 A05 Position candidate 的其他 provider physical reset 当时仍拒绝；这一时点结论不覆盖后续 PickCube physical candidate。合成映射不能授权真实写入，旧 position 路线保持原身份。

Sol 已按 [attempt003 独立主审](../maintenance/reviews/20261106_4a_attempt003_sol_review.md)有界接收原 4a 控制契约和条件性 4b 方案；4b 后续有界接收三后端 effort 和 MuJoCo 代表外力；独立测力未证明。

attempt003 修正持续 BodyWrench：Controller 在 outer boundary 提交一次原始 typed 命令，MuJoCo session 在每个 physics substep 用当前构型刷新运动学和 Jacobian，将各声明的表达 frame、作用点与力矩参考重新解析后，与 joint effort 合并并替换自有缓冲；正常 interval、异常、reset 与 close 清理可辨认的自有贡献。该路线对 BodyWrench 目前只准入 source-bound `implicitfast` 积分器；其他积分器写入前拒绝。非空或被外部修改的力缓冲拒绝，未提供与 UI/其他 writer 并发叠加能力；冲突时不覆盖被改写的槽位，其混合归属和剩余力不能推断，须结束该故障 session。`torque_Nm` 是关于声明的 `moment_reference` 的总力矩：力矩参考为作用点且为零时，偏置力在 body 原点有 `r×F` 力矩；参考为 body 原点且总矩为零时，不再额外加该项。上述 002 的实际候选使用 body frame 和 body origin 参考，不能当作 world force、作用点零矩的 4b 案例。新逐子步语义有定向 fake 和 A05/implicitfast 有界 session 证据，未证明其他 provider、其他 source／积分器的物理效果。

| 操作 | v2.1.1 目标 | 责任与边界 |
| --- | --- | --- |
| make_env／配置 | 查询并选择合法 physics／solver／renderer／Controller／batch 组合 | 复用 registry 和配置解析，Core→任务类→YAML→调用方 |
| reset | 新 episode 按初始化规则选择允许的执行组合／Controller | 同一public Env内部重建，不迁移旧物理状态；Core sampler按seed规则保持；固定 obs；原生 batch 按批次切换 |
| step | 运行已确定的组合，返回当前边界状态／图像和评价 | 不在步进中替换 provider 或 renderer；Controller 依赖公共反馈 |
| render | 可配置相机的 human／RGB 可视化 | 与相机 observation 协调，额外调用不推进任务物理时间 |
| 查询 | 实际生效配置、能力／拒绝原因、action spec／space | 输入规格可随 reset 更换 Controller 改变，调用方负责匹配 |
| close | 清理自有资源并使借用数据失效 | 原生共享资源和进程级 runtime 不假装每 env 独立销毁 |

用户只配置backend／renderer／controller／camera等，不需构造receipt hash、lease ID或generation。

权威语义见[协议索引](../README.md)；语义按已确认五协议，生产字段／方法在所属后续包冻结，阶段 3–6 随实现补齐 API 页面。`ExecutionSpec` 等现有类型与兼容解码须显式处置，不因本表新增平行 facade。

## 兼容和迁移记录要求

- 当前 selected state-only 输入继续有明确行为；新 renderer 不能通过无条件放开 admission 接入。
- 旧 position／mixed 命令和新 JointEffort／BodyWrench 主路线区分身份与准入；Robot／嵌套组件声明通道，Panda8维输入→7＋2输出，贡献显式组合，不改变旧证据含义。
- observation 构建后固定；动作输入变化须更新 schema／space，fixed-space consumer 不支持时明确拒绝。
- `BaseTaskEnv` 等保留名字按既有 2.x 约束处理，先迁生产 caller，不能创建第二套 reset／step。
- PickCube、NutAssembly 迁移按真实实现和 caller 收口，LIBERO 保留 benchmark 语义；不宣布全部任务已统一。
- 记录格式变化沿用已有 Recorder 和独立 reader；episode 配置、旧版本读取及失败行为有检查。

完成 3／4／5／6 阶段时更新对应 API 与迁移说明，7c 汇总。新示例只能使用已实现并验证的公共入口，不能以概念示例冒充已运行代码。

## Panda 重力选项（有界接收）

selected 构造的 `controller.gravity_compensation` 是可选布尔值，默认关闭；当前开启仅支持 MuJoCo CPU 进程内的 PickCube／NutAssembly 位置驱动，其他选择拒绝。详细来源、实际执行回执和限幅语义见[重力补偿指南](../guides/panda-gravity-compensation.md)。

MuJoCo／GeoPhys 旧 selected CPU RuntimeSession 的 `snapshot_free_joint_native_v1()` 返回当前边界具名自由关节位置与速度的拥有值副本，含 sample、materialization、时间、单位和速度坐标约定；它不推进物理。该接口不提供力传感数据；基于 USD 的 body-COM 原生读回使用既有 `snapshot_v1` 投影。

GeoPhys 的 `GeoPhysRuntimeBoundary.read_model_snapshot()` 委托 provider 的 `RigidSolver.read_model_snapshot()`，从该次物化的有效字段复制 body、joint、actuator、equality 和 tendon 值；session build facts 将 provider ID 绑定到同一来源名称。该快照不推进物理，缺失字段明确标注 unavailable。Isaac F06 另保存同一 bootstrap 边界的公开 Jacobian 和 tensor 连杆姿态，供轴方向与来源独立比较；读取前后物理计数必须一致。这些只读事实不构成跨 provider 功能认证。

## 4b 有界物理控制路线（历史记录）

本节保留原 4b 实验时点的 source、控制语义和证据；其中 candidate UID 已退休，当前正式构造使用上文 `make_env` 和 profile 配置。历史文字中的候选接口不能作为当前 UID 可调用的声明。

版本化 `pickcube-physical-candidate-v1`（MuJoCo／GeoPhys CPU）和 `pickcube-isaac-physical-candidate-v1`（Isaac Sim 6.2／CUDA、F06）通过既有 factory、SelectedReferenceEnv 和 RuntimeSession 提供 Panda 七臂及受源约束的成对双指 effort；直接贡献的限幅不代表与保留的原生 position drive 叠加后的总力。每个 interval 的贡献由 session 持有并清理；MuJoCo／Isaac 逐子步重施各自的有效写入，GeoPhys 保持本 interval 的公开广义力并在结束时清零，其独立 `hold_reapply` 声明当前拒绝。重复贡献、无效映射和未经协调的完整 PD 与活动 drive 组合被拒绝。原 source 的 tendon、equality 和 mimic 不变，不能由此推断两根手指可独立任意施力。

同一共享 Controller 可使用具名关节参考或 R3 末端参考。质量矩阵版本采用各 source 在指定初态公开读回的固定降维矩阵，限定 0.15 rad／0.019 m 状态邻域，并只在声明的 cadence 和原生 drive 已禁用的有界 fixture 中使用；它不是通用动力学模型或力传感器。MuJoCo／GeoPhys 使用公开 actuator 隔离，Isaac 使用公开增益接口，原始 source 未改写。直接 effort 路线仍允许按声明与 source drive 共存。

MuJoCo 的独立版本化自由体和 Robot hand fixture 分别验证实际外力响应与 world force、body-local 偏置点和点参考矩的语义；手部旋转后逐子步更新 frame 和 Jacobian。自由体与手部证据不代表其他 provider 的 BodyWrench 物理验证。所有物理响应为运动观察，ACK、计算力矩及公开模型读回不作为独立测力。

各次直接 effort 和外力实验的中间版本证据已按实际受影响路径作有界关联；最终版本的参考 Controller 对照不代替逐输入实验。具体接受范围及原失败见[002 独立主审](../maintenance/reviews/20261106_4b_attempt002_sol_review.md)。

## 4c 有界 reset 控制路线（历史记录）

MuJoCo CPU 的 `pickcube-physical-candidate-v1` 可显式设置 `reset_switch=True`，在 `reset(options={'controller': 'r3-pose'})` 或 `'joint'` 时选择控制器；需要调节参数时可用 `{'controller': {'kind': 'joint', 'parameters': {'kp': 120.0}}}`。`physical_action_spec()` 返回当前输入语义、参数、身份和 generation；用 `bind_physical_action(values)` 生成该 episode 的输入并交给 `step`。旧 episode 的输入即使 shape 相同也会拒绝。`action_space_policy='fixed_semantic'` 在破坏已有 session 前拒绝不同语义；这个候选是单环境标量接口，不承诺原生 batch。

`reset_for_solution` / `step_with_solution` 可将既有 PickCube Solution 的绝对位姿送入 R3 reference 和具名关节 effort。该路线使用对应 MuJoCo source 的状态相关质量矩阵与 bias、禁用原生 position drive，并复用 Generic H5 v3 Recorder；记录的 ACK 和 admitted effort 不等于独立测力。seed 31 原任务成功和 A→B→A 证据经[独立主审](../maintenance/reviews/20261106_4c_attempt001_sol_review.md)有界接收，不扩展为其他 seed、source 或后端资格。任务 profile 将 MJCF actuator8 编写的 ±5 N 运行时配置为 ±10 N，与原 2c 任务配置一致；该成功不证明 ±5 N 条件。详情见 [4c 计划](../planning/stage4-4c-attempt001.md)和该 attempt 的 ignored 原始证据。

<a id="visual-state-binding"></a>
## 5a 显式 visual-state 绑定（历史有界接收）

`pickcube-physical-candidate-v1` 的 MuJoCo CPU Position 路线成功 reset 后，可将 `CameraGeometry` 交给 `env.bind_visual_state(camera)`，再用 `env.sync_visual_state()` 消费最新已发布的 typed boundary。`env.visual_model_info()` 返回 source closure、具名几何／材质／相机／灯光、renderer-only 所有权和限制；`env.visual_body_pose(entity_id, frame_id)` 返回拥有的 body-origin world pose 副本。这个显式入口属于已有 Env 和 camera owner，独立 visual model 只复制 CPU 状态并运行同步 kinematics，不调用 physics step 或 Controller。reset／close 清理自有 renderer；不转移 physics 所有权。

此候选要求同一 Scene／Artifact／source closure 的具名 scalar Joint、floating Joint 和 Frame；floating body 使用米、右手系、world body origin、wxyz，四元数正负等价。重复、缺失、错来源、stale 或不支持的变形表示拒绝。该接口是 binding-only：构造用的 camera geometry 不构成 RGB 请求；对该 profile 的 capture 明确拒绝，RGB 能力为 unknown。普通旧 camera 路径、state-only 默认和旧 codec 保持原语义。seed 31、MuJoCo 3.8.1 CPU、同一 PickCube source、单 Env 的两次边界已由 [Sol 有界接收](../maintenance/reviews/20261107_5a_attempt002_sol_review.md)；此结果不证明窗口、正式离屏 RGB、同步 observation、renderer 切换或 GeoPhys／Isaac／cross 支持。runtime finger cap ±10 N 与 source ±5 N 的既有边界不变。

视觉更新或其结果验证失败时，renderer binding 进入 fault 并尝试关闭自有资源；即便回滚后的 Frame poses 可核对，也须重建 binding，因为这不能证明所有 renderer 派生字段均已恢复。故障后不再提供 pose、sync、capture 或旧 receipt 作为当前结果；已返回给调用者的旧 receipt 只表示它原来的历史边界。`env.visual_binding_status()` 报告 fault 与 renderer close 的实际状态，close 失败时释放结果为 unknown；physics Env 不因该 renderer 故障被关闭。reset 后可重新 bind，已有其他 owner 不受此绑定清理影响。

<a id="observer-candidate"></a>
## 5b observer 路线（历史有界接收）

MuJoCo CPU 的 PickCube 候选及 Isaac 6.2 的 F06 候选可在构造时传入 `render_mode='human'` 或 `'rgb_array'` 和显式 `observer_camera`。`render()` 使用已发布边界；RGB 为拥有的 HWC float32 数组，窗口与任务 observation 分离。MuJoCo 的 RGB 路线检查 offscreen GL 附件为 `GL_LINEAR` 且禁用 framebuffer sRGB 写转换；无法核实时拒绝该帧并使 renderer fault。receipt 所述为未经色彩校准的 framebuffer RGB，不能推断标准 sRGB、已知原色或输入纹理色域。Isaac 候选将公开 PhysX body 位姿同步到 renderer-facing Fabric，再核对全部发布 body 和具名 frame；变换或时钟不一致时拒绝帧。其 RGB 声明为 RTX tone mapping 后的 sRGB 传递函数；采集前后核验指定 RTX 设置和 OCIO 文件摘要，未通过时拒绝该帧。该声明不校准原色或源素材色域。该候选依赖实际 F06 source／App，并不证明任意 Isaac 场景。

此前 Isaac 原生 viewport 的关闭会使共享 App 的物理时钟和运行态失效。当前选定候选使用 headless App 和 GeoChora 自有窗口；正常关闭窗口与 App 崩溃是不同情形，适用证据及限制见[诊断主审](../maintenance/reviews/20261107_5b_diagnostic_attempt002_sol_review.md)。

F06 候选可在 `make_env` 构造时另外提供 `task_camera=CameraGeometry(...)`，当前仅支持一个 world 挂载、与 observer 使用不同 camera ID 的相机，且需与同一 TaskArtifact 关联。每次 reset 的现有 Isaac 场景 owner 会创建该 USD camera；`env.task_camera_binding()` 从当前原生场景核验并读取几何、source、相机路径与状态边界。它是几何绑定，不自动采集 task RGB、depth 或 segmentation；reset 替换场景并重新绑定，close 释放场景。它不表示通用挂载或同步 task observation 已实现。真实场景观察相机运动和读回已在 F06 具体配置下有界接收。

PickCube physical candidate 的 MuJoCo CPU observer 与 GeoPhys CPU rasterizer observer 也可在构造时声明一个 world-mounted `task_camera`。任务相机与 observer 的 ID 必须不同；MuJoCo 当前还要求两者的 clip 和分辨率相同。`task_camera_binding()` 读取各自 renderer owner 的实际 camera；它不创建自动 observation。这两条 CPU 路线的真实窗口、相机隔离和 RGB 证据已按各自限定范围独立接收。

5c 实施候选提供单相机同步 RGB：selected-reference 路线在 `make_env` 同时传入 `task_rgb_camera=CameraGeometry(...)` 和固定的 `task_renderer`（`mujoco`、`geophys` 或 `isaacsim`）；组件路线使用 `CameraSpec` 并由该 task 的生命周期构建 camera provider。reset 和正常 step 的 observation 自动包含 `task_rgb`（HWC、float32、0–1 的 owned host copy），无需另调 `.render()`。selected receipt 包含发布状态边界、采集阶段及 renderer 身份；组件 receipt 区分 requested camera 与 renderer-native realized camera，类型为 `task_env.environment.CameraRendererReadbackV1`。`env.metadata['task_rgb_v1']` 记录色彩语义，renderer 颜色不作跨设备标定。Env 创建时固定 renderer，reset 不接受更换；旧 `task_camera` 只声明几何，不与新 `task_rgb_camera` 同时使用。

G05 5c attempt003 的实现与验证仍待 Sol 独立主审。selected 非 Position task RGB 需要带 canonical `SceneDefinition` 和 source-closure identity 的 source；Core 由实际 Artifact/source 解析具名 joint/frame binding 和 renderer state requirements，并在 reset/step observation 前发布与 RuntimeSession boundary/clock 一致的 typed state。缺少或过期 identity、binding 或 publication 会 fail closed。该 attempt 的非 Position 生命周期合同使用公开 `make_env`/SelectedReferenceEnv 与受控 Runtime；这不等于实际 non-Position task source/native route。Marker 示例此前在 renderer/physics 前因 asset closure 缺 source-bound receipt 被拒绝，不能据此声称它已经通过。

组件 camera 的 attempt003 候选目前只在 GeoPhys CPU rasterizer compute 路线上验证：单台 task camera、HWC float32 RGB、无 depth、有限 FOV/near/far，并要求相机尺寸等于 renderer framebuffer。Core 将相机 pose 与光学值写入实际 GeoPhys task camera，核对其独立 native readback 后才采集同步帧；不一致时拒绝。真实 Pendulum 用例是 world-mounted 96×72 相机。另有受控 camera spy 检查解析出的 body-mounted pose 会更新同一 binding，但尚无真实 native body/site-mounted camera 证据。多 task cameras、不同 framebuffer extent、depth、非 GeoPhys component renderer 不在这个交集内。attempt003 对 selected PickCube GeoPhys CPU、GeoPhys CPU × MuJoCo renderer-only 和 Pendulum 组件路线保存了当前源码实测；其它原生与 Isaac 路线只在代码和输入未受本次改动影响的范围复用历史证据，具体适用性由该 attempt 报告列明。


PickCube 的 GeoPhys CPU joint-effort 候选也可请求 observer，使用具名的 GeoPhys `rasterizer` compute 路线。它检查材质和灯光资源报告，缺失必需特性或使用默认太阳光时拒绝采集；PickCube 的 authored `top` trackcom 聚光灯和默认头灯使用同一公开状态边界更新；源零位质量中心由编译模型计算，实时质量中心由公开 body pose 和质量计算。投影能力未覆盖或其他 authored 灯光设置未准入时拒绝采集。相机有限 near/far 使用光轴距离，当前只准入无粒子、TAA、overlay 和 native graphics 的 CPU mesh／analytic 组合。若材质和灯光检查通过，RGB 从 renderer 的 ACES 后 gamma 2.2 值转换到 sRGB 传递函数；原色及源素材色域未校准。此前使用默认灯光的 CPU 离屏试验仅为探索证据；后续使用源灯光的所选 rasterizer 真实窗口/RGB 和 5b 相机隔离已按限定范围接收，这不代表同步 task observation 已接通。

5b attempt001 的未接收历史见 [Sol 主审](../maintenance/reviews/20261107_5b_attempt001_sol_review.md)；三路线 5b 当前接收范围与限制见[最终主审](../maintenance/reviews/20261107_5b_diagnostic_attempt003_sol_review.md)。同步 task observation、renderer 切换和 cross 组合仍属 5c，尚未完成。
