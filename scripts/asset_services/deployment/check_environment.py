# 作用：只读检查资产 MCP 的本机部署条件，不加载模型、不以显存容量阻止部署。
# 输入输出：下列路径和当前主机 -> workspace/asset-services/evidence/environment.json。
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.service_config import ROOT, DEPENDENCIES, BLENDER

REPO = ROOT.parents[1]
DEPLOYMENT = DEPENDENCIES
REPORT = DEPLOYMENT / "evidence" / "environment.json"


def main():
    """记录硬件、工具链和独立解释器的实际状态。

    Returns:
        None: 保存 JSON 清单；缺失项照实记录，不据此宣称 MCP 部署通过。
    """
    tools = {name: shutil.which(name) for name in ("git", "conda", "nvcc", "cl", "codex")}
    cuda = Path(os.environ.get("CUDA_PATH", ""))
    if cuda.is_dir() and (cuda / "bin" / "nvcc.exe").is_file():
        tools["nvcc"] = str(cuda / "bin" / "nvcc.exe")
    blender = str(BLENDER) if BLENDER.is_file() else shutil.which("blender")
    tools["blender"] = blender
    vswhere = Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft Visual Studio/Installer/vswhere.exe"
    if vswhere.is_file():
        result = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires",
                                 "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                                 "-property", "installationPath"], capture_output=True, text=True, timeout=30)
        tools["visual_studio_cpp"] = result.stdout.strip() if result.returncode == 0 else None
    gpu = {"available": False}
    if shutil.which("nvidia-smi"):
        result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version,compute_cap",
                                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=30)
        gpu = {"available": result.returncode == 0, "returncode": result.returncode,
               "inventory": result.stdout.strip(), "error": result.stderr.strip()}
    interpreters = {}
    for name in ("trellis2", "ultrashape"):
        root = DEPLOYMENT / "runtime" / name
        executable = root / ("python.exe" if os.name == "nt" else "bin/python")
        interpreters[name] = {"path": str(executable), "exists": executable.is_file()}
    free = shutil.disk_usage(REPO).free
    report = {"schema_version": "asset-mcp-environment-v1", "platform": platform.platform(),
              "python": sys.version, "repo": str(REPO), "gpu": gpu, "tools": tools,
              "runtime": interpreters, "free_disk_gib": round(free / 1024**3, 2),
              "current_python_has_mcp": importlib.util.find_spec("mcp") is not None,
              "deployment_verified": False,
              "trellis_oom_policy": "Real CUDA out-of-memory during model load/inference is accepted for deployment only."}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
