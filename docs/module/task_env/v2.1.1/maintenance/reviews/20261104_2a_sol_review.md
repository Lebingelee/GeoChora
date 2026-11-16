# G02/2a Sol 独立复审

日期：2026-11-04（Asia/Shanghai）。决定：`ACCEPTED_BOUNDED_2A_DIAGNOSIS`。接收对象是原 `V211_G02_2a_attempt001` 及维护者随后明确要求的补充诊断；不是执行代理自评自动生效，也不接受“gate 未过”单独充当上游根因。2b 仍须独立冻结工作包，由维护者转发后执行。

## 版本、来源与检查

- 复审输入/执行文档输出：`develop@920944934b6dfe92971b51ec75a6fb698ac5cc16`；parent 恰为原输入 `fcf0700a5ddaff85e7beb190f018d9f71d94100b`。实际 diff 只有原包允许的五份文档；生产代码没有变化。GeoPhys gitlink/checkout 仍为 `67da1165149486d3ae3e779c13ce31af49e17d50`。
- 原包 prompt/manifest/snapshot 校验通过；115 项冻结当前输入（四项已更新文档按输入 commit 字节比较）、40 项 G01 raw、137 项历史输入保持。原始 output manifest 的 28 项 raw 和五项 tracked 文档逐项 size/hash 通过。
- 原报告 SHA-256：`2c0ea079ec5acf5032f8ef0d800fd8ddf72ea001ce3d1ce7d64dc54598069f6f`；output manifest：`0965302925b462d17b39de56602f84fbdb6aaeb41da72342f368f88740967cd0`。原报告、执行摘要、manifest、历史 raw 均未修改。
- 补充诊断的四份 manifest 分别覆盖 38、102、43、17 项文件；全部逐项 hash/size 和 sidecar 通过。`_001` 保留为 settle 未完整对齐的前次结果；最后配置对齐结论只取 `_002`，不拼接两次运行。
- 独立审计脚本、结果：`/home/lly/Documents/ChatGPT/GeoChora v2.1.1/handoffs/V211_G02_sol_review_20261104/` 下的 `audit_evidence.py` 与 `evidence_audit.json`。本次 Sol 只读存储数据、做当前源码纯编译/FK/线性代数核验；没有构造 Env、reset、启动 provider、物理 step、GPU、窗口或 implementation tests。

## G0–G5 决定

| Gate | Sol 结论 | 独立依据与边界 |
| --- | --- | --- |
| G0 输入/范围 | PASS | 输入/parent、allowlist、pin、封包和保护字节匹配。原包与维护者后续追加实验分开，不将补充运行倒算进原包预算。 |
| G1 源码/历史 | PASS | 当前 caller 为 Solution→R3→RuntimeSession→公开 state→gate；旧新 trace 同字节不等于源码同身份。交叉运行的 reset 姿态和 controller 参数混杂保留。 |
| G2 当前合法复现 | PASS | 原 MuJoCo CPU seed31：227 transitions/228 boundaries；trace actions 与实际 H5 数组逐项相同，时钟每步 10 ms。原独立 reader、close、进程组/双锁 receipt 及字节身份一致。任务和 Expert 均失败，未发生系统 fault。 |
| G3 因果机制 | 有界 PASS（合并追加诊断） | 原包单独只证明近端 gate 失败，尚不足以选上游修复；速度干预、稳定 hold 和独立 DLS/FK 复算进一步定位了动态滞后与该记录构型下的局部停滞。未证明近奇异是唯一根因，也未证明某个姿态/waypoint 修复有效。 |
| G4 可实施下一步 | PASS（按本复审修订） | 2b 先固定 Controller/planner 后做姿态路径单因素对照，再据结果在任务 owner 修复；不降低 gate，不改 reset/source，不预先重写共享 R3 算法。遇到关爪问题才检验已定位的 interval/inner-servo 调用缺口。 |
| G5 交接/清理 | 有界 PASS | 仅五个文档提交、原报告清单完整、保护字节保持；执行聊天已返回，当前双锁无占有。原报告没有精确主动分钟数，补充实验也没有原包同等的统一 RSS/累计预算账，均保留为报告限制，不伪造补齐或提升资源合规声明。 |

## 已证实机制与尚未证明的命题

原 seed31 的 100 个 `over_cube_before_descent` gate 样本，按各 transition 的 **pre-step** 公开状态计算，没有一次同时满足高度≥0.215 m 和水平误差≤0.010 m；最后高度为 0.203426981 m、XY 误差为 0.034545039 m。该 gate 失败导致下降前 timeout；不是任务 oracle 错误的证据。

Sol 用当前 source-bound 纯 `PandaKinematics` 对原 trace 的 227 个 pre-step 具名关节状态计算 FK，位置与该边界公开 EE 的最大差为 `6.9556e-16 m`。因此在本记录位置量上，不支持“Controller 模型 TCP 与公开 TCP 点位错配”这个候选解释；这不外推全部姿态、其他 provider 或所有资产映射。

快速/慢速竖直对照保持 plant、reset、R3 和目标不变，仅改变平移速度/加速度：运动 RMS 从 94.04 mm 降至 6.99 mm。快速竖直 24 点的 15 次 joint velocity clip、17 次 lead clamp 与记录一致。这里只能把动态限制识别为运动误差的重要放大项，不能据此解释全部终点残差。

内部诊断 run 的最后一条 row 标为 step738，其 Controller 诊断来自 **pre-step737**。Sol 将 738 条 q_actual 与同 run H5 的前边界逐项对齐，再以当前模型重算 J 和 DLS：

- 当前 R3 的 rotation row weight=0.22、damping=0.02；最小奇异值 `3.703678e-7`，条件数约 `2.38599e6`。
- 加权修正 twist 约 `0.264876`；其在最弱左奇异方向上的归一投影约 `0.9999999999996`。由同一公式重算最大 |qdot_raw|=`0.000197553 rad/s`，与保存的实际 Controller 输出一致；J·qdot 范数仅 `2.48315e-7`。
- 最后100 tick 的实测最大 |qdot|=`0.000338233 rad/s`；持续约50.6 mm位置残差，延长 hold 未消失。这个记录已显示当前加权任务请求被局部 DLS 几乎完全抑制。该奇异性描述依赖当前单位、权重、完整关节构型和 pose 约束，不简化为“joint5=0 就是唯一原因”。

这些内部量属于 **4 rad/s** 的内部诊断 run，不能冒充 `_002` 的 2 rad/s 同 run 诊断。`_002` 只是进一步反证“对齐参数足以解决问题”：实测重算 move_above RMS=25.0964 mm，下降段 RMS=3.4480 mm；同 run H5 SHA-256 为 `acae4eb906174adc36a79430e7e441c2f7a4ea69d3aa719a62bc174e67f55883`。

仍待验证的是：固定 resolved Controller/planner 后，只改变姿态路径能否摆脱停滞，并在真实任务 gate/碰撞下产生有效控制与成功。G3 要求具体失效机制和可实施 owner，不要求证明全局唯一根因；上述有界接收据此成立。姿态/waypoint 的干预和修复效果是 2b 的第一项验证，不另开无变化诊断轮。

## 对补充材料的限制和修正

1. 交叉运行和 `_002` 的碰撞关闭由维护者明确要求，但脚本通过 native model 副本和私有诊断访问实现，且使用外部动作重放。它们可用于受控现象比较，不能作为完整 public task/lifecycle 成功参考，不能把“下降段已执行”解释为原 measured gate 通过。2b 的任务成功必须恢复原碰撞和真正 task-owned Solution。
2. `_002` 的 Controller 数值配置对齐已核实；实例 identity 保留 PickCube 资产/模型绑定。合成 observation 只用于生成名义后续点列，不代表真实状态到达该位姿。
3. `control_tracking_followup_001/report.md` 中“端点更稀、段中更密”的一句文字颠倒。源码和实际点距表明端点间距小、空间更密，段中间距大。原 raw 不改，本复审记录更正。
4. NutAssembly seed19 的当前完整成功是一个精确任务/路线参考，不证明 PickCube 全路径可达，也不把跨任务源码一致当作 resolved Controller 一致。
5. 原包150分钟、MuJoCo-only预算与后续维护者直接授权的实验分别保留。补充实验没有伪装为原包内新 run，没有进入2b；后继包不得继承其临时 monkeypatch、碰撞 mask 或未冻结预算。

## 2b 计划与停止边界

主归属 `FIX_EXISTING`：`pick_cube/solution.py` 的既有目标/点列/阶段形成，`specialization.py` 的既有 R3 profile 与绑定。先采用已核对的 Nut Controller/planner 参数（含显式 settle=0 的调用点、每段 max_steps 和点数派生的 action budget），以相同 source/reset 和真实碰撞做 A/B；A 保留姿态路径，B 只改姿态路径。固定 gate、horizon6000、dt=0.002×5、seed31 和 task lift oracle；不能用修改 reset wrist posture 当作成功。

若 B 支持任务级修复，将策略留在原 Solution；必要时补 stage readiness，不能放松原 gate。下降后若确实出现 gripper latch，先验证 `specialization.make_reference_binding(interval_mode='grouped')`→`reference_env._step` 没有调用现有 R3 `inner_gripper_step` 的条件，再复用已存在 `RuntimeSession.step_control_interval`。不增加第二 physics step，不重写 provider、源 tendon/mimic 或阶段4 effort。

需要 MuJoCo seed31 的同 run task-success、合法完整 lifecycle、Solution completion、原物性/碰撞、记录/独立读回/close 全成立。GeoPhys 和 Isaac 的代表差异单独冻结 preflight/native 预算；依赖/资产未就绪不能算新运行通过。若需提前3a环境方案或其他后续公共能力，返回具体最小依赖决定，不能擅改 pin/requirements、隐式使用不满足声明的环境或放低2b出口。

2a attempt001 保留原自评/报告历史和一次普通包窗口；维护者追加实验以各 suite 和授权消息另列，不重命名抵消运行或窗口记录。2b 用新 attempt001，输入为本次主审文档提交之后的实际 HEAD。维护者转发一个完整包；本次 Sol 不派发、不执行 native，不进入2c或阶段3。
