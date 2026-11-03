# G01 阶段 1 协议联合实施映射（实施基线）

状态：`APPROVED_IMPLEMENTATION_BASELINE`，2026-11-03 维护者确认；见[确认收据](../maintenance/20261103_protocol_baseline_confirmation.md)。本文是后续实施的语义基线；新类型名称和字段仍须由所属子阶段工作包映射到现有 owner，不代表生产 schema、API 或运行能力已经实现。

v2.1.0 tag与旧Artifact/Scene/Execution codec/hash保持；阶段2先有成功参考，不因本次修订重排阶段3–6。数值容差、生产类型与签名由所属冻结包确定。

## 交付顺序与阶段门

| 顺序 | 范围 | 进入条件/输出 | 本包要求 |
| --- | --- | --- | --- |
| 1a–1d | 阶段 1：owner、表示、physics/control/render 协议设计 | Sol/维护者有界审阅各独立包；维护者已确认语义实施基线 | 保留四次交付／审阅历史；下一候选2a，由维护者手动转发 |
| 2a–2c | 成功参考、生命周期/记录基线 | 在 3a–6c 前先有小而真实的成功参考 | 不因接口设计先做 3a/5a；保留该前置 |
| 3a | execution/config/codec/admission | 严格路由身份、静态能力与依赖冲突处理 | render requirements 并入现有 admission owner，不建立 renderer manager |
| 3b | Scene/asset representation/codec/translation/state receipt | 新版 typed representation 兼容旧 decoder/hash | 增加具名 visual/frame mapping、pose 与 build receipt，保留旧版本拒绝行为 |
| 3c | lifecycle/reset/advance/publish/close | pure preflight、first-effect fault、public receipt | 承载 shared lease、rebind、capture barrier 和 fault lifecycle |
| 4a–4c | effort/model/controller/action spec | Controller 需求可由 provider query/readback；reset 可换 action spec | renderer requirements 消费已有完整 state，不重新定义 controller semantics |
| 5a | render source、capability、native 与 cross build | 三 native 候选 + GeoPhys×MuJoCo、精确 API/dependency/build oracle | 明确 renderer adapter/build receipts、free-body/frame support、App/device/window dependency |
| 5b | window/observer camera/present/close | human lifecycle、camera UI、per-worker App lease | observer/task camera 分离；display loss 不静默改变 task camera |
| 5c | RGB capture、同步 task observation、fault/cache | reset-initial 与 post-control phase、owned/borrowed image | 每次 reset 和正常 step 完整 capture；terminal/reset frame 身份；无旧图/零图 |
| 6a–6c | native batch、multi-provider、parallel layout/autoreset | 至少两 physics provider 且至少一 native batch | env→worker→row→camera mapping、mask reset receipt、same-step terminal/reset image |
| 7a–7c | reuse/final/integration | 依赖前段完整实现 | 当前不授权、不启动 |

## 要求 → owner → 最小修改 → 后续 oracle

| 关键要求 | 权威协议/决策 | 当前源码 owner/caller | 最小 additive 修改与旧兼容 | 子阶段 / 将来 oracle |
| --- | --- | --- | --- | --- |
| route、依赖、设备、renderer/camera/window 需求一起准入 | physics-provider query/admission；render-provider requirements | `environment/configuration.py`、`runtime/sessions/api.py` admission/materialize、`SelectedReferenceEnv._reset`、`TaskEnvRenderProvider` | 在既有 admission request 加 source-bound `RenderRequirementsV1` 与逐项 `CapabilityAssessmentV1`；旧 `ExecutionSpecV1` decoder/hash 不变；renderer 不放宽 physics | 3a + 5a；required static mismatch 在任何 native effect 前拒绝；build-only 项必须有 owner/check |
| source closure→mechanical/collision/visual representation 具名映射 | unified-task-representation；render-provider binding receipt | `TaskSourceV1`、Asset/Scene compiler、`RenderVisualInstanceBindingV1`、`DynamicCameraRenderSourceV1.from_runtime_source` | Scene/representation owner 加版本化 entity/frame/asset mapping；保留 v1–v3 decoder/hash；缺失/多义 mapping 显式拒绝 | 3b + 5a；同一 semantic entity 对应正确 renderer body/frame |
| Free body pose/quaternion 与非刚体扩展位置 | unified-task-representation；render-provider update | `JointDefinition`/`TypedFrameStateValue`/`StateBoundaryIdentity`；当前 dynamic source 拒绝 `free_joints` | typed visual update 使用 frame pose，不由 scalar qpos 推断；定义 world/local、COM/body origin、quat order、m/handedness；非刚体只保留有类型 extension slot | 3b + 5a；floating cube pose oracle；无第二 solver |
| physics 与 Controller 必需 state/feedback、render state 共用同一完成边界 | physics-provider、control-and-feedback、lifecycle-and-data | RuntimeSession snapshot/readback/advance；SelectedReferenceEnv observation/step | 在现有 publish boundary 增加 render update fence；不得读私有 solver storage；多 solver 全场景 completion 才可发布 | 3c + 4a–4c + 5c；capture 对齐同一 state revision/sample clock |
| native shared scene vs renderer-only model；一个 owner | physics-provider shared binding；render-provider route | provider session materialize/close、`MuJoCoDynamicCameraSession`、`IsaacSimAppOwnerV1` | typed lease 带 owner/generation/allowed ops/expiry；render-only model 明确 no-physics authority；session close 只释自身资源/lease | 3c + 5a–5b；owner table、重复 close、App 多 lease |
| public `render_mode`/metadata/render/close，observer 与 task camera 分开 | render-provider API; lifecycle-and-data | `BaseTaskEnv`/`TaskEnvRenderProvider`；Selected PickCube renderer none | 保持现有 generic UI caller；新增 receipt/typed mode mapping，任务 RGB 由 observation consumer，不由 UI `.render()` 代替；reset route 是项目扩展 | 5b；human/rgb_array/None 分别验证，window drag 不改任务相机 |
| reset 首帧 phase 与每步同步 RGB | render-provider capture/clock；lifecycle barrier | `DynamicCameraObservationConsumerV1.capture`、`CameraGeometry.capture_phase`、`CameraCaptureIdentityV1.validate` | capture phase 按调用边界传入；reset=`reset_initial`，step=`post_control_step`；补 identity/canonical schema；不改旧历史 receipt | 5c；reset clock 0 与 step 1 identity distinct；每个 required camera 同步 |
| RGB layout/color/device/lifetime/copy/fence 与 cache invalidation | render-provider CapturedFrame；lifecycle data | `CanonicalCameraObservation`、camera sessions `.copy()`、Recorder/Env publication | 固定输出 schema；owned snapshot 默认；借用 lease/fence explicit；cache 加 route/env/episode/state/camera/topology generation | 5c；channel/range/dtype/device oracle；过期后访问拒绝；无 shape-only/zero success |
| renderer/App update 不推进 physics | render-provider present/warmup；physics clock authority | `TaskEnvRenderProvider.render_human`；Isaac `SimulationManager`/RenderingManager boundary；`IsaacSimAppOwnerV1` | 用公开 render-only/pause route；无法分离则 admission reject；warmup 先于正式 reset/readback 且记账 | 5b–5c；capture/render 前后 physics clock 不变或明确拒绝 |
| 已推进后 required image fail 不伪造成功 | physics-provider partial effects；lifecycle-and-data fault; render-provider failure | SelectedReferenceEnv mixed step fault latch、camera close、RuntimeSession advance receipt | structured capture issue 并挂到现有 execution fault；completed interval 和真实 state 保留；不做通用 rollback | 3c + 5c；强制 capture failure 后没有 normal transition/旧帧/零图 |
| same-step autoreset terminal/reset image分离；未选 row 不动 | lifecycle-and-data batch；render-provider batch | `vectorization/parallel.py::_step_and_autoreset`、`vectorization/sb3.py::TaskEnvSB3VecAdapter.step_wait`、`RemoteBatchVecEnv.get_images`、`SceneBatchRuntime.reset(mask)` | typed env→worker→local row map + 每camera image identity；保留 `terminal_observation`/`reset_info`；旧 get_images 重复帧只作 preview | 6a–6c + 5c；两 env×两 camera，env-1 terminal/reset identities 分离，env-0 lineage 不变 |
| 三 native routes 与 cross route 精确而不降目标 | capability-matrix `target_resolution`；render-provider route table | MuJoCo/GeoPhys camera sessions；Isaac app/session owner；admission | 继续保留 MuJoCo CPU、GeoPhys CPU、Isaac Sim 6.2 PhysX/CUDA 三行及 GeoPhys×MuJoCo cross target；按 provider API/adapter/dependency/evidence 拆列 | 5a–5c；各完成目标分别检查；官方 API 不代替本仓库证据 |
| 现有依赖/历史证据 pin 与规范边界 | source-map；capability matrix | Core/GeoPhys manifests、历史 D05 evidence | 当前 Core MuJoCo `<3.9` 与 GeoPhys `>=3.15` 冲突作为 3a dependency blocker；旧 pin cross evidence 不升格为当前 pin；不自动换隔离进程或依赖 | 3a 先确定；native 之前 exact environment receipt |
| protocol baseline/decision trace/旧 caller compatibility | 五份 contracts + `goals/01-protocols.md` | declarations, public APIs, Env, Recorder, vector wrappers | additive typed value version；迁移 caller 有 compatibility note；统一表示/control按当前确认收据修订；旧review/raw不改 | 已由维护者确认为实施基线；2a另有单包且不自动派发 |

## 五协议实施追踪补充

| 关键要求 | 权威协议 | 现有 owner / 最小修改 | 子阶段 / 未来 oracle |
| --- | --- | --- | --- |
| 嵌套Robot通道、7＋2 JointEffort与BodyWrench、typed load扩展及source transmission | control-and-feedback；physics-provider | canonical command/ack、ControlBindingPlan、各 adapter 的 public drive/actuation；明示 q/qdot 与 effort/ctrl 区别、Jacobian 方向、贡献组合与drive owner；不把 position compatibility 算 effort 完成 | 4a/4b；单位/轴/符号/功率、限幅/传动及三后端实际共同命令，非严格 F05 等价研究 |
| Controller 公共模型与测量 provenance/cadence | control-and-feedback | 现有 binding 声明 q/qdot/FK/J/M/bias/contact 等 required/optional 与可替换模型依赖；源/状态 identity、sample age、模型无 physics advance；ACK 不当测量 | 4a/4b；missing required 拒绝、freshness/model-to-live 映射及 actuator force readback |
| reset 更换 Controller/action spec、obs 固定、旧调用方适配 | control-and-feedback；lifecycle-and-data | binding/Env/wrapper 发布 action-space generation、清积分器/滤波/历史；同批布局一致，固定 action wrapper 对不兼容更换显式拒绝 | 4c；旧动作拒绝、新输入可查询、obs schema 不变及 PickCube 修复后复核 |
| 资产数值与语义准入、非刚体预留 | unified-task-representation；physics-provider | 同一 Scene/Asset/compiler/source owner 的版本化字段与 oracle；质量/全惯量/单位/frame/constraint/interaction/reset readback；缺必需表示不静默改资产；非刚体只保留扩展 | 3b；输入物理合法性／native mapping/readback／reset短程行为的具名oracle/容差；required未测不通过；旧 codec/hash不变 |
| 初始/正常/terminal/reset 边界与记录读回 | lifecycle-and-data；render-provider | 一个既有 Recorder；T transitions/T+1 boundaries、frame identity 与 episode/config；terminal frame在mask reset覆写前保留 | 5c/6c；7a/7b 集成复用及独立读回，不用图像 shape 代替真实场景/时序验证 |

## 联合审阅形成的补充（已确认，具体实现待后续包）

- 对 unified representation 建议增加 renderer 消费的具名 `entity/frame/asset representation` mapping 与 free-body visual pose 版本值；不改变 1b 已定的任务语义、旧 codec/hash 或 PickCube 不动作的浮动 cube。
- 对 control-and-feedback 建议把 render update 定义为读同一已发布 state boundary 的 consumer；不得在 `.render()`/App update 中触发 controller compute、command 或 physics advance；effort/feedback采用当前控制协议及维护者7＋2修订。
- 对 physics-provider 与 lifecycle-and-data 的 shared lease、state fence、partial-progress fault、唯一 close owner 做统一术语 cross-reference；避免重复定义 Runtime/Recorder。
- 对 render-provider 与 lifecycle 对 reset capture phase、batch terminal/reset、window close independent from task capture 采用同一身份与错误语义。现有 reset phase identity gap 与 `RemoteBatchVecEnv.get_images()` repeated-frame route 必须作为明确 blocker/owner保留。

外部参考只支持 API 概念：Gymnasium 给出 `render_mode`/metadata 与 autoreset 语义；MuJoCo 文档说明 renderer completion/readback 的界面；Isaac 6.2 文档展示 camera/Replicator 与 physics/render 更新边界。具体本仓库支持、依赖、证据必须由 future exact build/capture oracle 建立。

## 维护者确认修订的强制追踪

| 要求 | Owner／子阶段 | 必需oracle |
| --- | --- | --- |
| 嵌套Robot／组件到具名Joint/Body通道，8维输入→7＋2输出 | Scene robots／ControlGroup／ControlBinding；3b、4a/4b | 不硬编码Panda维度；传动约束内可实现力域；Controller不直接依赖live SDK |
| BodyWrench及未来typed load、显式贡献组合 | canonical/control、session adapter；4a/4b/4c | frame/point/torque转换、joint＋body外力、重复贡献/J^T双施拒绝、hold不累计、reset清旧载荷；具体runtime样例在4a冻结 |
| 同一public Env切换与简洁配置 | Env/config/admission/worker；3a/3c、5c、6c | 三物理路线往返；内部隔离环境/App，不要求用户make_env；receipt/lease/generation内部形成 |
| Core sampler连续与provider RNG隔离 | reset sampler/plan、Env；3c、6c | explicit seed重置、None继续、preflight拒绝不消费、失败effect记已消费；provider派生seed可查 |
| task cadence与native dt、旧hash | Artifact/execution/timebase；3a/3b | 默认共享timebase；异值需显式版本化映射，不改旧codec/hash |

当前决定以[确认收据](../maintenance/20261103_protocol_baseline_confirmation.md)和五份权威协议为准。历史closure-force提案只保留在原交付／审阅记录，不再作为实施要求。
