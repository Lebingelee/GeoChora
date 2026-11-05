# G03/3b attempt001：Sol独立复审与TCP返工分析

2026-11-05。决定 **REWORK_REQUIRED_3B**；返包技术结果THREE_B_TECHNICAL_PARTIAL保留，3b不接收、不进入3c。普通attempt_count=1，不启动attempt002。3a接收及其普通／诊断历史不变。

输入0192f2ec538582c3945acc2b9fcfca22589500ec，源码d5731655，返包2c565f5336d3cb1ff700f98db2b238f01ad86ab9；codex/v211-stage3。Sol核对原包10成员及239输出摘要（4,866,498 bytes），审查45文件diff及实际caller、三个最终run/reader；两保护untracked和两子模块pin保持。跟踪原件见[执行摘要](20261105_3b_attempt001_execution.md)，不重写原始结果。

## 决定及可保留成果

三条public PickCube31路线都完成reset、10步、记录和独立读回，6.2 pip App确实启动并正常关闭。GeoPhys原生rigid路线不再被未选MuJoCo solver依赖阻断；SDK worker与Core host职责分开，原source/request/native metadata贯通已有进展。它们是有效有界成果，整体数值门未过不使这些事实归零。

三路线原N08仍FAIL；required物性／初始化／约束与记录覆盖尚未闭合，另有本次独立复现的App launcher缺口。6.1已由维护者告知另装，但本轮native未运行；安装状态与NOT_RUN分列，不能继续写“本机未安装”。其辅助native授权以当前必需目标完成且明确有余时为前提。真实App分发native NOT_RUN本来就不是本包额外阻塞；SDK fixture不能代替实际运行。

## TCP：已定位到哪一层

按[TaskEnv Skill](../../../../../../.agents/skills/geochora-task-env/SKILL.md)及[调试与恢复](../../../v2.1.0/guides/troubleshooting.md)，先比较输入／source／state／Controller／驱动，再讨论physics。Sol只读取现有H5／日志并在阻断SDK导入的独立进程中做纯Core source组合、FK和控制算术；没有GeoPhys Scene／OpenUSD解析、引擎编译、初始化或物理推进。

| 路线 | 前5步hold的Z变化 | 后5步上移目标的Z变化 | 原N08 |
| --- | --- | --- | --- |
| MuJoCo CPU | -2.400646 mm | -1.229934 mm | FAIL |
| GeoPhys CPU | -2.400517 mm | -1.230121 mm | FAIL |
| Isaac6.2 CUDA | -2.553889 mm | -1.290584 mm | FAIL |

下沉在上移目标发出前已开始。MuJoCo boundary5的Z速度由同源Jacobian乘记录qdot得到约-0.04607m/s，boundary10仍约-0.01378m/s；这支持“正在衰减的初始下沉”假设，不单凭该趋势宣判重力补偿根因。

独立检查得到：

- MuJoCo记录q经原PandaKinematics得到的TCP与记录位姿最大差7.11e-16m；GeoPhys最大差1.23e-7m。两者目前没有显示关节到TCP的坐标映射改反。该结论不外推Isaac全部Frame／速度映射。
- 使用原R3 arm helper、同一source和逐边界记录输入，独立重构MuJoCo／GeoPhys全部10个七关节目标，与记录值最大差均为0。目标FK确实向上，例如MuJoCo transition6目标Z=0.567407355m，当时实际Z=0.563701783m；transition10目标Z=0.568069762m。
- 从阶段3接手9d942d43到当前返包，canonical Controller／kinematics／R3 profile、PickCube config和Solution语义文件均无diff；3b对三个非canonical Controller仅换Gym import。新source/worker/admission接线仍需具体路径对照，不能仅凭上述未变断言完全无回归。
- 尚无“同一10步hold/up输入在修改前已通过”的匹配native对照。旧Solution成功轨迹和3a短程动作不同，不能拿它们直接证明新probe发生代码回归。

因此已确认最早可观测偏离在初始hold段的实际运动；请求、目标方向和两条CPU状态FK接线的证据优先排除了简单符号／坐标翻转。待区分：既有驱动/重力瞬态、新接线引入的运行条件变化、短窗判据／采样约定。不能直接归因为“3b把三后端TCP都改坏”。

N08由Sol在准备包中冻结；50ms hold后，以50ms内绝对位移判定1mm命令的正向响应，缺少同输入基线校准，归因能力不足。承认这个设计前提未验证，不等于删除门或将本次FAIL改PASS。先做matched control，再决定修代码，或基于独立依据单独提出oracle修订；不得根据当前结果加大动作／延长窗口／调gain凑过原门。

## 已复现的其他问题与缺口

1. **App launcher上下文丢失（P1）。** provenance.probe_interpreter_environment和transport.start_selected_worker使用-I -S。Sol以临时python.sh仅经PYTHONPATH提供一个无SDK代码的isaacsim包：普通launcher路径可发现，生产probe返回origin=None。framing、空格路径均正常，问题是运行上下文丢失。这证明此部署形态的Core缺口，不证明新6.1实际SDK已经失败。应在原provenance／bootstrap owner保留或显式重建所选SDK所需路径，并继续核对当前Core/GeoPhys/SDK来源，不复制launcher服务或删除全部检查。
2. **Isaac qdot未入同run H5（P1）。** 最终H5有11×9 joint_position、ee/hand pose，缺joint_velocity。现有reader对已有数值集检查有限性，无法证明缺失的required量；空集合all(...)也不能证明覆盖。沿已有state→Recorder T+1路径保存真实速度／单位／Frame并要求完整具名集合，不用FD速度、target或Ack代测量，不为此偷偷改变已冻结Observation结构。
3. **物性证据需要补齐及缩减伪缺口。** GeoPhys目前是公开compiled模型事实，不能改称solver-effective读回；先核对现有公开getter／构建绑定，确有公共API缺口才明确owner，不访问私有solver。源约束、actuator/axis/Frame、realized reset、支撑等仍须逐量列已测／缺测。
4. **cube惯量不需要补写主轴。** USD cube声明diag=(3.333333370392211e-5)I；对任何旋转R，RIRᵀ=I。Sol据原N04容差独立比较既有runtime tensor，完整矩阵误差为0。这一子项可以补证，不应因principalAxes未显式authored而说无法比较，也不需改资产或降低容差。COM未authored仍单列：不能把native默认值冒充source声明，应核对冻结几何及schema规则能否形成独立oracle。OpenUSD区分显式属性与计算语义，参考[MassAPI](https://openusd.org/release/api/class_usd_physics_mass_a_p_i.html)及[physics schema](https://openusd.org/dev/api/usd_physics_page_front.html)。这不是整个N04或3b接收。

B02优先级／显式冲突和B06 required API/schema/DOF只补实际生产consumer的未证断言；不重开坏输入组合矩阵。B04/B05不以真实6.1未跑作为自动FAIL，但共同6.1身份必须在真实生产consumer的离线终端fixture中贯通，单个version helper不能替代。

## 过程、计量与独立检查

窗口记录20:52:28至22:04:28（UTC+8），约72分钟，并非240分钟耗尽。83条已记命令中native/source累计754.428秒，offline104.412秒，reader4.601秒；主动与等待未单独计量。至少745物理substeps，失败启动的准确总数unknown；不把unknown填0，也不为补计量重跑。已采样RSS约6.29GB、全卡GPU约2.74GB，进程VRAM未知，保留原计量口径。

四次source-only未持双锁／cwd在Core根的过程偏差保留，最终模型组已持锁在ignored目录重跑；不能倒改早期合规性。04–07慢关闭被提前杀掉的失败保留，最终正常关闭也保留。保护字节未变，当前writer／自身进程／双锁已有释放回执；Sol不额外扫描整机或干扰其他进程。

Sol独立guard检查12 passed（0.84s）；另完成H5/FK/R3重构、launcher路径丢失fixture和各向同性惯量验算，均无引擎。第一次pytest调用漏PYTHONPATH仅收集失败，已用明确当前来源修正，未冒充通过。原33 passed可引用，不相加为native覆盖。

外部审核材料位于维护者交接工作区workspace/reviews/V211_G03_3b_attempt001_sol_review，含identity-output-audit.json、offline-tcp-forensics.json、controller-source-diff.json、app-launcher-offline-reproduction.json、isotropic-inertia-offline-check.json和independent-offline-tests.log。原返包目录不改写。

## 返工安排

见[聚焦返工分析](../../planning/stage3-3b-rework-analysis.md)。下一候选仍为普通3b attempt002，当前只是分析，不是已冻结／派发包。先最小MuJoCo匹配对照分离TCP原因，再修实际owner，之后只复核受影响路线及尚缺required项。3c保持依赖阻塞，6.1辅助验证不抢主线。普通第三次前重评、第三次未接收须维护者主导人工诊断的规则不变。
