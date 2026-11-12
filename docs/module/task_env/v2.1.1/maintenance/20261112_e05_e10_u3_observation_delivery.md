# E05～E10 U3 状态、观测与相机实施记录

状态：`IMPLEMENTED`（实施者自评）；输入 `73eebf37`。独立主审和维护者接收尚待后续整体工作；不代表 E07、E08 或本轮优化已接收。原始计划、源码哈希、失败和收据见 [U3 证据目录](../../../../../workspace/maintenance/v211_e05_e10_u3_20261112_001/)。

| 检查点 | 最终 owner 与结果 |
| --- | --- |
| S13 | `selected_reference` 组合 binding 的 Robot 状态投影与 Task 物体投影；Panda 的字段、Position 与 physical 视图移入 Robot owner，PickCube state-only switch 的空间、alias、单位和投影移入该 Task。简单主体原有观测不伪造 Panda。fake 非 Panda Robot 证明公共组合不依赖 Panda 字段；直接使用 binding 的 agent harness 显式声明 Panda Robot。 |
| S14 | Robot 声明主体字段、顺序、单位及 frame；Task 由 binding 声明物体和兼容 alias；空间用于生成并校验 schema、实际数组。修复未采样时嵌套 Dict 无法生成 schema；正式 Panda 声明和样本顺序对齐。不同实际 caller 的公开输出顺序仍由其声明保留；缺少语义声明的扩展字段继续显示 `task-defined`，不是虚构物理单位。简单任务保留各自 ObservationBuilder。 |
| S15 | 相机 adapter 从当前 source/Artifact 绑定和声明 renderer 的 joint、frame 与 evaluation-boundary 状态需求并准备 visual source；Env 只协调绑定、独立 publication 和采集。fake 检查确认 renderer publication 不覆盖 Controller publication，并拒绝陈旧时钟；真实 RGB 的控制边界/时钟对照见下。既有 source 绑定函数仍沿用 position 命名，不意味着改变物理控制类型。 |
| S16～S17 | 普通 `CameraSpec → CameraGeometry → source/episode 绑定 → adapter` 保持无预先 hash；已有高级身份、stale、world mount 与 RGB 输出限制保留。真实两个 RGB 路线使用 CameraSpec；本单元未增加深度或动态挂载，不声称重新读回所有 native 光学参数。 |
| S18 | 四任务 schema 在真实 reset、step、二次 reset 校验；Nut 现有正式 info/Solution caller 使用共同 schema，完整 Solution 不在此处验证。camera consumer 的 stale 检查与 publication 独立性有版本诊断；renderer 全部 capability、光学 readback、重复 render 无额外推进及 observer 身份留 U4/U7。 |

| 正式 caller | 字段来源及实际边界 |
| --- | --- |
| PickCube Position，一体/装配 | Robot 的 ee、关节、hand 与 boundary；Task 的 cube pose；Controller 和 renderer 各自 typed view，依同一 Runtime 边界发布。 |
| PickCube effort（非 Position） | Panda physical 投影提供 ee、9 关节、hand 与 boundary；Task 提供 cube pose。GeoPhys × MuJoCo RGB 实采。 |
| NutAssembly Position | Robot 提供主体；Task binding 提供 nut/peg pose；Solution 从正式 info 取 schema。 |
| Pendulum、双轮车 | 各自 ObservationBuilder/Robot 声明自己的 proprioception，Task 提供评价；不引入 Panda 字段。 |

## 实际验证与边界

- [定向 source/合同](../../../../../workspace/maintenance/v211_e05_e10_u3_20261112_001/contracts-final/result.json)：18 项通过，含有效资产构建、fake 非 Panda 组合、嵌套 schema 和 shape/dtype 拒绝、switch alias 复制、相机 stale 和控制 publication 保全。它不是 native 完整矩阵。
- [六条 MuJoCo 路线](../../../../../workspace/maintenance/v211_e05_e10_u3_20261112_001/native-schema/native-results.json)：四任务、一体/装配及 Position/effort 覆盖正式构造、reset、非零 interval、二次 reset、重复 close；schema 验证三次，合计 70 个显式 MuJoCo 子步。短程不证明任务成功或 Solution 完成。
- [真实 RGB](../../../../../workspace/maintenance/v211_e05_e10_u3_20261112_001/rgb-schema/native-results.json)：MuJoCo Position 与 GeoPhys effort × MuJoCo 独立 renderer 均采集 reset、step、再 reset，验证 schema；采集 boundary 与物理读回一致，仿真时钟均从 0 到 0.01 s，第二 episode 身份改变。MuJoCo 记录 5 个显式子步；GeoPhys 子步未独立计数。此处没有额外声称重复 render 的推进增量，留 U4/U7。此两组真实运行后的生产变化仅为公共观测函数文档字符串和独立 agent harness caller 的 Robot 声明，不把运行时 HEAD 改写为提交后的身份。
- [跨 provider reset](../../../../../workspace/maintenance/v211_e05_e10_u3_20261112_001/reset-switch-retry/native-results.json)：MuJoCo R3 一 interval 后切换 GeoPhys，兼容 cube alias、关节速度单位、schema 和 close 通过，MuJoCo 显式 5 子步；GeoPhys 仅 reset 未计步。首次尝试由于目标默认 isolated interpreter 不可用，在切换预检拒绝；重试显式指定进程内解释器，失败收据保留。锁均释放。
- 当前没有在最终 U3 源码下重跑 Isaac 采集；U2 原生证据不冒称本单元采集证据。Isaac 具体 camera/fault 修改及真实采样属于 U4。SDK 隐式启动推进仍未知。

## 总账对照及待办

本单元结束核对 ENV-04、OBS-01/02、REN-03：公共组合不再默认 Panda，renderer 不再由 Env 按控制类型拼状态需求；四任务当前样本与 schema 已对照。ENV-04 的 Recorder metadata、OBS-02 的各 adapter 原生光学参数和 REN-03 的重复 render/跨资源采集仍依 U4/U6/U7 的影响复验，故总账跨事件条目不提前关闭。兼容期内未声明含义的第三方字段仍显示 task-defined；不能据此声称任意主体或传感器已支持。

## 文件和代码变化

本单元与输入 `73eebf37` 同口径：tracked blob 项目 **1,375 → 1,379**、`task_env` **981 → 984**；新增 Robot 观测、PickCube 兼容观测、版本诊断及本记录共 4 个文件，无整文件删除或迁移。生产代码 **+280／−180，净 +100 行**，诊断／测试 **+143／−2，净 +141 行**；文档增减以本次提交 diff 为准。按完全相同的连续行粗略对照，公共观测至 Robot 至少 53 行、至 PickCube 10 行，PickCube physical 至 Robot 24 行，Env 至相机 adapter 10 行；代码有职责重组，迁移量不能按净增删叠加。

相对 5c 输入 `1f1359ee` 的累计 tracked blob 项目 **1,361 → 1,379**、`task_env` **977 → 984**；生产代码 **+6,685／−15,191**，诊断／测试 **+5,343／−0**，文档与其他内容见提交 diff。累计包括 E00～E04 和 U1/U2，不能归功于 U3。
