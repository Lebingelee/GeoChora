# 作用：按参考图细化一个粗网格，并恢复输入的米制 Z-up 坐标。
# 输入输出：NPZ、图片及采样参数 argv -> refined.npz、result.json。
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.service_config import configure_runtime
from common.worker_io import load_mesh, save_image, write_result


def main():
    """加载 UltraShape，采样粗网格锚点并输出一个细化网格。

    Returns:
        None: 输出 refined.npz 与包含坐标变换的交付记录。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--mesh_path', required=True)
    parser.add_argument('--image_path', required=True)
    parser.add_argument('--num_latents', type=int, default=4096)
    parser.add_argument('--steps', type=int, default=8)
    parser.add_argument('--resolution', type=int, default=512)
    parser.add_argument('--chunk_size', type=int, default=8000)
    parser.add_argument('--guidance', type=float, default=5.0)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    vertices, faces = load_mesh(args.mesh_path)
    image = save_image(args.image_path)
    configure_runtime()
    from services.ultrashape.model_adapter import load_pipeline
    import numpy as np
    import torch
    import trimesh
    from ultrashape.surface_loaders import load_surface_sharpegde
    from ultrashape.utils import voxelize_from_point

    started = time.perf_counter()
    np.savez_compressed('input_mesh.npz', vertices=vertices, faces=faces)
    center = (vertices.min(axis=0) + vertices.max(axis=0)) / 2
    extent = float(np.ptp(vertices, axis=0).max())
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    original_rng = np.random.default_rng
    np.random.default_rng = lambda seed=None: original_rng(args.seed if seed is None else seed)
    try:
        # 官方加载器将最长边归一化到 [-0.99, 0.99]，输出必须使用其逆变换。
        surface, _ = load_surface_sharpegde([mesh], num_points=204800,
                                          num_sharp_points=204800, normalize_scale=.99)
    finally:
        np.random.default_rng = original_rng
    _, coords = voxelize_from_point(surface[:, :, :3].to(device='cuda', dtype=torch.float16),
                                    args.num_latents, resolution=128)
    print('加载 UltraShape', flush=True)
    pipeline = load_pipeline()
    with torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16):
        meshes, _ = pipeline(
            image=image, voxel_cond=coords, generator=torch.Generator('cuda').manual_seed(args.seed),
            guidance_scale=args.guidance, box_v=1.0, mc_level=0.0,
            octree_resolution=args.resolution, num_inference_steps=args.steps,
            num_chunks=args.chunk_size)
    refined = meshes[0]
    if refined is None or not len(refined.faces):
        raise RuntimeError('UltraShape 未返回有效网格')
    restored = (refined.vertices * (extent / 1.98) + center).astype(np.float32)
    triangles = restored[refined.faces].astype(np.float64)
    valid = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0],
                                    triangles[:, 2] - triangles[:, 0]), axis=1) > 0
    np.savez_compressed('refined.npz', vertices=restored, faces=refined.faces[valid])
    output_vertices, output_faces = load_mesh('refined.npz')
    write_result({'mesh': 'refined.npz', 'input_mesh': 'input_mesh.npz', 'reference_image': 'input.png'}, {
        'parameters': vars(args), 'seconds': time.perf_counter() - started,
        'input_center': center.tolist(), 'normalization_scale': 1.98 / extent,
        'vertices': len(output_vertices), 'faces': len(output_faces),
        'removed_degenerate_faces': int((~valid).sum()),
        'bounds': [output_vertices.min(axis=0).tolist(), output_vertices.max(axis=0).tolist()],
        'units': 'meter', 'up_axis': 'Z',
    })


if __name__ == '__main__':
    main()
