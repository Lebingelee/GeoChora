# G03/3b attempt003前重评与最后窗口

2026-11-06，Sol。基于[002主审](../maintenance/reviews/20261106_3b_attempt002_sol_review.md)，维护者要求一次向Terra转交3b003及其后3c001。当前3b仍REWORK_REQUIRED_3B／count2，3c PLANNED／count0，无活动包；准备不计attempt。外部完整包入口为维护者交接工作区 `handoffs/V211_G03_3b003_3c001_bundle/`，精确HEAD由其snapshot在本次准备提交后冻结。

## 已明确事实与三种剩余风险

旧／新匹配MuJoCo轨迹最大差0，下沉在3b前已存在；最终Panda补偿开启时PickCube31／Nut19保持后正向上移约0.407／0.417 mm。因果定位和该有界行为已接收，不再跑旧HEAD／gain或seed扫描。最终补偿同次记录与长时保持、GeoPhys有效物性读回及部分required量仍待完成。

| 类型／假设 | 当前依据 | 最小实施及验证 |
| --- | --- | --- |
| 现有接线／记录／拒绝缺项 | launcher/F06已修；最终补偿没有同次最终H5，required API/schema/DOF反例仍不足 | 原Env／session／Recorder消费链补最小缺项；最终Nut350保持和两任务10步记录／reader |
| 上游公共模型能力缺失 | GeoPhys现有facts读compiled input，RuntimeBoundary读动态state，不能证明solver-effective物性 | 现有RigidSolver host IO增加正式owned model getter，Core boundary委托，原session／worker消费；独立provider本地提交和Core pin更新 |
| oracle瞬态前提不成立 | default-off up相对hold+0.407 mm但绝对仍下降；补偿开启绝对上移 | 事前冻结N08-v2，将三路线配对方向效应与MuJoCo补偿保持／绝对方向分开；旧N08及FAIL原样保留 |

## 选择的开发范围

GeoPhys当前pin67da1165、分支codex/v2.1-integration且干净，RigidSolver已在runtime/allocation.py、articulation/field_allocation.py和equality/field_allocation.py拥有实际mass／COM／inertia／轴／限幅／约束存储；host_io.py有同类read_*风格。允许仅为公共有效模型快照增加getter／owned值协议及对应规范测试、API/docs，保留provider祖先，在现有provider分支提交后更新Core gitlink。Core只经GeoPhysRuntimeBoundary委托与sessions/geophys消费，不穿透private solver。Menagerie／依赖／solver数值不改，不新建分支／worktree。

正式快照返回实际storage复制值及frame／COM reference／单位／有效count／generation，按原N02–N05比较源绑定动态body、joint、actuator和源声明约束。来源compiled与native-effective保留两种事实；required缺失阻塞，不默认零或N/A。其它provider继续现有公开model/tensor getter。分类为FIX_EXISTING／EXTEND_EXISTING／COMPOSE_EXISTING，不新增平行Runtime、Env、Controller或Recorder。

## 官方资料与可比实现

- [MuJoCo mjModel官方字段](https://mujoco.readthedocs.io/en/stable/APIreference/APItypes.html#mjmodel)：质量、body-local COM与principal inertia/rotation分列。沿当前MuJoCo adapter，不接入新模型库。stable页可能变化，实际使用本机3.8.1及当前消费者核对；[上游许可](https://github.com/google-deepmind/mujoco/blob/main/LICENSE)为Apache-2.0，本包不复制源码。
- [Isaac6.1 experimental prims](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/py/source/extensions/isaacsim.core.experimental.prims/docs/index.html)和[6.2 public prims](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/py/source/deprecated/isaacsim.core.prims/config/python_api.html)：复用当前experimental/tensor真实consumer。后者含deprecated路线，不把其拼写盲搬至现有getter，实际SDK仍须验证。无新增依赖或许可流程。
- [Gymnasium reset合同](https://gymnasium.farama.org/api/env/#gymnasium.Env.reset)、[官方checker](https://github.com/Farama-Foundation/Gymnasium/blob/main/gymnasium/utils/env_checker.py)与[上游多次reset确定性盲点](https://github.com/Farama-Foundation/Gymnasium/issues/1084)：3c复用现有Gym随机流／空间和多次seed/None序列检查；不以第一次成功认定完整语义。

现有GeoPhys host IO和Core boundary就是直接可复用实现。未找到无需适配即可证明当前solver存储的新库，MuJoCo数据布局或Newton/MJX跨库转换也不能替代此读回，故不引入额外物理库、solver服务或采样框架。外部资料不是本机qualification；细化引用／版本适配／不采用项随外包research收据冻结。

## 事前案例修订与不变门

原N01–N07、N09–N10容差、source合法性与required覆盖不变；原N08及其三路线FAIL不重标。新N08-v2事前随完整包冻结：三路线各5hold+5up对10hold，以相同reset/时序与前5步轨迹可比为前提，实测boundary10相对上移至少原1µm分辨率并大于已测前缀不一致／记录分辨率的10倍。两绝对位移仍分别报告；此门仅证明方向效应。

保持性能独立要求：最终Nut19开启补偿保持350步／3.5s，全程TCP高度偏差≤10µm、首子步各臂支撑力矩与实际执行器广义输出差≤1e-4 N·m、无目标／力限幅；最终PickCube31和Nut19开启补偿各10步还须过原绝对上移／位移上界。每组同次H5与独立reader。有限旋转／旧长时实验不代最终验收。

该修订由Sol在执行前明确，维护者转交此完整包后按所列案例实施；不是让Terra根据结果更换门，也不以相对响应宣称默认关闭的保持精度。仍有required缺项时不能整体PASS。新技术出口明确为THREE_B_TECHNICAL_PASS_REVISED_N08_V2，原FAIL另列。

## 可行性、顺序与停止

当前原始SDK／资产已具备，缺的是已明确owner的小公共接口和最终证据，已允许必要provider提交／pin。前45分钟接通getter到Core并确定required字段来源；然后修记录／拒绝，稳定源码后跑三路线×两模式10步及最终Panda保持／方向记录。主动预计120–180分钟、硬墙时240分钟；验证90分钟／native-source60分钟，owner发起物理子步6000，树RSS16GiB、输出512MiB，详见总包预算。不要再次把最后窗口用在历史全矩阵／208输出hash或开放式根因搜索。

这条路线具备收口的合理可行性，不能承诺PASS。第三次required未通过就完整返包并人工诊断，不普通004／改名续作／启动3c。通用装配树补偿不追加为3b阻塞；3c也不能替前包补required。连续技术通过后的具体调度例外见[双包顺序](stage3-3b003-3c001-sequential-execution.md)。
