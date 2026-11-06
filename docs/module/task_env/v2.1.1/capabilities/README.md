# v2.1.1 能力与验收矩阵

3b attempt003 经[Sol独立复审](../maintenance/reviews/20261106_3b_attempt003_sol_review.md)接收为 **ACCEPTED_BOUNDED_3B_NATIVE_EXECUTION**：冻结三路线的实际模型／reset／执行／同次记录读回，以及Panda MuJoCo CPU开启补偿的最终350步保持与两任务方向检查已闭合。新N08-v2通过，原N08三路线FAIL保留；不外推全任务或跨后端重力补偿。3c仍待单独复审。6.1辅助App状态为VERSION_VERIFIED_CLOSE_TIMEOUT，仅启动／版本有真实证据，完整运行和正常关闭未通过；不提升最终能力格或Qualification。

[capability-matrix.json](capability-matrix.json) 是本版本唯一能力／目标矩阵。当前为规划矩阵：所有新目标 `NOT_RUN`，实现状态为 `NOT_STARTED`，证据引用为空。五协议已获维护者确认为实施基线，设计批准与实现／运行状态分列；本次不提升targets或最终cells状态。阶段状态另由[编排索引](../maintenance/orchestration.json)维护；它不授予能力。

当前已存在的实现和有界结果继续查询 [v2.1.0 matrix](../../v2.1.0/capabilities/capability-matrix.json)。新目标 NOT_RUN 不否认那些历史结果，也不把历史 native 结果升级为当前 renderer／控制／并行证据。

3a attempt002 的 PickCube31／Nut19 在真实MuJoCo3.8.1 CPU各完成公开创建/reset/10步/close，已获[Sol有界接收核心恢复](../maintenance/reviews/20261105_3a_attempt002_sol_review.md)。该段为attempt002时点；3a其后已由Sol有限接收，不因此提升三后端目标、最终九格或资格。

历史3a attempt001经[Sol复审](../maintenance/reviews/20261105_3a_attempt001_sol_review.md)需返工，该次没有新增native或qualified证据。Isaac6.1／6.2列入v2.1.1共同路线实现，5.1延期；按[兼容规划](../planning/isaac-deployment-compatibility.md)分列实现／离线／逐版本native状态。当前6.1有真实辅助启动证据，但完整Env闭环未测、App关闭超时，不能继续笼统写成从未启动或完整兼容通过。

## 更新规则

- 首批具体 runtime、资产、renderer、两个以上 batch 后端及代表性交集在 1a/1d 冻结。未知信息保持 null 和 reason，不能填写猜测版本。
- 每次更新记录实际 Core／provider commit、原生包与设备、task／source／Controller、renderer、batch 方式、配置身份、检查和原始 Evidence 引用。
- `IMPLEMENTED` 只指源码实现；`TESTED_BOUNDED` 指精确交集检查通过；`PARTIAL`、`FAIL`、`BLOCKED`、`NOT_RUN` 和经确认的 `DEFERRED` 各保留真实含义。
- 最终九格记录 `runtime_valid`、`task_success`、`solution_complete`、图像／记录／close 结果，未知为 null，不能以一个 pass 代替所有门。
- 本矩阵不等同正式 Qualification 或 Release，也不扩权未验证 source／solver／renderer 组合。

相关完成条件只在[执行与验收](../planning/execution-and-acceptance.md)及对应 Goal 维护。矩阵链接那里，不再复制第二套门。原始 H5／图片／日志保持 ignored，保留失败和真实运行身份。

Panda 本体重力补偿的 MuJoCo CPU 进程内有界运行和不支持组合见[指南](../guides/panda-gravity-compensation.md)。这是新增实现与有限证据，待独立复审，不自动提升本矩阵任何最终能力格。
