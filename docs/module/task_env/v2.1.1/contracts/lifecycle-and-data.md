# 生命周期、时间与数据协议草案

状态：`DRAFT_FOR_DISCUSSION`；1c/1d 共同冻结。既有环境是生命周期唯一 owner，session／adapter 对原生资源负责，Recorder 消费同一运行边界。

## 构建、reset、step、close

| 时点 | 约束 |
| --- | --- |
| 构建 | 解析配置，汇总 physics／render／Controller 需求并准入；固定 observation 契约和 batch 布局；资源唯一归属 |
| reset | 验证请求；必要时重建执行资源；按任务初始化新 episode；校验 realized state，清空 Controller／相机历史并发布首帧 |
| step | 使用已选后端／solver／renderer／Controller；完成明确控制区间后发布状态、评价及同步观测 |
| render | 只消费公开状态或受控原生绑定；窗口和图像更新不自行推进任务物理时间 |
| close | 关闭自有资源并使数据失效；重复 close 可安全处理，失败与未释放项明确报告 |

这些是行为约束，不指定新增生命周期 enum。实现前对照现有环境／session 的实际状态机，避免第二个可变 owner。

## Reset 重建

切换使用任务初始化规则重新开始，不迁移上轮 q／qdot、接触、积分器、随机器内部 native state 或 GPU 图缓存。seed 由 Core sampler 与 provider randomness 分别记账；相同 seed 不保证跨 solver 轨迹完全相同。

先验证可静态判断的配置，再按照原生资源约束释放／创建。允许保留公共 env 对象并替换后端工作进程；不要求所有原生 runtime 在同一进程反复卸载。若实现只支持跨进程重建，应在能力中公开。

重建失败不得返回成功 reset 的 obs，也不得默认继续旧 episode。记录已完成阶段和清理结果，使环境不能 step；允许明确重新 reset 或 close。旧环境是否在纯 preflight 拒绝后仍可使用，须由 1c 明确；不承诺通用事务回滚。

原生批次统一配置；切换 backend／renderer 按整批重建。不换配置的部分 reset 仅对支持路线开放，保留其他环境的 episode、时间、Controller 状态与图像身份。对批内变更 Controller 的粒度，保持共同动作规格及已冻结资源约束。

## 时间与代次

公开数据至少能关联 execution／materialization、episode、reset／configuration 代次、环境编号、状态 revision 和模拟时间；控制区间、图像采样与异步完成分别说明。拓扑和对象映射变化不得复用旧索引。

Native 控制／渲染预热与真实用户 transition 分账。部分失败不生成伪成功 transition，不把未完成步计入完整 episode。既有 T transitions／T+1 boundaries 和 native interval evidence 继续使用，不凭窗口循环次数计算模拟时间。

## Observation 与缓冲区

构建后固定字段、结构、shape、dtype、单位、坐标、含义、相机标定语义以及对外数据设备约定。切换后的路线若需要改变这些约定，拒绝本 env 的该组合，或由调用方另行构建环境。

设备内部布局可以不同，经声明转换满足对外契约；设备转换成本和同步可查询。字段可以按需求投影，不能因统一就强制所有状态 host-copy。任何借用视图须明确只读、有效期、next step/reset/close 是否失效，以及调用方如何取得独立副本；不能悄悄改写已交付的历史 observation。

RGB 必需字段失败时不得以零图／旧帧补齐；缺失接触力等可选字段须有明确 availability。控制器输入 action 的变更另见[控制协议](control-and-feedback.md)，与固定 observation 分开处理。

## 批量终止与记录

6a 选择并公开支持的 auto-reset 语义，区分 `terminated`、`truncated`、终止观测和新 episode 首帧。记录 reset mask／env ID，保护同批次不同 episode；不要求同时实现所有 Gymnasium autoreset 模式。

每 episode 记录实际配置、任务／资产／source、provider／solver／设备、renderer、Controller／模型依赖、action／obs schema、相机参数和 seed。统一命令的接受回执与实测反馈分别存储。独立 reader 应能识别 episode 边界和输入规格变化，不为新功能新建平行 Recorder。

## 故障验证

工作包覆盖构建中断、reset 部分写入、step 部分推进、相机失败、窗口关闭、跨代数据使用、重复 close 及 worker 异常退出。具体错误结构与资源观测方法在 1c/1d 冻结；不要求为每个后端伪造不具备的通用原生快照回滚。
