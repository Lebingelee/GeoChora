# 阶段3前维护 attempt001：交付与待复审

输入：`develop@4bdf4d5ff9c7699a561454ebdd10ca5cea29e6c4`。本项独立于七阶段，不改变阶段2接收决定，也不启动阶段3。交付状态为 `REPORTED_PENDING_REVIEW`；本记录是有界实施与未完成项，不是验收结论。

- `631d4351` 将旧 trajectory replay 的历史构造边界从 diagnostics 反向依赖移入 environment 内部；diagnostics 原入口保留转发。PickCube 历史 UID 继续拒绝，Nut 兼容构造不等于精确恢复旧源码。Isaac 监督入口新增外部解释器选择；记录开始时采集 adapter 源码摘要并供同次记录复用。
- `baf441a4` 在执行边界复用相同 XML 字符串的摘要；内容变化时重新计算，动态边界身份仍重新生成。
- `8c2b042e` 将 selected 环境和内部绑定移入 `environment`，更新生产调用者、compatibility 导出及同源 replay 的来源身份；`4a554cdb` 将 Position 录制 metadata 投影移入 recorder。`c2c0cb2f` 修正当前 API 导航中关于旧 BaseTaskEnv 和并行能力的说明。这些是迁移中间结果，尚未完成旧任务迁移。
- `6c193d07` 补充显式路径启动入口和安装指南，只有离线参数检查，尚无该入口的 native 验证；`3bb6f0ad` 将 selected 观测投影归入 observations owner，同源身份随之更新。
- `b1e9f2a7` 与 `d542b635` 修正新手、任务开发、配置、reset 和当前语义说明；`5c9b2bf7`、`ff894102` 移除 classic Env 中无读取者的状态副本。仍须在真正统一生命周期后重新核对这些页面和调用者。
- `12cc64e1` 修复已有 GeoPhys 零 DOF、无 reset sampler 场景中不适用的 articulated 静态位姿读取；显式静态位姿覆盖会被拒绝，articulated 原有恢复路径有正例。Empty 单环境重试在该提交 reset/step/close 成功，原失败保留。`a1727403` 之后复用不可变 Artifact 的 canonical 摘要，`c77e7838`、`9b78b50b` 补齐低层篡改与 signed-zero 失效检查；不能将此后代码混同于早期 native 结果。
- MuJoCo CPU PickCube seed31 和 Nut seed19 在 `a1727403` 分别完成 960 和 2377 transitions、task/Expert success 和同 run 独立 reader；这不是后续源码或完整维护的验收。`f6e4e70c` 将 LIBERO benchmark 接入现行 Core `TaskCompositionSpec`，冻结资产的 provider-free 31 项检查通过，不改任务判据或数据。
- 先前源码另有同方案的 PickCube/Nut MuJoCo CPU 代表运行与独立读回：分别 960/2377 transitions，任务和兼容 Expert 完成；三个 classic 任务各有 GeoPhys CPU 最短 reset/step/close 检查。详见工作报告的 run、提交和限制；classic 尚未迁入统一生命周期，这些结果不满足 G1。
- Phase C 的标准方向是外部 Solution 基于 observation 产生 action，再由调用方 `env.step(action)`；`step_expert()` 是迁移前的受限兼容而非标准 Env API。现有 `step_with_solution()` 路线虽由调用方持有 Solution，Env 仍调用其 act/observe，不能称通用外部 action 迁移完成。Nut 现有调用方驱动的 `act → step(action) → observe` 路径，采用来源绑定的 `ExpertAction`，返回五个 native 样本并在 Solution 侧校验。合成反馈、负例及 H5 检查通过；新路径完整物理成功待验证，录制发生在调用方 observe 之前，旧兼容路径的录制顺序保留。
- Position 单／双 Entity 与 leaf 录制投影及 reset 录制 metadata 已归入现有 recorder owner；F04 和 attached leaf 合成 H5 验证通过，部分依赖真实 scene 或缺历史 fixture 的检查未通过／未运行，具体见工作报告。
- 有界离线检查确认摘要重用、内容替换及解释器选择；较宽历史测试有失败，具体命令与结果见 ignored 工作报告 `workspace/maintenance/v211_pre_stage3_refactor_attempt001/report.md`。上面所列代表性 native 与独立 reader 属于当时的源码提交，尚不覆盖最新源码，不能从静态检查推断最新源码运行成功。
- 唯一环境实现、三个旧任务迁移、完整当前文档与启动路线均尚未完成；G1、G2、G3 未通过。本页不代表 Sol 接收，也不把旧证据重标为新实现证据。
- 维护者追加的任务目录收敛决定及 staged 规划由 Sol 在本窗口释放后与实际输出整合；当前三个共享 task 根模块、Marker 中间层／包装、PickCube 的 `isaac.py` 和 Nut 的 trusted source manifest 尚未按该决定迁移，当前 Marker 教程仍需同步。该决定不改变此窗口预算，也不表示阶段3已启动；详细路径与真实调用者见本次工作报告。

## 实际门状态与移交

| 门 | 结果 | 说明 |
| --- | --- | --- |
| G0 | PARTIAL | 输入、pin 和保护文件匹配；一次 P99 有监督运行含真实单步时 cwd 使用了 Core 根，已记录，不能算合规 native 验收。 |
| G1 | FAIL | 三个 classic 单环境仍用独立 BaseTaskEnv／lifecycle，未完成同对象 alias；后续范围决定要求的三个共享模块、Marker 中间层、PickCube Isaac 文件及 Nut source manifest 也未完成归位。 |
| G2 | PARTIAL | 静态来源优化和动态负例、Nut caller 合成行为与独立 H5 读回有证据；最终源码上的完整 PickCube/Nut 物理回归及已迁移 classic 任务检查均未完成。 |
| G3 | PARTIAL | 当前入口和多页已实质更新、启动器与路径检查已交付；新范围下 Marker 指南及最终统一接口仍须更新，完整安装组合未验证。 |
| G4 | PARTIAL | 运行、失败与限制保留；旧物理成功和 reader 只属于其当时源码，不能重标。现有合成 H5/reader 不证明物理成功。 |
| G5 | PASS | 本地提交、工作报告、文档校验及此待复审记录已准备；状态仅为 `REPORTED_PENDING_REVIEW`，不是接受或整体通过。 |

本次工作报告位于 Core 的 `workspace/maintenance/v211_pre_stage3_refactor_attempt001/report.md`，索引和逐次监督／读回结果同目录；此前旧 raw 与受保护 untracked 未重写。维护者追加的 `V211_PRE_STAGE3_scope_decision_20261104` 明确由 Sol 在当前 writer 释放后依据实际 HEAD 合并 staged 规划与未完成范围，维护者手动转发；本窗口不叠加该后继执行、不进入阶段3。Sol 应独立检查 Nut caller 动作／反馈、录制与 provenance，及上述 G0/G1/G2/G3/G4 缺口。
