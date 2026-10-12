# Human Review handoff

分支codex/p1.8-integration，起点44adbbf，冻结源码9ce545d4534da68d551921778298a0f74772f9d1；报告后HEAD由git rev-parse HEAD解析。public/main未改变；未push；未新建branch/worktree。

新入口：
```sh
PYTHONPATH=.:GeoPhys/src:GeoPhys MUJOCO_GL=egl OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m task_env.diagnostics.phase1.integration.grasp_height_probe --provider geophys --rate 100 --output NEW_DIR
```

仅诊断入口，生产候选未迁移。证据根/home/lly/.codex/worktrees/p1-8-e-r5-controller-architecture/Geochora/workspace/qualification/phase1/p1_8_pre_d0_d2_readiness/review_refresh_1mm；review_refresh_1mm报告为最新审计，父目录报告是历史。所有复用源/复制/hash列在reuse_manifest.json与g0_reuse_manifest.json。当前六G0判定、快照mock局限、时钟首个拒绝、归档验证、freeze identities已机器化。

下一项具体工程工作：在单独批准的范围内接入live recorder，保留recipe/owner snapshot/完整physics target stream；证明真实prefix-vs-checkpoint next-target与不改变v0的时钟表示。完成Human Review与这些阻断后，另行授权T1/full/goldens/formal replay。
