# Phase-I Mainline Integration Status

代码发布与 subphase qualification 是不同决定。v1.0 接受 scoped Core baseline；下表保存历史 Human approval，新增整合 smoke 不扩大资格范围。原 Phase I blueprint **NOT COMPLETE**。

| 阶段 | 状态 | 范围与限制 |
|---|---|---|
| P1.0 | APPROVED_BOUNDED historical | provenance/docs/bounded baseline；不外推整个 runtime |
| P1.1 | APPROVED_BOUNDED | TaskArtifact v0、state、capability admission、provider-free contract；当前 detector 30 项 PASS |
| P1.2 | APPROVED_BOUNDED | GeoPhys/MuJoCo CPU bounded PickCube reset/step lifecycle |
| P1.3 | APPROVED_BOUNDED | 声明的 5 类 primary-provider conformance probes |
| P1.4 | APPROVED_BOUNDED | native GeoPhys/MuJoCo camera geometry/depth/timestamp contract |
| P1.5 | APPROVED_BOUNDED | R1/PickCube control/replay/expert，冻结 seeds 31/73；非所有 task/provider |
| P1.6 | APPROVED_BOUNDED | PickCube 100Hz、Flow_Vanilla/ConditionalUnet1D V2a FINAL 15000、26D、h50/a36；GeoPhys/MuJoCo D3 各 20/20 |
| P1.7 | DEFERRED | 没有完成 visuomotor qualification |
| P1.8 infrastructure | IMPLEMENTED_AND_TESTED_IN_DECLARED_SCOPE | Current candidate focused regression 66/66 PASS；涵盖 lifecycle、guarded transition、diagnostic isolation、replay contract 与 streaming recorder |
| P1.8 MuJoCo NutAssembly FULL and same-provider D0/D1/D2 | DEVELOPMENT_ONLY | Recorded development matrix covers 20/50/100/500 Hz; it is bound to source identities and does not grant qualification |
| P1.8 GeoPhys NutAssembly FULL | FAILED_ORIGINAL_FULL_GATE | FULL attempts at 50/100/500 Hz fail the original stable_height_mismatch gate. Later shadow predicates do not make the original Expert lifecycle valid |
| P1.8 GeoPhys diagnostic D1/D2 | DIAGNOSTIC_ONLY | GeoPhys-source D1 and frozen-action diagnostic D2 ran on GeoPhys and MuJoCo at 50/100/500 Hz; execution validity, task predicates, and Expert completion remain separate |
| P1.8 GeoPhys D0 | PARTIAL / FIRST DIVERGENCE | Representative 50 Hz exact reconstruction first diverges at transition 157; 100/500 Hz D0 not run |
| P1.8 formal cross-provider D0/D1/D2 | NOT_QUALIFIED | No symmetric valid GeoPhys FULL source; candidate Human review pending; diagnostic D2 is not formal Canonical Solution D2 |

P1.6 早期 state_bc 1/8、Flow 失败 variants 和原 D0–D2 dirty provenance 保留。Genesis 10/10、SAPIEN 9/10 是 supplementary development Evidence（SAPIEN seed2212 failure），没有 provider-wide approval。

早期 P1.8 10 N G0、T1 与 residual contact drift 结果保留为其原始 development evidence；这些旧结果不替代下方较新的 guarded-candidate 记录，也不授予 qualification。RoboSuite frequency reference、摩擦对照和 GeoChora 20 Hz 诊断仍为 DEVELOPMENT_ONLY。

在 GeoPhys shadow execution 中，原始 Expert route 记录 stable_height_mismatch；后续 insertion/release/task-success predicates 不能修复该 lifecycle failure。20 Hz 未被当前 loaded-episode GeoPhys diagnostic runner 接纳。完整 provider/rate/status 见 [v1.0 capability matrix](../../../releases/v1.0/capability_matrix.json) 和 [release evidence index](../../../releases/v1.0/evidence_index.json)。

原 Human decisions 的字节副本在 [historical_decisions](historical_decisions/)，各自 SHA 和原范围见 [Evidence index](03_phase1_evidence_index.json)。P1.6 frozen checkpoint 与 selected dataset 的恢复见 [recovery manifest](p1_6_recovery_manifest.json)。原始大型证据保存在本地 archive，off-host backup 未核验；公共 Git 不包含模型权重/视频/H5。
