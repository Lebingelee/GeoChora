# 作用：验证外部停止事件、空闲退出、阶段收尾及 Windows 服务控制回调。
# 输入输出：隔离数据库、轻量子进程和模拟系统接口；不注册服务、不调用模型。
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduler import task_queue, task_runner
if os.name == 'nt':
    from scheduler import windows_service
    from deployment import register_service
from common import service_config
from scheduler.task_files import working_directory


class ServiceLifecycleTests(unittest.TestCase):
    """覆盖正常停机以及服务错误传播，不改变生产队列。"""

    def setUp(self):
        """为每个测试创建独立数据库。"""
        temporary = tempfile.TemporaryDirectory(prefix='asset-service-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patcher = patch.object(task_queue, 'DB_PATH', self.root / 'tasks.sqlite3')
        patcher.start()
        self.addCleanup(patcher.stop)
        task_queue.initialize()

    def test_stopped_before_start(self):
        """预先收到停止信号时不领取已排队任务。"""
        identifier = task_queue.enqueue([{'resource': 'gpu', 'argv': [sys.executable, '-c', 'pass']}],
                                        str(self.root / 'output'))
        stop = Event()
        stop.set()
        task_runner.main(stop)
        self.assertEqual(task_queue.get_task(identifier)['status'], 'queued')

    def test_stop_while_idle(self):
        """空队列时收到停止信号能及时退出。"""
        stop = Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(task_runner.main, stop)
            try:
                time.sleep(0.15)
                self.assertFalse(future.done())
                stop.set()
                future.result(timeout=2)
            finally:
                stop.set()

    def test_stop_finishes_stage_and_preserves_next(self):
        """停止时完成正在执行的阶段，保留中间文件和排队任务，后续可继续。"""
        ready, release = self.root / 'ready', self.root / 'release'
        command = ('from pathlib import Path; import sys,time; '
                   "Path('intermediate').write_text('keep'); "
                   'Path(sys.argv[1]).touch(); end=time.monotonic()+8; '
                   '\nwhile not Path(sys.argv[2]).exists() and time.monotonic()<end: time.sleep(.02)')
        first = task_queue.enqueue([
            {'resource': 'gpu', 'argv': [sys.executable, '-c', command, str(ready), str(release)]},
            {'resource': 'cpu', 'argv': [sys.executable, '-c',
                "from pathlib import Path; assert Path('intermediate').read_text()=='keep'"]},
        ], str(self.root / 'first'))
        second = task_queue.enqueue([{'resource': 'gpu', 'argv': [sys.executable, '-c', 'pass']}],
                                    str(self.root / 'second'))
        stop = Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(task_runner.main, stop)
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(ready.exists())
                stop.set()
                self.assertFalse(future.done())
                self.assertEqual(task_queue.get_task(first)['status'], 'running')
            finally:
                stop.set()
                release.touch()
                future.result(timeout=10)
        task = task_queue.get_task(first)
        self.assertEqual((task['status'], task['current_step']), ('queued', 1))
        self.assertTrue((working_directory(first) / 'intermediate').is_file())
        self.assertEqual(task_queue.get_task(second)['status'], 'queued')
        self.assertEqual(task_runner.run_next('cpu')['status'], 'succeeded')
        self.assertEqual(task_runner.run_next('gpu')['status'], 'succeeded')
        self.assertFalse(working_directory(first).exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows 服务控制接口')
    def test_windows_service_stop_and_failure(self):
        """正常停止更新系统状态；执行异常被记录并向系统传播。"""
        dependency = self.root / 'tool.exe'
        dependency.touch()
        for fail in (False, True):
            with self.subTest(fail=fail), ExitStack() as stack:
                service = windows_service.AssetService.__new__(windows_service.AssetService)
                service.stop = Event()
                service.ReportServiceStatus = Mock()
                started = Event()

                def execute(stop):
                    """模拟执行端等待停止或报告故障。"""
                    self.assertIs(stop, service.stop)
                    started.set()
                    if fail:
                        raise RuntimeError('simulated failure')
                    stop.wait(5)

                stack.enter_context(patch.dict(os.environ, {}, clear=True))
                stack.enter_context(patch.object(windows_service.shell, 'SHGetFolderPath',
                    return_value=str(self.root)))
                stack.enter_context(patch.object(windows_service.win32serviceutil,
                    'GetServiceCustomOption', return_value=str(dependency)))
                stack.enter_context(patch.object(task_runner, 'main', side_effect=execute))
                log = stack.enter_context(patch.object(windows_service.servicemanager, 'LogErrorMsg'))
                if fail:
                    with self.assertRaisesRegex(RuntimeError, 'simulated failure'):
                        service.SvcDoRun()
                    self.assertTrue(service.stop.is_set())
                    log.assert_called_once()
                else:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(service.SvcDoRun)
                        try:
                            self.assertTrue(started.wait(2))
                            service.SvcStop()
                            future.result(timeout=2)
                        finally:
                            service.stop.set()
                    service.ReportServiceStatus.assert_called_with(
                        windows_service.win32service.SERVICE_STOP_PENDING, waitHint=10000)
                    service.SvcShutdown()
                    log.assert_not_called()


    @unittest.skipUnless(os.name == 'nt', 'Windows 服务注册接口')
    def test_registration_configuration_and_rollback(self):
        """模拟服务注册，验证路径配置、重复注册保护和失败回滚。"""
        dependency = self.root / 'tool.exe'
        dependency.touch()
        self.assertEqual(windows_service.AssetService._svc_name_, register_service.SERVICE_NAME)
        self.assertEqual(windows_service.AssetService.__name__, register_service.SERVICE_CLASS)
        for case in ('success', 'existing', 'rollback'):
            with self.subTest(case=case), ExitStack() as stack:
                stack.enter_context(patch.object(register_service.ctypes.windll.shell32,
                    'IsUserAnAdmin', return_value=True))
                stack.enter_context(patch.multiple(service_config, BLENDER=dependency))
                api = {name: Mock() for name in ('OpenSCManager', 'OpenService', 'CreateService',
                    'ChangeServiceConfig2', 'DeleteService', 'CloseServiceHandle')}
                api['OpenSCManager'].return_value = 'manager'
                api['CreateService'].return_value = 'new'
                if case == 'existing':
                    api['OpenService'].return_value = 'existing'
                else:
                    api['OpenService'].side_effect = register_service.pywintypes.error(
                        1060, 'OpenService', 'not found')
                if case == 'rollback':
                    api['ChangeServiceConfig2'].side_effect = RuntimeError('configuration failed')
                stack.enter_context(patch.multiple(register_service.win32service, **api))
                stack.enter_context(patch.object(register_service.win32serviceutil,
                    'LocatePythonServiceExe', return_value='C:/fixture/pythonservice.exe'))
                bind = stack.enter_context(patch.object(register_service.win32serviceutil,
                    'InstallPythonClassString'))
                option = stack.enter_context(patch.object(register_service.win32serviceutil,
                    'SetServiceCustomOption'))
                if case == 'rollback':
                    with self.assertRaisesRegex(RuntimeError, 'configuration failed'):
                        register_service.main()
                    api['DeleteService'].assert_called_once_with('new')
                else:
                    register_service.main()
                    api['DeleteService'].assert_not_called()
                if case == 'existing':
                    api['CreateService'].assert_not_called()
                    option.assert_not_called()
                    bind.assert_not_called()
                else:
                    self.assertEqual(api['CreateService'].call_args.args[5],
                                     register_service.win32service.SERVICE_AUTO_START)
                    self.assertEqual(option.call_args_list[0].args,
                        (register_service.SERVICE_NAME, 'BLENDER_PATH', str(dependency)))
                    self.assertEqual(option.call_count, 1)
                    bind.assert_called_once()
                self.assertEqual(api['CloseServiceHandle'].call_count, 2)

if __name__ == '__main__':
    unittest.main(verbosity=2)
