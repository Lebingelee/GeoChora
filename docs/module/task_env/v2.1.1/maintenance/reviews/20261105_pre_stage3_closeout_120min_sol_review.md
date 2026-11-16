# 阶段3前置核心收尾：Sol复审

决定：**ACCEPTED_BOUNDED_PRE_STAGE3_CORE_CLOSEOUT**。接收维护者限定两小时窗口的C1、C2、V，结束本次前置核心收尾；不将原宽范围的所有整理与未验证路线改成PASS。阶段3尚未启动。

审阅输入为`f3650a7520e96e392758a9605d86d513c819a469`，返包为`99de88abd6d3f464de0d5c9c98362813f52252c9`，包含`cf425acc`、`b6ce2372`两项实现提交及报告。开始复审时develop与返包一致、tracked clean。依据[本轮规划](../../planning/pre-stage3-environment-refactor.md#pre-stage3-closeout-120min)、[执行报告](20261105_pre_stage3_closeout_120min_001.md)、实际diff和原始结果作出本决定。

| 项 | Sol判断与依据 |
| --- | --- |
| C1 核心职责 | **有限通过**。`materialize_control`删除`selected_solution`参数及Nut Solution反向导入；保留source、Controller、频率、feedback等准入。具体Solution类型、配置、来源与时间检查归Nut任务binding。R05b普通构造／reset不持有Solution，兼容专家仅按需创建并经任务侧校验；调用方act／step／observe有100／500 Hz正例。已接受的唯一Env生命周期保持；未新增诊断探针或替代factory |
| C2 当前文档 | **通过本窗口范围**。任务开发指南按真实Marker／Nut示例定位声明、reset、评价、action／observation binding与Solution，使用公共make_env；不让开发者手写SHA。Env／Solution说明和安装导航对应当前接口，区分新克隆与已有安装，未把内部binding、新安装或任意provider称为通用已验证能力 |
| V 受影响行为 | **有限通过**。核对执行者182 passed／1 deselected原日志；Sol在返包HEAD独立执行针对性R05b文件，**25 passed、1 deselected**，使用现有禁止native导入的guard。排除项是跨任务真实provider测试。新增独立物化正例与任务端错误Solution负例对应职责迁移，不是单纯删除旧检测；控制器与反馈保护保留 |

## 原生证据及复用边界

- 核对`cf425acc`的Nut MuJoCo CPU原运行结果和同次`reader/readback.json`：2377 transitions、2378 boundaries、11885 native substeps，任务／Solution成功，T+1、时钟与target ack检查PASS；H5摘要为`c8985c02448ab935e846c0f0330ff6c8389e4d5ed34ec3fc4703433be59d61e8`。Sol只读核对这些结果，本轮未重跑物理或reader。
- `cf425acc → b6ce2372`的生产差异仅在R05b专用构造／reset和按需兼容分支；普通MuJoCo执行路径不变，文件来源摘要会变化。接受按该差异说明引用原Nut运行，不重标为新HEAD生成。
- PickCube任务／控制实现及本次实际执行分支未变；`5a04140a`的seed31成功及reader按原身份复用。三个旧任务的组件分支也未改，保留原短检查身份，不为此次文档或不相关分支重跑。
- R05b新caller路线真实GeoPhys provider、新安装、Isaac／GPU、并行／RGB、D0与Qualification没有因本决定通过。R05b两档反馈当前支持的是无引擎契约结果，其后原生验证按对应后端工作安排。

Sol的针对性检查及文档检查日志位于ignored `workspace/maintenance/v211_pre_stage3_closeout_120min_001/sol-review/`。当前文档检查为0 errors、0 stale paths，96条历史链接问题保留；实现diff及复审文档的`git diff --check`通过。本次复审不运行宽矩阵、不重新审计历史资源，也不因剩余helper／历史诊断／完整安装矩阵延长维护。

环境类多路线编排和更广的整理仍可后续改善，但不再是本次C1／C2／V出口。原R1有限接收、旧失败及原始报告保留；本决定关闭限定的前置核心范围，不宣称整个仓库已彻底重构。后续可另行准备阶段3分支及G03/3a包；本轮未创建分支或派发执行，3a–3c仍为PLANNED。
