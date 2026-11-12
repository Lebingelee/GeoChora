# E05～E10 U4 renderer、采集与展示实施记录

状态：`IMPLEMENTED`（实施者自评）；输入 `ff5309d0`。完整事件 E08 的独立主审、维护者接收和 U7 最终影响对账仍待完成；不是全部版本能力接收。[原始计划、差异、失败、日志和收据](../../../../../workspace/maintenance/v211_e05_e10_u4_20261112_001/)保持原时点。

| 检查点 | 结果与最终 owner |
| --- | --- |
| S19 | `render/base/contracts.py` 的 task RGB capability 按真实 physics/provider/renderer 组合集中提供 profile、设备、颜色、借用/独立及 framebuffer 约束；公共查询不加载 SDK。`task_rgb.py` 的真实 consumer 工厂消费同一 capability；`camera/api.py` 的对应 profile 常量也由此取得。显示 backend 的 rasterizer/raytracer/flora registry 仍是不同接口，隐藏的 `mujoco_reference` 不因此变成已接通的 task RGB；注册与受测事实分列。 |
| S20 | renderer adapter 准备 task/observer 配置、color setup、共享 framebuffer 检查与输出描述，Env 编排 space、资源和采集；已有 visual source 和 Runtime state 需求仍归 U3 的 adapter。GeoPhys 的 rasterizer 现仍使用同一进程内的 observer scene 准备对象承载共享 framebuffer；它不是新物理 owner，完整的内部 scene 命名重整不声称完成。 |
| S21 | Isaac task rendering 有独立请求和 task-camera fault，不再伪造 observer 请求；相机局部故障只关闭自己的 sensor，共享物理时钟/App 故障仍共同失效。G05 正式准入传递任务请求和已准入的 observer 请求，F06/G05 的 source、身份、时间和资产检查未放宽。关闭请求与完成分开报告，sensor detach 失败保留 owner 并报告未完成。 |
| S22 | MuJoCo 独立 visual 模型继续只同步公开状态；GeoPhys 使用自己的 camera/source，并在绑定时执行 FOV/near/far 读回检查。原 authored/default 灯光限制保留，不扩大为任意光照支持。 |
| S23～S24 | 单环境 UI 不再跨 owner 调用 visualizer 的 `_initial_camera_pose`、`_refresh_render_snapshot`、`_render_frame_to_buffer` 等私有方法；公开 source camera、`set_camera_pose` 和 `read_frame` 分别负责声明、姿态和采集，UI 持窗口与 presentation。复用 `InteractiveCameraController` 处理按键、中键和鼠标，具体 Taichi 按键在 UI 调用方提供；普通运动模块导入不加载 Taichi。窗口现在经同步 host 帧提交，性能影响未做基准声明。 |
| S25 | 四条注册 pairing 的 factory 有针对性检查；三首批真实原生或独立 cross 按下述实际路线复验。一次窗口关闭、返回帧保留、task/observer 独立、重复采集无物理推进分别以各自收据为准；不同视觉设备、完整任务成功、所有组合及动态 renderer 切换不在此结论内。 |

## 验证与结果

- [最终合同检查](../../../../../workspace/maintenance/v211_e05_e10_u4_20261112_001/contracts-final/result.json)：27 项通过，含注册与真实 consumer 对应、无 SDK 纯查询、简单任务 schema 与 RGB 组合、task/observer 局部 fault 和共享时钟故障、detach 失败、公开窗口接口、键盘与中键输入、F06/G05 严格拒绝；这些是纯/fake 检查，不冒充真实 SDK。
- [MuJoCo 原生、GeoPhys × MuJoCo cross、GeoPhys 自有 rasterizer](../../../../../workspace/maintenance/v211_e05_e10_u4_20261112_001/rgb-registry/native-results.json)：正式构造、reset 首帧、非零 interval、再 reset 和 close；MuJoCo 显式 5 子步，GeoPhys 原生子步未独立计数。其后变动集中在 observer、窗口与 Isaac G05 准入，不改变这三条 task-only factory 的调用，最终全局影响仍由 U7 对账。
- [GeoPhys Pendulum](../../../../../workspace/maintenance/v211_e05_e10_u4_20261112_001/observer-view-final/native-results.json)：task RGB+observer 和仅 observer 两条非 Position 路线，三次 observer render 与相机更换期间状态边界及物理时钟不变；并存路线 task 相机身份与原帧保持。reset、step、二次 reset 和重复 close 均完成，GeoPhys 子步未独立计数。早期尝试分别揭示旧不可显示标志遮挡显式 observer、V2 控制状态误交 V1 camera；两处已修复，失败与重试收据保留。
- [Isaac Pendulum headless task RGB](../../../../../workspace/maintenance/v211_e05_e10_u4_20261112_001/isaac-headless-final/isaac-pendulum/result.json)：无 observer 请求也能完成 reset、25 个显式子步、再 reset 和采图；Env、snapshot lease 与 App close 完成。初试暴露 G05 未传任务采集标志；重试暴露简单任务 info 的旧 schema 未合并 RGB，两次均在首个外部 interval 前失败且 App 完整关闭；现有任务字段语义已保留并与 RGB schema 组合。
- [Isaac PickCube 双相机](../../../../../workspace/maintenance/v211_e05_e10_u4_20261112_001/isaac-dual-camera/isaac-position/result.json)：真实 G05 Position 以外的 joint-effort 路线，task+observer 分别构建，连续三次 observer 采集及 A→B 不推进物理或改变 task 帧／身份；非零 interval 记录 5 个显式子步，二次 reset、重复 close、lease 和 App close 完成。共享 App 的启动隐式推进仍未知，不称 SDK 日志完全无警告。
- [GeoPhys 公开窗口接口](../../../../../workspace/maintenance/v211_e05_e10_u4_20261112_001/public-ui-final/native-results.json)：Pendulum 的真实 source 经公开方法离屏采图、创建窗口并呈现，展示前后物理边界/时钟不变，随后完成短程与 close；窗口输入行为另由合同检查覆盖，未自动化鼠标。最初一个进程在 8 GiB 虚拟地址空间限制下 Vulkan 设备创建中止，第二个在调整为内存 cgroup 后中止；跟踪探针改用 `MemoryMax=8G` 且显式暴露 GPU 后成功。异常进程无完整退出收据，OS 释放锁，前两次隐式物理推进未知；没有删除其日志。

本单元修正了 U3 对简单任务附加 RGB schema 的遗漏。相机只支持现有 world mount、RGB HWC float32 与已注册配对；颜色传递函数及素材原色仍未校准。用户关闭窗口后的全部 OS/UI 事件和所有光学设备组合未扩张成全矩阵；U7 根据最终 diff 与先前关窗/光学收据复用或补验。

## 总账及成效

已核对 REN-01～08、OBS-02、ENV-04 的 renderer/schema 部分：task capability 与 factory、相机状态与生命周期、display/input 已按上述 owner 分工。由于最终 source、Task、Recorder 与全部事件仍将变化，对应跨事件总账条目及 E08 不在本单元直接宣布维护者接收。

以 `ff5309d0` 为输入，tracked blob 项目 **1,379 → 1,381**、`task_env` **984 → 985**；新增版本诊断和本记录各一份，无整文件删除或迁移。生产代码 **+292／−141，净 +151 行**，诊断／测试 **+284／−2，净 +282 行**，文档增减以提交 diff 为准。原 Env 的 renderer 设置/准入与原 UI 的帧循环按职责重组；相同连续行只提供保守近似，不把移动逻辑视为独立删码收益。

相对 5c 输入 `1f1359ee`，累计 tracked blob 项目 **1,361 → 1,381**、`task_env` **977 → 985**；生产代码 **+6,970／−15,325**，诊断／测试 **+5,625／−0**，文档和其他内容见提交 diff。累计包含 E00～E04 与 U1～U3，不能归功于 U4。
