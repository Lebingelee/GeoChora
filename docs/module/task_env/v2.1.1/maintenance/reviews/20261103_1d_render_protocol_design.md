# G01/1d Render Protocol Design Review — attempt001

日期：2026-11-03。范围：只读联合设计审阅摘要，状态 `DRAFT_FOR_DISCUSSION` / `REPORTED_PENDING_REVIEW`，不是 Sol 最终审核，也不是五份协议冻结、实现批准或 qualification。

## 输入与审阅对象

- Package：`V211_G01_1d_attempt001`；提示词要求 1d，input Core HEAD `8e70ee581602016932c99a257faad7aa6e5f91ea`，GeoPhys pin `67da1165149486d3ae3e779c13ce31af49e17d50`。
- 审阅五份协议：unified-task-representation、control-and-feedback、physics-provider、render-provider、lifecycle-and-data。可写范围只触碰后三份；前两份只列主审建议。
- 源码 owner/caller 经 CodeGraph 定位后对磁盘 current file 核实；index 有漂移，没有重建或同步。未用 subagent；primary sole writer。

## 收敛的设计

1. `render-provider.md` 成为 render 双向操作、建议 typed requests/receipts、三类完成目标、两种 scene 接入路径、route matrix、RGB lifetime/cache/error、window/task camera 与 batch frame 语义的权威正文。
2. `lifecycle-and-data.md` 加入三方唯一 owner、共同 build prerequisites、reset/step publish barrier、owned/borrowed image、same-step autoreset 与 close 顺序；保留 1c physics lifecycle 不变。
3. `physics-provider.md` 只补 shared-scene limited binding、build-time requirements、同步 scene boundary 与 resource lease；不改 1c 控制、model、effort、feedback 决定。
4. 新增 5 个 positive + 7 个 negative planning-only cases，以及条款→源码 owner→最小 additive change/compatibility→3a–6c substage→未来 oracle 的映射。
5. capability matrix 仅更新 `target_resolution`：3 native routes 和 GeoPhys×MuJoCo cross 目标仍保留，所有目标/结果状态保持未开始/未运行。

## 当前源码事实与意见

- Generic `TaskEnvRenderProvider` 的 window/rgb_array 是 UI owner；其 render 不推进 physics，不会自动填充 task observation。
- 现有静态 MuJoCo/GeoPhys camera session 不等于 selected PickCube 的动态 reset/step RGB。
- 当前 camera geometry/identity 把 reset 首帧和 post-step 都记为 `post_control_step`；推荐 5c 增加调用边界 capture phase 与版本化 identity。
- GeoPhys CPU→MuJoCo OpenGL dynamic renderer 可作为 render-only model 更新路径，但当前 projection 拒绝 `free_joints`；推荐 5a 引入 typed free-body/frame pose mapping 后再检查 PickCube，严禁第二 physics advance。
- Isaac Sim 6.2 F06 App owner 是 headless/camera-disabled，当前无 task camera owner；未来按 exact 6.2 public/experimental camera API 建 adapter/build oracle，不以官方文档、viewport 或启动成功代替 capture。
- `RemoteBatchVecEnv.get_images()` 将一个 worker frame复制到 slots；same-step autoreset 的 `terminal_observation`/`reset_info` 语义可复用，但任务图像必须逐 row/camera identity。推荐 terminal frame reset 前 copy/retain。
- 失败若发生在 physics interval 已推进后，保留 clock/completed interval 和 fault；不得返回正常 transition、旧/零图或承诺回滚。关闭只由资源原 owner 执行，App 依 lease 完成后关闭。

## 五协议只读建议

- representation：增加 typed entity/frame/asset visual mapping 与 floating-body pose；保留 1b 旧 codec/hash、语义和被动 cube。
- control：renderer 仅消费已发布 state boundary，不在 `.render()`/App update 内运行 Controller/command/advance；不改 1c effort/feedback 决定。
- physics/lifecycle：共享 limited lease、completion fence、partial-progress fault、唯一 close owner 使用一致词汇并交叉引用。
- render/lifecycle：同步 reset phase、batch terminal/reset identity、window display loss 与 task capture 降级规则。

## 建议维护者集中确认

| 问题 | 推荐 | 替代 | 影响 |
| --- | --- | --- | --- |
| reset 首帧 identity | 新版本增加 `reset_initial`，request 由 Env 按调用边界提供 phase | 扩展旧 profile/identity 并兼容旧值 | 不加会无法证明 reset 与 step image 属于各自状态边界 |
| RGB canonical default | 新 required routes统一 HWC RGB uint8 `[0,255]`，旧 consumer float32 `[0,1]` 保留兼容转换入口；具体固定在5a/5c | 保持每路由不同dtype/range | 统一有利 observation schema 与 batch；需维护者接受跨 caller 兼容策略 |
| borrowed frame default | public observation/Recorder 默认 owned copy；仅显式 leased view 可零拷贝 | adapter-specific borrowed by default | owned较重；borrowed则增加 expiry/fence错用风险 |
| window 与 sensor 故障 | window closed只停展示；required capture failure使Env faulted；App不可分则该route显式失败 | App-loss整条route可选降级 | 影响episode是否继续与 fault receipt/API |
| 首发路线能力矩阵 | 保留 3 native + 1 cross 和三个独立完成目标，不预先声明互相覆盖 | 分阶段将某个 mode 标非required | 后者会减少用户工作包已确认的最终范围，需明确决策 |

这些问题不影响 3a owner安排：admission 合并需求由现有 admission/RuntimeSession owner负责；renderer exact API/build gate由5a；reset phase与buffer语义在5c冻结；batch row camera在6c。MuJoCo 依赖区间冲突需在3a处理，不在本 review 擅自指定隔离进程/改 pin。

## 未做与限制

静态文档、source、官方文档研究。没有 import/init renderer、Isaac App、window、runtime、solver、model compile、physics/GPU、图像 capture 或 implementation tests；没有新增 native evidence。96 个历史 source-link warning 是既有项，只能在最终文档治理输出中单列。报告由维护者手动转发；Sol 审核前不要冻结协议/派发 2a。
