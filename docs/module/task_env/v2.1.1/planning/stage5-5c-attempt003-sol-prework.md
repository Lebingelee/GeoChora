# G05 5c attempt003 — Sol 只读前置分析

状态：`PREWORK_ONLY_NOT_DISPATCHED`。普通 attempt 已完成 2 次；按[第三次前重评](stage5-5c-attempt003-reassessment.md)，下次是最后一次普通 attempt。本页是可供构建工作包的代码和证据索引，不构成实现、native、source 解析、SDK、GPU、GUI 或新资源授权。此前用户批准的固定 renderer、真实跨组合及不以 PickCube 特判的目标继续有效；不恢复同一 Env 运行中切换。

## 现状身份与历史

5c attempt002 原始实施 hash 和 release hash 保留在原始证据；分支历史经维护者指定范围清理，原始和新 hash 映射见[清理收据](../maintenance/20261108_5c_history_cleanup.md)。下一包应在实际创建时重新检查 writer、双锁、保护文件、分支、Core HEAD、GeoPhys/Menagerie pins、前包 release 与输出目录，再冻结当时真实输入，不直接复用旧 package snapshot。

## 一：非 Position selected 的最早真实失败链

- 公开 `make_env` → selected binding 的工厂入口已移除 `position_profile` 检查；`_prepare_reference_reset` 的 `read_state` 只在 Position 分支调用 `session.snapshot_v1` 产生 `self.typed_state`，随后 `observation()` 各 RGB 组合都要求 `self.typed_state.view`。普通非 Position 控制分支随后使用自己的 controller/state 路径，因而不能靠取消 admission 完成 reset/step。
- `task_env/runtime/sessions/source.py` 已有 `position_frame_bindings_from_artifact` 和 `position_joint_bindings_from_artifact`，名字带 Position，但其解析目标是 Artifact/Scene/RuntimeSource 的具名关系；`task_env/runtime/sessions/common.py::snapshot_v1` 要求真实 `SceneDefinition`、exact source ID、joint/frame bindings 全覆盖、`StateRequirements`。`DynamicCameraRenderSourceV2.from_runtime_source` 还要求 canonical Scene 和 source closure，并校验映射等于 Artifact/source。检查这些前提是否对具体非 Position source 成立；不建议只给变量改名、不校验 Scene 或把 legacy source 冒充 canonical Scene。
- 已保存的 `marker-selected-rgb/preflight-rejection.json` 明确失败在无 source-bound receipt，先于 RGB 及物理。`examples/tasks/declared_marker.py` 经 `ReferenceTaskBinding.from_provider_free_compiler` → `compile_panda_box_task`；PickCube 的另一构建路径明确调用了 `snapshot_legacy_mjcf_source`，它只支持固定的 Panda 资产目录。可作为定位 source provenance 的线索，不能把此 helper 硬编码成任意任务的通用解法，也不能断言 Marker 已可构建 canonical Scene。应比较已有已准入非 Position production binding、Artifact 版本和 source 组成，再选真实代表；source/preflight 规则必须保留。
- 可复用既有纯测试的参考入口：`test_phase_ii_d02b_typed_runtime_state.py`、`test_phase_ii_f03_core_contract_call_chain.py`、`test_v211_task_rgb.py`，其中前者/后者不同用例的 native/source 范围需逐项确认，不能因文件名而默认零步。Sol 的负例和 SDK/source 守卫保存在 ignored `workspace/reviews/V211_G05_5c_attempt002_sol_review/guarded_counterexample.py`、`guarded_counterexample.log`；它复现属性缺失，但其合成对象不是生产路径验收。

## 二：组件 camera 的最早真实失败链

- `CameraObservationProvider.capture` 当前仅 `write_camera_pose` 再 `read_frame(synchronized=True)`；`CameraSensor.metadata` 按声明计算 FOV/intrinsics，不是 native camera 读回。原 Pendulum 配置 FOV 1.2 rad、near 0.01、far 10；该路线 raster camera 代码默认 60°/0.001/∞。Sol 的 `guarded_camera_spy.py` 和日志在上面同目录，可直接复现“未透传”。单靠图像尺寸、非黑像素、receipt 所填数值或当前代码默认值不是修复证据。
- GeoPhys 的公开 `RasterSceneVisualizer.bind_task_camera/read_task_camera/project_task_camera/read_task_camera_frame` 已提供实际相机参数与投影读回；`task_env/runtime/sessions/geophys.py::bind_task_camera/task_camera_binding` 可参考，但它服务 selected、要求 world-mounted `CameraGeometry` 和当前 typed state，不应直接冒称对组件路线适用。底层现有 binding 一次只容纳一个任务相机，并要求任务相机尺寸与共享 framebuffer 匹配；对既有多相机、不同分辨率和组件 body/site mount，要按真实能力保留、扩展或明确拒绝，不能假设自动支持。当前看到的公共任务相机 API 没有单独的 pose 更新方法，动态挂载的处置需实际确认。
- 避免不必要的大矩阵：先 provider-free 测试声明→真实相机 API 的参数传递及缺失能力拒绝；再在获批窗口验证一个原有 Pendulum world-mounted 任务相机的 FOV/near/far 实际读回、固定点投影或裁剪负例、reset/step/close 和状态/时钟关联。如果改动影响 observer、其他 sensors 或支持范围，补有针对性的隔离/兼容检查，而非仅测试两次截图是否不同。复用 `GeoPhys/test/verification/rendering/test_raster_task_camera_binding.py` 与 `raster_clip_interval_cpu_smoke.py` 的设计时，先核查是否涉及 native、权限和预算。

## 三：最小验收路线与资源规划

1. 在前置/纯检查中暴露两个老失败；修复通用 owner 后通过真实工厂及真实 lifecycle 的非 Position reset/step，证明 state identity 和 bindings、错误/歧义拒绝、无额外 physics；fake/stub 只能辅助验证合同。
2. 对组件任务做真实相机参数读回和边界图像验证，保留默认 state-only、renderer 从创建固定至 close、reset/fault/资源行为；真实时钟、状态和 RGB 同边界，优先 Pendulum。历史 RGB 原始文件仍可做对照，不能单凭旧错误 FOV 的元数据签收。
3. 已有 PickCube 三原生和 GeoPhys→MuJoCo 成果按代码、source、输入/身份影响复用；只重测受影响入口，5b 的人工可辨决定不重开。不要让所有任务、所有组合或 Agent 迁移成为额外矩阵。
4. 建议沿前包准备 12 小时墙钟、source/native 各 ≤14400 秒、单 native worker ≤1200 秒、显式物理 ≤10000 子步、CPU ≤8、12 GiB 和新增 ignored 输出 ≤5 GiB 的预算提议；具体按实际候选与维护者批准重新冻结。先验证 GPU 可用性与需要，002 的 `nvidia-smi` 曾返回 exit 6；没有证据可承诺 Isaac 可用。不因非必需路线的设备未知自动浪费最后一次窗口，确需受影响重测而资源不可得则如实返包。
5. 精确区分普通 attempt 与多个 repair run；首个错误按 source/producer/consumer 最早边界排查，同一窗口解决常规问题。不得 force-add `workspace/` 或 `temp_output(s)/`；证据文件与 manifest 留工作区。交付后由 Sol 独立主审；如第三次仍未接收，停止普通派包，转维护者主导人工诊断。

本次预备工作没有运行场景、解析任务 source、运行 native、SDK、GPU 或 GUI，也没有新增实现代码、执行 goal、创建对话或 subagent。
