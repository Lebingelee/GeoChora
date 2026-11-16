# 3b attempt001 执行摘要（待 Sol 复审）

本窗口技术结果 **THREE_B_TECHNICAL_PARTIAL**；不是阶段接收、Qualification 或 3c 授权。输入 Core `0192f2ec538582c3945acc2b9fcfca22589500ec`，GeoPhys gitlink `67da1165149486d3ae3e779c13ce31af49e17d50`，Menagerie gitlink `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。attempt_count=1，源码提交 `d5731655`。完整命令、失败日志、数值与同次 H5 保留在 ignored 目录 `workspace/maintenance/v211_g03_3b_attempt001/`；最终提交身份和文件清单位于该目录返包。

3b按实际消费角色修正依赖：GeoPhys native rigid 不被未选 MuJoCo solver 的声明挡住；明确使用 MuJoCo solver 时仍检查。SDK worker 不再装入 host 的其他路线二进制包，Gym 与 H5 的 host 职责按需加载，缺实际必需依赖仍拒绝。Core 和 SDK 解释器身份、带日志 launcher、静态/运行版本与真实来源分开；6.1/6.2 fixture 是离线证据，不是6.1 native。F06 的 USD 在 App 初始化后重建，远程 episode、原生确认和 Recorder 身份/模型事实经现有 RuntimeSession 传递。

| 指定路线 | 本轮实际结果 | 冻结 N08 的第5→10控制边界 TCP 世界 Z 位移 |
| --- | --- | --- |
| MuJoCo 3.8.1 CPU | 公开 factory/reset/10步/close，同次 canonical H5 独立读回 T=10、T+1=11 | **-0.001229934 m，FAIL** |
| GeoPhys native rigid CPU | 同上，控制时间增量 0.10000000000000007 s | **-0.001230121 m，FAIL** |
| Isaac 6.2 pip / PhysX / cuda:0 | 同上，同次 v3 H5 独立检查请求、source、版本、模型事实、10组目标确认及各5个子步回执；App正常关闭 | **-0.001290584 m，FAIL** |

要求为至少正向 `1e-6 m`，没有放宽门槛或把 target/Ack 当测量。控制诊断显示请求的关节目标对应向上的目标，但观测在短窗口内下沉；这还不是充分的动力学根因证明。Nut seed19 MuJoCo 用原 Solution act/observe 补测10步/close通过，不声称任务成功。三路线闭环能够执行不等于数值门通过。

MuJoCo公开 MjModel 和 GeoPhys公开 compiled scene 对12个 MJCF 惯性体、9个关节轴/限位及具名 equality/tendon 的已比较量通过；GeoPhys结果是公开compiled模型而非私有solver有效值。Isaac公开 tensor views 对12个质量、11个显式声明的 COM 和11个显式惯量／轴比较通过；cube的 COM 和惯量主轴在 USD 中未显式声明，分别标记未声明/未按声明框架比较，不能拿默认值冒充声明。MJCF cube 保留 `0.08 kg`、`3.5e-5 kg·m²`；冻结 USD cube 声明约 `0.08 kg`、`3.333333e-5 kg·m²`，不改资产使其相等。所有 body、axis、传动、reset、支撑、qdot 和 frame 的全部 required 门尚未闭合；尤其 Isaac v3 原有观测未提供完整 qdot，N10不可整体判PASS。

独立6.1 native及官方 App `python.sh` native **NOT_RUN**。维护者在执行期间告知另装了6.1，并授权在完成当前目标且时间明确剩余后辅助核验；由于本目标尚未过 required 门，本窗口没有启动或检查该安装。6.2使用已有pip解释器；内部 headless MinimalRendering初始化不等于用户 render/capture。

聚焦guard离线组33 passed；另一受影响F05 synthetic测试因其历史delivery路径缺失而失败，未借空文件或重导出绕过。实际Isaac SDK 6.2版本、完整请求与本轮运行需以原始记录为准；并非对6.1或其他task的资格证明。

过程偏差必须保留：早期 `model-compare-01/02`、`control-diagnostic-01` 和 `sdk-binding-01` 为source-only检查，未按包要求取得双锁、工作目录为仓库根；未启动物理引擎。最终模型对照已在ignored目录取得两锁后重新运行。Isaac `04`–`07` 的部分失败后曾因误判较慢的App关闭为卡住而终止本窗口自有worker；最终 `08` 与最终组正常关闭，不能倒改前次退出。进程树RSS与GPU全卡占用以监控记录为准；无法单独测得进程VRAM，记null。启动或失败期间无法从日志精确恢复的物理步数记unknown，不以估值填充。输出文件、锁与writer最终状态见返包。

后续由 Sol 依据原始读回、各oracle的未测原因、路线依赖声明、关闭和资源账本独立复审；不自动启动下一attempt或3c。
