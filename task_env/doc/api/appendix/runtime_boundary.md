# Runtime boundary

**Import path**：`task_env.RuntimeBoundary`、`task_env.runtime`  
**任务域**：Appendix  
**稳定性**：Advanced boundary  
**职责**：解释环境、运行会话、进程传输与 provider 之间的所有权边界。
**调用者/消费者**：统一环境的组件任务和 runtime bootstrap；selected 任务使用 RuntimeSession 接线。
**源码**：`environment/protocols.py`、`runtime/`

## `RuntimeBoundary`

**Kind**：Protocol；**Defined in**：`environment/protocols.py`

成员包括 `apply_reset_state(state, *, static_world_child_poses=None)`、`apply_control(command)`、`set_actuator_force_limits(actuator_ids, limit_N)`、`step(*, substeps)`、`read_snapshot(request)`、`snapshot_state()`、`restore_state(state)`、`prewarm(profile="interactive")`。这是 framework integration contract，而不是用户控制入口。selected 的 `RuntimeSession`／provider adapter 使用不同的 artifact、source 和 control contract；两种运行时组件接入同一 episode owner；不把该 Protocol 描述成所有 provider 共用的物理接口。

`GeoPhysRuntimeBoundary`、`TaskRuntimeBootstrap`、`bootstrap_task_runtime` 是 advanced runtime API；不将 solver 内部布局、Taichi field、private runtime 方法、`ctrl` 或 `qpos` 写成 planner/recorder 可访问路径。

## Selected 运行链与资源寿命

普通调用从 [`make_env`](../../../registry.py) 开始。配置解析和共同 builder 建立 Task、Robot、Controller 及 source 的匹配；reset 将 source 物化到 provider 的 `RuntimeSession`，产生 episode 与边界。`step` 由环境准备 action，经 Controller 计算和公共场景提交，provider adapter 将 typed 命令降低到对应原生接口，推进后发布 snapshot。Recorder 消费同一边界，不负责推进。`close` 释放 session、worker 和 recorder 资源；异常时也应放在 `finally`。reset 或重新物化后的旧绑定和旧边界不能再用于新 episode。

`task_env.runtime.sessions`、`runtime.transport` 和 `runtime.providers` 是实现者阅读入口，不是要求应用自行构造的稳定 factory。isolated worker 使用既有 typed IPC 传递 source、状态、命令与 ACK；in-process 不经过 IPC。ACK 只证明接受提交，实际响应仍须查看公开状态。支持范围以[版本 API](../../../../docs/module/task_env/v2.1.1/api/README.md)和[能力矩阵](../../../../docs/module/task_env/v2.1.1/capabilities/capability-matrix.json)的具体交集为准。

## 同一间隔的场景载荷

通过配置 `scene_body_producers` 声明 writer 与具名 source body；reset 后 `env.physical_scene_context()` 提供当前边界及已绑定 body。`BodyWrenchV1` 使用声明的 frame、作用点、力（N）和力矩（N·m），再以 `env.step(action, scene_body_wrenches=(wrench,))` 与 Controller 的 joint effort 在同一间隔提交。组合、冲突、饱和和写入归已有 typed compositor 和 adapter，调用者不直接相加原生 buffer。interval 结束后载荷由其 owner 清除；每次 step/reset 后应重新取得 context。未声明 writer/body、过期边界及不支持的 source 均应拒绝。

力和力矩可各自声明表达 frame，作用点与矩参考也必须随命令明确；把力平移到参考点时，总矩包含力臂叉乘力。相同 body 的贡献只有在声明允许组合、effect 身份不冲突且同一 interval 范围内才可合成。MuJoCo、GeoPhys、Isaac 和 MJWarp 各由自己的 provider adapter 降低为其可用的 native 载荷接口；设备路线的 `DeviceBodyWrenchCommand` 同样绑定实际 device boundary，不将 scalar 对象直接视作批量接口。Recorder 分别保存 action Controller 和 scene producer 的贡献、binding/ACK；ACK 不是物理响应 oracle。

以下完整的公开示例声明独立 writer，并记录一次场景载荷：

```python
from pathlib import Path
import numpy as np
from task_env import make_env
from task_env.controllers.canonical.physical_commands import BodyWrenchV1, ContributionPolicyV1
from task_env.recorders import load_physical_recording_h5

path = Path('scene-load.h5')
env = make_env('pick-cube-p16-reference-v1', config={
    'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu', 'deployment': 'in_process'},
    'controller': {'profile_id': 'panda-direct-effort-v1'},
    'robot': {'native_drive': 'disabled'}, 'episode': {'horizon': 8},
    'scene_body_producers': [{'writer_id': 'load', 'producer_kind': 'caller',
                              'body_keys': [['cube-v1', 'PickCube']]}],
})
try:
    env.reset(seed=31)
    context, bodies = env.physical_scene_context()
    body = next(b for b in bodies if (b.entity_id, b.body_id) == ('cube-v1', 'PickCube'))
    frame = body.body_frame
    policy = ContributionPolicyV1('physical-contribution-policy-v1', 'load-1',
                                  'effect-1', 'load', 'exclusive', 'reject_outside', 'one_interval')
    wrench = BodyWrenchV1('body-wrench-v1', context, policy, 'cube-v1', 'PickCube',
                          frame, (0., 0., 0.), frame, (0., 0., 0.), frame,
                          (0., 0., 1.), (0., 0., 0.))
    env.start_recording(path)
    env.step(np.zeros(8, dtype=np.float32), scene_body_wrenches=(wrench,))
    env.finish_recording('external_stop')
finally:
    env.close()
record = load_physical_recording_h5(path)
print(record['transition_count'], record['observation_count'])
```

示例改写自[正式 caller](../../../../examples/tasks/scene_body_wrench.py)，本页代码本轮尚未单独运行；已有受测证据及 provider、frame 限制见 [7b 独立主审](../../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261117_g07b_final_acceptance.md)。MuJoCo 原 FREE 角向 armature 的受限力矩组合仍在写入前拒绝；零 armature 诊断 source 的通过不消除该限制。记录中 Controller 和场景 producer 分别归属，独立 reader 与 caller 的 close 事实需关联同一次运行。

### Optional contact-pair extension

When `SnapshotRequest.contact_summary` is true, the boundary may call an optional public peer method `read_contact_summary()`. The returned value must be a `ContactSummary`; any other type raises `TypeError`. A peer without the method yields `ContactSummary.unavailable("provider_contact_pair_query_not_implemented")`. This extension is not a required member of the `RuntimeBoundary` Protocol and does not admit a provider or task. The current GeoPhys peer does not implement the pair query, so its contact result remains unavailable; callers must not convert unavailable evidence into `False`.
