# G03/3a attempt002 revision 2：Sol独立复审

2026-11-05。决定：`ACCEPTED_BOUNDED_3A_CORE_RUNTIME_RECOVERY`。本轮核心恢复接收；3a整体为`PARTIAL_CORE_RUNTIME_RECOVERED`，已执行2次，3b／3c尚未开始。依据维护者最新runtime-first安排，不把旧20case重新全验作为本轮出口。

## 接收的实际结果

输入`81e257cbef6c3469ba23fadcfe481d93b114f4d1`，待审实现`42dfcda57757d6d14bd963f692f6bd9154a974f3`，同一`codex/v211-stage3`。Sol核对原包8成员、输出manifest的17个修改文件及26份原始产物、commit patch摘要；均吻合。两份保护untracked及两子模块gitlink／checkout保持原值，tracked clean。

已按AGENTS先用CodeGraph，索引漂移后读当前diff。源码消费链确认为：普通task source构造→既有ExecutionSourceReceiptV1捕获实际Panda引用→selected preflight→重建闭包核对→原MuJoCo Session从receipt消费importer XML及相同assets字节。canonical XML保持，未改资产物性、Solution、依赖或pins。这是现有Panda普通MJCF的有界修复，不声称任意MJCF／所有后端均已适配。

| 真实生产入口 | 运行交集 | 原始结果 |
| --- | --- | --- |
| make_env(pick-cube-p16-reference-v1, provider=mujoco) | seed31，MuJoCo3.8.1，CPU，state-only | 创建→reset→Solution.act/env.step/observe×10→close；control_step 0→10，time 0.00→0.10s |
| make_env(nut-assembly-outcome-reference-v1, provider=mujoco) | seed19，其余同上 | 相同闭环；control_step 0→10，time增量0.10s |

Sol直接核对`native_probe.py`及两份`*-native-state-final.log`：无materializer／Session替换，实际类型为`task_env.runtime.sessions.mujoco._MuJoCoSession`；诊断在逐步执行中断言关节位置／速度、位姿、观测和reward有限，检查时钟／控制步且未提前terminated/truncated，记录close与锁释放。配置回执仍为静态preflight结果、native_effective unknown；本次真实执行事实由原生日志给出，不把该字段自动改成所有能力已readback。

原始证据在Core ignored `workspace/maintenance/v211_g03_3a_attempt002/`：`native_probe.py`、`pick-native-state-final.log`、`nut-native-state-final.log`、`commands.json`、`results.json`和`output-manifest.json`。原始文件不改写；后继文档提交不重标这些运行的源码身份。

## 独立验证与缺口处置

Sol没有重跑native或历史大组，只在SDK导入guard下独立执行5个受影响检查，**5 passed，2.50s**：本轮两个缺失mesh／错误actuator和Frame测试、真实闭包assessment、错误JSON对象形状与进程回收，以及公开worker→info/metadata→Recorder/H5 metadata读回。后者仅替换原生终端，已经移除attempt001的closure／assessment绕过，因此可证明真实source接线与离线记录契约；它不构成worker物理或物理H5独立reader证据。

| 项 | 本次Sol结论 |
| --- | --- |
| R1普通reset回归 | CLOSED_BOUNDED：两条真实公开MuJoCo路线恢复，实际引用字节由原importer消费 |
| R2通用build oracle | OPEN：不能把三个通用函数名白名单理解为每项能力的准确检查；本轮未强制新建框架 |
| R3具名／嵌套／typed | PARTIAL：普通MJCF的joint/freejoint/body/site/actuator错误名已检查；更广的声明求交未闭合，未实现typed执行仍属阶段4 |
| R4错误回复遗留进程 | CLOSED_BOUNDED：已复现的非JSON对象回复转为TransportProtocolError并回收owned worker；不声称全协议安全审计完成 |

独立命令、日志及逐运行摘要在主工作区`reviews/V211_G03_3a_attempt002_sol_review/`。Terra的24项受影响离线结果予以引用；Sol不重复108项、8组未变codec、G02或前置维护验收。

执行者报告本窗口16:45:38–16:56:28（UTC+8），约10.8分钟，主动／等待未分开测量；工具累计约95分钟包括此前工作，不能等同本attempt墙时。8次成功的10控制步运行按固定5substeps、零settle推得约400原生步，未独立采集引擎私有步计数。峰值RSS未测、离线pytest无同等内存限制等报告局限保留，不为补账本重跑；未据此声称完整资源测量。Sol本轮native、physics、GPU、App均0，没有自动发消息或启动后续执行。

## 3a剩余范围与下一步

本次维护者要求的核心矛盾已经解决，后继不得再要求重做这两例或历史路线来证明同一事实。只在源代码再次影响该路径或出现新故障时针对性回归。

3a尚需收口两个实现问题：实际task/source/Controller声明的required集合完整进入assessment；required unknown能对应现有adapter中具体的映射／构建检查点。先复用已有检查，不要求另造oracle注册表、逐SDK API安全表或全对象边界矩阵。未实现的嵌套／typed请求只需准确表达未实现及拒绝required，不提前实施阶段4；哪些既有证据可覆盖、哪些确有缺口须逐项判断，不能把NOT_RUN一律扩成新测试任务。

GeoPhys／Isaac的真实构建、物性readback、完整三后端闭环属于3b，不将其尚未运行列为3a必须提前执行的阻塞。Isaac6.1／6.2兼容范围与5.1延期仍按[兼容规划](../../planning/isaac-deployment-compatibility.md)，不改当前证据边界。三后端环境选择／声明求交的离线接线仍属于3a本身。

当前只更新复审和剩余范围，**未准备或派发attempt003**。第三次前按既有工作流对上述剩余owner做有界根因／可行性重评，再冻结一个最小完整包；不重复已接收核心恢复，不自动进入3b或阶段4。G02与前置核心有限接收保持。
