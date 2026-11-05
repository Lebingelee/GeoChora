# G03/3a attempt001 执行摘要（待 Sol 独立复审）

- 包：`V211_G03_3a_attempt001`；执行者：维护者指定的 Terra 对话；输入 `40ca5d56153b9e13848b20c2af550c1efe076b98`；状态 `REPORTED_PENDING_SOL_REVIEW`。
- 这是未完成的实现返包，不是阶段接收：普通 PickCube／Nut MJCF 来源尚无完整资产闭包回执，预检因此拒绝 reset；既有兼容性门未通过。没有扫描或复制资产来制造证明。
- 沿现有解析、Session/admission、来源和 Recorder owner 增加分层选择、request-specific assessment、依赖环境预检、薄 worker 和配置回执。跨进程仅传受限值，worker 重建同一 task 并再次核对来源与准入；不新增 Env 或物理生命周期。`RemoteBatchVecEnv` 是同构 batch，不是跨解释器 scalar session。
- 最终无引擎有界组 `final-offline-01`：108 passed、1 deselected；测试子进程替身只验证协议。F06 精确来源策略有无引擎负例。旧 codec/hash 对照输入 HEAD 的独立冻结源码。没有 native import/init、物理 step、GPU、render 或 App。
- 门 A 部分通过；B 未通过（普通资产闭包及嵌套／typed 需求覆盖未完成）；C 部分通过（冲突、source origin、fake worker 已验证，真实三路线不可宣称）；D 部分通过（替身路径和拒绝回执）；E 未通过（selected 兼容性回归）；F 以完整报告、文档检查、保护与提交核验为准。真实源闭包、普通兼容路线及三后端运行需要后续单独安排；不得自动进入 3b。
- Core 当前解释器中 MuJoCo 3.8.1 符合 Core 约束，不满足当前 GeoPhys 的 `mujoco>=3.15.0`；本包未安装依赖。GeoPhys distribution 缺失不否认当前 checkout 源码；Isaac SDK 未发现。应由维护者准备绑定当前 Core/GeoPhys 源码且满足各自约束的隔离解释器。
- 完整逐 case 结果、日志、命令、限制与输出 manifest 保留在 Core ignored `workspace/maintenance/v211_g03_3a_attempt001/`。维护者手动转交 Sol；只有 Sol 独立复审可作接收决定。
