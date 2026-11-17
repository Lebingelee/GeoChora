# G07 7c attempt002 执行返包（待独立主审）

本记录是实施者的有界结果，不是维护者接收或发布。工作包 SHA256 `bb2941163a530caf1b94ca347aa620e9ea3de9809d398acda2a63ec72ae58fab`；输入 HEAD `2c697908d7e7948c4b33e65fabdd6ec88e3dda1b`；分支 `codex/v211-stage7-integration`；普通 attempt 计数 2。GeoPhys `198d30ac64ce873a1467f55d2adfc471db18fbc5`、Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` 未变。最终候选 commit/tree 与锁释放以 ignored 输出根的 `closeout.json` 为准，避免文档自引用。

| 门 | 实施者结论 | 实际范围及核验入口 |
| --- | --- | --- |
| C2-1 普通动作和严格 Solution | PASS（待主审） | Nut binding 准入合法 world-pose；既有 Controller 解释并施控，非法 shape、NaN、零四元数在推进前拒绝。`invalid-001`、`solution-guard-002`、`reverse-mix-001`、`registered-mix-001` 保留 caller 结果；不以注册和属性替代运行。原/装配及两种入口的逐 transition 证据见下表。 |
| C2-2 真实运行和记录 | PASS（有界，待主审） | 原 MuJoCo/GeoPhys 各 32 步、装配 MuJoCo 8 步；两条 MuJoCo Nut Solution 各自完整成功、严格完成、轨迹完成和关闭。同 run 独立 reader 和 interval audit；GeoPhys Nut Rasterizer 首帧拒绝是下述独立限制。 |
| C2-3 marker | PASS（待主审） | 声明 Panda/R1 后经 source snapshot、composition/subject binding、Controller 和 Runtime；`marker-007` reset→非零 step→reset→close，marker 自身高度有记录，H5 独立 1/2 读回。 |
| C2-4 深入模块文档 | 候选完成，待逐页独立复核 | 原结构 34 页逐页映射、输入输出哈希及模块归属在 `doc-map-audit.json`；8 篇历史日志保留。50 个当前文档/JSON 项的 77 代码块完成语法与本地链接检查，核心普通动作、marker、静态声明等有命名运行；其他示例是静态核对，不声称全量运行。 |
| C2-5 合同/教程/矩阵 | 候选完成，待独立复核 | 单一能力矩阵保留原 7b 九格实际输入 `78349184d0600e2fb804e6461930c475bfcc67c1` 和有界复用；普通动作与完整 Nut 为独立条目。BodyWrench、记录身份及已知 native 拒绝均保留范围。 |
| C2-6 本地候选 | 候选资料已准备，待独立接收 | `docs/releases/v2.1.1/` 为未发布候选；本执行者不移动 develop、不 push/tag/发布。独立主审后再依工作包核实祖先与占用并 fast-forward。 |
| C2-7 资源和保护 | PARTIAL：历史 GPU 监控缺口 | 后述完整和短程代表复验有 CPU RSS/整卡 GPU 监督；此前 CPU 监督器未采样整卡 GPU，原运行监控数据无法事后恢复。历史结果和失败均保留，不能声称每次 native 运行均满足整卡采样要求。 |

## 同运行证据

路径均相对于 `workspace/maintenance/v211_g07c_attempt002/`。各目录含 `result.json`、`supervisor.json`、`episode.h5` 与独立进程 `reader.json`；普通动作及完整 Solution 还含 `interval-audit.json`。H5 SHA256 是对应同一次调用的文件，T/T+1 不是跨运行拼接。

| 运行 | T/T+1 | H5 SHA256 | 结果 |
| --- | --- | --- | --- |
| `random-mujoco-004` 原 Panda | 32/33 | `22b75356ff31d6f440d41398e7106dcf10d729983b5da21949761d7792b5d5f2` | ordinary，close |
| `random-geophys-004` 原 Panda | 32/33 | `b7b95a95b68f10ab47e3672545132e120e79daa3b21369d484a42680dabf4f74` | ordinary，close |
| `random-assembled-004` 装配 Panda | 8/9 | `ec805f89be52c630c619f85d690813ca34a13ea9e2bbf134e196986218b77099` | ordinary，close |
| `solution-original-004` | 2377/2378 | `f82550092d7de6dacfad7aabf0ed6ad25807296f792ac8503234eee2cd63cfab` | task success、strict completion、planned trajectory 均 true，close |
| `solution-assembled-002` | 2378/2379 | `5646741e429676400d38b28cd353c12a147ae8d4c90220b157d9b8af41bffc74` | task success、strict completion、planned trajectory 均 true，close |
| `marker-007` | 1/2 | `059e085ce16c59ebe780cfe203c16f71082996b32c497d23f02f77c60ed83818` | ordinary、marker metric、close |

普通动作三条分别测得最大关节变化 0.0047619165、0.0047619343、0.0020107148 rad，最大开口变化 0.0252638632、0.0252640229、0.0029937369 m；按预冻阈值 1e-7 与前四步 hold 对照，记录逐步 action、ACK、5×2 ms 和实际状态，详见 `response-audit-resource-recheck.json`。普通动作没有 Solution 完成结论，Task success 与 Solution completion 分开。

兼容字段 `expert_identity` 仍为声明身份，允许合法 proposal 做来源匹配，不能单独证明专家执行；新记录按成功提交的 transition 区分 `ordinary`、已校验 `solution_proposal` 和未具备完整校验事实的 `solution_proposal_unverified`。普通动作为空的实际 Solution 身份、completion 未评估；reader 不从旧 `planned_action` 或 metadata 推断执行。PickCube 与 Nut 共用该记录投影；caller-owned Solution 不靠 `env.solution` 推断。外来身份、过期边界、缺控制请求和同 episode 混用仍拒绝。7b 九格未重跑。

## 构建与 owner 对账

Task 声明经正式 `make_env` → source snapshot/closure → Robot composition/subject binding → Controller 绑定 → RobotRuntime；marker 不手造 closure 或跳过 subject guard。Robot 持有 recipe/名称和能力，Controller 持有解释和计算，Task 拥有其语义；未建立专用 factory、Runtime 或 Recorder。Nut action 和 feedback 的缺口分别回原 Task binding、共同 Env 和 action contract；canonical reader 解释记录身份角色。实际正负例与同 run 读回优先于类注册和配置自比较。普通 reset 后旧 Solution 身份失效；本证据不扩展任意 Controller 切换矩阵。

## 失败、资源与限制

`render-geophys-001` 在首帧以 `selected task RGB requires a canonical Scene and source closure` 拒绝，未完成 action，关闭成功；不能把 state-only GeoPhys 成功写成该 render 成功。`marker-001`～`003` 的构造失败和其他重试未删除；旧 lifecycle 测试收集时依赖已退休 `dispatch_leaf_control_interval`，未恢复旧接口，其他失败见原日志。有效 Solution compatibility 15 项与目标测试 2 项通过。全新安装、human 窗口观感、所有相机参数和 device 六命令未在本包验证；MuJoCo FREE angular armature 写前拒绝、既有 GeoPhys/其他 provider 的限定继续有效。

本 attempt 的 50,000 子步上限经用户追加 30,000 为 **80,000**，未重置已有消耗；计费 **72,980**，余 **7,020**，含 GeoPhys worker 与教程按完成 transition ×5 保守计入；隐式启动/reset 步数无法计数。受监督 native 累计 **778.17 秒**，上限 3,600 秒；各 run 原始回执与单次峰值见 `run-ledger.json`。此前 CPU-only 监督未记录整卡 GPU，后续六条补测按最终源码、同一锁和 CPU/GPU 监督执行，不能为此前运行补造数据。原始输出目标与保护核对以 `closeout.json` 为准。

实施者仅交付独立审阅候选；不自授 7c 接收，不重开 attempt003、G05/G06，不改写既有失败或把本候选说成已发布版本。
