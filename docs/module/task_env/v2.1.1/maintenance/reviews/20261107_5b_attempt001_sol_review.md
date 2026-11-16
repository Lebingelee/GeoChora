# G05 5b attempt001：Sol 独立主审

## 决定

`REWORK_REQUIRED_5B`，普通 attempt count=1。001 是完整返包的部分实施，原 5b 三条原生路线的窗口和离屏 RGB 均未完成，不进入 5c。已执行的窗口、图像、同状态 guard、故障、诊断及其原 code/source 证据保留；不将结果表述为整条路线或整个 5b 通过。5a 原有界接收与 G03/G04 不重开。

## 输入、释放和独立核验

- 分支 `codex/v211-stage5`：input `a387ff96a033e8bb16d5f31aca545e55eb664ccb` → output `a79273d045191d004bc938fd03c87f76661156ff` 直接父子，14 个路径与包内 Core/测试/文档范围相符。三保护 untracked hash 未变，GeoPhys `dc2685e28c6c916fb6403a2342c04e0d2520aef7` 与 Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` pin 未变。报告、释放凭据和进程退出记录齐；实时只读检查没有共享锁持有者或相关 native runner，idle 本身没有被当成释放依据。
- output-manifest 重算 **1498/1498** 大小和 SHA 匹配，共 634181592 bytes；manifest SHA `530ed319a447fc48393256d27cd566dbe403ad51df1cd093d9dec90c876a48b0`。最终 MuJoCo `native07` 与 `window03` 的生产文件 diff SHA `cabdc07c80decd8854f833442128bfa4b10f149f1cc3e76a1d827ad61deacfa1` 与最终 12 个对应生产路径差异相同。新增测试和文档不声称属于该原运行。
- Sol 在 SDK/XML guard 下独立重跑 observer、5a binding/fault 定向组 **24 passed**；实施者 `pure10` 的 54 passed 与 `pure11` 的 8 source fixture 被 guard 拒绝、24 passed 分别保留，不能把受 guard 拦截的项当成已验证。Sol 未解析 source、启动 SDK/native/GPU/GUI，也未重跑历史矩阵。resource ledger 是各监控 runner 的保守总和，CPU/RSS/GPU 数值为离散采样，GPU 为全卡观测，不能当连续峰值或单进程归因。

## 各原路线判断

1. **MuJoCo CPU × MuJoCo renderer：窗口 PARTIAL，RGB INCONCLUSIVE。** `mujoco-window03` 的 public Env、真实窗口、present、WM_DELETE、重复 close 和 boundary 结果可保留；`mujoco-native07` 有真实 owned HWC float32 RGB、双 camera 和 no-step 证据，reader03 的位移方向和数值是可审阅的探索结果。reader 的颜色掩码在看过预检图后建立，object body-origin 与可见几何中心/遮挡尚未独立论证，RGB transfer curve 也未知，报告正确未将其升级为独立 PASS。两个目标须继续分别验证。`task_env/render/camera/api.py::v211_rgb_render_manifest` 当前将 RGB 列为 implemented，而 `render/providers/single.py` 仍把颜色空间写作 `unverified native framebuffer encoding`；后续须落实真实颜色语义及 admission，不能从返回 float32 和注册状态推断已达到 required RGB 颜色合同。`native05` 跨 GL context 变化仍为诊断而非确定缺陷；native06 同 context 读回及 mount 核对按各自输入范围保留。
2. **GeoPhys raytracer / rasterizer：目标窗口和 RGB 均未闭合。** raytracer 的诊断数据与 `geophys-native08` 的 13 个公开 state-to-transform 对照可作为当前 pin 的有界诊断，但 `native07` 丢材质/光照，非完整真实生产路线。`geophys-preflight04/05` 所测 RayCamera 有 pose/FOV；RasterCamera 有 near，未找到完整可配置 near/far 入口。静态审阅还发现公开 `RenderCameraDesc` 有 near/far 字段，但尚无证据证明生产 renderer 实际消费这些字段；这避免把“描述类型有字段”误说为可用，也不能仅凭扫描断言修改 provider 是唯一方案。下一包先沿公开 descriptor→renderer/SDK 能力和 near/far 效果检查；若缺口属 provider、其他公开方案确不可闭合，冻结实际目标、最小 public API 变更、gitlink/回归影响和成本，另请维护者授权，不用私有状态绕过。只要求完成原计划一条明确命名的 GeoPhys renderer；分别保留另一条预检及未测边界。`geophys-native05` 对私有 `_representation_refs` 的意外序列化记录为越界事件，未用作证据，不扩散为后续方法。
3. **Isaac Sim 6.2 PhysX/CUDA：窗口和 RGB BLOCKED。** native13 production capture 实际在 public renderer-facing USDRT/Fabric cube 与已发布 physics pose 差约 `0.160432 m` 处拒绝，旧 native12/window01 图像不可当已发布状态正确展示。native14/16/17 的公开 USD/USDRT/Fabric 对照分别记录 cube 约 `(0.5, 0, 0.487)`，typed 状态约 `(0.635134, -0.086464, 0.488)`；force_update、公开 update_transformations 与 render-only 未消除差异，诊断期间 physics counter 未推进。这是具体的观测偏差，不足以单独确定是发布顺序、GPU同步、父子 frame、错误 prim 或 renderer 其他因素；不得通过多走一步 physics 隐藏它。native13 的 code diff 比最终少后续外层 fault invalidation：核心 USDRT 对比逻辑相同，但不把它说成最终字节的完整 capture 重跑；native17 的最终 diff 相同，它是公开状态诊断，不是完整 capture/window 成功。native01/02/04/11 teardown SIGSEGV 保留；使用既有 `_exit_after_isaac_cleanup` 的后续正常退出只能按真实 close receipt 的范围解释。

## 下一步

按原 5b 出口准备一个 attempt002 完整返工窗口：先分类具体失败层和受影响范围，MuJoCo 冻结独立于预检图片的 landmark/颜色 oracle；GeoPhys 证实实际公开 clipping/source/material/light route 或提出必要 provider 修改的具体审批；Isaac 区分 tensor→Fabric 同步与 prim/frame/oracle 假设，以 no-step 小实验找最早边界，再回到真实 public Env 窗口及 raw RGB。逐 route/window/offscreen 单独报告、保留原失败；有影响才重跑，失败后的复核须绑定最终代码。三条都需按原门闭合，不把 renderer reset 切换、同步 task observation 或 cross 的终验提前到 5b。

attempt002 尚未派发或执行；需维护者授权其新范围/预算并人工转发。若第二次仍未接收，按 GeoChora Skill 在第三次前重评已有证据、最小修复、版本匹配的官方文档/开源实现与原出口可行性；第三次仍未通过需维护者主导诊断，不自动 004。不得自动进入阶段6、push/merge/tag/发布。
