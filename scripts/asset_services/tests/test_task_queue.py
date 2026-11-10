# 作用：使用临时数据库与模拟任务验证生命周期和跨进程领取。
# 输入输出：unittest 无参数运行；只创建临时队列，不调用模型或访问真实 GPU。
import multiprocessing
from pathlib import Path
from queue import Empty
import sys
import uuid
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduler import task_queue


def use_store(directory):
    """将本测试进程连接到指定的隔离数据库。"""
    task_queue.DB_PATH = Path(directory) / 'tasks.sqlite3'


def produce(directory, output):
    """从独立进程提交四项任务并回传任务 ID。"""
    use_store(directory)
    output.put([task_queue.enqueue([{'resource': 'gpu', 'argv': [sys.executable, '-c', f'print({i})']}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex))) for i in range(4)])


def consume(directory, output):
    """从独立进程领取并完成全部 GPU 任务，回传执行顺序的任务 ID。"""
    use_store(directory)
    executed = []
    while True:
        task = task_queue.dequeue('gpu')
        if task is None:
            break
        time.sleep(0.02)
        task_queue.finish(task['id'], result={'done': True})
        executed.append(task['id'])
    output.put(executed)


def wait_for_task(directory, job_id, output):
    """在独立进程等待指定任务，并将最终结果回传。"""
    use_store(directory)
    output.put('waiting')
    output.put(task_queue.wait_job(job_id))


class QueueTests(unittest.TestCase):
    """验证持久任务状态及多进程共享行为。"""

    def setUp(self):
        """为每个测试建立独立数据库。"""
        self.temporary = tempfile.TemporaryDirectory(prefix='asset-queue-test-')
        self.addCleanup(self.temporary.cleanup)
        use_store(self.temporary.name)
        task_queue.initialize()
        self.context = multiprocessing.get_context('spawn')

    def run_processes(self, target, *arguments):
        """运行三个独立客户端，收集结果并回收本测试创建的进程。"""
        output = self.context.Queue()
        processes = [self.context.Process(
            target=target, args=(self.temporary.name, output, *arguments)
        ) for _ in range(3)]
        try:
            for process in processes:
                process.start()
            results = [output.get(timeout=20) for _ in processes]
            for process in processes:
                process.join(timeout=10)
                self.assertEqual(process.exitcode, 0)
            return [item for batch in results for item in batch]
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
            output.close()
            output.join_thread()

    def test_lifecycle(self):
        """验证 JSON 往返、FIFO、成功失败状态以及重新初始化不丢数据。"""
        argv = [sys.executable, 'C:/输入/模型 script.py', '--steps', '8', '--label', '中文 空格']
        first = task_queue.enqueue([{'resource': 'gpu', 'argv': argv}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
        second = task_queue.enqueue([{'resource': 'gpu', 'argv': [sys.executable, '-c', 'print(1)']}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
        with self.assertRaises(ValueError):
            task_queue.finish(first)
        task = task_queue.dequeue('gpu')
        self.assertEqual((task['id'], task['steps'][0]['argv'], task['status']), (first, argv, 'running'))
        task_queue.finish(first, result={'mesh_path': 'C:/输出.npz'})
        self.assertEqual(task_queue.dequeue('gpu')['id'], second)
        task_queue.finish(second, error='模拟失败')
        task_queue.initialize()
        self.assertEqual(task_queue.get_task(first)['result'][-1], {'mesh_path': 'C:/输出.npz'})
        self.assertEqual(task_queue.get_task(first)['status'], 'succeeded')
        self.assertEqual(task_queue.get_task(second)['status'], 'failed')
        self.assertEqual(task_queue.get_task(second)['error'], '模拟失败')
        self.assertIsNone(task_queue.dequeue('gpu'))
        self.assertIsNone(task_queue.get_task(second + 1))
        with self.assertRaises(ValueError):
            task_queue.finish(first, error='禁止覆写终态')

    def test_invalid_argv(self):
        """拒绝命令字符串、空列表和未转换为字符串的参数。"""
        for argv in ['python script.py', [], ['python', '--seed', 42]]:
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                task_queue.enqueue([{'resource': 'gpu', 'argv': argv}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
        self.assertIsNone(task_queue.dequeue('gpu'))

    def test_wait_specific_job(self):
        """验证其他任务结束不会提前返回，指定任务成功或失败均能结束等待。"""
        for error in (None, '模拟失败'):
            with self.subTest(error=error):
                first = task_queue.enqueue([{'resource': 'gpu', 'argv': [sys.executable, '-c', 'print(1)']}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
                target = task_queue.enqueue([{'resource': 'gpu', 'argv': [sys.executable, '-c', 'print(2)']}], output_dir=str(task_queue.DB_PATH.parent / ('output-' + uuid.uuid4().hex)))
                output = self.context.Queue()
                process = self.context.Process(
                    target=wait_for_task, args=(self.temporary.name, target, output)
                )
                process.start()
                try:
                    self.assertEqual(output.get(timeout=10), 'waiting')
                    with self.assertRaises(Empty):
                        output.get(timeout=0.35)
                    self.assertEqual(task_queue.dequeue('gpu')['id'], first)
                    task_queue.finish(first)
                    with self.assertRaises(Empty):
                        output.get(timeout=0.35)
                    self.assertEqual(task_queue.dequeue('gpu')['id'], target)
                    task_queue.finish(target, result={'done': True}, error=error)
                    task = output.get(timeout=10)
                    self.assertEqual(task['id'], target)
                    self.assertEqual(task['status'], 'succeeded' if error is None else 'failed')
                    self.assertEqual(task['error'], error)
                    self.assertEqual(task['result'][-1], {'done': True})
                    self.assertEqual(task_queue.wait_job(target), task)
                    process.join(timeout=5)
                    self.assertEqual(process.exitcode, 0)
                finally:
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5)
                    output.close()
                    output.join_thread()

    def test_wait_missing_job(self):
        """验证不存在的 ID 直接报错，不进入无限等待。"""
        with self.assertRaisesRegex(ValueError, '不存在'):
            task_queue.wait_job(1)

    def test_atomic_claim(self):
        """验证并发入队 ID 独立，多进程并发领取也不会重复。"""
        identifiers = self.run_processes(produce)
        self.assertEqual(len(set(identifiers)), 12)
        executed = self.run_processes(consume)
        self.assertEqual(sorted(executed), sorted(identifiers))


if __name__ == '__main__':
    unittest.main(verbosity=2)
