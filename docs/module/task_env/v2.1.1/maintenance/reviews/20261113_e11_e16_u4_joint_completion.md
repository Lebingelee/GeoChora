# U4：五条完整运行的同次联合证据

维护者于 2026-11-13 明确同意以关闭后的同次 H5 独立读回、caller 的 Solution 完成事实及身份／监督／关闭收据联合判断 T19。实施者完成下述离线核对，**联合证据成立，H5 单文件不自含完整 completion**；独立主审复核和维护者授权下的 U4 有界接收见[独立接收记录](20261113_e11_e16_u4_independent_acceptance.md)。没有更改旧 H5，未重跑物理，不扩大至 G07 或其他 seed。

| 同次运行 | H5 内 Solution completion | 独立读回 T／T+1、任务结果 | 同次 caller 的完成事实 |
| --- | --- | --- | --- |
| PickCube MuJoCo seed31 | 不存在（canonical v0 无 Outcome） | 960／961，success true | done true、failed false，close 成功 |
| PickCube GeoPhys seed31 | 不存在（canonical v0 无 Outcome） | 951／952，success true | done true、failed false，close 成功 |
| Nut MuJoCo seed19 | 不存在（canonical execution v2 无 Outcome） | 2377／2378，success true | done true、failed false，原严格 completion 与 planned 成立，close 成功 |
| Nut GeoPhys seed19 | 不存在（canonical execution v2 无 Outcome） | 2442／2443，success true | done true、failed false，原严格 completion 与 planned 成立，close 成功 |
| PickCube Isaac PhysX CUDA seed31 `solution-002` | 存在但为 null（v3 Outcome） | 951／952、4755 显式子步，success true，lift 105.254 mm | done true、failed false；native IO、USD lease、App close 有回执 |

CPU 的 `stop_reason=pass` 和任务 success 不用作 Solution 完成证明。四个 canonical 文件的完整逻辑 JSON 对 `solution_completed`、`expert_complete`、`planned_trajectory_completed` 递归检查均无字段，独立主审记录见 ignored `workspace/maintenance/v211_e11_e16_independent_review_0506ae26/cpu-h5-completion-audit.json`。现有 `association-verified-v2.json` 的 `NOT_CHECKED` 表示旧关联器未检查，并不表示字段存在；原输出保持不变。

新 Isaac caller 最后一次 `env.step` 返回 `terminated=false`、`truncated=false`，此后 caller 主动结束记录。既有 recorder 在此情形写入 `external_stop`、Outcome `truncated=true`、`solution_completed=null`；这与 caller 最后一步的标志不是同一事实，不能从该投影反推 Solution 完成。完成事实由同次原 caller 读取 `solution.done`／`failed` 并写入结果。调用代码、受监督 argv、seed、horizon、H5 SHA、episode、Controller／Solution 身份、边界数及 App 关闭收据均关联；隐式 startup／reset 步数仍为 unknown。旧 `pick-isaac-r3` 1000 步失败及其不完整 SDK 关闭日志作为历史诊断保留，不与成功 run 合并。

可复算入口位于 ignored `workspace/maintenance/v211_e11_e16_u4_joint_20261113_001/`：`offline_guard_runner.py` 禁止 provider／SDK 导入；对四个原 H5 依次运行原 `read_pick.py`／`read_nut.py`；`read_isaac_solution.py` 读取关闭后的新 H5 并检查 typed witness、动作、任务谓词、时钟、T/T+1 与 4755 连续子步；`compile_joint.py` 核对同次关联、日志、监督、计划及 caller 源身份，输出 `joint-evidence.json`。五条正式完整记录均为 state-only；腕部图像来自单独的受控夹持对照，不替代正式 Solution，见[夹爪返工报告](20261113_isaac_gripper_rework_ef10e348.md)。原始结果各用各自冻结源码与配置，四条 CPU 并未在最新 HEAD 重跑。

T20 影响补充：`0506ae26` 修改 Isaac 相机移动挂载／状态同步与 PickCube 就绪语义，不能沿用 U3 当时“本批未改 renderer”推断这次代码未变。该提交的 Isaac 腕部 RGB 对照、240 项 guarded pure/fake 及原生三路／cross 历史证据分别保持其 source、配置与覆盖范围；本轮不声称 MuJoCo／GeoPhys 移动挂载或所有 Controller 图像路线通过。
