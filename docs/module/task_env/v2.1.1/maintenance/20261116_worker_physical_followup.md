# Scalar worker physical端口与模型收尾

2026-11-16；维护者授权审查、实施与测试，随后明确增加MuJoCo模型代理及physical worker reset，并要求Controller选择／匹配归Robot、Controller和公共绑定。输入Core `704e3f094b0a69761cb272ded4b5d94be8ab378a`；沿用`codex/v211-stage6-parallel`。GeoPhys pin `198d30ac64ce873a1467f55d2adfc471db18fbc5`、Menagerie pin `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`未变。未启动G07或增加G06 attempt。

## 方案质疑与判断

原方案方向成立，但只放开worker guard并不够：实际缺口还包括G05提交owner直接读取本地physical port，以及source adapter仍整类拒绝CPU physical worker。仅有RemoteSession方法或ACK不能证明接线完成。

不把整个Env／Controller调度搬到worker，也不重写builder优先级框架。只提取两端重复的native装配、保留既有声明owner和生命周期。worker可以重建Controller声明，却不初始化／计算physical Controller。最初建议将模型依赖留为拒绝；维护者明确要求加入本轮后，复用原MuJoCo scratch model，新增受约束的值代理，并落实真实physical reset重建。

代码总行数会增加：必要的IPC值编码、绑定确认和模型代理都有实现成本。简化体现为一处native装配和明确的所有权，不是净删行。没有另建Env、Runtime、任务factory、Controller manager、provider框架或通用RPC。新增能力复用由现有绑定／Controller声明决定，不能按profile扩充worker分派。

## 当前owner与实际接线

| owner | 本轮工作与边界 |
| --- | --- |
| Robot／Controller及公共绑定 | 既有选择与匹配不变；reset capability编码和恢复最终kind／参数／generation，factory仍归Controller owner |
| selected_materialization.py | 进程内builder和worker复用native装配及Position端口准备；既有builder声明、优先级、匹配检查与initial-state能力保留 |
| worker.py | 消费重建后的绑定与能力需求，绑定真实物理端口；按source dynamics能力提供模型值查询，不识别Controller profile／任务／Robot名称 |
| transport.py | 仅增加实际使用的joint-effort物理端口、白名单value编码、真实绑定核对；MuJoCo model的metadata/evaluate值代理，不传Controller、SDK或任意ndarray |
| control_submission.py | 同一个G05提交owner消费本地native绑定或经远程核验的本地声明；未制造假的本地native port，也不新建动作队列／调度器 |
| api.py／source_composition_adapters.py | 将整类worker拒绝替换为真实能力边界；保留provider/source检查，worker动态模型只准入MuJoCo CPU，BodyWrench仍拒绝 |

主进程持有physical Controller的唯一有效运行状态，使用实际reset初态初始化，计算typed effort；共同提交owner执行原区间／资源检查。worker验证实际源、资源、writer／版本／generation，写入一次并返回native ACK，随后响应一次原session.step。通信异常沿原fault/reset机制处理，不自动重发。

MuJoCo模型代理只传joint state、boundary和mass matrix／bias结果。原scratch data留在worker；无物理推进、无通用SDK访问。保留原模型在同episode内对指定state的纯查询语义，不额外强迫boundary等于当前revision。外来episode拒绝；旧remote session关闭后旧模型代理不可再用。既有模型自身的Robot/source限制不扩大。

## 验收与证据

真实调用走普通make_env；与进程内相比不替换Task／Robot或物理参数。独立数值对照允许`atol=rtol=1e-10`，实际所测字段差值均为0。不是跨引擎对齐或力标定。

| 实际交集／检查 | 结果与范围 |
| --- | --- |
| GeoPhys CPU Pendulum默认worker | seed73/74各reset＋3个非零动作；6次Controller计算均在主进程；二次reset、旧worker退出与重复关闭 |
| GeoPhys Pendulum进程内／worker | 两seed的完整状态obs／reward逐值一致，最大差值0 |
| GeoPhys双轮canonical worker | 两个不同非零轮力矩、多关节及自由根真实状态、二次reset；child禁止physical Controller compute／initialize仍通过 |
| GeoPhys Pendulum worker RGB／human | CPU uint8 RGB、自动展示、状态边界与二次reset；重复关闭及worker退出；未新增视觉外观开发 |
| 既有PickCube R3 worker | GeoPhys human、MuJoCo RGB；3步＋二次reset与相机边界通过，保留旧回调路线 |
| 显式PickCube physical R3 worker | MuJoCo／GeoPhys各两seed、3步、真实native ACK、九关节端口与二次reset；没有中途canonical物理世界启动 |
| MuJoCo physical reset＋模型 | joint→参数化r3-pose→joint，generation 1/2/3，旧动作与旧remote模型拒绝；child禁止physical Controller执行仍通过 |
| MuJoCo进程内／worker模型对照 | 三次reset的mass matrix、bias、状态obs、reward与实际admitted effort逐值一致；模型query前后公开状态相同，physics_steps=0 |
| MuJoCo模型＋reset＋RGB | 正式observer，reset首帧和3步后图像边界均对齐，uint8、非均匀帧，重复关闭 |
| 真实构建失败 | 原生port校验之后注入异常，既有session cleanup仅执行一次，worker退出；不是fake物理通过 |
| 真实写入ACK丢失 | 接到实际native write ACK后在父端注入EOF，fault阻止再次step，无自动重发；worker退出。没有把不确定写入写成完成推进 |
| 定向回归 | 最终309项通过；含协议、能力、旧控制、reset、渲染及G06设备语义。现有一个MuJoCo Solution测试实际reset／step，不能统称全为fake／纯测试 |

[持久证据索引](g06/worker-physical-evidence-index.json)保存每条命令、supervisor回执、结果与原始文件SHA；原始workspace保留在`workspace/maintenance/v211_worker_physical_followup_20261116/`，被Git忽略，不清理或覆盖。初始失败也保留：失配的builder／物理端口fixture和旧v1字段断言；故障脚本错误地把整数属性当作dict；以及模型范围扩展前的reset拒绝。早期“缺模型拒绝”的正向负例只证明扩展前状态，不作为最终MuJoCo模型能力证据。

所有原生运行串行复用既有共享锁和进程树监督：每次900秒、树RSS 10GiB、卡显存6144MiB、至少1GiB可用RAM／512MiB空闲VRAM、输出1GiB；没有资源限额违规、强制监督退休、改swap或杀外部进程。实际进程退出不等于任意SDK故障都已覆盖。

## 限制与代码规范复核

BodyWrench／physical sequence／任意扩展载荷的scalar IPC不在本次范围；source dynamics代理仅MuJoCo CPU既有mass/bias交集，不扩大GeoPhys或Isaac模型能力。没有运行中Controller热切换、全G06原生矩阵、完整抓取或Qualification声明。Scalar CPU值传输有RPC和复制成本；device CUDA训练链未改。

对照[代码优化账本](../planning/post-5c-code-project-optimization-diagnostic-ledger.md)、[G06分解](../planning/stage6-work-packages.md)及[诊断边界规范](../../../../global/diagnostics-and-code-boundaries.md)：无任务名、Robot名或Controller profile专属接线；新Controller复用已有能力无需改worker/provider构造。原有source-specific native模型实现仍由原能力owner负责，不以“通用”为名搬到公共worker。调度、物理推进、reset和teardown保持唯一owner；不加逐步全场景hash、诊断开关或核心对diagnostics的反向依赖。测试归现有diagnostics，临时运行／故障注入只在ignored workspace。

代码提交`e88fdaa7cf26d07411f92362bd2b55990b819fe3`，本记录与证据索引由后继文档提交配对；保护日志SHA保持`3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`，两个submodule无修改。未push、merge或tag。`git diff --check`通过；当前文档校验仅报既有`protected local input changed: MUJOCO_LOG.TXT`，无stale path引用。实际保护日志SHA与输入一致，不修改日志或基准以消除该已知差异。最终检查无残留runtime worker。
