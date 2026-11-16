# 作用：集中配置本机解释器、模型与 Blender 路径；导入时不加载模型。
# 输入输出：configure_runtime() 为计算子进程设置离线缓存和 CUDA 依赖。
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = Path(os.environ.get('ASSET_SERVICES_HOME', ROOT.parents[1] / 'workspace/asset-services')).resolve()
BACKENDS = DEPENDENCIES / 'third_party'
TRELLIS_BACKEND = BACKENDS / 'TRELLIS.2'
TRELLIS_PYTHON = DEPENDENCIES / ('runtime/trellis2/python.exe' if os.name == 'nt' else 'runtime/trellis2/bin/python')
ULTRASHAPE_PYTHON = DEPENDENCIES / ('runtime/ultrashape/python.exe' if os.name == 'nt' else 'runtime/ultrashape/bin/python')
_blenders = sorted(Path('C:/Program Files/Blender Foundation').glob('Blender */blender.exe')) if os.name == 'nt' else []
BLENDER = Path(os.environ.get('BLENDER_PATH') or shutil.which('blender') or
               (str(_blenders[-1]) if _blenders else 'blender'))
if BLENDER.is_dir():
    BLENDER = BLENDER / ('blender.exe' if os.name == 'nt' else 'blender')


def configure_runtime() -> None:
    """在加载计算库之前配置本地依赖、缓存及离线推理环境。"""
    cache = DEPENDENCIES / 'data/cache'
    os.environ.update({
        'PYTHONNOUSERSITE': '1', 'PYTHONIOENCODING': 'utf-8',
        'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
        'HF_HOME': str(cache / 'huggingface'), 'TORCH_HOME': str(cache / 'torch'),
        'TORCH_EXTENSIONS_DIR': str(cache / 'torch_extensions'),
        'TRITON_CACHE_DIR': str(cache / 'triton'),
        'FLEX_GEMM_AUTOTUNE_CACHE_PATH': str(cache / 'flex_gemm.json'),
        'ATTN_BACKEND': 'xformers', 'SPARSE_ATTN_BACKEND': 'xformers',
        'TORCHDYNAMO_DISABLE': '1', 'OPENCV_IO_ENABLE_OPENEXR': '1',
        'PYTORCH_CUDA_ALLOC_CONF': 'garbage_collection_threshold:0.65',
    })
    sys.path.insert(0, str(TRELLIS_BACKEND))
