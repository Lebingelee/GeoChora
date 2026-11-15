# G06a～c CUDA 并行环境实施方案（维护者审批稿）

日期：2026-11-15。状态：`DRAFT_FOR_MAINTAINER_REVIEW`。本轮讨论修订输入 HEAD：`0c258085e12dc70bb86a60d462ff77b6a1520e45`，阶段分支：`codex/v211-stage6-parallel`。本次只交付方案；尚未安装依赖、改变 pin、运行 native 仿真或实施生产代码。方案批准后，由维护者转交实施 agent。

本文细化[现行 G06 Goal](../goals/06-parallel.md)，承接[项目／上游调研](20261115_g06_parallel_research.md)、[G06 交接](../maintenance/20261115_g06_agent_handoff.md)和[原始优化总账](post-5c-code-project-optimization-diagnostic-ledger.md)。总账的历史待办以[G05 逐项结案](../maintenance/reviews/20261114_e14_current_state_alignment_closeout.md)为准；下文引用其职责原则，不重开已经接收的 G05。

## 1. 拟批准的交付范围与决策

推荐：**统一 SceneDefinition／TaskDefinition，入口分开、声明和计算共享；首批 device API 使用 Dict action、B 轴 observation 和 same-step autoreset；先完成 canonical effort 的 CUDA 链，再接 batch Robot 信息及既有 R3／重力补偿。** 大规模 Env／Robot 精简在 G06 接收后另行规划。

维护者已确认以下范围。确认设计方向不等于依赖兼容性或 native 能力已经通过，也不构成开始实施的授权；讨论完成后再转交实施。

| ID | 已确认方向／仍待确定事项 |
| --- | --- |
| D1 | Isaac＋MJWarp＋GeoPhys 三条 CUDA 路线均须接通 Pendulum 和 PickCube，共六格；GeoPhys 优先复用 BRS，缺失的公开 device／资产能力成为必需工作，不再按可选第三路线处理。Isaac 6.2 固定方向不变；MuJoCo／MJWarp 4.0.1 精确组合仍需兼容验证后冻结 |
| D2 | 统一用户入口，主环境为 `/home/lly/miniconda3/envs/geochora`；按 provider profile 选择依赖解释器，共用源码。保留 Isaac 专用环境；MJWarp 隔离解析，不擅自升级主环境。隔离只在需要时引入 worker，不要求所有后端一律跨进程 |
| D3 | Dict action 各叶前置 B；obs 保持树结构并前置 B；same-step autoreset 完整保留终止观测与已配置图像。先验收 canonical action＋batch Robot，再验收 R3／模型／重力补偿。第二包的 provider 范围及是否属于 G06 总出口仍待确认 |
| D4 | 相机只作传感器挂载，不增加质量／惯量／碰撞。无相机、仅 observer、观测相机分开；具名 `obs["cameras"][name]["rgb"]` 已确认，dtype 尚待确认。几何／相机／时间／图像身份正确即可，一个共同 renderer 验收足够；推荐先验证现有 RayTracer，MJWarp renderer 备选，待维护者选择 |
| D5 | 主要数据全程 CUDA，允许必要 GPU 内部复制和少量 CPU 控制信息。参考 Isaac Lab／ManiSkill／mjlab 的核心设计和必要局部实现，不引入整套运行依赖。第 10 节具体代码落位仍为审批稿；无资产名／类名专属管线 |
| D6 | 在当前约 8 GiB VRAM／16 GiB RAM 机器验收。B=3 用于行隔离与生命周期正确性，不是容量上限；纯状态与渲染分别测量。4096 环境、16 control steps/s 是维护者 Go2 历史经验，作为参考，不直接变成 PickCube 或三后端统一硬门 |

剩余产品取舍：RGB dtype、共同 renderer 首选、R3 包覆盖范围／阶段出口。版本共存、设备互操作、公开相机输出和 GeoPhys 接触能力属于实施前应验证的技术事实，不要求维护者猜测结论。

## 2. 版本冻结与 MuJoCo 迁移

### 2.1 冻结单位是解释器 profile，而不是一个全局 requirements

| Profile | 当前事实／拟定目标 | 冻结方法 |
| --- | --- | --- |
| Isaac native worker | 当前专用环境：Isaac `6.2.0.0`、Torch `2.11.0+cu128`、Warp `1.18.0`、MuJoCo `3.12.0` | 保留 SDK 配套依赖；记录 Python、distribution、扩展包、driver、GPU、资产 source closure、可复现安装来源。禁止向该环境直接装 MuJoCo 4.0.1 |
| 隔离 MJWarp profile（必要时 worker） | 目标 `mujoco==4.0.1`、`mujoco-core==4.0.1`、`mujoco-studio==4.0.1`、`mujoco-warp==4.0.1`；Warp 候选严格固定 `1.18.0` | 独立环境解析依赖并验证；MuJoCo 元包／core／studio 对齐，保留 classic renderer 的受影响 scalar 能力。Torch 以当前 Core `2.14.0` 为首选候选，实际 wheel／CUDA build 与全部传递依赖经 6a 验证后落锁，不把尚未解析的组合称为已冻结 |
| 当前用户主环境 `/home/lly/miniconda3/envs/geochora` | 当前 Python `3.12.14`、MuJoCo `3.8.1`、Torch `2.14.0`、Gymnasium `1.3.0`、NumPy `2.2.6`、taichi-forge `0.6.3` | 保持统一入口和现有依赖；隔离验证不破坏主环境。是否迁移其 MuJoCo 在兼容结果明确后另行确定，不靠 PATH 随机选版本 |
| GeoPhys worker | 当前 submodule pin `c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7`；main 调研点 `2110d359a90f3fbcea89d35d7756a523ebd91cde` | 先以 pin 评估 BRS；需要升级时先批准具体上游提交和 ABI 变化，再更新 pin／profile。`env_task_design` 不是默认依赖，禁止浮动 main |

Menagerie 继续固定 `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。当前 Core 的 `mujoco>=3.8.1,<3.9.0` 与 GeoPhys requirements 的 `mujoco>=3.15.0` 已有不一致；实施包必须在依赖 owner 解决，不能靠 `--no-deps` 安装后忽略。Isaac profile 的绑定不由 Core 的 MuJoCo target 锁覆盖。

建议在 `task_env/dependencies/` 保存 profile 输入和经解析的精确 lock，参见第 10 节；运行时只读取选择结果和一次元数据，不逐 step 跑版本探针或重算包 hash。6a 的版本出口必须包含实际安装结果、wheel／lock hash、CPU 配置面与 CUDA 设备检查；当前表只有精确目标和已有环境事实，没有伪造完整 lock。

### 2.2 3.8.1 → 4.0.1 的实际差异清单

| 差异 | 当前影响／处理 owner | 通过证据 |
| --- | --- | --- |
| Python distribution 拆分 | 4.0 将包分为 core／studio／元包；在新环境完整安装匹配版本，不原地覆盖旧 monolithic 环境 | 无残留文件／版本冲突，`MjModel/MjData`、classic `Renderer` 和所需工具实际可用 |
| `mj_fullM` 签名 | 当前 `runtime/sessions/mujoco_dynamics.py` 使用 `(m,dst,d.qM)`；3.10 起变为 `(m,d,dst)`。在该 native model owner 修复；不在 Controller 或每步异常重试中兼容 | source-bound M、bias 的形状／单位／有限性；与该版本 native API 独立读回一致；模型求值无 physics step |
| 稀疏质量矩阵字段 | `qM` 向 CSR `M` 演进；检查所有直接读取、模型输出和缓存假设 | 不依赖过期内存布局，不把 source 坐标与 policy 通道矩阵混用 |
| native API／枚举／模型字段 | 清点实际使用的 `mj_step/mj_forward/mj_resetData/mj_jacSite/mj_rne/mju_*`、状态编码、actuator／tendon／equality 映射；逐调用对照中间版本变更 | 受影响实际 caller 通过；不要仅比较 3.8 与 4 的同名函数是否存在 |
| source／编译行为 | 检查重复 include、移除的 cable／composite、sidesite wrapping、free／ball RK4 等是否出现在冻结资产；不擅自修改资产规避差异 | 原始 source closure 不变；确需迁移时有显式转换和新身份；MJB 等缓存包含引擎版本，跨版本不复用 |
| 渲染 API | 4.0.1 仍导出 classic `mujoco.Renderer`，不能因新增 Studio 就删除旧 adapter；检查相机矩阵、分辨率、颜色通道与 EGL 生命周期 | 受影响 scalar RGB 短程＋重复 render 不步进＋正常 close |
| Warp 执行差异 | MJCF 可解析不等于 `put_model` 可运行；检查 integrator、mesh/contact、transmission、mimic/equality、sensor、contact／constraint 容量和 overflow | 两任务真实 source 转入 MJWarp，非零动作、接触和 reset 有效；不忽略 overflow、不更改碰撞形状来获得 PASS |

4.0.1 修复了 4.0.0 的稀疏 Cholesky 问题，建议直接选择修订版。迁移只复核本次受影响的 scalar 入口、模型、source、相机和关闭行为，不重新执行全部 G05 历史实验；若出现真实回归，按调用影响扩大验证。

上游依据：[MuJoCo 4.0.1 changelog](https://github.com/google-deepmind/mujoco/blob/4.0.1/doc/changelog.rst)、[4.0.1 C API](https://github.com/google-deepmind/mujoco/blob/4.0.1/include/mujoco/mujoco.h)、[3.8.1 C API](https://github.com/google-deepmind/mujoco/blob/3.8.1/include/mujoco/mujoco.h)、[4.0.1 Python exports](https://github.com/google-deepmind/mujoco/blob/4.0.1/python/mujoco/__init__.py)、[MJWarp v4.0.1 dependencies](https://github.com/google-deepmind/mujoco_warp/blob/v4.0.1/pyproject.toml)。

## 3. 公共场景、任务构造与路由

### 3.1 保留当前 owner，拆开两个时间尺度

```text
make_env / make_parallel_env（独立入口，显式 API 模式）
  → 同一 Task UID／配置规范化／Robot 与 Controller 规格
  → Task 场景声明／Assembly／SceneDefinition／source intent
  → 同一 source-bound TaskBuildRequest 与能力准入
  → scalar layout 或 homogeneous(B, CUDA) layout
  → 对应 provider materialization／native row mapping
  → RuntimeSession＋RobotRuntime／Controller 实例绑定
  → 同一 TaskDefinition 的 reset、评价和 observation 语义
```

共同的 SceneDefinition 表达资产、实体、frame、关节、articulation、受控资源和附件关系；它不携带 B 份 native handle、solver 对象或 renderer grid 坐标。B、env IDs、device、layout 与模板身份作为构建输入／绑定结果的批量信息。每个 provider lowerer 消费同一逻辑声明并返回具名映射，允许 MJCF／USD 等具体表示不同。

provider 路由负责 **物化、native 控制写入、状态／frame 读取、reset 和 completion**；TaskDefinition 中的 reward、success、termination、horizon 与 observation 意义保持共同。不得出现 `if provider == ...` 后为同一任务换一套成功公式或不同的公共 observation 字段。

| 阶段 | 允许执行的工作 | 不在此阶段执行的工作 |
| --- | --- | --- |
| 声明／结构构建 | 声明 Task 物体、Robot、source／Assembly、Controller requirement、相机挂载意图；分配共享拓扑和 native row；验证能力 | 推进 physics、采样每个 episode 初态、复制完整 Task 类 |
| episode 初始化／部分 reset | 按 env IDs 采样 pose／joint／velocity／已准入参数；写 native state，刷新 frame／contact cache；从 realized state reset Controller | 重载资产、改变拓扑、重建全部 B 或重置未选 slot |
| interval | 接受一次动作；按现有 cadence 计算控制；native substeps；发布完成边界；Task 计算和 required RGB | 重新解析 source、重复绑定 Controller、逐 env scalar step |
| 整批配置变更 | 结束旧 generation、释放自有 native 资源，按新 provider 重建整个 batch | 在同一 native batch 内更换某一行的后端 |

结构性随机化只能在 rebuild 时生效；episode 随机化只能修改 provider 声明可按 world 存储的字段。若某 native model 参数全世界共享，不能通过改共享 model 实现单行质量／摩擦随机化；该项要么在 build 冻结，要么补原生按 world 参数能力。

### 3.2 任务复用的具体落点

- 复用注册数据、普通配置、Scene／Robot 声明、Controller 规格、reset 分布参数及 TaskDefinition。并行 registry 可保留，但登记指向同一声明与 batch adapter 能力，不再维护第二份完整任务构造配方。
- Pendulum 先接通具名单关节 effort、既有 reset 和 reward；PickCube 再补 cube／Panda／gripper 状态的 device 访问与任务 tensor 计算。只在真实实现具备后解除各自 formal batch guard，`B=1` 不豁免。
- 标量／device 数值核可因 NumPy／Torch 不同而存在实现差异；阈值、单位、通道顺序、公式和 reset 设定只能有一份语义来源。先提取必要纯公式／参数再实现 tensor 运算，不引入覆盖全项目的 array backend 框架。
- device Task 通过公开 named batch state 计算，不创建 B 个 scalar CanonicalTaskStateView，不让每行 state 绕回 Python dict／NumPy。
- 首批新能力验收两个任务；双轮车和 Nut 保留现状。不得因为二者存在注册或旧 batch demo，就把四任务一起标为已支持。

## 4. 公共 device API、动作、观测与身份

### 4.1 基础抽象与入口

复用 `HomogeneousVectorTaskEnv`、`ParallelTaskSpecProtocol`、`TaskLifecycleAdapter/BatchTaskLifecycleAdapter`、`DeviceBatchRuntimeProtocol` 及 `DeviceBatchState/Transition/ResetSelection`。这些是既有 owner／合同，不新增 `ParallelTaskBase`、`ParallelRobotAgent`、`UnifiedEnvV2` 或第二套 Runtime 生命周期，也不为了名称一致强制继承 Gymnasium VectorEnv。

拟议入口（参数名仍属 D3 审批范围，实施后须写入现行 API）：

```python
env = make_parallel_env(
    uid=task_uid, env_config=config, num_env=3, backend="cuda",
    api="device",  # 执行解释器与必要传输由已解析的 provider profile 决定
)
obs, info = env.reset(seed=seed)
obs, reward, terminated, truncated, info = env.step(action_dict)
# provider／implementation 与 fixed renderer 由同一规范配置选择。
# 配置变更复用既有 reset 配置解析机制，整批重建，见第 9 节。
```

`api="device"` 是新模式；旧省略参数时的 SB3／remote NumPy 行为保留。如暴露 `execution`，其只描述依赖隔离和进程归属，不表示 B 个 CPU 仿真进程。单环境入口不自动返回带 B 轴的数据。B=1 device 仍是批量接口。

### 4.2 已确认 shape 与待确认的图像 dtype

| 数据 | 规范形状／语义 |
| --- | --- |
| action | Dict 树，每叶 CUDA Torch tensor `[B, *single_leaf_shape]`，首批连续动作 float32；每叶保留其原通道含义／单位与限制 |
| observation | 现有任务树，数值叶前置 B；任务规定的 float32 等 dtype 不随 provider 改变；本来是标量的叶为 `[B]` |
| RGB | 具名 `obs["cameras"][name]["rgb"]`，每 key 独立 `[B,H,W,3]`，推荐 CUDA uint8 RGB，dtype 待确认；同一 vector Env 内 key、尺寸、通道布局固定；不能用 observer 拼图替代 |
| reward／terminated／truncated | 分别为 CUDA float32 `[B]`、bool `[B]`、bool `[B]`；两个 done 标志保留原始值，重置选区使用 OR |
| reset mask | CUDA bool `[B]`；错误 shape／dtype／device 明确拒绝；全 false 为无作用，不能暗示全部 reset |
| info | 列式结构，数值／mask 可驻 CUDA；静态标签留 host。含 env ID、episode ID、generation、step／frame 边界；不每步构造 B 份重复的静态字典 |
| spaces | `single_*_space` 为无 B 规格；device 模式明确提供批量规格和 schema；不能把目前 `action_space` 的单例别名未经说明当作批量空间 |

默认 canonical action 是 **现有 source-bound 物理通道的批量形式**。Pendulum 对齐其现有 effort 限幅和 N·m 单位；Panda 的 direct effort 配方有 8 个输入、绑定到含成对手指的具名资源，不能假定 action、joint、actuator 都是同一组 9 维行。最终宽度／上下限来自已解析 Controller spec，6a 出具每叶通道表，不在通用模块硬编码 Panda 维度。

Dict key 使用稳定的语义名称，编译结果再映射到 source-bound Controller／resource ID。provider 切换可能改变内部绑定 hash，不能因此改变公共 action key。R3 reference action 与 direct effort 是不同规格；同一 vector 对象不在 A→B→A 中切换 Controller profile／action 维度。

首批 parallel 配置显式选择现有 canonical direct effort；PickCube 当前 scalar 默认 R3 不受影响。后续 R3 batch 是同一 Controller 规格的另一数值执行能力，不把 direct effort 输入悄悄解释成 pose target。

### 4.3 identity、时钟、buffer 与行绑定

- 稳定 `env_id` 对应 `[0,B)` 固定行；`episode_id[B]` 仅所选行递增；`generation` 在整批 native 重建时改变。每次 publication／command 带所需 generation、source／Scene、row binding 身份，不每行复制一份完整合同。
- 区分 native scene clock、每 env episode elapsed steps／time、control interval／substep、frame capture boundary。部分 reset 只归零选中行 episode clock，不能倒退整个 Isaac scene 的 native 时间。
- 位置、frame、速度约定沿用当前 canonical 合同，包括单位、四元数顺序与速度所属 frame；adapter 在边界转换。public task state 使用 env-local world；presentation grid offset 不进入 reward／Robot FK。
- JointEffort、BodyWrench、nested subject、Controller writer 都需要 `(env row, logical resource)` 映射。可做一组真实错误行／冲突注入，不能只有 schema 正例；不因此扩大首批到所有控制器物理能力。
- 普通 borrowed device state／RGB 的期限明确到下一次会改写相应存储的操作；终止观测使用独立保留存储。旧 typed view／command 的 generation 检查由边界 owner 承担；裸 Torch view 无法自动抛“已失效”，文档不能承诺这种行为。
- TaskDefinition 如需 `previous_state`，只为其声明所需字段保留上一步的 owned device 数据；不能把上次 native borrowed view 留到下一步后当作旧值，也不因此复制全量状态并产生第二 publication owner。

## 5. Warp／Torch 交互与原生 worker

### 5.1 进程归属

用户从 `/home/lly/miniconda3/envs/geochora` 运行统一入口。provider 配置解析到明确的依赖 profile；可共存的实现可同进程调用，必须隔离的 SDK 使用对应解释器启动一个管理整个 B 的 worker。不能通过拼接另一个虚拟环境的 site-packages 来混载 ABI，也不是 B 个 scalar worker。

Isaac 使用原专用解释器；MJWarp 先在隔离 profile 解析 4.0.1 组合；GeoPhys 按公开 API 和依赖共存结果决定归属。renderer 采用同一原则：能共存则在现有 owner 中运行，确需隔离才增加进程。版本和进程布局由 6a 实证确定，不能预先强制主环境换成 4.0.1 或叠加所有 SDK context。

构建、提交、读取仍通过既有 RuntimeSession adapter；native session 是唯一 physics owner。公共 Task／Controller 的语义与实现共享不等于其所有数值运算必须在 caller 进程：内层控制 cadence 尽量与 native 执行同处，避免每个 substep Python IPC 往返。用户每次 control interval 提交动作，按公开完成边界取得结果。公共导入／配置查询不启动 App；不复用旧 SB3 NumPy data-plane。

### 5.2 数据面与同步

1. 同进程优先 `wp.to_torch/from_torch` 或已公开的 device view，共享内存时记录 producer／consumer stream 和寿命；DLPack 只用于进程内，不能充当跨进程协议。
2. 跨解释器使用 Warp `array.ipc_handle/from_ipc_handle` 和可共享 Event。IPC buffer 由一个明确 owner 分配为可导出内存，禁用该分配的 mempool（按 Warp 限制）；不要依赖 Torch 私有 storage reducer 或两套 Torch ABI 相同。
3. action／typed control、public state／frame pose、必要 model 输出通过固定命名 device buffers；每次提交带 generation＋sequence，producer 完成 event → consumer wait → 执行 → completion event。若 native storage 不可直接导出，允许 GPU→GPU 打包／复制到公开 IPC buffer，须如实记录，不能说是零复制。
4. 正常 step 的动作、物理、状态、任务计算、图像不经 NumPy／CPU 全量往返。复用当前 DeviceResetSelection 时允许一次 B 个 bool 的 reset 控制面读回，以及小型时钟／错误／seed metadata；需要明确记录同步点。Recorder／导出图像的 CPU 复制属于显式证据路径。
5. 借用与关闭有配对确认：consumer 不再使用 → completion → 关闭 imported mapping → exporter 释放。超时／worker 崩溃时关闭整个失效 generation，不继续使用未完成帧／旧命令；不通过吞掉异常假装成功。

现有 Warp 1.18 安装源码已包含内存和 event IPC 的公开入口，但 **本项目两解释器、两套 native context 的互操作尚未执行验证**。6a 早期必须先验证 2 行已知 device 数据双向写读、event 顺序、worker close 和 generation 重建，再叠加仿真器。若 GPU／context 不支持 IPC，此推荐架构的技术门失败，需要维护者选择方案，不退回 host tensor 传输冒称 CUDA 通路。[Warp IPC 说明](https://nvidia.github.io/warp/v1.17/user_guide/runtime.html)、[Warp array 公共接口](https://nvidia.github.io/warp/stable/api_reference/_generated/warp.array.html)。

## 6. 默认控制、batch Robot 与 R3／重力补偿

### 6.1 先交付 canonical action 的最短真实链

复用现有 Controller 规格、LinearEffort／physical command、resource binding 和 cadence。扩展 tensor 执行所需的最小方法，按 B 维一次产生贡献；provider 绑定 joint／actuator／tendon／body 映射，再由 native adapter 提交。不新增为了演示而绕过 Controller 的 torque writer。

首批关闭可选重力补偿；zero effort 保持原有物理含义。每个 interval 只消费一次 RequestedAction，增量动作不能在每个 substep 被重复累计；Controller cadence 和 finger servo 的现有 inner cadence 分开。相同资源只有合法的单 writer 或显式 contribution composition，wrench 更新替换本 owner 的贡献，不跨步无意累加。

### 6.2 batch Robot 信息的复用

实际 owner 是 `RobotComponent/AgentComponent`、`RobotRuntime`、`ControlledSubjectV1`，当前没有需要照名字新建的 `RobotAgent` 类。共享 Robot declaration／asset recipe；每个 live scalar／batch env 分别绑定 Runtime／Controller 实例，不共享已 bind 的 cached default controller。

在既有 RobotRuntime／state/model 合同上提供具名批量访问：joint position／velocity `[B,J]`，root／EE／hand frames `[B,...]`，必要 Jacobian `[B,6,J]`、模型输出 `[B,J,J]` 或 `[B,J]`。只声明当前 Controller 实际要求的数据；Pendulum 不伪造 gripper／EE，direct effort 不强制读 Jacobian／质量矩阵。

映射至少包含 joint 名称、单位、速度／Jacobian frame、手指传动、source identity、generation、B 行来源。static mapping 可共享，动态值从唯一 publication 读取；不在 RobotRuntime 中创建第二份可独立更新的 q／qd 状态。

### 6.3 R3 和重力补偿是两项独立能力

1. 先复用 `production_r3.py`、`r3_effort.py` 的配置／规格／限幅／cadence，将已有 DLS/FK/Jacobian、reference update、servo 数值实现接到 tensor；保留 R3 reference 与 effort 输出的既有意义。每 env 的参考目标、上次动作、积分／滤波／phase 状态有 B 轴，mask reset 只清选中行。
2. pure 数值核可在合法 realized state 上对照当前 scalar R3，比较动作和模型输出，不逐行调用 scalar Controller 作为生产实现。随后在同一 native batch 中验证不同目标、不同 reset 时序，实际控制只提交一次。
3. gravity flag 默认仍为 off。打开前必须满足现有 source-bound ControllerModelRequirement：确切 source、具名通道、单位、求值边界、cadence、无 physics step。provider 提供公开模型能力；若用 Core 纯模型，必须验证其来自实际 source 和当前 q，不用名义 Panda 常量冒充任意资产。
4. gravity-only 与包含 Coriolis 等项的完整 bias 必须区分；不能直接将 `qfrc_bias` 全部命名为重力。已有 MuJoCo position-drive 补偿通过参考偏置实现，仅对原受限 profile 成立，不能直接复制到 batch direct effort。
5. R3＋重力通过显式贡献组合，明确每项来源和相加位置；禁止重复 feedforward，禁止用关闭实体 gravity 冒充补偿。某 provider 不提供所需模型时在 native 副作用前拒绝该 flag，不影响已经准入的 direct effort。

两个连续工作包分别验收：包一为三后端×两任务的 canonical action、batch Robot 与公共并行生命周期；包二为现有 R3 的 tensor 执行、所需模型和显式重力补偿。包二具体覆盖哪些 provider、是否必须完成才能接收 G06 总阶段，尚待维护者确认，不再把之前推荐的两后端硬门当作已经批准。R3 与重力分别举证；不给没有对应控制需求的 Pendulum 伪造 R3。

## 7. same-step autoreset、随机流与记录

### 7.1 一次 step 的顺序

新 device 模式由现有 `HomogeneousVectorTaskEnv` 统一协调 autoreset，BatchTaskLifecycleAdapter 继续提供任务评价、观测、reset primitive；provider 不自行 reset，Controller 不自行开启 episode。旧 raw NumPy／SB3 owner 模式保持并显式适配，避免两次 reset。

```text
动作 t → 完成声明的 native substeps → publish pre-reset boundary
  → 用该边界计算 reward / terminated / truncated / final obs
  → 完成 required final RGB，保存 done 行的终止观测和身份
  → mask reset(done)，按 realized reset state 初始化 Controller
  → 完成 reset 行的新 episode obs 与首帧
  → 返回：done 行为新首帧；其余行为本次 step obs；reward/done 属旧 transition
```

不得在 reset 后再从已经覆盖的 GPU buffer “补取” final image。必需相机失败则本次 transition 未完成，Env 进入明确 fault，保留实际已完成的 physics boundary；不能回报半份成功，也不能重复执行已完成 interval 来补图。

### 7.2 终止数据的具体形式

拟采用固定 B 轴的 `info["final_observation"]`，树结构与 obs 相同，另有 bool `[B]` 的 `info["_final_observation"]` 有效 mask。无效行内容不用于学习；不逐步分配 B 份 terminal Python 对象。可预分配独立 final buffer，按 mask 复制；其借用期限至少覆盖当前返回值消费，下一次 step／reset 前可由调用者显式 clone 取得 owned 数据。

`final_info` 保存旧 episode／step／frame boundary，`reset_info` 保存新 episode／首帧身份；新旧 episode ID 不同，env ID 相同。完整终止观测包括该 Env 配置承诺的所有 RGB，而不只是 state；未配置的 camera 不凭空添加。终止指标／reward terms 取 pre-reset 评价。

同一行同时 terminated、truncated 时保留两个 true；只 reset 一次。每次 step 的 reward 和 done 关联旧 transition，returned obs 的 done 行属于新 episode；bootstrap 使用 `final_observation`，不能拿 reset obs 代替。SB3 adapter 如接入该新模式，只翻译 final keys／输出并做必要 host copy，不能沿用其当前再次调用 `reset(mask)` 的逻辑；也可暂时明确拒绝 device 模式，旧 host caller 继续原行为。

### 7.3 reset RNG、隔离与 Recorder

- Core sampler 使用每 env 独立流，依据稳定 seed、env ID、episode 序号和命名采样域派生；只推进选中行。不同调用顺序、不相关行是否 done，不改变未选行未来样本。provider seed 独立派生，不能声称各引擎轨迹逐位相同。
- 延续既有 reset 分布和参数；若采样先在 CPU 小控制面实现，必须标明且只产生所选行初态，不把整个 batch GPU state 读回；后续 tensor sampler 不得改变已冻结分布的意义。
- 显式 mask reset 对未选行不重新采样噪声／curriculum，不刷新 Controller 历史，不清外力贡献；观察已完成 step 的当前状态，不能拿 step 前状态作“不变”比较基线。
- Recorder 通过公开 transition／frame 接口记录 env ID、旧／新 episode、generation、clock、终止／首帧类别。普通 GPU borrowed 数据在异步落盘前由 Recorder 取得 owned 副本；不复用已覆盖视图。
- 独立 offline reader 至少读回一个普通步、终止帧和新首帧，核对状态／图像身份与同次 caller 的实际数据。只写出 H5 文件不证明行关联或 task success。

## 8. 固定 renderer、网格大场景与相机

### 8.1 推荐的固定 renderer 与前置技术门

推荐先验证现有 GeoPhys RayTracer 作为共同 renderer，MJWarp renderer-only 为备选，不同时开发两套。此选择待维护者确认；既有批量几何能力不等于新任务相机合同已经接通。

| 当前适配 | 已有源码能力／路径 | 与本轮要求的缺口 |
| --- | --- | --- |
| GeoPhys RayTracer | 通用场景 backend；共享资产／GPU 几何实例／批量 device world-major 变换 | 公开 CUDA RGB 输出、base／hand 多相机、跨物理 provider 输入及生命周期仍需验证；尚不是现有正式 task RGB 路线 |
| GeoPhys Rasterizer | 通用并行场景 backend；亦有有界 GeoPhys CPU task-camera 路线 | registry 不声明共享资产／GPU 实例和批量变换更新能力；共享 framebuffer 路线不等于已支持 CUDA 多相机观测 |
| Flora | 已有并行场景共享资产表和多实例 | 当前显式 host transform readback 和 host RGBA8 输出，不满足默认设备图像链 |
| MuJoCo OpenGL／reference | MuJoCo CPU 与 GeoPhys CPU 的有界同步 task RGB；通用 reference 路线不声明 parallel | 现有 host pose／owned CPU 图像不能直接满足本轮要求 |
| Isaac RTX | Isaac CUDA 同步 task RGB，已有 frame mount | 跨后端独立 renderer、统一视觉物化与本机共存开销待验；当前公开 task RGB 仍是 CPU copy |
| MJWarp renderer | 上游候选接口；Geochora 尚无该 adapter | 需要新增适配与完整资产／相机／生命周期验证，作为 RayTracer 不适用时的备选 |

上述两类适配分别以 `render/base/backend.py` 的场景 registry 和 `render/base/contracts.py` 的 task-camera 合同为准，不能混成已接通矩阵。RayTracer 优先理由是已有批量设备几何链和资产实例复用；其 `geophys_framebuffer` 声明不证明终端 CUDA Torch RGB 已实现。先在既有 `render/raytracer`、camera／frame owner 补最小公开能力；如果需要读私有 framebuffer 或 solver，必须扩展公开接口，不能用私有补洞。

复用 `ParallelRenderLayout` 的网格变换。当前 `ParallelRenderProvider` 的 NumPy 展示帧不能冒充 device task image；设备 frame／completion 在既有 contracts 扩展，observer 显示单独显式读回。若首选不成立，记录具体缺口后再确认备选及条件性新增文件，不默默切换 renderer。

6a 内先做 R0 门，必须在大规模 batch 适配前回答：

| R0 子项 | 明确证明的内容 |
| --- | --- |
| R0.1 visual materialization | 相同 SceneDefinition 的 Pendulum／PickCube geometry、mesh、颜色／材质与 canonical visual map 能构造 renderer-only 模型；USD 来源不能假装 MJCF，所需 source 转换有明确 owner |
| R0.2 三后端状态同步 | 同一实现接收 Isaac、MJWarp、GeoPhys 的公开 pose，完成初帧、非零动作后的新帧；不读 provider 私有 solver、不调用额外 physics step |
| R0.3 相机与网格 | observer、每 env base、PickCube 每 env hand 挂载正确；稳定 camera ID／env row；末端移动引起相机外参同步变化，RGB 来自同一已完成边界 |
| R0.4 设备／进程 | 真实 IPC fence、GPU buffer、打包布局可用；重复 render 的显式 physics step 增量为 0；旧帧不能混入 reset／新 generation |
| R0.5 A/B 资源兼容 | 关闭 A 的 physics 资源后 renderer 可以绑定 B，并按同一相机与输出 schema 重建自有绑定；不需要换 renderer 实现或偷偷启动第二 physics owner |
| R0.6 显存共存 | 本机 RTX 5060 总显存约 8 GiB；主环境入口／选定 renderer 与当前 physics provider 同时存在时，B=3 的真实两任务场景在批准预算内可创建、步进、关闭，不用单独运行两者的峰值相加推测 |

R0 未通过不能冻结为已接通共同 renderer。CPU 图像路径只可用于定位或原 scalar 回归，不能替代已确认的 CUDA 主要数据链。

physics worker 采用 headless／physics 所需的最小 SDK 配置，不启动本次未用的 RTX 相机或 observer；固定 renderer 承担图像。是否能关闭相关扩展必须按 Isaac 6.2 的实际依赖验证，不能删掉必需 USD／PhysX／Fabric 功能省显存。若 8 GiB 不能容纳，先精简重复视觉／缓存分配；仍不足时报告缺口并调整 renderer／进程架构，在本机重新验证；更大 GPU 不作为本轮出口，不降级 CPU physics，不把 B=1 作为本轮验收。

### 8.2 网格场景的坐标与隔离

构建一次 logical env template，每 env 的 render root 使用固定网格平移 `T_grid[i]`。列数建议 `ceil(sqrt(B))`；spacing 根据该任务冻结 workspace、运动包络和相机 near／far／FOV 明确计算／设置，6a 记录最终值，不写一个对所有任务通用的任意常数。

共同 renderer 可物化为 **一个 render world 中 B 组 visual 实例**；observer 可看全场景或配置的 K 个展示实例，每 env task cameras 对应自己的实例。MJWarp physics 的 B 个 native worlds 仍是独立 world；Isaac physics 可在一个 stage 复制 env namespaces 并使用 collision filtering。两者都向 public state 发布无 grid offset 的 env-local pose。

`T_visual_world = T_grid[i] @ T_env_local`；若 Isaac native 场景已经包含自身 env origin，adapter 先还原 env-local，再由 renderer 应用 presentation grid，不能叠加两次。固定附件和 hand camera 的 mount 链按同样原则处理。

网格距离不能代替物理接触隔离：Isaac 验证 collision filtering／共享地面归属；MJWarp 验证 world-local 状态与接触。也不能仅靠间距声称相机看不到邻居：优先使用 renderer 公开可见性能力；若没有逐相机隔离功能，应为冻结运动包络证明 FOV／far／spacing 不包含邻居，必要时调整 renderer scene 组织并回报 D4，不伪造图像裁剪隔离。

### 8.3 observer、base、hand 的配置

| 相机 | 绑定和输出 | 验证 |
| --- | --- | --- |
| observer | 共同 renderer 的 world camera，显示整个 grid；不是 Agent observation | 能辨认 B 个实例及运动；不混入 task image key |
| base | 任务声明明确使用 env-world 固定 frame 或 Robot base frame，两者不可混称；每 env 同一 intrinsics／mount transform | 公共 frame 投影与图像地标一致；若 Robot root 可移动，挂载按声明更新 |
| hand | PickCube 绑定现有 canonical hand／EE frame，加一次已声明外参；每 env 独立 camera | 不使用零 pose／另一行手爪；运动前后外参和可见物变化与实际状态对应 |

相机职责分工：Robot 声明公开安装 frame 和可选预设；任务／配置选择启用的相机、内外参、输出 key 与是否进入 obs；公共 camera owner 管绑定和生命周期，不在 Robot 构造时直接创建 SDK 相机。传感器挂载不改变机器人动力学。

三种执行模式必须独立成立：

- 无观测相机且无 observer：保留状态 obs；不分配图像、视觉快照、render scene／BVH 或 RGB fence，不走 render。同一 SDK 必需的 physics App／场景基础开销另计。
- 仅 observer：按配置频率展示，不加入 Agent obs；可仅物化 K 个选中环境，不要求为全部 B 创建 task-camera 图像。
- 观测相机：追加具名 cameras 树；同一配置用于 scalar 与 batch，后者只多 B 轴。首批建议每 control step 同步采图，autoreset 在重置前保留终止图，重置后取得首帧；后续降采样需显式帧时钟合同，不能悄悄重复旧帧。

当前旧 `task_rgb` 为单相机 HWC float32、0～1、CPU owned copy；保持旧接口兼容。新具名相机接口推荐 CUDA uint8，scalar／batch 一致，但 dtype 尚待确认，不能称为既有合同。

首批建议 task RGB 每 camera `128×128` RGB、observer `640×480`；如现有 task 配置有已固定规格，以审批后的配置为准并写入 schema。Pendulum 配 base，PickCube 配 base＋hand；不为 Pendulum 伪造 hand。相机不同任务可有不同 key，但同一对象 A→B→A 中 key／shape 保持不变。

当前 task RGB owner 主要协调单 CameraSpec，MuJoCo／GeoPhys 的移动 mount 还存在拒绝；应在 `render/camera` 同一 owner 中扩展多 camera／frame mount，然后由 renderer 消费公开 frame。不能只因为 Isaac scalar hand camera 受测，就宣布跨后端 batch mount 已完成。

## 9. 部分 reset 与整批 A→B→A

### 9.1 部分 reset 事务

1. 完成当前 interval／必要 RGB；冻结 pre-reset boundary 和选区。构建一次 DeviceResetSelection，不多层重复 GPU→host mask 转换。
2. 验证同配置、合法 mask／source／generation；采样选中行，写 selected native root／joint／velocity／参数，清该行 contact／warmstart／pending contributions 等 provider 必要状态。
3. 重新取得选中行 realized state；reset 其 Controller、episode clock／RNG 与 camera；只发布该行新首帧。
4. 未选行 native state、时间、Controller memory、RNG、pending contribution 及图像身份不变。共享 borrowed allocation 可按合同整体失效，但这不是未选行数据可以改变的理由。
5. 如果 native reset 发生部分副作用后失败，保留边界并 fault 当前对象，不宣称原子回滚；不得顺手把全 batch reset 以“恢复”。

### 9.2 同一 public vector 对象上的整批切换

沿用既有配置解析／reset 机制增加 batch rebuild 分派，不增加第二个 `switch_backend_manager`。存在配置变更时必须整批；同时传 partial mask 为错误。新 provider 配置能在构建前验证的部分先验证，再进入不可逆的旧 generation teardown。

首批切换仅接受已冻结的 provider／implementation 变更，B、Task UID、Robot／Controller 规格、camera key／尺寸和公共 action／obs schema 保持一致；这些维度变化需要新建 vector Env，不塞进本轮 A/B/A。整批重建使全部 env 的 episode ID 继续递增；Core sampler 流不因换 native worker 自动回到初始 seed，只有公开 seed 参数可显式重播。

```text
READY(A,g0)
  → 预检 B 与固定 renderer／action／obs／source 合同
  → 完成 outstanding physics／render／record borrows
  → retire(g0)，清 Controller／commands／camera／IPC binding
  → close A native worker 与自有资源
  → 构建 B 整批；绑定同一 renderer 实现；reset 全部；发布 g1
  → READY(B,g1)
  → 同流程回 A，发布 g2
```

renderer 实现／选择在创建时固定到 close；允许其为新 source／generation 释放重建自有 GPU scene／camera binding，不能偷换 renderer。建议保留 caller 侧 renderer owner 以降低生命周期复杂度，但不能为了对象指针不变而保留已失效资源。

选择失败且尚无副作用时维持旧 ready 状态；旧 generation 已退休后新构建失败则 fault／可关闭，不假装仍可继续 A。切换后旧 source-bound command、typed view、frame receipt、Controller model binding 必须被拒绝；老 borrowed buffer 按合同失效。close 支持重复调用，所有自有 mapping／worker／App／锁有明确清理结果，不以 `close()` 返回代替 receipt 可读与进程退出证明。

## 10. 代码落位审批表与禁止的重复 owner

表内路径均相对仓库根。现有文件优先原位扩展；“新增”是功能职责上确有缺口，不要求为了凑目录创建空模块。实施前以 CodeGraph＋当前磁盘确认 owner；需要偏离的地方记录旧／新落位、真实 caller 和理由，交维护者调整。

| 职责 | 现有落位／拟新增落位 | 改动方式和边界 |
| --- | --- | --- |
| 配置／入口／注册 | `task_env/registry.py`、`environment/configuration.py`、`vectorization/parallel.py`、`vectorization/registry.py` | EXTEND／COMPOSE；共享 Task registration payload，显式 device 模式；不在 Task 增加完整 parallel constructor |
| 共同构建与 layout | `environment/reference_binding.py`、`vectorization/factory.py`、`vectorization/contracts.py` | EXTEND；batch layout／binding 为小型值合同；复用 TaskBuildRequest，不新建万能 builder |
| 生命周期／autoreset | `vectorization/homogeneous.py`、`vectorization/task_definition.py` | EXTEND；Env 协调 same-step，adapter 负责共同任务计算／reset primitive；只保留一个 autoreset owner |
| device publication／row identity | `runtime/contracts.py`、`artifacts/state.py`、现有 physical command contracts | EXTEND；把缺少的 batch identity 加到既有 typed boundary，不复制一套全量 scalar state objects |
| native dispatcher／session | `runtime/factory.py`、`runtime/sessions/api.py` 及当前 selected materialization owner | EXTEND；薄 layout／provider 路由；不把 IPC、相机配置、Task reward 堆进 api.py |
| Isaac batch adapter | 新增 `runtime/providers/isaac/batch.py` | NEW native layout 实现，组合现有 Isaac session／I/O／source owner；只管 clone、tensor row、控制／状态／masked reset，不复制 scalar Env |
| MJWarp batch adapter | 新增 `runtime/providers/mujoco_warp/batch.py` | NEW native API 实现；shared model＋nworld data、控制／状态／reset／fence；source lowering、模型接口仍复用 MuJoCo owner，必要纯映射同包再拆 `mapping.py`，不预建空层 |
| GeoPhys adapter | `runtime/providers/geophys/rigid_batch.py` | EXTEND；改用公开 device port，选入 factory；当前 constructor 读取 `solver.storage` 的路径不能成为新 device 方案，修复受影响绑定，不扩大成全库私有字段清理 |
| GeoPhys 上游端口／能力 | GeoPhys 既有 materialization、`solvers/rigid/batch`／loaded component owner | COMPOSE 优先；不足时 EXTEND public control／state／mask／completion。禁止把 static physics kernels 搬回 Geochora；pin 改动单独确认 |
| worker／GPU IPC | 新增 `runtime/transport/worker.py`、`runtime/transport/cuda_ipc.py` | NEW 缺失 transport 实现；worker 管解释器／消息／close，cuda_ipc 管 device buffer／event／borrow；尽量复用现有进程协议，不再复制一套 Env 生命周期 |
| 公共网格／camera | `render/providers/parallel.py`、`render/providers/parallel_source.py`、`render/camera/api.py`、`render/camera/task_rgb.py`、既有 `render/contracts.py`／`render/base/contracts.py` | EXTEND；复用 ParallelRenderLayout，新增明确的 optional device frame 能力，旧 host 展示协议保留；multi-camera、mount／boundary 在 renderer owner；provider 内没有 Task camera 特判 |
| 固定 renderer | 首选原位扩展 `task_env/render/raytracer/` 与公共 camera／contracts；仅选中 MJWarp 备选时新增 `task_env/render/mujoco_warp/backend.py`、`scene.py` | EXTEND 优先；缺失的 native render API 才 NEW；context／完成／RGB 与视觉 geometry mapping 分工，挂载数学复用 camera owner |
| batch Robot | `robots/runtime.py`、`environment/protocols.py`、现有 ControlledSubjectV1 | EXTEND；声明／静态映射共享，动态 device view、model capability 按需求供给；不创建 B 个 RobotComponent／Controller |
| canonical／R3 tensor 实现 | 原 `controllers/canonical/physical_controller.py`、`r3_effort.py`、`production_r3.py` 等保留规格与入口；必要时新增 `controllers/canonical/tensor/effort.py`、`tensor/r3.py` | EXTEND＋NEW 数值实现；只放 device 算术与 B 轴 memory；不复制整个 Controller framework，重力模型留既有 model owner |
| Task 数值实现 | 现有 Pendulum／PickCube 的 TaskDefinition owner | EXTEND；阈值／分布参数一份，纯 tensor hook 就近放；不得在 tasks 根堆 provider/render/worker 文件 |
| profiles／版本锁 | 新增 `task_env/dependencies/README.md`、`mujoco-warp.in`／精确 `.lock`、`isaac-6.2.lock`；GeoPhys 锁仅在相应包批准后添加 | 版本／安装说明一个 owner；lock 标注适用平台和解释器，不伪造跨平台通用 freeze，不把本机所有无关包纳入产品依赖 |
| 有界诊断／offline reader | 新增 `task_env/diagnostics/tasks/v2.1.1/g06/`，按 `contracts.py`、`native.py`、`readback.py`、`run.py` 职责组织 | diagnostics 外部调用公开 API；可按实际需要合并，禁止每个实验新造生产 probe 参数或每运行一轮复制 runner |
| 用户示例 | 现有 examples 的并行入口 owner；拟按功能建 `examples/parallel/`，一个 caller＋两个任务配置 | 一个普通用户调用链；不把验收 runner 当唯一生产 caller，不替用户手写 source hash／receipt／IPC handle |
| 文档／能力 | 当前 `v2.1.1/api`、contracts、capabilities、maintenance | 只更新已实现且有证据的交集；本方案未批准／未实施时不标 PASS，不提前将新目录写入 Skill 为现有能力 |

落位表不是大型重构授权。`reference_env.py` 本次仅做共同构建所需的薄交接；不为 batch 复制其数千行，也不借 G06 顺便大搬家。若某段纯逻辑必须共享，抽出最小连续职责并迁移实际 caller；不通过跨模块调用大量 `_private` 方法假装复用。

### 10.1 与 G05 总账逐类对齐

| 总账原则 | G06 具体约束／审查证据 |
| --- | --- |
| ENTRY-01/02/03 | 一份规范配置和构建请求；入口不猜反射标志切换生命周期；相机普通声明在构建后绑定 Artifact，不要求 caller 制造 hash |
| TASK-01～04 | 不复制 ParallelPickCube／ParallelPendulum；Task 保留语义和实体声明，provider 物化归 owner；简单主体复用具名 Robot 引用 |
| ENV-01～05 | 构建、reset、interval、fault、close 相位清楚；只有一套事务协调、一个 physics owner；列资源创建者／borrower／关闭者 |
| SUBJ-01～03 | 简单主体不伪造能力；Robot 不启动 SDK；root mode 与 action mode 独立 |
| CTRL-01～05 | action／joint／actuator 三命名域；SI effort／wrench 语义、单次提交、R3 cadence、source-bound 重力显式准入 |
| SRC／RUN | Scene／source 统一交接与 native lowering 分离；无 provider-private 状态补洞，不恢复 static／candidate 退休链 |
| REN／OBS | renderer 固定、observer／task 分离、frame／image 完成身份；没有第二状态发布 owner，重复采图不推进物理 |
| REC／CALL | 正常调用链产生 Evidence；Recorder 列式身份／owned 数据／offline reader；示例不是诊断特权入口 |
| TEST-01～04／DOC | SDK guard 纯入口、相关最小测试；实验输出留 ignored workspace；生产无 probe／实验名分支；当前能力与提案、历史分别陈述 |

每个实施包结束给出新增／修改生产文件、诊断文件、文档、净行数和新增抽象／owner／caller 表，解释增长原因。行数用于发现重复，不设置“文件越少越好”的虚假验收门；不新增逐步日志、全状态 hash、重复 shape 检查或无调用者的泛用工具。合法准入、数据边界和 fault 校验必须保留。

## 11. 分阶段执行包与依赖

复用一个 Geochora 阶段分支、零新增 worktree、一个生产 writer。若 GeoPhys 确需上游 API 扩展，D1／D5 批准后才在 GeoPhys 另设一个阶段分支／独立输出 commit，再显式更新 Core pin；不要修改保存历史调研的 `env_task_design` 分支来代替正式上游包。该条件下预计总量为两个仓库各一个阶段分支，不为每个 provider／attempt 新开分支。

以下为完整执行窗口，不是每行都开 branch／thread。每个窗口包含实现、必要修复、相关验证、文档和本地 commit；attempt 1 主攻实现，attempt 2 主攻复核与有界修复，每子阶段最多 3 attempts；第 3 次前按仓库流程重评 blocker。单个 native run 失败不等于整个 attempt 结束。每次真正 dispatch 前，根据已解除的技术未知冻结预计时长和 attempt timebox；不把下述 per-run 15 分钟上限当成整个实现窗口预算。

| 窗口 | 内容与顺序 | 出口／转交条件 |
| --- | --- | --- |
| 6a attempt 1 | 读取审批 D1～D6；精确版本解析／MuJoCo 兼容修复；layout／身份／公共 device shape；共同 build 真实 caller；IPC 与 R0 renderer 前置验证；Pendulum 最短 batch 链 | 实际构建进入共同 owner；版本／ABI 缺口可定位；至少两条代表路线能与固定 renderer 同步短程，或明确未过 R0、不得进入依赖它的 6b 大改 |
| 6a attempt 2 | 审核真实 diff；补行绑定／错误输入／终止保留／资源故障的关键合同；冻结经过验证的版本、source、相机、预算与能力表 | 6a 合同和必需实现成立；不只交 schema／fake；更新 API 的已实现部分；形成 6b 唯一 ready 包 |
| 6b attempt 1 | 三后端六格 canonical effort 小批量；PickCube device Task 计算；batch Robot；GeoPhys BRS 缺失公开能力在对应上游 owner 补齐 | 三后端两任务真实构建／reset／非零 step／RGB／obs；三条均验证 native batch；隔离与物理含义成立 |
| 6b attempt 2 | 复核状态与相机、控制 cadence／传动、同次记录读回；修复实际问题；确认 GeoPhys／R3／gravity 具体交集 | 先完成六格 direct effort 与 batch Robot；随后开展独立 R3／model／gravity 包，范围和总出口待确认；不跨出实际受测模型声明 |
| 6c attempt 1 | 全 false／单行／多行 mask；staggered episode autoreset；同一个 public vector 对象 Pendulum A→B→A，再做 PickCube A→B→A；旧 generation／异常重建／close | 固定 renderer 与 schema；不重置未选行；旧资源／命令失效；退出与 worker／IPC／App 释放证据 |
| 6c attempt 2 | 独立 readback、重复 close／失败清理与最终合同审查；对照本方案和总账收口；更新当前能力与维护交接 | G06abc 按批准范围有界接收；未完成矩阵显式列出；随后另议 Env／Robot 精简，G07 集成门保持原范围 |

6a 的 R0 可以使用最小 native source 和数步执行定位兼容性；6b 必须使用真实冻结 Task source 和非零动作。不能把 6a 原型换名当作六格正式验收，也不把 G07 完整 Solution／三 seed 矩阵前移。

## 12. 验收矩阵、物理 oracle 与运行预算

### 12.1 必达矩阵

| Task × provider | B／动作 | 相机 | 6b 真实链 | 6c mask／A→B→A |
| --- | --- | --- | --- | --- |
| Pendulum × Isaac 6.2 CUDA | B=3，原 canonical effort；三行不同非零动作 | base＋observer | 必达 | 必达，A=Isaac，B=MJWarp |
| Pendulum × MJWarp 4.0.1 CUDA | 同一公共 schema／timebase／分布 | 同上，固定 renderer | 必达 | 同一对象回到 A |
| PickCube × Isaac 6.2 CUDA | B=3，显式 canonical direct effort；后续 R3／gravity 包另验 | base＋hand＋observer | 必达，控制规格分别验证 | 必达，另一个 PickCube 对象做同样 A/B/A |
| PickCube × MJWarp 4.0.1 CUDA | 同一 source 语义／具名映射；后续 R3／gravity 包另验 | 同上，固定 renderer | 必达，控制规格分别验证 | 同上 |
| Pendulum × GeoPhys BRS CUDA | B=3，须 public device ports 真实接通 | base，使用共同 renderer | 必达，不以 host-only BRS 代替 | mask／autoreset 必达；A/B/A 先以 Isaac↔MJWarp 代表组合 |
| PickCube × GeoPhys BRS CUDA | B=3，原资产 mesh／contact／transmission 必须接通 | base＋hand，使用共同 renderer | 必达；缺失通用能力在上游补齐，不换简化资产冒名 | mask／autoreset 必达；共同 renderer 必达 |

### 12.2 一组足够证明问题的用例

| 用例 | 输入／观测 | 判断依据 |
| --- | --- | --- |
| 动作行与状态行 | 同初态，行 0 正 effort、行 1 零、行 2 负 effort；必要时分开重置重放 | 按关节轴／重力模型检查初始加速度和响应方向；零 effort 允许自由运动，不能当 hold oracle；行映射不能错位 |
| native batch 证明 | native layout／world_count、单批提交与一次场景推进、真实进程归属 | 不以 device 字符串、worker 数或一次 Python 方法调用替代原生批量实现证据 |
| Pendulum 物理 | actual q／qd、joint frame、显式 dt／substep、已知 effort | 限幅和单位符合原任务；kinematics 对齐；相同 backend 受控反事实可判断动作作用；不要求三家轨迹逐位相同 |
| PickCube 物理 | Panda／finger／cube／table 的公开状态、effort／contact、base／hand 图像 | joint／actuator／tendon 传动正确，cube 受重力／接触，不能穿桌或悬空假运动；R3 小幅目标运动与实际末端一致。G06 物理有效与完整抓取成功分列 |
| 相机真同步 | 公开 frame 和冻结 intrinsics 预测可见地标；同次 RGB、frame ID、physics boundary | 相机／物体运动与投影一致；非零 step 带来对应变化；不用“任意像素变了”证明正确；重复 render 显式子步增量 0 |
| 环境物理隔离 | 固定初态／seed，改变一行 action 或 reset，其余行做同 backend 对照 | native contact／constraint 无跨 env 耦合；未选行数据不改变。warmstart／浮点容差提前按同 provider 精度冻结，不能见结果后放宽 |
| 同步终止与自动 reset | 短 horizon 测试配置，先错开一行 reset，再走到真实 horizon；另做 TaskDefinition 级自然 terminated 合同用例 | 最终 obs／全部配置图像先保存，done 原值和奖励保留，returned done 行新 episode，未 done 行仍是本步；不改 Task 成功阈值制造 native PASS |
| RNG 隔离 | A 运行重置行 0 多次，B 对照不重置行 0，再 reset 行 1 | 行 1 的 Core sampler 流／后续样本一致；仅 seed 值相同但 RNG 历史已变不能算通过 |
| mask 不变性 | 显式 step 完成后快照 S，mask reset，再比未选行 | state／episode clock／Controller memory／RNG／pending contribution／image identity 对应 S；不是对应上一个 step 之前 |
| A/B/A 与失效 | 保留旧 typed view／command／frame receipt，切换并再提交旧对象 | generation／source 错配拒绝；新动作／obs／image schema 不变；同一个 public Env 对象，旧 native batch 整批关闭 |
| 清理与读回 | 正常结束、一个构建或 worker 失败、重复 close；独立读取同次文件 | 资源 owner 与清理结果相符；没有孤儿 worker／有效旧 IPC mapping／错误释放共享 App；H5 能区分终止帧和新首帧 |

行绑定、borrow／generation、nested subject、effort／BodyWrench 的关键错误用例可用受控 fake／scoped injection；它们证明合同拒绝，不扩大 native qualification。原生物理 oracle 使用公开边界与外部计算，不让生产代码为验收额外暴露私有 solver。

### 12.3 预算与证据最小集合

建议批准以下上限作为首轮默认，实施 agent 在实际资源预检后写入单次执行包；它们不是性能目标，也不允许忽略已有 Harness 更严格的限制：

- 单卡，功能验收 B=3；IPC/R0 可以 B=2。容量测试另按预算逐级增加 B，不能把 B=3 当作性能上限。只启用当前 provider；renderer 仅在需要图像时启动，避免重复 App／context。已有 shared native lock／Harness 监督照用，不 unlink 锁绕过占用。
- 每个 native run 显式列 seed、physics dt、control substeps、policy intervals 和 maximum explicit physics steps；沿用任务 timebase，不调 dt／solver／horizon 追求 PASS。建议 Pendulum seed73、PickCube seed31 作为单 seed 起点；特殊终止用例单列 Experiment horizon，不修改正式默认值。
- 初轮短程 20 intervals／run；根据物理／接触不确定性扩到最多 200 intervals 或 10,000 显式 substeps，先达到者停止；编译／启动与 steady execution 分开记录。完整 Solution 超出这一短程窗时不擅自扩大。
- 每 run 默认 wall-clock 15 分钟（含 SDK／kernel 首次启动，超时由 Harness 收尾）；窗口内可修复后重新运行，但每次新 run 留边界。本次只读硬件查询为 RTX 5060、总显存 8151 MiB、物理 RAM 15792 MiB；建议 G06 整组 caller＋worker 的 VRAM 上限 6144 MiB、RAM 上限 12288 MiB，给桌面与其他工作留余量。运行前必须按实时空闲与既有 Harness 取更严格上限；不能把这份静态查询当作已取得资源独占。无法容纳则回报具体资源缺口，不能未经批准减成 B=1。
- 每 run 证据默认 ≤256 MiB：只保存能支持结论的初帧、非零动作帧、选定终止／首帧和 A/B/A 关键帧及对应状态；其余只保留小型 step／completion 摘要。没有要求逐 substep 全量录像／大日志。

性能与资源分别按纯状态、仅 observer、观测相机三组报告。纯状态测启动／编译后稳态的 GPU／RAM 峰值和吞吐；observer 记录展示 K 与频率；观测相机记录 B、相机数 C、分辨率、采样频率及终止缓冲。容量可在预算内从小批量递增至 128、512、1024、4096 等适用档位，不要求在无法容纳的配置上硬跑，不为追求吞吐改变物理步长或求解器质量。

维护者提供 Go2 历史经验：B=4096、每秒约 16 个 control step。若指整批每秒推进 16 次，则约 65,536 env transitions/s；本项目尚未复现，任务、接触、控制 substeps、相机和训练器是否计入均需随测量报告。它说明纯状态应另测规模，不构成 PickCube 的预设性能保证。

图像理论预算示例：B=4096、两相机、128×128 RGB，仅一份 uint8 全批图像为 384 MiB，float32 为 1536 MiB；若使用同尺寸独立终止图像缓冲再翻倍。此数值不包含深度／中间 framebuffer、BVH、视觉实例、物理状态、模型、context 或策略。只有实际峰值能证明能否容纳。报告 batch control steps/s 与 B×steps/s，区分 physics substeps 和 sensor FPS；不以图像 FPS 代替仿真吞吐。

通用管线审查要求：asset／Task recipe 可声明各自实体和 frame，provider 可按公开格式／能力分派；不得按 Pendulum／PickCube UID、Panda／Go2 类名或某个资产路径选择专属控制、接触或图像接线。GeoPhys 扩展应形成公开通用形状／约束／device 端口能力。

一个 run 的必要证据为：输入 HEAD／diff、profile／source／配置身份、完整命令、owner／worker／device／传输说明、实际显式 step／clock、选定公开状态＋RGB、done／reset／generation 关联、close／worker 结果。一个统一外部 runner 和一个 offline reader 足够；不按每项 gate 新增生产探针。

纯检查复用已有 SDK／asset guarded 入口，新增与变化行为直接相关的用例；native、offline readback 分开报告。既有通过证据在输入未变时可引用，不为日志齐全重跑全部 G05。禁止为可逆文档／落位变动编写镜像实现的测试。

## 13. agent 接手规范与最终交付

维护者批准后，转交 agent 的单个完整 prompt 至少包含：本方案审批结果／修订、实际输入 HEAD／protected hashes、阶段分支、当前执行窗口、允许修改目录、精确目标与 mandatory gates、资源和 run 上限、依赖 profile、文档／证据位置、退出／提交规则。未批准的设计不由 agent 根据“尽量复用”自行决定。

可直接引用的任务骨架：

> 在现有 `codex/v211-stage6-parallel` 上，先核对实际 HEAD、dirty、protected inputs 和执行窗口。阅读 G06 Goal、交接、当前能力、优化总账的现行结案及本方案。仅实施维护者已批准的 D1～D6 和本次指定 attempt；按 owner 表扩展，禁止复制任务／Env 生命周期或读取 provider 私有 solver。完成同一窗口内的实现、必要修复、相关 pure/native/offline 验证、当前文档和本地提交。保留 MUJOCO_LOG.TXT、pins 与无关 workspace；新环境／pin 仅按批准范围处理；不 push／merge／tag。返回实际 diff、命令／证据、各 gate 结论、限制、输入／输出 HEAD 及下一窗口所需信息。

接收报告逐项写 `PASS / FAIL / NOT_RUN / UNSUPPORTED`，并区分 schema／fake、native、task predicate、Solution completion、RGB completion、Recorder readback、close／进程退出。不能用“调用成功／画面正常／shape 正确”三个结论替代物理与生命周期证据。

G06 接收后再提出 Env／Robot 精简包，按真实重复和职责收益确定范围；本阶段不新增 6d，也不挪用 G07 的三 provider×三 seed、最终集成与版本收口出口。

## 14. 本次方案交付的验证边界

本次验证仅覆盖当前源码／官方版本资料核对、设计与 G06abc／总账映射、文档链接／格式和 Git 变化边界。没有 native CUDA／IPC／renderer／4.0.1 安装兼容性实测，因此 D1～D6 中的候选方案仍须按前置门取得证据后才能转成能力声明。既有 `MUJOCO_LOG.TXT` 与历史 migration manifest 的 hash 不一致属于预存文档验证问题，保留原字节并单列，不通过修改保护输入使检查变绿。

上一版三个变更文档的相对文件链接检查无缺失，`git diff --check` 无格式错误。全仓文档 validator 仍返回上述唯一保护输入错误，并报告既有 79 项 historical link issues；不将其表述为全仓检查通过。输入／输出的生产 `task_env` tree 保持 `1f6ab03cde3e9075821cc59a09240637a4c4d535`，两个 submodule pin 不变。只读硬件元数据和文档检查明细位于 ignored `workspace/maintenance/v211_g06_plan_20261115_001/`。

本轮讨论修订只修改本文；已确认范围与待确认取舍见第 1 节。未开始实施、安装或 native 验证；文档检查记录位于 ignored `workspace/maintenance/v211_g06_plan_20261115_002/`。
