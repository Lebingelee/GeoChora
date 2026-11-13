# U3 Isaac：构建、推进、action 响应与未成功边界的独立核查

日期：2026-11-13。审查输入 `1d58333ff6c9e8383086395d0ac8feedda8cba13`；维护者要求确认 Isaac Task 能否创建、env.step 能否有效推进、action 是否产生目标运动，再综合分析。本次是当前对话的只读专项核查，**不是 U1～U4 全量独立代码主审或维护者接收**。不创建子代理，不修改生产代码、旧 H5 或原报告，不启动 SDK/native，也不据此启动 U5～U7。

## 1. 结论

**受测 Isaac PickCube 路线已经能构建/reset、真实推进，并表现出有效的末端目标跟随；本次没有抓取／抬升成功。失败不能解释成“env.step 无效”或“action 没传到机器人”，也尚不能直接归因于 solver。**

| 问题 | 独立判断 | 本次依据与边界 |
| --- | --- | --- |
| Task／Env 能否创建并 reset | 该受测交集成立 | 正式 `make_env` caller、同次 reset 初始边界、请求/source/materialization 身份及后续1000个非零interval形成一致记录；不是本轮新启动SDK |
| env.step 是否有效推进 | 成立 | 1000 transitions／1001 boundaries；逐条核5000个连续 native advance 收据；evaluation time 0→10 s，原生步长0.002 s、每次外部step五个子步；启动/reset隐式推进仍unknown |
| action 是否产生末端运动 | 受测轨迹成立 | action为world absolute pose；观测为`panda-v1/ee`的provider实测位姿；关节与EE实测随命令变化，位置跟随误差见第3节；不是仅凭目标ACK认定运动 |
| 夹爪是否响应 | 有响应，未达到当前close-ready | 开口80→53.63 mm；最终请求0 mm、servo目标51.63 mm，未达到45 mm的现有任务门槛 |
| Task／Solution是否成功 | 未成功 | cube最终lift约0.222 mm，原门槛100 mm；1000步horizon截断；同次caller报告done=false、failed=true。H5没有独立持久化Solution完成事实 |
| 是否足够关闭整个U4 | 否 | 本报告只核Isaac实际响应和completion记录边界，未审完U1/U2代码及全部60项；整体接收不由本专项结论代替 |

## 2. 输入与只读方法

原始运行：[pick-isaac-r3/episode.h5](../../../../../../workspace/maintenance/v211_e11_e16_u3_20261113_001/pick-isaac-r3/episode.h5)，20,555,513 bytes，SHA-256 `3f163081760f6ad8a49abb593c6a1266dc47f20bd72751bf49e5bd1e30951d48`。实际为 PickCube正式UID、Isaac Sim 6.2／PhysX CUDA／cuda:0、R3 continuous、seed31、horizon1000、state-only。独立核查不覆盖Nut Isaac或任意目标／资产／Controller交集。

重新从原H5读取action、1001个EE/关节/物体观测、typed state witness、1000条structured control、全部native advance和Outcome；关联原stdout与supervisor。**未将此前reader的PASS当成本次运动分析的输入结论。** 输入文件以`h5py.File(..., 'r')`只读，未调用Core reader构造环境。plain Python缺h5py后切换到原监督计划指定的既有Conda解释器，没有安装依赖。最初探查发现env_meta为YAML，最终读取按其格式执行，未改原件。

动作/观测、计数、source boundary、target hash和native收据关联检查均通过。typed测量与float32观测投影的最大pose分量差约`2.98e-8`；该差是数据投影核对，不是跟随误差。原native plan冻结的两份caller源码、两份Task YAML和Solution源码，共五份SHA与当前源码全部一致；不据此声称所有provider源码都在本轮重新验证。

原运行输入是`1ff617d0`加当时保存的修复，不是最终干净HEAD实测。原supervisor退出码0，未触发资源中止；runtime_valid只表示该次执行/记录/关闭等检查结果，**不表示task_success**。原App shutdown日志限制与启动隐式步unknown保留。

原始核查程序和机器可读结果：

- [只读程序](../../../../../../workspace/maintenance/v211_isaac_u3_motion_review_20261113_001/read_motion.py)、[完整数值结果](../../../../../../workspace/maintenance/v211_isaac_u3_motion_review_20261113_001/isaac-motion-readback.json)、[作用范围收据](../../../../../../workspace/maintenance/v211_isaac_u3_motion_review_20261113_001/offline-scope.json)。
- [四CPU completion字段盘点](../../../../../../workspace/maintenance/v211_isaac_u3_motion_review_20261113_001/cpu-completion-field-inspection.json)、[输入/保护快照](../../../../../../workspace/maintenance/v211_isaac_u3_motion_review_20261113_001/input-snapshot.json)。

程序拒绝SDK导入及安装资产/SDK文件访问；最终无SDK导入、无native、无资产构造。它是独立离线测量脚本，不是一个新增产品检查框架。

## 3. 实际 action→物理→状态链

源码核对路径为：`examples/tasks/pick_cube.py`正式make_env/reset → caller-owned Solution `act → env.step → observe` → `SelectedReferenceEnv`共同提交 → `PandaPositionServoProfileV1.compute`／既有R3算法 → native position write → `NativeRuntimeSession` interval → Isaac public Tensor API读取DOF及frame → typed状态与Task观测。

`runtime/sessions/native_io.py::apply_control`的write ACK本身明确不声称运动；`isaac_native_io.py::_read_views/read_state`用公开`get_dof_positions/get_dof_velocities`及frame view读回，read_state还核对读前/读后计数未推进。本次观察来自这些实测字段及随时间变化的关节，而非把command ACK或目标值复制成状态。

误差定义：第i个输入action的world XYZ，与该次step返回的第i+1观测边界EE XYZ作欧氏距离。position action是伺服目标，不要求每0.01 s瞬时抵达。本次只报告观测量，不新增验收容差。

| 样本集合 | 数量 | 位置误差中位数 | RMS | P95 | 最大 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 全部输入，包括保持目标 | 1000 | 0.933 mm | 1.739 mm | 3.396 mm | 7.018 mm |
| XYZ命令变化大于1e-7 m的样本 | 503 | 1.379 mm | 2.232 mm | 5.642 mm | 7.018 mm |

运动样本单列用于避免大量静止保持拉低误差。该分组阈值只是统计选择，不是跟随PASS门槛。全部样本的四元数角误差中位数约0.018°、P95约0.133°、最大约0.592°。

末端初始`(0.546506,-0.093816,0.566101)m`，最终`(0.635098,-0.086457,0.530613)m`，累计位移路径约220.04 mm；目标先抬高、横移、下降，再保持关闭。7个Arm关节均有变化，最大单关节偏离初始约0.699 rad。最终EE接近保持的末端目标，但最后一次Arm各关节servo target与实测仍有最大约0.00925 rad误差，不能把EE接近目标泛化为所有关节精确到位。

| step后的仿真时刻 | action目标XYZ（m） | 实测EE XYZ（m） | 位置误差 |
| --- | --- | --- | ---: |
| 1.01 s | (0.546506,-0.093816,0.603000) | (0.546229,-0.093770,0.606450) | 3.462 mm |
| 3.01 s | (0.626887,-0.087148,0.603000) | (0.627680,-0.086925,0.601990) | 1.303 mm |
| 6.01 s | (0.635134,-0.086464,0.532000) | (0.635093,-0.086458,0.529901) | 2.100 mm |
| 10.00 s，目标保持末期 | (0.635098,-0.086457,0.530613) | (0.635098,-0.086457,0.530613) | 约0.00012 mm，受float32投影精度限制 |

![同次Isaac action与实测响应](../../../../../../workspace/maintenance/v211_isaac_u3_motion_review_20261113_001/isaac-action-response.png)

图由原始H5直接绘制，虚线是用户action的目标，实线是实测。最后一行的requested opening不是native最终servo target；二者经Controller限幅转换，不能混为一条曲线。

## 4. 失败已经定位到什么程度

零基action索引610开始关闭，643起357个action持续请求完全关闭。实测总开口从约80 mm降至约53.632 mm；完全关闭请求期间最小仍约53.632 mm，始终大于45 mm。

最后一次输入gripper=-1，经规范化requested opening=0；既有`position_gripper_servo_opening`按当前实测开口和命令修正上限计算servo opening≈51.633 mm，再由native mimic leader drive消费。它没有把0 mm请求原封不动作为native位置目标；该转换有正式算法owner，不可因没瞬时闭合就判丢动作。原生drive上限5 N是受测路线约束；CPU记录的Controller force_limit为10 N，不能把路线不同写成完全相同控制配置，也不能仅凭该差就判定力不足。

`tasks/pick_cube/task.py::_gripper_execution_info`要求目标和实测开口都≤45 mm，且两指绝对速度和≤0.005 m/s；最终目标开口0、实测53.632 mm，速度和约0.002025 m/s，**开口条件明确未满足**。Task的grasped_cube从未为true。后半段action持续保持相同EE pose并关闭，没有出现后续抬升形态；这与close-ready未满足相符。

H5没有完整持久化Expert stage/内部completion events，不能把上述推断写成已独立复现其内部stage。原caller最终是horizon截断、Solution done=false/failed=true，不是已证实的`gripper_readiness_timeout`异常。cube最终lift约0.222 mm、task_success=false与记录及原谓词一致。

**尚未判定根因：**当前H5不足以区分接触几何/指尖相对cube高度、native drive/effort设置、Controller步进语义与Task readiness适配。不能仅用“PhysX不同”或“策略失败”结案，也不能直接修改45 mm门槛、提高force或把cube lift阈值降低来追PASS。

若后续需要区分根因，最小检查应聚焦同一正式交集：空载关闭与接触关闭的对照；公开指尖/物体几何、开口/速度、native目标/drive上限及实际可用力读回；原Task/Controller/source身份保全。目标是先判定夹爪/资产/判据的责任，不是重跑整个矩阵。本次没有执行这些native对照，也没有要求非MuJoCo必须调参到任务成功。

## 5. Completion记录与U4停门

Isaac H5的`meta/episode_outcome_v1_json`中**字段`solution_completed`存在，值为null**；准确说法是未保存完成事实，而不是整个Outcome或字段不存在。原同次stdout明确保存done=false、failed=true、truncated=true；文件身份可以关联，但这不等于H5中独立核验了Solution lifecycle。

当前`SelectedReferenceEnv::_make_position_episode_end`仅在physical reset selection及external Solution owner都存在时填写完成状态；该普通Position caller由外部持有Solution，没有该交接，于是值为None。由源码可以解释记录缺口，不是物理step失败。补齐时应让caller在结束边界把有身份的最终facts交给现有Recorder/Outcome owner，保留Solution外部所有权，不为记录重新把Solution放回Env。

本次还直接读取了四份CPU原H5的canonical logical JSON：四份均无显式solution_done/failed/completed、expert_complete或planned/outcome complete字段；stop_reason为pass，最后task_success=true，PickCube最后stage为lift、Nut为release_retreat。它们提供任务/阶段证据，但不能据此直接替代Nut严格完整Outcome的独立复算。原关联器的NOT_CHECKED不是“字段存在但尚未验证”的证明。具体结果见第2节CPU盘点；本次未重执行Solution策略或全部guard。

对停门的建议：

1. 将Isaac拆成“构建/reset/推进：成立”“受测末端跟随：成立”“抓取/抬升：失败”“completion持久化：缺口”，不因task失败撤销已证明的基础能力，也不以runtime_valid抹除失败。
2. 总账允许非MuJoCo单seed任务失败有界报告；但本次夹爪责任尚未确定，不能由审查者直接签成solver限制。是否保留该失败作为明确能力边界，需要维护者对具体范围作决定；适配/控制缺陷若确认仍应修复。
3. T19单独明确接收口径：历史原件保持不变，可审查“同次原caller facts＋H5身份关联”的受限证据是否满足本轮要求；若不满足，落实标准的结束facts持久化/独立读回方案，按实际影响补证。不能将null改为false/true后重写旧文件，或仅修关联器就声称已产生缺失数据。
4. U4全量代码/五运行主审与维护者代码接收仍需完成。**本报告不自动解除原Goal的blocked状态，不改变U4→U5→U6→U7顺序，也不把一次专项核查写成整轮优化已接收。**

## 6. 本轮保全与验证

本轮仅新增本专项审查文档，原始数值/程序/图保存在ignored workspace；四保护输入、两个submodule pins与本轮输入快照一致，五份原H5哈希与前述U3身份一致。无生产代码修改、无pytest/SDK/native/训练、无清理或消息其他会话。

文档检查按当前基线比较：已知保护MUJOCO日志错误和79条历史链接限制保留；不修改保护原件或历史结论来使检查全绿。图和数值均是旧记录离线再分析，不称新的物理测量或新的Qualification。
