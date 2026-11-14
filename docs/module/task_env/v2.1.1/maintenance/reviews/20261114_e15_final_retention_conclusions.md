# E15 最终保留结论与证据闭包

本表冻结**整理所需保留的既有结论**，不新增或变更 G01～G05、U4／U5 的接收，也不代表 U7 项目接收。每行分别使用原 run 的源码、配置及证据身份；索引中的历史路径用于映射，不要求重建全部旧 attempt 或使旧 manifest 完整可运行。现有对象和内容索引优先复用；后续查找仅针对表内或本表下方列出的实际闭包缺口。

| 保留结论及边界 | 原源码／配置身份 | 必要原始证据及 source／资产 | 读取／复核入口 |
| --- | --- | --- | --- |
| G01 协议与设计有界接收；不是 native 或物理成功 | 1a～1d 各自历史 HEAD；主审后协议快照 `11b1e6c5`，五项仍为 draft | 四组原报告、manifest、主审及五份协议快照 | [G01 包内入口与设计重算](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/stage01/README.md)；[原路径／内容索引](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/stage01/index.json) |
| G02 PickCube 诊断与 MuJoCo 参考按各次结果接受；追加实验不证明任务成功或唯一根因，seed32 失败不改写 | 四份 2b H5 记录 `8fba7f8f`、各自任务/seed/配置和逐文件哈希；并非进程内加载字节的独立测量 | 最终选中诊断原始数据、四份 H5、历史源码对象及 2c 冻结文件 | [G02 包内入口、诊断与隔离读回](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/stage02/README.md)；[源码身份](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/stage02/code-identity-recompute.json) |
| G03 构建/reset 及配对方向有界接受；原 N08 绝对门 FAIL；3a 两条恢复只支持 10 控制步和关闭 | 3b 终选记录 `305b1fa5`、3c `af663868`；各 H5 的 seed、配置和源码哈希分开 | 选中 H5、动作/状态与 source receipts、69 文件 MuJoCo 闭包、Panda XML、重建 Nut XML 及原审查 | [G03 包内入口与重算](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/stage03/README.md)；原 N08 两份历史源码哈希缺口及 OBJ 间接材质限制继续保留，不把重建字节说成进程测量 |
| G04 控制、方向对照和 reset 按原冻结口径接受；ACK 不是独立测力，4c 同一对象与拒绝时机是联合证据 | 4b 最终身份 `a7181de4` 及各运行记录/影响表；4c 同次脚本、H5、日志及 source 各自身份 | 4a 选中子步日志和源码、4b 原状态/对照及失败记录、4c 三份切换 H5 和 native19 同次完整记录；选中 source/资产闭包 | [G04 包内入口与联合复核](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/stage04/README.md)；4b 未完整保全当次中间源码的受限影响分析不扩大 |
| G05 renderer、相机及统一主体按原 5a/5b/5c 选中运行和六门接受；COM 原严格门 FAIL，R05c NOT_REQUALIFIED | 各运行按索引中 source/provider/renderer 原身份区分；cross 的 69 文件及 `17bde018`＋记录 diff 身份独立，canonical XML 绝对 meshdir 与 5a 不同 | 选中原 RGB/XWD、raw、H5、receipt、source/USD 对象与原 reader；必要 R05c 和解释当前限制的核心诊断 | [G05 包内入口与六门](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/stage05/README.md)；不由短程帧或 ACK 推导完整任务或测力 |
| E11～E14 代码优化/U4 有界接收；U3 四条 CPU 与 Isaac `solution-002` 各保留冻结身份；T19 联合证据成立，H5 单文件不自含完整 completion | CPU 各自 base/repair 与录制哈希；Isaac 采用 `0506ae26` 夹爪专项受测身份、seed31/原 1000 步 horizon，951 步完成、抬高 105.254 mm、4,755 显式子步 | 五路原 H5、同次 caller/监督/关闭与源码配置、两 Nut source receipts、夹爪必要诊断、U4 独立审查；旧 Isaac 失败仅为诊断 | [优化入口及包内联合复核](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/optimization/README.md)；CPU completion 不存在、Isaac 为 null；主动结束与 `external_stop`/recording `truncated` 按原语义区分 |

## 内容复用与当前必须核对的缺口

1. **Panda 资产。** 历史 285 套各 67 个 OBJ/STL 的文件名及 SHA 完全相同，共 19,095 条原路径、67 个内容 SHA；以现有 U5 冻结对象作字节来源，保留各选中 source/receipt 的路径—内容及运行身份映射。必须在具体方案中完成当前 fixture、包内 reader、旧绝对 meshdir 和必要重建入口的检查；不要求 285 个旧目录继续原地运行。不能把 OBJ 的未随 receipt 保存的间接 MTL 材质扩展为已证实闭包。
2. **闭包和调用。** 以 [U5 最终选择](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/retained-claim-selection.json)、[包内入口](../../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/README.md)及已有读回收据为准，核对最终 reader 所需内容对象、source/资产索引、当前 fixture、保护输入和双 pins；按已接受限制记录旧 N08 源码、4b 中间源码、T19 completion 与外部环境依赖，不为追求完整历史 manifest 补跑或补存所有过程。
3. **实际处置与例外。** 将已选核心对象、当前 caller、共享锁、第三方源码、冻结 archive 与独有成果排除；对历史运行自有 Kit/shader/Taichi/OptiX 缓存和无必要的输出准备精确路径。257 条旧 overlay 链接仅保留目标映射，拟移除链接本身；loader 001 原位大事件流作为已形成历史更正的单项保留例外，不是本表接收结论的必要核心证据。同内容记录仍区分运行身份；未选中的早期成功 H5 等历史运行不再保证原样重放。不能从旧报告的所有过程引用推导保留义务。
4. **临时材料与度量。** 对此前新增归位、重复资产和工具过程输出按本表裁定，复用现有 U5 对象与样本恢复，不再建立全 workspace 副本。真实净额在执行后按同序 `du` 同时计入保留与分类新增量；历史累计缺基线为 UNKNOWN。

当前总体状态、清单版本和审核边界见[压缩状态入口](20261114_e11_e16_e15_residual_classification.md)；详细历史记录保留但不自动转化为本表的保留义务。最终具体清单需维护者集中授权，项目接收仍由维护者决定。
