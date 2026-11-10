"""judge 模块：对"自报成功但缺少断言"的 run 做受限预算复核。

设计约束（用户确认：断言为主 + 兜底；judge 不占并发配额）：
- 仅在 run 自报 success 且 manifest 未提供 expect 断言时触发。
- 输入**只含白名单字段**：任务一句话摘要、worker 自报的 status/artifacts/reason、
  以及服务侧实际的文件系统比对结果。绝不传入 worker 正文、推理或完整日志。
- 输出只有 verdict(pass/fail) + ≤100 字理由，不回传解释过程。
- 用 gpt-6-luna + low，独立于 worker 的并发闸门。

重要函数：
- should_judge(run_row, manifest_run): 是否需要兜底复核。
- judge(run_row, manifest_run): 返回 (verdict, reason)。
"""

import asyncio
import json
import os
import shutil
import tempfile

from . import VERDICTS
from .app_server import AppServer
from .runtime import JUDGE_EFFORT, JUDGE_MODEL, JUDGE_REASON_MAX_CHARS

# judge 的 cwd：只需可写即可，产物在实验仓库内，用 danger-full-access 访问。
JUDGE_CWD = tempfile.gettempdir()

# judge 单次 turn 的等待上限（秒）；超时即判 unknown，不阻塞归档。
JUDGE_TURN_TIMEOUT = 180

# 强约束 judge 输出，便于机器解析（实测非法 schema 会异步失败，故此处只用合法关键字）。
JUDGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}


def assertion_check(workdir, expect):
    """按 manifest 的 expect 列表做存在性断言。

    实测教训：`all(exists(p) for p in artifacts)` 在列表为空时恒为真，
    会放行"假成功"。因此：
    - expect 为空视为**无法断言**（返回 None，交由 judge），而不是通过。
    - expect 中每一项都必须存在，且必须落在该 run 自己的 workdir 内。
    - 比对按**字面路径**进行，不解析符号链接（实测 artifacts 保留书写路径）。

    返回 (passed: bool|None, detail: str)。
    """
    if not expect:
        # 空列表绝不视为通过：整体判定交给 judge 兜底。
        return None, "no expect declared"

    # root 做 normpath 归一但**不** realpath，保持字面路径语义。
    root = os.path.normpath(workdir)

    for raw in expect:
        # 相对路径按 workdir 解析（manifest 里常写相对路径）。
        path = raw if os.path.isabs(raw) else os.path.join(root, raw)
        resolved = os.path.normpath(path)

        # 越界检查：normpath 已消解 ../，此处按字面路径前缀判断。
        if resolved != root and not resolved.startswith(root + os.sep):
            return False, "outside workdir: %s" % raw

        if not os.path.exists(resolved):
            return False, "missing: %s" % raw

    return True, "%d expect path(s) present" % len(expect)


def should_judge(manifest_run, assertion_result, self_report):
    """判断是否需要兜底 judge。

    规则：自报 failure -> 不需要（直接 fail）；
          有 expect 且断言失败 -> 不需要（直接 fail）；
          有 expect 且断言通过 -> 不需要（直接 pass）；
          无 expect 且自报 success -> 需要 judge。
    """
    # 自报失败直接定 fail，无需复核。
    if (self_report or {}).get("status") == "failure":
        return False

    if (manifest_run or {}).get("expect"):
        # 有 expect 时断言已是权威结论（通过或失败都不需要 judge）。
        return False

    # 无 expect 且自报成功：唯一的兜底场景。
    return (self_report or {}).get("status") == "success"


async def judge(run_row, manifest_run, self_report, fs_detail):
    """跑一次兜底裁决，返回 (verdict, reason)。

    verdict ∈ VERDICTS；reason 截断到 JUDGE_REASON_MAX_CHARS。
    judge 自身失败时返回 ("unknown", <短理由>)，不阻塞归档。

    fs_detail 由服务侧（runtime）产出，必须包含三键：
    expected（expect 声明的路径）、found（实际存在的）、missing（缺失的），
    另可附 workdir/note 等补充说明。judge 以它为准，不索取超出它的产物。
    """
    try:
        return await asyncio.wait_for(
            _run_judge(run_row, manifest_run, self_report, fs_detail),
            timeout=JUDGE_TURN_TIMEOUT + 30,
        )
    except asyncio.TimeoutError:
        return "unknown", "judge timeout"
    except Exception as exc:  # judge 内部任何异常都不得阻塞归档
        return "unknown", "judge error: %s" % type(exc).__name__


async def _run_judge(run_row, manifest_run, self_report, fs_detail):
    """单次 judge 往返：thread/start -> turn/start -> 等 turn/completed。

    返回 (verdict, reason)；解析失败返回 ("unknown", ...)。
    """
    run_row = run_row or {}
    manifest_run = manifest_run or {}
    self_report = self_report or {}

    # 白名单输入：只含任务一句话摘要、自报字段、服务侧文件系统比对结果。
    payload = {
        "task": run_row.get("name") or run_row.get("id") or "(unnamed)",
        "prompt_summary": _one_line(manifest_run.get("prompt")),
        "self_report": {
            "status": self_report.get("status"),
            "artifacts": self_report.get("artifacts") or [],
            "reason": self_report.get("reason"),
        },
        "fs_check": fs_detail,
    }
    text = (
        "You are a strict verifier. Decide whether the worker task actually succeeded.\n"
        "Judge ONLY from the JSON evidence below.\n"
        "- The worker's self-report (self_report) is a CLAIM and is not proof.\n"
        "- fs_check is the service-side ground truth about files. Treat it as authoritative;\n"
        "  do not demand artifacts beyond what fs_check reports.\n"
        "Rules: if fs_check reports missing files, or reports that the workdir is empty or\n"
        "that zero artifacts were produced, then verdict=fail. If fs_check confirms the\n"
        "expected artifacts exist and none are missing, then verdict=pass.\n"
        "Reply with the required JSON only.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    errors = []      # 记下本 turn 的 error 通知，失败时给出短理由

    def sink(message):
        """消费通知并保留本次内部复核的错误事件。"""
        # sink 仍需消费全部事件（runtime 也依赖该行为）；judge 只关心 error。
        if message.get("method") == "error":
            errors.append(message)

    server = AppServer(
        [os.environ.get("ORCHESTRATOR_CODEX", shutil.which("codex") or "codex"), "app-server", "--stdio"],
        sink,
    )
    try:
        await server.start()
        started = await server.call(
            "thread/start",
            {
                "cwd": JUDGE_CWD,
                "model": JUDGE_MODEL,
                "config": {"model_reasoning_effort": JUDGE_EFFORT},
                # 服务器无 bubblewrap，必须 danger-full-access，否则沙箱直接拒写。
                "sandbox": "danger-full-access",
                "approvalPolicy": "never",
            },
        )
        thread_id = started["thread"]["id"]
        turn = await server.call(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [{"type": "text", "text": text}],
                "outputSchema": JUDGE_OUTPUT_SCHEMA,
            },
        )
        turn_id = turn["turn"]["id"]

        # 阻塞等本 turn 的 completed 通知（其它 turn 的通知不属于本次裁决）。
        def is_this_turn(message):
            """判断通知是否属于正在等待的复核回合。"""
            if message.get("method") != "turn/completed":
                return False
            turn = (message.get("params") or {}).get("turn") or {}
            return turn.get("id") == turn_id

        try:
            event = await server.wait_notification(is_this_turn, timeout=JUDGE_TURN_TIMEOUT)
        except asyncio.TimeoutError:
            return "unknown", "judge timeout waiting turn/completed"

        data = event["params"]["turn"]
        if data.get("status") != "completed":
            return "unknown", "judge turn status=%s" % data.get("status")

        raw = _agent_text(data)
        if not raw:
            return "unknown", "judge produced no output"
        try:
            parsed = json.loads(raw)
        except ValueError:
            return "unknown", "judge output not JSON"
        verdict = parsed.get("verdict")
        if verdict not in VERDICTS:
            return "unknown", "judge verdict invalid: %s" % verdict
        reason = str(parsed.get("reason") or "")
        return verdict, reason[:JUDGE_REASON_MAX_CHARS]
    finally:
        try:
            await server.close()
        except Exception:
            pass


def _agent_text(turn):
    """从 turn.completed 的 items 里取出 agentMessage 的文本，无则返回空串。"""
    chunks = []
    for item in turn.get("items") or []:
        if isinstance(item, dict) and item.get("type") == "agentMessage":
            chunks.append(item.get("text") or "")
    return "\n".join(chunks).strip()


def _one_line(text, limit=200):
    """把 prompt 压成一行摘要，供 judge 作为任务背景（不含正文全文）。"""
    if not text:
        return ""
    return " ".join(str(text).split())[:limit]
