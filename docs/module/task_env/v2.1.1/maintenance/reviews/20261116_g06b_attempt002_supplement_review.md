# G06b attempt002 supplement001 独立复核

日期：2026-11-16。结论：补充交接完成；G06b 仍为 PARTIAL_NOT_ACCEPTED。未启动 attempt003，未运行新的 native，未修改产品代码。

已阅读补充 report、index、comparison 和比较脚本；独立核对两次有效 B1 的保存数组，zero/hold/descent 的 qpos、qvel、joint_position、cube_pose 对当前 B3 对应行最大差均为0且为有限值，监督运行正常退出。证据只覆盖这些字段，不能推成完整 Task/clock/reset 已比较。scalar 接触后明显分叉仍如实保留；此前“手部首次接触之前”并非严格完全无接触。

剩余工作收敛为：完整 B1 生命周期/Task 对照及有界 scalar 平滑响应核对、无效研究分支清理、普通 discrete/32 配置落地、最终 renderer 的受影响 B3/记录检查与8项性能补测。7项历史性能按影响复用。已有双指接触、32次配置下1.715mm及当前 reset 证据保留，不再加入跨引擎接触力追平或 scalar mixed 重写门。

维护者在本轮明确答复“批准上述限定资源例外”：资源仍不足时，仅 Isaac PickCube 的 B16 sensor、window、sensor+window 可保留 RESOURCE_LIMIT 并允许有界接收；B3 正确性仍需成立。不能把例外推广到 B3 或其他后端，也不能将资源例外写成性能通过。报告时6.52GiB可用RAM并不保证Isaac B3可启动，下一包必须重新采样及按影响审查复用，不强行启动。

[attempt003工作包](../work-packages/20261116_g06b_attempt003_goal.md)已准备供维护者转交。原attempt计数仍为2，开始执行时才记第3次。补充是原attempt002的证据交接，不另计新attempt。目标是收口原G06b；不承诺尚未执行的检查必然通过。
