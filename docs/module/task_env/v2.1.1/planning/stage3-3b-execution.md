# G03/3b首份实施包

2026-11-05，Sol准备；PREPARED_NOT_DISPATCHED。3a已按[独立复审](../maintenance/reviews/20261105_3a_diagnostic_attempt001_sol_review.md)接收，3b仍PLANNED／attempt0、active_packages为空。维护者要求开始下一步，本轮准备一个完整3b包，由维护者指定Terra／Luna手动转发；无自动派发、native、安装或新对话。

## 当前依据与修复顺序

沿当前configuration／provenance／transport、真实factory、三adapter和Recorder owner，先修按路线依赖判断及Isaac部署／版本身份，再补公开物性事实，最后做三条有界真实闭环与独立读回。使用同一codex/v211-stage3 checkout，不重开G02／前置维护／3a历史。

维护者本轮明确：GeoPhys仅在选择MuJoCo求解路线时消费对应MuJoCo依赖；原生GeoPhys solver不因Core MuJoCo版本而冲突。当前provenance无条件套全部GeoPhys依赖是待修准入范围。按实际host／engine／solver、source/model helper与worker消费链判断，不改GeoPhys pin或依赖清单、不为未选solver升级环境；显式需要MuJoCo的消费者仍准确检查。Isaac也区分Core host与SDK worker实际依赖，不把未选Taichi/PyVista路线强加到SDK；真正必需缺项继续拒绝。

## 具体owner与实现

- configuration／provenance：现有selection和metadata/preflight分期，消费级依赖，集中6.1/6.2版本／SDK来源；保留raw/build和实际worker解释器。
- examples/start与builtin_example_validation／transport：Core默认当前解释器、CLI/env/config归一、pip Python与官方python.sh、stdout结果framing、argv/cwd和异常回收；不执行旧Core或Kit内部python。
- source／representation、App owner、native_io、admission／drive／feedback、Recorder：同一请求真实版本贯通，保持旧codec/6.2历史身份及冻结F06相同closure；不复制资产、分叉Env或Controller。
- 三adapter及已有model/build metadata：具名质量／COM／完整惯量、axis/limit、transmission/mimic、单位/Frame和realized reset公开读回。只使用公开provider API，不穿透私有solver；required未测量不通过，约5%cube惯量差保留。

6.1／6.2范围按[兼容规划](isaac-deployment-compatibility.md)，5.1留后续。6.1本机未安装，必须完成适配和离线生产consumer，native单列NOT_RUN；真实App分发暂无显式launcher，离线launcher接线不冒称原生通过。

## 完整外部包与冻结

包名V211_G03_3b_attempt001，位于维护者交接工作区handoffs同名目录。prompt、acceptance-cases、numeric-oracles、environment-readiness、snapshot、离线guard与只读verify-input脚本和manifest共同冻结。准确输入HEAD见准备提交后的snapshot；不是直接回退到实现6b11123e。索引只记录外部路径和prompt摘要，避免提交／manifest自引用。

Sol只用标准库metadata探测5个已知环境，未导入SDK/native、未source解析。Core现有MuJoCo3.8.1／Taichi-forge0.6.3；Isaac pip环境6.2.0.0，含SDK自有NumPy2.3.1，缺部分Core host库。该raw事实不等于所选worker链缺依赖；由上面的真实消费修复确认，不重复整机盘点。F06 manifest摘要6cb07d216689d1e0b6f31ef127d9a511906be90c2acbecb9a30667cdebf113e2不变。

## 验收与预算

三条必达：MuJoCo CPU、GeoPhys原生CPU、Isaac6.2 PhysX CUDA:0。各以公开PickCube factory、seed31、原R3/observation、state-only batch1完成build/reset/10step/state/H5独立读回/close；dt0.002×5，控制增量0.10s，5hold+5个TCP世界Z+0.001m目标。量纲、source参照、容差与短程数值判据在执行前冻结的numeric-oracles.json，不按结果调宽、不要求任务成功或九格。Nut19／Position／leaf只补实际受影响路径，旧未变证据保留原身份引用。

预计主动150–210分钟，总墙时240分钟（含等待和交付）；验证75分钟，其中native45分钟，单组20分钟，累计2500物理substeps，单Isaac启动/settle200上限，进程树RSS16GiB，输出512MiB/单日志16MiB。GPU仅cuda:0，VRAM上限执行时该卡总量减512MiB并记录峰值；不复用旧6GiB启动门。一个writer/运行组，原双锁顺序获得、逆序释放，native/worker cwd在本包ignored目录；不清理他人进程。

开工/最终身份与实际消费来源核对，不重跑全矩阵或全库SHA。到时完整返包，required三路线/物性/readback缺项不得整体PASS。无安装下载、pin修改、3c、阶段4、render/capture、batch、push/merge/tag/Qualification。普通attempt上限3与第三次失败人工诊断规则继续有效，准备不计次数。
