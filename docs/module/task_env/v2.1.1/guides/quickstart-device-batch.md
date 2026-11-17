# Pendulum／PickCube device 并行与三后端选择

本页只教当前**正式 device 路线**：两个任务（`pendulum-v1`、`pick-cube-p16-reference-v1`）× 三个 batch provider（`mujoco_warp`、`geophys`、`isaacsim`）。旧 local/remote/SB3/RSL wrapper 是另一套合同，不能从类名推断兼容。

> **验证口径（2026-11-17）**：命令与参数按 `examples/parallel/*`、`task_env/vectorization/parallel.py` 和 G06 证据静态核对；**本轮没有启动 CUDA、没有重跑六格**。下表的“既有证据”都属于 G06 冻结交集，不自动扩展到其他 B、source 或 renderer。

## 4.1 共同入口与新旧并行路线区别

```python
from task_env import make_parallel_env

env = make_parallel_env(
    "pendulum-v1",
    num_env=3,
    backend="cuda",
    execution="device",
    env_config={
        "execution": {"physics_provider": "mujoco_warp"},
        "episode": {"seed": 73, "horizon": 20},
    },
)
try:
    observation, info = env.reset(seed=73)
    import torch
    actions = {"torque": torch.zeros((3, 1), dtype=torch.float32, device="cuda")}
    for _ in range(20):
        observation, reward, terminated, truncated, info = env.step(actions)
finally:
    env.close()
```

真实签名（`task_env/vectorization/parallel.py`）：

```text
make_parallel_env(
    uid,
    env_config=None,
    num_env=1,
    backend="cuda",
    *,
    execution="remote",
    start_method="spawn",
    compile_mode="fastest",
    **env_kwargs,
)
```

- `execution="device"` 选择设备 batch；`start_method` / `compile_mode` 只属于 SB3 worker，device 路线会拒绝非默认值。
- `env_config` 是 **selected 配置**（与 scalar 的 `config` 内容同义），不是第二个 `config` 参数。
- `execution='device'` 表示**生命周期/数据在设备 batch 上**；`execution.physics_provider` 才选择 `mujoco_warp` / `geophys` / `isaacsim`。两者不能互相替代。
- 三个 batch provider 名称就是 `mujoco_warp`、`geophys`、`isaacsim`；**不能用 `mujoco` CPU 冒充 MJWarp**。
- `device` 的正式接口是 `step()`。`HomogeneousVectorTaskEnv.step_device()` 在 device 模式下会明确抛 `RuntimeError('use step() for the coordinated device lifecycle')`；不要教 `step_device()`。
- 旧 SB3/RSL `step_device` 适配器不是正式 device 训练通过；旧 `local`/`remote` 也不自动具备 same-step autoreset、CUDA 相机或整批切换。
- `execution='device'` 的 worker 解释器由 `execution.interpreter` 或 provider 变量决定（见 [安装](installation-and-start.md#18-后端路径配置与优先级)）。

## 4.2 六个可复制命令

从仓库根运行；父进程用 Core 解释器，`--interpreter` 是所选 worker 解释器。

```bash
"$GEOCHORA_CORE_PYTHON" examples/parallel/pendulum_device.py --provider mujoco_warp --interpreter "$GEOCHORA_MJWARP_PYTHON" --num-env 3 --steps 20
"$GEOCHORA_CORE_PYTHON" examples/parallel/pendulum_device.py --provider geophys --interpreter "$GEOCHORA_GEOPHYS_PYTHON" --num-env 3 --steps 20
"$GEOCHORA_CORE_PYTHON" examples/parallel/pendulum_device.py --provider isaacsim --interpreter "$GEOCHORA_ISAAC_PYTHON" --num-env 3 --steps 20
"$GEOCHORA_CORE_PYTHON" examples/parallel/pick_cube_device.py --provider mujoco_warp --interpreter "$GEOCHORA_MJWARP_PYTHON" --num-env 3 --steps 20
"$GEOCHORA_CORE_PYTHON" examples/parallel/pick_cube_device.py --provider geophys --interpreter "$GEOCHORA_GEOPHYS_PYTHON" --num-env 3 --steps 20 --geophys-contact-mode discrete --geophys-contact-iterations 32
"$GEOCHORA_CORE_PYTHON" examples/parallel/pick_cube_device.py --provider isaacsim --interpreter "$GEOCHORA_ISAAC_PYTHON" --num-env 3 --steps 20
```

### 运行卡（六条共用）

| 必填项 | 取值 |
| --- | --- |
| 环境 | Linux；CUDA `cuda:0`；对应 provider 的隔离解释器；窗口默认关闭 |
| 身份 | Pendulum 或 PickCube；MJWarp 4.0.1/Warp 1.18.0；GeoPhys pin `198d30ac`；Isaac 6.2 |
| 前置与启动 | 先 `source scripts/setup/geochora-env.sh`；Isaac 还需 `OMNI_KIT_ACCEPT_EULA=YES`；从仓库根运行 |
| 输入/输出 | 脚本打印 JSON：`observation_shape`/`state_fields`、`camera_shapes`、reward/done、`episode_id`、`native_step`、`closed` |
| 结束 | `--steps` 到达 horizon；`finally: env.close()`；输出可写 `--output`（父目录必须真实） |
| 验证 | G06a/b/c 既有证据按 B3/指定 source 引用；六条命令的**参数**已静态核对；本轮 native=0 |
| 故障 | 解释器缺失/依赖错 → worker preflight；provider/backend 不符 → 配置 admission；GeoPhys 未显式 discrete/32 → 不能拿默认预算宣称已受测 |

逐条说明：

- `pendulum_device.py` 的 config 是 `execution={physics_provider}` + `episode={seed,horizon}`；脚本用 `torch.linspace(-1.5,1.5)` 生成 B 行力矩，在 Pendulum 的 `[-2,2]` 声明范围内。
- `pick_cube_device.py` 固定 `controller.profile_id='panda-direct-effort-v1'`、`robot.native_drive='disabled'`。动作是 8 路直接 effort，不是 R3 pose。
- GeoPhys PickCube 必须显式 `--geophys-contact-mode discrete`（映射到 `execution.geophys_contact_mode`）和 `--geophys-contact-iterations 32`（映射到 `runtime.body_contact_solver_iterations`）。`provider_default` 不触发这两项。
- GeoPhys 的 coupled/equality 预算来自 **source 约束与 provider 冻结配置**，不在该 CLI 单独暴露；接触迭代 32 不等于 coupled 预算 32，也不能说明默认预算的 10 mm 级穿透问题已解决。
- 首次启动可能等待 worker 构建、SDK/Kit 初始化和 kernel 编译/缓存；这不是“卡死”，但要以脚本的时间/资源预算为准。
- 输出 JSON 里 `contact_mode_requested/resolved`、`solver_iterations_requested/resolved` 只在 GeoPhys 有；用它们核对**实际**模式/预算，而不是抄命令行假设。

### 六格与既有证据（只读对账）

| 任务 | MJWarp CUDA | Isaac PhysX CUDA | GeoPhys CUDA |
| --- | --- | --- | --- |
| Pendulum | native batch、canonical torque、state/Task、部分 reset、窗口、记录 | 同左 | 同左；不需要传感器相机 |
| PickCube | native batch、source-bound effort、手指传动/接触、双相机/窗口、记录 | 同左；真实 collision filtering 负对照 | 有界交集；**必须显式 discrete/32** |

这些是 G06 的有界结果，不是“任意 B/source 都能跑”。G07 的九格（三 provider × seed 31/32/33、完整 PickCube Solution）属于 7b，不在本页被重跑或改写。

## 4.3 两个动作树与输出轴

### Pendulum

```python
import torch
shape = env.single_action_space["torque"].shape          # (1,)
actions = {"torque": torch.zeros((env.num_envs, *shape),
                                 dtype=torch.float32, device="cuda")}
observation, reward, terminated, truncated, info = env.step(actions)
```

- action 叶：CUDA float32 `[B,1]`，单位 N·m；
- observation：`observation["state"]["proprioception"]`，CUDA float32 `[B,3]`；
- `reward`：CUDA float32 `[B]`；
- `terminated`/`truncated`：CUDA bool `[B]`；
- `info["episode_id"]`、`info["episode_step"]`：逐行时钟，CUDA int64。

### PickCube

```python
shape = env.single_action_space["effort"].shape          # (8,)
effort = torch.zeros((env.num_envs, *shape), dtype=torch.float32, device="cuda")
observation, reward, terminated, truncated, info = env.step({"effort": effort})
```

- action 叶：CUDA float32 `[B,8]`；最后一路是对称手指 tendon 输入，**不是**把标量 R3 Solution 的 pose+opening 直接塞进 batch。
- observation 的 `state` 至少含 `ee_pose`、`joint_position`、`hand_pose`，每个叶前置 B 轴；具名相机在 `observation["cameras"][name]["rgb"]`。
- `single_action_space` / `single_observation_space` 描述单行；`action_space` / `observation_space` 描述批量。不要用单行 shape 去构造 `[B,...]` 时漏掉 B 轴。

### `read_device_state`

```python
state = env.read_device_state(("qpos", "qvel"))
print(type(state), state.identity)
print({name: tuple(value.shape) for name, value in state.arrays.items()})
```

- 返回**带 source/generation/revision/native clock 身份的 owned snapshot**，可以跨 step 保留；不是借用 buffer。
- `state.identity.native_step` / `native_time_s` 是 provider 事实；不同 provider 的 native clock 语义不同（MJWarp 每行 world time、Isaac 共享 simulation manager 时钟、GeoPhys direct solver step 计数），不能把后两者当逐 world 原生时钟。
- 字段（`qpos`、`qvel`、`body_position` 等）是 provider 公开的布局事实，不是可移植算法 API；不要把 solver 的 qpos 索引写进 Task 逻辑。
- 导出 CPU 会产生拷贝代价；训练热路径应尽量在设备上消费 observation/camera，不要每步 `read_device_state().cpu()`。

## 4.4 生命周期、相机与整批切换

### same-step autoreset 与 final observation

设备 `step()` 中，结束行会在**同一次调用**自动 reset：

- `reward`/`terminated`/`truncated` 属于**旧 episode**；
- 返回的 `observation` 属于 reset 后的**新 episode**；
- `info["_final_observation"]` 是 CUDA bool `[B]`，标记哪些行本次结束；
- `info["final_observation"]` 保留固定 B 轴和与 observation 相同的树结构，只消费 mask 为 true 的行；
- `info["final_mask"]` 是同一 mask 的兼容别名；
- `info["final_info"]` 提供旧 transition 的 env/episode/step/boundary/task info；`info["reset_info"]` 提供新身份；
- `info["final_episode_id"]`/`final_episode_step` 是旧行时钟。

不要用旧 mask 去索引新 episode 的 observation，也不要把 same-step 终止帧覆盖成 reset 后新首帧。相机时同理：终止帧在 `final_observation`，新首帧在 `observation`。

### 部分 reset

```python
import torch
mask = torch.tensor([True, False, False], device="cuda")   # 只重置第 0 行
observation, info = env.reset(seed=123, mask=mask)
```

- mask 是 CUDA bool `[B]`；省略即整批 reset。
- 只重置选中行；native 全局 step/time 不因逐行 reset 倒退。
- 未选行的物理状态、RNG 和 Task 计数保持；但共享 scene 的图像可能因选中行变化而改变（见下）。
- 每行独立维护 seed 和随机流；device 随机算法不保证与 NumPy 产生逐值相同的样本。

### 整批 provider 切换（只教已接收边）

```bash
"$GEOCHORA_CORE_PYTHON" examples/parallel/reconfigure_device.py \
  --task pick-cube \
  --isaac-interpreter "$GEOCHORA_ISAAC_PYTHON" \
  --mujoco-interpreter "$GEOCHORA_MJWARP_PYTHON"
```

等价核心调用：

```python
observation, info = env.reset(
    seed=31,
    options={"execution": {"physics_provider": target,
                           "interpreter": target_python}},
)
```

合同（G06c 有界接收）：

- 同一个 Env 对象、固定 Task/Robot/动作/观测/renderer/相机声明；
- 当前代表边是 **Isaac ↔ MJWarp**，两个任务各 A→B→A 已实际验证；
- **GeoPhys 跨 provider 切换未准入**；不要从“部分 reset 成功”外推。
- 切换时 mask 必须省略或全 true；Task/Robot 动作与观测空间、renderer/相机布局保持固定。
- 纯预检拒绝保留旧环境；替换开始后失败会进入 faulted，只能关闭并重新构造；清理失败时 `close()` 会重试尚未关闭的资源。
- 重建后 generation/materialization 区分新边界；旧 Robot view、reset selection 和旧状态不能用于新绑定；已有 owned snapshot 仍可作历史读取。
- renderer 选择与相机布局不变，但绑定旧场景的 GPU 资源会释放并为新场景重建；不能假定 native framebuffer 身份不变。

**shared scene 视觉隔离**：device 相机渲染共享的平铺场景，其他行的几何若进入视野，重置这些行可能改变未选行的图像，即使未选行物理状态和相机绑定不变。需要视觉隔离时检查相机视野和布局，不能只凭行状态未变假定逐像素不变。

### 窗口、相机与关闭

```bash
# 窗口 + 传感器（注意资源开销）
"$GEOCHORA_CORE_PYTHON" examples/parallel/pick_cube_device.py \
  --provider geophys --interpreter "$GEOCHORA_GEOPHYS_PYTHON" \
  --geophys-contact-mode discrete --geophys-contact-iterations 32 \
  --num-env 3 --steps 20 --sensor --window
```

- `--window` 设置 `render_mode='human'`，在 reset/step 后自动展示共享视口；`--sensor` 启用 base/hand 两个 CUDA uint8 相机。
- 传感器采集和窗口**彼此独立**：只开 `--sensor` 不创建窗口；只开 `--window` 不创建相机叶。
- `env.close_render()` 关闭窗口并停止自动展示，但物理和传感器可继续；有传感器时保留其 renderer。`env.close()` 释放全部资源。
- `render_mode='rgb_array'` 显式创建共享 GeoPhys Rasterizer；`env.render()` 返回 owned CPU NumPy uint8 视口图（尺寸由配置决定），不是 `[B,H,W,3]` 相机叶。
- 默认不创建可选 renderer 或相机传感器。

B=3 的资源数字见 [G06 实施总结](../maintenance/g06/implementation-summary.md) 的 B16 性能表；本页不给出未经测量的 batch 上限。缩小显存/内存的实际手段是减少 `num_env`、关闭 `--sensor`/`--window`、减少相机数量/尺寸，而不是修改 provider 私有预算。

### 不在本章扩展的范围

- NutAssembly batch；
- R3（位置/重力补偿）batch；
- 完整训练、任意 autoreset 模式、异构行、多 GPU；
- GeoPhys continuous mesh + 约束、跨 provider 切换；
- 旧 SB3 masked autoreset 再次包住 same-step Env reset。

这些仍是独立后续/未准入项，不能因为本页示例能构造就宣称已支持。
