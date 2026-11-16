# 阶段3前维护 attempt001：Sol独立复审

日期：2026-11-04。决定：**REWORK_REQUIRED_PRE_STAGE3**。保留已提交的部分实现作为后继基线，整体维护目标未接受；G1仍为FAIL，G2–G4为PARTIAL。阶段3未开始，七阶段／22子阶段状态与阶段2有界接收决定不变。

## 审阅输入与证据

- 原输入Core：`develop@4bdf4d5ff9c7699a561454ebdd10ca5cea29e6c4`；首次返包`538835aa00c55628344368e6c10920d9b8d6c12b`；续作最终输出`656ef136d60754615634e8142c42bf1ad1633010`。
- 阅读原工作报告及`resumed_after_manual_forwarding/report.md`、[执行者交付记录](pre-stage3-refactor-attempt001.md)，检查输入至输出diff及续作diff，重点核对生命周期、四文件目录、Marker、完成／guard、USD接线、来源摘要与当前指南。
- 原五文件交接包checksum、所列prompt／README／snapshot、两个保护untracked及两个子模块checkout与snapshot一致。Nut来源manifest迁移前后字节完全相同，SHA-256为`0895a65980b97650bcc91ed9ee8a536958a15b0bc8d5703f5eab5ffdebd5c7d6`。
- 输出tracked-clean；两个任务均为`task.py`、`specialization.py`、`solution.py`、`config.yaml`及薄`__init__.py`；三个原tasks根模块及PickCube `isaac.py`已删除。原模块名出现在历史记录中不等于仍有生产导入。
- 核验续作`marker_test/clean_head`实际stdout及supervisor：88 passed、1 deselected，返回码0；`clean_head_isaac`为31 passed、1 skipped、2 deselected，返回码0。`final_manifest`为4 passed。均有禁止引擎import的tripwire，属于合成／离线证据，不是原生成功。
- 续作17份supervisor均记录本次worker进程组已退出、未请求共享锁，worker累计71.946秒；三份早期非零退出记录保留。该核验不等于现场检查他人进程／锁，也不声称他人已释放锁。
- 旧源码的MuJoCo成功及独立H5只能归属各自记录的源码。最终`656ef136`的调用方驱动Nut路径尚无完整真实物理与同run独立reader证据；3-transition FakeSession H5不能填补此门。

本轮Sol只做静态／Git／文件与既有收据核验，以及文档校验，不import provider、不跑pytest、reader或native。当前doc validator通过：0 errors、0 stale paths，96条历史链接问题保留；git diff --check通过。CodeGraph已漂移的文件按当前源码读取，未重建索引。原完整输出保留在Core的`workspace/maintenance/v211_pre_stage3_refactor_attempt001/`，本页不复制raw或重新封存整个历史树。

## 必须返工的问题

### R1／P1：规范生命周期仍未统一

`task_env/environment/env.py:48`仍定义独立`BaseTaskEnv`，`environment/reference_env.py:75`另定义`SelectedReferenceEnv`。Empty、Pendulum、TwoWheelBalance仍继承前者；前者持有SingleTaskLifecycleAdapter／RuntimeBoundary，后者持有RuntimeSession及其自身reset／step／fault／close路径。不是仅缺一个导出别名，而是本包最主要的实现目标尚未完成。

后继修改必须完成三个任务的单环境构造及调用者迁移，复用一个实际episode生命周期owner后再将各既有BaseTaskEnv导出指向规范类对象并删除旧实现。不能直接改alias、套空继承壳，或在同一门面后保留两份状态机。保留非Panda任务的动作观测、seed/reset、reward/done、有效scalar render和纯组装不启动runtime边界；并行仍延期G06。

### R2／P2：Marker移除了模板名字，尚未形成简单的任务开发路径

`examples/tasks/declared_marker.py:48`的`_compile_value()`和`:107`的`from_resolved_config()`承接了原模板的构造逻辑。用户示例仍需手工创建Controller、ReferenceTaskBinding、recipe／solution identity，枚举源码owner并读文件计算SHA，再设置resolved配置；任务声明和评价在其后。当前任务指南又要求复制这个示例。

删除`make_marker_env`和DeclaredPandaBoxEnv是已完成的部分，但把其基础设施内联到示例没有满足“通用能力归现有模块、降低二次开发难度”的原要求。后继应沿既有assembly／规范Env构造收回通用接线和provenance生成，使示例主要表达声明／reset／评价及正常注册，并继续由make_env创建。不能重新增加一个专用模板或make_<task>_env包装来隐藏问题，也不要求普通任务开发者手工构造SHA。以当前构造能力缺口为范围修复，不提前实施阶段3–6新协议。

### R3／P2：PickCube固定映射从task搬进runtime，职责分离尚不充分

`task_env/runtime/sessions/api.py:369`的`_validate_f06_pickcube_isaac_input()`新增了固定Panda关节名、`/F06Scene` body/frame映射、R3及1000-tick范围等原task输入检查；`:539`附近又把通用UsdRuntimeInput类型直接归入F06 PickCube路线。任务文件虽缩减，新增任务／source映射仍需修改通用runtime的具体任务规则。

source／执行身份、provider能力及受限来源准入本来就是runtime责任，严格校验不能移除或改为无条件信任任务。后继须分清：任务固定场景映射和策略值由现有specialization／声明构造，runtime依据既有受信source/profile及精确输入做统一核验；本轮新增搬入的任务硬编码不能只因放进“admission”函数就视为归位完成。保持原delivery、binding、horizon等拒绝语义和负例，不泛化／重写全部历史F04/F05路线，不扩大Isaac运行范围。

## 可以保留的部分成果

- 通用selected Env、binding、观测及大部分Position记录投影已迁到各自owner；历史replay不再默认反向导入diagnostics；静态摘要复用和动态边界负例有有界证据。
- Marker额外factory和中间模板、task根三个模块、PickCube `isaac.py`已移除；两个任务目录形态及Nut来源manifest原字节迁移得到确认。目录形态不能代替R1–R3的职责验收。
- Nut已有调用方驱动`Solution.act → env.step(action) → Solution.observe`实现，动作／来源／控制请求／五个native反馈样本及target/applied ack的合成正负例存在。step_expert保持受限兼容，不作为新标准Env入口。静态与合成证据不授予最终物理成功。
- README、当前API、多份task_env/doc和启动器有实质更新；关于两条生命周期、state-only与并行未适配的限制较准确。教程仍受R1/R2牵制，尚不能作为完成的新手最短开发路线。

## 门状态与验证边界

| 门 | Sol复审结果 | 尚缺事项 |
| --- | --- | --- |
| G0 | PARTIAL | 原P99真实单步的Core根cwd违规保留；事后保护SHA相同不使该运行变为合规 |
| G1 | FAIL | R1为主要出口；R2/R3职责整改尚需完成 |
| G2 | PARTIAL | 离线正负例、静态摘要与部分旧源码物理结果保留；最终实现尚无必要的代表物理回归 |
| G3 | PARTIAL | 当前文档已有更新，但统一接口及Marker最短开发路径未完成；新安装和启动入口的验证范围必须如实标注 |
| G4 | PARTIAL | 最终源码对应的完整物理记录、独立读回和清理证据缺失；旧run不重标 |
| G5 | PASS（仅交付动作） | 本地提交、两段报告及收据可审阅；不是整体接受 |

已排除的历史candidate测试、因引擎tripwire未覆盖的完整projection与过时R3断言分别记账，不能并入通过数。后继按当前正式契约保留／迁移有效检测，说明排除依据，不以简单删除断言凑绿。

本维护的必要最终运行仍是MuJoCo PickCube31／Nut19代表回归、三个迁移旧任务的CPU短检查及受影响scalar能力／独立reader。待源码稳定并合法取得两锁后执行；有新变动只重测受影响范围。Isaac native、GPU、三后端九格、训练和全后端新安装不是本维护新增完成门；完整Isaac投影未验证继续明确NOT_RUN，不借此扩大工期。

## 后继与当前停止点

追加的目录收敛要求已由执行者合入仓库planning，本轮不盲覆写staged整页；Sol在现有规划上补入本次复审与R1–R3。原冻结包、原报告、失败和阶段2证据不改写，不恢复旧源码。

下一份整合返工包应以本次Sol复审文档提交后的实际HEAD冻结，集中完成生命周期统一及相关职责／教程收敛，随后一次受影响验证。没有新的执行包或native预算从本页自动生效；维护者继续手动转发，Sol不向Terra活动对话追加指令。当前writer已释放，Terra已返包；其他用户的锁不干扰。阶段3仍未开始。
