# C5：集中复验与交付

输入 HEAD `730eae0025402dbeb5703b88ab74b199bfb3092c`；执行时另有本单元针对 close receipt 的两个 property 修复和诊断测试，冻结在[运行计划](../../../../../../workspace/maintenance/v211_c5_final_20261114_001/native-plan.json)的 tracked diff SHA 与 source SHA 中。H5 的 `source_revision` 是输入 HEAD，不能将其单独当作完整工作树身份。E00～E16 的有界接收及其例外不变。

## 复核与修复

独立只读主审检查 `7f9d1091..730eae00` 实际生产 diff、调用关系和 C1～C4 关键证据，发现 C3 两个 provider 的 `close_receipt` 丢失 `@property`：实际读取成 bound method，transport 编码拒绝。实施者恢复 MuJoCo／GeoPhys 的属性；独立复审确认修复，参数化测试覆盖 close 前拒绝、close 后值、transport 编码及嵌套副本隔离，独立运行 **2 passed**。这不是端到端 worker native 复跑。C3 的短程 probe 仅证明 close 返回，不单独证明此前 receipt 可读；原报告不能扩大为该证明。

当前正式受守卫 pure／fake 集 **263 passed**，覆盖发布、失败 reset、generation、资源冲突、唯一提交／推进、Solution observe、recording fault 和新增 close receipt 合同。C1／C2 的 Pendulum、TwoWheel、PickCube、Nut 正式调用者分别有 reset、非零 step、再 reset 和 close 的当前短程证据；split 和 physical switch 的受影响内部 caller 见 [C2](20261114_post_optimization_c2_shared_interval.md)。sequence 的两次 native 候选在类型准入即拒绝、零子步，其发布分支仅有 fake 证据，不称 native sequence 通过。未恢复旧产品入口来满足历史测试。

## 两条完整 Solution

两次独立 CPU 运行均由正式 `examples/recording/record_expert.py` 在共享锁、独立 scope 和冻结计划下串行执行；锁与 scope 均在退出后释放／为空，无自动重试。每条运行各一次构造与 reset、无采图、5 个显式子步／控制 interval；启动及 reset 的隐式推进为 unknown。监督收据、命令、caller JSON、关闭后的 H5 和 reader 输出均位于[本轮目录](../../../../../../workspace/maintenance/v211_c5_final_20261114_001/)。

| 路线 | runtime／任务 | 同次 Solution／close | 独立 H5 读回 |
| --- | --- | --- | --- |
| PickCube MuJoCo，seed 31，horizon 1000 | 退出 0；960 intervals、4800 显式子步；任务成功，最终抬高 0.1051895808 m | caller 报 `solution_done=true`、`solution_failed=false`、正常 close | 960 transitions／961 boundaries、clock 9.60 s、逐边界 predicate PASS；SHA `b25f1c3200be5898d2fd47a34e8382c88adf9848c7c2f1dbaa1c683ac8e2b8f0` |
| Nut MuJoCo，seed 19，horizon 6000 | 退出 0；2377 intervals、11885 显式子步；任务成功 | caller 报完整 planned route、Outcome 与 Solution 完成，严格 lifecycle completed，正常 close | 2377 transitions／2378 boundaries、clock 23.77 s、逐边界 predicate PASS；SHA `bb8acb2ee1732f531414568d2f7f4c7621e5fa82d08dab8aae177d4e18d6d1e4` |

各 H5 同次文件、seed／任务、source、controller／Solution identity、边界数量与 caller／监督收据关联；`stop_reason=pass` 和任务成功本身不证明 Solution 完成，完成和 close 引用同次 caller 事实。两条均为 state-only，无图像完成 claim；不声明 D0、重放或新资格。PickCube reader 首次调用缺 `PYTHONPATH` 导致 import 失败、未读文件；设置路径后只对同一关闭 H5 重读成功，未重跑物理。

C3 的 MuJoCo／GeoPhys mixed source 各 2 显式子步和 C4 的 Isaac 真实 task RGB reset→step→重复同边界采图→reset→close 复用各自新证据及其冻结源码／限制；C4 两次重复采图物理推进为零，H5 两帧有限且与同次返回帧哈希一致，Solution 未运行。其他旧路线按原来源身份复用，不称本 HEAD 全矩阵重跑。

## 成效和原账对照

以 `7f9d1091` 到本单元生产修复为口径、在本报告加入前：tracked 文件 1456→1464；生产 9 路径 `+131/-222/net -91`，诊断 12 路径 `+610/-8/net +602`，文档 5 路径 `+107/-1/net +106`；无示例代码差异。新增文件是诊断及各单元记录，不把文件拆分或测试代码算作精简。各单元的文件跨度、移动量和分项数据以 [C1](20261114_post_optimization_c1_publication.md)、[C2](20261114_post_optimization_c2_shared_interval.md)、[C3](20261114_post_optimization_c3_provider_values.md)、[C4](20261114_post_optimization_c4_task_rgb.md) 为准；本单元恢复两个被误删的属性装饰器，最终生产统计已计入。约 19 行任务身份与约 7 行 writer/resource 投影转移到已有 owner，不能算作删除。

四处发布收敛为一个 Env 方法；四处 selected interval 的 state／obs 挂接收敛至原 lifecycle owner；Solution 观察与 writer/resource 值投影共用实际生产路径。每项增加一次调用跳转，没有第二状态或推进 owner。C3 共同进度只收敛身份／计数；native clock、monitor、admission 各自保留。C4 退出常规采集的详细 SDK 调试输出，原 completion gate、Fabric／dispatcher witness 和 fail-closed 仍保留；未为拆分引入私有状态穿透。

回看原总账 ENV-01～05、CTRL-02／04／05、RUN-01～04、SRC-04、OBS-01、REC-01／02、REN-02～07、TEST-01／03、GOV-04、DOC-01／02：实际变更与验证分别映射至以上四份单元记录和本报告；既有 [60 项有界结案](20261114_e14_current_state_alignment_closeout.md)及历史来源不改写。四项保护输入 SHA 与 E14 基线相同，GeoPhys／Menagerie pins 未变；冻结 archive 未处置。历史测试、validator、native sequence、强制终止与原有 Qualification 限制继续有效。未清理其他目录／refs，未 merge、push、tag、发布或启动 G06。
