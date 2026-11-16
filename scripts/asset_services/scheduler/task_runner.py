# 作用：CPU 与 GPU 两条通道各自执行阶段，不同资源可跨任务重叠。
# 输入输出：run_next(resource) -> 当前阶段执行后的任务记录；无就绪阶段返回 None。
# 主入口：main() 启动两条执行线程；每个阶段仍由 subprocess.run 启动独立进程。
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import subprocess
import tempfile
from threading import Event

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduler import task_queue
from scheduler.task_files import working_directory, publish_output, remove_workspace


def run_next(resource: task_queue.Resource, stop: Event | None = None) -> task_queue.Task | None:
    """领取并执行一个就绪阶段，保存日志和退出码。

    Args:
        resource: cpu 或 gpu。
        stop: 停止事件；收到信号后不再领取新阶段，已领取阶段正常执行。
    Returns:
        Task | None: 阶段结束后的任务记录，或无就绪阶段时的 None。
    """
    if stop is not None and stop.is_set():
        return None
    task = task_queue.dequeue(resource)
    if task is None:
        return None
    step = task['steps'][task['current_step']]
    directory = working_directory(task['id'])
    result = {'returncode': None, 'log': ''}
    error, output = None, None
    last_step = task['current_step'] == len(task['steps']) - 1
    try:
        if not task['output_dir']:
            raise ValueError('任务缺少 output_dir，请重连新版 MCP 后重新提交')
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=directory) as log:
            try:
                process = subprocess.run(
                    step['argv'], cwd=directory, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT, shell=False, check=False,
                    env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONNOUSERSITE': '1'},
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                )
                result['returncode'] = process.returncode
            finally:
                log.seek(0, os.SEEK_END)
                log.seek(max(0, log.tell() - 8192))
                result['log'] = log.read().decode('utf-8', errors='ignore')
        if process.returncode != 0:
            raise RuntimeError(f'子进程以退出码 {process.returncode} 结束，详见 result 中的日志')
        if last_step:
            output = publish_output(directory, task['output_dir'])
    except Exception as exception:
        error = f'{type(exception).__name__}: {exception}'
    if error is not None or last_step:
        try:
            remove_workspace(task['id'])
        except Exception as exception:
            error = f'{error + "; " if error else ""}临时文件清理失败：{exception}'
    task_queue.finish(task['id'], result=result, error=error, output=output)
    return task_queue.get_task(task['id'])


def run_channel(resource: task_queue.Resource, stop: Event) -> None:
    """持续处理对应资源的就绪阶段，空闲时休眠半秒，收到停止信号后退出。"""
    while not stop.is_set():
        if run_next(resource, stop) is None:
            stop.wait(0.5)


def main(stop: Event | None = None) -> None:
    """初始化队列并启动两条通道；停止后等待当前阶段结束，管理异常向上传播。

    Args:
        stop: 外部停止事件；省略时创建内部事件，保留直接运行方式。
    Returns:
        None: 持续运行；停止时等待正在执行的阶段退出。
    """
    task_queue.initialize()
    if stop is None:
        stop = Event()
    with ThreadPoolExecutor(max_workers=2) as executor:
        channels = [executor.submit(run_channel, resource, stop) for resource in ('cpu', 'gpu')]
        try:
            for channel in as_completed(channels):
                channel.result()
        finally:
            stop.set()


if __name__ == '__main__':
    main()
