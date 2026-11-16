# G06 CUDA 并行环境：项目与上游调研

日期：2026-11-15。性质：源码／官方资料调研与设计建议；不是 G06 实施、native 验收或新 Qualification。本文响应维护者本轮提出的五类问题，供补充材料和后续 6a～6c 工作包使用；不替代[现行 G06 Goal](../goals/06-parallel.md)、[交接记录](../maintenance/20261115_g06_agent_handoff.md)或既有接收结论。

维护者补充要求后的具体版本目标、模块落位、设备／终止／相机合同及执行窗口，统一收于[G06a～c 实施方案审批稿](stage6-parallel-execution-plan.md)。本文保留调研基线，实施以维护者批准后的方案和当前源码为准。

## 1. 结论与调研基线

**建议保留既有 `make_parallel_env` 入口，复用同一 Task 注册、声明、source 构建及 TaskDefinition；以 CUDA tensor 为并行数据路径，扩展既有 batch lifecycle 和 provider owner。不要复制完整的 ParallelTask／ParallelRobot／ParallelReferenceEnv。**

本轮维护者新约束是并行环境使用 CUDA，不把 CPU physics 或 CPU 多进程方案纳入拟议交付路线。注册、资产编译、资源协调仍会有 CPU 控制面；这不等于使用 CPU 仿真。正常 action → control → physics → state → task evaluation → observation 应驻留 GPU；reset 控制面、Recorder 和显式调试读回须单独说明，不能宣称整个程序完全没有 CPU 工作。

| 调研对象 | 实际身份 | 调研结果的范围 |
| --- | --- | --- |
| Geochora 输入 | `4c72be5332fc851eada2eb15d25a5bb418768188`；输入 `task_env` tree `1f6ab03cde3e9075821cc59a09240637a4c4d535` | 本地 develop 与 stage5 分支相同；初始只有受保护的 `MUJOCO_LOG.TXT` untracked |
| Geochora 内 GeoPhys | `c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7` | 固定 pin，未升级、未切换 |
| GeoPhys 独立 checkout | `env_task_design`，`db09dfbe80ed66611f177d2f8c7e73d026ddb478` | tracked clean；确有旧 `task_env/runtime/providers/static` |
| GeoPhys 远端 main | `2110d359a90f3fbcea89d35d7756a523ebd91cde` | 通过 GitHub API 查询分支、完整树及选定源码；本地缓存的 `origin/main=9a43b920` 不能代表最新 main |
| MuJoCo／MuJoCo Warp | 当前正式 release 均为 4.0.1，2026-11-11 发布 | Warp 调研源码另冻结到 `ab6e192b8da2946f3c8908e2155cae7fa27cac66` |
| Isaac Lab | main `d7e49f0af7ee6dd4e211ecc2ef99628ae91bb290` | latest release API 返回 v3.0.0；下文具体源码结论指该 main，不将 main API 当作旧版接口 |
| ManiSkill | `62ff3a5896b4d5b4cf0ac4c8d79afe600c9404a3` | 使用迁移后的 `mani-skill/ManiSkill` 仓库 |
| mjlab | `6ab9846ea068714678fd0e9f791f898c6b697b20` | 直接 MuJoCo Warp＋PyTorch 的主要参考 |

先使用了 CodeGraph。Geochora 索引有 drift，按工具提示读取当前磁盘源码；独立 GeoPhys 的 CodeGraph 服务未找到可用索引，转为源码检索，没有重建索引。

仅查询安装元数据：Geochora conda 解释器为 MuJoCo 3.8.1、Torch 2.14.0、Gymnasium 1.3.0，未发现 `mujoco-warp`／`warp-lang` distribution；既有 Isaac 专用解释器为 Isaac Sim 6.2.0.0、Torch 2.11.0+cu128、Warp 1.18.0、MuJoCo 3.12.0。两套环境不能按目录名或另一解释器的版本推断兼容性。本轮没有安装／升级依赖，没有启动 SDK／App 或 physics。

调研输出复用一个阶段分支 `codex/v211-stage6-parallel`，从上述已同步的本地 develop 创建；只写本报告及调研证据。未创建额外 worktree，未更改 develop／main／tags／provider pins，未 push。

## 2. 三家仿真器的并行能力

### 2.1 Isaac Sim：原生 GPU 并行可用，Geochora 的正式 batch 适配仍缺失

Isaac Sim 6.2 提供 Cloner／GridCloner、physics replication、环境间 collision filtering，以及 articulation／rigid-body Tensor views。USD 用于构建；运行期批量读写应走 Tensor／Fabric 路径，而不是逐 prim 查询 USD。[Cloner](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/py/source/extensions/isaacsim.core.cloner/docs/index.html)、[physics 数据通路](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/physics/new_physics_engine.html)

对本项目的适配方式：

1. 共同声明产生一个环境模板，由 Isaac adapter 创建 B 个 env namespaces，完成实例复制、接触隔离和 native row 映射。
2. 创建批量 articulation／rigid views，绑定具名 joint／body／frame；控制按整批提交，在每个 physics substep 推进一个 native scene。
3. 对选定 env IDs 写 root pose、joint state 和控制器 reset 状态；不能调用整个 World reset 冒充部分 reset。
4. native stage 的全局时间与每个 episode 的逻辑时间分开；部分 reset 不要求把整场景物理时钟归零。
5. 相机须为各 slot 发布实际独立图像。复制一张窗口图给 B 个 slot 不是 batch observation。

限制：当前 G05 的 Isaac 单环境 source、mimic、effort、相机与 App 生命周期证据不能自动覆盖克隆后 B>1。需重新验证 batch source 映射、复制限制、tensor row ordering、共享 App 的 teardown、异步图像完成及 reset 后帧身份。

**分类：EXTEND_EXISTING。** 扩展既有 Isaac session／native I/O 和 renderer owner，不让 Task 启动 App，也不将 Isaac Lab 的 Env 作为另一套 task lifecycle 嵌入 Core。

### 2.2 MuJoCo：并行能力由执行实现决定，升级 4.0 并不自动得到 CUDA batch

需要修正一个前提：MuJoCo 在 4.0 之前已经有 Warp／MJX 并行路线；3.7 官方文档已描述 MJWarp。因此“必须到 4.0 才有并行”不准确。但**本轮若采用当前 MJWarp 4.0.1，其依赖确实要求 `mujoco-core>=4.0.0`、`warp-lang>=1.15`、Python>=3.11**。建议候选使用修复了 4.0.0 已知问题的 4.0.1，并冻结确切依赖组合；已另外读取 v4.0.1 release tag，确认依赖、masked reset 及 renderer exports，而不只检查 main。[3.7 MJWarp 文档](https://mujoco.readthedocs.io/en/3.7.0/mjwarp/)、[release 依赖声明](https://github.com/google-deepmind/mujoco_warp/blob/v4.0.1/pyproject.toml)、[4.0.1 changelog](https://mujoco.readthedocs.io/en/latest/changelog.html#version-4-0-1-november-11-2026)

| 路线 | 实际方式 | 本轮判断 |
| --- | --- | --- |
| C MuJoCo／`mujoco.rollout` | CPU 单次推进／CPU 线程批量 | 保留 scalar 基线，不作为本轮 CUDA parallel 路线 |
| MJX JAX | JAX 批量执行 | 合法候选，但本项目已有 Torch device 合同，不宜同时引入第二套 JAX task 数值层 |
| MuJoCo Warp | 一个共享 model＋B 个 world 的 device data | 推荐的 MuJoCo CUDA batch 候选；以独立 implementation/profile 与 CPU MuJoCo 区分 |

实际接口是 `put_model`、`make_data/put_data(nworld=B)`、`step`；`reset_data(..., reset=mask)` 有 device per-world mask。model 参数可按字段声明 batch size，不能把共享第一行原地随机化后声称只影响一个 slot。[I/O 源码](https://github.com/google-deepmind/mujoco_warp/blob/ab6e192b8da2946f3c8908e2155cae7fa27cac66/mujoco_warp/_src/io.py#L412)

还需单独适配：

- 公共 action 必须经现有 Controller 绑定为正确的 ctrl／generalized effort／body wrench；不能把 N·m 直接改名为无量纲 native ctrl。
- 4.0 的 API／包拆分、源模型变化和旧 3.8.1 参考行为分别检查，不在现有解释器中直接覆盖依赖。
- `put_model` 对 actuator、equality、geom、sensor、integrator 等做真实准入；支持 MuJoCo MJCF 不等于所有字段在 Warp 中等价。
- 固定 contact／constraint 容量及 overflow 要有明确故障策略；不能为减少同步而忽略溢出。
- f32、warmstart 和不同求解实现不应被描述为与 CPU f64 逐位一致。

MJWarp 当前还有批量 renderer，提供 `RenderContext`、`refit_bvh`、`render` 与按 camera 解包接口；输出原始像素布局并非直接就是公共 RGB tree。需将 world／camera 索引、分辨率、dtype 与完成 fence 映射到 Geochora 合同。[公开 exports](https://github.com/google-deepmind/mujoco_warp/blob/ab6e192b8da2946f3c8908e2155cae7fa27cac66/mujoco_warp/__init__.py)、[批量渲染说明](https://mujoco.readthedocs.io/en/latest/mjwarp/#batch-rendering)

**分类：EXTEND_EXISTING＋必要的新 native adapter 实现。** MuJoCo Warp 是当前 scalar MuJoCo I/O 不具备的原生 API，因此需要对应 lowerer／device 实现；它仍从既有 RuntimeSession／provider dispatcher 接入，不创建第二种 Runtime 生命周期。

### 2.3 GeoPhys：已有 rigid native batch；旧 static 目录不是待直接恢复的功能包

三个对象必须分开：

| 对象 | 已核实内容 | 对本轮的含义 |
| --- | --- | --- |
| GeoPhys 当前 main | `SimulationExecutionLayout(mode="homogeneous_batch", world_count=B)` → `materialize_rigid` → `BatchedRigidSolver`；共享模型、world-local 状态和限定接触／约束 | 已有真正的 native rigid batch，无需从零再造 shared-template rigid solver |
| Geochora 当前 pin | 已有同构 rigid batch planner／solver、fixed tendon／观测相关实现；planner schema v25，main 为 v26 | 这些能力不是 main 才刚出现；仍须针对 pin 与实际 Task source 逐项准入 |
| `env_task_design/task_env/runtime/providers/static` | 8,441 行旧 TaskEnv 物理实现，含多个 profile | 同一目录名下既有 fused batch，也有逐 world scalar reference，不能统一归类 |

GeoPhys 的 FEM／MPM provider 仍报告 scalar；`materialize_fem/materialize_mpm` 在 batch 物化前拒绝。当前 main 没有 `task_env/` 子树。**未找到 FEM／MPM native batch、batch coupling 或异构 multi-block 已实现的依据。**[main 批量架构](https://github.com/SCAILab-USTC/GeoPhys/blob/2110d359a90f3fbcea89d35d7756a523ebd91cde/docs/architecture/homogeneous-batch-runtime.md)、[materialization 准入](https://github.com/SCAILab-USTC/GeoPhys/blob/2110d359a90f3fbcea89d35d7756a523ebd91cde/src/solvers/materialization.py)

旧 static 的具体路线：

| profile | 实现 owner | 能否直接算作本轮 native CUDA batch |
| --- | --- | --- |
| `hinge_or_slide_no_contact_v1` | 专门的窄域 static physics | 有实现，但支持范围很窄，且已退出 Geochora 当前路线 |
| `articulated_fused_no_contact_v1` | 共享模型的 Torch 批量数值实现 | 有 batch 实现；不是完整接触仿真 |
| `articulated_fused_ground_contact_v1` | Torch／Triton 等实现的限定 ground rows | 有 batch 实现；不代表任意 Panda 物体接触 |
| `articulated_ground_contact_v1` | `StaticTemplateRigidSolverReference` 创建 exact-B scalar solvers，并循环 step | 不能用作 native batch 证明 |
| `rigid_batch_v1` | 委托 GeoPhys 的 `BatchedRigidSolver` | 是现有 GeoPhys native batch 的适配，不是另一套新 solver |

来源：[static profile](https://github.com/SCAILab-USTC/GeoPhys/blob/db09dfbe80ed66611f177d2f8c7e73d026ddb478/task_env/runtime/providers/static/profile.py)、[runtime 分发](https://github.com/SCAILab-USTC/GeoPhys/blob/db09dfbe80ed66611f177d2f8c7e73d026ddb478/task_env/runtime/providers/static/runtime.py#L537)、[逐 world reference](https://github.com/SCAILab-USTC/GeoPhys/blob/db09dfbe80ed66611f177d2f8c7e73d026ddb478/task_env/runtime/providers/static/reference.py#L282)。

Geochora 在 `0ff2d846a36c7014d2b40a530f52d99e64266ff9` 的 S4 主动移除了 static physics／profiles／workspaces／kernels；当前 typed config、factory、CLI 和[retirement 检查](../../../../../task_env/diagnostics/tasks/test_s4_static_retirement.py)均保留显式拒绝。该历史可通过 `git show 0ff2d846:docs/module/task_env/p2_0_s4_static_solver_retirement.md` 读取；不修改冻结报告。

当前 Geochora 有两项可复用但不完整的基础：

- [SceneBatchRuntime](../../../../../task_env/runtime/providers/merged_scene.py)：构建时复制／合并 scene，以一套 solver 推进；但每步 host NumPy 读回，跨 slot contact exclusion 的构造规模随 slot/body 对组合增长。它不是三 provider 的 selected batch dispatcher。
- [GeoPhysRigidBatchRuntime](../../../../../task_env/runtime/providers/geophys/rigid_batch.py)：已委托原生 BRS，明确为 host-only；device read／step／reset、world randomization、独立 task rendering 等未接通，ground/domain 也在桥接层被拒绝。当前公共 batch factory 没有选择这条路线。

GeoPhys 当前 public batch state/observation API仍以显式 host readback 为主。solver 内有 device fields、selected-world render snapshot，不等于已经有完整的 Agent batch observation port。[public BRS facade](https://github.com/SCAILab-USTC/GeoPhys/blob/2110d359a90f3fbcea89d35d7756a523ebd91cde/src/solvers/rigid/batch/solver.py#L959)

main 另有 loaded component 的公开`RigidBatchComponentSolver.borrow_operation_inputs/prepare_operation`，可以绑定已有资源和导出 operation，值得优先评估为 device transport 的组合入口；其普通`read_state`仍通过host staging，reset会retire旧operation/borrow。它不能直接证明已具有Geochora需要的Torch状态、控制和mask合同，也不能忽略当前pin与该loaded路线的差别。[loaded batch公开接口](https://github.com/SCAILab-USTC/GeoPhys/blob/2110d359a90f3fbcea89d35d7756a523ebd91cde/src/solvers/rigid/batch_deployment.py#L277)

**建议的开发位置与顺序：**

1. 先评估并组合GeoPhys既有公开materialization、operation borrowing和snapshot入口；对仍缺失的runtime-facing device control／state／masked reset／completion合同扩展既有owner。Core 不读取 solver.storage 私有字段补洞。
2. Geochora adapter 消费这些公开接口，接入共同 source／Controller／clock／publication。
3. 对实际任务 source 执行 batch planner。active contact 目前主要是 sphere／box 的限定交集；Panda／Nut 资产是否准入必须查实际 mesh／convex、transmission、equality、integrator 和接触需求。
4. 若缺少所需形状／约束，由 GeoPhys rigid batch owner 扩展。不得通过静默换碰撞模型、取消接触或修改物理参数来获得 PASS。
5. 只有既有 owner 经分析确实无法承接时才评估新的数值实现；本次尚无此证据。

“static”在这里应被准确改写为 **固定 topology 的共享模型＋每 world 可变状态**，不是“静态刚体”、CUDA Graph，也不是 FEM quasi-static。现有 BRS 已具备这一基本组织方式；真正缺口是公开 device 交互、实际资产能力与正式 TaskEnv 集成。

## 3. 下游开源库的借鉴及不能照搬之处

| 参考 | 可借鉴的具体设计 | 对 Geochora 的落点／边界 |
| --- | --- | --- |
| Isaac Lab | scene/asset 声明与 MDP 计算分开；批量 entity views；env IDs/origins；reset event、action、observation 等按职责组合 | TaskDefinition／Robot 声明与 native mapping 分开；不需要整体引入其 manager 层 |
| ManiSkill | 同一个 Task 类支持单例／批量；reconfiguration 与 episode initialization 分开；`env_idx` 指定部分 reset；Robot 的 articulation/controller 以 batch 视图工作 | 声明物体与 Robot 复用；构建期结构随机化和每 episode 数值随机化分开 |
| mjlab | MuJoCo Warp 的实际 Torch bridge；mask reset；model fields 和 device data 区分；固定 buffer 与 Graph 引用 | 是直接接 MJWarp 最具体的参考；复用接口设计，保持本项目自己的状态／控制语义 |
| Gymnasium／Farama | 明确 next-step、same-step、disabled 三种 autoreset，metadata 公示模式；same-step 保存 final obs | 冻结一种模式并为旧 SB3／RSL caller 做明确翻译，不混用不同库的 final key |

具体证据与审阅结果：

- [Isaac Lab DirectRLEnv](https://github.com/isaac-sim/IsaacLab/blob/d7e49f0af7ee6dd4e211ecc2ef99628ae91bb290/source/isaaclab/isaaclab/envs/direct_rl_env.py)本身使用 `gym.Env`，并不要求继承 `gym.vector.VectorEnv`。因此“选定某个 Gym 基类”不能代替 batch 合同设计。
- [InteractiveScene](https://github.com/isaac-sim/IsaacLab/blob/d7e49f0af7ee6dd4e211ecc2ef99628ae91bb290/source/isaaclab/isaaclab/scene/interactive_scene.py)有 env origins、selected env reset 与 device mask；映射不能假定 native buffer 每隔固定行必然对应一个 env。
- [ManiSkill task template](https://github.com/mani-skill/ManiSkill/blob/62ff3a5896b4d5b4cf0ac4c8d79afe600c9404a3/mani_skill/envs/template.py)把加载场景与初始化 episode 分开；[vector wrapper](https://github.com/mani-skill/ManiSkill/blob/62ff3a5896b4d5b4cf0ac4c8d79afe600c9404a3/mani_skill/vector/wrappers/gymnasium.py)明确限制 partial reset 与自动 reconfiguration 的组合。
- [mjlab sim](https://github.com/mujocolab/mjlab/blob/6ab9846ea068714678fd0e9f791f898c6b697b20/src/mjlab/sim/sim.py)直接使用 `reset_data(reset=mask)`；[TorchArray／WarpBridge](https://github.com/mujocolab/mjlab/blob/6ab9846ea068714678fd0e9f791f898c6b697b20/src/mjlab/sim/sim_data.py)通过 Warp/Torch 共享内存并维护稳定引用。共享内存仍要求正确 stream、完成和 lifetime。
- [Farama autoreset 说明](https://farama.org/Vector-Autoreset-Mode)区分模式和 final observation，不能把 ManiSkill 的 `final_observation`、Gymnasium 的 `final_obs` 与 SB3 的 `terminal_observation` 当作同一个既有字段。

不能照搬：

1. mjlab 当前[step 源码及其 docstring](https://github.com/mujocolab/mjlab/blob/6ab9846ea068714678fd0e9f791f898c6b697b20/src/mjlab/envs/manager_based_rl_env.py#L387)明确接受 reward／termination 使用滞后一个 physics substep 的 derived quantities。本项目要求同 boundary 的公开 state／evaluation／image，不能继承该取舍。
2. Isaac Lab final obs 受 `compute_final_obs` 配置控制；本项目一旦承诺 same-step 且可用于 truncation bootstrap，就必须保存真实终止状态和 required 图像，不能默认省掉。
3. ManiSkill BaseAgent 某些 passive-force balancing 会通过禁用 link gravity 处理。本项目保留既有物理参数及施力语义，不采用这一替代。[BaseAgent](https://github.com/mani-skill/ManiSkill/blob/62ff3a5896b4d5b4cf0ac4c8d79afe600c9404a3/mani_skill/agents/base_agent.py)
4. 最新 Isaac Lab 的 `TiledCamera` 已是兼容 alias；新适配应核对具体 SDK／相机 owner，不按旧教程类名冻结方案。[alias 源码](https://github.com/isaac-sim/IsaacLab/blob/d7e49f0af7ee6dd4e211ecc2ef99628ae91bb290/source/isaaclab/isaaclab/sensors/camera/tiled_camera.py)

额外检查了 MuJoCo Playground 当前 main `fa0f150cb82b350a6cbca8f4f56d25e2c9b3e93a`：经典 `_src/mjx_env.py`／单文件 wrapper 路径已迁移，树中 `rss2025/` 保留历史实现。故本次不把旧 JAX/vmap 示例当作当前 main 架构依据，主要采用与本项目 Torch 路线更贴近的 mjlab。

## 4. 任务构造：保留入口，复用声明与语义

维护者的 a／b 不必二选一。**入口可以分开，任务实现仍然共享。** `make_parallel_env` 已经存在，无需再新造一个 factory；独立的 parallel registry 可以保留为能力索引，而不是再注册一份完整 Task 实现。

现有[parallel registry](../../../../../task_env/vectorization/registry.py)已经支持把同一个 environment class 绑定到 framework factory。问题是旧 [factory](../../../../../task_env/vectorization/factory.py)仍走 `build_runtime=False` component 流程，并明确拒绝 selected public config；正式四任务不能仅通过移除 guard 或补 decorator 得到 batch。

建议构造顺序与当前任务流程对齐：

```text
同一 task UID／任务配置
  → TaskArtifact／Scene 声明，确定 source 与 Robot
  → 共同 source composition／lowering，解析具名资源
  → Controller 规格、资源归属与能力匹配
  → TaskDefinition／observation schema 绑定
  → scalar 或 homogeneous batch 的 materialization plan
  → 同一 RuntimeSession 职责下的具体 native adapter
  → 既有 lifecycle 执行 reset／interval／fault／close
```

前半段负责声明和解析；后半段在 scene 物化、数据布局和 batch 执行上分流。native row／prim offset／per-world 数组属于 adapter／binding，不写进 Task 的奖励或成功条件。

| 内容 | 复用方式 | 需要批量适配的部分 |
| --- | --- | --- |
| task 注册、默认配置、Artifact、阈值 | 共享同一 owner | 执行配置增加明确 batch/device 能力，不另造 parallel UID |
| Scene 物体／资产／Robot 声明 | 逻辑模板复用一次 | Isaac clone、Warp nworld、GeoPhys materializer 各自 lowering |
| 初始状态／域随机化 | 共享分布、范围、依赖和 reset 规则 | 每 slot 独立 RNG；将 selected payload 写入 native batch |
| Controller | 规格、具名通道、SI 单位及控制律语义复用 | device 运算、每 slot memory、resource row binding、mask reset |
| TaskDefinition | 同一公式／predicate／temporal rule | 将 scalar-only 运算改成 batch-aware tensor kernel，避免按 B 循环调用 scalar Task |
| observation／RGB | 共享字段名、单位、Frame、dtype | 每个 leaf 前置 B 轴，图像与相应 boundary 绑定 |
| Recorder | 沿既有 owner 扩展 | transition 加 env／episode／generation 身份，不让 physics 等待每步全量同步 H5 写入 |

对数值复用不要求另建通用 tensor 框架。优先把 Task 计算收敛为少量 array/tensor 运算；必要的 NumPy／Torch 后端实现共用公式、参数和语义 owner，以边界样本校验一致性。禁止在 CUDA 路径隐式 `np.asarray(tensor)`、`float(tensor)` 或逐 env `.item()`。已有 scalar f64 参考不因批量 f32 自动改写。

`TaskBuildRequest`／`SourceBoundTaskBuilder` 的既有职责应扩展为能够接收 batch layout／seed selection；不能让 batch builder 从另一个 scalar Env 读取私有运行状态。[共同构建 owner](../../../../../task_env/environment/reference_binding.py)

## 5. 建议冻结的基础抽象与数据合同

以下是设计建议，尚未改动生产 API。

### 5.1 基础抽象

- **任务：**继续以 `TaskDefinitionBase` 为语义扩展点，不增加 `ParallelTaskDefinition`。
- **生命周期：**继续由 `TaskLifecycleAdapter` 共享任务语义；扩展 `BatchTaskLifecycleAdapter` 的正式配置、tensor identity 和 per-slot episode 支持。
- **公共 vector façade：**扩展既有 `HomogeneousVectorTaskEnv` 的 device 路径和标准五元组；不要继承整套 `SelectedReferenceEnv` 来复制 scalar 私有流程。
- **物理交互：**扩展 `DeviceBatchRuntimeProtocol`、`DeviceBatchState`、`DeviceBatchTransition` 及既有 RuntimeSession owner；typed joint effort／wrench／Position 的资源与单位语义必须随 batch 保留。
- **学习库：**SB3／RSL／Gymnasium 适配留在各自 wrapper。需要严格 Gym VectorEnv 形式时加薄适配；它不拥有第二份 Task／physics 生命周期。

当前公共 `make_parallel_env` 默认返回 remote SB3 VecEnv，标准 step 是 NumPy／IPC；但 local SB3、Homogeneous 和 RSL 已有 `step_device/reset_device` 等可选能力。这些基础需要复用，不能描述为全不存在。新 CUDA 正式路线须明确如何选择 device 五元组；保留旧 caller 的默认和 autoreset 语义，不静默改变其返回类型。[当前入口](../../../../../task_env/vectorization/parallel.py)、[device contract](../../../../../task_env/runtime/contracts.py)、[RSL adapter](../../../../../task_env/alg/rsl_rl/adapter.py)

### 5.2 固定 shape 与 device

令 B 为一个同构 native batch 的环境数。B=1 在 parallel API 中仍保留 batch 轴；单环境公开 API 维持现有非 batch shape。

| 数据 | 建议的 CUDA 合同 |
| --- | --- |
| 单个 Box action | `torch.Tensor[B, *single_action_shape]`；通常为 `[B,A]`，dtype 按已声明 action |
| Dict／多 Controller action | 保持同一 key tree；每个 leaf 是 `[B,*leaf_shape]`，不强制压成一个无法辨认单位的扁平向量 |
| observation | 保持单环境 observation tree；每个数值 leaf 前置 B 轴，dtype／单位／Frame 不变 |
| task RGB | 每个 camera key 对应 `[B,Hc,Wc,3]`；首批固定 camera 集合和分辨率，不以窗口拼图代替 |
| reward | `[B]`，float32 |
| terminated／truncated／reset mask | `[B]`，bool |
| episode steps／episode serial | `[B]`，整数；同一 generation 内固定 env ID→row 对应 |
| info | device tensor tree＋冷元数据；需要 list-of-dicts／NumPy 的消费方显式适配 |

所有 action row 都必须校验 shape、finite、bounds、device 和来源绑定；不能只检查 row 0。不同 Controller 的维度由同一次共同构建结果决定，不把所有任务固定为 Panda 的某个 A。BodyWrench 的力、力矩、Frame 和作用点保留 typed 意义。

现有 `HomogeneousVectorTaskEnv.action_space/observation_space` 保存 single space；新 device façade 应明确展示 batched space，另有 `single_*`；SB3 wrapper 继续符合其 own VecEnv space 约定。这是 API 适配项，不是可以悄悄修一行的字段变更。

### 5.3 时钟、RNG、坐标与 buffer

**每 slot episode 与全批 physics step 分开。** 可以用 native completed step 与每 slot episode 起点推导 episode time，但来源必须是实际公开 clock；不编造 SDK startup／reset 中未知推进。mask reset 不递增未选 slot 的 episode、task time 或 temporal state。

RNG 应按稳定 env ID 和 episode 流隔离；`seed=None` 继续选定 slot 的流，显式 seed 按冻结语义重启，不能因其他 slot 提前结束而改变本 slot 后续采样。provider seed 是 Core 派生且可报告的另一层，不等于 task seed。Nut 当前固定 seed19 provenance 的限制必须保留；不能自动用 base_seed+row 绕过它。

初始随机化分成：

| 随机化 | 处理 |
| --- | --- |
| pose、velocity、goal 等 episode 数值 | 能力允许时按 mask 写选定 slot |
| mass／inertia／friction 等物性 | 先确认 per-world 字段与 derived constants 更新；不可写共享模板污染其他 slot |
| topology／资产替换／B／容量／固定 observation schema | 整批 rebuild，或在执行前拒绝；不伪装成普通 partial reset |

公共 Task world 必须说明是每个环境自己的 world；Isaac／merged scene 的展示 offset 在 adapter 中转换，不能让 Task 重复补 offset。声明及绑定使用 entity-qualified names，native index 只在已编译的映射中出现。

`DeviceBatchState` 当前允许 runtime-owned view。缓存上一时刻对象并不保证保存上一时刻数据；需要 previous-state 的 task 必须在推进前保留所需的有限字段，terminal frame 必须在 reset 前 retain/copy。owned／borrowed、generation、lease、stream/fence 和下一次覆写边界都必须可查询；不以“零拷贝”省略生命周期。

初期建议同一 backend 专用进程内 colocate policy 与 simulation。既有 remote wrapper 通过 host NumPy Pipe 传输；若坚持 parent policy／worker simulation 且保持 CUDA tensor，则需要显式 CUDA IPC／共享 buffer／event／租约合同，不能把现有 remote 模式改个名称就算 device transport。不同 SDK 的 Torch／Warp 依赖应在选定执行包内验证兼容。

## 6. terminated／truncated 的处理建议

**首批建议只正式支持 same-step autoreset。** 这既符合 CUDA 训练连续采样，也能延续现有 SB3 caller 的模式。原始无 autoreset 接口可保留给明确 caller；不要求本轮新增全部模式。

正确次序：

```text
action → 完整 physics interval
  → 同一 post-step boundary 的 state／evaluation／required camera
  → 保存 done rows 的 terminal observation、image、info、旧 episode identity
  → reset(done mask)，只改选定 slot
  → 新 episode reset state／required camera
  → 返回五元组：reward／flags 属于刚结束的 transition；
     done row 的 obs 属于新 episode，info 指向真实 terminal obs
```

公共字段沿项目现有 `terminal_observation/reset_info` 合同评估；Gymnasium wrapper 可映射为 `final_obs/_final_obs`，SB3 wrapper 继续原约定。新旧 episode 身份必须能分别定位，不能只用一条当前 episode_id 解释两份观测。truncation 的 bootstrap 必须使用 terminal obs，而不是新 episode 的第一帧；terminated 与 truncated 不应被不可逆合并成一个 done。

第二种“terminated 后 mask，等整批结束”的方式需先区分两件事：

| 策略 | 实际含义 | 额外合同 |
| --- | --- | --- |
| 只 mask 采样／损失 | native physics 可以继续跑，但该 slot 不再贡献有效 transition | 锁存 first terminal obs，标记 active/valid mask，不把后续物理状态当作同一 episode 的合法数据 |
| 真正冻结物理 slot | 停止该 world 的物理、控制记忆、RNG 与接触历史 | 需要 provider 明确支持 active mask；零 action 不能阻止重力／接触，不能冒称冻结 |
| 忽略 success termination，统一跑 horizon | 成功只作为 metric，episode 仍持续 | 这是任务终止政策变化，不是简单的 autoreset 选择，不能修改既有成功／终止合同来实现 |

barrier 条件应是明确的整批 horizon 或“所有 slot 已锁存 terminated OR truncated”；**不能字面等待所有 slot 都 truncated**，因为提前终止且已冻结的 slot 不一定再增加时钟。该策略本轮可保留为后续设计，不加入默认实现量。

## 7. reference_env 与 RobotAgent 的精简和复用

### 7.1 已定位的真实负担

[reference_env.py](../../../../../task_env/environment/reference_env.py)当前 4,244 行、148 个方法；AST 统计中：

| 方法 | 行数 |
| --- | --- |
| `_prepare_reference_reset` | 570 |
| `_prepare_reference_step` | 310 |
| `_prepare_physical_control` | 296 |
| `_prepare_position_profile` | 172 |
| `_build_runtime_with_rollback` | 162 |

这不自动证明每段都应拆类，但说明不能把这个 façade 直接复制成 ParallelReferenceEnv。需按实际 owner 收敛：共同构建继续放 reference binding/source builder；控制 binding／interval 留既有 physical／Position execution owner；相机保留 renderer consumer；episode/fault/publish 由生命周期协调。按真实调用移动职责并删除旧重复逻辑，不用一层层 forwarding 只换文件名。

单任务代码量也须区分语义与 Solution：PickCube 的 task／specialization／observation 分别 407／600／52 行，Solution 另有 1,064 行；Nut task／specialization 为 171／504 行，Solution 另有 1,407 行。外部 Solution 不应被自动实例化到每个 batch slot。精简先针对构建与语义重复，不能将策略代码算成 Env 基类必需体积。

现有四任务的情况：

- Pendulum／TwoWheel 已有 NumPy scalar/batch 语义，可用作 device 向量化的起点。
- PickCube／Nut 的正式 TaskDefinition 仍要求 scalar `CanonicalTaskStateView`；共同类名及 `uses_unified_state_view=True` 不表示已经支持 tensor batch。
- 四任务及现行 controllers 中未发现 `evaluate_device/build_device_observation/convert_device_batch` 正式实现。device lifecycle 基础存在，但正式任务尚未满足其准入。
- 旧 batch host reset 先采整批再应用 mask；公共 RNG 和 device selected sampler 的独立性都要按 per-slot 流检查，不能只看未选 physics state 没变。
- 新 device batch 必须保留 source／Controller writer／scene interval 的一次提交，以及 render failure 后不发布 normal transition 的既有 fault 语义。

### 7.2 当前“RobotAgent”的实际 owner

当前生产代码没有名为 `RobotAgent` 的类；相关职责由 [RobotComponent／AgentComponent](../../../../../task_env/environment/protocols.py)、Panda／Pendulum 等具体 Robot、[RobotRuntime](../../../../../task_env/robots/runtime.py)、`ControlledSubjectV1` 与 Controller binding 共同承担。后续实现应沿这些 owner，避免按旧名称新建一个通用 Agent 大类。

建议继续区分：

| 层次 | 单环境与 batch 的复用规则 |
| --- | --- |
| Robot／Assembly 声明 | source intent、具名 joints/frames/actuators、Controller 可用规格共享；不启动 native SDK |
| 编译后的资源绑定 | 为执行布局解析 source／generation／env row；静态索引映射可共享 |
| live RobotRuntime／Controller | runtime-owned，状态和 target memory 按 B 组织；partial reset 只改选定行 |
| 多主体／装配 Panda | 保留子主体／writer／channel 归属，不能把“同一 slot 有多个 Controller”与“B 个 env”混成同一轴 |

尤其是 `default_controller` 通过 cached property 产生，并要求 bind once。**可以共享 Robot 声明，不能将一个已绑定的 Controller 实例同时分配给 scalar Env 和另一个 native batch。** 每个 materialization 持有自己的执行上下文；batch 内可由一套 vectorized Controller 维护 B 行记忆，不等于创建 B 个 scalar Env。

## 8. 对 6a～6c 的具体影响与推荐安排

本轮是调研，不启动实施 attempt，也不修改能力矩阵为“已支持”。

| 单元 | 应完成的实际工作 | 必须留下的证据 |
| --- | --- | --- |
| 6a | 冻结 CUDA 路线、任务／资产／Controller／source／renderer、B 和返回合同；接入共同 selected builder；batchize Task/Robot/controller device 语义 | 真实 caller 进入共同构建；shape／row identity／seed／mask／旧 command 拒绝；纯/fake 只说明合同 |
| 6b | 至少两条 CUDA physics 后端的真实小批量 construct/reset/非零step/render/obs；至少一条 native batch，目标优先均为 native | 不同 slot 使用不同 action／初态，测出状态与图像对应；记录进程、设备、传输和有效 native step |
| 6c | partial reset 只改选定 slot；整个 batch 切换 A→B→A；renderer 创建时固定 | 对比 post-step/pre-reset 基线；未选 state/time/controller/RNG/image 不变；旧 generation/view/command 失效；异常与 close 资源回收 |

拟议后端组合：

- **原路线优先：Isaac PhysX CUDA＋GeoPhys native rigid CUDA。** 先用固定拓扑、明确无接触的简单任务探查公共 device port 与正式构建；Pendulum 的 exact source／integrator 也必须准入，不能为了符合 BRS 的窄域配置而改参数。接触任务和四正式任务适配继续按 G06 范围处理，这个探查不是降级结案。
- **新增 MuJoCo Warp 4.0.1 为明确第三候选。** 若维护者希望本阶段三家都接入，就在实施包中明确纳入其适配和依赖迁移成本。G06 原文最低“两条”不是三家全部已获执行承诺；也不能遇到 GeoPhys 缺口后悄悄用替换名单规避该缺口。
- 若选定 GeoPhys 任务超出现有碰撞／约束交集，应在同一次规划中列出 provider 上游能力扩展，不恢复旧 Torch static solver 绕过 owner。

**6c 有一项必须提前解决的组合问题：** 三家各自 native renderer 成功，不代表存在一个固定 renderer 同时接受 A、B 的 batch 状态。当前 scalar 的 GeoPhys CPU physics × MuJoCo renderer-only 证据不能外推到 CUDA batch；Isaac RTX、GeoPhys selected-world snapshot、MJWarp batch renderer 也不是现成互通矩阵。应在 6a 先选定固定 renderer，验证其跨后端公开 state 投影与每 slot 图像能力；若缺失，作为 renderer adapter 的明确实施项。不得在 6c 静默换 renderer，或用 state-only 切换替代 required RGB。

优先验证的错误实现包括：所有 action 写 row0；native row 顺序错误；跨环境碰撞；共享随机化参数串行污染；部分 reset 清整批 Controller／pending wrench；previous-state 与当前 view alias；terminal RGB 被 reset 覆写；derived frame 比 joint state 早一 substep；只给各 env 返回同一 preview；remote NumPy 往返被标成 GPU direct。

首批 B 可从 2 开始、增加 3 以发现非二次幂布局假设；具体数量、RAM／VRAM、App、步数、墙钟、输出和共享锁仍由当次执行包冻结。吞吐可记录，不新增大规模性能、多 GPU 或 G07 完整三 provider×三 seed 验收。

## 9. 已完成核验、未验证项与下一步决策

已完成：当前磁盘 source owner/caller 调研、三个 GeoPhys 身份对照、远端 main 全树检查、static 分派与退休记录、四任务／Controller device hook 检索、源代码规模统计、两套解释器 distribution 元数据、上游版本和下游具体源码审阅。已 fetch/check `public/develop`，确认其落后于本地已接收基线，不据此回退本地成果。

未执行：依赖安装、MuJoCo 4.x 模型编译、SDK/App 启动、CUDA native step、性能测量、全量 pure/fake、offline H5 或完整 Solution。因此本文所有“建议接入”都不是实际 batch 支持声明。

文档核验：本次相对链接和文件引用无新增错误，`git diff --check`通过。全仓`validate_docs.py --mode current`未全绿，唯一当前错误为保护输入`MUJOCO_LOG.TXT`与v2.1.0迁移manifest的旧快照不匹配：manifest记120 bytes／SHA `dfb37ada202855d609f9e210cf79b287de78f2ded70e704ceeb544d17bf7ad4b`，本轮接手即为239 bytes，当前SHA `3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`，mtime为2026-11-10。保留日志和历史manifest，未为使检查通过而改写；79项历史链接问题仍由validator单列，不是本次新增。

实施前需合并维护者后续材料并确定：

1. 本阶段是“两条必达＋MuJoCo Warp 后续”，还是三家 CUDA 全部作为本轮实施范围。
2. 首批 task/source/controller，以及需要 GeoPhys 新增的真实碰撞／约束能力。
3. 公共 CUDA façade 的选择方式、same-step 模式和旧 SB3／RSL 兼容边界。
4. 固定 renderer 与 A→B→A 的确切可实现组合。
5. 允许 reset 控制面的小量 host 同步／采样，还是要求进一步实现 device-native RNG／mask 全程执行；不把该性能要求默认为已有 G06 门。

这些是具体方案冻结项，不是新增审批门。调研结论支持沿既有 owner 扩展；没有发现应重开 G05／E00～E16 或恢复退休 static 分支的理由。
