# v2.1.1 协议实施基线确认收据

日期：2026-11-03。状态：`APPROVED_IMPLEMENTATION_BASELINE`。维护者已确认G01独立审阅及后续讨论，明确要求修改协议与后续Goal，再进入阶段2。本收据记录当前决定，不替换1a–1d原始交付／主审记录，不新算执行attempt。

## 来源与归属

- 本次输入：`develop@11b1e6c5bf8011acdc39f10449e2eb25764da92d`；GeoPhys pin／checkout：`67da1165149486d3ae3e779c13ce31af49e17d50`。
- 四个子阶段保留各自attempt001与有界设计审阅；本次只修订v2.1.1当前文档。既有raw reports、历史review、版本证据与未跟踪保护输入保持。
- “确认”指语义实施基线；生产版本值／签名由所属工作包在既有owner内落实。13个实现目标仍NOT_STARTED，9个最终PickCube格仍NOT_RUN。协议通过不等于运行能力通过。

## 确认决定与权威正文

| 决定 | 权威正文 | 后续owner／阶段 |
| --- | --- | --- |
| Robot可嵌套，声明受控通道与Controller binding；Panda8维输入→7臂力矩＋2手指关节力，closure仅内部中间量；保留source约束与可实现力域 | [控制协议](../contracts/control-and-feedback.md) | Scene／ControlGroup／canonical binding，3b、4a/4b |
| JointEffort／BodyWrench独立类型；typed其他载荷预留；多贡献显式组合，唯一提交authority不禁止有意叠加 | [控制协议](../contracts/control-and-feedback.md)、[physics](../contracts/physics-provider.md) | 4a冻结最小BodyWrench真实交集，4b执行，4c清旧episode贡献 |
| Controller只依赖Core公共state/model接口；模型库可替换、依赖与source明确，不直接使用live SDK或增加physics step | [控制协议](../contracts/control-and-feedback.md) | 4a/4b |
| 同一public Env在reset切backend／renderer；可内部隔离依赖及重建session/worker/App；有限验证组合不成为永久profile白名单 | [生命周期](../contracts/lifecycle-and-data.md)、[render](../contracts/render-provider.md) | 3a/3c、5c、6c |
| Core sampler显式seed重置、None继续；preflight拒绝不消费当前流；provider RNG按派生seed新建而不迁移私有状态 | [生命周期](../contracts/lifecycle-and-data.md) | 3c、6c |
| task cadence与native dt分清；旧Timebase codec/hash精确保留；不同native dt需显式版本化执行映射 | [统一表示](../contracts/unified-task-representation.md) | 3a/3b |
| 资产数值三层准入、required未测不通过；cube约5%惯量差保持待核对 | [physics](../contracts/physics-provider.md) | 3b |
| 公共API保持配置直接；receipt/lease/generation由内部形成；三项目标窗口／RGB／同步obs与原定资源、数据和故障规则保留 | [render](../contracts/render-provider.md)、[API入口](../api/README.md) | 3–6 |

结构化新增[控制案例](../planning/control-command-cases.json)仅为设计检查。Scene-v4／ExecutionSpecV2等是建议版本标签，旧codec/hash不原地改语义，不预先承诺完整非刚体DSL。

## 顺序与下一动作

保持7阶段／22子阶段及原依赖：2a失败归因→2b当前控制链修复→2c参考冻结→3后端→4控制→5渲染→6并行→7集成。2a不实施新effort／BodyWrench或跨路线重建；R3导致失败仍是待验证假设。若必须提前后续公共能力，带证据提出最小依赖调整，不能私自重排。

下一包只包含2a，由维护者转发一个Terra或Luna主代理，报告后停止并待主审。当前文档窗口不运行implementation tests、native、physics、GPU或窗口；不自动发送任务、push、merge、改tag或发布。

## 本次文档检查

- 文档validator：0 errors、0 stale path references；96项既有历史链接问题保持。
- 7阶段／22子阶段依赖及既有attempt历史不变；五协议采用已确认基线；4组planning案例为9／10／12／12项，JSON可解析。
- 13个implementation targets、9个final cells的实现／验证／证据字段未提升；只更新相关planning limitation。
- GeoPhys gitlink与checkout、两份未跟踪保护输入hash不变；历史review和raw证据未编辑。
- `git diff --check`通过；native、physics、GPU、窗口启动及implementation tests均为0。两份Skill只同步当前文档状态。
- 自动审批曾拒绝用HEAD内容收口representation案例JSON格式；该操作未执行。保留当前JSON内容／排版，只读比较确认除document_status外与原语义一致。

本次检查仅证明文档一致性，不是协议实现或任务成功证据。下一步2a单包由维护者手动转发；当前窗口没有执行它。
