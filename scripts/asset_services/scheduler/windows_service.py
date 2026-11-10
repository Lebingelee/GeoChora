# 作用：连接 Windows 服务控制管理器与资产执行循环，支持正常停止和关机通知。
# 输入输出：SvcDoRun() 运行执行端；SvcStop() 停止领取新阶段并等待在途阶段结束。
from concurrent.futures import ThreadPoolExecutor, wait
import os
from pathlib import Path
import sys
from threading import Event
import traceback

import servicemanager
import win32service
import win32serviceutil
from win32com.shell import shell, shellcon

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduler import task_runner


class AssetService(win32serviceutil.ServiceFramework):
    """承接系统启停通知；不向 MCP 暴露服务管理接口。"""
    _svc_name_ = 'AssetGenerationService'
    _svc_display_name_ = 'Asset Generation Service'

    def __init__(self, args):
        """建立服务控制通道和共享停止事件。"""
        self.stop = Event()
        super().__init__(args)

    def SvcStop(self):
        """停止领取新任务，并向系统报告正在等待当前阶段收尾。"""
        self.stop.set()
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=10000)

    def SvcShutdown(self):
        """系统关机时请求正常停止；最终退出期限由 Windows 决定。"""
        self.SvcStop()

    def SvcDoRun(self):
        """运行执行端，停机期间持续更新状态；异常交由系统恢复策略处理。

        Returns:
            None: 当前阶段已收尾、执行线程退出；异常写入系统事件日志后重新抛出。
        """
        try:
            blender = win32serviceutil.GetServiceCustomOption(self, 'BLENDER_PATH')
            if not blender or not Path(blender).is_file():
                raise FileNotFoundError('服务配置缺少有效的 BLENDER_PATH，请检查注册配置')
            os.environ['BLENDER_PATH'] = blender
            # Blender 子进程要求在本账户 LocalAppData 的 Temp 目录中创建工作目录。
            local_app_data = os.environ.get('LOCALAPPDATA') or shell.SHGetFolderPath(
                0, shellcon.CSIDL_LOCAL_APPDATA, None, 0)
            os.environ['LOCALAPPDATA'] = local_app_data
            (Path(local_app_data) / 'Temp').mkdir(parents=True, exist_ok=True)
            with ThreadPoolExecutor(max_workers=1) as executor:
                execution = executor.submit(task_runner.main, self.stop)
                while not execution.done():
                    wait([execution], timeout=5)
                    if self.stop.is_set():
                        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=10000)
                execution.result()
        except Exception:
            self.stop.set()
            servicemanager.LogErrorMsg(traceback.format_exc())
            raise
