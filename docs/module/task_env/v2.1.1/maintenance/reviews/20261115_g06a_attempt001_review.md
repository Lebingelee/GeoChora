# G06a attempt001 独立复核与 attempt002 输入

日期：2026-11-15。复核输入 `3a277e03d010e8bb3dbeb2eff26a69232be97572`，分支 `codex/v211-stage6-parallel`。tracked clean，既存 `MUJOCO_LOG.TXT` 保留。结论：**保留已有 MJWarp Pendulum native 有界证据，整体 PARTIAL；6a 不接收，需要继续实现。不是文档收尾。**

依据：[首包](../work-packages/20261115_g06a_attempt001_goal.md)、[实施方案](../../planning/stage6-parallel-execution-plan.md)、ignored `workspace/maintenance/v211_g06a_attempt001/report.md`、同次readback／gates以及实际diff。按项目、TaskEnv、架构、公共API、文档治理和 evidence-driven-delivery 方法复核；不重新开启已接收G05。

## 1. 已经成立的部分

- 主环境普通 `make_parallel_env(execution='device')` 进入共同selected配置、source-bound构建、canonical Controller和MJWarp隔离worker；不是复制Pendulum Env。
- pinned MuJoCo/MJWarp 4.0.1、Warp1.18的实际隔离环境与CUDA driver IPC有同次运行记录；主环境未被升级。worker内一次control interval循环native substeps，不是每个世界scalar Env。
- MJWarp Pendulum B=3非零控制、q/qvel设备发布、任务观测、错开reset、owned snapshot和close有真实证据。独立reader记录首interval q误差约4.39e-7 rad、qd约7.43e-8 rad/s；这些只支持指定任务／source／参数。
- 本次重新执行报告的定向集合，结果 **65 passed、1项既存依赖warning（7.78s）**。这确认现有测试仍通过，不证明尚未测试的新合同正确。
- 本次没有重新运行native／GPU／窗口；native结论是对001同次证据的复核，未宣称新HEAD原生复测。

## 2. 已确认的实现差异与缺口

| ID／优先级 | 实际位置／事实 | 需要的处理及阶段 |
| --- | --- | --- |
| A02-01／P1 | `vectorization/homogeneous.py:_copy_selected_device_tree/_finish_device_autoreset` 将终止叶压缩为`[N_done,...]`，只在done时出现；方案7.2约定固定B轴与有效mask。已有测试断言压缩格式 | 6a修正为固定B轴`final_observation`＋`_final_observation[B]`，未结束行不消费；统一final／reset身份。若保留`final_mask`仅为兼容别名，不形成另一语义。旧实现不是已经批准的新接口 |
| A02-02／P1 | 同方法重新创建infos，未消费`transition.infos`；Task reward_terms／metrics会丢失。公共info缺少完整transition boundary／env ID／generation与final/reset分区 | 6a保留任务info、旧transition identity和reset identity，避免覆盖；Recorder据此记录，不靠再次查询已reset状态补旧信息 |
| A02-03／P1 | `task_definition.py:reset_sampled_device` 只围绕native reset捕获fault；其后的episode提交和observation builder失败未锁存fault。seed状态在sampler／native参数拒绝前可能已写入 | 6a明确无副作用预检与提交边界；预检失败不推进RNG／episode，native已变更后obs／camera失败必须fault，不能继续step或宣称原子回滚 |
| A02-04／P1 | 同方法在公共生命周期内固定抽两次uniform并构造`qpos/qvel`模板；`factory.py`硬接MJWarp；`transport/worker.py:main`硬导入MJWarp类；运行模式依赖重复metadata字符串 | 6a把所需随机域／形状交任务声明、RNG流所有权留生命周期；runtime creation／worker bootstrap按已解析provider能力薄分派。第二来源不能复制worker／factory或把PickCube随机化塞进公共reset |
| A02-05／P1 | 正式`MuJoCoWarpBatchSession`只发布qpos/qvel。`g06/runner.py:_render_worker`另建MJWarp模型，直接导出native xpos/xquat；`raster-005`只取world0 | 6a扩展正式session的具名body/frame CUDA publication，接共同render adapter；证明B行和网格。现有证据是native render接口探索，不是正式batch Env已支持render |
| A02-06／P1 | GeoPhys `RasterSceneVisualizer.read_task_camera_frame`经`FrameBuffer.read_color`走NumPy，单task camera、共享framebuffer尺寸；尚无公开CUDA rgb8成帧端口和device mount更新合同 | 6a最小公开设备输出／完成边界／相机更新扩展，Core接入；终止帧保留必须跨下一次capture。不能把host float→CUDA uint8当驻GPU |
| A02-07／P1 | `recorders/vector.py:VectorTransitionRecorder`仍消费SB3四元组、list infos；不是新device五元组／列式info | 6a扩展既有Recorder owner，明确启用记录才做选定行／字段的owned导出，独立H5读回普通步／终止／新episode。禁止另造Recorder体系 |
| A02-08／P1 | Isaac第二设备pose来源、PickCube真实base/hand图像、窗口未验证；67mesh存在和mount-intent不能证明实际成像 | 6a完成代表性第二来源R0、真实资产多相机挂载及窗口开关技术门；不要求本包完成三后端PickCube控制或性能矩阵 |

A02-01／02已经通过额外CPU合同复现：B=3仅中间行done时final shape为`[1,1]`而非`[3,1]`，传入的metrics不出现在返回info。结果位于 ignored `workspace/maintenance/v211_g06a_attempt001_review/contract-reproduction.json`；这是合同复现，不是native资格。

A02-03由实际异常边界确认；需在002加失败注入检查，无须为其启动新引擎。A02-04是明确的复用缺口，不因为只有一条provider已通过就称为当前Pendulum物理错误。A02-06应优先复用既有Taichi公开field导入，不能仅因需要completion合同就再造完整foreign-buffer管理层；确缺公开输出时在GeoPhys原owner补接口。

附带核对：device `action_space/observation_space`仍沿用single别名，未完整公开批量规格；6a应以已有schema owner给出B轴规格并保留旧host兼容。当前MJWarp拒绝外部资产文件、非单位传动和非source序scalar坐标，是已声明的限制；完整PickCube source／free cube／paired-finger控制扩展留6b，不把这几项都塞入002。

## 3. 代码质量与证据处置

现有生产净增约1163行、诊断约1238行不是拒收理由；真正需要修复的是公共reset的任务形状假设、provider硬接线和终止合同偏差。895行runner混合监督、native worker、case及读回准备，002若继续扩展，按已有职责拆出实际case实现并保留一个入口，不按attempt复制另一runner；不为行数目标新增空层。

对transport清理还需补有界失败测试：部分IPC import成功后失败、worker启动失败／中途退出、一个资源释放失败时继续处理其余资源。当前close部分路径先置closed，失败后无法重试；不要据此声称所有异常资源已释放。是否需要改重试策略以实际测试为依据，不能用重复close不抛异常冒充清理成功。

原准备prompt SHA是`b1bf179a997c8b75e873d4aa7a2e2b0176ab6422e44ceee5533126066b5c8f54`，001报告实际goal SHA为`d6b8cf895475138fe8d021d3fc90e8221daf65481270d3ce28f3f3ce720f8431`。现有交付未附可定位的实际goal正文，暂不能确认是UI封装还是范围修改；不据此判定实现违规，也不覆盖历史hash。002开头记录可获得的实际派发正文与SHA，若001正文可恢复则补对照，否则标UNKNOWN；此元数据问题不替代代码修复。

## 4. 阶段分界及后续

002必须完成：终止／info合同、reset故障原子边界、可复用reset请求和provider接线、正式public pose→Rasterizer CUDA uint8、代表第二来源、多相机挂载技术门、device Recorder及定向检查。需要GeoPhys有限公开接口扩展，已非仅Core文档修改。

6b保留：三后端×两任务完整canonical闭环、GeoPhys rigid接触／控制device能力、MJWarp复杂source／传动能力、完整PickCube Task tensor计算、16→256→4096条件性能矩阵。6c保留：三后端严格mask隔离和真实固定renderer A→B→A集成；R3仍独立接收。

[attempt002 goal prompt](../work-packages/20261115_g06a_attempt002_goal.md)是待维护者派发的下一窗口，不自动启动。主审当前只做证据核对、pure复现、文档收口；没有顺手修改这些相互关联的生产合同，避免未经统一修复形成第二套终止／记录格式。
