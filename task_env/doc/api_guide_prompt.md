# TaskEnv API Reference 撰写引导

你现在需要为 **`task_env`** 撰写完整、准确、可维护的 API Reference。文档风格参考
ManiSkill 的“总索引 → 领域页 → 模块页 → 类/函数详情”结构，但不能机械复刻 Python 文件树。

目标是让开发者不阅读实现源码，也能理解 TaskEnv 的公开对象如何共同完成：

```text
组合任务元素 → 定义任务语义 → 生成公开 action → 记录公开 transition
```

本文只规定后续 API 文档的工作范围、目录和事实核验规则；不要在本 prompt 中记录实现结果。

## 写作完成定义：不是“导览”，而是可安全引用的 Reference

后续产物必须同时满足以下两层目标：

- **导览层**：新读者能在不先阅读文件树的前提下，理解任务元素、任务语义、规划和采集四域的上下游关系。
- **Reference 层**：读者可以复制页面中的 import 和示例，在页面声明的前置环境中运行；每个公开对象的
  参数、返回、异常和状态约束均可回溯到源码。

不能因为有 `script/` 或 smoke 已存在，就只写“见某文件”。API 页面本身必须包含足以完成该页面核心
操作的最小完整代码；`script/` 和 smoke 仅作为该代码的证据与扩展示例。

下列情形说明文档**尚未完成**：

- 示例缺 import、未定义的变量（例如孤立的 `config`）、资源释放或必要的前置配置；
- import path、方法签名、默认值、参数名或返回值与当前源码不一致；
- 将 Protocol/基类的契约误说成某个具体实现的实际调用签名，或反之；
- 只说“有 planner/recorder/config”，却未给出 action mode、数据形状、调用顺序或最小用法；
- 以纯文本列文件位置，读者不能跳转到定义处；
- 未说明解释器/依赖/仓库根目录等运行前置条件，导致用户无法判断示例为何不能 import。

## 0. 已冻结的文档信息架构

API 文档根目录固定为：

```text
task_env/doc/api/
```

一级导航只保留四个任务流程域。不要把当前每个 Python package 都提升为一级页面。

```text
api/
├── index.md                         # 导航、数据流、稳定性、迁移提示
├── composition/                     # 1. Task Composition
├── semantics/                       # 2. Task Semantics
├── planning/                        # 3. Task Planning
├── recording/                       # 4. Dataset Recording
└── appendix/                        # 横切 API：创建环境、配置、I/O、runtime 边界
```

### 1. Task Composition

说明“一个任务场景由哪些元素组成，以及如何编译为可运行环境”。该域的二级页面建议为：

```text
composition/
├── index.md
├── worlds.md                        # worlds/
├── passive_objects.md               # objects/
├── active_agents_and_control.md     # robots/ + controllers/
└── assembly_and_references.md       # assembly/
```

这里必须把 controller 作为 **active agent 的控制接口** 介绍，不能与 robot 并列为独立一级域。
需要说明 world、passive object、active agent/controller 到 `TaskReferences` 的编译关系。

### 2. Task Semantics

说明“同一套物理元素如何成为一个明确任务”。二级页面建议为：

```text
semantics/
├── index.md
├── task_environment.md              # BaseTaskEnv 的 task-facing lifecycle
├── task_definition.md               # TaskDefinition / TaskEvaluation
├── episode_reset.md                 # reset sampler、seed、initial state
└── built_in_tasks.md                # PickCube、NutAssembly 的任务级 API
```

必须明确：`reward`、`success`、`failure` 属于 task definition；success/failure 决定
`terminated`，episode horizon 决定 `truncated`。任务代码不得绕过 `env.step()` 推进 runtime。

### 3. Task Planning

说明“如何只通过公开 observation/info 和 public action 完成任务”。二级页面建议为：

```text
planning/
├── index.md
├── public_motion_primitives.md      # planners/
└── task_owned_solutions.md          # solutions/ + tasks/<task>/solution.py
```

必须区分：`planners/` 是 task-agnostic action-sequence 生成器；task-owned solution 可理解任务语义，
但两者都不能写 `ctrl`、`qpos` 或访问 private runtime。

### 4. Dataset Recording

说明“如何记录公开 Gym transition 并保存 H5”。二级页面建议为：

```text
recording/
├── index.md
├── wrapper_lifecycle.md             # TransitionRecordWrapper
├── trajectory_contract.md           # FrozenTrajectory / T+1,T invariant
└── h5_schema.md                     # RecorderConfig、layout、metadata、H5 writer
```

必须说明 recorder 只依赖 `reset()`、`step()`、metadata 和 `get_record_metadata()`；不得访问 solver、
runtime、controller private state 或 task private state。

### Appendix：横切而非一级任务域

下列内容不可成为一级导航，应放在附录并从需要它们的页面交叉链接：

```text
appendix/
├── environment_creation.md          # make_env、registry、registered UIDs
├── configuration.md                 # ResolvedEnvConfig 及子 config
├── observation_and_rendering.md     # observations/、renderers/
├── public_contracts.md              # action / observation / metadata schemas
├── runtime_boundary.md              # RuntimeBoundary：边界、不是用户控制入口
└── migration.md                     # 旧路径已移除的迁移表
```

`runtime/` 仅以 boundary/advanced API 介绍；不将 solver 内部布局、Taichi field 或私有 runtime
方法写成普通用户 API。

## 1. 当前源码边界与映射

只扫描 `task_env` 及直接验证其 API 的 `test/smoke_only_tests/task_env`、`task_env/script`。
不要扩展为整个 GeoPhys 项目的 API 文档。

| 文档域 | 当前源码位置 | 主要对象 |
| --- | --- | --- |
| 创建与配置（附录） | `registry.py`、`environment/` | `make_env`、registry、`ResolvedEnvConfig` |
| Task Composition | `worlds/`、`objects/`、`robots/`、`controllers/`、`assembly/` | component protocols、Panda、action adapters、references |
| Task Semantics | `tasks/`、`environment/env.py`、`environment/protocols.py` | `BaseTaskEnv`、`TaskDefinition`、`TaskEvaluation` |
| Task Planning | `planners/`、`solutions/`、`tasks/*/solution.py` | Cartesian/joint planner、task solution |
| Dataset Recording | `recorders/` | wrapper、recorder、trajectory、H5 |
| 横切 I/O（附录） | `observations/`、`renderers/` | observation schema、camera/render provider |
| 内部物理边界（附录） | `runtime/` | `RuntimeBoundary`、compiled runtime assembly |

顶层 `task_env.__all__` 是最短用户导入面的事实来源；各子 package 的 `__all__` 是模块级公开导出
的第一证据。一个对象即使没有列入 `__all__`，若它是 Protocol、抽象基类、dataclass contract 或明确的
子类覆写 hook，也可在相应页面记录为 **Extension API**，但必须标明其稳定性。

## 2. 事实核验原则

所有描述必须以当前源码为唯一事实依据。逐项检查：函数签名、类型标注、默认值、`__all__`、父类、
调用位置、config、smoke、script 和 docstring。

- 禁止根据名称猜测功能、shape、dtype、单位、坐标系、返回 key 或异常。
- 源码未明确的信息写“源码未声明”或 `TODO: maintainer confirmation required`，不要补全。
- 不修改真实接口来迁就文档。
- 不为私有 helper 生成常规 API 页面；只有子类覆写 hook 或生命周期必需的私有方法可记录，并标为
  **internal hook**，不可推荐直接调用。
- 不把 runtime/solver 私有对象、`ctrl`、`qpos` 写入路径或 Taichi field 误写为 recorder/planner API。

### 2.1 import、签名与示例的硬性核验

每一条 **Import path** 都必须给出可复制的 `from ... import ...`（或 `import ...`）语句，并按当前
package 实际导出面验证；不能仅因定义文件存在就假设某个父 package re-export 了它。区分以下情况：

- 顶层 `task_env.__all__` 导出；
- 子 package `__all__` 导出；
- 可通过模块属性访问但未列入 `__all__`；
- 只能从定义模块导入的 advanced/internal 实现。

页面必须据此给出**唯一推荐 import**，并将其他路径标为兼容、实现细节或不可用，不能笼统写
“从 `task_env.environment` / 顶层均可导入”。

对每一个实例方法、构造器和函数，直接从当前源码复制完整 signature，包括 keyword-only 标记、参数名和
默认值。不得用伪参数简写；例如源码需要 `snapshot` 的方法不能写成 `ctrl`，源码的具体 solution 需要
`metadata` 时不能只沿用较宽泛 Protocol 的 `reset(observation, info)` 描述。

每个 Python code block 必须同时具备：

1. 完整 imports；
2. 本块使用的 config、UID、metadata 等变量定义；
3. 必需的 `reset()`、`step()` 或 wrapper 调用顺序；
4. 资源清理（对环境使用 `try/finally: env.close()`）；
5. 该示例的验证状态与验证命令。未在当前环境运行的示例必须明确写“未运行”，并说明原因；不能写成已验证。

文档开头或 appendix 必须给出统一的“运行前置条件”：从仓库根目录运行、推荐的项目 Python 环境、最小依赖、
`PYTHONPATH`/direct-script 规则。不要把执行机器的缺失依赖误描述为 API 行为。

每个页面标明一种稳定性：**Public API**、**Extension API**、**Advanced boundary** 或 **Internal**。

## 3. 页面和模块写作模板

每个页面开头必须包含：完整 import path、所属一级任务域、稳定性、职责、调用者/消费者，以及源码
文件定位。源码定位必须是可点击的相对 Markdown 链接；若页面只是 re-export，必须同时标出 re-export
位置和真实定义位置。

对于类、Protocol、dataclass、Enum、公开函数和装饰器，按证据填写以下内容：

```markdown
## `qualified.import.path.Object`

**Kind**：class / Protocol / dataclass / function / decorator
**Stability**：Public API / Extension API / Advanced boundary / Internal
**Defined in**：`task_env/...`

### Signature

```python
# 直接复制当前源码签名
```

### Responsibilities and relationships

说明它拥有/不拥有何种状态，处于四个任务流程域的哪个位置，依赖什么并被什么消费。每个二级页面至少给出
一次“生产者 → 当前对象 → 消费者”关系，避免读者只能看到平铺类名。

### Parameters / fields

逐项说明类型、默认值、语义、允许值、shape/dtype/单位/坐标系/生命周期；只有源码确认时才写。

### Returns / raises / state changes

说明稳定返回结构、显式异常、是否改变 episode、registry、缓存、文件或 H5；无返回值必须写 `None`。

### Lifecycle or call order

区分用户调用、框架调用、子类覆写、每 episode、每 control tick、terminal 后的行为。

### Example

给出可复制的完整最小示例；说明是否已运行验证和相应命令。随后才可链接 `script/` 或 smoke 作为完整
工作流示例。
```

对于 dataclass/contract，字段表应优先说明不可变性、复制/readonly 行为和 shape；对于 Protocol/ABC，
列出实现者必须提供的方法与禁止跨越的层级；对于 registry decorator，明确其 registry side effect；
对于 H5 和 observation tree，明确 leaf path、时间轴和 metadata，而非只写 `dict`/`array`。

不要在每个子类复制未变更的 inherited API；使用“Inherited API”链接父类。子类重写或语义改变时，
必须重新说明差异。

对每个类/函数的 Reference 项，额外给出以下开发者必需信息：

- **Recommended import**：唯一推荐的可复制导入；
- **Prerequisites / mode compatibility**：依赖的 action mode、已 reset 状态、metadata 或可选依赖；
- **Returns / output contract**：对 ndarray/observation/H5 数据写明 shape、dtype、坐标或单位、时间轴；
- **Raises**：只列源码显式抛出的异常及触发条件；
- **Side effects**：registry 写入、episode 状态推进、文件写出或缓存变化；
- **See also**：父类、实现者、生产者与消费者的交叉链接。

对 Protocol/ABC 必须分别列出“实现者必须做什么”和“使用者可安全调用什么”；对 concrete class 必须说明它
实际覆盖后的签名与 Protocol 是否完全一致。对于没有稳定 public import 的 helper，不能因它有用就标为
Public API。

## 4. 必须重点解释的关系

在 `api/index.md` 和相关页面中重复使用下面的真实边界，而不是按文件夹罗列：

```text
world + passive objects + active robot/controller
    -> assembly compile + stable references
    -> BaseTaskEnv Gym lifecycle
    -> TaskDefinition reward/success/failure
    -> public planner / task-owned solution
    -> env.step(public action)
    -> recorder H5 transition
```

还需清楚区分：

```text
external_action    # ActionAdapter 实际解释的 policy/controller-facing action
universal_action   # controller/native adapter 后的 canonical runtime action，维度按 task family 版本化
actuator ctrl       # runtime/backend 细节，不是 H5 v1 public action
```

除首页流程图外，四个一级域各自的 `index.md` 也必须给出本域的层级树。例如 Composition 必须明确：

```text
World / passive object / active agent
    -> component asset_manifest() + reference_spec()
    -> compile_task_scene(...)
    -> TaskReferences
    -> BaseTaskEnv / observation / TaskDefinition / controller
```

Planning 页面必须建立 action mode 与 planner 的明确对应关系，而不是只比较维度：Cartesian pose planner
生成 `cartesian_pose_target` 的 public action；joint planner 生成 `absolute_joint_position_target` 的 public
action。若源码支持更多模式或具体限制，以源码为准补齐。Recording 页面必须画出
`reset observation (t=0) -> T transitions -> next observations (T+1) -> FrozenTrajectory -> H5`，并说明
`external_action`、`universal_action` 与 backend `ctrl` 的保存边界。

## 5. 迁移说明

当前 canonical imports 为 `task_env.environment`、`task_env.controllers`、`task_env.robots`、
`task_env.worlds`、`task_env.assembly`、`task_env.planners`、`task_env.recorders`、
`task_env.renderers`、`task_env.solutions` 和 `task_env.tasks`。

旧 `task_env.action`、`agents`、`core`、`scene/scenes`、`observation`、`planning`、`recording`、
`rendering`、`experts`、`utils` 不保留 compatibility shim。仅在 `appendix/migration.md` 集中说明，
不要在每个模块页重复迁移文字。

## 6. 实施顺序与验证

1. 输出 API inventory：按上述四域与 appendix 罗列候选对象、定义文件、实际推荐 import、稳定性、
   已知实现者/消费者、示例来源和风险。把 Protocol、concrete implementation、re-export 分开列出。
2. 先写 `index.md`，并写四域各自的层级树和入口卡片；随后完成 Composition contracts、
   TaskDefinition/TaskEvaluation 与 `BaseTaskEnv`。
3. 再写 planners/solutions、recorders 和 appendix。每个域至少落地一段端到端、可复制的核心示例。
4. 最低示例覆盖矩阵为：
   - 创建：查询/选择 UID，构造 config，`make_env`，`reset/step/close`；
   - 组合：新增一个 world/object/agent component 的最小骨架，以及它被 registry/assembly 消费的路径；
   - 语义：实现 `TaskDefinition` 并解释 reward、success、failure、terminated、truncated；
   - 规划：分别使用 Cartesian 与 joint planner，并显式配置相配的 action mode；
   - 采集：wrapper 的 `reset -> start_record -> step -> end/save_h5`，以及最小 H5 读取/检查；
   - 二次开发：一个内置 task 的完整 solution loop，包含其实际所需的 metadata 或其他参数。
5. 每页完成后做四类检查：
   - import 检查：逐条执行页面的 recommended import；
   - signature 检查：与定义处逐参数比对，重点检查 keyword-only 参数与 concrete override；
   - Markdown 检查：所有相对链接、锚点和源码链接存在且可解析；
   - example 检查：在文档声明的项目环境中运行；若依赖 runtime/GPU，复用现有 direct script 或 smoke，
     并在页面记录命令和结果。
6. 文档的用户指南和 API Reference 应交叉链接但不要重复：教程负责“为什么/工作流”，Reference 负责
   “精确调用合约”。涉及可运行示例时复用 `script/` 或 smoke，不能凭空构造。
7. 最终输出 coverage report：已记录对象、其 verified import、已运行/未运行示例、未确认行为、已发现的
   文档-源码偏差，以及刻意排除的 Internal API。任何未验证示例不得写成可直接运行。

文档语言使用中文；类名、函数名、参数名、类型名、文件路径和 import path 保持英文原样。术语应直接、
精确，不使用宣传性描述。

# Codex 的具体回答内容

结论：这是一份“架构导览质量不错、但尚未达到可直接依赖的 API Reference”的文档。作为项目新人理解 TaskEnv 很有帮助；作为复制代码即可调用、据此二次开发的依据，还需要一轮系统补强。

| 维度 | 评分 | 判断 |
| --- | ---: | --- |
| 易读性与通俗性 | 6/10 | 四域概念清楚，但术语与可调用代码不足 |
| 结构清晰性 | 8/10 | 已较好落实“环境构成 → 语义 → 规划 → 采集” |
| 示例与二次开发 | 2/10 | 只有一个不完整代码片段，几乎没有端到端示例 |
| API 准确性与可执行性 | 4/10 | 发现若干会直接误导或报错的接口说明 |
| 作为正式 API 文档的完成度 | 4/10 | 目前更像 API 导览，而不是 ManiSkill/Piper 级 reference |

优点首先很明确：

- [API 首页](api/index.md:1) 的单向数据流正确且好理解：场景/物体/机器人控制 → 装配引用 → Gym 生命周期与任务语义 → 规划 → 记录。
- 四个一级域的划分符合用户构建 TaskEnv 的心智模型；world、被动物体、active robot/controller 放在 Composition 下尤其合理。
- 多数页面都标记了 Public / Extension / Advanced，并强调不能越过 `env.step()`、不能把 `ctrl` 当作公共 action。这对避免错误的二次开发非常有价值。
- 对 `T+1` observation 与 `T` transition 的 H5 约束讲得准确、醒目。

主要问题按严重程度排序：

1. 有会造成直接报错或错误调用的 API 说明。

- [Configuration](api/appendix/configuration.md:3) 写了 `task_env.environment` 可导入 `resolve_env_config`，但实际它只由顶层 `task_env` 导出；`from task_env.environment import resolve_env_config` 会失败。
- [机器人控制页](api/composition/active_agents_and_control.md:24) 将 `ctrl_for_target` 写为 `ctrl_for_target(target, ctrl)`；实际签名是 `ctrl_for_target(*, snapshot, target)`，按文档调用必然报错。源码见 [gripper.py](../robots/gripper.py:49)。
- [任务规划页](api/planning/task_owned_solutions.md:20) 把 `PickCubeSolution` 和通用 `TaskExpertSolver` 混为同一 reset 契约。通用 Protocol 是 `reset(observation, info)`，但内置 PickCube 实现要求 `reset(observation, info, metadata)`；少传 `env.metadata` 会报错。源码见 [solution.py](../tasks/pick_cube/solution.py:175)。

2. 示例不足，且现有唯一代码块不可复制运行。

[BaseTaskEnv 示例](api/semantics/task_environment.md:24) 缺少 `make_env` 的 import，`config` 也未定义；此外没有 `try/finally: env.close()`。目前大量页面只说“见 `script/*.py`”，但 API 文档本身应至少提供：

- 创建并 reset/step/close 的完整最小示例；
- 三种 action mode 与 planner 的匹配示例；
- `PickCubeSolution` 的完整 rollout；
- recorder 包装、结束、写 H5，以及最小 H5 读取示例；
- 新增 object / robot / task 各一个最小骨架。

3. “上下级关系”只在首页流程图中出现，没有落实到各对象。

目前读者能知道有 `TaskReferences`，却不够容易建立以下关系：

```text
World / Object / Agent
  └─ Component 接口与 UID
      └─ compile_task_scene()
          └─ TaskReferences
              └─ BaseTaskEnv
                  ├─ TaskDefinition
                  ├─ Planner / Solution
                  └─ TransitionRecordWrapper
```

建议每个一级域首页增加该域的对象树，并在每个二级页面写清“创建者、消费者、前置条件、下一跳 API”。尤其应明确 `CartesianPosePlanner` 只能配合 `cartesian_pose_target`，`JointPositionPlanner` 只能配合 `absolute_joint_position_target`；二者虽都是 `(T, 8)`，语义并不相同。

4. API 覆盖和呈现深度不足。

469 行、25 页的规模适合导览，但不足以承担详细参考。大量关键类只写“存在什么”，没有统一给出：

- 精确导入语句；
- 完整 constructor / method signature；
- 参数类型、shape、单位、默认值、有效范围；
- 返回值结构；
- 会抛出的异常与触发条件；
- 调用前后的状态变化；
- 可运行示例；
- 源码链接。

例如 `TaskEvaluation` 写得相对接近目标；而 `BaseTaskEnv`、三种 controller adapter、三个 planner、`TransitionRecordWrapper`、`RecorderConfig` 和内置 task 都还需要上述信息。

5. 文件定位目前不可点击，且公开面不够可验证。

页面中的 `源码：task_env/...` 大多只是行内文本。应换成可点击的相对链接，并把“导入路径”改成可直接复制的形式，例如：

```python
from task_env import make_env, resolve_env_config
from task_env.planners import CartesianPosePlanner
from task_env.recorders import TransitionRecordWrapper
```

还应增加“已注册 UID / 如何运行时查询 UID”的小节，以及“依赖与运行环境”说明。我的本机只读校验中，系统 `python3` 缺少 `numpy`，因而连导入验证都无法开始；文档至少应明确需进入哪个环境、安装哪些依赖、从哪个目录运行。

对标来看，ManiSkill 的 API 索引先给出完整包树，再按模块列出 Attributes / Classes / Functions，类和函数都有签名、参数、返回值和源码入口；其 registry 页面尤其适合作为 `make_env` / `ComponentRegistry` 的写法模板。[ManiSkill package API](https://maniskill.readthedocs.io/en/latest/api/mani_skill/index.html) [ManiSkill registration API](https://maniskill.readthedocs.io/en/latest/api/mani_skill/utils/registration/)  
RoboMimic 则把面向使用者的教程与 Source API 明确分层，避免 API 参考承担入门教学。[RoboMimic documentation structure](https://robomimic.github.io/docs/introduction/overview.html)  
Piper 的强项是每个接口都稳定采用“定义—参数表—返回值—边界说明—可复制示例”的格式，尤其适合本项目的 controller、planner、recorder 页面。[Piper API documentation](https://github.com/agilexrobotics/pyAgxArm/blob/master/docs/piper/piper_api.md)

我建议下一轮优先顺序是：先修正上述三处 API 不一致与唯一示例，再为四域各补一个完整端到端示例，最后以统一模板补全核心公开类的签名、参数、返回、异常和源码链接。这样这套很好的四域结构才能真正成为初学者可安全依赖的开发文档。
