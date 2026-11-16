# G03 3c ordinary attempt001 执行摘要

技术结果 `THREE_C_TECHNICAL_PASS`，等待 Sol 独立复审，不代表 ACCEPTED 或 Qualification。输入 Core `305b1fa5f99e3430b8e71ee6d0ed61586f6556af` 来自 3b 最终结果绑定，GeoPhys pin `dc2685e28c6c916fb6403a2342c04e0d2520aef7` 未改变。实现提交 `4f22b28d`、`bd678582`、`91c99d8c`、`af663868`；本摘要所在提交为最终文档提交。

显式 `pickcube-state-only-switch-v1` 下，同一个公开 Env 实际完成 MuJoCo→GeoPhys→MuJoCo→Isaac 6.2 CUDA→MuJoCo，五段均为 5 transitions / 6 boundaries、各自 H5 和独立 reader。回显式 seed31 重现首个样本并继续一步。非法目标预检保持旧 session、状态和随机流；下一样本与独立 PCG64 序列吻合。配置／拓扑代次、source、request、sample 和 materialization 在同次记录中核对。默认路径和已存在 codec 不因未启用 profile 扩权。

实际星形链基于 Core `af6638684c071749c6ecb19f990b13afdb742cee`；最终摘要提交仅改文档。三种目标的真实 source 沿生产 reset/预检进入合成 terminal 故障，旧 session 释放后构建／reset 写入失败、部分 advance 和旧绑定输入拒绝有定向 fixture。未知 reset 写入明确标 `unknown`；失败不伪造 transition。旧 owned observation 与 typed state 仍可读；此 profile 的 session publication 使用 owned snapshot，没有暴露 provider_alias，借用别名失效没有实测。

最终 Isaac worker PID 与 exit 0、App close 成功且一次、USD snapshot lease 关闭、重复 Env.close 和双锁释放有同次记录。早期运行 worker exit -11 已保留；参考 F04 attempt004，在专用 worker 的 App/session/source 清理和响应完成后受控结束，失败路径保留非零和原错误。此策略不证明自然 Python/Kit 析构修复。

3b 影响：共享 transport/worker 等改动后，默认关闭 profile 的 Isaac F06 10-step hold 已有代表性重测及独立 reader；与原 3b 对应 run 的末边界一致。3b 原文件、原 N08 失败和原技术结果均未改写。其他 provider、controller/renderer 切换、通用装配树、真实 6.1 App 与任务成功未验证；6.1 App 此时 NOT_RUN。

过程偏差：早期一次源解析相关无引擎测试未持双锁；另一批无引擎测试的异步观察句柄未记录，完整输出/结束状态无法独立恢复。后续受影响测试在双锁内重跑；不能把缺失的旧日志补成通过。此前无引擎 reader 使用错误字段名、一次测试 fixture 断言错误、首次 CPU 和 Isaac 短跑错误及 exit -11 均保留。各 run、资源／未知计数与释放记录见 ignored 输出 `workspace/maintenance/v211_g03_3c_attempt001/`。
