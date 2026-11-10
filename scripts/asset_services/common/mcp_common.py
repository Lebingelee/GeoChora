# 作用：为三个独立 MCP 入口注册公共查询和单任务等待工具。
# 输入输出：create_server(name, capability) -> FastMCP；job_response(Task) -> 对外任务记录。
import asyncio
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from scheduler import task_queue


def existing_file(path: str | Path) -> str:
    """检查绝对文件路径并返回字符串，供三个入口组装 argv。"""
    path = Path(path)
    if not path.is_absolute() or not path.is_file():
        raise ValueError(f'需要已存在的绝对文件路径：{path}')
    return str(path)


def job_response(task: task_queue.Task | None) -> dict:
    """将队列记录转换为 MCP 返回值，未知任务直接报错。"""
    if task is None:
        raise ValueError('任务不存在')
    output = task['output'] if task['status'] == 'succeeded' else None
    return {'output_dir': task['output_dir'], 'output': output, 'job_id': task['id'], 'status': task['status'],
            'current_step': task['current_step'], 'step_count': len(task['steps']),
            'resource': task['resource'], 'result': task['result'], 'error': task['error']}


def create_server(name: str, capability: str) -> FastMCP:
    """创建独立服务并注册公共工具；算法提交工具由各入口定义。"""
    mcp = FastMCP(name, instructions=capability +
        '每次提交一个生成单位并指定全新绝对 output_dir；立即返回 job_id。'
        '使用 wait_job(job_id) 等待指定任务成功或失败；get_job 用于状态诊断。'
        '成功后 output.artifacts 提供交付文件绝对路径，每阶段最多 8 KiB 的末尾日志见 result[].log。'
        '本机后端由独立 task_runner 按就绪顺序调度，CPU 与 GPU 各自执行。')

    @mcp.tool()
    def get_job(job_id: int) -> dict:
        """查询指定任务的状态、结果或错误；不存在的 ID 报错。"""
        return job_response(task_queue.get_task(job_id))

    @mcp.tool()
    async def wait_job(job_id: int) -> dict:
        """等待指定任务成功或失败并返回记录；不因其他任务完成而返回。"""
        task = await asyncio.to_thread(task_queue.wait_job, job_id)
        return job_response(task)

    return mcp
