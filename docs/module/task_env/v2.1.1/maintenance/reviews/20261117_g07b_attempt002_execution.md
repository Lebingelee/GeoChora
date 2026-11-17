# G07 7b attempt002 执行返包

**PARTIAL；待独立审阅，尚非 7b 完成候选。** 输入 HEAD `4fdf9379482af6bb913eb1a6587316e64b6a0fed`；旧九格生产输入 `78349184d0600e2fb804e6461930c475bfcc67c1`，原证据按其身份有界复用，未重跑。详细单一工作报告、逐次冻结、原始失败、H5、独立读回和资源收据保留于 `workspace/maintenance/v211_g07b_attempt002/`，入口为 `report.md`、`results.json` 与 `reuse-and-impact.md`。

| 门／案例 | 原 owner、最小修复及证据 | 结论与限制 |
| --- | --- | --- |
| B2-1 共同准入／提交 | source composition、physical admission 和 worker transport 绑定声明的 caller producer；`native-reject-moment-001`、`mjwarp-reject-002` 零步拒绝 | 有界通过，仅限声明的 source、body、writer 及受测边界。 |
| B2-2 MuJoCo 手部与自由体 | 原 physical owner 刷新受力；`mujoco-hand-hold-003` 两构型对公开 Jacobian，误差最大 2.22e-16；`mujoco-zero-response-002` 与独立质量／惯量 oracle | **部分完成**。生产 implicitfast FREE 角向 armature 的力矩存在原生异常，现写入前拒绝；新建零阻尼／零 armature 诊断 source 的资格待独立审阅，不能冒充原输入。 |
| B2-3 其他 provider | GeoPhys FREE `geophys-response-003`、Isaac `isaac-response-001` / `isaac-free-response-001`、MJWarp `mjwarp-response-recorded-005` 各有真实响应及独立读回 | 有界通过；仅受测 source、body、reset、载荷及设备。 |
| B2-4 记录与生命周期 | 原 Recorder／reader 保留贡献、binding 与 native ACK；`mjwarp-reset-004` 载荷后同一步 reset 与无残留对照，独立读回 | 有界通过；不能外推 B1 以外。 |
| B2-5 普通 caller／无载荷 | 三 scalar examples 独立读回，`mjwarp-no-load-002` 正常推进与 close；`affected-regression-001` 115 通过、3 失败 | **部分完成**：3 项旧 fixture／退休入口失败未迁移；更宽旧回归 15 通过、28 失败，不能报全绿。 |
| B2-6 影响与返包 | `reuse-and-impact.md` 逐项保留输入和范围 | **部分完成**；剩余门需判定及独立主审，不自动进入 7c。 |

此实现沿共同 source、场景 interval、绑定、提交及既有 recorder owner；分别记录真实 Controller 动作与 caller 载荷，未宣称任意多 Controller、任意载荷或 provider 组合。总账关联：CTRL-01/02/05 为选择及动作语义，SRC 为 source／body 绑定，RUN 为单次提交、隔离和清理，REC-01/02/03 为同运行身份和读回；逐次事实与失败在工作报告中。

原生数值异常的同源 MjData 对照显示 `mj_forward` 与 `implicitfast` `mj_step` 的角加速度不一致；它不能证明上游根因，也不授权更换 source、积分器或依赖。受保护 `MUJOCO_LOG.TXT` 保持原字节；文档校验的既有 protected-input 基准差异须单列。最终提交及锁释放回执见工作报告，不构成维护者接收。
