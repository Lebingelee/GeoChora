# G05 / 5b 诊断 attempt002：Sol 独立主审

## 决定

`DIAGNOSIS_PARTIAL_REWORK_REQUIRED`；**5b 尚未接收**。保留 R1 的可恢复 observer fault 公开 reset 有界进展、MuJoCo/GeoPhys 实际关窗复验和旧 receipt 失效证据。普通 count=3，诊断 count=2；不将本次写成普通 004 或重置计数。5a 有界接收不重开；5c 和后续阶段未开始。

但本次返包对 Isaac 关窗的下一步判断需要修正：**当前 selected Isaac 生产路线是 headless App + GeoChora 所有窗口，而不是旧 Isaac 原生 viewport。** 诊断 001 已在 `0cfb43ef` 下真实执行 GeoChora 窗口关闭、同边界继续采集及后续一步对照；002 未修改 `task_env/runtime/sessions/isaac_native_io.py` 或 `task_env/render/providers/single.py`，`_configure_selected_observer` 继续未设置 native `frame_presenter`。002 虽改变通用 Env reset 与 fault 后报错消息，但正常情况下的选定 capture/present/close 链路未被替换，既有 D2/D3 可按输入及本次差异保留为有界证据。它们是 001 时点真实运行，不能冒称 35be7af4 下原生重跑。旧 headed viewport 关窗使 App 失效是旧路线历史事实，不应在当前 headless 路线自动变成必须重测的验收门；真正 App 故障的 typed latch 仍只有注入/纯测试证据，不能宣称 native crash 已验证。

## 交付、独立检查和 R1

输入 `e15ec081a6094787f1e146ff9c0ab5ea5631d4ce`；唯一输出 `35be7af495c21925ad7a97595fd4fec9c6db36d7` 为其直接子提交，只改五个 Core Env/测试/合同文件。GeoPhys `a6bf45b3422e31dfc632a58948e57fa4b686f1b0`、Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` 和三保护文件 unchanged。前包记录双锁逆序释放和资源关闭；这是 release 时点证据，后续执行仍须重新核查。

Sol 逐个重算 manifest **858/858** 文件的大小和 SHA，218,861,349 bytes，目录未列出和多列文件均为 0；manifest SHA `337e5acae736e22ae88a023d8fd8c52b4449db469d22f4a6d66dd52bd9dbeb8d`。`git diff --check` 通过。执行者的最终提交定向检查为 26 passed；Sol 在阻止 SDK/provider import 和场景 XML/USD 读取的 guard 下独立复跑其 observer test 文件，**24 passed**，没有重跑另两项会进入 source 的测试或 native。

`reset` 和 `reset_for_solution` 不再统一拒绝已有 fault；`EpisodeExecutionState` 在新 reset publication 完成前保持 fault，正常 step/render 继续拒绝。执行者的真实 MuJoCo 生产 Env 验证了 capture 故障注入后两个公开入口均可 rebuild、发布新 episode 并再次 RGB；其 worker 在最终 commit 前运行，记录 WIP 文件身份与后续未再改源码的说明，提交后 26 项为纯测试，不把它表述为最终 commit 后的新 native 运行。接受该组 **可恢复 observer fault 的有界修复证据**，不外推真实 Isaac App 崩溃恢复或所有 fault 均可恢复；失败 rebuild 的清理次错和 prior fault 保留按实际测试范围成立。

## RGB 与相机：分清证据不足和 5c 实现

旧 D1 固定规则在 C 视角 `0.0728297 < 0.1` 的失败必须保留；这是旧规则未过，不自动证明产品缺陷。002 的像素/投影再分析合理保留为 `INCONCLUSIVE`，未提供冻结新 oracle 的独立 holdout，因此尚不能据此单独关闭图像证明。

Sol 增加两项只读前置工作，结果和脚本位于 `workspace/reviews/V211_G05_5b_diagnostic_attempt002_sol_review/`：

1. 对 001 的提交后 D2 窗口原生帧，使用真实 source state/camera 将旧 D1 中心环规则事后复算：A 为 `0.1031042039`，B 为 `0.0475658774`。这只是**探索性**复算，不能当独立新盲测，也不能证明 B 图像错误或据此放宽阈值。更关键：D1 的 headless A `.npy` 与 001 最终提交后的 D2 human A `.npy` 完整 SHA 完全一致 `0930bd8c5b914e3eccc16d109c0b72dff2c4e0a9356fb83f44c1fa8b2bdb8b6c`。这可桥接同一数据的图像内容及所测窗口，但 human 和 rgb_array 是不同生产入口，仍不能冒称最终代码下 D1 全流程已重跑。
2. 在禁 SDK/场景读取 guard 下，用真实 `SelectedReferenceEnv.set_observer_camera`、真实两项 `CameraObservationConfigV1`/camera geometry 和合成 Env 验证：observer identity 改变、两个 task geometry identity 不变，且触发旧帧 invalidation。它是 **provider-free API 逻辑证明**，不是已配置生产 Env 的 task camera 或真实采集证明。旧 `isaac-mount03` 同一 native scene 的诊断 sidecar 相机在观察视角切换前后 calibration/config 不变，为互补的有界 native 事实；sidecar 不是 5c task observation。

代码原因已具体定位：`task_env/tasks/pick_cube/physical_isaac_candidate.py` 的 public factory 仅消费 `observer_camera`，其余 kwargs 被拒；没有把 task-camera config 传入 candidate。现有 `CameraObservationConfigV1` 绑定早期 R04a 的两路 321×241 RGB、depth 和 Entity mask，不能在 5b 通过“先配置生产 task camera”悄然强制完整自动 observation/depth/segmentation。5b 原合同的 observer/task camera 分离仍有效，现有真实 task-camera 对照未闭合；应先明确可在 5b 单独表达/绑定 task camera geometry 且不触发 5c 消费链的最小路线，或由维护者明确采纳分层证据并把具体生产 task-camera 集成留给 5c。不能以 null 配置或纯 fake 宣称实际 task 相机已接收，也不应以不存在的自动 task-camera consumer 把整个 5c 提前。

002 对 MuJoCo 与 GeoPhys 的真实 WM_DELETE、同次窗口/RGB 一致、关闭后 capture-only 和时钟不变提供新有界证据；对应 worker 的脚本/数据目录与 `r3_*_window_close_*` runner 目录名称不同，应按记录关联，不能把两者误当缺失证据。既有 `isaac-mount03` 真实 step 0→7 后调用 `render_receipt()` 拒绝旧 boundary 可作按原身份的有限旧 receipt 证据；当前 `render()` 没有旧 snapshot 参数，无须为完成 5b 新增旧状态请求公共 API。并不证明任意旧 RGB/frame 在所有路径均被拒。

## 剩余工作和交接

关键剩余是：在不新增 5c 全链的前提下，落实 5b 的已配置 task-camera 分离证据及真实图像可辨判据；按实际改动复用已验的三路线 window/close/clip，针对确受影响路径补检查。保留原 C 失败、探索性选择偏差、受限 RGB 色彩、旧 SIGKILL 和 bootstrap unknown；不反复追旧 native viewport、不可补历史、所有 seed/色域或 5c 终验。后续具体实现/预算仍按维护者手动指定；本次未创建新执行包或联系其他对话。
