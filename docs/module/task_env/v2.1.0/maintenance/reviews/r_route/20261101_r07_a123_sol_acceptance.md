# R07 A123 技术部分：Sol 有界接受（2026-11-01）

决定：**`ACCEPTED_BOUNDED_R07_A123_TECHNICAL`**。

接受范围是固定 LIBERO/robosuite 来源、当前 profile 和冻结序列上的三个任务、MuJoCo/GeoPhys CPU 的 A 阶段技术交集。任务2 GeoPhys 的接触前偏差按维护者明确批准的本次限定例外接受，不提升为一般跨仿真器等价性。

**文件级许可与署名仍为 `UNRESOLVED_FILE_SPECIFIC_LICENSE_ATTRIBUTION`。本决定不关闭来源/许可门，不授权资产再分发或发布，也不表示整个 R07、R00–R07/P99、Solution 或 Qualification 已完成。** 这项技术接受与未关闭门分别记录，可以开始准备 F/R 集成方案；本轮没有执行 merge/push/tag/Release。

## 代码与证据

- Core 最终代码：`d6fe8e1bff52854e4b69fb79235f0ef0386cc83b`，含 `22f6946a` 的 reset/reference/gripper 修复、`d338b2b6` 的已批准 task3 监视容差和 `d6fe8e1b` 的 V1 回归覆盖。
- GeoPhys pin：`7d3d3d082ce871de1ddc5333505eaeebecf28246`；Menagerie pin 保持 `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。
- 固定上游：LIBERO `8f1084e3132a39270c3a13ebe37270a43ece2a01`、robosuite `fbee5844ff5632f5b5698e204ec5357ca50be0df`；MuJoCo 3.8.1、20 Hz、25×2 ms。
- [Luna 原始返工报告](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/libero_a123_review_rework_20261101_001/report.md)保留交回时的 pending 状态；此页是后续 Sol 决定，不改写原报告、运行结果和失败。

| 任务 | MuJoCo | GeoPhys | 有界处置 |
| --- | --- | --- | --- |
| 黑碗放盘上 | 复用已接受的95动作结果 | 复用已接受公开 reset/step/close | v1夹爪2,375子步目标离线精确一致；不重开旧接触门 |
| 打开中间抽屉 | 103动作 / 2,575子步 | 103动作 / 2,575子步 | GeoPhys偏差使用维护者限定例外 |
| 推盘到炉前 | 245动作 / 6,125子步 | 245动作 / 6,125子步 | 已批准A范围；成功谓词不可用不作任务成功 |

任务2 MuJoCo 与上游在首次目标接触前的 TCP 位置 P95/max 为 0.546/0.605 mm、姿态为 3.841/4.030 mrad。GeoPhys 为 33.143/37.916 mm 和 229.074/259.412 mrad；维护者回复“接受本次限定例外”，仅对应此次来源/controller/action capture。没有以此提高一般 tracking 阈值，也没有把该偏差归因为接触求解。

任务3相应 MuJoCo 位置为 0.620/0.780 mm、姿态为 1.241/2.118 mrad；GeoPhys 为 0.945/1.153 mm、1.174/1.303 mrad。task3 的 MuJoCo A 回放夹爪监视容差500 μm来自维护者明确答复，保留原始过冲；它不修改夹爪命令，也不应用到其他任务/profile。GeoPhys reset关节角2e-7 rad门保持独立。

## Sol 验证与限制

1. 读取实际 diff，确认旧 v0 reset 的零速度/无fixture行为和 V1 source/closure验证恢复；A入口使用现有 reference V6，V7仅保留为改进profile；v1夹爪0/80 mm与opt-in v2分开。
2. 独立运行两份定向测试：**9 passed in 0.38s**，未启动native。
3. 验证 manifest 的26份证据、5份代码和7份待审文档哈希；从原始上游capture及四份最终candidate输出重算动作数、步数、raw action、完成/close和接触前位置/姿态统计，与报告相符。
4. 只读核对维护者批准的 task2例外、task3监视容差与来源未决答复。没有替维护者补造许可判断。
5. provider contacts、task3炉前predicate不可用；辅助IK未收敛记录保留。没有完整seed覆盖、像素等价、自主任务成功、控制器资格或通用provider能力声明。

本次 staged diff 空白检查、新增接受链接和 Phase 文档哈希检查通过。全库 `validate_docs.py` 已执行但未通过：它按旧 consolidation 基线将后续产品源码列为 non-documentation changes，并报告文档数量超出旧限制、本 checkout 缺少既有 R03c ignored 报告链接；不是本次文档局部检查的通过结果。原始日志保留在 Sol 收据目录，不为取得绿色而修改历史基线或补造报告。

Sol 机器收据和前稿位于主 checkout ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_accept_libero_a123_20261101_001/`；运行证据仍在 camera 原目录，后续集成/清理前须保留其字节与映射。

下一步是收齐本次文档本地提交并准备 F/R 集成核对，保持未关闭的来源/许可事项独立可见。高精度控制改善、自主 Solution 和 Isaac Sim 仍为可选/延期工作，不再因为本次技术接受自动启动。
