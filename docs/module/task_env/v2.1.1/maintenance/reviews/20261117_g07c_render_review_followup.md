# G07 7c 独立审阅与 GeoPhys Nut 渲染跟进（未闭环）

维护者指示对早期 CPU 运行缺少整卡 GPU 采样作有界过程偏差处理；原始记录不补造。独立只读审阅重新核对六条最终代表运行的 H5 SHA、T/T+1、supervisor 退出和 close，一致；其结果仅限各自配置。九格和两条完整 Nut Solution 未重跑。

独立审阅指出四处 Pendulum 示例使用被当前解析器拒绝的旧 `runtime.backend`、Pendulum/TwoWheel batch 描述矛盾、marker 示例缺录制读回、H5 structured 与 physical reader 的字段和核验范围不足。本次逐项修正；独立复核确认这些修改符合当前解析器和 writer/reader，未逐一动态执行 34 页示例。`review-doc-config-001` 在配置成功解析后的打印步骤因错误属性失败，保留；修正打印的 `review-doc-config-002` 通过。其无物理子步，且受共享锁、CPU/GPU 监督。

## 渲染缺口的已核实边界

已有 `render-geophys-001` 在首次 observer frame 失败并正常 close。原 Nut RuntimeSource 有真实 closure `bf08619661608cf4caa7ecacda2ab9f4cd02489fd411935a26678bdde8b07f6c`，**缺的是 canonical `scene_definition`**，不是缺 closure。其 Artifact 为 v0；该 Artifact 没有 `legacy_frame_bindings`，而 typed render binding 要求这些引用；`RuntimeSource.__post_init__` 不允许 v0 execution receipt 与 canonical Scene 混用，`snapshot_v1` 要求 source ID 与 Scene identity 绑定。Nut 的任务定义与 reset 还严格要求 v0 Artifact。

现有 `prepare_reference_task_robot_source(..., compile_declaration=...)` / `bind_reference_scene_source` 能从真实快照创建 canonical source，但它改变 source ID、closure 和 Artifact 身份，GeoPhys 导入还使用 Scene 投影 XML。监督的无物理 `review-source-projection-001` 仅把已声明 Panda Scene 对旧 Nut 快照做有界投影：导入 XML SHA 从 `16b19e020f843dfd11b0f2086da777426cd56e015d69c5363a97e5f86dc6dc17` 变为 `e789f2ab88a660ccc6390928262da9c307dcba456b23f283f8f9`，九个关节显式写入 axis；这不是完整 Nut Scene，也不能证明物理语义变化或等价。不得把该试验的 Scene 冒充完整 Nut 绑定。原始 stdout 和 supervisor 在 `workspace/maintenance/v211_g07c_attempt002/review-source-projection-001/`。

随后 `review-scene-prototype-001` 在 ignored 工作区用同一冻结快照和现有绑定器构造了包含 Nut/peg/table 的静态 Scene 原型：源 Artifact `99e374bd…` 变为 `a1baeddf…`，closure 从 `bf086196…` 变为 `82f5ebf4…`。原型未验证 GeoPhys 物化、状态同步或任务闭环，不是生产 Scene，也不是通过证据。

当前没有落生产渲染补丁，也没有声明 GeoPhys Nut 渲染通过。需要在现有 owner 确定可验证的同快照 Scene/Artifact 绑定和物理导入影响后，才能执行 reset→首帧→动作→后续帧→reset→close，检查同一边界及 render 不推进。guard 没有删除，旧 H5 和失败未改。该缺口未关闭，7c002 不作完整接收，develop 未移动；历史过程偏差的维护者有界决定不等于渲染通过。

## 后续：维护者授权 canonical Artifact 后的修复与证据

以上未闭环记录保留为当时事实。维护者随后明确允许 Nut 使用与 PickCube 对齐的 v1 Artifact，并要求以实质物理输入与新旧轨迹比较评估影响。GeoPhys Nut 现从真实 execution receipt 的 importer XML 和同一快照资产构建 Panda/Task Scene，经现有 `bind_reference_scene_source` 构造 source 和 TaskArtifactV1；reset 使用现有 `sample_episode_reset_plan`，校验实际 TaskSource、Scene 和 Artifact。v0 helper 仍精确匹配；v1 TaskDefinition 的 reset 要求其确切 Artifact identity。共同 source、Controller 绑定和现有身份 guard 保留。此更改影响所有 GeoPhys Nut 构建，不仅开启渲染时；MuJoCo 仍使用原 v0 route。

| 证据 | 结果和范围 |
| --- | --- |
| `render-geophys-003` | 原 Panda、GeoPhys CPU isolated worker、seed19、128×96 Rasterizer observer；首帧、非零一步后帧、再次 reset 后帧均为 HWC uint8、非空，render 前后公开状态与时钟不变，close；同 run H5 独立读回 1/2、ordinary。三张 PNG 保存于运行目录；主体较小，不据此判断细节几何准确性。 |
| `random-geophys-006` | 同新 source 的 32 步普通 action、真实关节与夹爪响应、逐区间 ACK 和 5×2 ms，close；同 run H5 独立 32/33，ordinary。worker 子步按 160 保守计入。 |
| `solution-guard-geophys-001` | 新 source 下 foreign identity、缺 request、stale 与 reset 后旧 proposal 被拒绝；合法 proposal 一步成功，普通动作混用被拒绝，close，H5 独立 1/2。非完整 Solution 回归。 |
| `review-followup/trajectory-comparison.json` | 新旧 GeoPhys 相同 seed、32 条相同动作、33 边界，state 1,815、task metrics 759、feedback 132、requested action 256 个数值的最大绝对差均为 0；非数值字段也相等。这是用户认可的该输入轨迹强证据，不外推所有动作。 |
| `review-import-equivalence-003` | 以 source name 对应比较原始和投影导入的 15 body 质量属性、10 joint 的轴/frames/limits/dynamics、106 shape 的资源/变换/角色/缩放及 physics，所列字段相等；两次 importer 均有一条 retained/rejected semantics 警告，不概括为所有 MJCF 语义等价。前两次比较按 hash 派生 ID 的顺序配对失败，其日志保留。 |
| `review-reset-guard-001` | 不同 Artifact、错误 Scene 和 v0 helper 接收 v1 的负例均拒绝。 |

最终三个生产文件 hash 及运行预留见 ignored `review-followup/final-run-plan.json`；独立审阅已核对 hash、渲染与随机 H5、guard 和上述比较，未发现受测交集的具体阻断。旧 source 和旧 H5 不改、不冒充新身份。完整新版 GeoPhys Solution、其他相机和其他 provider 未因本次变更重跑；维护者明确要求不重跑完整 Solution 和其他后端。资源和连续子步计费见 `review-followup/run-ledger.json`。
