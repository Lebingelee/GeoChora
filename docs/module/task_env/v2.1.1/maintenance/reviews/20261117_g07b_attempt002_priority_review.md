# G07／7b attempt002：主线优先的裁决与补证

2026-11-17，审阅输入 `81d1138d54f9397fe1bd3569871fdf8beb05dcb8`，分支`codex/v211-stage7-integration`。
维护者要求优先处理直接影响当前主线的部分；仿真器本身的数值问题可留专门后续，退役入口不强制恢复/迁移。本轮由主agent实际核对和补证，未委派subagent，未新开attempt003、未重开已释放的attempt002实施窗口。

**结论：当前合同测试和无producer录制补证已完成；不再将MuJoCo原生数值研究或退休注入入口迁移列为本轮必修。7b整体仍等待完整独立主审，原PARTIAL返包与失败记录保留，不据此宣布维护者接收。**

## 1. 三项失败分别处理，不追求旧套件全绿

| 项目 | 当前主线关系与证据 | 本轮裁决 |
| --- | --- | --- |
| 默认Robot配置往返 | 原fixture有两个Robot却无默认UID，且缺当前Task configuration接口、仍期待robot_uid=None及旧异常文字。正式PickCube/Nut已有明确default_robot_source_uid。 | 修正为使用真实`PickCubeReferenceEnv`声明，保留原/装配Robot显式选择、resolved往返、未知UID与多余字段拒绝；不修改生产解析器或随意选择默认Robot。定向通过。 |
| 旧robot_source_adapter故障注入 | 测试在已不存在的`specialization.build_reference`设置monkeypatch时失败，没有进入清理；当前正式source stage在`SourceBoundTaskBuilder`内管理新source lease。 | 旧测试/原失败原样保留，不恢复接口、不为绿灯加skip或删断言。检查现有`test_source_composition_failure_releases_source_before_controller`：R3/direct两条正式source绑定在composition失败后都清理snapshot，原异常保留。本轮两实例通过。 |
| 旧identity projection故障注入 | 同样未到核心行为；旧Task独自投影方式已由共同source/控制构建替代。 | 不迁回旧注入点。复用现有运行时source/physics事实覆盖拒绝与Controller构造失败清理检查；本轮4实例通过。当前builder异常分支包围composer、Controller及compile_control并关闭新source，未发现需要新增生产清理逻辑的本轮证据。 |

定向命令仅选择上述当前合同和现有清理节点，**7 passed**，见ignored目录`workspace/maintenance/v211_g07b_attempt002_sol_review_20261117/current-contract-and-cleanup-001/`。
这些节点来自现有`test_tabletop_robot_source.py`，未新增另一套cleanup测试或仿真封装。定向结果不与原115/3相加，也不声称旧失败已变为PASS。

原`affected-regression-001` **115 passed、3 failed**及更宽旧套件15/28、split4/1均保留其原输入/范围；未重跑这些整套suite。与当前仍支持路径没有对应的旧candidate/注入入口，不作为本轮恢复功能的理由。

## 2. MJWarp无载荷：只补真正缺少的Recorder链

原`mjwarp-no-load-002`脚本没有构造`VectorTransitionRecorder`，因此只能证明普通action/reset/close，不能证明最后一版无producer录制/reader兼容。
本轮在同一生产代码上，走正式`make_parallel_env`＋`VectorTransitionRecorder`，不声明scene producer/body binding：

- B1、PickCube、MJWarp4.0.1、`panda-direct-effort-v1`、native_drive disabled，正常seed31，无相机、无Task成功要求。
- 两次显式reset，各一次非零joint effort step，分别5个子步；episode_id为1和2，native_step为0→5、5→10。普通任务初态不换成载荷诊断初态。
- reset归档首个episode，close归档第二个；两份H5均由**独立进程**读回，分别T=1/T+1=2，时钟/episode关联正确，未出现虚假的scene载荷声明/收据。
- close正常返回，监督器无违规/强制退役，运行结束后共享锁可非阻塞取得。

文件及原始SHA256：

| 文件（review目录下`mjwarp-no-producer-record-001/`） | SHA256 |
| --- | --- |
| `trajectory_slot_000_episode_000000.h5` | `74ae0c49f67b33c79fedb7e21098eba4d110d74ab3ece4bc2de844548ddd875c` |
| `trajectory_slot_000_episode_000001.h5` | `a26dd046729ddb1b2f1451df2675cc2ee81cd042c1e21a8422c39e3a76697f48` |

范围限无producer B1的正常action/reset/record/read/close；不外推新任务成功、任意B或完整训练。原带载荷same-step/残留检查继续按其原输入使用，不重复运行。

## 3. MuJoCo数值问题：保留拒绝边界，交专门后续

问题标识 **G07B-MJC-FREE-ARMATURE**。本机MuJoCo3.8.1、FREE body、非零角向armature、implicitfast条件下，原生独立MjData已经复现数值差异；这与公共场景提交层的错误不能混为一谈。
原`mujoco-integrator-diagnose-001`在相同无阻尼/保留armature夹具上，`mj_forward`角加速度0.996512，而implicitfast `mj_step`为285.714286；Euler/implicit对照没有该差异。原有阻尼source的直接native对照也记录了implicitfast失稳/QACC warning。
这支持将该精确原生交集列为后续问题，**并未确认上游根因或任意MuJoCo版本的一般缺陷**。本轮不研究修复引擎、不升级SDK、不换生产source/积分器，不把对照积分器写成已准入替代路线。

当前port保留写入前guard；适用的FREE角向armature力矩/非body-origin矩参考明确拒绝，原失败不改成PASS。没有该载荷的原九格也不因该拒绝被机械重跑。

### 独立自由体夹具的使用裁决

原工作包第6节允许另行声明无阻尼夹具，要求独立source/初态且不改旧矩阵输入。`mujoco-zero-freeze.json`在run前冻结了质量、惯量、零阻尼/零armature、载荷、时长、oracle/容差与source closure；没有证据要求该夹具必须是此前内置Task。
因此`mujoco-zero-response-002`可以作为**这一另行声明夹具上的公共BodyWrench响应证据**，不需要为“夹具新建”再启动功能开发。

- 独立source closure：`3febbe438df9129f7c837d405fb1474a0ce496d44355a21565e6d1ff58d0f84c`。
- ±1N作用10ms的速度差为±0.125m/s；±0.01N·m的角速度差为±2.857142857rad/s；后续无载荷interval维持该差值，符合事前冻结的独立质量/惯量oracle。
- 五份H5的原独立reader回执与现存文件SHA一致；原source/失稳/失败及历史九格未被覆盖。手部移动参考系/偏置点/hold-reapply/clear继续按`mujoco-hand-hold-003`的实际证据单独成立。

这不是原生产FREE力矩组合已经修复的证据，也不将B2-2历史PARTIAL改成原source全通过。后续专门处理该数值问题时，从原诊断/完整source与profile恢复，再确定根因和修复；当前G07不强制开展。

## 4. 状态、资源与仍需完成的审阅

本轮只改变一个测试函数及审阅/状态文档；生产代码仍为81d1138d。未push/merge/tag，未修改pins/SDK/原始失败/保护日志，未写7c独立工作树。
3条受监督命令（7项测试、一次device补证、独立reader）保守共计**12.071495502秒**，其中仅device补证新增**10个显式子步**；native累计余额约**1213.377548秒**。冻结为`review-freeze.json`，实际为`review-results.json`，均在上述独立review目录。没有重置旧资源消耗；Isaac隐式启动/reset子步仍未知。

7b ordinary attempt_count维持2；本轮是有界主审小修与补证，不是attempt003或继续原实施窗口。原attempt002输入/输出/返包状态保持可恢复。
当前可进入最终独立主审，核对共同准入/各provider正向/记录生命周期及旧矩阵复用的完整证据；**不再把旧退休入口、要求全suite全绿或修复MuJoCo原生数值问题作为自动新增开发门**。本页不是整个7b已接收的声明。

后续状态：本页记录定向审阅时点；其后的完整独立裁决及维护者授权有界接收见[7b最终主审](20261117_g07b_final_acceptance.md)，原始PARTIAL／失败及本页补证事实保留。
