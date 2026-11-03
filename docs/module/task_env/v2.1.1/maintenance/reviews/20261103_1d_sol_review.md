# G01/1d attempt001：Sol 独立审核

日期：2026-11-03。结论：`ACCEPTED_BOUNDED_1D_DESIGN`，包含下述有界文档修正。G01 的 1a–1d 设计交付均已独立审核；**五协议仍为 DRAFT_FOR_DISCUSSION，最终冻结等待维护者确认**。这不是代码实施、native支持、任务成功或Qualification，未启动2a。

## 提交、输入和原始输出

- input `8e70ee581602016932c99a257faad7aa6e5f91ea` → output `f1d9484214f9940ba3baec89c2704227317cf263` 是直接父子；develop 原执行恰改11个授权文档路径。GeoPhys pin/检出 `67da1165149486d3ae3e779c13ce31af49e17d50`，provider clean。
- package manifest `1e8e68502abb9ee13267a8f6b91cb53838db432c3f014d52eab809f659f9d5ee`、prompt `db366f1e82d8dee188f9502fc00a5b8aa525de33597498630a1270abd87872da` 与sidecar匹配。prompt中的seal指该checksum sidecar；无独立seal文件不是少一份强制输入，不改原封存包。
- output manifest `353187742985051aa6d38e77a5f8321cc2c8afc4cd6e43e9be0f295a66aa8f9d`；清单14文件的大小/hash全匹配，总188601 bytes。report SHA-256 `f41204dcf821fb88b1fb0bd090c45064bd674787c680449a55450a223fce6395`。
- 90项冻结输入中82项未修改、8项属于允许更新；24项先前raw文件/manifest及两个untracked保护文件hash保持。能力矩阵原执行只改target_resolution，其余JSON值完全相同。
- 原执行与本主审均未使用subagent、provider import、runtime/App/window/solver/physics/GPU或implementation tests。原raw、保护文件、子模块、依赖与生产代码保持；主审修正另记本地提交，不增加执行attempt。

## G0–G5

| Gate | 主审处置 | 依据与限制 |
| --- | --- | --- |
| G0 | 接收 | 输入父子/范围/包与raw hash、保护/pin一致；seal备注解释清楚 |
| G1 | 修正后接收 | 七类双向操作、三目标、camera/state/completion/lifetime具体；修正公共Env返回与内部adapter receipt分工 |
| G2 | 修正后接收 | 三native＋一cross候选/缺口/owner保留；App独立owner与generic UI私有调用欠账明示，不升级证据 |
| G3 | 修正后接收 | terminal retain在覆写前、mask-reset参照post-step时刻、reset副作用失败与初次构建失败分开 |
| G4 | 修正后接收 | 5P+7N保留，P3时钟按typedclock、P5单独检验renderer切换；补齐control/asset/Recorder映射，DAG/draft/status静态校核 |
| G5 | 接收 | 完整报告/命令/findings/快照/hash/本地提交与窗口释放声明；不把执行工具的Goal完成等同G01协议最终冻结 |

## 主审修正与源码依据

1. **公共返回与内部回执分开。**原建议render返回PresentationReceipt/OwnedRGBFrame、close返回EnvCloseReceipt，与当前TaskEnvRenderProvider的human→None、rgb_array→array及公共close习惯不一致。保留结构化内部receipt，公共render返回数组/None、close返回None，诊断沿现有receipt通道；不新增第二套生命周期。标准NumPy返回与显式device/lease API分开，task obs无需因此全部CPU化。旧BaseTaskEnv的mode参数和无UI时报错须在5b明确兼容/迁移，建议行为不能追述为当前事实。
2. **RGB默认不强制无理由迁移。**CameraGeometry/normalize_rgb已支持float32/uint8和HWC/CHW，当前默认HWC float32[0,1]。原交付摘要建议全新route默认uint8，主审建议沿用既有默认并允许构建显式选择；构建后跨renderer保持相同契约。颜色空间不能从dtype推断，5a需明确来源/转换；旧无颜色声明不自动取得新保证。
3. **Terminal保留先于reset覆写。**原P4把retain列在autoreset之后，与正文要求矛盾；现把terminal两相机copy/retain移到reset前。parallel.py::_step_and_autoreset及sb3.py::TaskEnvSB3VecAdapter.step_wait均在reset前通过tree_index保存终止obs；tree_index对NumPy叶子copy，已有事实保留，未来device view仍需明确租约。
4. **未选行只在mask reset中不变。**env-0随batched step正常从step4/rev50推进到step5/rev51；随后env-1的mask reset保持env-0这个post-step边界不变。正文和N7不再误示整个batched step未推进env-0。
5. **时间/相机上下文完整。**P3不再把episode/step/revision三元组当StateSampleClock；明确schema/domain/index/simulation_time_s及2ms×5的时序。observer render与task capture区分。P2补body-origin/world/wxyz/m等约定；P5由同时换physics+renderer改为同一GeoPhys CPU下renderer A→B→A，联合切换仍留3c/5c真实集成，不新增当前支持声明。
6. **Reset失败不能只看时间。**reset已写新状态或rebind已关旧资源，即使physics time未前进，capture失败也已过first effect，须fault；只有纯preflight才无损拒绝。初次构建清理完整可回未物化与破坏性rebuild后失败分开，沿用1c。
7. **共享owner不合并App。**Physics adapter持physics scene/model，App由原per-process App owner管理；renderer借用有限lease。Generic UI当前仍跨visualizer下划线操作，不能当成目标public binding证据；5a/5b须经正式公开/runtime-facing renderer API收敛，若修改provider API/pin先单独冻结范围。
8. **完整五协议追踪。**新增具名effort/gripper传动、Controller公共模型/反馈provenance、reset action spec/旧wrapper、资产数值准入及Recorder独立读回的owner/子阶段/oracle，避免联合表只追踪render而丢失1b/1c要求。统一表示与control正文保持原字节。

本审核不把规划JSON当public schema或可执行实现测试。原报告/findings保全，其中被收紧处以本页为后续审核说明；不能追溯扩大原checker或原运行证据。

## 建议维护者最终确认的协议边界

以下是可整体确认的具体建议，协议正文仍draft：

- reset/step的**实际capture phase**在新版本请求/identity中分别表达reset_initial/post_control_step；旧CameraGeometry/identity decoder/hash保持，不直接放宽旧版本枚举。
- **图像规格由构建契约决定**：默认复用现有HWC RGB float32[0,1]，构建可显式选择uint8/其他已实现布局；一个Env跨backend/renderer保持固定。颜色空间/必要转换在5a前明确并由admission核对。
- **普通obs/Recorder默认独立存储**，保证跨下一调用可持有；owned不等于强制CPU或重复copy。显式device borrowed view须有caller能力、fence/retain/expiry，不隐式改变普通调用语义。
- **窗口关闭只停展示**，独立task capture可继续；required capture在有native effect后失败则faulted。App无法分离时按准确route报告限制，不能拿旧/零图补正常transition。
- 既定scope不变：三物理路线、三项render目标、一个cross组合、至少两physics provider并行；复杂后端/非刚体扩展位置与effort方向保留，具体运行实现按3–6推进。最终PickCube9/9仍是7b目标，不因设计交付而降低。

上述建议是对既有需求的兼容收敛，不要求维护者指定实现类名或所有容差。维护者确认后才记录协议基线并准备2a单子阶段包；本轮不派发、不编码、不启动native。

## 静态核对与参考

CodeGraph先定位single render provider、camera contracts/images、parallel/SB3/tree与MuJoCo visual consumer；当前源码证实return/dtype、tree_index copy、capture phase限制及shared App边界。只运行文档治理current、JSON/案例引用与时序、22项DAG、5份draft、13个NOT_STARTED目标/9个NOT_RUN格、diff空白和hash保护核查。96个历史链接问题保持，未运行实现测试或native。

[Gymnasium Env API](https://gymnasium.farama.org/api/env/)支持human返回None、rgb_array数组以及close习惯；当前项目没有因此声称全部wrapper/human自动呈现兼容。[Isaac Sim 6.2 core migration](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/migration_guides/isaac_sim_6_0/core_api_to_core_experimental.html)区分SimulationManager与RenderingManager职责；[6.2 camera sensors](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/sensors/isaacsim_sensors_camera.html)是未来public API候选来源。2026-11-03查阅，均不是本机adapter/runtime证明。

原始[报告](../../../../../../workspace/maintenance/v211_g01_1d_attempt001/report.md)、[交付摘要](20261103_1d_render_protocol_design.md)与[实施追踪](../../planning/protocol-implementation-map.md)保留。
