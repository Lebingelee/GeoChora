# G05 5c attempt001 — Sol 独立主审

日期：2026-11-08。结果：`REWORK_REQUIRED_5C_GENERIC_PUBLIC_INTEGRATION`；普通 attempt count=1。技术交付中的 PickCube 指定三原生及 GeoPhys→MuJoCo 真实结果有界保留；完整 5c 因工作包要求的通用任务接线尚未成立而不接收。执行偏差须原样保留，不靠事后记账改写为合规；它不单独使其他有身份的真实技术证据失效。

## 身份、交付与独立检查

- Core 输入 `c7402e4e7d40ce95ec85b6ddc3f8e3bc4d466311`，输出 `9d7b14a47ea419d9d825bc18dadbc37eead95f74`；GeoPhys 输入 `1dd9ebdfb5160cbe903aebf026d502b201161a23`、输出 `60300ed315932f67ac01b078c35b51547d727917`，Core gitlink 对应，Menagerie 未变。工作包、维护者批准、release 与本次提交已核对；三个保护输入 SHA 与前包一致。
- Sol 以离线文件字节独立复核输出清单 3242/3242 项（3228 文件与 14 symlink，合计 2,344,766,970 文件字节），无丢失、错 hash 或未列输出；manifest 自身与最后写的 release 依清单明确排除。清单和 release SHA 对应。
- 在禁止 provider／native SDK import 和 XML/MJCF/USD 等任务 source 读取的 guard 下，独立运行 `test_v211_task_rgb.py` 与 `test_v211_render_binding.py`：**16 passed**。执行者在最终提交下报 **50 passed**，这不是 Sol 的 native 重跑。
- Sol 独立离线读取四条路线各 13 个保存边界：全部 receipt state boundary、sample clock 与 reset/step phase 对应，无错项；对照同次已保存 no-task-RGB run，52 个边界的所有共同具名 frame pose 精确一致。离线 audit 和 guard 脚本保存在 ignored `workspace/reviews/V211_G05_5c_attempt001_sol_review/`。这些比较只覆盖记录内的 scene／配置，不代表所有内部物理状态或任意运行。

## 技术证据的边界

执行者的 `mujoco-native-motion-001`、`geophys-native-motion-001`、`isaac-motion-002` 和 `cross-motion-003` 实际得到 PickCube reset 首帧及 12 步任务 RGB；各路线各自保存原始 RGB、状态、receipt、颜色范围和独立图像/姿态检查。GeoPhys→MuJoCo 对 cube 和 link 的 render-only body-origin pose 比较、wrong-entity／stale 对照和 `mj_step` guard 保留为该场景/状态的跨组合证据。图像负例的判据受探索性选择影响，不提升为通用视觉精度证明。Isaac 启动前、订阅之前不可观测的隐式步仍 unknown；GPU 采样不是显存硬峰值。没有新的 GUI 测试，不重写 5b 的历史真实窗口结论。

## 主要未闭合：不只 PickCube 的通用任务接线

维护者明确要求手工搭建的其他环境在符合实际 provider/source 能力时也走同一个公开配置入口；工作包还明确禁止将 Panda 关节数或 PickCube 等特定结构作为公共机制前提，不要求因此新增第二个真实 native 任务。

1. `task_env/registry.py::make_env` 的通用 finish 分支和 `SelectedReferenceEnv._configure_task_rgb` 明确要求 `position_profile`。而 `task_env/runtime/sessions/control.py::bind_selected_controller` 的该标志，普通 profile 分支依赖 `PandaPositionServoProfileV1` 的类型判断；已有的通用示例 `examples/tasks/declared_marker.py` 使用 `ProductionCanonicalPandaController`，其非 Position 路径被这一 renderer 入口拒绝。执行者所谓不同任务 public factory 测试通过 `object.__new__` 手工设置 `position_profile=True`，只证明配置拼接，不证明其他已声明任务可以 reset/step 及从真实发布状态采集。Sol 在 SDK/source 守卫下独立复现 `position_profile=False` 时立即拒绝。不能把“没有第二个 native 验证”与“通用入口存在硬性控制器类型准入”混为一谈。
2. GeoPhys 新 task RGB 路径复用既有 `_GeoPhysSession._ensure_observer_visualizer`，它要求 source 恰好一个 `world_trackcom` 灯和一个 headlight，之后无条件更新追踪灯和 `'mjcf:headlight'`。Sol 用无灯具的合成 render-scene 描述独立复现该路径立即拒绝；这证明具体假设存在，不证明任意无灯 scene 已获支持或其图像效果。这个限制源于既有 5b 观察路径，但新 5c task RGB 对其产生依赖，不能把 5b 的 PickCube 灯光证据扩展成其他场景的通用接线。应依据公开 source/scene 的实际灯光声明处理已支持的灯光及缺失情况；如某种表示不支持，说明真实能力和拒绝边界，不能为通过捏造 source 灯或删掉 PickCube 灯光语义。

最小返工：让 task RGB 的初始化／发布依赖通用 scene、named state 与 renderer 的真实能力，而不是借 `PandaPositionServoProfileV1` 证明可渲染；保持 Controller/physics 准入，不创建第二 Runtime。用已有非 PickCube 的真实生产绑定或真实构造链做 **provider-free 合同验证**，覆盖非该 Position profile、不同命名和缺失/歧义拒绝，并说明相应 native intersection 的可用条件；若具备现成资源可在本包授权范围内增强真实任务证据，但不把第二个 native 任务新增为门。GeoPhys 灯光接线应补声明驱动的受支持情形与反例。针对实际改动评估并重测受影响路径，复用四条原始结果，无需重新跑完整历史矩阵。

## 执行偏差的独立判断

`task_rgb_contracts_005` 明确以 source/零步预约启动，却包含会构建真实 MuJoCo 并 step 的测试。锁和受限 scope 的记录存在，但**事前预约和 native 分类确实违反本包**；事后 500 步上界是基于静态 horizon／测试实例数的保守估算，不是实测数，也不能补造成事前合规或独立证明全程硬上界。pytest 在 `/tmp/pytest-of-lly/pytest-107`、`108`、`109` 写入包外，原目录保留并有副本；日志未提供事前存量清单，pytest 自动保留策略是否影响旧目录未知，不能断言未影响。无证据证明实际超过已批准总预算，也不能把该未知改写为已证明合规。

以上偏差应在最终收尾记录中持续公开，后续将测试分为 guarded pure 与 native、在启动前预约（包括零步）并显式设 package-local basetemp；不得删除原临时目录或篡改账本。已经由其他正确记录运行产生的真实 RGB 证据可以按输入和代码影响保留；是否通过 5c 仍依实际技术出口判断，本次独立拒收的直接技术原因是上面的通用性缺口。

## 后续

维护者手动决定是否准备聚焦返工 attempt002；本次 review 不自动创建、发送或派发工作包，不启动 native、SDK、GPU、GUI、5b 重审或阶段 6，不 merge/push/tag/发布。普通 5c attempt 已用 1 次；同 renderer reset 保持，A→B→A 延期决定不变。

## 维护者后续处置（2026-11-08）

维护者允许保留上述执行偏差及其未知项；不为补造事前合规而追加调查、清理旧临时目录或重跑历史证据。此决定不改变当时事实、预算测量边界或技术主审结论，也不自动授权后续窗口的资源。后续应按具体批准包控制预算、记录实际事件；常规流程应服务于实施，不以追查不可恢复的历史事实阻断开发。
