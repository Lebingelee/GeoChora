# 生命周期、时间与数据协议

状态：`APPROVED_IMPLEMENTATION_BASELINE`，2026-11-03 维护者确认；见[确认收据](../maintenance/20261103_protocol_baseline_confirmation.md)。本文是后续实施的语义基线；新类型名称和字段仍须由所属子阶段工作包映射到现有 owner，不代表生产 schema、API 或运行能力已经实现。

## Owner 和操作状态

逻辑状态用于说明合法操作，不要求本包新增 enum：

| Env 状态 | 可做操作 | 转换 |
| --- | --- | --- |
| configured / unmaterialized | query、build、reset preflight、close | 完整 materialize 后进入 ready |
| ready（已构建，未成功 reset） | query、reset preflight/reset、close；不可提交 episode command、step 或正常 state/obs | reset/readback 门通过后进入 running |
| running | reset preflight、组合后唯一提交 command、一次 control interval、snapshot/publish、record、close | 完整 reset 开始新 episode；完整 interval 才发布下一正常 transition |
| faulted | 读取 fault/cleanup receipt、明确 rebuild reset、close | 不允许再 step 或提交旧 command；不得继续产生正常 transition |
| closed | 读取终结 receipt | 所有 state view/lease 无效，重复 close 安全 |

这是 faulted Env 的目标行为。公开 `reset` 与 `reset_for_solution` 是明确的新 episode rebuild 请求；在 Env 未关闭且 reset 前置校验通过后，SelectedReferenceEnv 会关闭旧 camera consumer/session，再创建并 reset 新 session。纯 preflight 拒绝发生在该破坏边界之前，保留既有 fault 和未被触及的 session；越过边界后失败则关闭半构建资源、保留本次错误与清理次错、记录 reset effects 并继续 faulted，不恢复旧 episode。只有 `finish_reset` 在 state/readback/observation 已发布后才清除执行 fault；失败 rebuild 不返回正常 reset observation/info，旧 state/frame/receipt 在 faulted 状态下不得用于新的正常 transition。若 App/worker owner 无法 reopen，保留其原始拒绝及现有 fault，后续 step/render 仍被拒绝，Env 可在 owner 再次可用时显式 retry reset 或 close。

未完成或故障中的 Recorder 仍须按其自己的失败合同处理；reset 不得静默丢弃未完成 transition。`reset_failure_receipt` 在 destructive rebuild 失败时记录阶段、首错、prior execution fault、旧/新 session close 与 reset-write effects，以及清理次错；成功 rebuild 发布后才清除该收据。

## 构建、reset、step、publish 与 close

| 时点 | Core/Env | RuntimeSession/adapter | 故障边界 |
| --- | --- | --- | --- |
| query/build | 汇总 Artifact/Scene/source/Controller/state/batch/共享资源需求；固定 observation 契约和 batch layout；发布 binding 和 route identity | 仅构建已准入路线；记录 dependency/provider/device/compiled map/materialization receipt；native 构建失败尽力清理 | static admission failure 无原生 effect；初次 build 失败且清理完整可回未物化；reset/rebuild 过 first effect 后失败或 cleanup 不完整则 faulted |
| reset preflight | 验证 seed/sample、source identity、mask、配置/action spec，并为新 episode 分配 generation | 在通过前不写 state、不释放现有 session | preflight reject 保持旧 episode/Controller/state view 有效 |
| reset effect | 绑定新 episode/reset sample；重置 Controller、filter/integrator/force latch/action histories | 按 mask 写选中 state、zero velocity/initialize targets，返回 ResetWriteReceipt、realized state 与公开 readback | 第一个 native effect 后失败就 faulted；记录已写 env rows/fields；无通用 native snapshot rollback |
| command + advance | 每边界由 Core 按声明组合贡献后唯一提交；拒绝重复或未协调覆盖；记录 `submitted → accepted` | 精确映射并 ack；按固定 physics_dt/substeps 走一组公开 native advance | command 在第一 write 前 reject 可继续；写入/推进部分失败则 faulted |
| publish/evaluate/record | 等完成 fence 后 snapshot；校验 identity/freshness；再计算 observation/evaluation 并记录完整 transition | 返回 named state, sample clock, revision/interval evidence；不把未完成 device write 暴露出去 | required state/readback 不齐，不得生成正常 observation/transition；不把 incomplete interval 写成 complete |
| close | 终止正常 episode/Recorder（若无 fault）；依次关闭 owned consumer/session/source/task resources | 释放 session-owned native model/context/lease；返回 close receipt | 尽力清理所有资源并保留首错和附加失败；不重复 close 已被另 owner 接管的对象 |

### Reset 和 batch

Reset 重新执行当前任务初始化，不迁移旧 episode 的 q/qdot、接触历史、provider 内部 solver state、Controller integrator、pending force contribution 或 GPU graph state。**Core sampler 的受控随机流不随物理重建丢弃**：显式 `reset(seed=x)` 重置该流，`seed=None` 延续现有流。Provider 私有 RNG 不跨后端迁移，每 episode 采用记录的派生 seed 重新初始化；同 seed 不承诺跨 solver 轨迹相同。

Core 的 seed/sample 准备与提交须有明确消费边界：可用候选 RNG 状态准备样本，纯 preflight 拒绝时不提交候选或推进现有流；一旦提交／发生 effect，记录样本与消耗，即使后续失败也不伪装从未消费。只操作 sampler 自己的 RNG，不要求复制 provider 私有 RNG。

Backend／renderer／Controller 切换由**同一个 public Env 对象**在 reset 上处理；可重建内部 session/worker/App 和隔离运行环境。已准入切换不能要求用户 close 后再次 make_env；内部复杂度由 Core/adapters 管理。用户只提供 backend/renderer/controller/camera 等配置，不需手写 receipt hash、lease ID 或 generation。

- scalar env 的 route/config reset 若必须重建 session，先做可静态判断的 query，再关闭旧 session、创建新 route、执行 reset 和 readback；新 route 成功前不得发布 success obs。失败后只可明确重建/reset 或 close，不能偷偷返回旧状态。
- native batch 的 backend/host/engine/solver/coupler/device/action mapping 变化整批重建。只有 capability report 声明 mask-reset 的路线可 same-config partial reset；receipt 精确列受影响 env ids/rows。未选 row 的 episode id、simulation time、state revision、Controller state、terminal obs 和 action spec identity 保持不变。
- 支持 mask reset 不代表支持批内选择不同 route。mask 不合法或不支持时必须在任何 native effect 前拒绝；不能静默升级成 full reset。
- 当前 `ReferenceEnv` 选择路径每次 reset 重建 selected RuntimeSession；当前 GeoPhys merged batch 有按行 reset 能力，但这不是 PickCube selected session 的 partial-reset 证据。Isaac batch 尚无本仓库 adapter。

## 时间、完成与失败状态

每条执行绑定 Artifact timebase 的 physics `dt` 和 substep count；task control/observation cadence 与 native integration cadence 语义分开，当前旧 codec/hash 保持。不同路线若必须不同 native dt，由 3a 冻结显式版本化执行映射，不静默改 task/timebase identity。Core 一个外部 action/control interval 可能采用：
1. outer Controller 算一次，target zero-order held 跨 N 个 native steps；
2. 明示 physics-rate hook，每个 native boundary 以最新同步 state/revision 算新 command。

两种 cadence 分别准入，不由 provider 或 action 名称隐式改变。同步 `RuntimeSession.step()` 完成所有 N 个 substeps 才能 snapshot。若 route 需异步推进，adapter 返回含 materialization/episode/config generation/attempt id 的 completion ticket；调用方先 wait/device synchronize，再 read state、feedback、render snapshot 或 Recorder 数据。当前 RuntimeSession 是同步接口，Isaac App owner 不表示 step 是异步。

advance fault 至少记 expected interval、attempted/completed native step indices/count、last confirmed simulation time/revision、remaining/unknown interval、command ack(s)、partial effects 和 recovery action。已确认完成区间不回滚；不能返回“未推进”的正常 result 或把部分动作记成完整 T→T+1 transition。若无法知道最终状态，标记 unknown 并只开放 reset/rebuild/close。Reset/command/write fault 同样区分 before-first-effect 与 partial native write。

## State identity、sample clock 与 lifetime

StateBoundaryIdentity 至少联合绑定 Artifact/source closure、Execution/materialization、scene instance/env id+row、episode/reset sample、config/topology generation、control step 与 state revision。SampleClock 独立声明 evaluation boundary 或 native step/domain/index/time；各字段需说明物理单位、坐标系、reference point、joint order、batch layout 与设备。NativeIntervalEvidence 逐 control-substep 记录 measurement/availability，不从窗口循环次数推时间。

required/optional 由 StateRequirements 指定。required 缺值或 sample clock 不匹配时 reject；optional 以带 reason 的 UnavailableStateValue 表示。无传感器力、contact force 或不支持的动力量不能填零。published state 只含 Core 语义名称、typed values、完成凭据和映射身份；不暴露 native pointer、solver private array 或不稳定 ordinal。

- **owned snapshot：**adapter/Core 已复制成独立只读 storage；调用方可持有，除非共享对象另声明，否则不受下一 step 影响。
- **borrowed view：**只读，但绑定 owner/lease、device/layout、identity、revision 和 expiry operation。下一次 write/advance/reset/close 或 lease release 后必须视为失效；API 可检测时拒绝 stale view。调用方需跨边界持有数据时显式 deep copy/retain。
- 对 device view 必须提供 synchronization/fence；不得强制全量 CPU copy，也不得声称全部零复制。NativeRuntimeReadbackV1 当前明确为 owned named values；其他 view 不能自动沿用这个保证。

Recorder 只收完整 state boundary 与对应 command/ack/measured feedback；fault interval 保存独立 fault/evidence，不伪造成功 transition。完整 observation schema 构建后固定；Renderer 具体 buffer/capture lifetime 按 1d 扩展，不改变上述 physics identity 和 synchronization 规则。

## 资源与 close owner

| 资源 | 唯一 owner | Env close/reset 的动作 |
| --- | --- | --- |
| Task observation/Recorder/lifecycle | Env/Core | 按现有 Recorder contract 完成或保留 fault；关闭 env-owned consumer |
| RuntimeSession 与 native model/scene/context | provider adapter session | 调用 session.close；释放且只释放自己创建的对象，返回 close receipt |
| Source closure receipt/task assets | task/source owner | env 结束后关闭/释放 owner receipt；不由 provider 重复删共享资产 |
| Isaac SimulationApp | per-worker `IsaacSimAppOwnerV1` | session 获得/释放 process-lifetime lease；一个 session.close 不直接关掉仍被其他 session 使用的 App；最后 lease 后由 App owner 单独 close |
| worker/process | vectorization/deployment owner | 先停任务、收齐 cleanup receipt，再关闭 worker；worker 崩溃需报告无法观测的资源，而非声称全部释放 |
| renderer shared resource | renderer owner（1d 具体定义） | physics 只交付批准的 identity/lease/fence；不因 share 直接 transfer App/model/context owner |

现有 Env close 有顺序清理和错误累积；部分 mixed route 有 typed/structured close receipt，而通用 RuntimeSession `close()` 目前返回 None。目标接口让每个 owner 的 close attempt 幂等且回报 failed/unreleased resources。重试只由原 owner 管理，不能由多个 consumer 重复释放。

## 故障验证范围

后续实现至少要验证 query/build admission mismatch、build 后半初始化清理、reset preflight 和 partial write、command stale/未协调 writer 冲突／重复 force contribution／持续力错误累加、同步/异步 advance partial failure、required/optional feedback、borrowed view expiry、partial batch reset、App shared lease 与重复 close。1c 只交付设计与静态一致性检查，不启动 App、solver、GPU 或实现测试。


## Renderer、task camera 与 shared lifecycle（1d）

本节补充 render/observation 与 physics 生命周期的交界，不更改上文 1c reset、command、advance、fault、state identity 与唯一 owner 原则。renderer 协议权威字段和路线矩阵见[render-provider](render-provider.md)；本节只定义共同调度、数据有效期和资源次序。

### 三方 owner 与 shared build

| 对象 | 唯一 owner | 可借用者 | 不允许的动作 |
| --- | --- | --- | --- |
| task semantics、scene/source closure、reset sample、observation/Recorder | Core/Env/task owner | physics 与 render adapter 以 typed identity/binding 使用 | adapter 修改 task semantics、私自改变 obs schema 或增加第二 Recorder |
| solver、physics model、published state、物理 timebase | physics RuntimeSession/provider adapter | renderer 读取 fence 后的 public named state 或 lease-scoped visual binding | renderer 推进第二物理、读取私有 solver memory、改 live state |
| shared native scene/App/model/context/device buffer | 创建它的 provider/App/renderer owner | 经准入的 adapter 通过 generation-bound lease 只用允许操作 | 借用者关闭共享对象或向 Core/Agent 泄露裸 native/GPU handle |
| render-only model/data、window、camera、capture target | render adapter/session | Env 提交带 identity 的 request | render-only world 获得任务物理 authority |
| process/worker、跨进程 image transport | vectorization/deployment owner | Env/learner 以 env→worker→row map 使用 | 把一个 worker frame 冒充所有 env 独立结果 |

Physics、Controller/model、state/interaction、render/camera、App/device/window/context 和 batch/worker 的 required inputs 必须在 native build 前合并到同一 request-bound admission。所有 required static checks 通过才可构建；只有明确 adapter/build oracle 的 pending 项允许 provisional build；episode ready 前所有 required build checks 必须通过。renderer 不能扩宽 physics/Controller admission。Shared-scene route 由 physics owner 持模型/scene；independent renderer route 有自己的 render-only model 与映射 receipt；两者都不创建平行 Env Runtime。

### Reset/step 的 image publish barrier

reset 初始 observation/boundary 与正常 step transition 必须分别满足 physics 与 task-RGB 的 publish 条件；reset 本身不是 step transition：

```text
静态 preflight
→ native build/bind receipt
→ reset write/readback (reset) 或 command ACK + 完整 physics interval (step)
→ public StateBoundaryIdentity + completion fence
→ renderer consume same state revision + update fence
→ 每个 required camera capture 完成且身份/phase 相同
→ observation / evaluation / Recorder
→ 向调用方发布结果
```

reset task RGB 用 `reset_initial` capture phase；step task RGB 用 `post_control_step`。当前实现将两者都描述为 `post_control_step`，这是尚未解决的 identity 区分，不视为已验证。UI `.render()` 可以独立消费最新完成状态，不是 publish barrier 的替代品。physics/control clock 只由 RuntimeSession 产生，present/fps/render/camera warmup 不递增 task clock。

若 physics 已完成而 required render update/capture 未完成或失败，Env 保留真实 completed interval、clock、partial effects 与故障；不发布 normal transition，不用旧图/零图，不声称 rollback。window 单独关闭时独立 capture 可继续；若 App 生命周期让两者不可分，adapter 需在 admission 标记该限制并在故障 receipt 中通知 Core。optional camera 只有在 build 固定 schema 与 optional reason 后才可 typed unavailable。

### image/view 的 lifetime 与 batch

Owned image 在独立 storage 中且只读；borrowed view 带 owner/lease generation、env/worker/row/camera、完整 frame identity、layout/device、expiry operation 与同步 fence。下一次可覆写其 buffer 的 update/capture/reset/close/lease release 后 view 无效。跨 Recorder、step return 或 worker transport 存储时，接收方必须 copy 或持有明示的 retain lease 到最后消费点。异步 `pending` 图像不可进入 observation。

批量顺序用 `env → worker → local row → camera → image` receipt 表示；不能把 native batch 轴与进程 worker 轴合成含糊的一个维度。same-step autoreset 在 reset 前保留 done row terminal observation/frame，在 reset 后构造新 episode reset observation/frame，并分别赋予 state/camera identity；返回值的 done row 是 reset observation，info 保留 `terminal_observation` 与 `reset_info`。未选 env 随先前 batched step 正常推进；只有 mask reset 阶段保持其 post-step/pre-reset physics/controller/episode/clock 不变，借用共享 storage 失效需另行标识。现有 RemoteBatchVecEnv `get_images()` 复制一帧给各 slot，只能算 repeated preview，不能作为 row-specific task observation。

### close 与 partially initialized renderer

Env 作为协调 owner，按 renderer session → 自有 camera/output buffer/window/render-only model → 释放 physics/App borrowed lease → 原 provider/App owner → worker 的依赖顺序收集 close receipts。session close 不能直接关闭仍有其他 lease 的 per-worker Isaac App；App owner 在最后 lease 后自行 close。部分初始化失败逐项记录 acquired/released/unreleased resource；初次构建且清理完整可回未物化，清理不完整则 faulted。reset/rebuild 释放旧资源或写状态后失败按 faulted，不承诺回到原 episode；是否已经推进时间不是唯一判断条件。所有 owned close 操作由唯一原 owner 执行且可重复调用；其他 consumer 仅报告 lease release。
