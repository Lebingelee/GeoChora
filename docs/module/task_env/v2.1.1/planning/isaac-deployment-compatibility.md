# Isaac部署兼容：v2.1.1与后续版本范围

3b attempt001 已完成一条6.2 pip环境的真实F06短程运行与同次读回，但 N08 失败，整体待 Sol 复审。6.1 仅有离线兼容检查；维护者后续告知已有6.1独立安装，本次依其先完成当前目标的顺序未启动该安装。详见[3b attempt001执行摘要](../maintenance/reviews/20261105_3b_attempt001_execution.md)。

2026-11-05，Sol按维护者反馈及版本化官方资料核对后的仓库实施规划。此页规定G03后续包的版本范围；当前实现／原生证据仍查[能力矩阵](../capabilities/README.md)。当前源码尚有6.2精确门和回执字面量，不能把本页写成已支持。外部反馈调整单保留完整维护者需求和逐项验收，此页是仓库内执行入口。

| 版本 | 本次安排 | 真实运行证据 |
| --- | --- | --- |
| 6.2.0／发行包6.2.0.0 | v2.1.1保留既有PhysX state-only路径并修部署可移植性 | 仍须按3b授权从公开入口形成构建→reset→step→状态→记录读回→close的有界结果 |
| 6.1.0／发行包6.1.0.0 | v2.1.1实现与6.2共用adapter、部署选择、真实版本回执及同USD／closure消费 | 本机未安装；native保持NOT_RUN，离线实现／接口对照与真实运行分列；安装后做同资产单个代表闭环，不先要求完整多任务矩阵 |
| 5.1.0 | 后续版本适配，未指定具体发布号 | 当前不安装、不提前宣称兼容；需初始化／推进／生命周期公共API映射及真实验证 |
| 其他／未知 | 不自动扩权 | 明确unadmitted或unknown及原因，不猜测版本 |

## 版本差异依据

已对当前路线选取40个公开接口条目逐项比较。6.1和6.2对应条目均存在；规范类型别名、空白与尾逗号后，参数／默认值／返回类型表达一致，支持复用现adapter的可行性判断，不是SDK全接口／ABI等价证明。参见[6.1 prims](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/py/source/extensions/isaacsim.core.experimental.prims/docs/index.html)、[6.2 prims](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/py/source/extensions/isaacsim.core.experimental.prims/docs/index.html)、[6.1 manager](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/py/source/extensions/isaacsim.core.simulation_manager/docs/index.html)和[6.2 manager](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/py/source/extensions/isaacsim.core.simulation_manager/docs/index.html)。

[6.2发布说明](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/overview/release_notes.html)记录Kit 110.3→110.4、DOF getter独立数组、update_app重入限制及质量getter不再补写缺失属性。当前有序同步worker、即时owned value投影和required物性声明／readback是有界复用方向；不据此分叉Env／Controller或复制所有资产。Newton／传感器／Cortex等非当前调用变化不自动扩大PhysX state-only实施范围。[6.1资产结构](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/robot_setup/asset_structure.html)已有UsdPhysics／PhysX及mimic示例，同资产复用有依据。

5.1的[manager参考](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/py/source/extensions/isaacsim.core.simulation_manager/docs/index.html)使用step(render=False)，6.1／6.2则使用steps／callback／update_fabric；5.1公开参考未列出当前setup_simulation等入口，需查明公共替代。[5.1 utils](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/py/source/extensions/isaacsim.core.experimental.utils/docs/index.html)也未列出当前play／stop／update_app组合。不能说5.1所有控制接口都不存在；延期依据是当前调用链确有不同的初始化与推进边界。

## v2.1.1的有界实现

- 路径／launcher：Core常规入口默认当前sys.executable；Isaac显式选择pip Python或SDK官方python.sh，统一CLI／环境／部署配置的优先级与冲突检查。复用现有launcher／3a transport；不直接运行Kit内部python，不把整个stdout当JSON，正确传递空格路径及argv，回执报告实际worker解释器。
- SDK识别：在原provenance／App owner集中核验pip metadata或绑定所选SDK根的VERSION／公开版本信息。缺pip distribution不等于缺App SDK；不能按目录名猜版本。分别报告环境缺失、版本未准入、required接口／schema缺失和native未运行。
- 共同接口与回执：在既有admission／native IO owner集中表达6.1／6.2共同要求，协调真实版本的生产者和校验消费者，包括App owner、native metadata和驱动回执；不能只删除==6.2.0.0守卫。沿用既有值和codec，旧6.2历史身份与旧F04/F05候选不自动扩权。
- 资产：优先消费完全相同的USD文件和依赖closure，不按minor版复制／重导出。内容hash描述资产，实际SDK／runtime身份另记；仅当具体API／schema或载入结果证明不兼容时再安排最小转换。旧证据不重标版本。
- 文档：实现完成后同步当前README、安装／已有安装指南、TaskEnv开发指引、API语义、矩阵、恢复页和相关Skill；不能先把拟议参数写成可运行接口。

## 实施顺序与验收边界

当前3a已独立接收，[3b attempt001完整包](stage3-3b-execution.md)已执行，结果待Sol复审。消费级依赖按实际host／engine／solver与worker角色判断；Core host安装清单不直接等于Isaac worker必需清单。真正required缺项继续拒绝，不能用未选GeoPhys/Taichi路线依赖误报SDK缺失。维护者已澄清GeoPhys原生solver不消费其MuJoCo求解路线依赖；本包在原preflight owner修正，不改pin或混装环境。以下早期协调顺序保留历史。

3a attempt001按原包复审，新增反馈不倒加门。attempt002先修普通reset闭包与原能力／worker缺口。3a独立接收后，3b完整包先纳入上述路径、SDK识别、6.1／6.2共同接口与准确身份接线，再在单独授权的native预算内验证三路线。不得以本规划开启3b、安装或native。

离线门覆盖两种部署、带空格路径、参数转发、pip缺失但SDK有效、SDK与版本不符、未知版本、required API／schema缺失、真实版本贯通及旧codec／资产hash兼容。正例通过既有生产consumer，以外部fixture替代SDK，不以目录名或伪版本自证。6.2按3b实际可用环境完成原门；6.1无本地SDK时实现和离线检查可先完成，运行层单列NOT_RUN，不能声称已验证支持或因此把实现推迟到未来版。旧F06启动18步只代表所属历史基线，不硬套所有SDK。

后续5.1复用同一配置、Env、Controller、Session、Recorder和资产owner，先定位实际公共替代API，再用同资产运行单个完整代表闭环；只有具体不兼容证据才改资产。暂不引入第二套provider骨架、全量render/batch矩阵、额外转换链或泛化版本框架。

调研原始材料在主工作区 `feedback/20261105-isaac61-62-interface-research.md`、40项comparison JSON及sources收据；完整维护者需求为 `feedback/20261105-isaac-deployment-portability.md`。它们的绝对路径和摘要随下个正式实施包冻结，不复制为第二份资产或运行证据。
