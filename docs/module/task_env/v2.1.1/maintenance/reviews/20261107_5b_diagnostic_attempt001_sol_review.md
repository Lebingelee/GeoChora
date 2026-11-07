# G05 / 5b 诊断 attempt001：Sol 独立主审

## 结论

`DIAGNOSIS_PARTIAL_REWORK_REQUIRED`；**5b 未接收**。普通 attempt count=3 不变，本次是维护者批准并人工转交的独立 diagnostic attempt001，diagnostic count=1。保留 Isaac 6.2 headless 原生 RGB、GeoChora 所有窗口和关窗后持续采集的有界真实进展；它们不能证明原 5b 三路线出口完整通过。5a 既有接收不重开，5c 和阶段6未启动。不会自动普通 004、派下一包或联系其他对话。

## 必须修复：通用 reset 故障恢复回归

最终提交 `0cfb43efdcf22baac411d244819c47a5863fc7cf` 在 `task_env/environment/reference_env.py:1384` 的通用 `SelectedReferenceEnv.reset` 入口调用 `_require_execution_healthy`；该 helper 对**任意**既有 execution fault 拒绝 reset，要求新 Env/session。`reset_for_solution` 也采用相同入口策略。这不只影响 Isaac 或 `observer_render` 故障：`reset_seed`、`physics_step` 等故障也被阻断。

Sol 在阻止 XML/USD 等场景资产读取和 native/SDK/provider import 的 guard 下，用真实 `SelectedReferenceEnv.reset`、真实 `EpisodeExecutionState` 和合成 `ExecutionFaultV1` 分别注入 `reset_seed`、`physics_step`、`observer_render`，三种均在入口报 `selected execution is faulted; a new Env/session is required`，未到 rebuild。此为纯合同分支复现，不是对三类真实 native 故障或实际重建成功的证明。旧 HEAD `427b8626` 的入口只要求 Env 未关闭；现存 `test_selected_consumers.py:1556` 明确要求失败的 reset 后可再次 reset，该测试本身依赖真实 source 解析，Sol 未执行。`contracts/lifecycle-and-data.md:14`、`:36`、`:38` 允许 faulted Env 明确 rebuild/reset，且已准入切换由同一 Env 在 reset 上处理。全局拒绝造成既有恢复回归，不能因诊断包对渲染故障要求 fail-closed 而扩展为所有故障必须换 Env。

后续修复须区分真正不可恢复的 App/worker 资源和可通过受控 rebuild reset 恢复的故障，保留旧 fault/partial effect 和旧 receipt 失效；不能简单清空 fault 后继续旧 episode。覆盖实际公共 reset/reset_for_solution 入口、旧非渲染故障、observer 故障、资源不可恢复分支及相邻真实路线，且不得把 5c 全套切换提前设门。此处不擅自指定唯一代码方案。

## 图像与相机仍未闭合

- D1 `isaac_d1_rgb_headless_006` 的真实 headless CameraSensor 帧非黑，物理边界保持，构成有界 RGB 证据；其预先固定的 A 与 C holdout 分别为 `0.1031042039` 和 `0.0728297234`，固定阈值 `0.1`。Sol 直接从 raw state、相机矩阵和 `.npy` 像素独立重算得到相同结果。C **未通过该判据**；这既不能宣称该图像已经通过，也不能仅凭单个对比度结果断言渲染器像素或场景必然错误，需区分投影、遮挡/光照和 oracle 的原因。不得事后仅调低阈值。D1 原 run 基于输入 HEAD 上的未提交工作树，未见该 run 的完整产品 diff/hash；D2/D3 为输出提交后的不同采样，不能自动把 D1 说成已精确证明最终代码。
- D1 reader 的 stale 负例是构造不同 episode ID 并比较 receipt 字典，与真实旧状态图像拒绝、实际生产 stale capture 调用是不同证据；不能当作真实旧帧像素或完整生产路径负对照。前期图像特征及颜色选择有探索偏差；源材质色域及 primaries 未标定，保留限定。
- D2 真实 320×240 窗口 A/B 与同次 raw RGB 转换后的像素完全一致，物理计数保持 `(18, 0.036)`，可保留为所测窗口展示和程序切换观察视角的有界证据。当前 F06 **没有配置任务相机**；其 null 配置及 artifact/binding 在 A/B 前后不变，不能单凭此证明存在任务相机时其 geometry/mount/identity 不变。旧 002 mount03 可按原输入和实际代码影响评估复用，不把 5c 自动任务 observation 变成 5b 前置，也不要求鼠标操作。
- 三路线旧窗口／RGB、裁剪和 GeoPhys rasterizer 灯光证据只在各自输入、route、版本和受影响代码范围内复用。此次共用 `TaskEnvRenderProvider` 的窗口关闭语义改变；Isaac 实测与纯合成测试不能自动证明 MuJoCo/GeoPhys 对同一变更的全部原生行为。先按实际路径核实，必要时只补受影响代表例；不重复历史全矩阵。

## 可保留的生命周期进展及限制

D3 在真实生产 Tk 窗口执行 WM_DELETE，随后窗口消失、Isaac headless App 和 Env 仍运行、同边界 capture 继续；之后一段显式控制与 headless 对照的 action、typed state 和时钟一致。维护者已批准 GeoChora 窗口展示 Isaac 原生帧作为 5b 窗口候选。此证据支持**被测配置**下展示/采集生命周期分离，且不同于旧 Isaac 原生 viewport 一关即令 App 失效。未诱发真实 native App/renderer crash；typed fault 是 24 项纯测试中的注入分支结果，不可外推为实测 native crash。

代码在 source stage 无 authored light 时向内存 stage 加 `UsdLux.DomeLight` 并修订退化时间范围，未保存 source；此会改变实际图像光照，应按所测配置和 receipt 说明，不能把新模式下结果直接外推为旧 headed 模式或完整源灯光/颜色等价。早期全黑、关停 SIGSEGV、前次 `isaac_rgb01` SIGKILL 和旧零步预约/RSS 偏差保留；未知 bootstrap 隐式物理步不按零记。

## 输入、输出和独立核对

- 诊断输入 `codex/v211-stage5@427b862665af5ab79f8cae7068f6d575ce9b6223`，输出提交 `0cfb43efdcf22baac411d244819c47a5863fc7cf` 为其直接子提交，五文件；GeoPhys `a6bf45b3422e31dfc632a58948e57fa4b686f1b0` 和 Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` 未变。原 Sol 两份未提交文件和三保护输入在 executor release 时与快照一致；此后本次 Sol 正常更新独立审查和编排，不改历史 executor 输出。
- Sol 独立读取 manifest，逐文件复算 **457/457** 大小和 SHA，核对目录未列出/多列文件均为零，总 32,498,914 bytes；manifest SHA `f15ece1e51a3949fc5f3a7bb4e20cbfce3422e6ddefe0971080c62662261b447`。release receipt 单独存在并报告 worker/锁逆序释放。时点状态及 receipt 不能代替未来开工前的 writer/锁复查。
- 实施者最终提交的纯 render 测试记录 **24 passed**，不覆盖上述通用 reset 恢复；Sol 未重跑其需要 scene 来源的旧测试。Sol 仅做两项无 native/SDK/source 解析检查：重算保存帧的 holdout、注入 fault 检查公共 reset 入口。`git diff --check` 通过。
- 诊断窗口约 112 分钟；账本 reported 15 native workers、source 45.840 秒、native 1168.505 秒、显式预留 64 substeps、bootstrap 早期 unknown；显存为采样而非硬上界，28 个早期 RSS peak 样本缺字段。受限数据与采样限制原样保留。

## 后续

在维护者主导诊断下，下一步应集中解决通用 reset 回归、D1 holdout 最早失败边界、真实 task camera 隔离证据与实际 stale 检查，并按 diff 确认共用窗口修改对 CPU 路线的影响。按现有证据可复用原则组织，不重新跑完整路线矩阵。需要新的执行窗口、具体授权和预算时，由维护者决定并人工转交；本次主审未创建下一派发包。
