# G04/4c attempt001：Controller reset 与迁移后 PickCube

状态：准备人工转发；4b 已有界接收。执行与接收分离：维护者手动转交单一实施会话，Sol 独立主审。依赖原 [4c 目标](../goals/04-control.md#4c)、[控制协议](../contracts/control-and-feedback.md)和 [4b 审查](../maintenance/reviews/20261106_4b_attempt002_sol_review.md)。外部包 snapshot 为实际执行输入及预算的权威，本文不改变原目标。

## 已知真实缺口及优先次序

1. 3c 是 provider reset 重建，不是同一 Env 的 Controller／input spec reset；`physical_candidate.py` 当前按一次构造选 controller，必须接入现有 `SelectedReferenceEnv`／binding／session owner。公开 reset 同一 Env 做 A→B→A，先对新 binding、能力、空间策略预检，再按实现的实际 reset state 初始化，发布 action spec 和 generation；episode 内禁止改变。
2. 以现有 R3 reference effort 和 joint reference effort 为代表规格；二者都可能为八维但语义不同。按规格身份及 generation 拒绝旧 action／贡献／载荷，不能只比 shape；外层调用者能实际取得新规格及生成值，旧 profile 兼容。固定空间 wrapper 在不可兼容语义（包括同 shape 不同含义）时有清晰策略与事前拒绝；同 batch 统一布局。不要要求非 4c 旧接口凭空携带新 token。
3. 每次切换按新 realized state 重建 q_ref，清积分、滤波、pending、force latch、反馈历史和命令序列；确保 reset 失败不留下可误用半切换状态。obs 架构／shape／dtype／单位／frame 稳定。覆盖旧输入及 episode 内切换等拒绝，观测先于副作用。
4. physical 控制路径当前拒绝 active Recorder。复用现有 Recorder/H5 owner 和独立 reader，记录每集规格身份、generation、控制／反馈和成功可核验信息；不以禁用记录或自写不相连日志代替原门。处理切换、T/T+1、关闭和失败，保留未测项为 unavailable。
5. `PickCubeReadinessSolution` 是 2c 的 absolute-pose 输入；让原任务 Solution 经现有公开 env 控制入口变成 R3 reference→typed joint effort→真实 session，完成迁移后的任务成功。4b 的固定 nominal mass 仅 source 初态邻域适用，不能删校验或假定覆盖完整抓取轨迹；可在已有 controller/model owner 内扩展真实所需的状态依赖模型、源绑定重力支持、夹爪控制／cadence 和合法限幅（例如复用现有 `PandaKinematics` 公共模型），避免重复 PD。必要修复纳入本次；不以原 position-only 兼容路径、ACK、篡改成功判据、替换任务、fake 或先前 2c 成功冒充。

## 原出口及证据

- 独立可复现的纯／fake 测试覆盖动作身份同 shape、A→B→A generation、realized state、存量状态清理、episode 内拒绝、fixed wrapper、同 batch、异常清理和 active Recorder；仅跑受影响测试，不重跑历史矩阵。
- 一条真实 MuJoCo 3.8.1 CPU 代表源、同一 Env 的 A→B→A，真实各阶段 reset/step；记录 identity、source、spec/generation、realized state、公开命令／ACK、旧输入拒绝及 obs。对原生不可直接读的内部状态以缺陷敏感 fake 补充，不凭 ACK 声称物理效果。至少在迁移方案的 active Recorder 下以独立 H5 reader 复核 episode 边界和元数据。
- 在同一个公开迁移接口，以 R3 方案运行 PickCube 既有任务／Solution，验证真实成功并独立读取记录。参考 2c seed 31、horizon 1000、physics 0.002s×5、原 source 约束和 lift ≥0.10m 门；使用既有任务成功逻辑及原重置/资产定义，记录 source 闭包和实际参数。原 2c 结果仅是基线，不能当作新成功；不擅自更改任务判据或挑选物理状态制造成功。必要调节合法 controller 参数，保留实际每次失败及更改原因。不以附加装配 Panda、三后端重新矩阵、独立测力、三 seed 九格作为 4c 新门。
- 若原条件下尝试失败，先按最早失败边界区分构造、规格、控制、接触/抓取、到达和任务谓词，按预算修复并只复跑受影响路径。允许运行必要的短预检和完整 episode，保留每次 log／代码身份和资源账本；预算不能替代完成条件。

## 完整执行窗口与保护

维护者转发后，由实施者单一 writer 在同一 branch/checkout 完成；开始前核验真实 HEAD、gitlink、三项保护输入、上一窗口 release 和双锁。详读现有 Geochora 编排、TaskEnv Skill、原目标/协议、2c 冻结、3c/4a/4b 主审及外部包。不得并发写或自动联系其他会话。允许相应 owner 内开发、修复、定向测试、文档和本地提交，允许真实 MuJoCo CPU source/build/reset/short step 和完整 PickCube episode（在外部包声明的冻结预算和双锁内）；Sol 不运行 native。原 4b 已接受证据按实际影响复用，若变更侵及已接受路径只补受影响的最小验证。

source/native 各 180 分钟；物理子步含构建预热上限 30000，单进程 600 秒，整窗墙时 600 分钟，CPU 8 线程、进程树 RSS 8 GiB、新输出 2 GiB。任何构造、解析、复位、运行逐项记账；严格避免无界搜索。仅 MuJoCo CPU，不启动 GeoPhys/Isaac/GPU，不变更 provider gitlink，不 push/merge/进入 5；不得修改三项保护输入。若权限、双锁、资源、budget 或真实外部依赖不足，保存证据并在最早失败边界报告，不将普通工程问题提前转成人工诊断。

最终输出 `workspace/maintenance/v211_g04_4c_attempt001/`：report、结果矩阵／逐案例 evidence、独立 reader 结果、原始运行记录、代码身份与构造输入、预算账本、失败及限制、release receipt、哈希 output manifest 和本地提交；`TECHNICAL_PASS_PENDING_SOL_REVIEW` 只有全部原出口有证据才可用。保持 writer／锁／子进程释放；报告真实 HEAD、pins、保护哈希。由维护者手动转交 Sol，Goal complete 不是接收。
