# API 详细用法、迁移与排错

本页按**使用场景**组织，不复制第二套字段规范：

- 公共字段/默认值/能力定义以 [v2.1.1 API](../api/README.md) 为跨边界 owner；
- 符号级细节以 `task_env/doc/api/` 为 owner；
- 教程解释、完整例子、预期结果和失败路径在本页。

> **验证口径（2026-11-17）**：签名/异常/字段按当前源码静态核对；**本轮没有 native 运行**。历史证据按原身份引用。

## 6.1 构造与配置速查

### `make_env`

```text
task_env.make_env(
    uid: str,
    *,
    config=None,              # mapping / YAML path / ResolvedEnvConfig
    render_mode=None,         # None | 'human' | 'rgb_array'
    execution: str | None = None,   # 仅显式 'device' 表示单行设备路线
    **kwargs,
) -> TaskEnvironmentComponent
```

- `uid` 必须是已注册的当前任务；未知 UID → `KeyError`。
- selected 任务的 `config` 只接受 `execution`、`episode`、`task`、`controller`、`robot`、`runtime`、`render`；未知 section/字段会拒绝。
- `execution='device'` 复用 device batch 生命周期并去掉公开返回的 B 轴；`backend='cuda'`、可选 `worker_directory`。不要用 `execution='device'` 选 physics provider，provider 仍在 `config.execution.physics_provider`。
- `task_rgb_camera` 与 `task_renderer` 必须成对传入；只给一个 → `ValueError('task RGB camera and fixed renderer must be declared together')`。
- 旧 UID `pick-cube-v1`、`nut-assembly-square-v1`、Go2 相关 UID 已退休，factory 明确拒绝且不映射。

### `make_parallel_env`

```text
task_env.make_parallel_env(
    uid: str,
    env_config=None,          # selected 配置（与 make_env 的 config 同义内容）
    num_env: int = 1,
    backend: str = "cuda",
    *,
    execution: str = "remote",  # 'remote' | 'local' | 'device'
    start_method: str = "spawn",
    compile_mode: str = "fastest",
    **env_kwargs,
)
```

- device：`execution='device'`，拒绝 SB3 的 `start_method/compile_mode` 非默认值；接受 `worker_directory`、`render_mode`。
- 只有 `remote`/`local` 是旧 SB3 路线；它们的合同不是本页 device 教程。
- `env_config` 必须含显式 `physics_provider`（device scope 要求），否则配置拒绝。

### `make_agent` / `make_object` / `make_scene`

```python
task_env.make_agent("panda-v1")            # RobotComponent；无参数构造 UID 在类上
task_env.make_object("cube-v1")            # TaskObjectComponent
task_env.make_scene("tabletop-v1")         # SceneBuilderComponent
```

- 这些是组件 registry 创建入口；不构造 native runtime。
- `PandaAgent`/`AssembledPandaAgent` **没有** `__init__(uid)`；不要写 `PandaAgent('panda-v1')`。
- 未知 UID → `KeyError`；退休 UID → `ValueError`。

### registries

```python
task_env.ENV_REGISTRY.uids()
task_env.AGENT_REGISTRY.uids()
task_env.OBJECT_REGISTRY.uids()
task_env.SCENE_REGISTRY.uids()
task_env.PARALLEL_ENV_REGISTRY   # 懒加载
```

注册/可 import **不**证明端到端能力；能力看矩阵和实际证据。

### `resolve_env_config`

```text
task_env.resolve_env_config(
    *,
    task_uid: str,
    scene_uid: str,
    agent_uids: tuple[str, ...] = (),
    object_uids: tuple[str, ...] = (),
    success_definition: str = "none",
    asset=None, runtime=None, robot=None, control=None, action=None,
    observation=None, render=None, episode=None,
) -> ResolvedEnvConfig
```

- 它是**关键字构造函数**，不是 `resolve_env_config(mapping)`。
- 返回 `ResolvedEnvConfig`（classic/component 配置），不是 selected 任务的 `ResolvedSelectedConfig`。selected 任务应直接给 `make_env` mapping/YAML。
- 未知键/类型/冲突会抛 `ValueError`/`TypeError`，并附 `phase/reason/request_identity/receipt`。

### mapping/YAML 与 roundtrip

```bash
"$GEOCHORA_CORE_PYTHON" -m task_env.script.env.single_inline \
  --env-id pick-cube-p16-reference-v1 --backend cpu --steps 1 --horizon 10 --seed 31
"$GEOCHORA_CORE_PYTHON" -m task_env.script.env.single_from_file \
  --env-id pick-cube-p16-reference-v1 --env-config pick-cube.yaml \
  --backend cpu --steps 1 --horizon 10 --seed 31
```

`--backend` 是这些 CLI 的覆盖入口；YAML 的其他正式字段按 selected 解析。`env.resolved_public_config` 是实际解析后的声明，可用于核对 section/字段；不要把旧 top-level `provider/backend/horizon`、`recipe/environment`、退休 UID 或 `static_template` 写回。

### 七 section 与 classic 结构

| selected section | 允许字段（摘要） | 关键约束 |
| --- | --- | --- |
| `execution` | `physics_provider`、`physics_backend`、`physics_device`、`source_delivery_manifest`、`render_default`、`host/engine/solver_family/solver_algorithm/coupler/batch_layout/deployment/interpreter/native_dt/reset_profile/geophys_contact_mode` | provider/backend/device 必须命中 admitted route；device 还要显式 provider |
| `episode` | `horizon`、`seed`、`ignore_done` | horizon ≥1；seed 语义按任务（Nut 固定 19） |
| `task` | 任务声明允许的参数（如 `lift_height_m`） | 不是任意 kwargs |
| `controller` | `profile_id`、`gravity_compensation`、`parameters` | parameters 键由 Task 声明；不是控制对象 |
| `robot` | `uid`、`native_drive` | 只能选 Task 准入的 Robot |
| `runtime` | `body_contact_solver_iterations` | 仅 GeoPhys；正整数 |
| `render` | `camera_obs`、`backend`、`cameras`、`width/height`、`render_preset`、`parallel/training` | camera_obs 与 cameras 必须一致；backend 必须在声明集合 |

classic/component 结构（scene/agents/objects/control/action/observation）仍由 `resolve_env_config` 和保留 caller 使用；不要把两者混写成一个 mapping。

## 6.2 生命周期与动作

### `reset`

```python
observation, info = env.reset(seed=31)
observation, info = env.reset(seed=None)                    # 继续已初始化的随机流
observation, info = env.reset(options={"controller": "r3-pose"})
observation, info = env.reset(mask=cuda_bool_B)             # 仅 device batch
```

- selected scalar 的 `seed`：显式值重置 Core 随机流；`None` 继续已初始化流；首次 `None` 初始化新流。
- `options` 只在对应声明/route 支持时生效：state-only switch、Controller reset selection、device 整批切换。未声明的 option 会拒绝，不是静默忽略。
- 预检失败保留旧 episode；替换开始后失败会 fault（见 6.6）。
- renderer 在构造时固定，普通 reset **不切换 renderer**。

### `step`

scalar：

```python
observation, reward, terminated, truncated, info = env.step(action)
```

device batch：

```python
observation, reward, terminated, truncated, info = env.step({"torque": cuda_B1})
```

- scalar 五元组；device 五元组但 reward/done 为 CUDA `[B]`、observation 树前置 B。
- device 的 same-step autoreset：reward/done 属于旧 episode，返回 observation 属于新 episode；终止帧在 `info["final_observation"]`，mask 为 `info["_final_observation"]`/`final_mask`。
- `step()` 不能在步进中替换 provider 或 renderer；切换只能通过 `reset(options=...)` 的已准入边。

### spaces、config、metadata

```python
env.action_space
env.observation_space
env.single_action_space          # device batch 的单行空间
env.single_observation_space
env.resolved_public_config
env.metadata
```

- `metadata` 是构造/任务/渲染声明的只读摘要；不是 native 状态。
- `state` 查询只在对应路线可用；不要用 `env.robot` 的便利字段推断所有任务都有 Panda 视角。
- `Panda` 组件路线的 `references/gripper/ee` 便利投影保留；selected 视图未声明时为 `None`。

### `close` 与幂等/关闭后行为

```python
try:
    ...
finally:
    env.close()
```

- `close()` 释放 Env 自有资源（UI/observer、相机 consumer、recorder、session、source）。
- 重复 close 是允许的；清理失败会保留首个异常并允许后续重试未关闭资源（真实合同以当前源码为准）。
- 关闭后 `reset/step/render` 会抛 `RuntimeError`（如 `environment is closed`）；不要继续消费旧 observation 当当前数据。

### stale/foreign、preflight、fault

| 情况 | 行为 |
| --- | --- |
| stale/foreign command | 在 Controller/admission 处拒绝；旧 generation/context 不能用于新 episode |
| preflight 失败 | 不修改活 episode；保留旧状态/随机流 |
| replacement 后失败 | 进入 faulted；拒绝继续 step，必须显式 reset/重建或 close |
| partial write | 保留真实 fault/清理语义；不假装回滚所有 native 写入 |
| 构造/清理复合失败 | close 会重试尚未关闭资源；最终错误可带 notes |

## 6.3 图像与数据有效期

| 数据 | 何时产生 | dtype/布局 | 有效期/拷贝 |
| --- | --- | --- | --- |
| `env.render()`（`rgb_array`） | 显式调用；不推进物理 | CPU HWC `uint8` | owned；可长期保存 |
| `human` 窗口 | reset/step 成功后自动；`render()` 可选 | 无返回图像 | 构造时固定 mode |
| scalar `observation["task_rgb"]` | reset/step 的同步 sensor | CPU float32 `0..1` HWC | 与本次返回 boundary 绑定；需要长期保留时 copy |
| device `observation["cameras"][name]["rgb"]` | reset/step 同步 | CUDA `uint8 [B,H,W,3]` | 借用/当前 step；跨 step 保留需显式 clone/copy |
| `info["final_observation"]` | same-step 终止 | 与 observation 同树 | 只在 mask 行有意义；下一 step 前消费 |
| `read_device_state` | 显式查询 | owned snapshot | 可跨 step 保存；CPU 导出有拷贝代价 |

三个实际调用例子：

```python
# 1) 需要长期保留 UI 帧
frame = env.render()
saved = frame.copy()             # 防止后续覆盖（owned 时通常安全，但 copy 更明确）

# 2) 需要长期保留 task sensor
rgb = np.array(observation["task_rgb"], copy=True)

# 3) 只需要窗口时关闭展示、继续物理/传感器
env.close_render()               # device batch；scalar 用 close()
```

不要：

- 把 GPU `tensor.numpy()` 当零拷贝；需要 CPU 时显式 `.cpu()`；
- 把 sensor 默认 float32 套到 UI；
- 用旧步图像配新步状态；
- 通过额外 `render()` 生成训练观测。

## 6.4 Solution、记录、独立读回

### caller-owned Solution

```python
solution = build_readiness_solution(backend="cpu", controller_profile="r3_continuous_v1")
observation, info = env.reset(seed=31)
solution.reset(observation, info, env.metadata)
while not solution.done and not solution.failed:
    action = solution.act(observation, info)
    observation, reward, terminated, truncated, info = env.step(action)
    solution.observe(observation, reward, terminated, truncated, info)
    if terminated or truncated:
        break
```

- `reset/act/observe/done/failed` 是 caller-owned 生命周期；Env 不替它判定完成。
- `task_success`、`solution.done`、`expert_complete`、`planned_trajectory_completed`、`outcome_complete` 是不同字段；`completion_facts` 给出组合规则。
- Nut 的 `ExpertAction` 必须由原 Solution 生成；不要手写 identity。

### 记录

```python
env.start_recording("workspace/tutorial/run.h5")   # 必须在 reset 后、control_step==0
# ... steps ...
receipt = env.finish_recording("task_success" or "horizon_or_stop")
```

- `start_recording` 只允许一次，且在 reset 边界；`finish_recording` 返回 finalize receipt。
- 记录要求实际运行解释器能 import `h5py`；缺依赖会在启动记录时立即失败。
- H5 边界是 **T+1**（N 个 transition、N+1 个 observation/boundary）；不要用文件大小/存在推断完成。
- canonical 记录与 v3 物理记录的 schema 不同；读回用对应 reader：
  - `task_env.recorders.load_physical_recording_h5(path)`：物理 v3，校验 boundary/clock/control/outcome/可选 RGB capture identity；
  - `task_env.recorders.load_structured_control_records_h5(path)`：普通 v3 结构化控制；
  - `task_env.trajectory.canonical.h5.load(path)`：canonical H5；
  - `load_legacy_leaf_control_h5`：旧叶节点，只读兼容。

```python
from task_env.recorders import load_physical_recording_h5

record = load_physical_recording_h5("workspace/tutorial/run.h5")
print(record["transition_count"], record["observation_count"])
print(record["outcome"])
```

- completion 字段可能缺失或为 `null`；历史 canonical H5 缺失 completion 不补造，必须用同 run caller facts + 独立读回。
- 源身份不能由文件名推断；读回与 caller 必须同 run。
- 图像字节没有独立内容摘要；capture identity 描述边界，不等于像素正确性。

## 6.5 learner/vector 边界与迁移

| 入口/概念 | 当前支持 | 明确拒绝/未迁移 | 正确替代 |
| --- | --- | --- | --- |
| `make_env` | 四个正式任务 + 保留 component 路线 | 旧 candidate/退休 UID | 正式 UID + config |
| `make_parallel_env(execution='device')` | 两任务 × 三 provider 的 G06 交集 | Nut batch、R3 batch、异构行 | 本文 device 章 |
| `execution='remote'/'local'` | 旧 SB3 合同 | 不是 device 生命周期 | `execution='device'` |
| `step_device()` | 旧 component/RSL 兼容路径 | **device 模式拒绝** | `step()` |
| `BaseTaskEnv` | 2.x alias；Empty component | 不是新教程主线 | `SelectedReferenceEnv` / `make_env` |
| `step_expert()` | 受限兼容 | 不是标准 Env API | caller-owned Solution + `env.step` |
| `step_with_solution()` | 过渡兼容 | 不是所有路由支持 | 调用方 `act → step → observe` |
| `SB3FlattenVecWrapper` | learner 边界 flatten | 固定空间/autoreset 限制 | 明确 fixed-space consumer |
| RSL `step_device` adapter | 旧路线 | 不是正式 device 训练通过 | device `step()` + 自己的 learner 包装 |

旧 → 新参数/UID 对照：

| 旧写法 | 当前写法 | 异常/说明 |
| --- | --- | --- |
| `pick-cube-v1` / `nut-assembly-square-v1` | `pick-cube-p16-reference-v1` / `nut-assembly-outcome-reference-v1` | factory `ValueError`，不映射 |
| 顶层 `provider/backend/horizon` | `execution`/`episode` section | selected 配置拒绝未知顶层键 |
| `control.profile_id` / `task.controller_profile` | `controller.profile_id` | 旧选择器不是正式输入 |
| `recipe/environment` | 任务 YAML 默认 + selected section | 调用方不能替换 task-owned scene/object/agent |
| `build_reference` / `build_isaac_reference` / `build_runtime_source` | `make_env` + 正式配置；Solution 用 `build_readiness_solution` / `build_outcome_solution` | 退休直接构造入口 |
| `static_template.batch_physics_layout` | 仅 `merged_scene`；device batch 用 native_batch 解析 | 非默认 `static_template` 拒绝 |

不要为了兼容旧教程恢复退休生命周期、宽泛 kwargs、`getattr` 兜底链或第二套 reset/step。

## 6.6 排错表与可恢复信息

| 触发 | 失败阶段 | 实际异常/信息（典型） | 用户检查 | owner/链接 | 是否需重建 |
| --- | --- | --- | --- | --- | --- |
| 解释器/ABI 不对 | worker preflight | `deployment interpreter unavailable` / `worker interpreter unavailable` | 路径、可执行位、Python 版本 | [安装](installation-and-start.md) | 否（换解释器重试） |
| MuJoCo 版本冲突 | 安装/import | resolver 冲突；Core 要求 `<3.9`，GeoPhys 要求 `>=3.15` | 是否混装两份完整 requirements | [安装 1.4](installation-and-start.md) | 换独立环境 |
| GeoPhys 分支/pin 不符 | source 预检 | `scene` 来源不一致 / source identity 拒绝 | `GEOCHORA_GEOPHYS_SRC`、gitlink | [安装 1.2](installation-and-start.md) | 修 source 后重试 |
| SDK 子进程缺依赖 | Isaac 启动 | 子进程 import/初始化失败 | `execution.interpreter`、SDK 环境、EULA | [安装 1.6/1.7](installation-and-start.md) | 否 |
| source/mesh/delivery 缺失 | source 预检 | 缺文件、closure/manifest 不符 | asset root、manifest、gitlink | [资产/Robot](authoring-scenes-assets-robots.md) | 是（修正资产后重建） |
| 未知 profile/UID | 静态配置 | `KeyError: unknown environment uid` / `unsupported ... profile` | 注册 import、profile 拼写 | 6.1 | 否 |
| Controller shape/单位错误 | 动作计算 | `Controller action shape or finite values are invalid` / bounds | action 树、dtype、单位 | [Controller](custom-controllers.md) | 否 |
| Nut 普通随机拒绝 | 动作准入 | `selected NutAssembly requires a source-bound ExpertAction; unguarded external actions are not admitted` | 是否用原 Solution | [2.5](quickstart-state-only.md#25-nutassembly随机动作版当前真实缺口t-nut-random) | 否（需原 Solution） |
| unsupported renderer pair | renderer 构建 | `unsupported ... pair` / `RenderUnavailableError` | physics×renderer 准入 | [渲染](quickstart-rendering.md) | 是（换声明重建） |
| window 依赖缺失 | UI 构建 | display/GL 失败 | `DISPLAY`、驱动 | 3.7 | 否（改 `rgb_array`） |
| fault/stale | 运行中 | `selected execution is faulted; reset() is required` / stale context | 是否 reset/切换后继续用旧命令 | 6.2 | 是（显式 reset/重建） |
| 资源不足 | 构造/运行 | OOM/超时/RESOURCE_LIMIT | B、相机、窗口、进程树内存 | [device](quickstart-device-batch.md) | 缩小后重建 |
| close 失败 | close | 首个异常 + cleanup notes | 资源是否仍被占用 | 6.2 | 可重试 close；必要时重建 |

排错原则：

- 不推荐“重装全部依赖”“放宽门限”“关闭检查”“切换私有 solver”；
- 先定位最早失败阶段（静态配置 → source/资产 → worker/SDK → Controller → native），再决定是否重建；
- ACK、runtime-valid、task success、Solution completion、Qualification 是不同层，不能互相替代。
