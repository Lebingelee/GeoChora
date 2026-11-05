# 阶段3前维护：恢复后的物理检查

2026-11-05 维护者恢复 goal，并明确增加 40000 物理步预算：上限由 120000 增至 160000。原保守预留 115807，本次 PickCube 和 Nut 分别预留 5000 和 30000，合计预留 150807，剩余 9193。首次 PickCube 启动因包装脚本路径缺失退出，Python 未导入环境、未执行物理步；其失败和释放锁的收据保留。

维护者明确将两个维护输出目录的当前占用作为 2 GiB 存储检查口径。清理后经逐文件核对的 72 份 F04 测试副本已删除，冻结来源保留，核对和删除记录位于 ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/f04-copy-cleanup-20261105/`。本次两任务与 reader 完成后两个目录合计 846690014 bytes，低于 2 GiB。历史超限记录保持原身份；当前占用不代表历史累计写入量。

在 tracked clean `1d8cabdc632b9215a4aea734a87aed5aa0be9e38`，先通过不导入引擎的构造预检，然后串行执行 MuJoCo 3.8.1 CPU 测试。每个 native worker 按原顺序非阻塞获取两把共享锁，退出后释放；未启动 Isaac 或 GPU。执行源码、预检、argv、预算、资源采样、锁收据和原始输出位于 ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/physical-gate-20261105-resumed/`。

| 任务 | 物理结果 | 独立 reader |
| --- | --- | --- |
| PickCube seed 31，horizon 1000 | 960 transitions，任务与 Solution 报告成功；H5 SHA-256 `7d3fd5b5db2868fbf9f46423bbfdbe37a69e0c851f584b42c23b63152bafb852` | PASS，961 boundaries；时间间隔与 target/applied 身份通过。记录不包含原生子步数据。 |
| NutAssembly seed 19，horizon 6000 | 2377 transitions，外部 Solution 与任务报告成功，计划路线完成；H5 SHA-256 `136b9e39cc690bb2afbd55199017cb32ad811cd7e57fa4fba251c74f5e509ff7` | PASS，2378 boundaries、11885 原生子步；时间间隔与 target/applied 身份通过。 |

reader 在独立进程运行，输出报告未加载 native 模块。此结果只覆盖上述两条 MuJoCo CPU 路线及其记录读取，不构成 D0、Qualification、其他 provider 或全新安装验收。此前源码的证据不重标；此前续作的新职责调整仍待 Sol 独立复审。Marker 构造、F06 任务与 runtime 职责、诊断归位和完整新手入口等保留项仍按规划判断，阶段3未开始。

F04 篡改测试后续改为每个 pytest worker、每种来源按需复用一份临时副本；每个用例在 `finally` 恢复被篡改文件，module fixture 结束时删除副本。六种实际篡改用例在禁止引擎导入的进程中 **6 passed**；受监控输出峰值 248783523 bytes，结束后输出目录约 2657 bytes。输出及 supervisor 记录位于 ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/f04-reuse-verification-20261105/`。该修改仅针对测试，不重标上述物理运行的源码身份。

在 tracked clean `08a728ea` 通过 `examples/start.py` 指定已有 Python 和 GeoPhys 源码路径，执行 Pendulum／GeoPhys CPU／state-only seed 73 的 reset、一个 transition 和 close，观测空间检查通过，进程返回 0。两把锁按序获取及释放，worker 进程组退出，峰值 RSS 720629760 bytes；完整 argv、stdout/stderr 和 supervisor 位于 ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/starter-geophys-pendulum-08a728ea/`。此运行额外保守预留 1000 物理步，累计预留 151807／160000，剩余 8193；仅验证已有安装中的最小启动路径，不代表全新安装或所有入口完成。

在 tracked clean `fd365612` 以与 `7756812f` 相同范围及排除项重新运行完整无引擎组合：**290 passed、1 skipped、5 deselected**；禁用外部 pytest 插件并以 guard 禁止引擎导入，峰值 RSS 170401792 bytes。输出、实际 argv 和资源记录位于 ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/offline-fd365612/`；临时目录位于同一受监控输出目录。本次不覆盖被排除的真实场景及 provider。

`2fd30a47` 将 selected 录制时的配置投影、静态来源快照和 canonical metadata／recipe 组装转入既有 `recorders/reference_provenance.py`；Env 仍负责开始边界和 recorder 生命周期。对该 tracked clean 源码重新运行相同无引擎组合，**290 passed、1 skipped、5 deselected**，其中包含录制、来源摘要、同源重执行和故障检查；输出、argv 和资源记录见 ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/recorder-owner-clean-2fd30a47/`。生产录制代码已变更，以上 `1d8cabdc` 物理结果不重标到本提交；最终源码的两任务物理回归仍需额外预算后重跑。

`79ea472c` 继续将 selected 的 H5 持久化和 roundtrip 校验交给 recorder owner，Env 保留活动记录／故障检查和 Stop 顺序。扩展无引擎组合首次为 **324 passed、2 failed、1 skipped、5 deselected**：增加的历史诊断测试导入已移除的 `tasks.nut_assembly.assets` 而失败，堆栈在 ignored `recorder-finalize-refactor-offline/`；这些诊断还引用其他已移除的旧任务内部模块，不以换一个导入路径冒称已迁移。保留这两项为待处理诊断调用者问题，并在 tracked clean `79ea472c` 显式排除两项后重跑，**324 passed、1 skipped、7 deselected**；完整输出、argv 和资源记录在 ignored `recorder-finalize-clean-79ea472c/`。新源码尚无当前物理回归证据。

维护者随后明确将物理步总上限提高到 **300000**。对 tracked clean `a1ac8053` 重新进行 source-bound 构造预检，并在两把共享锁下串行运行 MuJoCo CPU 回归和独立 reader：PickCube seed 31 为 **960 transitions／PASS**，H5 SHA-256 `a0268c8edc49f9a1679f9dbf4a9b7cb052cbb400130ef929d780eff1f33c5773`；Nut seed 19 为 **2377 transitions／PASS**，H5 SHA-256 `7239556b93e8b66be913a6830f25fe26b69fe486fdd5149a9923684daa2c4087`。独立 reader 均 PASS，Nut 读回 11885 原生子步；PickCube 记录不含原生子步数据。两次 native 进程组均退出并释放两把锁，没有启动 Isaac／GPU。当前累计保守预留 **186807／300000**，余 113193；运行后原 attempt 与续作目录占用合计 953946079 bytes，低于当前 2 GiB 存储门。预算、逐阶段预留、命令、预检、stdout/stderr、资源和锁收据位于 ignored `workspace/maintenance/v211_pre_stage3_continue_marker_20261105/physical-gate-300k-a1ac8053/`。上述旧检查点“尚无当前物理回归”仅反映当时状态；本次不构成其他 provider、D0 或 Qualification 验收。

`b78b5e63` 修正上述两项历史诊断测试的导入边界：纯记录策略及无效参数检查不再预先导入已退役的任务实现；尝试实际运行历史 FULL 诊断时，若旧 NutAssembly 内部模块缺失，在创建输出或导入 native provider 前明确抛出 `StageUnavailableError`，指向冻结历史 checkout 或当前公开示例。这没有恢复旧 FULL 任务，也不宣称全部 52 处旧诊断引用均已迁移。原失败记录保留。对该 tracked clean 提交运行扩展无引擎组合，**327 passed、1 skipped、5 deselected**，包含原先失败的两项与新增的不可用路径检查；完整输出、argv 和资源记录在 ignored `legacy-diagnostic-clean-b78b5e63/`。

`2521a1b2` 让 Nut 组装和 R05b 控制准入从既有 `controllers.canonical` owner 直接引用共享控制器，不再经 Solution 模块转出。由于控制器身份包含 Nut 组装源码摘要，严格准入身份随之变化：100 Hz 从 `ff8581c5…` 更新为 `081685dc…`，500 Hz 从 `03d7b779…` 更新为 `e0540a9e…`；Solution 身份、控制器配置以及类型／source／provider 检查保持原值。首次仅更换导入时原身份固定值拒绝了两种频率（失败日志 `controller-owner-import-offline/`），重新按新源码生成身份并保留所有其他检查后，tracked clean 组合为 **329 passed、1 skipped、5 deselected**，覆盖两种 R05b 假 provider、来源准入及共享 owner；输出和资源记录在 ignored `controller-owner-clean-2521a1b2/`。这次源码变更尚无新的物理回归，不重标先前结果。

`0b7166f2` 将 F05 native、DG02 与 Isaac source preparation 共用的七项 TaskSource／Scene／Artifact／reset 摘要一致性校验归入 `runtime.sessions.source`；原类型检查、各路线独有的任务、资产、映射及 provider 限制保留。新增无引擎检查逐一构造七种错配，并使用实际 F04 source 验证一致输入与错误 reset plan。首次扩展测试为 **331 passed、1 failed、1 skipped、5 deselected**：额外纳入的 F05 测试需要导入真实 GeoPhys `scene`，被引擎导入 guard 拒绝（`f05-identity-refactor-offline/`）；没有启动引擎。移除该不符合离线边界的测试后，tracked clean 为 **332 passed、1 skipped、5 deselected**，记录在 ignored `f05-identity-clean-0b7166f2/`。这只是共享身份校验的归位，`runtime.sessions.api` 对 F05 候选类型的反向导入仍未消除，F05 真实构造／物理未因此验收；该源码亦尚需最终物理回归。

`648ffea8` 将历史 lifecycle 测试对已退役 Nut V1／V2 Solution 的导入限定在四个相关用例中：当对应模块缺失时明确 skip，通用生命周期用例继续执行。结合当前 Outcome Solution 的预算、运行时终止及失败拒绝测试，在 tracked clean 源码上 **19 passed、4 skipped**，记录在 ignored `solution-lifecycle-clean-648ffea8/`。先前将当前 Outcome 全部长轨迹与完整组合一次运行时达到 180 秒墙时限制，supervisor 终止进程组，不能计作完整通过；输出和限额收据在 `solution-lifecycle-compat-offline/`。历史四项没有恢复，当前 Solution 的长轨迹用例也未由这次受限运行完整验证。

针对 `0b7166f2` 的 F05 来源校验，在 tracked clean `92bbda90`（两者之间仅测试和文档变化）允许 GeoPhys CPU 公共 USD source／model 导入，在两把共享锁、禁用 CUDA 可见设备及 Isaac import guard 下运行：**4 passed**，覆盖真实 Menagerie 来源构造、错误设备／来源族拒绝、不支持的时间基准和能力在 native factory 前拒绝、公共 factory 转交。该测试不执行物理推进，进程组已退出、双锁已释放；命令、输出、资源和锁收据位于 ignored `f05-cpu-source-validation-92bbda90/`。此检查不等于 F05 真实 provider rollout 或 Isaac 验收，之前无引擎 guard 对 `scene` 的拒绝仍保留为该尝试的事实。

`f3601bdd` 将三个 F05 source-bound runtime 准入类型及其共同的冻结来源声明和映射收归 `runtime.sessions.position_admission`；任务 builder 继续负责构造并保留同对象兼容导出，任务 Scene 组装仍在任务侧。`runtime.sessions.api` 的精确类型分类不再导入任务 builder，且继续拒绝子类和错路线；新增测试禁止分类过程导入 Position 任务。tracked clean 无引擎组合 **333 passed、1 skipped、5 deselected**（`f05-admission-owner-clean-f3601bdd/`），GeoPhys CPU source／model 及前置拒绝检查 **4 passed**（`f05-admission-owner-cpu-clean-f3601bdd/`），后者双锁已释放、无物理推进。尝试 DG04 合成最低 I/O 测试时，冻结输入 `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic04/window_002/isaac_usd_v4/delivery_manifest.json` 缺失，读取前报 FileNotFoundError；原输出在 `f05-admission-owner-dg04-synthetic/`。因此 DG04 正向路径未验证、未启动 Isaac，不能把类型分类测试当成 DG04 物理或完整准入通过。最终源码物理回归仍需重跑。

随后在已有外部安装目录找到 DG04 原始 manifest，SHA-256 `06958dd05d901408f74f8e71cefdd73f6e5e28df0451457ea3b616c95ab0ad58` 与冻结准入值一致；直接只读使用，没有复制资产。首次读取成功后发现 F05 仍从 Nut 配置的旧位置读取 R3 profile（失败日志 `f05-dg04-synthetic-external-verified/`）。`3f7ab45d` 改为从共享 R3 Controller owner 加载 profile 及其源码摘要，并允许合成测试经 `F05_DG04_DELIVERY_MANIFEST` 显式指定来源。tracked clean 严格禁止引擎导入的扩展组合 **335 passed、1 skipped、5 deselected**，包含 DG04 两 episode 合成最低 I/O、recording/H5 读取及共享 profile 校验；命令、原件路径、哈希和输出位于 ignored `f05-dg04-clean-3f7ab45d/`。此前缺失路径的失败仍保留；该结果不启动 Isaac/GPU，不是 DG04 真实物理、D0 或 Qualification 验收。最终生产源码的 PickCube／Nut 物理回归仍需重跑。

`f06ee2f5` 将 selected 的 reset seed、options、来源和 mixed sample 校验归到已有 binding，Env 保留 session／录制／生命周期协调。tracked clean 无引擎组合 **335 passed、1 skipped、5 deselected**；使用已存在 task1 来源及假 provider 的 mixed 组合 **9 passed**，包括错误 seed／来源在关闭现有 session 前拒绝。第一次 mixed 尝试未设置 `R07C_COMPOSED_MJCF`，五项在构造前失败，原日志 `reset-binding-mixed-regression/` 保留；明确来源后通过，干净结果见 `reset-binding-clean-f06ee2f5-offline/` 和 `reset-binding-clean-f06ee2f5-mixed/`。

对 tracked clean `f06ee2f5` 串行重跑 MuJoCo CPU：PickCube **960 transitions／PASS**，H5 SHA-256 `d47c5e60ba0ffea6cf3bc652d427b075b57af51783c26b8913e8eac248b4c644`；Nut **2377 transitions／PASS**，H5 SHA-256 `e132641de721632998193088af1af7ed740ad0c5e20120a6b37fd04a4434266f`。两条独立 reader 均 PASS，Nut 读回 11885 原生子步；PickCube 记录不含原生子步。native 进程组退出并释放两把锁，未启动 Isaac／GPU。累计保守预留 **221807／300000**，剩余 78193；两个维护目录当前合计 1108769077 bytes，低于 2 GiB 存储门。预检、逐阶段账本、argv、资源及原始输出见 ignored `physical-gate-reset-f06ee2f5/`。结果仅属于该源码和上述 CPU 路线，不重标其他 provider、D0 或 Qualification。

为完成之前达到单次 180 秒上限的当前 Nut Solution 全部语义用例，在 tracked clean `0c224302` 对 `test_nutassembly_outcome.py` 收集的 **35 个唯一用例**按原 node ID 分七批串行运行，每批单独受同样墙时、内存及输出限制，结果 **35 passed**。包含完整规划轨迹、测量插入／释放／撤离、异常状态和故障拒绝；各批 argv、资源、退出码及完整收集清单位于 ignored `nut-outcome-batches-0c224302/`。这是合成测量状态的 Solution 语义检查，不是新物理 rollout；原超时记录保留。
