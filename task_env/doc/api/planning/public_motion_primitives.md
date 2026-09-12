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
