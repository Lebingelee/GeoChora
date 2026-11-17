# G07 7b attempt001：实施结果，待独立主审

本记录是实施者返包，不代表维护者接收。结果 **PARTIAL**：九格成功及其同运行证据成立，当前 BodyWrench 公共选择／native 链未验证；不得以九格或资料完备代替该门。7c仍 PLANNED／0。

输入 `923eb2cdc53585c0eb3c017ca1996e78b9b5ed77`，PR #3 固定 head `23387a9cffd82fe02fb69fb5d2993141fdd54ae9` 本地双父 merge `ab4f9b13c17bcf522ca84bcc8bc94ad527320052`，最终生产冻结 `78349184d0600e2fb804e6461930c475bfcc67c1`；后继 `c41db4af` 只修复 fake close fixture。GeoPhys `198d30ac64ce873a1467f55d2adfc471db18fbc5`、Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。冲突决议、冻结输入、H5、图像、失败、资源和独立读者原始文件在 `workspace/maintenance/v211_g07b_attempt001/`，其中 `report.md`、`results-final.json`、`reuse-and-impact.md`、`budget-ledger.json` 是入口。

维护者授权在 PickCube Solution 原 owner 压缩前段三个固定 settle 尾段；保留轨迹速度／加速度、真实 TCP gate、姿态 readiness、下降、闭合及抬升、任务与终止条件、105 mm 收集端点和 1000 步上限。旧输入 seed32 未成功与 seed33 成功同时截断均保留，不迁为最终通过。原事件驱动 Solution 在目标达到时完成，`planned_trajectory_completed=null` 按原样报告，不能伪造完成字段或要求预计算 lift 点列耗尽。

| provider | seed 31 / 32 / 33 transitions | 同运行任务与 Solution | 独立 H5 和关闭 |
| --- | --- | --- | --- |
| MuJoCo CPU | 883 / 964 / 923 | 3/3，未截断 | 3/3 |
| GeoPhys CPU | 874 / 956 / 915 | 3/3，未截断 | 3/3 |
| Isaac PhysX CUDA | 876 / 956 / 916 | 3/3，未截断 | 3/3 |

每个 seed31 有同运行 reset／首个非零动作／最终边界 RGB；其余 state-only。原 predicate 逐边界重算，原 H5 和 caller 身份关联，Isaac v3 原始 external-stop projection 的 truncated=true 与 caller 最后实际 truncated=false 分列。离线 reader 首次错误的 T/T+1 对齐及重试保留；canonical v0 和 v3 使用各自真实 schema。GeoPhys／Isaac 的 `grasped_cube` 几何奖励诊断为 false，不能改写为 true；原任务唯一成功门是升高。当前 seed31 完整上升过程的方块和末端共同上升约105 mm，图像不证明接触力，静态保持和摩擦未单独测量。

| 规范或独立门 | 调用链与依据 | 本次结论及限制 |
| --- | --- | --- |
| 7a 正式共同构建／装配与原 Panda | 正式 Task config → `make_env` → 共同 builder/source composition → Robot recipe 与 Controller binding；详见 7a 两份独立主审 | 按对应输入复用原共同构建、默认／显式选择与 reset 有界证据；新 PickCube Solution 已对装配 Panda 正式 caller 补跑，870 transitions、任务及 Solution 成功、独立 H5 和 close。四个 MuJoCo 交集原结论不推广为任意装配树或任意 Controller 切换。Nut 的当前 GeoPhys 源码未复验。 |
| G03 provider 切换 | 当前同 Env MuJoCo→GeoPhys→MuJoCo→Isaac→MuJoCo，每段五步，5 条独立 H5 | 当前五段及关闭通过；旧更强证据只按原输入引用，GeoPhys↔Isaac 直接切换未准入。 |
| G04 Controller/reset | 同 Env joint→R3→joint，generation 1/2/3，返回参数 kp=100，3 条独立 v3 H5 | 当前短程与关闭通过；旧故障／stale 条件只按原输入引用，不扩成任意装配切换。 |
| G04 7＋2 effort | 当前 MuJoCo 同 Env joint→R3→joint 的 3 条独立 H5 与 native ACK | 三段各有七个具名 N·m 臂关节及两个具名 N 手指关节准入项，9 个 contribution ID 与写入 ACK 对应；非独立测力或逐输入方向验证。GeoPhys／Isaac 原 4b 有界证据保留原输入。 |
| G04 BodyWrench | 真实 Panda source、subject、Controller 和公共选择 | 原 subject 仅声明 effort writer，WrenchController 未声明同一 selection profile；真实组合在零步被 guard 拒绝。历史 4b 的数学及原生记录与本次 COM +2 N ACK 均不能证明当前 BodyWrench 链。缺少合法 composite authority 的最小路线，未伪造声明或放宽 guard。`BODYWRENCH_CURRENT_CHAIN_NOT_VERIFIED`。 |
| G06 设备运行 | 当前固定 Rasterizer Isaac↔MJWarp 同 Env A→B→A，Pendulum、PickCube 各 9 条独立 H5；GeoPhys PickCube 单／非相邻部分 reset 与独立相机归因 | 两个切换代表与 GeoPhys 部分 reset 33 项检查通过。当前 MJWarp PickCube 交错终止及同运行 7 条 H5 独立读回通过；未把旧多 provider stagger／随机流全矩阵自动迁为当前源码通过；GeoPhys 直接跨 provider 未准入。首次无相机归因的两项像素检查失败已保留。 |
| LIBERO | 7a 正式 caller、当前未改相关 owner | 仅复用已接收的 64 步有界结果；task_success=false，Solution 未评估，无完整任务或独立夹爪宣称。 |
| Harness/delivery | 公共 compiler、共享锁、进程清理和 Core 双 delivery 准入 | 定向测试通过；desktop manifest 实际字节验证，第二身份 catalog 测试采用合成 hash 替代，不证明该交付的真实字节新鲜度。external asset 为 XML proxy，未声称材质化外部资产。 |

定向回归包括旧监督和 binding 检查、Solution／时钟／信号检查及最终 70 项通过。此前一项 fake fixture 不满足真实 port close 合同导致 69 通过／1 失败，修正 fixture 后通过；历史测试导入已退役 `build_reference` 的收集失败也保留。未运行 setup、doctor、完整训练、全部 provider 或任意装配树。

维护者授权显式子步预算重置到新周期 200000：旧周期已知 71875，之后两次部分 reset 各保守计 375，MJWarp stagger 保守计 150，另计 CLI 25、G03 首次强制终止保守 125 与重试 125，新周期已用 1175、全历史已知 73050；Isaac 隐式启动／reset 步数未知。其他 wall／native／内存／显存／输出限制仍按原包。OMP、OpenBLAS、MKL 请求均为1，初始 affinity 最多4 CPU，Taichi/Forge 编译日志4线程，solver 线程池未实测；不称全 SDK 为单线程。先前运行使用 canonical 锁与继承 FD，但未逐次核 legacy inode／blocker；事后 inode 一致，后续监督器已在获取锁后核 alias 和 blocker，不倒填旧运行检查。澄清005与006及其 SHA、原始 receipts 在工作包证据中。

最终检查：`git diff --check` 与更新 JSON 解析通过；文档 current 校验退出 1，唯一错误为保护输入 `MUJOCO_LOG.TXT` 与文档基准不一致，其实际 SHA256 仍为启动前的 `3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`，未修改该保护文件。50 个监督回执 wall 合计约 3950.399 秒（包含受监督测试，保守计），最大进程树 RSS 约 8.14 GiB（图像／CUDA 类），最大整卡 3128 MiB。

后续 MJWarp 交错终止代表补证：69 项检查通过、正常关闭；独立读回 7 条 H5、27 个边界与 10 组终止／重置相机对通过。首次读者因新旧监督回执字段名不同而失败；独立保存映射及原回执 SHA 后重试，原 H5 未改动。该结果不推广至全部 provider／任务。

维护者要求先完成其余内容并自行与 Sol 确定 BodyWrench 方案；[缺口说明](20261117_g07b_bodywrench_gap.md)列明实际准入拒绝、所需权限和验证边界。正式 CLI 的 `--help`、MuJoCo 五步短程及其独立 H5 读回已补齐；短 horizon 的 task/Solution 实际失败，不能当任务成功。G03 五段五步首次在 Isaac 启动时因误用 CPU 6 GiB 监督类别被强制结束，前三段 75 子步可见、未正常 close，保守计 125；按 CUDA 10 GiB 类别重试并取得五条同运行 H5 独立读回和正常关闭。冻结源码及九格 H5 哈希、三个 seed31 图像关联事后完整性对账通过。

返包索引复核：最终 `results-final.json` 的其他门此前仍为 pending 占位；现逐门列出当前代表 PASS、历史有界复用与 BodyWrench 原生链 NOT_RUN，并保留修改前原字节及 SHA `74731180197b040474bf4f33ffc8996f4fdabf6da2007e09100993c20fd68119`。最初 `results.json` 仍属于旧冻结输入，不覆盖为最终九格。
