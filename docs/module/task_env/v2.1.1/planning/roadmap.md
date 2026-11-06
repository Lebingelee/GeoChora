# v2.1.1 范围与实施路线

状态：`ROUTE_CONFIRMED`，2026-11-03。确认的是路线和目标；五协议语义已由维护者确认，具体生产值映射在所属工作包冻结，实施与 native 执行由后续冻结工作包承接。

## 必达范围

1. 统一 Core、physics adapter、render adapter 的责任、值契约、生命周期和能力准入。
2. 首批真实物理路线为 MuJoCo／CPU、GeoPhys／CPU、Isaac Sim＋PhysX／CUDA，限定具体任务和资产。
3. 修复 PickCube Solution，先有当前控制链的成功参考，再迁移和复核；NutAssembly 检查复用。
4. 以具名关节广义驱动力为统一施控主路线，Robot／嵌套组件声明受控通道和 Controller，公共状态／可替换模型支持 Controller；BodyWrench 独立类型和未来 typed loads 有明确边界；reset 可切 Controller 输入规格。
5. 窗口、离屏 RGB、RGB 同步进入 observation 全部实现；相机可配置，`.render()` 不额外推进任务物理时间。
6. 在至少两个确实支持并行的物理后端上验证，至少包含一条原生 batch；记录进程并行与原生批量的区别。
7. 同一 public Env 构建／reset 可选择执行组合；不更换配置的部分 reset 按能力支持，换后端按原生批次重建。
8. observation 构建后保持结构、shape、dtype、单位、坐标及字段语义；为非刚体表示和设备数据保留扩展边界。

2026-11-06重新编排建议：[装配Panda](stage4-assembled-panda.md)是本版附加集成用例，原G04的typed命令、三后端effort／BodyWrench及Controller reset主线保持。建议4a作接口需求审阅，4b主能力稳定后早做空载／夹爪／补偿检查，4c有效PickCube参考复用，7a完成两任务原Solution在原／新机器人上的完整复用，7b仅按输入变化定向复核。新类仍置于`task_env/robots/`并由任务配置消费；不要求物性等价。排期待维护者审阅，不增加子阶段或重开G03；当前未实施。

## 已确定的架构边界

- 一个 physics provider 负责整场景，可内部组合多个求解器；跨 provider 力学协同仿真另行规划。
- 同一原生批次使用共同执行配置，切换时整批重建；reset 不做旧物理／Controller 状态迁移；Core sampler 的 seed=None 随机流继续。
- 任务语义、奖励、成功条件与 Solution 属于任务／既有 Core owner；adapter 负责原生翻译和公开反馈。
- 配置优先级继续为 Core → 任务类 → YAML → 调用方；不新增平行 factory、Runtime 或 Recorder。
- 资产由任务提供已准备表示；原生导入、单位变换和声明的构建步骤可由 adapter 完成，重新网格化／替换物理模型等须有明确产物和身份。
- 支持某类求解器与支持其耦合是不同能力；读取文件与数值有效也是不同结论。

## 七阶段、二十二子阶段

| 阶段 | 数量 | 子阶段 | 主交付 |
| --- | --- | --- | --- |
| 1 协议 | 4 | 1a 现状与范围；1b 统一表示；1c physics 协议；1d render 与共享资源 | 已确认实施基线；具体实现不由设计 PASS 代替 |
| 2 PickCube | 3 | 2a 归因；2b 修复；2c 成功参考 | 现有控制链的有效参考与差异记录 |
| 3 后端 | 3 | 3a 路由与准入；3b 三后端翻译；3c reset 重建 | 统一协议驱动真实初始化与步进 |
| 4 控制 | 3 | 4a typed 命令／反馈；4b Controller／外力组合；4c 切换与复核 | 多种输入进入同一施控主路线 |
| 5 渲染 | 3 | 5a 场景数据；5b 窗口与采集；5c 同步 observation／切换 | 三个渲染完成目标分别成立 |
| 6 并行 | 3 | 6a 批量契约；6b 多后端；6c 部分 reset／整批重建 | 状态、动作、图像与 episode 正确对应 |
| 7 集成 | 3 | 7a 任务复用；7b 最终矩阵；7c 文档收口 | 有证据的版本交付与未决项 |

默认顺序为 `1a → 1b → 1c → 1d → 2a … → 7c`。具体依赖及阻塞处置由[执行表](execution-and-acceptance.md)维护；不因某项技术上独立就静默重排。

阶段 2 先建立 MuJoCo 成功参考，检查 GeoPhys／Isaac 差异；三后端完整三 seed 矩阵放在 7b。固定目标是最终 PickCube 9/9 task-success，不能用 runtime-valid 替代。控制迁移后必须复核，不能沿用迁移前成功作为最终结果。

## 渲染与并行组合

原生适配路线优先。阶段 1a 冻结 MuJoCo 自带 renderer、GeoPhys 可用 renderer、Isaac 原生展示／图像路径的具体实现、版本、设备和限制。GeoPhys 的 renderer 名称不得只写“原生”，也不以历史证据替代当前 pin 验证。

首个跨组合候选为 GeoPhys physics × MuJoCo renderer，须经 1a/1d 确认公开数据与资产绑定；若不可行，须带依据提出另一组合供维护者确认。阶段 5 必达一个实际跨组合，不默认为任意 physics × renderer 矩阵。

并行候选优先核对 GeoPhys 原生 batch 和 Isaac GPU batch。1a 冻结至少两个后端的名单、原生／进程方式及 6b 的实现范围；能力未就绪列为实现缺口，不能靠减少数量完成阶段。

## 后续 v2.1.x

Flora 不属于 v2.1.1 必达。SAPIEN、Genesis、独立 Newton、Isaac 内 Newton 需要在架构与能力表达上有合法位置，本版不承诺全部实际接通。

完整 F07、asset harness 自动适配、软体／流体／绳索真实样例、RL／IL demo、`agent_factory` 优化、R07 自主 Solution 扩展与 Isaac Lab 全功能差距研究后移。当前只研究与本版协议相关的优秀实现。

严格 F05 源柔顺／传力等价、同 USD 全后端等价、DG03、正式 Qualification 和发布不成为本版普通执行的隐含前置。已接收原生适配及其限定例外保持；不恢复旧 D01、退役执行器或整体 60% 删减指标。
