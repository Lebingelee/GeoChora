# G05 5c — 第二次未接收后的普通 attempt003 前重评

日期：2026-11-08。状态：`REASSESSED_NOT_DISPATCHED`。用户要求的 5c 范围仍为：Env 构建选择固定 renderer 至 close、同步任务 RGB、至少一个真实跨组合和非 PickCube 专门化的通用接线。同一 Env 的 renderer 切换延期。此记录不是执行授权、不是新的 goal prompt，也不启动第 3 次 attempt；第三次是最后一次普通 attempt。

## 实际根因与约束

独立主审见 [attempt002](../maintenance/reviews/20261108_5c_attempt002_sol_review.md) 和 [attempt001](../maintenance/reviews/20261108_5c_attempt001_sol_review.md)。当前继承含已完成实现的分支，开工时以新冻结 HEAD 为准。主体代码缺口是：

1. `task_env/environment/reference_env.py` 的 selected RGB 消费无条件依赖 Position 路径创建的 typed publication 及 MuJoCo 源 bindings；撤去入口检查没有为普通非 Position selected task 建立它们。`examples/tasks/declared_marker.py` 的 source closure preflight 被拒绝是另一个上游输入/准入边界，不能拿该拒绝证明 RGB 不可能，也不能绕过来源检查。
2. 组件链 `task_env/observations/capture.py::CameraObservationProvider` 写 pose 不写 FOV/near/far；`task_env/observations/camera.py` 仅按声明计算 metadata。已有 `GeoPhys/src/visualization/rasterizer/scene_visualizer.py` 的 public `bind_task_camera`/`read_task_camera`/`read_task_camera_frame` 与 Core `task_env/runtime/sessions/geophys.py` 是可研究的同仓实现；需确认它们对组件 lifecycle、可选其他相机、实时状态同步、故障/资源和当前 CPU envelope 的适配，不保证接通仅是增加一行 setter。不同 camera pose convention 必须显式换算。
3. 001 四条路线对各自输入和实际代码仍有有界证据；002 新 Pendulum 的帧与 receipt 不能证明正确光学参数或 state→frame 几何。002 PickCube selected GeoPhys 记录可用于受测条件，但公共 state 发布及 GeoPhys camera 修改的实际影响须复审。

这两项主要是实现和证据缺陷，不是用户要求的跨组合不可能，也不是需要把 renderer 运行中切换加回本阶段。全量 Agent/Controller 迁移不是该包的绝对门，客观实体可为空。

## 开源与已有能力复查

- [MuJoCo 官方可视化实现说明](https://github.com/google-deepmind/mujoco/blob/main/doc/programming/visualization.rst) 区分 scene 更新和实际 low-level camera；FOV 等应进入 renderer 实际使用的 camera，而非仅由元数据报告。可借鉴 owner/参数分离，不引入新的 MuJoCo renderer 或依赖。官方 main 分支为设计参考，不保证当前安装版本每项 API 相同；[许可证](https://github.com/google-deepmind/mujoco/blob/main/LICENSE)按其仓库文件核查；本计划不复制代码。
- [ManiSkill CameraConfig 与 sensor](https://github.com/mani-skill/ManiSkill/blob/main/mani_skill/sensors/camera.py) 和 [scene camera 构建](https://github.com/mani-skill/ManiSkill/blob/main/mani_skill/envs/scene.py) 显式处理 FOV/intrinsics、near/far 与底层 camera，是声明到实际相机绑定和核验的对照；其 SAPIEN/torch 体系不直接复用于本项目、不新增安装依赖。链接指上游 main 而非本机版本证明，[许可证](https://github.com/mani-skill/ManiSkill/blob/main/LICENSE)按其仓库核查；不复制代码。项目维护与版本可在需要 vendor 时另核；目前只参考设计。
- 上游资料不提供可直接替代本仓已完成的 GeoPhys→MuJoCo 具名状态 identity/source bridge，因此选本仓现有 provider/runtime 接口，不迁移仿真器、不依赖额外下载。已有 GeoPhys public task camera API 和 selected 的 typed state/renderer binding owner 比新增 manager 或外部包装更贴近本包。

## 拟议的有界修复与验证顺序

1. **先封住非 Position 假准入**：按实际 capability 生成初始和每个 step 的 `CanonicalStateView`/等价经合同批准的已发布状态，以 scene-qualified named frame/joint 显式绑定 source、episode、generation、clock 与 renderer。将 position 所属绑定参数从通用 camera consumer 中解耦，公共控制准入保持原样；做真实 production binding 的 provider-free 生命周期检查，包含非 Position reset/step、状态变化与拒绝缺失/歧义。不接受只测 `object.__new__` 或只更新 admission。
2. **再接通组件相机**：优先复用 GeoPhys 已有独立 task camera public binding 和读回，按每个 `CameraSpec` 向实际 renderer 提供 pose、FOV、near/far、尺寸，验证请求值与已实现值一致；必要时添加通用 provider public capability。无法满足的输入在构建／捕获前明确拒绝，避免假 receipt。验证多个 camera 不互相污染、同 snapshot、reset/close/failure 和无额外 physics；验证真实受测相机下图像、裁剪与配置可对应，并保存实际状态及客观读回。不得强行消除观测用显示相机的隔离。
3. **真实闭环与证据影响**：优先重用非 Position 的现有已准入 production 路线或在可用现有 source/预算内消除可修复的 Marker provenance 问题；如来源确不可用，记录候选和原因、选择另一个真实公开构造路径，不绕过 preflight。选择已准入 PickCube 原生和 GeoPhys→MuJoCo 跨组合作为受影响回归；组件优先 Pendulum，同一 Env reset/step/reset/close，发布 state、RGB、clock 和独立光学/geometry 比较，遵守固定 renderer。先判断改动影响再重测其他原生路线，不重跑历史完整矩阵。若涉及 Isaac 而设备不可用，按真实边界保留 unknown 并报告，由 Sol 按受影响证据决定。
4. **交付与安全**：保留 001、002 运行和失败，不把未预约 75 子步补造为预约；新的真实测试事前预约、输出放被忽略的 workspace，记录预算和 release。002 错误跟踪的 workspace 证据在版本治理上需维护者决定；不 reset/clean/改写历史，不删除现场。第三次未接收则停止普通派包、依 Skill 进入维护者主导人工诊断。

## 可行性与待冻结资源

从现有代码的公共相机读回和可复用状态编译接口判断，原定 5c 在有设备、source closure 和合理预算时**有可信的修复路径，但不能保证一定通过**。当前 Marker 的预检拒绝、组件帧真实性和设备可用性仍要实查。下一包若获维护者明确授权，可沿已用 002 的 12 小时墙钟、source/native 各 ≤14400 s、单 worker ≤1200 s、CPU ≤8、12 GiB、≤10000 显式子步、输出 ≤5 GiB作为资源提议，依现场验证及用户意见重新冻结；不是本重评的自动授权。Sol 不执行 native/source 解析/SDK/GPU/GUI，后续实施由维护者指定并手动转交。
