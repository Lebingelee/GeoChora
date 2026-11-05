# G03/3a attempt003 执行摘要（待 Sol 独立复审）

- 状态 `REPORTED_PENDING_SOL_REVIEW`；整体技术结果 `THREE_A_PARTIAL`，不是3a接收。输入 `2825c5749326fcca60845dde5cae21f9cfcd04ad`，复用 `codex/v211-stage3`；这是第三次、最后一次普通attempt。
- 将实际 task/source/Controller 状态声明投影到assessment，并在 MuJoCo、GeoPhys 和 Isaac 的现有构建点连接具名检查及请求绑定事实。当前查询、info、Recorder 元数据保留同一请求；构建检查不声称 native-effective 参数、物性或资格。
- 最终源码上 PickCube seed31 与 Nut seed19 分别通过真实 MuJoCo 3.8.1 CPU 公开创建、reset、10次 act/step/observe 和 close，均推进0.10秒；真实隔离worker的 PickCube 另完成相同10步。一次实际H5元数据离线读回一致。最终受影响离线组31 passed；这些结果不证明其他后端native或完整轨迹。
- 不能声明整个3a通过：F06真实factory在离线guard禁止 `pxr` 时停在source加载，未到达完整生产preflight；嵌套/versioned StateRequirements 的生产投影helper有离线检查，但完整selected assessment及真实构建连接证据不足；已有mixed-control三通道的合成任务声明通过selected assessment和SDK终端替身layout检查；原夹具模拟过进程库映射，其完整materializer/reset结果不计为有效证据。三adapter中Isaac的helper当前仅有合成source形状测试，不能当作真实F06 source接线通过。
- 输出 `workspace/maintenance/v211_g03_3a_attempt003/` 的 `report.md`、`results.json`、`commands.json`、`output-manifest.json` 和原始日志分别列明失败、复用、未测及资源限制。维护者手动交Sol独立复审；若未获整体接收，必须由维护者组织人工诊断，不自动attempt004或进入3b。
