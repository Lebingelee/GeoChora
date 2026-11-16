# G01/1a attempt001：Sol 独立审核

日期：2026-11-03。结论：`ACCEPTED_BOUNDED_1A_AUDIT`。只接收 1a 的源码／caller／范围核实及文档交付，不批准五份协议定稿，不授予 native、Solution、renderer、batch 或 Qualification。

## 输入与独立核对

- 冻结包：`V211_G01_1a_attempt001`，manifest SHA-256 `c254b8b0252e26d79075da203c8dc728a0c4cea755051cd251584be2809a4ab8`。
- 执行 input：Core `ba874c2d57dc9cd5e3cb710d87d3405808393967`；执行 output／commit：`eb64b89f1dbceb6c7dbd10bef400846f8ab91ec9`，两者为直接父子。
- GeoPhys gitlink／检出保持 `67da1165149486d3ae3e779c13ce31af49e17d50`。原始规划 baseline `fd03817c…` 不变。
- 独立重算输出 manifest SHA-256，与转述的 `425db5ac93f9c5864f37ef7d546a5343cbeed56a083ca1dda39088c4afb08896` 一致；其 9 个文件的大小和 SHA-256 全部一致，总计 221379 bytes。
- 实际 diff 只有 6 个允许文档；提交空白检查通过，tracked tree clean，两个保护输入字节／hash 保持。未修改生产代码、依赖、测试或 provider pin。
- 独立 JSON／默认顺序检查：22 项依赖一致，1a 报告待审，其他 21 项未启动；13 个目标与 9 个 seed cell 未升级运行能力。

审阅采用实际 diff、原始 findings／commands／报告和当前源码；未重复运行实现测试或 native。执行报告声明 native、physics、GPU、实现测试均为 0，报告的无后台 worker／窗口释放为本次交接事实；本审核没有把静态检查解释成原生验证。

## G0–G5 处置

| Gate | 主审结论 | 依据与范围 |
| --- | --- | --- |
| G0 | 接收 | 输入、提交关系、允许路径和保护文件核对一致 |
| G1 | 接收 | 已核对构造／source、动态 camera、merged batch／vector 及其公开接口边界；owner／caller 入口可复查 |
| G2 | 接收 | 三 physics 目标保持；明确现有 render／batch 缺口，没有以 CPU/CUDA 充当两个 provider |
| G3 | 接收 | 源参数和公开检查入口作为后续准入依据；未测容差保留，不要求本审计证明原生数值正确 |
| G4 | 接收 | 文档校验原报告 0 errors／96 历史问题，JSON 和变更范围一致；下述文字澄清随本审核落地 |
| G5 | 接收 | 报告、命令／发现、输出清单、单一本地文档提交及窗口释放声明完整；没有进入 1b |

未使用 subagent 不构成缺陷：包中允许使用而非强制使用，实际执行已如实报告。

## 接收并带入后续的事实

1. `DynamicCameraRenderSourceV1.from_runtime_source` 明确拒绝 `source.free_joints`；Panda-box declaration 确实将 cube 绑定为 free joint。因此现有 scalar-joint 动态 camera 路线不能直接证明 PickCube 可渲染。1b 需覆盖 free pose／标量 joint 语义及映射，1d/5a 决定和实施投影。
2. Core requirements 的 `mujoco>=3.8.1,<3.9.0` 与当前 GeoPhys 必需依赖 `mujoco>=3.15.0` 无交集。这证明声明无法在同一环境同时满足，不证明已有手工环境不能执行。1b 保留依赖／环境事实位置；1c/3a 再处理版本和隔离选择，本轮不改依赖。
3. 现有 merged native batch 是 GeoPhys；同 provider 的 CPU/CUDA 不满足至少两个 physics provider 目标。Isaac＋PhysX 是第二 provider 的建议，仍缺 TaskEnv batch adapter，交 6a–6c 实施。
4. merged batch 关闭 render source，remote get_images 重复返回一个 worker frame；终止观测采用 same-step 包装。1b 应允许 env／episode／表示映射身份，1d/6a 冻结具体数据布局和 auto-reset 契约。
5. 立方体声明惯量与均匀立方体解析值的差异只是模型意图待核实项。本次保留现有源值；不能自动“修正”质量或惯量。

## 审核澄清：证据 pin 与默认配置

原始完整报告 §3 的 GeoPhys physics 行把“historical F06 used older GeoPhys evidence”和“No current-pin run”并列，措辞过宽。实际 [v2.1.0 matrix](../../../v2.1.0/capabilities/capability-matrix.json) 的 `F06-GEOPHYS-CPU` 明确记录 provider `67da1165…`、Core `f5d36460…` 的短程运行／独立读回、task_success=false；该事实保持。**尚无本次新运行**与**历史没有当前 pin 运行**不能混淆。

较旧 pin 的限制只用于原报告指明的 D05b cross-render receipt；不能由当前 pin 的 state-only F06 反推当前 pin 的 cross-render 已验证。原始报告、findings 和 manifest 保持字节，本文是其审核解释，不重签原件。

源码映射中的 R3 描述同时澄清为默认选择；当前仍允许显式 R1，并非只能使用 R3。6000 是当前 YAML 的 horizon 默认，不是覆盖所有历史 Harness／Isaac 冻结运行的统一 horizon。

## 接收后状态与下一包

编排登记本次执行的真实 output HEAD／commit、审核结论和证据，其他子阶段仍 PLANNED。1b 可准备单独完整工作包：仅收敛四类统一表示、已有 schema／caller 映射、free／scalar／batch 正反例和兼容方案；具体 physics／render 操作和实现留后续。

1b 执行代理可提交建议协议草案，但产品语义和协议最终批准仍由维护者审阅；不得自动写 `FROZEN` 或继续 1c。新包仍由维护者手动转发，本次审核不自动派发。原始 [1a 报告](../../../../../../workspace/maintenance/v211_g01_1a_attempt001/report.md)和[执行摘要](20261103_1a_scope_audit.md)保留。
