# G05 5b attempt003：Sol 最终独立主审

## 决定

`NOT_ACCEPTED_5B_HUMAN_DIAGNOSIS_REQUIRED`，普通 attempt count=3。三条指定路线均取得有界真实窗口与离屏 RGB 证据，但 Isaac 原生窗口关闭会使 App/physics 运行态失效，当前 selected Env 未将该事件发布为合同要求的 typed route fault，也未锁存 Env 执行故障；其关闭／故障边界不满足原 5b 出口。上述不是以 5c 同步 observation、跨 renderer 切换或跨组合提前加门。5a 原有界接收不重开；5c 继续 PLANNED。

## 直接阻塞：Isaac 窗口关闭后的路由故障

- 实际 `isaac_window_close_final01` 通过 WM_DELETE 关闭窗口后，native physics counter 从 `(18, 0.036)` 重置为 `(0, 0.0)`。后续 render 抛普通 `RuntimeError`，旧 receipt 被拒，snapshot 被拒，reset 提示需要新 worker；该运行的 App close receipt 完成。它证明了这些具体保护，而非 physics/episode 可继续。早一次 `isaac_window_close01` 亦提供相应范围的关闭证据。
- [render 合同](../../contracts/render-provider.md)“用户关闭窗口/display lost”明确要求：若 App/window 生命周期无法分离，以 typed route fault 明确通知；[生命周期合同](../../contracts/lifecycle-and-data.md)要求在 admission 标记该限制并在 fault receipt 通知 Core。当前 `task_env/render/base/contracts.py::ObserverRenderRequestV1` 只校验 camera/mode/provider/backend，没有该生命周期限制；当前 API 文档也没有对该 Isaac 窗口行为作明确声明。`task_env/runtime/sessions/isaac_native_io.py::_check_observer_clock` 将 native/App owner 置失效并抛 `RuntimeError`；`UsdCoreRuntimeSession` 使 observer 失效后重抛；`task_env/environment/reference_env.py::render` 直接返回 provider 调用，未形成或锁存 `ExecutionFaultV1`。现有同次 native close probe 不读取 `env.execution_fault`，因此不能声称其已验证 typed fault。
- Sol 在禁止 SDK/source import 的 guard 下用真实 `SelectedReferenceEnv.render` 和注入相同错误的纯 provider 定向检查：异常为 `RuntimeError`、无 `execution_fault` 附件，`env.execution_fault` 仍为 `None`。这是对 Env 错误传播分支的离线验证，**不是**重新运行 native window，也不能单凭此推定后续 step 已实际推进或改写物理。代码中 selected step 的故障前置检查依赖 `_execution_fault`，因而不能将底层 App 失效等同于 Env 已显式进入 typed fault。需要维护者主导的诊断确认最小修复：要么让窗口与 App 生命周期实际分离，要么对已确认不可分离的路线在 admission 宣告限制、在实际失败时以项目既有 fault/receipt owner 类型化并使 Env 不再把该 episode 当正常可执行；保留主错和清理次错，并验证真实窗口关闭及故障前后行为。

## 其他证据与具体范围

- Final Core `codex/v211-stage5@2b8f82b719880f9eb65cb332b30363c64b034deb` 是 `30a19011885be4e68b179601be2bc4edce02fd2f` 直接子提交；GeoPhys `a6bf45b3422e31dfc632a58948e57fa4b686f1b0`、Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` 和三保护输入保持。002、003 和 CPU followup 的历史决定与 release 均保留；当时已核对 003 原包 8/8、CPU followup 2974/2974 输出摘要。
- 本次续作 output manifest **345/345** 大小及 SHA 独立重算匹配，共 146525919 bytes，manifest SHA `d15938e41b9e42135c6e87ca5446236879089d2f20eaef8c9f601867fcd0cf12`。`isaac_rgb_final03` 和 `isaac_window_final02` 的 core.diff 与最终提交完整二进制 diff SHA `6a9afdacc04b8eb38fb8b429763de73fe218fced43294dfeb12444234dacd01d` 相同。Sol 在 SDK/source import 守卫下独立复跑 **38 passed**，`git diff --check` 通过；未运行 source 解析、SDK、native、GPU 或 GUI。前包 writer/锁 release 已返，时点检查无相关持锁者；时点检查不取代 release。
- Isaac 两个真实视角 source cube 投影/强度在各自 raw 中可复算；Sol 独立按保存的相机矩阵重算 cube 中心／ring contrast 为 `0.19256`、`0.19469`。真实窗口与同次 native RGB 相关分别为 `0.997996`、`0.998057`，window oracle 经探索，不能当盲测或证明完整场景。两个运行均为公开 Env 与真实 source、帧、identity 和受限 App 生命周期；no-step 守卫期间 counter 维持 `(18, 0.036)`。
- **纠正返包的负例计数：**`isaac_rgb_final03/read_landmark.py` 将 `stale_frame` 与 `swapped_view` 都设为 `images[1-i]`，两者是相同变异，不是两个独立检测；这两个视角的图像也是同一 state boundary 的不同相机，不是真实旧物理状态。其余 black、mirror、swapped 和 wrong-state 均按原脚本结果保留。002 `isaac-window-state01` 的同运行 step 0/7 状态与 raw/window 可作为跨状态变化的旧代码证据，且后续 003 针对 Isaac 的关键修改是 capture 的颜色准入；不把旧运行改写为最终代码下独立 stale-frame 负例，也不宣称完整状态同步证据。后续按实际修改影响选择核验，不重跑历史矩阵。
- `isaac_color03` 的 6 级相同 product gamma on/off 差分，Sol 离线复算 OETF 最大差 `0.0034991125`、on/off 最大差 `0.2657952`。支持所测 RTX tone mapping 后的窄 sRGB 传递声明，不证明线性场景辐射、原色或源素材色域。最终代码对指定 RTX/OCIO 设置和文件 SHA 在 capture 前后检查，真实 `isaac_color_reject01` 的范围保留；不可推广到任意设置或 Isaac 版本。单个有／无 observer 同初态同动作对照的 public joint/frame 前后数值相同；Sol 独立对比 raw 得到完全相同，仅证明一个 5-substep 区间，不能证明所有接触状态。
- MuJoCo 和 GeoPhys CPU 的窗口、RGB、裁剪和来源灯光证据按[资源边界中间主审](20261107_5b_attempt003_resource_review.md)实际运行范围复用；本续作四个变更文件主要是 Isaac 色彩检查、对应测试/说明及 shared provider receipt 的 Isaac 字符串，不改变所引用的 MuJoCo/GeoPhys renderer 核心路径。两条路线的特征选择亦带探索偏差、源素材和原色未全面校准；仅保留原子能力，不宣称其他 scene/backend/representation 通过。
- 隐式 SDK bootstrap 步数 unknown 是维护者授权的资源口径修订，不能据此主张总物理步≤10000。续作自报显式累计预约 256、观察新增 20 步，内存/GPU 为所述 systemd 与采样范围；前次 10 个零步诊断漏事先预约及 RSS 硬峰值未证明，不补造成合规。`isaac_rgb01` close 期间 SIGKILL（-9）原因未明、无 close receipt；后续成功清理不能抹去失败，也不能宣称通用解释器退出已解决。`isaac_window01` 含被遮挡的无关桌面内容，原始文件按原隐私限制保留，不复制传播。

## 后续

第三次普通尝试仍未接收。依用户指示及 `.agents/skills/geochora/references/goal-orchestration.md` 的 post-limit 规则，停止普通派包；维护者主导人工诊断并决定明确后续范围和资源。不能自动 004、改名清零、启动 5c/阶段6、创建／联系对话或 push/merge/tag/发布。所有路线先前真实进展与可复用证据保留。
