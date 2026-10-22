# P99 两项运行缺口关闭收据（2026-10-22）

## 结果与范围

**PASS_BOUNDED：公开单 Panda Position candidate 主线与当前 pin D05b pairing。**
[P99 readiness](P99_Readiness_Review_2026-10-22.md) 记录最终范围仍待维护者审阅；本收据不是 Judge decision。
B04a 三类历史 H5 golden 继续 ACCEPTED-DEFERRED，与这两项通过分开处置。

执行基线：`codex/phase-ii-c03b`，Core HEAD `1e3b558d38de746e3290246171b8e578d7323603` 加本地 source/docs changes；
GeoPhys checkout/gitlink `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`；Menagerie
`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。Python 3.12.14（已有 `geochora` conda 环境）、
MuJoCo 3.8.1、Taichi Forge 0.6.3。旧审阅和既有 dirty patch 已先检查点保全，hash 见 P99 review。
无 Provider/frozen Artifact/ref 修改，无 push/merge。

原始日志/实测 H5/图像/depth/mask/label-map/receipts 都在 ignored
`workspace/maintenance/p99_runtime_closure_20261022/`，以下称 `$RUN`。新输出目录拒绝覆盖已有内容。
`execution_manifest.json` 记录实际命令、退出结果、源码与原始输出 SHA-256；`final-source.patch` 保留本地 source diff。
这些事实不代替保留原始 Evidence。

## 复用 gate 与边界

分类：**EXTEND_EXISTING**（公开 registry route）；**EXTRACT**（task/source construction）；Runtime/Controller/Observation/Recorder **KEEP COHESIVE**。

| 七步证据 | 检查与处置 |
| --- | --- |
| owner | `task_env/tasks/` 拥有任务配方；registry 仅保存 class，selected Environment 拥有生命周期 |
| public APIs | `make_env()` → `ENV_REGISTRY` → `from_reference_config()`；现有 `from_position_candidate()` 是内部扩展 hook |
| implementations | 原 `c02b_position_candidate.py`、D01a/D01b source helpers、Position Profile、plan-bound RuntimeSession、Generic H5 v3 |
| callers | C02b/C02c/C03b、D03/D04/D05b 诊断共享原 builder；旧 PickCube/NutAssembly selected registration 继续原路 |
| tests | Position/H5、Position Profile、C02c、D01a source/projection 与 D05b integration；新增 public UID admission/failure 回归 |
| established limitation | 原 builder 导入 test modules，registry 无 candidate，不能以独立 diagnostic 证据拼成 P99 mainline；旧 pairing pin 不适用当前 pin |
| repair/extension/composition | 提取必要函数及精确源输入到同一个 task owner，原 diagnostic facade/test helpers 转用该 owner；新增一个显式 UID，不复制执行框架 |

| owner / state | lifecycle 与 exposure | 验证/处置 |
| --- | --- | --- |
| `tasks/position_candidate/source.py`、`builder.py` | 固定 Scene/Artifact/ResetPlan/source snapshot/plan；construction 才读文件/import scene | 原始四份输入 bytes 保留，task-owned active inputs 与历史副本逐字节相等；没有 test import；原 source/Artifact identity 不变 |
| `PositionCandidateEnv` / registry | import 只注册；construction 限定 GeoPhys CPU、state-only、固定 seed 31 | config/render/kwargs/旧 overlay/重复 source 目录拒绝；import subprocess 禁止 native/test modules |
| `SelectedReferenceEnv` / RuntimeSession | reset→request preflight→compute/apply/step→publish；原有故障闭锁/close | 无新 mutable state owner，真实连续 mainline 与 failure tests |
| Observation / Generic H5 v3 Recorder | reset observation + 每个实际 step append；finish 后同文件 reader | 64/65，数值和身份精确相等；record failure 零伪 transition |
| existing dynamic CameraSession | source/typed-state→sync/capture，独立消费者/close | current-pin S1/S2；不接 policy observation/TransitionRecorder |

原 D01a frozen fixture files 未移动/删除；从其精确 bytes 提取四份 active inputs 到 task owner，测试会比对它们。
生产 identity gate 使用显式 ValueError，避免 Python `-O` 消除断言。旧 candidate builder import 路径保持转发兼容；
旧 UID 和默认 selected task 路线未改。未建立第二个 Runtime、Recorder、Controller、provider abstraction 或 Skill。

## 公开主线真实执行

公开 UID：`panda-position-servo-candidate-v1`。入口仍为 `from task_env import make_env`，config 仅
`provider=geophys`、`backend=cpu`、`horizon`（整数 1–6000）、可选 fresh/empty `source_workspace`。
默认 source 路径在 ignored workspace；默认 horizon 6000。reset seed 省略使用 31，其他 seed 拒绝。
render mode/任意 overlays/kwargs/其他 provider/backend 拒绝。详细使用与 reader imports 见 [Public API](../../public-api.md)。

同一个公开构造对象完成 reset、start_recording、64 次真实 `step(StructuredActionRequestV1)`，每步返回公开 observation，
finish_recording 后从同一路径读回 Generic H5 v3。复用原动作段：20 open + 12 移动/open + 20 close + 12 reopen；
100 Hz / 每 interval 五个 2 ms native steps（通过公开 clock delta 推断，不冒称额外 native counter）。

| identity | 本轮原值 |
| --- | --- |
| Scene | `047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e` |
| Artifact | `a56b6cbac66bc570c43d38b8eb5a7e3098873cc196015242d3e46df76dd0364c` |
| TaskSource | `e57fcc60788cab2c3c0d06648740f10c14d4ee12f3061fb91ed014f18cd6403e` |
| source closure | `aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47` |
| ResetPlan | `7965ae3292f96c82e99a442754b36172c885e049204ffb1b1bcb58a4d4a2d53d` |
| Position Profile | `3c8fae3e65515f4a62a0c2ba9c5b09d11e8b67ff724642948371b2539050836e` |

request/target/applied ack 的 writer/group/target hash 逐步核对；request 从同一 H5 typed reader 读回并与发出的 request 相等。
H5 joint/hand/boundary leaves 与 live returned observation 全部精确相等；64 transitions / 65 observations，action projection 64 条。
Artifact/Scene/source/reset/plan/profile、episode boundary、native/control clock 都由同一环境和所记录 payload 绑定。
arm 最大 joint delta **0.167802706 rad**；gripper opening 初始 0、峰值 **0.004882263 m**、closing 后 **0.002224914 m**、
reopen 后 **0.003592893 m**。运动 detector 保持原门槛（arm 1e-4 rad、gripper 各段差 1e-3 m），没有放宽。

原 runner 的 terminal guard、重复 reset 新 episode/相同 ResetSample、apply/step/record fault trials 同时从公开 factory 构造。
record append failure 后物理已前进，但 recorder 保持 0 transitions / 1 observation，现有 C03a fault 闭锁拒绝下一 action。
该失败不冒称物理 rollback 或有效 transition。主线 H5 只来自一段连续运行，不与 fault trials 或 camera 诊断拼接验收。

Evidence：`$RUN/public_s2/{geophys-receipt.json,geophys-position-s2.h5}`、`$RUN/public_s2.log`。
公开 observation 的独立 read-only 重读、错误 Scene/plan request、错误 source identity、import/config/录制失败另见 public S1。

## 当前 pin D05b pairing

真实 context：MuJoCo EGL 离屏，`MUJOCO_GL=egl PYOPENGL_PLATFORM=egl EGL_PLATFORM=surfaceless`。
GL vendor **NVIDIA Corporation**；renderer **NVIDIA GeForce RTX 5060/PCIe/SSE2**；OpenGL **4.6.0 NVIDIA 595.84**。
Execution selection device=None，actual device 由驱动选择，未伪称显式 GPU ordinal。Physics 仍是 GeoPhys CPU；未更换 provider。

S1 **3 passed**：default/override admission、缺 native dependency、错误 identity、不触发 physics、分配后 constructor failure
恰好 close 一次、capture failure、sibling consumer 可用、重复 close 和已 close 拒绝。

S2 **PASS_BOUNDED**：原 Position candidate/source 同一 RuntimeSession reset→12 个真实 interval→sync/capture→reset/capture→close。
固定与 hand-mounted 两个 consumer 共六次 RGB/Depth/Entity-mask capture；检查 capture/state boundary、clock、episode、reset/source
和 effective renderer selection；mask uint32/0 background、dense Entity labels、label-map/disk readback、已知几何 optical-Z/depth/遮挡。

- hand displacement **0.086662478 m**；mounted camera translation **0.086517026 m**；fixed camera pose delta 0。
- fixed/mounted RGB changed pixels：**2251 / 1171**；Depth：**2154 / 15010**；Entity mask：**913 / 754**。
- capture 期间 Controller.compute / Provider.step / mj_step / mj_forward 均 **0**；clock 保持同一 boundary。
- 两个独立 consumer/native Renderer 各 close 一次；共 **2** 次。资源 oracle 是 session-scoped close，不要求进程 GL allocator memory 归零。

Evidence：`$RUN/d05b_s1.log`、`$RUN/pairing_s2.log`、`$RUN/pairing_s2/d05b_pairing_s2_receipt.json` 及其
`paired-camera-s2/` 中 PNG/depth/mask/label-map 原件和 raw receipt。旧 `4436787e` 收据和此前 X11 失败日志保持历史身份。
本轮不把 Camera 接入 policy observation/TransitionRecorder，也不据此声称 visuomotor 或通用 pairing 支持。

## 命令与检查

全部从 repo root 执行，使用已有 GeoChora conda Python，`PYTHONPATH=GeoPhys/src:.`。Renderer 命令加上文 EGL 三个环境变量。

| command（省略 Python 可执行文件绝对路径） | 结果 / 原始日志 |
| --- | --- |
| `python -m task_env.diagnostics.tasks.c02b_position_s2_probe --provider geophys --public-factory --output $RUN/public_s2` | PASS_BOUNDED；64/65；`public_s2.log` |
| `python -m pytest -q -p no:cacheprovider task_env/diagnostics/tasks/test_p99_public_position_candidate.py` | 最终 **15 passed**；`public_s1_public_request.log`（使用公开 plan/observation 构造 request；先前两版日志亦保留） |
| `python -m pytest -q -p no:cacheprovider task_env/diagnostics/tasks/test_phase_ii_d05b_pairing_integration.py` | **3 passed**；`d05b_s1.log` |
| `python -m task_env.diagnostics.tasks.d05b_pairing_s2_probe --output $RUN/pairing_s2` | PASS_BOUNDED；`pairing_s2.log` |
| Position execution H5 / Position Profile / C02c / D01a 四文件 targeted pytest | **35 passed、1 historical-pin failure**；`targeted_regression.log`；详见下文，不报告全绿 |

定向四文件命令：

```bash
python -m pytest -q -p no:cacheprovider \
  task_env/diagnostics/tasks/test_phase_ii_c02b_position_execution_h5.py \
  task_env/diagnostics/tasks/test_phase_ii_c02b_position_profile.py \
  task_env/diagnostics/tasks/test_phase_ii_c02c_position_switch.py \
  task_env/diagnostics/tasks/test_phase_ii_d01a_scene_materialization.py \
  -k 'not materializes_canonical and not canonical_axis'
```

该 `-k` 未排除旧 D01a pin-specific test；其真实执行后在 `provider_revision == 4436787e…` 断言失败，实际为要求保留的
`a53a8cfe…`。断言和 pin 均未改，也未覆盖旧 receipt（失败发生在写 receipt 之前）。该结果属于历史测试适用性失配，
不是 current-pin 通过；35 项其他检查通过。当前 pin 的 native 运行证据来自本轮两项专门验收。
native pytest 仅有已知 `locale.getdefaultlocale` deprecation warning，无 silent skip/fake renderer。native importer 仍产生已有 retained/rejected-semantics warning；有界 source/projection gates 与上述运行 assertions 均保留，没有据此声称完整 importer 语义支持。

## Skill refresh 与 review

module=`task_env`，mode=`refresh`；触发为新公开 UID、构造 owner 提取和 current-pin pairing 证据更新。
既有 Skill 的“无 candidate make_env / current pin 未复验”发生 drift；已就精确 Position CPU 路线、source workspace、
fixed reset、结构化 action/record/readback、EGL pairing、失败与消费者边界更新原 Skill 和 routes，未新增同义 Skill。
七步复用证据与 owner/state/lifecycle 表见上。最终检查：

- `check_module_skill.py .agents/skills/geochora-task-env`：PASS（metadata、本地链接、显式源码路径）。
- 系统 Skill Creator `quick_validate.py .agents/skills/geochora-task-env`：Skill is valid。
- 10 个变更 Python 文件 `py_compile`：PASS；`git diff --check`：PASS。
- touched Markdown 本地链接/显式锚点检查：**311 links / 20 files，全部通过**。
- Public API 四步示例真实执行：exit 0、同文件 **4 transitions / 5 observations**；
  `$RUN/public_api_example.log` 和 `workspace/maintenance/p99_candidate_example/episode.h5`。
  该补充示例单独验证文档，不替代上文 64 区间主线。

独立冷启动核对只授予 read-only/provider-free 范围：以 repo、AGENTS、module Skill 与“公开 Position candidate 录制/readback、
当前 pairing 和不支持交集”的具体请求导航 owner/API。该核对由独立冷启动 Agent 只读执行，初查发现 request 构造/import/plan ID 与 finalize reason 使用说明不足；
已补全现有 Public API 可执行示例及 Skill 路由，复核确认两项导航缺口关闭、无剩余阻断。
原始核对摘要保存在 `$RUN/cold_start_review.md`。该核对不替代 native Evidence 或独立 maintainer review。
API/qualification-sensitive change 保持 **Human review pending**。

NOT_RUN：A–D 全量审计、NutAssembly 四组矩阵、485 interval R1、CUDA/R1/Assembly/Task Harness 扩展、
Camera policy/TransitionRecorder 接线、B04a 原始 H5 golden 恢复、新 Task randomized feasibility/Judge/freeze、
Qualification campaign、develop/main 集成。不得由本轮结论自动宣布 Phase II 完成。
