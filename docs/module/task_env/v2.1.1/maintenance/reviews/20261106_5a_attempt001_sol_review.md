# G05 5a attempt001：Sol 独立主审

## 决定

`REWORK_REQUIRED_5A`，普通 attempt count=1；执行者的代表路线 PASS 保留为真实的有界证据，原 5a 整体因渲染更新失败后的状态失效/清理缺口暂不接收。不是 5b 的窗口/RGB 或 5c 的同步 observation/renderer 切换/cross 未完成导致返工。需在同一原出口下修复本页明确的失败路径，再依实际影响复用或补充证据；准备 attempt002 不消耗新 attempt，也不自动派发。

## 独立核对

- `codex/v211-stage5` 输入 `3ca161c41340d6015be4fc949ac43771c233ee1c` → 输出 `90a46f968dcdcb663659ebb9562390f2ebf02639` 为父子提交，8 个受限路径；两 submodule pin 和三项保护输入与冻结包一致。执行报告及 release receipt 已返回；实时 lslocks 未发现共享 native 锁持有者，相关进程扫描无本包 native 进程。idle 本身未作 release 证据。
- 重新计算 output manifest 的 **1292/1292** 项大小和 SHA-256，全部匹配；manifest SHA `6b1cc75eaedfc9c60d73ff8512bc588d38f916b87063eb268ac945ee5b1eb0fe`。native14 运行中七个 tracked 文件的 diff SHA `994539c28f87f9809433683246be0c20786f5beeadee1456c5d5df960bb368d8` 与最终对应提交 diff 一致；新测试文件在运行后添加，不属于当次生产路径。
- 独立对 native14 原始 JSON 的两次 typed Frame 与公开 renderer body pose 做数值计算，cube/hand 位置差 0，最大 quaternion sign-invariant L2 `5.55111524223979e-16`，均低于预冻 `1e-5`；seed31 的 cube 变化 `0.0003718646980549467 m`。reader09 的互换、stale、单位、旋转变异和 reader10 的 88 geometry、58 个显式 material 引用及源灯光检查保留各自边界。它们不证明窗口或图像。
- Sol 用实施包 `pure09/sitecustomize.py` 守卫禁止 SDK import 和 XML 解析，独立重跑所列定向检查：**32 passed**；独立构造单元替身复现下述失败路径。Sol 未解析 source、启动 native、SDK、GPU 或 GUI。旧 GeoPhys native scalar 受本包授权限制未重跑；fake 检查只证明合同分支，旧结果不升级为最终 HEAD 实测。
- native16 的清理测试为先实际关闭 real context，再注入 synthetic close error，验证首错/次错与 sibling；不能证明更新及恢复均失败时可安全失效。保留 native02/06 失败、resource ledger 与采样局限。

## 必须修复：恢复失败后仍可读取不可信 renderer state

`task_env/render/camera/mujoco.py::MuJoCoDynamicCameraSession._consume_projection` 在更新过程中异常时尝试恢复 `qpos`/time 并再次调用 `mj_kinematics`。若恢复也失败，它只向原异常添加 note 并继续抛出，session 没有 fault/close/invalidation；`visual_body_pose` 仍可读取该模型的 `xpos/xquat`，旧 receipt/session 仍保留。此时 kinematics 派生数据不保证与恢复后的 qpos 或上次成功 publication 一致。`SelectedReferenceEnv.sync_visual_state` 也没有在该异常后使绑定失效。此路径与 frozen package 要求的失败清理、状态身份及旧状态可靠性直接相关。

Sol 采用守卫的纯替身，令两次 kinematics 均在修改可见 transform 后失败：原错误抛出、次错记录，但 `_closed == False`，`visual_body_pose` 仍返回注入的 `(99, 0, 0)`。这是对当前 Python 失败控制流的合成复现，不宣称真实 MuJoCo GPU 故障已发生。复现脚本和日志在 `workspace/maintenance/v211_g05_5a_attempt001_sol_review/rollback_failure_probe.py` 与 `.log`；不访问 provider private state、不启动 native。

至少应使恢复失败后的 renderer binding fail closed，拒绝所有可能泄露不可信状态/旧 receipt 的查询、同步与 capture，尽力释放 owned 资源并保留主次异常；如设计选择让 physics Env 继续运行，须区分它与失效 renderer 的 owner，不得假称视觉状态恢复成功。也应检查绑定更新的普通失败及 close 失败如何准确报告资源；不要在 Core 引入 test/probe 分支或关闭非本 owner 的共享资源。补充能检测此缺陷的 guarded 测试，关联最终代码与已通过真实运行，按影响决定是否需目标 native 验证；不可用纯 fake 伪称真实故障运行。

## 后续范围

只要原 5a 的完整门未通过，5b 尚不就绪。5b 的三条首批物理/renderer 路线、human 与 offscreen 分别验证，以及 5c reset/step 自动 RGB、同一 Env A→B→A 和真实跨组合保持后续范围。GeoPhys 既有 raytracer 和 rasterizer 都应在后续准备中准确区分其能力、设备和预期路线；本次 `routes.md` 只具体列了 RayTraceEngine，未验证任一 GeoPhys native renderer。装配 Panda 仍为附加用例。无第三次前重评或 attempt002 执行，不自动创建对话、发送、push、merge 或发布。
