# R07c D01 diagnostic attempt001 — Sol 复核

日期：2026-10-30（Asia/Shanghai）。复核输入 `83f411ba726386fb2830ff2d334e913070d653b6`，camera 分支 `codex/phase-ii-01-camera`。冻结执行包输入 `06e289aa`，native 绑定实现 `4eaa76ba`。结论为 **`R07C_DIAG_D01_PROGRESS_RETAINED_REWORK_REQUIRED`**；不接收包级 S2/S3 PASS，不回退已完成的统一路线和原生执行事实。

## 已独立确认的增量

- candidate 当前确经 SelectedReferenceEnv → RuntimeSession → MuJoCo adapter，旧 BaseTaskEnv 活跃 candidate/策略路径已退出；不是旧 GeoPhys fake 代证。
- 交付清单按 output/protected/phase-md 三种命名空间解析，3287/3287 匹配：1074 个输出、2201 个保护输入和12份 Markdown。869项输入源码身份与冻结Git对象匹配；native plan列出的11项源码与当前实现匹配，`4eaa76ba..83f411ba` 只改文档/Skill。
- 按 run111 冻结环境复跑129项，129 passed。第一次 Sol 回放遗漏 `R07C_COMPOSED_MJCF`，产生12项 fixture 失败/117 passed；补齐环境后通过，两次日志保留，不归为实现回归。
- 按 run114 的参数独立重放 reader，返回 verified_complete；三个 H5 的192 transitions/195 observations、4800 step、原 row/模型/源/进程与锁绑定及手指开度 `q1-q2` 修正事实保留。该 reader 的成功不能替代下面缺失的检测。
- run108及更早失败原件、全部普通 attempt 历史保持。主 checkout 临时 receipt 写入事件已披露，最终 protected bytes一致；“无tracked源码改动”与“从未越出输出范围”是不同声明，本次不将后者签为通过。后续launcher须强制本包输出根。

## 必须修复的问题

1. **Contact revision 未在生产消费方检查。** `SelectedReferenceEnv.observation` 校验 source/materialization/episode/reset/control_step/time，却漏 `state_revision`。同路线底层替身复现：reset边界 revision0注入1，step后 revision1注入旧0，均仍发布 available predicate。reader的离线拒绝不能保护未录制或录制前的生产语义；G2 freshness 门未闭合。
2. **实测 joint limit 门缺失。** 从 run113 row0 的 H5 复算，boundary11的 finger_joint2 为 `+0.000563930778298527 m`；源XML声明 `[-0.04, 0] m`。当前reader只检查 action/target范围，没有校验实测 q，仍返回 verified_complete。MuJoCo是soft-constraint求解，此事实本身不等于solver实现错误；但原包未冻结允许该偏差的物理包络，不能将其忽略后签“无非法越界”门通过。修复优先保持源物理属性，以安全的内部目标/轨迹避免触边；不得事后扩大range、clamp观测或放宽原门。新run要记录实际限位/非有限值/warning检测证据。
3. **不匹配reset schema会先产生副作用。** 对已准入mixed session调用公开 `reset(v0_sample)`，落入legacy分支，执行第二次底层 `mj_resetData` 后才因缺 `_target_actuators` 报AttributeError；随后Env close还观察到reset-required错误。必须在 `_begin_reset`/native write前完成schema×profile×provider admission，v1进入legacy provider也应拒绝，不能静默清qvel。原v0正常路线不得受影响。
4. **任务语义构造穿过反向依赖。** Core `reference_env.py`直接import `bench_deploy.libero.evaluation.OnBowlPlateEvidenceV1`并构造benchmark证据。应经现binding回调由benchmark组装/求值，Core只校验/调度通用state/contact/lifecycle；不另建一套task协议或Runtime。此项是原工作包的所有权约束，不是新增功能。

另有收尾漂移：planning_manifest中的07/09哈希过期，但单独12项Markdown清单有效；Skill把会实际materialize MuJoCo的reset/step示例标为provider-free，并称stale contact始终unavailable。Sol本次只修正文档/状态/哈希；上述运行时缺口留下一份集中返工包，避免把新实现混入本次native身份。

## 证据与门处置

ignored复核根：`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r07c_diag_d01_001/`。关键原件：`integrity_mapped.json`、`s1_replay_receipt.json`、`reader_replay_receipt.json`、`raw_motion_limits.json`、`stale_contact_revision_reproduction.json`、`reset_profile_reproduction.json`及两个可复跑的底层替身脚本。原交付根 `r07c_diag_d01_001/` 只读，原manifest/report/gate_receipt不改。

G0输入/保护身份确认，输出范围事件保留偏差；G1当前source/reset增量保留；G2因freshness/reset拒绝门未闭合而需返工；G3冻结与N0事实确认；G4 counts/motion/On事实保留但实测限位门不接收；G5旧reader可复现通过但缺必要detector，不能作完整包接收；G6修正文档后仍须随返工包核实现/Skill。五任务R07c、18/22、P99、Qualification与develop-full集成均不变。

官方soft-limit解释：[MuJoCo computation — Limit](https://mujoco.readthedocs.io/en/stable/computation.html#limit)。该资料用于解释为何可能出现偏差，不用于追溯放宽本包阈值。

## 下一有界窗口

准备 D01 diagnostic attempt002，复用camera分支；Sol本次文档提交后的真实HEAD作为新输入。一个窗口集中完成上述四项、限位/warning与reader正负例、输出根守卫和必要文档/Skill收口；复用原source/采样/许可/编译布局与不受影响证据。不转D02/D03/D04、不合F线、不重做资产平台。

预计主动240–360分钟、timebox420分钟（末30分钟收口，包含下述维护者追加的Core去特化）；先S1再新的冻结native run。沿原MuJoCo3.8.1 CPU与共享锁策略，每进程600秒、RSS采样2GiB/终止3GiB、启动MemAvailable≥6GiB/低于2GiB中止；新attempt累计native3600秒/20000 step/30 reset，证据≤1GiB。新预算只有维护者转交完整attempt002包后生效，不继承attempt001余额。本次复核零新增native，无实施返工、无自动派发。

### 维护者追加：公共Core去除LIBERO专门处理

维护者在本次复核中明确要求将此项纳入attempt002。范围覆盖整个D01新增公共链路，而不仅是单个反向import：Selected入口/branch、Runtime admission、reset样本约束、MuJoCo layout/control/contact、canonical target和H5 metadata不得包含LIBERO任务名、On/物体名、固定7+2通道/48+43布局、50行init、benchmark controller身份或专用schema白名单。只改函数/变量名而保留同样隐式白名单不满足此门。

benchmark配方自行声明并校验固定source/hash/布局/采样/谓词/增益，Core在既有owner接收版本化、source-bound typed plan，按真实public compiled metadata验证可执行能力、名称/类型/单位/资源唯一性、写入和生命周期。MuJoCo adapter中的provider-specific lowering允许保留；任务知识移出。不能把Core admission整个挪给benchmark，或把任意字符串/manifest当增权令牌；不建立第二Runtime/Recorder/控制框架。

在同一真实公共Core路径增加一个非LIBERO、不同关节名称和通道数量的最小synthetic fixture，验证reset/mixed target/contact query/step/记录和收尾；它只证明公共合同摆脱固定benchmark假设，不授予另一任务/Provider native支持。旧PickCube/NutAssembly/Position/leaf/F线compatibility保留；本包不是全Core既有Panda历史profile重构。输出逐项去特化前后owner矩阵与静态残留分类，最后仍以LIBERO原门的真实native/H5结果验收。
