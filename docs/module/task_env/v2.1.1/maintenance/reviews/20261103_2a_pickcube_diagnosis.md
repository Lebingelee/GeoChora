# G02/2a PickCube 归因交付摘要（attempt001）

日期：2026-11-03。状态：`REPORTED_PENDING_REVIEW`；本摘要由执行代理提交，未代表 Sol 或维护者接受。

## 输入与范围

工作包 `V211_G02_2a_attempt001`，manifest SHA-256 `d4ff0b48efd942d52eb468156d591f20a0eae4c53ca4bfcc9345c26041bc6c97`；Core 输入 `develop@fcf0700a5ddaff85e7beb190f018d9f71d94100b`，GeoPhys gitlink/checkout `67da1165149486d3ae3e779c13ce31af49e17d50`。仅做历史失败复用、当前源码归因及一条 seed31 MuJoCo CPU 公共 Harness 复现。未改生产代码、未实施2b、未跑三后端九格。

## 诊断结果

当前运行 227 个 control transitions（5×2 ms substeps），`RUNTIME_VALID`、独立 HDF5 读回 `PASS`、close `PASS`。任务在 `over_cube_before_descent` 连续100个 gate-hold 样本未满足实测 TCP clearance，失败原因为 `measured_tcp_clearance_timeout:over_cube_before_descent`。attempt227（2.26→2.27 s）请求 TCP `(0.635134,-0.086464,0.753000) m`，实测 `(0.600891,-0.081910,0.716055) m`；对 cube 顶面的高度为 `0.203427 m`（要求0.215 m），水平误差 `0.034545 m`（要求≤0.010 m）。运行未进入下降或关爪，cube lift `0.000628 m`、task success与Expert complete均为false。

本次 `step_trace.json` SHA-256 与F06历史 MuJoCo seed31逐字节相同；当前与历史源码身份不同，故仅称失败行为在输入HEAD上的重现。F06 seed33曾通过同类 gate，反证该 gate 对所有 seed 均不可达。静态 grouped R3 gripper 内环风险在本次失败阶段之后，尚非该失败的已证原因。

## G0–G5 自评

| Gate | 结果 | 证据摘要 |
| --- | --- | --- |
| G0 输入／范围 | PASS | 包ID、checksum、snapshot、HEAD、pin与保护文件hash一致；范围仅2a。 |
| G1 源码与历史 | PASS | 当前公开调用链和 F06 源身份差异已登记；seed31时间/状态表和seed32/33反证保留。 |
| G2 最小复现 | PASS | 当前 MuJoCo 公共运行、T+1记录、同run独立读回、close、进程组结束及双锁释放齐全。 |
| G3 因果归因 | PASS（近端机制） | measured TCP→门限→100次hold→明确Solution失败原因形成逐样本链；更下层目标/参考/执行差异仍未区分，未归罪于R3。 |
| G4 下一步 | PASS（方案） | 建议2b由PickCube task owner做定向FIX，保持gate、lift oracle、碰撞和reset；先查公开pose差值，夹爪只在到达close段后单独验证。 |
| G5 交接／清理 | PASS（待审阅） | 仅五个授权tracked路径提交；ignored原始输出、资源账、中文完整报告及manifest保留；保护hash不变，native窗口与锁已释放。 |

## 交接边界

报告建议状态 `PASS（2a诊断交付）/REPORTED_PENDING_REVIEW`。这是可审阅的2a交付，不是Sol验收，不授权2b，不构成任务成功、跨后端等价或Qualification。完整证据见本地 ignored 输出 `workspace/maintenance/v211_g02_2a_attempt001/report.md`。
