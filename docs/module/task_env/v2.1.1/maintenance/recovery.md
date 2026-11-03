# v2.1.1 恢复页

更新时间：2026-11-03。交接／压缩后先读本页、[确认收据](20261103_protocol_baseline_confirmation.md)、[路线](../planning/roadmap.md)、[执行表](../planning/execution-and-acceptance.md)及当前Goal。

- **当前阶段：**7阶段／22子阶段；G01/1a–1d均有attempt001独立交付与有界审阅，维护者已确认五协议为 `APPROVED_IMPLEMENTATION_BASELINE`。G02/2a `V211_G02_2a_attempt001` 已完成一次有界诊断交付，状态 `PASS（2a诊断交付）/REPORTED_PENDING_REVIEW`，尚未接受审阅。原始draft/closure-force提案见历史review，当前控制正文已更新为7＋2，不据旧提案实施。
- **下一动作：**Sol/维护者审阅[2a报告](../../../../../workspace/maintenance/v211_g02_2a_attempt001/report.md)及本地提交；保持2b为PLANNED。仅审阅后由维护者决定是否另发独立2b包，不修生产代码、不提前实现阶段3/4/5、不自动派发。
- **控制决定：**嵌套Robot／组件声明通道和Controller；Panda一类8维输入→7臂torque＋2手指joint force；保留tendon/mimic可实现域。JointEffort、BodyWrench独立，其他typed loads预留；显式贡献组合后唯一提交，禁止未协调覆盖／重复PD／重复施力。
- **其他已确认：**Controller用公共可替换model/state；同一public Env reset切backend/renderer，内部worker/环境可隔离；Core sampler seed=None延续，provider RNG不迁移；Timebase旧codec/hash保留；资产required未测不准入；用户不拼内部receipt/lease。
- **源码基线：**来源版本 `develop@fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`；本次协议修订输入 `11b1e6c5bf8011acdc39f10449e2eb25764da92d`。GeoPhys pin／checkout `67da1165149486d3ae3e779c13ce31af49e17d50`；当前HEAD每包重新核实。
- **工作树／分支：**`/home/lly/.codex/worktrees/v210-integration/Geochora` 的既有develop；不使用旧Program_Files/Geochora detached checkout，不恢复F/R或新建分支／worktree。
- **未解决实施项：**PickCube历史9/9 runtime-valid但0/9 task-success，R3为线索而非已证根因；free cube阻塞当前dynamic camera；reset camera phase未区分；Isaac缺task camera；remote batch重复worker帧；当前native batch只有GeoPhys。Core MuJoCo `<3.9` 与GeoPhys `>=3.15`依赖无交集，3a需冻结真实环境方案，当前不安装／升级依赖。
- **证据状态：**13实现targets NOT_STARTED，9最终cells NOT_RUN；本次2a仅有一条当前 MuJoCo CPU seed31 baseline：227 control transitions、runtime-valid、独立 HDF5 读回PASS、closePASS，但任务/Expert/solution失败于实测 TCP clearance gate。D0与qualification均NOT_ASSESSED；没有2b实现、implementation tests、GPU、Isaac、GeoPhys或三后端九格。完整输入、命令、原始hash与资源账见[2a输出目录](../../../../../workspace/maintenance/v211_g02_2a_attempt001/report.md)。
- **窗口与保护：**首次启动因MemAvailable 5.066 GiB低于6 GiB门限而未启动worker；复查内存回升后，成功运行启动时MemAvailable为8.718 GiB（运行期间最低8.491 GiB），seed31 worker约4秒结束。两个共享native锁随worker进程组退出而释放；忽略输出保存在本地。`MUJOCO_LOG.TXT` SHA-256 `dfb37ada202855d609f9e210cf79b287de78f2ded70e704ceeb544d17bf7ad4b` 与顶层handoff SHA-256 `18cc56c7f0ffbcb947db4bd8725279489171efbee8f08b28603b79c47f509d61` 前后不变。
- **保护与历史：**保留MUJOCO_LOG.TXT、顶层diagnostic handoff、ignored资产／raw证据、GeoPhys pin及旧refs；原始1a–1d报告／manifest与历史review保持。精确hash由工作包snapshot冻结。
- **范围提醒：**Flora、完整F07、RL/IL、agent_factory、R07扩展、新后端全接入及非刚体真实样例后续规划；不重开F05严格研究，不自动发布或Qualification。

实时attempt／包／审核入口：[编排索引](orchestration.json)。最近四次接收见[1a](reviews/20261103_1a_sol_review.md)、[1b](reviews/20261103_1b_sol_review.md)、[1c](reviews/20261103_1c_sol_review.md)、[1d](reviews/20261103_1d_sol_review.md)；本次确认不重写其中时点状态。
