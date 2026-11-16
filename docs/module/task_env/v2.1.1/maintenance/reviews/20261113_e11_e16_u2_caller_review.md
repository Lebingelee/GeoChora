# E11–E16 U2 caller 对账（实施自评）

输入 `d0c25ae49afe3e1fceebaa9fa77f35587447976e`，输出为本页所在提交；本页不是独立主审或维护者接收。总账的保护副本不在本轮修改范围。未启动 G06/G07，以下测试不声称原生 batch、训练或新物理资格。

| 项 | 当前事实和证据 | 剩余边界 |
| --- | --- | --- |
| T08 / CALL-01 | 四任务及 scalar/YAML、recording、camera 路由在 `examples/README.md` 列出；普通 PickCube Isaac 使用正式配置及已安装 USD，F06 Harness 显式保留其冻结 manifest。Python/YAML 等价及直接 Isaac 成功/失败路径以 fake 检查。 | 直接 Isaac 实际 App、USD 和完整 R3 属 U3；采图仅按已声明能力。 |
| T09 / CALL-01 | 显式 backend 或 `auto` 只调用一次；`auto` 当前选 CUDA，CPU 必须显式选。原异常不触发 CPU 或训练重试，日志分别标记请求和选择；CLI help 写明行为。 | 这不是硬件可用性测试，也不声称 CUDA 原生初始化成功。 |
| T10 / CALL-01 | 普通示例、planning、recording 共用任务/Outcome 投影；Outcome policy 完成与 Harness 严格 Expert eligibility 分别给出。已测试 task failure、truncation、strict lifecycle、execution failure 和 close error；planning 与录制在 close 后报告。 | 实际运行的 validity、原始 Solution、记录和 App close 由 U3 同次证据决定。 |
| T11 / CALL-02 | 四正式 UID 的 local、remote 和直接 framework 工厂在资源前拒绝未实现的 batch；已注册 component factory 仍经旧三工厂边界。fake 检查 SB3 same-step autoreset、terminal observation；renderer 关闭失败时仍尝试关闭 task 和 Runtime，并保留原错误。 | renderer 的具体 native owner 和多 provider batch 未新增资格；G06 不在本轮实现。 |
| T12 / CALL-02 | fresh guard 下检查 agent factory、RSL adapter、PPO 入口导入、Gym space 和合成 H5 的观察转换；旧 Pendulum batch 学习/渲染示例现标示历史依赖。 | 没有训练、Go2 恢复或全面算法验证。 |
| T13 / CALL-04 | LIBERO 保留源、任务谓词、V6 OSC 的 20 Hz 外层/2 ms ×25 子步和夹爪端点；现有 fake replay、身份/单位/clock/close 篡改测试经 guard 运行。独立 reader 重新读取历史 GeoPhys task1 的 95 transitions/96 boundaries 和 MuJoCo task2 的 103/104，均 `verified_complete`、task success false；精确路径、SHA 和命令范围见 ignored `workspace/maintenance/v211_e11_e16_u2_20261113_001/libero-offline-readback.json`。 | 两份是历史 frozen-action 记录，不是本轮原生重跑或任务成功。bench/Core source、controller、Runtime 和 recorder 无本单元 diff。 |
| T14 / CALL-03 | `make_object` 仍由 compiler 和 PickCube/Nut builder 调用；`CanonicalSolutionLifecycle` 属 Solution lifecycle；`ReporterSession` 只在有效回复后委托 env.step；`tree_copy` 供 vector/recording 使用。所选 lifecycle、过期 reply 和 vector fake 检查通过；未见需改写这些 owner 的证据。 | U3 命令、锁、物理上界和资源计划须在真实执行窗口冻结；此表不是运行授权或计划。 |

最近一次固定纯/fake 入口为 **207 passed**，包括 LIBERO fake 契约；另有当前 reader 对两份真实历史 H5 的离线读回。守卫限制见诊断 README。文档 validator 当前仍为原有 2 errors（保护日志基线、历史已退休 source 链接）和 96 历史链接问题；不得称全库通过。本单元计数及验证结果见专用账本第 11 节，后续原生结果及主审分别归 U3/U4。

## U3 调用入口准备

以下命令固定 task、provider、seed、horizon、公开入口与 H5 出口，供 T15 制作受监督运行计划；这些命令**尚未执行**，也不代替锁和资源计划。`RUN` 是 T15 创建的全新唯一目录，标准输出、进程组、日志和独立 reader 输出由监督器保存。当前拟用 Core Python `/home/lly/miniconda3/envs/geochora/bin/python`、Isaac Python `workspace/environments/isaacsim-6.2.0/bin/python`，T15 须复核两者和已安装资产。用户已授权 CUDA 及所需 EULA；实际 Isaac 环境再设置 `OMNI_KIT_ACCEPT_EULA=YES`。

```sh
"$CORE_PYTHON" -B examples/recording/record_expert.py --env-id pick-cube-p16-reference-v1 --provider mujoco --seed 31 --horizon 1000 --output "$RUN/pick-mujoco/episode.h5"
"$CORE_PYTHON" -B examples/recording/record_expert.py --env-id pick-cube-p16-reference-v1 --provider geophys --seed 31 --horizon 1000 --output "$RUN/pick-geophys/episode.h5"
"$CORE_PYTHON" -B examples/tasks/pick_cube.py --provider isaacsim --isaac-python "$ISAAC_PYTHON" --seed 31 --horizon 1000 --controller-profile r3_continuous_v1 --recording "$RUN/pick-isaac/episode.h5"
"$CORE_PYTHON" -B examples/recording/record_expert.py --env-id nut-assembly-outcome-reference-v1 --provider mujoco --seed 19 --horizon 6000 --output "$RUN/nut-mujoco/episode.h5"
"$CORE_PYTHON" -B examples/recording/record_expert.py --env-id nut-assembly-outcome-reference-v1 --provider geophys --seed 19 --horizon 6000 --output "$RUN/nut-geophys/episode.h5"
```

T15 必须根据当前 HEAD、解释器、source、锁、设备与任务配置冻结实际 argv 和独立 reader；物理时间步当前配置为 0.002 s、每 control 5 substeps，计划还须计入 reset/构造和可能的 App 重建，隐式推进未知不能写零。示例的 420 秒及地址空间限制不是完整进程树预算，具体可用性和纠偏留待 T15。
