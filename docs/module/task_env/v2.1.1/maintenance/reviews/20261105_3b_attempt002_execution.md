# 3b 普通 attempt002 执行摘要

状态 REPORTED_PENDING_SOL_REVIEW；技术结果 THREE_B_TECHNICAL_PARTIAL，ORACLE_REVIEW_REQUIRED。普通次数 2；001 的失败及复审决定原样保留。本次输入 `470c3ef90bf2179916733f0049444bedefe07e3d`，实现提交 `be88c5cd4ac823c997040d3166f7ea14e069b610`。完整数据、命令、检查映射、输出哈希和释放收据见 `workspace/maintenance/v211_g03_3b_attempt002/` 的 report、results、commands、numeric-readback 和 output-manifest。维护者手动交 Sol 独立复审；不自动启动 003 或 3c。

同一 checkout 的旧 0192 与输入版 MuJoCo 配对控制，身份、源闭包、初始状态和动作相符，11 个边界 q/qdot/TCP/time 差为零。旧／新 N08 驱动段均下降 1.229934 mm；同条件 hold-only 下降 1.636992 mm，上移动作相对 hold 有 +0.407058 mm 效应。100 步预热是独立诊断，不取代冻结 N08。结合维护者转述的首子步力矩与静态 bias 诊断，支持初始缺少重力前馈、反馈逐渐建立支撑力的机制；不将其标为 3b 新引入回归。

实现修复 launcher 上下文并将真实 F06 七臂／两指速度贯通同 run T+1 记录。三路线默认关闭下真实 PickCube 原测试与同次独立 H5 reader 已运行，原 N08 仍分别为 MuJoCo −1.229934 mm、GeoPhys −1.230121 mm、Isaac 6.2 −1.290584 mm，均 FAIL。物性完整公共读回仍有缺口；GeoPhys solver-effective 公共 API 缺口见输出包。6.1/6.2 有真实 consumer 链加合成 SDK 终端 fixture，6.1 真实 App 因主门未完成未运行；6.2 pip SDK 实际运行并关闭，退出后有析构告警。

维护者在本次中明确审阅并授权不同于原冻结包的默认关闭重力补偿。当前仅 selected MuJoCo CPU、进程内的 Panda 本体和一体手；校验来源／模型、旋转坐标、已有补偿及执行器映射并报告限幅。Nut19 一次 3.5 s 固定姿态实验最大高度误差约 0.0000143 mm，首步执行器力与计算支撑的最大差约 5.96e-6 N·m，所测样本无目标或力限幅。该实验使用早于最终细化的补偿代码，最终代码另有短回路；求解器执行器力并非正式七关节力传感接口。旋转 scratch 实验没有记录无接触前提，不可当完整验收或任意旋转证明。早期 H5 没有最终新增手指力回执字段；不声称其已做同次最终 H5 读回。更通用的[装配树子段选择](../../planning/gravity-compensation-assembly-tree.md)尚未实现。

过程限定：原 helper 首次在 reset 后访问缺失的 runtime receipt 失败；复制补丁与失败日志保留。两组只读 reader 重叠约 0.1 秒；一条 GeoPhys 运行时发生重力开启专用代码修改，已在稳定源码重跑。一次 Isaac fixture 兼容性失败已修复并重跑。稳态预冻结文件实存早于实验，但其手填冻结时间晚于启动约 11 秒，不能据该时间戳声称预先冻结。writer 在维护者暂停期间账面未释放；恢复后在最终交付释放。已知真实物理子步下限约 3909，首次失败 reset 隐含启动数未知，不能证明总数上界；不再运行物理步。部分早期离线只读命令无完整启动账本。详见完整报告，不将缺失项伪记为零。
