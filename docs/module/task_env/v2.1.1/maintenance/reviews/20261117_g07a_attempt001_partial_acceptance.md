# G07 7a attempt001：维护者部分范围接收与attempt002入口

2026-11-17。维护者在“准备G07 7a工作包”对话明确：“我个人同意验收A3之前的内容，A3以及剩余后面的部分我会放在attempt002”。本记录据此接收A1／A2／AP-C1～C4的现有有界交付；不是全部7a接收，也不冒称补做了一次全源码独立主审。原执行者报告中的“待主审/未接收”保留其历史时点，本决定不重写旧报告或失败。

实际交付Core `73e5ea2f37df31c778a14f70e837415f26ac553b`，分支`codex/v211-stage7-integration`；相关实现提交`cd8a6362`、`948f69f9`、`73e5ea2f`。tracked clean，仅保护`MUJOCO_LOG.TXT`未跟踪，SHA仍为`3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`；GeoPhys `198d30ac64ce873a1467f55d2adfc471db18fbc5`，Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。执行者[完整续接报告](../../../../../../workspace/maintenance/v211_g07a_attempt001/continuation001/report.md)已明确释放写入/native窗口，原线程idle/completed。

| 范围 | 本次维护者决定与限制 |
| --- | --- |
| A1／A2 | 接收已有集成/边界对账的有界交付，不重开E00～E16/G06。GeoPhys Nut旧8mm成功与当前路由配置相同但源码identity不同，按维护者限定没有重跑；保留当前源码未复验，不能写成全后端新身份通过。 |
| AP-C1 | 共同source/Controller构建与指定普通reset绑定成立；不扩任意Robot/provider/装配树或profile切换。 |
| AP-C2 | 固定装配MuJoCo CPU/in_process、预冻空载300controls/1500子步，峰值约0.708mm/0.000208rad，符合2mm/0.03rad；自身模型/补偿/ACK证据有界接收。 |
| AP-C3／C4 | 指定四个MuJoCo交集的原Task成功/原Solution完成、同运行记录/close及独立reader有界接收，Nut strict/planned完成。 |
| A3 | 未完成，转attempt002：LIBERO公共构建/canonical/default/所选Controller与精度、reader及其余caller边界。现行revision002允许合适Controller，不要求完整OSC/逐子步cadence复刻。 |
| A4 | 未完成，转attempt002：当前门/证据索引、受影响API/Skill/示例、提交/资源释放与最终独立主审。 |

四条最终H5已只读核对实际大小/SHA，并核对执行报告与独立reader收据；本次没有pytest/native重跑：

| Robot／Task | controls／boundaries | H5 SHA256 |
| --- | --- | --- |
| 原Panda／PickCube31 | 960／961 | `69b446c4711e6af1697dbb69d9c2f945cfa4b24b9f2dc4603a0fbb6760d83bc4` |
| 装配Panda／PickCube31 | 946／947 | `aae41cb7a36a598220b5adb1076b3a6e41fe778bdb4e81473e95ac2d8578de6f` |
| 原Panda／Nut19 | 2377／2378 | `c78e9325fa147e993e9983e04ab1b5c7ecb7dbc0a77f81768201421167857f6f` |
| 装配Panda／Nut19 | 2378／2379 | `c6cfd3ebe8acece4e70e94fed5337ba47e96787c6db8b1e5977538f2ac34e4b7` |

默认effort在这些Position Task中的原证据仍仅真实来源绑定/synthetic计算，不升为native默认力运行；R1-split隔离worker拒绝、旧device CPU tensor边界保持。Nut路由保持MuJoCo原1mm/GeoPhys8mm。attempt001子步重置授权后23,775实测＋100保守预留，与此前182,098估算及旧/侧边未知消耗分列保留，不补造历史计数。

[attempt002工作包索引](../work-packages/20261117_g07a_attempt002_goal.md)包含A3/A4及维护者新增的指定`v2.1.1-asset-skills`冻结分支本地整合；总连续wall≤240分钟，允许实际阻塞点向规划线程提问。准备时7a计数仍1，实际启动新窗口才登记2；7b/7c维持PLANNED／attempt0及原九格门。已接收内容只在本包真实改动影响时定向复核，不将新包变成全部历史重跑。
