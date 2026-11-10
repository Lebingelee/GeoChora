# 作用：独立验证三个本机资产 MCP 的真实模型请求，保留 CUDA OOM 的原始失败事实。
# 输入输出：已初始化环境与公开样例 -> workspace/asset-services/evidence/live-*/report.json。
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import numpy as np
import psutil
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.service_config import ROOT, DEPENDENCIES, TRELLIS_BACKEND, TRELLIS_PYTHON

DIRECTORY = DEPENDENCIES / "evidence" / ("live-" + uuid.uuid4().hex[:12])
TIMEOUT_SECONDS = 1800
OOM = re.compile(r"(?:torch(?:\.cuda)?\.OutOfMemoryError:|RuntimeError: CUDA out of memory)")


def unpack(response):
    """提取 MCP 返回值，工具协议错误直接报告。"""
    if response.isError:
        raise RuntimeError(str(response))
    return response.structuredContent or json.loads(response.content[0].text)


async def run_case(name, service, tool, request):
    """提交独立真实请求，检查产物或记录明确的 CUDA OOM。"""
    row = {"case": name, "request": request, "deployment": "FAILED"}
    parameters = StdioServerParameters(command=str(TRELLIS_PYTHON),
        args=[str(ROOT / "services" / service / "server.py")],
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1"})
    try:
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=TIMEOUT_SECONDS)) as session:
                await session.initialize()
                row["tools"] = [item.name for item in (await session.list_tools()).tools]
                expected = {"get_job", "wait_job", "submit_job"} | ({"submit_remesh"} if service == "texture" else set())
                assert set(row["tools"]) == expected
                submitted = unpack(await session.call_tool(tool, request))
                row["job_id"] = submitted["job_id"]
                print(f"{name}: 已提交真实任务 {submitted['job_id']}", flush=True)
                result = unpack(await asyncio.wait_for(session.call_tool("wait_job", submitted), TIMEOUT_SECONDS))
                row["raw_job"] = result
                if result["status"] != "succeeded":
                    logs = "\n".join(item.get("log", "") for item in result.get("result", []) if item)
                    # 必须来自真实模型 worker 的 traceback；其他错误保留为失败。
                    if (OOM.search(logs) and "CUDA out of memory" in logs
                            and "Traceback (most recent call last)" in logs):
                        row["deployment"] = "DEPLOYED_OOM"
                        return row
                    raise RuntimeError(result.get("error") or result)
                artifacts = result["output"]["artifacts"]
                assert artifacts
                for role, raw_path in artifacts.items():
                    path = Path(raw_path)
                    assert path.is_file() and path.stat().st_size > 0, role
                    if path.suffix == ".npz":
                        with np.load(path) as mesh:
                            assert len(mesh["faces"]) > 0 and np.isfinite(mesh["vertices"]).all()
                    elif path.suffix == ".glb":
                        scene = trimesh.load(path, force="scene")
                        assert scene.geometry and all(len(mesh.faces) > 0 for mesh in scene.geometry.values())
                        if name in {"trellis2", "texture"}:
                            assert all(getattr(mesh.visual.material, "baseColorTexture", None) is not None
                                       for mesh in scene.geometry.values())
                row["deployment"] = "DEPLOYED_GENERATED"
    except Exception as error:
        row["error"] = {"type": type(error).__name__, "message": str(error)}
    return row


async def main():
    """检查 CUDA 栈后独立调用四条生成路线，最后清理本次启动的执行端。

    Returns:
        None: 保存原始任务及逐项部署结论；任一其他故障使进程非零退出。
    """
    DIRECTORY.mkdir(parents=True)
    with (DIRECTORY / "cuda.log").open("w", encoding="utf-8") as log:
        subprocess.run([str(TRELLIS_PYTHON), str(Path(__file__).with_name("verify_linux_cuda.py"))],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    mesh = trimesh.creation.box(extents=(0.1, 0.08, 0.15))
    coarse = DIRECTORY / "coarse.npz"
    np.savez_compressed(coarse, vertices=mesh.vertices.astype(np.float32), faces=mesh.faces.astype(np.int32))
    image = TRELLIS_BACKEND / "assets/example_image/T.png"
    assert image.is_file()
    log = (DIRECTORY / "runner.log").open("w", encoding="utf-8")
    runner = subprocess.Popen([str(TRELLIS_PYTHON), str(ROOT / "scheduler/task_runner.py")],
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    cases = [("trellis2", "trellis2", "submit_job", {"image_path": str(image)}),
             ("ultrashape", "ultrashape", "submit_job", {"mesh_path": str(coarse), "image_path": str(image)}),
             ("remesh", "texture", "submit_remesh", {"mesh_path": str(coarse), "resolution": 512}),
             ("texture", "texture", "submit_job", {"mesh_path": str(coarse), "image_path": str(image)})]
    report = {"schema_version": "asset-mcp-deployment-v1", "cuda_stack_passed": True,
              "model_defaults_unchanged": True, "rows": []}
    try:
        for name, service, tool, request in cases:
            request["output_dir"] = str(DIRECTORY / name)
            row = await run_case(name, service, tool, request)
            report["rows"].append(row)
            (DIRECTORY / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"{name}: {row['deployment']}", flush=True)
    finally:
        try:
            process = psutil.Process(runner.pid)
            children = process.children(recursive=True)
            for child in reversed(children):
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            process.terminate()
            _, alive = psutil.wait_procs([*children, process], timeout=10)
            for child in alive:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(alive, timeout=5)
        except psutil.NoSuchProcess:
            pass
        log.close()
    report["passed"] = all(row["deployment"] in {"DEPLOYED_GENERATED", "DEPLOYED_OOM"} for row in report["rows"])
    (DIRECTORY / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"部署结果：{DIRECTORY / 'report.json'}")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
