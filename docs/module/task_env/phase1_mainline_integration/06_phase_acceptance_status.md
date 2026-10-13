# Phase-I Mainline Integration Status

代码发布与 subphase qualification 是不同决定。下表保存历史 Human approval，新增当前整合 smoke 不扩大资格范围。Phase I **NOT CLOSED**。

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
| P1.8 infrastructure | TESTED / REPLAY_INFRASTRUCTURE_GO | v2 live recording、owner snapshots、interval stream、integer/native clock，已声明 primary scope |
| P1.8 10 N G0 | DEVELOPMENT_ONLY | NA-S0 equal-rate 500/100/50 六格已有通过记录 |
| P1.8 T1 | PARTIAL | GeoPhys 3/3；MuJoCo 0/3，raise_for_transport 首先越过 8 mm capture drift |
| P1.8 Full NutAssembly | BLOCKED / PARTIAL | GeoPhys lower_nut_to_table readiness timeout；无成功完整 source golden；其余格受 prerequisites 限制未运行 |
| P1.8 formal D0/D1/D2 | NOT_RUN | 无可供完整任务 replay campaign 的 accepted goldens |

P1.6 早期 state_bc 1/8、Flow 失败 variants 和原 D0–D2 dirty provenance 保留。Genesis 10/10、SAPIEN 9/10 是 supplementary development Evidence（SAPIEN seed2212 failure），没有 provider-wide approval。

P1.8 residual contact drift 未解决。MuJoCo G0 约 5.46 mm，相比 GeoPhys 约 0.02 mm；T1 MuJoCo drift 达约 13.1 mm。RoboSuite frequency reference、摩擦对照、GeoChora 20 Hz 诊断均为 DEVELOPMENT_ONLY。20 Hz GeoChora drift 5.436 mm，没有达到 RoboSuite 20 Hz reference 的 0.771 mm；两边配方/控制语义不等价。

P1.8 full expert：GeoPhys/TB100 的 lower_nut_to_table endpoint error 约 75 mm，inserted_on_peg=false、task_success=false；TB500 有失败 terminal evidence，但 H5 finalization 未验证；TB50 Full Expert 未运行。不能将这些结果改成 Full PASS。

原 Human decisions 的字节副本在 [historical_decisions](historical_decisions/)，各自 SHA 和原范围见 [Evidence index](03_phase1_evidence_index.json)。P1.6 frozen checkpoint 与 selected dataset 的恢复见 [recovery manifest](p1_6_recovery_manifest.json)。源数据保存于独立本地 archive，off-host backup 未核验；公共 Git 不包含模型权重/视频/H5。
