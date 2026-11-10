# 场景与资产 MCP 独立部署

本页维护资产与场景准备服务的部署合同。服务源码随本仓库分发，上游算法与权重通过固定公开来源获取；部署和运行均不需要原开发者仓库、服务器、解释器或模型缓存。三个制作 Skill 负责方法选择、Blender 装配及验收，MCP 不自动接管 TaskEnv 的任务、控制与评分。

部署状态与本机记录见[迁移验证记录](../maintenance/reviews/20261110_asset_mcp_migration.md)。安装步骤执行完成并不自动建立新资产的运行准入。

## 服务与依赖

| MCP 名称 | 工具与用途 | 执行依赖 |
| --- | --- | --- |
| `trellis2` | `submit_job`、`get_job`、`wait_job`；参考图生成带 PBR 的 GLB | TRELLIS.2、CUDA、共享执行端 |
| `ultrashape` | `submit_job`、`get_job`、`wait_job`；米制 Z-up NPZ 与参考图细化几何 | 独立 UltraShape 环境、CUDA、共享执行端 |
| `trellis-texturing` | `submit_remesh` 重拓扑；`submit_job` 固定表面贴图；共用查询与等待 | CuMesh、TRELLIS 官方贴图、Blender |
| `experiment-batch` | `start_batch`、`get_status`、`list_batches`、`wait_for_change`、`cancel_run` | 本机 Codex CLI、有效登录与可用模型 |

前三个服务通过 stdio 提供 MCP，并共用同一数据库和一个 `task_runner`。只启动 MCP 入口不会执行队列中的任务。编排服务按需自动启动本机 daemon；它创建独立 Codex 会话和 Skill 快照，`completed` 只表示会话结束。

场景布局、几何装配和 USD 导出由宿主 Agent 使用 Blender/OpenUSD 完成。二维生图工具由接收方的 Agent 客户端提供；这四个 MCP 不包含二维生图模型。Isaac Sim 用于适用的物理与实际渲染检查，单独安装，不属于模型服务的 Python 环境。

## 硬件与系统

- **GPU**：NVIDIA CUDA GPU；编译目标取本机实际 compute capability，不固定为开发机的架构。驱动须支持选用的 PyTorch CUDA runtime，CUDA Toolkit 与编译器还须能编译对应扩展。
- **显存**：本次迁移不设容量准入门槛，不开发或尝试显存优化。完整 CUDA 依赖检查通过后，真实 TRELLIS 模型请求发生 CUDA OOM，按维护者约定记为 `DEPLOYED_OOM`。原始任务仍保持失败，资产生成结果不记为成功。
- **内存与磁盘**：模型权重约数十 GB；另需两个 Python 环境、源码、编译临时目录和产物空间。初始化前运行环境检查器记录可用磁盘；本项目尚未测定统一的主机内存最低值。
- **Windows**：64 位 Windows、Conda、Python 3.11、Git、CUDA Toolkit 12.8、Visual Studio 2022 C++ Build Tools 与 Windows SDK。配置脚本自动查找 C++ 工具链；编译并发为两个任务。
- **Linux**：同一服务实现使用本机路径、Unix socket 和本地数据库。需要 C++ 编译器、CUDA Toolkit、Conda；本轮 Windows 结果不构成 Linux 验证。
- **建模与编排**：Blender 可执行文件；Codex CLI 与登录仅在使用批次编排时需要。`BLENDER_PATH` 可指定可执行文件或其目录，未指定时查找 PATH 和 Windows 标准安装目录。

原版 TRELLIS.2 的[安装说明](https://github.com/microsoft/TRELLIS.2#installation)声明其上游硬件基线；本页的部署验收按上述 OOM 口径记录，不把该上游显存数值作为安装阻断条件。

## 目录与版本

从仓库根执行下文命令。服务代码位于 `scripts/asset_services/` 与 `scripts/orchestrator/`，所有生成文件默认位于已忽略的 `workspace/`：

```text
workspace/asset-services/
  runtime/trellis2/        # 新建的 Python 3.11 环境
  runtime/ultrashape/      # 同一 Torch ABI、独立模型依赖
  third_party/            # 固定提交的公开算法与 CUDA 扩展
  models/                 # 固定 HF revision 的原始模型文件
  data/                   # 队列数据库与运行缓存
  wheels/                 # 本机编译 wheel，不跨平台复用
  evidence/               # 环境、构建、协议和真实请求结果
workspace/scene-generation/
  task_*/                 # 独立 Codex 工作目录与 Skill 快照
  .orchestrator/          # 编排记录；锁、连接与数据库位于本机临时目录
```

`ASSET_SERVICES_HOME` 可指定另一个本机绝对运行目录；MCP 注册会固定本次使用的绝对路径。更换 checkout、平台、GPU 架构或运行目录后，重新准备环境、编译、注册并验证。不要复制另一台机器的 Conda 环境、编译 wheel 或已改写绝对路径的模型配置。FlexGEMM、Torch 与 Triton 运行缓存也位于该部署目录；FlexGEMM 初始缓存来自固定公开源码，不读取开发者的个人调优缓存。

算法提交号在 `scripts/asset_services/deployment/prepare_sources.py` 固定，权重 revision 与选择文件在 `prepare_models.py` 固定。两者从公开地址获取并保存收据。TRELLIS.2 与独立贴图共用同一源码和模型 revision；UltraShape 单独固定。项目代码许可与各上游模型、算法和资产条款分别处理，保留下载的 LICENSE/README。

## 初始化 Python 与公开源码

Windows PowerShell 示例：

逐步执行，前一步非零退出时先保留错误并修复，再继续下一步。

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
conda create --prefix "$PWD/workspace/asset-services/runtime/trellis2" --override-channels -c https://conda.anaconda.org/conda-forge --repodata-fn current_repodata.json python=3.11 pip -y
$PY = "$PWD/workspace/asset-services/runtime/trellis2/python.exe"
& $PY -m pip --isolated install torch==2.8.0 torchvision==0.23.0 xformers==0.0.32.post2 --index-url https://download.pytorch.org/whl/cu128
& $PY -m pip --isolated install -r scripts/asset_services/deployment/requirements-trellis.txt -c scripts/asset_services/deployment/constraints-trellis2-win64.txt --index-url https://pypi.org/simple
python scripts/asset_services/deployment/check_environment.py
python scripts/asset_services/deployment/prepare_sources.py
```

`pip --isolated` 避免继承个人 pip 源及额外索引。可按网络条件使用可信镜像；本次本机清华 Conda/PyPI 镜像不可用，已使用上述公开源。下载失败须保留具体错误，不能跳过依赖后宣称安装成功。

CUDA 扩展包含 CuMesh、FlexGEMM、nvdiffrast、renderutils 和 o-voxel；`utils3d` 也从固定源码构建。`prepare_sources.py` 不修改已有不同版本或有跟踪文件改动的源码目录。初始化中断后保留目录与错误，确认实际 HEAD 再重跑。

## 模型授权、下载与路径生成

以下两个上游要求 Hugging Face 账号授权：

- [DINOv3 ViT-L/16](https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m)
- [RMBG-2.0](https://huggingface.co/briaai/RMBG-2.0)

使用自己的账号按上游要求取得访问权限，然后在本机终端登录。凭据只由 Hugging Face 标准凭据存储或 `HF_TOKEN` 提供，不写进仓库、示例、MCP 配置或验证日志。

```powershell
& "$PWD/workspace/asset-services/runtime/trellis2/Scripts/hf.exe" auth login
& $PY scripts/asset_services/deployment/prepare_models.py
```

下载器还准备 `microsoft/TRELLIS.2-4B`、TRELLIS 初版的结构解码器、UltraShape 权重和 DINOv2 配置。原始配置保留在固定 revision 目录；生成入口配置把模型位置改为本次部署路径。离线推理只读取这些本地文件。401/403 表示授权或下载未完成，不属于可接受的 OOM。

## 编译与第二环境

```powershell
& $PY scripts/asset_services/deployment/install_extensions.py
& $PY scripts/asset_services/deployment/verify_linux_cuda.py
conda create --prefix "$PWD/workspace/asset-services/runtime/ultrashape" --override-channels -c https://conda.anaconda.org/conda-forge --repodata-fn current_repodata.json python=3.11 pip -y
$UPY = "$PWD/workspace/asset-services/runtime/ultrashape/python.exe"
& $UPY -m pip --isolated install torch==2.8.0 torchvision==0.23.0 numpy==1.26.4 --index-url https://download.pytorch.org/whl/cu128
& $UPY -m pip --isolated install -r scripts/asset_services/deployment/requirements-ultrashape.txt -c scripts/asset_services/deployment/constraints-ultrashape-win64.txt --index-url https://pypi.org/simple
& $UPY -m pip --isolated install --no-deps (Get-Item "$PWD/workspace/asset-services/wheels/cumesh-*.whl").FullName
& $PY -m pip check
& $UPY -m pip check
```

`verify_linux_cuda.py` 是迁入的 CUDA 运算检查器，历史文件名包含 Linux，检查本身不依赖 Linux；本机结果见验证记录。UltraShape 使用同一 Torch/CUDA ABI 的 CuMesh wheel，但拥有独立 NumPy、Transformers、Diffusers 依赖。Windows 约束文件记录本次可用版本，原生扩展仍按固定源码构建，不能从 PyPI 同名包替代。构建日志保存在 `workspace/asset-services/evidence/build-*.log`；`prepare_sources.py` 显式记录 Windows 的模板消歧、标准 double 字面量和 Torch int64 维度转换补丁。编译错误、架构不匹配、缺失 DLL、未安装包和缺失模型必须修复；不以 OOM 口径豁免。

## 注册与启停

使用编排服务前，先在本机安装 Codex CLI 并执行 `codex login`；已有登录可用 `codex login status` 检查。`start_batch.model` 应使用接收方账号可用的模型，当前代码默认 `gpt-6-astra`，不依赖原开发者账号。

```powershell
& $PY scripts/asset_services/deployment/register_mcp.py
$env:PYTHONPATH = "$PWD/scripts"
& $PY -m orchestrator.server --register
```

注册器保留其他用户配置并备份旧文件。资产配置片段位于 `workspace/asset-services/mcp_config.toml`；默认注册到 `CODEX_HOME/config.toml` 或用户的 `.codex/config.toml`。其他 MCP 客户端使用同一 command/args/env。重启或重连客户端加载新工具。

在独立终端启动一个资产执行端并保持运行：

```powershell
& $PY scripts/asset_services/scheduler/task_runner.py
```

同一个数据库只启动一个执行端，以免 GPU 通道在多个进程中同时计算。停止前等待在途任务完成，再结束该进程。Windows 系统服务是可选项：管理员可运行 `deployment/register_service.py` 注册，但不会自动启动；普通部署与本轮验证均不要求管理员权限。

`experiment-batch` 首次查询会自动启动 daemon。其默认 Skill 来源为本 checkout 的 `.agents`，独立会话创建时真拷贝冻结。`ORCHESTRATOR_CODEX` 可指定 Codex 可执行文件；`ORCHESTRATOR_REPO`、`ORCHESTRATOR_STATE`、`ORCHESTRATOR_RUNTIME`、`ORCHESTRATOR_AGENTS` 分别定义工作区、记录目录、本地状态目录和 Skill 来源。Windows 使用带随机令牌的 loopback TCP；Linux 使用 Unix socket。数据库和锁放本地文件系统，不能放不支持锁的共享盘。

## 本机验收与结果含义

先运行迁入的协议、队列、文件交付和生命周期检查，再运行真实请求：

```powershell
& $PY -m unittest discover -s scripts/asset_services/tests -p 'test_*.py' -v
& $PY -m unittest discover -s scripts/orchestrator -p 'test_*.py' -v
& $PY scripts/asset_services/deployment/verify_deployment.py
& $PY scripts/orchestrator/verify_deployment.py
```

协议测试使用隔离数据库和模拟计算脚本，只验证 MCP 到子进程、队列和错误传播。编排验证实际启动一个 Codex 会话，要求它写一个固定文件，并读回文件及 Skill 来源；会消耗一次真实模型请求。

资产真实请求验证分别提交图生资产、细化、重拓扑和贴图，不因前一项 OOM 略过后续服务。检查器为本次测试启动一个执行端，完成后清理其进程；执行该检查前不要再为同一数据库启动另一个执行端。保留工具清单、参数、job_id、终态和服务返回的原始错误日志（每阶段最多8 KiB末尾），并重新检查交付文件。NPZ 输入是米制 Z-up `vertices[N,3]`、三角 `faces[M,3]`；输入路径和全新输出目录必须是本机绝对路径，输出目录不能位于服务 data 或临时任务目录内。

结果逐项记录：

- `DEPLOYED_GENERATED`：真实请求成功，交付文件重新加载检查通过。
- `DEPLOYED_OOM`：实际模型请求的原始异常明确是 CUDA 显存不足；仅按本次维护者约定接受其部署，任务状态和推理失败仍保留。
- `FAILED`：其他异常、超时、缺依赖、缺授权或不完整产物。
- `NOT_RUN`：未执行的路径，不能由工具枚举或其他服务成功替代。

生成 GLB/NPZ/Blend 不代表已交付可运行的 USD 场景。后续材质、碰撞、装配、USD 依赖闭包及物理验收沿用三个制作 Skill 与[资产场景交接](../../../../../.agents/skills/geochora-task-harness/references/asset-scene-integration.md)，TaskEnv 运行准入与任务成功维持原有合同。
