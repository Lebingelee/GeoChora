# G07 7a attempt001 continuation001：装配路径实施记录

状态：`IN_PROGRESS`，独立主审和 7a 接收尚未完成。原 attempt001 延续，7b／7c 未启动。输入 Core `c2ed2f3d236ba480fc6f66c368af4b707b69b15c`，原执行输入 `7862433cafef91800e7b0321b774dcb64b22c777`；GeoPhys `198d30ac64ce873a1467f55d2adfc471db18fbc5`，Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。运行时工作树含本包未提交的实现；轨迹中的 source revision 是输入 HEAD，不能误认为运行时无 diff。详细案例—owner—台账—证据、失败、命令和监督回执见[本地续接报告](../../../../../workspace/maintenance/v211_g07a_attempt001/continuation001/report.md)。

本包沿现有 Robot recipe、source composition、Controller、session 和 Task binding 接通装配 Panda；来源模型和重力补偿绑定实际装配，任务成功判据保持；维护者之后明确授权对 Nut Solution 的释放高度作有界调整，见文末续证。组合源将 Task 原有具名执行器参数保留到匹配传动上。原 Panda／装配 Panda 与 PickCube／Nut 四个 MuJoCo CPU 交集分别完成真实 caller、原 Solution、同运行 close，以及独立正式 H5 读回：

| Robot／Task | seed | 控制步／边界 | caller 完成与任务成功 | H5 SHA-256 |
| --- | --- | --- | --- | --- |
| 原 Panda／PickCube | 31 | 960／961 | done，成功，close | `69b446c4711e6af1697dbb69d9c2f945cfa4b24b9f2dc4603a0fbb6760d83bc4` |
| 装配 Panda／PickCube | 31 | 946／947 | done，成功，close | `aae41cb7a36a598220b5adb1076b3a6e41fe778bdb4e81473e95ac2d8578de6f` |
| 原 Panda／Nut | 19 | 2377／2378 | done，strict／planned 完成，成功，close | `c78e9325fa147e993e9983e04ab1b5c7ecb7dbc0a77f81768201421167857f6f` |
| 装配 Panda／Nut | 19 | 2378／2379 | done，strict／planned 完成，成功，close | `c6cfd3ebe8acece4e70e94fed5337ba47e96787c6db8b1e5977538f2ac34e4b7` |

装配 PickCube 原始失败保留：close 从 608 步持续到 1000 步上限，未进入 lift；修正 source 驱动参数后 close 为 84 步，最终 lift 105.3 mm。装配本体的冻结精度路径在 300 个 control interval、1500 个 native substep 下满足预定 2 mm／0.03 rad 容差；300 个提交 ACK，补偿样本无目标限幅或力限标记。最终 source 模型的独立 MuJoCo 运动学、Jacobian 和重力 oracle 通过。R1、R1-split 的进程内短运行通过；隔离 worker 的 R1 通过，R1-split 首次提交被现有 owner 校验拒绝，不能宣称该 worker 组合受支持。

SB3／RSL 对 coordinated device 提前拒绝，同时保留 host masked autoreset／terminal observation；旧 RSL device 协议另以 CPU tensor 模拟运行时验证，未声称 CUDA qualification。Nut 原策略和严格完成测试 35 项通过，source／worker 定向回归与完整结果见本地报告。当前 pure 计划中 pendulum 和 two-wheel 的两项旧 `build_runtime=False` 调用失败，拒绝分支与测试在输入 HEAD 未变；LIBERO 旧外部调用向现有 binding 传入已移除参数，在构造前失败，列为未迁移而非添加 fixture 兼容层。

**未闭合：**原 Panda 的 GeoPhys Nut 旧运行开爪失败；维护者定位夹爪触桌后授权调整释放高度，8 mm 候选在同 seed GeoPhys 和原 Panda MuJoCo 下成功并独立读回。但装配 Panda MuJoCo 两次在开爪阶段出现相同 QACC 数值不稳定，不能声称该候选已完成 AP-C4 或整体 7a；未改 provider solver 或任务成功判据。旧 device、LIBERO 和各门结论以本地报告最新记录为准。7b 三 backend × 三 seed 仍为 NOT_RUN。

`git diff --check` 在此前检查通过；current 文档校验仅报告已知的 `MUJOCO_LOG.TXT` 保护基准差异，实际保护文件 SHA 仍为 `3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`。最终交接前须重新校验状态、预算和关闭回执；不 push、merge、tag 或发布。

## 共同构建与 reset 的补充复核

维护者要求在原 G05 单元4／优化账本边界内核对真实构建、默认 Controller、显式选择及 reset。初版提交将 Nut 的装配模型选择重复放在 Task binding 中；续接已归回既有 source composition adapter，两任务均调用同一 Position Controller 选项 owner，再沿原共同 binding 进入 Runtime。上表是该补充调整后的四条完整运行；此前初版轨迹和失败记录仍保留在本地报告。

| 规范条目 | 实际调用链与处理 | 当前验证／限制 |
| --- | --- | --- |
| 共同构建／source | `make_env → selected_binding → SourceBoundTaskBuilder → source composition adapter → Controller → 公共 binding`；Robot 保留 recipe、Frame、Joint、传动 | 原／装配及两任务的 7 个已准入配置，经真实动作和普通 reset 验证；不声明任意装配树或 provider |
| 默认 Controller | 装配 Robot 提供稳定未绑定对象，既有 `bind_many` 绑定真实来源 arm／hand canonical writer | 两个实际 Task 的 native MuJoCo 模型核对关节、执行器、tendon、范围和 .5／.5 耦合；错误单位和外源拒绝。绑定后的 typed effort 计算使用明确标记的 synthetic physical boundary，**未在 Position Task 中提交 native 默认力控制** |
| 显式 Controller 匹配 | R1、R1-split、R3 保留 Task 选择，复用既有 source／scene／writer 绑定与提交；不以默认对象替换 | 两任务各自受支持配置的绑定和真实 step／ACK 通过，错误装配拒绝；R1-split 隔离 worker 限制仍保留 |
| 普通 reset | 既有 reset reconstruction 重建同一选择、参数、source binding 和 Controller 状态 | 7 个真实配置各作两次 reset 及动作，比较初态、profile、参数和绑定；不把普通 reset 当作任意 profile 切换证明 |

共同构建补充时的四个完整轨迹均经独立 readback 并关闭；其 revision 是当时未提交调整的父提交 `cd8a6362`。上表 Nut 行后来由 provider 路由后的新轨迹替换，新轨迹 revision 为运行时父提交 `948f69f9`，均以逐文件哈希记录实际源码身份。共享 native 锁被其他工作持有时未并行启动。审查和各门最终状态以[同一续接报告](../../../../../workspace/maintenance/v211_g07a_attempt001/continuation001/report.md)及其原始回执为准。


## 维护者授权的 Nut 释放高度候选

为避免夹爪触桌，Solution 将释放前螺母底面的规划间隙从 1 mm 调为 8 mm；仍要求插入、开爪反馈、退让和最终成功。Solution 回归 40 项通过；当前 pin 原 Panda GeoPhys seed19 完成 2420/2421，开度约 0.080 m，严格完成、close 与独立读回通过，H5 SHA `274ae0475a45465c05673e93f371e3774988f9ceb8abfc897789988af15cdf6c`。原 Panda MuJoCo 2359/2360、同样完成并独立读回，H5 SHA `471c924ca1383f0bad713650477db8d5485e229fe045d2616aa5255c83136773`。装配 Panda MuJoCo 在开爪阶段两次出现相同 QACC 不稳定，close 返回，H5 未写完；该全 provider 候选为历史状态，不代表后续 provider 路由；当前表格以路由后 MuJoCo Nut 复验替换对应两行。详见同一续接报告。

维护者随后选择按 provider 路由释放高度：路由调整在正式 Task 绑定中为 MuJoCo 选择原 1 mm、GeoPhys 选择 8 mm；5 项定向检查通过，核对实际构建的配置、identity 和重建。上段 8 mm 全 provider 候选的装配失败保留为历史证据。维护者已授权重置为 200,000 子步后，原／装配 Panda 的 MuJoCo Nut 已按完整 horizon 复验成功、严格完成、同运行 close、各自独立读回，见上表；新预算实测使用 23,775 子步。GeoPhys 旧 8 mm 成功记录的 Solution 配置经标准 JSON 比较与当前路由一致，但源码和 identity 不同；按维护者要求没有重跑 GeoPhys。不得把配置相同等同于当前源码的 GeoPhys 同运行证据。

provider 路由候选的 Nut Solution 全文件回归已通过 41 项；这些测试不替代 MuJoCo 物理完整复验。


2026-11-17 当前核验：按 provider 路由后的 MuJoCo 两次运行均开爪 110 步，66 个记录源码文件的哈希在独立读回时与工作树一致；PickCube 两条旧轨迹的记录源码清单仍匹配。AP-C1–C4 的指定 MuJoCo 交集具备有界执行证据，独立主审尚未接收。A2 的当前源码 GeoPhys 同运行证据未按用户指定复跑，配置相等但身份不同；A1 全受影响边界、A3 的 LIBERO 未迁调用及 A4 独立主审仍须如实交接。旧 H5 不作为 D0 replay。
