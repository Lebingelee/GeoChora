# G01/1b attempt001：统一任务表示设计交付摘要

日期：2026-11-03。执行结论：`PASS`（1b 设计交付）；执行状态：`REPORTED_PENDING_REVIEW`。这不是协议接受/冻结，也未开始 1c。

## 交付与核实

- 冻结输入 HEAD：`498f03b55b3f557af962f98d2f7b5c9f543262c2`，branch `develop`；GeoPhys pin/检出 `67da1165149486d3ae3e779c13ce31af49e17d50`。
- 核对 package manifest checksum、快照列出的 69 个输入文件、2 个保护文件及 10 份 1a accepted raw output；全部 hash 匹配。初始 tracked tree clean，原有两个未跟踪文件和 ignored 资产保持。
- 权威设计正文为[统一任务表示草案](../../contracts/unified-task-representation.md)；源码/caller 和官方来源索引在[source map](../../planning/source-map-and-references.md)；可审阅 JSON 例子为[representation cases](../../planning/representation-cases.json)。原始执行报告和 SHA-256 清单在 `workspace/maintenance/v211_g01_1b_attempt001/`。

## 采用的设计

1. 不建顶层 TaskIR。Task semantics 留 Task Artifact/TaskDefinition；Scene/Asset/Source 各留现有 Core owner；编译绑定与动态 state/capture publication 分开。
2. 精确复用 Scene v1-v3、TaskArtifact v0/v1、TaskSourceV1 和 ExecutionSpecV1 codecs。旧 identity 不重签。Scene-v3 物理参数/碰撞/视觉 representation 与 mapping 欠 typed owner；只有真实消费者到位时，在同 `SceneDefinition` owner 增加有版本的最小模型/representation/mapping types。ExecutionSpecV1 无法明确拆分 provider、host、engine、solver/coupler 和环境；建议同 execution owner 版本化 ExecutionSpecV2，不扩大 v1 字段。
3. `JointDefinition`/typed state 已表达 floating Joint 的 7 个 position、6 个 twist；TaskArtifactV1 的 required Joint reset/state bridge 仍仅接纳 scalar。PickCube cube 是被动 free Entity：reset/source 绑定和 pose/state 需求独立于 action/effort；现有 dynamic camera 仍拒绝 free_joints。
4. 同语义 Entity 可关联 mechanical/collision/visual 表示及来源、Frame、映射和 topology generation。native importer lowering 是执行记录；改变 representation 的 asset harness 输出必须有独立来源/recipe/output identity。可表达要求不等于 provider admission。
5. Timebase 仍进入现有 TaskArtifact v0/v1 identity；dt/substeps 改动会改变当前 Artifact hash。backend/render route 由 ExecutionSpec/resolved config 分开绑定。未来若拆分 identity 必须升版本并显式迁移，不能改变历史 hash。
6. 一份同构 Scene template 通过 scene instance/env/episode/reset ID 与 batch axis 引用多实例；native batch 与 process vectorization 分开。每批统一 provider/config；reset 不迁移旧 state，observation/camera contract 固定。

## G0–G5 出口自检

| Gate | 执行结论 | 依据与限制 |
| --- | --- | --- |
| G0 输入／范围 | PASS | manifest、全部冻结 hash、provider pin、branch/HEAD、dirty paths 和保护输入一致；仅改允许文档及 ignored raw 输出；native、physics、GPU 和实现测试均为 0。 |
| G1 四类表示 | PASS | 四类字段/单位/条件/owner/caller、现有复用与建议扩展理由写入权威协议；无生产代码改动。 |
| G2 关键边界 | PASS | scalar/floating layout、qpos/qvel/effort、被动 free cube、三种资产表示映射、execution 层级/coupler、native/process batch 和实例 identity 均明确。 |
| G3 身份／兼容 | PASS | 当前 Artifact/Asset/Scene/TaskSource/Execution/publication hash 分层、Timebase 影响、严格版本 codec、PickCube/NutAssembly/LIBERO/legacy 路径处置和 unknown-capability rejection 已列明；未宣称 caller 已迁移。 |
| G4 案例／文档 | PASS | P1–P4、N1–N5 为独立 planning JSON；ID/reuse/owner reference/disposition 核对通过；文档 current validator 与 JSON/依赖/status 检查见原报告。设计 JSON 不是 runtime validator。 |
| G5 完整交接 | PASS | 完整报告、findings、commands、输入快照、输出 manifest、输出 HEAD/commit 和 hashes 均在 ignored raw 目录；唯一写入者已结束写入，未进入 1c，待 Sol 审阅。 |

## 待维护者确认

- 是否认可 Scene-v4 在既有 Scene owner 内承载最小 typed physics/model 与 representation mapping。
- 是否认可 ExecutionSpecV2 分离 provider/host/engine/solver/coupler/precision/environment，并保留 v1 exact decoder。
- 新 Artifact 版本是否继续将 Timebase 放在 task identity 中；本交付建议 v0/v1 保持不变、将来只显式迁移。
- PickCube 质量/惯量约 5% 的均匀立方体解析差异仍待资产 owner 确认；本次保留源值。
- 直接 entity wrench 是否属于后续任务需求；本设计不把被动 cube 增加为 action target。

协议草案仍为 `DRAFT_FOR_DISCUSSION`。本摘要不签 `ACCEPTED`/`FROZEN`，不授予运行能力或 Qualification。
