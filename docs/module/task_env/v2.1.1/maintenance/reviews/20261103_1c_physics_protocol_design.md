# G01/1c physics 双向协议设计摘要

状态：`REPORTED_PENDING_REVIEW`；结果 PASS 仅表示本包设计交付与静态文档检查完整。本记录不是协议接收、冻结、runtime qualification 或实现授权。

## 输入与输出

- 包：`V211_G01_1c_attempt001`；完整报告：[raw report](../../../../../../workspace/maintenance/v211_g01_1c_attempt001/report.md)。
- Core 输入：`develop@b0024c71614f2d2ede8d9eb1db594cfcde3e9278`；GeoPhys pin/检出：`67da1165149486d3ae3e779c13ce31af49e17d50`。
- Output commit/HEAD、manifest hash、保护项和验证结果见 raw report；[orchestration](../orchestration.json)记录 1c 的 pending-review 状态。
- 只改本包 allowlist 内的协议、规划案例、source map、Goal、recovery、orchestration 与本摘要。production code、tests、dependencies、provider、matrix、unified representation 和 render-provider 未改。
- native/App/solver/physics/GPU 与 implementation tests 均为 0；无 subagent。执行后写入窗口已释放。

## 协议结论

1. 将 query、build、reset、command、advance、state publication、close 写为 Core→adapter 的输入/输出/副作用/失败契约；能力分列 provider API、adapter、dependency 和 exact evidence，并标 query/build/runtime 阶段。
2. 对现有 admission/materialize 缺少 general capability query 和统一 build receipt 提出同一 owner 内的 additive value；复用 source/execution/state/clock identity，不新增平行 manager。
3. Panda effort 主路线建议七个具名 arm generalized torques（N·m）加 source-bound gripper closure coordinate/effort（m/N）和 compiled transmission/功率映射；当前位置/mimic 与 mixed arm-effort/finger-position 是显式 compatibility，不算 effort 完成。缺 mapping、required feedback 或 coupler 的路线应拒绝。
4. R3 source kinematics 输出 q_ref；LIBERO source-bound MuJoCo model 计算 FK/J/M/bias 而不执行 physics step，但仍属 benchmark owner/依赖。ACK、估算与实测分开。
5. pure preflight reject 保持 session；first effect 后 partial failure fault、保留事实、不承诺 rollback；async route 需 completion ticket/fence，当前 RuntimeSession 同步；borrowed view 对 next mutation/step/reset/close 失效。
6. MuJoCo CPU、GeoPhys CPU、Isaac Sim 6.2.0.0/PhysX/CUDA 的精确 profile mapping 与缺口见权威 [physics-provider](../../contracts/physics-provider.md)。Isaac F06 position/mimic 不满足 direct effort；当前无通用 Isaac batch。Renderer共享接口留 1d。

## 审阅入口

建议按顺序审阅 [physics-provider](../../contracts/physics-provider.md)、[control-and-feedback](../../contracts/control-and-feedback.md)、[lifecycle-and-data](../../contracts/lifecycle-and-data.md)、[planning cases](../../planning/physics-provider-cases.json)、[source map](../../planning/source-map-and-references.md)。案例 P1–P4/N1–N6 仅用于静态设计示例与结构上下文核对，不是 validator 或运行证据。1d仍为 `PLANNED`；当前所有五份协议仍 `DRAFT_FOR_DISCUSSION`。
