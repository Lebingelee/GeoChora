# G06结案后 scalar／batch render 收尾

后续更新：[physical worker修复](20261116_worker_physical_followup.md)已替代本文输入版本的direct-effort worker拒绝限制；本文保留原渲染修复时的实测与决策，不把后续能力反写成当时已通过。

日期：2026-11-16。维护者要求在G07前修复公开scalar render断线，并授权代码与测试。输入Core `bff786e6ab21a1d5a5c7da0f28237c8db28f0a1f`，沿用`codex/v211-stage6-parallel`；GeoPhys `198d30ac64ce873a1467f55d2adfc471db18fbc5`、Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`均未改。本维护修复不启动G07，不重置已接收阶段的attempt，也不扩大为完整Solution、性能或求解器研究。

## 1. 事实、必要修复与owner

施工前调用链及原始失败保留在`workspace/maintenance/v211_scalar_render_closeout_20261116/`。变更归类FIX_EXISTING；公共数据／推进／关闭继续使用既有owner。

| 实际缺口 | 最小修复及落位 |
| --- | --- |
| scalar拒绝顶层render，resolved配置只在batch保留它 | configuration.py在两个scope共用RenderConfig overlay／往返；mapping与YAML相同 |
| task YAML／RenderConfig／缺省RenderBuildRequest仍选RayTracer | 共同缺省改Rasterizer；scalar native backend的名称在render contracts一处声明；MuJoCo和Isaac分别解析到其原生展示路线 |
| observer准入用Controller kind与reset参数限制默认R3 | render/camera/task_rgb.py只根据已有source family与renderer路线准入；物理Controller/source准入仍由原owner保留 |
| observer依赖Position Controller发布槽，默认R3没有该槽 | reference_env.py复用已有renderer独立typed-state投影及当前Runtime边界，不另建状态或物理owner |
| human不可用／旧离屏分支彼此遮挡 | 移除正式构造中不可达的旧fallback，使用已有TaskEnvRenderProvider的窗口／采集生命周期 |
| scalar worker未转交observer/task RGB，transport不支持相机值 | 原worker传递请求；原有有界JSON transport增加RGB-only的CanonicalCameraObservation值编码，仍拒绝SDK对象、任意数组和句柄；Isaac在同一App owner选择render launch profile |
| GeoPhys worker解释器为空；Pendulum示例又请求未准入的effort worker | 未设置环境变量时用当前解释器作为worker解释器；维护者确认保留worker默认，只修正Pendulum示例为显式in_process/current interpreter，不删除direct-effort worker guard |
| rgb_array在scalar返回float32，在device batch返回CUDA tensor | 按维护者确认，只在UI边界导出owned CPU HWC uint8；sensor合同不变，展示图不增加B轴 |
| human必须手工调用，mode=None却可能默认展示 | 按维护者确认，在成功reset/step发布之后展示；无mode不自动展示；原示例删除每步重复render |
| 关窗／close_render后自动展示可能重新打开或触碰已关闭renderer | 现有window owner保留关窗状态；batch close_render停止自动展示，保留物理和必要sensor资源 |
| device窗口请求的非Rasterizer backend被忽略 | 在source/runtime构建前拒绝；不默默使用另一renderer |
| scalar render.camera_obs/cameras没有具名观测实现 | 按维护者确认明确拒绝，继续保留已有task_rgb_camera/task_renderer；本轮不新增多相机scalar框架 |
| 当前API附录仍说selected不可render，Controller配置也用已退休alias | 修正当前入口及示例，链接单一版本合同；不更改冻结历史结论 |

共享字段含`render.backend/width/height`、metadata的`render_modes/render_mode/render_backend/render_resolution`。显式scalar CameraSpec尺寸优先，并写回resolved配置，内部捕获声明仍为HWC float32；UI最后一步量化与任务obs分离。原CameraSpec的安装坐标为+X forward／+Z up，示例已用正确朝向，未改相机坐标约定。

## 2. 行为与验证边界

[API中的render合同](../api/README.md#render-contract)是当前行为权威。维护者已逐项确认CPU uint8导出、human自动展示、scalar多相机明确拒绝。renderer仍固定，不新增动态renderer切换。batch保留原显式mode兼容调用，但不再用它修改构造mode。

补查的GeoPhys Pendulum默认worker拒绝是真实部署边界，与Rasterizer计算无关。维护者随后选择保留worker默认，仅修正正式例子为进程内；不得将该决定记录成direct-effort worker通过。

真实检查使用普通make_env／make_parallel_env；监督器复用已有共享native锁、process-tree监督与资源采样。每次900秒、进程树RSS 10GiB、整卡6144MiB、至少1GiB可用RAM／512MiB空闲VRAM、输出1GiB，串行启动，不改变swap或杀外部进程。RSS含共享页，不当作净新增内存。

| 当前实测交集 | 结果／能证明什么 |
| --- | --- |
| MuJoCo CPU Pendulum scalar，96×72 rgb_array | 真实非均匀uint8帧、3步、重复render不推进物理、owned数组与重复close |
| MuJoCo CPU PickCube默认R3 scalar，rgb_array／human | 3步、窗口自动更新、同边界读回／相机身份、关闭；没有任务成功声明 |
| GeoPhys CPU PickCube默认R3，当次resolved为scalar worker，rgb_array／human | 请求及真实RGB往返，3步、窗口自动更新、状态／时钟不因render变化、重复关闭 |
| Isaac6.2 PickCube默认R3 scalar worker，rgb_array | 真实RTX帧、3步、原生状态边界与时钟、完整关闭；非三后端像素／轨迹相等测试 |
| MJWarp Pendulum B=2，human | 自动窗口、CPU uint8展示导出；CUDA状态/reward保留；close_render后继续step |
| MJWarp Pendulum device scalar，rgb_array | 无B轴动作/reward合同、CPU uint8展示、CUDA状态与关闭后继续物理 |
| GeoPhys Pendulum正式RGB示例，显式in_process，96×72 | 真实reset／step观测、uint8帧及关闭；worker默认未改变，worker effort仍拒绝 |
| MuJoCo PickCube observer＋task RGB | UI uint8与obs float32同时成立；二次reset后的新边界采图；无额外物理推进 |

更广的受监督回归244项通过，覆盖formal configuration、worker/transport、renderer fault清理、device语义和reconfiguration。最后一轮对关窗、默认backend、公开示例与task RGB补定向回归106项及6个subtest通过；最终进程内示例调整后，两个公开caller测试再次通过。精确命令、结果及原始文件摘要见[证据索引](g06/scalar-render-evidence-index.json)。两组有重叠，不相加为“总测试数”。

原失败均保留：默认R3缺少Position publication导致真实observer失败；错误测试相机朝向导致空视野；缺少GeoPhys解释器配置；补码期间的transport import错误；Isaac probe遗漏CUDA配置；RTX重复像素严格相等的错误oracle；测试未迁移新的Rasterizer默认期望；仅设置Core PYTHONPATH的source测试无法导入GeoPhys scene。修复时未删除有效物理、单位、clock、fault、stale和cleanup检查。RTX重复采图像素不同可以成立，但它不能掩盖状态或相机身份变化。

## 3. 明确未完成／不外推

- RayTracer的`native`参数与`_surface_texture_payload`兼容问题没有被本轮实现；正式scalar GeoPhys observer限Rasterizer，显式不支持的backend拒绝。保留optional代码不等于通过，也不通过访问provider私有状态修补。
- scalar具名多相机观测按维护者决定不接通；旧task_rgb、device具名相机合同各自保留。Depth、segmentation或任意image对象不因增加RGB传输获得支持。
- direct-effort scalar worker仍不支持；维护者决定使用明确的进程内示例，不将本轮扩成新的物理worker集成。配置、preflight与文档均保留该边界。
- scalar RGB worker沿原16MiB消息上限传输base64编码的host float32帧，有CPU复制成本；不宣称零复制或大分辨率吞吐。device训练相机与此路径分开。
- 未重跑Nut、任意装配Robot、所有renderer/provider矩阵、完整Solution、G06性能矩阵或完整A→B→A native序列；复用的是未改solver、Controller、相机几何、任务计算和原清理owner，不作这些新运行声明。
- Isaac本轮真实窗口未单独重测；UI provider窗口实测来自MuJoCo／GeoPhys与MJWarp。原Isaac窗口证据保持原输入范围。
- 原G06的canonical六格／部分reset／固定renderer切换结论按原输入保留，不能改写为当时已经覆盖本次scalar默认组合。

## 4. 代码规范、提交与恢复

对照[stage6分解](../planning/stage6-work-packages.md)及[优化账本](../planning/post-5c-code-project-optimization-diagnostic-ledger.md)：入口仍为共同configuration/builder；渲染只消费公开状态；窗口／相机／worker关闭保留原owner；没有PickCube/Panda名称、维数或固定资产特判；没有新增Runtime、RendererManager、Controller、永久探针开关或每步hash。新增断言和CPU回归留在diagnostics，原生调用脚本及日志留ignored workspace。

原始输出、测试失败和源码patch不清理；保护日志SHA仍为`3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`。两个submodule无变更。代码提交`ae54597695e65968928458a8c9d42a80858e7315`，本记录及证据索引由后继文档提交配对，当前G07交接须从修复后HEAD读取；不push、merge、tag或发布。当前文档检查仅报既有的`protected local input changed: MUJOCO_LOG.TXT`；无stale path引用。日志实际SHA与输入一致，不修改日志或基准使检查变绿。`git diff --check`通过。
