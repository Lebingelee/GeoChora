# 作用：用真实轻量子进程验证 argv 传递、故障隔离、日志及跨执行端领取。
# 输入输出：unittest 无参数运行；仅使用临时数据库与 Python 脚本。
import json
import multiprocessing
from pathlib import Path
import sys
import uuid
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduler import task_queue
from scheduler import task_runner
from scheduler.task_files import working_directory


def drain(directory, output):
    """在独立管理进程中处理临时队列，返回已执行任务的 ID。"""
    task_queue.DB_PATH = Path(directory) / 'tasks.sqlite3'
    identifiers = []
    while (task := task_runner.run_next('gpu')) is not None:
        identifiers.append(task['id'])
    output.put(identifiers)


def serve(directory):
    """在隔离目录启动真实调度循环。"""
    task_queue.DB_PATH = Path(directory) / 'tasks.sqlite3'
    task_runner.main()


class RunnerTests(unittest.TestCase):
    """验证管理端实际启动子进程后的行为。"""

    def setUp(self):
        """为每项测试隔离数据库和日志目录。"""
        temporary = tempfile.TemporaryDirectory(prefix='asset-runner-test-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        paths = patch.multiple(
            task_queue, DB_PATH=self.directory / 'tasks.sqlite3',
        )
        paths.start()
        self.addCleanup(paths.stop)
        task_queue.initialize()

    def test_argv_and_logs(self):
        """验证带空格、中文和 shell 字符的参数原样传入，输出写入任务日志。"""
        script = self.directory / '参数 script.py'
        script.write_text(
            "import json, os, sys\n"
            "print(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}, ensure_ascii=True))\n"
            "print('stderr marker', file=sys.stderr)\n",
            encoding='utf-8',
        )
        arguments = ['中文 空格', '', 'a"b', '& echo not-a-shell', '$value']
        identifier = task_queue.enqueue([{'resource': 'gpu', 'argv': [sys.executable, str(script), *arguments]}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
        task = task_runner.run_next('gpu')
        self.assertEqual((task['id'], task['status']), (identifier, 'succeeded'))
        self.assertEqual(task['result'][-1]['returncode'], 0)
        lines = task['result'][-1]['log'].splitlines()
        data = json.loads(next(line for line in lines if line.startswith('{')))
        self.assertEqual(data['argv'], arguments)
        self.assertEqual(Path(data['cwd']), working_directory(identifier))
        self.assertIn('stderr marker', lines)

    def test_failures_then_success(self):
        """验证启动失败、脚本异常及突然退出均不会阻止管理端处理下一项。"""
        requests = [
            [str(self.directory / 'missing-python.exe')],
            [sys.executable, '-c', "raise RuntimeError('child failure')"],
            [sys.executable, '-c', 'import os; os._exit(7)'],
            [sys.executable, '-c', "print('next job succeeded')"],
        ]
        identifiers = [task_queue.enqueue([{'resource': 'gpu', 'argv': argv}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex))) for argv in requests]
        tasks = [task_runner.run_next('gpu') for _ in requests]
        self.assertEqual([task['id'] for task in tasks], identifiers)
        self.assertEqual([task['status'] for task in tasks], ['failed'] * 3 + ['succeeded'])
        self.assertEqual([task['result'][-1]['returncode'] for task in tasks], [None, 1, 7, 0])
        self.assertTrue(all(task['error'] for task in tasks[:3]))
        self.assertIn('FileNotFoundError', tasks[0]['error'])
        self.assertIn('RuntimeError: child failure',
                      tasks[1]['result'][-1]['log'])
        self.assertIsNone(task_runner.run_next('gpu'))

    def test_multiple_runners(self):
        """验证两个实际执行端不会重复领取，全部任务各执行一次。"""
        command = [sys.executable, '-c',
                   'import json,time; start=time.monotonic(); time.sleep(.08); '
                   'print(json.dumps([start,time.monotonic()]))']
        identifiers = [task_queue.enqueue([{'resource': 'gpu', 'argv': command}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex))) for _ in range(6)]
        context = multiprocessing.get_context('spawn')
        output = context.Queue()
        processes = [context.Process(target=drain, args=(str(self.directory), output))
                     for _ in range(2)]
        try:
            for process in processes:
                process.start()
            batches = [output.get(timeout=20) for _ in processes]
            for process in processes:
                process.join(timeout=10)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(sorted(item for batch in batches for item in batch), identifiers)
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
            output.close()
            output.join_thread()
        for identifier in identifiers:
            self.assertEqual(task_queue.get_task(identifier)['status'], 'succeeded')

    def test_empty_queue(self):
        """验证空队列直接返回且不会创建任务日志目录。"""
        self.assertIsNone(task_runner.run_next('gpu'))
        self.assertFalse((self.directory / 'tasks').exists())

    def test_scheduler_loop(self):
        """验证空队列时保持运行，后来入队的失败及成功任务均能持续处理。"""
        context = multiprocessing.get_context('spawn')
        process = context.Process(target=serve, args=(str(self.directory),))
        process.start()
        try:
            time.sleep(0.7)
            self.assertTrue(process.is_alive())
            for command, status in [
                ('import sys; sys.exit(7)', 'failed'),
                ("print('later job succeeded')", 'succeeded'),
            ]:
                identifier = task_queue.enqueue([{'resource': 'gpu', 'argv': [sys.executable, '-c', command]}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
                deadline = time.monotonic() + 10
                task = task_queue.get_task(identifier)
                while task['status'] in ('queued', 'running') and time.monotonic() < deadline:
                    self.assertTrue(process.is_alive())
                    time.sleep(0.05)
                    task = task_queue.get_task(identifier)
                self.assertEqual(task['status'], status)
                self.assertTrue(process.is_alive())
        finally:
            process.terminate()
            process.join(timeout=5)
            self.assertFalse(process.is_alive())


if __name__ == '__main__':
    unittest.main(verbosity=2)
