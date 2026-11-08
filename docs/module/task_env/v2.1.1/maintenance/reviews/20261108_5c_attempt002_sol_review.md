# G05 5c attempt002 — Sol 独立主审

日期：2026-11-08。结论：`REWORK_REQUIRED_5C_GENERIC_PUBLICATION_AND_COMPONENT_CAMERA`。5c 普通 attempt 已执行 2 次；未整体接收。第三次普通 attempt 前按既有 goal-orchestration Skill 进行重评，不自动派包。维护者指定固定 renderer 生命周期、同步任务 RGB、真实跨组合和通用接线的 5c 调整不变；不重开 5b。

## 直接未闭合的两个技术问题

1. **selected 非 Position 的 RGB 入口已放开，实际 reset 时仍缺少所需状态。** `task_env/registry.py::make_env` 不再检查 `position_profile`，但 `SelectedReferenceEnv._prepare_reference_reset::read_state` 当前只在 `self.position_profile` 分支创建 `self.typed_state`；非 Position 分支只读取 `self.state` 和 feedback。随后所有 task RGB 路线在 `observation()` 无条件使用 `self.typed_state.view`。因此正常新建的非 Position selected Env 到达 task RGB 采集时存在缺失状态的确定路径；MuJoCo renderer 的 `_new_task_rgb_consumer` 还读取只在 Position materialization 分支准备的 `position_joint_bindings`、`position_frame_bindings`。这不是 source preflight 失败所造成的结论，也不声称 Marker 已实际越过该 preflight。实测的 PickCube physical candidate 自身创建 `PandaPositionServoProfileV1` 并使用 position candidate，因此不能证明非 Position 路线。新增的 `test_public_factory_adds_camera_to_an_independently_named_selected_task` 用 `object.__new__` 和假的 artifact，只测配置，没有 reset/step。Sol 在禁止 SDK/provider 导入、任务 XML/MJCF/USD/URDF 读取的守卫下，用合成对象独立调用真实 `observation` 方法，复现 `AttributeError: ... no attribute 'typed_state'`，capture 尚未调用；该最小反例是合同级证据，不是 native route 实测。脚本及日志在 ignored `workspace/reviews/V211_G05_5c_attempt002_sol_review/guarded_counterexample.*`。
2. **组件式 task camera 的实际光学参数未绑定，receipt 将声明值当成采集参数。** 新组件路线使用 `CameraObservationProvider.capture()`；其调用 visualizer 时只写 pose 并 `read_frame(synchronized=True)`，没有传递 `CameraSpec.fov_y`、near、far。GeoPhys rasterizer 创建 `RasterCamera()` 默认 FOV 60°、near 0.001、far ∞；组件路线未调用现成的 `bind_task_camera` 或 `set_fov`/`set_clip_interval`。交付的 Pendulum 相机声明 FOV 1.2 rad（约 68.755°）、near 0.01 m、far 10 m，而其 metadata 按声明计算 intrinsic；根据实际代码路径，这些参数没有被设置到采集 camera，不能把声明 metadata 当作真实摄像机回读。Sol 在相同 SDK/source 禁止守卫下，以有 setter 的 spy visualizer 独立运行真实 `CameraObservationProvider.capture`，只观察到 build、pose、read_frame，没有 fov/clip 设置；这证明配置未透传，不是新 native 读回。相关 guard 脚本和日志在 `workspace/reviews/V211_G05_5c_attempt002_sol_review/guarded_camera_spy.*`。必须通过公开 renderer API 绑定并读回所声明光学参数，或对无法表示的值提前拒绝，并验证影像／裁剪，不能从 shape/range/自填 metadata 推断。

## 可复用成果及边界

- `lifecycle.py` 的可选 observation transform、组件 factory 和 Pendulum 的实际 reset/step 是可继承进展；执行者在最终代码记录 Pendulum GeoPhys CPU 25 子步和 PickCube GeoPhys CPU 5 子步。Sol 无 SDK/source/native/GPU/GUI 重跑。Pendulum 两个 64×64 float32 原始帧的字节 SHA 与 report 吻合，40 像素有变化；这些事实不证明 FOV、裁剪、同一物理状态对应的几何或任务相机完整正确。该 probe 使用 0 力矩，run.json 未保存实际 reset/step state 向量及独立的状态到图像几何对照；避免把单个时间戳和不同 hash 扩成完整同步正确性证明。
- Selected PickCube 的 saved reset/step/reset 3 个 `capture_identity.state_boundary` 和 `sample_clock` 与保存状态逐项一致，分别是控制步 0/1/0；这有界支持其采集证据，不代表非 Position。001 四条路线可按最终修复的代码/输入实际影响复用；GeoPhys session/lighting 路径已有改动，不能以“renderer 未改”一概证明原运行完全适用于最终代码，应记录具体差异及必要的受影响重测。
- GeoPhys 的空/受支持灯表处理与 visual/default-only 明确 unsupported 是进展，真实 PickCube 当前代码有运行记录。CPU lighting smoke 由执行者运行，不是 Sol 的 native 重跑。非 MJCF、任意灯具和更一般 camera 不在目前通过证据内。
- 对 Pendulum／双轮车的 Agent/Controller 迁移，按获批包这是优先分析与可行时安全实施，不要求全量迁移作为本次绝对门；沿用源内机构和直接 torque，避免强行复用 Panda 的担忧有代码依据。现有报告可以作为有限可行性评估，不表明已归一两个环境的物理构建，也不因该迁移延期单独拒收 5c。

## 身份、独立验证与流程

- 已核对 Core 输入 `c13ae2703230eb633833bfdefdd88acaea4e2d59`、实现 `1c6b7e4f49107fe57e31e9be43e2729162ffaca1`、release `13111ca78f3c678a02da1d7ffb5a7c248447b036`；GeoPhys `40df100c84d900d5ad40a6a23de48ef61c2f6f74` 与 gitlink 相符，Menagerie 未变。三个保护输入 SHA 及 attempt001 release/manifest SHA 独立复核相符。
- output-manifest 217/217 文件 hash/大小独立复核，无未列且不在排除范围的文件；manifest 与 release/pytest/tmp 的排除规则如 release receipt 所述。Sol 在 SDK/source 禁止守卫下独立运行 `test_v211_task_rgb.py`：13 passed；上面的两个反例不在这一套测试里。执行者的最终 59 passed、1 deselected 与先前 60 passed 是执行者数据。
- 新出现的 75 物理子步事前未预约，报告按现有测试 3×25 计入 110 子步总账；这违反 attempt002 本身的预约要求，用户对 001 偏差的历史处置不能自动改写本次事实。保留偏差和依证据计量，不因单独这一项否定其余真实结果。本次技术拒收由上述两个独立缺口决定。
- 额外仓库卫生：`1c6b7e4f` 将 `workspace/maintenance/v211_g05_5c_attempt002/` 下 218 个生成文件强制跟踪，含两份 source snapshot/资产副本；最终 HEAD 下该目录有 219 个 Git 文件、约 72.9 MB，尽管 `.gitignore` 明确忽略 `workspace/`。这与工作包只提交相关 Core 与必要 GeoPhys 修改、证据留 workspace 的边界不一致。文件和历史目前保留；后续应由维护者决定适合的版本治理，不能通过 reset/clean/重写历史或删除原证据掩盖事实。此项不单独使现场真实数据失效。
- 根据 release receipt 和本次只读锁／进程名称检查，没有发现本包活跃 worker 或锁占用；这只表示检查时状态，不代替将来开工前的实时检查。执行者报告 GPU 查询失败，CPU 证据不证明 GPU 状态。尚未 merge、push、tag、发布或进入阶段 6。

## 最小后续方向

先对非 Position selected 的实际 source/scene/publication 建立独立于 Panda Profile 的真实具名状态和 render binding，覆盖真实生产构造、reset、step 和不支持能力的显式拒绝，不放宽 controller/physics admission；再通过公共相机 binding 实际设置/读回组件相机 FOV、near/far 和 pose，保留 observer 隔离、reset、fault、close，并以受影响的真实代表 route 对照帧、状态及 geometry。保持可复用旧证据、无需全历史矩阵或强制第二任务矩阵。根据两次未接收，第三次普通尝试前进行现有 Skill 强制重评和必要调研，由维护者决定下一工作包与执行授权。
