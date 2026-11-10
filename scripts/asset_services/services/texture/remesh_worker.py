# 作用：采用 TRELLIS 导出中的 CuMesh 补孔、DC 重建及简化流程。
# 输入输出：Z-up NPZ 与重建参数 -> 米制 NPZ、Y-up GLB、双向几何变化报告。
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.service_config import configure_runtime
from common.worker_io import load_mesh, write_result


def surface_distance(source, target):
    """以固定随机种子采样源表面，返回到目标表面的距离统计（米）。"""
    import cumesh
    import numpy as np
    import torch
    import trimesh
    points, _ = trimesh.sample.sample_surface(source, 20000, seed=42)
    bvh = cumesh.cuBVH(torch.tensor(target.vertices, dtype=torch.float32, device='cuda'),
                       torch.tensor(target.faces, dtype=torch.int32, device='cuda'))
    distance, _, _ = bvh.unsigned_distance(torch.tensor(points, dtype=torch.float32, device='cuda'))
    values = distance.cpu().numpy()
    return {'samples': len(values), 'mean_m': float(values.mean()),
            'p95_m': float(np.percentile(values, 95)), 'max_sampled_m': float(values.max())}


def main():
    """完成独立 CuMesh 重建并保存资产及几何变化，不生成材质。

    Returns:
        None: 写入 remeshed.npz、remeshed.glb、remesh_check.json 与结果清单。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--mesh_path', required=True)
    parser.add_argument('--resolution', type=int, choices=[256, 512, 1024], required=True)
    parser.add_argument('--decimation_target', type=int, default=1000000)
    parser.add_argument('--remesh_band', type=float, default=1.0)
    parser.add_argument('--remesh_project', type=float, default=0.0)
    args = parser.parse_args()
    configure_runtime()
    import cumesh
    import numpy as np
    import torch
    import trimesh

    started = time.perf_counter()
    vertices, faces = load_mesh(args.mesh_path)
    center = (vertices.min(axis=0) + vertices.max(axis=0)) / 2
    extent = float(np.ptp(vertices, axis=0).max())
    mesh = cumesh.CuMesh()
    mesh.init(torch.tensor((vertices - center) / extent, dtype=torch.float32, device='cuda'),
              torch.from_numpy(faces).cuda())
    mesh.fill_holes(max_hole_perimeter=0.03)
    v, f = mesh.read()
    bvh = cumesh.cuBVH(v, f)
    del mesh
    nv, nf = cumesh.remeshing.remesh_narrow_band_dc(v, f,
        center=torch.zeros(3, device='cuda'),
        scale=(args.resolution + 3 * args.remesh_band) / args.resolution,
        resolution=args.resolution, band=args.remesh_band,
        project_back=args.remesh_project, bvh=bvh, verbose=True)
    del v, f, bvh
    torch.cuda.empty_cache()
    mesh = cumesh.CuMesh()
    mesh.init(nv, nf)
    del nv, nf
    mesh.simplify(args.decimation_target, verbose=True)
    v, f = mesh.read()
    out_v = (v.cpu().numpy() * extent + center).astype(np.float32)
    out_f = f.cpu().numpy().astype(np.int32)
    # 米制 float32 落盘可能形成精确退化面，移除后才能交给固定网格贴图入口。
    triangles = out_v[out_f].astype(np.float64)
    valid = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0],
                                   triangles[:, 2] - triangles[:, 0]), axis=1) > 0
    out_f = out_f[valid]
    _, unique = np.unique(np.sort(out_f, axis=1), axis=0, return_index=True)
    out_f = out_f[np.sort(unique)]
    removed = len(f) - len(out_f)
    np.savez_compressed('remeshed.npz', vertices=out_v, faces=out_f)
    load_mesh('remeshed.npz')
    del mesh, v, f
    torch.cuda.empty_cache()
    source = trimesh.Trimesh(vertices, faces, process=False)
    result = trimesh.Trimesh(out_v, out_f, process=False)
    report = {'parameters': vars(args), 'source_faces': len(faces), 'faces': len(out_f),
        'removed_degenerate_or_duplicate_faces': removed,
        'source_bounds': source.bounds.tolist(), 'result_bounds': result.bounds.tolist(),
        'source_to_result': surface_distance(source, result),
        'result_to_source': surface_distance(result, source),
        'watertight': bool(result.is_watertight), 'quality_acceptance': 'not_evaluated'}
    Path('remesh_check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    result.vertices = out_v[:, [0, 2, 1]] * [1, 1, -1]
    result.export('remeshed.glb')
    write_result({'mesh': 'remeshed.npz', 'glb': 'remeshed.glb', 'remesh_check': 'remesh_check.json'}, {
        'parameters': vars(args), 'seconds': time.perf_counter() - started,
        'vertices': len(out_v), 'faces': len(out_f), 'units': 'meter',
        'mesh_up_axis': 'Z', 'glb_up_axis': 'Y', 'blend_up_axis': 'Z',
    })


if __name__ == '__main__':
    main()
