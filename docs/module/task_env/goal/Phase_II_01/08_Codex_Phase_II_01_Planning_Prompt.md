# Codex — Revised Phase II-01 Planning Review / Approval Handoff

这是随附原 08 的修订版审阅指令，状态 REVISED_DRAFT。维护者当前只授权规划文档审阅/修订；首版 R07 规划已另经明确授权提交并推送为 `535ce251…`。后续提交/推送按当次明确授权，不从此 Prompt 推定；最终 Goal/DAG 尚待批准，P00/R01–R07 尚未启动。本文件不能被当成继续实现授权。

读取 AGENTS、canonical architecture/ownership/Public API/qualification、冻结 Phase II 决定与九文件状态、当前代码/callers与 gitlinks、00–07、09 R07、README、planning_manifest 和 validation_receipt。重新核对实际 Git/ref/dirty paths，保护 ignored Evidence/探针。参考版本固定 Isaac Lab v3.0.0 和 Isaac Sim6.1.0，不用滚动latest推断新能力。

仅 AUDIT_ONLY / REVISE_PLAN：

1. R01：区分 owning Entity Member / Existing-Entity Subcomponent Reference / nested Assembly；稳定ID与内容摘要无循环，typed路径/递归/唯一拥有，旧Scene/Artifact/Entity身份不变。
2. R02：审查独立Arm-only/Hand-only版本化Action/Target/Ack/Required State/TCP/资源，preset+override→唯一writer；不得用双完整Panda替代leaf证据，不泛化C02c/R1切换。
3. R03：R03a依赖P00；核对独立panda_nohand+hand、MuJoCo3.8.1 compile先验、GeoPhys a53 site-size拒绝及缺NativeS2/S3事实；MuJoCo CPU首个required候选、第二Provider未准入；评估mount/root/equality/tendon/collision/ordered mapping/publicS3，禁止prebuilt Panda替代。
4. R04/R05：分别审查同边界Camera消费/同H5reader与Provider正式native反馈合同，R04/R05不作为Position子链无关前置；原host诊断不升格。
5. R06/P99：R06b依赖R06a/R01c/R02c/R03b；P99依赖R06c/R07d；7父Goal/22切片DAG、当前状态、negative evidence、顺序/机械语义/版本保护、历史缺失原件、独立scope-change门槛完整；required失败不自动延期。
6. R07：固定LIBERO8f1084e…的指定5个BDDL/pruned_init/native predicates/assets与robot/dependency；推断不得来自名字（Push/And非动作/顺序），真实construction/reset/motion/Controller/Planner/语义fixtures/H5而非Expert/成功率；独立Agent cost protocol/真实session与human code quality，native成本baseline仅额外研究。RoboCasa2ce1aecd…仅feasibility。逐Task声明R02c/R03c/R04c条件前置，无R04/R05全局边；RGB保持Recorder CHW uint8。
7. 核对固定外部参考仅用于工程原则，未引入USD/Warp/IsaacLab或第二Runtime。

输出 ACCEPT_PLAN / REVISE_PLAN / REJECT_PLAN、P0/P1/P2与源码/文档定位、scope/provider/版本风险、修订建议及维护者待决项。不得独立签署Human Judge/Qualification，不改冻结PhaseII/Evidence/Artifacts/pins，不在没有新批准时启动P00、提交功能/推送/main/tag/Release。完成后停止，等待维护者明确批准最终Goal/DAG/实施范围。
