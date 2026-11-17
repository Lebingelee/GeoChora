# 安装、后端隔离与路径配置

本页是 v2.1.1 **唯一安装教程**。它按“先选路线，再装依赖，最后核对路径”的顺序展开；符号级配置字段仍以 [API 入口](../api/README.md)和 `task_env/doc/api/` 为权威。

> **状态边界（2026-11-17，7c attempt001）**
>
> 本页的命令与源码接口按源码基线和既有部署清单静态核对；**本轮没有执行 clone、pip、下载、setup 脚本、MCP 注册或任何 SDK/native 启动**。文中标为“既有部署事实”的内容来自已有环境记录；标为“未验证”的内容不得当作全新安装成功。

## 1.1 先选择最小安装路线

参考操作路径是 **Linux x86-64 + CPython 3.12**。本页不把其他平台、其他 Python 版本或 Windows/macOS 组合宣称为已验证。GPU、驱动和显示需求只对相应路线提出；纯 state-only CPU 任务不要求 Isaac、CUDA renderer、资产生成服务或 MCP。

| 路线 | 已知冻结身份 | 必须理解的隔离关系 |
| --- | --- | --- |
| Core／MuJoCo CPU | MuJoCo `>=3.8.1,<3.9.0`（参考环境观测到 3.8.1） | Core 的参考解释器；不为了迁就其他 SDK 升到 4.0 |
| GeoPhys CPU／CUDA | pin `198d30ac64ce873a1467f55d2adfc471db18fbc5`；匹配开发分支 `codex/v211-stage6-render-device`；`taichi-forge==0.7.0` | pin 才是恢复身份，分支名不足；其完整 requirements 声明 `mujoco>=3.15.0`，与 Core 区间无交集 |
| MJWarp device | MuJoCo／`mujoco-warp==4.0.1`、`warp-lang==1.18.0`、Python 3.12 冻结清单 | 专门 worker 解释器；不能把该清单覆盖安装进 Core 3.8.1 环境 |
| Isaac Sim 6.2 | Python 3.12；pip 依赖库与 app 解压两种部署 | SDK 自带 NumPy/Torch/pxr 等独立约束；不在 SDK 环境里安装全部 Core requirements |

来源与核对口径：

- **本机参考条件**：约 8 GiB VRAM、16 GiB RAM；这是本机运行条件，不是厂商最低要求，也不是 batch 上限。G06 的 B16 性能/资源数据见 [G06 实施总结](../maintenance/g06/implementation-summary.md)。
- **Torch**：既有 device 主解释器使用 Torch 2.14.0+cu130 与 CUDA Python bindings；它和 Isaac Sim 官方安装页给出的 SDK 依赖版本分开记录，不强行统一。该版本记录属于既有部署事实，不是本页新装验证。
- **磁盘**：Core + 两个 submodule 加 Python 环境通常需要数 GiB；Isaac app 解压另需官方包声明的空间。本页不给出未经本机实测的精确数字。
- **来源日期**：pins 与依赖清单按 2026-11-17 工作树和已完成部署核对；NVIDIA 官方页面的版本/平台要求以用户查阅时页面为准。

## 1.2 获取 Core 与固定 submodule

本仓库真实 `.gitmodules` 声明：

| submodule | URL | 本版 pin |
| --- | --- | --- |
| `GeoPhys` | `https://github.com/SCAILab-USTC/GeoPhys.git` | `198d30ac64ce873a1467f55d2adfc471db18fbc5` |
| `asset/external/mujoco_menagerie` | `https://github.com/google-deepmind/mujoco_menagerie.git` | `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` |

```bash
# 将两个尖括号值替换为维护者给出的真实 remote/ref；在新目录运行。
git clone --branch <受支持的 Core 分支或 tag> <GeoChora 仓库 URL> GeoChora
cd GeoChora
git submodule update --init --recursive
git rev-parse HEAD
git submodule status --recursive
```

三件事分别完成：

1. `git clone` 取得 Core 提交；
2. `git submodule update --init --recursive` 把 `GeoPhys` 与 Menagerie checkout 到 Core 记录（gitlink）的提交；
3. 后面的 Python 环境安装只安装**解释器依赖**，不会替你选择或切换 submodule。

预期 `git submodule status --recursive` 的前缀是空格（已初始化且与索引一致）；若前缀是 `-`，表示未初始化；若是 `+`，表示 checkout 与 gitlink 不一致。不要用 `git checkout -f` / `git clean` 覆盖已有 dirty 工作。

已有 checkout 先检查：

```bash
git status --short
git rev-parse HEAD
git -C GeoPhys rev-parse HEAD
git -C asset/external/mujoco_menagerie rev-parse HEAD
```

**诊断位置**：Panda 的源 MJCF 由 `PandaAgent.asset_manifest()` 指向 `asset/external/mujoco_menagerie/.../franka_emika_panda/panda.xml`；缺失或版本不符时，先核对 gitlink，再核对任务声明的 asset root。不要从另一份旧 checkout 隐式补文件。

修复 GeoPhys 到 pin 的**只读核对**：

```bash
git -C GeoPhys rev-parse HEAD            # 期望 198d30ac64ce873a1467f55d2adfc471db18fbc5
git -C GeoPhys branch --show-current     # 本机既有部署为 codex/v211-stage6-render-device
```

**分支名不是恢复身份**：追踪 GeoPhys `main` 会丢掉与 Core 匹配的 stage6 render/device 能力；即使分支名相同，也必须核对 pin。若某个 remote 不存在该匹配分支，用 Core gitlink 的提交恢复，不要让用户创建同名分支掩盖差异。

## 1.3 Core／MuJoCo CPU 安装

```bash
python3.12 -m venv .venv-core
.venv-core/bin/python -m pip install --upgrade pip
.venv-core/bin/python -m pip install -r task_env/requirements.txt
```

`task_env/requirements.txt` 的实际内容包含：`numpy==2.2.6`、`scipy>=1.14`、`psutil`、`pydantic>=2.11.0`、`PyYAML>=6.0`、`taichi-forge`、`trimesh`、`pyvista==0.46.5`、`Pillow>11.0`、`mujoco>=3.8.1,<3.9.0`、`gymnasium>=1.3.0`、`h5py>=3.10`。

注意两点：

- Core requirements 里的 `taichi-forge` **没有固定版本**；GeoPhys 要求 `taichi-forge==0.7.0`。Core 单环境不一定会 import GeoPhys，但一旦把 GeoPhys 源码放进同一解释器，版本就必须按 GeoPhys 的声明核对。
- **Torch 不在 Core requirements 中**。它只在 learner/device 父进程或特别声明的路线需要；不要因为清单没列就以为所有路线都不需要 Torch，也不要因此把它塞进 MJWarp/Isaac worker 环境。

参考环境中的 CPU/CUDA Torch 选择：

```bash
# 需要 Torch 的 learner/device 父进程（示例值，按机器 CUDA 选择官方 wheel）
.venv-core/bin/python -m pip install torch --index-url <所选 CUDA 版本的官方索引>
```

仓库没有 root `pyproject.toml`、`setup.py` 或 `setup.cfg`，**不要写 `pip install -e .`**，也不要为了教程通过而新建 packaging。运行示例时用显式 `PYTHONPATH`。

版本/模块核对（只检查，不构造引擎）：

```bash
.venv-core/bin/python --version
.venv-core/bin/python -m pip show mujoco numpy gymnasium h5py
.venv-core/bin/python - <<'PY'
import mujoco, numpy, gymnasium, h5py
print('mujoco', mujoco.__version__)
print('numpy', numpy.__version__)
print('gymnasium', gymnasium.__version__)
print('h5py', h5py.__version__)
PY
.venv-core/bin/python -m pip check
```

预期：Python 3.12.x；MuJoCo 落在 `3.8.1`～`<3.9.0`；`pip check` 输出 `No broken requirements found.`。**import 成功不等于 reset/step 成功**，更不等于任务成功；下一步的 scalar Quickstart 才检查生命周期。

## 1.4 GeoPhys 安装与分支切换

GeoPhys 在本仓库中以源码子模块存在，Core 通过 `GeoPhys/src` 导入；provider bootstrap 调用公开的 `geophys.init_taichi`（见 `task_env/runtime/provider_bootstrap.py`）。Forge 是 GeoPhys 默认的 Taichi 发行实现，不是官方 Taichi 的同义替换；官方 `taichi` 仅用于对照，且需要单独的 A/B 环境。CPU/CUDA 与 renderer 依赖分别判断，renderer 不是 state-only 的前提。

**依赖冲突必须明说**：Core 声明 `mujoco>=3.8.1,<3.9.0`；该 GeoPhys pin 的 `requirements.txt` 和 `pyproject.toml` 声明 `mujoco>=3.15.0`。两个完整 requirements 没有交集，**不存在“连续安装两份完整 requirements 到同一解释器”的已验证方案**。

### 路线 A：复用已验证的 Core＋GeoPhys source profile

这条路线不让两份 requirements 的 resolver 互相覆盖，而是显式提供已有的 GeoPhys `src`，并核对所需依赖：

```bash
export GEOCHORA_GEOPHYS_SRC=/absolute/path/to/GeoPhys/src   # 必须含 scene/__init__.py
export GEOCHORA_GEOPHYS_PYTHON=/absolute/path/to/core/env/bin/python
```

- 既有 G06/worker 部署把 GeoPhys 源码作为路径使用；`geophys` 不是必须存在的 pip 发行包。
- GeoPhys 的 Forge 版本按 pin 为 `taichi-forge==0.7.0`；G06 记录还使用同版 `taichi-forge-runtime==0.7.0`。
- 这条路线复用“已存在的 Core＋GeoPhys 部署清单”。本页不根据经验手工删掉 GeoPhys 的 `mujoco>=3.15.0` 后宣布新安装通过。

### 路线 B：单独安装 GeoPhys 开发环境

在独立解释器中按 pin 的 `pyproject.toml`/requirements 安装，Core 通过 `execution.interpreter` 或 worker 连接：

```bash
python3.12 -m venv .venv-geophys
.venv-geophys/bin/python -m pip install --upgrade pip
.venv-geophys/bin/python -m pip install -r GeoPhys/requirements.txt
.venv-geophys/bin/python -m pip show taichi-forge taichi-forge-runtime
.venv-geophys/bin/python -m pip check
```

`GeoPhys/requirements.txt` 能否被 resolver 完整满足必须单独报告；如果失败，保留失败输出，不要隐藏，也不要改成“只装子集就算通过”。本页没有在本轮运行该命令，因此**不声明全新 GeoPhys 环境已可运行**。

各入口的支持范围要分开描述：

| 入口 | 已稳定使用的范围 | 不能由此推出 |
| --- | --- | --- |
| scalar state-only | GeoPhys CPU 的 Pendulum/双轮车/所测 PickCube/Nut 路线 | 任意 control/model/render 组合 |
| scalar worker | 默认 GeoPhys worker；显式解释器可覆盖 | CUDA 训练热路径或零拷贝 |
| device batch | G06 受测 B3（provider/source/renderer 交集内） | 任意资产、任意 batch 或连续 mesh |

检查 `GEOCHORA_GEOPHYS_SRC`：

```bash
test -f "$GEOCHORA_GEOPHYS_SRC/scene/__init__.py" && echo "geophys src ok" || echo "GEOCHORA_GEOPHYS_SRC is not a GeoPhys src"
```

注意 `examples/_common.py` 的行为：如果当前进程已经从不一致路径 import 了 `scene`，bootstrap 会要求新解释器，避免混用两份源码。

## 1.5 MJWarp／MuJoCo 4.0 安装

```bash
python3.12 -m venv .venv-mjwarp
.venv-mjwarp/bin/python -m pip install --upgrade pip
.venv-mjwarp/bin/python -m pip install -r task_env/dependencies/mujoco-warp-4.0.1-python312.txt
```

该清单是 **G06a attempt001 已解析的隔离 worker 环境**，不是主解释器替代品：

- `mujoco==4.0.1`、`mujoco-core==4.0.1`、`mujoco-studio==4.0.1`、`mujoco-warp==4.0.1`、`warp-lang==1.18.0` 属于 4.0/MJWarp 路线；
- 不是旧的 `mujoco-py`，也不是 MJX；
- 清单不含 Torch；learner 父进程仍用 Core/Torch 解释器；
- `pip check` 在该隔离环境已通过（既有部署事实）。

这只说明清单本身在冻结环境中解析成功，**不说明全新环境已完整可运行**。安装后还须：

1. 选择 worker 解释器（`execution.interpreter` 或 `GEOCHORA_MJWARP_PYTHON`）；
2. 在设备上检查 GPU/驱动可用性（`nvidia-smi`；不初始化 CUDA）；
3. 接受首次 kernel 编译/缓存较慢；
4. 用有界 Pendulum 或 Quickstart 的 device 章节做小 batch 验证。

该清单不含 Torch，也不是完整 Core 替代：worker 通过 `PYTHONPATH` 导入本 checkout 的 `task_env`，其自身环境若在 preflight 报缺 Core 侧导入依赖，应按实际错误补齐；不要把 Core 的整份 requirements 覆盖安装进 worker。

```bash
.venv-mjwarp/bin/python --version
.venv-mjwarp/bin/python -m pip show mujoco mujoco-warp warp-lang
.venv-mjwarp/bin/python -m pip check
nvidia-smi   # 只读检查；本教程不启动 CUDA 初始化
```

**本轮不执行安装、不初始化 CUDA、不运行 native。**

## 1.6 Isaac Sim：pip 依赖库安装

先阅读并自行决定是否接受 NVIDIA 许可；脚本不会替你接受 EULA。官方 6.2 安装页：

- pip 安装：<https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/install_python.html>
- app 安装：<https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/install_workstation.html>

页面上需要自行核对：Linux GLIBC 要求（6.2 页面给出 ≥2.35 的口径）、Python 3.12、GPU/驱动要求。本页不把厂商步骤称为 GeoChora 实测。

```bash
# 只读平台核对；不启动 SDK
ldd --version | head -1          # 核对 GLIBC
nvidia-smi                       # 核对驱动/GPU 可见性
python3.12 --version
```

使用**单独 venv**，不要复制 Core requirements：

```bash
python3.12 -m venv .venv-isaac
.venv-isaac/bin/python -m pip install --upgrade pip
# 按官方 6.2 页选择该 SDK 兼容的 CUDA/Torch 配置后，再执行：
.venv-isaac/bin/python -m pip install 'isaacsim[all,extscache]==6.2.0.0' \
  --extra-index-url https://pypi.nvidia.com
```

关系要分清：

| 角色 | 解释器 | 责任 |
| --- | --- | --- |
| Core 父进程 | `.venv-core/bin/python`（或所选 Core 解释器） | 解析配置、构造 Task/Scene、发命令、汇总结果 |
| Isaac SDK 子进程 | `.venv-isaac/bin/python` 或 app 的 `python.sh` | 初始化 Kit/PhysX、真实推进、返回边界 |
| USD source delivery | 由 Task/source owner 或显式 manifest 提供 | 资产内容与 closure；不是 Python 包安装的副产物 |

`execution.interpreter` 指定 SDK 子进程解释器；未显式给定时，selected 配置的默认值来自 `ISAAC_SIM_PYTHON`。父进程能 `import isaacsim` **不证明** SDK 子进程可用；反过来，父进程不需要 import 整个 SDK。

缺少 USD 资产或 manifest 的典型报错来自 source/delivery 预检（缺文件、closure 不符、未准入），不是 pip 依赖问题。直接 Isaac 示例使用已安装资产；高级 F06 Harness 才要求精确 delivery manifest，两者是不同命令合同。

厂商安装验证与 GeoChora task 验证分开：

```bash
# 只做版本/路径检查，不启动 App（示例；以官方 6.2 页为准）
.venv-isaac/bin/python -c "import isaacsim; print(isaacsim.__file__)"
```

v2.1.1 对 6.2 有既有短程 Env 证据，但**不是**“任意 Isaac 场景/任意资产”资格。7b 仍在调整的 dependency overlay/bootstrap/BodyWrench transport 归 attempt002；本页只写已稳定合同与准确缺口。

## 1.7 Isaac Sim：app 下载解压安装

与 pip 路线并列，不是替代关系：

1. 从官方 6.2 下载页选择 Linux 平台包；
2. 核对下载文件的官方校验值/大小；
3. 解压到**用户可写**的 SDK 目录（仓库外或 ignored workspace；不要提交 SDK）；
4. 按官方 post-install 步骤初始化；
5. 确认启动脚本与 Python 入口。

```bash
# 目录名与包名以官方 6.2 页面为准；下列是结构示意，不是伪造的官方文件名
export ISAAC_SIM_ROOT=/absolute/path/to/isaac-sim-6.2
test -x "$ISAAC_SIM_ROOT/python.sh" && echo "python.sh present"
test -x "$ISAAC_SIM_ROOT/kit/python/bin/python3" && echo "kit python present"
"$ISAAC_SIM_ROOT/python.sh" --version
```

两类入口不能无条件互换：

- `python.sh` 是 SDK 提供的 shell launcher；GeoChora 的 interpreter provenance 能识别名为 `python.sh` 的 launcher，并以 `launcher` 记录；
- `kit/python/bin/python3` 是 Kit 内部 Python；直接运行它不一定带上 app 的启动环境变量和扩展路径。

实际边界是 **transport 的启动方式**：`execution.interpreter` 应指向经验证能启动该 SDK 的入口（pip Python 或官方 launcher）。以 `python.sh` 启动时，仍按真实子进程回执核对版本与 origin，而不是把 stdout 当作 JSON。

给已有 SDK 的例子（SDK 在仓库外）：

```bash
export ISAAC_SIM_PYTHON="$ISAAC_SIM_ROOT/python.sh"
export OMNI_KIT_ACCEPT_EULA=YES        # 只有在你已阅读并接受 EULA 后才设置
```

不要把 SDK 复制进 ignored workspace 来“让路径统一”，也不要让新工作树隐式指向另一个工作树里的缓存。`scripts/setup/geochora-env.sh` 只在 `workspace/environments/isaacsim-6.2.0/bin/python` 存在时才给默认值；显式变量优先。

## 1.8 后端路径配置与优先级

建议把机器相关值放在仓库外：

```bash
# ~/.config/geochora/env.sh
export GEOCHORA_CORE_PYTHON=/path/to/core/bin/python
export GEOCHORA_GEOPHYS_PYTHON=/path/to/geophys/bin/python
export GEOCHORA_MJWARP_PYTHON=/path/to/mjwarp/bin/python
export GEOCHORA_ISAAC_PYTHON=/path/to/isaac/bin/python
```

每个运行 shell：

```bash
source ~/.config/geochora/env.sh
source scripts/setup/geochora-env.sh
```

`scripts/setup/geochora-env.sh` 实际会：

- 设置 `GEOCHORA_PROJECT` 为 checkout 根；
- 设置 `GEOCHORA_CORE_PYTHON`（默认 `python3`）；
- 设置 `GEOCHORA_GEOPHYS_PYTHON`（默认等于 Core）；
- 若未设置 `GEOCHORA_ISAAC_PYTHON` 且 checkout 内默认路径存在，则设置它；
- 把 `GEOCHORA_ISAAC_PYTHON` 映射到 `ISAAC_SIM_PYTHON`；
- 设置 `GEOCHORA_GEOPHYS_SRC` 为 `<core>/GeoPhys/src`；
- 设置 `PYTHONPATH="<core>/GeoPhys/src:<core>"`；
- 设置 `PYTHONDONTWRITEBYTECODE=1`；
- 把 Core Python 所在目录放到 `PATH` 前面。

它**不会**自动设置 `GEOCHORA_MJWARP_PYTHON`；需要的话自己 export。

优先级（按源码 `task_env/environment/configuration.py::_layered_execution_selection` 与各入口）：

| 消费者 | 真实优先级 |
| --- | --- |
| selected 配置的 `execution.interpreter` | 调用方显式 `execution.interpreter` 最高；否则按 provider 默认：MJWarp→`GEOCHORA_MJWARP_PYTHON`，GeoPhys→`GEOCHORA_GEOPHYS_PYTHON` 或当前解释器，Isaac→`ISAAC_SIM_PYTHON` |
| `examples/tasks/pick_cube.py` | `--isaac-python` 高于 `ISAAC_SIM_PYTHON`；非 Isaac provider 不接受该参数 |
| Harness CLI | `--isaac-python` 高于 `ISAAC_SIM_PYTHON`；两者都没有时直接报错 |
| `examples/parallel/*_device.py` | `--interpreter` 写入 `execution.interpreter`；未给时用上面的 provider 默认 |

**不要假设所有入口共用同一条全局优先级**；以你运行的 CLI 和 resolved 配置为准。

检查变量与解释器（不导入 SDK）：

```bash
printf 'CORE=%s\nGEOPHYS=%s\nMJWARP=%s\nISAAC=%s\nSRC=%s\n' \
  "$GEOCHORA_CORE_PYTHON" "$GEOCHORA_GEOPHYS_PYTHON" \
  "$GEOCHORA_MJWARP_PYTHON" "$GEOCHORA_ISAAC_PYTHON" "$GEOCHORA_GEOPHYS_SRC"
test -x "$GEOCHORA_CORE_PYTHON" && echo "core python ok"
test -x "$GEOCHORA_GEOPHYS_PYTHON" && echo "geophys python ok"
test -x "$GEOCHORA_MJWARP_PYTHON" && echo "mjwarp python ok"
test -f "$GEOCHORA_GEOPHYS_SRC/scene/__init__.py" && echo "geophys src ok"
```

两个容易踩的坑：

1. **worker 的 `PYTHONPATH` 可能不生效**：provenance 探测使用 `-I -S`，会隔离 site 和用户路径。父进程能 import 不代表 SDK 子进程能 import；以 worker 的实际依赖预检和回执为准。
2. **source 脚本会改变 cwd 的语义**：`GEOCHORA_PROJECT` 是 checkout 根；从别的目录运行示例时仍要显式写脚本路径，或先 `cd "$GEOCHORA_PROJECT"`。不要在脚本 source 后假设 cwd 也变了。

本页不运行 `scripts/setup/setup.sh` 的默认资产下载/MCP 注册。若需要 agent 一键设置，阅读 [agent setup](../../../../global/agent-setup.md) 并显式选择 `--skip-assets` / `--skip-mcp`；默认资产步骤会下载模型并写 Codex MCP 配置，不属于 Core Quickstart。

## 1.9 检查与排错

| 症状 | 失败阶段 | 先检查 | 原 owner／下一步 |
| --- | --- | --- | --- |
| `ModuleNotFoundError: mujoco` | Core import | 该解释器是否装了 `task_env/requirements.txt` | 用 `$GEOCHORA_CORE_PYTHON -m pip show mujoco`；不要在 MJWarp/Isaac 环境里补装 |
| resolver 报 `mujoco` 冲突 | 安装 | 是否把 Core 与 GeoPhys 完整 requirements 装进同一环境 | 分开环境；复用已验证 Core＋GeoPhys source profile 或独立 GeoPhys 环境 |
| `scene` 从错误路径导入 | 启动 | `GEOCHORA_GEOPHYS_SRC` 是否指向本 pin 的 `src` | 新解释器重跑；不要混用旧进程 |
| `deployment interpreter unavailable` | worker 预检 | `execution.interpreter` 是否存在且可执行 | provider 对应变量/CLI 参数 |
| Isaac `interpreter path not configured` | Isaac 预检 | `execution.interpreter` / `ISAAC_SIM_PYTHON` | 显式给 pip Python 或 `python.sh` |
| Isaac 子进程缺依赖 | SDK 启动 | 该入口是否带上 SDK 环境 | 用官方 launcher；不要把 Core requirements 装进 SDK |
| `unknown env uid` | 构造 | 是否 import 了注册任务的示例模块 | 任务 UID 与注册 owner |
| GPU 不可用/CUDA 初始化失败 | device/native | 驱动、设备号、`cuda:0` 是否可见 | 不在本教程用 CPU provider 冒充 CUDA |
| 资产 closure/manifest 不符 | source 预检 | gitlink、asset root、delivery manifest | Task/source owner；不要静默换资产 |

需要“跑通”的最小检查不是本章的 `import`，而是下一篇 [单环境无渲染 Quickstart](quickstart-state-only.md) 的一次 reset/step/close。
