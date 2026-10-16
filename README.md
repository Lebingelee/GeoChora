# Geochora

面向具身智能的统一多仿真器、多渲染器 API 与工具中枢。

当前公开基线是 [GeoChora v1.0.0](docs/releases/v1.0/README.md)：它接受限定的 Phase I Core baseline，不代表原 Phase I 蓝图已经完成，也不授予新的 task、provider 或 policy 资格。P1.0–P1.6 保留各自原有的 bounded approvals；P1.7 仍为 deferred；P1.8 的生命周期、时间基准、guard 和流式 recorder 基础设施在声明范围内完成测试，但 NutAssembly 结果仍属开发或诊断证据。完整状态见 [Phase I mainline 记录](docs/module/task_env/phase1_mainline_integration/README.md)、[v1.0 证据索引](docs/releases/v1.0/evidence_index.json) 和 [Phase I follow-up](docs/roadmap/phase1_followups.md)。

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

`task_env` 当前提供或集成以下 Core 接口和实现：

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

接口存在、任务已注册或类可导入，都不等于某条 task/provider 路线已获资格。v1.0 的资格只覆盖发布证据索引所列的具体交集：P1.0–P1.6 各自保留原 bounded approvals；其中 P1.5 是限定的 PickCube expert 路线，P1.6 是限定的 PickCube V2a policy/D3 结果，不扩展为通用任务、learner 或 provider 批准。

P1.7 的完整 visuomotor 路线尚未资格化。P1.8 的基础设施回归在声明范围内通过；NutAssembly MuJoCo 的 FULL/D0/D1/D2 结果仍是绑定其来源的 development evidence。GeoPhys 50/100/500 Hz FULL 均保留原 `stable_height_mismatch` Expert gate failure；shadow sequence 后出现的插入、释放和原始 task-success predicates 不构成 lifecycle-valid Expert completion。GeoPhys D0 50 Hz 在 transition 157 首次分歧、属 partial/invalid reconstruction；GeoPhys-source D1 和 frozen-action D2 是 diagnostic execution，不是 formal cross-provider qualification。Human review 与正式 P1.8 qualification 均未完成。细节和已知限制见 [发布进度表](docs/releases/v1.0/phase1_progress_summary.md) 与 [限制清单](docs/releases/v1.0/known_limitations.md)。

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

能力声明必须以实际执行证据和对应的 bounded decision 为准。Go2 CUDA/static/RSL 是当前 HEAD 的回归路线，不扩大 task/provider qualification。PickCube 有 P1.5 expert 与 P1.6 policy 的限定结果，但不代表所有 provider、随机化分布或数据工作流均获批准；历史 P1.8 NutAssembly 证据按上文保留。S1.6 的独立 Outcome V1 路由在 100 Hz GeoPhys/MuJoCo 完成具名完整轨迹的 bounded functional acceptance；S2-A 新公开 `make_env` 路由也已在相同 provider/seed 交集完成四条完整 CPU 功能回归。PickCube GeoPhys 原测试包装器在 H5 finalization 后因阶段字段、时钟容差和 grouped-step 计数检查错误返回 FAIL；独立 H5 合同验证及与 S1.5 的逐 transition/boundary 对照通过。后续提交 `0f27225a` 修正了 trajectory record CLI 的失败结果门控。新入口没有继承 P1.6 checkpoint 或 P1.8 FULL/D0 资格。详见 [S2-A 最终审阅](docs/module/task_env/p2_0_s2_a_final_review.md) 和 [当前 reference 入口](docs/module/task_env/p2_0_active_task_consumers.md)。

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

# Selected P1.6 reference recording (S2-A API migration under review)
PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory collect \
  --env-id pick-cube-p16-reference-v1 --provider geophys --seed 31 \
  --horizon 6000 --output workspace/new-run/pickcube.h5
```

所选 reference 的 [S2-A 入口和不兼容迁移说明](docs/module/task_env/p2_0_active_task_consumers.md) 区分 active construction 与 historical recovery。新 reference 录制写入 ignored `workspace/`；旧示例输出 `temp_outputs/` 也不属于 Git 源码。

## Task Artifact、Experiment 与 Evidence

任务定义、实验配置和实验事实是三个不同的一等对象：

```text
Task Artifact version 1 -> 多个 Experiment
Experiment             -> 一个 canonical Evidence package
```

推荐的本地工作区结构如下。`develop` 中的 `workspace/` 数据按本地工作区管理并由 `.gitignore` 忽略。历史 P1.6 closure metadata 的权威副本保留在不可变的 [v1.0.0 evidence index](https://github.com/Lebingelee/GeoChora/blob/v1.0.0/workspace/qualification/phase1/p1_6_closure/evidence_index.md) 及其 release tree；本地副本和归档仍需按 [Evidence 归档所有权规则](docs/maintenance/p2_0_part_a.md) 保全，不能仅因目录名为 `workspace/` 就删除证据。

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
└── workspace/  # 本地任务、实验、维护与归档证据；develop 不跟踪生成数据
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
| v1.0 release evidence and limits | [`docs/releases/v1.0/README.md`](docs/releases/v1.0/README.md) |
| Phase I follow-up tracks | [`docs/roadmap/phase1_followups.md`](docs/roadmap/phase1_followups.md) |
| Phase II roadmap | [`docs/roadmap/phase2_plan.md`](docs/roadmap/phase2_plan.md) |
| GeoPhys provider | [`GeoPhys/README.md`](GeoPhys/README.md) |

## 开发与验证原则

- 一次只推进一个明确的变更单元，开始前声明范围和非目标；
- 以真实调用路径、运行时/backend provenance 和可复现证据判断能力，不以注册表、可导入类或单个 demo 推断通用支持；
- Core 更新必须保留已有资格化能力，并通过 API/契约、golden-path task 和 provider/system regression 分层验证；
- 评估结果与接受决策分离，Evaluator 产出事实，Judge 产出明确的 approve/reject；
- 任务级变化、可复用技能变化和 Core 能力变化遵循不同的所有权与审查路径。
