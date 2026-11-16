# G05 5c 单元 9：Sol 综合主审与功能有界接收

日期：2026-11-11。主审结论：**`SOL_ACCEPTED_BOUNDED_5C`**。单元 9 综合交付接收，修订后的 5c 功能在下述实际受测交集内有界接收；维护者最终接收仍待确认。执行者提交为 `b23fb3cc5b1fdfd2699a177c9916019583d63b5c`，生产实现为 `a53bf19d2526c6c336dd5d0d7108eb0f643f80bd`；GeoPhys `c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7`、Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。

本次是对执行者单元 9 交付的独立核对，不把其自评直接改成通过。Sol 曾参与前序设计、前置修复及主审，本记录不声称整个实现由从未参与项目的第三方审查。本次只读代码、Git 和保存证据并更新接收文档，未启动 native、解析任务资产或重跑物理矩阵。

## 原出口与综合判断

| 门 | 主审结论及实际范围 |
| --- | --- |
| G1 四主体与共同控制 | 一体 Panda、装配 Panda、Pendulum、双轮车的受测公开构建、reset、非零 step、state/clock、close 成立。共同主体／Assembly、Controller 绑定、scene interval 和 Runtime owner 按单元 4 最终更正、单元 6 真实证据及后续 diff 复用；公开装配 Panda arm/hand 双 Controller 有共同 interval／资源证据。不声称四主体在 a53 全部重新运行。 |
| G2 provider 与任务语义 | Pendulum、双轮车在 MuJoCo CPU、GeoPhys CPU、Isaac 6.2 PhysX CUDA 固定派生资产上的短程路由有界接收。单元 7／8 后续改动集中 F06 图像／状态链，不改变简单主体的 effort port 施控及步进算法；不是任意 USD 或任意任务准入。 |
| G3 同步任务 RGB | 复用已独立接收的最新 Isaac reset／非零 step／第二次 reset 三帧及关闭；MuJoCo、GeoPhys 原生旧证据按 source、factory 与公共发布变化复用。当前 RGB 使用独立 publication，不再以 Panda Position profile 决定是否发布，不替换 Controller typed_state。 |
| G4 固定 renderer 与跨组合 | 构建时选择 renderer、保持至 close；reset 可重建同种资源。最新 GeoPhys CPU physics × MuJoCo renderer-only 真实状态映射、同步 RGB、pose 独立读回和零 MuJoCo step 证据成立；不代表完整自由组合。 |
| G5 施控、时间及生命周期 | 历史同初态同动作对照与当前共同控制／独立 renderer publication、采集前后进度、callback、旧 episode／fault／owned-frame 合同共同支持受测范围。不能将历史成对记录称为最终代码成对物理重跑；也不要求跨 provider 轨迹逐点相等。 |
| G6 兼容与 G06 准备 | 当前相关 diff 未改变既有 Controller reset、scene interval、重力算法或 seed sampler；selected reset 的图像后置与清理已在最新二次 reset／合同中覆盖。原 3c／4c 与已受测重力范围保留。标量 episode、boundary、clock、generation、RNG 与 buffer ownership 可作为后续设计输入，尚非 batch／并行验收。 |

这些结论对应[原 G05 目标](../../goals/05-rendering.md)、[render 协议](../../contracts/render-provider.md)、[生命周期／数据](../../contracts/lifecycle-and-data.md)及维护者修订的统一主体要求。不是把九个单元的 PASS 相加，也不把类名相同当作共同生产链的证明。具体 Controller、位置与力矩的不同 lowering 仍合法；当前 candidate 配置消费共同生命周期的受测功能可接收，普通用户入口和所有兼容代码的最终归并另外收口。

## 本次独立验证

- 核对 `b23fb3cc` 仅改三份文档；其 `task_env` tree 与 `d6e9865a`、`a53bf19d` 完全相同，为 `c4460cd6bcc96a16067d3f61556a66e52da23bbc`。
- 交付 manifest 的 14 项大小／SHA-256 全部匹配；清单 SHA-256 为 `0ed7aec32275b5446b8bd7e3ecbc426c6b9dd9b05ea51853d07f548a496a7ce3`。36 项主要证据哈希核对通过，其中本包改动的目标／路线图按输入 HEAD 原字节核对，而非要求旧哈希等于修改后的文件。
- 独立重算四组历史比较 summary，每组 13 个边界的 action、clock、control step 与 joint-position 比较成立；这只是保存比较记录的核对，不是再次测量物理。
- 核对最新 Isaac 3 次、cross 2 次采集记录：各自同次采集前后可观测进度一致，physics callback 安静，MuJoCo 采集步进为零。原始三帧、pose 与实际运行代码关联复用[单元 7／8 独立主审](20261111_unit007_008_sol_review_a53bf19d.md)，没有重复其 684 文件／24 项守卫合同或启动新引擎。
- 阅读单元 4 最终复审更正、单元 5／6 主审及当前相关 reset、source、Controller 匹配、factory 和 capture diff。CPU 原生相机的旧成果结合当前 adapter／publication 影响继承；不外推为每个 Controller 的最终 RGB 实测。
- 保护文件及用户优化台账哈希、两个 pins 与输入一致；单元 9 无 native／GPU／GUI／物理执行或锁占用。文档检查的已知保护日志历史基准差异及历史链接问题不新增为技术否决项。
- 本次三份主审／状态文档的 34 个本地链接目标存在，`git diff --check` 通过。文档检查器仍只报既有的 `MUJOCO_LOG.TXT` 历史保护基准错误和 96 项历史链接问题；没有修改该保护文件或检查器基准。

交付定位：[报告](../../../../../../workspace/maintenance/v211_g05_5c_unit009_execution_20261111_001/report.md)、[逐门证据与复用依据](../../../../../../workspace/maintenance/v211_g05_5c_unit009_execution_20261111_001/gate-evidence.json)、[清单](../../../../../../workspace/maintenance/v211_g05_5c_unit009_execution_20261111_001/output-manifest.json)、[释放记录](../../../../../../workspace/maintenance/v211_g05_5c_unit009_execution_20261111_001/release-receipt.json)。主线工作文档 `reviews/V211_G05_unit9_b23fb3cc_audit/` 保留本次标准库 reader 与结果，不修改执行者原包。

## 限制、历史失败与下一停门

保留 COM 原 `1e-5 m/s` 判据 FAIL、维护者对受限偏差的认可、原 N08 FAIL；新 R05c 候选仍 `NOT_REQUALIFIED`，56 条外层 target 哈希仍是事后关联，不转移历史资格。启动／reset unknown、旧预算和预约偏差、早期失败及关闭限制按各原记录保留，不要求通过重跑追补合规。

Isaac RGB 限受测 F06／headless／world-mounted camera；颜色不等于原色／素材色域完整校准。重力默认关闭与已支持的 MuJoCo 一体 Panda 交集不扩大；effort 显式 profile 的单 writer／subject 限制不等于装配 Position 双 writer 失效。不宣称任意嵌套、任意组合、动态 renderer 切换或通用闭环完成。

**5c 功能、代码优化、项目优化必须分开结论。** 本次没有发现需要新增 native 才能闭合原 5c 出口的直接矛盾，故不增加像素评分、轨迹一致、启动零步、全矩阵或全库保护镜像测试等门。原 5a／5b 的有界结果及维护者人工图像接收按影响继续有效。

依[后续优化台账](../../planning/post-5c-code-project-optimization-diagnostic-ledger.md)，正式入口归并、职责／registry 简化、剩余探针与兼容清理、优化范围的完整 Solution 复验、证据与分支／worktree 整理仍未完成。它们不是本次功能否决项，也没有被本次接收顺带批准或标成完成。等待维护者接收本次功能结论并安排优化；优化及人工接收完成后才决定进入 G06。本次未自动启动任何后续 Goal。
