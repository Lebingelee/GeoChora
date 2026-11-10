# 作用：验证迁移后的本机控制协议、Windows 连接认证与独占 daemon 锁。
# 输入输出：临时目录、真实本机连接与空状态库 -> unittest 结果；不启动模型会话。
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import Invalid, runtime
from orchestrator.server import register


class DeploymentTests(unittest.IsolatedAsyncioTestCase):
    """检查跨平台部署接缝，不改变真实编排记录。"""

    async def asyncSetUp(self):
        """为真实 daemon 建立独立状态与控制目录。"""
        self.temporary = tempfile.TemporaryDirectory(prefix='orchestrator-test-')
        self.root = Path(self.temporary.name)
        self.settings = patch.multiple(runtime, STATE=str(self.root / 'state'), REPO=str(self.root / 'jobs'),
            RUNTIME=str(self.root), SOCKET=str(self.root / 'control.sock'), ENDPOINT=str(self.root / 'control.json'),
            DAEMON_LOCK=str(self.root / 'daemon.lock'), DAEMON_PID=str(self.root / 'daemon.pid'),
            DAEMON_LOG=str(self.root / 'daemon.log'), _SHARED_STORE=None)
        self.settings.start()
        self.store = runtime.Store(state=self.root / 'state', database=self.root / 'state.sqlite3')
        self.daemon = runtime.Daemon(self.store)
        self.task = asyncio.create_task(self.daemon.serve())
        endpoint = Path(runtime.ENDPOINT if os.name == 'nt' else runtime.SOCKET)
        for _ in range(100):
            if endpoint.exists():
                break
            if self.task.done():
                await self.task
            await asyncio.sleep(.02)
        self.assertTrue(endpoint.exists())

    async def asyncTearDown(self):
        """关闭测试 daemon 和库，再恢复模块设置。"""
        await self.daemon.shutdown()
        await asyncio.wait_for(self.task, timeout=5)
        self.store.connection.close()
        self.settings.stop()
        self.temporary.cleanup()

    async def test_control_and_exclusive_lock(self):
        """真实控制调用可读空批次，第二个 daemon 无法取得同一锁。"""
        result = await asyncio.to_thread(runtime.control, 'list', {})
        self.assertEqual(result, {'batches': []})
        self.assertTrue(await asyncio.to_thread(runtime.daemon_running))
        second = runtime.Daemon(self.store)
        with self.assertRaises(Invalid) as failure:
            await second.serve()
        self.assertEqual(failure.exception.code, 'manager_unavailable')

    @unittest.skipUnless(os.name == 'nt', 'Windows loopback 连接认证')
    async def test_reject_wrong_control_token(self):
        """错误令牌不能通过本机端口提交控制请求。"""
        endpoint = json.loads(Path(runtime.ENDPOINT).read_text(encoding='utf-8'))
        reader, writer = await asyncio.open_connection('127.0.0.1', endpoint['port'])
        writer.write(b'{"operation":"list","args":{},"token":"wrong"}\n')
        await writer.drain()
        result = json.loads(await reader.readline())
        writer.close()
        await writer.wait_closed()
        self.assertEqual(result['error']['code'], 'manager_unavailable')
        self.assertNotIn('result', result)

    async def test_registration_dry_run_has_no_filesystem_effect(self):
        """全新配置目录的预览也不能创建目录或备份。"""
        config = self.root / 'not-created/config.toml'
        result = register(config_path=str(config), backup_path=str(self.root / 'backup.toml'), dry_run=True)
        self.assertTrue(result['changed'])
        self.assertIn('[mcp_servers.experiment-batch]', result['content'])
        self.assertFalse(config.parent.exists())
        self.assertFalse((self.root / 'backup.toml').exists())


if __name__ == '__main__':
    unittest.main()
