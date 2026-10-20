# GeoChora Phase II — P00 基线、Caller、兼容矩阵与有界可行性审查

日期：2026-10-20。审查类型：**AUDIT_ONLY**。
Core source：`8bc95ef4a38b6adbc61166c05b5bb5c2221065a6`，从 fetched `public/develop` 建立审查 topic branch。
结论：**COMPLETE_WITH_BASELINE_LIMITATIONS**；可供维护者授权下一步 A01，A02 仍以前置 A01 收据为条件。
本收据不是 Human Judge approval，不授权连续实施 A–D，不构成任何新 Qualification。

## 1. 范围、基线和保留义务

输入为 [00–05 的既有规划及首审收据](05_Architecture_Review_and_Execution_Order.md)、
[独立二审](GeoChora_PhaseII_Second_Review_develop_8bc95ef.md)，以及维护者随后要求执行 P00 的指令。
独立二审在本地仍是未跟踪文件，本次不代为提交，也不修改其内容。
本次仅新增 P00 文档收据；诊断脚本、日志、轨迹、图像及机器可读索引保存在 ignored workspace。
没有修改生产源码、tests、examples、canonical contracts、Skills、现有规划、冻结 Evidence 或 Gitlinks。

| 项目 | 实际基线 / 保护方式 |
| --- | --- |
| Core HEAD、远端 develop | 均为 `8bc95ef4a38b6adbc61166c05b5bb5c2221065a6`；fetch 后核对 |
| 实现树 | 前两个提交仅含规划 Markdown；生产实现与 `f292df1` 相同，本次执行结果重新绑定 `8bc95ef` |
| GeoPhys Gitlink | `c665ce5028a12bb4d2afe49f05e015fa9b684a39`；子模块工作区未改变 |
| Menagerie Gitlink | `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`；子模块工作区未改变 |
| v1.0.0 annotated tag | object `17c3100d4fabcb061c23569dea49973ebd177d51`；commit `42787f5e4f658a3f81fdd2140cf7544d6342c783` |
| v1.1.0 annotated tag | object `da46f1d213a457af7784a97d6d8470b7fa20cc32`；commit `7ed9e78a60d407fa1150c99209e06c70bfa0ed87` |
| 本地 `refs/heads/v1.1.0` | `f292df149f41520b484ff27cf2ff78a584903013`；与同名 tag 区分，未改写 |
| 已跟踪文件 | 对 738 个 root-owned 普通文件记录 SHA-256，结束时逐项复核原有 bytes 未变 |
| 原始五份规划 | 复核 `a299d8b` 中五个 SHA-256，均与 05 的原稿表一致 |
| 用户二审文件 | 记录并复核本地 SHA-256，保持未跟踪和原始 bytes |
| 已发布轨迹 | 五份轨迹只读加载并核对 hash；未知版本负例仅操作 workspace 副本 |

CodeGraph 索引在审查时为 current；先经索引定位 owner/caller，再检查具体源码、配置与 detector。
规范依据为 [ownership](../../../../global/ownership.md)、[public API](../../public-api.md)、
[runtime](../../runtime-and-providers.md)、[Artifact](../../task-artifact.md)、
[recording](../../recording-and-learning.md)、[qualification](../../qualification.md)。
计划、新增 proposal 和诊断通过均不改变这些页面所描述的当前支持范围。

## 2. Owner、生产 Caller 与复用决定

下表区分实际生产消费方、现有验证入口和待扩展能力。诊断目录的历史 worker 不能替代当前生产路径。

| 边界 / 当前 owner | 实际消费路径 | 本次判定与后续约束 |
| --- | --- | --- |
| [facade/registry](../../../../../task_env/registry.py#L130) | root task examples、env CLI、trajectory replay | **COMPOSE_EXISTING**。保留 `make_env`、registries；generic nested config 与 selected flat config 不混用；退休 UID 不恢复为 alias |
| [strict value codec / Artifact](../../../../../task_env/artifacts/contracts.py#L94) | 两任务 `task.py`、Runtime admission、trajectory metadata | **EXTEND_EXISTING**。A01/A02 归现有 artifacts owner，复用不可变值、strict codec、identity；v0 的 World/Entity/Action 约束不能原地放宽 |
| [generic lifecycle](../../../../../task_env/environment/lifecycle.py#L353) | `BaseTaskEnv` → `SingleTaskLifecycleAdapter` → RuntimeBoundary | **EXTEND_EXISTING**。reset/step/evaluation/fault 继续由现有生命周期 owner 承担，不创建第二个 Runtime/TaskEnv |
| [selected lifecycle](../../../../../task_env/tasks/reference_env.py#L68) | `make_env` selected branch、root examples、record CLI | **COMPOSE_EXISTING**。保留 task-owned Solution、Controller 和 native interval 行为，获得实际替代证据后迁移 |
| [control session](../../../../../task_env/runtime/sessions/control.py#L29) | selected env、control diagnostics | **EXTEND_EXISTING**。当前只准入 7 arm targets + 1 gripper actuator、0.08 m mapping；不能宣称通用 Entity×Group |
| [materialization](../../../../../task_env/runtime/sessions/api.py#L39) | control materialization、advanced runtime callers | **COMPOSE_EXISTING**。保留实际 manifest、source/Artifact/timebase linkage；复用 Provider public lowering |
| [Controller memory](../../../../../task_env/controllers/canonical/production.py#L79) | selected measured-boundary compute | **KEEP COHESIVE / EXTEND_EXISTING**。`compute()` 改写 gripper/expected-step memory，不能充当纯 preflight |
| [generic Recorder/wrapper](../../../../../task_env/recorders/wrapper.py#L16) | 公共 recorder exports、vector recorder；本次新增真实 scalar 诊断消费 | **EXTEND_EXISTING**。TreeCodec 缓存 spaces；wrapper 仅在 step flags 上自动 finalization，无独立 Stop contract |
| [canonical H5](../../../../../task_env/trajectory/canonical/h5.py#L8) / [execution](../../../../../task_env/trajectory/canonical/execution.py#L14) | selected env、`examples._common.load_recording_summary`、部分 learner/diagnostics | **KEEP COHESIVE**。保留 Panda/expert/native evidence owner；不要把它们强制改成通用 action tree 的同一 binary schema |
| [conversion validator](../../../../../task_env/trajectory/processing/transcode.py#L269) | convert CLI、collection conversion | **EXTEND_EXISTING**。当前要求 v2 和 `(T,7)+(T,1)` Panda universal action；通用 inspector 不等于 validating reader |
| [ExpertDataset](../../../../../task_env/alg/agent_factory/data/impl/expert_dataset.py#L82) | 同文件 dataset construction、训练数据入口 | 格式由 shape 推断；termination 被用于 legacy success signals。新版本需显式准入和 outcome policy，不能静默解释新文件 |
| [CPIQL data owner](../../../../../task_env/alg/agent_factory/data/impl/cpiql/common.py#L277) | dataset caching/segment/bootstrap 消费 | 已有 success/terminated/truncated 分离，可评估组合复用；本轮未运行该训练路线，不宣称 vNext 兼容 |
| [Reporter V2](../../../../../task_env/reporter/v2.py#L284) | remote command endpoint、已有 TCP fixture | 已缓存 descriptor/space；无 STOP command。C03b 要明确拒绝/版本化扩展；schema 改变需要新 Env/session，不能默认 remote 自动兼容 |
| [camera admission](../../../../../task_env/render/camera/api.py#L27) / [MuJoCo camera](../../../../../task_env/render/camera/mujoco.py#L15) | advanced camera factory、P1.4 diagnostic | **EXTEND_EXISTING**。当前 same-name pairing、静态 mesh bridge；正式动态跨 Provider 支持仍在 D03/D04/D05b |

GeoPhys 已有 [ImportedScene public lowering](https://github.com/SCAILab-USTC/GeoPhys/blob/c665ce5028a12bb4d2afe49f05e015fa9b684a39/src/scene/scene_import.py#L296)：
`ir`、`capability_report`、`solver_scene_desc`、`build_render_scene_desc`。
本次原生诊断复用仓库既有 conformance adapter 和 Provider public APIs；没有读 solver-private arrays 或 renderer-private handle。
原生 MuJoCo render-only model/data 由诊断自己持有，只调用 forward/capture，不参与权威物理积分。

### 2.1 A01/A02 前必须保留的现状

- `EntityDefinition.semantic_id`、`WorldDefinition` 唯一引用检查、strict unknown-field/schema 拒绝、immutable Mapping 与 deterministic hash 已实现。
- `ActionIntent` v0 固定为 arm joint + gripper target；typed multi-group Scene/Asset 契约仍是新提案。
- [generic Env](../../../../../task_env/environment/env.py#L154) 明确拒绝多 Robot Controller 所有权。
- [Pendulum action](../../../../../task_env/robots/pendulum.py#L54) 已有公开 `{"torque": array}` 树，进入 `ControlCommand` 后投影为向量。这是可复用能力；不能把现有 Core 一概称为“没有 action tree”。
- 现有 Recorder 无法直接存储任意 Entity×Group 的嵌套 request；其 limitation 是 vector-only durable representation，不能通过让 Env 丢失结构来规避。

## 3. 旧/新兼容矩阵

本轮没有创建 vNext writer、reader 或 EpisodeOutcome。下列“后续要求”是实施门槛。

| 路线 | 当前 reader/writer 与实际 Evidence | 后续要求 / owner |
| --- | --- | --- |
| Artifact/world/state v0 | strict codec + reference construction；JSON/YAML roundtrip、未知字段/版本、NaN、重复 Entity、未知 pose、零 quaternion 负例通过 | A01/A02/B04 保留 v0 bytes/hash；新 discriminator、显式 projection/migration；拒绝新版本被旧 codec 静默读取 |
| generic H5 v1 | 历史 regression writer；本轮 T=1 fixture 写入/基本 inspection 通过；Stage11 conversion 明确拒绝 v1 | C05a3 保留历史读取义务，不作为新 structured writer |
| generic H5 v2 | T=0、T=1 terminated/truncated fixtures；真实 Pendulum T=2，均满足 T/T+1 并可 inspection | C05a2 在现有 owner 扩展新版本；增加 typed request、events/outcome 和最低必需 non-arm loader |
| canonical outer v0 | 3 份已发布轨迹当前 reader 通过；当前两 Provider PickCube 各录 3 intervals | C05a3/b 保留旧 schema、logical/numeric/hash 检查，不套用通用 binary ABI |
| execution v1/v2、old/streaming layout | 2 份已发布 v2 轨迹通过；old/streaming detector 34 项通过；当前两 Provider NutAssembly 各录 3 intervals | C05a3/c 保留 native substeps、owner/clock/payload 校验；逐项列明 legacy/layout 适配 |
| non-arm conversion | synthetic torque 与真实 Pendulum 文件可写、可 inspection；`validate_trajectory` 因缺 Panda universal keys 拒绝 | 已复现能力缺口；C05a2 扩展声明支持的 non-arm 转换，不能把 inspection PASS 当训练准入 |
| unknown schema | 对 workspace 副本改版本，canonical outer、execution、generic conversion validator 均拒绝 | generic inspector 只报告未知版本；部分训练 loader 依 shape 推断，尚未证明 fail-closed。C05a2/a3 需独立版本入口测试 |
| offline Expert/CPIQL loaders | 仅 SOURCE_AUDIT；两者 success/end 处理不同，未运行训练 | 明确必需 loader；保留旧数据语义；对新 Stop/failure/horizon 的 end/bootstrap 做有界测试，不升级全部算法 |
| wrapper/vector/online learner | scalar wrapper 当前正向步骤与手动 end_record 通过；新 Stop/switch 未实现 | C03b 实现 exactly-once finalizer；任意 Gym wrapper/learner 不自动获准；vector slot/autoreset 独立保护 |
| Reporter V2 | SOURCE_AUDIT；协议只有既有命令和固定 descriptor | C03b 明示 remote Stop 支持/拒绝；C02c 禁止不兼容 schema 热切换 |
| camera cross pairing | 当前 admission 在 native construction 前拒绝；本次仅独立 native 诊断通过 | D05a 绑定实际 graphics/device envelope；D03/D04/D05b 完成 lowering、动态同步和正式准入 |

### 3.1 生命周期、失败与训练结束矩阵

以下是 C02/C03/C05 需要固化的契约检查项；独立 Stop、统一 Fault 和相关 adapter 目前未实现，本轮没有将这些格子记为运行通过。

| 情况 | 需要保证的结果 | Recording / end / bootstrap |
| --- | --- | --- |
| reset 前 step/Stop | step 保持拒绝；新 Stop 明确拒绝尚无 episode 的调用 | 不创建伪 initial boundary 或样本，不调用 Provider |
| reset 后 T=0 Stop | 一个 outcome/event、一次 finalizer；重复调用保持同一结果 | 0 transitions / 1 boundary；无训练 transition，不能补造 flags |
| 正常 active episode 外部 Stop | 在已完成边界终结；不回写上一条已返回 flags | episode end 独立表达；bootstrap 仅在最终 state 有效且版本化任务策略允许时成立 |
| task 自然终止 / task-defined Stop | 保留 task success/failure 的原始事实和明确终止原因 | 真正 terminal 按声明 policy 关闭 bootstrap；success 不自动等于所有任务的 episode end |
| horizon | 保留截断原因和最后有效 observation | end 与 terminated 区分；有限 horizon / continuing policy 的 bootstrap 由任务契约确定 |
| task failure | 保留语义 failure 与合法边界，不冒充成功 | 自然 terminal failure 关闭 bootstrap；不能将 terminated 直接当 success label |
| 部分 native commit/step 失败 | FAULTED，记录最后已知完整边界、已发生进度及未知部分；后续 step 拒绝 | 不补造完整 interval/transition；旧 strict writer 不能保存有效轨迹时，保留独立 failure receipt，不伪造完整录制 |
| 已 terminal/fault 后 Stop、重复 Stop | 不覆盖既有 outcome，不重复事件/finalization | 收据保持原失败/结束原因；原生不确定状态不能用于 bootstrap |
| Recorder inactive / active | Stop 的生命周期结果不依赖是否录制；active recorder 的 finalizer 有唯一 owner | 不漏关闭、不重复关闭；inactive 不凭空生成轨迹 |
| same-schema switch | 同一 declared safepoint、memory initialization/ack/event；副作用前拒绝或不可恢复时 Fault | 存储 switch event，不改变 observation/action space；不兼容 schema 重建 Env/wrapper/session |
| wrapper/vector/remote/learner | 每个声明支持的消费路径显式处理 outcome；未适配路径清晰拒绝 | 不假设 Gymnasium、Reporter V2 或全部算法自动理解独立 Stop |

现有闭环的 owner 顺序需要保留：`make_env` 选择实际构造分支 → config/admission → materialization →
reset sample/realization → Controller/Solution 与物理 interval → task evaluation/observation → Recorder。
失败和 close 沿同一 owner 链返回；Recorder 不取得 Controller memory 或 physics authority。

### 3.2 五份已发布轨迹的只读结果

路径均位于 `docs/releases/v1.1/evidence/raw/l2/`；完整路径、SHA-256、原始 source revision 和 metadata 存入本地 `frozen_readers.json`。

| 冻结记录 | Schema | T / T+1 | 结果 |
| --- | --- | --- | --- |
| `p2_0_b_s4_5_a_20261016/5d57272d/pickcube_mujoco_seed31.h5` | canonical outer v0 | 470 / 471 | PASS |
| `p2_0_part_b_s2_c1_20261016/pickcube_geophys_v4/execution.h5` | canonical outer v0 | 151 / 152 | PASS |
| `p2_0_part_b_s2_c1_20261016/pickcube_mujoco_v4/execution.h5` | canonical outer v0 | 470 / 471 | PASS |
| `p2_0_part_b_s2_c2_20261016/nutassembly_geophys_final/execution.h5` | execution v2 | 2380 / 2381 | PASS |
| `p2_0_part_b_s2_c2_20261016/nutassembly_mujoco_final/execution.h5` | execution v2 | 2373 / 2374 | PASS |

这些是当前 reader 对冻结旧 source 记录的兼容结果，不是 current-HEAD rollout。
inspector 的 `storage_roundtrip=PASS` 仅是其返回字段，本次只读加载未执行新 save/load roundtrip、物理 replay 或 D0。
另一个已跟踪 H5 是 learner return curve，不是 trajectory，本次仅识别其类型，不纳入五份轨迹通过数。

## 4. 实际运行、Detector 缺口和资源范围

### 4.1 环境与预算

- 既有 Python 3.12.14 环境；未安装或更新依赖。默认 shell Python 为缺依赖的 3.14 环境，未用于验证。
- NumPy 2.2.6、MuJoCo 3.8.1、Taichi Forge/runtime 0.6.2、Gymnasium 1.3.0、H5py 3.16.0、pytest 9.1.1。
- Linux x86_64，Intel i5-14450HX，16 logical CPUs，约 15.42 GiB RAM。采样初始 available 约 4.18 GiB。
- `PYTHONPATH=GeoPhys/src:.`，`GEOPHYS_TAICHI_BACKEND=taichi-forge`；OMP/BLAS/MKL/NumExpr 设 1 thread。GeoPhys init 日志仍报告 native CPU runtime 4 threads，不能称全部线程均为 1。
- 每个诊断 worker 独立进程：8 GiB 单进程 RLIMIT_AS、1800 MiB 采样进程树 RSS guard；通常 wall/CPU 为 30/20 s，GeoPhys 为 90/60 s，五文件 pytest 为 240/180 s。
- RSS 每 0.1 s 采样，可能漏掉瞬时峰值；不是 hard RSS 限额。RLIMIT_AS/CPU 是 per-process，不是整棵进程树 quota；未测 GPU VRAM 峰值。
- warm native kernel cache 被保留；本次耗时不是冷启动性能承诺。native 资源最终回收边界包含 worker exit，不把 `close()` 当 process-global allocator 全释放。

### 4.2 本轮执行结果

| 执行 / 成本层 | 结果 | 实际范围、失败和解释 |
| --- | --- | --- |
| 原五文件 targeted pytest / S1 | **93 passed、6 subtests passed、1 failed**；153.35 s pytest / 153.622 s supervisor | 唯一失败为 retired `clearance_candidate_v5` import；没有删除或跳过 |
| recording streaming pytest / S1 | **34 passed、2 failed**；2.11 s | 两项由 live_recording/lifecycle_full 导入 retired `nut_assembly.assets` 失败；独立 old/streaming payload 检测仍通过 |
| selected record CLI pytest / S1 | **12 passed**；0.30 s | 完成条件、truncation/strict status 和失败录制可读性；synthetic session，不是 native task qualification |
| solution_lifecycle detector | **collection ERROR** | retired `nut_assembly.canonical_solution`；未执行该文件测试体 |
| P1.1 detector | **FAIL at import** | retired `pick_cube.candidate`；未生成有效 P1.1 report |
| P1.4 `fresh_guard()` | **FAIL** | 同一 retired PickCube candidate，旧 hard-coded hash 不代表 current selected task |
| 当前 v0 strict contract / S1 | **PASS** | 三个 recipe，JSON/YAML identity 及上述负例；不启动 native session |
| camera pure/admission / S1 | **26/26 pure PASS；admission PASS** | 缺能力、未知 renderer、cross pairing 均在 native construction 前拒绝；positive constructor 为 mock，单报 |
| synthetic generic H5 / S1 | **PASS_DIAGNOSTIC** | T=0/T=1/T+1 与 flags 写读；structured request 被 TypeError 拒绝、non-arm conversion 被拒绝均作为现有限制记录 |
| 五份冻结旧轨迹 / S1 | **5/5 PASS** | 只读、provenance/hash/T+1；严格 reader 的未知版本负例也拒绝 |
| Pendulum public scalar + wrapper / S2 | **PASS**；修正后 15.995 s / 约 532 MiB sampled RSS | seed 73，2 steps，torque tree、observation space、generic H5 2/3；conversion 仍因 Panda 约束拒绝 |
| selected task 当前微探针 / S2 | **4/4 scoped PASS** | PickCube seed31 / NutAssembly seed19 × GeoPhys/MuJoCo CPU，各 horizon3、3/4 边界、真实录制/reader；均 expert incomplete/failed due bounded truncation，不能称 expert PASS |
| 双原生对象施控 / S2 diagnostic | **GeoPhys、MuJoCo 均 PASS** | 两个无接触 1-DOF root bodies，独立 motor；每 phase 50×0.002 s；非施控对象位移 0；不经 Core Entity×Group |
| native MuJoCo EGL / S2 diagnostic | **PASS**；0.646 s | 无 DISPLAY；两次创建/关闭，每次两帧 RGB/Depth 与 transform oracle |
| native MuJoCo GLFW | **PASS**；0.528 s | 有现有显示会话；不是 headless fallback |
| native MuJoCo OSMesa | **FAIL**；0.215 s | import OpenGL 时 `NoneType.glGetError`；本机 OSMesa 软件路径不可用，不安装依赖来掩盖 |
| GeoPhys fixed boundary × MuJoCo EGL | **PASS_DIAGNOSTIC**；6.115 s / 约 420 MiB sampled RSS | 公共 SceneRuntime tick/readback 不变；仅诊断几何更新与 renderer，不是 D05b 正式 pairing |
| docs baseline validator | **FAIL：仅 count limit exceeded** | 实际 tracked docs64 / task_env20；固定 docs limit58。冻结 refs/bytes、JSON、链接等未报告其他错误 |

三组 pytest 合计为 **139 passed、6 subtests passed、3 failed**；另有一个 collection error，不能汇总成“全绿”。
P00 还保留一个诊断自身的错误首跑：Pendulum wrapper 收到向量而不是其公开 torque tree，在物理 step 前拒绝。
修正诊断调用后重新运行通过；首跑日志未删除，也未将其归类为生产回归。

四条 selected 微探针耗时分别为 MuJoCo PickCube 0.647 s、NutAssembly 0.950 s，
GeoPhys PickCube 21.189 s、NutAssembly 23.186 s；最高 sampled RSS 约 645 MiB。
它们只保护 construct/reset/3 intervals/record/read；本次未重跑完整 expert、C1/C2、checkpoint、训练、batch campaign 或 S4。
首审记录的完整 GeoPhys NutAssembly 60 s CPU TIMEOUT 仍是未解决的完整路线 Evidence 缺口。

### 4.3 渲染与双对象探针的精确 Oracle

原生图形身份：**NVIDIA Corporation / GeForce RTX 5060 / OpenGL 4.6.0 NVIDIA 595.84**。
因此本次证明的是 **CPU physics + MuJoCo native EGL/NVIDIA graphics**；没有证明无 GPU 的 CPU 软件渲染。
以后 D05a 必须区分 physics backend、graphics platform 和实际 render device，不能把 `backend=cpu` 当软件 rasterizer 承诺。

渲染 microfixture：96×64，fixed camera `(0,0,2)`、identity quaternion、FOV45°，
红色 box half-size0.12 m、无接触，render-only mocap body 的 x offset 从 -0.3 m 到 +0.3 m。
Oracle 为可见像素 >20、centroid x 位移 >15 px、光学深度1.88 m±0.002 m、render data.time 保持0。
EGL 独立 worker 删除 DISPLAY；GLFW 保留显示会话；OSMesa 独立 worker 删除 DISPLAY 后明确失败。

结合 GeoPhys 的诊断先推进 slide fixture 10 native ticks，冻结在 outer step1/time0.02 s、x≈0.0100000007 m。
随后仅更新 render-only geometry，centroid 从36到60 px、depth≈1.8800508 m。
每次 capture 后复核 Provider public `SceneRuntime.clock_snapshot()`、qpos/qvel 和 canonical readback：
physics_ticks 仍为10、publication_epoch0、state完全相同。无 render `mj_step()`。
这是受控 visual transform 的技术可行性证据，未证明 Task Artifact→视觉 lowering→动态同步→camera admission 的生产闭环。

双对象 probe：同一 MJCF 两个相隔1 m的 root bodies，各一 z-axis hinge 和 motor，gravity/contact关闭；
两 phase 从公开 reset state 分别提交 `(0.1,0)`、`(0,-0.1)`，每 phase 0.1 s。
要求目标关节沿请求方向转动 >0.005 rad、另一个关节变化 <1e-6 rad、时间0.1 s。
GeoPhys 为约±0.0174897 rad，MuJoCo 为约±0.0157395 rad；这里只检验各自的隔离和方向，
没有用这些不同结果宣称跨 Provider dynamics equivalence。
Core 多 Entity/action group 绑定、Controller memory 原子性及部分施控失败仍为 **NOT_IMPLEMENTED**。

## 5. Detector 的处置与后续保护门槛

| 问题 | 本轮分类 | 后续保护责任 |
| --- | --- | --- |
| Guard 的 V5 candidate import | 退休任务依赖导致 detector 失效；不是此次代码回归 | 保留纯 Guard 的 dwell/clock/priority 断言；C05c 审查当前 selected Guard composition；旧 candidate 行为归 frozen source，不恢复 alias |
| solution_lifecycle collection error | 退休 canonical_solution 依赖 | C03/C05c 将仍适用 completion/failure/reset invariant 指向当前 lifecycle/Outcome owner；保留历史范围，不直接删除文件求绿 |
| 两个 streaming live-policy tests | imports 链经 tracking_worker 触及退休 assets | C05a3 区分 format/owner codec 检测与旧 campaign worker；current policy detector迁移需独立审查 |
| P1.1/P1.4 fresh guard | 旧 candidate/hash detector，无法启动 | A01 保护当前 strict codec/selected identities；后续建立 current provider-free fresh-process sentinel，历史 oracle 不静默替换 |
| non-arm conversion | 已复现的当前功能限制 | C05a2 扩展现有 conversion/loader；generic H5 inspection 继续保留独立职责 |
| ExpertDataset shape inference/end signals | SOURCE_AUDIT 的兼容风险，训练未运行 | C05a1/a2/a3 明确未知版本拒绝、task success 与 episode end 分离，增加 loader-level fixture |
| remote Stop 与 cached descriptor | 当前无支持入口 | C03b/C02c 明确协议与适配边界；不把新 Env 方法视为所有消费端已兼容 |
| docs fixed ceiling | 历史整合治理政策冲突 | 需范围限定例外/政策决定，保留 hash/source/URL 检查；本次不修改 inventory/validator |

## 6. P00 后收敛的实施入口

本次收据记录上一轮收敛的 **20 个父 Goal / 33 个实施切片 + P00/P99**。
00–05 文件仍保留 `8bc95ef` 的31切片规划，本次未重写；不能声称旧表已同步。
后续对应 Goal 开工前须在其 owner 规划中落实下面修订。机器可读建议 DAG 经检查有35个唯一条目、无缺失前置和环。

| 父 Goal | 需要固定的切片 / 退出要求 |
| --- | --- |
| A01 | 单切片；现有 artifacts owner 内的新 Asset/Entity/Scene 身份值契约，保护 v0 |
| A02 | 单切片；Component/Articulation/Frame 静态契约及解析 Oracle |
| A03 | 单切片；Robot/Group 组合与双实例命名、引用解析 |
| A04 | 单切片；复用 registry/public importer 的 source lowering 与 factory 迁移 |
| A05 | 单切片；A 的静态集成、legacy identity/reference gate |
| B01 | 单切片；strict YAML/declared Hook，不启动 native Runtime |
| B02 | 单切片；Role、固定拓扑 Variant、sample/RNG/reset realization |
| B03 | a只读/action-aware语义；b时序 memory 每 sample 一次提交 |
| B04 | a版本/discriminator/migration baseline；b compiler/codec/hash 与嵌套拒绝矩阵 |
| B05 | 单切片；参考语义差分；candidate/frozen、Stage-1/Judge 分开 |
| C01 | a配置/静态 plan；b实际 requirements/manifest admission |
| C02 | a Entity×Group binding；b纯 preflight 与原生提交分开、单 Robot arm+hand及最小双 Entity S2；c同 schema safe switch |
| C03 | a scalar/reset/step/fault；b wrapper-visible Stop/outcome/end/bootstrap |
| C04 | 单切片；固定 public/privileged/private schemas、必要反馈与诊断分离 |
| C05 | **a1值语义/版本/Stop finalizer契约；a2现有generic H5 vNext与最低必需loader；a3旧canonical/execution适配；b PickCube；c NutAssembly** |
| D01 | a有限输入真实 bridge；b两 Provider 限定 vNext materialization/realization |
| D02 | a typed state/clock/lifetime契约；b真实投影、free/spherical等验证 |
| D03 | 单切片；public visual lowering、rigid/articulation动态同步、像素/step/多consumer Oracle |
| D04 | 单切片；camera、RGB/Depth、受限segmentation分别准入 |
| D05 | a配置/graphics/device/版本与可行性 envelope；b正式动态跨Provider路线与失败/资源验收 |

关键直接依赖修订：

- C05a1 ← C02a、C01b、D05a；C05a2 ← C05a1；C05a3 ← C05a1、C05a2。
- C03a ← C02a、D01b、C05a2；C04 ← C03a、D02b。
- C02b ← C02a、C03a、C04、C05a2、D01b；C03b ← C03a、C04、C05a2。
- **C02c ← C02b、C03b、C05a2**，解除完整 C05c 的不必要前置；具名任务可继续拒绝未验证切换。
- C05b ← C02b、C03b、C04、C05a3；C05c ← C05b、D02b。
- B04b ← B04a、B03b、D05a。A03/B03 定义静态要求，B04b 编译要求，C02a 实现实际 binding；不引入反向编译依赖形成环。
- D03 ← D01b、D02b、D05a；D04 ← D03、C04、C05a2；D05b ← D05a、D04、C01b。Renderer 不等待 C05c。
- P99 的 required envelope 保留真实新主线、最小双 Entity 执行和正式 D05b；缺必需 Evidence 就明确 partial，不用 accepted-deferred 宣称完整 A–D。

### 6.1 A01 授权后的第一项检查

仅在收到维护者下一条实施指令后开始；本次未启动 goal mode。

1. 确认届时 HEAD/Gitlinks/dirty 与本收据是否漂移；漂移时先复核受影响部分。
2. 在现有 artifacts owner 内明确新值契约与 v0 projection；不先改 Runtime、registry factory 或冻结任务。
3. 明确 Asset definition identity、Entity instance identity、Scene content identity 的区别；同 Asset 两实例互不冲突，instance renaming/content变更具有明确 hash 规则。
4. 新 codec 对 unknown field/version、重复实例、非法引用、NaN/Inf、输入对象后续突变 fail closed；复用现有 strict codec 能力，扩展前检查是否影响 v0。
5. 将本次当前 v0保护诊断的必要断言落实为后续受治理 detector；原 reference construction、旧轨迹 reader及v0 bytes/hash保持。
6. 提交 A01 receipt 后，再审 A02 Frame/Articulation 的字段、变换约定及独立解析 Oracle。

A02 必需覆盖父子 frame composition/inverse、quaternion方向、joint/actuator引用、重复名、cycle/missing parent拒绝，
并区分 static contract成立与实际Provider multi-DOF实现。涉及现有共享codec时执行旧identity与camera geometry负例；
若扩大到实际runtime，则须重新界定切片并增加相应S2，不能用静态结果替代。

## 7. Evidence、复现及交付状态

本地唯一原始记录根为 `workspace/maintenance/phase_ii_p00_20261020_audit_01/`，按仓库规范不提交：

- `baseline.json`、`protected_tracked_sha256.json`、`protection_verification.json`：source/ref/bytes与用户文件保护。
- `caller_matrix.json`、`compatibility_matrix.json`、`proposed_dependency_map.json`：owner、版本及建议前置。
- 各 run 的 `run.json/stdout.log/stderr.log`：精确argv、环境、预算、return code、采样资源；共23个受监督run。
- `probes.py`、`run_bounded.py`：本次可复现诊断；脚本逐步增补probe，保留最终版本；并非新的production test framework。
- `strict_contract.json`、`frozen_readers.json`、各native/selected/scalar JSON、H5和NPZ：实际输入/输出事实。
- `gl_identity.json`：辅助原生context身份读取，独立于23个受监督run计数。
- `audit_receipt.json`、`run_index.json`、`evidence_index.json`：scope、结果和本地文件SHA-256索引；无自动Judge批准。

从仓库根使用已配置的 TaskEnv Python 复验五文件基线：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=GeoPhys/src:. "$TASKENV_PYTHON" -m pytest -q -p no:cacheprovider \
  task_env/diagnostics/tasks/test_reference_construction.py \
  task_env/diagnostics/tasks/test_selected_consumers.py \
  task_env/diagnostics/tasks/test_nutassembly_outcome.py \
  task_env/diagnostics/phase1/integration/test_guarded_transition.py \
  task_env/diagnostics/render/test_backend_registry.py
```

其他受监督命令、fresh-process环境及输出名以 `run_index.json` 为准。重跑需使用新输出目录，不能覆盖本次原始记录。
不将本地绝对路径、缓存和机器可读事实升格为稳定 public API；外部审阅者未取得raw时，只能据本文核对有界结论，不能据此授予Qualification。

本收据的文档检查使用临时隔离 Git index 纳入新增文件，真实 index 保持原样。
新增收据计入后 docs65/task_env21，仍受现有固定数量上限约束；本次不调整治理政策。
完成后复核相对链接、`diff --check`、原有738文件、Gitlinks、冻结refs和用户二审文件。

**停止点：P00 审查完成；等待维护者命令进入 A01 → A02。没有启动实施、commit、push、merge 或任何 S4 campaign。**
