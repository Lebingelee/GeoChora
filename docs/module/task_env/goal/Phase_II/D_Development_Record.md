# Phase D 开发记录 — Materialization、Typed State、Camera 与 Pairing

> **2026-10-23 范围决定**：本记录声明的交集按 [维护者决定](../../../../maintenance/phase_ii_scope_freeze_20261023/maintainer_scope_decision.yaml) 获有界工程接受；历史 S0/S1/S2/S3、失败、原 pin 与缺失原件记录保持原义。本次范围冻结不产生新 Task freeze、发布或 Qualification。

日期：2026-10-22。当前声明交集已有有界实现/验证；D04/D05 consumer 接线和广泛组合已在本次范围中接受延期，后续另行决定实施。
目标契约见 [04_Phase_D_Physics_Rendering.md](04_Phase_D_Physics_Rendering.md)；统一状态见 [05](05_Architecture_Review_and_Execution_Order.md)。

## D01

D01a 复用 Source/assembly/RuntimeSession owners，让 A05 原样 Scene-v3 payload 真正参与 materialization/reset/realization/step，而非只复制 identity。
frozen Artifact hash 不改；错误 Frame/Joint/closure/geometry/tolerance 拒绝。原 axis-change probe 绑定 GeoPhys `4436787e`。
D01b 接通 TaskArtifact v1、固定 topology Role/ResetPlan 与 GeoPhys/MuJoCo CPU；真实 source→materialize→reset→realization→step，保留来源 identity 和 native owner。
不是通用 parser、跨 topology、任意多 Entity 或所有 Provider 支持。

当前 pin `a53a8cfe` 下，原 axis-change test 单项 **HISTORICAL_NOT_APPLICABLE**；未知 pin 仍失败，精确历史断言保留。
同一测试 owner 的 `test_b02_plan_consumes_the_exact_a05_v3_scene_identity` 明确要求 a53 并执行真实当前路径；wrong identity/closure/tolerance 检测照常运行。
receipt 仅向 fresh pytest tmp_path 独占写入，拒绝覆盖旧 Evidence。
交付准备最小回归 **12 passed / 1 historical-not-applicable / 0 failed**，50.03 s；不把 skip 算作 pass。
日志：`workspace/maintenance/phase_ii_second_review_20261022_001/d01a_regression.log`。
原 D01a/D01b pin 的 receipt 保留历史身份，不能以当前测试换写旧 SHA。

## D02

D02a 在同一 artifacts owner 定义 typed Joint/Frame、StateRequirements、sample clock/boundary/revision、NativeIntervalEvidence 和 StateViewLifetime；v0 codec 不变。
相同 control step 的修改由 state_revision 区分；native index 不从 outer step×substeps 冒算，缺 required contact 失败，optional 缺测带原因。
D02b 的 `snapshot_v1()` 发布 immutable owned tuples，与匹配 lifetime 一起返回；Entity read views 是同一值的投影，不再建 state store。
GeoPhys/MuJoCo CPU scalar/free-base evaluation-boundary 真实 probe 验证 7D pose/6D twist、child-frame 线速度、clock、reset identity 和只读 consumer 一致性；owned snapshot 可在 close 后保留。
历史相关联合 14 passed；provider alias、native spherical/contact 与完整 native interval publication 未由该 slice 实现。
后续 raw-force v2 仅为精确 R1 candidate/build 扩展，仍是 evaluation-boundary publication，见 [C02b](C_Development_Record.md#c02b)。
不得因 C05c diagnostic native samples 通过，就将 D02 通用 native-rate/alias 能力标为完整。

## D03

复用 Scene/source lowering、Canonical State 和 Camera/Renderer owners。
GeoPhys RuntimeSession 是唯一演化物理 authority；MuJoCo renderer-only model 消费公开 typed scalar joints，维护视觉副本，不执行另一套物理。
Canonical Entity/Frame→native body/geom instance 映射与 source identity 校验；geometry、publication、transform 分开版本化，每 consumer 独立 cursor。
capture/sync 不调用 Controller 或推进 physics；same-step publication/reset/双 consumer/close 隔离有 S1。
原真实 S2：12 outer interval/60 native steps（公开 clock 推断），hand 移动约 0.08044 m，RGB 327 个变化像素，静态 geometry 只构建一次。
历史 S1 2 passed，相关 D01b/D02b/D05a 15 passed。
Evidence：`workspace/maintenance/d03_visual_sync_20261021/`，原来源身份与 pin 在该收据中；当前 pin pairing 的独立复验见下。

## D04

在既有 CameraGeometry、CanonicalCameraObservation、dynamic render source 和 MuJoCo session 增加独立 RGB/Depth 与 Entity-instance-mask profiles，保留旧 v0 convention。
fixed/mounted 使用同一 state publication/pose，optical frame 为 +X right/+Y down/+Z forward。
`T_world_from_camera = T_world_from_parent @ T_parent_from_mount @ T_mount_from_camera`；hand parent 唯一解析到 `panda-main/hand`。
321×241、vertical FOV 90° 的 K 为 `[[120.5,0,160.5],[0,120.5,120.5],[0,0,1]]`，pixel center `(col+0.5,row+0.5)`。
RGB HWC float32 [0,1]；Depth H×W float32/m/optical-Z，near/far/background 按 profile 归一 invalid=0，exclusive far；旧 inclusive convention 不变。
独立 square-peg 几何 oracle：固定相机 front-surface Z 1.484 m，实测 1.48399997 m；mounted depth ≤2 mm、backprojection ≤3 mm 的事前阈值通过。
reset 新 capture identity 且重现初帧，旧 episode state 拒绝；capture/sync 不 step/compute。

受限 Entity-instance segmentation 通过 MuJoCo public render output 映射到 Canonical Entity，不泄漏 native geom IDs。
mask 与 label-map/capture/scene-instance identity 一并校验/磁盘回读；错/歧义 body/geom ownership 与 unsupported object type 拒绝。
Semantic class segmentation、link masks、free-joint dynamic rendering、async/deformable 未支持。
Evidence：`workspace/maintenance/d04_rgbd_camera_20261022/`；Entity-mask receipt 与当前 pairing capture 在 `p99_runtime_closure_20261022/pairing_s2/`。

**兼容勘误**：早期两项 B04a sweep failure 来自测试把已支持的 H5 v3/canonical-v1 当未知版本，后更正为 v99 并在真实 typed reader 边界验证拒绝（2 passed）。
`inspect_trajectory_h5()` 为 metadata summary，不是全语义 decoder；未建立生产 reader 缺陷，旧失败日志保留。

## D05

D05a 在 existing Execution/Camera owners 版本化 physics/render selection、完整 per-camera override、manifest identity 和静态 capture-request identity；旧 ExecutionSpec mapping 和同 Provider 路线保留。
D05b 首个受限 pairing 是 Scene-v3 scalar-joint Position source：GeoPhys CPU physics × MuJoCo 3.8.1 native OpenGL renderer。
原 S2 绑定 `4436787e`/Core `ab73f78`；换到 a53 后曾因 X11 context 无法创建而 NOT_REVALIDATED，不能借旧 receipt 通过。
随后在 a53 上用 NVIDIA EGL 完成独立当前 pin S1/S2，关闭该运行缺口，原失败与旧 receipt 均保留。

### 当前 pin pairing

GeoPhys `a53a8cfed7c9d6464274b5c96fca601271dc4ee4` CPU、MuJoCo 3.8.1、Taichi Forge 0.6.3、Python 3.12.14。
`MUJOCO_GL=egl PYOPENGL_PLATFORM=egl EGL_PLATFORM=surfaceless`；实际 NVIDIA RTX 5060/OpenGL 4.6 driver 595.84，仅记录实际选择，selection device=None 不代表显式 GPU ordinal pinning。
S1 **3 passed**；S2 **PASS_BOUNDED**：同一 RuntimeSession reset→12 个 10 ms interval→capture→reset/capture→close。
fixed-default/hand-mounted override 两 consumer，共六次 RGB/Depth/Entity-mask，same boundary/clock/episode、遮挡/depth/mask/label-map/原文件读回通过。
capture instrumentation 的 Controller.compute、Provider.step、mj_step、mj_forward 均为 0；两 native Renderer 各 close 一次，构造/sync/capture 失败和 sibling 隔离有检查。
不要求进程级 GL allocator 全归零；renderer-only 资源关闭不关闭物理 RuntimeSession。
Evidence：`workspace/maintenance/p99_runtime_closure_20261022/` 的 `d05b_s1.log`、`pairing_s2.log` 和 `pairing_s2/`。

### Consumer 边界与未准入范围

当前 dynamic CameraSession 输出由诊断 probe 直接消费。generic BaseTaskEnv 的既有 CameraObservationProvider 路线不是这里的 dynamic pairing。
Position candidate 未把这些 RGB/Depth/mask 接入 policy observation 或 TransitionRecorder；相机原文件回读不等于相机轨迹录制或 visuomotor。
通用 renderer pairing matrix、semantic masks、free-joint、Assembly、device pinning、真实 async 与 Qualification 均未获得支持。
本轮只整合文档，未重跑 native rendering campaigns。

原始完整命令、identity、容差与收据：[整合前 D 文档](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/04_Phase_D_Physics_Rendering.md)、[P99 运行收据](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/P99_Runtime_Closure_2026-10-22.md)。
轻量二审包只保留相机 receipts/索引，PNG/Depth/Mask 原数组外置；像素级复核须取完整 Evidence。
