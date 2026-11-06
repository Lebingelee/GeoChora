# G05 5a attempt002：Sol 独立主审

## 决定

`ACCEPTED_BOUNDED_5A_RENDER_BINDING`，5a 普通 attempt count=2。按原 5a 公开场景/状态、具名视觉绑定和有限资源生命周期出口有界接收：真实代表交集是 PickCube、seed31、MuJoCo 3.8.1 CPU physics、MuJoCo renderer-only model、单 Env，使用 EGL context。此为 5a 技术接收，不是窗口、RGB、同步 observation、renderer reset 切换、GeoPhys/Isaac native、cross 或正式 Qualification。001 的 `REWORK_REQUIRED_5A` 及真实有界证据保留，002 修复了该次发现的问题。

## 核对与证据

- `codex/v211-stage5` input `2c5d87d33ec8d3bc69e39f3adc00b9baee116849` → output `3eee8e1e19cd7078964b0495961773c90f690f24`，直接父子，5 个提交文件均属范围。三保护输入 hash、GeoPhys `dc2685e28c6c916fb6403a2342c04e0d2520aef7` 与 Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` 未变。完整报告和 writer/native release receipt 已返回；时点只读检查无共享 native 锁持有者或相关 native 进程。
- 重新计算 output manifest **504/504** 项 hash/size 均匹配，manifest SHA `711151270c141d4bed4bb259aae195302e00069514ef59fa658320f55ce0db0d`。native05 四个 tracked 文件的运行 diff SHA `e5936ad50889f7d39aed1587d4b3f770fd23f35ee97cd3fc04624295d7379f66` 与最终对应提交差异一致；额外测试不在当次 native 生产路径。
- 独立检查 `_consume_projection`：更新/验证异常先尝试恢复可用前态和校验，随后不论恢复是否成功均 fault、清空 receipt/projection、尽力关闭自有 renderer，保留主错和恢复/关闭次错。失败绑定的 pose、sync、capture、receipt 被拒；close 失败报告 `close_failed_unknown_release`，不冒充释放。Env status 保留独立 renderer 的故障及清理情况；不关闭 physics 或 sibling。guarded fake 覆盖 v1/v2、恢复失败/错误 pose/成功、close 失败与部分构建；这些不是实际 GPU 故障证明。
- Sol 在阻止 SDK import 与 XML source parse 的 guard 下独立重跑受影响六组节点，**46 passed**；自行读取 native05 raw JSON 并按预冻 oracle 数值对照 cube 与 hand 两状态，位置误差 0 m、最大 quaternion sign-invariant L2 `5.55111524223979e-16`。同一次真实状态、receipt 和 20 transitions 的身份匹配。两次 cube 位移 `0.0003718646980549467 m`；交换、旧状态、单位及旋转检测由原 reader03 记录。Sol 未运行 source 解析、native、SDK、GPU 或 GUI。
- 独立比较 native14 与 native05 的 source files、source 对象与 visual model inventory 均一致。001 reader10 对 88 geometries、58 显式 material 引用和源灯光的核查保留为旧 run 结果；新 run 关联基于实际相同 inputs 与 inventory，不改写为新 reader 的执行。native05 同次 public boundary/clock 不变及禁止额外 physics/Controller 的运行守卫、native06 的真实 EGL context 清理与 sibling 存活按日志的准确范围接收；native06 的 close 次错是在真实 close 后注入，非真实设备故障。

## 限制与后续

公开 visual binding 为显式 bind/sync，当前 profile 明确拒绝 capture；其 receipt/模型绑定不证明真实图像。GeoPhys 旧 native scalar 因授权范围未在本次运行；它对共享代码的 fake 回归不能替代该原生交集。GeoPhys raytracer、rasterizer 与 Isaac native 的实际窗口和 RGB 未证明；5b 应明确路线与设备并分别验证窗口、离屏 RGB。5c 才负责 reset/step 同步 RGB、renderer A→B→A 和至少一个真实跨组合。装配 Panda 为附加用例，历史 N08 和 Isaac 6.1 close 超时等保留；不据 5a 免去后续真实原目标。5b 只有在维护者授权具体新包并人工转发后执行；无自动进入阶段6、push、merge、tag 或发布。
