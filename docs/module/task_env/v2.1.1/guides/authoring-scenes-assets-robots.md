# 环境构建、资产实例、Robot 与 canonical action

本页讲清一条执行链：**声明 → source composition/compiler → binding → SelectedReferenceEnv → RuntimeSession/provider**。目标不是让读者记住类名，而是知道“要改哪一层”和“不能把哪两件事混在一起”。

> **验证口径（2026-11-17）**：本页按 `examples/tasks/declared_marker.py`、`task_env/artifacts/*`、`task_env/assembly/source_composition.py`、`task_env/robots/*` 静态核对；**本轮没有构造资产、没有启动引擎**。7b 正在变化的 BodyWrench producer/transport/API 标 `WAIT_7B_ACCEPTANCE`。

## 5.1 从最小场景理解唯一执行链

```text
Task / Robot / Scene declarations
        │  (UID、语义、资产引用、初态、评价)
        ▼
source composition / compiler
        │  (MJCF/USD → provider source、closure、named entities/channels)
        ▼
binding
        │  (ReferenceTaskBinding、PhysicalControlBindingV1、writer/units)
        ▼
SelectedReferenceEnv  ← 唯一 public Env / reset / step / close owner
        │
        ▼
RuntimeSession / provider  ← 唯一 native 推进、状态发布、清理 owner
```

责任切分：

| 角色 | 拥有 | 不拥有 |
| --- | --- | --- |
| Task Artifact/Definition | 任务语义、reset sampler、成功 predicate、Solution owner | provider 索引、native 句柄、全局控制器注册 |
| Robot/source recipe | 资产组合、命名关节/Frame/TCP、传动、source profile | Task 成功语义、直接写 provider 私有数组 |
| Controller | 动作解释、状态依赖计算、typed contribution | 推进物理、提交/合并/清理（由现有 execution owner 做） |
| SelectedReferenceEnv | 公共 reset/step/render/close、随机流、episode transaction | 第二套 Runtime、provider 内部实现 |
| RuntimeSession/provider | native 构建、推进、状态/时钟、ACK、清理 | Task 语义或用户可见的伪 API |

`reset` sampler 只产生**命名初态**；`TaskDefinition` 只做语义；`Controller` 只计算；`Runtime` 独占 native 推进/清理。不要为了降低教程难度创建第二 Env/Runtime，也不要通过 `solver.qpos` 私有索引实现 Task。

真实构造顺序（以 PickCube 为例）：

1. `make_env('pick-cube-p16-reference-v1', config=...)` 进入 `registry.make_env`；
2. selected 任务用 `configuration.resolve_task_env_config` 解析七个 section；
3. `PickCubeReferenceEnv` 的 binding 通过 `task_env.tasks.pick_cube.specialization` 构造 `ReferenceTaskBinding`；
4. `SelectedReferenceEnv.from_resolved_config` 创建 Env，`reset` 时建立/复用 source+RuntimeSession；
5. `step` 把公共 action 交给已绑定 Controller，再交给 session 的 control submission；
6. session 发布 canonical state/feedback，Env 生成 observation/info；
7. `close` 按 owner 顺序释放 recorder、相机、session、source。

## 5.2 导入资产与构建实例必须分开讲

至少两种来源：

1. **已 pin 的 MJCF/mesh closure**（Menagerie Panda/table/box 等）；
2. **已准入的 USD delivery**（Isaac 场景）。

不承诺通用 URDF/任意网格自动成为可仿真 Robot。资产“能构造数据类”不等于“已导入仿真”。

| 阶段 | 真实 owner/类型 | 必须理解的内容 |
| --- | --- | --- |
| 源身份 | `AssetDefinition`、组件 `AssetManifest` | 稳定 URI/版本/内容/来源 vs 本地路径；mesh/textures/includes closure；源文件不在 step 中改写 |
| 表示与交付 | `task_env/artifacts/contracts.py`、`task_env/artifacts/asset_scene.py`、`task_env/assembly/asset_scene.py` | 受支持表示、USD bindings/prepare/load、原始检查；manifest ≠ runtime 准入 |
| 场景实例 | `EntityInstance`、`SceneDefinition`、`PoseWorld` | 同一 asset 可有不同 `entity_id`；初始位姿/速度属于实例；资产本身不保存 native 句柄 |
| Robot 实例/引用 | `RobotInstance`、`FrameReference`、`JointReference` | 命名关节/Frame、TCP、axis/sign/单位、source 映射；asset ID 与 entity ID 不能混用 |
| 编译与提交 | `task_env/assembly/source_composition.py`、`task_env/runtime/sessions/source_composition_adapters.py` | lowerer 拥有 provider 转换；Task 不写 provider 索引；Scene 只有一个推进 owner |

### 一个真实的 AssetDefinition + EntityInstance 配对

```python
from task_env.artifacts import AssetDefinition, EntityInstance, PoseWorld

asset = AssetDefinition(
    "asset-definition-v1",
    "menagerie-panda",                       # asset_id
    "menagerie-b846dd12",                    # asset_version
    "mujoco-menagerie://franka_emika_panda/panda.xml",
    source_revision="b846dd12bc459d776cccb3dee0b1d02acbf7a9c7",
)
asset.validate()

first = EntityInstance("entity-instance-v1", "panda-a", asset.asset_id, asset.asset_version)
second = EntityInstance("entity-instance-v1", "panda-b", asset.asset_id, asset.asset_version)
first.validate()
second.validate()
print(first.identity_hash == second.identity_hash)   # False：entity identity 不同
print(first.asset_id == second.asset_id)             # True：同一个 asset
```

要点：

- `source_reference` 必须是稳定 URI，不接受 `file:` 或本地绝对路径；本地路径应属于 runtime asset root，而不是资产身份。
- 本 pin 的 Panda/Menagerie 资产根是 `asset/external/mujoco_menagerie/franka_emika_panda/`；mesh 在 `assets/` 下（obj/stl），MJCF 通过 include/mesh 引用。closure 检查要覆盖这些文件，缺 mesh 时先核对 gitlink 和 asset root。
- `source_revision` 是 pin（本例 Menagerie gitlink），不是分支名。
- 两个 `EntityInstance` 共享同一资产版本，但 `entity_id` 不同，因此是不同场景实例；**不能混用 asset ID 与 entity ID**。
- `PoseWorld(position, quaternion_wxyz)` 的 quaternion 必须已归一化；初始位姿/速度属于 episode/实例，不属于 asset 定义。

### 接入真实 Scene

不要手写一个平行 Scene。内置任务通过声明和 compiler 构造 Scene；例如 `examples/tasks/declared_marker.py` 复用 `PandaBoxDeclaration` 与：

```python
from functools import partial
from task_env.assembly.panda_box import compile_panda_box_task
from task_env.environment.reference_binding import ReferenceTaskBinding
from task_env.controllers.canonical import ProductionCanonicalPandaController
from task_env.robots.panda import panda_reference_control_binding
from task_env.observations.selected_reference import selected_observation_binding
from task_env.controllers.canonical.contracts import reference_pose_action_binding

binding = ReferenceTaskBinding.from_provider_free_compiler(
    partial(compile_panda_box_task, declaration, config=config.environment, robot=robot,
            controller_factory=ProductionCanonicalPandaController.from_source),
    task_id=declaration.task_id,
    construction_schema='declared-panda-box-construction-v1',
    metadata={'object_id': declaration.object_id},
    reset_sample=partial(_sample_box_reset, declaration),
    evaluate=cls.evaluate_task,
    object_poses=((declaration.object_id, declaration.object_id.replace('-', '_')),),
    scalar_control_binding=panda_reference_control_binding(),
    external_actions=True, interval_mode='grouped', recorder_mode='canonical',
    **reference_pose_action_binding(), **selected_observation_binding(),
)
```

这是**现有 owner 级扩展接口**，不是“任意资产都支持的顶层公共 API”。`ReferenceTaskBinding` 只把声明/compiler 结果接到 Env；不要把这段内部接线当作稳定 CLI。

USD 交付的入口：

- 直接 Isaac 路线：已安装资产由 source 预检使用；普通 `make_env` 可不填内部 manifest。
- 高级 F06 Harness：显式 `execution.source_delivery_manifest` / `--source-delivery-manifest`，closure 必须匹配。
- 预装维护命令：`python -m task_env.assembly.usd_cache --provider isaacsim --robot <robot-uid> --manifest <已验证交付清单>`；它复制并重新验证完整 closure，不覆盖同位置的不同资产，默认用户缓存。

资产服务生成/下载只是可选入口；本教程不自动部署模型，也不宣称第三方分发许可。

## 5.3 复用并修改一个 Task

从 `examples/tasks/declared_marker.py` 逐段理解：

| 片段 | 作用 | 修改时注意 |
| --- | --- | --- |
| `PandaBoxDeclaration(...)` | 声明 task_id、artifact、object_id、table/box 几何、source 初态、reset 中心/范围、`Timebase` | 换已有物体时先看它是否在同一 source/scene 声明内；不要伪造新的 provider 资产 |
| `SemanticDefinition(...)` | 任务语义：entities、参数、success definition | `success_definition` 必须与 `evaluate_task` 的语义一致 |
| `Timebase(.002, 5, .01)` | physics dt、control substeps、control dt | 不要为了“跑得快”改 cadence 而不同步改 Controller/记录 |
| `_sample_box_reset(...)` | 用 seed 采样 box 初始位置；校验 Artifact identity | 只改 reset 范围时改 `initial.randomization`/采样，不动 success |
| `TaskEvaluation(...)` | 返回 reward、success、failure、metrics | 换 predicate 时保留 metrics 单位/语义 |
| `@register_env()` + `uid` | 注册 UID；`make_env` 可找到 | 不要覆盖已有 UID；未知 UID 要能解释 |
| `ReferenceTaskBinding...` | 把声明接到共同 builder/Env | 这是 extension 接线，不是通用用户注入 API |

三个常见修改的最小差异：

1. **只改 reset 范围**：改 `PandaBoxDeclaration.reset_center_xy/reset_half_extent_m` 或采样函数中的 bounds；保留 `evaluate_task`、source box、时间基。
2. **只改 success predicate**：改 `SemanticDefinition` 参数与 `evaluate_task` 的判定/返回值；保留 reset/source。
3. **换已有物体**：先在声明/Scene 中找到对应 object token 和资产 closure；同时更新 `object_poses` 映射与 predicate 的 state 字段。不要直接写一个新的 MJCF 路径绕过 `AssetDefinition`/source compiler。

完整可追踪的现有例子见 `examples/tasks/declared_marker.py` 本身（本页不复制一份会漂移的全文）。运行方式：

```python
import examples.tasks.declared_marker   # 触发注册；不要从 diagnostics 导入私有 fixture
from task_env import make_env

config = {
    "execution": {"physics_provider": "mujoco", "physics_backend": "cpu"},
    "episode": {"horizon": 10},
}
env = make_env("marker-height-example-v1", config=config)
try:
    observation, info = env.reset(seed=7)
    print(sorted(observation), info.get("task_metrics"))
finally:
    env.close()
```

预期/失败：

- 未知 UID → `KeyError: unknown environment uid`；先 import 注册模块。
- `ReferenceTaskBinding` 的 `task_id` 与注册 UID 不一致 → `ValueError('registered UID and declared task identity differ')`。
- reset Artifact 与声明不一致 → `ValueError('reset Artifact does not match the task declaration')`。
- `evaluate_task` 缺 state 字段 → `semantics.require_state` 失败。

该例的 Marker 路由是**合成/静态检查为主**，不是完整资产导入或正式任务资格；不要新建另一个正式 Task UID，也不要重跑全部 A123。

## 5.4 Robot 主体如何构造

**实际构造签名**（不要猜）：

- `PandaAgent` 与 `AssembledPandaAgent` 都**没有 `__init__` 参数**；UID 是类属性。用 `make_agent('panda-v1')` / `make_agent('panda-arm-hand-v1')` 或 registry 创建，不要写 `PandaAgent('panda-v1')`（会 `TypeError`）。
- Task 选择 Robot 走 selected config 的 `robot.uid`，不是把 Robot 对象塞进 `controller` section。

```python
from task_env import make_agent

panda = make_agent("panda-v1")
assembled = make_agent("panda-arm-hand-v1")
print(panda.uid, assembled.uid)
print(panda.asset_manifest())
print(assembled.source_recipe())
```

| 声明 | `PandaAgent`（`panda-v1`） | `AssembledPandaAgent`（`panda-arm-hand-v1`） |
| --- | --- | --- |
| `asset_manifest()` | 一体 Panda MJCF（Menagerie pin） | `panda_nohand.xml` + `hand.xml` 两源，固定 `source_revision` |
| `source_recipe()` | 单源 recipe/profile | `replace-task-subtree`，arm/hand 两条 `RobotSourceReferenceV1`，`fixed-transform-from-task-authored-tcp-v1` 连接 |
| `reference_spec()` | Panda 命名 body/joint/frame | arm+hand 的 probe 名称、attachment site、actuator 映射 |
| `initial_state_spec()` | Panda 初态 | arm+hand 具名初态（含 `probe_hand_*`） |
| `supported_controller_kinds()` | `absolute_joint`/`absolute_pose`/`delta_pose` | 位置路线与 effort 扩展按实际方法 |
| Controller profile | 见下文 | `r1`、`r3_continuous_v1`、`r1_split`；effort 扩展按实际编译 |

`RobotComponent`/`AgentComponent` 的抽象能力：`asset_manifest`、`reference_spec`、`initial_state_spec`、`supported_controller_kinds`、source recipe/profile。它们是**声明 owner**，不分配 native runtime。

装配例复用现有 arm+hand 与固定 attachment：

- 两个源：`mujoco-menagerie://franka_emika_panda/panda_nohand.xml`、`hand.xml`；
- 连接：`attachment_site` → `hand`，`fixed-transform-from-task-authored-tcp-v1`；
- 具名关节：`joint1..7` + `finger_joint1/2`；
- profile：`r1`（默认整机）、`r1_split`（arm/hand 两个 writer）、`r3_continuous_v1`（位置参考）；effort 要按实际 `compile_effort_subjects`/`build_effort_execution` 声明；
- 夹爪：一条对称 tendon + equality，不是两个独立任意力通道；
- TCP：由 source 的 frame 声明给出，不要在 Task 里硬编码 `panda-v1/ee` 之外的私有索引。

支持范围（按现有证据）：

| 路线 | 已稳定使用 | 未由此获得 |
| --- | --- | --- |
| `r1` | MuJoCo CPU 位置路线；原/装配的解与历史回归 | 任意 provider、任意 Controller |
| `r1_split` | MuJoCo CPU 进程内 arm/hand 双 writer；worker 首提交因远端缺同一存活 Controller 分路而拒绝 | 多 Position writer 的 worker 支持 |
| `r3_continuous_v1` | MuJoCo/GeoPhys/Isaac 的受测 scalar 路线 | 任意 seed/资产；batch R3 |
| effort | 受 source/Controller/驱动隔离约束的 MuJoCo/GeoPhys/Isaac 有界路线 | 换 Robot 后 Solution 无需验证 |

位置/力矩控制、native drive、模型与本体补偿要分开解释：

- Position drive 是 source 的原生执行器行为；
- 直接 effort 是声明 writer 的广义力贡献，可能和保留的 position drive 共存，**直接贡献限幅不等于总力限幅**；
- 模型/本体补偿只在其声明的 source/provider/cadence 内成立，不自动补偿抓持物载荷；
- 换 Robot 后，不能承诺任意 Solution 无需重新验证。

## 5.5 canonical action 与 native actuation

完整命名映射：

```text
用户 action
  → Controller 解释（pose/joint/effort/wrench）
  → typed physical contribution（JointEffortV1 / BodyWrenchV1 / ...）
  → 现有 adapter/组合与饱和 owner
  → session native application（actuator/qfrc/外载）
  → ACK / feedback
```

必须区分：

- **canonical action 不是所有 Task 固定一个向量**。Pendulum 是 `{'torque': (1,)}`；PickCube R3 是 8 维绝对 world pose+归一化夹爪；Panda direct effort 是 8 路 named effort；device PickCube 是 `{'effort': (B,8)}`。
- `joint_efforts` 是关节轴力/矩（`N·m` 或 `N`），`body_wrenches` 是 body 外载（世界/body frame 的力与矩）。两者**不混成 native `ctrl`**；由 adapter 分别降低到合法 actuation/外载接口。
- 默认恒等 Controller 初始 **unbound**；只有绑定 subject/writer/units 后才能计算。见 [独立 Controller 章](custom-controllers.md)。
- reset 后旧 generation/context 失效；stale/foreign command 会被拒绝。

### 两个已稳定实例

Pendulum：

```python
action = {"torque": np.array([0.2], dtype=np.float32)}   # N·m
```

PickCube R3：

```python
action = np.array([x, y, z, qw, qx, qy, qz, gripper], dtype=np.float64)
# 位置 m、world；四元数 wxyz；gripper 归一化 [-1,1] → 0..0.08 m
```

### 场景外载（公共语义）

当前公开 typed 表达包括：

- `ExternalComWrenchV1`：单 interval 的世界力 + 关于当前质心的世界力矩；
- `ExternalComWrenchSegmentV1`：额外声明 writer 和整数半开子步范围；
- `ExternalComWrenchSumSegmentV1`：显式声明可求和的片段，同一 native body 的重叠贡献必须全用该类型且 effect 不同；
- `env.step(action, external_com_wrenches=(wrench, ...))`：在选定 grouped Position interval 提交。

可以讲清的公共语义：

- 独立场景载荷（Task/caller 场景载荷）与正常动作 Controller 分别准入、提交、记录/清理；
- `force_N`、`torque_Nm` 的单位；表达式 frame、作用点、矩参考；同一 body 的 sum/effect 去重；
- hold/clear 的公共语义以现有类型/文档为准；
- 当前准入限 MuJoCo CPU implicitfast、source 明确绑定的有质量可动 body；每子步重读当前 COM；
- 不把普通物体伪装 Robot、不把 wrench 伪装 joint channel、不通过清空 subject/selection 绕过检查。

**`WAIT_7B_ACCEPTANCE`**：7b 正在新增/调整的 public BodyWrench producer、transport、API 签名与最终准入矩阵，本页不冻结。attempt002 需要回填：

| 待填字段 | 当前 owner/入口 | attempt002 动作 |
| --- | --- | --- |
| producer API（谁创建、参数、返回类型） | 7b accepted HEAD 中的公共 typed 表达 | 按实际签名替换本页“当前公开 typed 表达”段落 |
| transport/IPC 合同（scalar/device、哪些段可传） | `task_env/runtime/sessions/*` 与 provider adapter | 写实际支持/拒绝边界 |
| provider × body/source 准入矩阵 | 7b 主审接收的 capability matrix | 只维护一份最终矩阵 |
| 记录/回执字段与 H5 读回 | Recorder/reader owner | 回填实际 schema 与同 run 证据 |
| 与 joint effort/position drive 的组合规则 | existing compositor owner | 按最终候选写 sum/effect 与冲突拒绝 |

在此之前，读者只能把上述内容当**已稳定公共语义**，不能把本页当 7b 新接口的最终文档。
