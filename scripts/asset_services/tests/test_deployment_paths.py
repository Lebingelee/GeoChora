# 作用：在带空格及中文的新源码位置验证部署路径和真实 MCP 工具发现。
# 输入输出：临时源码副本及独立运行目录 -> 路径断言；不读取已准备的模型或原服务数据库。
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SOURCE = Path(__file__).resolve().parents[1]
PROBE = """
import json,sys
sys.path.insert(0,sys.argv[1])
from common.service_config import ROOT,DEPENDENCIES,TRELLIS_PYTHON,ULTRASHAPE_PYTHON
from scheduler.task_queue import DB_PATH
from deployment.prepare_sources import DESTINATION
print(json.dumps({k:str(v) for k,v in dict(root=ROOT,home=DEPENDENCIES,trellis=TRELLIS_PYTHON,
    ultrashape=ULTRASHAPE_PYTHON,database=DB_PATH,sources=DESTINATION).items()}))
"""


class DeploymentPathTests(unittest.IsolatedAsyncioTestCase):
    """保护接收方 checkout 和运行目录的独立性。"""

    def setUp(self):
        """仅复制服务源码，创建没有模型和旧环境的新目录。"""
        self.temporary = tempfile.TemporaryDirectory(prefix='mcp-relocation-')
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / '新 checkout with spaces'
        self.source = self.repo / 'scripts/asset_services'
        shutil.copytree(SOURCE, self.source, ignore=shutil.ignore_patterns('__pycache__', 'tests'))
        self.home = Path(self.temporary.name) / 'independent runtime'
        self.environment = {**os.environ, 'ASSET_SERVICES_HOME': str(self.home),
                            'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'}

    async def test_default_and_explicit_runtime_roots(self):
        """源码移动后默认路径跟随新 checkout，显式运行目录也不回退旧位置。"""
        for explicit in (True, False):
            environment = dict(self.environment)
            expected = self.home if explicit else self.repo / 'workspace/asset-services'
            if not explicit:
                environment.pop('ASSET_SERVICES_HOME')
            output = await asyncio.to_thread(subprocess.check_output, [sys.executable, '-c', PROBE, str(self.source)],
                                             env=environment, cwd=self.repo, text=True, encoding='utf-8')
            value = json.loads(output)
            self.assertEqual(Path(value['root']), self.source.resolve())
            self.assertEqual(Path(value['home']), expected.resolve())
            self.assertEqual(Path(value['database']), expected / 'data/tasks.sqlite3')
            self.assertEqual(Path(value['sources']), expected / 'third_party')
            self.assertTrue(Path(value['trellis']).is_relative_to(expected))
            self.assertTrue(Path(value['ultrashape']).is_relative_to(expected))

    async def test_real_protocol_from_relocated_source(self):
        """三个新位置入口可枚举工具，并只初始化新的本机数据库。"""
        for service in ('trellis2', 'ultrashape', 'texture'):
            parameters = StdioServerParameters(command=sys.executable,
                args=[str(self.source / 'services' / service / 'server.py')], env=self.environment)
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as session:
                    await session.initialize()
                    actual = {item.name for item in (await session.list_tools()).tools}
                    expected = {'get_job', 'wait_job', 'submit_job'} | ({'submit_remesh'} if service == 'texture' else set())
                    self.assertEqual(actual, expected)
        self.assertTrue((self.home / 'data/tasks.sqlite3').is_file())
        self.assertFalse((self.home / 'models').exists())


if __name__ == '__main__':
    unittest.main()
