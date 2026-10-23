# R03 — Physical Attachment

状态：REVISED_DRAFT；R03a/b/c 均 PLANNED / NOT_STARTED。以下已发生探针是前次审阅事实，不是本阶段 slice 完成或 Native S2/S3。

## 已知事实与精确 Provider 路线

Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` 的 [panda_nohand.xml](../../../../../asset/external/mujoco_menagerie/franka_emika_panda/panda_nohand.xml) + [hand.xml](../../../../../asset/external/mujoco_menagerie/franka_emika_panda/hand.xml)，许可 [Apache-2.0](../../../../../asset/external/mujoco_menagerie/franka_emika_panda/LICENSE)，是两个独立资产来源，不能用完整 Panda 替代。

| 先前审阅观察 | 结果 | 不构成的证明 |
| --- | --- | --- |
| MuJoCo 3.8.1 分别加载未修改资产 | 编译成功：arm nq/nv/nu=7/7/7，hand=2/2/1、neq=1、ntendon=1 | 不证明 Core admission 或手的真实运动 |
| 公开 MjSpec.attach，以 prefix 把 Hand 挂到 Arm link7 frame 后编译 | 成功：nq=9、nu=8、neq=1、ntendon=1 | 无 solver/reset/step/Controller/H5；没有该独立装配的 Native S2/S3 |
| 同一导出 MJCF 经 GeoPhys a53 公开 SceneSource/import_scene_source | 拒绝：`geometry.articulation.site_config.invalid`，`site size: exactly 1 real, non-bool values required` | 只阻塞这份 source dialect；不证明所有 GeoPhys Attachment 不可能，也不改变 Phase II 旧路线结果 |

该导出 sphere site 带三分量 size；[MJCF parser](../../../../../GeoPhys/src/geometry/mjcf_loader.py) 将它交给 [SiteConfig](../../../../../GeoPhys/src/geometry/articulation.py)，其 [site_size](../../../../../GeoPhys/src/geometry/site_volume.py) 校验精确形状宽度。原导出 XML/JSON/失败日志仅保全并记录 hash，见 [planning manifest](planning_manifest.json) 和 [README](README.md#provenance)；本轮未重跑或修复它。

拟定 **MuJoCo 3.8.1 CPU** 为首个 Required Provider。当前仅 source compile 可行，R03 S2/S3 = NOT_RUN，不能称运行支持。GeoPhys a53 为第二 Provider：这份导出 source NOT_ADMITTED/BLOCKED，未获 Assembly Qualification；新独立装配 S2/S3 非首版 required，但失败与准入边界必须记录，不自动改为 DEFERRED。增加第二 Provider required 范围须维护者单独批准。

## R03a 提前 Gate 与可审计策略

前置改为 **P00**，不等待 R01a codec。先做 source feasibility，再投入大规模 lowering；可使用已审议的 mount/identity 草案，不以逻辑 Assembly 已实现为前提。

必须盘点：source dialect/版本与实际消费闭包（XML、mesh、default/include、纹理、license、prefix/name remap）；两个来源各自 root 与 mount；inertial frames/质量/单位；joint axes/limits；Equality、Tendon、mimic/驱动资源；碰撞几何与 exclusions；canonical→native body/joint/actuator 的顺序和逆映射；keyframe/reset、固定-base/child root 处置。信息存在于 source 不等于目标 solver 消费了它；逐项 CANONICAL_REPRESENTED / SOURCE_RETAINED / NOT_ADMITTED，必需语义缺失就停止。

GeoPhys owner 的候选策略：① 在其既有 MJCF importer 明确支持合法的 padded site dimensions 并验证有效维度/冗余值；或 ② 现有 Core source owner 采用带版本的、保持语义的 source normalization，保留原始 bytes、变换规则和新 closure，并经独立审查。两者均只是方案，未授权实施、未选择、未获得 Provider 批准；不得删 site、丢 equality/tendon 或放宽所有维度校验求通过。若需新 Provider pin，另行批准并记录新 Evidence，不移动冻结 pin/旧收据。

## 物理 lowering 与 Oracle

Attachment intent 独立版本化：stable Assembly ID + logical content hash、parent/child Entity 与 typed mount refs、kind=fixed、`T_parent_mount_from_child_mount`、碰撞白/黑名单、root 处置、source/closure。Attachment hash 不参与 logical hash 的反向自指；materialization receipt 绑定本次 Provider/build/backend/native topology 与映射。

首版为静态无环固定连接树，child 仅一个物理父级。MuJoCo 允许通过 jointless child body 的固定树表达约束，不要求创建不存在的 native fixed DOF；必须记录 canonical Fixed Attachment→native 固定关系的 lowering。独立 Hand 不保留第二个 world root，不能受两个 Runtime 推进。两个 canonical Entity 可映射同一 native articulation 的不同 link 集，但身份不融合；现有 single-Robot/dual-independent-root admission 不可直接冒充 attached-pair admission。

Oracle：`T_WC ≈ T_WP · T_PC`，米、弧度、wxyz，明确变换从 child mount 到 parent mount；分别检查位置范数/旋转测地误差。R03a 基于 source 精度/analytical FK 预先冻结 tolerance 与接触/自由运动片段，不事后调宽。必须在重复 reset、连续 Arm 运动、Hand 开合及受控接触/负载中测量刚性相对位姿、真实 q/pose 变化、coupling、有限性/稳定性与 collision filtering；看起来贴合、compile/FK 一致均不能替代动力学证据。

## 切片

| ID | 前置 | 工作与交付 | 必需 Evidence / Stop Condition |
| --- | --- | --- | --- |
| R03a | P00 | MuJoCo CPU source/closure/机械语义的早期真实可行性与 GeoPhys 精确拒绝审计 | S1 + 最小 native S2 probe；当前 compile 仅先验。无法证明独立 fixed dynamics 则阻塞 b/c，提交 owner/成本/兼容策略 |
| R03b | R01c,R03a | 既有 assembly/source/materialization owners 中固定树 lowering、root/collision/逆映射与新准入 | S1 错 mount/环/重复 child/root/source/顺序拒绝；S2 reset/运动 mount invariant；禁止降低旧 admission 保护 |
| R03c | R03b,R02c | 独立 Arm+Hand 真实 Position 施控，现有 public Env→Recorder→reader | S2/S3：同一个公开实例 reset/连续 step/observation/H5 T/T+1/request/Target/Ack/state/identity/close；无真实 hand actuation 或 native coupling 即失败 |

S3 必须沿现有 factory/SelectedReferenceEnv 或已明确批准的公共 candidate 入口，在原 RuntimeSession/Recorder owners 扩展；public path 不导入 test_*。失败保留原日志、partial apply/fault receipt、资源关闭检查；不伪装 rollback。R03 不依赖 Camera 或 R05 force-only 路线；不引入动态 attach/detach/闭环约束拓扑、USD ABI 或第二 Runtime。外部装配语义参考固定 [Isaac Sim 6.1.0](README.md#references)。
