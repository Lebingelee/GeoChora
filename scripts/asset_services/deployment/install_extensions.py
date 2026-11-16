# 作用：使用固定源码编译 CUDA 扩展；Windows 自动加载已安装的 C++ 工具链。
# 输入输出：当前 trellis2 解释器、CUDA Toolkit 和 prepare_sources.py 产物 -> 本机 wheel 与安装日志。
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import uuid

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.service_config import BACKENDS, DEPENDENCIES, TRELLIS_BACKEND
from deployment.prepare_sources import WINDOWS_PATCHES

MAX_JOBS = 2
EXTENSIONS = [BACKENDS / "linux-extensions" / name for name in
              ("CuMesh", "FlexGEMM", "nvdiffrast", "nvdiffrec", "utils3d")]
EXTENSIONS.append(TRELLIS_BACKEND / "o-voxel")


def main():
    """在当前 GPU 架构上编译并安装服务依赖，保留完整构建日志。

    Returns:
        None: 写入 wheels/ 和 evidence/build-*.log；任一编译失败即停止并报告日志位置。
    """
    environment = dict(os.environ)
    if os.name == "nt":
        from setuptools._distutils._msvccompiler import _get_vc_env
        environment.update(_get_vc_env("x64"))
        environment["CL"] = "/std:c++17 /EHsc /Zc:__cplusplus " + environment.get("CL", "")
        environment["NVCC_PREPEND_FLAGS"] = "-allow-unsupported-compiler " + environment.get("NVCC_PREPEND_FLAGS", "")
        environment["DISTUTILS_USE_SDK"] = "1"
        environment["MSSdk"] = "1"
        environment["VSLANG"] = "1033"
    capability = torch.cuda.get_device_capability()
    environment["TORCH_CUDA_ARCH_LIST"] = f"{capability[0]}.{capability[1]}"
    environment["MAX_JOBS"] = str(MAX_JOBS)
    environment["CPLUS_INCLUDE_PATH"] = str(BACKENDS / "linux-extensions/CuMesh/third_party/cubvh/third_party/eigen")
    environment["PYTHONIOENCODING"] = "utf-8"
    wheels = DEPENDENCIES / "wheels"
    logs = DEPENDENCIES / "evidence"
    wheels.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    receipt_path = logs / "extension-builds.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else {}
    packages = {"CuMesh": "cumesh", "FlexGEMM": "flex_gemm", "nvdiffrast": "nvdiffrast",
                "nvdiffrec": "nvdiffrec_render", "utils3d": "utils3d", "o-voxel": "o_voxel"}
    for source in EXTENSIONS:
        context = {"source_revision": subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip(),
                   "torch": torch.__version__, "cuda": torch.version.cuda,
                   "architecture": environment["TORCH_CUDA_ARCH_LIST"], "python": sys.implementation.cache_tag}
        if os.name == "nt" and source.name == "FlexGEMM":
            context["portability_source_sha256"] = hashlib.sha256(
                (source / "flex_gemm/kernels/cuda/spconv/sparse_neighbor_map.cu").read_bytes()).hexdigest()
        if os.name == "nt" and source.name == "o-voxel":
            context["portability_sources_sha256"] = {
                name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                for name in (str(Path(path).relative_to("o-voxel")).replace("\\", "/")
                             for path in WINDOWS_PATCHES["TRELLIS.2"])}
        previous = receipt.get(source.name, {})
        if previous.get("context") == context and previous.get("wheels") and all(
                (wheels / name).is_file() and hashlib.sha256((wheels / name).read_bytes()).hexdigest() == digest
                for name, digest in previous["wheels"].items()):
            print(f"复用已核对的 {source.name} wheel", flush=True)
            continue
        log_path = logs / f"build-{source.name}-{uuid.uuid4().hex[:8]}.log"
        print(f"开始构建 {source.name}；日志：{log_path}", flush=True)
        with log_path.open("w", encoding="utf-8") as log:
            result = subprocess.run([sys.executable, "-m", "pip", "--isolated", "wheel", str(source),
                                     "--no-build-isolation", "--no-deps", "--wheel-dir", str(wheels)],
                                    env=environment, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"{source.name} 编译失败；完整日志：{log_path}")
        artifacts = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in wheels.glob(packages[source.name] + "-*.whl")}
        if not artifacts:
            raise RuntimeError(f"{source.name} 未产生预期 wheel")
        receipt[source.name] = {"context": context, "wheels": artifacts,
                                "compiler_flags": environment.get("CL", "")}
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(f"已构建 {source.name}", flush=True)
    subprocess.run([sys.executable, "-m", "pip", "--isolated", "install", "--no-deps",
                    *map(str, sorted(wheels.glob("*.whl")))], check=True)
    (logs / "cuda-build.json").write_text(json.dumps({"torch": torch.__version__, "cuda": torch.version.cuda,
        "compute_capability": list(capability), "architecture": environment["TORCH_CUDA_ARCH_LIST"]}, indent=2) + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
