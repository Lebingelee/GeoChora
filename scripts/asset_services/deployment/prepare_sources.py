# 作用：从公开仓库获取固定版本的三维生成源码与 CUDA 扩展，不读取开发者机器目录。
# 输入输出：下列公开 URL/提交号 -> workspace/asset-services/third_party 及来源清单。
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.service_config import BACKENDS

DESTINATION = BACKENDS
SOURCES = {
    "TRELLIS.2": ("https://github.com/microsoft/TRELLIS.2.git", "75fbf0183001ed9876c8dbb35de6b68552ee08bd"),
    "UltraShape-1.0": ("https://github.com/PKU-YuanGroup/UltraShape-1.0.git", "5e8dcef05df101ab00ab6cd5fdd0ed0c74fbca66"),
    "linux-extensions/CuMesh": ("https://github.com/JeffreyXiang/CuMesh.git", "12289e1062f0603f2f0d0771b02e1395d247f26f"),
    "linux-extensions/FlexGEMM": ("https://github.com/JeffreyXiang/FlexGEMM.git", "6dd94a859c26ee8246888502eada3dd8ad85532e"),
    "linux-extensions/nvdiffrast": ("https://github.com/NVlabs/nvdiffrast.git", "253ac4fcea7de5f396371124af597e6cc957bfae"),
    "linux-extensions/nvdiffrec": ("https://github.com/JeffreyXiang/nvdiffrec.git", "b296927cc7fd01c2ac1087c8065c4d7248f72da4"),
    "linux-extensions/utils3d": ("https://github.com/EasternJournalist/utils3d.git", "9a4eb15e4021b67b12c460c7057d642626897ec8"),
}
WINDOWS_PATCHES = {
    "linux-extensions/FlexGEMM": {
        "flex_gemm/kernels/cuda/spconv/sparse_neighbor_map.cu": [
            ("expanded_keys.data_ptr<T>()", "expanded_keys.template data_ptr<T>()", 1)],
    },
    "TRELLIS.2": {
        "o-voxel/src/convert/flexible_dual_grid.cpp": [("1e-6d", "1e-6", 1), ("0.0d", "0.0", 1)],
        "o-voxel/src/io/filter_neighbor.cpp": [
            ("torch::zeros({N, C},", "torch::zeros({static_cast<int64_t>(N), static_cast<int64_t>(C)},", 2)],
        "o-voxel/src/io/filter_parent.cpp": [
            ("torch::zeros({N_leaf, C},", "torch::zeros({static_cast<int64_t>(N_leaf), static_cast<int64_t>(C)},", 2)],
        "o-voxel/src/io/svo.cpp": [
            ("{svo.size()}", "{static_cast<int64_t>(svo.size())}", 1),
            ("{codes.size()}", "{static_cast<int64_t>(codes.size())}", 1)],
    },
}


def main():
    """获取固定源码并保留提交、子模块和关键文件摘要。

    Returns:
        None: 写入 source-receipt.json；已有不同版本目录直接报错，保留原文件。
    """
    DESTINATION.mkdir(parents=True, exist_ok=True)
    receipt = {"schema_version": "asset-mcp-sources-v1", "sources": {}}
    for name, (url, revision) in SOURCES.items():
        target = DESTINATION / name
        if not target.exists():
            target.mkdir(parents=True)
            subprocess.run(["git", "init", str(target)], check=True)
            subprocess.run(["git", "-C", str(target), "remote", "add", "origin", url], check=True)
            subprocess.run(["git", "-C", str(target), "fetch", "--depth", "1", "origin", revision], check=True)
            subprocess.run(["git", "-C", str(target), "checkout", "--detach", "FETCH_HEAD"], check=True)
        actual = subprocess.check_output(["git", "-C", str(target), "rev-parse", "HEAD"], text=True).strip()
        if actual != revision:
            raise ValueError(f"{name} 已有版本 {actual} 与固定版本 {revision} 不同")
        dirty = subprocess.check_output(["git", "-C", str(target), "status", "--porcelain", "--untracked-files=no"], text=True)
        patch_records, expected_files = [], {}
        if os.name == "nt" and name in WINDOWS_PATCHES:
            for relative, replacements in WINDOWS_PATCHES[name].items():
                original = subprocess.check_output(["git", "-C", str(target), "show", "HEAD:" + relative]).decode("utf-8")
                expected = original
                for before, after, count in replacements:
                    if original.count(before) != count:
                        raise RuntimeError(f"固定 {name} 源码的编译兼容位置已变化")
                    expected = expected.replace(before, after)
                current = (target / relative).read_text(encoding="utf-8")
                if current not in (original, expected):
                    raise ValueError(f"{name} 源文件存在未识别改动")
                expected_files[relative] = expected
                patch_records.append({"path": relative, "reason": "NVCC/MSVC syntax portability; no algorithm or memory-policy change",
                    "original_sha256": hashlib.sha256(original.encode()).hexdigest(),
                    "patched_sha256": hashlib.sha256(expected.encode()).hexdigest()})
            changed = subprocess.check_output(["git", "-C", str(target), "diff", "--name-only"], text=True).splitlines()
            if dirty and (not set(changed).issubset(expected_files) or any(
                    (target / path).read_text(encoding="utf-8") != expected_files[path] for path in changed)):
                raise ValueError(f"{name} 存在迁移补丁之外的改动")
            for relative, expected in expected_files.items():
                if (target / relative).read_bytes() != expected.encode("utf-8"):
                    (target / relative).write_bytes(expected.encode("utf-8"))
        elif dirty:
            raise ValueError(f"{name} 存在本地改动，停止以保留原文件")
        subprocess.run(["git", "-C", str(target), "submodule", "update", "--init", "--recursive"], check=True)
        submodules = subprocess.check_output(["git", "-C", str(target), "submodule", "status", "--recursive"], text=True)
        hashes = {str(path.relative_to(target)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                  for pattern in ("LICENSE*", "README*") for path in target.glob(pattern) if path.is_file()}
        receipt["sources"][name] = {"url": url, "revision": actual,
                                    "submodules": submodules.splitlines(), "file_sha256": hashes}
        if patch_records:
            receipt["sources"][name]["portability_patches"] = patch_records
        if name == "linux-extensions/FlexGEMM":
            cache = BACKENDS.parent / "data/cache/flex_gemm.json"
            cache.parent.mkdir(parents=True, exist_ok=True)
            if not cache.exists():
                shutil.copyfile(target / "autotune_cache.json", cache)
            receipt["sources"][name]["default_autotune_sha256"] = hashlib.sha256(
                (target / "autotune_cache.json").read_bytes()).hexdigest()
        (DESTINATION.parent / "source-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已固定 {name}: {actual}", flush=True)


if __name__ == "__main__":
    main()
