# G07／7c 教程逐项填充大纲

2026-11-17，revision001；准备输入 `4fdf9379482af6bb913eb1a6587316e64b6a0fed`。
本页是维护者要求的教程实施蓝图，不是已运行教程或版本接收结论。
配套[7c attempt001 工作包](../maintenance/work-packages/20261117_g07c_attempt001_goal.md)规定隔离工作树、修改范围与验证。7b 最终接收后的动态内容归 attempt002。

## 0. 写作方式与交付文件

读者按“安装 → 无渲染 → 相机/窗口 → device batch → 自定义环境/资产/Robot/Controller → API”学习。
每节必须让读者知道：为什么需要这一步、在哪个目录/解释器运行、完整输入是什么、输出怎么解释、失败去哪里改。
`〔填写：…〕` 是实施者须填的具体槽位；禁止把槽位、`...`、伪 API 或只有链接的说明留在声称完成的教程中。
无法运行的段落可以完整交付，但必须标明静态核对/历史证据/未验证；不能据此授予能力。

| 章节 | 唯一教程落位 | 与现有文档的关系 |
| --- | --- | --- |
| 总入口/选择路线 | `guides/README.md` | 将旧交付要求转为当前学习导航；历史要求链接到原提交，不复制新手教程 |
| 第一部分 安装 | `guides/installation-and-start.md` | 原页扩写，保留其权威；不再建第二份 installation |
| 第二部分 无渲染 | `guides/quickstart-state-only.md` | 新页，含三个任务、随机/策略两种动作来源及明确缺口 |
| 第三部分 相机与窗口 | `guides/quickstart-rendering.md` | 新页；以 GeoPhys Rasterizer 演示，再说明可用替代路线 |
| 第四部分 并行 | `guides/quickstart-device-batch.md` | 新页；只教当前两个任务/三个 provider 的正式 device 路线 |
| 第五部分 环境/资产/Robot | `guides/authoring-scenes-assets-robots.md` | 新页；声明、实例化、编译、绑定、运行分层说明 |
| 第五部分独立章 Controller | `guides/custom-controllers.md` | 必须单独一页；不能缩成上页一个段落 |
| 第六部分 API 用法 | `guides/api-usage.md` | 按使用场景组织并链接 `api/README.md` 与 `task_env/doc/api/`，不复制第二套字段规范 |

所有 public API 的字段/默认值/能力定义只保留在对应规范页；教程给教学解释、完整例子、预期结果和到规范的链接。
根 README、`task_env/README.md`、`task_env/doc/index.md`、本版 README 都导航到这套教程。
符号级 API 继续维护于 `task_env/doc/api/`；修改旧页的真实错误，不把当前页面整套复制后让两个版本竞争。

每一个“可运行实例”均附下表，不能只附 Python fenced block：

| 必填项 | 填写规则 |
| --- | --- |
| 环境 | Linux 参考路线、Core/worker 解释器、provider/backend/device、display 是否必需 |
| 身份 | 验证所用 Core/pins、Task UID、Robot/profile、source/delivery；普通读者不手写 SHA |
| 前置与启动 | 从仓库根运行的命令、完整文件/导入、配置、资产位置和输出目录 |
| 输入/输出 | action/observation 的树、shape、dtype、device、单位/坐标系；以真实输出填写 |
| 结束 | 步数与 horizon、terminated/truncated、任务成功与 Solution 完成如何分别读取、`finally: close()` |
| 验证 | 静态核对、既有运行复用或本轮 native 三者分开，给日期与证据路径；没有运行就直说 |
| 故障 | 至少列本例实际可能遇到的参数/依赖/资产/准入错误和对应原 owner |

## 第一部分：安装、后端隔离与路径配置

### 1.1 先选择最小安装路线

写出参考操作系统/CPU架构、Python、GPU/驱动/显示依赖的来源和核对日期。
主教程以 Linux/CPython 3.12 为参考操作路径；这不把其他平台/版本宣称为已验证。
先给选择表，再安装依赖；仅无渲染 CPU 任务不要求装 Isaac、CUDA renderer、资产生成服务或 MCP。

| 路线 | 已知冻结身份 | 必须解释的隔离关系 |
| --- | --- | --- |
| Core／MuJoCo CPU | MuJoCo 3.8.1；Core requirements 为 `>=3.8.1,<3.9.0` | 单环境 CPU 的参考解释器；不升级到4.0来迁就其他 SDK |
| GeoPhys | pin `198d30ac64ce873a1467f55d2adfc471db18fbc5`；匹配开发分支 `codex/v211-stage6-render-device`；Forge0.7.0 | pin 才是恢复身份，分支名字不足；其完整 requirements 的 MuJoCo 下界与 Core 冲突 |
| MJWarp | MuJoCo／MuJoCo-Warp4.0.1、Warp1.18.0；Python3.12 清单已存在 | 专门解释器；不能将其 requirements 覆盖安装到 Core 3.8.1 环境 |
| Isaac Sim | 6.2；Python3.12；pip 与 app 两种部署 | SDK 自带 NumPy/Torch/pxr 等有独立约束；不在 SDK 里安装全部 Core requirements |

`〔填写：具体 Python/Torch/驱动的来源、适用路线、是否本机实测、安装/下载空间预估来源〕`。
当前约8GiB VRAM/16GiB RAM是本机条件，不是厂商最低要求或任意 batch 上限。
本机主环境 Torch2.14.0+cu130 与 Isaac 官方安装页给出的 SDK 依赖版本分开记录，不强行统一。

### 1.2 获取 Core 与固定 submodule

从本仓库真实 `.gitmodules` 填 URL；教程使用用户有权访问的 remote 和发布/候选 ref，不能虚构 v2.1.1 tag。

```bash
# 将两个尖括号值替换为维护者给出的真实 remote/ref；在一个新目录运行。
git clone --branch <受支持的Core分支或tag> <GeoChora仓库URL> GeoChora
cd GeoChora
git submodule update --init --recursive
git rev-parse HEAD
git submodule status --recursive
```

解释 clone、submodule checkout 与后端安装分别完成什么。已有 checkout 先检查 dirty，不能教用户强制 checkout/clean。
展示 GeoPhys 与 Menagerie 两个 gitlink 的核对命令，以及缺少 Panda mesh/MJCF 时的诊断位置。
解释追 GeoPhys main 会丢失匹配能力；跟踪匹配分支时仍须核对 pin。
如果 matching 分支在某个 remote 不存在，使用 Core gitlink 恢复，不要求用户创建同名分支掩盖差异。

### 1.3 Core／MuJoCo CPU 安装

核心命令骨架：

```bash
python3.12 -m venv .venv-core
.venv-core/bin/python -m pip install --upgrade pip
.venv-core/bin/python -m pip install -r task_env/requirements.txt
```

随后单独写 Torch 的实际必需消费者、参考 wheel 命令与 CPU/CUDA 选择依据，不能因为 requirements 未列 Torch 而漏掉需要它的路径。
仓库没有 root packaging metadata；不写 `pip install -e .`，也不新建 packaging 来让教程通过。
`〔填写：纯版本/模块路径检查命令、正常版本结果、pip check结果的解释；不将 import 成功说成 reset/step 成功〕`。

### 1.4 GeoPhys 安装与分支切换

必须逐项说明：Core 内置源码位置 `GeoPhys/src`；pin/branch；公开 `geophys.init_taichi`；Forge与传统Taichi的区别；CPU/CUDA与renderer依赖。
该 pin 的 `requirements.txt` 确实声明 `mujoco>=3.15.0`，Core声明 `<3.9.0`。不得给出连续安装两个完整 requirements 到同一解释器的命令。

分成两条写清楚：

1. **复用已验证 Core＋GeoPhys source profile**：引用真实已有部署清单，列出其明确依赖集与缺项检查；不能凭经验手工删 GeoPhys requirement 后宣布新安装通过。
2. **单独安装 GeoPhys 开发环境**：按 pin 对应 `pyproject.toml`/requirements 及官方安装入口；Core通过 `execution.interpreter`/worker 连接。完整 requirements 能否被 resolver 满足要单列，不能隐藏解依赖失败。

`〔填写：两条路线的精确安装命令、manifest出处、Python ABI、pip check、解释器路径、已验证范围/未验证项〕`。
Core scalar worker、in_process 和 G06 device 的支持范围分别描述；“隔离环境安装成功”不证明其支持所有 control/model/render 组合。

### 1.5 MJWarp／MuJoCo4.0 安装

```bash
python3.12 -m venv .venv-mjwarp
.venv-mjwarp/bin/python -m pip install --upgrade pip
.venv-mjwarp/bin/python -m pip install -r task_env/dependencies/mujoco-warp-4.0.1-python312.txt
```

解释清单中 MuJoCo4.0.1、mujoco-core/studio、mujoco-warp 与 warp-lang 的关系；这些是4.0路线，不是旧mujoco-py，也不是MJX。
`〔填写：device worker实际还需的 Core 导入依赖及其来源、纯版本检查命令、GPU/driver预检、kernel首次编译/缓存说明〕`。
不得用“这份清单存在”宣称全新环境已完整可运行。安装后还须选择 worker 解释器并运行有界 Pendulum；本轮不执行安装/native。

### 1.6 Isaac Sim：pip 依赖库安装

先链接固定6.2官方安装页，列 Python3.12、Linux GLIBC≥2.35、GPU/driver核查方法。
使用单独 venv，不复制 Core requirements。官方基础命令可写为：

```bash
python3.12 -m venv .venv-isaac
.venv-isaac/bin/python -m pip install --upgrade pip
# 按官方6.2页选择该SDK兼容的CUDA/Torch配置后，再执行：
.venv-isaac/bin/python -m pip install 'isaacsim[all,extscache]==6.2.0.0' \
  --extra-index-url https://pypi.nvidia.com
```

`〔填写：SDK/Torch依赖命令与版本出处；Core父进程/SDK子进程关系；USD source delivery从哪来、如何传入、缺manifest的报错〕`。
厂商安装验证与 GeoChora task 验证分开；EULA由用户阅读并决定，不让安装脚本替用户接受。
7b仍在调整的 dependency overlay/bootstrap/BodyWrench transport 归 attempt002；本轮只能写旧合同/准确缺口，不能把未提交实现当稳定命令。

### 1.7 Isaac Sim：app 下载解压安装

与pip路线并列完整列出：官方下载页与版本/平台选择、下载文件校验、解压到用户可写SDK目录、官方post-install步骤、`python.sh`/真实解释器、启动脚本环境。
`〔填写：官方6.2包名/目录与校验来源、解压与初始化命令、app启动和Python启动两类命令、GeoChora参数接受Python可执行文件还是shell launcher的实际边界〕`。
不能把 `python.sh` 和 `kit/python/bin/python3` 当作无条件互换；以 transport 启动方式核对。
给已有SDK在仓库外的例子；不要求复制 SDK 到 ignored workspace，也不让新工作树指向另一个工作树里的隐式缓存。

### 1.8 后端路径配置与优先级

```bash
# 本机值建议保存在 ~/.config/geochora/env.sh；下列均换成自己的绝对路径。
export GEOCHORA_CORE_PYTHON=/path/to/core/bin/python
export GEOCHORA_GEOPHYS_PYTHON=/path/to/geophys/bin/python
export GEOCHORA_MJWARP_PYTHON=/path/to/mjwarp/bin/python
export GEOCHORA_ISAAC_PYTHON=/path/to/isaac/bin/python
source scripts/setup/geochora-env.sh
```

逐项说明脚本会设置 `GEOCHORA_PROJECT`、`GEOCHORA_GEOPHYS_SRC`、`PYTHONPATH`，并把 `GEOCHORA_ISAAC_PYTHON`映射到`ISAAC_SIM_PYTHON`。
列配置 `execution.interpreter`、环境变量、CLI `--isaac-python` 在各消费者中的真实优先级，不能假设全局完全相同。
注明 shell脚本不自动设置MJWarp解释器；`PYTHONPATH`在`-I -S` worker中可能不会生效；父进程import可用不证明SDK子进程可用。
`〔填写：检查变量/文件存在/解释器ABI的命令、预期输出示例、运行cwd、source脚本后改变cwd的影响〕`。
Core入门不运行`setup.sh`默认资产下载/MCP注册；如介绍它，链接agent setup并解释`--skip-assets`等实际副作用。

## 第二部分：单环境无渲染 Quickstart

### 2.1 首先解释共同交互合同

逐行解释 `make_env`、mapping/YAML、`reset(seed)`二元组、`step(action)`五元组、space/metadata、done和`close()`。
`render_mode=None`且不声明相机；不调用`render()`。两种随机性：task seed 与随机动作Generator分别设定。
不要把fixed-space wrapper、Gym space成员合法、任务source准入与策略动作准入混为一谈。

### 2.2 Pendulum 随机力矩完整文件

以下是可直接扩写的骨架；实施者须补文件落位、逐行解释和输出，不必为它新增公共CLI。

```python
import numpy as np
from task_env import make_env

rng = np.random.default_rng(73)
env = make_env("pendulum-v1", config={
    "execution": {"physics_provider": "geophys", "physics_backend": "cpu"},
    "episode": {"horizon": 100},
})
try:
    obs, info = env.reset(seed=73)
    print(env.action_space, env.observation_space)
    for index in range(100):
        action = {"torque": rng.uniform(-1.0, 1.0, size=(1,)).astype(np.float32)}
        obs, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break
finally:
    env.close()
```

核对依据：`examples/tasks/scalar_step.py`、Pendulum task binding、default canonical Controller。
解释`torque`的N·m、shape(1,)、float32、CPU；区分步进、摆杆状态变化、控制目标达成。
补MuJoCo CPU的最小配置差异表；Isaac仅链接安装和其受测来源，不把此例扩成全provider矩阵。

### 2.3 PickCube 随机动作版

默认R3使用绝对world pose，8维为xyz＋wxyz＋归一化gripper；不是8个motor effort。
随机策略给出reset后 `obs['state']['ee_pose']` 周围的有界位置扰动、保留有效四元数、合法gripper。
`〔填写：完整代码、实际spaces/dtype、该profile的合法工作空间和gripper映射来源、动作范围为何适合短程教学〕`。
禁止直接对无限界Box做“全空间均匀采样”；不声称随机动作应完成任务。
另给显式`panda-direct-effort-v1`/native drive disabled路线的可选解释，和R3分开；其具体scalar准入以源码为准，不从batch例子移植假能力。

### 2.4 PickCube 原 Solution 版

现成普通入口：

```bash
"$GEOCHORA_CORE_PYTHON" examples/tasks/pick_cube.py \
  --provider mujoco --seed 31 --horizon 1000 \
  --recording workspace/tutorial/pickcube-mujoco31.h5
```

写出不使用Harness也不使用诊断包的等价Python调用：
`build_readiness_solution(backend='cpu', controller_profile='r3_continuous_v1')`，
`solution.reset(obs,info,env.metadata)` → `act` → `env.step` → `observe`，按`done/failed/terminated/truncated`结束。
补可用GeoPhys配置差异；Isaac direct/Harness源与delivery参数分别说明，不能混用两个命令合同。
`〔填写：Solution构造来源、完整循环、task predicates/lifecycle success/Solution completion/plan completion输出解读、记录与独立读回命令〕`。
原事件驱动完成可在成功边界停下；历史267/438等进度与null字段不能补造成点列全发送。最终7b结论在attempt002写入。

### 2.5 NutAssembly 随机动作版：当前真实缺口须保留

本节是维护者必需内容，**不能删除或伪装完成**。准备输入下：

- `tasks/nut_assembly/specialization.py::_binding`设置`external_actions=False`；只准入source-bound `ExpertAction`。
- 其`_validate_external_solution`要求实际`NutAssemblyOutcomeSolutionV1`、同provider/source/config/clock/identity。
- `SelectedReferenceEnv._prepare_selected_step`对普通数组明确拒绝。

因此“构造合法8维pose数组”仍不足以实现普通随机策略；禁止伪造solution_identity/request_boundary、手改binding或关闭guard。
attempt001必须给出完整**预期拒绝示例**：构造/重置Nut，读取action_space，尝试普通随机数组，捕获并解释该特定准入错误，最后close；示例标为“不支持普通随机动作”，不能标为随机控制成功。
reset必须使用该Task实际准入的seed19（None也解析为19）；不能套用Pendulum的73或PickCube的31而先在reset处失败，导致未触达要解释的动作拒绝。
同时在交付缺口表登记 `T-NUT-RANDOM`：用户需求未满足、真实owner与最小可能扩展点、是否在7b最终输入已自然解决。
7c attempt002复核最终源码；仍无该能力则交维护者裁定是否另开task-local接线，不能在文档包扩展运行时，也不能以负例等价于用户需求已完成。

### 2.6 NutAssembly 原 Solution 版

```bash
"$GEOCHORA_CORE_PYTHON" examples/tasks/nut_assembly.py \
  --provider mujoco --seed 19 --horizon 6000
```

等价Python通过`task_env.tasks.nut_assembly.task.build_outcome_solution(provider='mujoco')`，按同一caller循环驱动，使用原Task判据。
解释Nut外部Solution action中的边界和control request由原Solution生成，读者不手写内部identity。
`〔填写：完整代码、GeoPhys替换配置、记录方式、严格完成/轨迹完成/Task成功分列、horizon不足的预期截断〕`。
明确当前NA-S0固定seed19，其`_reset_seed`与`sample_reset`会拒绝其他seed；不把固定seed例子描述为任意随机初态支持。
MuJoCo释放1mm、GeoPhys8mm为task-owned路由事实；不把它做成公共Env特判或教程自行调参建议。
原/装配Panda都给`robot.uid`等**实际字段核对后的**配置与受测范围；未核对之前不猜字段名。
Nut没有Isaac/native batch准入；完整成功历史与当前源码未重跑的GeoPhys限制分别标注。

### 2.7 一次完整运行结果怎样读

用一个实际JSON/H5摘要解释runtime valid、raw predicate、lifecycle task_success、Solution completion、plan completion、stop reason和close。
短程随机例子的目标是合法交互，不要求成功；Solution短测截断不能写成任务失败根因或完整成功。
输出路径必须由读者自己设定且不覆盖旧H5。读回使用正式reader，不能用文件存在/截图/stop_reason=pass反推完成。

## 第三部分：有头窗口、相机参数与图像

### 3.1 先区分三类图像通路

| 通路 | 教学须明确的合同 |
| --- | --- |
| scalar observer/UI | 显式world `observer_camera`；human在reset/step后自动显示；`rgb_array`请求时导出拥有独立存储的CPU HWC uint8 |
| scalar task RGB | `task_rgb_camera`与固定`task_renderer`成对声明；现有task observation float32合同不随UI修改；按受支持pair准入 |
| device named cameras | `render.camera_obs=True`/`render.cameras`，保留CUDA uint8和batch轴；same-step终止帧与reset后帧分开 |

Scalar具名多相机仍明确拒绝。不要把所有`rgb`都讲成同shape/dtype/device，也不让sensor依赖额外调用`render()`。
“无窗口”不等于“无渲染”；human窗口、离屏UI导出、Task sensor分别给一个调用时序。

### 3.2 CameraSpec 每个字段都要解释

精确来源`task_env/environment/config.py::CameraSpec`，填写下表的教学列与限制：

| 字段/源码默认 | 教学必须补齐 |
| --- | --- |
| name 必填；width/height=128 | 名字、像素尺寸、UI尺寸与sensor尺寸关系、正整数约束 |
| rgb=True、depth=False | 模态声明不等于任意renderer已支持深度；只演示本合同准入模态 |
| rgb_layout=HWC、rgb_dtype=float32 | 这是sensor声明默认，不能用来改写UI CPU uint8合同 |
| frame=world、parent=None | world/body/site含义；当前observer只能world；moving task camera的provider限制 |
| position=(0,0,0) | 长度3、米、world或parent坐标；三个任务实际桌面/摆杆范围 |
| quaternion_wxyz=(1,0,0,0) | wxyz次序、归一化、光轴/上方向、世界轴与外参的实际约定；不能套别家OpenGL规则 |
| fov_y=π/2 | 垂直视角单位rad，如何换算度数/焦距；长宽比从哪来 |
| near=.01、far=100 | 米、裁剪条件、根据桌面/摆杆尺寸选范围；near>0、far>near |

`〔填写：一个手算相机姿态/视线例子与图示，按实际render owner校验光轴；三个任务各一组有来源的完整参数〕`。
可以使用小型坐标图；不靠未经验证的相机位姿猜测来声称物体在画面内。

### 3.3 Pendulum：GeoPhys Rasterizer 默认有头例子

以`examples/rendering/pendulum_single_rgb.py`的world相机为已存在起点：position(0,0,2)，wxyz(√.5,0,√.5,0)。
完整脚本显式`render.backend='rasterizer'`，使用GeoPhys CPU，说明原例显式in_process而默认scalar可走worker。
分别给`render_mode='human'`和`'rgb_array'`完整差异：前者自动展示，后者`frame=env.render()`并检查shape/dtype，保存PNG可选。
`〔填写：显示环境/renderer依赖、退出方式、human返回值、无DISPLAY如何改用离屏、close后行为〕`。

### 3.4 PickCube：桌面相机与动作可视化

沿第二部分随机pose或Solution循环，只加公开render/camera声明，不调用provider viewer私有方法。
固定GeoPhys Rasterizer为首个教程路线，给桌面与TCP都可见的world相机参数/尺寸/fov/near/far，并写明其来源及验证状态。
另给MuJoCo reference/Isaac RTX如何按实际准入选择；不在MuJoCo native observer上强填rasterizer后默默fallback。
解释`render_mode`不负责切换physics；renderer构造后固定，普通reset不换renderer。
`〔填写：完整human脚本、rgb_array差异、物体/TCP预期位置、一次step前后画面如何关联同一边界〕`。

### 3.5 NutAssembly：相同配置方式与Task差异

复用原Nut Solution和same renderer/world-camera合同，给Nut/peg/手同时可见的相机参数；不能把PickCube source当Nut图像代替。
明确随机输入限制、有头显示不等于strict Solution完成，GeoPhys当前源码未重跑不能写为最新完整任务已复验。
`〔填写：完整human例子、正常关闭、支持/未验证的render组合、源帧与任务边界对照方法〕`。

### 3.6 独立的任务sensor例子

展示一个现有受测scalar task_rgb声明和一个device base/hand声明，解释mount、图像设备/布局、metadata与记录。
只选已有强证据，不扩张成三个任务×三provider×多renderer全矩阵；深度、分割、moving camera按原能力明确标注。
附故障排查：全黑/镜头朝向、裁剪、缺渲染资产、未知parent、unsupportedpair、陈旧图像、无display、可选RayTracer私有兼容错误。
禁止静默fallback或读provider私有渲染状态。

## 第四部分：Pendulum/PickCube device 并行与三后端选择

### 4.1 共同入口与新旧并行路线区别

```python
from task_env import make_parallel_env
env = make_parallel_env(
    "pendulum-v1", num_env=3, backend="cuda", execution="device",
    env_config={"execution": {"physics_provider": "mujoco_warp"},
                "episode": {"seed": 73, "horizon": 20}},
)
```

给完整reset/step/finally close，写明`config`与`env_config`参数差异，`execution='device'`与`execution.physics_provider`各自含义。
batch三个provider是`mujoco_warp`、`geophys`、`isaacsim`；不能用`mujoco`CPU替代MJWarp。
`step()`是正式device接口，不能教`step_device()`；旧local/remote/SB3是另一合同，不从类名推断兼容。

### 4.2 六个可复制命令

从仓库根运行，解释器见第一部分；`--interpreter`是所选worker解释器，父进程用Core。

```bash
"$GEOCHORA_CORE_PYTHON" examples/parallel/pendulum_device.py --provider mujoco_warp --interpreter "$GEOCHORA_MJWARP_PYTHON" --num-env 3 --steps 20
"$GEOCHORA_CORE_PYTHON" examples/parallel/pendulum_device.py --provider geophys --interpreter "$GEOCHORA_GEOPHYS_PYTHON" --num-env 3 --steps 20
"$GEOCHORA_CORE_PYTHON" examples/parallel/pendulum_device.py --provider isaacsim --interpreter "$GEOCHORA_ISAAC_PYTHON" --num-env 3 --steps 20
"$GEOCHORA_CORE_PYTHON" examples/parallel/pick_cube_device.py --provider mujoco_warp --interpreter "$GEOCHORA_MJWARP_PYTHON" --num-env 3 --steps 20
"$GEOCHORA_CORE_PYTHON" examples/parallel/pick_cube_device.py --provider geophys --interpreter "$GEOCHORA_GEOPHYS_PYTHON" --num-env 3 --steps 20 --geophys-contact-mode discrete --geophys-contact-iterations 32
"$GEOCHORA_CORE_PYTHON" examples/parallel/pick_cube_device.py --provider isaacsim --interpreter "$GEOCHORA_ISAAC_PYTHON" --num-env 3 --steps 20
```

说明GeoPhys其余冻结coupled/contact预算从哪来，不能只因CLI显式32就声称默认预算物理问题解决。
`〔填写：每条命令的纯静态参数核对、既有G06证据对应表、首次启动预期等待、输出JSON字段与受测B范围〕`。
不要求本窗口重跑六格；命令静态成立、历史已运行、当前源码native三类标签必须分开。

### 4.3 两个动作树与输出轴

Pendulum示范CUDA float32 `(B,1)`的`{'torque':...}`；PickCube按`single_action_space['effort'].shape`建立 `(B,*shape)`的`{'effort':...}`。
PickCube显式profile`panda-direct-effort-v1`与`robot.native_drive='disabled'`，不把标量R3 Solution塞入batch。
逐项给obs树、reward/done `(B,)`、seed/episode_id、owned/borrowed数据合同与读回示例；不能只写“返回Tensor”。
`〔填写：`read_device_state(('qpos','qvel'))`实际返回类型/identity、哪些字段是provider事实而非可移植算法API、CPU导出拷贝代价〕`。

### 4.4 生命周期、相机与整批切换

用已存在`reconfigure_device.py`等caller给部分reset、same-step终止帧/_final_observation、episode_id、固定Rasterizer重建的时序。
区分“构造时选择provider”和“同Env reset整批切换”；后者只教已接收Isaac↔MJWarp，GeoPhys跨provider明确拒绝。
shared scene可能看到邻行几何，不承诺视觉隔离。SB3旧masked autoreset不能再次包住same-step Env reset；RSL旧step_device adapter不能当正式device训练通过。
`〔填写：一个最小终止/partialreset解释图、`--sensor`/`--window`如何使用、close_render与close区别、batch记忆体缩小方法〕`。
Nut batch、R3 batch和完整训练不在此章扩展范围。

## 第五部分：环境构建、资产实例、Robot与canonical action

### 5.1 从最小场景理解唯一执行链

绘制并解释 `Task/Robot/Scene declarations → source composition/compiler → binding → SelectedReferenceEnv → RuntimeSession/provider`。
reset sampler只产生命名初态；TaskDefinition只做语义；Controller只计算；Runtime独占native推进/清理。
`〔填写：逐步对应真实文件/符号和一个内置task的构造顺序、state publication/feedback返回路径〕`。
不要创建第二Env/Runtime来降低教程难度，也不让用户通过solver.qpos私有索引实现Task。

### 5.2 导入资产与构建实例必须分开讲

至少给两种来源：已pin的MJCF/mesh closure，以及已准入USD delivery；不承诺通用URDF/任意网格自动成为可仿真Robot。

| 阶段 | 真实owner/类型 | 本节必需内容 |
| --- | --- | --- |
| 源身份 | `AssetDefinition`、组件`AssetManifest` | 稳定URI/版本/内容/来源与本地路径区别，mesh/textures/includes closure，源文件不在step中改写 |
| 表示与交付 | `artifacts/contracts.py`、`artifacts/asset_scene.py`、`assembly/asset_scene.py` | 受支持表示、USD bindings/prepare/load、需要的原始检查、manifest不等于runtime准入 |
| 场景实例 | `EntityInstance`、`SceneDefinition`、`PoseWorld` | 同一asset可以有不同entity_id，初始位姿/速度与Task reset属于实例；资产本身不保存native句柄 |
| Robot实例/引用 | `RobotInstance`、`FrameReference`、`JointReference` | 命名关节/Frame、TCP、axis/sign/单位、source映射，asset ID与entity ID不能混用 |
| 编译与提交 | `assembly/source_composition.py`、`runtime/sessions/source_composition_adapters.py` | lowerer拥有provider转换，Task不写provider索引，Scene只有一个推进owner |

教程中给一个实际可构造的`AssetDefinition('asset-definition-v1',...)`和`EntityInstance('entity-instance-v1',...)`配对例子，含validate、两实例身份比较。
再沿一个内置Scene展示它们如何接入真实source，不把数据类能构造冒充资产已导入仿真。
`〔填写：所用MJCF路径、mesh根、closure验证/报错、USD source delivery入口、文件与Scene实体映射表、完整小例子〕`。
资产服务生成/下载只是可选入口，链接原Skill/asset workflow；不在本教程自动部署模型或宣称第三方分发许可。

### 5.3 复用并修改一个Task

从`examples/tasks/declared_marker.py`逐个解释`PandaBoxDeclaration`、Timebase、SemanticDefinition、ResetSample、TaskEvaluation、注册UID与binding。
解释该例用到的`ReferenceTaskBinding`/compiler是现有owner级扩展接口，不把它提升为任意资产都支持的顶层API。
给“只改reset范围”“只改success predicate”“换已有物体”各自应改哪一段、不该改哪一段；代码必须完整可追踪，不能从diagnostics导入私有fixture。
`〔填写：逐段带注释的现有例子、注册导入与make_env调用、一个实际初始化/观测/成功谓词结果、未知UID/未解析引用失败说明〕`。
不要求新建另一个正式Task UID、新factory或重跑全部A123。

### 5.4 Robot主体如何构造

比较`PandaAgent('panda-v1')`与`AssembledPandaAgent('panda-arm-hand-v1')`的**实际构造签名**，不能把UID当作其Python位置参数猜着调用。
沿`RobotComponent`/`AgentComponent`抽象能力解释asset_manifest、reference_spec、initial_state_spec、supported_controller_kinds、source recipe/profile。
装配例必须复用现有arm＋hand与固定attachment；给原件ID/装配实例ID/TCP/通道/传动/夹爪耦合映射，不再造装配Panda。
`〔填写：最小Robot声明代码、如何注册/选择已有Robot、source_recipe对应关系、r1/r1_split/R3支持表与worker限制〕`。
位置/力矩控制、native drive、模型与本体补偿分别解释；不自动补偿抓持物载荷，不承诺换Robot后任意Solution无需验证。

### 5.5 canonical action与native actuation

给用户action → Controller目标 → typed物理贡献 → adapter/native application → ACK/feedback的完整命名映射。
区分canonical action并非所有Task固定一个向量；`joint_efforts`为关节轴力/矩，`body_wrenches`为body外载，两者不混成native ctrl。
给Pendulum torque和Panda pose各一条已稳定实例，并解释默认恒等Controller初始unbound、绑定subject/writer/units后才可用。
独立场景载荷、force/torque参考点/坐标系、sum/effect去重、hold/clear公共语义可以讲；**新的公共调用签名/provider边界/IPC/证据须等7b接收后由attempt002填写**。
`〔填写：单位、作用轴、ordered keys、source/scene绑定、reset后stale失效、反馈和记录字段的规范链接〕`。

## 第五部分独立章：从现有Controller抽象实现自己的控制器

### C1. 先选择当前存在的扩展合同

`task_env.controllers.contracts.Controller`是Protocol，包含`action_space`、`reset(snapshot)`、`convert(action,snapshot)->ControlCommand`；不是需要继承的ABC。
当前selected typed物理路线的实例采用`compute(action,state,context)`、source-bound binding和显式model/reset生命周期。
教程必须分别标明这两条合同的真实消费者、稳定性与限制，不能宣称旧Protocol能直接接任何selected Task。
`〔填写：精确import、方法签名/调用者、Protocol与ABC区别、为何推荐先复用已有Controller再做小扩展〕`。
不得凭空引入`BaseController`、`register_controller`、全局manager或给selectedfactory新增kwargs来让教程简单。

### C2. 先复用：默认恒等与已有profile

按真实`DefaultCanonicalController.bind`/`bind_many`给一个single subject与已有nested subject配置例子。
逐项解释channel声明、writer、单位/axis、transmission/native drive、action_space、source identity。
说明默认Controller并不表示任意夹爪position actuator可以把旧pose数组当effort透传。
给一个现有profile参数修改示例，写明合法字段和reset是否重新绑定；不是把Controller对象塞进未声明config字段。

### C3. 第一个自定义算法：命名关节PD／线性effort

以现有`LinearEffortControllerV1.zero_bias`/`LinearEffortProfileV1`和真实`PhysicalControlBindingV1`为最短起点。
如选择新的教学类，放普通示例/文档代码，只实现现有extension contract，不新建生产Controller框架。
`〔填写：完整可读代码；输入目标的单位和shape；q/qd来自公开state；kp/kd与饱和；逐通道JointEffortV1；PhysicalCommandBatchV1输出〕`。
必须解释下列每一步，不可只贴长代码：

1. 从当前Task/source取得真实binding与有权限的ordered channels；禁止硬填Panda7维到公共代码。
2. 定义有界action_space并验证finite/shape；区分目标q、deltaq与effort。
3. reset用已实现状态清理积分/历史目标，episode或source变更后拒绝旧context。
4. 在公开同边界state上计算；模型只做pure evaluate，不推进scratch或真实物理。
5. 使用声明writer/policy/unit/range输出typed贡献；组合与饱和顺序归原公共owner。
6. 通过原Task binding/Robot选择接入；没有通用用户注入入口时明确这是extension author步骤，不伪称一行config插件。
7. caller只调用`env.step`，检查ACK/实际状态与close；Controller不得直接写native数组或step。

### C4. 带模型、TCP和重力补偿的进阶控制器

参考`OperationalSpaceEffortControllerV1`、`ControllerModelRequirementV1`、原source dynamics，解释model source/ABI、joint order、frame和cadence。
给模型绑定/释放、普通reset与参数重建、same-source质量/偏置项读取的时序；R3位置路线与effort路线不要混为一套算法。
阐述补偿贡献的effect ownership，避免重复加gravity；原/装配本体模型不能用相同维度推定同源。
`〔填写：world TCP pose→effort的公式、数据来自哪个公开model/state字段、source/timing错误怎么拒绝、适用provider/部署范围〕`。
不在7c实现新的OSC、数值模型或任意provider模型代理。

### C5. 一份能揭露错误的验收示例

教学至少展示：非零输入后实际状态响应；reset后目标/积分清零；错误shape/单位/过期context拒绝；受支持的普通profile重置；close。
空载TCP跟踪需要同输入可比oracle与误差单位，ACK不是跟踪精度；静态/纯算法验证不是native成功。
`〔填写：教学验证代码、已有可复用运行证据、测量误差的计算方式、未执行的native项〕`。
新profile未支持worker/device/夹爪时明确列出，不把未验证组合升为“跨后端控制器”。

## 第六部分：API详细用法、迁移和排错

### 6.1 构造/配置速查

按实际签名逐项写`make_env`、`make_parallel_env`、make_agent/object/scene、registries、mapping/YAML与resolved roundtrip。
解释`resolve_env_config`是需要task_uid/scene_uid等关键字的构造函数，不是`resolve_env_config(mapping)`。
selected七section（execution/episode/task/controller/robot/runtime/render）与classic结构分开；列表中每个字段要标默认、类型、单位、可选值、约束、覆盖优先级和对应短例子。
禁止复制旧顶层provider/backend/horizon、recipe/environment、已退休UID或`static_template`配置。

### 6.2 生命周期与动作

逐项说明reset(seed/options)、step、action_space/observation_space、resolved_public_config、metadata、可用state/spec查询、close及幂等/关闭后行为。
给scalar五元组和batch五元组并排例子；reset执行/Controller切换只列当前受支持reset_profile，固定renderer不切换。
stale/foreign命令、preflight不修改活episode、replacement后fault与恢复、partialwrite处理按真实合同描述。

### 6.3 图像与数据有效期

将render/human/rgb_array、task sensor、namedcamera、CPU/CUDA、拥有/借用、布局、值域、终止图像规则链接到第三部分与canonicalAPI。
给“需要长期保留哪份数据”“何时copy”“何时close_render”三个实际调用例子。
不通过把GPU tensor.numpy直接调用省略设备拷贝，也不把sensor默认float32应用于UI。

### 6.4 Solution、记录、独立读回

解释caller-ownedSolution reset/act/observe/done/failed、env.start_recording/finish_recording、普通trajectoryCLI/reader。
列H5边界N+1与transitionN、最终边界图像、schema、identity、completion可缺/null的语义；源身份和完成证据不能由文件名推断。
每种实际API至少一段完整例子；历史缺completion不补造，读回与caller同run关联。

### 6.5 learner/vector边界与迁移

记录SB3固定空间/flatten/autoreset，RSL现有step_device与正式device step的兼容边界。
BaseTaskEnv保留2.x alias；旧构造/step_expert不是新教程主线，不重建旧基类生命周期。
`〔填写：支持/明确拒绝/未迁caller表、旧→新参数/UID对照、对应异常与正确替代例子〕`。
不要求完整训练或重跑历史矩阵来写本节。

### 6.6 排错表与可恢复信息

表列触发命令、失败阶段、实际异常/信息、用户可检查项、原owner/文档链接、是否需要重新构造：
解释器/ABI、MuJoCo版本冲突、GeoPhys分支/pin、SDK子进程缺依赖、source/mesh/delivery缺失、未知profile、单位/shape错误、Nut随机拒绝、unsupportedrenderer、window依赖、fault/stale、资源不足、close失败。
避免通用“重装全部依赖”“放宽门限”“关闭检查”“切换私有solver”等建议。

## 7. 合并、验证与填充完成判据

### 7.1 已确认的文档漂移：必须逐项处理

| 编号 | 当前矛盾/缺口 | attempt001处理 |
| --- | --- | --- |
| D01 | `examples/README.md`和`task_env/doc/api`仍称正式device batch未适配 | 按G06受测两个任务/三provider改正，保留旧local/remote区别及历史失败 |
| D02 | 安装/示例沿用早期Isaac失败而未导航后续U4/7a/G06 | 更新当前能力导航；九格最终接收仍等待7b，不重写早期失败 |
| D03 | Core3.8.1、GeoPhys完整requirements≥3.15、MJWarp4.0混装风险 | 分清安装profile与已验证解释器，未验证新安装明确留下收据 |
| D04 | UI rgb_array旧float32/CUDA说法与CPU uint8合同不一致 | 同步当前render合同，保留sensor自身dtype/设备 |
| D05 | 资产/Robot/Controller文档部分仍按旧BaseTaskEnv推进 | 更新为共同SelectedReferenceEnv与真实extension合同，不把所有旧组件路径删掉 |
| D06 | 教程要求Nut随机动作，但普通随机当前被拒绝 | 保留所需章节、预期拒绝例子及T-NUT-RANDOM缺口；禁止假完成 |
| D07 | 新BodyWrench、Isaac bootstrap/IPC与7b最终能力仍变化 | 记录固定WAIT_7B_ACCEPTANCE槽位和owner，attempt002才冻结最终签名/证据 |

### 7.2 每个片段的审阅方法

先做实际源码与caller逐字段核对，再做Python AST/YAML/JSON静态校验；参数名、action树、import与生命周期须有对应符号。
引用已有native证据时核对精确task/provider/source/controller/render和受影响diff；仅需新增片段的未验证范围单列。
attempt001不安装依赖、不初始化引擎/CUDA，不为文档重跑7b九格。不能把AST、`--help`、mock或截图数量当运行通过。
无运行预算时仍应把文案/完整代码写完并明确未验证，不能全页写TODO；真实实现缺口保留在缺口表。

attempt001返包逐章节列：目标页、已填槽位、源码符号、示例完整性、复用证据/静态检查、缺口/WAIT项。
主审需要按读者顺序检查能否从零选择路线、运行例子、判断结果和定位错误；不按页数/字数/通过测试数接收。

### 7.3 attempt002专有收尾

仅在7b独立主审接收之后，从实际接收HEAD对docs分支做影响对账/正常整合，保留历史输入与失败。
填写新的场景外载API/provider准入/传输/记录合同、最终单一能力矩阵、7Goal/22子阶段摘要、最终恢复页/Skills与文档快照。
复查本页所有WAIT项及T-NUT-RANDOM，不以“7b通过”推定Nut普通随机已支持。
attempt002再按可用授权决定最短受影响示例验证，不能自动借用7b资源预算或声称全新安装/所有图像例子已验证。
版本接收与发布分开；不自动merge到develop/main、push/tag/Release或分发第三方资产。

## 8. 外部教程结构参考（2026-11-17查阅）

- [mjlab v1.1.1安装](https://mujocolab.github.io/mjlab/v1.1.1/source/installation.html)：借鉴“先选择安装路径，再给验证步骤”的组织方式；GeoChora不照抄其editable安装。
- [Isaac Lab 3.0安装](https://docs.nvidia.com/isaaclab/3.0/isaac-lab/installation)：借鉴SDK/解释器选择的分流；GeoChora使用自身部署合同。
- [Isaac Sim6.2 pip安装](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/install_python.html)与[app安装](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/install_workstation.html)：核对Python/GLIBC、独立环境与两种安装入口；不将厂商步骤称为GeoChora实测。
- [ManiSkill Quickstart](https://maniskill.readthedocs.io/en/latest/user_guide/getting_started/quickstart.html)：借鉴先展示spaces/reset/step再介绍GPU batch的教学顺序；GeoChora的动作、设备和autoreset按自己合同解释。
- [robosuite自定义Controller](https://robosuite.ai/docs/tutorials/add_controller.html)：借鉴完整算法、配置和接入示例独立成章；不引入它的继承/注册API。

这些页面只提供教学组织参考；本教程所有API、可执行片段和能力结论必须来自上述冻结GeoChora源码、实际caller与证据。
