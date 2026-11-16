# G03/3a attempt003前重评与最后窗口安排

2026-11-05，Sol。重评输入为`codex/v211-stage3@e200faad15f2f086344da90930ef7d705af57173`，实际实现仍为`42dfcda57757d6d14bd963f692f6bd9154a974f3`。本页是投放前分析，不是执行报告或实施完成声明。当前3a已执行2次；未准备或派发attempt003，没有新writer／native。

## 三次规则与历史依据

已检索现有[geochora Skill](../../../../../.agents/skills/geochora/SKILL.md)和[Goal编排流程](../../../../../.agents/skills/geochora/references/goal-orchestration.md#mandatory-reassessment-before-attempt-3)。普通子阶段最多三次，第三次前必须合并实际失败证据、调查可复用实现、确认根因与原验收可达性；[Phase II-01执行表](../../v2.1.0/history/phase_ii_01/07_Execution_Order_and_Acceptance.md)记有R06b第三次前重评及最后有界修复的先例。

维护者本次重申的硬规则已收紧到Skill：**003是最后一次普通attempt；若3a整体仍未接收，必须停止普通执行并进行人工诊断。**不能换名、开新对话或称局部PASS来自动进入第四次。诊断的组织和后续授权由维护者决定，Sol不自动创建／发送对话。人工诊断是失败后的停止点，不应成为每阶段常规流程。

## 两次窗口说明了什么

| 窗口 | 实际结果 | 对003的含义 |
| --- | --- | --- |
| attempt001，40ca5d56→32397283 | 有配置／assessment／worker接线，但普通source无新预检要求的receipt，合法reset被拒绝；嵌套／typed及build检查覆盖未闭合 | 主要是生产consumer未接通、资产读取限制被过度解释，并非证明provider缺少普通任务能力 |
| attempt002 revision2，81e257cb→42dfcda5 | 维护者改为runtime-first后，真实PickCube31／Nut19各完成MuJoCo CPU创建/reset/10步/close；Sol有界接收核心恢复 | 不是同一核心故障连续两次修不动。002刻意先恢复主路，剩余3a没有在该窗口全面实现，不能把未实施都叫作新失败 |

保留[002独立复审](../maintenance/reviews/20261105_3a_attempt002_sol_review.md)和原生证据。003不重查G02、前置维护、Panda资产库、旧codec、108项或历史大组，也不因报告完整性重复物理运行。诊断规范及7a集中整理安排不变。

## 当前代码中的真正缺口

已按AGENTS先用CodeGraph，再读漂移源；未运行SDK或物理。

| 缺口 | 当前owner／事实 | 选择的最小修复 |
| --- | --- | --- |
| 需求汇总不完整 | `api.assess_selected_request`主要遍历Artifact required和固定CONTROL_REQUIRED，只从position profile取StateRequirements；已有`ControllerBindingV1.feedback_requirements`、ControlBindingPlan、Scene robots/control_groups和逻辑assembly resolver没有成为完整的请求投影来源 | 在现有admission/control owner汇总**实际存在的声明**；旧scalar从现有Artifact semantics/source/Controller声明投影，versioned路线复用已编译binding／StateRequirements，不设计第二套nested模型或配置语言 |
| pending凭通用函数名 | row默认将provider_api设unknown；`CapabilityAssessmentV1.decision`凭三个构造函数名白名单允许pending，缺少“此对象由哪个实际检查验证”的联系；Core的scalar/state-only限制也走同一默认 | 静态能判定的Core条件直接判定；仅对本请求确需原生确认的项记录对象、具体adapter检查及成功／失败条件。保留声明／依赖／Evidence分维，不能把未知转成已支持 |
| 构建检查已有、结果未与请求关联 | MuJoCo构造中已有`_addresses`和body/site/actuator具名映射；GeoPhys构造、public boundary与source import已有映射；IsaacNativeRuntimeIO构造和`_read_views`已有USD路径／DOF及状态检查 | 复用或抽出各adapter中的小型具名layout检查helper，让生产构建实际消费并回报；与同一request绑定。无需通用注册服务、oracle框架或逐SDK全API表，也不能只在文档填方法名 |
| typed／嵌套范围容易越界 | 当前RequiredCapabilitySet vocabulary尚无完整BodyWrench／TypedLoad语言；ControlGroup／StateRequirements／逻辑assembly已有部分表示，真正typed执行由4a/4b落地 | 3a验证已有表示的需求求交，并准确拒绝不认识／未实现的required请求。未知schema与provider不支持分别说明，不为“覆盖”在003提前实现施力或新表示 |

这是同一个“声明→assessment→具体build检查→回执”的接线问题，应在一个最后窗口整体闭合，不再分成多个只完成局部的返包。缺安装与代码缺口分开：GeoPhys依赖冲突和Isaac SDK不可用是既有事实，3a验证环境选择／正确拒绝及离线接线；真实三后端执行和物性readback仍属3b，不能倒加为003门。

## 官方与开源实现调研

| 来源 | 可采用的做法／适配性 | 不采用的部分 |
| --- | --- | --- |
| [MuJoCo官方named access](https://mujoco.readthedocs.io/en/stable/python.html#named-access) | 按真实model对象名建立joint/body/site/actuator映射；当前Core已有该调用方式，002的3.8.1运行证明本地调用可用 | 网页stable并非冻结3.8.1合同，不按最新文档升级依赖，不借一次constructor成功宣称全部能力正确 |
| [dm_control named indexing源码](https://raw.githubusercontent.com/google-deepmind/dm_control/main/dm_control/mujoco/index.py) | 名称与shape／DOF映射来自实际模型，缺名自然报错；Apache-2.0。借鉴模式，复用Core原映射，不复制源码或增加依赖 | 不引入dm_control／Composer作为新runtime／nested系统；它不提供GeoChora三后端专用assessment |
| [Gymnasium passive checker](https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/gymnasium/utils/passive_env_checker.py)及[MIT许可证](https://raw.githubusercontent.com/Farama-Foundation/Gymnasium/main/LICENSE) | 从外部消费真实reset/step返回值，按实际接口验证。符合本仓库诊断不侵入核心的方向 | 它不证明provider能力或物性；不把其全量checker接为新的前置验收平台，不照搬最新main新增检查 |

另检索上游issues，未找到可直接替换本项目这段request-specific准入接线的修复。无证据把当前问题归因到上游solver或SDK；不开展求解器调参。上述源码是比较依据，新增库／vendor复制为0。先前Isaac6.1/6.2逐项调研继续复用，其适配实现按[独立规划](isaac-deployment-compatibility.md)交3b，本页不重复调研或扩入003。

## 003的整体出口

目标是**完成原3a剩余准入接线并给出可独立接收的整体验收结果**，不是再交一个局部CORE_PASS。验收范围仍是[Goal03/3a](../goals/03-backends.md#3a)与原20case；只对受影响部分产生新证据：

1. 实际task/source/Controller／已有嵌套通道／state声明进入同一请求；漏项、错Frame或未实现required不能静默忽略，optional保留原因。针对真实缺口选少量生产consumer正负例，不构造全对象矩阵。
2. required unknown没有准确检查时拒绝；有检查时仅pending。生产build确实调用该检查，失败阻止交付正常session；成功只回报其实际检查结果，不升级物性、Evidence或Qualification。
3. 三条冻结route走同一配置／metadata／admission入口，环境不可用准确拒绝；无SDK离线fixture只替换原生API终端，不能绕过source、需求汇总或实际检查helper。
4. 查询、info、Recorder metadata记录同一请求与assessment，JSON／既有H5 metadata读回一致。static、build事实和未知native readback分开，不因回执字段更新重跑完整轨迹。
5. 若改动影响MuJoCo构建／reset／admission，源码稳定后做一次PickCube31与Nut19各10步的真实CPU回归；这是验证本次变动，不重复002原记录。仅文档／未受影响代码沿用002证据。旧codec不变就不重测，worker cleanup不变就直接复用。
6. 逐原20case给本次通过／有效旧证据引用／明确3b或4a阶段归属。3a自身required不能以NOT_RUN或另阶段标签掩盖；3a本就允许的provisional build合同不等于3b物理已通过。

## 调度、预算和投放决定

**可行性结论：有可信的最小实现路线，适合进入最后完整包准备；目前未封包、未投放。** 投放前由Sol固定实际声明来源、每组检查的生产消费点和上述完整出口，不把空白设计留给执行者，也不承诺必过。若核实有真正必需的外部输入／公共API缺失，先报告并解决，不先消耗第三次。

预计主动90–120分钟、总墙时180分钟。一个writer、沿现阶段分支；0–10分钟一次输入核对和直接方法阅读，10–70分钟完成共同接线与聚焦检查，70–120分钟离线生产consumer及必要CPU回归，120–150分钟针对失败修复，150–180分钟最终最小验证／文档／提交／返包。一次失败在同窗口修复，不因单个测试失败另算attempt或立即返包；不做新一轮历史审计。

拟沿002包络：全部验证累计60分钟、必要MuJoCo CPU累计30分钟／2000物理步、单组15分钟、RSS8GiB、输出256MiB；无新安装，GPU／Isaac App／GeoPhys native／render为0。预算及准确输入将在实际完整包冻结，不继承旧维护／工具累计时钟。Sol本次仅分析／文档，native为0。

003结束时只能是：原3a出口满足、提交Sol独立审核；或整体未过／外部阻塞，停止普通执行并进入人工诊断。不能以局部PASS再派“003补包”掩盖耗尽；真正同窗口内修复不另计attempt，窗口结束后不自动续时。诊断交接只需三包／当前HEAD、已接收证据、精确未决owner和根因假设、最小验证方案，不再次搬运全历史。003通过也只解锁3b的后续包准备，不自动启动3b或阶段4。
