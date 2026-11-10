# 作用：为协议测试启动指定真实 MCP 入口，仅替换数据库、锁和模型脚本位置。
# 输入输出：模块名、临时目录、模拟脚本路径 -> stdio MCP 服务。
import importlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduler import task_queue


if __name__ == '__main__':
    module_name, directory, worker = sys.argv[1:]
    task_queue.DB_PATH = Path(directory) / 'tasks.sqlite3'
    task_queue.initialize()
    service = importlib.import_module(module_name)
    if worker != '-':
        service.PYTHON_PATH = Path(sys.executable)
        service.WORKER_SCRIPT = Path(worker)
        if module_name == 'services.texture.server':
            service.REMESH_SCRIPT = Path(worker).with_name('remesh_worker.py')
            service.EXPORT_SCRIPT = Path(worker).with_name('export_worker.py')
    else:
        service.WORKER_SCRIPT = Path(directory) / 'missing_worker.py'
        if module_name == 'services.texture.server':
            service.REMESH_SCRIPT = Path(directory) / 'missing_remesh.py'
            service.EXPORT_SCRIPT = Path(directory) / 'missing_export.py'
    service.mcp.run(transport='stdio')
