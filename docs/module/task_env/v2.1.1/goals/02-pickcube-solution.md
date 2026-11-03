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

### 2a attempt001 结果（待主审）

状态：`PASS（2a诊断交付）/ REPORTED_PENDING_REVIEW`。输入为 Core `develop@fcf0700a5ddaff85e7beb190f018d9f71d94100b`、GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50`。历史 F06 seed31 的 MuJoCo 公开轨迹在当前 HEAD 上以同一字节级 `step_trace.json` SHA-256 再现；当前的 Solution、Controller 与 task 源码身份已变化，因此这是失败行为复现，不是源码身份相同。

本次 CPU MuJoCo seed31 经当前公共 Harness 完成 227 个 control transitions（5×2 ms/substep，约 2.27 s），runtime、记录、独立 HDF5 读回、close 均通过；任务仍失败。Solution 在 `over_cube_before_descent` 连续 100 个等待样本未满足 measured TCP clearance gate，随后以 `measured_tcp_clearance_timeout:over_cube_before_descent` 失败。请求 TCP 为 `(0.635134, -0.086464, 0.753000) m`；最后一条 gate 样本（attempt 227，2.26→2.27 s）中，公共实测 TCP 为 `(0.600891, -0.081910, 0.716055) m`，相对 cube 顶面的高度 `0.203427 m < 0.215 m`，水平误差 `0.034545 m > 0.010 m`。运行没有进入下降或关爪；lift `0.000628 m`，task success、Expert complete 均为 false。G2 通过不代表任务成功或 Qualification。

**已定位的近端根因**是任务 Solution 的 over-cube measured-TCP readiness gate 在本次 seed31 运行中持续不满足并触发超时。证据把请求动作、R3 参考、公开测量状态、gate 数值和最终失败原因连接起来；它尚未区分“为何实测 TCP 未到请求位姿”的更下层原因。R3 改动与失败存在版本相关性，不据此判定 R3 是根因。源码中 grouped R3 关爪路径没有推进 `inner_gripper_step()` 是待证伺服风险，但本次运行失败在关爪之前，不能将其归因于本次失败。历史 F06 seed33 曾在 attempt 192→193 通过同类 over-cube gate，反证“此 gate 对所有 seed 都不可达”的泛化说法。

最小 2b 候选是 **FIX（任务级 PickCube target/reference/gate 形成路径）**：由 `task_env/tasks/pick_cube` owner 先用公开量定位请求 TCP、参考 TCP 与 `panda-v1/ee` 实测 site 的偏差来源，再只调整必要的 hover/侧移 waypoint 或其时序；保持当前 clearance gate、cube lift 成功判据、碰撞和 reset 分布不变。代表 seed 先固定 31；验证应保留逐 control boundary 的请求 pose、q_ref/target、实测 TCP/cube pose、R3 clipping/lead 诊断、gate、gripper servo/实测 finger state、阶段与结束原因，并完成同 run 独立读回。只有当失败被推进到 close 段后，才以一个有明确假设的短检查验证夹爪内环。详见[2a 完整报告](../../../../../workspace/maintenance/v211_g02_2a_attempt001/report.md)；2b 需独立审阅与新工作包授权。

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
