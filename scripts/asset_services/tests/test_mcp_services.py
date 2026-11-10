# 作用：通过真实 stdio MCP 验证三个独立入口的提交、查询、单任务等待与参数拒绝。
# 输入输出：使用隔离数据库及模拟脚本，验证协议到子进程的完整路径，不加载模型。
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduler import task_queue
from scheduler import task_runner
from scheduler.task_files import working_directory

SERVICES = {'services.trellis2.server': 'trellis2', 'services.ultrashape.server': 'ultrashape',
            'services.texture.server': 'trellis-texturing'}


@asynccontextmanager
async def connect_server(module, directory, worker):
    """启动独立 MCP 子进程并初始化真实协议连接。"""
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name('mcp_fixture_server.py')), module,
              str(directory), str(worker)],
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONNOUSERSITE': '1'},
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as session:
            initialized = await session.initialize()
            assert initialized.serverInfo.name == SERVICES[module]
            yield session


def unpack(response):
    """拒绝工具错误并提取结构化结果。"""
    if response.isError:
        raise AssertionError(response)
    return response.structuredContent or json.loads(response.content[0].text)


class MCPTests(unittest.IsolatedAsyncioTestCase):
    """验证三个实际服务只暴露约定接口并共享本机队列。"""

    def setUp(self):
        """准备临时输入、模拟执行脚本与隔离队列。"""
        temporary = tempfile.TemporaryDirectory(prefix='asset-mcp-test-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        paths = patch.multiple(task_queue, DB_PATH=self.directory / 'tasks.sqlite3')
        paths.start()
        self.addCleanup(paths.stop)
        task_queue.initialize()
        self.image = self.directory / '参考 image.png'
        self.mesh = self.directory / '模型 mesh.npz'
        self.image.touch()
        self.mesh.touch()
        self.worker = self.directory / '模拟 worker.py'
        self.worker.write_text(
            "import json, pathlib, sys\n"
            "args = sys.argv[1:]\n"
            "if '--mesh_path' in args:\n"
            "    assert pathlib.Path(args[args.index('--mesh_path') + 1]).is_file()\n"
            "pathlib.Path('arguments.json').write_text(json.dumps(args), encoding='utf-8')\n"
            "result = {'artifacts': {'arguments': str(pathlib.Path('arguments.json').resolve())}, 'metadata': {}}\n"
            "pathlib.Path('result.json').write_text(json.dumps(result), encoding='utf-8')\n",
            encoding='utf-8',
        )

        self.exporter = self.directory / 'export_worker.py'
        self.exporter.write_text(
            "import json, pathlib\n"
            "path = pathlib.Path('result.json')\n"
            "result = json.loads(path.read_text())\n"
            "pathlib.Path('textured.blend').write_bytes(b'fixture')\n"
            "result['artifacts']['blend'] = str(pathlib.Path('textured.blend').resolve())\n"
            "path.write_text(json.dumps(result), encoding='utf-8')\n", encoding='utf-8')
        self.remesh = self.directory / 'remesh_worker.py'
        self.remesh.write_text(
            "import json, pathlib, sys\n"
            "args = sys.argv[1:]\n"
            "source = pathlib.Path(args[args.index('--mesh_path') + 1])\n"
            "output = pathlib.Path('remeshed.npz')\n"
            "output.write_bytes(b'mesh fixture')\n"
            "pathlib.Path('remesh_arguments.json').write_text(json.dumps(args), encoding='utf-8')\n"
            "pathlib.Path('result.json').write_text(json.dumps({'artifacts': {'mesh': str(output.resolve())}, 'metadata': {}}), encoding='utf-8')\n",
            encoding='utf-8',
        )

    def request(self, module):
        """返回指定服务的最小合法框架参数。"""
        request = {'image_path': str(self.image), 'output_dir': str(self.directory / uuid.uuid4().hex)}
        if module != 'services.trellis2.server':
            request['mesh_path'] = str(self.mesh)
        return request

    async def test_independent_tools_and_missing_worker(self):
        """验证每个服务独立启动、工具清单准确，脚本未接入时明确拒绝入队。"""
        for module in SERVICES:
            async with connect_server(module, self.directory, '-') as session:
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                self.assertEqual(set(tools), {'submit_job', 'get_job', 'wait_job'} |
                                 ({'submit_remesh'} if module == 'services.texture.server' else set()))
                if module == 'services.texture.server':
                    self.assertNotIn('target_quad_count', tools['submit_job'].inputSchema['properties'])
                    self.assertEqual(set(tools['submit_remesh'].inputSchema['required']),
                                     {'mesh_path', 'resolution', 'output_dir'})
                self.assertEqual(tools['wait_job'].inputSchema['properties']['job_id']['type'], 'integer')
                response = await session.call_tool('submit_job', self.request(module))
                self.assertTrue(response.isError)
                self.assertIsNone(task_queue.dequeue('gpu'))
                self.assertIsNone(task_queue.dequeue('cpu'))
                for name in ['get_job', 'wait_job']:
                    response = await session.call_tool(name, {'job_id': 999})
                    self.assertTrue(response.isError)

    async def test_shared_queue_and_single_wait(self):
        """验证多服务受理独立任务、真实执行，以及等待期间仍可查询和提交。"""
        async with AsyncExitStack() as stack:
            sessions = {module: await stack.enter_async_context(
                connect_server(module, self.directory, self.worker)) for module in SERVICES}
            submitted = []
            for module, session in sessions.items():
                for _ in range(2):
                    job = unpack(await session.call_tool('submit_job', self.request(module)))
                    submitted.append((module, job['job_id']))
            identifiers = [identifier for _, identifier in submitted]
            self.assertEqual(len(set(identifiers)), 6)
            module, target = submitted[-1]
            session = sessions[module]
            pending = asyncio.create_task(session.call_tool('wait_job', {'job_id': target}))
            try:
                await asyncio.sleep(0.1)
                extra = unpack(await asyncio.wait_for(
                    session.call_tool('submit_job', self.request(module)), timeout=5))
                task = unpack(await session.call_tool('get_job', {'job_id': target}))
                self.assertEqual(task['status'], 'queued')
                self.assertNotIn('argv', task)
                first = await asyncio.to_thread(task_runner.run_next, 'gpu')
                self.assertEqual(first['id'], identifiers[0])
                await asyncio.sleep(0.35)
                self.assertFalse(pending.done(), '其他任务结束不能触发目标等待返回')
                for service, identifier in submitted[1:]:
                    completed = await asyncio.to_thread(task_runner.run_next, 'gpu')
                    self.assertEqual(completed['id'], identifier)
                    if service == 'services.texture.server':
                        self.assertEqual(completed['status'], 'queued')
                        if identifier == target:
                            await asyncio.sleep(0.35)
                            self.assertFalse(pending.done(), '打包完成前不能返回成功')
                        completed = await asyncio.to_thread(task_runner.run_next, 'cpu')
                    self.assertEqual(completed['status'], 'succeeded')
                result = unpack(await asyncio.wait_for(pending, timeout=5))
                self.assertEqual(result['job_id'], target)
                self.assertEqual(result['status'], 'succeeded')
                self.assertEqual(task_queue.get_task(extra['job_id'])['status'], 'queued')
                self.assertEqual(unpack(await session.call_tool('get_job', {'job_id': target})), result)
                self.assertEqual(unpack(await session.call_tool('wait_job', {'job_id': target})), result)
                self.assertTrue(Path(result['output']['artifacts']['arguments']).is_file())
                self.assertEqual(result['output_dir'], task_queue.get_task(target)['output_dir'])
                self.assertFalse(working_directory(target).exists())
                self.assertEqual(result['step_count'], 2)
                self.assertEqual(len(result['result']), 2)
                self.assertIsNone(await asyncio.to_thread(task_runner.run_next, 'cpu'))
                self.assertEqual((await asyncio.to_thread(task_runner.run_next, 'gpu'))['id'], extra['job_id'])
                self.assertEqual((await asyncio.to_thread(task_runner.run_next, 'cpu'))['id'], extra['job_id'])
            finally:
                # 若断言失败，结束目标任务使服务端等待线程可退出，再关闭连接。
                with task_queue._connect() as connection:
                    connection.execute(
                        "UPDATE tasks SET status='failed', error='test cleanup' "
                        "WHERE id=? AND status IN ('queued','running')", (target,))
                if not pending.done():
                    await asyncio.wait_for(pending, timeout=5)
            for module, identifier in submitted:
                arguments = json.loads((Path(task_queue.get_task(identifier)['output_dir']) / 'arguments.json').read_text())
                self.assertEqual(arguments[arguments.index('--image_path') + 1], str(self.image))
                if module == 'services.ultrashape.server':
                    self.assertEqual(arguments[arguments.index('--mesh_path') + 1], str(self.mesh))
                if module == 'services.texture.server':
                    self.assertEqual(arguments[arguments.index('--mesh_path') + 1], str(self.mesh))
                    self.assertNotIn('--target_quad_count', arguments)
                    index = arguments.index('--guidance_interval')
                    self.assertEqual(arguments[index + 1:index + 3], ['0.6', '0.9'])


    async def test_independent_stage_dependencies(self):
        """验证两类提交互不依赖对方脚本；重拓扑不需要图片且有独立终态。"""
        for missing, available_tool, unavailable_tool in [
            (self.remesh, 'submit_job', 'submit_remesh'),
            (self.worker, 'submit_remesh', 'submit_job'),
        ]:
            content = missing.read_text(encoding='utf-8')
            missing.unlink()
            requests = {
                'submit_job': self.request('services.texture.server'),
                'submit_remesh': {'mesh_path': str(self.mesh), 'resolution': 512, 'decimation_target': 12000,
                                  'output_dir': str(self.directory / uuid.uuid4().hex)},
            }
            try:
                async with connect_server('services.texture.server', self.directory, self.worker) as session:
                    rejected = await session.call_tool(unavailable_tool, requests[unavailable_tool])
                    self.assertTrue(rejected.isError)
                    job = unpack(await session.call_tool(available_tool, requests[available_tool]))
                    self.assertIsNone(await asyncio.to_thread(task_runner.run_next, 'cpu'))
                    completed = await asyncio.to_thread(task_runner.run_next, 'gpu')
                    self.assertEqual(completed['id'], job['job_id'])
                    self.assertEqual(completed['status'], 'queued')
                    await asyncio.to_thread(task_runner.run_next, 'cpu')
                    result = unpack(await session.call_tool('wait_job', job))
                    self.assertEqual((result['status'], result['step_count']), ('succeeded', 2))
                    self.assertTrue(Path(result['output']['artifacts']['blend']).is_file())
            finally:
                missing.write_text(content, encoding='utf-8')

    async def test_export_failure(self):
        """验证贴图成功但打包失败时，整项任务报告失败。"""
        self.exporter.write_text("raise SystemExit(8)\n", encoding='utf-8')
        async with connect_server('services.texture.server', self.directory, self.worker) as session:
            job = unpack(await session.call_tool('submit_job', self.request('services.texture.server')))
            self.assertEqual((await asyncio.to_thread(task_runner.run_next, 'gpu'))['status'], 'queued')
            await asyncio.to_thread(task_runner.run_next, 'cpu')
            result = unpack(await session.call_tool('wait_job', job))
            self.assertEqual(result['status'], 'failed')
            self.assertIsNone(result['output'])
            self.assertEqual(result['result'][-1]['returncode'], 8)

    async def test_texture_remesh_failure(self):
        """验证独立重拓扑在 GPU 阶段失败后不会执行打包。"""
        self.remesh.write_text("raise SystemExit(7)\n", encoding='utf-8')
        async with connect_server('services.texture.server', self.directory, self.worker) as session:
            job = unpack(await session.call_tool('submit_remesh', {
                'mesh_path': str(self.mesh), 'resolution': 512, 'decimation_target': 12000,
                'output_dir': str(self.directory / uuid.uuid4().hex)}))
            self.assertIsNone(await asyncio.to_thread(task_runner.run_next, 'cpu'))
            failed = await asyncio.to_thread(task_runner.run_next, 'gpu')
            self.assertEqual(failed['id'], job['job_id'])
            result = unpack(await session.call_tool('wait_job', job))
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['current_step'], 0)
            self.assertEqual(result['result'][0]['returncode'], 7)
            self.assertIsNone(await asyncio.to_thread(task_runner.run_next, 'gpu'))
            directory = working_directory(job['job_id'])
            self.assertFalse((directory / 'arguments.json').exists())

    async def test_reject_invalid_parameters(self):
        """验证参数范围、缺失文件和贴图必填字段在入队前被拒绝。"""
        for module in SERVICES:
            async with connect_server(module, self.directory, self.worker) as session:
                request = self.request(module)
                missing = {key: value for key, value in request.items() if key != 'output_dir'}
                self.assertTrue((await session.call_tool('submit_job', missing)).isError)
                overrides = [{'output_dir': str(self.directory)}, {'output_dir': 'relative'},
                             {'seed': -1}, {'resolution': 256},
                             {'image_path': str(self.directory / 'missing.png')}]
                if module != 'services.trellis2.server':
                    overrides += [{'steps': 0}, {'mesh_path': 'relative.npz'}]
                if module == 'services.texture.server':
                    overrides += [{'guidance_interval': [0.9, 0.1]}]
                    for invalid in ({}, {'resolution': 17}, {'resolution': 512, 'decimation_target': 99},
                                    {'resolution': 512, 'remesh_band': 0},
                                    {'resolution': 512, 'remesh_project': 1.1}):
                        remesh = {'mesh_path': str(self.mesh), 'output_dir': str(self.directory / uuid.uuid4().hex), **invalid}
                        self.assertTrue((await session.call_tool('submit_remesh', remesh)).isError)
                for override in overrides:
                    response = await session.call_tool('submit_job', {**request, **override})
                    self.assertTrue(response.isError, (module, override))
        self.assertIsNone(task_queue.dequeue('gpu'))
        self.assertIsNone(task_queue.dequeue('cpu'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
