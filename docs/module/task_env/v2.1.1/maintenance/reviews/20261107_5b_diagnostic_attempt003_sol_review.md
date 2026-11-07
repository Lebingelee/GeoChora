# G05 / 5b 诊断 attempt003：Sol 独立主审与收尾

## 决定

`ACCEPTED_BOUNDED_5B_WINDOW_CAMERA_RGB`。原 5b 的三条指定路线在所声明的 PickCube 场景与具体配置下，已分别取得真实窗口、离屏 RGB、相机与任务／observer 隔离、发布后渲染不推进所测物理时钟及关闭证据。维护者已人工确认 Isaac 所示场景可辨；本次真实 CPU 隔离补齐前次缺口。接收是 **5b 有界工程接收**，不代表任意场景/设备/挂载、正式 Qualification 或 5c 完成。5a 原有界接收不重开；5c 仍为 PLANNED、attempt0，未自动进入。

普通 5b attempt 仍为 3；诊断 001、002、002 补充重做、003 共 4 个独立诊断窗口。旧失败、被纠正判断、原图像选择偏差和先前资源记账偏差均保留，不把诊断 003 伪称普通 004。

## 身份、权限和独立校验

工作包按维护者明确批准的范围执行；Core 输入 `292a4446aa37b53de2f3103ac96c7f7dc4f6d61b`，输出 `b9f5bc5e7764667d706a9119188ff6780d78a3e3`；GeoPhys 从 `a6bf45b3422e31dfc632a58948e57fa4b686f1b0` 更新到 `1dd9ebdfb5160cbe903aebf026d502b201161a23`，Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` 和三个保护文件哈希不变。Core、provider 变更均在本包授权范围内；writer 和 native release 以交付 release 时点记录为准。静态现场查到无本诊断相关进程或锁文件打开者，不代表未来资源状态。

Sol 不启动 native/SDK/GPU/GUI，也不解析 frozen scene。独立重算输出 manifest **1961/1961** 路径、大小及 SHA，749450759 bytes，无缺失或多列；manifest SHA `c1fa15211a38e79aeb5bea16ca1322424e24b3cba897c3362bfdb0aa165e73e5`。受禁止 provider/SDK import 和 XML/USD 读取 guard 的纯 observer 测试 **27 passed**；执行者最终提交测试为 **30 passed**，另有 1 个 Taichi 弃用警告，不能记为 Sol 的 native 重跑。Core 与 GeoPhys 提交间 `git diff --check` 均通过。Sol 只读 `workspace/reviews/V211_G05_5b_diagnostic_attempt003_sol_review/audit_saved_results.py` 和 `audit-result.json` 独立重算当前两路线保存的 XWD、原始 RGB、发布 boundary、绑定矩阵与 GeoPhys 实际 scene 点投影。

真实窗口/RGB 运行在 Core `97aca27f`、GeoPhys `0e886b3f`；Core 后续差异只有 GeoPhys gitlink，GeoPhys 后续差异只有 verification test（治理头及清理断言），生产代码不变。故将原生证据按真实运行身份和精确差异有界复用到最终提交，不能说原生运行发生在最终 commit 之后。受测 CPU 路线 source closure 为 `a837b9a7db1aa97e4c11401d06a8d70fe746ac4fb6eaf5480a613b1a07abefb8`，各路线不同 artifact、run、状态和 camera identity 保留在各自 raw。

## 逐路线 5b 证据

| 路线 | 实际生产能力与独立复核 | 范围 |
| --- | --- | --- |
| MuJoCo 3.8.1 CPU × native OpenGL | `probes/mujoco_007` 真实 human 窗口 A/B 与同次帧 XWD 转换后逐像素一致；`mujoco_rgb_005` 为单独 `rgb_array` 路径。renderer-only model 内有第二具名 native task camera，A 前/A 后/B 后/实际 WM_DELETE 后绑定相同；任务 camera world matrix 与声明最大差 `2.22e-16`，frame A/B 的 RGB 均值绝对差 `0.03333`。 | 一个 world task camera，task/observer 使用相同 clip 和分辨率，320×240；不代表动态挂载或 task sensor。 |
| GeoPhys CPU × rasterizer compute | `probes/geophys_006` 真实 human A/B 与同次帧逐像素一致；`geophys_rgb_004` 为单独 `rgb_array` 路径。既有 scene visualizer 拥有独立真实 `RasterCamera`，在 A/B/关窗后同一绑定；world matrix 差 `9.54e-9`；native camera kernel 对当前发布 cube frame 的投影与 Sol 独立 pinhole 计算最大差 `3.27e-6`（像素/深度分量混合的数值上界）。observer A/B RGB 均值绝对差 `0.02765`。 | 指定 rasterizer CPU 组合、一个 world task camera、320×240；真实 task camera 当前用于绑定/投影，不声称它已经输出 task RGB。raytracer 不是新增必选门。 |
| Isaac Sim 6.2 PhysX/CUDA × RTX | 复用诊断 001 的 headless App + GeoChora 独立窗口实际关窗/后续采集，以及诊断 002 补充重做的生产 USD task camera 隔离与独立 RGB；[维护者人工认可](20261107_5b_diagnostic_attempt002_rerun001_sol_review.md)确认所示场景可辨。 | 一个 world task camera；保留各运行身份和 code diff，不宣称 final Core 下重新运行 Isaac 或真实 App crash 恢复。 |

两 CPU 路线的实际 probes 记录同次发布 boundary/时钟前后不变、step/Controller guard 未触发，真正 WM_DELETE 后停止展示并可在同一健康发布下继续 capture-only，重复 Env.close 成功。独立审计重算四张窗口帧与 XWD 的最大像素差均为 0，确认 A/B observer identity 不同、任务相机绑定前后和关窗后相同；独立离屏帧均为有效 owned HWC float32 RGB。结合原先按身份复用的裁剪、材料、灯光和限制，符合本包的 5b 范围。截图本身不代替 raw/状态/camera/receipt 与实际窗口证据。

## 保留限制与未完成事项

本次只验证 PickCube seed31 所列具体 provider、版本、source、设备和窗口/相机配置；MuJoCo task/observer 的 clip 与分辨率必须共享，不支持本次未准入的动态任务挂载。MuJoCo 为 GL linear framebuffer；GeoPhys 为 ACES 后 sRGB 传递；Isaac 为所测 RTX tone mapping 后 sRGB 传递；均不外推完整原色/输入素材色域或显示器 ICC 校准。历史旧 C 判据失败、探索性选择、6 cm 反事实与早期 SIGKILL、SDK bootstrap 前隐式步 unknown，以及 CPU followup 零步预约/RSS 证明偏差都保留；不能用新成功改写历史。新窗口显式 physics substep 预约为 0，render/present no-step 只按可观测 guard/时钟声明。GPU 采样不等同硬峰值上界。

GeoPhys 全库文档 check 仍有已有历史错误，本轮日志与前包 `geophys-docs-check01.log` 的 SHA 均为 `66d9b89d14e1c60a07b14964221c17f46af96041fe365d8a4132c2e1ef12fb2b`；provider 测试导航仍有三个旧条目错误。它们不是本轮新通过，按真实限制保留，不将全库治理检查描述为成功。失败后的 provider 清理测试重跑与最终提交测试按执行日志有界保留。

同步 task RGB/observation、reset 首帧与 step 同步、renderer A→B→A、至少一个真实跨组合仍是 5c 的原目标，未实现或验收；不要求鼠标事件或自动 task RGB 作为 5b gate。无自动派发、merge、push、tag 或发布。阶段 5 分支与 checkout 保持，后续由维护者安排。
