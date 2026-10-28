# 检查点恢复与 Provider / USD / Task Harness 补丁计划

更新于 2026-10-28。状态：**F00 S1_PASS / SYNTHETIC_CAMPAIGN_EXPERT_FAILED (20/20) / ORACLE_NOT_RUN**。
本计划的后续方向仍为计划状态；F00 是维护者本轮单独授权的实现/验证包，不代表其他补丁行已授权或开始。
`develop-full` 集成、Harness 生命周期修复和定向 provider-free S1 已完成。唯一有界 synthetic MuJoCo campaign 已执行，但 20/20 seeds 均为 `expert_failed / gripper_readiness_timeout`；candidate 未通过，因此 Oracle/H5 与 pending Judge 未运行，F00 native 兼容出口未通过。
R03c 接收合同由 [07](07_Execution_Order_and_Acceptance.md#r03c-checkpoint-recovery) 维护。

## 1. 已确定的方向与范围

- 一个 Core Runtime / RuntimeSession 合同，多个 provider adapter；共用任务、reset/step、
  canonical state/control、Recorder 和 Evidence。不同 Python 环境或 native 应用宿主不产生第二套 Core Runtime。
- 首轮 Isaac：官方 Panda + 一个可动刚体；通过后扩展到当前实际使用的 Panda 导入 Isaac。
  完整 Panda 与独立 Arm+Hand fixed Attachment 分别记账，不能替代对方证据。
- 维护者选择 pip 安装最新稳定 Isaac；2026-10-28 审阅选定版本为 6.2.0.0 / Python 3.12。
  执行安装包时重查官方 stable，版本改变须明确更新依赖/API/资产 catalog 配方，不浮动升级冻结运行。
  接受 8GB 显存的小环境探索，先单 env、state-only，实测资源；它不等于官方硬件资格。
- 资产团队已确定，尚未提交分支。**上游按 USD 且已验证成功为输入前提**；本阶段消费验证收据，
  不重做上游资产重建、USD 转换或几何/惯性验证系统，不因缺上游分支而停止规划。
  实际运行仍绑定实际 bytes、entry/variant、source revision、闭包和报告 hash。
- 无已知外部调用方直接依赖 `ReferenceTaskBinding`。扩展现有 Core 构造入口供 Harness 消费，
  binding 继续作为内部 seam，不将其发布为资产团队的新公共任务协议。
- 原 R01–R07 目标、22 切片与 P99 required envelope 保留。下面 F00–F07 是**补丁计划行**，
  不计入原 7/22，也不静默增加 P99 依赖；各行按实际工作包确定实现/运行范围。

原 R04 Camera、R05 正式反馈、R06 历史原件处置和 R07 五 LIBERO 部署均继续保留。
新增单 Panda USD/Position 不以 split Attachment、R05 500Hz 或全阶段 P99 通过为全局前置。
若在原默认执行表之外提前推进独立行，工作包应明确记录顺序选择、理由与未变的原 gates。

2026-10-28 顺序选择：07 原表在 R03c 后默认进入 R04b；维护者本轮明确优先推进 Isaac、USD 与 Task Harness，且 F00 是可独立启动的 Harness 生命周期缺陷修复行，因此要求先执行 F00 attempt001。该选择只调整本次工作包先后顺序，不更改 R04b/R04c 的出口、原 7/22 DAG、P99 Required Envelope、R05a/R06 blocker，也不把 F00 增加为 F01–F05 或 R04 的全局前置。本工作包不启动其他 slice。

## 2. 实际输入与当前实现边界

| 输入 | 固定审阅身份 / 状态 |
| --- | --- |
| Core 检查点 | `c30d97efa6ad169c205ea25d7917bc7b9a06e93c`；R03c 静态修正接收，S2 INCOMPLETE、S3 NOT_RUN |
| GeoPhys / Menagerie | `a53a8cfed7c9d6464274b5c96fca601271dc4ee4` / `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` |
| Harness merge | `9d0b3e524d67105e67ddb98e6dec903f19eb4255`，PR #1 source `710b42253dae2ce0175c3c51eee97d0ce83fabeb` |
| 两线共同基线 | `535ce2516e61ecd538d5ff6dccf7493a1cfe2cac`；Harness 为 13 个新增文件，Core phase 自此有 70 条变更路径；文本无交叉不能证明语义兼容 |
| handoff | 飞书页面无法读取；维护者在对话转述正文，已与固定提交实现对照。运行成功结论来自交接方报告，未取得其原始 seed 行/H5 作独立复验 |

Harness 当前只有 `pick-lift-v0`，消费 synthetic mock box，并调用旧 v0 Artifact、
`SelectedReferenceEnv`、Panda R1 controller / expert、canonical H5。Physics 被交接方报告为真实 MuJoCo CPU。
Phase II-01 的 typed Scene/leaf/Generic H5 是另一条合同路线，接入时须同时迁移其生产调用者与 reader。
`--provider` 参数化、catalog manifest available、安装成功均不能证明新 provider 可以执行。

## 3. 按层级定位补丁

下表中 Core 路径相对 `task_env/`；显式 `GeoPhys/` 路径相对仓库根目录，
Harness 文件相对固定分支的 `task_env/script/agent/`。分类优先 FIX_EXISTING / EXTEND_EXISTING / COMPOSE_EXISTING。
新增实现只限当前不存在的 Isaac native adapter；不复制 Runtime、工厂、Controller 或 Recorder。

| 层 / 所有者与方法 | c30 检查点的缺口 | 补丁与验收边界 |
| --- | --- | --- |
| `artifacts/contracts.py::AssetDefinition`；`assembly/assets.py::_asset_definition_from_manifest` | 有稳定来源声明，缺 USD entry/variant、完整闭包与上游验证报告的消费链接 | 在现有 asset owner 接收版本化 delivery/representation，关联现有 AssetDefinition；不复制 Asset/Scene 定义，不重做上游验证器 |
| `assembly/source.py::TaskSceneSource`；`runtime/sessions/source.py::RuntimeSource` | 当前 source 为 xml/base_dir/source_id，不能把 USD 路径塞进 XML 字段 | 版本分派 USD/MJCF source，绑定 entry prim、variants、resolver/依赖闭包；保留旧 source mapping/hash |
| `assembly/assets.py::_source_closure_manifest/_source_closure_digest` | 主文件 hash 不足以绑定 USD reference/payload/mesh/material/variant | 复用闭包工具与 provider dependency manifest；缓存键含 source/representation/recipe/options/provider-build；依赖变更失效 |
| `sessions/geophys_source.py::native_scene_source/GeoPhysSourceComposer` | Core bridge 固定 `SceneSource.mjcf_string`，canonical import mapping 有 MJCF 名称假设 | 复用 GeoPhys 已公开 `SceneSource.usd_path/urdf_path`、`import_scene_source`、ImportedScene inventory/capability/lowering；未消费属性明确报告 |
| `sessions/mujoco.py::_MuJoCoSession`；`sessions/source.py::source_asset_bytes` | 当前 Core 从 XML 构造，未接 USD entry/decoder/dependency receipt | 先查实际 build 的 USD decoder；可用则走 native，其他方案另定 build/profile 或明确派生配方，不覆盖旧 frozen build，不猜反向 converter |
| `task_env/requirements.txt`；root lazy exports；`sessions/api.py::_materialize_admitted` | 依赖清单将 MuJoCo 3.8.x、Taichi、renderer 一起安装，不能直接照搬到 Isaac | common/provider constraints 分域并锁定解析；保留 lazy import；catalog/import 不启动 Kit/Taichi；无根 packaging metadata 时使用明确 PYTHONPATH，不默认 editable install |
| `sessions/api.py::_validate_v1_materialization_source`；`environment/task_source.py::sample_episode_reset_plan`；`sessions/common.py::reset_plan` | runtime admission 拒绝 poses_world；现有 ResetSample/Plan 与 v0 provider reset 已有 pose 路线 | 补 free entity/root/frame/floating joint 绑定及 source projection，复用 realization gate/zero velocity/target reset；不是从零新建 reset 系统 |
| `sessions/source.py::project_scene_definition_v3_to_mjcf` | scalar-only projection 不能因打开 pose admission 就直接处理 floating Joint | 显式保留/映射 authored free joint，核 entity/root 与 pose；正反例覆盖，不能只删除 admission guard |
| `sessions/common.py::snapshot_v1`；两 provider 的 `_snapshot_with_native_free_joints` | 要 JointDefinition 而非 JointReference；部分 binding 校验在 readback 之后；free velocity 解释采用 MuJoCo 约定 | 从 Scene 统一解析定义，前移可静态确定的检查；adapter 明确 quaternion、linear/angular velocity、frame/unit，禁止把 Isaac 数据套入未确认的 qpos/qvel 语义 |
| `sessions/api.py::provider_manifest/materialize`；`sessions/provenance.py::provider_build_identity` | 无 Isaac 分派；CPU/strict profile 有界；materialize 目前使用 legacy ExecutionSpec | 精确新增 execution/profile/build admission，显式处理 ExecutionSpecV1 到实际 session 的路径；利用现有 backend/device/render 字段，不把 host/solver/device 混作单字段 |
| `controllers/canonical/position_profile.py::PandaPositionServoProfileV1.from_source`、`controllers/canonical/production.py::ProductionCanonicalPandaController` | XML-derived kinematics、actuator1..8/tendon 假设；Harness R1 还有 force-feedback 依赖 | 复用 Position 算法，提供 source-derived public kinematic/resource 描述；核 joint order/sign、TCP、opening、drive gains/limits；R1 force-aware 单独准入 |
| `sessions/control.py::materialize_control`；`sessions/leaf_control.py::LeafNative*MappingV1/LeafMaterializationReceiptV1` | leaf admission 为 MuJoCo CPU；native receipt 含 qpos/dof/ctrl slots、nq/nv/nu、tendon/equality 假设 | 保留旧 V1，新版分离 canonical resources 与 provider-native bindings，定义实际 drive 通道与 hand fan-out；唯一 writer、整体 preflight、partial-apply fault 保持 |
| `registry.py::make_env`；`tasks/reference_env.py::SelectedReferenceEnv.__init__/_reset/_step*/close` | provider/CPU/leaf guard、固定 Panda shape；reset 重建 session；无已冻结的对外通用 Artifact seam | 扩展既有构造入口和配置，接版本化 task/scene 输入；同步 action/obs shape、runner 额外 snapshot、rebuild/close；不直接公开 ReferenceTaskBinding |
| `runtime/sessions/` 的 Isaac adapter（拟新增同目录模块） | 尚无 Isaac session | native bootstrap→stage/reference/physics/view→reset/readback→apply/step/sync→fault/close；明确 process app 与 scene/session 生命周期、重复 reset 和最终 exactly-once close |
| `GeoPhys/src/geometry/mjcf_loader.py::_parse_site` | MjSpec sphere size 三槽导出形式按单有效维数被拒绝；raw Panda 单槽已可接受 | parser 按 primitive 规范化及有限值检查，不改通用 padded helper 语义；不重写原 source/hash，不称它为所有 GeoPhys 路线的唯一 blocker |
| `GeoPhysSourceComposer`、`_GeoPhysSession`、fixed Attachment admission / leaf hooks | 缺双 source→一固定树的公开 lowering、model-bound mapping 和 interval 接线 | 保留两个源闭包、mount/root/collision/actuator/tendon/equality、clock/publication；公开 API 无法保真时交 GeoPhys owner，不穿透 solver；与 single-Panda USD 分开 |
| `recorders/h5.py::load_leaf_control_records_h5/_load_attached_leaf_control_records_h5`；Env `start_recording/finish_recording` | exact MuJoCo3.8.1/64/65/两 writer profile；Harness 另用 canonical H5 | 抽公共身份/Target/Ack/clock/T+1 校验，增加新 profile/receipt codec；保留旧 strict reader；canonical Oracle metadata/inspector 同步，不另建 writer |
| Harness `catalog_query.attach_asset_bundle`、`CandidateSpec`、`harness_compiler.compile_candidate/CompiledTask.env_class` | mock-only schema/synthetic true、固定 box/质量、无 fixture、固定 Panda 名称/CPU/timebase，内部 binding | 保留 mock 模板；真实 USD delivery 与模板经现有 Core 构造；绑定 execution/representation/receipt；不能只换 path 或 synthetic 字段 |
| Harness `evaluate_lift`、`semantic_check.check_semantics`、Judge `check_semantic` | 固定 cube_world_z/lift_height 端点，不表达任意 benchmark | 首轮 real pick-lift 明确语义；On/In/region 由 task-owned evaluator 与独立样例处理，不改名为 lift |
| Harness `feasibility_probe`、`oracle_candidate.record_candidate`、`construction_ledger`、`judge_package` | CPU/synthetic 多处写死；后者要求 mock bundle；记录路由及原始 seed lifecycle 检查不足 | provenance 决定 synthetic，admitted execution 决定 backend/profile；按记录版本独立检查；保持 Judge pending/NOT_ASSESSED |

## 4. F00 必须修复的 Harness 判定缺陷

固定 Harness 实现的 `feasibility_probe.run_seed` 在检查 terminated/truncated 前，
先用 `solution.done && task_success` 判 solved。2026-10-28 的 host-only 复现中，
terminated-only、truncated-only、二者同时三类均被记为 solved；实际 `judge_package.check_probe`
定义也接受 20 个 terminated=True 的 solved 行。`construction_ledger.finish` 源码同样未核这些行事实，
该函数本轮仅静态审阅。此结论不表示交接方已有真实 H5 必然受影响；需复核其原始行。

FIX_EXISTING：明确共享的有效完成事实合同，先处理 fault/lifecycle，再判 solved；
probe、ledger 接收、Judge 独立复核均核原始 task/expert/terminated/truncated/fault/cleanup 信息。
复用既有 `examples._common.run_expert` 成功语义，补最后一步合法成功与终止/截断负例。
expert_failed 不直接等于 task infeasible；不得缩窄 reset 分布隐藏 fault。

## 5. 分阶段顺序与出口

| 行 | 前置 | 实施与检查 | 出口 / 停止条件 |
| --- | --- | --- | --- |
| F00 集成与 Harness 修复 | 复核实际检查点/两条提交线；单写入窗口 | 固定 Harness/phase 输入，正常整合并修第4节判定；旧 mock 正反例与实际 Core caller 兼容 | 无历史丢失、无重复 Core owner；已有 raw 未取得时明示 unavailable。检查点可为 c30 静态修正基线，不要求 R03c/P99 先通过 |
| F01 Isaac 安装/原生对照 | 固定官方 stable、实际 interpreter/dependencies/资源；独立 native 预算 | 隔离 Python 环境，官方 Panda+刚体小场景先 native reset/step/close，记录 build/API/VRAM/RSS | 安装与运行分栏；native 失败保留，不声称 Core 已接通。安装准备可独立提前，不能继承 R03c 启动额度 |
| F02 已验证 USD 输入 | F00；固定官方资产/API 配方，可复用 F01 样本，不以 F01 native PASS 为前置 | delivery codec、entry/prim/variant/闭包、验证报告链接、native representation resolver；确定 MuJoCo USD build/decoder 或显式派生方案 | mock/real 分离、依赖变更失效、缺 entry/依赖/错 hash 拒绝；不重做上游资产验证，不等待其开发分支 |
| F03 Core 合同与调用链 | F02；首个精确 execution/Panda 资源定义 | free-body reset、typed state/frame/unit、execution admission、control receipt、factory、reader 正反例 | 调真实工厂/准入/reset/runner snapshot/首步/publication/录制读回/close，只替 native IO；不得 stub 掉失败 owner 后声称覆盖 |
| F04 Isaac Core 闭环 | F01/F03 | 先官方 Panda+刚体，再当前实际 Panda 的固定来源导入；同 public Env/既有记录器 | source/drive/pose/reset/clock/运动/刚体接触/close 与 H5 独立读回通过；完整 Panda 不代 split Attachment |
| F05 GeoPhys 与三 Provider | F02/F03；各 cell 的公开 source lowering/receipt 就绪 | GeoPhys public USD 单 Panda+物体、MuJoCo USD 执行；旧 MJCF/已知 importer 局部修复回归；split Attachment 另列 | 同一声明 USD 交付在三个 provider 各自 construct/reset/step/record/read/close；不能以旧 MJCF 替代 USD cell。split 单元不成为 single-Panda 全局前置 |
| F06 真实 Harness | F00；对应 provider 的 F04/F05 出口 | 新 spec、四报告、独立正负语义端点、≥20 seeds、Oracle、pending Judge 包 | 每个声明交集全 seeds solved、Oracle task+expert+lifecycle+storage/identity；保留 invalid/expert_failed/unknown；不复用 mock 最终结论 |
| F07 后续扩展 | 基础三 provider 闭环；具体扩展范围确定 | 更多 USD scene/fixtures/benchmark 谓词/render；选定 Newton host/solver 路线 | 每个新交集独立准入/证据。当前不要求同时建设 standalone Newton 与 Isaac-hosted Newton，也不退役旧 MuJoCo reader |

F05 内部按 ready cell 顺序交付，不必为等待某 provider 阻塞其他已就绪行；
但没有全部要求的 cell Evidence，就不能接受“三 provider 闭环”总出口。
F06 的 Expert/20-seed 要求不回写为 R07 五任务部署的新增必需项。

### 原生资产与对应 Provider

Isaac USD→Isaac 优先保留原生 physics layers/reference/payload/variant；
GeoPhys 优先复用公开 USD 路线；MuJoCo 先查实际 USD-enabled build，必要派生表示单独有 recipe/损失身份。
当前 Panda MJCF/URDF→Isaac 是单独扩展，对照实际 source/joints/TCP/mimic/tendon/inertia/collision/手爪行程，
不能用另一个官方 Franka 替代。统一的是 delivery、身份、选择、错误和报告；不承诺不同 solver 数值轨迹一致。

## 6. 防止字段与接线错误进入 native

1. 每包列 source→Scene/Artifact→reset/Execution→mapping/requirements→state→Target/command/Ack→
   observation→H5→report 的实际类型、版本、shape、单位、frame、顺序、owner 和消费者。
   runner 复用 typed 生产构造/解析，不自行拼出第二份字段定义。
2. 输入/hash/账本预检与实际生产调用链 S1 分开记账。`--check` 使用同一个构造入口；
   既有 c30 四配置/20 项结果在输入未变时复用，受影响行才扩展回归。
3. S1 调真实 public reset/step、runner 的额外 snapshot/checker、Recorder codec/reader、fault/close；
   假 IO 不证明动力学。负例至少覆盖 Reference/Definition、tuple/StateRequirements、缺/重映射、
   shape/unit/frame、非有限数、stale boundary/config、丢 Ack、重复 native writer、partial apply、
   finalize/close 失败和 NumPy 标量 JSON。
4. 能由 source/schema 检出的错误先于 native import/write；依赖编译的资源信息在实际 compile 后、
   reset/写入前验证 public metadata。不得伪造 DOF/slot/drive 值凑旧 receipt。
5. native 计数区分 app start/materialize/reset/forward/physics substep/outer interval/record finalize；
   render update 不能暗中步进。失败保留 traceback、partial progress/H5；不宣称物理回滚。
6. 普通接线缺陷在同包有界修正；重跑遵循该包启动额度。新 native 窗口冻结实际 HEAD、source、
   build、case/oracle/timeout/资源/关闭规则；不沿用已耗尽 attempt002 的账本或额度。
7. storage roundtrip、task success、有效完成、Expert done、Judge approval、D0/D1/D2 与 training-ready 分开；
   不以一个 pass 推出其他层级。未变回归不反复全库重跑，不固定追加准备轮。

## 7. 分支、接收人与待核实项

F00 attempt001 按授权在 `develop-full` 执行，未创建 worktree；基线 merge 与当前提交记录见下方 F00 快照。
原 `codex/phase-ii-01-p00-20261023` 阶段 topic 保留；后续 F 行若获单独授权，复用 `develop-full`，不逐行建分支。
不移动 frozen refs；push/merge `develop`/`main`、Tag 和 Release 仍遵循单独授权。
GeoPhys importer 如需提交，子模块可用 1 个专用 topic（基于实际审核 pin），主仓单独审查 gitlink 更新。

资产团队保留源 bytes/revision/验证报告真源，Core 接收及绑定，Harness 消费；
Human Judge 与 trajectory qualification 仍独立，不由 Harness 自动填写 approve。
训练字段/筛选分布/接收人与更广 replay 容差/视频要求不阻塞基础 import/step，但在对应验收前确定。

以下未知应由 provider owner / 实际版本 API 或网页 GPT 专项复核，不靠删除 guard 猜测：

- GeoPhys 双 MJCF source fixed-tree 能否保留 actuator/tendon/equality/collision 和每 Entity 映射；
  single ImportedScene 与 USD 入口的存在不证明该装配路线。
- Isaac 6.2 公开 articulation/rigid/drive 的实际签名、views 初始化/失效、reset/sync、app 与 scene close；
  官方 Panda 与当前 Panda 的资源/TCP/力反馈 phase/freshness 需分别确定。
- 当前 MuJoCo 3.8.1 build 是否启用 USD decoder；官方 tag 有实验性 USD 支持但选项默认 OFF。
  `mujoco-usd-converter` 的 MJCF→USD 功能不能当作已有反向转换。
- 已验证 USD 的 provider 特性消费：GeoPhys public USD 不自动说明全部 PhysX/drive/mimic 扩展已实现；
  Core 消费 capability/report，未消费属性明示，不重复上游验证，也不据文件格式直接宣称仿真可行。
- 物理接触与语义 contact query 分开。当前 session manifest 将 contact_detection/contact_impulse 列 known_unsupported；
  R07 的 On/In 等若需公开接触事实，必须补 public query/state/evaluator 的对应 owner 与证据，不能用位置重叠代真实接触。

<a id="f00-attempt001-实施快照-native-result"></a>

## F00 attempt001 实施与 native 结果

Harness 与阶段基线已按本包合并到 `develop-full`：Harness parent
`9d0b3e524d67105e67ddb98e6dec903f19eb4255`、phase parent
`0d11d33ee6e6a9b09f2924b3450bbedff9aefd91`、merge tree
`7684aeceb3e49013c700403e1e9f9431e2a484dd`、merge commit
`5d890891ac6172d343d0cd904768bf415e0f9907`。F00 实现提交为
`6e477765cf0539535e848e7717e029a44e413b29`。FIX_EXISTING 在现有 Harness
owner 内完成：`run_seed` 保存原始 outcome/lifecycle、reset/step、fault、primary
error 与 close facts；solved 只在无任务/专家失败、无 fault/terminal flags 且
close 成功后产生。`construction_ledger.finish` 与 `judge_package.check_probe`
分别检查报告身份和每条 raw row、seed 顺序与 totals。provider-free 定向测试
覆盖实际 `run_seed`、两消费者、20-row 正例、完成/终止/截断/失败/fault/cleanup
反例、expert lifecycle 失败、部分异常和旧报告证据不足；目前 13 项通过。真实 Core caller 链由
`compile_candidate` → `ReferenceTaskBinding` → `SelectedReferenceEnv` →
reset/step/close 的实际 MuJoCo campaign 运行；campaign 中 assets、compile、semantic 三份报告通过，feasibility 报告失败。seed 0–19 全部是 `expert_failed`，原因 `gripper_readiness_timeout`；每行 reset/close 成功，steps 为 853–864，物理 task success 0/20、expert failure 20/20，没有 termination/truncation、execution fault、step error 或 cleanup error。进程正常结束而非 timeout，退出码 1，wall 56.45 s、user 56.13 s、system 0.81 s、CPU 100%、peak RSS 568368 KiB、swap 0。账本记录一轮失败并保持 `ready`，不是 `candidate_ready`。

该 campaign 使用此包新生成的 synthetic pick-lift box proxy，asset SHA-256 `317ef3820b957f17e1a9ad0e09732b5863360e74eebf22446d3e1254d1a67be5`；它不是未提供的历史 handoff bytes，也不是真实 benchmark。Oracle seed0、同-run H5 reader 和 Judge prepare/verify 按失败门未运行，无 H5 或 Judge 包；不得将 `expert_failed` 解释为 task infeasible、不能记 Harness acceptance，Qualification 保持 `NOT_ASSESSED`。没有重试 campaign、修改 candidate/reset 分布或启动其他 slice。逐 seed 原始行、四份报告、账本、stdout/stderr、进程退出与资源日志见 ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f00_001/`。

源码审计、固定 Harness 13 文件副本、9 项 host-only 检查及失败复现在 ignored
`workspace/maintenance/multi_provider_asset_harness_review_20261028_001/`。
其中 2 项检查是成功复现验收缺陷，34 个静态 import 声明可定位；均非 native/Harness 接收。
缺该目录的 clone 标记 **indexed but raw unavailable**，不能把本页摘要当作新物理证据。
R03c 原始收据见 [R03](03_R03_Physical_Attachment.md)，原 `validation_receipt.json` 保留签署时点，不覆盖历史。
本次文档修订/检查在 manifest 的独立 revision 条目记账，不回写旧运行结论。

## 8. 来源与证据可用性

固定官方参考（2026-10-28 审阅；采用方向不表示本仓已实现）：

- [Isaac Sim 6.2 pip 安装](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/install_python.html)、
  [6.2 release notes](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/overview/release_notes.html)、
  [6.2 Panda 教程](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/core_api_tutorials/tutorial_core_adding_manipulator.html)。
  原 6.1 Robot Assembler 参考仍保留其历史设计用途；此次安装选择不等于升级旧合同。
- [MuJoCo 3.8.1 USD importing 源文](https://github.com/google-deepmind/mujoco/blob/3.8.1/doc/OpenUSD/importing.rst)、
  [3.8.1 CMake USD 选项](https://github.com/google-deepmind/mujoco/blob/3.8.1/CMakeLists.txt)。
- [固定 Harness merge 源码](https://github.com/Lebingelee/GeoChora/tree/9d0b3e524d67105e67ddb98e6dec903f19eb4255/task_env/script/agent)。
