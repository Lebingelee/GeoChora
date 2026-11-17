# 有头窗口、相机参数与图像

本页教三条**不同**的图像通路：scalar UI 窗口/离屏导出、scalar task sensor、device 具名相机。默认教学路线是 **GeoPhys Rasterizer**，因为它在 scalar UI 和 device batch 都有受测路径；MuJoCo reference 与 Isaac RTX 作为已准入的替代路线说明，不静默替换。

> **验证口径（2026-11-17）**：本页参数按 `task_env/environment/config.py::CameraSpec`、渲染合同和现有示例静态核对；**本轮没有打开窗口、没有采集像素、没有初始化 CUDA**。既有像素证据按原 task/provider/renderer/seed 交集引用。

## 3.1 先区分三类图像通路

| 通路 | 谁产生 | 合同 |
| --- | --- | --- |
| scalar observer／UI | 构造时 `render_mode` + 显式 world `observer_camera` | `human` 在成功的 reset/step 后自动展示；`rgb_array` 只在 `env.render()` 时导出**拥有的 CPU NumPy HWC uint8**（0～255）。内部捕获声明是 float32，但 UI 导出合同是 uint8。 |
| scalar task RGB | `task_rgb_camera` 与固定 `task_renderer` 成对声明 | 出现在 `observation["task_rgb"]`，现有合同是 **CPU float32、0～1、HWC**；不是 UI 导出，也不随 UI dtype 改变。 |
| device named cameras | `render.camera_obs=True` + `render.cameras` | 返回 `observation["cameras"][name]["rgb"]`，**CUDA uint8、`[B,H,W,3]`**；same-step 终止帧与 reset 后新首帧分开。 |

常见误解：

- “无窗口”不等于“无渲染”。`render_mode='rgb_array'` 可以完全离屏；task sensor 也可以在无 window 时采集。
- 不要把所有 `rgb` 都讲成同 shape/dtype/device。UI、task sensor、device camera 是三套消费合同。
- scalar 的 `render.camera_obs/cameras` 仍**明确拒绝**（尚未形成具名多相机观测）；scalar 具名多相机请使用 `task_rgb_camera` 的单相机能力。device 的同名字段则是正式具名相机。
- sensor 图像由 reset/step 的观测管线产生，不依赖额外调用 `render()`；`render()` 只负责 UI。

## 3.2 CameraSpec 每个字段

精确来源：`task_env/environment/config.py::CameraSpec`。

| 字段／源码默认 | 教学解释与限制 |
| --- | --- |
| `name`（必填） | 相机名。空字符串拒绝；同一 `render.cameras` 内不能重名。 |
| `width=128`, `height=128` | 像素尺寸；正整数。scalar observer 的尺寸决定最终视口；`render.width/height`（640×480）是共享视口字段，显式 observer 尺寸优先。sensor 尺寸按各 `CameraSpec` 独立。 |
| `rgb=True` | 请求 RGB 模态。`rgb=False, depth=True` 至少要有一种模态；`rgb/depth` 都 false 拒绝。 |
| `depth=False` | 声明深度**不等于**任意 renderer 已支持深度。本教程只演示已准入的 RGB 合同；不要用 depth 字段推断 depth 像素可用。 |
| `rgb_layout='HWC'` | sensor 声明布局；可选 `CHW`。这是观测声明，不是 UI 导出布局。 |
| `rgb_dtype='float32'` | sensor 声明 dtype；可选 `uint8`。**不能**用它改写 scalar UI 的 CPU uint8 合同，也不能把 sensor 默认 float32 套到 device camera（device 是 uint8）。 |
| `frame='world'` | 挂载坐标系：`world`、`body`、`site`。当前 scalar **observer 只能 world**；`body/site` 必须给 `parent`。移动的 task camera 目前仅 Isaac RTX 的特定路线准入；MuJoCo/GeoPhys 的 frame-mounted task RGB 构建时拒绝。 |
| `parent=None` | `body/site` 的父引用，格式是 `entity_id/frame_id`（例如 `panda-v1/ee`）；缺失或不唯一时拒绝。`world` 不能声明 parent。 |
| `position=(0,0,0)` | 长度 3，单位 m；相对 world 或 parent 的安装位置。三个任务的实际桌面/摆杆范围见下方参数表。 |
| `quaternion_wxyz=(1,0,0,0)` | `wxyz` 次序；内部按单位四元数使用。约定是 **local +X forward、local +Z up** 的安装坐标，不是别家 OpenGL 的光学坐标。 |
| `fov_y=π/2` | **垂直**视场角，单位 rad。π/2 = 90°。水平视场由 `width/height` 长宽比推出；不要把它当水平 FOV。 |
| `near=0.01`, `far=100.0` | 单位 m；必须 `near>0` 且 `far>near`。按桌面/摆杆尺寸选择，避免把目标裁掉或让深度精度过差。 |

校验失败会在构造/配置阶段抛出 `ValueError`（例如 `camera width/height must be positive`、`camera near/far planes are invalid`、`body/site camera must declare a parent`）。

### 手算一个视线与姿态

任务约定 local `+X` 指向目标，local `+Z` 尽量对齐世界 `+Z`。仓库已有公开工具 `task_env.utils.rotation.look_at_quat_wxyz(position, target)`，它正是按这个约定构造 WXYZ 姿态：

```python
from task_env.utils.rotation import look_at_quat_wxyz

position = (0.5545, -0.55, 1.25)          # 桌子前方上方
target = (0.5545, 0.0, 0.48)              # 桌面中心附近（table_top_z≈0.462）
quaternion = look_at_quat_wxyz(position, target)
print(quaternion)
```

这比手填四元数可靠：它先归一化 forward，构造 right/up，再转成 `wxyz`。但**“几何上指向目标”不等于“已验证目标在画面内”**；是否入画还取决于 FOV、near/far、宽高比和遮挡，必须实际采图核对。

### 三个任务的完整参数（来源与验证状态）

| 任务 | 相机 | 参数 | 来源／状态 |
| --- | --- | --- | --- |
| Pendulum | observer | `position=(0,0,2)`, `quaternion_wxyz=(√0.5,0,√0.5,0)`, `fov_y≈1.5708`, `near=.01`, `far=100`, 32×24（示例默认） | `examples/rendering/pendulum_single_rgb.py` 的真实参数；既有短程 RGB smoke |
| PickCube | observer | `position=(0.5,0,2)`, `quaternion_wxyz=(√0.5,0,√0.5,0)`, 320×240 | [API 渲染合同](../api/README.md#render-contract)的文档示例；**静态/文档来源，未在本轮重采**。该姿态从上方看向桌面中心。 |
| PickCube | 手腕 task RGB（Isaac RTX） | `frame='body'`, `parent='panda-v1/ee'`, `position=(0.04,0,-0.06)`, `quaternion_wxyz=look_at_quat_wxyz(position,(0,0,.035))`, 256×192, `fov_y=1.15`, `near=.005`, `far=2`, `depth=False` | `task_env/diagnostics/tasks/v2.1.1/isaac_gripper_rework.py::wrist_camera` 的真实参数；既有 Isaac seed31 受控抬升证据，只是诊断，不是正式 Solution 成功 |
| NutAssembly | observer | `position=(0.5545,0,2)`, `quaternion_wxyz=(√0.5,0,√0.5,0)`, 640×480 | 由 PickCube 同一安装约定和 Nut 桌面中心 `x≈0.5545` **推导**；本页不声称已在 Nut 上采到像素。首次运行请先按 3.4 的方法核对物体入画。 |

长宽比与焦距换算：

```text
aspect = width / height
focal_px_y = height / (2 * tan(fov_y / 2))
focal_px_x = focal_px_y          # 方形像素、由宽高比给出水平 FOV
```

例如 `height=240, fov_y=π/2` → `focal_px_y=120`。这是针孔近似，用来理解视场，不是 renderer 的标定值。

## 3.3 Pendulum：GeoPhys Rasterizer 默认有头例子

已有起点是 `examples/rendering/pendulum_single_rgb.py`。下面把它展开成完整、可跟随的 human 版本；显式 `render.backend='rasterizer'`，使用 GeoPhys CPU：

```python
# workspace/tutorial/pendulum_window.py
import numpy as np
from task_env import make_env
from task_env.environment.config import CameraSpec

env = make_env(
    "pendulum-v1",
    config={
        "execution": {"physics_provider": "geophys", "physics_backend": "cpu",
                      "physics_device": "cpu", "deployment": "in_process",
                      "interpreter": __import__("sys").executable},
        "episode": {"horizon": 100},
        "render": {"backend": "rasterizer", "width": 640, "height": 480},
    },
    render_mode="human",
    observer_camera=CameraSpec(
        "observer", width=640, height=480,
        position=(0.0, 0.0, 2.0),
        quaternion_wxyz=(2 ** -0.5, 0.0, 2 ** -0.5, 0.0),
    ),
)
try:
    observation, info = env.reset(seed=73)
    for _ in range(100):
        observation, reward, terminated, truncated, info = env.step(
            {"torque": np.zeros(1, dtype=np.float32)}
        )
        # render_mode='human'：成功的 reset/step 后自动展示；返回值不含图像
        if terminated or truncated:
            break
finally:
    env.close()          # 同时关闭窗口/observer
```

### 运行卡

| 必填项 | 本例取值 |
| --- | --- |
| 环境 | 需要可用 display（Xorg/Wayland）；GeoPhys CPU + Rasterizer；Core 解释器 |
| 身份 | `pendulum-v1`；observer 名 `observer`；无任务相机 |
| 前置与启动 | 先 `source scripts/setup/geochora-env.sh`；从仓库根运行；若 `DISPLAY` 不存在，改用 3.3 的 `rgb_array` |
| 输入/输出 | action `torque (1,) float32`；`render()` 在 human 下返回 None；窗口自动更新 |
| 结束 | horizon 100 或关闭窗口后 Ctrl-C；`finally: close()` 释放窗口 |
| 验证 | 示例参数和 `render_mode` 合同按源码核对；**本轮未开窗**；历史 Pendulum rasterizer smoke 只属原证据 |
| 故障 | `DISPLAY` 缺失/GL 不可用 → renderer 构造失败；显式不支持的 backend → native 构建前拒绝；不静默 fallback |

### 同一任务的 `rgb_array` 差异

```python
env = make_env(..., render_mode="rgb_array", observer_camera=CameraSpec(
    "observer", width=320, height=240,
    position=(0.0, 0.0, 2.0),
    quaternion_wxyz=(2 ** -0.5, 0.0, 2 ** -0.5, 0.0),
))
try:
    observation, info = env.reset(seed=73)
    frame = env.render()           # 不推进物理
    assert frame.shape == (240, 320, 3) and frame.dtype.name == "uint8"
    print(frame.min(), frame.max())  # 0～255
finally:
    env.close()
```

`human` 与 `rgb_array` 的 mode 在构造时固定；`env.render(mode=...)` 不能切换成另一种 mode（会抛 `ValueError: TaskEnv render mode is fixed at construction`）。`render()` 不额外推进物理。

说明：原示例显式 `deployment='in_process'`；默认 scalar GeoPhys 也可走 worker（`GEOCHORA_GEOPHYS_PYTHON` 未设置时用当前解释器）。本页保留示例的显式 in-process 以便新读者少一个进程变量；这不是说 worker 不支持 observer。

## 3.4 PickCube：桌面相机与动作可视化

沿第二部分的随机 pose 或 Solution 循环，只增加公开 render/camera 声明；不要调用 provider viewer 私有方法。下面是 **human + Solution** 的完整骨架：

```python
# workspace/tutorial/pickcube_window.py
from task_env import make_env
from task_env.environment.config import CameraSpec
from task_env.tasks.pick_cube import build_readiness_solution

env = make_env(
    "pick-cube-p16-reference-v1",
    config={
        "execution": {"physics_provider": "geophys", "physics_backend": "cpu"},
        "episode": {"horizon": 1000},
        "controller": {"profile_id": "r3_continuous_v1"},
        "render": {"backend": "rasterizer", "width": 640, "height": 480},
    },
    render_mode="human",
    observer_camera=CameraSpec(
        "observer", width=640, height=480,
        position=(0.5, 0.0, 2.0),
        quaternion_wxyz=(2 ** -0.5, 0.0, 2 ** -0.5, 0.0),
    ),
)
try:
    solution = build_readiness_solution(backend="cpu", controller_profile="r3_continuous_v1")
    observation, info = env.reset(seed=31)
    solution.reset(observation, info, env.metadata)
    for _ in range(1000):
        action = solution.act(observation, info)
        observation, reward, terminated, truncated, info = env.step(action)
        solution.observe(observation, reward, terminated, truncated, info)
        if terminated or truncated or solution.done or solution.failed:
            break
finally:
    env.close()
```

**GeoPhys Rasterizer 是首个教程路线**：上面的示例已经显式使用 `physics_provider='geophys'` + `render.backend='rasterizer'`；其他组合只能按实际准入选择：

| physics | 可用 UI backend | 说明 |
| --- | --- | --- |
| MuJoCo CPU | `mujoco_reference` | 原生 OpenGL reference；不是“在 MuJoCo 上强填 rasterizer” |
| GeoPhys CPU | `rasterizer` | 本页默认；也可按既有路线做 physics×renderer-only |
| Isaac CUDA | `isaac_rtx` | RTX tone mapping/sRGB 合同；需要 SDK 子进程 |

### 运行卡

| 必填项 | 本例取值 |
| --- | --- |
| 环境 | GeoPhys CPU + Rasterizer；需要 display（human）；Core 解释器与 `GEOCHORA_GEOPHYS_SRC` |
| 身份 | `pick-cube-p16-reference-v1`；`r3_continuous_v1`；seed 31；Menagerie pin |
| 前置与启动 | `source scripts/setup/geochora-env.sh`；从仓库根运行；新 H5/输出路径 |
| 输入/输出 | Solution 的 8 维 pose+开口；窗口自动更新；`rgb_array` 时 `(480,640,3) uint8` |
| 结束 | 成功/失败/horizon/策略结束均退出循环；`finally: close()` 释放窗口与物理 |
| 验证 | 示例参数、render 合同静态核对；该世界相机来自文档示例，**未在本轮重采**；native=0 |
| 故障 | MuJoCo 上使用 `rasterizer` → 不支持；display/GL 缺失 → 改 `rgb_array` 或修显示；Solution identity 不符 → Task 拒绝 |

关键语义：

- `render_mode` 不负责切换 physics；`render.backend` 是构建时选择的 renderer，**普通 reset 不换 renderer**。
- 从上方看的 observer 中，桌面在画面下半部、Panda 从上方进入；`ee_pose` 与图像对应**同一个 reset/step 边界**。一次 step 前的画面是旧边界，step 后是同一调用的新边界。
- 该 observer 参数来自文档示例，**没有在本轮验证“桌面与 TCP 同时入画”**。若画面偏离，优先调 `position/target/fov_y/near/far` 并采一张 reset 帧核对，而不是读 provider 私有相机状态。

`rgb_array` 的区别同 3.3：`frame = env.render()`，shape `(480,640,3)`，dtype `uint8`；可再用 Pillow 保存 PNG（可选，不属于 Env 合同）。

## 3.5 NutAssembly：相同配置方式与 Task 差异

复用原 Nut Solution 和同一 renderer/world-camera 合同：

```python
# workspace/tutorial/nut_window.py
from task_env import make_env
from task_env.environment.config import CameraSpec
from task_env.tasks.nut_assembly.task import build_outcome_solution

env = make_env(
    "nut-assembly-outcome-reference-v1",
    config={
        "execution": {"physics_provider": "geophys", "physics_backend": "cpu"},
        "episode": {"horizon": 6000},
        "render": {"backend": "rasterizer", "width": 640, "height": 480},
    },
    render_mode="human",
    observer_camera=CameraSpec(
        "observer", width=640, height=480,
        position=(0.5545, 0.0, 2.0),
        quaternion_wxyz=(2 ** -0.5, 0.0, 2 ** -0.5, 0.0),
    ),
)
try:
    solution = build_outcome_solution(provider="geophys")
    observation, info = env.reset(seed=19)
    solution.reset(observation, info, env.metadata)
    for _ in range(6000):
        observation, reward, terminated, truncated, info = env.step(solution.act(observation, info))
        solution.observe(observation, reward, terminated, truncated, info)
        if terminated or truncated or solution.done or solution.failed:
            break
finally:
    env.close()
```

说明：

- 不能把 PickCube 的 source 或截图当 Nut 图像；Nut 的相机位置来自同一 tabletop 约定和 Nut 桌面中心，**静态推导，未重采**。
- 随机输入限制仍在：普通随机数组会在动作准入被拒绝（见 [2.5](quickstart-state-only.md#25-nutassembly随机动作版当前真实缺口t-nut-random)）；**有头显示不等于 strict Solution 完成**。
- GeoPhys 当前源码未重跑完整 Nut；本页不把历史完整成功写成“最新 HEAD 已复验”。
- 正常关闭：`env.close()` 释放窗口、observer 和物理资源；窗口关闭后的行为以 close 回执为准。

### 运行卡

| 必填项 | 本例取值 |
| --- | --- |
| 环境 | GeoPhys CPU + Rasterizer；需要 display；Core 解释器与匹配 GeoPhys source |
| 身份 | `nut-assembly-outcome-reference-v1`；seed 19；Panda + square nut/peg |
| 前置与启动 | `source scripts/setup/geochora-env.sh`；从仓库根运行；新输出路径 |
| 输入/输出 | 原 Solution 的 `ExpertAction`；窗口自动更新；`rgb_array` 为 `(480,640,3) uint8` |
| 结束 | 完整 Solution 计划走完；horizon 不足会截断；`finally: close()` |
| 验证 | 相机参数为静态推导；既有 Nut seed19 运行按原身份引用；**本轮未重采/未重跑**；native=0 |
| 故障 | 普通随机 action → 2.5 拒绝；seed≠19 → reset 拒绝；display/GL 缺失 → `rgb_array` |

源帧与任务边界对照：在 `reset` 后保存一帧，在每个 `step` 返回后保存一帧，并同时记录 `info["episode_id"]`、`info.get("state_boundary_identity")`（若该路线提供）和 transition 序号。不要用截图时间戳猜物理时钟。

## 3.6 独立的任务 sensor 例子

任务 sensor 与 UI 是两条通路。下面是一个**已有强证据**的 scalar task RGB 例子：PickCube × Isaac PhysX CUDA × Isaac RTX × 手腕 `body` 相机。它来自 `isaac_gripper_rework.py` 的相机参数，但只演示已准入 pair，不扩张成三任务×三 provider 矩阵。

```python
# workspace/tutorial/pickcube_task_rgb.py   （需要 Isaac SDK；本轮未运行）
import numpy as np
from task_env import make_env
from task_env.environment.config import CameraSpec
from task_env.utils.rotation import look_at_quat_wxyz

position = (0.04, 0.0, -0.06)
wrist = CameraSpec(
    "wrist", frame="body", parent="panda-v1/ee",
    position=position,
    quaternion_wxyz=look_at_quat_wxyz(position, np.asarray((0.0, 0.0, 0.035))),
    width=256, height=192, fov_y=1.15, near=0.005, far=2.0, depth=False,
)
env = make_env(
    "pick-cube-p16-reference-v1",
    task_rgb_camera=wrist,
    task_renderer="isaacsim",
    config={
        "execution": {"physics_provider": "isaacsim", "physics_backend": "cuda",
                      "physics_device": "cuda:0"},
        "controller": {"profile_id": "r3_continuous_v1"},
        "episode": {"horizon": 8},
    },
)
try:
    observation, info = env.reset(seed=31)
    reset_rgb = observation["task_rgb"]          # CPU float32 (192,256,3), 0..1
    print(reset_rgb.shape, reset_rgb.dtype)
    print(info["task_rgb_v1"])                   # 同步捕获 receipt
    pose = np.asarray(observation["state"]["ee_pose"], dtype=np.float32).copy()
    pose[0] += 0.002
    action = np.asarray([*pose, 1.0], dtype=np.float32)
    observation, reward, terminated, truncated, info = env.step(action)
    step_rgb = observation["task_rgb"]
    print("same-boundary task RGB:", step_rgb.shape, info["task_rgb_v1"]["capture_identity"])
finally:
    env.close()
```

### 运行卡

| 必填项 | 本例取值 |
| --- | --- |
| 环境 | Isaac Sim 6.2 SDK 子进程；CUDA；已安装 USD 资产；不需要 Xorg 窗口（RTX headless 可采） |
| 身份 | `pick-cube-p16-reference-v1`；Isaac PhysX CUDA；Isaac RTX；seed 31 |
| 前置与启动 | `execution.interpreter`/`ISAAC_SIM_PYTHON` 指向 SDK；`OMNI_KIT_ACCEPT_EULA=YES`（在阅读 EULA 后自行设置） |
| 输入/输出 | task RGB CPU float32 HWC `(192,256,3)` 0～1；`info["task_rgb_v1"]` 是同一 reset/step 边界的 receipt |
| 结束 | horizon 8；无额外 `render()`；`finally: close()` 释放 sensor 和 SDK 资源 |
| 验证 | 相机参数与任务 RGB 合同按源码/诊断核对；Isaac 腕部 430 步历史证据只支持原受控路线；**本轮 native=0** |
| 故障 | `body` parent 不在已发布 Frame → 构建拒绝；MuJoCo/GeoPhys frame-mounted task RGB → 构建拒绝；缺 SDK/资产 → preflight |

device 具名相机（`base`/`hand`）的声明来自 `examples/parallel/pick_cube_device.py --sensor`：`render.camera_obs=True`、`render.cameras=[{...rgb_dtype:'uint8'...}]`，返回 `observation["cameras"][name]["rgb"]`，形状 `[B,H,W,3]`，dtype 为 CUDA uint8。它属于 [device batch](quickstart-device-batch.md)，不是本节的 scalar task RGB。

任务 sensor 记录：物理 v3 记录可在每个边界保存 `task_rgb` 与 capture identity；独立读回用 `load_physical_recording_h5` 校验图像边界与 capture identity，但图像字节没有独立内容摘要，记录成功不等于像素任务成功。本页不把 UI 导出图当训练观测。

**明确不支持/未验证**：

- scalar `render.camera_obs/cameras` 具名多相机：明确拒绝。
- depth、segmentation：字段存在不等于本教程路线已准入；不要从 `depth=True` 推断图像可用。
- 任意 moving task camera：只有 Isaac RTX 的特定 frame 路线；MuJoCo/GeoPhys 的 frame-mounted task RGB 未实现。
- 相机跨行视觉隔离：device 共享平铺场景，其他行几何可能进入视野；不承诺逐像素隔离。

## 3.7 渲染故障排查

| 现象 | 先检查 | 原 owner／处理 |
| --- | --- | --- |
| 窗口不出现 | `render_mode` 是否为 `human`；`DISPLAY`/GL；`render.backend` 是否支持 | 改用 `rgb_array` 离屏；不要假设有窗口才是渲染成功 |
| 全黑/全白 | 相机是否朝向目标；near/far 是否裁掉场景；灯光/材质资产 | 用 `look_at_quat_wxyz` 重算姿态；保存 reset 帧对照 |
| 目标被裁掉 | `fov_y`、距离、`near/far`、宽高比 | 调整相机参数；不要把 `near>far` |
| 图像过期 | 图像来自哪次 reset/step；是否消费了同一返回边界 | 同一边界配对 `info` receipt；不要读私有帧缓存 |
| `unsupported ... pair` | physics × renderer 是否在准入表 | 按 3.4 的表选择；**不静默 fallback** |
| `body/site camera must declare a parent` | `frame` 与 `parent` 不匹配 | 补 `entity_id/frame_id` 或改回 `world` |
| `camera near/far planes are invalid` | 数值关系 | `near>0` 且 `far>near` |
| `TaskEnv render mode is fixed at construction` | 是否在 `render()` 里传了不同 mode | 构造时就选定 `human` 或 `rgb_array` |
| Xorg 窗口/RTX 设置失败 | 驱动、显示、RTX 设置/OCIO 摘要 | 按 Isaac 记录核对；不要改私有 renderer 状态 |
| task RGB 与 UI dtype 不同 | 是否把 float32 sensor 当 UI | UI 导出是 uint8；sensor 默认 float32，device camera 是 uint8 |

不要为了“让画面出现”而：静默换 renderer、读 provider 私有 framebuffer、关闭必要的相机/身份检查，或把 UI 导出图当训练观测。
