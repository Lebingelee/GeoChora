# Phase-I Mainline Integration Handoff

开发分支：codex/p1.8-integration。源码 merge checkpoint：`be47e72fe81790813b784cb1a47c91d2f59b68ab`。发布状态与 public exact refs 见 [publication report](09_publication_report.md)；所有工程 source identities 见 [source manifest](07_mainline_source_manifest.json)。

合并能力：P1.1–P1.5 contracts/runtime/camera/R1 PickCube；P1.6 Flow/V2a/100Hz/D3 diagnostics 和原批准记录；P1.8 四 provider adapters、R3 persistent reference、10 N candidate、v0/v2 recorder、clock/owner/interval diagnostics、loaded/full runner。

保留 503 份历史 governing Evidence 索引与 7 项 Human decision；P1.6 D3 316 个原始文件与 100 条 selected training trajectories 均核验，441-member independent recovery archive 包含 checkpoint/config/raw Evidence。它不在公共 Git，off-host backup 未核验；交接时通过本地 audit locator 找到 archive，按 manifest SHA 恢复。

本轮 fresh：21 pytest cases、P1.1 30 assertions、checkpoint import/shape、synthetic owner/interval/v0 roundtrip、两 primary-provider TB100 recorded checkpoint continuation、compile/link/hygiene。未重跑昂贵 qualification。所有源码/API/物理参数保持原批准或开发版本语义。

下一 P1.8 开发应从发布后的 mainline source tree开始，保持当前 10 N G0 配方，分别解决 MuJoCo loaded retention/capture drift 与 GeoPhys lower-stage pose/readiness。先保留失败 baseline，再做有界因果分析。成功完整 expert/live-recorded goldens 建立并经过 Human Review 后，才考虑正式 D0 6 / D1 12 / D2 12 same-rate primary matrix。

已知风险：辅助 pad penetration；MuJoCo T1 capture drift；GeoPhys lower-stage timeout；native GeoPhys contact-resume 非 bitwise；P1.6 checkpoint archive local-only；历史 profile YAML 保留旧路径 provenance。P1.7 deferred、boundary-provider 新资格无新增、Phase I not closed。
