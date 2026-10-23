# R04 — Dynamic Camera → Public Observation / Recorder

状态：REVISED_DRAFT；R04a/b/c 均 PLANNED / NOT_STARTED。required 候选交集为 GeoPhys a53 CPU physics × MuJoCo 3.8.1 Native OpenGL/EGL × 既有单 Panda Position source，双 fixed/hand-mounted RGB/Depth/Entity mask。不把新 Assembly source 默认纳入 Camera 支持。

## Owners 与真实消费断点

复用 [typed-state](../../../../../task_env/artifacts/state.py)、[CameraSession API](../../../../../task_env/render/camera/api.py)、[dynamic renderer](../../../../../task_env/render/camera/mujoco.py)、[ObservationBuilder](../../../../../task_env/observations/state.py)、[SelectedReferenceEnv](../../../../../task_env/tasks/reference_env.py)、[Recorder](../../../../../task_env/recorders/recorder.py) 与 [H5 owner](../../../../../task_env/recorders/h5.py)。

当前独立 CameraSession pairing 已有有界 capture/隔离/关闭证据，[D 开发记录](../Phase_II/D_Development_Record.md)保留其原身份；Position public Env 是 state-only。generic SensorObservation/ObservationBuilder 的 depth 为 provider-defined passthrough，不等于 advanced CameraSession 的 Optical-Z/Entity-mask。R04a 必须确定在现有 Observation owner 的显式桥接与 Env 可选配置；不能用两个诊断调用拼接验收或另造 Env/Recorder。

## Observation / Capture / Storage 合同

- Env lifecycle 持有需要的 camera consumer 资源并负责 close/构造失败清理，renderer 不拥有 physics。一次真实 step 结束后，先取得同一 typed publication，再 capture 并构造 public observation；同边界重复读取使用已发布缓存，不调用 Controller、physics step、mj_step 或隐式 mj_forward。只允许 renderer 自身的只读几何同步。
- public leaf schema 显式列 camera key、RGB HWC float32 [0,1]、Depth H×W float32/m/optical +Z/invalid=0、Entity mask H×W uint32/background=0，以及 layout、unit、visibility、calibration frame/pixel convention。policy-visible 数组与 privileged/diagnostic metadata 分开；optional 缺测明确 unavailable，required 缺测失败，不能填零伪装观测。
- Capture Identity 绑定 Scene/source/materialization、consumer、episode/reset/boundary/clock 与共采 modality；Calibration 绑定内外参、分辨率/near/far；Label Map 绑定 canonical Entity IDs、正标签与该 capture/scene instance，禁止 native geom IDs 外泄。reset 后清旧缓存、首帧 freshness，旧 episode/capture 拒绝。
- observation_space、ObservationSchema、info_schema 与真实返回一致；不可只增加 metadata 而不提供真实 buffer。用户不选 Camera 时保持旧 state-only defaults 和 import 无 native 初始化副作用。
- 同一个 TransitionRecorder 记录 T+1 个 state/camera observations 与 T 个 Action/Target/Ack transitions；每组图像必须与该 boundary 的 state/clock/capture identity 一致。Generic H5 v3 已可容纳固定 shape/dtype 的 numeric tree；先复用，不仅为 RGB 重写 writer。
- calibration、label map、capture identity 采用显式版本化 metadata extension + 对应 strict semantic reader；需要新版本时说明 dispatch，不改旧 v1/v2/v3 meaning。structured control reader、metadata inspector、raw pixel/state dataset readback 各司其职，任何一个成功不代表另两个通过。
- physics 已推进后 capture/observer/append 失败，沿既有 C03a latch 报 physical progress 与 transition validity，不生成有效 transition，不 finalize 完整轨迹，不假回滚。missing modality、shape/dtype/label-map/身份或 metadata 写入错误也 fail-closed。

## 资源与独立性

321×241、RGB float32 + depth float32 + mask uint32、双相机每 boundary 原数组 3,094,440 bytes；65 boundaries 约 191.82 MiB，未计 copy/stack/H5/native GL 峰值。这是算术预算，不是本轮内存实测。建议首个 S3 horizon=16（17 observations），R04a 必须冻结超时、Recorder buffer、峰值 RSS/GL/磁盘预算再运行；超预算为 FAIL/NOT_RUN，不删模态或降 schema 求绿。

记录实际 EGL context、renderer、设备与 driver；device=None 不是 GPU ordinal pinning。缺真实 EGL 则 NOT_RUN/失败并保留日志，禁止 fake renderer/静默 skip。R04 失败不阻塞 R01/R02 Position，但当前 P99 required Camera gate 会阻塞；改范围须维护者显式接受，不自动 DEFERRED。

## 切片

| ID | 前置 | 工作与交付 | 必需 Evidence / Stop Condition |
| --- | --- | --- | --- |
| R04a | P00 | 现有 owner 桥接、public config/space/schema、metadata reader 和预算合同 | S1：缺模态/旧reset/错capture/calibration/label-map、容量与失败链；不同意消费合同则停止 |
| R04b | R04a | 显式公共 Candidate 内同边界 capture→observation、资源/cache lifecycle | S2：同一 make_env reset/多步→真实双相机三模态、读零推进、reset freshness/隔离/close |
| R04c | R04b | 同文件 H5 图像/深度/mask/metadata/数值控制与状态 semantic readback | S3：T/T+1、每帧identity/calibration/labels/数值与像素比对、故障不成完整轨迹；不能以 inspector 代 reader |

不引入 visuomotor policy Qualification、async、semantic/link mask、free-joint/Assembly rendering 全矩阵；不把 Isaac Lab 的 Warp-native buffer 作为本项目 ABI。参考 producer/native refresh/consumer lifetime 分离原则见 [README](README.md#references)。
