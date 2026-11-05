# G03：复杂后端路由、翻译与 reset 重建

规划标识：`V211_G03_BACKENDS`。3 个子阶段，默认在阶段 2 后推进。依据[physics 协议](../contracts/physics-provider.md)、[统一表示](../contracts/unified-task-representation.md)和[生命周期](../contracts/lifecycle-and-data.md)，扩展现有 RuntimeSession／adapter。

## Owner 与边界

涉及配置解析／make_env、selected lifecycle、RuntimeSession admission、MuJoCo／GeoPhys sessions、Isaac native IO 与记录配置。三条必达为 MuJoCo CPU、GeoPhys CPU、Isaac Sim＋PhysX CUDA 的冻结任务／资产交集。SAPIEN／Genesis／Newton 有能力表达位置，不在此自动实施全路线。

<a id="3a"></a>
## 3a：执行路由、配置与能力交集

2026-11-05诊断001／6b11123e经[Sol独立复审](../maintenance/reviews/20261105_3a_diagnostic_attempt001_sol_review.md)接收为 **ACCEPTED_3A_ROUTING_ADMISSION**。普通attempt3次及诊断1次分别保留，原003 PARTIAL不改写。F06前置依赖准确拒绝、真实Position/leaf声明与构建检查及同请求H5回执已贯通；普通PickCube31／Nut19 MuJoCo CPU回归通过。3a接收不表示真实Isaac/GeoPhys物理或3b通过；3b其后已执行，当前结果见下节。

- **输入／依赖：**1c、1d、2c。首批 route 和协议已冻结。
- **工作：**将宿主、引擎、solver／coupler、设备、renderer 和 batch 选择接入单一配置解析；能力求交任务／资产／嵌套Robot通道／Controller／typed物理命令／render 要求，替换必要的阶段特判但保留真实限制。
- **检查：**默认优先级、旧配置兼容、未知字段／层级冲突、依赖缺失、未实现、未验证及不支持的拒绝；静态与原生后才能知道的检查分层。
- **交付／出口：**实际生效配置和拒绝原因可查询／记录；没有静默 fallback 或用户配置扩权，编译身份保持可追溯。明确Core/GeoPhys的MuJoCo依赖冲突处理；可内部隔离worker／环境，但用户只配置执行方案。区分task控制/观测cadence与native dt；旧Timebase codec/hash不变，如需不同native dt则冻结版本化映射。

<a id="3b"></a>
## 3b：首批三后端的场景翻译和公开反馈

2026-11-05：[attempt001执行摘要](../maintenance/reviews/20261105_3b_attempt001_execution.md)已返包，技术结果 `THREE_B_TECHNICAL_PARTIAL`，等待Sol独立复审。三路线10步与同次读回已执行，但冻结N08短窗方向门均FAIL；其他required物性与读回项目部分未完成。GeoPhys原生solver的准入不再因未选MuJoCo solver而拒绝，6.2 pip路线已实测、6.1仍NOT_RUN。

- **输入／依赖：**3a；真实资产与 source、既有原生适配例外、1a 数值检查范围。新增反馈按[兼容规划](../planning/isaac-deployment-compatibility.md)在完整3b包中先实现6.1／6.2共同路线、SDK部署与真实版本身份；5.1延期。6.1尚未执行运行层验证，保留NOT_RUN，不追溯改动3a attempt001门。
- **工作：**在各 adapter 内消费统一模型，公开 native mapping、realized reset、单位／坐标转换、状态和时间；使用各自公开 API，报告无法表达或未测量项。按源约束编译具名通道和嵌套语义映射，不提前宣称阶段4命令已实现。
- **检查：**三路线从 make_env 真实构建→reset→施控／step→state→记录／读回→close；检查实体／关节、质量／惯性及声明的约束／传动与初始化。源码／设备身份和错误关闭可核实。资产检查分别覆盖输入物理合法性、native映射/readback、reset/短程数值行为；每项有quantity-specific oracle/容差，required未测量不能通过，optional保留原因；cube约5%惯量差不自动修正。
- **交付／出口：**三后端协议的真实最小连续执行；不声称同源模型严格等价、全任务支持或 task-success 已完成。

<a id="3c"></a>
## 3c：reset 重建及失败处置

- **输入／依赖：**3b；固定 observation 与当前相机需求。
- **工作：**reset 更换 backend／solver 方案时重建资源与映射；必要时重建 worker，刷新 configuration／materialization／episode 代次并使旧状态失效。保持同一个public Env对象，内部可重建session/worker/App；不能用用户close/make_env替代切换。
- **检查：**同一public Env的代表性 A→B→A 包含三后端的已声明切换边，不以拒绝所有跨路线切换充数；显式seed重置／seed=None延续Core sampler、provider派生seed、preflight拒绝不消耗现有流／初始化样本、固定 obs、旧 view／command 拒绝、构建／reset 故障、重复 close、worker／GPU／锁回收。不将失败后的部分推进当成回滚成功。
- **交付／出口：**重建后可开始新 episode；失败不能 step、可明确重新 reset 或 close。renderer 资源实际切换在 5c 联合复核。

## 验收与限制

每条路线的 source／provider／runtime／device 和实际 exercised intersection 记录到[矩阵](../capabilities/README.md)。若修复要求 provider 公共 API 或新 pin，先按[工作包规则](../planning/execution-and-acceptance.md)冻结范围。不得穿透私有字段或把模型读取能力缺口交给任务脚本规避。
