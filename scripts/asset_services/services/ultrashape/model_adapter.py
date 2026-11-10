# 作用：在 Windows 运行时加载官方 UltraShape，适配现有 CUDA 稀疏 MC 与注意力入口。
# 重要接口：load_pipeline() 返回严格加载的官方管线；sparse_mc() 调用原生稀疏 MC。
import importlib
import json
import os
from pathlib import Path
import sys
import types

from common.service_config import BACKENDS

BACKEND = BACKENDS / 'UltraShape-1.0'
os.environ['CA_USE_SAGEATTN'] = '0'
os.environ['USE_SAGEATTN'] = '0'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HOME'] = str(BACKEND / 'cache')
if not os.environ.get('CUDA_PATH'):
    os.environ['CUDA_PATH'] = str(Path(sys.executable).resolve().parents[1] / 'Library')
sys.path.insert(0, str(BACKEND))

import torch
import torch.nn.functional as F
import cumesh._cubvh as native_cubvh
from omegaconf import OmegaConf
import diffusers.utils.import_utils as diffusion_imports

diffusion_imports._xformers_available = False


def sparse_mc(coords, corners, iso):
    """将官方稀疏 MC 输入传入已安装的同名原生 CUDA 算子。"""
    return native_cubvh.sparse_marching_cubes(coords.to(torch.int32).contiguous(),
        corners.float().contiguous(), float(iso), False)


def flash_varlen(q, k, v, cu_q, cu_k, max_q, max_k, dropout_p=0.0, softmax_scale=None, causal=False):
    """逐序列执行精确掩码语义的 SDPA，避免依赖 Linux flash_attn 扩展。"""
    outputs = []
    for index in range(len(cu_q) - 1):
        qi = q[int(cu_q[index]):int(cu_q[index + 1])].transpose(0, 1).unsqueeze(0)
        ki = k[int(cu_k[index]):int(cu_k[index + 1])].transpose(0, 1).unsqueeze(0)
        vi = v[int(cu_k[index]):int(cu_k[index + 1])].transpose(0, 1).unsqueeze(0)
        outputs.append(F.scaled_dot_product_attention(qi, ki, vi, dropout_p=dropout_p,
            is_causal=causal, scale=softmax_scale).squeeze(0).transpose(0, 1))
    return torch.cat(outputs, dim=0)


def sequential_cfg_forward(model, x, t, contexts, **kwargs):
    """分开计算 CFG 的独立 batch，保持注意力范围和引导公式。"""
    if x.shape[0] == 1:
        return model._ultrashape_original_forward(x, t, contexts, **kwargs)
    outputs = []
    for index in range(x.shape[0]):
        context = {key: value[index:index + 1] for key, value in contexts.items()}
        options = {key: (value[index:index + 1] if isinstance(value, torch.Tensor)
                    and value.ndim and value.shape[0] == x.shape[0] else value)
                   for key, value in kwargs.items()}
        outputs.append(model._ultrashape_original_forward(x[index:index + 1], t[index:index + 1], context, **options))
    return torch.cat(outputs)


for name, folder in [('ultrashape', 'ultrashape'), ('ultrashape.models', 'ultrashape/models'),
                     ('ultrashape.models.autoencoders', 'ultrashape/models/autoencoders')]:
    package = types.ModuleType(name)
    package.__path__ = [str(BACKEND / folder)]
    sys.modules[name] = package
cubvh = types.ModuleType('cubvh')
cubvh.sparse_marching_cubes = sparse_mc
sys.modules['cubvh'] = cubvh
flash = types.ModuleType('flash_attn')
flash.__spec__ = importlib.machinery.ModuleSpec('flash_attn', loader=None)
flash.flash_attn_varlen_func = flash_varlen
sys.modules['flash_attn'] = flash
from ultrashape.models.autoencoders.model import ShapeVAE
from ultrashape.models.autoencoders.attention_blocks import FourierEmbedder
from ultrashape.models.autoencoders.surface_extractors import SurfaceExtractors
sys.modules['ultrashape.models.autoencoders'].ShapeVAE = ShapeVAE
sys.modules['ultrashape.models.autoencoders'].SurfaceExtractors = SurfaceExtractors
from ultrashape.pipelines import UltraShapePipeline
from ultrashape.utils.misc import instantiate_from_config


def load_pipeline():
    """严格加载三组官方参数并启用逐阶段显存卸载。"""
    config = OmegaConf.load(BACKEND / 'configs' / 'infer_dit_refine.yaml')
    cfg = config.model.params
    image_cfg = cfg.conditioner_config.params.main_image_encoder.kwargs
    image_cfg.config = json.loads((BACKEND / 'checkpoints' / 'dinov2_config.json').read_text())
    weights = torch.load(BACKEND / 'checkpoints' / 'ultrashape_v1.pt', map_location='cpu', weights_only=True, mmap=True)
    components = {}
    for name, model_cfg in [('vae', cfg.vae_config), ('dit', cfg.dit_cfg), ('conditioner', cfg.conditioner_config)]:
        with torch.device('meta'):
            model = instantiate_from_config(OmegaConf.to_container(model_cfg, resolve=True))
        model.load_state_dict(weights[name], strict=True, assign=True)
        for module in model.modules():
            if isinstance(module, FourierEmbedder) and module.frequencies.is_meta:
                module.frequencies = FourierEmbedder(num_freqs=module.num_freqs,
                    include_pi=bool(cfg.vae_config.params.include_pi)).frequencies
        missing = [key for key, tensor in list(model.named_parameters()) + list(model.named_buffers()) if tensor.is_meta]
        if missing:
            raise RuntimeError(f'未初始化参数：{name}: {missing}')
        components[name] = model.eval().requires_grad_(False).to(dtype=torch.float16)
    components['dit']._ultrashape_original_forward = components['dit'].forward
    components['dit'].forward = types.MethodType(sequential_cfg_forward, components['dit'])
    pipeline = UltraShapePipeline(vae=components['vae'], model=components['dit'], conditioner=components['conditioner'],
        scheduler=instantiate_from_config(cfg.scheduler_cfg), image_processor=instantiate_from_config(cfg.image_processor_cfg),
        device='cpu', dtype=torch.float16)
    pipeline.enable_model_cpu_offload()
    pipeline.device = torch.device('cuda')
    return pipeline
