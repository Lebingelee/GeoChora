# 作用：提供 CuMesh 独立重拓扑和 TRELLIS 官方独立贴图 MCP。
# 输入输出：submit_remesh(网格、重建参数)、submit_job(网格、图片) -> job_id；共用查询与等待。
from pathlib import Path
import sys
from typing import Annotated, Literal

from pydantic import Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.service_config import TRELLIS_PYTHON
from common.mcp_common import create_server, existing_file
from scheduler import task_queue


PYTHON_PATH = TRELLIS_PYTHON
REMESH_SCRIPT = Path(__file__).with_name('remesh_worker.py')
WORKER_SCRIPT = Path(__file__).with_name('worker.py')
EXPORT_SCRIPT = Path(__file__).with_name('export_worker.py')
mcp = create_server('trellis-texturing', 'submit_job 保持表面形状生成 UV/PBR；submit_remesh 使用 CuMesh 独立重拓扑并报告几何变化。共用 get_job、wait_job。')


@mcp.tool()
def submit_job(
    mesh_path: str,
    image_path: str,
    output_dir: str,
    resolution: Literal[512, 1024] = 1024,
    steps: Annotated[int, Field(ge=1, le=100)] = 12,
    guidance_strength: Annotated[float, Field(ge=0, le=20)] = 1.0,
    guidance_interval: tuple[float, float] = (0.6, 0.9),
    texture_size: Literal[1024, 2048, 4096] = 2048,
    seed: Annotated[int, Field(ge=0, le=4294967295)] = 42,
    preprocess_image: bool = True,
) -> dict:
    """提交单个固定网格的贴图任务，立即返回 job_id；无重拓扑步骤。

    Args:
        mesh_path: 本机绝对 NPZ 路径，含米制 Z-up 的 vertices[N,3] 和三角 faces[M,3]；保持表面形状、位置和尺度，UV 接缝可拆分顶点及重排索引。
        output_dir: 位于服务 data 目录之外的全新绝对交付目录；成功后只保存最终产物。
        image_path: 对应该部件的绝对参考图路径。
        resolution: 材质场分辨率。
        steps: 采样步数。
        guidance_strength: 引导强度。
        guidance_interval: 引导起止比例，满足 0 ≤ 起点 ≤ 终点 ≤ 1。
        texture_size: 贴图边长。
        seed: 随机种子。
        preprocess_image: 使用官方参考图预处理。
    Returns:
        dict: job_id；成功后 output.artifacts 提供内嵌 PBR 的 glb 和可查看的 blend。
    """
    if not 0 <= guidance_interval[0] <= guidance_interval[1] <= 1:
        raise ValueError('guidance_interval 须满足 0 ≤ 起点 ≤ 终点 ≤ 1')
    texture_argv = [
        existing_file(PYTHON_PATH), '-u', existing_file(WORKER_SCRIPT),
        '--mesh_path', existing_file(mesh_path), '--image_path', existing_file(image_path),
        '--resolution', str(resolution),
        '--steps', str(steps), '--guidance_strength', str(guidance_strength),
        '--guidance_interval', str(guidance_interval[0]), str(guidance_interval[1]),
        '--texture_size', str(texture_size), '--seed', str(seed),
        '--preprocess_image' if preprocess_image else '--no-preprocess_image',
    ]
    return {'job_id': task_queue.enqueue([
        {'resource': 'gpu', 'argv': texture_argv},
        {'resource': 'cpu', 'argv': [existing_file(PYTHON_PATH), '-u', existing_file(EXPORT_SCRIPT)]},
    ], output_dir)}


@mcp.tool()
def submit_remesh(
    mesh_path: str,
    output_dir: str,
    resolution: Literal[256, 512, 1024],
    decimation_target: Annotated[int, Field(ge=100, le=16777216)] = 1000000,
    remesh_band: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 1.0,
    remesh_project: Annotated[float, Field(ge=0, le=1)] = 0.0,
) -> dict:
    """提交独立 GPU 重拓扑任务，立即返回 job_id；不需要参考图。

    Args:
        mesh_path: 本机绝对 NPZ 路径，含米制 Z-up vertices[N,3] 和三角 faces[M,3]。
        output_dir: 位于服务 data 目录之外的全新绝对交付目录。
        resolution: 重建体素分辨率；NPZ 不含原体素网格信息，须显式指定。
        decimation_target: 目标三角面数，实际数量可偏离目标。
        remesh_band: 重建表面距原网格的偏移，以体素为单位；1 约对应一个体素。增大可能填合小缝隙，也可能使薄片粘连或细节变钝；实际距离随物体尺度及 resolution 改变。
        remesh_project: 新顶点向原表面最近点移动的比例，0 不回投影，0.9 移动 90%，1 完全贴回。增大可减少偏移，也可能贴回噪声或压扁三角形；后续减面仍会改变几何。默认 0 沿用 TRELLIS 导出示例。
    Returns:
        dict: job_id；wait_job 成功后交付 mesh(NPZ)、glb、blend 和 remesh_check。
            检查报告包含拓扑与双向表面距离，供调用方判断形状变化；
            确认网格后可将 mesh 与参考图交给 submit_job 贴图。
    """
    argv = [
        existing_file(PYTHON_PATH), '-u', existing_file(REMESH_SCRIPT),
        '--mesh_path', existing_file(mesh_path),
        '--resolution', str(resolution), '--decimation_target', str(decimation_target),
        '--remesh_band', str(remesh_band), '--remesh_project', str(remesh_project),
    ]
    return {'job_id': task_queue.enqueue([
        {'resource': 'gpu', 'argv': argv},
        {'resource': 'cpu', 'argv': [existing_file(PYTHON_PATH), '-u', existing_file(EXPORT_SCRIPT)]},
    ], output_dir)}


if __name__ == '__main__':
    task_queue.initialize()
    mcp.run(transport='stdio')
