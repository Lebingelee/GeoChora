# 作用：在现有 Windows TRELLIS.2 运行时装载官方独立贴图网络及必要兼容层。
# 重要接口：load_pipeline() 返回指定分辨率的官方贴图管线。
import functools
import importlib.util
import inspect
import json
import os
import sys
import textwrap
import types

from common.service_config import BACKENDS, TRELLIS_BACKEND as BACKEND
CHECKPOINTS = BACKEND / 'models/hub'
DINO = CHECKPOINTS / 'dinov3-vitl16-pretrain-lvd1689m'
OFFICIAL = BACKENDS / 'trellis-texturing-official'

os.environ['ATTN_BACKEND'] = 'xformers'
os.environ['SPARSE_ATTN_BACKEND'] = 'xformers'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['TORCHDYNAMO_DISABLE'] = '1'
sys.path.insert(0, str(BACKEND))

import torch
from safetensors.torch import load_file
from common.trellis_compat import patch_sparse_shape, patch_trellis_windows_runtime

patch_trellis_windows_runtime()
patch_sparse_shape()
import xformers.ops as xops
xops.memory_efficient_attention = functools.partial(xops.memory_efficient_attention, op=(xops.fmha.cutlass.FwOp, None))
from trellis2 import models
from trellis2.pipelines import samplers
from trellis2.pipelines.rembg import BiRefNet
from trellis2.modules.image_feature_extractor import DinoV3FeatureExtractor


def clear_convolution_cache(tensor):
    """释放卷积缓存，保留贴图解码需要的逆细分索引。"""
    for scale in list(tensor._spatial_cache):
        cache = tensor._spatial_cache[scale]
        tensor._spatial_cache[scale] = {key: value for key, value in cache.items()
                                       if key.startswith('channel2spatial_') or key == 'shape'}


def load_pipeline(resolution):
    """严格加载指定贴图分辨率所需的官方网络。"""
    spec = importlib.util.spec_from_file_location('trellis2.pipelines.asset_texturing', OFFICIAL / 'trellis2_texturing.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = json.loads((OFFICIAL / 'texturing_pipeline.json').read_text(encoding='utf-8'))['args']
    names = ['shape_slat_encoder', 'tex_slat_decoder', f'tex_slat_flow_model_{resolution}']
    loaded = {}
    for key in names:
        stem = CHECKPOINTS / config['models'][key].split('/')[-1]
        options = json.loads(stem.with_suffix('.json').read_text(encoding='utf-8'))
        with torch.device('meta'):
            model = getattr(models, options['name'])(**options['args'])
        state = load_file(str(stem.with_suffix('.safetensors')))
        expected = model.state_dict()
        model.load_state_dict({name: value.to(dtype=expected[name].dtype) for name, value in state.items()},
            strict=True, assign=True)
        for block in model.modules():
            if hasattr(block, 'freqs') and block.freqs.is_meta:
                phase = torch.arange(block.freq_dim, dtype=torch.float32) / block.freq_dim
                block.freqs = block.rope_freq[0] / (block.rope_freq[1] ** phase)
        if any(parameter.is_meta for parameter in model.parameters()):
            raise RuntimeError(f'{key} 存在未初始化权重')
        if key == 'tex_slat_decoder':
            model.low_vram = True
            source = textwrap.dedent(inspect.getsource(type(model).forward))
            if source.count('h._spatial_cache.clear()') > 1:
                raise RuntimeError('TRELLIS 解码器缓存实现已变化')
            if 'h._spatial_cache.clear()' in source:
                namespace = dict(sys.modules[type(model).__module__].__dict__)
                namespace['clear_convolution_cache'] = clear_convolution_cache
                exec(compile(source.replace('h._spatial_cache.clear()', 'clear_convolution_cache(h)'),
                    '<texture_decoder_cache_compatibility>', 'exec'), namespace)
                model.forward = types.MethodType(namespace['forward'], model)
        loaded[key] = model.eval()
    pipeline = module.Trellis2TexturingPipeline(models=loaded,
        tex_slat_sampler=getattr(samplers, config['tex_slat_sampler']['name'])(**config['tex_slat_sampler']['args']),
        tex_slat_sampler_params=config['tex_slat_sampler']['params'],
        shape_slat_normalization=config['shape_slat_normalization'], tex_slat_normalization=config['tex_slat_normalization'],
        image_cond_model=DinoV3FeatureExtractor(str(DINO)), rembg_model=BiRefNet(json.loads(
            (BACKEND / 'models/pipeline/pipeline.json').read_text(encoding='utf-8')
        )['args']['rembg_model']['args']['model_name']), low_vram=True)
    pipeline.cuda()
    official_postprocess = pipeline.postprocess_mesh

    def postprocess_float(mesh, pbr_voxel, resolution=1024, texture_size=1024):
        """将 Windows 解码器的半精度输出对齐官方 float32 烘焙缓冲。"""
        return official_postprocess(mesh, pbr_voxel.replace(pbr_voxel.feats.float()), resolution, texture_size)

    pipeline.postprocess_mesh = postprocess_float
    return pipeline
