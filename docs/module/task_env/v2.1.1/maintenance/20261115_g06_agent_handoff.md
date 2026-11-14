# v2.1.1 G06 Agent handoff

交接日期：2026-11-15。维护者将本文件转交G06 agent使用；本轮已完成指定Markdown提交、开发总路线更新和本地develop首次快进。G06代码实施尚未开始，v2.1.1整体尚未完成。

## 1. 接手基线与必读入口

| 项目 | 交接事实 |
| --- | --- |
| checkout | `/home/lly/Program_Files/Geochora`；接手先核对实时HEAD、branch、dirty及运行窗口 |
| 最新生产代码 | `7f8796b43f34ee19ad6301357d2cce0ea7f11d53`；其后截至本交接的提交仅增改文档，生产字节未变 |
| G05最终复核 | `afb58944`，见[G05→G06复核](reviews/20261114_g05_pre_g06_readiness_7f8796b4.md)；未发现须重开G05的功能阻断项 |
| 三份既有Markdown | `0722341b`原样提交总账、2026-10-30 runtime交接及stage3重力提案；保留原历史时点，不自动执行旧prompt |
| 总路线与首次develop同步 | `23c6c86f2a0b7a65f36ec1c2247be2a95b1df8c2`；本地develop从`9d942d43`正常fast-forward至该提交，无冲突、无历史重写 |
| 本交接交付 | 包含本文件的后续文档提交也将同步到本地develop；最终以`git rev-parse develop codex/v211-stage5-diagnostic`核对，两者应相同。不要仅checkout上面的旧文档提交 |
| 远端与发布 | 已fetch/check `public/develop`；本轮只同步本地develop，未push，main／tags／release未变 |
| GeoPhys pin | `c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7` |
| Menagerie pin | `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` |

接手先读仓库`AGENTS.md`、现有TaskEnv Skill，再读[开发总路线](../planning/roadmap.md)、[G06 Goal](../goals/06-parallel.md)、[当前状态](current-state.md)及[能力矩阵](../capabilities/capability-matrix.json)的`current_support`。**[原始60项优化总账](../planning/post-5c-code-project-optimization-diagnostic-ledger.md)是后续开发的重要依据**；当前完成情况见[逐项结案表](reviews/20261114_e14_current_state_alignment_closeout.md)，不把原文历史“未完成”重新当成G06待办。

三份原保护Markdown现在已按维护者明确授权纳入Git，字节／SHA未改；`MUJOCO_LOG.TXT`仍为保护untracked输入。历史报告“四个untracked”的说法保留原时点。不得按目录名清除ignored证据、冻结archive、保留锁别名或本地输入。

## 2. 目前能力与开发状态

| 范围 | 已成立的能力 | 仍需保留的边界 |
| --- | --- | --- |
| G01～G05 | 各自范围有界接收；协议、真实provider执行、控制、reset重建、原生渲染和同步RGB有对应证据 | 设计接收不等于任意任务／资产／Controller／provider／renderer自由组合；G06／G07未完成 |
| 四个正式任务 | `pick-cube-p16-reference-v1`、`nut-assembly-outcome-reference-v1`、`pendulum-v1`、`two-wheel-balance-v1`通过正式`make_env`和共同配置／构建合同 | 每个task／Robot／Controller／source／provider交集按准入及实测判断；不能因同类注册成功外推能力 |
| 主体与控制 | 一体Panda、装配Panda、Pendulum、双轮车有共同声明／Assembly／Controller绑定及场景interval；装配Panda双Controller有受测资源归属证据 | 简单主体不伪造夹爪／末端；Position、joint effort、BodyWrench各保留物理语义；不宣称任意嵌套或任意多writer组合 |
| 物理路线 | MuJoCo CPU、GeoPhys CPU、Isaac 6.2 PhysX CUDA在受测任务／资产上有真实短程或完整运行 | 不等于全部路线都在同一最新HEAD重跑；重力、wrench、source与SDK限制按原证据保留 |
| 渲染 | 三条指定原生窗口／离屏路线；reset／step自动task RGB；GeoPhys CPU physics × MuJoCo renderer-only真实跨组合 | renderer创建时固定到close；动态图中切renderer未排期，颜色primaries未校准，其他组合须准入 |
| 相机 | world camera及observer/task分离；Isaac受测腕部frame mount；C4有reset→非零step→重复采图→二次reset→close | MuJoCo／GeoPhys移动挂载仍拒绝；GeoPhys task／observer共享framebuffer分辨率约束；重复render不能推进physics |
| 完整Solution | 原优化范围五条单seed路线以同次联合证据有界接收；C5另补PickCube／Nut两条MuJoCo完整成功及独立H5读回 | C5为state-only；Solution completion引用同次caller，不能只由H5 stop_reason推断；不是G07三provider×三seed矩阵、D0或新Qualification |
| 生命周期与记录 | 同一Env／Runtime协调构造、reset、step、fault、close；普通记录、历史codec及严格oracle分层 | SDK隐式startup/reset推进仍有unknown；close返回、receipt可编码、App关闭和整个SDK无日志异常是不同事实 |

最近直接验证：C5及G05复核的正式guarded集合为**263项pure/fake通过**。C5 MuJoCo PickCube seed31完成960 intervals／4800显式子步，Nut seed19完成2377 intervals／11885显式子步，均由同次caller报告任务成功、Solution完成及正常close，关闭H5独立读回成立。Isaac C4是独立的短程RGB证据；两帧H5与同次返回图像字节SHA一致，第二reset由同次result证明，不冒称三帧H5自含。

原N08／COM严格FAIL、维护者有界修订、R05c `NOT_REQUALIFIED`、integration旧Git管理元数据损失、历史累计净空间UNKNOWN、SDK关闭及证据身份限制均保留。它们不因此自动成为G06新前置门，也不得被新成功覆盖掉。

## 3. G05期间两次主要改造，不能回退

### 3.1 G05c诊断单元4：共同任务／主体构建路线

G05并非只增加renderer。5c人工诊断单元4把一体Panda、裸臂＋独立手爪装配Panda及简单主体接到共同的受控主体、嵌套Assembly、具名关节／Frame／Actuator、Controller绑定和场景命令机制；后续单元5／6补了provider路线及Controller能力匹配，单元7／8处理独立renderer状态投影，单元9综合有界接收。

因此当前生产链应按以下职责理解：

```text
正式任务配置／Task声明
  → Robot与source intent／Assembly声明
  → 共同构建请求及source lowering
  → Controller能力匹配、具名资源绑定
  → Env共同reset／interval／fault／close
  → Runtime session／provider adapter唯一物理提交与推进
  → 公开state／boundary／clock
  → Task评价与观测；renderer消费公开状态并完成RGB
```

不同provider、MJCF／USD和不同主体允许各自lowering；它们必须遵守同一交接与生命周期合同。单一Runtime合同不表示所有Env共享一个进程，也不表示强迫三家native实现继承同一个大基类。原单元4背景见[诊断路线](../planning/stage5-5c-diagnostic-refactor-roadmap.md#工作单元-4一体-panda-与多层装配-panda-的同一主体流程)，现行结论以最新代码和接收记录为准。

### 3.2 G05c验收后：按总账完成E00～E16优化

5c功能接收后，又按原总账完成正式入口／配置归并、Task／Robot／Controller／Env减责、source与adapter归位、状态与相机合同、Recorder／replay分层、caller迁移、诊断收口、完整Solution复验及批准的证据／项目整理。E00～E04和E05～E10分别接收，E11～E16项目于交付`86921c62`有界接收；原60项后续资料缺口已结案。

其后C1～C5继续减少重复发布、interval回调、provider进度值和Isaac详细诊断；没有第二生命周期／状态镜像／physics owner。C3曾误删MuJoCo／GeoPhys `close_receipt`的`@property`，C5独立复核发现后已修复并补行为检查。不能把C3早期probe仅仅close返回的成功当成receipt可读证明。完整内容见[C5交付](reviews/20261114_post_optimization_c5_final.md)。

G06必须继承上述改造成果：不恢复Position candidate、旧UID／builder／fixture产品分支，不为batch复制Task语义，不把探针和实验配方放回公共Env、Runtime或adapter。总账是持续的职责和代码质量依据；真实新缺陷按影响在既有owner修复，不用重跑已接收大阶段替代定位。

## 4. 当前batch基础与真正的缺口

**代码库有batch基础设施，但四个正式任务的G05统一路线尚未接入formal batch，G06没有被这些旧基础设施提前完成。**

| 层次／当前owner | 已有基础 | G06需要补齐／核实 |
| --- | --- | --- |
| 公共vector入口：[parallel.py](../../../../../task_env/vectorization/parallel.py) | `make_parallel_env`、`make_homogeneous_env`、registry、local／remote及SB3桥接 | `_require_parallel_registration`在资源创建前拒绝无formal batch adapter的正式任务；四UID目前均不支持，`num_env=1`也不豁免。需真实适配后再解除对应拒绝 |
| 构建：[vectorization/factory.py](../../../../../task_env/vectorization/factory.py) | `make_framework_parallel_spec`装配旧component TaskDefinition／action／observation与batch runtime | 对`uses_selected_public_config`仍显式拒绝，内部消费旧component构建形式。不能仅删guard或翻注册flag，应让正式配置、共同Task/Robot/Controller/source阶段实际进入batch构建 |
| 语义：[task_definition.py](../../../../../task_env/vectorization/task_definition.py)、[homogeneous.py](../../../../../task_env/vectorization/homogeneous.py) | `BatchTaskLifecycleAdapter`继承共同TaskLifecycleAdapter，已有masked reset、终止处理、seed与host/device合同；`HomogeneousVectorTaskEnv`做shape与terminal-slot协调 | 核对并接通四任务的正式TaskDefinition、episode／clock／RNG、Controller资源及typed publication；已有实现不等于已适配，不应另写一个batch任务生命周期 |
| physics：[runtime/factory.py](../../../../../task_env/runtime/factory.py) | 当前`make_batch_runtime`只接`merged_scene → SceneBatchRuntime`，复用GeoPhys公开场景构建；`static_template`已退休并拒绝 | 这是旧batch路径，不是统一selected RuntimeSession的三provider dispatcher。`backend='cuda'`不能据此推断Isaac／MuJoCo已支持；至少两个后端／模式和至少一条native batch须按G06冻结名单真实接通 |
| native batch与IPC | `SceneBatchRuntime`一次复制scene并以一个solver推进各slot；remote wrapper是一个子进程拥有一批 | 复用既有public capability并核对实际资产／接触／控制需求，优先查GeoPhys与Isaac。不能用N个串行scalar step、仅有一个remote worker或GPU device名字证明native batch |
| render与Recorder | 已有parallel presentation、tree／device plan和记录metadata；标量同步RGB有清楚身份 | 将每slot图像／state／episode／clock和终止obs／新首帧关联；窗口拼图不能替代Agent每env observation。继承owned／borrowed期限，不强制所有GPU状态CPU copy |
| 部分reset与backend切换 | 旧masked reset机制和标量reset重建可复用 | 未选slot的state／time／Controller／RNG／pending contributions／图像不变；整批切backend后旧view／command／frame失效，并核对异常／重复close／worker／共享资源回收 |

`static_template`、旧provider兼容类或历史Pendulum batch demo即使还可定位，也不能作为绕过当前准入的替代路线。旧SB3 caller的same-step autoreset／terminal_observation语义应按实际受影响合同保全；这不要求本轮额外完成RL训练资格。

## 5. G06实施顺序与最低出口

以[G06 Goal](../goals/06-parallel.md)为范围，逐大单元推进，不另造一张全历史矩阵：

1. **6a：批量契约与共同构建。** 冻结首批Task／Robot／Controller／source／provider／renderer和小批量数；确定env ID、batch轴、device、reset mask、每slot episode／Core seed流／provider派生seed、固定action／obs／图像布局及公开的一种autoreset语义。实际caller进入共同构建与提交，不仅交schema。
2. **6b：两个后端真实小批量。** 至少两条明确后端路线实际construct／reset／非零step／render／obs，至少一条native batch；测出slot间动作／状态／图像身份与隔离，记录实际进程及数据传输。不能静默减为单后端，不新增大规模性能或多GPU门。
3. **6c：部分reset及整批A→B→A。** 同配置mask reset按已完成step后的pre-reset边界对比未选slot。切backend时整个native batch重建，保持创建时固定renderer；不兼容组合提前拒绝，不在一个native batch中只替某个slot换backend。新episode、source/generation及借用buffer的失效规则可验证。

具体路线／种子／RAM／VRAM／App及显式子步／墙钟／输出预算、现行共享锁和失败清理应在当次执行包冻结。通常复用`workspace/locks/shared_native_execution.lock`及当前Harness监督，不能把旧run的锁释放或历史资源授权当作当前独占窗口；不得unlink锁绕过争用。

G06不承诺任意资产异构混批、每slot不同维Controller、全部autoreset模式、runtime renderer切换、D0或新Qualification。G07继续承担原集成、最终三provider×三seed及版本收口，不用本次单seed或短程替代。

## 6. 接手动作与开发约束

- 先核对`develop`和`codex/v211-stage5-diagnostic`及dirty；本地develop已获得本阶段成果，不能再从旧`9d942d43`或远端旧tip开工。G06阶段分支可按仓库流程规划为`codex/v211-stage6-parallel`并在6a～6c复用，接手者核实是否已有合适分支；本轮没有创建G06分支／worktree或启动其Goal。
- 先用CodeGraph定位（本仓库索引可能drift，读取被标明的磁盘当前源码），复用上表owner；无需为接手重建索引、恢复candidate或重新设计Runtime／Recorder／Controller／factory。
- 每个完整大单元包含实现、必要修复、按影响验证、文件／生产代码／迁移／诊断／文档分项度量、压缩记录及本地提交；单元末回看原总账对应原则。旧测试布局与文件总量不定义新架构，新增抽象必须有真实caller和职责收益。
- 本版诊断代码放`task_env/diagnostics/tasks/v2.1.1/`；经公开API、正常组合或有范围的测试注入工作。Core不得反向import诊断、读provider私有solver/renderer状态，Task不得启动SDK／App。
- 可先运行既有纯入口：`/home/lly/miniconda3/envs/geochora/bin/python -B task_env/diagnostics/tasks/v2.1.1/run_pure_checks.py`。该入口有SDK／资产guard，不能换成混合目录整跑后声称纯检查；native、真实source、offline H5及完整Solution分别报告。
- 正式Solution继续由caller驱动`act → env.step → observe`；任务成功、Solution completion、runtime validity、记录读回、render completion和close分别证明，不更改成功门槛、物理参数或旧记录以追求PASS。
- 不重开已接收G05或E00～E16，不顺手清理更多workspace／branch／worktree，不更改pins、main、tags或发布。后续维护者指令可启动G06；历史“尚未开始”是本交接时点，不是新增永久审批门。

维护者可直接转交本文件作为G06上下文；后续实施应在读取实际源码后完善一个连贯的6a～6c执行安排，避免每查到一处小问题就重读全账、只改一处再停下。
