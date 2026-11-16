"""本机批处理调度服务：按 MCP 提供的任务文本创建独立 Codex 会话。

任务正文、会话日志和工作目录保存在本机；MCP 仅返回编号、状态和错误码。
completed 仅表示会话结束，任务产物由调用方另行检查。

模块划分：
- app_server.py  单个 codex app-server 子进程的 JSON-RPC 客户端
- runtime.py     进程池 + 调度 + 状态库 + 控制协议（本服务的核心）
- server.py      stdio MCP 入口，对外只暴露窄工具面
- judge.py       兜底裁决（受限预算）

部署形态：本包与 Codex、产物及状态库位于同一台接收方机器。
"""

# 运行状态：queued -> starting -> running -> {completed | failed | interrupted}
# needs_attention 表示调度器重启后无法确认结局，需人工或 reconcile 处理。
STATES = (
    "queued",
    "starting",
    "running",
    "cancelling",
    "completed",
    "failed",
    "interrupted",
    "needs_attention",
)

# 终态：不再变化，可被 retry。
TERMINAL = ("completed", "failed", "interrupted")

# 活跃态：占用并发配额。
ACTIVE = ("starting", "running", "cancelling")

# 裁决结果：judge 或断言给出的最终判定。
VERDICTS = ("pass", "fail", "unknown")

# 仅这些代码可以跨 MCP 边界返回；不泄露错误正文。
ERROR_CODES = (
    "invalid_identifier",
    "invalid_input_path",
    "input_outside_repository",
    "input_not_found",
    "invalid_manifest",
    "unknown_manifest_field",
    "invalid_parallel_limit",
    "invalid_run_fields",
    "duplicate_run_id",
    "invalid_directory",
    "directory_already_exists",
    "model_not_in_catalog",
    "unsupported_reasoning_effort",
    "model_does_not_support_images",
    "invalid_output_schema",
    "unknown_run",
    "unknown_batch",
    "run_not_finished",
    "retry_latest_attempt_only",
    "launch_interrupted",
    "backend_disconnected",
    "manager_restarted",
    "manager_unavailable",
    "assertion_failed",
    "no_artifacts",
    "invalid_timeout",
    "not_implemented",
)


class Invalid(Exception):
    """跨 MCP 边界的受控错误；只携带预定义 code 与简短 message。"""

    def __init__(self, code, message=""):
        """保存可跨 MCP 返回的错误码与简短消息。"""
        super().__init__(message or code)
        self.code = code
        self.message = message or code
