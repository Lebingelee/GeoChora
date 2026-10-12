# P1.8 Pre-D0–D2 最终准备审计：当前微调设定

## 结论

**Human Review材料：READY_FOR_REVIEW。Infrastructure：NO-GO。正式D0–D2 Campaign：BLOCKED。**

| Provider | Hz | 来源 | 授权 s | 开度 mm | 力 N | 抬升 mm | 漂移 mm / rad | G0 |
|---|---:|---|---:|---:|---:|---:|---|---|
| geophys | 500 | 新运行 | 0.932 | 33.504 | 9.048 | 100.891 | 0.015 / 0.000376 | PASS |
| geophys | 100 | 复用 | 0.930 | 33.468 | 9.132 | 101.523 | 0.022 / 0.000318 | PASS |
| geophys | 50 | 新运行 | 0.920 | 33.275 | 9.996 | 102.133 | 0.022 / 0.000269 | PASS |
| mujoco | 500 | 新运行 | 0.932 | 28.593 | 9.024 | 97.216 | 5.460 / 0.037855 | PASS |
| mujoco | 100 | 复用 | 0.930 | 28.524 | 9.163 | 97.299 | 5.459 / 0.037839 | PASS |
| mujoco | 50 | 新运行 | 0.920 | 28.567 | 9.077 | 97.398 | 5.481 / 0.037742 | PASS |

## 与旧审计的区别

旧审计44.895mm的GeoPhys高度门失败保留原结论；当前采用用户授权的45.895mm/取消绝对高度门诊断，不覆盖历史，也不自动迁移默认profile。两个TB100结果hash复制，四个500/50单元新运行。历史MuJoCo4550物理边界精确对照只证明原44.895mm提取前后等价，不用于宣称当前改动精确相同。当前抓取位置变化是明确行为改变，而非重构误差；source identity和physical behavior分别记录。

## 已验证

30个fresh contracts；Artifact/Reset identity不变；R1/PickCube/arm/gripper/planner/runtime/trajectory源未变；四provider源码保留。当前recipe synthetic12204正向/9反例通过；六cell实际interval重构/native count/cap/hold检查见JSON。原3576hash复核和关键原件恢复通过，新增视频像素decode；安全清理0bytes。

## 阻断与风险

Live recorder未串接owner checkpoint+完整interval；GeoPhys100/50原时钟被v0 one-ULP拒绝，derived误差界通过不能替代规则批准。没有真实native状态checkpoint恢复、T1/full专家、六完整任务goldens、正式replay及boundary资格。辅助pad穿透风险与单reset适用范围保留；同盘归档无off-host冗余。

## Human Review决策

1. 是否采用此task-local shared grasp recipe；默认仍44.895mm/高度门。
2. 审查versioned owner/interval与时钟方案，批准live recorder实施和真实恢复验证。
3. 处置辅助pad风险，另行授权T1/full后再冻结source goldens和formal replay oracle。
4. 确定off-host archive备份位置。

本轮未执行T1/full/D0-D2/SAPIEN/Genesis，没有声明Phase I关闭或NutAssembly qualified。

## 行为变化定位与视频

对旧44.895mm轨迹，当前首次物理字段差异为500Hz boundary240、100Hz boundary49、50Hz boundary25；这是明确的抓取目标改动，不是重构精确等价。关闭跨boundary arm target精确保持检查也通过。六单元腕部MP4与SHA已保存，见media_manifest.json；均为记录状态renderer-only重建，无渲染时物理推进。
