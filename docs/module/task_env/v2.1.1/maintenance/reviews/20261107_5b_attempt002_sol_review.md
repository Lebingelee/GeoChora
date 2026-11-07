# G05 5b attempt002：Sol 独立主审

## 决定

`REWORK_REQUIRED_5B`，普通 attempt count=2。原 5b 要求三条首批路线各自具备真实窗口和离屏 RGB；GeoPhys 尚无闭合路线，MuJoCo 和 Isaac 的图像与颜色证明仍有下述有界限制，因此不接收整个 5b。5a 的既有有界接收不重开，5c 保持 PLANNED。此次主审保留 002 的进展和失败，不将未运行的 5c 同步 observation、renderer 切换或 cross 提前作为 5b 门禁。

## 身份和独立核验

- `codex/v211-stage5` 输入 `344f6099a7a70581ea4d21393b5e7d9366d4000a` 到输出 `1bbcf68a0854a982753e891eafe923e8d1476f5f` 为直接父子。两 pin、三个保护文件摘要与 002 输入一致；GeoPhys checkout 和受控路径未见新修改。维护者转交了最终报告和释放收据；只读时点检查未发现本包相关 runner 或共享锁持有者，时点检查本身不代替释放收据。
- 对 ignored `workspace/maintenance/v211_g05_5b_attempt002/output-manifest.json` 的 **1378/1378** 项独立重算大小和 SHA，全部一致，共 609826523 bytes；manifest SHA `61958f599386d0a1029f83abde16c973f598985cf1d8b79801c022174c141609`。包输入 manifest SHA `4f5a8a8b9dba15fb1e5cf249f91804619692068d41088d837bec2f04943d4350`。
- Sol 在 SDK/XML 守卫下独立复跑 observer、binding、fault 测试 **30 passed**；`git diff --check` 通过。这些纯测试不能证明真实渲染。Sol 未解析 source，也未运行 native、SDK、GPU 或 GUI。执行者另报的八项 legacy 和 15 项 fake-SDK 检查按其原日志与范围保留。
- 每个运行的 code.diff 是证据身份的一部分。Isaac `isaac-segmentation02`、`isaac-window04`、`isaac-window-state01`、`isaac-window-close05` 和 `isaac-lifetime03` 的生产/相关测试 diff SHA 为 `a42f9a69ab2bf2c7ad6e1dca18b56eb6eb9439f7f373e004327f29c7d54579d2`，与最终对应路径差异匹配。MuJoCo `mujoco-capture03` 早于后续 Isaac 改动；对照记录的差异后，仅在未受后续变更影响的具体 MuJoCo 路径上复用，不能改写为最终代码的完整重跑。
- 收据记载 source/native 分别保守记账 2725.72 秒、54 worker；RSS/GPU 为离散采样，GPU 是全卡观测而非进程归因。物理子步**没有重建累计精确值或可核验累计上界**，故不能独立确认该项预算合规；这不是超限的证明。下一窗口须从启动前建立包括失败/中断上界的累计计数。`isaac-lifetime02` 的模块路径遗漏和随后清理 SIGSEGV（退出 -11）保留；它未产生 close receipt，不能由后续成功退出抹去或扩大为正常解释器清理的保证。

## 按路线判断

1. **MuJoCo：窗口 PARTIAL，离屏 RGB PARTIAL。** `mujoco-window01` 是真实窗口、四次 present 及同运行窗口像素和原始帧一致；WM close 另有运行。`mujoco-capture03` 与 `mujoco-segmentation01` 的 RGB 逐字节关联，source 具名几何、独立投影及负例对识别真实场景提供强有界证据；但特征选择受先前预检影响，原冻结独立 oracle 未完全满足。near/far 诊断有界通过。七级 emission 数值和真实 GL attachment 检查支持受控条件的线性 framebuffer channel transfer；它们不独立建立所有纹理/着色输入的完整颜色语义。合同需要明确 sRGB/linear，不能仅凭 attachment 状态将完整输入至输出链条视为已证实，也不额外要求 ICC 校准。
2. **GeoPhys：窗口及 RGB BLOCKED。** 固定 pin 的 raytracer 描述符 far 和 near 改变在所测路径均未改变帧；rasterizer 描述符 far 改变未改变帧，而公开 near setter 有可观测效果。测试证实这些实际组合存在缺口，不证明所有公开组合均不可行。旧 `native07` 缺材质/光源，不能作完成的生产路线。两种 renderer 都已调查，但原 5b 只要求一条明确命名的 GeoPhys 路线。诊断及拟议 provider 公共接口在 `geophys-public-gap.md`；provider、gitlink 均未授权变更。
3. **Isaac 6.2：窗口 PARTIAL，离屏 RGB PARTIAL。** `isaac-publish03` 的 12 个具名刚体公开渲染侧 pose 与已发布状态位置最大误差 0、四元数误差约 `1.91e-7`，有界修复了此前约 0.1604 m 的已观测偏差。真实窗口/离屏、挂载、裁剪、终止和最终 constrained worker exit 0 分别有记录；图像选择经探索、诊断 AOV 与真实 RGB 的关联以及最终运行身份应按各运行实际范围解释，不能把单一旧运行当最终代码全场景证明。RTX 输出设置已记录但 sRGB/linear 的端到端语义未定。窗口关闭后进程生命周期的可推论范围以具体 close receipt 为限。

Isaac 发布实现将 physics tensor 的当前 pose 写入 USDRT/Fabric；[Isaac Sim 6.2 官方可见性表](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/py/docs/overview/experimental.html)说明 USDRT/Fabric 的写入可能在下一 physics update 由 tensor 后端处理。`isaac-transition01` 的一个 5-substep 对照未观察到差异，但不能排除更广泛的动力学影响；这是有依据的**待验证风险，不是已证实缺陷**。重复 render 不推进 physics 的原 5b 约束仍适用；后续以小范围受控运动/接触验证解决风险，不提前变成 5c 全矩阵。

## 后续

已完成[第三次前重评](../../planning/stage5-5b-attempt003-reassessment.md)。有可讨论的 GeoPhys 修复方向，但尚无已授权的完整解决路径；不启动 attempt003，不以重命名清零。等待维护者决定是否授权所提 GeoPhys public API、对应 provider 本地提交及 Core gitlink 等具体范围，并在此后冻结完整包和预算、由维护者手动转发。若第三次仍未接收，则按 Skill 停止普通派包并由维护者主导诊断。无自动进入 5c/阶段6、push、merge、tag 或发布。
