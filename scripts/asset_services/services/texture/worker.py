# 作用：调用 TRELLIS 官方独立贴图入口，将归一化结果恢复为米制资产。
# 输入输出：Z-up NPZ、参考图与官方参数 -> 内嵌 PBR 的 Y-up GLB、result.json。
import argparse
from pathlib import Path
import sys
import time

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.service_config import configure_runtime
from common.worker_io import load_mesh, save_image, write_result


def main():
    """运行官方贴图、恢复坐标尺度并交付 GLB。

    Returns:
        None: 写入 textured.glb 和供 CPU 打包阶段读取的结果清单。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--mesh_path', required=True)
    parser.add_argument('--image_path', required=True)
    parser.add_argument('--resolution', type=int, choices=[512, 1024], default=1024)
    parser.add_argument('--steps', type=int, default=12)
    parser.add_argument('--guidance_strength', type=float, default=1.0)
    parser.add_argument('--guidance_interval', type=float, nargs=2, default=[0.6, 0.9])
    parser.add_argument('--texture_size', type=int, default=2048)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--preprocess_image', action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    configure_runtime()
    from services.texture.model_adapter import load_pipeline

    vertices, faces = load_mesh(args.mesh_path)
    # 官方 run 接受 Y-up 并自行转为模型所用 Z-up；输出仍是归一化的 Y-up。
    vertices_yup = vertices[:, [0, 2, 1]].astype(np.float64)
    vertices_yup[:, 2] *= -1
    center = (vertices_yup.min(axis=0) + vertices_yup.max(axis=0)) / 2
    factor = 0.99999 / np.ptp(vertices_yup, axis=0).max()
    mesh = trimesh.Trimesh(vertices_yup, faces, process=False)
    image = save_image(args.image_path)
    started = time.perf_counter()
    pipeline = load_pipeline(args.resolution)
    output = pipeline.run(mesh, image, seed=args.seed, resolution=args.resolution,
        texture_size=args.texture_size, preprocess_image=args.preprocess_image,
        tex_slat_sampler_params={'steps': args.steps, 'guidance_strength': args.guidance_strength,
                                 'guidance_interval': args.guidance_interval})
    output.vertices = output.vertices / factor + center
    if not len(output.faces) or not np.isfinite(output.vertices).all():
        raise RuntimeError('官方贴图输出网格为空或含非有限坐标')
    output.export('textured.glb')
    write_result({'glb': 'textured.glb'}, {
        'parameters': vars(args), 'seconds': time.perf_counter() - started,
        'vertices': len(output.vertices), 'faces': len(output.faces),
        'units': 'meter', 'glb_up_axis': 'Y', 'blend_up_axis': 'Z',
        'geometry_policy': '官方 UV 可拆分顶点和重排索引；保持输入表面形状、位置和尺度',
        'source_bounds_zup': [vertices.min(axis=0).tolist(), vertices.max(axis=0).tolist()],
    })


if __name__ == '__main__':
    main()
