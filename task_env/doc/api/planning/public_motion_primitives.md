# Public motion primitives

**Import path**：`task_env.planners`  
**任务域**：Task Planning  
**稳定性**：Public API  
**职责**：生成独立于具体任务的公开 action 序列。  
**调用者/消费者**：solution 或用户，再交给 `env.step()`。  
**源码**：`planners/joint.py`、`cartesian.py`

## `JointPositionPlannerConfig` / `JointPositionPlanner`

**Kind**：frozen dataclass / class；**Defined in**：`joint.py`

config 默认限制每 step 的 joint/gripper delta 与 acceleration，并有 `settle_steps=48`、`max_steps=400`；非法非正限制、负 settle 或小于一的 max steps 抛 `ValueError`。`JointPositionPlanner(config=None)` 提供 `plan_to_joint_positions(...)` 与 `plan_gripper_transition(...)`，返回 float32 `(T, 8)` absolute-joint public action。joint 输入须为有限 `(7,)`；超出 `max_steps` 抛 `ValueError`。

## `CartesianPosePlannerConfig` / `CartesianPosePlanner`

**Kind**：frozen dataclass / class；**Defined in**：`cartesian.py`

用于生成 Cartesian pose waypoint public actions。签名、默认值和 pose contract 以 `cartesian.py` 为准；源码将 pose 规范化为位置加 wxyz quaternion，零范数 quaternion 抛 `ValueError`。它只生成动作，不执行环境。

`plan_to_pose(*, current_pose, goal_pose, steps=None, gripper=1.0, max_translation_per_step=None, max_rotation_per_step=None, settle_steps=None)` 消费七维 xyz（米）与 wxyz 姿态并返回每行八维 pose/gripper 数组。每行对应调用方计划的一次控制边界，实际秒数由目标环境的 control dt 决定；平移与旋转上限按每步米和弧度解释。调用方必须确认目标 Controller 接受该 schema，不要把关节数组传给 pose Controller。

```python
import numpy as np
from task_env.planners.cartesian import CartesianPosePlanner

planner = CartesianPosePlanner()
start = np.array([.50, 0., .60, 1., 0., 0., 0.])
goal = np.array([.51, 0., .60, 1., 0., 0., 0.])
actions = planner.plan_to_pose(current_pose=start, goal_pose=goal,
                               steps=20, gripper=1., settle_steps=0)
assert actions.ndim == 2 and actions.shape[1] == 8
print(actions[-1])
```

该示例只计算参考，不打开环境、求解碰撞或证明到达。若将其用于已构造的兼容环境，调用方应逐行 `env.step` 并根据终止／反馈提前停止，最终 `close`；不要直接写 ctrl/qpos。序列耗尽与事件驱动 Solution `done`、Task success 分开评估；非法形状或零四元数会抛出异常。此片段已在本轮受监督的无物理步骤脚本中执行，受测 Task/provider 列表见版本矩阵。

[Planner implementations](../../../planners) own these geometric calculations; the environment owns native execution.
