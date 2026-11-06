# G04/4b attempt001：Sol 独立主审

## 决定

`REWORK_REQUIRED_4B_EVIDENCE_PROVENANCE`：暂不整体接收 4b。唯一当前主审缺口是：三后端逐输入 direct effort 及 MuJoCo 两类 BodyWrench 的关键真实运行使用了中间源码；多个相关文件随后改变，交付包尚未提供这些变化对对应具体路径的完整影响分析，也没有覆盖全部相应路径的最终版本真实验证。**这不是说旧实验未发生、代码一定有物理错误，或必须重跑全部历史矩阵。** 原 4b 本就要求的真实 7＋2 和外力结果，须能关联到待接收实现；可先用可验证的实际源码差异证明对应路径未受影响，确实受影响或无法证明的部分才做最小定向补证。

执行者的技术完成和 Goal complete 是其交付状态，不等于本次 Sol 接收。4a 仍按原范围有界接收；不启动 4c 或阶段 5。该决定不重置 4b attempt 计数；本报告为 attempt001 主审，不自动派发续作。

## 已独立核对和可复用成果

- 当前分支 `codex/v211-stage4`，执行输入 `c111569447ce89254e959b4d60fe250ca90b010b`，执行输出 `a7181de4a454bf95079b9a84c37ad338c66edabb`；GeoPhys `dc2685e28c6c916fb6403a2342c04e0d2520aef7` 与 Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` 未变，三个保护文件 SHA 与输入一致。提交使用 GeoPhys 现有公开能力及 Core adapter，未修改 GeoPhys 或 pin。
- 独立逐项核对输出清单：**5409/5409** 文件及 symlink 路径／摘要匹配；清单自身 SHA 与对应 SHA 文件一致。Sol 在禁止 XML source 解析及 MuJoCo／Taichi／pxr／Omni／Isaac 等 SDK 导入的 guard 下独立运行受影响六组纯测试及 wrench 子步回归，**55 passed**；未运行 source 或 native。文档 current 检查执行者记录为零当前错误，96 条旧历史链接问题不改。
- `native38`／`native39`、`native40` 及 `isaac24`／`isaac25` 的共享 joint／R3 参考对照有真实方向性结果；核对运行记录中的对应受检源码摘要与输出 HEAD 一致。`native40` 的源码摘要位于 `complete` 记录，其两个 `result` 记录分别给 joint 和 R3 结果。结果限定 source、隔离的 native drive、固定局部质量模型、初态、采样与信号判据，不是独立测力，也不代表通用任务成功。
- `native27`、`native30`／`native31`、`isaac13`／`isaac15` 原始结果分别列出 8、4＋4、4＋4 个方向 gate，均为 `PASS_DIRECTION_ONLY`；`native04` 为 hand 外力方向响应，`native05` 为逐子步投影、叠加及 clear/reapply 写入核对，`native11` 为自由体冲量，最大线／角速度误差分别约 `5.56e-17 m/s` 和 `8.89e-15 rad/s`。这些运行在各自运行内的前后代码摘要相同，预注册脚本摘要及其登记时间与所查原始记录匹配；它们可作为对应中间版本的有界真实证据，不把 ACK 称为实测力。
- 原 Isaac 方向失败、接触无效、早期退出故障及最终 `get_stage_state` 关闭异常由执行者保留；最终参考运行有 owner close receipt 与退出码 0，但不称无异常关闭。执行期间误读私有字段的搜索记录见执行者 `boundary-events.md`，其报告称未用于实现；该越界历史不抹除。用户曾授权 source/native 各从 180 增至 360 分钟，账本保守记为约 67.5／67.1 分钟和 3263 物理子步；先前把分钟误记为秒的事件保留。

## 需要闭合的证据身份

对每次运行 `result` 或 `complete` 的 `code_sha256` 与输出 HEAD 实际文件逐项比较：

| 原门与证据 | 与最终实现的身份差异 | 不能自动推出的结论 |
| --- | --- | --- |
| MuJoCo hand `native04`／`native05` | 六个记录的 Core 文件摘要均不同，包括 `reference_env.py`、`mujoco.py`、`mujoco_physical.py` 与对应 profile/builder | 本轮运行发生于较早代码；最终版本 hand 外力和合批的相同路径是否全部不受改变影响，须逐项证明或补证。 |
| MuJoCo free body `native11` | 十项中七项不同，涉及 `api.py`、`mujoco.py`、physical port、profile/builder 与 selected Env | 自由体冲量结果有效地证明了该运行版本，不能直接当作最终版本该目标已运行。 |
| MuJoCo direct `native27` | 九项中四项不同，包括 selected Env、physical port、PickCube candidate 与 physical profile | 最终 `native40` 覆盖了同一后端的 joint/R3 控制器，但其两个对照不是原冻结的八个 direct-effort 基向量。 |
| GeoPhys direct `native30`／`native31` | 各七项中四项不同，包括 Core boundary、GeoPhys physical port、physical profile 与 selected Env | 最终 `native38`／`native39` 是隔离 drive 的参考 Controller，不等于逐项证明此前 drive coexist 的八路 direct case。 |
| Isaac direct `isaac13`／`isaac15` | 各十项中 `isaac_native_io.py` 与 `physical_isaac_candidate.py` 摘要不同 | 最终 `isaac24`／`isaac25` 是参考 Controller 对照；不自动证明最终 direct 候选的八个基向量。 |

例如，`native05` 使用的 MuJoCo physical port 与 4b 输入提交的该文件一致；最终文件新增了针对 no-drive Artifact 的 drive 模式选择和隔离分支，**不是一见文件摘要变化就断言 hand 路径坏了**。执行会话的编辑记录还显示，后续涉及新 Controller 模式及 Isaac 接触读回等变化。应以运行时版本的可恢复源码、完整变更记录及调用／配置为依据，对每条路径列出变化及适用条件；无法恢复足够差异时保持未证实，不能仅凭源码文件名或结果数值相似认定不受影响。新 source fixture 测试只证明对应构造／声明，不替代受影响的物理响应。

## 最小闭合方式

1. 对上表列出每条证据从其运行时源码到 `a7181de4` 的可核验差异，核查对应 Artifact、profile、adapter、writer、clear、读回及判据是否进入更改分支；给出证据与具体理由。不要重算无关输出或重新开启 3b/3c。
2. 仅对实际受影响、或无法以可信版本差异证明不受影响的原门，用同一已授权的三后端窗口规则和双锁执行最小定向真实验证；按需保留原八基向量的完整覆盖或只补缺失基向量，外力只补受影响的 hand／free-body、合批／清理部分。先冻结 source、代码身份、oracle 和资源；继续保留旧正负实验。
3. 原 4b 的饱和、cadence、重复 PD 拒绝与 source 限制应逐项列证据及适用后端。分别给出 `PASS`、有限制或未测，不将位置 drive 力、写入 ACK 或计算力标为独立传感测量。完成后给出新的输入／输出 HEAD、清单、释放收据，再由 Sol 主审；不是先行进入 4c。

已有两个 provider pin、三项保护文件、4a 结论与阶段 3 限制保持不变；装配 Panda 不作为 4b 新前置门。
