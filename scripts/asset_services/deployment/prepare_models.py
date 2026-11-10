# 作用：从固定公开模型版本准备本地权重和路径配置，不使用任何远程开发环境文件。
# 输入输出：Hugging Face 标准登录凭据 -> workspace/asset-services 下的模型及下载收据。
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.service_config import BACKENDS, DEPENDENCIES, TRELLIS_BACKEND

os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
os.environ.setdefault("HF_XET_CACHE", str(DEPENDENCIES / "data/cache/xet"))
from huggingface_hub import snapshot_download

MODELS = {
    "microsoft/TRELLIS.2-4B": ("af44b45f2e35a493886929c6d786e563ec68364d", ["pipeline.json", "texturing_pipeline.json", "ckpts/*", "README*", "LICENSE*"]),
    "microsoft/TRELLIS-image-large": ("25e0d31ffbebe4b5a97464dd851910efc3002d96", ["ckpts/ss_dec_conv3d_16l8_fp16.*", "README*", "LICENSE*"]),
    "infinith/UltraShape": ("5aeb21a7185d39f042d02b2695802f125a6f5159", ["ultrashape_v1.pt", "README*", "LICENSE*"]),
    "facebook/dinov2-large": ("47b73eefe95e8d44ec3623f8890bd894b6ea2d6c", ["config.json", "README*", "LICENSE*"]),
    "facebook/dinov3-vitl16-pretrain-lvd1689m": ("ea8dc2863c51be0a264bab82070e3e8836b02d51", ["*.json", "model.safetensors", "README*", "LICENSE*"]),
    "briaai/RMBG-2.0": ("5df4c9c76d8170882c34f6986e848ee07fd0ba43", ["*.json", "*.py", "model.safetensors", "README*", "LICENSE*"]),
}


def main():
    """下载精确版本，保留原始配置，再生成仅含本机路径的运行配置。

    Returns:
        None: 保存模型收据及服务需要的路径；授权和下载错误直接抛出。
    """
    locations = {}
    receipt_path = DEPENDENCIES / "model-receipt.json"
    receipt = {"schema_version": "asset-mcp-models-v1", "models": {}}
    for repository, (revision, patterns) in MODELS.items():
        target = DEPENDENCIES / "models" / repository.replace("/", "--") / revision
        snapshot_download(repository, revision=revision, local_dir=target,
                          allow_patterns=patterns, max_workers=2)
        locations[repository] = target
        # 权重以固定 HF revision 标识；小型配置额外保存摘要，避免混入另一个版本。
        configuration = {str(path.relative_to(target)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in target.rglob("*.json") if ".cache" not in path.parts}
        receipt["models"][repository] = {"revision": revision, "config_sha256": configuration}
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pipeline = json.loads((locations["microsoft/TRELLIS.2-4B"] / "pipeline.json").read_text(encoding="utf-8"))
    for name, value in pipeline["args"]["models"].items():
        if value.startswith("microsoft/TRELLIS-image-large/"):
            path = locations["microsoft/TRELLIS-image-large"] / value.removeprefix("microsoft/TRELLIS-image-large/")
        else:
            path = locations["microsoft/TRELLIS.2-4B"] / value
        pipeline["args"]["models"][name] = str(path)
    for name in ("image_cond_model", "rembg_model"):
        args = pipeline["args"][name]["args"]
        args["model_name"] = str(locations[args["model_name"]])
    directory = TRELLIS_BACKEND / "models/pipeline"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pipeline.json").write_text(json.dumps(pipeline, indent=2) + "\n", encoding="utf-8")
    hub = TRELLIS_BACKEND / "models/hub"
    hub.mkdir(parents=True, exist_ok=True)
    for stem in ("shape_enc_next_dc_f16c32_fp16", "tex_dec_next_dc_f16c32_fp16",
                 "slat_flow_imgshape2tex_dit_1_3B_512_bf16", "slat_flow_imgshape2tex_dit_1_3B_1024_bf16"):
        for extension in (".json", ".safetensors"):
            source = locations["microsoft/TRELLIS.2-4B"] / "ckpts" / (stem + extension)
            target = hub / source.name
            if not target.exists():
                try:
                    target.hardlink_to(source)
                except OSError:
                    shutil.copyfile(source, target)
    dino = hub / "dinov3-vitl16-pretrain-lvd1689m"
    dino.mkdir(exist_ok=True)
    for source in locations["facebook/dinov3-vitl16-pretrain-lvd1689m"].glob("*"):
        if source.is_file() and not (dino / source.name).exists():
            shutil.copyfile(source, dino / source.name)
    official = BACKENDS / "trellis-texturing-official"
    official.mkdir(exist_ok=True)
    for name in ("trellis2_texturing.py",):
        shutil.copyfile(TRELLIS_BACKEND / "trellis2/pipelines" / name, official / name)
    shutil.copyfile(locations["microsoft/TRELLIS.2-4B"] / "texturing_pipeline.json", official / "texturing_pipeline.json")
    shutil.copyfile(TRELLIS_BACKEND / "LICENSE", official / "LICENSE")
    ultra = BACKENDS / "UltraShape-1.0/checkpoints"
    ultra.mkdir(exist_ok=True)
    target = ultra / "ultrashape_v1.pt"
    if not target.exists():
        try:
            target.hardlink_to(locations["infinith/UltraShape"] / target.name)
        except OSError:
            shutil.copyfile(locations["infinith/UltraShape"] / target.name, target)
    shutil.copyfile(locations["facebook/dinov2-large"] / "config.json", ultra / "dinov2_config.json")
    print(f"已准备全部模型；收据：{receipt_path}")


if __name__ == "__main__":
    main()
