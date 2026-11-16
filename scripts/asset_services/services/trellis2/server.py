# 作用：提供独立 TRELLIS.2 MCP，提交单张图片的图生资产任务。
# 输入输出：submit_job(图片与生成参数) -> job_id；查询与等待由公共模块注册。
from pathlib import Path
import sys
from typing import Annotated, Literal

from pydantic import Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.service_config import TRELLIS_PYTHON
from common.mcp_common import create_server, existing_file
from scheduler import task_queue


PYTHON_PATH = TRELLIS_PYTHON
WORKER_SCRIPT = Path(__file__).with_name('worker.py')
mcp = create_server('trellis2', '从单体参考图生成带 PBR 材质的三维资产。')


@mcp.tool()
def submit_job(
    image_path: str,
    output_dir: str,
    resolution: Literal[512, 1024] = 1024,
    seed: Annotated[int, Field(ge=0, le=4294967295)] = 42,
    texture_size: Literal[1024, 2048, 4096] = 2048,
    max_faces: Annotated[int, Field(ge=10000, le=1000000)] = 200000,
) -> dict:
    """提交单个图生资产任务，立即返回 job_id。

    Args:
        output_dir: 位于服务 data 目录之外的全新绝对交付目录；成功后只保存最终产物。
        image_path: 本机绝对图片路径，物体完整，优先透明背景。
        resolution: 几何分辨率。
        seed: 随机种子。
        texture_size: 贴图边长。
        max_faces: 导出目标三角面数。
    Returns:
        dict: 本次请求独立的 job_id，可交给 get_job 或 wait_job。
    """
    argv = [
        existing_file(PYTHON_PATH), '-u', existing_file(WORKER_SCRIPT),
        '--image_path', existing_file(image_path),
        '--resolution', str(resolution), '--seed', str(seed),
        '--texture_size', str(texture_size), '--max_faces', str(max_faces),
    ]
    return {'job_id': task_queue.enqueue([{'resource': 'gpu', 'argv': argv}], output_dir)}


if __name__ == '__main__':
    task_queue.initialize()
    mcp.run(transport='stdio')
