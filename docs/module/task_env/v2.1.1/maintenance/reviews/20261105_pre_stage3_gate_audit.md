# 阶段3前维护：当前验收门核对草稿

本页核对源码基线 `8416ef49e3af32f197fe13e847bfe4f02b7b98b5`，不是Sol复审决定，也不是阶段3启动授权。维护仍在进行；后续源码提交须重新核对受影响证据。详细变更和历史运行身份见[续作检查点](20261105_pre_stage3_continuation.md)，原attempt001／attempt002门结果不倒填。

| 门 | 当前判断 | 证据与缺口 |
| --- | --- | --- |
| G0 输入和范围 | PARTIAL | 本次核对tracked clean，仅有两份原保护untracked；SHA及两个gitlink与原快照一致。原始包和已有运行账本保留。综合离线命令有180秒超时，但本次没有连续RSS采样，不能据此宣称资源上限已独立核实。 |
| G1 代码结构 | PARTIAL | 生命周期R1在 `48401525` 获[Sol有限接收](20261105_lifecycle_unification_sol_review.md)；后续Marker公共组装、F06声明、动作／观测／记录职责及调用方Solution接线已有实现，均待Sol复审。当前Env仍有3867行，runtime的F05 Session分类仍引用任务候选类型，不能据此宣布全部职责整理完成。 |
| G2 功能和SHA | PARTIAL | 当前基线离线组合 **264 passed、1 skipped、5 deselected**，完整argv、输出和退出码在ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/audit-8416-offline.json`。包含生命周期、selected、R05b合成、记录、CLI参数及candidate接线；skip为缺少冻结Isaac解释器，排除项为真实provider／scene。XML和绑定源码摘要复用／替换、动态边界与篡改检查已有离线证据；TaskArtifact含可变内部映射，不安全地永久缓存其摘要。最终源码的PickCube31、Nut19完整物理和独立reader均未完成。 |
| G3 当前文档和启动 | PARTIAL | [API索引](../../../../../../task_env/doc/api/index.md)、[Solution接口](../../../../../../task_env/doc/api/planning/task_owned_solutions.md)、[安装与启动](../../guides/installation-and-start.md)、[任务开发指南](../../../../../../task_env/doc/自定义任务构建指南.md)及显式路径启动器已更新；安装组合、新手端到端native与全部适用入口仍未完整验证。历史阶段材料保留原身份。 |
| G4 证据和清理 | PARTIAL | `fa885280` 的三个classic单步、`f9cb51fd` 的PickCube31／独立reader只对应各自源码；不能重标到当前基线。Nut新caller路线及当前源码完整物理reader未运行。原120000物理步账本已预留至少115107步，新增完整Nut回归所需额外预算已向维护者提出，尚无答复。通用candidate正式Oracle／Judge的clean-check被两份保护untracked阻挡；合成调用链测试不冒充该预检。 |
| G5 本地交付 | PARTIAL | 本地提交及逐项记录已存在，当前不是最终交付、writer释放或Sol复审。待剩余代码与已授权验证完成后，冻结实际HEAD，补充最终报告、文档处置清单与窗口状态供维护者转交。 |

## 当前接口与文档处置

- 公共单环境入口是 `task_env.make_env(uid, *, config=None, render_mode=None, **kwargs)`；`BaseTaskEnv` 是 `SelectedReferenceEnv` 同对象兼容出口。组件任务仍经RuntimeBoundary，selected任务经RuntimeSession，共享episode协调；并行统一留待G06。
- PickCube与Nut当前示例由调用方执行 `Solution.act → env.step(action) → Solution.observe`；Nut要求来源绑定的控制请求与五样本反馈，PickCube的Position/F06新调用方路线只有合成验证。`step_expert()`保留为受限兼容，不是标准入口。详细签名与限制以[当前Solution接口](../../../../../../task_env/doc/api/planning/task_owned_solutions.md)和源码为准。
- 新手入口与实际示例由[安装与启动](../../guides/installation-and-start.md)、[任务开发指南](../../../../../../task_env/doc/自定义任务构建指南.md)、`examples/start.py`及`examples/tasks/declared_marker.py`共同承接；显式路径、state-only和依赖冲突边界已写明，不把静态检查当全新安装成功。
- [迁移附录](../../../../../../task_env/doc/api/appendix/migration.md)保留历史旧入口作为受限兼容说明；`v2.1.0`及更早文档、历史H5、raw和原评审不改写。仓库TaskEnv skill的路线图已按R1接收更新，但当前续作仍待复审。

## 不可重标的原生检查

- GeoPhys CPU Empty／Pendulum／TwoWheel：每项在 `fa885280` 各reset、一个control interval、close；只支持该源码和最短路径。
- MuJoCo CPU PickCube：`f9cb51fd` seed31、horizon1000，960 transitions，任务与Solution完成，独立reader通过；它不证明本页基线。
- MuJoCo CPU NutAssembly新调用方路线：当前源码物理回归和独立物理reader均为 `NOT_RUN`。未启动Isaac、GPU或新native窗口；其他用户的共享仿真使用必须继续受双锁保护。

保护文件SHA-256：`MUJOCO_LOG.TXT` 为 `dfb37ada202855d609f9e210cf79b287de78f2ded70e704ceeb544d17bf7ad4b`，`docs/maintenance/20261030_runtime_route_diagnostic_handoff.md` 为 `18cc56c7f0ffbcb947db4bd8725279489171efbee8f08b28603b79c47f509d61`。GeoPhys为 `67da1165149486d3ae3e779c13ce31af49e17d50`，Menagerie为 `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。
