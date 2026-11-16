# G03/3b attempt002完整安排

2026-11-05，维护者要求构建工作包并手动转发。状态PREPARED_NOT_DISPATCHED；3b仍REWORK_REQUIRED_3B、普通attempt_count=1，active_packages=[]。001原技术结果、FAIL、过程偏差及[Sol复审](../maintenance/reviews/20261105_3b_attempt001_sol_review.md)保留；3a接收不变，3c未启动。

## 首要目标与已定位owner

按[返工分析](stage3-3b-rework-analysis.md)和TaskEnv Skill→调试与恢复，先区分新接线回归、初始下沉／驱动瞬态、短窗oracle前提，定位后修实际3b缺陷。Sol已核实两CPU的FK和R3目标重构一致、下沉先于上移请求；不能直接判为三后端TCP符号错误。

同时闭合已明确缺项：provenance／transport／worker的launcher上下文；observations.selected_reference公开typed info→position_metadata reset/step→h5既有T+1 typed-state witness与reader；真实物性／Frame／reset和源约束。现有F05 witness是复用落点，F06尚未消费；最小扩展同一owner，保持旧Observation和F05数据语义。compiled/native-effective/authored/derived区分；USD cube各向同性惯量已有独立验算，不补资产主轴，不改MJCF约5%惯量差。

## 具体因果控制与分支安排

复用当前checkout、codex/v211-stage3与两个pins。外部包提供只供执行者运行的run-causal-controls.py及mujoco-causal-driver.py，Sol只做静态语法／逻辑审阅，native=0。

在任何tracked编辑前，执行者先在ignored ledger登记实际start／writer／普通002计时，再由helper取得原双锁。锁内临时git switch --detach到0192f2ec538582c3945acc2b9fcfca22589500ec，以真实旧Core身份运行MuJoCo hold/up；finally恢复当前主题分支／准确snapshot HEAD，再运行当前hold/up与hold-only。三组相同seed31、horizon32、实际reset/source／原R3参数、0.002×5；10步、5hold+5up0.001m，同样不开Recorder，外部JSONL保留状态。它们是因果控制，不是最终H5门。

此方案明确取代准备前分析中的未冻结只读源码快照设想：不新建branch/worktree或旧Core副本，避免源码路径与Git身份伪造；原分支和输入提交始终保留。禁止stash/reset/force覆盖；恢复失败精确返还，不在detached基线上实施。恢复完成后才将tracked编排count=2／writer登记，再在同一窗口修复。没有Sol自动checkout或执行。

诊断分叉参考q1e-8rad／qdot1e-7rad/s／TCP1e-8m／time1e-12s，只用于同引擎同输入定位，不是跨引擎产品等价门。若仍需区分瞬态，仅允许预冻结的100步hold＋10步控制与hold-only成对诊断，不自适应延长，不作为原门PASS。

## 验收与oracle责任

完整原N01–N10规则和容差逐字继承001，尤其原N08 5hold+5up、boundary5→10正向至少1e-6m不变。因果证据定位实现缺陷就最小修复并复测实际受影响路线；不先扫gain或更改Solution／资产。

如果匹配旧基线和独立对照证明判据前提不成立、没有可归属3b实现缺陷，完成同scope可独立修复并返回精确oracle-revision-proposal及ORACLE_REVIEW_REQUIRED／PARTIAL，保留原FAIL供Sol／维护者决定。不自行换门、加4a Controller/effort、标PASS或自动003。普通第二次的目标是收口，routine可修失败不是提前返包理由；真实外部oracle/public-API/pin决定才据实列阻塞。

最终受影响三路线仍public PickCube31、原R3、state-only batch1、reset/10步/H5独立reader/close；F06同USD closure。未受影响事实按原run身份复用，不重复证明已成功的App启动。Nut19/Position/leaf/codec只补具体受影响路径，禁止全矩阵／G02长成功重跑。

## 6.1安装与条件

只读已有Terra窗口确认idle和writer释放；维护者的人类消息提供6.1官方独立安装路径，并限定主线完成且明确有余时辅助核验App版本。Sol只读VERSION/python.sh/setup_python_env.sh，未运行SDK；raw VERSION=6.1.0-rc.26+release.49347.2d230af4.gl，实际launcher上下文依赖PYTHONPATH已从脚本确认。

准确私有路径与人类许可来源放外部snapshot/authorization-receipt，不发布为稳定API。主线所有required完成、材料基本齐且至少余20分钟才允许最多10分钟6.1 App版本／来源／close辅助核验，计入总预算；否则NOT_RUN。6.1离线共用实现不等它运行，本包不安装下载／直接调用Kit内部python。6.2 pip仍承担主线真实运行。

## 时间、资源与完整交付

预计主动120–180分钟，总墙时240分钟；前30分钟因果初判，210分钟后不启新设计。验证75分钟，其中native／原生编译45分钟，单组20分钟；累计4000物理substeps，含所有reset/startup/失败/重试/可选诊断与6.1，单Isaac启动/settle200。一个writer/运行组，RSS16GiB、GPU仅cuda:0且VRAM总量减512MiB、输出512MiB／日志16MiB。沿原SDK有限deadline等待close，未超时不因无日志提前杀worker。

两原锁Core→历史checkout取得、逆序释放；native/source-only及worker cwd在本包ignored目录，只清理自身资源。原生计数未知保留unknown和下限，不为补账本重跑。无新branch/worktree/subagent／消息／执行对话、render/capture、batch、4a、push/merge/tag/Qualification；子模块／依赖清单／SDK不改。

输出workspace/maintenance/v211_g03_3b_attempt002，完整报告／R01–R08及B/N映射／commands／causal-comparison／numeric-readback／H5独立reader／新manifest／本地提交和释放收据。后继由Sol独立复审，第三次前重评及第三次未接收人工诊断规则保持。

外部完整包V211_G03_3b_attempt002的prompt／8case／原10oracle／诊断脚本／snapshot／只读verifier／manifest共同冻结。准备提交后的准确HEAD由snapshot给出；准备不计attempt，不自动派发。
