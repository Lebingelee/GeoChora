# G01：统一任务表示与三方协议

规划标识：`V211_G01_PROTOCOLS`，不是已启动 Goal。4 个子阶段，默认顺序 1a→1b→1c→1d；依赖及接收统一见[执行表](../planning/execution-and-acceptance.md)。本阶段以现有 owner 的契约收敛为主，具体 API 与协议经讨论后冻结。

## Owner 与当前基础

公共构造、配置、Artifact／Scene／source、RuntimeSession、render／camera、Controller、batch 和 Recorder 都有现有入口，见[源码映射](../planning/source-map-and-references.md)。selected 与通用 TaskEnv 尚有兼容路径；当前 protocol／profile 不能直接外推所有后端。本阶段不新建平行抽象，不把源码注册等同运行能力。

<a id="1a"></a>
## 1a：核实 owner、当前范围和可实施组合

- **输入／依赖：**已确认路线、当前 HEAD、v2.1.0 有界矩阵与既有失败；先检查 worktree、dirty paths、gitlink 和依赖版本。
- **工作：**沿 make_env、配置、reset、step、render、记录和 close 追 caller；列出现有协议与缺口。冻结首批三个物理路线的资产、设备、renderer、窗口／RGB 能力；核实 GeoPhys×MuJoCo 跨组合及两个以上并行后端的公开入口。
- **资产范围：**列出质量／惯性／单位／关节／传动／约束／reset／稳定性检查和未测项；区分原生构建转换与未来 asset harness 适配。
- **交付／出口：**更新源码映射、能力矩阵的目标组合和 D01/D05/D06；有依据地区分支持、实现缺口、依赖缺失及未验证，不减少已确认的必达数量。
- **检查／证据：**源码／生产 caller／已有证据核对；只有决策确实依赖且获得后续包授权时才做最小原生探针。审计不默认运行整矩阵，不无限展开全项目盘点。

**attempt001 审计结果：**1a 源码与 caller 审计已交付，状态 `REPORTED_PENDING_REVIEW`。明确了 MuJoCo CPU、GeoPhys CPU、Isaac Sim 6.2.0.0/PhysX/CUDA:0 三条 physics 候选；未把 provider capability 或历史 F06 运行升级为新验证。PickCube 的 free cube 不满足当前 scalar-joint-only dynamic camera admission；Core 与 GeoPhys 的 MuJoCo 依赖区间冲突；现有 native batch 只有 GeoPhys provider，Pendulum／TwoWheelBalance 注册，尚无第二 physics-provider batch。具体资产 oracle、缺失能力、来源及后续 owner 见[本次审计摘要](../maintenance/reviews/20261103_1a_scope_audit.md)和[源码映射](../planning/source-map-and-references.md)。本次未启动原生 runtime 或实现测试；1b、1c、1d 未执行。

<a id="1b"></a>
## 1b：统一任务表示

- **输入／依赖：**1a。Owner 为既有 declaration、TaskDefinition、Artifact／Scene、assembly compiler 和 execution config。
- **工作：**讨论并冻结[统一表示](../contracts/unified-task-representation.md)，把任务语义、物理模型、资产表示、执行配置映射到既有 schema；明确 semantic ID、表示映射、扩展类型和兼容解码。
- **交付／出口：**形成字段与 owner 对照、复用／扩展理由、版本与不支持规则。刚体、关节和相机可实际落地；非刚体保留有意义的接口位置，不设计完整未来语言。
- **检查／证据：**结构化正例及未知字段、身份／映射冲突、缺失必需物理表示的拒绝案例；可先使用静态说明，实际检查代码由冻结包授权，不以文档示例代替实现。

**attempt001 设计交付：**统一表示正文已扩展四类字段/owner/caller、兼容 codec/identity、free/scalar layout、资产映射、execution 层级和 batch identity；新增 planning-only 的 P1–P4/N1–N5 JSON 案例。结论 `PASS`（设计交付），状态 `REPORTED_PENDING_REVIEW`，待 Sol 独立审阅。未改生产 schema/code，不运行 implementation tests/native/physics/GPU；protocol 仍 `DRAFT_FOR_DISCUSSION`，1c 继续 `PLANNED`。摘要及待维护者确认项见[1b 设计交付摘要](../maintenance/reviews/20261103_1b_representation_design.md)，逐项依据见[权威协议](../contracts/unified-task-representation.md)。

<a id="1c"></a>
## 1c：Core 与 physics provider 双向协议

- **输入／依赖：**1b。Owner 为 RuntimeSession、admission、ControlBinding、provider adapter 及公开 provider API。
- **工作：**冻结[physics 协议](../contracts/physics-provider.md)及[控制语义](../contracts/control-and-feedback.md)；定义 query／build／reset／command／advance／publish／close 的值与失败责任。独立 Newton、Isaac 宿主内引擎、多 solver 与 coupler 可区分。
- **关键决定：**最小必需状态、数值准入、夹爪 effort／传动、公共模型服务、反馈时序、命令与实测区别，及 reset preflight 拒绝后的状态。
- **交付／出口：**三条首批路线逐项对照协议；能力不匹配和原生构建限制有结构化拒绝；明确错误／部分执行、异步完成、公开数据有效期。不承诺所有后端提供所有量。
- **检查／证据：**量纲／轴向／排序、数据身份、缺失反馈、solver 耦合不支持、资产不可表达和 stale command 等反例；已有事实与新目标分别记录。

#### G01/1c attempt001 当前结果

状态：`REPORTED_PENDING_REVIEW`；结果：PASS（仅表示双向协议设计和静态文档交付完整）。本轮扩写 [physics provider](../contracts/physics-provider.md)、[control and feedback](../contracts/control-and-feedback.md)、[lifecycle and data](../contracts/lifecycle-and-data.md)，新增 [planning cases](../planning/physics-provider-cases.json)，并在 [source map](../planning/source-map-and-references.md) 记录当前 owner/caller、D03/D04/D06/D07 与官方参考。三条路线仍受各自精确 profile/source 约束；generic capability manifest 不作 task admission 证据。Panda 主路线定义七臂 torque 加 source-bound gripper closure generalized force；现有 R3/PickCube position drive 是 compatibility，所需 effort/feedback 未实现的 route 必须拒绝。静态 query、build-time mapping、runtime measurement 三种证据分开；partial failure 不承诺 rollback；borrowed state 有效期和共享 App owner 明确。

本轮不改统一表示、renderer 协议、能力矩阵、生产代码或 tests；协议全部仍 `DRAFT_FOR_DISCUSSION`。1c 待主审复核；1d 仍 `PLANNED`，不得由此摘要自动启动。完整命令、案例检查、hash、commit 与限制见外部 raw report。


<a id="1d"></a>
## 1d：Core 与 render 协议及共同生命周期

- **输入／依赖：**1b、1c。Owner 为既有 render／camera、RuntimeSession、环境生命周期和数据契约。
- **工作：**形成供维护者审阅的[render 协议草案](../contracts/render-provider.md)和[生命周期／数据补充](../contracts/lifecycle-and-data.md)。汇总原生构建需求，明确共享 scene、app、device、context 和 worker 的唯一 owner；确定 renderer 输入、输出及动态几何扩展。
- **关键决定：**reset 首帧与 step 同步、窗口／任务相机分离、窗口关闭语义、数据设备／借用期限、相机失败；公布 batch 终止语义的设计约束。
- **交付／出口：**五份协议草案统一审阅；确认字段／签名映射、首批 render／cross 组合和每项资源 owner。具体不可确定项须有明确后继 owner 与冻结时点，不能留下影响 3a 开工的强制未知。
- **检查／证据：**原生共享场景和独立 renderer 两类时序图／案例；reset 后旧图、借用过期、重复 close、需求冲突等拒绝行为；明确后续最小 contract 检查。

## 阶段接收

四项是协议与可实施性出口，不是三后端 native 或渲染 PASS。讨论决定写回对应权威协议，Goal 只保存决定与检查索引。参考来源及采用／拒绝理由更新[研究入口](../planning/source-map-and-references.md)。派包遵守[统一工作包要求](../planning/execution-and-acceptance.md)，不把本页直接当作可执行 prompt。

2026-11-03：Sol 核对 attempt001 的实际 diff、9 项输出 hash、JSON／依赖和关键源码后，接收 **1a** 为 `ACCEPTED_BOUNDED_1A_AUDIT`。证据 pin、R3 默认和 horizon 范围澄清见[独立审核](../maintenance/reviews/20261103_1a_sol_review.md)。仅开放准备 1b 单子阶段包，不批准后续协议或自动执行。

2026-11-03：Sol 核对 1b 提交与 7 项输出 hash，并收紧并行维度、partial reset、案例 context／Scene 引用及 extension 槽描述后，接收 **1b** 为 `ACCEPTED_BOUNDED_1B_DESIGN`。见[1b 审核](../maintenance/reviews/20261103_1b_sol_review.md)。这是设计交付接收，五份协议仍 draft；只准备 1c 独立包，由维护者转发。


2026-11-03：Sol 核对 1c 的允许提交、5 项 raw hash 与源码后，作有界文档修正并接收为 `ACCEPTED_BOUNDED_1C_DESIGN`。修正夹爪 Jacobian/功率方向、opening 与 force provenance、准入阶段与初次 build/重建故障区分；补齐多 solver 案例、时间数值上下文及协议→实施阶段映射。见 [1c 主审](../maintenance/reviews/20261103_1c_sol_review.md)。这不冻结协议、不完成任何 production implementation；只准备 1d 独立包由维护者手动转发。


#### G01/1d attempt001 当前结果

状态：`REPORTED_PENDING_REVIEW`；结果：PASS（仅代表协议/生命周期设计、案例与实施追踪文档交付，等待维护者/Sol 审阅）。新增 [render-provider-cases.json](../planning/render-provider-cases.json) 5 正例＋7 反例（规划-only）及 [protocol implementation map](../planning/protocol-implementation-map.md)，更新 render、lifecycle/data、physics-provider 的共享边界与 source map/capability planning。render 三目标分别定义窗口、离屏 RGB、reset/step 同步 task RGB；shared-scene/renderer-only 两路径各有 owner；提出 request/receipt/identity、buffer lifetime、batch terminal/reset 与已推进后 capture failure 规则。

源码审计确认 reset 初帧与 post-step 当前共用 `post_control_step` capture phase，GeoPhys→MuJoCo dynamic source 拒绝 `free_joints`（PickCube 浮动方块未接通），Isaac F06 camera-disabled，remote batch `get_images()` 重复单 worker 帧。因此这些均作为 5a–5c/6c gap，而非能力证据。三条 native renderer 目标及 GeoPhys×MuJoCo cross target 保留；13 targets 仍 `NOT_STARTED`、9 final cells 仍 `NOT_RUN`。协议维持 `DRAFT_FOR_DISCUSSION`，本轮未修改 unified representation 或 control 正文。

本轮仅更新本包 allowlist；未改 production source/schema、tests、依赖、资产或旧 evidence；未启动 App/window/runtime/solver/model/physics/GPU，未导入有初始化副作用的后端，implementation tests=0。报告、hash、命令、检查与实际 commit 在外部 raw output；只准备手动交给 Sol/维护者审阅，不批准冻结、不启动 2a。
