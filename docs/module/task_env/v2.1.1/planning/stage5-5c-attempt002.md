# G05 5c attempt002 — 通用任务接线返工准备

状态：待维护者批准，准备本身不启动 attempt；5c 已执行一次且仍未接收。继承 attempt001 的四条 PickCube 有界证据和独立主审；不得仅凭本计划声明能力通过。

返工面向不依赖 Panda Position profile 的公开任务 RGB 接线、声明驱动的 GeoPhys 灯光及实际不支持能力的清楚拒绝。Env 创建时选择 renderer 并保持至 close；同步 observation 和 GeoPhys physics × MuJoCo renderer 仍是原定目标，同一 Env 切换 renderer 已延期。不得为 PickCube、Pendulum 或双轮车特设渲染路径，不重复完整历史矩阵。

`PendulumEnv` 与 `TwoWheelBalanceEnv` 的单环境类均通过 `BaseTaskEnv = SelectedReferenceEnv` 构造；它们采用组件生命周期，并不意味着已有 5c task RGB 支持。优先尝试 Pendulum 的真实有界验证，遇具体限制可尝试双轮车；不因可选第二任务未跑成而自动否定满足原范围的通用证据。真实运行与旧的独立观察图像分开报告。

组件路线使用 runtime assembly、snapshot 和各自 observation builder，现有 task RGB 实现绑定 selected Position 路线；接线需真实覆盖公开构造、reset、step 及 observation，而非仅改变类型检查。保留原 state-only API、现有物理和 Controller 准入；按受影响范围验证，清楚报告实际支持的 renderer 和 source。

维护者允许保留 attempt001 的预算预约和临时目录执行偏差及其未知项，不追加不可恢复的历史调查；见 [Sol 独立主审](../maintenance/reviews/20261108_5c_attempt001_sol_review.md)。执行包、具体预算和必要的 provider 改动均待本次单独批准；用户手工转交，Sol 独立主审。
