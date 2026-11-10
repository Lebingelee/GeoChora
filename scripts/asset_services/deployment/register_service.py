# 作用：将资产执行端注册为自启 Windows 服务，配置异常恢复；不启动服务或提交任务。
# 输入输出：main() 读取下列固定配置，写入 Windows 服务注册信息；失败时撤销本次新建服务。
# 执行：用 runtime/trellis2/python.exe 在管理员终端运行本文件。
import ctypes
from pathlib import Path
import sys

import pywintypes
import win32service
import win32serviceutil
import winerror

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.service_config import ROOT, TRELLIS_PYTHON
PYTHON = TRELLIS_PYTHON
SERVICE_MODULE = ROOT / 'scheduler/windows_service.py'
SERVICE_CLASS = 'AssetService'
SERVICE_NAME = 'AssetGenerationService'
DISPLAY_NAME = 'Asset Generation Service'
DESCRIPTION = '本机资产生成任务服务，管理共享队列及 CPU/GPU 执行。'
# 使用 Windows 默认 LocalSystem；不创建账户或保存用户密码。
SERVICE_ACCOUNT = None


def main() -> None:
    """检查依赖后注册服务；已有同名服务保持原样，不自动启动。

    服务入口须定义 AssetService，并将 _svc_name_ 设为 SERVICE_NAME。
    异常退出时由 Windows 重启；管理员主动停止服务不会触发异常恢复。

    Returns:
        None: 输出注册结果；权限、依赖或系统操作失败时抛出异常。
    """
    if not SERVICE_MODULE.is_file():
        raise FileNotFoundError(f'尚缺服务运行入口：{SERVICE_MODULE}；未注册服务')
    if not PYTHON.is_file() or not Path(sys.executable).samefile(PYTHON):
        raise RuntimeError(f'请使用项目解释器运行本脚本：{PYTHON}')
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError('注册 Windows 服务需要管理员终端；本脚本不会自动提权')

    sys.path.insert(0, str(ROOT))
    from common.service_config import BLENDER
    if not BLENDER.is_file():
        raise FileNotFoundError(f'BLENDER_PATH 对应文件不存在：{BLENDER}')

    manager = win32service.OpenSCManager(
        None, None, win32service.SC_MANAGER_CONNECT | win32service.SC_MANAGER_CREATE_SERVICE)
    try:
        try:
            existing = win32service.OpenService(manager, SERVICE_NAME, win32service.SERVICE_QUERY_CONFIG)
        except pywintypes.error as error:
            if error.winerror != winerror.ERROR_SERVICE_DOES_NOT_EXIST:
                raise
        else:
            win32service.CloseServiceHandle(existing)
            print(f'{SERVICE_NAME} 已存在，未修改或启动')
            return

        # pywin32 将宿主及所需 DLL 放到当前 Python 环境中，不移动模型或业务代码。
        host = win32serviceutil.LocatePythonServiceExe()
        service = win32service.CreateService(
            manager, SERVICE_NAME, DISPLAY_NAME, win32service.SERVICE_ALL_ACCESS,
            win32service.SERVICE_WIN32_OWN_PROCESS, win32service.SERVICE_AUTO_START,
            win32service.SERVICE_ERROR_NORMAL, f'"{host}"',
            None, 0, None, SERVICE_ACCOUNT, None)
        try:
            # pywin32 支持绝对模块路径，服务启动不依赖终端的当前目录。
            class_path = str(SERVICE_MODULE.with_suffix('')) + '.' + SERVICE_CLASS
            win32serviceutil.InstallPythonClassString(class_path, SERVICE_NAME)
            win32serviceutil.SetServiceCustomOption(SERVICE_NAME, 'BLENDER_PATH', str(BLENDER))
            win32service.ChangeServiceConfig2(
                service, win32service.SERVICE_CONFIG_DESCRIPTION, DESCRIPTION)
            win32service.ChangeServiceConfig2(
                service, win32service.SERVICE_CONFIG_FAILURE_ACTIONS, {
                    'ResetPeriod': 86400,
                    'RebootMsg': '',
                    'Command': '',
                    'Actions': [(win32service.SC_ACTION_RESTART, delay)
                                for delay in (30000, 60000, 120000)],
                })
            win32service.ChangeServiceConfig2(
                service, win32service.SERVICE_CONFIG_FAILURE_ACTIONS_FLAG, True)
        except Exception:
            # 仅撤销本次创建的服务；不会删除此前已有的同名服务。
            win32service.DeleteService(service)
            raise
        finally:
            win32service.CloseServiceHandle(service)
    finally:
        win32service.CloseServiceHandle(manager)
    print(f'已注册 {SERVICE_NAME}：开机自启、异常恢复；当前尚未启动')


if __name__ == '__main__':
    main()
