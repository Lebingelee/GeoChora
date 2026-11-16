"""stdio MCP 入口。对外只暴露窄工具面，绝不返回会话正文。

用法（必须以模块方式启动，包父目录即实验仓库根）：
    将仓库 scripts/ 加入 PYTHONPATH 后启动：
    python -m orchestrator.server              以 stdio 提供 MCP（供 DSH 注册）
    python -m orchestrator.server --daemon     前台运行常驻调度器
    python -m orchestrator.server --register   在 codex 的 config.toml 里注册本服务
    python -m orchestrator.server --inspect ID 本地调试用（不在 MCP 工具面内）

上下文隔离契约（本服务存在的理由）：
所有工具只返回编号、状态与裁决，不提供会话正文、摘要、日志、图片或历史。
completed 仅表示本轮 agent 已结束，不表示实验通过验收。

重要函数：
- build_server(): 构造 FastMCP 实例并注册 5 个工具，返回实例。
- registered_tools(): 返回 build_server() 注册的工具名列表（校验用）。
- main(): 按 argv 分派 stdio / --daemon / --register / --inspect。
"""

import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile

from mcp.server.fastmcp import FastMCP

# 绝对导入（本模块以 `python -m orchestrator.server` 启动）：包父目录需在 sys.path 上。
# runtime 必须在函数内部延迟导入——runtime 与 judge 互相模块级导入，
# 顶层导入会触发循环导入失败；延迟导入同时让工具面在 daemon 未就绪时仍可枚举。
from orchestrator import Invalid

# 服务名与对统筹 agent 可见的 instructions。
SERVER_NAME = "experiment-batch"

INSTRUCTIONS = """批次会话服务：start_batch 直接接收任务文本、数量、模型和强度。
自动建立独立目录、复制 .agents，随后启动独立 codex 会话。
用 wait_for_change 等待，get_status 查询；仅返回编号、状态与错误码。
completed 只表示对话结束，不判断任务产物或业务成败。
worker 正文和会话内部编号不会出现在工具返回中。
"""

# 本模块名：--register 时以 -m 形式写进 config.toml。
MODULE_NAME = "orchestrator.server"

# 生产区根（worker 工作目录集中地）与状态根：与 runtime.REPO / runtime.STATE 同默认值。
# 此处不导入 runtime —— --register 是纯本地配置操作，不应依赖调度栈。
REPO = os.environ.get("ORCHESTRATOR_REPO", str(Path(__file__).resolve().parents[2] / "workspace/scene-generation"))
STATE = os.environ.get("ORCHESTRATOR_STATE", os.path.join(REPO, ".orchestrator"))

# 代码所在目录（开发仓库 scripts/）：与生产区 REPO 刻意分离。
# PYTHONPATH 必须指向这里，子进程才能以 -m 找到 orchestrator 包；
# ORCHESTRATOR_REPO 则指向生产区。二者不同，勿混用。
CODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# codex 的配置文件位置与注册段名。
CODEX_DIR = os.environ.get("CODEX_HOME", os.path.join(os.path.expanduser("~"), ".codex"))
CODEX_CONFIG = os.path.join(CODEX_DIR, "config.toml")
CODEX_CONFIG_BACKUP = os.path.join(CODEX_DIR, "config.before-experiment-batch.toml")
MCP_SECTION = "mcp_servers.experiment-batch"

# wait_for_change 最长 86400 秒，工具超时留出余量。
TOOL_TIMEOUT_SEC = 86520


def _call(operation, args):
    """调用 runtime.control，并把受控错误转成 error dict。

    Invalid 与任何未预期异常都不会跨越 MCP 边界泄露 traceback：
    未预期异常统一折叠为 manager_unavailable（daemon 未起或 socket 不可用）。
    """
    try:
        # 延迟导入在 try 内：runtime 的循环导入/未就绪也必须折叠成受控错误。
        from orchestrator import runtime

        return runtime.control(operation, args)
    except Invalid as exc:
        # 只回传预定义 code 与简短 message，绝不带堆栈。
        return {"error": {"code": exc.code, "message": exc.message}}
    except Exception as exc:  # noqa: BLE001 - 兜底，避免 traceback 泄露
        return {"error": {"code": "manager_unavailable", "message": str(exc)[:200]}}


def build_server():
    """构造 FastMCP 实例并注册全部工具。

    Returns:
        FastMCP: 已注册 5 个窄工具的实例；每个工具都只是
        control(<op>, args) 的薄封装，返回值必为 dict。
    """
    server = FastMCP(SERVER_NAME, instructions=INSTRUCTIONS)

    @server.tool()
    def start_batch(prompt: str, count: int = 1, model: str = "gpt-6-astra",
                    effort: str = "high", max_parallel: int = 10) -> dict:
        """创建 count 个独立会话并输入相同任务；返回批次和 run 编号。"""
        return _call("start", {"prompt": prompt, "count": count,
                               "model": model, "effort": effort,
                               "max_parallel": max_parallel})

    @server.tool()
    def get_status(batch_id: str) -> dict:
        """读取指定批次的当前状态快照（编号、状态、错误码）。

        返回值：{"batch_id", "revision", "counts": {queued/running/completed/failed},
        "runs": [{"id","name","attempt","state","error_code"}]}

        注意：state=completed 不代表产物通过验收。
        不返回：线程编号、目录、正文、日志。
        """
        return _call("status", {"batch_id": batch_id})

    @server.tool()
    def list_batches() -> dict:
        """列出最近至多 100 个批次的编号与状态计数，便于总控发现历史批次。

        返回值：{"batches": [{"batch_id": str, "revision": int, "counts": {...}}]}

        不返回：run 明细、worker 正文、日志、图片。
        """
        return _call("list", {})

    @server.tool()
    def wait_for_change(batch_id: str, after_revision: int = 0,
                        timeout_seconds: float = 300) -> dict:
        """阻塞等待批次状态发生变化或全部结束；超时则返回当前状态。

        这是服务端条件等待，**不产生模型轮询开销**：把一个批次的观察折叠成
        少数几次调用，而不是反复 get_status。after_revision 传上一次返回的 revision。
        timeout_seconds 最长 86400 秒。

        返回值：与 get_status 同构，另有 {"changed": bool, "finished": bool}
        （changed 表示 revision 已前进；finished 表示全部 run 已进入终态）。

        不返回：线程编号、目录、正文、日志、图片。
        """
        return _call("wait", {
            "batch_id": batch_id,
            "after_revision": after_revision,
            "timeout_seconds": timeout_seconds,
        })

    @server.tool()
    def cancel_run(run_id: str) -> dict:
        """取消排队中的 run，或对运行中的回合发 turn/interrupt。

        目录与人工可读日志会保留，供事后排查。

        返回值：{"run_id": str, "state": str}

        不返回：中断原因正文、日志、线程编号。
        """
        return _call("cancel", {"run_id": run_id})

    return server


def registered_tools(server=None):
    """返回服务上已注册的工具名排序列表（供验证脚本核对工具面）。"""
    server = server or build_server()
    return sorted(server._tool_manager._tools)


# ---------------------------------------------------------------------------
# --register：把本服务写进 codex 的 config.toml
# ---------------------------------------------------------------------------

def _render_section():
    """渲染 [mcp_servers.experiment-batch] 段及其 env 段（不含前后空行）。"""
    repo = os.path.expanduser(REPO)
    code = os.path.expanduser(CODE_ROOT)
    return "\n".join([
        f"[{MCP_SECTION}]",
        "command = " + json.dumps(sys.executable),
        "args = [\"-m\", " + json.dumps(MODULE_NAME) + "]",
        f"tool_timeout_sec = {TOOL_TIMEOUT_SEC}",
        "enabled = true",
        "",
        f"[{MCP_SECTION}.env]",
        # PYTHONPATH 指向**代码目录**（让子进程以 -m 找到包）；
        # ORCHESTRATOR_REPO 指向**生产区**（worker 工作目录集中地）。二者不同。
        "PYTHONPATH = " + json.dumps(code),
        "PATH = " + json.dumps(os.environ.get("PATH", "")),
        "ORCHESTRATOR_REPO = " + json.dumps(repo),
        "PYTHONIOENCODING = \"utf-8\"",
        "PYTHONNOUSERSITE = \"1\"",
    ])


def _strip_sections(text, section):
    """删除 [section] 及其所有子段（[section.*]）的整个块，返回剩余文本。"""
    lines = text.split("\n")
    out, skipping = [], False
    for line in lines:
        header = re.match(r"\s*\[([^\]]+)\]\s*$", line)
        if header:
            name = header.group(1).strip().strip('"')
            skipping = name == section or name.startswith(section + ".")
        if not skipping:
            out.append(line)
    # 折叠删除后可能留下的多余空行。
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


def register(config_path=CODEX_CONFIG, backup_path=CODEX_CONFIG_BACKUP, dry_run=False):
    """在 codex 的 config.toml 中新增/更新本服务的注册段。

    用 regex 定位 [mcp_servers.experiment-batch] 段及其子段并整体替换，
    备份原文件后写临时文件再 os.replace 原子替换。其他 MCP 服务配置不受影响。

    Args:
        config_path: 目标 config.toml 路径。
        backup_path: 备份路径，默认 ~/.codex/config.before-experiment-batch.toml。
        dry_run: 为真时只返回将要写入的内容，不落盘、不备份。

    Returns:
        dict: {"path", "backup", "dry_run", "changed", "sections_before",
        "sections_after", "content"}；content 仅 dry_run 时返回。
    """
    original = Path(config_path).read_text(encoding="utf-8") if Path(config_path).is_file() else ""

    sections_before = _section_names(original)
    stripped = _strip_sections(original, MCP_SECTION).rstrip("\n")
    updated = stripped + "\n\n" + _render_section() + "\n"
    sections_after = _section_names(updated)
    changed = updated != original

    result = {
        "path": config_path,
        "backup": backup_path,
        "dry_run": dry_run,
        "changed": changed,
        "sections_before": sections_before,
        "sections_after": sections_after,
    }
    if dry_run:
        result["content"] = updated
        return result

    if not changed:
        return result

    # 先备份原文件，再原子替换。
    Path(config_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(config_path).is_file():
        shutil.copy2(config_path, backup_path)
    directory = os.path.dirname(os.path.abspath(config_path)) or "."
    fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".config-", suffix=".toml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(updated)
        os.replace(temp_path, config_path)
    except BaseException:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
    return result


def _section_names(text):
    """返回 config.toml 中所有段名（用于核对其他服务配置未被破坏）。"""
    return [m.group(1).strip().strip('"')
            for m in re.finditer(r"(?m)^\s*\[([^\]]+)\]\s*$", text)]


# ---------------------------------------------------------------------------
# --inspect：本地调试（不在 MCP 工具面内）
# ---------------------------------------------------------------------------

def inspect_batch(batch_id):
    """直接从 sqlite 打印某批次的 runs，仅供人工调试。

    打印内容包含目录等内部字段，因此**绝不注册进 MCP 工具面**。
    """
    db_path = os.path.join(STATE, "state.sqlite3")
    if not os.path.exists(db_path):
        print("状态库不存在: %s" % db_path)
        return 1
    conn = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM runs WHERE batch_id = ? ORDER BY rowid", (batch_id,)
        ).fetchall()
    except sqlite3.Error as exc:
        print("查询失败: %s" % exc)
        conn.close()
        return 1
    conn.close()

    if not rows:
        print("批次 %s 没有记录" % batch_id)
        return 1

    print("批次 %s：%d 条 run" % (batch_id, len(rows)))
    for row in rows:
        keys = row.keys()
        cells = []
        for key in ("id", "name", "attempt", "state", "verdict", "error_code"):
            if key in keys:
                cells.append("%s=%s" % (key, row[key]))
        print("  " + "  ".join(cells))
        if "directory" in keys and row["directory"]:
            print("    directory=%s" % row["directory"])
    return 0


def usage():
    """打印用法。"""
    print(
        "用法（以模块方式启动）:\n"
        "  python -m orchestrator.server                以 stdio 提供 MCP\n"
        "  python -m orchestrator.server --daemon       前台运行常驻调度器\n"
        "  python -m orchestrator.server --register     在 ~/.codex/config.toml 注册本服务\n"
        "  python -m orchestrator.server --inspect ID   本地调试：打印某批次的 runs\n"
    )


async def main():
    """按 argv 分派：stdio / --daemon / --register / --inspect。

    无参数时以 stdio 提供 MCP（供 DSH 或 codex 拉起）；
    --daemon 前台跑调度器；--register 写 config.toml；
    --inspect 直接读 sqlite 调试；其他参数打印 usage 后退出。
    """
    argv = sys.argv[1:]

    if not argv:
        await build_server().run_stdio_async()
        return 0

    flag = argv[0]

    if flag == "--daemon":
        from orchestrator import runtime

        store = runtime.Store()
        daemon = runtime.Daemon(store)
        await daemon.serve()
        return 0

    if flag == "--register":
        dry_run = "--dry-run" in argv
        result = register(dry_run=dry_run)
        if dry_run:
            print("dry-run：将写入 %s（未落盘）" % result["path"])
            print("段变化: %d -> %d" % (len(result["sections_before"]),
                                        len(result["sections_after"])))
        else:
            print("已注册到 %s（备份 %s，changed=%s）"
                  % (result["path"], result["backup"], result["changed"]))
        return 0

    if flag == "--inspect":
        if len(argv) < 2:
            usage()
            return 2
        return inspect_batch(argv[1])

    usage()
    return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
