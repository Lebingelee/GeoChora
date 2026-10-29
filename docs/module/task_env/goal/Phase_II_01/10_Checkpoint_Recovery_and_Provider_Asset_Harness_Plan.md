# 检查点恢复与 Provider / USD / Task Harness 补丁计划

更新于 2026-10-29。状态：**F00已有 `ACCEPTED_BOUNDED_F00`；F01 attempt003 GPU PhysX有界native已获 `ACCEPTED_BOUNDED_F01`；F02 attempt002已修复嵌套USD闭包根目录和MuJoCo build归因，定向S1通过，待 Sol 复核**。
本计划的后续方向仍为计划状态；F00与F02分别按独立冻结包获得实现/验证授权，F02当前候选待Sol复核，不代表其他补丁行已授权或开始。

### 当前双Luna分工（2026-10-29）

维护者将Luna1固定到F00–F07，停止R07资产来源调查；Luna2继续R04c之后的非F阶段。F00完整闭环已接收。Isaac 6.2.0.0隔离环境及依赖检查、实际API/资产核对均已完成；F01 attempt002的两次零物理步失败仍保留。F01 attempt003已由维护者授权进行GPU PhysX复验，并由Sol按原始运行源码副本、worker/parent receipts、资源账本、独立reader和定向S1完成复核，获`ACCEPTED_BOUNDED_F01`。F02 attempt002已按Sol返工要求修复并通过定向S1，当前待Sol复核；F03未启动。

未来Isaac Sim native验证默认使用CUDA GPU PhysX（设备`cuda:0`、`gpu_dynamics=true`）；每个冻结包仍需明确记录实际设备、CUDA进程证据、GPU动态配置与资源上限。CPU配方仅在维护者为具体工作包明确指定时使用。此偏好不代表Core Isaac provider已接通。

F06需要真实来源与对应provider基础出口，但不要求完整五任务LIBERO或TurboSquid资产先通过。维护者另选择“少量可接收资产任务先闭环”的LIBERO pilot，按R07单独记账；它不阻塞F01官方Panda+方块，也不把benchmark的On语义改成现有lift模板来求绿。每位Luna一次只执行一个冻结包，完整返回后再派发后继。
F00 attempt001的整合、Harness生命周期修复和S1已由Sol接收，但其20/20 synthetic seeds均为`expert_failed / gripper_readiness_timeout`；该失败原件保持不变。attempt002随后完成受控物理归因、输入修复、20-seed native验收、Oracle/H5独立读回和pending Judge prepare/verify。完整出口仅待Sol复核；F01仍未派发或启动。
R03c 接收合同由 [07](07_Execution_Order_and_Acceptance.md#r03c-checkpoint-recovery) 维护。

2026-10-28 Sol复核F00 attempt001：接收 `develop-full` 两线整合与完成事实修复/S1；33项manifest（25文件、8个Git blob）匹配，13项provider-free tests复核通过，20条原始campaign行经report validator再核一致。candidate仍为20/20 `expert_failed / gripper_readiness_timeout`，ledger round1 fail/state ready、Oracle/H5/Judge未运行；F00整体保持PARTIAL。该专家可行性缺口不作为独立F01安装/官方原生Panda+刚体对照的前置。维护者要求下一子阶段工作包，当前明确选择F01，之后按F02/F03/F04逐包推进；R04b/c可独立安排，原DAG/P99门保持。复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_f00_001/sol_review.md`。

2026-10-28 维护者最新纠正顺序：先成功验收F00完整闭环，再准备/执行F01。F00 attempt001仅整合/修复/S1接收，20seed候选失败，下一包为F00 attempt002集中诊断、必要owner修复、20seed/Oracle/H5/pending Judge收口；F01草稿保留待用、未派发、未安装或启动。该选择覆盖此前独立提前F01的计划，R04b/c及原7/22/P99门仍保留。

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

## F00 attempt002 完整出口（待Sol复核）

2026-10-28，Luna在输入HEAD `3bfd07a323fbcfdc3ee6f7ba9bfddbe54165a6cd`及clean tracked tree上开始，复用`develop-full`。实现提交为`0d75d7646d45f96cc22c567aa61e070dbab5dd94`；没有新建branch/worktree、push/merge或改动tag/submodule。F00 attempt001原件不变。完整命令、raw traces、run ledger、H5和pending Judge包见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f00_002/`。

归因先执行同seed0、同reset/timebase/horizon/控制路线的builtin与旧mock真实Core A/B。builtin在427 outer steps有效完成；旧mock在854 steps的`close_gripper`阶段以`gripper_readiness_timeout`失败。两边controller/expert/readiness身份相同，public target/Ack哈希持续匹配，execution fault均未出现；完整编译source body不同。builtin包含freejoint damping `0.8`、armature `0.01`、collision margin `0.001`、condim `4`、friction `1.8 0.10 0.002`、contype/conaffinity、独立visual与center site；旧mock缺少这些配置，diaginertia也不同（`3.5e-05` vs `0.000033333333`）。该A/B支持source/composition差异是解释路径，但不能隔离唯一物理因果属性。v002保留现有builtin body物性与reset/goal/timebase，改用新synthetic UID/version及XML hash；未降低30N readiness、未改R1、0.06m reset、0.10m goal、6000 horizon、solver或provider路线。

修复后seed0/19 sentinel均以MuJoCo 3.8.1 CPU运行并valid solved（427/433 steps）。该sentinel runner在两episode完成后因汇总变量`STARTED`未初始化退出1；raw stdout/traces保留，provider-free整理验证两episode facts，没有重启。正式campaign单进程exit 0：seeds0–19全部`solved`，无invalid、expert_failed、unknown、execution fault、termination/truncation或cleanup error，共8612 outer steps、29.66秒wall、peak RSS 626312 KiB。ledger为v1 `candidate_ready`：round1仍为旧Core `6e47776`上的fail，round2在实现Core`0d75d76`上pass，artifact `6320dd63cf056f229fec9ad5156722e2d233f7f3c65f7f51bf8026983eac83bb`。20-seed结果是此synthetic lift候选证据，不表示LIBERO In/On等价。

同一commit/spec/catalog执行Oracle seed0一次，exit 0；task success与expert完成、无fault/terminal/cleanup error，427 transitions、428 boundaries。真实canonical H5关闭，T+1、逻辑映射精确回读与独立Core inspector均通过。实际Judge `prepare`和独立`verify`都通过，86项文件已核验，decision仍`pending`，Qualification/D0/D1/D2均`NOT_ASSESSED`。此状态报告为`F00_FULL_PASS_PENDING_SOL_REVIEW`，不是Sol接收、Human批准、正式Qualification或training-ready。F01继续`HELD`，本包没有安装/启动Isaac，也没有启动其他slice或运行全局文档validator。

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

<a id="f00-sol-acceptance"></a>

## F00 Sol接收（2026-10-28）

Sol独立核对338项输出清单、旧attempt001保护字节、全部20条原生completion facts、round1 fail/round2 pass上下文、Oracle真实H5及源码快照、pending Judge包86项索引，确认本包完整出口满足；Luna2独立审阅未推翻本次原生结果。复核发现两项新增路径缺陷：非空portable diagnostic中的Core标量被误当文件ref；新round产生owner/fault issue后账本load拒绝合法追加。两者已在本地提交`1045fd9c65daaa56fdb7eab06779d946bf4b8cd6`修正，Sol复核actual diff并重跑29项provider-free tests全部通过。

结论为`ACCEPTED_BOUNDED_F00`，仅覆盖本次synthetic pick-lift-v0、Panda R1、MuJoCo3.8.1 CPU的20seed/Oracle/H5/pending Judge闭环及所述消费者修复。真实物理/H5结果仍绑定`0d75d7646d45f96cc22c567aa61e070dbab5dd94`；复核修正只做provider-free验证，零新增native，不声称新HEAD跑过原生。新portable诊断测试依赖保留的workspace fixture，缺该原件会skip，不能据此声称全新checkout的CI覆盖。

Human decision仍pending，Qualification/D0/D1/D2均NOT_ASSESSED，无benchmark等价、freeze或training-ready声明。既有Judge YAML部分身份校验缺口单列后续；不追加为本次出口。Luna2所述S1无预检H5/回执的判断未采纳：实际`diagnostics/s1/oracle_preflight/oracle/`已保留并索引H5、Oracle报告和Inspector；顶层命令摘要缺该调用仅记可追溯性限制，不影响真实Oracle证据。

F00前置已满足，允许准备F01新工作包；旧草稿未派发，需重新固定HEAD/官方稳定版本/安装环境/启动预算和资源，不能直接恢复旧授权快照。原7/22、Required Envelope、P99、R04b/c与其他slice不变。复核和独立审阅见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_f00_002/`及`sol_luna2_f00_review_001/`。

## F01 attempt002 execution（2026-10-29）

输入HEAD为`552c43aab8641608c64781fe5f6e6bfca38481a6`；实现提交为`015e620`、`5deeadb`、`5904f8e`。隔离Isaac Python 3.12.14、Isaac Sim/core/extscache-kit 6.2.0.0、Torch 2.11.0+cu128、NumPy 2.3.1的metadata核对及`pip check`通过；installed-source API/官方Panda资产配方已记录；11项provider-free S1通过，独立reader绑定固定plan/source hashes并重算trace中的bootstrap、refresh、steps与clock。

首次native App进程在Kit kernel bootstrap时要求EULA接受，非交互进程以`SystemExit`在`app_start`退出，0 physics steps；preflight通过，worker RSS峰值约8.4 MiB、RX差值432 bytes，无超时/resource abort，flock正常释放。该原件保留在attempt输出。维护者随后确认已接受EULA，授权包内唯一一次条件性重试；该启动使用`--attempt-second-start --eula-already-accepted`，由supervisor仅对子进程设置`OMNI_KIT_ACCEPT_EULA=YES`。

第二次worker进入SimulationApp路径后，在`driver.open()`导入`isaacsim.robot_motion.examples.manipulation.ManipulationScenario`时报`ModuleNotFoundError: No module named 'isaacsim.robot_motion.examples'`，发生于scene/asset/physics前。worker receipt记录`app_start_attempts=1`、`app_close_attempts=1`、`app_closed=true`、无cleanup errors、0 physics steps/0 trace rows；worker错误出口为1。父supervisor观察到进程组最终以`-11`退出，`worker_wall_seconds=821.487`，未超900秒，无resource abort/timeout；flock持有829.926秒后释放。resource preflight为MemAvailable 8,280,596,480 bytes / GPU0 6,643 MiB；运行期最小MemAvailable 3,082,502,144 bytes、最小GPU空闲6,138 MiB、worker组RSS峰值6,594,056,192 bytes；RX增量47,273,450 bytes、Omniverse cache增长52 bytes，均未超包内预算。

两次独立reader均输出`REJECTED_NATIVE_GATES`、0 trace rows；第二次reader确认plan/source hashes匹配，但app-stage错误、无asset inventory和无物理证据使native gate失败。首次reader也拒绝，且记录首次receipt使用的旧supervisor source hash与当前不一致。总计native启动2/2、physics steps 0/1200、simulation time 0/10秒；不启动第三次，不把本次诊断描述为F01 baseline PASS。F01的实际扩展导入问题交Sol复核；F02保持HELD，需后续单独冻结/授权。此诊断不表示Core Isaac adapter、当前Panda导入或Qualification。

<a id="f01-attempt003-sol-acceptance"></a>

## F01 attempt003 GPU PhysX native与Sol接收（2026-10-29）

attempt003以`ed4e5468daf19ad5f132242c44b4822b60992ad4`为输入，在Isaac Sim 6.2.0.0隔离环境运行官方Panda与0.08 kg刚体。首次Kit启动被非交互EULA提示挡在物理步前；维护者已明确接受EULA，第二次启动完成两轮`cuda:0`/GPU dynamics实验。总计486 physics steps（含6步bootstrap）、4.05 simulated seconds、worker wall 86.4秒、exit 0；每轮选中关节运动约0.09706 rad、cube下落约0.225 m、final home误差约0.002915 rad。32项独立reader gate及20项定向S1通过。启动资源预检MemAvailable 11,332,579,328 bytes、GPU空闲6,887 MiB；运行期worker PID VRAM峰值935 MiB、组RSS峰值6,114,865,152 bytes、GPU空闲最低5,921 MiB、MemAvailable最低6,380,040,192 bytes；RX增量3,022,266 bytes、Omniverse cache增长0，超预算项为空，锁在worker退出后释放。

Sol复核重新校验attempt003 42项SHA清单和attempt002 53项原件清单；用冻结运行源码副本重跑离线reader得到32/32通过，并重跑定向S1得到20/20通过。直接从develop-full目录重放reader时，仅运行副本supervisor的三个路径常量与tracked文件不同，导致源码哈希gate拒绝；attempt003所附native harness副本仅将`ATTEMPT_DIR`、`LOCK_PATH`、`ENV_PYTHON`指向隔离输出/环境，使用该精确运行副本后哈希gate通过。实现本地提交为`c88da2f`；复核receipt位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_f01_003/`。

接收为`ACCEPTED_BOUNDED_F01`，仅对应本次Isaac Sim 6.2.0.0官方Panda+刚体、CUDA GPU PhysX与上述资源/步数边界。attempt002失败原件与attempt003首次EULA启动记录不变；F02未启动。该结果不表示Core Isaac provider、真实当前Panda资产导入、其他任务/场景或Qualification通过。

<a id="f02-attempt001-usd-delivery-and-representation-resolution"></a>

## F02 attempt001 USD delivery 与表示选择（2026-10-29，历史候选；Sol要求返工）

输入为 `develop-full` HEAD `1632a11774d817f2ebe36198bbc40a74e7f36974`，冻结包及460项保护路径通过readback；代码提交依次为 `9acd7a8c08cb150221dd53a70abc8e7ac2595bef`、`c12578deba177a07fc2f2869850a4d31a5ef0cd2`、`99dc62a6efe296f42dcddfad6f9aaa114c91361a`。核心出口是严格版本化USD delivery/report/representation合同、同一Assembly owner的受控bytes loader与provider resolver、catalog独立`asset_deliveries`消费字段及CLI。旧 `AssetDefinition` / `TaskSceneSource` 身份不变；旧mock box检查和编译器不会把USD误作box。

最终定向provider-free S1为24项通过，受影响旧asset identity/closure回归19项通过。真实调用链从catalog CLI/`build_catalog` 到 `attach_asset_delivery`、Core delivery loader、OpenUSD composition和provider/build resolver运行；synthetic delivery保持在独立catalog字段，production默认拒绝。最终6文件fixture由OpenUSD 0.26.8解析，闭包含entry、reference、sublayer、payload、两variant分支和texture；独立进程重读报告/manifest/字节并通过，核出5个layer及1个asset dependency。reader通过所测18类tamper gate。相同source fixture也由GeoPhys固定gitlink `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`的公开`SceneSource.usd_path` importer消费，得到2 body/2 shape；这是source/IR导入，不含solver/runtime准入。

MuJoCo精确安装为Python/native 3.8.1/API 3008001，library SHA-256 `8969010a8325d32b9b154159862ffe3b112277cc993983a0168f7dbe2efe0592`。一次锁保护的微型USD decoder probe在compile前由实际build拒绝：`could not decode content` / 找不到decoder，未创建`MjData`、未forward/step/render；resolver因此拒绝MuJoCo native USD，不回退MJCF，也没有通用转换器。probe supervisor曾因把worker stdout最后一行warning误作JSON而记为`PROBE_FAILED`，其原件保留；posthoc重读首条worker JSON确认实际结果为`PASS_PROBE_REJECTED_USD`。官方3.8.1文档说明decoder由build选项启用且CMake默认关闭，完整版本/API/路线调研见F02包内`evidence/provider_representation_decision.md`。

S1迭代期间的launcher未启动、strict test失败及初次GeoPhys重放因缺`pxr`路径失败均保留；修正后的独立reader和GeoPhys probe分别在新run中通过。最终GeoPhys probe峰值RSS为134,708 KiB（约132 MiB）；独立reader及S1均远低于3 GiB单次限额。没有安装/升级依赖、下载官方资产、启动Isaac App、运行GPU/native physics、H5或Expert；官方Panda真实bytes及上游validated report仍未交付。Isaac 6.2.0只能在本resolver中选择原生USD表示，runtime仍`not admitted`。完整命令、运行账本、原始失败、readback和hash见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f02_001/`。状态为`F02_BOUNDED_DELIVERY_RESOLVER_PASS_PENDING_SOL_REVIEW`，不是Sol接收；F03及其他slice未启动。

<a id="f02-attempt002-bounded-delivery-resolver-repair"></a>

## F02 attempt002 delivery/resolver 返工（2026-10-29，待 Sol 复核）

输入为`develop-full` HEAD `469a6f9feef514dc7e4bbf0cc775747e37357be7`；冻结prompt SHA-256为`ac14740d501321521420ddb0f1b80bdc425fbf6b534547f8f4f3fd98443493ff`。Sol的attempt001复核提出两项定向修复；原attempt001的180项输出清单、460项保护路径及MuJoCo 3.8.1 decoder probe均复用并在本次收尾再次核对，没有更改原件。

R1在Core inspector中将临时snapshot root与entry layer路径分开。新增已保存的`nested/deep/entry.usda`样例，其variant/reference与sublayer使用`../../sibling/...`指向交付根内的真实sibling层，纹理、reference、payload和两个variant分支均由OpenUSD解析；Core loader、provider resolver、实际catalog builder和独立reader都通过该manifest。另一个同样嵌套的fixture加入指向snapshot外绝对路径的有效USD sublayer，Core和独立reader均拒绝。既有18类tamper、重定位、依赖更改/stale检查保持在合并S1内通过。

R2只把`native USD decoder is not enabled`归因于实际核验的完整身份`mujoco-3.8.1-libsha256-8969010a8325d32b9b154159862ffe3b112277cc993983a0168f7dbe2efe0592`。同版本其他library hash和假设中的USD-enabled身份均以“build/decoder未核实”拒绝；所有resolver结果仍`runtime_admitted=false`。Isaac/GeoPhys的选择只表示source格式可准备，不证明任意调用方build的runtime兼容。

Core实现提交为`0acadcd158850f49f92c3172af24548629ae9dc5`；更深入口回归提交为`f5e35e3b43ec90cf02e6665dd2d57463dcff2bb7`。干净提交树上的F02 26项及legacy资产身份/闭包19项合计45/45通过；最终`nested/deep/entry.usda`正反例单独运行也通过。此前一次合并集失败来自测试断言读取了`to_mapping()`中不存在的`identity_hash`，下一次运行在dirty checkout触发catalog既有provenance守卫；两次原件均保留，随后在实现提交的clean checkout修正断言并重跑全套通过。保护输入652/652匹配，attempt001的180项输出manifest也复核匹配。文档及Skill收尾提交、输出HEAD和最终hash见本attempt报告及`sha256.manifest`：`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f02_002/`。

没有官方Panda真实bytes或upstream-validated report；该限制保持披露但不是本次门槛。未启动Isaac/Kit、solver/materializer、decoder/native compile、physics、H5或Expert，也没有依赖修改/下载。结果为`F02_BOUNDED_DELIVERY_RESOLVER_PASS_PENDING_SOL_REVIEW`，不是Sol接收；F03和其他slice未启动。
