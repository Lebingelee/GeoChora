# E11–E16 U3：完整 Solution 实施结果与开放边界

状态：执行及修复已记录，T19 的 completion 记录边界、T20 最终对账和整体接收仍 OPEN；非独立主审或维护者接收。输入 HEAD `1ff617d0c441ea7968c90f23b1bdb027ae5b65d8`；输出 HEAD 为本记录所在提交。原始计划、锁与资源采样、stdout/stderr、H5 和独立读回位于 ignored `workspace/maintenance/v211_e11_e16_u3_20261113_001/`，由 `u3-intermediate.json` 索引；不把数据写入 Git。运行使用含未提交修复的工作树，不能声称全部记录来自干净提交。PickCube 的 Solution 源 SHA 为 `603a339a1ded6c26fb1d53746a18b75196433edc472e78f90534906d71977c07`；实际命令、其余源码身份和限制见各 plan。

| 检查点 | 实施结果 / 未决 owner |
| --- | --- |
| T15 | 五交集及定向复验的命令、源码、锁和资源计划已冻结；SDK 隐式推进 unknown。 |
| T16 | 两条 CPU PickCube 完整运行并成功，含 GeoPhys clock 修复后的受影响复验。 |
| T17 | Isaac 完整执行并同次记录，运行有效但任务和 Solution 失败；App 日志限制不抹除。 |
| T18 | 两条 CPU Nut 完整运行，MuJoCo 和 GeoPhys 均满足原严格任务／Outcome 条件。 |
| T19 | 同次 H5 动作、状态、clock、任务谓词和 T/T+1 已独立读取；v3 completion 不在 H5，关联 caller 原报告且不回填。此记录边界须独立主审并由维护者决定，不自封例外。 |
| T20 | V01～V09 证据入口和复用理由见下，完整逐 claim 评审仍归 U4。 |
| T21 | 五条分项结果及失败历史见下；T19 未决时 E13 不标记全部关闭。 |

| 同次运行 | 执行 / 任务 / Solution | 记录独立读回 | close |
| --- | --- | --- | --- |
| PickCube MuJoCo seed31 R3 | PASS / 成功 / 完成 | 960 transitions、961 boundaries，PASS；`9a429ce009fdb3d408be0e2936da253770511e5d1f640a7f7fcd80635588369d` | 报告成功 |
| PickCube GeoPhys seed31 R3 | PASS / 成功 / 完成 | 951 / 952，PASS；`8e0902433c60d87e3d8183905a5e80080cc8dd169227d357f58b22bf7a3eb794` | 报告成功 |
| Nut MuJoCo seed19 Outcome | PASS / 成功 / 原严格完成及 planned、Outcome 成立 | 2377 / 2378，PASS；`539609ec20eab16049f5c21b111547cb18c128fd1d1f191a7f4d3340f1d5e090` | 报告成功 |
| Nut GeoPhys seed19 Outcome | PASS / 成功 / 原严格完成及 planned、Outcome 成立 | 2442 / 2443，PASS；`b87abe1e7a2a467e47dab5b56ddb0147ab7e931f634cc7a07161ea11cf10c6f0` | 报告成功 |
| PickCube Isaac PhysX CUDA seed31 R3，读回修复后定向复验 | runtime valid、退出码 0；到 horizon，任务失败、Solution 未完成 | 1000 / 1001，5000 原生子步收据和时钟、任务谓词独立读回 PASS；`3f163081760f6ad8a49abb593c6a1266dc47f20bd72751bf49e5bd1e30951d48` | API 报告成功；App shutdown 日志未给出完整终止证明 |

Isaac 第二次运行的原报告 ERROR，直接原因是示例在 v3 通用记录校验后又用 canonical 专用 reader 打开该文件。修复后先独立读取原 H5，再按同一参数定向复验，生成第三次运行及其自己的 H5；未改写第二次原报告、退出码或 H5。独立关联器核对两次报告与各自 H5 的 episode、provider materialization、Controller、Solution 和计数，分别见 `pick-isaac-r2/same-run-association.json`、`pick-isaac-r3/same-run-association.json`。v3 无 `planned_action` 标志且 Outcome 的 `solution_completed` 为 null；示例不伪造该标志，任务与 Solution 状态及 close 使用同次原报告，状态记录与任务谓词由独立 reader 复算。以第二次原 H5 和原 episode 内容驱动的 `offline-fake-caller.json` 仅验证修复后的报告路径，环境与 close 均为 fake，不是物理运行。此次 state-only，不声称 RGB、D0 或额外资格。

GeoPhys 首次 PickCube 在第 3 个 transition 遇到 clock guard；修复以实际 `physics_dt × control_substeps` 的现有误差界验证，仍拒绝 stale/skipped。随后两条 PickCube CPU 重跑均使用此 Solution。Isaac 首次运行 worker EOF、无 H5；原因未证实。第二次取消示例对子进程继承的 CPU 时间限制，保留独立墙时和 cgroup 限额；执行 584.5 秒、未触发资源中止。第三次在读回修复后以相同交集和资源预算执行 590.9 秒，退出码 0、未触发资源中止，冻结计划 SHA `76e75ff15035938d373ecda22c432d615cac3d594cda3dc5639875e66b285ac1`。两把既有锁均释放，SDK 隐式推进量仍为 unknown。四 CPU 运行早于 Isaac 示例预算及读回的后续修改；不可将其描述为在最终干净 HEAD 重跑。

当前受守卫纯/fake 集合 **223 passed**，包含 v3/canonical 读取分派、记录计数不一致、文件摘要错误和 close 失败测试；这不是新增物理运行。文档检查仍为既有 2 errors、96 条历史链接问题，没有新增错误。四保护输入字节及 GeoPhys/Menagerie pins 相对 U2 输入快照未变。T19 的完成事实由 caller 持有并写入同次报告，v3 H5 没有该事实；独立关联器只核对其身份与位置，不把此缺失改称 H5 内独立验证通过。须继续核对该 owner 补齐方式与接收边界；T20 的 V01–V09 映射草稿见下，最终 U3 对账及独立主审仍 OPEN；U4–U7 未完成。保留首次失败、来源和 SDK 关闭限制，不靠读回补造 Solution 成功。

离线关联入口已纳入 [版本诊断](../../../../../../task_env/diagnostics/tasks/v2.1.1/associate_solution_record.py)，逐条核对原 H5 SHA、独立读回、同次 caller、监督命令及身份，五条输出分别为各运行目录的 `association-verified-v2.json`。Isaac 的 Outcome completion 标为 `ABSENT`，canonical 路线在此关联检查中标为 `NOT_CHECKED`；二者均不从 caller 报告回填。真实 H5 与复制的小收据进行离线负例：更改 H5 哈希、命令输出路径、seed 和混入另一运行日志均被拒绝，见 `association-negative-checks-v2.json`；未启动仿真。该关联入口消费原有独立读回结果，并不代替读回动作／状态／clock 或验证 Solution 内部生命周期。

五次运行的真实 argv、环境、具体 source／配置摘要及资源计划保存在各自 `supervisor.json` 和 `native-plan-repaired.json`（四 CPU，SHA `0d8da36fa7dca080de7cdd57622161d1488bdaa93d445a6c38497980f922b12e`）／`native-plan-isaac-r3.json`。按上表顺序实测墙时约 31、160、116、424、591 秒，非预测下次运行耗时。关联命令见诊断 README；独立物理数据读回分别为 `python -B workspace/maintenance/v211_e11_e16_u3_20261113_001/read_pick.py <原H5>`、`read_nut.py <原H5>`、`read_pick_v3.py <原H5>`，需使用该目录作为后三个脚本的父路径，并按计划设置无 SDK／资产 guard；这三个命令只读文件、无 App 或物理步。输出带 H5 字节与 SHA；输入发生迁移时必须重新关联，不能把旧路径当作新包证明。

提交前计量（2026-11-13）：相对 U3 输入 HEAD，生产 Python／示例 `+52/−19`、净 `+33`，诊断 `+209/−10`，文档 `+58/−5`；新增两个诊断文件和本记录，无整文件删除或迁移。相对规划输入 `a6b107ac`，生产 `+340/−232`、诊断 `+3035/−1188`、文档 `+740/−44`；累计相对 `1f1359ee` 生产 `+8487/−16975`、诊断 `+9383/−1187`、文档 `+2692/−169`，另有其他类型 `+1/−3`。这些是按 Git diff 的行数（Markdown 算文档），含此前已接收工作及 Git 重命名判定，不是本单元独占成果。此次生产修改仅涉及 Solution 时钟核对与示例监督／读回，不改 Runtime advance owner、Position/effort/wrench 语义或 renderer。

## V01–V09 对应入口（实施者复核，待独立主审）

| 验证 | 当前或历史证据 / 影响与限制 |
| --- | --- |
| V01 | `test_public_isaac_example.py::test_public_yaml_and_mapping_have_same_selected_configuration` 的纯测试；本轮真实 PickCube/Nut 命令见各 `native-plan*.json`。这是所测任务配置，不推断所有组合。 |
| V02 | 上表 PickCube、Nut 完整路径；Pendulum、双轮车及装配 Panda 的旧最短路径见 [E05–E10 U7 按 provider 的结果](../20261113_e05_e10_u7_delivery.md)。本批 Solution clock 和示例读回没有修改这些旧主体的 source 或 Runtime；旧证据保持原输入，不声称本轮重跑。 |
| V03 | Position 的五条本轮记录；effort、装配及冲突/fault 原输入见 U7 的 S27 和 [E05–E10 独立主审](20261113_e05_e10_independent_review_d9dc02c6.md)，本批未修改 Controller 提交 owner 或物理语义。纯集 `test_effort_servo.py`、`test_control_lifecycle.py` 为 fake，不替代 native。 |
| V04 | borrowed／独立及非 Position 的 native 入口见 U7 的 S19、S25；当前纯集 `test_task_rgb_source_routing.py` 验状态、clock 与职责分离。本批未改 renderer，旧渲染结果不能称最终 HEAD 重跑。 |
| V05 | 三 native、GeoPhys physics × MuJoCo renderer 和 window 的具体原始入口见 U7 的 provider 表及 U4 收据；不同结果使用各自冻结输入，GeoPhys 子步和 Isaac 启动隐式推进限制仍在。 |
| V06 | U7 的 S19 和 S25 包含 reset、step、再 reset、重复采集及关闭；本轮 `test_task_rgb.py` 为 fake。无新增 RGB 物理矩阵，实际 SDK/window 与颜色限制保持历史范围。 |
| V07 | 固定纯入口列于 [诊断 claim 表](../../../../../../task_env/diagnostics/tasks/v2.1.1/README.md)，其中资源、stale、fault、旧入口测试须按所列精确节点解释；`test_pickcube_clock.py` 新增正常多子步与 stale/skipped 验证。U2 的失败/回退与旧入口见 [caller 对账](20261113_e11_e16_u2_caller_review.md)。 |
| V08 | 上表五条不同真实进程；两项 MuJoCo 的任务和原 Solution 完成，Isaac 修复后复验任务失败原样保留；第二次原报告错误不能升格为 PASS。 |
| V09 | 四条 canonical 的 `read_pick.py` / `read_nut.py`，Isaac 的 `read_pick_v3.py`，均在原 H5 关闭后单独进程读取；输入、hash 和报告见 ignored run 目录。Solution lifecycle、close 不由缺少该字段的文件推断；没有图像的路线不声称图像验证。 |

旧 native 的精确 argv、source、输入 SHA、预算与结果保存在 U7 所链接的原计划／收据；本轮新的五条见 U3 plan 和 supervisor 收据。上述对应不是把全部历史结果变成当前 HEAD 的新测试，也未替代 U4 的独立代码主审。

V02/V04～V06 历史复用的可核查输入示例：U7 `final-native/native-plan.json` 输入 `f83c0601` 加其 plan 内逐文件 SHA，计划 SHA `08dc79d9ed4029c5b989194edd0339d541b4a417babc1e5d5879f9481b95fa7c`，Nut/装配 Panda 为 MuJoCo、Pendulum 为 GeoPhys physics × MuJoCo RGB，单次预算 180 秒，原计划和 `native-results.json` 同目录。U7 `isaac-record-retry/plan.json` 同样以 `f83c0601` 和 plan 内 diff/source SHA 标识，plan SHA `76debafe4f3129e456998104b620f39d4bcf3c671e4ccc64993f23dedf7b2041`，Isaac CUDA Pendulum RGB，单次预算 240 秒，SDK 启动隐式步 unknown。S19 `native-retry/native-plan.json` 输入 `ebe87550` 加计划内 source SHA，plan SHA `b98a926870e1de1ec91a58d02d0b6e45fabdf939013ed1ff21c4ab1878468127`，单次预算 180 秒；该脚本的后续总预算偏差仍按 U7 原记录保留。以上三个相对路径从 `workspace/maintenance/v211_e05_e10_u7_20261113_001/`、同目录及 `workspace/maintenance/v211_e05_e10_s19_observer_admission_20261113_001/` 分别展开；原计划内 `runs`／runner 为精确参数，不执行这些历史计划。
