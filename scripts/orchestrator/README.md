# 本机 Codex 批次编排

该 MCP 管理独立会话，不直接生成几何或裁决资产质量。入口为 `python -m orchestrator.server`，需要把本仓库 `scripts/` 加入 `PYTHONPATH`。

部署、认证、注册、状态目录及本机验证参见[场景与资产 MCP 部署说明](../../docs/module/task_env/v2.1.0/guides/asset-mcp-deployment.md)。服务提供 `start_batch`、`get_status`、`list_batches`、`wait_for_change`、`cancel_run` 五个工具。

默认冻结本 checkout 的 `.agents`。`completed` 表示 Codex 会话结束，调用方仍需检查实际产物。`verify_deployment.py` 通过真实 MCP 启动一个会话并读回固定文件，会消耗一次模型请求。
