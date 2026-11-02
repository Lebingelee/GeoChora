# R04 — Dynamic Camera → Public Observation / Recorder

状态：REVISED_DRAFT；R04a attempt001 原23项provider-free S1通过后经Sol复核为CHANGES_REQUESTED；attempt002 已修复 capture 请求绑定与 H5 独立 state/clock/episode 锚点，定向 provider-free S1 为33 passed，Sol已复核接收为ACCEPTED_S1_BOUNDED。R04b attempt002 已获Sol有界接收 `ACCEPTED_BOUNDED_S2`；R04c attempt001 的同Env双相机 H5 S3 已完成，当前为 `R04C_BOUNDED_CAMERA_H5_S3_PASS_PENDING_SOL_REVIEW`。required 候选交集为 GeoPhys a53 CPU physics × MuJoCo 3.8.1 Native OpenGL/EGL × 既有单 Panda Position source，双 fixed/hand-mounted RGB/Depth/Entity mask。不把新 Assembly source 默认纳入 Camera 支持。

## Owners 与真实消费断点

复用 [typed-state](../../../../../task_env/artifacts/state.py)、[CameraSession API](../../../../../task_env/render/camera/api.py)、[dynamic renderer](../../../../../task_env/render/camera/mujoco.py)、[ObservationBuilder](../../../../../task_env/observations/state.py)、[SelectedReferenceEnv](../../../../../task_env/tasks/reference_env.py)、[Recorder](../../../../../task_env/recorders/recorder.py) 与 [H5 owner](../../../../../task_env/recorders/h5.py)。

当前独立 CameraSession pairing 已有有界 capture/隔离/关闭证据，[D 开发记录](../Phase_II/D_Development_Record.md)保留其原身份；Position public Env 未显式配置时仍为 state-only。generic SensorObservation/ObservationBuilder 的 depth 为 provider-defined passthrough，不等于 advanced CameraSession 的 Optical-Z/Entity-mask。R04a 已在现有 Observation owner 增加显式 opt-in bridge 与 Env lifecycle 接线；R04b attempt002在同一Env完成有界S2并获Sol接收，R04c attempt001完成同一条公开Env路线的双相机H5 S3读回并等待Sol复核。各结果仅覆盖下文标明的冻结交集。

## R04a 实现边界（2026-10-26）

`panda-position-servo-candidate-v1` 接受显式 `camera_observation` mapping；未选择时，state-only observation/schema、source/Controller identity 和导入无 native 初始化保持原样。opt-in 仅允许一个现有单 Panda Position Profile，production 几何固定为 321×241、D04 RGB/optical-Z/Entity-mask、固定相机与 hand-mounted 相机的 canonical 顺序；每个 `CameraMountRequestV1` 必须带明确 parent Frame 和 proper rigid mount transform，配置在 source workspace 创建前验证。它不准入新 Assembly source、其他 Provider/backend 或任意 renderer profile。

新增 `CameraObservationConfigV1`、capture metadata 与 boundary 值复用现有 `CameraGeometry`、`CameraCaptureIdentityV1`、Calibration、Canonical Entity LabelMap 和 `DynamicCameraRenderSourceV1`。`DynamicCameraObservationConsumerV1` 在已发布 typed state 后延迟创建两个现有 CameraSession，只读 capture；相同 boundary 复用缓存。Env 在 reset/构造失败/step fault/close 时拥有并关闭 consumer；post-step capture/observer 失败沿 C03a latch 保留实际 progress，不伪造 transition 或回滚。RGB HWC float32、Depth H×W float32 米制 optical +Z、Mask H×W uint32 进入已有 public `observation_space`/`ObservationSchema`/info contract。

Generic H5 v3 保持原 ABI；opt-in 时追加 `camera_observation_contract_v1_json`、`camera_observations_v1_json` 与 `camera_recording_binding_v1_json`。binding 锚点由 writer 从实际 Position state boundary digest、reset/transition info clock、独立 reference profile、EpisodeOutcome 和 structured controls 生成；reader 从真实 state dataset、独立 profile 与现有 typed control/outcome readers重建并交叉核对。缺少必需 state digest、binding sidecar、未知 binding 版本、episode/clock/control 顺序不一致均 fail closed；写入校验失败不发布最终文件并清理临时文件。reader 继续核对 T+1、source/capture/boundary/calibration/label-map、RGB CHW uint8 既有量化布局、Depth/mask dtype 与 mask digest。provider-free synthetic S1 验证配置、请求身份/calibration、输出空间、缓存、故障关闭与 H5 正负例；attempt002 定向套件33 passed，Sol已接收其S1有界出口。真实 MuJoCo/EGL renderer、真实 Env reset/step 与同文件实际相机读回均为 NOT_RUN，分别留给 R04b/R04c。此 S1 不证明 camera native/runtime 或 P99 gate 已通过。

## Sol复核与定向返工（2026-10-26）

Sol核对18文件diff、16项原包输出及18项tracked摘要，重跑原定向S1仍为23 passed；但纯S1反例复现两个拒绝缺口：consumer接受同camera ID/尺寸而mount偏移0.2m的自洽capture；H5 reader接受camera sidecar与真实state boundary digest或finalized episode outcome不一致的文件。R04a出口尚未接收，下一包为同分支attempt002的有界实施修正，不新增研究轮次或native实验。复核入口为本机ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r04a_001/`；原attempt001与通过项保留。修复后按原表交Sol复核，正常下一行R06a，R04b/c仍未启动。

## R04a attempt002 定向绑定修复（2026-10-26）

`DynamicCameraObservationConsumerV1` 在创建 capture sessions 时固定实例实际 config、artifact/source、execution 与 manifest 请求上下文。每个capture的 `CameraCaptureIdentityV1` 必须等于从这些独立输入生成的期望身份；calibration还须等于 `resolve_camera()` 对同一请求几何与当前 typed publication 的结果。请求mount/source/execution或parent Frame不匹配时，在更新公开leaf/cache之前拒绝，继续使用现有 Env fault/cleanup owner。

H5 camera extension 新增 strict `camera-recording-binding-v1` sidecar，不改变 Generic H5 v3 根ABI。writer在原子发布前校验每个 T+1 observation 的32-byte state boundary digest、reset/transition identity与clock、capture/episode、typed final outcome、每个 transition 的 Position control source boundary/clock和 action顺序。reader从 H5 state dataset、独立 reference-profile metadata 与现有 typed control/outcome readers读取实际锚点交叉核验；sidecar缺失、未知版本或不一致时 fail closed。零transition外部Stop和多transition记录均保留为正例；失败输出仍由现有 temporary→`os.replace`路径拒绝并清理。

attempt002使用 provider-free 合成capture/H5定向S1，33 passed；报告、命令日志与原始小型H5正负例见 ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r04a_002/`，Sol已接收其S1有界出口。未运行真实 renderer、MuJoCo/EGL、public Env S2或camera H5 S3；R04b/c仍PLANNED，P99 required与R05a状态不变。

## Sol attempt002 复核结论（2026-10-26）

审阅实施提交 `72b5274e2adc438d2df165bd0190963909705630` 的10文件差异、生产metadata路径及33项S1日志，F01/F02已关闭，接收为 **ACCEPTED_S1_BOUNDED**。Sol复用交付的小型H5独立检查2个合法正例及11个拒绝反例，全部符合预期，未重复生成资产。24项输出与10项tracked摘要、8项保护输入、11份phase文档hash核验通过。文档validator仍为相同148项既有错误，不构成全仓PASS。复核入口为ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r04a_002/`；attempt001与失败日志保留。下一行R06a；真实native、R04b/c、S2/S3与Qualification均未授予。

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

## R04b attempt001 Sol复核（2026-10-28）

独立camera分支`codex/phase-ii-01-camera`的实现提交`f7bc956`、`37ca3ee`、`27fad20`共4个诊断/测试文件，未改生产camera合同。Sol核149项evidence hash并重跑24项provider-free tests通过，仅接收S1和partial reset/capture事实，**S2_NOT_ACCEPTED**。两个启动额度已用：首进程CLI相对导入预检失败；次进程完成一次GeoPhys materialize/reset和两相机RGB/depth/Entity-mask捕获后，因Contract tuple与JSON list直比失败，0outer/0physics substeps。比较及异常Renderer.close计数修正未native复验；原离线reader缺boundary行而失败。

另有明确未走到的worker接线错误：`CanonicalStateViewV1`没有直属`scene_identity_hash`，应通过`view.boundary.scene_identity_hash`。下一包R04b attempt002在同分支修正并先让实际worker成功分支、序列化及独立reader的provider-free全链通过，再使用新有界native窗口。旧失败原件保持；不以新比较helper测试替代全链、不自动进入R04c/H5、不改oracle/provider/预算。主develop-full的F01下载由维护者接管，Luna1独立R07a审计，camera分支不混入主分支安装提交。复核入口为ignored`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r04b_001/sol_review.md`。

## R04b attempt002 bounded S2 execution (2026-10-28)

在同一 camera 分支，输入 HEAD `90f89cd67414c148bf547952612cf301cd4ec99d` 上完成诊断 runner/reader 修正；native freeze 为 `8ff099640c9b0282ce224282a957e23e0a47656c`。production Camera/Env API 与 TaskArtifact 未改。完整 provider-free S1 文件 10 passed，覆盖真实公开 Candidate Env/Controller/consumer 的成功收尾路径、独立 reader 正例与11类语义拒绝、部分构造和关闭计数；此 S1 仅替换物理/GL IO，不作为物理结果。

有界 native worker 1次启动并 exit 0；独立 offline reader 通过。该次冻结交集为 GeoPhys a53 CPU × MuJoCo 3.8.1 Native OpenGL/EGL × `panda-position-servo-candidate-v1`、seed31、2 ms × 5、固定 D04 双相机与0.08 m Position target。结果为2次 reset、24次 public step、120个在成功返回的 runtime-boundary 调用中接受的 substep、26个 boundary、53个 capture（52个 normal、1个 isolation）；clock 独立推导同为120 substeps/0.24 s。双相机 RGB变化、6个光学深度/回投样本、cache零推进、复位身份/图像重复、consumer隔离与 renderer/Env close 门通过。Luna报告状态为 **`R04B_BOUNDED_PUBLIC_CAMERA_S2_PASS_PENDING_SOL_REVIEW`**，尚待Sol复核，不是S2接收、Qualification或task success；截至此attempt时R04c/H5尚未运行或授权。

完整命令、receipt、raw Evidence 与哈希见 ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r04b_002/`。本camera分支不包含或更新main checkout的F01/Isaac安装进展；该状态仍由维护者在主checkout管理。

## R04b attempt002 Sol接收（2026-10-28）

Sol已复核camera分支输入`55e713fd9fdc0b6309facf912976fcb822068432`的实际diff及原始证据，接收**`ACCEPTED_BOUNDED_S2`**。105项输出hash、9项冻结输入源码、3项native冻结源码和5项受保护证据全部匹配；`derive_camera_config`、光学depth oracle与10个冻结常量的AST比较未变。Sol在新隔离进程调用现有独立reader重新读取原NPZ/JSONL，通过26 boundary、53 capture、24 control的同run证据与原几何/变化/reset/cache/close门，进程未导入TaskEnv/GeoPhys/MuJoCo/Taichi/OpenGL。原件未重写；10项S1与11项拒绝例沿用Luna结果，Sol未重跑测试或启动native。

接收仅限上一节冻结的GeoPhys a53 CPU × MuJoCo3.8.1 EGL、既有单Panda Position source、seed31、2ms×5、两轮12-step、双D04相机交集。120 substeps为24次成功返回的公开runtime step调用所接受的substep数，clock独立推导同为120；不是逐kernel trace。RSS 2,171,637,760 bytes为监督采样最大值，不是interval内硬峰值。四个renderer生命周期各观察到一次close，五次session close含一次预期的重复close。

复核原件位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r04b_002/`。接收记录仅提交camera分支，未合入develop-full；主checkout与R07a冻结窗口保持。**截至该次R04b接收**，R04c同H5相机S3尚未运行/授权；该历史接收不建立Qualification/task success。

<a id="r04c-attempt001-camera-h5-s3"></a>

## R04c attempt001 同Env双相机 H5 S3（2026-10-28）

R04c在输入 `cb6313f117f70678ee7c821e8344d8c595dea5ad` 后实现并冻结于 `72f136c6c089eb0bfc6c4389b3d81441b605c28f`；实现复用现有 Position Candidate Env、TransitionRecorder、Generic H5 v3 writer 和 public semantic readers。定向 provider-free S1 文件为 **8 passed**，R04b共享runner回归为 **10 passed**；S1替换底层 physics/GL IO，不作为物理结果。六类失败注入（post-step capture、Recorder append、H5 metadata、H5 dataset、atomic replace、Env close）均走fail-closed路径。此前一条R04b回归命令因缺少GeoPhys `PYTHONPATH` 失败，修正执行环境后的最终回归通过，原始失败日志保留。

唯一有界native worker在共享flock保护下启动一次并exit 0；父supervisor持锁覆盖worker组生命周期并释放。固定路线为同一 `make_env('panda-position-servo-candidate-v1')`、GeoPhys a53 CPU × MuJoCo 3.8.1 NVIDIA EGL、seed31、2 ms × 5、两轮各12个public step。产生两份同run `task-env-h5/v3` 文件，各12 transitions/13 observations、双D04 RGB/depth/entity-mask/state/action/Target/Ack与sidecar。两轮按 `stop('external_stop')` 和 `finish_recording('external_stop')` 收尾；实际EpisodeOutcome为 `terminated=false`、`truncated=true`、`task_success=false`。这是该有界外部停止的生命周期结果，不代表horizon耗尽或task success。

Native receipt记录2 reset、24 outer/public step、120 accepted physics substeps（成功返回的公开runtime-boundary调用计数）及独立clock推导120/.24 s；52个public双相机capture加1次isolation capture。Env close为1/1成功，renderer close为4/4，session close为5/5。监督器共37次资源采样，最大采样process-group RSS为2,121,879,552 bytes（约1.976 GiB）；这是采样最大值，不是区间硬峰值。两层新进程reader分别通过public H5 semantic校验和raw写前witness逐帧/状态比较；native派生22项H5篡改均被拒绝。最终门状态为 **`R04C_BOUNDED_CAMERA_H5_S3_PASS_PENDING_SOL_REVIEW`**，不授予Qualification或task success，也不推广至其他provider/camera交集。

Native结束后发现worker按既定收尾记录68项source workspace哈希后删除了source副本。2026-10-28 15:23:10 UTC，收尾阶段从R04b attempt002保留的同路径source副本恢复到R04c输出：逐项按原 `source_workspace_manifest.json` 核验并在复制后复核，68/68、34,307,151 bytes相符。原R04c manifest、删除disposition、worker/native receipt和日志均保持原字节；恢复事实与来源另记在 `native/worker_001/source_workspace_recovery_receipt.json`。该恢复发生在native完成后，不将其伪记为native期间仍有source副本。

Sol并行只读复核报告24项输入源码与`cb6313f` bytes、19项native冻结源码与`72f136c`/当前文件、8项保护证据均匹配；用实际环境Python新进程重新读取两份原始H5，semantic与raw reader均PASS，raw无TaskEnv/provider/engine导入，semantic无engine导入。复核中的两次错误`.venv`路径命令exit127，未启动Python/native；随后改用receipt指定Python完成成功读回。该只读核对不改R04c pending review状态，Sol最终接收仍待其完成收尾审阅。

完整报告、Evidence索引、命令和输出哈希清单位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r04c_001/`。此结果只覆盖上述固定task/provider/backend/seed/horizon交集；不改变R04b接收事实、原7/22 DAG或P99 required，也不涵盖R04其他source或Qualification。

## R04c attempt001 Sol接收（2026-10-29）

Sol完成对camera输入HEAD `150dae45dcdd00d08cd1b7c37aebc50266a9656b`的最终复核，接收 **`ACCEPTED_BOUNDED_S3`**。162项输出清单全部匹配，目录含manifest共61,227,398 bytes，低于256MiB；24项输入源码Git bytes、19项native冻结源码与当前bytes、8项保护证据、12份phase Markdown hash一致。68项恢复source共34,307,151 bytes与原native manifest及R04b保留件逐字节相符；恢复receipt保留来源/时间，原删除记录和native/H5/reader原件不改。

复用Sol此前新隔离进程对两份原H5的独立semantic/raw读回：当前H5 hash仍匹配，semantic未导入engine，raw未导入TaskEnv/provider/engine。复用Luna已记录的8项R04c S1、10项共享R04b回归及22/22 native派生拒绝；本次没有重跑native或测试套件。接收只限上述GeoPhys a53 CPU × MuJoCo3.8.1 EGL、单Panda Position、seed31、2ms×5、双D04、两轮12/13交集；external_stop的truncated=true/task_success=false及RSS采样限制不变，不构成Qualification。

复核收据和报告位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r04c_001/`。camera分支未合入develop-full。R04有界出口可收口；R05b仍被R05a Provider正式合同阻塞。R06b为可独立准备的后继，历史missing raw/phase decision gate仍未关闭；尚未派发新的实现/native包。
