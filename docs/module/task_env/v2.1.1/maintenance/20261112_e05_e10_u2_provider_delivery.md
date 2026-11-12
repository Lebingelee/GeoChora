# E05～E10 U2 provider 与 worker 实施记录

状态：`IMPLEMENTED`（实施者自评）；输入 `1a2bc947`。本页记录代码、调用方和验证边界，独立主审及维护者接收待后续整体工作；不代表 E06 或整个优化已经接收。

| 责任 | 实际 owner 与范围 |
| --- | --- |
| 通用 Runtime | `sessions/api.py` 保留公开协议、共同分派和薄兼容导出；既有 typed submit、state boundary、clock、fault 与 session close 不因 source 准入迁移而更换。 |
| Isaac USD 准入 | `isaac_usd_admission.py` 拥有已支持 F06 delivery、Task binding、固定 capability、USD input 和 execution 构造；`isaac_g05.py` 拥有 G05 effort source 的精确验证。保留 delivery、hash、身份、timebase、设备、Controller 与 horizon 限制。 |
| MuJoCo 固定资产准入 | `mujoco_attachment_admission.py` 拥有历史 R03/R06 Panda 固定资产的精确校验；真实 source／attachment 校验仍交 U1 的结构与资产 owner。 |
| GeoPhys bootstrap | `provider_bootstrap.py` 集中 backend 初始化、solver 选项及对 `simulation.assemble_mjcf_articulated_runtime` 的调用；`bootstrap.py` 负责编排 source、初始状态和唯一 `GeoPhysRuntimeBoundary`。`merged_scene` 也使用公开 assembly 入口；此改动不实施 G06。 |
| worker 与 App | worker 管理请求、进程、source/session 和关闭；Isaac provider 选择并打开 App。isolated worker 的父进程构造 source 时不再启动本地 App，in-process 路线仍先准备 App。 |

GeoPhys 固定子模块的 `simulation` 已公开导出真实 assembly 函数；当前 pin 未发现等价的正式 backend 初始化 facade，`init_task_env_backend` 仍集中调用 `geophys.test_runtime.init_test_backend`。后续最小 provider 改善是由 GeoPhys 提供正式初始化入口，再由该 adapter 迁移调用；本轮不改子模块 pin、不使用私有 solver 补洞。

可交付给 GeoPhys 的最小接口方案：在 provider 自有的公开 runtime 命名空间提供 `initialize_backend(arch, **options)`（名称由 provider 最终确定），让现有 test/demo 和 TaskEnv adapter 调用同一个进程级初始化 owner。该 owner 需要保持当前 backend 归一化、编译／缓存策略、可用架构选择及失败清理，并与现有一次性初始化和 shutdown 状态共用；不能把 `test_runtime.py` 复制到 Core 或直接通过私有 solver 初始化。接口需定义重复调用、已初始化后切换 backend、并发调用和关闭归属的语义；当前实现对已初始化直接返回，不能推断它会校验后续 backend 是否一致。

交接和验收顺序：先在 GeoPhys 自己测试单进程首次／重复初始化、不同 backend 冲突、失败后清理及非 owner 不关闭共享 runtime；再由维护者更新 provider 依赖，修改 `provider_bootstrap.init_task_env_backend` 调用正式入口，复验 scalar 的构建、reset、一个 interval、第二次 reset、重复 close，以及 component 纯构建和现有 worker 参数转发。batch 实物验证仍属于 G06。本轮不改子模块 pin；现有公开 `simulation.assemble_mjcf_articulated_runtime` 是场景装配接口，不能把它误作 backend 初始化接口。

| GeoPhys 调用方 | 本单元边界 |
| --- | --- |
| 正式 scalar | `make_env → _GeoPhysSession → bootstrap_task_runtime → provider_bootstrap → GeoPhysRuntimeBoundary`；Pendulum 短程实际复验。 |
| component／纯构建 | `build_runtime=False` 不启动 bootstrap；U1 的 Empty/Panda source 编译检查可复用。component 的实际 runtime 仍使用同一 bootstrap，未单独扩张为任务矩阵。 |
| batch | `make_framework_parallel_spec` 先通过 component 声明与 compiler，再交 `make_batch_runtime/merged_scene`；后者直接使用公开 `simulation` 入口和同一初始化 owner。本单元没有运行或接收 G06 batch。 |
| replay | `reexecute_selected` 经正式 `make_env`，仍按记录源码与身份严格检查；跨源码重执行不会因为本次代码迁移获得资格，离线 codec 整理留 U6。 |

三家 adapter 分别物化其声明的 source 和 native 名称映射；共同 Runtime/Controller 合同仍负责已发布状态、clock、一次提交与推进。MuJoCo 和 Isaac 的显式子步及 GeoPhys 的状态/clock 证据分别保留在各自收据；GeoPhys 没有独立子步计数，启动隐式推进为未知，requested/applied 不当作实测力。

## 已有验证

- [定向合同](../../../../../workspace/maintenance/v211_e05_e10_u2_20261112_001/provider-contracts-final2/result.json)：20 项通过，包含实际 USD/MJCF 资产读取、精确 delivery/policy 拒绝、worker App 打开及关闭故障、父进程按部署方式选择 App；无 Isaac SDK 启动和物理推进。
- [GeoPhys Pendulum](../../../../../workspace/maintenance/v211_e05_e10_u2_20261112_001/geophys-provider-final/native-results.json) 在迁出 solver 选项后完成正式构造、reset、非零 interval、再 reset 与重复 close；其 native 子步未独立计数。[MuJoCo 装配 Panda](../../../../../workspace/maintenance/v211_e05_e10_u2_20261112_001/provider-native/native-results.json) 在固定资产准入迁移后完成同样短程，记录 5 个显式子步。
- Isaac F06 Position 和 G05 Pendulum 的进程内短程分别记录 5 和 25 个显式子步及成功 App close；[Position](../../../../../workspace/maintenance/v211_e05_e10_u2_20261112_001/isaac-provider-native/isaac-position/result.json)、[Pendulum](../../../../../workspace/maintenance/v211_e05_e10_u2_20261112_001/isaac-provider-native/isaac-pendulum/result.json)。这些运行早于最终 USD input 构建函数迁移；[函数对照](../../../../../workspace/maintenance/v211_e05_e10_u2_20261112_001/provider-function-comparison.json)确认迁移的九个函数 AST 不变，G05 实际配置和受限准入未变，但这些收据仍不是最终源码身份的进程内重跑。
- [最终源码的 isolated Isaac worker](../../../../../workspace/maintenance/v211_e05_e10_u2_20261112_001/isaac-isolated-worker-final2/result.json) 在明确预算两次顺序 App 启动后完成构建、reset、一个 interval、第二次 reset 和重复关闭；native 子步未独立计数，按 50 子步保守预算。较早一次计划只预算一次启动却因第二次 reset 实际顺序启动两次，偏差和原始日志保留在专用账本第 11 节。

本单元不宣称完整 Solution、任务成功、任意后端组合、renderer 收口或 SDK 退出日志无警告。启动时隐式推进仍为未知。

## 检查点与总账对照

| 检查点 | 结果 |
| --- | --- |
| S07～S08 | F06/G05 与固定 Panda 精确约束已分别归 provider/source owner；公共 API 留共同分派和薄导出。非本轮旧测试注入不再定义正式路线；实际 LIBERO 使用的 mixed actuator 能力保留，未当作纯实验删除。 |
| S09～S10 | provider bootstrap、实际 caller 和公开接口缺口见上；三个 provider 的代表 caller 完成有界运行，source、状态、clock 和推进证据按不同能力分别报告。 |
| S11～S12 | worker 保留进程／协议和关闭责任，App 选择／打开由 Isaac provider 完成；父子 source 重建与故障清理在实际 isolated 运行和 fake 故障中检查。 |

已对照总账 RUN-01～04 与 SRC-04 的 provider 准入部分；renderer/source 格式消费、所有旧 caller、记录/replay 和跨事件最终复验分别留 U4～U7。总账条目和 E06 的最终接收不因本单元实施者自评自动关闭。

## 文件、代码与来源

本单元统计基线为 `1a2bc947`。新增两个 provider admission 模块和本文，没有整文件删除或迁移；旧 API 的准入与 USD 构建函数按职责迁出，不能把重复计入的增删视为全新功能或净删成果。输入快照、逐次 source hash、diff、命令和原始收据保存在同一 [ignored 证据目录](../../../../../workspace/maintenance/v211_e05_e10_u2_20261112_001/)。

本单元 tracked blob：项目 **1,372 → 1,375**、`task_env` **979 → 981**；生产代码 **+405／−380，净 +25 行**，诊断／测试 **+88／−0**，文档 **+54／−4**。以有序完全相同行粗略匹配，原 API 至两个新 owner 分别至少有 96、134 行迁移；G05 和 GeoPhys 配置亦按函数迁出，不把这些迁移算作删码收益。相对 5c 接收点 `1f1359ee` 的累计 tracked blob 为项目 **1,361 → 1,375**、`task_env` **977 → 981**；Python/C/C++ 等生产代码 **+6,277／−14,938**，诊断／测试 **+5,202／−0**，文档 **+1,506／−94**，其他文本 **+125／−945**。累计值包含之前单元，不能归功于 U2。
