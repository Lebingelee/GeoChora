# G02：PickCube 归因与成功参考

规划标识：`V211_G02_PICKCUBE_REFERENCE`。3 个子阶段；具体依赖和出口见[执行表](../planning/execution-and-acceptance.md)。本阶段先修复现有控制链，不以新 effort 架构假定替代根因分析。采用[已确认协议基线](../maintenance/20261103_protocol_baseline_confirmation.md)，不在2a提前实施7＋2 effort／BodyWrench／后端与渲染重建。

## Owner 与事实

优先定位 PickCube `solution.py`／`specialization.py`、R3 参考生成、现有 control session、任务初始化和判定。历史九格 runtime-valid、task-success 0/9；clearance timeout／horizon 及 R3 的关系仍需验证。不得提前将“R3 导致失败”写成已证实根因。

<a id="2a"></a>
## 2a：以失败证据定位根因

- **输入／依赖：**1a、1d；旧失败原件、当前任务与 R3 配置／高层输入和实际position-command边界、实际资产和已确认时间／控制语义。
- **工作：**核对 TCP／参考点、关节／夹爪映射、目标轨迹、clearance、阶段切换、保持时间、控制频率和 horizon；区分控制、Solution、物理／导入和任务判定问题。
- **检查：**先复用历史日志与离线轨迹，再做包内批准的最小 MuJoCo 复现；只读取公开状态和回执，保存失败而不改 oracle。
- **交付／出口：**有证据的根因、仍待验证的假设、最小修复 owner 与受影响路线。无变化重试不构成进展；2a只归因与最小复现，不提交生产修复。诊断脚本／观察量若确有需要，仅在冻结包授权的diagnostics owner或ignored目录增加，不绕过公共状态。

<a id="2b"></a>
## 2b：修复当前控制与 Solution

- **输入／依赖：**2a 的根因与冻结修复方案。
- **工作：**在原 owner 修复轨迹／控制／映射或生命周期；不把 task-specific 策略迁入 Core，不恢复旧 bundle／阶段执行器。先取得 MuJoCo 代表性 seed 完整成功，再检查 GeoPhys 和 Isaac 的实际差异。
- **检查：**任务谓词、合法生命周期成功、Solution completion 分开报告；验证必要运动、抓取／抬升／保持等阶段事实，完整记录有效执行并独立读回。
- **交付／出口：**MuJoCo 有完整成功参考；另两路线的代表性结果和需后续公共能力解决的问题明确，不要求每改一处跑九格。

<a id="2c"></a>
## 2c：冻结可复现参考

- **输入／依赖：**2b 成功实现、实际运行和独立读回。
- **工作：**固定 task／source／Controller／资产／seed／timebase／Solution／horizon／容差；保留阶段状态、输入、target、applied ack 和结束原因。
- **检查：**参考确实属于同一版本和运行，成功不是人工修改状态或宽松判定；剩余后端差异有归因和下一动作。
- **交付／出口：**供 4c 对照的冻结参考及未决清单，不授予全后端等价或正式 Qualification。

## 阻塞与后续

若发现必须提前实施 3／4 阶段公共能力，按[执行表](../planning/execution-and-acceptance.md)提出最小依赖调整，由维护者确认，不无限重试也不建立私有补丁链。控制迁移使输入变化时，阶段 2 证据保持历史；4c 重新验证，7b 再做三 seed 九格。
