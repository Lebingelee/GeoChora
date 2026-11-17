# 单环境无渲染 Quickstart：Pendulum、PickCube、NutAssembly

本页只教 **state-only、单环境、CPU** 的真实公共入口。所有例子都从仓库根运行，使用 `task_env.make_env`，并在 `finally` 中 `close()`。例子中的路径由读者自己设定；不要覆盖旧 H5。

> **验证口径（2026-11-17）**
>
> 本页代码按当前源码、`examples/tasks/*` 和正式 caller 静态核对；**本轮没有启动 native、没有跑物理子步**。文中引用的历史运行证据只支持其原始 task/provider/source/seed 交集。随机交互例子是“合法交互”演示，不承诺任务成功。

## 2.1 共同交互合同

每段代码都围绕同一个合同：

```text
env = make_env(uid, config=<mapping 或 YAML 路径>, render_mode=None)
observation, info = env.reset(seed=...)
observation, reward, terminated, truncated, info = env.step(action)
env.close()
```

逐项解释：

| 元素 | 真实含义 |
| --- | --- |
| `make_env(uid, *, config, render_mode, **kwargs)` | 从 `ENV_REGISTRY` 构造一个单环境；selected 任务会解析 mapping/YAML，然后走共同 Task/Runtime 构建链。UD 不存在时报 `KeyError: unknown environment uid`。 |
| `config` | selected 任务的公共 section：`execution`、`episode`、`task`、`controller`、`robot`、`runtime`、`render`；不是任意字典透传。未知字段会拒绝。 |
| `reset(seed=...)` | 返回 `(observation, info)`。`seed` 同时影响 Core 任务随机流；某些任务有固定 provenance seed（Nut 见 2.5/2.6）。 |
| `step(action)` | 返回五元组 `(observation, reward, terminated, truncated, info)`。`reward` 是 Python float（scalar），`terminated/truncated` 是 bool。 |
| `observation_space` / `action_space` | Gymnasium 空间；action 树的键和 dtype 由当前 Task/Controller 决定，不能从别的任务移植。 |
| `metadata` | 构造/任务身份、action schema、render modes 等只读信息；不是 native 状态。 |
| `info` | 本步评价、Task metrics、边界/身份等；字段随路线不同。 |
| `close()` | 释放 Env 自有资源；`finally` 必须调用。关闭后不能继续 step。 |

`render_mode=None` 表示**不自动展示**，也不分配窗口；`env.render()` 返回 `None`。无渲染例子不声明相机，也不调用 `render()`。

两种随机性要分开：

- **task seed**：`reset(seed=73)` 决定任务初态/随机流；
- **随机动作**：需要单独的 `numpy.random.Generator`，如下面 Pendulum 例子。二者不能混成一个概念。

`env.action_space.contains(action)` 为真只说明动作在声明的空间内；它**不等于**任务 source 准入、Controller 可计算或动作会产生预期物理效果。

## 2.2 Pendulum：随机力矩完整文件

参考源码：`task_env/tasks/pendulum.py`（action `torque`，单位 N·m，范围 `[-2.0, 2.0]`；观测 `state.proprioception=[cos(theta), sin(theta), theta_dot]`）和现有 `examples/tasks/scalar_step.py`。

```python
# workspace/tutorial/pendulum_random.py   （读者自建；仓库不新增通用 CLI）
import numpy as np
from task_env import make_env

rng = np.random.default_rng(73)
env = make_env(
    "pendulum-v1",
    config={
        "execution": {"physics_provider": "geophys", "physics_backend": "cpu"},
        "episode": {"horizon": 100},
    },
)
try:
    observation, info = env.reset(seed=73)
    print("action_space:", env.action_space)
    print("observation_space:", env.observation_space)
    print("reset observation:", observation)

    for index in range(100):
        # tau ∈ [-2, 2] N·m；shape (1,)，float32，CPU
        torque = rng.uniform(-2.0, 2.0, size=(1,)).astype(np.float32)
        action = {"torque": torque}
        observation, reward, terminated, truncated, info = env.step(action)
        if index == 0:
            print("first step:", observation, reward, terminated, truncated)
        if terminated or truncated:
            print("episode ended at step", index + 1, "reason:", info.get("task_metrics"))
            break
finally:
    env.close()
```

### 运行卡

| 必填项 | 本例取值 |
| --- | --- |
| 环境 | Linux 参考路线；Core 解释器；GeoPhys CPU；不需要 display |
| 身份 | `pendulum-v1`；无 Robot/submodule 资产依赖；Geophys source 通过 `GEOCHORA_GEOPHYS_SRC` |
| 前置与启动 | `source scripts/setup/geochora-env.sh`；`"$GEOCHORA_CORE_PYTHON" workspace/tutorial/pendulum_random.py`；从仓库根运行 |
| 输入/输出 | action `{'torque': float32 (1,)}`，N·m；observation `{'state': {'proprioception': float32 (3,)}}`；reward float；done bool |
| 结束 | horizon 100；`terminated` 来自任务成功窗口，`truncated` 来自 horizon；无论哪种都在 `finally` 关闭 |
| 验证 | 静态核对源码/示例；历史 Pendulum 三 provider 短程与 G06 证据按原交集引用；**本轮 native=0** |
| 故障 | 缺 GeoPhys source → 启动 preflight；`torque` shape 非 `(1,)` → action 校验；MuJoCo 3.8.1 未装 → Core import |

逐行说明：

- `make_env` 只构造 Env，不推进物理；`reset` 才建立本次 episode。
- `torque` 是标量力矩，不是关节角速度，也不是位置目标；Pendulum 的 `theta=0` 是竖直向上，正方向绕 `+y`。
- 每一步 25 个 2 ms 子步（`PENDULUM_CONTROL_SUBSTEPS=25`），所以一个 `step()` 是 0.05 s 的控制间隔；循环 100 次是 5 s 仿真。
- `terminated` 通常表示任务成功条件达成；`truncated` 表示 horizon 到达。二者都不是“控制目标必然达成”。
- `info` 里可以看到 Task metrics；不同 provider 的身份/时钟字段不同。不要用 `is_success` 单独替代完整任务生命周期判断（见 2.7）。

### MuJoCo CPU 的最小差异

把 `execution` 改成：

```text
"execution": {"physics_provider": "mujoco", "physics_backend": "cpu", "physics_device": "cpu"}
```

其余任务合同不变。Isaac 只在下文安装/证据中链接，不把本页扩成全 provider 矩阵。Pendulum 的 device/CUDA 版本见 [device batch](quickstart-device-batch.md)。

## 2.3 PickCube：随机动作版

PickCube 默认的 R3 参考动作是 **8 维绝对 world pose**：

```text
[x, y, z, qw, qx, qy, qz, gripper]
```

- 前 3 维：世界坐标位置，单位 m；
- 中间 4 维：`wxyz` 四元数，必须是有限、非零范数（内部会归一化）；
- 最后 1 维：归一化夹爪命令，取值 `[-1, 1]`；Controller 把它映射到 `0.0`～`0.08 m` 开口（`ControlBinding('panda-v1/gripper', 0.08)`）；
- 这不是 8 个 motor effort。直接 effort 是另一个 profile，见 2.3 末尾。

随机策略的正确做法是**围绕 reset 后的实际 EE pose 做有界扰动**，保留有效四元数：

```python
# workspace/tutorial/pickcube_random_pose.py
import numpy as np
from task_env import make_env

rng = np.random.default_rng(31)
env = make_env(
    "pick-cube-p16-reference-v1",
    config={
        "execution": {"physics_provider": "mujoco", "physics_backend": "cpu"},
        "episode": {"horizon": 40},
    },
)
try:
    observation, info = env.reset(seed=31)
    print("action_space:", env.action_space)          # Box(-inf, inf, (8,), float64)
    print("state keys:", sorted(observation["state"]))

    measured = np.asarray(observation["state"]["ee_pose"], dtype=np.float32)  # [x,y,z,qw,qx,qy,qz]
    base_position = measured[:3].copy()
    quaternion = measured[3:].copy()
    quaternion /= np.linalg.norm(quaternion)           # 保持 reset 的合法姿态

    for index in range(40):
        position = base_position + rng.uniform(-0.02, 0.02, size=3).astype(np.float32)
        gripper = np.float32(-0.2)                     # 轻微闭合；+1 全开，-1 全闭
        action = np.concatenate([position, quaternion, [gripper]]).astype(np.float64)
        if not env.action_space.contains(action):
            raise ValueError("action is outside the declared PickCube space")
        observation, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break
finally:
    env.close()
```

### 运行卡

| 必填项 | 本例取值 |
| --- | --- |
| 环境 | Linux Core 解释器；MuJoCo CPU；无 display |
| 身份 | `pick-cube-p16-reference-v1`；默认 `r3_continuous_v1`；Menagerie pin `b846dd12` 的 Panda/table/box |
| 前置与启动 | `source scripts/setup/geochora-env.sh`；从仓库根运行脚本；需要 Core 环境中 MuJoCo 3.8.1 |
| 输入/输出 | action float64 `(8,)`；observation `state.ee_pose` float32 `(7,)`；可选 `state.joint_position`、`state.hand_pose` 取决于 profile；reward float |
| 结束 | horizon 40；短程随机动作通常 `truncated=True`，这不是失败根因；`finally: close()` |
| 验证 | 空间/字段由源码与 `examples/tasks/pick_cube.py` 核对；随机轨迹**没有**历史 native 证据；本轮 native=0 |
| 故障 | 四元数零范数 → pose 校验；shape 非 8 → action 校验；物体/资产缺失 → source/asset 预检；provider 组合不支持 → 配置 admission |

为什么范围适合短程教学：±2 cm 的位置扰动只演示“如何在不破坏姿态和夹爪语义的前提下产生合法动作”。它**不应完成任务**；`ee_pose` 的 reset 值也不是方块位置。需要成功时使用 2.4 的原 Solution。

显式 `panda-direct-effort-v1`／`native_drive='disabled'` 是另一条真实 profile：

```python
config = {
    "execution": {"physics_provider": "mujoco", "physics_backend": "cpu"},
    "controller": {"profile_id": "panda-direct-effort-v1"},
    "robot": {"native_drive": "disabled"},
    "episode": {"horizon": 8},
}
```

它的动作是 8 路直接输入（7 臂力矩 + 成对 tendon 力），**不是**把 R3 pose 数组当 effort 透传。该 profile 的 scalar 准入以其源码和配置为准；不要从 batch 例子移植出未验证能力。

## 2.4 PickCube：原 Solution 版

现成普通入口（`--recording` 是 `examples/tasks/pick_cube.py` 的真实参数）：

```bash
"$GEOCHORA_CORE_PYTHON" examples/tasks/pick_cube.py \
  --provider mujoco --seed 31 --horizon 1000 \
  --recording workspace/tutorial/pickcube-mujoco31.h5
```

等价的 Python 调用（不使用 Harness、不导入诊断包）：

```python
# workspace/tutorial/pickcube_solution.py
from task_env import make_env
from task_env.tasks.pick_cube import build_readiness_solution

env = make_env(
    "pick-cube-p16-reference-v1",
    config={
        "execution": {"physics_provider": "mujoco", "physics_backend": "cpu"},
        "episode": {"horizon": 1000},
        "controller": {"profile_id": "r3_continuous_v1"},
    },
)
recording = "workspace/tutorial/pickcube-mujoco31.h5"
try:
    solution = build_readiness_solution(backend="cpu", controller_profile="r3_continuous_v1")
    observation, info = env.reset(seed=31)
    solution.reset(observation, info, env.metadata)
    env.start_recording(recording)

    terminated = truncated = False
    transitions = 0
    while transitions < 1000 and not solution.done and not solution.failed:
        action = solution.act(observation, info)
        observation, reward, terminated, truncated, info = env.step(action)
        solution.observe(observation, reward, terminated, truncated, info)
        transitions += 1
        if terminated or truncated:
            break
    if transitions >= 1000 and not solution.done and not solution.failed:
        truncated = True

    print({
        "transitions": transitions,
        "terminated": terminated,
        "truncated": truncated,
        "task_success": bool(info.get("task_metrics", {}).get("task_success", False)),
        "solution_done": solution.done,
        "solution_failed": solution.failed,
        "expert_complete": getattr(solution, "expert_complete", None),
        "failure_reason": getattr(solution, "failure_reason", None),
    })
    print(env.finish_recording("task_success" if terminated else "horizon_or_stop"))
finally:
    env.close()
```

要点：

- `build_readiness_solution(backend='cpu', controller_profile='r3_continuous_v1')` 是 Task 门面；它从 Task/`PandaAgent` 声明构造 Solution，不需要 source workspace。
- 完成判定是**调用方持有 Solution** 的 `reset → act → step → observe`；Env 不替调用方解释 Solution 完成。
- `task_success`（原任务 predicate）与 `solution.done/failed`（策略生命周期）是不同事实；两者都要读。
- Solution 在成功边界可以提前停止，所以“267/438 等历史进度”不是每次都必须走满；历史计划轨迹完成字段可能为 `null`，不能补造成点列全发送。

### 运行卡

| 必填项 | 本例取值 |
| --- | --- |
| 环境 | Core 解释器；MuJoCo CPU；可选择 GeoPhys CPU（把 provider 改 `geophys`，backend 仍 `cpu`） |
| 身份 | `pick-cube-p16-reference-v1`；Panda Menagerie pin；`r3_continuous_v1` |
| 前置与启动 | `source scripts/setup/geochora-env.sh`；新 H5 路径；不要把旧证据文件覆盖 |
| 输入/输出 | Solution 产生 8 维 pose+开口；observation 同 2.3；H5 有 T 个 transition、T+1 个 boundary |
| 结束 | 任务成功可 `terminated`；horizon 到达为 `truncated`；策略失败为 `solution.failed`；`finally: close()` |
| 验证 | 既有 7b 九格与 E13/U3 完整 Solution 证据按各自 provider/seed 引用；**本轮没有重跑** |
| 故障 | 未知 profile、资产缺失、记录路径已存在、Solution identity 不匹配 → 分别由配置/资产/Recorder/Task owner 拒绝 |

独立读回（不构造 Env）：

```bash
"$GEOCHORA_CORE_PYTHON" examples/recording/inspect_h5.py \
  --input workspace/tutorial/pickcube-mujoco31.h5
```

`inspect_h5.py` 读取既有 canonical schema 并检查 T+1；它不重放任务，也不证明 D0 或任务成功。

### GeoPhys／Isaac 差异

- **GeoPhys CPU**：把 `execution.physics_provider` 改为 `geophys`；需要匹配的 `GeoPhys/src` 与依赖。历史 GeoPhys 完整 Solution 有原源码/identity 限制，不能写成“最新 HEAD 已复验”。
- **Isaac direct**：必须显式选择 SDK 解释器；backend/device 为 `cuda`/`cuda:0`。direct 入口使用已安装 USD 资产；F06 Harness 则是另一条要求 `--source-delivery-manifest` 的合同，不能混用两个命令。
- **Harness**：`--execution harness` 的 PickCube 只接受 `r3_continuous_v1`、horizon 1000、seed 31/32/33（其他 seed 需 `--diagnostic-seed`），并要求 fresh 输出目录。

## 2.5 NutAssembly：随机动作版（当前真实缺口，`T-NUT-RANDOM`）

**这一节不能删减或伪装完成。**

当前准备输入的源码事实：

- `task_env/tasks/nut_assembly/specialization.py::_binding` 设置 `external_actions=False`；只准入 source-bound `ExpertAction`。
- 同一 binding 的 `external_action_error` 是：`selected NutAssembly requires a source-bound ExpertAction; unguarded external actions are not admitted`。
- `_validate_external_solution` 要求实际 `NutAssemblyOutcomeSolutionV1`，并核对同 provider/source/config/clock/identity。
- `SelectedReferenceEnv._prepare_selected_step` 对普通数组在 `binding.external_actions=False` 时明确抛出 `RuntimeError`。

因此：**构造一个合法的 8 维 pose 数组仍然不足以实现普通随机策略**。伪造 `solution_identity`/`request_boundary`、手改 binding 或关闭 guard 都不是教程允许的做法。

下面是一个**预期拒绝**示例。它使用该 Task 实际准入的 seed 19（`None` 也解析为 19），确保失败发生在动作准入而不是 reset：

```python
# workspace/tutorial/nut_random_expected_refusal.py
import numpy as np
from task_env import make_env

env = make_env(
    "nut-assembly-outcome-reference-v1",
    config={
        "execution": {"physics_provider": "mujoco", "physics_backend": "cpu"},
        "episode": {"horizon": 10},
    },
)
try:
    observation, info = env.reset(seed=19)             # 固定 provenance seed；不要套用 73/31
    print("declared action space:", env.action_space)  # 仍声明参考 pose 空间
    action = np.zeros(8, dtype=np.float64)
    action[3] = 1.0                                    # 合法单位四元数
    try:
        env.step(action)
    except RuntimeError as error:
        print("EXPECTED REFUSAL:", error)
        assert "source-bound ExpertAction" in str(error)
    else:
        raise AssertionError("ordinary random Nut action was unexpectedly admitted")
finally:
    env.close()
```

### 运行卡

| 必填项 | 本例取值 |
| --- | --- |
| 环境 | Core 解释器；MuJoCo CPU；无 display |
| 身份 | `nut-assembly-outcome-reference-v1`；固定 seed 19；Panda／square-nut／square-peg |
| 前置与启动 | `source scripts/setup/geochora-env.sh`；从仓库根运行；需要 Menagerie 资产 |
| 输入/输出 | 声明空间是 8 维参考 pose；实际 `step` 在动作准入处抛 `RuntimeError`；没有任何物理 transition |
| 结束 | 捕获并解释错误后 `finally: close()`；**不得**把这个例子标为随机控制成功 |
| 验证 | 源码核对 `external_actions=False` 与错误文本；本轮 native=0；没有正向随机控制证据 |
| 故障 | 若用 seed 31/73 → reset 先报 `selected NutAssembly NA-S0 has fixed provenance seed19`；不要把它误诊为动作准入 |

### `T-NUT-RANDOM` 缺口表

| 项目 | 内容 |
| --- | --- |
| 用户需求 | 用普通随机 action（不伪造 Solution 身份）驱动 NutAssembly |
| 当前状态 | **未满足**（UNMET）。`external_actions=False`；普通数组在 `_prepare_selected_step` 被拒绝 |
| 真实 owner | Task 绑定 `task_env/tasks/nut_assembly/specialization.py` + `SelectedReferenceEnv` 的动作准入；不是 provider/Controller |
| 最小可能扩展点 | 由 Task owner 明确定义普通动作合同（例如新增/启用受控的 external action 模式）及其预检；本 7c 文档包**不实现**，也不放宽生产 guard |
| 是否由 7b 最终输入自然解决 | 准备输入中未解决；attempt002 应按 7b 接收后的源码复核。若仍无能力，交维护者裁定是否另开 task-local 接线 |
| 交付判定 | 预期拒绝示例**不等于**随机控制成功；整包只能报 `PARTIAL_DOCS_WITH_KNOWN_CAPABILITY_GAP` 中的这一能力缺口，不能以文档完整替代能力 |

## 2.6 NutAssembly：原 Solution 版

CLI（`examples/tasks/nut_assembly.py` 没有 `--recording` 参数；录制需用下面的 Python 入口）：

```bash
"$GEOCHORA_CORE_PYTHON" examples/tasks/nut_assembly.py \
  --provider mujoco --seed 19 --horizon 6000
```

等价 Python：

```python
# workspace/tutorial/nut_solution.py
from task_env import make_env
from task_env.tasks.nut_assembly.task import build_outcome_solution

env = make_env(
    "nut-assembly-outcome-reference-v1",
    config={
        "execution": {"physics_provider": "mujoco", "physics_backend": "cpu"},
        "episode": {"horizon": 6000},
    },
)
recording = "workspace/tutorial/nut-mujoco19.h5"
try:
    solution = build_outcome_solution(provider="mujoco")
    observation, info = env.reset(seed=19)             # 固定 seed19
    solution.reset(observation, info, env.metadata)
    env.start_recording(recording)

    terminated = truncated = False
    transitions = 0
    while transitions < 6000 and not solution.done and not solution.failed:
        action = solution.act(observation, info)       # 含来源边界与控制请求的 ExpertAction
        observation, reward, terminated, truncated, info = env.step(action)
        solution.observe(observation, reward, terminated, truncated, info)
        transitions += 1
        if terminated or truncated:
            break
    if transitions >= 6000 and not solution.done and not solution.failed:
        truncated = True

    print({
        "transitions": transitions,
        "terminated": terminated,
        "truncated": truncated,
        "task_success": bool(info.get("task_metrics", {}).get("task_success", False)),
        "solution_done": solution.done,
        "solution_failed": solution.failed,
        "failure_reason": getattr(solution, "failure_reason", None),
    })
    print(env.finish_recording("task_success" if terminated else "horizon_or_stop"))
finally:
    env.close()
```

解释：

- Nut 的外部 Solution action 中的来源边界和 control request 由**原 Solution** 生成；读者不手写内部 identity，也不应尝试自己构造 `ExpertAction` 的边界字段。
- 固定 `seed=19` 是 NA-S0 的 provenance 约束；`_reset_seed` 与 `sample_reset` 会拒绝其他 seed。本页不把固定 seed 例子描述成任意随机初态支持。
- MuJoCo 释放 1 mm、GeoPhys 释放 8 mm 是 task-owned 路由事实；不要把它做成公共 Env 特判或教程自行调参建议。
- 记录/完成/Task 成功分开：任务成功是原 predicate；Solution completion 是 caller-owned 生命周期；H5 独立读回是存储证据，不自动给出 completion。
- 短 horizon（例如 10 或 100）会得到 `truncated`，CLI 退出非零；这是**预期截断**，不是“任务失败根因”。

### 运行卡

| 必填项 | 本例取值 |
| --- | --- |
| 环境 | Core 解释器；MuJoCo CPU 或 GeoPhys CPU；无 display |
| 身份 | `nut-assembly-outcome-reference-v1`；seed 19；Panda + square nut/peg |
| 前置与启动 | `source scripts/setup/geochora-env.sh`；新 H5 路径；horizon ≤ 6000 |
| 输入/输出 | Solution 生成的 `ExpertAction`；`info` 含 native interval receipt 与 Task metrics；H5 记录 native 子步 |
| 结束 | 完整 Solution 计划走完并退回才成功；不足 horizon 会截断；`finally: close()` |
| 验证 | 既有 Nut seed19 MuJoCo/GeoPhys 完整运行与同次读回按原身份引用；当前源码未重跑；本轮 native=0 |
| 故障 | seed 非 19 → reset 拒绝；未准入 action → 2.5 的显式拒绝；horizon 不足 → 截断而非伪成功 |

Nut 的配置字段同样使用 selected sections；替换 provider 时只改 `execution`，不要猜 `robot.uid` 等字段。原/装配 Panda 的 `robot.uid` 与受测范围必须按实际字段核对后再写，未核对之前不猜。

### GeoPhys 与证据边界

GeoPhys 配置：

```text
"execution": {"physics_provider": "geophys", "physics_backend": "cpu"}
```

Nut 没有 Isaac/native batch 准入；GeoPhys 的完整成功历史与“当前源码未重跑”的限制分别标注，不能互相替代。原 GeoPhys 完整 Nut 路线的源码身份限制来自历史记录，不在本页被抹平。

## 2.7 一次完整运行结果怎样读

下面是一个**字段解释表**，不是某一次运行的伪造 JSON：

| 事实 | 从哪里读 | 不能推出 |
| --- | --- | --- |
| runtime valid | 构造、reset、每次 step、finalize、close 都成功；记录 T+1 有效 | 任务成功 |
| raw task predicate | `info["task_metrics"]["task_success"]` 或任务 owner 的 evaluation | Solution 完成、正式 Qualification |
| lifecycle task success | Env 的 `terminated` + Task evaluation + lifecycle 规则 | 所有 provider/seed 都成立 |
| Solution completion | 调用方 Solution 的 `done/failed` 与 `completion_facts(...)` | 仅凭 H5 文件存在或 `stop_reason=pass` |
| plan completion | `planned_trajectory_completed` 等字段；可能为 `null` | 补造成全轨迹已发送 |
| stop reason | `finish_recording(reason)` 的显式 reason、episode end | 用 `stop_reason=pass` 反推成功 |
| close | 退出码与 close 回执 | 平台进程清理一定完整 |

`examples/_common.py::completion_facts` 的实际优先级是：先看 `terminated/truncated/failed/not done`，再看 `task_failure`、`task_success`，最后看 `outcome_complete/planned/override`。因此：

- `truncated=True` 时 `failure_reason` 是 `environment_truncated_or_horizon_reached`，即使部分指标看起来“接近成功”；
- `policy_complete=True` 仍要求 `expert_complete` 和 lifecycle 检查，才可能 `completion_eligible=True`；
- `terminated=True` 时 `failure_reason` 是 `environment_terminated`，不等于自动通过。

读回必须使用正式 reader，而不是读文件是否存在：

```python
from task_env.recorders import load_physical_recording_h5, load_structured_control_records_h5

path = "workspace/tutorial/pickcube-mujoco31.h5"
record = load_physical_recording_h5(path)      # 带物理边界的 v3
# 或者（取决于写出的 route）：
records = load_structured_control_records_h5(path)
print(record.keys() if isinstance(record, dict) else record)
```

读回与调用方必须属于**同一次 run**；不要用不同 run 的部分结果拼成通过，也不要因为 H5 能打开就说任务成功。
