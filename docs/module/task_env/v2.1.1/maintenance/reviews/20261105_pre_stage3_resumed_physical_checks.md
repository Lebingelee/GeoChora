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
