# G05 5c 人工诊断：现状、剩余事项与阻碍

2026-11-08。维护者指定进入人工诊断；此文件只记录 Sol 的只读分析，不授权新的 native/source/SDK/GPU/GUI 执行或自动派包。完整审阅以 [001](../maintenance/reviews/20261108_5c_attempt001_sol_review.md)、[002](../maintenance/reviews/20261108_5c_attempt002_sol_review.md)、[003](../maintenance/reviews/20261108_5c_attempt003_sol_review.md) 为准。

## 目标基准

以 [G05 5c 目标](../goals/05-rendering.md#5c)、[renderer 合同](../contracts/render-provider.md)、[生命周期合同](../contracts/lifecycle-and-data.md)和[维护者修订范围](stage5-5c-fixed-renderer-scope.md)为准。创建 Env 时选择并固定 renderer 至 close；每个成功 reset/step 自动返回与已发布状态同边界的任务 RGB；一个真实 physics × 不同 renderer 跨组合；公开接线使用通用 scene/source、具名状态及相机声明。PickCube 是必需的真实验证任务；不要求运行所有其他任务或全组合矩阵。

同一 Env 的 renderer A→B→A 已明确延后；已有 backend/Controller reset 能力不因这一调整取消，不兼容固定 renderer 的 reset 必须明确拒绝。5b 的三路线窗口／离屏历史有界接收与维护者对 Isaac 场景可辨的人工接收不重开。

## 当前可复用结果

| 目标 | 当前证据 | 解释边界 |
|---|---|---|
| 构建时选择固定 renderer | selected PickCube 的 MuJoCo、GeoPhys reset/step/reset 当前代码记录与历史固定 renderer/拒绝检查；Pendulum 组件路线在 reset/step/reset 保持所选 renderer | 按受测路线接收进展；不意味着任意 backend/reset 配置或所有 renderer 已实测 |
| 同步任务 RGB | 001 四条 PickCube 路线各有 reset 加 12 步真实帧、状态与 clock；003 当前代码有 MuJoCo、GeoPhys、跨组合各有 reset/step，Pendulum 另有 reset/step/reset | 001 是当时代码的真实运行，003 的更短运行不能扩称重跑 001 13 个边界；Isaac 当前存在回归，见下 |
| 无额外物理推进 | 001 保留各路线渲染／不渲染的同动作公开时钟/关节比较；跨组合有 MuJoCo `mj_step` guard；003 有受影响 CPU 短程证据 | 只覆盖记录内的物理边界；Isaac 在订阅前不可观测的启动阶段 implicit steps 仍 unknown |
| 真实跨组合 | GeoPhys CPU physics × MuJoCo renderer-only；001 独立比较 cube/link body-origin，003 当前代码有 reset/step 与相同边界/clock | 只承诺受测 source、场景、状态与组合；不是任意引擎自由组合，修复后的适用性按实际改动审查 |
| 组件光学接线 | 003 真实 Pendulum GeoPhys CPU × rasterizer 绑定、读回声明的 FOV/near/far/pose/extent，并取得状态、RGB 和同次投影检查；reset/step/reset | 一台 world-mounted camera；单点投影对照不证明普遍图像准确性。非 Position selected 的受控测试不等于真实 native 任务运行 |
| 状态、旧帧与失败 | selected consumer 区分 reset-initial/post-control、校验 boundary/clock、返回 owned RGB；001 有 reset、旧帧与一次 MuJoCo capture 故障处理证据；003 有 foreign-state 受控拒绝 | 按路径、输入及代码影响复用；不能将所有故障或所有组件推广为全覆盖 |
| 通用接线 | 003 非 Position selected 经过真实 public factory/生命周期入口，使用受控 Runtime、合成 source、测试 receipt 和替身相机完成 reset/step/reset；组件 Pendulum 真实接入 | 前者是生产编排合同证据，不是另一真实 selected native；后者是特定 GeoPhys 组件交集。不同声明/资产/renderer 的真实适用范围尚不能泛化 |

## 直接未闭合

1. **Isaac task RGB reset 回归：**001 的 Isaac PhysX/CUDA × RTX 真实结果存在，但 003 的公共 reset 无条件要求 `DynamicCameraRenderSourceV2` 处理 source。Isaac F06 使用 `UsdRuntimeSourceV1`，该适配器只接受 `RuntimeSource`。Sol 守卫式合成类型反例及真实调用链确认该类型边界；当前代码不能沿原 Isaac task RGB 路线抵达正常首帧。不是 SDK 性能问题，也不推翻 001 当时的图像及 5b 人工验收。先修复 source 类型／owner 分工与其通用约束，再在获授权窗口补当前代码的最小 Isaac reset/step/任务 RGB、时钟及资源关闭验证；不能只更改测试或复用旧身份。
2. **最终代码的通用性和旧证据适用性：**003 对非 Position selected 证明受控编排而未证明一个真实非 Position native；Marker 先在 source-closure preflight 拒绝。额外真实非 Position 任务不是 003 原工作包绝对门，但必须保留这一限制，并在修复 Isaac 时重新审查对 scene/source、物理发布、camera 等接线的影响。修复代码如触及 CPU/跨组合，补对应最小检查，不预先要求历史矩阵全重跑。
3. **剩余 5c 生命周期审查：**修复后重新核对固定 renderer 跨 reset、固定 observation 规格、旧帧失效、失败后的 fault/close、backend/Controller reset 的不兼容拒绝、采集不额外推进物理以及 state-only 兼容；沿已受测/未受影响的原始证据复用，不预设全需重新 native 执行。

## 开发中曾遇到的阻碍与处理

- 001：三原生和跨组合已取得真实帧，但公开接线依赖 Panda Position profile，GeoPhys 灯光假设过窄，通用任务目标未闭合。
- 002：入口不再要求 Position，但 non-Position reset 没建立 typed_state；组件相机只传 pose 未将 FOV/near/far 写入真实 renderer。Sol 独立发现并拒收。GeoPhys 对无灯/部分支持灯声明及 visual/default-only unsupported 的处理改进有界保留。
- 003：补了 typed state 的受控通用链和真实组件相机光学读回，却将只适用于 MJCF/renderer-only 的 `RuntimeSource` 条件强加到借用 Isaac 自有相机的 USD 路线，形成确定回归。第三次未接收，普通尝试停止。
- Marker 没有 source-bound receipt，先被合法 preflight 阻断；不绕过 provenance、不把该候选不可用扩展成所有非 Position 场景不可能。
- GeoPhys 的 authored lighting 仅支持已声明子集；visual/default-only 等不支持输入明确拒绝，`extension.light` 诊断保留，不宣称任意灯光源可完整转换。
- Pendulum/双轮车已有场景内主体和直接 torque adapter，现有 Panda Agent/Controller 源所有权与其不同；简单套用会有重复实体或改变动作语义风险。通用已编译主体 binding 与 controller 的设计/迁移延后，不是 5c 未接收的独立理由。双轮车尚未做本次真实 RGB 路线。
- Isaac 001 有启动、采集和关闭中的失败及复验记录；设备利用率和显存采样不能证明瞬时硬峰值，订阅前隐式步 unknown。不要把过去 5b 特定窗口的 VRAM 授权误写成当前通用硬限制。
- 001 的未事前预约/包外 pytest 输出、002 的 75 步未事前预约、003 的 25 步事后预约均有记录；001 的用户处置不自动消除 002/003 的事实。它们不是本次 Isaac 技术拒收的单独原因。原 ignored 证据保留，阶段 5 误跟踪证据的限定历史清理见 [收据](../maintenance/20261108_5c_history_cleanup.md)。

## 诊断原则

沿实际 USD source 拒绝这一最早边界厘清：哪些是任意 source 的状态/provenance 约束，哪些是仅 MuJoCo renderer-only 需要的绑定，哪些是借用 Isaac 原生相机的职责；不取消 USD source/identity 或状态时钟校验。先进行无 SDK、无 task source 解析的合同/调用链检查；随后由维护者明确后续执行范围和资源，必要时真实复验 Isaac 和受影响路线。普通 attempt 上限已经用完，人工诊断不能通过改名抹去记录；不自动进入阶段 6、merge、push、tag 或发布。
