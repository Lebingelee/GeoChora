# Observation and rendering

**Import path**：`task_env.observations`
**任务域**：Appendix  
**稳定性**：Public API / Advanced boundary  
**职责**：从一次公开 snapshot 构建 state、RGB、depth observation。
**调用者/消费者**：`BaseTaskEnv`。  
**源码**：`observations/state.py`、`observations/camera.py`、`observations/capture.py`

## `StateObservationBuilder`

**Kind**：class；**Stability**：Advanced boundary；**Defined in**：`observations/state.py`

构造签名：`StateObservationBuilder(*, references: TaskReferences, config: ObservationConfig, render_config: RenderConfig)`。`observation_space` 与 `schema` 是只读属性，`build(snapshot, sensor_observation=None)` 生成 observation。key、shape、dtype 由 `ObservationSchema` 的实际 fields 声明；不要猜测固定 key。

## `CameraSensor` / `CameraObservationProvider`

**Kind**：class；**Stability**：Advanced boundary；**Defined in**：`observations/camera.py`、`capture.py`

`CameraSensor(*, spec, references)` 从同一次 `RuntimeSnapshot` 解析 pose/metadata。`CameraObservationProvider(*, render_source, config, camera_sensors)` 实现 `reset()`、`capture(snapshot) -> SensorObservation`、`close()`。它属于 env 可选传感器采集，不是 private solver 数据的读取入口，也不是未来 `env.render()` 的 UI API。

## UI rendering

**Import path**：`task_env.render`；**状态**：单环境 RGB/offscreen 与基础 headed lifecycle 已接入。

创建环境时传入 `render_mode="human"` 或 `render_mode="rgb_array"`，之后调用 `env.render()`。UI
render source 在 runtime 装配时准备，但 visualizer 在第一次 `render()` 时 lazy 创建；`rgb_array` 返回
场景初始化固定视角下的 HWC `float32` 数组（范围 `[0, 1]`），不会继承 human 交互后的相机位姿。
`human` 使用已有单 scene visualizer 建立 headed window，并支持按住鼠标右键拖拽旋转、滚轮推拉以及
W/S/A/D/E/Q 键盘移动。
`env.close()` 会幂等释放窗口/provider；未配置 `render_mode` 或 runtime 没有 render source 时会抛出
`RenderUnavailableError`/`StageUnavailableError`。

UI rendering 绝不会把 `CameraObservationProvider` 的 sensor image 冒充为 UI render 结果。相机 RGB/depth、
未来的触觉/力觉等均继续属于 `task_env.observations` 的 sensor 路径。训练渲染 control mailbox、render toggle、metrics overlay 与 render-event manifest 仍不是该 public sensor API 的一部分。

## Parallel UI rendering

`task_env.render.ParallelRenderProvider` 统一 static-template 与 merged-scene 的并行渲染边界。默认
`world_ids` 为连续的 `0..parallel_render_num-1`，`parallel_render_num` 必须处于 `1..num_envs`；
`set_parallel_render_layout()` 只生成 renderer-facing 的 cell translation。provider 不创建 solver、不
复制完整 batch state，也不隐式做 physics reset/step。

并行渲染 contract 已接到真实批量 runtime：`merged_scene` 使用全局扁平 body/geom 字段的 selected
device slice，`static_template` 使用 `(world, local)` 字段的 selected slice；两者都只写入一个 renderer
proxy 和有界 `RenderSnapshotRing`，不进行完整 B 的 host state readback。选中的每个 world 在同一帧内写入
自己的 renderer record range，然后一次性发布快照，因此网格中不会只显示最后一个 world。

真实 source 当前支持内部 `rasterizer`/`raytracer`。`rgb_array` 保持 renderer 创建时的固定网格视角，
`human` 使用同一 visualizer/window，并保留单环境的右键拖拽、滚轮与 W/S/A/D/E/Q 相机控制；窗口关闭
不会触碰 batch physics lifecycle。运行中调整 `parallel_render_num` 或布局只失效 renderer-owned
visualizer/proxy/snapshot binding，并在下一帧重建；不会 reset、丢失 physics step 或改变 rollout transition。
human presentation 会在窗口关闭后重开，并显示 renderer rebuild、snapshot publish、帧耗时/FPS 和窗口重开
次数 metrics；这些 metrics 不写入 `rgb_array`。

并行 world 的刚体几何优先使用 surface 表示，以保留 `SubGeomDesc` 的局部位置/姿态；这对 Pendulum 的
`fromto` link 尤其重要。PickCube 尚未声明同构并行 task contract，仍使用单环境 render API。
