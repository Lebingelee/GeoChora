# E11–E16 U4 独立主审与维护者条件接收

2026-11-13。独立子代理主审输入生产 HEAD `0506ae26ef0240025876f3b6b163780946a46ac2` 及其后的 U4 文档／矩阵修复；审查前的 tracked diff SHA-256 `68f73bf068a818869f4cf896bb4ea4544a19365e475da62b38f72b7ba2872b8c`，新增联合证据文档 SHA-256 `cf6ef1a30d235a558e096d593cd319170a4c7f757590f36989c86b69d3e3b722`。独立主审先指出五路 completion 联合证据和当前入口漂移两项出口缺口；实施者补证并修正文档后，主审复审**未发现新的 U4 代码范围阻断项**。完整两轮审查、独立 H5 字段检查与最终复审见 ignored `workspace/maintenance/v211_e11_e16_independent_review_0506ae26/`；最终复审 SHA-256 `eda881074a0fd6ec92e52952fffecce09ddcc39a29cade5d0b0463d980cee429`。

维护者在本轮明确授权：独立主审完成、出口缺陷修复、五路线同次联合证据成立且限制登记、当前文档一致、项目义务仍 OPEN 后，记录 U4 代码范围有界接收并继续 U5。根据该条件授权及独立复审，记录 **MAINTAINER_ACCEPTED_BOUNDED_U4_CODE**；这不是实施者自行创设的例外，也不是项目最终接收。

[五路联合证据](20261113_e11_e16_u4_joint_completion.md)分别核验原 H5 的动作／状态／时钟／T/T+1／任务谓词及同次 caller、身份、监督与关闭。四条 CPU H5 不含 completion 字段，新 Isaac v3 为 null；caller 报告完成，不能称 H5 单文件独立证明完成。旧 Isaac 失败保留；新 `solution-002` 是 seed31、horizon1000、951步、lift 105.254 mm、4755 显式子步、App close 有回执。五个完整运行各保留自己的源码／配置身份，均为 state-only；腕部 RGB 是单独受控对照。CPU 运行时工作树为 dirty，冻结 Solution SHA 与相关 caller 源码作了对比，但未独立证明运行时逐文件载入字节；SDK 隐式启动／reset 步数 unknown。

主审核对 U1/U2 关键 caller、五路记录、Task/Solution 及 camera owner、T19/T20、当前入口和逐行映射；原总账 60 个 ID 各一次，V01–V10 分列，E00–E10 的既有有界接收按实际影响复用，并未重新逐项审计历史实现。当前生产 HEAD 的独立 guarded pure/fake **240 passed**；guard 非 OS sandbox。当前文档 validator 仍有 1 项保护 `MUJOCO_LOG.TXT` 历史 hash 差异和 79 项历史链接问题，已登记且未改保护输入，不能称全库通过。

E15/E16 的证据闭包、输出整理、refs/worktree、恢复与项目接收仍 OPEN；不因此启动 G06/G07，不构成 Qualification 或版本完成。U5 从该最终有界 claim 选择并独立复算新证据包，不删除原件。U6/U7 的具体删除和项目接收仍需维护者另行决定。
