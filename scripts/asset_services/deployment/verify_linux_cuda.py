# 作用：验证本机推理环境在当前驱动上的 CUDA、注意力、网格和栅格化能力。
# 输入输出：已安装的 trellis2 环境 -> 实际 GPU 运算检查结果；失败直接抛出异常。
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.service_config import configure_runtime
configure_runtime()

import torch
import xformers.ops
import cumesh
import nvdiffrast.torch as dr
import cumesh._cubvh
import flex_gemm.kernels.cuda
import o_voxel
import nvdiffrec_render.renderutils as renderutils


def main():
    """执行服务所需的实际 GPU 运算并检查结果。

    Returns:
        None: 输出 GPU 和软件版本；任何运算失败时抛出异常。
    """
    assert torch.cuda.is_available()
    matrix = torch.randn((256, 256), device='cuda')
    assert torch.isfinite(matrix @ matrix).all()
    query = torch.randn((1, 64, 4, 32), device='cuda', dtype=torch.float16)
    attention = xformers.ops.memory_efficient_attention(query, query, query)
    assert attention.shape == query.shape and torch.isfinite(attention).all()
    vertices = torch.tensor([[-.5, -.5, 0], [.5, -.5, 0], [0, .5, 0]], device='cuda')
    faces = torch.tensor([[0, 1, 2]], device='cuda', dtype=torch.int32)
    mesh = cumesh.CuMesh()
    mesh.init(vertices, faces)
    actual_vertices, actual_faces = mesh.read()
    assert actual_vertices.shape == (3, 3) and actual_faces.shape == (1, 3)
    homogeneous = torch.cat((vertices, torch.ones((3, 1), device='cuda')), dim=1)[None]
    raster, _ = dr.rasterize(dr.RasterizeCudaContext(), homogeneous, faces, resolution=(32, 32))
    assert (raster[..., 3] > 0).any()
    points = torch.tensor([[[1., 2., 3.]]], device='cuda')
    transformed = renderutils.xfm_points(points, torch.eye(4, device='cuda')[None])
    assert torch.allclose(transformed[..., :3], points)
    torch.cuda.synchronize()
    print(json.dumps({'passed': True, 'torch': torch.__version__, 'cuda': torch.version.cuda,
                      'gpu': torch.cuda.get_device_name(), 'gpu_count': torch.cuda.device_count()}))


if __name__ == '__main__':
    main()
