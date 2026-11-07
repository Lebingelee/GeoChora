# G05 / 5b 诊断 002 补充重做：Sol 独立主审

## 决定

`DIAGNOSIS_PARTIAL_5B_NOT_ACCEPTED`。接收 Isaac F06 单个 world-mounted task camera 在实际生产场景内隔离的有界证据；在限定场景与已披露限制下接收 Isaac 真实图像可辨性证据。两条 CPU 路线的 task camera 均为 null，未证明各自生产隔离，故不能接收各自完整 5b 路线或整个 5b。普通 count=3；这是已完成的第 3 个诊断窗口，保留诊断 001、002 和普通尝试，不是普通 004。5c 未开始。

一次工作包的第一主线只要求**一个**真实声明/绑定代表；Isaac 成果满足这一明确限定，并非因两 CPU 路线没有 task camera 而否定此项。但本包同时要求依原 5b 对三路线逐项回查，且明确不以缺少真实绑定的项目判生产 PASS。原 `goals/05-rendering.md` 要求三条路线、observer 与 task camera 默认分离；`contracts/render-provider.md` 要求逐路线准入和 present 不改 task camera。一个真实 Isaac 代表不能自动证明 MuJoCo/GeoPhys 自己的生产隔离。空配置不能证明有故障，也不能证明隔离成立；不据此推断 GeoPhys 必然需要 provider 改动或第二 visualizer。

## 接手和复核

交付 commit `8130549070c4d2941ea866318bf327177fb678e7` 是 `7557d8bbc014388887c77c09af868fb69e249dba` 直接子提交；保护 untracked 和两 gitlink 未纳入该提交。执行者的 release 记录锁和 worker 已释放。Sol 不启动 native、SDK、GPU、GUI 或解析场景；核对报告、代码、保存的 raw/state/receipt 与原始 RGB，manifest 298/298 文件大小及 SHA 一致且没有未列项，manifest SHA `5b844550d5c478e982e63ef2a53d2aca486498e6a3ecc22bc0f16543020341f6`。`git diff --check` 通过。Sol 在禁止 SDK/provider import 和 XML/USD 读取的 guard 下独立重跑 observer 测试 **26 passed**；执行者报告另有最终提交定向 **28 passed**。后者是执行者记录，不能说 Sol 自己跑了全部 28 项。

## Isaac 真实 task camera

公开 F06 `make_env(..., task_camera=CameraGeometry(...))` 在 reset 中将声明绑定到同一 session 所有的真实 `UsdGeom.Camera`；readback 返回 native prim、world transform、光学参数、clip、source 及发布 boundary，未创建 task sensor 或 task RGB。实际窗口 A→B 前后 task binding、identity、path 和参数不变，帧与同次实际窗口像素逐点一致，两个观察帧均值差 `0.015645`，published boundary 和所测 physics counter/time 不变。Sol 对保存 readback 独立复算 world transform 最大误差 0、垂直 FOV 误差约 `1.55e-8` 弧度。详细输入和独立审计脚本/结果保存在 `workspace/reviews/V211_G05_5b_diagnostic_rerun001_sol_review/`，不替代生产原记录。

本结论限 PickCube F06、Isaac Sim 6.2、单个 world-mounted task camera；不证明 body/hand-mounted task camera、多个任务相机、task RGB、自动同步 observation 或所有状态。有效窗口 run 比最终提交早一个针对异常清理的改动，正常绑定/展示代码未变；带任务相机的 RGB/reset run 的 `core.diff` 与最终提交 diff SHA `a87c2f1a5a30ae5336d16250cb3b089471305cff27a57de210f83a1fb76cb9be` 一致。捕获不推进 physics 的结论限 publication 后受测窗口，SDK 订阅前启动物理步骤仍 unknown。先前 headless 独立窗口 WM_DELETE 和后续采集按实际代码影响复用，不声称最终 commit 重新实跑该关窗。

## 图像判据

独立 reader 使用先冻结 D/E 视角、cube 和 robot end frame 在已发布状态与 receipt camera 的投影，在两张真实原始 RGB 的局部 patch 上计算灰度纹理方差与归一化相关；首次 NCC 约 0.970/0.947，后续绑定 task camera 的确认运行约 0.975/0.947；黑图、镜像、互换视角、+0.12 m 共同坐标偏移和不同旧 episode/不同视角这五个组合负例各未通过。配置相机的后续运行不是第二次盲测。Sol 直接读取最终代码配置运行的原始 RGB 并做显示转换，所测场景中机械臂、桌面和方块可见；结合 source/相机/状态/帧记录，接受**该场景真实 RGB 与有限场景可辨性**，而非全场景定量校准。

独立事后敏感性检查发现：把两个帧位置同时沿 world X 人工偏移 +0.06 m（保持原帧）仍使两项分别 NCC `0.935`/`0.979` 通过，-0.08 m 也通过；+0.12 m 时 robot end patch 本身仍通过，组合失败依赖 cube patch。该反事实只篡改 reader 输入，不是真实产品位置偏差，说明判据没有证明两个物体的语义身份或厘米级定位精度；不能将一次错位置负例推广成任意错状态检测。旧帧负例同时改变视角，不能单独证明同视角 stale 像素拒绝；已有 receipt 随 boundary 失效是另一项事实。旧 C holdout `0.0728297 < 0.1` 及旧选择偏差保留，不把它说成通过，也不因此断定产品缺陷。源颜色/色域、ICC 与未覆盖设备状态未校准；这些不是本 5b 冻结门，不要求以 5c 状态运动/同步目标替代。

## 后续最小工作

在维护者主导下，先沿 MuJoCo、GeoPhys 各自已选生产 factory/Env/camera owner，核对能否配置并真实绑定一个任务 camera，同时保持一个单独 observer；结合已保存 A/B 窗口和代码差异复用不受影响证据。若当前无能力，在获准范围内实现最小有用的真实声明/绑定/readback，分别验证同一 publication 下 observer 改变、窗口随之改变、task 几何/绑定与 physics clock 不变及资源关闭。需关联 task-camera config 与真实 scene，不能用 null、fake 或没有实际消费者/绑定的 Core descriptor 冒充；也不能预设必须实现自动 observation、task RGB、完整矩阵或 provider 变更。若发现某路线确实无法在现有公开接口及批准范围内实现，提供精确失败边界、可行方案与所需权限，由维护者决定；若维护者希望只用一个后端的代表证明作为跨路线约定，应明确修改/解释验收，不能由 Sol 擅自削门。

无需重跑整个历史矩阵、为 0.1 或有限判据追无限泛化、追旧 native viewport、SDK 启动不可观测步或未知 SIGKILL。保留发布后 render 不推进物理、窗口与 RGB 分别验证和依据实际改动补测的原门。未自动派包、联系其他会话或进入 5c；无 merge/push/tag/发布。
