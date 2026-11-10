# 作用：验证交付与临时文件回收，不运行模型。
# 输入输出：临时任务与模拟产物 -> 数据库结果、外部交付目录和清理断言。
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduler import task_queue
from scheduler import task_runner
from scheduler.task_files import working_directory, publish_output
from common.mcp_common import job_response


class DeliveryTests(unittest.TestCase):
    """覆盖阶段文件保留、终态清理、失败诊断和交付目录冲突。"""

    def setUp(self):
        """建立独立数据库与调用方输出目录。"""
        temporary = tempfile.TemporaryDirectory(prefix='asset-delivery-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        data = self.root / 'data'
        patcher = patch.multiple(task_queue, DB_PATH=data / 'tasks.sqlite3', DATA_DIR=data)
        patcher.start()
        self.addCleanup(patcher.stop)
        task_queue.initialize()
        self.output = self.root / 'delivered'

    def test_publish_then_clean_all_intermediates(self):
        """中间阶段保留文件，终态仅发布声明产物并从数据库返回清单。"""
        first = "from pathlib import Path; Path('intermediate.pt').write_bytes(b'large')"
        final = (
            "import json; from pathlib import Path; "
            "assert Path('intermediate.pt').read_bytes()==b'large'; "
            "Path('asset.glb').write_bytes(b'asset'); "
            "Path('result.json').write_text(json.dumps({'artifacts':"
            "{'asset':str(Path('asset.glb').resolve())},'metadata':{'passed':True}}))"
        )
        identifier = task_queue.enqueue([
            {'resource': 'gpu', 'argv': [sys.executable, '-c', first]},
            {'resource': 'cpu', 'argv': [sys.executable, '-c', final]},
        ], str(self.output))
        waiting = task_runner.run_next('gpu')
        self.assertEqual(waiting['status'], 'queued')
        self.assertTrue((working_directory(identifier) / 'intermediate.pt').exists())
        self.assertIsNone(job_response(waiting)['output'])
        self.assertFalse(self.output.exists())
        completed = task_runner.run_next('cpu')
        self.assertEqual(completed['status'], 'succeeded', completed)
        self.assertFalse(working_directory(identifier).exists())
        self.assertEqual({p.name for p in self.output.iterdir()}, {'asset.glb', 'result.json'})
        manifest = job_response(completed)['output']
        self.assertEqual(Path(manifest['artifacts']['asset']).read_bytes(), b'asset')
        (self.output / 'result.json').unlink()
        task_queue.initialize()
        self.assertEqual(job_response(task_queue.get_task(identifier))['output'], manifest)
        self.assertFalse((task_queue.DB_PATH.parent / 'tasks').exists())

    def test_failure_cleans_and_keeps_bounded_error(self):
        """失败后移除大中间文件，数据库保留有上限的日志末尾。"""
        code = ("from pathlib import Path; import sys; "
                "Path('large.pt').write_bytes(b'x'*100000); "
                "print('中'*10000); print('final error marker'); sys.exit(7)")
        identifier = task_queue.enqueue(
            [{'resource': 'gpu', 'argv': [sys.executable, '-c', code]}], str(self.output))
        failed = task_runner.run_next('gpu')
        self.assertEqual(failed['status'], 'failed')
        self.assertFalse(working_directory(identifier).exists())
        self.assertFalse(self.output.exists())
        log = failed['result'][0]['log']
        self.assertLessEqual(len(log.encode('utf-8')), 8192)
        self.assertIn('final error marker', log)

    def test_external_artifact_is_rejected_without_deleting_input(self):
        """拒绝将临时工作目录之外的文件当作自产物，保持输入不变。"""
        source = self.root / 'input.npz'
        source.write_bytes(b'untouched')
        code = ("import json; from pathlib import Path; "
                f"Path('result.json').write_text(json.dumps({{'artifacts':{{'mesh':{str(source)!r}}},'metadata':{{}}}}))")
        identifier = task_queue.enqueue(
            [{'resource': 'cpu', 'argv': [sys.executable, '-c', code]}], str(self.output))
        failed = task_runner.run_next('cpu')
        self.assertEqual(failed['status'], 'failed')
        self.assertFalse(working_directory(identifier).exists())
        self.assertFalse(self.output.exists())
        self.assertEqual(source.read_bytes(), b'untouched')
        self.assertFalse(list(self.root.glob('.asset-delivery-*')))

    def test_destination_conflicts_and_old_schema(self):
        """拒绝相对、已存在、服务 data 内与并发重复交付目录。"""
        steps = [{'resource': 'gpu', 'argv': [sys.executable, '-c', 'pass']}]
        for destination in ('relative', str(self.root), str(task_queue.DATA_DIR / 'output'),
                            str(working_directory(1) / 'delivery')):
            with self.assertRaises(ValueError):
                task_queue.enqueue(steps, destination)
        identifier = task_queue.enqueue(steps, str(self.output))
        with self.assertRaises(ValueError):
            task_queue.enqueue(steps, str(self.output))
        # 验证旧表升级保持既有状态和任务 ID，不要求重建数据库。
        with task_queue._connect() as connection:
            connection.execute('ALTER TABLE tasks DROP COLUMN output')
        task_queue.initialize()
        self.assertEqual(task_queue.get_task(identifier)['status'], 'queued')
        self.assertIsNone(task_queue.get_task(identifier)['output'])


    @unittest.skipUnless(os.name == 'nt', 'Windows ACL regression')
    def test_delivery_inherits_project_permissions(self):
        """交付目录和嵌套产物继承项目读权限，不携带临时目录的受保护 ACL。"""
        import ntsecuritycon
        import win32security as security
        users = security.CreateWellKnownSid(security.WinBuiltinUsersSid, None)
        sd = security.GetNamedSecurityInfo(str(self.root), security.SE_FILE_OBJECT,
                                         security.DACL_SECURITY_INFORMATION)
        acl = sd.GetSecurityDescriptorDacl()
        acl.AddAccessAllowedAceEx(security.ACL_REVISION,
            security.OBJECT_INHERIT_ACE | security.CONTAINER_INHERIT_ACE,
            ntsecuritycon.FILE_GENERIC_READ | ntsecuritycon.FILE_GENERIC_EXECUTE, users)
        security.SetNamedSecurityInfo(str(self.root), security.SE_FILE_OBJECT,
                                     security.DACL_SECURITY_INFORMATION, None, None, acl, None)
        source = self.root / 'source'
        source.mkdir()
        (source / 'nested').mkdir()
        (source / 'nested/asset.bin').write_bytes(b'asset')
        (source / 'result.json').write_text(json.dumps({
            'artifacts': {'asset': str(source / 'nested/asset.bin')}, 'metadata': {}}))
        publish_output(source, str(self.output))
        for path in (self.output, self.output / 'nested', self.output / 'nested/asset.bin',
                     self.output / 'result.json'):
            sd = security.GetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT,
                                              security.DACL_SECURITY_INFORMATION)
            self.assertFalse(sd.GetSecurityDescriptorControl()[0] & security.SE_DACL_PROTECTED)
            acl = sd.GetSecurityDescriptorDacl()
            self.assertTrue(any(acl.GetAce(i)[2] == users and
                                acl.GetAce(i)[0][1] & security.INHERITED_ACE
                                for i in range(acl.GetAceCount())), str(path))
        self.assertEqual((self.output / 'nested/asset.bin').read_bytes(), b'asset')
        self.assertFalse(list(self.root.glob('.asset-delivery-*')))

if __name__ == '__main__':
    unittest.main()
