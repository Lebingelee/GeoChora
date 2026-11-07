# G05 5b：第三次普通尝试前重评

状态：`CONDITIONAL_NOT_READY`，普通 count=2。本文是审阅及可行性提议，不是已派发工作包，不授权任何执行。依据 [002 主审](../maintenance/reviews/20261107_5b_attempt002_sol_review.md)、原 [5b 目标](../goals/05-rendering.md#5b) 和 [render 合同](../contracts/render-provider.md)。实际执行前重新核验真实 HEAD、两 pin、保护输入、writer、锁和 002 释放；最终包以届时真实 HEAD 为基线。

## 最早失败边界和原出口

- GeoPhys 所测实际公开路径不能使 raytracer 完整 near/far 和 rasterizer far 生效，真实带材料/灯光的 PickCube 生产窗口/RGB 未闭合。这是按当前实验确定的首要集成边界，不是所有可能公开组合不可行的数学证明。
- 可讨论的最小修复：在 pinned provider 自己的公开 camera/visualizer 增加并读取有效 `0 < near < far`，声明米、坐标/光轴与裁剪约定，从 `RenderCameraDesc` 传播到**选定的一条** renderer 的实际几何/像素管线；现有 raster near API 保持兼容。不能用 Core 事后遮图或简单删 geometry 代替真实裁剪。必须覆盖所准入 PickCube 表示、前中后及跨平面几何、遮挡与已发布状态，并对不支持的表示诚实拒绝；不能由现有 SDF/particle 代码推断所有表示已支持。候选位置 `GeoPhys/src/visualization/render_scene.py`、`visualization/rasterizer/{raster_camera,scene_visualizer,engine}.py` 及其实际 clipping 实现，或同级 raytracer `ray_camera.py`、`scene_visualizer.py`、`engine.py` 和交点路径；另改 Core 现有 adapter/admission 与受影响测试。实际路径需执行者/owner 以现有代码确认，避免把清单当现有能力。
- rasterizer 有公开 near setter，是优先调查的候选；其几何、SDF、particle 等可能走不同管线，far 的实现和开销尚未证明。raytracer 可作为同包内备选；其 ray distance 与光轴深度不同，不能直接把两者视为等价。用户可选择只做其中一条，原目标不要求两条皆通过。若找到正确且足以满足全部原语义的公开组合，可不改 provider；不得私读 provider 运行态修补 Core。
- MuJoCo 和 Isaac 复用各自输入/代码相符的窗口、mount、裁剪和状态证据；针对原 5b 图像要求冻结可复核的独立 scene/geometry/state oracle，关联最终生产 RGB 与实际显示及负例，并解决先前探索偏差。需声明并有根据地证明真实输出的 sRGB/linear 约定及转换/限制，不增加显示器 ICC 或完整色彩测量的新门禁。诊断 segmentation 是辅助而非 RGB 本身。
- Isaac 修复后的公开 pose 验证和一个 transition 可复用；针对 USDRT 写入可能被后续 physics 处理的风险，选择少量受控动态/接触比较，记录 render 前后及下一次动作 state/clock，若出现差异先修最早边界。不能假定 [官方 6.2 可见性表](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/py/docs/overview/experimental.html)证明一定发生动力学问题。OpenGL [ARB_framebuffer_sRGB](https://github.com/KhronosGroup/OpenGL-Registry/blob/main/extensions/ARB/ARB_framebuffer_sRGB.txt) 描述 framebuffer 操作，不能单独推出上游纹理与 shader 的端到端色彩约定。以上是原 5b 合同的证据路线，不要求提前完成 5c。

## 需维护者决定的具体授权

002 授权明确排除了 GeoPhys provider/submodule 和 Core gitlink 改动。若公开组合不足，拟议允许：修改当前 GeoPhys 仓库中选定 renderer 的公开相机裁剪接口、实现、相应测试和文档，创建 provider 本地主题分支与本地提交；在 Core `codex/v211-stage5` 内更新 GeoPhys gitlink 指向该本地提交，并修改既有 Core 适配器、测试和对应文档。不得改源资产、任务语义或 Menagerie，也不 push/merge/tag/发布。当前 GeoPhys checkout `codex/v2.1-integration@dc2685e28c6c916fb6403a2342c04e0d2520aef7`，origin 为本机 file 路径；分支及唯一 writer 必须执行前重核，复用现有 checkout、保留原分支，不 reset/clean、覆盖他人工作。此处只是建议，尚未创建分支、修改代码或 pin。

第三次需要单独确认执行权限和预算；可先以 002 的原授权上限作为**待批准提议**：主动 6–10 小时、墙钟 12 小时，source/native 各≤14400 秒、单 worker≤900 秒、physics≤10000 substeps、CPU≤8 线程、worker process-tree RSS≤12 GiB、GPU VRAM≤6 GiB、新增 ignored≤5 GiB。source/native 重叠分别记账；必须对每次 warmup/step 和中断情况事先设置可证明上界并累计，监控采样及局限如实报告。包含受限 PickCube source、三路线真实 native、必要 GPU/GUI 和受影响回归；不含下载、安装或完整任务矩阵。锁按既有 local→shared 非阻塞获取，资源结束后反序释放。此预算不能从 002 授权自动沿用。

## 可行性与执行顺序

这是有具体候选的**条件可行**，并非成功保证：先确认 owner、授权、依赖和可用设备；核对公开路径是否已有充分实现，否则在获批 scope 内最小修改选定 provider、验证有效裁剪，再接 Core 生产入口。其次仅补受影响的 MuJoCo/Isaac 颜色、独立场景证据及 Isaac 后续状态风险，分别验证三个路线的窗口和离屏，绑定每次运行的代码、source、版本、身份和原始数据，最后做必要清理与回归。真实窗口、离屏和同步任务图像仍分别证明；同步任务图像属于 5c。原失败、旧证据和跨版本差异保留，不能复用到已改变路径。

实施者须按 troubleshooting 从最早边界修复；两个同 signature 局部修复仍失败或三次无新证据，保存 failure report、至少三个可区分假设（一个在当前编辑文件外）及最小实验，同授权窗口内继续处理。单 run 失败不消耗新 attempt；达到真实权限、预算或外部资源边界则安全返包。完整包须列逐路线 gate、具体命令/独立 reader 与可辨负例、精确资源记账、提交和锁/资源 release。第三次仍未接收则停止普通派包，维护者主导诊断，不改名重计。
