# Grouped trajectory CLI

统一入口是：

```bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory collect --env_id pick-cube-v1 --num-traj 4 --output pickcube.h5
PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory replay --trajectory pickcube.h5 --replay_config replay.yaml --output pickcube-replay.h5
PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory merge --input_dir ./trajectory_parts --output merged.h5
```

`collect` 生成一个 H5，内部为 `traj_000`、`traj_001` 等轨迹组。每组都有自己的 `obs/*`、`action/*`、`universal_action/*`、`meta/env_cfg` 和 `meta/env_meta`。

collect source 必须使用 `robot.controller.kind=absolute_pose`、`reference=world`。replay 默认 `simulator=auto`：没有目标控制器或 observation 改动时只复制 grouped 数据；发生改动时加载仿真器。`replay.yaml` 可设置 `target_controller`、`env_overrides`、`simulator`、`save_failures`、`reward_mode`（`defined` 或 `sparse`），以及 `observation.keys` 选择目标 observation 的 dotted paths；`observation.params` 中的 `schema_version`、`include_privileged_state` 可覆盖环境 observation 配置。

`merge` 读取目录下所有 `.h5` 并保留每条轨迹的独立 metadata，不把多个 episode 拼成一个时间序列。
