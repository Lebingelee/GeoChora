# v2.1.1 执行顺序与验收

状态：G01/1a–1d已审阅并获维护者确认；G02阶段2已按原出口由Sol有界接收：2a归因、2b MuJoCo代表实现和2c成功参考冻结完成。原2b attempt002的G2 FAIL、G3 PARTIAL、G5 INCOMPLETE_USER_PAUSED历史保留；阶段3未开始。阶段 owner 入口见[源码映射](source-map-and-references.md)，协议正文在 contracts/，子阶段目标见对应 Goal。此页维护依赖和验收标准。

### 2026-11-04 G02/2b 中止与 2c 文档封存

MuJoCo PickCube seed31 完整成功并独立读回；NutAssembly seed19 两次独立运行均成功；PickCube seed32 在 1000 个控制 tick 后仍未达到 lift predicate。GeoPhys 已定位到 PickCube Solution 的 stale execution time guard；Isaac delivery closure 匹配，但当前 GPU gate 不稳定且没有 native run。原2b在用户暂停时G5未完成；之后由独立2c包整理历史和成功参考，旧G2/G3/G5结果不变。2c文档封存经[Sol主审](../maintenance/reviews/20261104_2c_sol_review.md)有界接收，G02收尾并停在阶段2；阶段3未开始。详见[2b中止记录](../maintenance/reviews/20261104_2b_closeout.md)和[2c参考冻结页](../maintenance/reviews/20261104_2c_reference_freeze.md)。

## 顺序与最小出口

默认按表逐项推进；依赖列描述技术前置。必要的协议跨页审阅不另算子阶段。

| ID | 依赖 | Goal / 完成条件 |
| --- | --- | --- |
| 1a | 规划文档完成 | [01](../goals/01-protocols.md)：当前 owner／caller、三后端资产／render／batch 组合、版本、缺口与数值检查范围有依据 |
| 1b | 1a | 四类表示、标识、映射与扩展规则确认；不引入平行 Core |
| 1c | 1b | physics 双向协议、路由层级、最小反馈与拒绝语义确认 |
| 1d | 1b、1c | render 双向协议、共享资源、时间和生命周期确认；阶段 1 统一评审 |
| 2a | 1a、1d | [02](../goals/02-pickcube-solution.md)：根因有证据；R3 假设与事实分开 |
| 2b | 2a | 当前控制链 MuJoCo 完整成功；其他两后端差异可定位 |
| 2c | 2b | 成功参考、冻结配置和剩余问题可复现；不提前要求九格重复矩阵 |
| 3a | 1c、1d、2c | [03](../goals/03-backends.md)：配置解析、能力交集、拒绝与配置回执接通 |
| 3b | 3a | 三后端公开构建／reset／step／state／close，含资产映射与数值检查 |
| 3c | 3b | 同一 public Env 的代表性 A→B→A、Core随机流连续、故障重建、旧数据失效和资源回收 |
| 4a | 1c、2c、3c | [04](../goals/04-control.md)：typed JointEffort／BodyWrench、嵌套主体、反馈／模型、时间及组合后唯一提交落地 |
| 4b | 4a | R3／关节参考／direct effort 的7＋2映射在三后端成立；有界BodyWrench、显式叠加和驱动冲突检查 |
| 4c | 4b | reset 切 Controller，输入契约可识别，observation 固定，Solution 重新复核 |
| 5a | 1d、3c、4c | [05](../goals/05-rendering.md)：公开 scene data／原生绑定接入既有 renderer |
| 5b | 5a | 首批路线窗口和离屏 RGB 分别验收，相机可配置，render 不推进物理 |
| 5c | 5b | reset 首帧、step 同步图像、renderer 切换及一个跨组合成立 |
| 6a | 3c、4c、5c | [06](../goals/06-parallel.md)：批量布局、reset mask、终止／首帧和 schema 接通 |
| 6b | 6a | 至少两个物理后端真实并行，至少一条 native batch，覆盖构建／reset／step／render／obs |
| 6c | 6b | 支持路线部分 reset，切配置整批重建，故障、资源及环境隔离成立 |
| 7a | 4c、5c、6c | [07](../goals/07-integration.md)：NutAssembly 已支持后端复用及受影响兼容 caller 检查 |
| 7b | 7a | 冻结输入下 PickCube 三后端×三 seed 任务成功与独立记录检查；切换／render／batch 组合分别收口 |
| 7c | 7b | API／指南／矩阵／Skills／恢复页与实际证据一致；版本未决项明确 |

初建时全部22项为 `PLANNED`、attempt为0；现1a–1d及2a–2c均有相应有界接收，维护者已确认五协议实施基线，阶段3–7的15项仍未执行；原2b扩展包失败及中止记录保留。实时状态只在[编排索引](../maintenance/orchestration.json)维护。Goal 页面记录结果摘要，不复制第二套状态表。

阶段 2 若证明必需修复属于后续公共协议 owner，先记录根因、最小提前实施范围和依赖影响，经维护者确认后更新执行表；可复用修复不重复实施。不得以无变化重试、私有状态或更改任务判定跨过阻塞。

## 每包必须冻结

- 子阶段／attempt、授权范围、输入 HEAD、允许修改 owner／路径、保护输入及摘要。
- task／Artifact／Scene／资产来源、实际 provider／引擎／求解器、renderer、设备、Controller 与动作／观测身份。
- 当前行为、根因或缺口、选择 FIX_EXISTING／EXTEND_EXISTING／COMPOSE_EXISTING 的理由；新增抽象须证明既有 owner 不适用。
- 必须运行的正／负例、oracle、单位与容差依据；seed、horizon、控制／物理周期和图像尺寸；离线与 native 检查分开。
- 主动工作时长估计、attempt timebox、单次运行及累计墙钟／RAM／VRAM／磁盘预算、共享 native 资源约束。
- 输出目录、报告／独立 reader、允许本地提交、失败／清理／窗口释放要求。

派包前补齐具体方法和调用者，不能拿目录名或本页顺序替代可实施工作包。五协议采用 APPROVED_IMPLEMENTATION_BASELINE；生产类型／签名仍需按现有 owner 实施，未实现前不提供伪可执行 API。工作包必须引用当前基线确认收据，不能沿用历史 1c 的 closure-effort 提案。

## 证据与终验

| 层次 | 必须能回答 |
| --- | --- |
| 协议／离线 | 身份、类型、单位、排序、权限、拒绝、时序和旧数据失效是否被保护 |
| 原生运行 | 指定配置是否真实构建、初始化、控制、步进、读回并关闭 |
| 任务成功 | 原任务谓词、生命周期有效成功、Solution completion 分别是什么 |
| render／obs | 消费哪个状态、首帧和终止帧是否正确、图像规格／设备／同步是否满足 |
| 记录 | 同一运行的 T transitions／T+1 boundaries、episode 配置和 schema 是否能独立读回 |
| 版本能力 | 哪个 task × source × provider × backend × renderer × Controller × batch 范围实际通过 |

最终 PickCube 以三后端×seed 31/32/33 为初始九格目标；如种子因有依据的任务约束需要变更，须在矩阵执行前经维护者确认。runtime-valid 不替代 9/9 task-success；不要求跨后端轨迹逐点相同。

RGB 不要求不同 renderer 像素逐点相同；须有可辨识场景、相机标定／姿态、状态身份和同步检查，不能只有 shape 检查或人工截图。开启／关闭渲染应保持任务物理时间及施控序列；随机／GPU 非确定路线按声明容差比较。

NutAssembly 用于已有后端的代表性复用；不自动扩为所有任务的九格 Solution。最终九格不隐含每个 renderer × batch × Controller 都重复三 seed。各维度最小代表性交集在 1a/1d 冻结。

## 工作流、分支与资源

维护者已指定继续当前 `develop` 工作树，本版本计划新增分支数和工作树数均为 0，不恢复 F/R 线，不逐 Goal 新建分支。每个冻结包仍需重新检查真实 HEAD／dirty paths。若需修改 GeoPhys 公共 API 或 pin，先冻结子模块修改范围、分支／提交归属和受影响检查；不把 pin 修改当成默认动作。

Sol 负责讨论、编排和接收；Luna／Terra 按后续明确授权承担一个完整包。默认一个 writer 和一个 native 执行窗口；尚未指定谁执行哪个阶段，不自动创建线程或发送消息。完整报告与窗口释放后再审核 diff 和证据，PASS 不是自动接收。

按[Goal 编排流程](../../../../../.agents/skills/geochora/references/goal-orchestration.md)，一次 attempt 可包含多次修复与运行；普通子阶段至多三次窗口，第三次前重审根因与官方项目实现。常规修复不因单次测试失败而结束 attempt。执行包有完整预算，不能把“一次启动、失败即停”设成默认。反复同根因且无新假设时归因并向维护者报告。

原始日志、失败、图像和 H5 保持 ignored；跟踪文档仅保存摘要和证据引用。每个有界输出配本地提交，只暂存本包路径。推送、合并、tag、Release、正式 Qualification 不在当前文档授权中。
