# GeoChora

面向具身任务的多仿真器、多渲染器 API 与工具中枢。
当前公开基线为 [v1.1.0](docs/releases/v1.1/README.md)，于 2026-10-18 发布。
本版本整合 Core、selected task authoring 和开发工作流；带 documented breaking API changes，
不宣称 strict SemVer，也不代表 Phase II 完成。

`task_env/` 是 Core 唯一 owner。PhysPi 负责外部 Agent 编排、记忆、经验和 Skill 演进，
通过 GeoChora 公共 API 使用 Core；Core 再依赖 provider 公共/runtime-facing API。
Physics 与 Renderer 保持独立，task/recorder/planner 不读取 provider 私有 solver/renderer 状态。

## 开始使用

从仓库根目录和已准备的 Python 环境运行。仓库无根 packaging metadata，
依赖通过 `task_env/requirements.txt` 安装，按需增加 `task_env/requirements-rl.txt`。

```bash
git submodule update --init GeoPhys asset/external/mujoco_menagerie
export PYTHONPATH=GeoPhys/src:.
python - <<'PYTHON'
from task_env import make_env
env = make_env("pendulum-v1", config={"runtime": {"backend": "cpu"}})
try:
    observation, info = env.reset(seed=73)
    observation, reward, terminated, truncated, info = env.step(env.action_space.sample())
finally:
    env.close()
PYTHON
python examples/tasks/pick_cube.py --provider mujoco --seed 31
```

完整环境准备、selected public API、expert/record/inspect 命令及失败行为见
[TaskEnv 入口](docs/module/task_env/README.md)和[examples](examples/README.md)。
Selected NutAssembly CLI 保留 guarded `step_expert()`；另有 task-owned external Solution 路线，task outcome 与
Expert completion 分开记录。其 GeoPhys CPU/CUDA × gripper 100/500 Hz S2/S3 是逐子步公开 host snapshot 的
diagnostic comparison，不扩大 Provider capability 或 Qualification，详见
[C05c cadence report](docs/module/task_env/goal/Phase_II/C_Development_Record.md#c05c)。

## 当前能力边界

PickCube/NutAssembly × GeoPhys/MuJoCo CPU、100 Hz、指定 seeds 有 TESTED_BOUNDED receipts；
不授予新 formal qualification。NutAssembly GeoPhys accepted warning 和原 strict Expert failure
不因 Outcome Completion V1 改写。Pendulum learning/RGB 是 wiring smoke，无一般训练或 renderer 资格。
Go2 专用与 GeoChora-owned static-template physics 已退休，通用 RL/Batch/Device/Vectorization、
受限 GeoPhys-owned adapter 和 Renderer contracts 保留。精确 source/task/config/provider/Evidence
以[唯一矩阵](docs/module/task_env/capability_matrix_v1_1_0_candidate.json)为准。

v1.0.0 P1.0–P1.6 bounded approvals 保留原 source/scope；P1.7 deferred；历史 P1.8 diagnostics
不提升 formal acceptance。没有当前一般 manipulation PPO、checkpoint inference、native Flora/
GeoPhys Rigid Batch 或 Physics × Renderer qualification。

## 文档与 Agent 入口

| 主题 | Canonical 入口 |
| --- | --- |
| 系统定位、依赖和工作流 | [architecture](docs/global/architecture.md) |
| 模块/API/Skill 所有权与复用 gate | [ownership](docs/global/ownership.md) |
| 当前 TaskEnv contracts、使用与验证 | [TaskEnv](docs/module/task_env/README.md) |
| 已发布变化、migration、Evidence 和限制 | [v1.1.0](docs/releases/v1.1/README.md) |
| 历史 scoped baseline | [v1.0.0](docs/releases/v1.0/README.md) |
| Benchmark → TaskEnv → Harness 研究方向 | [roadmap](docs/roadmap/README.md) |
| Agent activation 与仓库规则 | [AGENTS.md](AGENTS.md) |
| 模块 Skill | [TaskEnv Skill](.agents/skills/geochora-task-env/SKILL.md) |

Task Artifact、Experiment 和 Evidence 必须独立存储。生成 workspace 不提交，
冻结任务变更要求新版本与 Human Judge；facts、approval、formal qualification 分离。
22 个 L2 原始文件及 hashes 保留。发布接受 same-account L2 copy 和历史备份风险，
并非完整历史 workspace 或独立管理域备份已验证；详见发布限制。

近期研究以 LIBERO + Panda + MuJoCo 的一条 native/canonical workflow 对照为候选，
优先 Oracle 验证、质量报告与 training-ready data；Harness/adapters/PhysPi integration 均为未来工作。
