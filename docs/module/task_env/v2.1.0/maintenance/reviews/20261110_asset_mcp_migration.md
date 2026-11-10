# 场景与资产 MCP 迁移记录（2026-11-10）

## 范围与来源

- 阶段分支：`v2.1.1-asset-skills`；输入 HEAD：`360d65bec75cc73f24c2f89190311fa4f73bd69d`。输出与包含本记录的本地提交绑定，不推送、不合并。
- 范围：`scripts/asset_services`、`scripts/orchestrator`、部署说明与三个制作 Skill 的工具路由；不修改 TaskEnv 任务、控制、录制、评分或准入。
- 分类：`COMPOSE_EXISTING`（复用现有模型服务和编排）；`FIX_EXISTING`（消除机器路径、补齐公开依赖准备及 Windows 控制接缝）。
- 原资产服务来自源仓库提交 `15086d82751e9fdce278b301a6a04f4b04722375` 的已跟踪文件；编排是工作区文件快照，不声称它们已包含在该提交中。逐文件输入摘要保存在[迁移来源清单](../../../../../../scripts/asset_services/deployment/migration-provenance.json)。该清单用于追溯，部署不需要访问源仓库。
- 算法与权重使用固定公开来源，版本在部署脚本中声明；本机重新下载与构建，没有使用原开发环境的模型、解释器、wheel、运行数据库或资产产物。

## 复用与接入决定

| 证据步骤 | 检查对象与结论 |
| --- | --- |
| owner | 模型业务由原 `services` 及共享 `scheduler` 维护；批次会话由原 `orchestrator` 维护 |
| 公共接口 | 三个资产 MCP 的提交/查询/等待与独立重拓扑；批次 MCP 五个工具 |
| 现有实现 | 保留原 worker、队列、结果交付、Codex app-server 客户端和 daemon |
| 生产调用 | `asset-creation`、`asset-material-creation`、`scene-orchestration`；GeoChora 交接文档路由 |
| 检查 | 迁入的 34 项资产协议/队列/生命周期检查；新增两项路径搬迁/真实工具发现、三项编排控制与注册检查 |
| 已建立限制 | 原包没有服务和完整下载过程；路径、缓存、解释器、CUDA 架构与 Unix 控制依赖原机器 |
| 修复/组合 | 代码随仓库分发；公开源重建依赖；本机独立运行目录；Windows loopback 认证控制；不创建另一套 TaskEnv |

官方源码不包含原开发版本的部分特征卸载/缓存清理代码，对这些原兼容补丁增加适用性判断，保持固定官方源码的原有实现。没有为本机显存容量开发、尝试或追加优化。

## 部署验收口径

维护者明确指定：不解决 TRELLIS 显存问题；真实模型请求发生 CUDA OOM 可以作为部署成功。验证保留 `raw_job.status=failed`、原始 traceback 和独立 `DEPLOYED_OOM` 标签。其他依赖、授权、编译、DLL、输入和超时错误不适用此口径。

该标签不是资产生成成功、外观通过、可运行场景、TaskEnv 准入或 Qualification。迁入的模拟协议检查也不证明模型推理能力。

## 本机环境与检查

Windows 11，RTX 3060 Laptop 6 GiB（SM 8.6），主机内存约 23 GiB；CUDA Toolkit 12.8、Visual Studio 2022 C++ Build Tools、Blender 5.2。新建 Python 3.11 环境，PyTorch 2.8.0+cu128、xformers 0.0.32.post2；其他版本由本机环境锁记录。

| 项目 | 当前结果 | 原始依据（仓库内忽略路径） |
| --- | --- | --- |
| 本机环境检查 | 完成；记录显存，不设置容量阻断 | `workspace/asset-services/evidence/environment.json` |
| 固定公开源码获取 | 完成；含子模块版本与 LICENSE/README 摘要 | `workspace/asset-services/source-receipt.json` |
| 上游模型授权 | 两个受控模型均确认可访问 | 本机 Hugging Face 下载检查，凭据不留档 |
| 资产协议/队列/生命周期与路径搬迁 | 36 项通过；包含中文/空格新 checkout 的真实 MCP 工具发现 | `workspace/asset-services/evidence/unit-tests-final.log` |
| 编排本机连接、令牌/独占锁、注册预览 | 3 项通过 | `workspace/asset-services/evidence/orchestrator-tests-final.log` |
| 编排真实 MCP 会话 | 通过；固定文件读回一致，Skill 来源为当前 checkout | `workspace/scene-generation/deployment-check.json` |
| 模型准备 | 六个固定公开 revision 下载、路径生成完成 | `workspace/asset-services/model-receipt.json` |
| CUDA 扩展与运算 | 六个本机 wheel 完成；实际矩阵、注意力、网格、栅格化、变换检查通过 | `workspace/asset-services/evidence/extension-builds.json`、`cuda-check.log` |
| 两个 Python 环境依赖 | 两项 `pip check` 通过，公开源约束安装 dry-run 通过 | `workspace/asset-services/evidence/pip-check-*-final.log`、`constraints-*-check.log` |
| Blender 文件交付接缝 | 实际 GLB→Blend、打包 PBR 后重载通过；CPU 诊断输入 | `workspace/asset-services/evidence/blender-export-f1e0d853/check.json` |
| 四个 MCP 本机注册 | 完成，保留其他三个 MCP 配置 | `workspace/asset-services/evidence/registration.json` |
| 资产真实模型请求 | 四项均 `DEPLOYED_GENERATED`；状态成功、交付文件读回通过 | `workspace/asset-services/evidence/live-33aadcca902f/report.json` |
| Linux | NOT_RUN | 本轮没有 Linux 独立部署执行 |

真实资产请求逐项使用当前公共 MCP，未降低服务默认参数。输入为固定 TRELLIS.2 源码中的 `assets/example_image/T.png`；几何相关路线另用检查器生成的米制 Z-up 闭合盒体（0.10 × 0.08 × 0.15 m），互相独立提交，不因前一项结果跳过后续服务。

| 路线 / job_id | 参数范围 | 结果与读回 |
| --- | --- | --- |
| `trellis2` / 2 | 默认 1024、seed 42、2048 贴图、目标 200000 面 | `DEPLOYED_GENERATED`；GLB 含 183103 顶点、189393 面，PBR 贴图存在 |
| `ultrashape` / 3 | 默认 4096 latents、8 steps、512、guidance 5 | `DEPLOYED_GENERATED`；NPZ 含 750950 顶点、1501116 面 |
| `trellis-texturing.submit_remesh` / 4 | 显式 resolution 512，其余默认 | `DEPLOYED_GENERATED`；NPZ、GLB、Blend 和几何变化报告交付，991064 面 |
| `trellis-texturing.submit_job` / 5 | 默认 1024、12 steps、2048 贴图 | `DEPLOYED_GENERATED`；带 PBR 的 GLB 和 Blend 交付，24 个 UV 顶点、12 面 |

四项真实请求均未发生 CUDA OOM；部署豁免没有用于把失败请求记作生成成功。检查器执行结束后已确认其 runner 和模型进程全部退出，显存回落到桌面占用。产物、状态与原始末尾日志在上述 report 中；这些检查不评价外观质量或任务可行性。

## 部署与 Skill 路由

权威步骤见[独立部署说明](../../guides/asset-mcp-deployment.md)。三个制作 Skill 和 GeoChora 资产场景交接均指向该页；原始 Skill 来源档案仍保留，本轮只刷新安装入口摘要。

编排最终验证为批次 `batch_0fba7188cef74715b02b1fa84ed237be`、会话 `run_60d8b720385d41f6aa33f86dbdac986b`。此前资产请求 job 1 因维护者需要 GPU 主动终止，单独保留中断记录；不将它计为 OOM 或部署成功。恢复后使用全新请求。

验证完成后，为本机已注册的入口另行启动一个空闲资产执行端；启动时队列无在途任务，进程身份保存在 `workspace/asset-services/evidence/resident-runner.json`，没有额外模型驻留。接收方仍按部署说明启动自己的执行端，不复用本机进程记录。

三个制作 Skill 的元数据、本地链接与源码路径静态检查通过。文档全量检查存在 74 项输入基线问题：62 项冻结文件字节差异、10 项历史发布文件非导航字节差异、两项缺失的受保护本地输入。抽查冻结文件差异为 Windows CRLF checkout，受影响历史路径没有本轮 Git diff；本轮不改写冻结事实或补造缺失输入。具体列表保留于 `workspace/asset-services/evidence/docs-check.json`。

本记录只报告上述部署交集。所有生成环境、权重、日志、模型产物和会话位于忽略的 `workspace/` 或本机临时状态目录；不提交凭据、环境、模型或运行数据库。
