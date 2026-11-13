# 安装、复用已有路径和启动单环境

3b attempt001 对既有环境执行了三路线短程检查，结果和限制见[3b attempt001执行摘要](../maintenance/reviews/20261105_3b_attempt001_execution.md)。GeoPhys 原生 rigid solver 不消费未选的 MuJoCo solver 声明；显式选择后者时仍检查其版本。Core 与 SDK 的安装清单和所选运行链依赖分开判定；这不证明两份 requirements 可以整体混装。

本页记录阶段3前维护中的入口；环境统一与下列组合的最终验收尚未完成。命令中的路径是占位符。仓库无根 packaging metadata，不使用 `pip install -e .`。训练和 renderer 都不是 state-only 首次启动的前提。

## 新克隆与已有安装

新克隆先按项目权限取得 Core，并初始化与该 Core commit 对应的 `GeoPhys` 和 `asset/external/mujoco_menagerie` 子模块；确认其 commit 与 Core 记录一致。已有安装可以在 checkout 外，显式提供其 Python、GeoPhys `src` 和所选 SDK 路径。不要让 Python 从另一份旧 Core 或 GeoPhys 导入。需要的 Python 包清单见 `task_env/requirements.txt` 和 `GeoPhys/requirements.txt`；资产还受任务和 provider 的具体声明约束。

| 路线 | 所需路径与当前边界 |
| --- | --- |
| GeoPhys CPU | Core checkout、与其匹配的 GeoPhys `src`、该路线所需 Python 包和任务资产；classic-control 单环境当前走此路线。GeoPhys 的 rasterizer 是可选 render 路线，不是 state-only 的前提。 |
| MuJoCo CPU | 已有 Core Python 环境中的 MuJoCo Python 绑定及任务资产；[MuJoCo 官方 Python 安装说明](https://mujoco.readthedocs.io/en/stable/python.html)说明其发行方式。当前 Core 声明 `mujoco>=3.8.1,<3.9.0`，GeoPhys 声明 `mujoco>=3.15.0`，区间无交集；不要将两份 requirements 的直接混装当成已验证方案。现有解释器中检测到 MuJoCo 3.8.1 不证明新安装组合可解析或全部路线可用。 |
| Isaac Sim | PickCube CUDA 直接入口使用所选 Isaac Python 和已安装 USD 资产；独立的 F06 Harness 仍要求精确 delivery manifest。需要兼容的 Core Python、SDK 和资产。参考 [NVIDIA Isaac Sim 安装文档](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_workstation.html)及 [NVIDIA Isaac Lab 6.2 安装说明](https://docs.nvidia.com/isaaclab/3.0/isaac-lab/installation)核对版本和平台。历史阶段3前维护窗口没有启动 Isaac 或验证全新安装；后续3b的既有6.2 pip环境运行见本页开头摘要。 |
| Flora | 可选外部 renderer，复用 `FLORA_ROOT` 或 `runtime_root`；布局与要求见 [Flora adapter](../../../../../task_env/render/flora/README.md)。本页启动器没有提供 Flora 路线，selected tasks 仍只接收 state-only。 |

在选定解释器中可用 `python --version` 和 `python -m pip show mujoco taichi-forge` 检查已安装发行包元数据；找不到 `geophys` 发行包不代表源码路径不可用。GeoPhys 的实际来源由下面的 `--geophys-src` 显式指定。不要凭上述元数据推断 native 任务成功。本轮未验证新克隆后的完整安装，也没有执行下载或安装。

### 准备路线的区别

- **新克隆**：先取得与 checkout 对应的子模块（例如在 checkout 中运行 `git submodule update --init --recursive`），再按所选 provider 准备隔离解释器、SDK、依赖与任务资产。先检查上表的依赖冲突；本轮没有验证全新安装，不承诺一组 requirements 可以同时满足全部后端。
- **复用已有环境**：保留已有解释器和 SDK，核对它们与本 checkout 及所选资产匹配，再按下节显式传入 Python、Core 与 GeoPhys 源码路径。启动器不会安装或替换它们。

## 启动一个已有安装的单环境

`examples/start.py` 只转调现有示例或 scalar public factory，不安装依赖、不自动切 provider。脚本、解释器和 `--geophys-src` 均需指向本次希望使用的安装；`--core` 默认是脚本所在 checkout，若显式提供其他 checkout 会报错。

2026-11-05 已在已有 Python 环境、`08a728ea` 源码上，通过本启动器的显式路径运行 Pendulum／GeoPhys／CPU／state-only 一次 reset、step、close；观测符合空间，锁和资源收据见[恢复后的验证记录](../maintenance/reviews/20261105_pre_stage3_resumed_physical_checks.md)。这只验证该环境中的一条启动路径，不代表新安装或其他组合已验证。

```sh
CORE=/absolute/path/to/GeoChora
PY=/absolute/path/to/core-python
GEOPHYS_SRC=/absolute/path/to/GeoPhys/src
"$PY" "$CORE/examples/start.py" --python "$PY" --core "$CORE" \
  --geophys-src "$GEOPHYS_SRC" --uid pendulum-v1 \
  --provider geophys --backend cpu --renderer none --seed 73
```

此命令重置一次、执行一个零扭矩 transition 并 close；`empty-v1` 和 `two-wheel-balance-v1` 也有对应 scalar 路线。选择 `--renderer rasterizer` 仅路由到已有 Pendulum RGB 示例。选择 `pick-cube-p16-reference-v1` 或 `nut-assembly-outcome-reference-v1` 时使用现有 task-owned Expert 示例，`--provider` 可选 `geophys` 或 `mujoco`，`--backend cpu --renderer none`。这些 Expert 示例执行至完成或 horizon，而不是一 transition。当前 selected 的 `--renderer` 非 `none` 会明确拒绝。

Isaac PickCube 的公开入口示例如下，**本轮尚未原生运行**：

```sh
"$PY" "$CORE/examples/start.py" --python "$PY" --core "$CORE" \
  --geophys-src "$GEOPHYS_SRC" --uid pick-cube-p16-reference-v1 \
  --provider isaacsim --backend cuda --renderer none --seed 31 --horizon 1000 \
  --isaac-python /absolute/path/to/isaac-python
```

`--isaac-python` 优先于 `ISAAC_SIM_PYTHON`；启动器要求两者之一。Isaac App 需要所选 SDK 的许可和环境，直接入口使用已安装 USD 资产；高级 F06 Harness 的 manifest 仍须匹配其冻结准入。缺解释器、GeoPhys `scene` 源码、已安装资产或不支持的组合会报错；不会下载或静默切换。直接 Isaac 示例不设置地址空间上限，资源规划需另行覆盖子进程。`GEOCHORA_GEOPHYS_SRC`、`GEOCHORA_CORE_PYTHON` 由启动器传入子进程；一般直接示例也可用前者选择已有 GeoPhys `src`。如果 `scene` 已从其他路径导入，bootstrap 要求使用新解释器，避免混用。

参数与错误路由已离线检查；上述启动命令和 renderer 在本维护版本的 native 运行仍待验收，不能因 `--help` 或离线测试通过而视为运行成功。

## 同一正式配置的 Python 与 YAML 写法

例如，PickCube／MuJoCo CPU 的配置可以直接作为 mapping 传入：

```python
from task_env import make_env

config = {
    "execution": {"physics_provider": "mujoco", "physics_backend": "cpu", "physics_device": "cpu"},
    "episode": {"horizon": 10},
}
env = make_env("pick-cube-p16-reference-v1", config=config)
try:
    observation, info = env.reset(seed=31)
finally:
    env.close()
```

相同内容也可保存为 `pick-cube.yaml`：

```yaml
execution:
  physics_provider: mujoco
  physics_backend: cpu
  physics_device: cpu
episode:
  horizon: 10
```

使用 `python -m task_env.script.env.single_from_file --env-id pick-cube-p16-reference-v1 --env-config pick-cube.yaml --backend cpu --horizon 10` 读取。该示例的命令行 `--backend` 覆盖 YAML 的 backend；文件中的其他正式字段按配置解析。要使用其他 provider，必须提供该 provider 支持的完整 backend/device 组合。此映射等价性已离线检查，不代表上述命令已在本轮执行物理仿真。

## 基于示例开发

阅读 [`examples/tasks/declared_marker.py`](../../../../../examples/tasks/declared_marker.py)：它声明 UID、Panda/table/box 组合、reset 范围与 `evaluate_task`，导入示例完成注册，再直接使用 public `task_env.make_env(uid, config=...)`。示例中的接线属于内部实现，不是稳定扩展 API。修改自己的 UID、声明和评价后，先通过同一 public factory 检查 reset、action/observation 和 close；需要 Expert 时将 Solution 留在任务 owner。当前自定义任务说明仍在迁移，最终规范 Env 扩展点以完成迁移后的源码和文档为准。
