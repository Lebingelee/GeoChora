# 作用：在独立进程内将一张参考图生成为带 PBR 材质的 GLB。
# 输入输出：图片及生成参数 argv -> asset.glb、processed.png、result.json。
import argparse
import gc
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.service_config import TRELLIS_BACKEND, configure_runtime
from common.worker_io import save_image, write_result


def main():
    """执行一次 TRELLIS.2 推理并重读 GLB 验证几何与 PBR。

    Returns:
        None: 写入任务目录，错误向上传播并使子进程非零退出。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--image_path', required=True)
    parser.add_argument('--resolution', type=int, choices=[512, 1024], default=1024)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--texture_size', type=int, default=2048)
    parser.add_argument('--max_faces', type=int, default=200000)
    args = parser.parse_args()
    image = save_image(args.image_path)
    configure_runtime()
    import numpy as np
    import torch
    import trimesh
    import xformers.ops
    from common.trellis_compat import patch_sparse_shape, patch_trellis_windows_runtime
    patch_trellis_windows_runtime()
    patch_sparse_shape()
    xformers.ops.fmha.dispatch._set_use_fa3(False)
    from trellis2.pipelines import Trellis2ImageTo3DPipeline
    import o_voxel

    started = time.perf_counter()
    print('加载 TRELLIS.2', flush=True)
    pipeline = Trellis2ImageTo3DPipeline.from_pretrained(str(TRELLIS_BACKEND / 'models/pipeline'))
    pipeline.low_vram = True
    pipeline.cuda()
    image = pipeline.preprocess_image(image)
    image.save('processed.png')
    with torch.inference_mode():
        mesh = pipeline.run(image, seed=args.seed, preprocess_image=False,
                            pipeline_type='512' if args.resolution == 512 else '1024_cascade')[0]
        mesh.attrs = mesh.attrs.float()
        del pipeline
        gc.collect()
        torch.cuda.empty_cache()
        print('导出 GLB', flush=True)
        glb = o_voxel.postprocess.to_glb(
            vertices=mesh.vertices, faces=mesh.faces, attr_volume=mesh.attrs,
            coords=mesh.coords, attr_layout=mesh.layout,
            grid_size=args.resolution, aabb=[[-0.5]*3, [0.5]*3],
            decimation_target=args.max_faces, texture_size=args.texture_size,
            remesh=True, remesh_band=1, remesh_project=0, use_tqdm=True)
        glb.export('asset.glb')
        torch.cuda.synchronize()
    scene = trimesh.load('asset.glb', force='scene')
    geometries = list(scene.geometry.values())
    if not geometries or not all(np.isfinite(g.vertices).all() and len(g.faces) for g in geometries):
        raise RuntimeError('导出网格为空或包含非有限顶点')
    for geometry in geometries:
        material = getattr(geometry.visual, 'material', None)
        if (getattr(material, 'baseColorTexture', None) is None
                or getattr(material, 'metallicRoughnessTexture', None) is None):
            raise RuntimeError('导出 GLB 缺少 PBR 贴图')
    write_result({'asset': 'asset.glb', 'processed_image': 'processed.png'}, {
        'parameters': vars(args), 'seconds': time.perf_counter() - started,
        'vertices': sum(len(g.vertices) for g in geometries),
        'faces': sum(len(g.faces) for g in geometries),
        'bounds': scene.bounds.tolist(), 'glb_up_axis': 'Y',
        'units': 'normalized; scale to desired physical dimensions before assembly',
        'peak_cuda_gb': torch.cuda.max_memory_allocated() / 1024**3,
    })


if __name__ == '__main__':
    main()
