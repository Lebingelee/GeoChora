"""资产 MCP 初始化步骤；本模块只提供部署说明，导入时不执行安装。

硬件/软件：NVIDIA CUDA GPU、Conda/Python 3.11、Git、CUDA Toolkit 12.8；
Windows 还需 VS 2022 C++ Build Tools 和 Windows SDK。Blender 用于 GLB→Blend。
编排另需 PATH 中的 Codex CLI 和接收方自己的登录（codex login）。
模型和环境需数十 GB 磁盘；不设置显存容量门槛、不追加显存优化。
DINOv3 和 RMBG-2.0 需先用自己的 Hugging Face 账号取得模型访问权限。
所有命令从本仓库根目录在 PowerShell 中逐步执行，非零退出时先处理错误。

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
conda create --prefix "$PWD/workspace/asset-services/runtime/trellis2" --override-channels -c https://conda.anaconda.org/conda-forge --repodata-fn current_repodata.json python=3.11 pip -y
$PY = "$PWD/workspace/asset-services/runtime/trellis2/python.exe"
& $PY -m pip --isolated install torch==2.8.0 torchvision==0.23.0 xformers==0.0.32.post2 --index-url https://download.pytorch.org/whl/cu128
& $PY -m pip --isolated install -r scripts/asset_services/deployment/requirements-trellis.txt --index-url https://pypi.org/simple
& $PY scripts/asset_services/deployment/prepare_sources.py
& "$PWD/workspace/asset-services/runtime/trellis2/Scripts/hf.exe" auth login
& $PY scripts/asset_services/deployment/prepare_models.py
& $PY scripts/asset_services/deployment/install_extensions.py

conda create --prefix "$PWD/workspace/asset-services/runtime/ultrashape" --override-channels -c https://conda.anaconda.org/conda-forge --repodata-fn current_repodata.json python=3.11 pip -y
$UPY = "$PWD/workspace/asset-services/runtime/ultrashape/python.exe"
& $UPY -m pip --isolated install torch==2.8.0 torchvision==0.23.0 numpy==1.26.4 --index-url https://download.pytorch.org/whl/cu128
& $UPY -m pip --isolated install -r scripts/asset_services/deployment/requirements-ultrashape.txt --index-url https://pypi.org/simple
& $UPY -m pip --isolated install --no-deps (Get-Item "$PWD/workspace/asset-services/wheels/cumesh-*.whl").FullName

& $PY scripts/asset_services/deployment/register_mcp.py
$env:PYTHONPATH = "$PWD/scripts"
& $PY -m orchestrator.server --register
& $PY scripts/asset_services/scheduler/task_runner.py

最后一条在独立终端保持运行；同一个数据库只启动一个执行端，停止前等待在途任务结束。
编排 daemon 由 MCP 首次请求自动启动。客户端重连后加载新配置。
源码、权重、环境和产物均由本机在忽略的 workspace/ 下独立准备，不读取原服务器。
BLENDER_PATH 可指定 Blender 可执行文件；缺省查找 PATH 和 Windows 标准安装目录。
以上为已执行的 Windows 部署路线；Linux 的环境初始化未在本轮验证。
"""
