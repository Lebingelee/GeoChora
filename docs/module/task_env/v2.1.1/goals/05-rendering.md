# G05：统一渲染前端与同步 RGB

规划标识：`V211_G05_RENDERING`。3 个子阶段；以[render 协议](../contracts/render-provider.md)和[生命周期／数据](../contracts/lifecycle-and-data.md)为权威，原生适配优先。Flora、Depth、分割的新增验收不在本 Goal。

## Owner 与当前缺口

复用 render backend registry、single／parallel providers、camera API／source 及 provider 公开场景数据。selected 配置／session 当前仍 state-only；必须把场景、实际状态、采样、obs 和关闭一起接通，不能仅新增 renderer 名称。

2026-11-11 当前注记：上段 state-only 及下文 2026-11-08“尚未完整贯通”描述保留为历史起点。单元 9 的[Sol 综合主审](../maintenance/reviews/20261111_unit009_sol_5c_bounded_acceptance_b23fb3cc.md)已对修订后的 5c 功能作有界接收，维护者最终接收待确认；原 5a／5b 有界结果继续按影响保留。生产身份为 `a53bf19d`，综合交付为 `b23fb3cc`；不宣称任意组合或完整 Qualification。代码／入口及项目优化仍须另行完成和人工接收，尚未进入 G06。

<a id="5a"></a>
## 5a：公开场景数据和原生绑定

- **输入／依赖：**1d、3c、4c；1a/1d 冻结的三条原生适配及跨组合。
- **工作：**接入视觉模型／材质／相机／灯光，建立 semantic entity→render object 映射，按公开状态更新。允许 native 共享 scene／model，复用现有 owner 而非增加镜像 physics 状态。
- **检查：**变换轴向／参考点／单位、动态更新身份、映射／拓扑代次、共享资源唯一关闭；不支持的变形数据明确拒绝。
- **交付／出口：**renderer 可说明已消费哪个公开状态；设备 copy／共享方案和限制可查询，不读 physics 私有 field。

<a id="5b"></a>
## 5b：窗口、自定义相机和离屏 RGB

- **输入／依赖：**5a，实际窗口／离屏 context 与设备依赖。
- **工作：**先完成 PickCube×MuJoCo 自带 renderer，再补明确命名的 GeoPhys 路线和 Isaac 原生展示／采集；落实 render_mode／metadata／render／close。窗口观察相机和任务相机默认分离。
- **检查：**真实窗口与离屏 RGB 分别验收；相机姿态／参数可配置，挂载及分辨率正确，观察拖动不改任务相机。重复 render 不改变物理时间，窗口关闭、重复 close 与失败清理正确。
- **交付／出口：**三条首批路线具备声明的窗口＋RGB，图像来自真实 scene；截图不替代原始图像／相机／状态证据。

<a id="5c"></a>
## 5c：同步 observation、构建时 renderer 选择与跨组合

- **输入／依赖：**5b；相机输出、时间与借用数据契约。
- **工作：**构建 Env 时选择并绑定已准入 renderer，在该 Env 的 reset／step 中保持同一 renderer 直到 close。reset／step 自动协调更新、采样和完成等待，把 RGB 组合进固定 obs；reset 清理旧帧。验证至少一个 physics 与 renderer 跨组合。
- **检查：**reset 首帧、新状态运动对应、重复 render 的时间不变、相机失败拒绝／清理、旧缓存失效、同一 renderer 跨 reset 保持；有／无渲染的施控及物理边界一致。图像规格与独立记录读回，不能只有 shape 断言。
- **交付／出口：**调用方无需额外 render 即获得同步 RGB；至少一个真实跨组合，不宣称完整自由组合矩阵。

2026-11-08 维护者进一步明确：Pendulum 与双轮车需以受控主体接入统一构建及 Controller 生产流程；Controller 可为保持既有力矩动作语义的直接映射。Panda 的末端、夹爪和特定维度假设应由对应 Robot/Controller 负责，不应成为公共环境或渲染准入条件。该流程必须兼容既有多层嵌套 Robot，单层任务与嵌套主体应沿同一绑定和命令提交机制；公共 Runtime/state 不依赖任一 renderer，格式和实现适配留在各自边界。该流程目前尚未完整贯通，是 5c 人工诊断中的未完成目标；现状与证据见[统一 Runtime 与嵌套控制审计](../planning/stage5-5c-unified-runtime-control-audit.md)。

2026-11-08 维护者进一步指定：在进入 G06 前以多个必要的人工诊断实施窗口，完成一体／装配 Panda、Pendulum 和双轮车的统一主体构建与 Controller 接入、renderer-independent 公共状态及本轮涉及的诊断耦合归位；各窗口范围和资源另行冻结。装配 Panda 的真实主体/控制接入提前纳入 5c，原两任务完整 Solution 用例仍在 7a。详细工作单元与验收依据见[5c 诊断重构路线](../planning/stage5-5c-diagnostic-refactor-roadmap.md)。

## 失败与证据

先核实原生 App update 是否会推进物理，是否可控制其采样／显示更新；必须显式处理预热。若 renderer 换成另一种会改变固定 obs 规格或 camera 语义，应拒绝该 env 的组合。

首跨组合候选为 GeoPhys physics×MuJoCo renderer；若不可行，在派包前按 D01 提出替代并确认，不自行减少该必达项。不同 renderer 无需像素逐点相同，各自须满足公开状态、标定、场景可辨识和同步 oracle。

2026-11-07 维护者修订：同一 Env 的 renderer A→B→A 切换延后到未排期的后续任务，不是 5c 出口。renderer 选择在创建 Env 时确定，直到 close 均不更换；reset 可以重建同一 renderer 的内部资源，不得静默换成其他 renderer。已有 backend／Controller reset 目标不因本修订取消，若其新配置无法与固定 renderer 组合，须在作用发生前明确拒绝。不同 Env 可分别选择支持的原生或跨组合。实现须由通用场景、资产、具名状态与相机声明驱动，不得对 PickCube 写特殊渲染分支；PickCube 是本阶段真实验证任务，不代表其他任务已经通过。窗口／capture不调用Controller或推进physics；同步RGB沿用已确认state boundary与既定obs契约。详见[5c 范围与次序](../planning/stage5-5c-fixed-renderer-scope.md)。
