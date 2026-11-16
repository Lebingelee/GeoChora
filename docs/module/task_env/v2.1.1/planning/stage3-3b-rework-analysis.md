# 3b返工分析：TCP定位已闭合，003前收敛剩余出口

2026-11-06当前决定见[002独立复审](../maintenance/reviews/20261106_3b_attempt002_sol_review.md)。普通count=2，尚无003包。配对旧／新MuJoCo轨迹无差异；维护者诊断并授权的有界重力补偿在最终PickCube31／Nut19短程消除初始下沉，后5步分别上移约0.407／0.417 mm。此机制及已测修复有界接收，不再将“TCP根因不明”或“3b新回归”作为返工任务。

003前先明确：GeoPhys公共solver-effective物性快照的provider／Core边界及可能pin依赖；补最终补偿版本的同次H5与稳态；按原逐量清单补真实reset／约束等required缺项；最小required API/schema/DOF反例；独立冻结将方向响应与保持／精度分开的新案例。原N08 FAIL和全部历史保留；相对hold正响应不能单独替代保持性能。通用装配树选择是已确认设计方向，尚未实现，交4a合同与贡献组合范围评估，不新增为3b出口，不自动移出本版。

先形成可实施的最后普通窗口，再由维护者手动派发；不重复旧HEAD因果控制、历史全矩阵或完整任务，不自动003／3c。下文保留001后、002前的分析时点。

2026-11-05，Sol分析，非执行包。[独立复审](../maintenance/reviews/20261105_3b_attempt001_sol_review.md)决定REWORK_REQUIRED_3B；attempt_count=1、无活动writer，不自动attempt002或3c。原FAIL、全部native成果和过程偏差保留。

## 002准备后的执行入口

维护者随后要求构建002完整包，现已[准备未派发](stage3-3b-attempt002.md)，count仍1。以下是准备前分析；基线控制的准确实施方式由002包冻结为同checkout、双锁内临时detached旧输入后恢复主题分支，不采用第二只读Core副本，不新增branch/worktree。原N08保持，oracle修订只能交证据proposal待审。本分析不追加进活动执行窗口。

## 先诊断首要矛盾

当前证据：三路线先hold下沉约2.4–2.55mm，再在上移段继续下沉约1.23–1.29mm；两CPU source FK与实测TCP一致，R3目标逐项重构差0且方向向上。不能据此认定改代码造成TCP新偏移，也不能将三后端同方向失败拆成三项solver根因。

使用TaskEnv Skill→调试与恢复的known-good／最早失败边界／可区分假设流程。至少保留以下三个假设，先在MuJoCo CPU最小对照，避免把大量三后端重跑放在定位之前。

| 假设 | 最小区分证据 | 决策 |
| --- | --- | --- |
| H1：3b共同接线造成回归 | 同一seed31、实际ResetSample/source、原R3参数、dt0.002×5与完全相同10步动作，对比已接收输入0192f2ec和当前实现；先利用源码/离线值等价，只有缺匹配native证据才补一个旧基线CPU对照 | 旧基线通过、新版本失败或首个中间值分叉，才沿该diff修复；不得用动作不同的旧Solution成功作对照 |
| H2：既有初始下沉／驱动瞬态压过短时命令 | 当前同一reset上分别hold-only、冻结hold/up；逐边界比较q/qdot、TCP、target/applied和source-bound驱动参数，必要时用正常API做一个独立的有界稳定后控制实验 | 若基线同样下沉但up相对hold有正效应，原N08仍FAIL，转而定位驱动／瞬态与判据前提；不能反称命令已反向 |
| H3：oracle／采样或动作语义不合适 | 核对boundary5→10、action6开始、世界Frame、规范化开口、同一TCP、R3实际feedforward/feedback/deadband/限速消费；用既有H5和D0目标重构优先排除 | 不能只因profile含2mm deadband就断言1mm命令被忽略：当前目标已经变化。明确时序／物理前提后才提有依据的独立oracle修订 |

上述是因果对照，不另设一个降低后的3b通过门。需native的部分仅在下一完整授权包实施；旧基线若必须补测，其只读源码快照、准确来源、pin、同输入和回收安排随包单独冻结，不覆盖当前checkout、不执行历史ProgramFiles旧Core、不新增分支/worktree。Sol本轮不运行native。

优先使用外部驱动、正常state/Recorder和必要Controller包装，保持一次compute和唯一physics推进。先不扫gain／seed／near-singularity，不改变任务评价、Solution或资产。若修复属于4a新力控制目标，明确依赖／提前最小修复范围，不能偷塞完整4a。

## 其余修复按owner合并

1. provenance／transport/bootstrap：修复-I/-S丢失launcher SDK路径上下文，保留准确来源核对；用一条生产probe+worker consumer正例和一个实际required缺项反例，不泛化SDK巡检。新增6.1真实安装只按维护者条件使用；缺native不是离线实现验收失败理由。
2. source／provider facts：保留已测的12个MJCF惯性体、9关节和约束原证据；补实际缺项与构建绑定，不将compiled source冒充solver测量。USD cube各向同性惯量可由既有数据闭合，不改资产；COM应核对几何及schema派生依据，保留authored/derived/runtime三种来源。
3. state／Recorder／reader：保存T+1真实qdot及语义，明确具名覆盖；保留Observation固定契约，修Frame标签若与实际TCP不符，禁止用目标确认或差分速度代测量。
4. 最后运行受影响的public闭环和同run reader；代码未触及的事实按实际source/调用链复用。配置优先级、缺required API/schema/DOF及6.1真实版本身份只补生产链未证断言；TaskEnv Skill中“3b未开始”的陈述随实际能力文档一并更新。

## 验证安排与时间预估

先离线定位与最小CPU因果对照，再作所需修复，最后三条受影响路线的一次稳定源码10步/reader收口。不重跑九格、G02成功长轨迹、全部SDK配对、旧SHA全量审计或未变codec组；Isaac真实App启动已被证明，不为重复证明启动而跑。修到其state/record/launcher链时补对应闭环即可。

后继窗口主动约120–180分钟、总墙时建议240分钟，待完整包按根因和实际公共API缺口冻结；这是分析估计，不是延长已释放001或启动新权限。前30分钟应给出明确首个分叉或已排除假设，不能再以宽核查取代定位。不能因001约72分钟提前结束而续接其writer。当前attempt仍1，完整返工包后由维护者手动转交，Sol报告后独立复审。
