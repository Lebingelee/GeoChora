# G03/3a attempt002 执行摘要

状态 `REPORTED_PENDING_SOL_REVIEW`；输入 `81e257cbef6c3469ba23fadcfe481d93b114f4d1`。**CORE_RUNTIME_RECOVERY_PASS**：PickCube seed31 和 NutAssembly seed19 通过正常 `make_env`、真实 MuJoCo CPU reset、各10个 `Solution.act → env.step → observe`、close；两例各推进0.10秒，状态／观测／奖励有限。物理步合计与失败、重试、命令及日志见本次 ignored `workspace/maintenance/v211_g03_3a_attempt002/report.md`。

修复普通 MJCF 对实际引用 Panda mesh 的有界读取、canonical／importer XML及快照来源绑定，让原 MuJoCo importer 消费相同资源字节；重建来源与预检闭包一致。增加实际 named joint/body/site/actuator 检查及缺失 mesh 反例；JSON 非对象回复转为协议错误并回收 worker。相应离线测试24 passed。没有更改资产物性、Solution、pin或依赖。

本结果仅覆盖两例10步，不是全3a接收、任务成功、完整轨迹或三后端物理验收。R2 通用 build oracle／更广的嵌套与 typed 状态、GeoPhys／Isaac真实执行及 qualification 等仍需Sol判断和后续安排。维护者手动交Sol独立复审；不自动进入3b。
