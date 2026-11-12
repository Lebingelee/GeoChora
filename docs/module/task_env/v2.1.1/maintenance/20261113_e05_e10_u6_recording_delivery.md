# U6：Recorder 与 replay 实施结果

状态：实施者自评；独立主审与维护者接收待完成。输入 `5cb0d470`。本单元对应专用账本 S31～S36 和总账 REC-01～03，不覆盖 E13 完整 Solution。

| 项目 | 当前结果与边界 |
| --- | --- |
| S31 writer→reader | 带物理控制的正式短记录使用 `TransitionRecorder → task-env-h5/v3 → load_physical_recording_h5`，包括 schema、结构化控制、状态、clock、可选 task RGB 和 outcome；旧 canonical/execution writer 保留自己的版本及 reader，不能声称其自动保存 task RGB。 |
| S32 历史分层 | 通用 H5 保留 v3 完整性；`legacy_typed_witness` 解码有标签的 F05/F06 旧见证；`load_legacy_leaf_control_h5` 解码旧 leaf 观测和控制；R02c/R03c 原严格实验判断迁入版本诊断 `legacy_leaf_judge.py`。原 `load_leaf_control_records_h5` 公共入口退休，API 指明迁移；核心不反向导入诊断。两个被迁出严格函数与输入 AST 相同。 |
| S33 metadata | Env 启停交由已有 Recorder owner；physical metadata 消费实际主体、action schema、source、控制绑定和发布状态。Pendulum／双轮车一 Controller 一 action group 的正式物理入口不再要求 Solution 身份。受限选项仍在开始记录时拒绝。 |
| S34 provenance | 实际 Nut MuJoCo 一次正常 recording：开始时 `source_snapshot` 调用 5 次、对应 5 个不同源码文件；一次 interval 后仍为 5 次。此次测量不证明所有文件 I/O 或所有路线均无热点，因此不新增跨 reset 缓存，也不宣称性能提升。 |
| S35 replay | `inspect_selected_replay` 离线检查外层格式，不代表源码身份或重执行通过；旧 selected replay 仍检查 source，跨源码和不支持格式拒绝。以模拟 foreign source 确认拒绝发生在 `make_env` 前；没有声称跨源码或新 structured 格式可重执行。 |
| S36 读回 | 最终输入的 MuJoCo Pendulum RGB、双轮车、Panda physical RGB 运行各一个记录 interval 并二次 reset、重复 close；显式物理子步 25／25／10（Panda probe 包含切换后另一 interval）。独立无 SDK 读回同次文件，T=1、T+1=2，校验声明的动作、状态、边界和 clock、终止；RGB 两帧和 capture 身份随状态绑定。Pendulum 的 clock 为 0→0.05 秒，horizon 8。篡改时钟被拒绝。RGB 内容本身尚无独立字节摘要；旧多模态 Position 实验 camera reader 是不同合同。 |

最终证据位于 `workspace/maintenance/v211_e05_e10_u6_20261113_001/`：`physical-record-release/native-plan.json`、各 `result.json` 与 H5；`readback-release/plan.json` 和 `result.json`（12 项通过，禁 SDK import）；`ownership-test/result.json`（Panda metadata owner，1 项通过）；`provenance-count/nut-record/result.json`；`legacy-read/ast-comparison.json`。真实旧 R02c/R03c H5 只读通过严格 Judge，复制文件篡改边界后拒绝。Nut 常规 execution 短记录与 PickCube canonical RGB 记录分别保存并读回，但后者的 canonical 格式并未存储 RGB，不将其混同为上述 v3 同次记录。初次 Nut RGB reset 因 source closure 不满足准入被拒；初次 Panda physical runner 将 10 个实际子步误设为 5 的预期，probe 本身通过后 runner 断言失败；最终均按冻结计划独立重跑并如实保留失败记录。

相对本单元输入：已跟踪 blob 1383→1389（+6，排除两个 submodule gitlink）；新增 `recorders/legacy_typed_witness.py`、版本诊断 Judge、三个检查文件及本实施记录，无整文件删除。生产代码 +401/−721，净 −320；其中约 110 行 F05/F06 witness 从 H5 迁入 codec，约 480 行旧严格 Judge 从生产 H5 迁入诊断，迁移并非凭空减少。版本诊断 +646/−4，含上述迁入；本记录和索引文档另计。按当前 stage 5 基线 `1f1359ee` 到本单元生产 diff：生产及其他代码 +7749/−17256，净 −9507；该累计包括此前单元，不能归功于 U6。文件与文本统计不代替行为和职责验收。

限制：最终 MuJoCo 真实记录并不证明 GeoPhys/Isaac 新记录路径，相关代表性补测和最终影响映射留 U7；不扩展完整 Solution 或声称 task success。历史测试目录中旧严格 reader import 不再作为兼容目标，必要的当前检查已迁入 v2.1.1 诊断。未改变 protected untracked 输入、子模块 pin 或历史结果。
