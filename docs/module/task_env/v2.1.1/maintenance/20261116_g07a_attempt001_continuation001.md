# G07 7a attempt001 continuation001：装配路径实施记录

状态：`IN_PROGRESS`，独立主审和 7a 接收尚未完成。原 attempt001 延续，7b／7c 未启动。输入 Core `c2ed2f3d236ba480fc6f66c368af4b707b69b15c`，原执行输入 `7862433cafef91800e7b0321b774dcb64b22c777`；GeoPhys `198d30ac64ce873a1467f55d2adfc471db18fbc5`，Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。运行时工作树含本包未提交的实现；轨迹中的 source revision 是输入 HEAD，不能误认为运行时无 diff。详细案例—owner—台账—证据、失败、命令和监督回执见[本地续接报告](../../../../../workspace/maintenance/v211_g07a_attempt001/continuation001/report.md)。

本包沿现有 Robot recipe、source composition、Controller、session 和 Task binding 接通装配 Panda；来源模型和重力补偿绑定实际装配，原 Task Solution 策略和任务判据保持。组合源将 Task 原有具名执行器参数保留到匹配传动上。原 Panda／装配 Panda 与 PickCube／Nut 四个 MuJoCo CPU 交集分别完成真实 caller、原 Solution、同运行 close，以及独立正式 H5 读回：

| Robot／Task | seed | 控制步／边界 | caller 完成与任务成功 | H5 SHA-256 |
| --- | --- | --- | --- | --- |
| 原 Panda／PickCube | 31 | 960／961 | done，成功，close | `4d90e80b503429ba510040c8870d9f54319bf858366f1396a275e6a30c41b682` |
| 装配 Panda／PickCube | 31 | 946／947 | done，成功，close | `89adee65c416174a36c4f9d5382ccef04c8b1e2ec96d24f9c70ad6de0c620ee9` |
| 原 Panda／Nut | 19 | 2377／2378 | done，strict／planned 完成，成功，close | `4a49bfa6937116991e38946fa7a58fbcc9caa7e5f28629ea3499722200eb681d` |
| 装配 Panda／Nut | 19 | 2378／2379 | done，strict／planned 完成，成功，close | `ea9cab5c92a606d9b4cb47832059141ce304bbc5bf3e2ead7c8f8be6ce85bfba` |

装配 PickCube 原始失败保留：close 从 608 步持续到 1000 步上限，未进入 lift；修正 source 驱动参数后 close 为 84 步，最终 lift 105.3 mm。装配本体的冻结精度路径在 300 个 control interval、1500 个 native substep 下满足预定 2 mm／0.03 rad 容差；300 个提交 ACK，补偿样本无目标限幅或力限标记。最终 source 模型的独立 MuJoCo 运动学、Jacobian 和重力 oracle 通过。R1、R1-split 的进程内短运行通过；隔离 worker 的 R1 通过，R1-split 首次提交被现有 owner 校验拒绝，不能宣称该 worker 组合受支持。

SB3／RSL 对 coordinated device 提前拒绝，同时保留 host masked autoreset／terminal observation；旧 RSL device 协议另以 CPU tensor 模拟运行时验证，未声称 CUDA qualification。Nut 原策略和严格完成测试 35 项通过，source／worker 定向回归与完整结果见本地报告。当前 pure 计划中 pendulum 和 two-wheel 的两项旧 `build_runtime=False` 调用失败，拒绝分支与测试在输入 HEAD 未变；LIBERO 旧外部调用向现有 binding 传入已移除参数，在构造前失败，列为未迁移而非添加 fixture 兼容层。

**未闭合：**当前 pin 的原 Panda GeoPhys Nut 运行在开爪释放时超时，独立 H5 读回确认任务失败且 close 返回；旧成功运行使用不同 Core／GeoPhys 身份，原因未确定。用户将该问题交由单独侧边 agent 排查；本包不修改 provider solver 或 Solution 策略，也不将该格计为通过。A2 因此未通过，整体 7a 不得宣称通过或接收；旧 device、LIBERO 和文档／锁／最终提交等逐门结论以本地报告的最新记录为准。7b 三 backend × 三 seed 仍为 NOT_RUN。

`git diff --check` 在此前检查通过；current 文档校验仅报告已知的 `MUJOCO_LOG.TXT` 保护基准差异，实际保护文件 SHA 仍为 `3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`。最终交接前须重新校验状态、预算和关闭回执；不 push、merge、tag 或发布。
