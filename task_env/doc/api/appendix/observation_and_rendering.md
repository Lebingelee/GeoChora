# Observation and rendering

**Import path**：`task_env.observations`
**任务域**：Appendix
**稳定性**：Public API / Advanced boundary
**职责**：从一次公开 snapshot 构建 state、RGB、depth observation。
**调用者/消费者**：classic `BaseTaskEnv` 及 selected 路线。
**源码**：`observations/state.py`、`observations/camera.py`、`observations/capture.py`、`observations/selected_reference.py`

## `StateObservationBuilder`

**Kind**：class；**Stability**：Advanced boundary；**Defined in**：`observations/state.py`

构造签名：`StateObservationBuilder(*, references: TaskReferences, config: ObservationConfig, render_config: RenderConfig)`。`observation_space` 与 `schema` 是只读属性，`build(snapshot, sensor_observation=None)` 生成 observation。key、shape、dtype 由 `ObservationSchema` 的实际 fields 声明；不要猜测固定 key。

## `CameraSensor` / `CameraObservationProvider`

**Kind**：class；**Stability**：Advanced boundary；**Defined in**：`observations/camera.py`、`capture.py`

`CameraSensor(*, spec, references)` 从同一次 `RuntimeSnapshot` 解析pose/metadata。`CameraObservationProvider(*, render_source, config, camera_sensors)`实现reset/capture/close，属于env可选传感器采集，与`env.render()`的UI导出分离。

状态 observation 是任务声明的 tree；例如 selected manipulation 的 state 与可选 privileged 字段按实际 schema/space 读取。一个 snapshot 与同一 boundary/sample clock 关联；留存时遵循 publication 的复制与 lifetime 声明，不把后续 reset 的状态当作旧帧。`CameraSpec` 在构造时声明相机名称、宽高和姿态；renderer 及相机绑定不能在同一 Env 中通过 `render(mode=...)` 随意切换。

| 消费者 | 输出合同 | 注意 |
| --- | --- | --- |
| scalar UI `rgb_array` | owned CPU NumPy HWC `uint8` | 显式 `render()`，不额外推进 |
| scalar task RGB | CPU `float32`，通常 0～1 | Task sensor 与 UI 独立 |
| device named camera | CUDA `uint8`，带 B 轴 | 与同一步 boundary 对齐，按声明的 lifetime 使用 |

部分 reset/same-step autoreset 的 terminal 帧与新 reset 帧属于不同边界；不能用一次截图推断二者。7c002 的 GeoPhys Nut 最初尝试在首帧因缺少 canonical Scene 失败并关闭；改用 Scene 绑定的新 Artifact 后，原 Panda、GeoPhys CPU isolated worker、seed19 的 128×96 Rasterizer observer 已有首帧、一步、再 reset 和 close 的有界实测。帧主体较小，未证明几何视觉精度或其他相机／provider；旧失败保持历史。其他受测 UI 例子和完整相机参数见[渲染指南](../../../../docs/module/task_env/v2.1.1/guides/quickstart-rendering.md)。

以下是现有 Pendulum GeoPhys CPU observer 的最短用法；它不代表上述 Nut 交集：

```python
import sys
import numpy as np
from task_env import make_env
from task_env.environment.config import CameraSpec

env = make_env('pendulum-v1', config={
    'execution': {'physics_provider': 'geophys', 'physics_backend': 'cpu',
                  'physics_device': 'cpu', 'deployment': 'in_process', 'interpreter': sys.executable},
    'episode': {'horizon': 2},
}, render_mode='rgb_array', observer_camera=CameraSpec(
    'observer', width=32, height=24, position=(0., 0., 2.),
    quaternion_wxyz=(2**-.5, 0., 2**-.5, 0.)))
try:
    obs, info = env.reset(seed=73)
    frame = env.render()
    assert frame.shape == (24, 32, 3) and frame.dtype == np.uint8
    obs, reward, terminated, truncated, info = env.step({'torque': np.zeros(1, dtype=np.float32)})
finally:
    env.close()
```

该片段按[现有示例](../../../../examples/rendering/pendulum_single_rgb.py)核对，本轮未单独执行；无 renderer 依赖或不支持的相机配置会在构造/捕获时失败，不能用其他任务的帧填充。

## UI rendering

**Import path**：`task_env.render`。正式scalar／device batch的当前合同以[版本API](../../../../docs/module/task_env/v2.1.1/api/README.md#render-contract)为准；默认scalar R3 observer与worker断线已在2026-11-16收尾中补齐。以下component/merged-scene细节仅保留其原适用范围，不外推任意renderer组合。

创建环境时传入 `render_mode="human"` 或 `render_mode="rgb_array"`，之后调用 `env.render()`。UI
render source在runtime装配时准备，visualizer在首次需要采图时lazy创建；`rgb_array`返回拥有的CPU HWC `uint8`数组（0～255）。`human`在成功reset/step后自动展示，仍可显式render，不额外推进物理。未配置render_mode时，无参render返回None。
`human` 使用已有单 scene visualizer 建立 headed window，并支持按住鼠标右键拖拽旋转、滚轮推拉以及
W/S/A/D/E/Q 键盘移动。
`env.close()`幂等释放窗口/provider；显式请求未配置的展示或不支持的renderer路线时会报错。

UI rendering 绝不会把 `CameraObservationProvider` 的 sensor image 冒充为 UI render 结果。相机 RGB/depth、
未来的触觉/力觉等均继续属于 `task_env.observations` 的 sensor 路径。训练渲染 control mailbox、render toggle、metrics overlay 与 render-event manifest 仍不是该 public sensor API 的一部分。

## Parallel UI rendering

`task_env.render.ParallelRenderProvider` 提供 batch renderer-facing 的布局转换与 snapshot 边界。默认
`world_ids` 为连续的 `0..parallel_render_num-1`，`parallel_render_num` 必须处于 `1..num_envs`；
`set_parallel_render_layout()` 只生成 renderer-facing 的 cell translation。provider 不创建 solver、不
复制完整 batch state，也不隐式做 physics reset/step。

当前 `merged_scene` runtime 使用全局扁平 body/geom 字段的 selected device slice，只写入一个 renderer
proxy 和有界 `RenderSnapshotRing`，不进行完整 B 的 host state readback。内部仍保留对 `(world, local)` 字段形状的历史读取分支，但 public `develop` 集成 S4 后没有 TaskEnv physics route 产生该布局。选中的每个 world 在同一帧内写入
自己的 renderer record range，然后一次性发布快照。旧 parallel 路线保留，不能以该实现描述推断统一 Env 的 batch 能力。

旧component source接口保留`rasterizer`/`raytracer`；RayTracer目前有未修复的helper兼容缺口，不能从接口或旧运行推断本pin已可用。当前正式GeoPhys展示默认选择Rasterizer。`rgb_array`保持renderer创建时的固定网格视角，
`human` 使用同一 visualizer/window，并保留单环境的右键拖拽、滚轮与 W/S/A/D/E/Q 相机控制；窗口关闭
不会触碰 batch physics lifecycle。运行中调整 `parallel_render_num` 或布局只失效 renderer-owned
visualizer/proxy/snapshot binding，并在下一帧重建；不会 reset、丢失 physics step 或改变 rollout transition。
旧component renderer的交互和metrics仍由原owner负责，不写入`rgb_array`。现行device Rasterizer在用户关窗后不自动重开；`close_render()`停止自动展示并保留必要的sensor renderer。

并行 world 的刚体几何优先使用 surface 表示，以保留 `SubGeomDesc` 的局部位置/姿态；这对 Pendulum 的
`fromto` link尤其重要。G06已经接通PickCube的native CUDA batch；具体provider/source/相机范围及当前scalar展示见上述版本API，不能沿用旧“未声明/不可render”的结论。
