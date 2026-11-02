# Phase A 开发记录 — Object Model、来源与兼容

> **2026-10-23 范围决定**：本记录声明的交集按 [维护者决定](../../../../maintenance/phase_ii_scope_freeze_20261023/maintainer_scope_decision.yaml) 获有界工程接受；历史 S0/S1/S2/S3、失败、原 pin 与缺失原件记录保持原义。本次范围冻结不产生新 Task freeze、发布或 Qualification。

日期：2026-10-22。当前处置：A01–A05 的声明静态工程出口满足；真实 materialization、施控和渲染的证据分别归 C/D。
目标契约见 [01_Phase_A_Core_Object_Model.md](01_Phase_A_Core_Object_Model.md)；统一状态见 [05](05_Architecture_Review_and_Execution_Order.md)。

## A01

在唯一 `task_env.artifacts` owner 增加 immutable `AssetDefinition`、`EntityInstance`、`SceneDefinition`，区分可复用定义、场景实例和 native handle。
相同 Asset 的多实例具有不同 Entity identity；严格 codec、未知字段和重复身份拒绝。没有新增 Registry、Runtime 或 Provider loader。
历史 S1：31 passed。Evidence：`workspace/maintenance/phase_ii_a_20261020_A01_004/`，具体命令与原始版本见下方历史原文。

## A02

同一 Scene owner 版本化增加 Frame/Articulation/Joint 结构；保留 Scene v1 mapping/hash。
Frame 为 Entity-qualified 引用，authored-fixed 与 runtime 锚点分开；world pose 不能从含 runtime ancestor 的纯静态链推导。
joint position/velocity 分别声明布局，spherical 为 4/3，floating 为 7/6；结构支持不代表 native 实现支持。
独立 transform、cycle/missing/跨 Entity 引用、multi-articulation 与 legacy identity 联合 S1：49 passed。
Evidence：`workspace/maintenance/phase_ii_a_20261020_A02_004/`，`a02_receipt.json` 固定源文件摘要。

## A03

`scene-definition-v3` 在同一 owner 增加 `RobotInstance`、`ActuatorResourceDefinition` 与 `ControlGroup`。
RobotInstance 使用原 Entity ID，不再创建可分叉的 robot ID；资源引用采用 tuple/typed refs，不依赖字符串拼接。
Group 只声明静态资源，不隐含 Controller、action width、mode 或时序；当前 v3 拒绝重复有效 writer、未知资源与跨 Entity Group 引用。
单/双 Robot 命名空间和真实 reference resolver 的静态检查通过。后续双 Entity Position 的真实动力学证据归 [C02b](C_Development_Record.md#c02b)，不回写成 A03 原始证据。

## A04

复用 `AssetManifest`、现有 assembly、registry 与 GeoPhys public importer；不复制 parser。
Panda 固定来源闭包为 68 个文件（XML + 67 OBJ/STL），40 条 Source→Imported→Canonical 映射；298 条 capability semantic entries 逐项处置。
独立 XML 清单 230 节点中，28 映射到 Canonical，202 SOURCE_RETAINED。geometry、inertia、limits、tendon/equality、contact exclusions 等未表达内容保留来源及 locator，不冒称完整 canonical 化。
procedural `square-peg-v1` 记录 generator/version/参数和内容摘要；不同 checkout root 的同字节来源得到相同 closure digest。
旧 factory/UID/reference 与 unknown/duplicate 拒绝联合 S1：63 passed。
Evidence：`workspace/maintenance/phase_ii_a_20261020_A04_001/`；只读预审探针在 `phase_ii_a_20261020_A04_REVIEW_001/`。
受控快照及导入后字节核对不等于对任意可变目录的原子 importer consumption 保证。

## A05

A04 Panda/peg receipts 合并为 Scene-v3，identity 为 `047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e`。
34 条 canonical 字段映射完整携带来源摘要；原样 Scene-v3 mapping 是批准的 D01a 输入。
NutAssembly 只读兼容投影保持 frozen world-v0 Artifact hash `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe`；
PickCube hash 保持 `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`。
NutAssembly hand-local `ee` 投影不能使 A05 原始 Panda source 自动具有 `nutassembly_ee_site`；后续 Position 使用独立 hand-origin TCP。
A03–A05 在 B04a→D02a→C01a→D05a 前置补齐后复验：A 子集 64 passed，联合 91 passed。
Evidence：`workspace/maintenance/phase_ii_acceptance_20261020_d05a/run_metadata.json`，A05 receipt SHA-256
`d2ef1a18d4c47a36584c3875a2fde889016a42ba32a71b7246c5af1662f627eb`。

## 所有权、延期与复现

Scene 是唯一静态结构权威，AssetManifest 是来源描述，TaskReferences 是编译后映射；三者不维护独立可写世界。
v1/v2/v3 Scene 版本分开 strict dispatch；旧 world-v0 不伪装成 Scene-v3。
Logical Robot Assembly/Physical Attachment 仍为后续候选，不加入当前 C02b 前置，也不把 dual Position 当 Assembly。
当前本轮仅整合文档，未重跑上述历史测试。

原始完整设计/收据：[整合前 A 文档](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/01_Phase_A_Core_Object_Model.md)；原始五草案由 `a299d8b` 保存。
本地原文、原分支 refs 与恢复 bundle 见 [05 保全说明](05_Architecture_Review_and_Execution_Order.md#preservation)。
