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

## Position执行路线构造准入归位（续作，待复审）

六条既有versioned Position构造路线的provider／backend／device／determinism／profile组合从环境构造收回现有runtime sessions admission owner，复用该owner已有profile常量；原准入集合和错误语义不变。该预检不授予source、delivery、provider build或native session准入，后续各自的精确检查仍然保留。新增测试逐路线检查五项身份偏移均拒绝；禁止引擎导入的selected／R05b／PickCube组 **133 passed、2 deselected**，排除真实provider reset／step及真实场景投影。

F04合成adapter在显式独立输出目录下 **10 passed、3 deselected**；被排除的三项依赖本checkout不存在的历史attempt003 worker。首次尝试未设置 `F04_S1_OUTPUT`，另两项因输出目录环境变量缺失而失败；后续已设置并重跑。完整argv、输出及源码diff摘要见ignored `route-owner-evidence.json`和 `route-f04-evidence.json`。未启动真实引擎、Isaac或GPU，历史物理结果仍绑定原提交。

## Native反馈任务准入归位（续作，待复审）

Nut的GeoPhys CPU/CUDA与100／500 Hz native-feedback选择和profile名称从通用Env构造移到任务binding；环境传递经该binding检查的请求，在reset时保留同一选择。binding要求准入与构造成对提供；错误provider、backend、非整数／布尔值及不支持频率在源构造前拒绝。原profile互斥、runtime的真实来源／controller／Solution／provider校验及五样本语义不变；旧私有 `_native_feedback_gripper_control_hz` 构造参数已由内部通用请求替代，公开任务工厂签名不变。

任务specialization源码SHA-256由此前 `f5f1ff2abc7d49a71df1327e02dc22122a313da3e292b3c379105a977efb727e` 变为 `d569ab5eb807318ca703207e64ee68bf0413828b88e7a277f7242a6c142026d2`。基于实际新源码构造的R05b Controller身份分别由100 Hz `cb0587780036a783be872beb44f9757586d35a6c5e753863f3f96f1e023d4d5b`、500 Hz `2f4292e6e2b15d4ae2947164e9766f5c185d0e4fe64bd1355afcc91ac5b9a4b5` 更新为 `4f6d28f5494912d2cae90769e63fe605c9dec4b0d0f8fbeb04fd45a556678a24`、`b832d4d959a1b818c02275dcb46803b458ba7c810fa6ae2dde858f288a5828d0`；Solution身份保持 `2db224bced2156e691276c6eaedf7468a87e6e07b90c205f5a2df208c0da8f07`。仅刷新精确身份，不接受旧值作为新源码别名，也不放宽原其他逐项约束。

禁止引擎导入的R05b／selected／recorder组 **138 passed、1 deselected**；lifecycle组 **176 passed、3 deselected**；leaf／mixed合成组 **12 passed**。其中R05b包括两种频率、来源及反馈篡改拒绝和合成H5读回；被排除的真实provider／Pendulum／scene测试不能算通过。完整argv、输出与源码diff摘要见ignored `native-binding-evidence.json`、`native-binding-lifecycle.json`和 `native-binding-mixed.json`。无真实引擎、Isaac、GPU或物理reader运行；旧物理结果不重标。

## Position相机观测声明归位（续作，待复审）

既有单Panda Position相机路线的space与schema声明归入observations owner，基于同一次相机字段声明构建空间与schema；环境继续组合并发布原有metadata。字段次序、shape、dtype、语义和限定的Panda路线未扩大；新增离线检查各相机space和schema的shape／dtype一致。该调整不表示已支持任意资产或新的camera／provider组合。

禁止引擎导入的selected／camera发布与故障组合 **112 passed**；F04合成adapter **10 passed、3 deselected**，排除项仍依赖本checkout缺失的历史worker。完整argv、输出与源码diff摘要见ignored `camera-declaration-evidence.json`及 `camera-f04-evidence.json`。本次未运行真实scene、Isaac、GPU或物理reader；旧物理结果不能重标。

## Scalar控制主体声明归位（续作，待复审）

原Env内固定的 `ControlBinding('panda-v1/gripper', 0.08)` 改为由任务binding显式提供；已有Panda机器人owner提供相同绑定，PickCube、Nut、Marker和通用candidate声明并在来源摘要中包含该owner。Position／mixed仍使用原有各自绑定计划；已有 `ControlBinding` 只实现经审计的0.08 m映射，不因本次改动支持新机器人或新夹爪。合成测试核对声明值确实传给materialization；缺失绑定时拒绝并释放已构造的source snapshot，reset重建也在materialization前复核。通用candidate完整合成oracle预检仍受保护untracked文件的clean-check阻挡。

Nut specialization SHA由 `d569ab5eb807318ca703207e64ee68bf0413828b88e7a277f7242a6c142026d2` 变为 `489f2907990886877e2c00921174ba477ed05c9134dfc622e8943cd0005ac7fe`；实际新源码构造的R05b 100／500 Hz Controller身份分别为 `df93686b259161e81335869bc2514ec3493881cf603547e69af9cf3c835a8686`／`70808c3bc93e825f5c6e1619148098bf651c7b0b451f25b48906777171725769`，Solution身份不变。仅刷新精确source-bound值，其他字段／来源／provider检查不放宽，不将旧运行重标。

禁止引擎导入的selected、R05b和Harness组 **136 passed、1 skipped、1 deselected**，skip为缺少冻结Isaac解释器，排除真实provider reset／step；lifecycle组 **178 passed、3 deselected**；leaf／mixed合成组 **12 passed**。完整argv、输出及未提交diff摘要见ignored `scalar-binding-final-evidence.json`、`scalar-binding-final-lifecycle.json`和 `scalar-binding-final-mixed.json`。未运行真实引擎、Isaac、GPU或物理reader，仍需最终代表性物理验证和Sol复审。

## Selected动作契约显式声明（续作，待复审）

通用selected binding不再默认位姿动作schema、space或转换器。PickCube、Nut、Marker、通用candidate及既有Position／leaf候选显式声明原有参考位姿契约；mixed路线继续由其任务构造提供结构化动作，拒绝混入scalar契约。环境只发布并使用绑定声明的schema／space／转换器。新增合成检查以一维任务动作及其转换器完成一次step，并验证缺失声明拒绝；这仅验证接线，不宣称新控制器或物理路线已实现。

Nut specialization SHA由 `489f2907990886877e2c00921174ba477ed05c9134dfc622e8943cd0005ac7fe` 变为 `fd320df270e66c42600f2f99cf5f44b0cc9f3213255879681d7322f51c3f0f9c`；实际源码构造的R05b 100／500 Hz Controller身份更新为 `fa6a2eb30c9bcefd1be8eda8b63efb89f8c7a237119b4b8121180d3a3cc243f1`／`d45a3cbe52bb45c051b00c1a652b757eac2b0cf668f051ad04c6d1bbd90613b1`，Solution身份不变。仅刷新精确源码身份；控制参数、来源／provider和反馈校验不放宽。

禁止引擎导入的selected／R05b／Harness组 **151 passed、1 skipped、1 deselected**；F04合成adapter **10 passed、3 deselected**；lifecycle组 **179 passed、3 deselected**；leaf／mixed合成组 **12 passed**；PickCube F06投影离线 **13 passed、1 deselected**。skip为缺少冻结Isaac解释器；排除项为真实provider／scene或缺失历史worker。前四组完整argv、输出及未提交diff摘要见ignored `action-contract-evidence.json`、`action-contract-f04.json`、`action-contract-lifecycle.json`、`action-contract-mixed.json`。未运行真实引擎、Isaac、GPU或物理reader，旧物理结果不重标；candidate完整合成预检的工作树限制仍在。

## Selected观测契约显式声明（续作，待复审）

非mixed任务binding现显式提供observation space和projection，现有PickCube、Nut、Marker和Position候选选择原有Panda projection；Env不再为其无条件指定该projection。mixed路线继续使用任务提供的观测，并保留既有contact summary身份／时钟校验。合成测试使用不同的单字段space与projection检查reset和step，缺失声明拒绝；这验证组合接线，不证明任意新机器人／后端或新schema的物理能力。同步修正仓库TaskEnv skill路线图中旧BaseTaskEnv生命周期和旧阶段队列的过时描述。

Nut specialization SHA由 `fd320df270e66c42600f2f99cf5f44b0cc9f3213255879681d7322f51c3f0f9c` 变为 `4ed30e639e938797d965406d27a3d31e2c08078c12c3adf6476d0d0e28ec4d1b`；按该源码实际构造的R05b 100／500 Hz Controller身份更新为 `6282ca640c7a7d33c011f94f63e72c6decbf6310e55efec64a19ea004a62aca4`／`ca0af8368bfe799599eff974242aae3d5d9dd97811291f52c83545daf34870e3`；Solution身份和其他控制／来源／provider约束不变。旧物理结果不重标。

禁止引擎导入的selected／R05b／Harness组 **152 passed、1 skipped、1 deselected**，F04合成adapter **10 passed、3 deselected**，lifecycle组 **180 passed、3 deselected**，leaf／mixed合成组 **12 passed**。skip为缺少冻结Isaac解释器，排除真实provider／scene和缺失历史worker；完整argv、输出和未提交diff摘要见ignored `observation-contract-evidence.json`、`observation-contract-f04.json`、`observation-contract-lifecycle.json`、`observation-contract-mixed.json`。本次未运行真实引擎、Isaac、GPU或物理reader；candidate完整合成预检的工作树限制与代表性物理验证仍待解决。

上述验证后补入Marker和通用candidate的观测owner来源文件，Marker来源字节与candidate调用接线定向复验 **3 passed**；前述组合日志对应补入前的源码diff，不重标为最终diff的完整复跑。

## Mixed控制准入归位（续作，待复审）

将任务准备的mixed action、结构化请求、writer字段和实时source／episode／revision边界校验交给既有runtime control owner；Env继续调用该校验并协调执行、fault、记录和Solution发布。保留原字段集合、校验顺序、错误信息及推进前拒绝行为。新增合成用例覆盖过期state revision、非有限动作和多余字段，并安装runtime写入陷阱，确认拒绝前既无写入也无物理推进。

禁止引擎导入的selected／R05b／Harness组 **152 passed、1 skipped、1 deselected**；lifecycle组 **180 passed、3 deselected**；leaf／mixed假provider组 **15 passed**。前述组合完整argv、输出和当时diff摘要见ignored `mixed-preflight-selected.json`、`mixed-preflight-lifecycle.json`及 `mixed-preflight-expanded.json`。其后增强runtime写入陷阱，相关mixed成功／fault和篡改用例定向 **6 passed**；不将此前组合日志重标为增强后的完整复跑。无真实引擎、Isaac、GPU或物理reader运行；先前物理结果不重标。

## 通用candidate编译和调用方接线合成检查（续作，待复审）

新增一个明确标记的provider-free测试：使用当前Core commit和显式 `core_dirty=True` 的合成catalog，先确认正式 `validate_catalog` 拒绝，再仅在测试中替换asset checker的catalog准入，实际执行 `compile_candidate`、规范Env构造、reset、外部Solution `act → step → observe` 和close。任务动作／观测binding、Panda scalar控制绑定及source记录经此调用链执行；provider session为替身。该测试不调用Judge、不写正式报告或证据包、不声称dirty catalog通过，不能替代此前失败的严格Oracle／Judge预检或任何物理回归。

禁止引擎导入的selected／R05b／Harness组合 **153 passed、1 skipped、1 deselected**；完整argv、输出与当时diff摘要见ignored `synthetic-candidate-current.json`。skip为缺少冻结Isaac解释器，排除真实provider reset／step；两份保护untracked及严格clean-check均保留。未运行真实引擎、Isaac、GPU或物理reader。

## Structured录制终结与初始化原子性（续作，待复审）

Position与mixed共享既有recorder owner的v3终止原因、最终boundary、T/T+1和H5回读校验；保留Position的 `horizon` 别名、leaf／camera专用读回以及各路线原有错误信息。mixed录制开始改为先成功 `begin_episode` 再发布recorder和路径；合成故障注入确认初始化失败后环境无活动recorder、无输出文件且可重试。新增两路线的错误终止原因和不完整boundary检查，确认拒绝前录制状态不变。

无引擎selected／R05b／recorder组合 **164 passed、1 skipped、1 deselected**；lifecycle组 **183 passed、3 deselected**；leaf／mixed假provider组合 **13 passed**，日志及diff摘要见ignored `record-finalize-v2-selected.json`、`record-finalize-v2-lifecycle.json`、`record-finalize-v2-mixed.json`。附加严格禁引擎的attached-leaf合成H5及reader／篡改检查 **1 passed**（64 transitions／65 boundaries，不是物理reader）。首次完整lifecycle尝试中的一项candidate测试因严格guard拒绝查询MuJoCo spec而失败；已将该测试的provider身份明确替换为合成值后重跑。attached-leaf读回首次误用会预置假MuJoCo模块的mixed guard，reader按其禁止provider模块契约拒绝；改用严格guard后通过。未运行真实引擎、Isaac、GPU或物理reader。

## Scalar录制绑定来源（续作，待复审）

selected scalar录制在开始边界对绑定实际使用的动作转换／space、观测投影／space函数的源码文件取摘要，不再无条件把默认Panda观测模块当作实际投影来源。每次录制对同一文件只读取一次，新录制重新读取，不持久按路径缓存；文件内容变化后摘要变化。无法追溯到源码文件的callable在recorder发布前明确拒绝，修正后可重试；canonical和execution recorder均在首次boundary准备成功后才发布路径和实例。该摘要是开始时的文件字节，不单独证明运行中加载的代码与磁盘字节一致。

无引擎selected／R05b／recorder／Harness组合 **168 passed、1 skipped、1 deselected**；lifecycle组 **185 passed、3 deselected**；leaf／mixed假provider组 **12 passed**。测试覆盖自定义观测函数的真实文件摘要、重复文件单次读取、文件替换后重新计算、无法追溯函数拒绝及重试；完整argv、输出与当时diff摘要见ignored `binding-source-selected.json`、`binding-source-lifecycle.json`和 `binding-source-mixed.json`。本次不证明物理任务成功，未运行真实引擎、Isaac、GPU或物理reader。

## Position候选识别的调用方向（续作，待复审）

通用observations和recorders不再从 `tasks.position_candidate.builder` 导入版本候选识别器；版本候选binding显式提供原精确类型识别，公共组合层检查识别器存在及返回值在原有支持集合内。未知或非精确类型仍拒绝；runtime后续source／provider准入继续独立检查。此项只消除观测及记录两处反向依赖，runtime中的其他versioned候选类型依赖仍待处理，不视为完整职责整理。

无引擎selected／R05b／Harness组 **157 passed、1 skipped、1 deselected**；F04合成adapter **10 passed、3 deselected**；lifecycle组 **185 passed、3 deselected**；leaf／mixed假provider组 **12 passed**。严格禁引擎attached-leaf合成H5及reader／篡改检查另 **1 passed**。四组完整argv、输出与当时diff摘要见ignored `position-classifier-evidence.json`、`position-classifier-f04.json`、`position-classifier-lifecycle.json`及 `position-classifier-mixed.json`。排除真实provider／scene或缺失历史worker，未运行真实引擎、Isaac、GPU或物理reader；物理结果不能重标。

## Session候选类型准入收敛（续作，待复审）

F05三条Session准入、DG04合成IO上下文和GeoPhys／Isaac native adapter复用同一个现有精确类型分类，adapter不再分别导入候选类；保留每条路线的原错误、精确类型（包括拒绝子类）、输入验证和身份绑定。F06的通用USD输入先于F05候选导入完成分类，不再为F06分类加载无关Position构造器。这个分类只决定后续准入路径，不授予provider／source／delivery许可。Session的唯一分类点仍依赖三个任务候选类型；完整解除runtime对任务类型的依赖尚未完成。

无引擎selected／R05b／F06投影／Harness组 **170 passed、1 skipped、2 deselected**；F04合成adapter及DG02无效输入 **11 passed、3 deselected**；lifecycle组 **185 passed、3 deselected**；leaf／mixed假provider组 **12 passed**。新增检查覆盖不同路线／子类拒绝、无效输入在native provider初始化前拒绝，以及F06分类不导入Position任务。首次另外尝试的两项F05测试依赖真实 `scene`，被禁止引擎guard拒绝，未计为通过。完整argv、输出与diff摘要见ignored `session-route-selected.json`、`session-route-f04.json`、`session-route-lifecycle.json`和 `session-route-mixed.json`；本次未运行真实引擎、Isaac、GPU或物理reader。

## Recorder初始边界原子准备（续作，待复审）

`TransitionRecorder.begin_episode()` 先完成初始观测与元数据复制、容量核对，再替换原recorder状态。初始观测超出容量或元数据复制异常时，不再丢弃上一条已冻结轨迹或错误留下active状态；修正输入后可重新开始。该行为覆盖直接使用Recorder的调用方，不只依赖Env此前新增的局部初始化保护。

受监督、禁止引擎导入的selected／R05b／录制组 **145 passed、2 deselected**，最大进程树RSS 214175744 bytes；leaf／mixed假provider组 **13 passed**，最大RSS 127586304 bytes。命令、退出码、资源采样及输出保存在ignored `atomic-begin-selected/`和 `atomic-begin-mixed/`。排除真实provider／scene，未运行真实引擎、Isaac、GPU或物理reader。

## Selected轨迹调用方重执行与绑定来源校验（续作，待复审）

selected轨迹重执行现由调用方执行Solution的 `act → env.step(action) → observe`，并核对构造出的Solution身份；生产调用链不再调用 `step_expert()`。重执行对记录中存在的动作转换、动作space、观测投影和观测space来源，逐项核对实际binding的源码文件摘要，旧记录中不存在的字段不补造。PickCube和新Nut调用方录制均经禁止旧入口的合成测试；旧Nut专家录制的诊断契约不同，在创建输出前明确拒绝该重执行，原记录保留，不将其重标为调用方录制。历史重执行能力因此有明确收窄，不能把拒绝视为物理差异判断。

受监督、禁止引擎导入的selected／R05b／录制组 **150 passed、2 deselected**，最大进程树RSS 210403328 bytes；命令、退出码、资源采样和输出保存在ignored `caller-replay-selected/`。排除真实provider／scene，本次未运行真实引擎、Isaac、GPU或物理reader，旧物理证据不重标。

## Position切换记录投影归位（续作，待复审）

Position Controller切换事件及提交后记录失败的凭据由既有 `recorders.position_metadata` 构造；Env仍负责活跃边界准入、runtime准备和提交、事件校验／写入、指针发布及故障锁定。记录字段和提交顺序保持，合成调用覆盖提交成功与提交后记录失败，确认失败时保留已提交Controller身份、不发布pending且保留故障凭据。该改动只是职责整理的一部分，不代表环境类或runtime接线已全部归位。

受监督、禁止引擎导入的selected／R05b／录制／Position切换组合 **154 passed、17 deselected**，最大进程树RSS 207585280 bytes；完整命令、退出码、资源采样和输出保存在ignored `switch-projection-selected/`。最初直接运行Position切换全组时，15项依赖真实 `scene` 的测试被禁引擎guard拦截、2项通过；随后明确排除这些依赖后运行上述组合，不能将被排除项算作通过。未运行真实引擎、Isaac、GPU或物理reader；本次源码与旧物理证据身份不同。

## Position控制绑定显式声明（续作，待复审）

环境不再为Position及leaf路线选择Panda夹爪名称或构造固定0.08 m映射；PickCube、普通／版本候选、双实体候选及attached-leaf各自在binding声明原有 `ControlBinding`，环境在materialization前要求selector返回精确类型。0.08 m仍是现有控制owner的唯一已审计映射，不宣称新增夹爪能力。内部 `ReferenceTaskBinding.position_gripper_binding` 改为 `position_control_binding`，原本自行构造该内部binding的调用方须迁移；仓库当前调用者已同步。

PickCube specialization的源码SHA由 `101b68d9ae6876f90c2ef10a7f21cd025489f76aac5384938157a2f82ca28770` 变为 `ef9e5ddec299bac2fc00eda05cfbd11a79f58b285fb341a6aca74fc5d1d44a08`；新构造时按新源码取来源，不把旧运行重标。受监督无引擎selected／R05b／F06投影／录制组合 **151 passed、2 deselected**，包含F06 binding缺失及错误类型在runtime创建前拒绝，最大RSS 213626880 bytes；attached-leaf／mixed假provider组合 **13 passed**，最大RSS 160727040 bytes。日志及资源采样见ignored `position-binding-selected/`与 `position-binding-mixed/`。另一次直接运行F06投影时有1项因导入真实 `scene` 被guard拦截，未计通过；上述排除项包含对应真实scene测试。未运行真实引擎、Isaac、GPU或物理reader。

## Position控制绑定的录制来源（续作，待复审）

Position materialization成功后保留实际传入的 `ControlBinding` 和selector，v3录制开始时由recorder owner将绑定值及该selector声明文件的SHA-256写入 `resolved_config.position_control_binding_provenance`，经现有H5 `env_cfg` 保存。reset之后替换任务binding不会把新selector误记为当前session实际使用者；源码摘要是录制开始时磁盘字节，不单独证明加载代码或闭包内容与文件一致。摘要无法读取时在发布recorder前失败，可修复后重试。旧H5无该字段仍保留原身份，Position v3重执行仍不支持。

受监督无引擎selected／R05b／F06投影／录制组合 **151 passed、2 deselected**，最大RSS 213962752 bytes；attached-leaf／mixed假provider组 **14 passed**，最大RSS 165650432 bytes，包含64步合成H5写入及独立读取。其后仅将来源投影函数归入recorder owner，相关定向检查 **1 passed**；组合日志对应归位前的源码，不重标为最终diff。日志与资源采样见ignored `position-binding-provenance-selected/`和 `position-binding-provenance-mixed/`。首次单步写回尝试被R03c reader要求64步的契约拒绝，调整为64个合成interval后通过；另一次读取尝试误用v1元数据路径，改用实际v3公开inspect入口后通过。未运行真实引擎、Isaac、GPU或物理reader。

## Position运行时状态绑定归位（续作，待复审）

Position reset对runtime snapshot所需的Scene scalar Joint、free-body reset Frame到唯一floating Joint，以及body／Frame语义到Artifact FrameReference的解析，归入既有 `runtime.sessions.source`；Env调用这些解析器并继续协调materialization和reset。保留旧内部Frame解析入口的同对象导出。定向检查验证使用Artifact与Scene关系而非provider名称选择Joint，并覆盖缺少Frame、无匹配或多个floating Joint、与scalar名称重叠的拒绝边界。此项不宣称runtime与任务候选类型的反向依赖已完全解除。

受监督、禁止引擎导入的selected／R05b／F06投影／录制组合 **152 passed、2 deselected**，最大RSS 213581824 bytes；attached-leaf／mixed假provider组合 **14 passed**，最大RSS 165597184 bytes。完整命令、退出码和资源采样见ignored `source-bindings-selected/`与 `source-bindings-mixed/`。排除真实provider／scene，本次未运行真实引擎、Isaac、GPU或物理reader；旧源码物理结果不重标。

## 正式控制反馈归位及重执行源码清单（续作，待复审）

selected控制应用回执的target／applied、Artifact、Controller、provider、单interval边界及时钟校验和投影归入既有canonical feedback owner；Env仍取得真实评价边界、调用校验后发布结果。保留原校验次序、错误和浮点时钟容差；旧内部容差函数导出为同对象兼容入口。新增篡改检查覆盖错误target、Artifact、Controller、provider、control step与时间。

selected重执行现将记录的 `source_sha256:` 任务源码路径及摘要清单与当前任务构造所得清单精确比较，修改、缺失或新增文件均在reset／写输出前拒绝；已有绑定投影／转换源码检查继续保留。旧记录没有任务源码清单时沿用原路径，但因此不能凭这一检查证明旧记录完整任务源码一致。被检查的文件摘要对应当前构造时的磁盘字节，不证明运行中代码对象与磁盘一致。

最终受监督、禁止引擎导入的selected／R05b／F06投影／录制／时钟组合 **162 passed、2 deselected**，最大RSS 207974400 bytes；完整argv、退出码、资源采样见ignored `control-feedback-replay-final-v2/`。首次完整组合运行期间删除了一个不再使用的import，因此用最终源码重跑并仅以前述第二次结果为最终证据。排除真实provider／scene；未运行真实引擎、Isaac、GPU或物理reader，旧源码物理结果不重标。

## Marker binding来源收集归位（续作，待复审）

Marker不再逐项枚举reset、评价、观测等源码owner；已有assembly构造来源函数接收实际提供的 `ReferenceTaskBinding`，收集声明的callable及控制binding类型所在文件，PandaBox编译结果声明自身实际使用的场景、机器人和编译owner。新增合成检查确认换成独立文件的观测回调后，该文件字节变更会改变构造来源及recipe身份；旧来源摘要如实变化，不改写旧run。收集范围是显式binding、编译组件及共同owner的声明文件，不追踪闭包捕获或函数间全部间接依赖，也不证明加载代码等于磁盘字节。

受监督、禁止引擎导入的selected／R05b／F06投影／录制组合 **162 passed、2 deselected**，最大RSS 201625600 bytes，完整argv、退出码和资源采样见ignored `marker-binding-owners-selected/`。Marker仍显式创建 `ReferenceTaskBinding` 和resolved配置，本项减少来源枚举，不单独宣称R2新手构造目标完成；待Sol复审。未运行真实引擎、Isaac、GPU或物理reader。

## Marker重建时的当前binding来源（续作，待复审）

上一检查点的Marker构造闭包持有创建时的binding：如果环境在重建前替换binding，该闭包可能继续把旧binding交给来源收集。现有 `ReferenceTaskBinding` 增加显式opt-in的普通构造调用方式，在初次构造和reset重建时将当前binding传给构造函数；未opt-in的调用方仍使用原单参数调用，seeded、native-feedback及mixed的专用构造路径不变。Marker使用该能力，合成测试在构造后替换观测回调并reset，确认实际新回调的源码摘要进入重建值。该检查不消除已记录的间接依赖和运行中代码／磁盘字节限制。

受监督、禁止引擎导入的selected／R05b／F06投影／录制组合 **163 passed、2 deselected**，最大RSS 205631488 bytes；attached-leaf／mixed假provider组合 **14 passed**，最大RSS 165675008 bytes。完整argv、退出码和资源采样见ignored `current-binding-selected/`与 `current-binding-mixed/`。未运行真实引擎、Isaac、GPU或物理reader；Marker剩余通用组装和最终R2判断仍待后续工作及Sol复审。
