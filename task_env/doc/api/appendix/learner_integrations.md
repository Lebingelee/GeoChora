# Learner integrations

`task_env.alg` 是可选的 learner boundary，不参与 TaskEnv 核心 import。

## SB3

`task_env.alg.sb3.runner` 只负责构造/运行 SB3 PPO；结构化 observation/action 的 flatten 仍由已有
`task_env.utils.SB3FlattenVecWrapper` 完成。

## RSL-RL

`task_env.alg.rsl_rl.adapter.TaskEnvRslVecAdapter` 将 raw homogeneous vector contract 映射为 RSL-RL
`VecEnv` 所需的 `get_observations()` 与 `step()`。`terminated | truncated` 是 RSL `dones`；只有
`truncated & ~terminated` 进入 `extras["time_outs"]`。

learner 动作语义由同模块下的 `profiles/*.yaml` 和
`RslActionTransformSpec` 管理，不放入公共 `contracts.py` 或 Go2 task config。
`rsl_ppo.py`、`go2/go2_ppo_eval.py` 和独立 MuJoCo policy evaluator 从任务 YAML 解析
`unitree_go2_reference`；其他任务未声明 profile 时回退到自身 `single_action_space`。

RSL-RL 生产路径固定使用 current-5 TensorDict API；legacy 1.x 只在 `diagnostics/go2` 下做隔离探针。
`host_numpy` 适合
`RemoteBatchVecEnv` 的显式进程边界；`transfer_mode="device"` 只有 runtime 提供公开
`step_device` capability 时才可用。learner contract 必须声明 observation/action flatten order、dtype、
normalization policy 和 schema id。版本化 checkpoint 兼容性只能通过
`task_env.diagnostics.go2.checkpoint_compat` 的 tensor-only schema 检查后加载。对于 Go2 的
48/12 非循环 MLP，`PolicyArchitecture`（含 layer shape、activation、normalization、std 参数化和 action scale）
与 `convert_legacy_to_current()` / `convert_current_to_legacy()` 提供显式双向 key/layout 转换；它只迁移 actor/critic 张量和 manifest，
不会伪装迁移 optimizer/RND 状态。开发者可用 `task_env.diagnostics.go2.checkpoint_convert` 生成 inference artifact，
`task_env.diagnostics.go2.legacy_runner_probe` 已在 adamanip Python 3.8 中通过真实 legacy
`OnPolicyRunner` 的 48/12 save-load-inference smoke；它只在内存中为已知的
`distillation.py` PEP604 注解加 postponed-annotation shim，不修改 site-packages。
固定 48-d observation 的 current/legacy action parity 已通过脚本化 compare（最大绝对误差约
`8.2e-8`，`atol=1e-5`）；该结果只覆盖 actor tensor/schema/inference，不等同于 optimizer/RND
状态迁移或 walking policy 收敛。

device 路径有明确的公共转发点：`BatchTaskLifecycleAdapter.step_device()` 只有在 runtime 的
`step_device`、task 的 `build_device_observation/evaluate_device` 与 action adapter 的
`convert_device_batch` 同时存在时才可用；缺少任一项会返回 capability error，不会暗中把每个 physics
substep 转成 NumPy。RSL bridge 只包装这个命名 transition，仍不访问 Taichi field。Go2 已在私有 task/robot
边界声明这些 hooks，并可用 `transfer_mode="device"` 做固定 tick 与 horizon-boundary autoreset smoke；reset
sampler 只在 episode boundary 按 mask 注入状态；Go2 task-owned command schedule 仍按 Unitree reference
在每 500 个 policy tick 重采样 command/heading，使用 host RNG counter 但不读取 CUDA physics state，
因此 observation 与 tracking reward 在同一 tick 使用新 command。physics substep 仍无 NumPy readback。Go2 用户入口默认选择
static/device/local；flatten 或 remote 时显式使用 host_numpy。CUDA fused kernel 与 local-ground pipeline health 已有证据，但接触后的多步三端
forward/reward/done report 和 walking acceptance 仍是后续门禁。

device lifecycle 的 `elapsed_steps` 与 learner `episode_length_buf` 保持在 device；正常 policy tick 只做
terminal 标量探测，不复制完整 `(B,)` mask。只有发生 terminal 时才将 mask 读回，调用 reset sampler 并附加
`terminal_observation`，因此 reset 边界的低频 host exchange 不会退化成每 tick 的 bulk readback。

`BatchTaskLifecycleAdapter` 在构造期生成一次 task-agnostic `DeviceFieldPlan`。通过 raw local vector 的
`device_field_plan` 属性或环境 metadata 可以查看版本化的 named state fields、owner、device、reset policy、
terminal policy、execution/transfer provenance 和 capability reasons；该计划不包含具体 task 的
reward/observation algebra。device tick 复用
计划中的 state-field tuple 与已解析的 runtime/action/task hooks，缺少能力时保持 host/NumPy 路径并明确拒绝
device transfer，不做隐式 fallback。local device 路径报告 `execution=local, transfer_mode=device`；
RemoteBatchVecEnv 报告 `execution=remote, transfer_mode=host_numpy, available=false`，但仍保持远程
host lifecycle 可用。

Go2 的私有绑定位于 `task_env.robots.go2` 与 `task_env.tasks.go2_walk`，并提供
`script/rl/rsl_ppo.py`、`script/rl/go2/go2_ppo_eval.py`、`script/rl/go2/go2_mujoco.py` 与
`task_env.diagnostics.go2.isaac_ppo_reference`；开发者诊断模块
位于 `task_env.diagnostics.go2`。这些入口已经固定 48 维 observation、12 维 native PD action（Unitree
参考实现的 `clip_actions=100`）和
sim/rl device 参数；Isaac/MuJoCo/GeoPhys 的同状态 obs/PD contract smoke 已通过并记录一 tick envelope，
该 tick 的非接触 reward/done 逻辑也完成了三端数值 smoke；接触起始 envelope 与 B=1/B=2 slot-0 隔离
已有独立 smoke，但它明确不宣称 soft-contact 数值 parity。接触后的多步三端 report 与 PPO walking
acceptance 仍未完成。

`task_env.diagnostics.go2.isaac_contact_oracle` 还提供了 adamanip PhysX 的同状态接触窗口。它显示 Isaac 与
MuJoCo 在接触 onset 的差异较小，而当前 fused GeoPhys hard ERP/PGS 的支撑响应明显更强；
因此后续 compliance/solref/solimp 映射不能以“Isaac 也有同样偏差”作为默认解释。该 trace
是诊断证据，不是 contact parity 或 walking acceptance。

`task_env.diagnostics.go2.three_contact_oracle` 将该 Isaac trace 与 geophys 中的 MuJoCo/fused trace 聚合为
一个可审计 JSON；当前报告确认三端接触 onset 都在 tick 4，且 GeoPhys B=1/B=2 的接触
workspace slot-0 保持隔离。接触后的 state envelope 仍只作为测量记录，不能替代最终
compliance 和 walking acceptance。报告同时保存每 tick 的 canonical observation、任务
reward、terminated/truncated 及 reward terms；其中接触后的 reward 差异是待解释的三端
语义/physics envelope，而不是已通过的 parity 门禁。

CUDA 的 B=1/B=2 接触隔离使用固定 local row solve 的 f64 中间精度，公共 learner state
仍是 f32。该处理消除了 batch-size-dependent batched solve 舍入在长接触窗口的累积：八
tick smoke 的最大 slot-0 qpos/qvel 误差为 `7.45e-9`/`7.15e-7`，并继续使用原有
`1e-6` 隔离门禁；它属于通用 static runtime 数值稳定性，不是 Go2 专用逻辑。

当前 static-template 路径把 Jacobian 的 sparse local slot/DOF indexing 固定在 immutable template，并
提供 generic ordered row-PGS CUDA kernel：一个 world program 内的 DOF 可以并行，但 slot 仍严格
ascending，故没有改变 Gauss-Seidel 到 Jacobi 的算法语义。Triton 不可用时 runtime 使用同一 row
顺序的 eager fallback；`torch.compile` 不属于该路径，也未被启用。

`script/rl/go2/go2_ppo_eval.py` 是与 runner 对应的 held-out report entry：它默认加载 current-5
checkpoint，重新走 `make_parallel_env()`/`TaskEnvRslVecAdapter`，并记录 episode return/length、
termination/timeout、seed、sim/rl device 和 transfer mode。导入顺序会在 Taichi 初始化前加载
Torch/TensorDict，避免 Triton lazy import 与异步 logger 的进程崩溃；报告仍标记为 learner
probe，不能替代三端 walking acceptance。

`script/rl/go2/go2_mujoco_eval.py` 是独立 MuJoCo actor rollout entry：它只加载 current-5
`actor_state_dict`，通过 `--env-id` 选择 `go2-walk-v1` 的 48D、`go2-walk-deploy-v1` 的 45D 或
`go2-walk-deploy-height-v1` 的 46D observation contract，复用 12 维 native action（clip 到 ±100）和四个
physics substeps，输出 `eval.json`/`eval.h5`，可选 `mujoco.viewer` 与 `--realtime`。该报告只
记录 policy/physics trace，不伪造 GeoPhys reward、`terminated` 或 `truncated`，也不替代
`go2/go2_ppo_eval.py` 的 TaskEnv held-out 评估。

`script/rl/rsl_ppo.py` 的 `train.h5` 使用 `task-env-rsl-ppo-run-v4`；它既保存
RSL-RL scalar ledger，也保存按 PPO iteration 对齐的 `ppo_values`/`ppo_metric_names`。
`Train/mean_reward` 与 `Train/mean_episode_length` 在没有 completed episode 的 iteration
会明确写 NaN，并同时记录 completed count、rollout mean 和 partial active-episode 指标，
并保存 total steps、iteration time、elapsed time 和 ETA，以区分“尚未产生 episode”与“日志缺失”。
当 transition extras 提供 `reward_terms` 时，logger 还会在同一 PPO iteration 写入独立的
`Reward/total` 与 `Reward/<term>` TensorBoard 曲线；这些值是 rollout transition mean，
不是 completed-episode return。height-deploy 当前 term 还包括 `feet_air_time`、
`foot_clearance`、`effective_swing` 三项 gait shaping。reward term 聚合保留在 learner
device，iteration 边界只做一次紧凑 readback，避免在仿真 tick 中引入逐项同步。
训练入口的 `--resume [CHECKPOINT_OR_RUN_DIR]` 会恢复 current-5 的 actor、critic、optimizer 和
`iter`，随后从 `iter + 1` 开始；省略参数值时自动选择 `--output-dir` 下编号最大的 `model_N.pt`，
并兼容旧的 `tensorboard/model_N.pt`。当前 RSL-RL 生成的周期 checkpoint 只保留在 experiment
root（例如 `model_24.pt`），TensorBoard 目录只保存 event 文件，因此不会产生重复权重；旧运行
目录中的 `tensorboard/model_N.pt` 仍可被 resume 逻辑读取。恢复训练不会覆盖原有 `train.h5`，而会写入
`train_resume_from_<next_iteration>.h5`，TensorBoard event 则继续写入同一个实验目录。
恢复路径还会关闭 `init_at_random_ep_len`：该随机 episode-counter 只在新训练首轮使用，不能在
未保存 simulator state 的 resume 进程中重复应用，否则会让刚 reset 的 world 被错误标记为接近
horizon 并造成短期 reward/episode-length 假下降。

`task_env.diagnostics.go2.reward_alignment` 是 task-owned 的 reward algebra report：它将
`unitree_rl_gym` 的 raw reward scales 与 Go2 active scales 对照，并在 canonical no-contact
state 上以独立公式复算。该报告只证明 reward term/scale/dt/sign 一致，不声称 observation
noise、heading-derived yaw command、friction randomization 或 push domain randomization 已
实现；参考 `feet_air_time` 还是逐 foot force、collision 还是 selected-body force count，
当前运行时已经保留每个足部/选定碰撞 body 的 contact-active 身份，但尚未暴露
Unitree 参考实现使用的接触力阈值（足端阈值为 `>1`）与接触力计数；这些设置差异必须
在跨引擎 rollout 结果中单独记录。

`task_env.diagnostics.go2.isaac_ppo_reference` 只在 `adamanip` 执行 legacy 25-iteration reference
training；其 checkpoint 可先经 `task_env.diagnostics.go2.checkpoint_convert` 做 tensor-only legacy→current
转换，再交给 `go2/go2_ppo_eval.py` 在 GeoPhys static profile 中做 held-out probe。该流程用于
区分 checkpoint/load、reward algebra 和 physics/rollout gap，不能把 `mean_reward > 0.01`
本身当作 walking acceptance。

当前提供的 `adamanip` 探针还显示：其 Python 3.8 环境中的 `rsl_rl 1.0.2`
源码在普通导入时使用未延迟求值的 PEP 604 类型联合，因而会抛出 `TypeError`；
`legacy_rsl_compat` 只对该模块在内存中启用 postponed-annotation shim 后，真实
`OnPolicyRunner` 的 save/load/inference 已通过。这个兼容处理不修改外部环境；
diagnostic fingerprint 会同时保留原始异常与 shim 范围，不会将它误报为缺少 RSL-RL。
