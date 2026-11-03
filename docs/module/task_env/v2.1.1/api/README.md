# v2.1.1 API 与迁移入口

状态：设计目标，尚无本版实现。当前可调用 API 以 [v2.1.0 来源版本](../../v2.1.0/api/public-api.md)、当前源码及其有界矩阵为准。此页不提供尚未实现的函数参数示例。

## 需形成的公共体验

| 操作 | v2.1.1 目标 | 责任与边界 |
| --- | --- | --- |
| make_env／配置 | 查询并选择合法 physics／solver／renderer／Controller／batch 组合 | 复用 registry 和配置解析，Core→任务类→YAML→调用方 |
| reset | 新 episode 按初始化规则选择允许的执行组合／Controller | 不迁移旧物理状态；固定 obs；原生 batch 按批次切换 |
| step | 运行已确定的组合，返回当前边界状态／图像和评价 | 不在步进中替换 provider 或 renderer；Controller 依赖公共反馈 |
| render | 可配置相机的 human／RGB 可视化 | 与相机 observation 协调，额外调用不推进任务物理时间 |
| 查询 | 实际生效配置、能力／拒绝原因、action spec／space | 输入规格可随 reset 更换 Controller 改变，调用方负责匹配 |
| close | 清理自有资源并使借用数据失效 | 原生共享资源和进程级 runtime 不假装每 env 独立销毁 |

权威语义见[协议索引](../README.md)；具体字段／方法由阶段 1 冻结，阶段 3–6 随实现补齐 API 页面。`ExecutionSpec` 等现有类型与兼容解码须显式处置，不因本表新增平行 facade。

## 兼容和迁移记录要求

- 当前 selected state-only 输入继续有明确行为；新 renderer 不能通过无条件放开 admission 接入。
- 旧 position／mixed 命令和新 effort 主路线区分身份与准入，不改变旧证据含义。
- observation 构建后固定；动作输入变化须更新 schema／space，fixed-space consumer 不支持时明确拒绝。
- `BaseTaskEnv` 等保留名字按既有 2.x 约束处理，先迁生产 caller，不能创建第二套 reset／step。
- PickCube、NutAssembly 迁移按真实实现和 caller 收口，LIBERO 保留 benchmark 语义；不宣布全部任务已统一。
- 记录格式变化沿用已有 Recorder 和独立 reader；episode 配置、旧版本读取及失败行为有检查。

完成 3／4／5／6 阶段时更新对应 API 与迁移说明，7c 汇总。新示例只能使用已实现并验证的公共入口，不能以概念示例冒充已运行代码。
