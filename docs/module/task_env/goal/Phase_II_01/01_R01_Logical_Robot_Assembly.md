# R01 — Logical Robot Assembly

状态：REVISED_DRAFT；R01a 静态值合同与 provider-free S1 已获 Sol 接收（ACCEPTED_S1_BOUNDED）；R01b bounded 静态解析已获Sol接收（ACCEPTED_S1_BOUNDED；Sol修正早期深度门后82 passed）；R01c attempt001 source/compiler 声明级投影与18项 provider-free S1 已获Sol接收（`ACCEPTED_S1_BOUNDED`）。本 Goal 只实现静态逻辑引用，不承诺物理连接。

## 当前 owner 与版本边界

[Asset/Entity/Frame/Joint/Robot/Scene contracts](../../../../../task_env/artifacts/contracts.py)、[source bridge](../../../../../task_env/runtime/sessions/source.py)、[assembly compiler](../../../../../task_env/assembly/compiler.py) 是复用点。现有 RobotInstance root 属单 Entity，JointDefinition 拒绝跨 Entity endpoints；assembly compiler 是特定 source 配方，不是通用递归 Assembly。

EXTEND_EXISTING：优先在 artifacts owner 增独立版本化 Assembly 引用合同，由现有 compiler 消费；不为逻辑引用先行要求 Scene v4。若物理 lowering 确需新 Scene/Artifact envelope，R03b 必须提交显式版本派发方案；Scene v1/v2/v3 的 mapping、strict fields、hash 与旧 Artifact/Entity identity 保持原样。

### R01a 已实现的静态合同边界

`task_env.artifacts.LogicalAssemblyV1` 使用唯一 schema `logical-assembly-v1`，字段为 `assembly_id`、`revision`、`scene_pin` 和 `members`。`scene_pin` 是 `LogicalAssemblyScenePinV1`，锁定 `scene_id`、既有 Scene schema v1/v2/v3 与 `scene_identity_sha256`。`decode_logical_assembly()` 显式派发此版本；未知/缺失字段、未知 member kind、跨 kind 字段和错误 digest 均拒绝。

`LogicalAssemblyEntityMemberV1` 是逻辑 owning member，显式保存 component path、Scene Entity ID 与 asset ID/version；本合同不会创建第二个物理 Entity，也不验证 Entity/asset 是否存在于已 pin 的 Scene。`LogicalAssemblySubcomponentReferenceV1` 是 reference-only，target 必须是既有 `FrameReference`、`JointReference`、`ActuatorReference` 或新值 `LogicalAssemblyControlGroupReferenceV1`；它不使用 `ControlGroup` 定义冒充引用，也不赋予 writer 权。`LogicalAssemblyNestedMemberV1` 只编码固定 child assembly ID、revision 和 `logical_content_sha256`；child 存在性、摘要匹配、递归闭包、环、跨层重复 owning、悬空引用与 32/1024 预算交由 R01b。

Component path 保持 segment tuple；空路径、空 segment、`.`、`..`、分隔符和 percent 转义被拒绝。同层 path 与相同 typed target 重复也被拒绝。members 按 path/kind/typed target 排序。logical identity 是 schema、稳定 assembly ID/revision、Scene pin 和排序成员 mapping 的 canonical JSON SHA-256；计算出的摘要不写入自身 payload。`to_mapping()` 返回与内部值脱离的 JSON snapshot。这个值不解析 Scene、不生成 source/native mapping、不执行 Runtime 或连接物理 body；R01c 投影与 R03 lowering 仍未实现。

### R01b bounded 静态解析

`task_env.artifacts.resolve_logical_assembly(root, scene, child_assemblies)` 消费一个 `LogicalAssemblyV1`、精确现有 `SceneDefinition` 与以 `(assembly_id, revision)` 为 key 的显式 child catalog。输入先在 detached strict snapshot 上重验；只有 root 可达闭包参与 Scene-pin、child digest、Entity/Asset 与 typed Frame/Joint/Actuator/ControlGroup 检查。Scene v1 仅允许 Entity leaf；Frame/Joint 要求 Scene v2/v3；Actuator/ControlGroup 要求 Scene v3。runtime Frame 只按 entity-qualified identity 静态查找，不求 pose。

解析先以 Assembly key 检出直接/间接 containment cycle，再校验 child logical content SHA-256；不依赖自洽循环hash。展开将 nested path 与 child member path 作为 segment tuple 连接，结果按完整路径/kind/typed target 确定排序。闭包内 Entity 只能有一个 owning member；reference-only typed target 可指向同Scene已有Entity（包括其他叶的owner），不创建第二 owner/writer。相同 typed target 多路径alias及展开路径碰撞拒绝；不同 Entity 使用同一 Asset 保持为不同实例。root 深度按1计，最大32层；Entity member 与 Subcomponent Reference 各计一个 leaf，最大1024。调用内有限memo避免共享/空child重复递归展开，超限时在构造结果期间拒绝。

返回 `ResolvedLogicalAssemblyV1` 与不可变 `ResolvedLogicalAssemblyLeafV1`，记录root/Scene身份及每个leaf的full path、typed member、原 Assembly ID/revision/hash 与local path；它不增加旧codec字段或hash，不产出新的持久化 ABI。入口是advanced静态值API，不连接当前Runtime/source/compiler，不生成native mapping、物理连接或Task Source；R01c现已在既有source/compiler owner增加其后续静态投影。

### R01c 静态source声明投影（attempt001，Sol已接收静态出口）

`task_env.assembly.project_logical_assembly_source(root, scene, child_assemblies, source_receipts=None)` 每次从当前root、精确Scene和child catalog重新调用R01b resolver；它不接受调用者提供的resolved值作为准入收据。投影以唯一Entity表关联现有 `EntityInstance`、完整 `AssetDefinition` 及其声明identity，并按leaf保留segment tuple路径、owner/reference-only kind、原Assembly身份/hash/local path与typed target definition。Frame/Joint/Actuator使用精确Scene definition；ControlGroup保留其Actuator refs并展开至对应Actuator definitions，不推导native顺序。多个leaf复用同一Entity时source Entity只出现一次；不同Entity即便共用Asset仍分别保留。

投影是 `logical-assembly-source-projection-v1` immutable snapshot；自身 `identity_sha256` 是该版本canonical mapping的非自指digest，`to_mapping()`每次返回脱离内部值的JSON副本。A05完整Panda arm/gripper views共享 `panda-main`；独立Arm/Hand静态fixture保留Menagerie固定pin下的两个Entity/Asset来源声明。`source_content_sha256` null和历史receipt分别按原值保留；receipt只匹配Scene/Asset声明并标记 `MATCHED_DECLARATION_NOT_REVALIDATED`，不重读或验证bytes/closure。静态投影不lower/attach XML、不创建第二Scene/物理Entity/writer/native名字或indices、不调用旧 `compile_task_scene()`/Provider、不准入Runtime或Attachment。Sol已复核实际差异与原始18项S1，接收此声明级静态出口；不扩大为物理或执行准入。

### Sol复核（2026-10-27）

Sol审阅 `1ea9aee447d19640f36eb1c827c2221a23ec0e1c` 的10文件差异与81项S1证据，发现超深输入先触发Python RecursionError；已直接在递归入口增加32层门并补1100层回归，保持原cached-height检查及1024 leaf限制。5项定向检查通过，原四文件集合82 passed，接收R01b为 **ACCEPTED_S1_BOUNDED**，无需另开返工。旧codec/hash、R06 ledger、DAG/P99保持，native与R01c未运行；下一表行为R02a。复核证据见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r01b_001/`。

## 两类成员与拥有关系

| Member kind（拟议 discriminator） | 引用对象 | 拥有/消费语义 |
| --- | --- | --- |
| Entity Member | 给定 Scene 内已存在的唯一 Entity instance，绑定 asset/version/scene identity | 逻辑 owning edge 只表示该 Assembly 管辖其资源寻址；不分配第二物理实例、不自动连接 |
| Existing-Entity Subcomponent Reference | 明确 Entity 内的 typed Frame、Joint、Actuator 或 ControlGroup ref | 只读逻辑选择/视图；不得被注册为新 Physics Entity、articulation root 或额外 writer |
| Nested Assembly | 精确版本的子 Assembly stable ID + 内容摘要 | owning containment 无环；递归解析为上述两类 leaf，不复制子图 native state |

同一 Entity 在 owning containment 闭包只能有一个 owning member；不能被两个父 Assembly 同时 owning。同一 Entity 的 arm/gripper 可以是两个不同 ControlGroup 子引用，属于合法只读视图，不是重复 Entity ownership。跨 Assembly 的只读引用可以指向已有 owning member，必须显式标注 reference-only，不参与拓扑拥有，也不能因此获得执行器写权。相同 typed target 的重复成员/alias 拒绝；如仅为显示别名，应使用唯一 canonical path 的别名表，不创建第二成员。

## 递归、路径、身份与非自指

- stable Assembly ID 由作者给定、Scene-scoped、与内容 hash 分离；同一 ID 的新 revision 可有不同 content hash，旧引用必须锁 revision/hash。
- component path 用规范化 segment tuple 表示；空 segment、`.`、`..`、未声明转义/歧义 alias 拒绝，不靠 `/` 拼接解析 native 名称。声明顺序无关，按 canonical path/type/ref 排序。草案上界：32 层、1024 个展开 leaf；P00 可提出基于真实需要的调整，未批准前不默许无限递归。
- 拒绝 containment cycle、reference resolution cycle、悬空引用、重复 owning、错 Entity/Asset/Scene revision、无法唯一解析的 Frame/Joint/Actuator/Group；全部在 Provider 构造前完成。
- logical content hash = schema + stable ID/revision + Scene reference + 排序成员/typed refs + 已解析子 Assembly content hashes。自身份不包含自身 content hash、native handles、Provider indices 或 mutable state。
- Attachment intent 引用 stable Assembly ID + 精确 logical hash；Attachment hash 不回写 logical hash。composition digest 再组合 logical hash、Attachment hash、effective profile hash 与 source closure。这样只有有向依赖，没有 Assembly↔Attachment 的循环摘要。

## Canonical 到 Native 的责任

R01 持有 canonical refs，不持有 native body/joint/actuator indices。R03 的 source/materialization owner 负责 namespacing、joint/body/actuator 顺序置换和反向表，并绑定 source closure、Provider build/backend、scene/materialization identity；RuntimeSession 仅消费已验证 mapping。Renderer、Task、Controller、Recorder 不能各自猜测或维护第二份可写 mapping。固定连接可能融合 native articulation，但两个 canonical Entity 的 provenance 必须仍可追溯。

## 切片与出口

| ID | 前置 | 工作与交付 | 必需 Evidence / Stop Condition |
| --- | --- | --- | --- |
| R01a | P00 | 既有 artifacts owner 中两类 member、hash DAG、版本与边界设计/codec | provider-free S1 已通过：strict discriminator/roundtrip/non-self hash 与旧 Scene/Artifact 基线保持；报告 `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r01a_001/report.md`；Sol已接收该静态S1出口 |
| R01b | R01a | 递归 owning/reference-only 解析、typed paths 与有界负例 | provider-free S1 已实现：环/悬空/重复拥有/错Scene/child/typed target/alias/路径碰撞/32层与1024 leaf边界；Sol修正递归入口深度门后已接收（82 passed），报告在 ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r01b_001/report.md` |
| R01c | R01b | source/compiler 的只读投影与可追踪 leaf refs | S1：完整 Panda 内 arm/hand subrefs、独立 Arm/Hand Entity members 两类 fixture；canonical refs 不产生物理 joint |

本 Goal 不依赖 R04/R05。S1 不能作为 R03 的动力学或 R02 的执行证明。逻辑投影/只读view必须不可变；codec `to_mapping()` 可返回独立JSON副本，修改副本不能回写合同。关闭运行时不破坏可独立持有的逻辑值。接受条件与依赖唯一入口为 [07](07_Execution_Order_and_Acceptance.md)。

2026-10-27，Sol完成R01c attempt001复核，未发现需要返工的实现问题，接收为 **ACCEPTED_S1_BOUNDED**。复用未改动代码的18项provider-free S1与原始日志；20项交付哈希、9份保护输入、10个旧compiler函数、11份Phase Markdown哈希及R06 ledger均匹配。文档validator的152→156仅四项预期代码scope提示，无新增文档错误。下一包按执行表进入R02b effective leaf plan及真实adapter/preflight的provider-free实现/S1；native/S2/S3/S4仍未运行。复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r01c_001/`。
