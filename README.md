# Geochora

面向具身智能的统一多仿真器、多渲染器 API 与工具中枢。

Geochora 提供稳定、可复现、可验证的任务构造、仿真执行、渲染展示、数据记录、学习评估与证据接口。它不替代物理引擎、渲染器、控制器、规划器、学习算法或 Agent，而是让这些能力能够通过一致的公共契约组合和验收。

PhysPi 是预期的上层 Agent 消费者：它基于 pi，负责 LLM 推理、工具编排、经验、记忆与 Skill；Geochora 负责可执行的仿真与渲染能力。二者通过 Geochora 公共 API 单向连接，Geochora 本身也可由人、脚本、CI 或其他 Agent 独立使用。

## 项目定位

Geochora 的核心问题是：如何用同一组任务和生命周期契约调用不同仿真器与渲染器，并把一个具身需求变成可以执行、展示、验证和复现的实验对象。

项目中的主要职责划分如下：

| 组成部分 | 主要职责 |
| --- | --- |
| PhysPi（外部） | 基于 pi 的 Agent；理解需求、编排工具、维护跨任务经验、记忆与 Skill |
| Asset Library | 提供机器人、物体、网格、纹理和其他被动资源 |
| Geochora Core | 提供任务、环境、运行时、控制、记录、学习、评估和 provider-neutral 展示契约 |
| Physics / Runtime Provider | 决定物理世界如何演化；当前以 GeoPhys 为主 |
| Render / UI Provider | 产生视觉观测、展示帧和统一 UI 所需的展示数据 |

Geochora Core 必须能够在没有 PhysPi 和外部 Asset Library 的情况下独立工作。人或 Codex 应当可以仅使用 Core API 和本地/默认资源完成任务构造、验证、数据采集、策略评估和结果报告。

## 总体架构

```mermaid
flowchart LR
    Requirement[用户需求] --> Client[PhysPi / 人 / Codex / 其他客户端]
    Client --> Core[Geochora Core]
    Assets --> Core
    Client --> Assets[Asset Library]
    Core --> Artifact[Task Artifact]
    Artifact --> Validate[验证与 Judge]
    Validate --> Experiment[Experiment Engine]
    Experiment --> Evidence[Experiment Evidence]
    Evidence -.受审查的经验回流.-> Client
    Core --> Physics[Physics Provider\nGeoPhys 当前主 provider]
    Core --> Render[Render Provider]
    Core --> UI[统一 UI / 展示契约]
```

当前仓库中的 Core 实现位于 [`task_env/`](task_env/)。GeoPhys 作为独立 Git 子模块提供物理/runtime 能力；Core 通过明确的 provider 边界使用它，不依赖 GeoPhys 的私有 solver 或 renderer 内部实现。

![Geochora 总体架构](docs/figures/整体架构.png)

图中的 Agent 与 Part B 表示 PhysPi 或其他外部消费层，不属于 Geochora Core。该图用于说明完整产品上下文；具体所有权以 `docs/global/` 中的规范为准。

## 一次任务的标准流程

### 阶段一：任务构造与验证

```text
用户需求
  -> Task Artifact candidate
  -> 机器人 / 场景 / 任务构造
  -> 自动 Validator
  -> 专家路线与随机化可行性验证
  -> Judge #1
  -> 冻结 Task Artifact vN
```

自动 Validator 负责检查定义和运行时有效性，包括配置、资产、provider 能力、初始状态、控制器/动作兼容性以及观测契约。专家路线负责检查当前实现是否能够执行；专家求解失败不能直接等同于任务本身不可行。通过 Judge 后，Task Artifact 才能被冻结并供实验引用。

### 阶段二：数据、学习与评估

```text
Frozen Task Artifact
  -> 专家数据生成
  -> 记录 / 回放 / 数据检查
  -> 策略训练
  -> 闭环仿真评估
  -> ID / OOD 与失败案例分析
  -> Judge #2
  -> Experiment Evidence
```

阶段二可以在阶段一允许的范围内调整训练参数和随机化策略，但不能静默修改任务语义、成功标准、随机化硬边界或冻结的评估分布。实验事实写入 evaluation report，是否接受由独立的 Judge decision 记录。

![Geochora 一次任务工作流](docs/figures/一次工作流.png)

## 当前 Core 能力

`task_env` 当前提供或集成以下能力：

- 环境、任务、机器人、物体和场景注册与配置；
- Gymnasium 风格的单环境生命周期，以及同构并行环境；
- 状态、特权状态、相机观测，以及 physics/render provider 边界；
- provider 能力声明、接入与资格验证所需的公共契约；
- 面向相机、帧、视口、叠加信息和 UI 客户端的统一展示契约方向；
- `absolute_pose`、`delta_pose`、`absolute_joint` 等控制/动作转换；
- 规划器和专家路线接入点；
- transition / trajectory 记录、H5 数据集、回放和转换；
- SB3、RSL-RL 等 learner 边界及 `runner(env, policy)` 式闭环执行；
- 任务评估、报告、实验和证据基础设施。

常用公共入口为：

```python
from task_env import make_env, make_parallel_env

env = make_env(
    "pendulum-v1",
    config={"runtime": {"backend": "cpu"}},
)
```

具体 API、配置和脚本入口见 [`task_env/README.md`](task_env/README.md) 及 [`task_env/doc/`](task_env/doc/)。

## 当前开发重点与能力边界

当前首要目标是构建可靠的多仿真器调用与多渲染器展示中枢。下列参考任务是 Core 和 provider 的资格验证路线，而不是 Geochora 的产品定义：

```text
PickCube -> NutAssembly -> Agent 生成的相近但未见过的操作任务
```

Go2 walk / RSL 是当前需要保持的 locomotion / RL 回归路线。当前 provider 范围如下：

| 能力 | 当前状态 |
| --- | --- |
| GeoPhys physics/runtime | current/default physics implementation provider；qualification 绑定具体 intersection |
| Linux 默认渲染 | GeoPhys 默认 renderer |
| Flora | provider 接入路径，主要面向 Windows，尚非首个 Core milestone 的主路线 |
| Phase-I primary physics targets | GeoPhys + MuJoCo（roadmap roles） |
| Phase-I boundary-validation targets | SAPIEN + Genesis（roadmap roles） |
| 统一 UI 展示 | provider-neutral 契约方向，具体客户端仍在演进 |
| OpenUSD | 场景交换、组合与可视化的候选方案，尚未确定为 canonical 格式或必选依赖 |

Phase-I provider 角色是 roadmap 目标，不代表 implemented、tested 或 qualified；具体计划以 [Phase I 蓝图](docs/module/task_env/05-phase-1-multi-simulator-blueprint.md) 为准。

能力声明必须以实际执行证据为准。Go2 CUDA/static/RSL 是当前最强的 current-HEAD tested regression route；P1.0 bounded evidence 未将其提升为 formal qualification；PickCube 和 NutAssembly 已有任务语义与相关入口，但完整 physics execution、随机化可行性、采集/保存/加载/回放 oracle 仍在完善，不能仅因任务注册或类可导入就宣称端到端支持。

首个 Core milestone 明确不包含：PhysPi 的记忆与 Skill 实现、自动 Core patch 或递归自我改进、OpenUSD 强制集成、软体任务、手机视频到数字孪生、3DGS sim-to-real、大规模 VLA/WAM 训练、强制真实机器人部署，以及所有 planned provider 的完整支持。

完整或部分的 real -> sim -> policy -> real 验收是长期方向；只有在对应接口、provider 路线和证据完成后，才能声明具体能力已经获得资格验证。

## 快速开始

### 环境准备

开发通常从仓库根目录执行。需要 Python 3.10+、可用的 GeoPhys 子模块和对应后端依赖；CUDA 训练与大规模并行还需要兼容的 NVIDIA 驱动。

```bash
git submodule update --init --recursive

python -m pip install -r task_env/requirements.txt
# 并行环境、SB3 或 PPO 需要时再安装：
python -m pip install -r task_env/requirements-rl.txt

export PYTHONPATH=GeoPhys/src:.
```

建议使用仓库已有的 GeoPhys Python 环境。不同 physics/render provider 对图形库、GPU 驱动和显示会话的要求不同；无图形环境时优先使用 CPU 或 headless 入口。

### 运行一个最小环境

```bash
PYTHONPATH=GeoPhys/src:. python - <<'PY'
from task_env import make_env

env = make_env("pendulum-v1", config={"runtime": {"backend": "cpu"}})
try:
    observation, info = env.reset(seed=73)
    for _ in range(3):
        observation, reward, terminated, truncated, info = env.step(
            env.action_space.sample()
        )
        if terminated or truncated:
            observation, info = env.reset()
finally:
    env.close()

print("TaskEnv smoke OK")
PY
```

也可以使用脚本入口：

```bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.env.single_inline \
  --env-id pendulum-v1 --backend cpu --steps 3 --horizon 10
```

### 运行训练或轨迹流程

下面是仓库中已有的参考入口；参数、资源需求和能力边界请以对应脚本及文档为准：

```bash
# Pendulum 并行 PPO smoke
PYTHONPATH=GeoPhys/src:. python -m task_env.script.rl.pendulum_ppo \
  --num-env 8 --backend cpu --updates 3 --rollout-steps 5 \
  --output-dir temp_outputs/task_env/pendulum_ppo_quickstart

# PickCube trajectory collection
PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory collect \
  --env_id pick-cube-v1 --backend cpu --num-traj 1 --horizon 600 --no-render \
  --output temp_outputs/task_env/trajectories/source.h5
```

运行产物默认写入 `temp_outputs/`，该目录不属于提交到 Git 的源代码。

## Task Artifact、Experiment 与 Evidence

任务定义、实验配置和实验事实是三个不同的一等对象：

```text
Task Artifact version 1 -> 多个 Experiment
Experiment             -> 一个 canonical Evidence package
```

推荐的本地工作区结构如下。`workspace/` 不提交到 Git：

```text
workspace/
└── tasks/<task_id>/
    ├── artifacts/ver_001/
    │   ├── manifest.yaml
    │   ├── asset.py
    │   ├── solution.py
    │   ├── task.py
    │   ├── validation/
    │   └── judge_decision.yaml
    └── experiments/exp_001/
        ├── experiment.yaml
        ├── evidence.json
        ├── evaluation_report.json
        ├── report.md
        ├── judge_decision.yaml
        ├── videos/
        ├── trajectories/
        └── refs/
```

`evaluation_report.json` 和 `report.md` 记录事实、指标、失败案例和资源信息；`judge_decision.yaml` 记录明确的 approve/reject 决策；`evidence.json` 记录任务、实验、Core/provider 版本、数据、评估结果和产物引用。实验只能引用冻结的 Task Artifact，不能把冻结任务复制成实验内部的临时副本。

## 长期证据回流（非当前 RSI 目标）

Evidence 可以经过人工或受治理流程回流为三类改进：修正当前 Task Artifact；由 PhysPi 沉淀跨任务经验与 Skill；将反复验证的通用需求提交为 Geochora Core 的受审查软件更新。Evidence 本身不授权自动修改 Core，RSI 也不是当前目标。

![Geochora Evidence 驱动的三级改进闭环](docs/figures/改进方案.png)

上图表达的是长期、带审查门槛的反馈方向，不代表仓库已实现自治式自我改进。

## 仓库边界

```text
Geochora/
├── task_env/   # Geochora Core 的 canonical 实现
├── asset/      # 可复用资产的导入/解析接口
│   └── external/mujoco_menagerie/  # 外部资产 Git 子模块，仅记录链接
├── GeoPhys/    # GeoPhys Git 子模块与 physics provider
├── docs/       # 当前架构、契约与治理规范
└── workspace/  # 本地任务/实验工作区，不提交到 Git
```

核心边界包括：

- `task_env` 是任务/环境 Core 的唯一 canonical owner，不与 GeoPhys 保留第二份主动维护的 `task_env`；
- GeoPhys 只由 Core 通过 public/runtime-facing API 使用，GeoPhys 不依赖 Geochora；
- 可复用复杂资产归 `asset` 接口管理，简单任务局部资产可以跟随 Task Artifact；
- 单任务修复留在 Task Artifact；跨任务可复用的 Agent 知识与 Skill 归 PhysPi；需要改变共享可执行能力的修改才进入 Core，并经过资格与回归验证；
- Core 不通过读取 provider 私有状态来弥补 provider 缺失能力。

Geochora 后续可以位于 PhysPi 项目的路径下供其调用，但目录位置不会改变所有权和依赖方向：PhysPi -> Geochora 公共 API -> provider 公共 API。

## 文档导航

| 主题 | 文档 |
| --- | --- |
| 系统定位、架构和两阶段工作流 | [`docs/global/00-system-architecture-anchor.md`](docs/global/00-system-architecture-anchor.md) |
| 仓库所有权与 provider 边界 | [`docs/global/01-repository-ownership-and-boundaries.md`](docs/global/01-repository-ownership-and-boundaries.md) |
| Core API 与能力范围 | [`docs/module/task_env/02-core-api-and-capability-scope.md`](docs/module/task_env/02-core-api-and-capability-scope.md) |
| Task Artifact、Experiment、Evidence 契约 | [`docs/module/task_env/03-task-artifact-experiment-evidence-contract.md`](docs/module/task_env/03-task-artifact-experiment-evidence-contract.md) |
| Core 资格验证与治理 | [`docs/module/task_env/04-core-qualification-and-governance.md`](docs/module/task_env/04-core-qualification-and-governance.md) |
| Phase I 多仿真器实施蓝图（active plan，非 capability claim） | [`docs/module/task_env/05-phase-1-multi-simulator-blueprint.md`](docs/module/task_env/05-phase-1-multi-simulator-blueprint.md) |
| Phase I contract 与 provider 边界（active plan，非 capability claim） | [`docs/module/task_env/06-phase-1-contracts-and-provider-boundaries.md`](docs/module/task_env/06-phase-1-contracts-and-provider-boundaries.md) |
| Phase I smoke 与验收规范（active plan，非 capability claim） | [`docs/module/task_env/07-phase-1-smoke-testing-and-acceptance.md`](docs/module/task_env/07-phase-1-smoke-testing-and-acceptance.md) |
| Phase I 调试与恢复手册（active plan，非 capability claim） | [`docs/module/task_env/08-phase-1-debug-and-recovery-playbook.md`](docs/module/task_env/08-phase-1-debug-and-recovery-playbook.md) |
| TaskEnv API、脚本和 quickstart | [`task_env/README.md`](task_env/README.md) |
| GeoPhys provider | [`GeoPhys/README.md`](GeoPhys/README.md) |

## 开发与验证原则

- 一次只推进一个明确的变更单元，开始前声明范围和非目标；
- 以真实调用路径、运行时/backend provenance 和可复现证据判断能力，不以注册表、可导入类或单个 demo 推断通用支持；
- Core 更新必须保留已有资格化能力，并通过 API/契约、golden-path task 和 provider/system regression 分层验证；
- 评估结果与接受决策分离，Evaluator 产出事实，Judge 产出明确的 approve/reject；
- 任务级变化、可复用技能变化和 Core 能力变化遵循不同的所有权与审查路径。
