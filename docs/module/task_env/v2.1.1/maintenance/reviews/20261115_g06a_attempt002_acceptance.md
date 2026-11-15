# G06a attempt002 独立主审与收尾

日期：2026-11-15。结论：**SOL_ACCEPTED_BOUNDED_6A**。本次审核关闭 attempt001 的返工项和 attempt002 的有界 G06a 工作包，无需继续 attempt003。G06b、G06c、canonical 三后端 × 两任务六格和后续 R3 包仍未接收。

## 输入与授权边界

- Core：`3bc9e2a70daea2dda1004352c54ba1d1ada46b54`，分支 `codex/v211-stage6-parallel`。
- Core gitlink 与 GeoPhys 实际 HEAD：`a2c85b7fb87e821b1e3b211c97ed2b695db8b3c1`；GeoPhys 工作树干净。主环境 Forge / runtime 为 0.7.0。
- Menagerie：`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。
- [工作包](../work-packages/20261115_g06a_attempt002_goal.md)、[执行报告](../../../../../../workspace/maintenance/v211_g06a_attempt002/report.md)及[前次主审](20261115_g06a_attempt001_review.md)保留各自时点。
- 维护者明确决定暂不考虑 GeoPhys 主分支合并与 AOT 问题；执行报告中的既有治理／包准入问题同样按原批准边界暂缓。本主审不把它们记为 PASS，也不据此阻断 JIT 相机路线。没有宣布 GeoPhys 全包或合并基线通过全面验证。

## 代码与接线复核

| 范围 | 本次判断 |
| --- | --- |
| 生命周期与动作合同 | 固定 B 轴 final observation 与有效行 mask、Task info 保留和保留键冲突检查、reset 提交后失败锁存、声明式采样和逐行随机流已落实；复用共同 owner，没有另建并行任务框架。 |
| 正式 MJWarp 路线 | `make_parallel_env` → homogeneous device owner → MJWarp session → 公开设备状态／pose → Rasterizer。B=3 Pendulum 的非零控制、masked reset、same-step autoreset 维持原有证据。 |
| 设备图像 | 共享 Rasterizer 使用公开设备 pose、具名 frame/site 和 CameraSpec；输出 owned CUDA uint8，渲染不推进物理。GeoPhys 公开设备写帧 API 完成转换；窗口与传感器共享资源且能分别关闭。 |
| 第二物理来源 | Isaac 原生公开刚体视图发布 CUDA pose，真实 PickCube base/hand 挂载与窗口组合成立。物理仍为 scalar，B=3 只是渲染布局复制；仅接收 R0 第二来源／挂载前置验证，绝不认作 Isaac native batch。 |
| Recorder | 复用 VectorTransitionRecorder 和既有 H5 writer；显式开启记录才选行读回，保留五元组和终止图像，记录失败后锁存且清理可重试。全部公开记录边界均有独立状态、身份、时钟和像素比对。 |
| 兼容性与关闭 | scalar device facade 复用单行共同实现，去除 B 轴；旧入口范围保留。资源关闭、transport 和 recording 的受影响定向检查通过。 |

attempt002 的 H1–H7／A02 修复项按上述实测交集关闭；执行报告中的 `PASS_BOUNDED` 不升级为全 provider、任意资产、任意相机或规模性能通过。代码检查未发现需要额外生产补丁的本包阻断项。本次收尾只修改文档、编排和模块 Skill，不增加探针、防御分支或新的运行 owner。

## 独立复验

本次新跑的是 **58 项定向检查和 6 份离线读回**；没有重新启动 GPU／Isaac／窗口。真实 native 运行采用执行报告中的原始证据，不能描述为全部在本主审重跑。

执行环境为 `/home/lly/miniconda3/envs/geochora/bin/python`，测试时 `PYTHONPATH` 包含仓库与 `GeoPhys/src`。

| 新执行内容 | 结果 |
| --- | --- |
| `g06/test_device_semantics.py` | 29 passed |
| `test_v211_g03_3a_transport.py`、`test_v211_physical_recording.py`、`test_v211_render_fault_cleanup.py` | 合计 29 passed |
| `forge070-record-camera-002` | PASS；4 个 H5、2 行、21 intervals，全部公开边界逐项读回 |
| `forge070-isaac-sensor-window-001` | PASS；真实双相机与窗口，pose 最大误差约 1.42e-7，105 原生步 |
| `isaac-sensor-001` | PASS；无窗口传感器证据，保留其升级前运行身份 |
| `postmerge-isaac-window-001` | PASS；无传感器有窗口，关闭窗口不改变物理时钟 |
| `postmerge-isaac-no-window-001` | PASS；无传感器无窗口 |
| `scalar-device-scalar-camera-schema-003` | PASS；scalar owned CUDA 图像与终止帧 |

离线复验结果见 [readbacks.json](../../../../../../workspace/maintenance/v211_g06a_attempt002_review/readbacks.json)，身份与保护核对见 [review-summary.json](../../../../../../workspace/maintenance/v211_g06a_attempt002_review/review-summary.json)。执行包已保存的中间 RGB 像素和时钟破坏负例能被 reader 拒绝，本主审复核该记录，未重跑破坏实验。Isaac hand 图像的 H5 fixture 不等同于真实 PickCube 终止／reset 全链。

## 后续范围与收尾

6b 继续实现三后端 × Pendulum/PickCube 的真实 canonical batch、batch Robot 信息及通用声明接线；6c 完成固定 Rasterizer 跨后端验证、A→B→A 和规模测试。不能为某个 Panda、资产路径或类添加专属接线。R3／模型／重力补偿保持独立后续接收。

性能按用户已确认矩阵执行：PickCube 有无传感器 × 有无窗口；Pendulum 只测有无窗口。先 B=16，成功且无传感器无窗口达到 10 control steps/s 以上才依次测 256、4096，分别报告吞吐和显存。当前设备相机逐 camera／env 渲染、同步及终止帧复制需要纳入这些测量，现有 B=3 正确性证据不是吞吐承诺。Rasterizer 优先，MJWarp renderer 仅备选。

受保护 `MUJOCO_LOG.TXT` SHA-256 为 `3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`，未修改或纳入提交；共享 native 锁核对可用。本次不启动后续实施、不修改 pins、不执行 merge／push／tag。当前状态、API、能力矩阵、编排与模块 Skill 同步到本结论，历史报告原样保留。

文档静态校验：`validate_docs.py --mode current` 仅报既知 `protected local input changed: MUJOCO_LOG.TXT`，历史链接问题 79 项维持原有范围；本次未调整保护基准。实际日志摘要与本包要求一致。`git diff --check` 通过。校验原始输出保留在 review workspace 的 `doc-validation.txt`。
