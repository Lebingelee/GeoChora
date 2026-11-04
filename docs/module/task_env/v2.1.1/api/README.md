# v2.1.1 API 与迁移入口

状态：阶段3前维护整体仍为PARTIAL；生命周期R1已获[Sol有限接收](../maintenance/reviews/20261105_lifecycle_unification_sol_review.md)。当前可调用入口以 [TaskEnv 当前 API](../../../../../task_env/doc/api/index.md)和源码为准；selected 环境实现已迁至 `task_env.environment.reference_env`，旧导入保留兼容。`BaseTaskEnv` 已是 `SelectedReferenceEnv` 同对象兼容出口，三个组件任务使用共同 episode owner；源码与无引擎契约已复核，真实 provider 回归未运行。本页下表是阶段3–6的设计目标，并非当前能力；已有行为及证据不因本页或导入成功而扩展。

Phase C 的标准方向是外部 Solution 读取 observation 并产生 action，由调用方交给 `env.step(action)`；现存 `step_expert()` 是尚未迁移调用者的受限兼容，不是新标准 Env API。部分 `step_with_solution()` 路线由 Env 调用调用方持有的 Solution，属于受限过渡；NutAssembly 现支持调用方直接传入含来源边界和控制请求的 `ExpertAction`，并在 `observe` 校验五个 native 样本；裸数组仍拒绝，新路径完整物理验证待做。详见[当前 Solution 说明](../../../../../task_env/doc/api/planning/task_owned_solutions.md)。

## 需形成的公共体验

| 操作 | v2.1.1 目标 | 责任与边界 |
| --- | --- | --- |
| make_env／配置 | 查询并选择合法 physics／solver／renderer／Controller／batch 组合 | 复用 registry 和配置解析，Core→任务类→YAML→调用方 |
| reset | 新 episode 按初始化规则选择允许的执行组合／Controller | 同一public Env内部重建，不迁移旧物理状态；Core sampler按seed规则保持；固定 obs；原生 batch 按批次切换 |
| step | 运行已确定的组合，返回当前边界状态／图像和评价 | 不在步进中替换 provider 或 renderer；Controller 依赖公共反馈 |
| render | 可配置相机的 human／RGB 可视化 | 与相机 observation 协调，额外调用不推进任务物理时间 |
| 查询 | 实际生效配置、能力／拒绝原因、action spec／space | 输入规格可随 reset 更换 Controller 改变，调用方负责匹配 |
| close | 清理自有资源并使借用数据失效 | 原生共享资源和进程级 runtime 不假装每 env 独立销毁 |

用户只配置backend／renderer／controller／camera等，不需构造receipt hash、lease ID或generation。

权威语义见[协议索引](../README.md)；语义按已确认五协议，生产字段／方法在所属后续包冻结，阶段 3–6 随实现补齐 API 页面。`ExecutionSpec` 等现有类型与兼容解码须显式处置，不因本表新增平行 facade。

## 兼容和迁移记录要求

- 当前 selected state-only 输入继续有明确行为；新 renderer 不能通过无条件放开 admission 接入。
- 旧 position／mixed 命令和新 JointEffort／BodyWrench 主路线区分身份与准入；Robot／嵌套组件声明通道，Panda8维输入→7＋2输出，贡献显式组合，不改变旧证据含义。
- observation 构建后固定；动作输入变化须更新 schema／space，fixed-space consumer 不支持时明确拒绝。
- `BaseTaskEnv` 等保留名字按既有 2.x 约束处理，先迁生产 caller，不能创建第二套 reset／step。
- PickCube、NutAssembly 迁移按真实实现和 caller 收口，LIBERO 保留 benchmark 语义；不宣布全部任务已统一。
- 记录格式变化沿用已有 Recorder 和独立 reader；episode 配置、旧版本读取及失败行为有检查。

完成 3／4／5／6 阶段时更新对应 API 与迁移说明，7c 汇总。新示例只能使用已实现并验证的公共入口，不能以概念示例冒充已运行代码。
