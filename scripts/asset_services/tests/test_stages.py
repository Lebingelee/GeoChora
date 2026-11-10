# 作用：验证线性阶段依赖、资源就绪顺序、阶段失败与两通道执行。
# 输入输出：仅运行临时目录中的模拟 CPU/GPU 脚本，不使用真实 GPU。
import multiprocessing
from pathlib import Path
from queue import Empty
import sys
import uuid
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduler import task_queue
from scheduler import task_runner
from scheduler.task_files import working_directory
from test_task_queue import wait_for_task


class StageTests(unittest.TestCase):
    """验证一个任务的阶段顺序与不同任务的资源交叠。"""

    def setUp(self):
        """建立隔离数据库及信号目录。"""
        temporary = tempfile.TemporaryDirectory(prefix='asset-stages-test-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        paths = patch.multiple(task_queue, DB_PATH=self.directory / 'tasks.sqlite3')
        paths.start()
        self.addCleanup(paths.stop)
        task_queue.initialize()
        self.context = multiprocessing.get_context('spawn')

    def test_ready_order_and_dependency(self):
        """验证后续阶段必须等前步成功，且按就绪顺序而非任务 ID 领取。"""
        argv = [sys.executable, '-c', 'pass']
        earlier = task_queue.enqueue([{'resource': 'cpu', 'argv': argv},
                                      {'resource': 'gpu', 'argv': argv}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
        first_ready = task_queue.enqueue([{'resource': 'gpu', 'argv': argv}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
        second_ready = task_queue.enqueue([{'resource': 'gpu', 'argv': argv}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
        self.assertEqual(task_queue.dequeue('cpu')['id'], earlier)
        task_queue.finish(earlier, result={'prepared': True})
        midway = task_queue.get_task(earlier)
        self.assertEqual((midway['current_step'], midway['resource'], midway['status']), (1, 'gpu', 'queued'))
        for identifier in [first_ready, second_ready, earlier]:
            self.assertEqual(task_queue.dequeue('gpu')['id'], identifier)
            task_queue.finish(identifier)
        self.assertEqual(len(task_queue.get_task(earlier)['result']), 2)
        self.assertIsNone(task_queue.dequeue('cpu'))
        self.assertIsNone(task_queue.dequeue('gpu'))

    def test_wait_all_steps(self):
        """验证前一步完成不会结束 wait_job，最后一步完成才返回整个任务。"""
        argv = [sys.executable, '-c', 'pass']
        identifier = task_queue.enqueue([{'resource': 'cpu', 'argv': argv},
                                         {'resource': 'gpu', 'argv': argv}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
        output = self.context.Queue()
        process = self.context.Process(target=wait_for_task,
                                       args=(str(self.directory), identifier, output))
        process.start()
        try:
            self.assertEqual(output.get(timeout=10), 'waiting')
            self.assertIsNone(task_queue.dequeue('gpu'))
            self.assertEqual(task_queue.dequeue('cpu')['id'], identifier)
            task_queue.finish(identifier)
            with self.assertRaises(Empty):
                output.get(timeout=0.35)
            self.assertEqual(task_queue.dequeue('gpu')['id'], identifier)
            task_queue.finish(identifier)
            result = output.get(timeout=10)
            self.assertEqual(result['status'], 'succeeded')
            self.assertEqual(len(result['result']), 2)
            process.join(timeout=5)
            self.assertEqual(process.exitcode, 0)
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            output.close()
            output.join_thread()

    def test_failure_stops_following_steps(self):
        """验证阶段失败后不运行后续命令，其他任务仍可执行。"""
        identifier = task_queue.enqueue([
            {'resource': 'cpu', 'argv': [sys.executable, '-c', 'import sys; sys.exit(7)']},
            {'resource': 'gpu', 'argv': [sys.executable, '-c',
                "from pathlib import Path; Path('unexpected').touch()"]},
        ], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
        other = task_queue.enqueue([{'resource': 'gpu', 'argv': [sys.executable, '-c', 'pass']}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
        failed = task_runner.run_next('cpu')
        self.assertEqual((failed['id'], failed['status']), (identifier, 'failed'))
        self.assertEqual(len(failed['result']), 1)
        self.assertEqual(failed['result'][0]['returncode'], 7)
        self.assertEqual(task_runner.run_next('gpu')['id'], other)
        self.assertIsNone(task_runner.run_next('gpu'))
        self.assertFalse((working_directory(identifier) / 'unexpected').exists())

    def test_shared_working_directory(self):
        """验证阶段间可通过同一任务目录传递文件，每步日志独立保存。"""
        identifier = task_queue.enqueue([
            {'resource': 'cpu', 'argv': [sys.executable, '-c',
                "from pathlib import Path; Path('prepared.txt').write_text('ready')"]},
            {'resource': 'gpu', 'argv': [sys.executable, '-c',
                "from pathlib import Path; assert Path('prepared.txt').read_text() == 'ready'"]},
        ], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
        self.assertEqual(task_runner.run_next('cpu')['status'], 'queued')
        completed = task_runner.run_next('gpu')
        self.assertEqual(completed['status'], 'succeeded')
        self.assertEqual(len(completed['result']), 2)
        self.assertTrue(all('log' in item for item in completed['result']))
        self.assertFalse(working_directory(identifier).exists())


    def test_invalid_steps(self):
        """拒绝空计划、未知资源和非法命令，避免错误任务进入调度器。"""
        for steps in [[], 'command', [{'resource': 'other', 'argv': ['python']}],
                      [{'resource': 'cpu', 'argv': []}], [{'resource': 'gpu', 'argv': ['python', 42]}]]:
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                task_queue.enqueue(steps, output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
        self.assertIsNone(task_queue.dequeue('cpu'))
        self.assertIsNone(task_queue.dequeue('gpu'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
