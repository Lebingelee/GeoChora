# v1.1.0 Capability Limitations 与已接受风险

发布不扩张 qualification。[唯一矩阵](../../module/task_env/capability_matrix_v1_1_0_candidate.json)
绑定精确 task/provider/backend/source/config/seed/Evidence。四条 selected manipulation CPU routes
是 TESTED_BOUNDED；NutAssembly GeoPhys 的成功 outcome/Outcome V1 不抹去 strict Expert failure
和 `stable_height_mismatch` warning。完整 planned route、task predicate、Expert lifecycle、replay validity、
Judge acceptance 各自独立。

## 能力限制

- 无新增正式 P1.8 FULL、D0/D1/D2、manipulation checkpoint inference 或一般 manipulation PPO。
- Generic batch/device/learner contracts、GeoPhys-owned `GeoPhysRigidBatchRuntime` adapter 的存在不证明
  native batch qualification 或已注册 TaskEnv factory；当前 layout 仅 merged_scene。
- Pendulum SB3 是 CPU/2 env/4 timesteps/one update wiring smoke；保留原 CUDA-init warning，
  无 convergence。RSL provider-free admission 不是 native RSL training。
- Native rasterizer RGB 仅 Pendulum × GeoPhys CPU × scalar/merged_scene batch；Flora tests 是 fake endpoints，
  无 native Flora、selected manipulation × Flora 或一般 Physics × Renderer interoperability。
- 统一 Validator 与通用 Runner 未完成；完整 Policy Harness、benchmark adapters、PhysPi/RSI 为未来工作。
- Selected recording owner state 为 observation receipt，非完整 restoration checkpoint；H5 equality 不证明 D0。

## 当前文档复验发现

2026-10-18 实际执行 `single_inline --env-id pendulum-v1 --backend cpu --steps 1`，
`run_single` 读取不存在的 `env.binding` 而失败；直接公共 `make_env/reset/step/close` CPU
路线通过。当前快速开始改用公共 API，具体复现及 owner 见
[troubleshooting](../../module/task_env/troubleshooting.md#已复现的-cli-缺陷)。本轮不改执行语义，
也不以 CLI help 或既有绿色测试隐瞒该失败。

## 复现边界

原安装记录为 Ubuntu 24.04.4/x86_64/Python 3.12.14。fresh dependency installation 未执行；
requirements 非已验证 lockfile。Clean source checkout 做过两任务×两 provider construct/reset/close，
没有重跑 full trajectories。PickCube controller hash 包含带 absolute meshdir 的 generated MJCF，
可能随 checkout root 改变；Artifact/config/normalized XML 相同不保证 controller identity 字符串相同。
维护者接受 Option B（保留算法和限制），不得改历史 hashes；每次记录实际 identity。
原 relocated provider-free exploration 是 139 PASS/8 FAIL，分析后未重跑完整回归，不能改称全绿。
细节在[冻结 final gate](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/module/task_env/p2_0_s5_c1_final_release_gate.md)。

## 存储与历史恢复

22 L2 originals 的 same-account GitHub copy 已 size/SHA-256 readback，代表性 H5/JSON 可读。
发布时维护者接受 same-account/no separate administrative-domain backup、waive historical full-workspace
backup gate；状态为 **RELEASE_RISK_ACCEPTED**，绝非 FULL_BACKUP_VERIFIED。
历史 SATA/BadCRC/READ I/O 风险仍 OPEN；SMART counter-only 固定增长为调查信号，
不能据此断言新的 I/O failure，也不能用最近无错误证明硬盘可靠。

C8 获批的 65,826 ordinary paths 经 manual handling 后观察 absent，无逐文件 unlink logs。
Registered worktree、三份 P1.1 holds、P1.8 source bundle、516 unresolved C2 files 与两条 symlinks
仍在原 holdout 范围；不授权进一步清理。历史 P1.6 recovery tar 位置未知，P1.8 raw/source snapshot
可能永久丢失，GeoPhys historical bundle 不能证明完整 source reconstruction。
这些 accepted losses 不能靠 metadata/qualification decisions 重建。
[原 C8 records](https://github.com/Lebingelee/GeoChora/tree/v1.1.0/docs/releases/v1.1/evidence/retirement)
与[backup manifest](backup_manifest.json)保留时点事实及 hashes。

仓库扫描无法发现所有外部消费者；被删除 import/UID 的外部依赖仍需维护者检查。
本轮文档检查和 cold-start walkthrough 不执行 native qualification，不关闭以上历史风险。
