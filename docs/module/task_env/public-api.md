# TaskEnv 公共 API

以当前 source 与[唯一发布矩阵](capability_matrix_v1_1_0_candidate.json)为准。
Root facade 的声明见 [`task_env/__init__.py`](../../../task_env/__init__.py)，
组件创建见 [`registry.py`](../../../task_env/registry.py)。未知 UID 抛 `KeyError`；
重复注册默认失败。注册只保存 class，不应在 import 时构造 physics runtime。

## 两类 scalar 构造

| 类型 | 公共入口与配置 | 当前语义 |
| --- | --- | --- |
| 通用 scalar | `make_env("pendulum-v1", config={"runtime": {"backend": "cpu"}})` | `BaseTaskEnv` 的 Gymnasium 生命周期；另有 `two-wheel-balance-v1` |
| PickCube selected reference | `make_env("pick-cube-p16-reference-v1", config={"provider": "mujoco", "backend": "cpu", "horizon": 6000})` | lift-only task predicate，保留 selected P1.6 Artifact |
| NutAssembly selected reference | `make_env("nut-assembly-outcome-reference-v1", config={"provider": "geophys", "backend": "cpu", "horizon": 6000})` | Outcome Completion V1；只允许 `step_expert()` |

两条 selected route 只接受 `provider`、`backend`、`horizon`：provider 仅
`geophys`/`mujoco`，backend 仅 `cpu`，horizon 为 `[1,6000]` 内整数；render_mode、extra kwargs、
legacy overlays 会失败。不要把通用 `runtime` section 传入 selected reference。
每个 selected task 由 task-owned `task.py`、`solution.py`、`config.yaml` 与 `__init__.py` 所有。
UID 与序列化 Artifact ID 不同；精确 Artifact/config hashes 只引用发布矩阵，避免重复维护。

## 生命周期与 evaluation

`reset(seed=...) -> (observation, info)` 在首次 step 前调用；
`step(action) -> (observation, reward, terminated, truncated, info)`。
终端后需 reset，不能继续 step；使用 `try/finally: env.close()` 释放资源。
通用 `BaseTaskEnv` 组合 task definition、reset sampler、runtime、action、observation 和 rendering。
`TaskEvaluation` 提供 reward、success、failure、metrics、reward_terms；reward 与
`info["is_success"]` 不能替代 Judge。通用 `ignore_done=False` 时 success/failure 可终止 episode，
horizon 产生 truncation；selected expert 的 stop/completion policy 必须单独读取。
Selected reference 同一 episode 不可混用 expert 和 external action；NutAssembly external action 明确拒绝。

## Facade、扩展与 advanced contracts

| API | Owner/import | 用途/限制 |
| --- | --- | --- |
| `make_env`, `make_agent`, `make_object`, `make_scene` | `task_env` | 注册组件构造，不证明执行能力 |
| `ENV_REGISTRY`, `AGENT_REGISTRY`, `OBJECT_REGISTRY`, `SCENE_REGISTRY` | `task_env` | 用 `uids()` 查询；扩展注册见 `task_env.registry` |
| `BaseTaskEnv`, `TaskEvaluation`, `RuntimeBoundary`, `ResolvedEnvConfig` | `task_env` | environment/config/snapshot 生命周期 |
| `resolve_env_config` | `task_env` | 解析并冻结公共配置；task-specific overlay 走 factory 分支 |
| `AssetManifest` | `task_env.environment` | assembly 资产声明；保留本地 source/root 与版本字段，可选稳定 source reference/revision 和 procedural generator 元数据；构造时不读文件，也不证明 importer 消费了对应 bytes |
| `make_parallel_env`, `register_parallel_env` | `task_env` | optional homogeneous factory，与 scalar 无互相 fallback |
| `TaskArtifact`, `ExecutionSpec`, `CanonicalStateView`, `admit_capabilities` | `task_env.artifacts` | advanced data/admission contracts；不从 root 假造导出 |
| `AssetDefinition`, `EntityInstance`, `SceneDefinition` | `task_env.artifacts` | Phase II A01 identity/provenance、A02 frames/articulations、A03 `scene-definition-v3` static composition；strict codec only，不构造 Provider/runtime |
| `FrameReference`, `FrameDefinition`, `ArticulationDefinition`, `JointDefinition` | `task_env.artifacts` | entity-qualified frame、固定变换、runtime anchors 与多 articulation topology；不执行 FK 或 provider lowering |
| `RobotInstance`, `ActuatorResourceDefinition`, `ActuatorReference`, `ControlGroup` | `task_env.artifacts` | Entity-qualified 的静态 Robot/actuator/group identity；`SceneDefinition.resolve_*` 仅解析静态声明，不定义 Controller、动作维数、native binding 或多 Robot 执行 |
| `RuntimeSession`, `materialize`, `provider_manifest` | `task_env.runtime.sessions` | advanced bounded session route；需合法 artifact/source/profile |
| `RecorderConfig`, `TransitionRecorder`, `TransitionRecordWrapper` | `task_env.recorders` | 既有录制 contract；selected examples 使用 selected env 自有录制入口 |

`TaskDefinition` 只消费公开 snapshot/state，不访问 solver。
`BaseTaskEnv` 的 scene/reset/task-definition hooks 是 Extension API，不是第二套 task factory。
配置公共 sections 包含 asset、scene、agents、objects、runtime、robot、action、observation、render、task、episode。
通用 action mode 包括 `absolute_pose`、`delta_pose`、`absolute_joint`；以每个 task/robot 的
`ExternalActionContract` 和 observation schema 为准，不能给 non-arm 强加 Panda 维度。

## Parallel、退休和缺失路线

`make_parallel_env` 要求显式 homogeneous registration。`execution="local"|"remote"`
控制进程边界，`runtime.batch_physics_layout="merged_scene"` 控制物理布局，两者独立。
Remote 使用 spawn，并在 child 重建 registry。未支持的任务不退化成 N 个 single env。
当前学习/渲染有界样例是 Pendulum CPU；不能据此宣称 manipulation batch 支持。

Go2 task/robot/profile/RSL 专用路线、GeoChora-owned static-template physics、旧 PickCube/NutAssembly
construction routes 和部分 camera/render CLIs 已退休，不能静默 alias。显式
`runtime.static_template.*` 及 `static_template` layout fail closed；默认 legacy config 对象残留
仅为保持无关 resolved identity，不代表 active implementation。
通用 RL/Batch/Device/Vectorization contracts 保留，GeoPhys-owned `GeoPhysRigidBatchRuntime`
不是已注册的 TaskEnv batch factory。详见[迁移](../../releases/v1.1/migration.md)。

统一 Validator、通用 `Runner(env, policy).run()`、完整 Task/Policy Harness 不作为当前 API。
现有 `task_env/alg/runner.py` 的 PPO dispatch 与各脚本 rollout loop 不能冒称统一 Runner。
符号级细节见 [API reference](../../../task_env/doc/api/index.md)。
