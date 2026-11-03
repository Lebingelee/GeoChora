# Core ↔ render adapter 协议草案

状态：`DRAFT_FOR_DISCUSSION`；本文件是 1d 的 render-side 权威设计正文，待维护者统一审阅，不是已实现 API、冻结协议或接通证据。协议沿用 Env、RuntimeSession、render/camera、observation 与 batch 的现有 owner；不引入第二个 Runtime、Recorder、RenderManager 或可变 SceneDataManager。Depth、segmentation、Flora 和完整非刚体运行验收不属于本包。

## 三项独立完成目标

| 目标 | 用户入口 | 本目标完成条件 | 不构成的证据 |
| --- | --- | --- | --- |
| 窗口展示 | 构建时 `render_mode="human"`；`.render()` 驱动展示/事件泵 | 配置的 observer camera 显示当前已发布 scene boundary；present 与事件结果可读；关闭窗口的规定行为成立 | 不能证明任务 RGB observation 已接线 |
| 离屏 RGB | camera capture 请求或 `render_mode="rgb_array"` | 返回真实、带 identity/clock/completion 的 owned 或有 lease 的帧，布局/颜色/设备和期限明确 | shape 正确或全零缓冲区不能证明 capture 成功 |
| 同步任务 observation | 构建时声明固定的 task cameras 与 RGB 字段 | reset 首帧及每个正常 step 的 observation 自动包含该 boundary 的新图；不要求调用方另调 `.render()` | UI 相机、UI 帧率或 generic Env renderer 不自动等于 task sensor |

三个目标逐 route 分别准入；一个 route 可以先缺少窗口，但本路线最终范围必须明确补齐三者。窗口 observer 与 task cameras 默认独立。相机画面不能推进 physics，physics/control 的频率也不由显示帧率决定。

## 请求、回执与字段身份（建议类型，不是生产 schema）

所有值均为有类型、版本化、有限字段的 public contract；拒绝任意 dict、裸 native handle、私有对象或只能由 provider 内部解释的 ordinal。建议复用 `CameraGeometry`、`CanonicalCameraObservation`、`CameraCaptureIdentityV1`、`StateBoundaryIdentity`、`StateSampleClock`、`StateViewLifetime`，在同 owner 中以 additive 版本扩展，不重写旧 Artifact/Scene/Execution codec/hash。

| 建议值 | 关键字段 | 生产者 → 消费者 | 要回答的问题 |
| --- | --- | --- | --- |
| `RenderRequirementsV1` | Artifact/Scene/source-closure IDs；可视 asset/representation IDs；entity/frame 映射；route；observer/task camera 配置；灯光/材质；window、RGB、device/context/worker、batch 布局；required/optional；采样 cadence；buffer 生命周期要求 | Core 汇总 → admission | 所有 physics、Controller、state、sensor、renderer、batch 和 App 初始化要求能否在 native build 前共同评估？ |
| `RenderCapabilityAssessmentV1` | 每项 provider-native API、Core adapter、依赖版本/设备、精确证据等级；`supported/unsupported/unknown`；`implemented/not_implemented/unknown`；`available/unavailable/unknown`；检查阶段、reason、evidence ref | adapter/admission → Core | 哪些是公开能力，哪些只是设计或未验证？unknown 的 required 项如何拒绝或延迟到 build 核对？ |
| `RenderBindingReceiptV1` | route/materialization/config/topology generation；scene/model/context/App/worker owner IDs；视觉 binding 与 frame convention；requested/realized camera/output；共享 lease 或独立 visual model 标记；静态/build 检查结果 | adapter → Env/Core | 精确构建了什么；谁拥有资源；哪个输入 frame/entity 对应哪个 renderer object？ |
| `RenderUpdateReceiptV1` | `StateBoundaryIdentity`；来源 state revision；拓扑/材质 generation；转换/更新完成或 fence；async ticket（若声明支持）；changed/rebuilt bindings | adapter → Core | renderer 是否已消费所请求的完整、同步 physics boundary？ |
| `FrameCaptureRequestV1` / `CapturedFrameV1` | env/worker/row/camera IDs；episode/reset sample/control step/state revision；capture phase/clock；camera config revision；renderer/materialization/topology generation；像素存储 owner、layout/device、颜色约定、lease/expiry/fence | Core ↔ adapter | 这张图来自哪个状态与相机？何时完成？何时失效？谁必须 copy/retain？ |
| `PresentationReceiptV1` | requested/presented boundary、window ID/generation、event pump result、dropped/late frame、closed/display-lost 状态 | adapter → Env | 展示了哪一帧；事件是否只改变 observer camera/window 状态？ |
| `RenderCloseReceiptV1` | 已释放/未释放资源 IDs、lease generation、first error/secondary cleanup errors、old binding/frame invalidation、owner close result | owner → Env | 谁尝试关闭了什么；共享资源是否仍由原 owner 持有？ |

Identity 必须能连接 artifact、source closure、execution/materialization、env instance + row、episode、reset sample、control boundary/state revision、capture phase/clock、camera geometry/config revision、renderer route、topology/config generation 及 worker。对外发布刚体 pose 时写明 world/local/parent frame、body origin 或 COM、m 单位、handedness、quaternion 顺序；不能把 free-body 7-position/6-velocity 猜成 scalar qpos。非刚体未来扩展须有 typed deformed mesh/particle/volume、representation mapping、topology revision、device/layout/completion 和生命周期；本版不要求实现它。

## 双向操作与当前 owner

| 操作 | Core 输入 | adapter 的正向反馈 | 副作用与失败边界 | 当前 caller / 最小改动位置 |
| --- | --- | --- | --- | --- |
| query / requirements | 合并任务 source closure、physics/Controller/state、视觉表示、相机、输出、batch、设备、window/App/context/worker 需求 | 按目标逐项 assessment；缺项、精确依赖/设备、公开 API、检查阶段、reject reason；无原生副作用 | required `unsupported` 或静态 `unknown` 拒绝；能由明确适配器 build 证明的项可列为 pending check，但 provisional build 不得对 episode 报 ready | `SelectedReferenceEnv._reset`、registry/config、现有 admission 与 `TaskEnvRenderProvider`；将 renderer 需求并入既有 admission owner |
| prepare / bind | 已准入的 source closure、scene/asset representation、具名 entity/frame mapping、camera/config、已冻结 observation/batch 规格、owner/device 要求 | binding receipt、requested/realized 映射、build findings、资源 owner/lease、数据传输与限制 | 共享 scene 不改变 physics/App/model owner；独立 visual model/data 只允许渲染与所需 kinematics，不得执行第二 physics；半构建清理不完整进入 faulted | 复用 RuntimeSession/provider materialization、source receipts 和 Env；新增 typed renderer receipt，不建平行 manager |
| update | 同一个已发布的 typed state boundary/readback、mapping generation、完成要求 | 更新后确切消费的 state revision/topology generation、转换结果、完成 fence/ticket、拒绝/重建项 | 必须等多 solver 的整场景同步 completion；不读私有 solver storage；renderer 不改变 live physics state；stale state 必须拒绝 | `SelectedReferenceEnv` observation path 与 `DynamicCameraObservationConsumerV1`；扩展公共 typed visual-state binding |
| capture | camera ID/config revision、env/row、目标 boundary/capture phase、RGB 要求、deadline/ownership | `CapturedFrameV1` 或具名失败；实际 realized camera、identity/clock、HWC layout、RGB/color/range/dtype/device、completion、owned/borrowed 期限 | 不完整异步帧不可消费； required 缺帧不能回旧帧/零图；跨 lease/worker/Recorder 保留时 copy 或 retain | `DynamicCameraObservationConsumerV1.capture`、canonical observation assembly、Recorder 输入；reset 和 step 的 capture phase 需分开表达 |
| present / event | 当前完成帧、observer camera/window policy、是否允许交互 | `PresentationReceiptV1`、窗口事件、observer camera 更新 | 仅允许改 UI camera/window；不改 task camera、物理状态、episode 或任务时钟，除非构建时显式共享 camera 并记录 | `TaskEnvRenderProvider.render_human`；保持 `.render()` 是 UI owner，task capture 由 observation 调度 |
| reset / rebind | 完成静态 preflight 后的新 route/config、reset sample、resource generation、固定 obs spec | 新 binding receipt 与 reset 首帧；旧 binding/cache/lease/frame 的显式 invalidation；失败副作用 receipt | episode state 不迁移；A→B→A 走完整 rebuild/reset。first native effect 后失败 faulted；不得发布旧 episode frame | `SelectedReferenceEnv._reset` 先 close 旧 consumer 的现状须保留为已发生副作用事实；未来把静态拒绝前移，5c 验证 |
| close / failure | owner-scoped close/release 请求、错误上下文与当前 lease generation | 幂等 close receipt、逐项释放情况、旧 view 失效、primary/secondary failures | renderer 不关闭借用的 shared scene/App/model/context；先停止 capture/present，再释放 renderer-owned buffer/model/window/lease，最后由原 owner 决定关共享 App/worker | Env 汇总 cleanup；renderer session 管自有资源；per-worker `IsaacSimAppOwnerV1` 最终关闭 App |

### 两种 scene 接入路径

1. **Native shared-scene binding：**Physics adapter 是 model/scene/App 的唯一 owner；renderer 获得限权的 typed binding/lease，只能读取已同步发布的 visual state，或调用经批准的公开 render-only 更新。共享不 transfer ownership。Core/Agent 从不拿 native pointer。若厂商只提供私有 scene access，则该组合在公开 adapter/access protocol 前保持 unsupported。
2. **Independent renderer-only model：**renderer owner 从相同 source closure 构建 visual model/data，按公开 named pose/state 更新；必要 kinematics 可运行，但不得调用第二个 solver/physics step。比如 GeoPhys→MuJoCo 路线应把 MuJoCo model/data 明确标记为 render-only，写入公开 floating-body transform；不对其进行 `mj_step`，也不修改 live GeoPhys state。当前动态 projection 只支持 scalar joints 并拒绝 free joint，所以 PickCube 浮动方块须在 5a 扩展 typed Frame pose 与 mapping 后才进入候选。

renderer 与 physics 的共享 binding、同一 capture frame 和 batch image buffer 各只有一个明确 owner。lease 需含 generation、可用操作、device/layout、expiry event/fence；不能把原始 GPU/native handle泄露给 Agent。跨 worker/process 传输若不能延长原 buffer，则在发送前 copy 到明示 transport-owned storage。

## Camera、render API 与时序

Camera 固定字段至少包括稳定命名、mount entity/frame、相对 transform 方向、position 单位与 handedness、quaternion 顺序、intrinsic/FOV/projection、resolution、near/far clip、通道/颜色空间、dtype、range、layout、device、owner/lifetime。构建固定字段与 reset 可变化字段分别声明；缺值不静默套用默认。task camera geometry/count、observation shape/dtype/semantic 固定到 env 构建契约，允许 reset 重采样实际 extrinsics 时要把值绑定到 episode identity。窗口尺寸和 observer-camera 拖动不改 task camera。

建议调用外形（仅设计值）：

```text
Env(render_mode: "human" | "rgb_array" | null, observer_camera: CameraRequestV1?, task_cameras: tuple[CameraGeometry, ...]?)
render() -> PresentationReceiptV1 | OwnedRGBFrame | None
reset(seed?, options={"renderer": route, "controller": selection, ...}) -> (observation, info)
close() -> EnvCloseReceiptV1
```

`render_mode` 在构建时固定，沿用 metadata 声明；`human` 的 `.render()` 呈现最新已完成状态并泵 UI 事件，`rgb_array` 返回 observer view 的真实 RGB owned copy/明示 lease，`None` 不承诺 UI 输出。没有 renderer 的 state-only route 若仍接受 `None`，显式查询窗口/RGB 不可用；构建时请求 required output 则拒绝。renderer reset 不能改变已有 observation schema/shape/dtype。reset options 的 route/controller 是项目明确扩展，不能宣称所有 Gymnasium/RL wrapper 兼容。Gymnasium 参考定义了构建时 render mode、metadata 与 close 的惯用边界；项目需要另外定义 reset/rebind 与同步 task sensor。

**强制 task-RGB cadence：**每一次成功 reset 的 observation 取该 reset 初始化/readback 后的边界；每个正常 step 的图像对应该 interval 完成后的新状态；所有 required cameras 对齐同一 `StateBoundaryIdentity` 与 capture phase/clock。不得以未声明的一帧延迟、降采样或调用方另行 `.render()` 满足要求。physics/control cadence 与 UI FPS 分离。Recorder 记录图像时使用同一 identity，评价可以并行计算，但在所需 state 与图像都完成前不能发布完整 transition。

| 调用 | 目标时序 | 同一状态重复 render |
| --- | --- | --- |
| reset 首帧 | route build/bind → reset write/readback 完成 → publish reset state (control_step=0, reset_sample=n, phase=`reset_initial`) → visual update/fence → 每台 required task camera capture/fence → observation/Recorder → 返回 | 不推进物理；同相机 config 与相同 boundary 可按明示缓存策略复用 |
| step 图像 | command ack → physics interval 全部完成 → public state boundary/revision → visual update/fence → cameras capture/fence → observation/evaluation/Recorder → 返回 normal transition | 同一 boundary 可复用；不能把 capture 当新的 physics sample |
| reset A→B→A | preflight B → old task consumer/camera stop+close → bind B 新 generation → 新 episode reset/readback → capture 首帧；再次 A 同样重建 | A 的旧缓存/帧/lease 不可跨新 materialization、episode 或 camera revision |
| standalone `.render()` | 读取最新完整公开 boundary → observer camera update/capture/present → receipt | 不调用 physics advance；若无有效 state，按明确 none/error 行为答复 |

**当前时钟缺口：**`CameraGeometry.capture_phase` 目前由 `CameraObservationConfigV1.geometries()` 固定为 `post_control_step`，而 reset 初始 observation 也调用同一 consumer，并且 `CameraCaptureIdentityV1.validate` 只接收 `post_control_step`。因此目前 identity 无法区分 reset-initial 与真正的 post-step capture。5c 必须以调用边界传入 capture phase 并扩展 identity/验证；不得据现状声称该语义已验证。

若 App `update()`、render/present 或 camera warmup 可推进 physics，路线必须证明公开 pause/render-only 路径，或拒绝 task observation 模式。warmup 必须在正式 reset/readback 前显式记账，正式首帧仍从该 reset boundary 生成。当前 Isaac F06 为 headless 且 `enable_cameras=False`，不能作为 camera 支持；不得为本设计启动 App。官方 Isaac 6.2 文档将 SimulationManager stepping 与 RenderingManager/Replicator rendering 分开描述，实际所需 experimental RTX camera API 和 exact installed build 必须在未来包重新核对。

## RGB、缓存与失败语义

Canonical RGB observation 至少公开 H×W×3、RGB channel、明确 sRGB/linear 约定、`uint8 [0,255]` 或指定浮点归一化契约、HWC/CHW、device、连续性要求、capture phase、state/camera identity 和 storage lifetime。不同 renderer 通过同一个 CanonicalCameraObservation owner 归一；未定颜色/数值转换属于 5a 决策，不可用默认隐式转换。现有 Dynamic consumer 输出 HWC `float32 [0,1]`；协议不据此推断所有 provider 都满足。

缓存键必须联合 route/materialization、env/row、episode/reset sample、state revision/control boundary、camera config/extrinsics revision、topology/config generation 和 output format。下一步/重置/renderer rebind/topology 改变会使旧项失效。借用帧跨下一次 write/advance/reset/close/lease release 立即失效；Recorder、vector return 或远端 consumer 需保留时明确 copy/retain owner，并等待 device fence。异步返回值在 completion 之前不是图像。

| 条件 | required task RGB / physics | observer window | Core 返回/状态 |
| --- | --- | --- | --- |
| 静态 query/build 不匹配，尚无 native effect | reject | 若独立可继续 | admission failure；无 transition |
| initial partial build/cleanup | 无可见状态 | 未呈现 | 保留 cleanup receipt；不能报 ready |
| reset/step 后 required update/capture 失败 | physics 若未推进可拒；已推进时保留完成 interval/clock 与 fault | 不得拿 UI 帧替 task RGB | faulted；不得返回 normal transition、旧帧、零图，也不承诺 rollback |
| optional camera 不可用 | typed unavailable + reason，且 only if schema declared optional | 独立 | 不补零；required/optional 在 build 固定 |
| 用户关闭窗口/display lost | 不影响独立 task capture | 停止 present；记录 display event | physics/episode 可继续，除非此路线公开 App/window 生命周期无法分离，此时以 typed route fault 明确通知 |
| borrowed/async completion 未就绪 | 不得消费 | 不得 present incomplete | 等 fence 或返回 pending/error；不能伪造成功 |

## 首批路线与当前能力（静态审计，不是验证）

| physics route | renderer/capture 路径与公开入口 | 当前状态 | 1d/后续最小工作与 owner |
| --- | --- | --- | --- |
| MuJoCo CPU | task observation candidate：`MuJoCoCameraSession` 使用独立 `mujoco.Renderer`/OpenGL，从静态 triangle mesh 建 model；generic UI 另由 `TaskEnvRenderProvider` → visualizer | p1_4 `p1_4_native_camera_cpu_v0` 是 static same-provider camera；当前 selected PickCube renderer=none；generic UI 不等于同步 task RGB。Core 与 GeoPhys 声明 MuJoCo 区间冲突 | 5a：从同一 source closure 具名构建及逐帧更新；5b：UI/observer+camera lifecycle；5c：reset/post-step identities 和 RGB obs。3a 先厘清冲突依赖环境 |
| GeoPhys CPU | `GeoPhysCameraSession`：GeoPhys `RayCamera`/`FrameBuffer`/`EnvironmentPipeline`/`LightingSystem`/`MeshPipeline`/`RayTraceEngine`/`TonemapPass`，CPU Taichi；跨候选是 `DynamicCameraObservationConsumerV1` → `MuJoCoDynamicCameraSession` / MuJoCo native OpenGL | native session 静态 mesh；selected PickCube 没有该同步 native route。Dynamic D03/D04 当前只对 Position candidate、Scene-v3 scalar joints；free joints 明确拒绝。现有 session 不能更新 live typed dynamic state | 5a：public frame/visual binding 与 GeoPhys renderer capability/build; 5b：窗口；5c：state-synchronous RGB。GeoPhys→MuJoCo P2 需 free-body frame mapping/renderer-only transform，当前不支持 PickCube |
| Isaac Sim 6.2.0.0 + PhysX/CUDA:0 | 官方 native camera 候选：Isaac Sim 6.2 sensor/RTX/Replicator APIs；Core 的 `IsaacSimAppOwnerV1` 与 `UsdCoreRuntimeSession` 管 App/session，但无当前 task camera consumer | 精确 App owner 当前 headless、camera-disabled；无 selected PickCube camera/renderer route。官方能力不是本仓库 adapter/evidence | 5a：确认 public adapter + exact 6.2 experimental camera API/依赖/admission；5b：window/display 与 per-worker App lease；5c：synced capture/camera data/fence/RGB。不能以 viewport availability 代替 task RGB |
| GeoPhys CPU physics × MuJoCo native OpenGL renderer | 已有 `MuJoCoDynamicCameraSession` 从 source closure 构造 render-only MuJoCo model，写 scalar qpos/time，kinematics/camera/light/update/render；不 `mj_step`/`mj_forward` | 当前 dynamic candidate `best_effort`，仅 scalar Scene-v3；PickCube free cube 不可用；历史 evidence 对旧 GeoPhys pin，当前 pin 未验证 | 仍为必达真实跨组合候选，不缩减目标。5a owner `DynamicCameraRenderSourceV1`/typed state→visual mapping；5c owner consumer/Env；未来用无第二 physics advance 的 oracle 检查 free body transform/capture boundary |

对每种 native route 分别核实 provider 原生 public API、Core adapter、dependency/device readiness、精确 task/build 证据；当前没有的 capability 写 `unknown/not_implemented/unsupported`。先静态 query，再仅当有明确 adapter/build check 时做 provisional native build；全部 required gate 通过后才允许 episode。`.render()`、窗口与离屏路径若不是 task RGB 必需，可分别列出阶段，但 v2.1.1 的三种完成目标都必须有实施 owner。

## Batch、terminal frame 与关闭

图像语义的外层维度固定为 `env → worker → local row → camera → image`。定义逻辑 env 顺序与 worker/row 映射的 typed receipt；native merged batch 与 process deployment 是独立可组合轴。每行 image identity 必须匹配它自己的 state boundary；worker 只有单帧时不得复制该帧标成所有 env 的新 observation。用户 `.render()` 选某个 env 只影响 observer view。

沿用现有 same-step autoreset：一个 step 中先取得 done row 的 terminal state/frame；保存 `terminal_observation`；再只 reset done rows，产生新的 reset obs/frame 与 `reset_info`；返回给 learner 的 done row observation 是新 episode reset observation。terminal frame/state 属旧 episode，reset frame 属新 episode；Recorder 用各自真实 identity。`env-0` 未 done 时 state/clock/controller/episode lineage 不变。若终止帧要越过下一次 batch buffer 写入保留，先 copy/retain 到明确 owner。storage view 失效不意味着未选 row 物理状态变了。

当前 `_step_and_autoreset` 已按 done row 保存 `terminal_observation`、调用 mask reset 并返回 reset obs + `reset_info`；`RemoteBatchVecEnv.get_images()` 会把一个 worker render frame 重复给各 env slots，不能代表 per-row task camera。未来 `get_images`/observation 只能由明确 per-row camera adapter 提供，不要重用复制帧为真实性证据。

关闭顺序：停止新 capture/present 和异步提交 → wait/cancel 且记录 in-flight ticket → 使该 route 的 frame/cache/binding lease 失效 → renderer 关闭自有 window/buffer/render-only model/context → 释放 physics/App 的借用 lease → 原 owner 按引用计数决定关闭共享 scene/App → worker owner 等清理回执再退出。重复 close 安全且只由原 owner close 自有资源。App/worker loss 时报告无法观测的资源；不声称全清理成功。partial construction 与 first-effect rebuild failure 沿用 lifecycle-and-data fault 边界。

## 1d 后续实施 oracle

这些是将来 implementation packages 的验收建议，不在本包运行：

- query 对不支持的 renderer/source/free-joint/asset representation 在 native effect 前拒绝；能力行能区分 provider API、adapter、dependency 与 evidence。
- 每个 `RenderUpdateReceiptV1` 与输入 state boundary 对齐；capture phase 在 reset-initial 与 post-control-step 间不同且验证通过；连续 capture 的 control clock 不变。
- 同一 RGB case 检查真实非空画面、oracle region/object pose、channel/range、camera extrinsics 与 identity；不得将 shape 或零缓冲当成功。
- App.update/render/camera warmup 的 physics clock 前后相等，或该 route 被拒绝。
- required capture 在 physics completed 后故障时保存 partial-progress fault，不返回 normal transition；borrowed buffer expiry 后拒绝 stale access。
- 两 env/两 camera same-step terminal/reset case 校验四组独立 identity；未选 env lineage 不变；A→B→A 校验 resource generation 和旧帧失效。
- 共享与独立两路径各校验 owner/close receipt；重复 close 不重复释放共享 App/scene；无第二 physics step。
