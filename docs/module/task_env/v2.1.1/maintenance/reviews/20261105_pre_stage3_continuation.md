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
