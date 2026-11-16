# G03/3c attempt001完整安排（条件准备）

2026-11-06。当前3c PLANNED／count0，没有实施；维护者要求将3b003和本包一次转交Terra，按[连续安排](stage3-3b003-3c001-sequential-execution.md)条件启动。依赖3b全部required技术通过及提交／材料／释放冻结，准确input HEAD只能从其实际最终提交绑定，不预造未来SHA。Sol最后分别独立审阅，不授予Terra接收权。

## 实际现状与选定接口

当前SelectedReferenceEnv._prepare_reference_reset会重建session，但沿self.provider／backend和原binding，不实现跨route重选；reference_binding.prepare_selected_reset拒绝普通selected非空options，None随机流也未具备本目标语义。CPU／F06现有observation字段不同。故本包不是再跑reset矩阵，而要接通这些真实owner空档。

沿同一public `make_env('pick-cube-p16-reference-v1', config=...)`，新增显式 `execution.reset_profile='pickcube-state-only-switch-v1'`；仍用同一个SelectedReferenceEnv对象，在 `reset(options={'execution': target_config})` 内重建目标binding/source/session／worker/App。配置归一从目标provider默认值出发，不继承旧host/engine/USD manifest；task／R3／horizon和state-only batch1固定。缺省profile不影响既有observation、v1/v2执行身份或旧codec。

新profile在构建时固定现有F06风格superset：state.ee_pose[7]、joint_position[9]、hand_pose[7]（明示为ee兼容别名，并非hand-origin）、boundary_identity_sha256[32]及privileged cube_body_pose[1,7]。float32／uint8、Frame、named order和schema identity固定；9速度仍在公共typed state/info和记录保存。CPU从当前public measured state投影，不能填零或给metadata改标签冒充转换；旧默认obs不变。

声明边仅MuJoCo↔GeoPhys CPU、MuJoCo↔Isaac6.2 CUDA及same-route reset。真实链MJC→GP→MJC→Isaac→MJC覆盖两个A→B→A；不以拒绝所有跨route代实现，不宣称GP↔Isaac／其它任务／renderer/controller切换或其他SDK已验证。gravity_compensation False，通用树、effort、RGB和batch仍不在本包。

## 最小开发与生命周期

configuration/config扩展选项和归一；reference_env/reset与reference_binding装配候选plan并调用PickCube.selected_binding／原task builder，禁止影子Env或复制__dict__。现有lifecycle、session、transport、worker、App owner继续唯一管理各自effect与close。允许一个职责独立的reset plan数据模块，不另建Manager或第二Runtime。

prepare候选source、需求交集、固定obs兼容与候选样本；pure preflight拒绝保留旧session／state／Controller及随机流。开始destructive effect前commit Core sampler与代次，关闭旧资源并构建／reset／readback，新成功后才发布新obs。旧q、contact、Controller memory或provider RNG不迁移。首effect之后失败faulted，记录已释放／部分write/advance，不假回滚；只可明确reset重建或close恢复。

显式seed重置Core流，None／省略延续；优先复用np_random／现有task sampler，可用版本化episode task seed派生再调用确定性task采样，首个显式31保留原样本参数。provider seed纯派生并记录，不消费第二份Core流。候选副本准备、preflight拒绝不提交；effect后失败已消费如实保留。跨源比较task参数，不强求完整source-bound ResetSample hash相同。

刷新materialization、episode、source/request、config/topology代次、state boundary、action spec与sample clock。旧bound command／旧state作为新输入拒绝；owned旧obs/snapshot独立可读不被覆写，borrowed依lease失效。裸numpy动作没有来源身份，不能凭空检测其旧episode字节。用户不需手工hash或lease。

## 验证与证据

先生产reset消费链离线fixture，覆盖三provider终端、source／配置／generation／观测，局部注入preflight、destructive build/reset和partial advance故障；不向Core加实验分支。再稳定代码一次真实star链，5episode各5控制步、每段T5/T+1=6及同次H5/独立reader。每段按本段实测初始TCP保持，不宣称默认关闭下无重力误差或task成功。

第一段seed31，随后None延续；同一Env再显式31 reset和最小step，核对task参数重复。一个CPU live episode插入不支持execution的pure preflight拒绝，前后状态／资源／流保持且仍可step。其它故障通过真实生产lifecycle fixture验证，不为每种故障重启Isaac。owned返回值、stale输入、资源close两次、worker/App正常退出与lease顺序都有对应case。

每episode reset前按既有契约finish recording；允许原provider各自codec，以外部chain收据连接，固定public obs与schema在同run trace及对应H5状态核对，不混作单个H5。3c改动若影响3b能力只做受影响原门复核并保留3b原报告身份。

外部包9项C1-01…09全PASS才THREE_C_TECHNICAL_PASS，最后仍REPORTED_PENDING_SOL_REVIEW。输出workspace/maintenance/v211_g03_3c_attempt001及本版执行摘要、完整报告／results／commands／seed-switch-fault数值／manifest／释放收据；active窗口释放后一起交Sol。主动120–180分钟、墙时240分钟、验证90／native60分钟、owner物理advance4000，详细双锁和预算见总包。到时准确PARTIAL，不自动002或4a。
