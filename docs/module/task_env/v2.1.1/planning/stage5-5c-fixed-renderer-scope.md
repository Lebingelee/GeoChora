# G05 5c：固定 renderer、通用场景与跨组合

当前状态：5c 三次普通 attempt 均已主审，整体未接收；第三次发现 Isaac USD task RGB reset 回归，现由维护者主导人工诊断，见 [attempt003 主审](../maintenance/reviews/20261108_5c_attempt003_sol_review.md)及[诊断现状](stage5-5c-human-diagnosis-baseline.md)。本文保留维护者于 2026-11-07 修订的范围，承接 [G05 目标](../goals/05-rendering.md)及 [render 协议](../contracts/render-provider.md)，不改变 5a／5b 的历史接收或已保存证据；下面的实施次序是原规划，不代表当前进度。

## 已确认的范围

1. renderer 在创建 public Env 时选择并绑定，维持到该 Env 的 `close()`；reset 不切换 renderer。可为 reset 重新构建**同一** renderer 的内部 session／资源，但不允许静默换路线。renderer A→B→A 延后至未排期的后续任务，不是本阶段接收门，也不自动分配到 6c 或其他阶段。
2. 已有 backend／Controller reset 目标不撤销；若新 backend 或其他 reset 配置与该 Env 固定的 renderer 不兼容，必须在可静态判断的副作用之前明确拒绝，不能静默换 renderer 或声称已经支持该组合。不同 Env 可在创建时选择不同已准入组合。
3. 保留 5c 的同步任务 RGB：每次成功 reset 返回当前 reset 首帧，每个正常 step 返回与已发布状态对应的图像，无需用户再调用 `render()`；保留相机/状态身份、completion、缓存失效、失败传播、资源释放和无额外物理推进。此前 5b 的窗口和离屏 RGB 成果依照代码与输入影响复用。
4. 至少实现并真实验证一个不同 physics provider 与 renderer 的跨组合。首选 GeoPhys CPU physics × MuJoCo renderer；若不可行，按 G05／D01 带具体证据提出替代，由维护者决定；不暗示任意组合均可使用。
5. PickCube 是本阶段的真实验证环境。公共渲染构建、state→visual 映射、相机、同步与生命周期必须消费通用任务／场景／状态声明，不能按 PickCube 名称、cube 路径、Panda 关节数、固定相机 ID 或单一资产写产品特判；任务自己的 Solution、资产、相机配置与任务语义仍可位于正常 task owner。手工构建的其他任务若满足相同声明、资产、provider、状态及渲染能力，可通过同一公开构建入口配置并使用已准入组合，并以其 Solution 或固定动作 step；不承诺未验证的任务、表示或任意 provider 组合。

## 通用性与真实验证边界

本阶段用 PickCube 做真实端到端验证，并在实现审查中追踪 public factory → 通用 scene/source、named frame/state 和 camera declaration → renderer adapter → observation/close 的实际生产调用链。映射与准入由声明驱动，不用隐藏注册项、测试专用旁路或特定任务名来选择绑定。对不同名称／数量／层级的合成声明或轻量 fixture 做必要的合同测试，至少覆盖名字变化和缺失／歧义映射的明确拒绝；这些测试只证明通用契约，不冒充真实 native 任务验证。

若现成的第二个手工构建任务可以在授权和资源预算内通过同一入口做小规模真实验证，可作为额外增强证据；不把另建第二任务、完整第二 Solution、任务成功或完整任务矩阵设为原 5c 新门。若未做第二任务真实运行，报告必须明确“通用实现和有限合同证据”与“其他真实环境尚未实测”的区别，不能承诺任意用户任务立即可运行。

## 建议实施次序

1. 冻结创建时 renderer 选择与 RGB observation 规格，明确 route、camera、支持表示、数据 ownership、reset/step phase 和拒绝语义；先检查 GeoPhys→MuJoCo 的公开状态与 free-body 映射可行性，不用旧 Position scalar 结果代替 PickCube 验证。
2. 在 PickCube 的 MuJoCo 原生路线建立公开生产 Env → reset/step 同步任务 RGB 的纵向链路；不把 UI observer 帧直接当作任务图像。保持 state-only 和既有 observation 调用兼容。
3. 补 GeoPhys rasterizer 与 Isaac RTX 的任务 camera 采集及同步；按资源和实现依赖允许与下一步调整执行次序。三条原生路线分别按声明目标准入并验证，复用不受影响的 5b 结果。
4. 接通并验证真实跨组合，证明相同公开状态驱动 renderer-only visual model、正确自由体姿态和相机，不执行第二物理求解器。与同一 Env renderer 切换无关：每个 Env 只使用创建时所选 renderer。
5. 检查固定 renderer 跨 reset、旧帧失效、required capture 失败、真实清理、同初态同动作有／无渲染的物理控制边界，以及必要的非 PickCube 声明测试与代码审查；保留无受影响的历史证据。

先跑可行性小检查是为了尽早暴露阻碍，不以纯构建、schema、fake、截图或低质量像素分数代替真实 RGB 与状态同步。维护者先前对 Isaac 场景可辨性的人工接收继续有效；图像规格、camera 几何、state identity 和变化仍应以适合 5c 的独立证据核验。

## 后续安排

上述范围是规划合同，不是新的 native／SDK／GPU／GUI 授权或实施派发。三次普通 attempt 均已完成并独立主审；目前按维护者指示进入人工诊断，详见[诊断现状](stage5-5c-human-diagnosis-baseline.md)。后续具体实施仍须明确当前 HEAD、writer、范围、资源预算与执行授权，由维护者指定并手动转发。不要自动进入阶段 6、merge、push、tag 或发布。
