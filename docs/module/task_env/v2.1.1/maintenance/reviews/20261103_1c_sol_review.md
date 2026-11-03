# G01/1c attempt001：Sol 独立审核

日期：2026-11-03。结论：`ACCEPTED_BOUNDED_1C_DESIGN`，包含本页记录的主审文档修正。接收的是双向 physics 协议设计交付；五份协议仍为 `DRAFT_FOR_DISCUSSION`，不批准 schema/adapter 实现、不证明 native 支持、不启动 1d。

## 输入、范围与原始证据

- 实际 input `b0024c71614f2d2ede8d9eb1db594cfcde3e9278` → output `4c3894df74f1946417b360e76fe3440b0551805d` 为直接父子；develop 原执行仅改 9 项允许文档/JSON。
- 核对 1c package manifest `9f8554eedd5f1e66a8426a5053c82be74d9a6e18fd64ccc014c1d6fac2610da7`、prompt `c0bf1ec99591b51ba2ba9a14d8f36fc8e8963f4e5a35218323d006729293d20e` 与输入快照。交接前言提到曾打开旧 1a 文件；本审核依据封存的实际 1c 包、提交和输出内容判定，不依据“活动目标”字样扩大授权。下一包 README 应给出完整唯一入口。
- output manifest `06968c93b5b6f3b2ceed1b4ab90d7c5eaddf5ab5873143a44a3b87f41ee866a1`；清单 5 文件大小/hash 全匹配，共 63987 bytes；report SHA-256 `f7e6e8b16db0801120c8bca4fefc732964b45f83fab4d768e39693812ba87f20`。
- 78 项输入中 7 项是允许更新文档，其余输入保持；1a/1b/1c 原始 manifest 和文件全部复核，保持原字节。GeoPhys pin/检出 `67da1165149486d3ae3e779c13ce31af49e17d50`、两项未跟踪保护文件保持。
- 执行声明零 subagent、窗口已释放；主审未启动 subagent、provider import、App、solver、physics、GPU 或 implementation tests。

## G0–G5 处置

| Gate | 主审结论 | 依据与限制 |
| --- | --- | --- |
| G0 | 接收 | 输入父子关系、允许路径、包/raw hash、保护与 pin 一致 |
| G1 | 修正后接收 | query/build/reset/command/advance/publish/close 的输入、输出、owner、identity、失败责任具体；澄清 provisional build 与最终准入 |
| G2 | 修正后接收 | 三首批路线事实与未知分开；补具名复杂层级/两个 solver 的设计例，不新增能力证明 |
| G3 | 修正后接收 | 修正 Jacobian 方向和 force provenance；ready/running 分开；初次 build 与破坏性 reset/rebuild 的失败分开 |
| G4 | 修正后接收 | P1–P4/N1–N6 规划例，补 batch mapping、N4 interval 起点/全局索引；文档/JSON/DAG/draft/status 校核，非运行测试 |
| G5 | 接收 | 原始报告、命令、findings、快照/manifest 和释放声明齐全；主审修改另记提交，不改 raw 或增加执行 attempt |

## 主审修正

1. **力映射不能把 Jacobian 用反。**原 `q_native=f(q_closure)` 与 `tau_native=J^T F_closure` 使用同一 Jacobian，维数和映射方向不一致。现明确 A=df/ds 为 n×1，共轭关系 F_s=A^T*tau_native；native effort 分配并不唯一。若另有 s=g(q_native)，其 J_s 才能用于 tau_native=J_s^T*F_s，仍须证明 transmission/约束/限幅内可实现。主审只修正数学契约，不选未经验证的具体夹爪分力。
2. **保留已有原生 force 事实。**原文称 closing_force_N 可由 finger position 推导，没有源码支持。`control.py::feedback_value` 用位置计算 opening，用有效 native_force 的符号投影计算 closing magnitude；MuJoCo force-admitted profile 与 NativeControlFeedbackSampleV1 有独立测量来源/时间校验。actuator force 仍不等于接触传感器夹持力，不能由 ACK 或位置推断。
3. **先检查的条件与构建期条件分开。**静态 required 通过后，只有明确 adapter 能在 native_build 核对的未决项才允许 provisional build；最终所有 required 都通过才发布可执行 session。无 adapter 的未来路线在构建前拒绝，不能借 build 查明之名启动未实现路线。
4. **状态机和失败有具体起点。**已构建而未通过 reset 的 ready 不允许 episode command/step/正常 obs；初次 build 失败且清理成功可以回未物化，reset/rebuild 已关闭旧资源后失败则 faulted，不能声称旧 episode 恢复。
5. **案例要能检查实际问题。**原 P2 只有一个 solver 和刚体接触，不能展示多 solver；改为一个 Genesis provider 的 rigid＋FEM 和两条 required interaction，显式没有新运行证据。N4 给出从 global native step 5/t=.010 开始，确认到 step 7/t=.014、尝试 step 8、预期到 step 10/t=.020；不再把绝对时间与区间计数混用。补 env→row context 让 stale row 反例有依据。
6. **复杂层级与后续实现不悬空。**补 standalone Newton、Isaac/PhysX、Isaac/Newton、Genesis、SAPIEN 表达检查，区分 SDK solver 与宿主插件实际支持。source-map 增协议→代码 owner→3a/3b/3c/4a–4c/5a–5c/6a–6c 的归属，包括统一表示/兼容 codec；1d 再补完整三方追踪。

原始 report/findings 的相应判断保持原字节，由本主审说明收紧。执行 checker 只证明文档与上下文结构；本次增加的公式/时钟/状态机核查也是静态设计审阅，不是运行验证。

## 对报告五个待确认项的处置

- **Panda 夹爪：**保留 closure coordinate 与共轭力为 source-bound 设计建议；不是所有夹爪强制单标量，也不预定 Scene 版本/力分配。4a 必须验证具体映射，4b 统一 effort 门不能由 position compatibility 替代。数学修正不改变用户确认的物理 effort 方向。
- **Reset：**静态 preflight 无副作用、first effect 后失败保留事实并 fault 的方向进入 3c；不要求通用原子 rollback。这是已确定生命周期的具体化。
- **Isaac F06：**保留已接收 position/mimic 有界事实；缺 direct effort 仍是后续实现缺口。不能以 required effort 的拒绝结果替代本版最终三路线 effort 目标。
- **Scene/Execution：**同一 owner 版本化扩展仍为推荐；字段/codec 最小方案在 1d 联合审阅并在 3a/3b 包明确，旧 decoder/hash 保持。无需现在批准文档中建议的版本号。
- **MuJoCo 依赖：**归现有环境/依赖 owner，3a 必须解决准入 readiness，受影响的提前 native 执行也须先确认环境；目前不擅选隔离方案、降级或修改 pin。声明不相交不抹去旧环境的有界运行事实。

上述不产生新的本轮产品阻塞；维护者仍须审阅最终五份协议，G01 未整体冻结。

## 资料与验证

CodeGraph 先定位 RuntimeSession/native IO/feedback/Isaac App owner；索引提示 control.py 漂移时才定向读 on-disk。源码 `_require_reset`、`feedback_value`、NativeControlFeedbackSampleV1、IsaacSimAppOwnerV1 支持以上边界。

[MuJoCo actuation/transmission](https://mujoco.readthedocs.io/en/stable/computation/index.html#actuation-model)支持区分 ctrl、actuator force 与 transmission；[Isaac Sim 6.2 Newton](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/physics/newton_physics.html)支持 host/engine/solver 层级；[Genesis v1.4.5 coupling](https://genesis-world.readthedocs.io/en/v1.4.5/user_guide/theory/coupling/index.html)支持场景内 solver 与 coupler 分工。2026-11-03 查阅，均非本机或 GeoChora runtime 证明。

修正后文档治理 current、JSON/案例上下文/时间与力映射一致性、7 阶段/22 子阶段 DAG、5 份 draft、13 implementation targets/9 final cells 未启动、diff 空白与保护 hash 复核。既有 96 条历史链接问题单列；未运行 implementation tests/native。具体校验结果随主审交接报告记录。

## 后继

只准备 `V211_G01_1d_attempt001`：Core↔renderer 双向值、三类渲染目标、相机、physics/render/App 共享 ownership、reset/step/terminal frame 与数据时序、能力与拒绝、完整三方协议追踪和联合审阅。由维护者手动转发；1d 保持 PLANNED、attempt 0，其余实现阶段也不启动。

原始 [1c 报告](../../../../../../workspace/maintenance/v211_g01_1c_attempt001/report.md)与[设计摘要](20261103_1c_physics_protocol_design.md)保留。
