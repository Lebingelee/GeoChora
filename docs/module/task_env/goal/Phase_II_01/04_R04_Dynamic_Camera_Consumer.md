# R04 — Dynamic Camera → Public Observation / Recorder

状态：REVISED_DRAFT；R04a 已实现且原23项provider-free S1通过；Sol复核为CHANGES_REQUESTED（capture请求绑定、H5独立state/episode锚点待修复）；R04b/c PLANNED / NOT_STARTED。required 候选交集为 GeoPhys a53 CPU physics × MuJoCo 3.8.1 Native OpenGL/EGL × 既有单 Panda Position source，双 fixed/hand-mounted RGB/Depth/Entity mask。不把新 Assembly source 默认纳入 Camera 支持。

## Owners 与真实消费断点

复用 [typed-state](../../../../../task_env/artifacts/state.py)、[CameraSession API](../../../../../task_env/render/camera/api.py)、[dynamic renderer](../../../../../task_env/render/camera/mujoco.py)、[ObservationBuilder](../../../../../task_env/observations/state.py)、[SelectedReferenceEnv](../../../../../task_env/tasks/reference_env.py)、[Recorder](../../../../../task_env/recorders/recorder.py) 与 [H5 owner](../../../../../task_env/recorders/h5.py)。

当前独立 CameraSession pairing 已有有界 capture/隔离/关闭证据，[D 开发记录](../Phase_II/D_Development_Record.md)保留其原身份；Position public Env 默认仍为 state-only。generic SensorObservation/ObservationBuilder 的 depth 为 provider-defined passthrough，不等于 advanced CameraSession 的 Optical-Z/Entity-mask。R04a 已在现有 Observation owner 增加显式 opt-in bridge 与 Env lifecycle 接线；R04b 的真实 renderer/同一 Env S2 尚未运行，不能用两个诊断调用拼接验收或另造 Env/Recorder。

## R04a 实现边界（2026-10-26）

`panda-position-servo-candidate-v1` 接受显式 `camera_observation` mapping；未选择时，state-only observation/schema、source/Controller identity 和导入无 native 初始化保持原样。opt-in 仅允许一个现有单 Panda Position Profile，production 几何固定为 321×241、D04 RGB/optical-Z/Entity-mask、固定相机与 hand-mounted 相机的 canonical 顺序；每个 `CameraMountRequestV1` 必须带明确 parent Frame 和 proper rigid mount transform，配置在 source workspace 创建前验证。它不准入新 Assembly source、其他 Provider/backend 或任意 renderer profile。

新增 `CameraObservationConfigV1`、capture metadata 与 boundary 值复用现有 `CameraGeometry`、`CameraCaptureIdentityV1`、Calibration、Canonical Entity LabelMap 和 `DynamicCameraRenderSourceV1`。`DynamicCameraObservationConsumerV1` 在已发布 typed state 后延迟创建两个现有 CameraSession，只读 capture；相同 boundary 复用缓存。Env 在 reset/构造失败/step fault/close 时拥有并关闭 consumer；post-step capture/observer 失败沿 C03a latch 保留实际 progress，不伪造 transition 或回滚。RGB HWC float32、Depth H×W float32 米制 optical +Z、Mask H×W uint32 进入已有 public `observation_space`/`ObservationSchema`/info contract。

Generic H5 v3 保持原 ABI；opt-in 时追加 `camera_observation_contract_v1_json` 与 `camera_observations_v1_json`，`load_camera_observations_h5()` 以严格 typed semantic reader 核对 T+1、source/capture/boundary/calibration/label-map、RGB CHW uint8 既有量化布局、Depth/mask dtype 与 mask digest。provider-free S1 使用 synthetic captures/H5 验证配置、输出空间、缓存、故障关闭与 reader；真实 MuJoCo/EGL renderer、真实 Env reset/step 与同文件实际相机读回均为 NOT_RUN，分别留给 R04b/R04c。此 S1 不证明 camera native/runtime 或 P99 gate 已通过。

## Sol复核与定向返工（2026-10-26）

Sol核对18文件diff、16项原包输出及18项tracked摘要，重跑原定向S1仍为23 passed；但纯S1反例复现两个拒绝缺口：consumer接受同camera ID/尺寸而mount偏移0.2m的自洽capture；H5 reader接受camera sidecar与真实state boundary digest或finalized episode outcome不一致的文件。R04a出口尚未接收，下一包为同分支attempt002的有界实施修正，不新增研究轮次或native实验。复核入口为本机ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r04a_001/`；原attempt001与通过项保留。修复后按原表交Sol复核，正常下一行R06a，R04b/c仍未启动。

## Observation / Capture / Storage 合同

- Env lifecycle 持有需要的 camera consumer 资源并负责 close/构造失败清理，renderer 不拥有 physics。一次真实 step 结束后，先取得同一 typed publication，再 capture 并构造 public observation；同边界重复读取使用已发布缓存，不调用 Controller、physics step、mj_step 或隐式 mj_forward。只允许 renderer 自身的只读几何同步。
- public leaf schema 显式列 camera key、RGB HWC float32 [0,1]、Depth H×W float32/m/optical +Z/invalid=0、Entity mask H×W uint32/background=0，以及 layout、unit、visibility、calibration frame/pixel convention。policy-visible 数组与 privileged/diagnostic metadata 分开；optional 缺测明确 unavailable，required 缺测失败，不能填零伪装观测。
- Capture Identity 绑定 Scene/source/materialization、consumer、episode/reset/boundary/clock 与共采 modality；Calibration 绑定内外参、分辨率/near/far；Label Map 绑定 canonical Entity IDs、正标签与该 capture/scene instance，禁止 native geom IDs 外泄。reset 后清旧缓存、首帧 freshness，旧 episode/capture 拒绝。
- observation_space、ObservationSchema、info_schema 与真实返回一致；不可只增加 metadata 而不提供真实 buffer。用户不选 Camera 时保持旧 state-only defaults 和 import 无 native 初始化副作用。
- 同一个 TransitionRecorder 记录 T+1 个 state/camera observations 与 T 个 Action/Target/Ack transitions；每组图像必须与该 boundary 的 state/clock/capture identity 一致。Generic H5 v3 已可容纳固定 shape/dtype 的 numeric tree；先复用，不仅为 RGB 重写 writer。现有 `_recording_copy/_quantize_rgb` 默认将RGB分支保存为 **CHW uint8**；public RGB允许HWC float32 [0,1]，recording比对必须执行同一float32×255→np.rint→uint8及HWC→CHW变换，不能要求float32像素无损回读或为R04/R07重设计Recorder。
- calibration、label map、capture identity 采用显式版本化 metadata extension + 对应 strict semantic reader；需要新版本时说明 dispatch，不改旧 v1/v2/v3 meaning。structured control reader、metadata inspector、raw pixel/state dataset readback 各司其职，任何一个成功不代表另两个通过。
- physics 已推进后 capture/observer/append 失败，沿既有 C03a latch 报 physical progress 与 transition validity，不生成有效 transition，不 finalize 完整轨迹，不假回滚。missing modality、shape/dtype/label-map/身份或 metadata 写入错误也 fail-closed。

## 资源与独立性

321×241、双相机 public RGB float32 + depth float32 + mask uint32 每 boundary 为 3,094,440 bytes；Recorder RGB CHW uint8 加原 depth/mask 副本每 boundary 为 1,701,942 bytes。R04a 固定算术 horizon≤16（最多17 boundaries）：public payload 52,605,480 bytes，recorded payload 28,933,014 bytes；实现 admission limits 分别为 64 MiB 与 128 MiB。数值不含 state、metadata、copy/stack/H5 和 native GL；不以磁盘压缩大小代内存。后继执行预算 proposal 为一个 native worker、每包最多2次显式 reset/trial、每次 horizon≤16、每未来进程 timeout 300 s、整包≤900 s、RSS≤4 GiB、增量 Evidence≤256 MiB。若 driver/GL 无公开显存计量，VRAM 记 null+reason，RSS 不代表 VRAM；这些是待维护者执行包确认的预算，不是本包实测或 R04b/c 授权。

记录实际 EGL context、renderer、设备与 driver；device=None 不是 GPU ordinal pinning。缺真实 EGL 则 NOT_RUN/失败并保留日志，禁止 fake renderer/静默 skip。R04 失败不阻塞 R01/R02 Position，但当前 P99 required Camera gate 会阻塞；改范围须维护者显式接受，不自动 DEFERRED。

## 切片

| ID | 前置 | 工作与交付 | 必需 Evidence / Stop Condition |
| --- | --- | --- | --- |
| R04a | P00 | 现有 owner 桥接、public config/space/schema、metadata reader 和预算合同 | S1：缺模态/旧reset/错capture/calibration/label-map、容量与失败链；不同意消费合同则停止 |
| R04b | R04a | 显式公共 Candidate 内同边界 capture→observation、资源/cache lifecycle | S2：同一 make_env reset/多步→真实双相机三模态、读零推进、reset freshness/隔离/close |
| R04c | R04b | 同文件 H5 图像/深度/mask/metadata/数值控制与状态 semantic readback | S3：T/T+1、每帧identity/calibration/labels/数值与经过既有量化/布局变换的RGB像素比对、故障不成完整轨迹；不能以 inspector 代 reader |

不引入 visuomotor policy Qualification、async、semantic/link mask、free-joint/Assembly rendering 全矩阵；不把 Isaac Lab 的 Warp-native buffer 作为本项目 ABI。参考 producer/native refresh/consumer lifetime 分离原则见 [README](README.md#references)。
