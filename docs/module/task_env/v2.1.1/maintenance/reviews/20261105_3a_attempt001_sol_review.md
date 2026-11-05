# G03/3a attempt001：Sol 独立复审

2026-11-05。决定：`REWORK_REQUIRED_3A`，attempt_count=1。实现保留为返工基线，3a未接收、不可部署；3b／3c未开始。G02及前置核心有限接收不变。

## 输入与核验

原包 `V211_G03_3a_attempt001` 输入 `40ca5d56153b9e13848b20c2af550c1efe076b98`；执行输出 `32397283e635148788848c0c009e5223d40333df`，分支 `codex/v211-stage3`。Sol在执行者返包并释放写入窗口后核查29个修改文件、原包8个成员、输出manifest中29份源码和52份产物；字节摘要及commit patch摘要全部吻合。两个保护untracked字节和两子模块pin吻合，tracked clean；未改执行者原始报告或manifest。

已按AGENTS先使用CodeGraph，再读漂移或未索引文件的当前源码。审阅共同配置→selected reset→preflight→原Session／worker→控制转发→info／Recorder链。新代码不是新的Env／physics生命周期；但正常caller接线尚有以下阻断。

## 必须修复

| 项 | 实际证据／owner | 结论和返工要求 |
| --- | --- | --- |
| R1：普通reset回归，P1 | `runtime/sessions/api.py:1402` 强制receipt；PickCube和Nut普通source仍不提供该证明。Sol经公开make_env→reset分别复现，MuJoCo依赖available时均capability_rejected，native materializer／旧session.close／camera.close均未触及 | 原B02/C02/D01/E02未闭合。为真实source建立有界、可消费的闭包证明；不能删除所有闭包检查、伪造digest或给普通任务加豁免 |
| R2：required unknown检查过宽，P1 | `artifacts/contracts.py:1870`仅白名单三个通用函数名；`api.py`对多种能力统一赋 `_materialize_admitted`，未逐项绑定实际检查／结果 | B06未过。每个pending required项必须有准确的能力／对象检查、输入身份、失败条件及构建消费点；原生后验证未做仍unknown，不能把通用构造成功当作所有能力已兑现 |
| R3：嵌套／typed及具名绑定不完整，P2 | `api.py:1435`只查7＋1数量，StateRequirements只遍历position profile。独立测试将所有scalar actuator和Frame目标改为不存在的名字，assessment仍与原值完全一致 | B03/B04未过。按实际Scene／Robot／Controller声明遍历具名通道、model/Frame/state和typed load；可静态判定的缺项立即拒绝。阶段4未实现的JointEffort／BodyWrench只准确评估／拒绝，不在3a实现施力 |
| R4：错误worker回复未清理，P2 | `transport.py:317`等直接对JSON结果 `.get()`；合法JSON数组触发AttributeError，未进入协议错误清理。独立fake进程复现子进程仍存活，随后由Sol检测器显式回收 | C04不能按现有证据全部通过。验证ready/result/callback等消息形状和字段，转成协议错误并关闭连接／进程树；补格式错误、EOF、超时、回调失败及重复close的有界负例 |

R1现成owner包括 `RuntimeSource`／`ExecutionSourceReceiptV1`、`source_asset_bytes`、MuJoCo已有receipt lowering、GeoPhys `source_closure_digest_for_import`／imported dependency校验。既有collector对绝对路径和include有明确限制，不能直接把当前生成MJCF的路径当作已覆盖。应只遍历本次source真正引用的文件，确定root／logical path／alias和字节上限，并让实际importer消费相同字节或核对实际dependency。**定向解析、读取和必要的小型快照是实现闭包的授权工作；禁止的是全库扫描、整库复制或另造资产缓存。**本地引用能解析时，不把代码接线缺口误判成维护者缺资产。旧canonical XML、Artifact／Scene／Timebase及历史运行身份保持；必要的importer XML lowering须单独有身份并与canonical关联。

## 验证与逐门判定

Sol新增四个无引擎缺陷检测在parent／fake child均阻断SDK导入的条件下运行，结果4 passed，分别确认两条公开reset回归、具名映射未区分和错误回复存活进程。这个pass是**缺陷复现成功**，不是产品验收。前两次协议检测被沙箱禁止继承socket fd挡住，未产生产品结论；在批准的短时fake进程环境重跑后确认缺陷，进程已回收。8组旧codec oracle由原输入提交源码重新生成，与返包fixture完全一致。

| 原门 | Sol判定 |
| --- | --- |
| A 配置／兼容codec | PARTIAL；共同配置、strict字段、旧8组codec有证据；三条真实source／Controller完整交集仍未闭合 |
| B 能力交集 | FAIL；R1/R2/R3，required unknown不可按通用函数名放行 |
| C 环境／worker | PARTIAL；真实MuJoCo版本冲突及来源约束有离线证据；普通生产路由阻断，R4新增清理缺陷 |
| D 查询／Recorder | PARTIAL；拒绝回执、JSON和替身读回有证据；现成功路径使用显式closure绕过，不证明普通生产路径可用 |
| E 副作用／回归 | FAIL；拒绝先于close值得保留，普通reset回归必须修复 |
| F 交付 | 有界材料核验通过；资源账本有报告所述限制，不能反推未计量的active/wait或native能力 |

Terra最终108 passed、1 deselected按原报告保留；被排除的真实provider node不在本包授权内。不能把这个总数视作E02通过，也不要求为修复3a先运行native。worker成功使用fake session和测试专用closure绕过；这些旧测试不作为后续正常闭包正例。命令账本42项，保留3次失败；94.615秒是所记命令合计，80.9分钟是窗口墙时，主动／等待时间未分别计量。文档validator零错误及96项历史链接问题按执行者日志引用，本轮文档检查另存。

## 后续安排

准备 `V211_G03_3a_attempt002`，只修R1–R4并补齐原20项验收映射，使用同一阶段分支；由维护者指定一个Terra／Luna手动转发后才执行。准备不增加attempt_count；attempt2实际开工才计数。预计主动120–150分钟，总墙时180分钟，含验证、报告和等待；native import/init、physics/GPU/render/App为0。不以重复宽矩阵或全库资产工作消耗窗口。第三次前若仍未闭合，先执行既定根因与可行性重评。

维护者另行批准的Isaac 6.1／6.2兼容及5.1延期范围，见[兼容规划](../../planning/isaac-deployment-compatibility.md)。它不追溯增加attempt001验收条件，也不塞入此次回归返工；3a接收后，3b完整包必须先含该有界实现，再执行获授权的实际三后端验证。6.1未安装则native结果保留NOT_RUN；不能借此继续把6.1实现永久拒绝。现存诊断耦合仍按原安排在7a集中处理。

原始执行证据在Core ignored `workspace/maintenance/v211_g03_3a_attempt001/`，执行摘要见[Terra返包](20261105_3a_attempt001_execution.md)。Sol独立检测、命令及身份核验在主工作区 `reviews/V211_G03_3a_attempt001_sol_review/`；新包snapshot将冻结这些外部资料字节。本次Sol未运行任何原生引擎、物理、GPU或Isaac App，未发送其他对话消息。
