# 作用：通过真实 MCP 和一次最小 Codex 会话验证本机编排服务部署。
# 输入输出：本机 Codex 登录和默认模型 -> workspace/scene-generation/deployment-check.json。
import asyncio
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import runtime

EXPECTED = "GeoChora MCP deployment OK\n"
PROMPT = ('只在当前工作目录创建文件 mcp-deployment-ok.txt，内容精确为 "GeoChora MCP deployment OK" 并以换行结尾。'
          '只完成这个文件操作，不读取其他目录，不修改其他文件，不调用外部服务。完成后简短确认。')
REPORT = Path(runtime.REPO) / "deployment-check.json"
TIMEOUT_SECONDS = 300


def unpack(response):
    """读取 MCP 结构化结果并保留受控错误。"""
    if response.isError:
        raise RuntimeError(str(response))
    result = response.structuredContent or json.loads(response.content[0].text)
    if "error" in result:
        raise RuntimeError(str(result["error"]))
    return result


async def main():
    """提交一个独立文件创建任务，核对状态、实际产物与 Skill 来源。

    Returns:
        None: 保存部署验证收据；超时、会话失败或产物不匹配直接抛出。
    """
    environment = {**os.environ, "PYTHONPATH": str(runtime.CORE_ROOT / "scripts"), "PYTHONIOENCODING": "utf-8"}
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "orchestrator.server"], env=environment)
    report = {"schema_version": "orchestrator-deployment-v1", "passed": False,
              "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(), "agents_source": runtime.AGENTS_SOURCE}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=60)) as session:
                await session.initialize()
                tools = [tool.name for tool in (await session.list_tools()).tools]
                assert set(tools) == {"start_batch", "get_status", "list_batches", "wait_for_change", "cancel_run"}
                report["tools"] = tools
                batch = unpack(await session.call_tool("start_batch", {
                    "prompt": PROMPT, "count": 1, "max_parallel": 1,
                    "model": runtime.DEFAULT_MODEL, "effort": "low"}))
                report["batch"] = batch
                deadline = time.monotonic() + TIMEOUT_SECONDS
                revision = batch["revision"]
                while time.monotonic() < deadline:
                    status = unpack(await session.call_tool("wait_for_change", {
                        "batch_id": batch["batch_id"], "after_revision": revision, "timeout_seconds": 30}))
                    report["status"] = status
                    print(json.dumps(status, ensure_ascii=False), flush=True)
                    revision = status["revision"]
                    if status["finished"]:
                        break
                else:
                    await session.call_tool("cancel_run", {"run_id": batch["run_ids"][0]})
                    raise TimeoutError("编排部署测试超时，已请求取消本次会话")
                assert [run["state"] for run in status["runs"]] == ["completed"], status
                store = runtime.Store()
                try:
                    row = store.row(batch["run_ids"][0])
                    directory = Path(row["directory"]).resolve()
                finally:
                    store.connection.close()
                assert directory.is_relative_to(Path(runtime.REPO).resolve())
                content = (directory / "mcp-deployment-ok.txt").read_text(encoding="utf-8")
                assert content == EXPECTED, repr(content)
                assert (directory / ".agents/skills/scene-orchestration/SKILL.md").is_file()
                report.update(passed=True, artifact=str(directory / "mcp-deployment-ok.txt"),
                              artifact_sha256=hashlib.sha256(content.encode()).hexdigest())
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
