# 阶段3前维护续作检查点：Marker构造

日期：2026-11-05。输入 `develop@fdea7fbb`，根据维护者目标继续阶段3前维护；本检查点待Sol审阅，整体维护仍为 PARTIAL，阶段3未开始。此前两个保护 untracked 不属于改动范围。

既有 `ReferenceTaskDeclarationV1.compile` 的可选Controller编译通过 `compile_panda_box_task` 暴露；构造身份与来源字节快照交由assembly compiler准备。示例仍保留任务声明、reset、评价和正常注册，使用公共 `make_env`；构造摘要按本次真实源码计算，不复用历史SHA。`CompiledReferenceTaskV1` 记录场景构建owner，以保留 `PickCubeSceneComposer` 来源。源文件名冲突和缺失Controller拒绝构造。

Marker仍须在示例中配置并创建 `ReferenceTaskBinding` 和resolved配置；本检查点只收回部分通用接线，并不宣布R2完成。F06任务值与runtime准入职责分离、环境类减责、必要真实物理回归及独立reader尚待实施或验证。

无引擎guard与禁用外部pytest插件条件下，选定的配置／消费者／维护边界三组 **118 passed**；覆盖Marker公共factory、合成reset/step、实际来源文件SHA及recipe摘要。首次测试启动缺少 `PYTHONPATH` 导致收集失败；第二次因pytest basetemp父目录不存在导致38个setup error（80通过）；修复环境与目录后全组重跑通过。合成测试不证明物理成功。未启动Isaac、GPU或其他真实物理引擎，未申请共享native锁。

## F06任务声明与runtime准入（续作，待复审）

F06的固定body/frame/joint映射、controller profile与horizon范围由PickCube specialization给出；通用USD RuntimeInput携带该声明，runtime以固定的 canonical JSON SHA-256 `153dc47bf2993efa78e1efe835eced90c82c80284aef8ec532495b2fa2ea4fcb` 准入声明，再逐项核对RuntimeSource映射及输入限值。固定delivery manifest、representation、provider、seed、renderer和Task/Scene/Execution身份仍由runtime独立检查；未经允许的USD schema不再因仅属于同一类型就被归为F06。改变任务声明时不能只更新输入，须独立审阅受信摘要及其delivery对应关系。

无引擎guard下F06、配置、消费者及维护边界组合 **130 passed、1 deselected**；包括任务生成映射的固定摘要、篡改实际映射、同时篡改映射及policy、改horizon上限和错误schema的拒绝。此前尝试完整投影时 `scene` 导入被guard拒绝（11通过、1失败），保留为未覆盖项；组合命令显式排除该项。该测试不能证明真实USD解析、Isaac运行或物理能力；本轮未启动Isaac或GPU。须经Sol独立复审，不能仅凭移动位置认定R3已接受。

## Marker与Nut的规范组装入口（续作，待复审）

规范 `SelectedReferenceEnv.from_resolved_config` 负责共同的配置类型／UID、state-only检查及Env组装，Marker和Nut分别通过 `selected_binding(config)` 提供自己的任务接线；PickCube特殊Isaac构造保留其既有实现。示例不再重复 resolved-config 创建Env；task-specific binding仍在示例，尚需复核是否达到本维护所要求的新手最短组合。未增加Panda专用Env模板或任务factory。

无引擎guard下配置、消费者、边界测试 **118 passed**；新增的Marker入口与非法UID／render／额外参数检查 **2 passed**。仍为synthetic，待独立复审；未运行真实引擎。

## 控制器切换记录投影（续作，待复审）

Position终止时待确认切换的记录投影归入既有 `recorders.position_metadata`：区分未尝试、未确认和target/applied ack已见但transition未记录，Env继续拥有生命周期状态及最终提交时序。无引擎synthetic组 **13 passed**，含原leaf/mixed故障与新投影正负例；未将ack提升为已提交transition，也验证未确认分支不读取运行时边界。

尝试运行三个现有Position切换集成测试时，均在 `scene` import被禁止引擎guard拦截（3 failed，未执行到断言）；真实场景集成及物理仍为NOT_RUN，不以synthetic结果替代。完整命令与当前检查输出在ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/receipt-check.json`及相邻日志。

## PickCube位置执行反馈归位（续作，待复审）

PickCube特有的夹爪执行信息、输出字段及适用条件由任务specialization通过已有 `ReferenceTaskBinding` 声明；规范Env只调用可选投影并发布其结果，不再直接导入PickCube实现或根据任务名称决定该反馈。非F06 route不产生该字段，既有错误与量值验证保留。无引擎配置／消费者／F06组合 **131 passed、1 deselected**；反馈增加后针对测量值及发布的2项检查通过，leaf/mixed synthetic组 **13 passed**。真实F06 USD和Isaac未运行，本结果待Sol复审。

## 版本化reset输入归属（续作，待复审）

PickCube通过已有task binding选择其版本化runtime输入；通用Env使用该输入校验重建Artifact的对象身份及执行路线／seed，不再在这两处识别F06字段名。无版本化输入的现有行为保持原样。无引擎组合 **124 passed、1 deselected**，含相等但非同一Artifact的拒绝及F06重建Artifact到materialization的合成检查；真实USD/Isaac仍未运行。前一源码HEAD的生命周期合成回归 **172 passed、3 deselected**，本次修改后仍需对最终源码复核。

## Position夹爪绑定归属（续作，待复审）

由PickCube task binding选择版本化source对应的gripper semantic；通用Env将该语义交给既有ControlBinding，不再按F06字段名选择任务特定值。无引擎检查 **13 passed、1 deselected**，包括绑定实际到materialize的合成测试，leaf/mixed合成检查 **12 passed**。真实USD场景和Isaac仍未运行。

## Nut cadence诊断接线隔离与R05b准入缺口（续作，待复审）

Nut cadence的100／500 Hz检查和专用构建移到既有 `diagnostics/tasks/c05c_geophys_gripper_cadence.py` 的显式binding构造；诊断调用者使用同一个Nut Env。通用Env不再包含cadence参数、速率列表或Nut诊断分支，只传递显式diagnostic profile到现有runtime准入；普通native feedback保留原独立路径。旧 `for_gripper_cadence_diagnostic` 内部诊断入口已删除，仓库调用者同步迁移；不新增task专用环境factory。无引擎诊断／消费者／边界组 **115 passed**，覆盖不支持速率／provider拒绝、100 Hz五样本和普通selected路径。

较宽R05b检查 **101 passed、8 failed**：其中5项被无引擎guard拦截GeoPhys来源查找；另外3项在原严格Controller/Solution身份准入处被拒绝。恢复源码至本轮输入 `59b082d1` 后单独重跑这3项，仍全部以相同准入错误失败，说明问题先于本轮诊断隔离；日志 `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/r05b-baseline.log`。检查发现当前Controller和Solution身份绑定真实源码SHA，原R05b allowlist仍固定旧身份；试验性更新身份后这3项前进到GeoPhys来源检查并被guard阻止，不能由此认定物理或完整准入成功，试验修改已撤销。现有固定身份及所有其他严格检查保持不变；需在最终源码稳定后核对源码来源、冻结语义和负例，再明确更新或保留此有限准入的决定，不可伪造旧SHA或仅为绿灯放宽。

## R05b当前源码身份与严格准入（续作，待复审）

`80179561` 曾将R05b controller／Solution准入固定为当时的源码绑定身份；其后调用方驱动Solution、feedback完整性以及任务／生命周期归属迁移改变了源码与身份。当前Nut specialization SHA-256为 `f5f1ff2abc7d49a71df1327e02dc22122a313da3e292b3c379105a977efb727e`，Solution及guard所在文件SHA-256为 `abe5c361554d96455d505fe9b244326e96d72f44faeae054fa52a14c3a320386`。本次将受限R05b allowlist更新为这份源码真实构造的100／500 Hz Controller与Solution身份；不保留旧身份作为当前源码别名，不更改Artifact、物理参数、provider pin、source manifest或逐字段准入。后续修改这些身份来源须重新审查并刷新，不能把旧run重标。

无引擎guard只允许 `PathFinder` 对本工作树 GeoPhys及其同级源码进行真实路径spec查询；仍拦截这些模块的实际import，版本、Git修订、dirty状态和origin由现有provider provenance真实读取。R05b **14 passed、1 deselected**：覆盖CPU/CUDA两个来源准入、100／500 Hz假provider五样本、来源／映射／dirty／controller／Solution篡改拒绝以及同次synthetic H5独立reader；普通真实provider reset/step项排除。完整argv与输出见ignored `r05b-origin-final.json`及相邻文件。此结果不证明GeoPhys物理或GPU执行；需要Sol审核本次新源码身份及必要真实回归。

## 当前源码 classic CPU短检查（续作，待复审）

对 `develop@fa885280`，通过公共 `examples/start.py`／`make_env` 在GeoPhys CPU各运行一次 seed73 reset、1个零动作transition与close：Empty、Pendulum、TwoWheel均退出码0，观察符合各自space，动作shape分别0／1／2、dtype float32；Pendulum／TwoWheel观测shape分别3／7，reward分别0.9779344970878069／0.9996657105631644，均未终止或截断。每个worker在独立输出cwd运行，分别耗时5.780／18.323／19.949秒、进程组退出且有序释放两把共享锁；具体argv、资源采样、日志及锁收据见ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/native/{empty,pendulum,two-wheel-balance}/`。启动参数显式指向本工作树Core及GeoPhys src；本次未另作运行时模块origin打印，因此只记录已传递的路径。两个保护文件SHA与原快照一致，GeoPhys及Menagerie gitlink未变。

这是受限单步CPU检查，不证明任务成功、多环境、render或其他provider；PickCube／Nut物理及独立物理reader仍未运行。原attempt001累计预留约105107／120000步，本轮三个任务各1个control interval，按其配置的substeps计入后续统一总账；不得将旧run或本次结果重标到后续改动的源码。

## PickCube调用方驱动Solution（续作，待复审）

PickCube scalar CPU支持将Solution的 `ExpertAction` 直接交给 `env.step(action)`；保留action stage／readiness及target/applied ack记录。Solution的reset／observe可从公开info解析执行反馈并继续拒绝缺失／过期边界，旧显式参数兼容。Nut仍强制控制请求与source boundary；PickCube拒绝其未支持的请求字段。普通任务、录制和规划入口已迁移到调用方 `act → step → observe`。Position/F06在推进前拒绝该新动作入口，高级Harness仍使用受限兼容路径，不推断其已迁移。

无引擎离线组合 **188 passed、4 deselected**，涵盖原生命周期回归、PickCube动作／readiness和F06静态检查；此后新增不支持Position和多余请求的负例单独 **2 passed**。此前首次测试发现Nut binding约束被意外移除，已恢复并重跑通过；示例测试曾误以为runtime-valid但任务失败应返回非零，按既有报告契约修正测试。均不证明物理任务成功，当前源码真实PickCube/Nut记录与独立物理reader仍待验证。

## PickCube调用方驱动物理回归与独立reader（续作，待复审）

`develop@d61fd168`，经 `examples/tasks/pick_cube.py` 的 `Solution.act → env.step(ExpertAction) → Solution.observe` 普通CPU路线，MuJoCo 3.8.1、seed31、horizon1000、R3：960 transitions，cube lift 0.10518958081676949 m，task success与Solution completion均为true，record finalize及close返回。H5 SHA-256 `0a2b6faff3f580819ee6c9cb105476efc61d3872df8706b5e160dd40c0df6912`，记录的source revision精确为 `d61fd168b23754111062468bc522ae87a233e996`。双锁按顺序获取及释放，worker 11.730秒、进程组退出、最大进程树RSS 338841600 bytes；argv、资源采样、输出位于ignored `native/pickcube-caller/`。

独立进程执行既有 `independent_readback.py` 对同一H5校验：PASS，960 transitions／961 boundaries、0.01 s control_dt及target/applied ack一致；无native substep证据，D0及Qualification未评估。详细结果 `native/pickcube-independent/readback.json`，另有用户reader `native/pickcube-reader/` 的T+1／存储校验。这只证明所述源码、seed、provider及路线，不重标其他源码或provider。

按原attempt001登记的105107／120000原生步上限加本续作classic单步和本次PickCube预留5000步，剩余额度不足以保守预留Nut horizon6000所需30000步；Nut完整物理回归与独立物理reader保持NOT_RUN。历史上限的适用／新的原生预算需在后续执行账本中明确，不能静默重置。

## PickCube调用方动作来源与身份（续作，待复审）

PickCube readiness Solution在调用方提供公开info时将当前source boundary和自身identity附在 `ExpertAction`；普通scalar CPU Env在推进前核对动作边界及解析配置中的Solution identity，并继续拒绝未支持的控制请求。旧 `act()` 兼容调用可不带boundary；Nut既有guard不变。此检查是内容一致性，不是防伪或调用者身份认证。无引擎组合 **188 passed、4 deselected**，包含错误identity／过期boundary在物理推进前拒绝以及Nut caller约束。源码已改变，前述 `d61fd168` 物理结果保留其原身份，不自动重标；本次改动后的物理回归仍待执行。

## 动作来源校验后的PickCube物理复验（续作，待复审）

源码 `f9cb51fd5315d36ead7b8ac2c87a1c5a29389a7d`，MuJoCo CPU seed31／horizon1000／R3，调用方驱动Solution路径再次完成960个transition、task success及Solution completion；H5 SHA-256 `264b35a9f08e754287957d8d7271be072bc5c06157d3755e80b155b9a2896763`。独立reader PASS：960 transitions／961 boundaries、0.01 s control_dt及target/applied ack一致；native substep未记录，D0和Qualification未评估。worker约11.73秒，进程组退出并释放两把共享锁。输出和完整资源／锁收据在ignored `native/pickcube-boundary/`及 `native/pickcube-boundary-reader/`。此前 `d61fd168` 结果仍保留原身份。

本次按horizon保守追加5000原生步，与原attempt001预留105107、上次PickCube预留5000及三个classic单步一起记账；即使不计classic，原120000步上限仅剩4893步。Nut完整horizon6000需预留30000步，已请求维护者明确新预算；未收到答复前不运行该回归。

## PickCube Position调用方动作与内建Harness（续作，待复审）

PickCube Position/F06的调用方 `ExpertAction` 经现有runtime控制owner投影为结构化请求，校验任务Solution身份、公开state boundary与当前typed state；实际控制计划继续原有完整预检。Position episode owner负责推进、故障、发布和记录，调用方负责 `Solution.observe()`；不让Env在新路径中调用Solution。内建PickCube Harness的trace改为包装公开 `env.step()`，并由调用方驱动Solution。普通scalar CPU及旧 `step_expert()` 兼容路径保留。

无引擎组合 **131 passed、1 skipped、1 deselected**，包含合成Position请求与错误边界／身份／维度拒绝、调用方Position的record成功／失败发布边界及Harness trace；真实F06场景投影被排除；1项Isaac解释器help测试因本checkout未配置其冻结解释器而跳过，未启动Isaac或GPU。完整argv与输出在ignored `position-harness-final.json`及相邻日志。宽组首次 **130 passed、1 skipped、1 failed、1 deselected**：失败的旧R3测试要求4 rad/s，与维护者已接收的当前Nut对齐2 rad/s配置冲突；在本修改输入 `cb01ff45` 复跑同样失败，现根据实际版本化profile补齐全部固定参数断言后通过。合成结果不授予Isaac能力或物理成功；此源码改动后此前PickCube物理结果保留原commit身份，Sol复审与最终适用回归仍需完成。

## 通用candidate的调用方驱动入口（续作，待复审）

通用pick-lift candidate binding、oracle和feasibility probe已改为调用方 `Solution.act → env.step → Solution.observe`；Solution factory身份不匹配、缺少caller action route均在step前报错，不再将旧 `step_expert()` 作为回退。`examples/_common.py` 中无调用者的旧helper已删除；Env内旧方法仍作为兼容保留。legacy `--env`也须提供caller route与Solution factory，故不兼容的旧输入明确失败。

无引擎Harness与selected组合 **139 passed、1 skipped、29 subtests passed**；skip为本checkout没有冻结Isaac Python，未运行Isaac。首次试运行candidate的真实编译／H5合成预检被catalog clean-check拒绝：两份原保护untracked仍存在，源码有本轮未提交修改；未隐藏或更改这些文件，也未伪造clean provenance。本轮源码提交后在 `257e5573`、tracked clean且仅余两个保护untracked时再次执行，仍被相同clean-check拒绝，确认不能仅靠提交本轮改动通过。该合成预检仍未通过，以上结果不能替代它或任何物理验证。本轮测试中的fixture缺少 `SimpleNamespace` 导致首次失败，已补齐并重跑；unsupported与错误身份分类明确为invalid。

## Recorder native interval准入（续作，待复审）

将已存在于环境中的pending native interval完整性校验归到canonical execution recorder，并在 `ExecutionRecorder.append` 准备完边界、修改存储前自行执行；环境仍在自己的发布边界调用同一校验，覆盖受限合成recorder及原有故障分类。缺失样本、计数／索引／timebase被篡改均拒绝，新增测试确认拒绝时pending、transitions、boundaries和blobs不变。保留边界序列化异常原有优先顺序：首次扩展测试暴露先读未序列化boundary导致异常类型变化，修正顺序后复验通过。

禁止引擎导入的selected、structured recorder及R05b组 **119 passed、1 deselected**，排除真实provider reset/step；streaming组 **34 passed、2 deselected**。两项被排除的旧诊断测试原始尝试因 `nut_assembly.assets` 迁移后路径不存在而导入失败，尚未修复，不能计为通过；另一次扩展尝试包含需要真实 `scene` 的position／camera测试，被引擎guard拒绝，不计为通过。完整最终argv、stdout、退出码与当时未提交diff摘要保存在ignored `recorder-final-evidence.json`及 `recorder-stream-evidence.json`。以上均为离线／合成验证，未运行native、Isaac或GPU，也不将历史物理结果重标到新源码。
