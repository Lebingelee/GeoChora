# G05 5c attempt003 — Sol 独立主审

日期：2026-11-08。结论：`NOT_ACCEPTED_ISAAC_USD_TASK_RGB_REGRESSION`。第三次普通 attempt 已执行，5c 尚未整体接收；按 goal-orchestration，停止普通派包，后续由维护者主导人工诊断，不自动创建第四次、改名续包或执行对话。已接收的 5b 不重开，维护者对 5b Isaac 场景可辨的人工接收不变。

## 阻碍：Isaac 已受本次公共代码影响

实际受测的 001 路线是 `pickcube-isaac-physical-candidate-v1`，`task_renderer='isaacsim'`，其 `build_isaac_reference` 产生 `UsdRuntimeSourceV1`。003 在 `SelectedReferenceEnv._prepare_reference_reset` 的 `materialize_runtime` 内，凡启用 task RGB 均先调用新增的 `_prepare_task_rgb_state_binding()`；该方法无条件调用 `DynamicCameraRenderSourceV2.from_runtime_source`，后者只接受 `RuntimeSource`，而 `UsdRuntimeSourceV1` 不是其子类。即使前面的绑定映射全部成功，也必然在该类型检查处抛出 `TypeError: dynamic render source requires RuntimeSource`。因此 001 真机结果不能直接作为 003 代码下该路线通过的证据。这是 reset 路径的产品回归，不是认为历史 001 帧或 5b 证据无效。

Sol 在禁止 provider/SDK 导入及 XML/MJCF/USD/URDF 文件读取的守卫下，用 `UsdRuntimeSourceV1` 的合成实例隔离调用**真实** `_prepare_task_rgb_state_binding`，只将前置 joint/frame 映射替换成空映射，复现上述类型错误；该反例证明类型边界，不冒充 Isaac Env、真实 USD 构造或 native 运行。脚本、日志保存在 ignored `workspace/reviews/V211_G05_5c_attempt003_sol_review/guarded_usd_source_boundary.py` 与 `.log`。静态生产调用链和 001 真实入口共同确定适用性。`make_env` 过程可能已打开 Isaac App；这里的结论是 task RGB reset 在 session materialization 处不能继续，不能说整个 App 从未启动。

建议维护者主导诊断时沿最早边界处理：公共 state/source provenance 与 renderer-only MuJoCo 所需 MJCF 映射应按实际 source 和 renderer 能力分别构建，避免让借用 Isaac 自有 task camera 的路径强制通过 MuJoCo renderer-only source 适配；同时保持 Isaac 的 USD source 身份验证和边界检查，不能简单跳过所有 provenance 验证。先用不导入 SDK/不读任务 source 的类型/生命周期合同检查覆盖 MJCF 与 USD 分支，再按代码实际影响，对原有 Isaac PickCube 路线最小 reset/step/任务 RGB 及资源释放做有授权的真实复验。修复方案需由诊断确认，不预设唯一实现，不要求重做历史全部矩阵。

## 003 已形成的可复用证据

- 非 Position selected：公开 `make_env`、真实 SelectedReferenceEnv reset/step/reset 及 observation 路径用**受控 Runtime、合成 canonical source、测试 receipt 和替身相机**检查；两状态及跨 episode 和外来 publication 拒绝有合同证据。它解决原先的 typed_state 缺失接线问题的受控案例，但不构成真实非 Position native 的通过；Marker 仍在原有 source-closure 预检阻断，不能将其当成 native 的失败或通过。工作包明确不把额外真实非 Position native 单独设为绝对门。
- 组件 GeoPhys：真实 Pendulum CPU × rasterizer 的 reset/固定动作 step/reset 原始 observation、camera readback 与 boundary 保留。受测 world camera 96×72，FOV 1.2 rad、near 0.05 m、far 5 m；报告读回分别约 68.754936°、0.050000000745 m、5 m。Sol 对保存的 projection 两组数据独立求差，最大约 3.89×10⁻⁶ 像素，小于预设 0.002 像素；错误 60° 的横向差约 2.92 像素。该几何对照针对计算出的指定点，不能单独证明像素中某实体身份或普遍视觉一致性；depth、多相机及真实动态挂载未实测。守卫下独立运行 5 项相机纯合同测试通过，包括错误 FOV/near 拒绝及 body pose 替身更新；非 native 验证不替代真实读回。
- PickCube 当前代码下，实施报告提供 MuJoCo CPU × MuJoCo、GeoPhys CPU × rasterizer、GeoPhys CPU × MuJoCo renderer-only 三条实际路线的 reset/step/RGB；范围以 route-matrix 为准，不将 001 的 13 个边界声称为 003 重跑。新提交未来有修复时按实际影响决定是否需要再测。Isaac 001 有界历史结果可保存，但不能证明当前受影响接线可运行。
- Pendulum／双轮车 Agent＋Controller 统一迁移经评估延期，现有任务主体和直接力矩语义保留；不单独作为本包未接收理由。任务 RGB 保持固定 renderer 的用户修订范围；同一 Env 运行时切换 renderer 仍延期。

## 身份、核验与执行偏差

审阅 Core `9e6f2b0f9a42d70aa1add5382c30a42ea7a92425`、GeoPhys `c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7`；gitlink 与实际子模块一致，Menagerie pin 未变；当前 tracked 工作树干净，仅原有三个 protected 未跟踪文件。Sol 独立复核 output manifest **892/892** 项大小及 SHA-256（包括链接字面目标），manifest SHA-256 为 `f896c6f74cf31b248f37087112ee8ee71f62c607777220d3ff17cc4b7b048083`；输入快照中的三个 protected 文件和 001/002 交付证据共 14 项哈希一致。受影响 Core diff 无 workspace/temp_output(s) 跟踪文件，`git diff --check` 通过。实施者报告的 21 项 Core、1 项 GeoPhys 测试和文档检查是执行者结果，不是 Sol 的 native 复跑。

本次另有 25 个 Pendulum 子步在执行后才补记预约，违反 003 要求；计入报告 90 子步总数，但不能倒称为事前合规。保留异常和日志；既往用户对 001 的处置不能自动证明本次流程合规，此偏差不单独否定其他可追溯路线证据，也不是此次技术拒收的原因。释放收据记录双锁反序释放、worker 退出；Sol 检查时未见本包相关活动进程。Sol 未启动 SDK、native、source 解析、GPU 或 GUI，也未执行 merge/push/tag/发布。
