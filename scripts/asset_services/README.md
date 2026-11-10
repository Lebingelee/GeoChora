# 资产生成服务

独立部署入口：[场景与资产 MCP 部署说明](../../docs/module/task_env/v2.1.0/guides/asset-mcp-deployment.md)。

- `services/trellis2`：参考图生成带 PBR 的 GLB。
- `services/ultrashape`：参考图与米制 Z-up NPZ 细化几何。
- `services/texture`：CuMesh 重拓扑、TRELLIS 独立贴图和 Blender 打包。
- `scheduler`：三个入口共用的任务队列、执行端和交付管理。
- `common`：路径、文件读写和固定后端兼容层。
- `deployment`：公开源码与权重准备、CUDA 编译、MCP 注册、环境和真实请求检查。
- `tests`：迁入的队列、协议及错误传播检查；模拟计算结果不作为模型推理证据。

服务源码随仓库分发。解释器、模型、编译文件、数据库与结果默认位于忽略目录 `workspace/asset-services/`。本机部署不读取原开发者服务器或仓库。

源代码迁移与本机验证收据见[迁移记录](../../docs/module/task_env/v2.1.0/maintenance/reviews/20261110_asset_mcp_migration.md)。
