# Phase-I 源码整合

源码 checkpoint：`be47e72fe81790813b784cb1a47c91d2f59b68ab`（两个 parent：起始 P1.8 与已批准 P1.6）。本轮为跨分支工程整合，没有新的 NutAssembly 参数优化。

P1.6 的 `agent_factory` 七个独有修改、policy_search 实验入口/配置/单元测试、D3 runner 和 closure package 完整纳入。P1.8 runtime、controllers、planners、NutAssembly recipe 与 trajectory 源码保持起始字节。四 provider adapters 均保留，R1/PickCube production controller 没有迁移到 R3。

唯一 merge conflict 为 `06-phase-1-contracts-and-provider-boundaries.md`：base 只记录早期 state_bc partial；P1.6 增加 bounded closure，P1.8 增加后续 provider/replay 章节。解决方式是保留 P1.6 当前 closure scope，并保留注明历史时点的 P1.8 roadmap 与失败记录。没有源码冲突，没有 ours/theirs blanket resolution。

P1.6 工作树还有四个未提交 diagnostic source。三份新文件与已存在 source snapshots 完全一致；`flow_training.py` SHA 为 `a8e67802de9a93df3114fcc11fc27c3a8828310d4bb46eab2106d0dbcd962682`，对应历史记录中的 recovered inference driver。原始 patch、四份源码和 SHA 已保存于独立 archive。纳入这些入口是为了恢复历史实验的可执行依赖；既有 V2a main learner 与 D3 identity 由原 Git merge 保留。

`flow_horizon_training.py` 的历史绝对 interpreter 路径改为 `sys.executable`，使该诊断入口使用操作者的当前环境。该改动不改变 planner、learner、action 或 gripper 参数；原文件精确副本仍在 archive。历史 profile YAML 中的原机器路径保持为原始 provenance，不作为新 portable API。

未提交的 `.codegraph/`、`docs/module/task_env/goal/` 和 `MUJOCO_LOG.TXT` 没有纳入。Closure 原始批准与报告字节未改写。完整相同文件证明见 [source_identity_proof.json](source_identity_proof.json)。

整合时修正 Flow profiles/SUMMARY.md 的五个历史重复目录链接；只改变导航，不改变原实验结果或配置。
