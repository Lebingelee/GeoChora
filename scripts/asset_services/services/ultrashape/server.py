# 作用：提供独立 UltraShape MCP，提交单个网格及参考图的细化任务。
# 输入输出：submit_job(网格、图片与细化参数) -> job_id；查询与等待由公共模块注册。
from pathlib import Path
import sys
from typing import Annotated, Literal

from pydantic import Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.service_config import ULTRASHAPE_PYTHON
from common.mcp_common import create_server, existing_file
from scheduler import task_queue


PYTHON_PATH = ULTRASHAPE_PYTHON
WORKER_SCRIPT = Path(__file__).with_name('worker.py')
mcp = create_server('ultrashape', '根据粗网格与参考图细化单个生成单位的几何。')


@mcp.tool()
def submit_job(
    mesh_path: str,
    image_path: str,
    output_dir: str,
    num_latents: Literal[2048, 4096, 8192, 16384, 32768] = 4096,
    steps: Annotated[int, Field(ge=1, le=100)] = 8,
    resolution: Literal[512, 1024] = 512,
    chunk_size: Annotated[int, Field(ge=256, le=65536)] = 8000,
    guidance: Annotated[float, Field(ge=0, le=20)] = 5.0,
    seed: Annotated[int, Field(ge=0, le=4294967295)] = 42,
) -> dict:
    """提交单个部件的几何细化任务，立即返回 job_id。

    Args:
        mesh_path: 本机绝对 NPZ 路径，含米制 Z-up 的 vertices[N,3] 和三角 faces[M,3]。
        output_dir: 位于服务 data 目录之外的全新绝对交付目录；成功后只保存最终产物。
        image_path: 对应该部件的绝对参考图路径。
        num_latents: 空间锚点数。
        steps: 采样步数。
        resolution: 抽面分辨率。
        chunk_size: 解码查询批大小。
        guidance: 引导强度。
        seed: 随机种子。
    Returns:
        dict: 本次请求独立的 job_id，可交给 get_job 或 wait_job。
    """
    argv = [
        existing_file(PYTHON_PATH), '-u', existing_file(WORKER_SCRIPT),
        '--mesh_path', existing_file(mesh_path), '--image_path', existing_file(image_path),
        '--num_latents', str(num_latents), '--steps', str(steps),
        '--resolution', str(resolution), '--chunk_size', str(chunk_size),
        '--guidance', str(guidance), '--seed', str(seed),
    ]
    return {'job_id': task_queue.enqueue([{'resource': 'gpu', 'argv': argv}], output_dir)}


if __name__ == '__main__':
    task_queue.initialize()
    mcp.run(transport='stdio')
